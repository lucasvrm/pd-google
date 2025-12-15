"""
Tests for Gmail integration in the Unified Timeline API.

Tests verify that:
- Lead contact emails are correctly extracted for Gmail search
- Gmail emails are properly normalized to TimelineEntry format
- Graceful degradation when Gmail fails
- Company domain matching works correctly
"""

import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from database import Base
from main import app
import models
from routers.timeline import (
    get_db,
    _extract_email_domain,
    _get_lead_contact_emails,
    _get_lead_company_domain,
    _build_gmail_search_query,
    _parse_email_addresses,
    _fetch_emails_from_gmail,
)


# Setup test database
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_timeline_gmail.db"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)


@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


TestingSessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=engine, expire_on_commit=False
)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


# Apply dependency override
app.dependency_overrides[get_db] = override_get_db


# Test data IDs
TEST_USER_ID = str(uuid.uuid4())
TEST_LEAD_ID = str(uuid.uuid4())
TEST_CONTACT_ID = str(uuid.uuid4())
TEST_CONTACT_2_ID = str(uuid.uuid4())


@pytest.fixture(scope="module", autouse=True)
def setup_module():
    """Setup test database and seed data."""
    Base.metadata.create_all(bind=engine)

    db = TestingSessionLocal()
    try:
        # Create test user
        user = models.User(
            id=TEST_USER_ID,
            name="Test User",
            email="testuser@company.com"
        )
        db.add(user)
        db.commit()

        # Create test contacts
        contact1 = models.Contact(
            id=TEST_CONTACT_ID,
            name="Contact One",
            email="contact1@clientcompany.com",
            phone="+1234567890"
        )
        db.add(contact1)

        contact2 = models.Contact(
            id=TEST_CONTACT_2_ID,
            name="Contact Two",
            email="contact2@clientcompany.com",
            phone="+0987654321"
        )
        db.add(contact2)
        db.commit()

        # Create test lead
        lead = models.Lead(
            id=TEST_LEAD_ID,
            title="Test Lead for Gmail",
            owner_user_id=TEST_USER_ID
        )
        db.add(lead)
        db.commit()

        # Link contacts to lead
        lead_contact1 = models.LeadContact(
            lead_id=TEST_LEAD_ID,
            contact_id=TEST_CONTACT_ID,
            is_primary=True
        )
        db.add(lead_contact1)

        lead_contact2 = models.LeadContact(
            lead_id=TEST_LEAD_ID,
            contact_id=TEST_CONTACT_2_ID,
            is_primary=False
        )
        db.add(lead_contact2)
        db.commit()

    finally:
        db.close()

    yield

    # Cleanup
    # Clear dependency overrides to avoid conflicts with other tests
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    if os.path.exists("./test_timeline_gmail.db"):
        try:
            os.remove("./test_timeline_gmail.db")
        except OSError:
            pass


@pytest.fixture
def test_client():
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
def db_session():
    """Provide a session for tests."""
    db = TestingSessionLocal()
    yield db
    db.close()


class TestExtractEmailDomain:
    """Test the _extract_email_domain helper function."""

    def test_simple_email(self):
        """Test domain extraction from simple email."""
        assert _extract_email_domain("john@example.com") == "example.com"

    def test_email_with_name(self):
        """Test domain extraction from email with name."""
        assert _extract_email_domain("John Doe <john@example.com>") == "example.com"

    def test_subdomain(self):
        """Test domain extraction with subdomain."""
        assert _extract_email_domain("john@mail.example.com") == "mail.example.com"

    def test_empty_email(self):
        """Test with empty string."""
        assert _extract_email_domain("") is None

    def test_none_email(self):
        """Test with None."""
        assert _extract_email_domain(None) is None

    def test_invalid_email(self):
        """Test with invalid email (no @)."""
        assert _extract_email_domain("notanemail") is None


