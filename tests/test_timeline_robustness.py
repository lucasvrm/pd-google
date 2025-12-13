"""
Tests for Timeline API robustness - handling malformed data.

These tests verify that the Timeline API can handle:
- Audit logs with string instead of dict in the changes field
- Missing or invalid timestamps
- Malformed calendar event data

The API should return partial results, skipping bad items instead of crashing.
"""

import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

from database import Base
from main import app
import models
from routers.timeline import get_db, _safe_parse_changes, _safe_parse_timestamp


# Setup test database
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_timeline_robustness.db"
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
        
        # Create test lead
        lead = models.Lead(
            id=TEST_LEAD_ID,
            title="Test Lead for Robustness",
        )
        db.add(lead)
        db.commit()
        
    finally:
        db.close()
    
    yield
    
    # Cleanup
    Base.metadata.drop_all(bind=engine)
    if os.path.exists("./test_timeline_robustness.db"):
        try:
            os.remove("./test_timeline_robustness.db")
        except:
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


class TestSafeParseChanges:
    """Test the _safe_parse_changes function directly."""

    def test_parse_dict_returns_dict(self):
        """Test that dict input is returned as-is."""
        changes = {"field": {"old": "a", "new": "b"}}
        result = _safe_parse_changes(changes)
        assert result == changes

    def test_parse_json_string_returns_dict(self):
        """Test that JSON string is parsed to dict."""
        changes = '{"field": {"old": "a", "new": "b"}}'
        result = _safe_parse_changes(changes)
        assert result == {"field": {"old": "a", "new": "b"}}

    def test_parse_none_returns_empty_dict(self):
        """Test that None returns empty dict."""
        result = _safe_parse_changes(None)
        assert result == {}

    def test_parse_invalid_json_returns_empty_dict(self):
        """Test that invalid JSON string returns empty dict."""
        result = _safe_parse_changes("not valid json")
        assert result == {}

    def test_parse_json_array_returns_empty_dict(self):
        """Test that JSON array returns empty dict (we expect object)."""
        result = _safe_parse_changes('[1, 2, 3]')
        assert result == {}

    def test_parse_empty_string_returns_empty_dict(self):
        """Test that empty string returns empty dict."""
        result = _safe_parse_changes("")
        assert result == {}


class TestSafeParseTimestamp:
    """Test the _safe_parse_timestamp function directly."""

    def test_parse_datetime_returns_datetime(self):
        """Test that datetime input is returned as-is."""
        now = datetime.now(timezone.utc)
        result = _safe_parse_timestamp(now)
        assert result == now

    def test_parse_iso_string_returns_datetime(self):
        """Test that ISO string is parsed to datetime."""
        iso_str = "2024-01-15T14:00:00+00:00"
        result = _safe_parse_timestamp(iso_str)
        assert isinstance(result, datetime)
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15

    def test_parse_iso_string_with_z_returns_datetime(self):
        """Test that ISO string with Z suffix is parsed."""
        iso_str = "2024-01-15T14:00:00Z"
        result = _safe_parse_timestamp(iso_str)
        assert isinstance(result, datetime)

    def test_parse_none_returns_none(self):
        """Test that None returns None."""
        result = _safe_parse_timestamp(None)
        assert result is None

    def test_parse_invalid_string_returns_none(self):
        """Test that invalid string returns None."""
        result = _safe_parse_timestamp("not a timestamp")
        assert result is None


class TestTimelineWithMalformedAuditLogs:
    """Test that timeline handles malformed audit log data gracefully."""

    def test_timeline_with_string_changes_field(self, db_session, test_client):
        """Test that audit logs with string changes field are processed correctly."""
        # Insert an audit log with changes as a JSON string (not dict)
        json_changes = json.dumps({"title": {"old": "Old Title", "new": "New Title"}})
        
        audit_log = models.AuditLog(
            entity_type="lead",
            entity_id=TEST_LEAD_ID,
            actor_id=TEST_USER_ID,
            action="update",
            changes=json_changes,  # This is a string
            timestamp=datetime.now(timezone.utc)
        )
        db_session.add(audit_log)
        db_session.commit()
        
        # Make API request with auth header
        response = test_client.get(
            f"/api/timeline/lead/{TEST_LEAD_ID}",
            headers={"x-user-id": TEST_USER_ID}
        )
        
        # Should succeed, not crash
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        
        # Find the audit entry we just created
        audit_items = [
            item for item in data["items"] 
            if item["type"] == "audit" and item["details"].get("action") == "update"
        ]
        assert len(audit_items) >= 1

    def test_timeline_with_invalid_changes_string(self, db_session, test_client):
        """Test that audit logs with invalid JSON string in changes are skipped."""
        # Insert an audit log with invalid JSON string
        audit_log = models.AuditLog(
            entity_type="lead",
            entity_id=TEST_LEAD_ID,
            actor_id=TEST_USER_ID,
            action="update",
            changes="invalid json string {not valid}",
            timestamp=datetime.now(timezone.utc)
        )
        db_session.add(audit_log)
        db_session.commit()
        
        # Make API request
        response = test_client.get(
            f"/api/timeline/lead/{TEST_LEAD_ID}",
            headers={"x-user-id": TEST_USER_ID}
        )
        
        # Should succeed, returning partial results
        assert response.status_code == 200
        data = response.json()
        assert "items" in data

    def test_timeline_with_null_changes(self, db_session, test_client):
        """Test that audit logs with null changes are processed correctly."""
        audit_log = models.AuditLog(
            entity_type="lead",
            entity_id=TEST_LEAD_ID,
            actor_id=TEST_USER_ID,
            action="create",
            changes=None,  # No changes for create action
            timestamp=datetime.now(timezone.utc)
        )
        db_session.add(audit_log)
        db_session.commit()
        
        response = test_client.get(
            f"/api/timeline/lead/{TEST_LEAD_ID}",
            headers={"x-user-id": TEST_USER_ID}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "items" in data


class TestTimelineWithMalformedCalendarEvents:
    """Test that timeline handles malformed calendar event data gracefully."""

    def test_timeline_with_null_start_time(self, db_session, test_client):
        """Test that calendar events with null start_time are handled."""
        event = models.CalendarEvent(
            google_event_id=f"evt_{uuid.uuid4().hex[:12]}",
            calendar_id="primary",
            summary="Event with no start time",
            start_time=None,  # Missing start time
            end_time=None,
            status="confirmed",
        )
        db_session.add(event)
        db_session.commit()
        
        # We need a lead that will match this event somehow
        # Since this event has no attendees, it won't be included for a lead with owner
        # But the processing should not crash
        
        response = test_client.get(
            f"/api/timeline/lead/{TEST_LEAD_ID}",
            headers={"x-user-id": TEST_USER_ID}
        )
        
        assert response.status_code == 200

    def test_timeline_with_invalid_attendees_json(self, db_session, test_client):
        """Test that calendar events with invalid attendees JSON are handled."""
        event = models.CalendarEvent(
            google_event_id=f"evt_{uuid.uuid4().hex[:12]}",
            calendar_id="primary",
            summary="Event with invalid attendees",
            start_time=datetime.now(timezone.utc),
            end_time=datetime.now(timezone.utc) + timedelta(hours=1),
            status="confirmed",
            attendees="not valid json [",  # Invalid JSON
        )
        db_session.add(event)
        db_session.commit()
        
        response = test_client.get(
            f"/api/timeline/lead/{TEST_LEAD_ID}",
            headers={"x-user-id": TEST_USER_ID}
        )
        
        # Should not crash
        assert response.status_code == 200


class TestTimelinePartialResults:
    """Test that timeline returns partial results when some items fail."""

    def test_returns_partial_timeline_on_processing_errors(self, db_session, test_client):
        """Test that valid items are returned even if some items have errors."""
        # Create a known good audit log
        good_log = models.AuditLog(
            entity_type="lead",
            entity_id=TEST_LEAD_ID,
            actor_id=TEST_USER_ID,
            action="create",
            changes={"field": {"old": None, "new": "value"}},
            timestamp=datetime.now(timezone.utc)
        )
        db_session.add(good_log)
        db_session.commit()
        
        response = test_client.get(
            f"/api/timeline/lead/{TEST_LEAD_ID}",
            headers={"x-user-id": TEST_USER_ID}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Should have at least the good log entry
        assert data["pagination"]["total"] >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