class TestGetLeadContactEmails:
    """Test the _get_lead_contact_emails function."""

    def test_returns_contact_emails(self, db_session):
        """Test that contact emails are returned for a lead."""
        emails = _get_lead_contact_emails(db_session, TEST_LEAD_ID)
        assert "contact1@clientcompany.com" in emails
        assert "contact2@clientcompany.com" in emails

    def test_returns_lowercase_emails(self, db_session):
        """Test that emails are returned in lowercase."""
        emails = _get_lead_contact_emails(db_session, TEST_LEAD_ID)
        for email in emails:
            assert email == email.lower()

    def test_empty_for_nonexistent_lead(self, db_session):
        """Test that empty set is returned for nonexistent lead."""
        fake_lead_id = str(uuid.uuid4())
        emails = _get_lead_contact_emails(db_session, fake_lead_id)
        assert emails == set()


class TestGetLeadCompanyDomain:
    """Test the _get_lead_company_domain function."""

    def test_extracts_domain_from_contacts(self, db_session):
        """Test that company domain is extracted from contact emails."""
        domain = _get_lead_company_domain(db_session, TEST_LEAD_ID)
        # The domain is extracted from non-generic emails of contacts
        # "clientcompany.com" is not a generic domain like gmail.com
        assert domain == "clientcompany.com"

    def test_none_for_nonexistent_lead(self, db_session):
        """Test that None is returned for nonexistent lead."""
        fake_lead_id = str(uuid.uuid4())
        domain = _get_lead_company_domain(db_session, fake_lead_id)
        assert domain is None


class TestBuildGmailSearchQuery:
    """Test the _build_gmail_search_query function."""

    def test_builds_query_with_emails(self):
        """Test query building with email addresses."""
        emails = {"john@example.com", "jane@example.com"}
        query = _build_gmail_search_query(emails)
        assert query is not None
        assert "from:john@example.com" in query or "from:jane@example.com" in query
        assert "to:john@example.com" in query or "to:jane@example.com" in query

    def test_builds_query_with_domain(self):
        """Test query building with company domain."""
        emails = set()
        query = _build_gmail_search_query(emails, company_domain="example.com")
        assert query is not None
        assert "*@example.com" in query

    def test_none_for_empty_criteria(self):
        """Test that None is returned for empty criteria."""
        query = _build_gmail_search_query(set())
        assert query is None

    def test_combined_emails_and_domain(self):
        """Test query with both emails and domain."""
        emails = {"john@example.com"}
        query = _build_gmail_search_query(emails, company_domain="example.com")
        assert query is not None
        assert "john@example.com" in query
        assert "*@example.com" in query


class TestParseEmailAddresses:
    """Test the _parse_email_addresses helper function."""

    def test_simple_email(self):
        """Test parsing simple email address."""
        result = _parse_email_addresses("john@example.com")
        assert result == ["john@example.com"]

    def test_email_with_name(self):
        """Test parsing email with name."""
        result = _parse_email_addresses("John Doe <john@example.com>")
        assert result == ["john@example.com"]

    def test_multiple_emails(self):
        """Test parsing multiple email addresses."""
        result = _parse_email_addresses("john@example.com, jane@example.com")
        assert "john@example.com" in result
        assert "jane@example.com" in result

    def test_empty_string(self):
        """Test with empty string."""
        result = _parse_email_addresses("")
        assert result == []

    def test_none_value(self):
        """Test with None."""
        result = _parse_email_addresses(None)
        assert result == []


class TestTimelineGmailGracefulDegradation:
    """Test that timeline works gracefully when Gmail fails."""

    @patch("routers.timeline.GoogleGmailService")
    def test_timeline_returns_without_emails_on_gmail_failure(
        self, mock_gmail_service_class, db_session, test_client
    ):
        """Test that timeline returns calendar and audit entries when Gmail fails."""
        # Mock Gmail service to raise an exception
        mock_service = MagicMock()
        mock_service._check_auth.side_effect = Exception("Gmail service unavailable")
        mock_gmail_service_class.return_value = mock_service

        # Create an audit log for the lead
        audit_log = models.AuditLog(
            entity_type="lead",
            entity_id=TEST_LEAD_ID,
            actor_id=TEST_USER_ID,
            action="create",
            changes=None,
            timestamp=datetime.now(timezone.utc)
        )
        db_session.add(audit_log)
        db_session.commit()

        # Make API request
        response = test_client.get(
            f"/api/timeline/lead/{TEST_LEAD_ID}",
            headers={"x-user-id": TEST_USER_ID}
        )

        # Should succeed even if Gmail fails
        assert response.status_code == 200
        data = response.json()
        assert "items" in data

        # Should have audit entries
        audit_items = [item for item in data["items"] if item["type"] == "audit"]
        assert len(audit_items) >= 1

    @patch("routers.timeline.GoogleGmailService")
    def test_timeline_includes_emails_when_gmail_works(
        self, mock_gmail_service_class, db_session, test_client
    ):
        """Test that timeline includes emails when Gmail returns results."""
        # Mock Gmail service to return mock messages
        mock_service = MagicMock()
        mock_gmail_service_class.return_value = mock_service

        # Use timezone-aware timestamp
        now = datetime.now(timezone.utc)
        timestamp_ms = str(int(now.timestamp() * 1000))

        # Mock list_messages to return a message
        mock_service.list_messages.return_value = {
            "messages": [
                {"id": "msg123", "threadId": "thread123"}
            ]
        }

        # Mock get_message to return message details
        mock_service.get_message.return_value = {
            "id": "msg123",
            "threadId": "thread123",
            "internalDate": timestamp_ms,
            "snippet": "This is a test email snippet",
            "labelIds": ["INBOX"],
            "payload": {
                "headers": [
                    {"name": "From", "value": "contact1@clientcompany.com"},
                    {"name": "To", "value": "sales@ourcompany.com"},
                    {"name": "Subject", "value": "Re: Product Inquiry"},
                    {"name": "Date", "value": "Mon, 15 Jan 2024 10:30:00 -0500"}
                ]
            }
        }

        # Mock _parse_headers to return header dict
        mock_service._parse_headers.return_value = {
            "from": "contact1@clientcompany.com",
            "to": "sales@ourcompany.com",
            "subject": "Re: Product Inquiry",
            "date": "Mon, 15 Jan 2024 10:30:00 -0500"
        }

        # Make API request
        response = test_client.get(
            f"/api/timeline/lead/{TEST_LEAD_ID}",
            headers={"x-user-id": TEST_USER_ID}
        )

        assert response.status_code == 200
        data = response.json()
        assert "items" in data

        # Should have email entries
        email_items = [item for item in data["items"] if item["type"] == "email"]
        assert len(email_items) >= 1

        # Verify email entry structure
        email = email_items[0]
        assert email["type"] == "email"
        assert "timestamp" in email
        assert "summary" in email
        assert email["details"].get("message_id") == "msg123"
        assert email["details"].get("thread_id") == "thread123"


class TestTimelineEmailNormalization:
    """Test that email data is correctly normalized to TimelineEntry format."""

    @patch("routers.timeline.GoogleGmailService")
    def test_email_entry_has_required_fields(
        self, mock_gmail_service_class, db_session, test_client
    ):
        """Test that email timeline entries have all required fields."""
        # Mock Gmail service
        mock_service = MagicMock()
        mock_gmail_service_class.return_value = mock_service

        timestamp_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

        mock_service.list_messages.return_value = {
            "messages": [{"id": "msg456", "threadId": "thread456"}]
        }

        mock_service.get_message.return_value = {
            "id": "msg456",
            "threadId": "thread456",
            "internalDate": str(timestamp_ms),
            "snippet": "Test snippet",
            "labelIds": ["INBOX", "IMPORTANT"],
            "payload": {"headers": []}
        }

        mock_service._parse_headers.return_value = {
            "from": "sender@example.com",
            "to": "recipient@example.com",
            "subject": "Test Subject",
            "cc": "cc@example.com"
        }

        response = test_client.get(
            f"/api/timeline/lead/{TEST_LEAD_ID}",
            headers={"x-user-id": TEST_USER_ID}
        )

        assert response.status_code == 200
        data = response.json()

        email_items = [item for item in data["items"] if item["type"] == "email"]
        if email_items:
            email = email_items[0]
            # Verify required fields
            assert email["type"] == "email"
            assert "timestamp" in email
            assert "summary" in email
            assert "details" in email

            # Verify details structure
            details = email["details"]
            assert "message_id" in details
            assert "thread_id" in details
            assert "subject" in details
            assert "from" in details
            assert "to" in details
            assert "snippet" in details


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
