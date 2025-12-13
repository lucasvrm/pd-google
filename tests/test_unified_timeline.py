"""
Tests for Unified Timeline API endpoint.

Tests the `/api/timeline/{entity_type}/{entity_id}` endpoint that aggregates
calendar events, audit logs, and emails (placeholder) into a unified timeline.
"""

import json
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from database import Base
from main import app
import models
from routers.timeline import get_db
from services.audit_service import register_audit_listeners, set_audit_actor, clear_audit_actor


# Setup test database
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_unified_timeline.db"
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


# Test data IDs (fixed for consistent testing)
TEST_USER_ID = str(uuid.uuid4())
TEST_LEAD_STATUS_ID = str(uuid.uuid4())
TEST_LEAD_STATUS_2_ID = str(uuid.uuid4())
TEST_LEAD_ID = str(uuid.uuid4())
TEST_COMPANY_ID = str(uuid.uuid4())
TEST_DEAL_ID = str(uuid.uuid4())
TEST_CONTACT_ID = str(uuid.uuid4())


@pytest.fixture(scope="module", autouse=True)
def setup_module():
    """Setup test database, register audit listeners, and seed data."""
    Base.metadata.create_all(bind=engine)
    register_audit_listeners()
    
    # Seed test data in module scope so it persists across tests
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
        
        # Create lead statuses
        status1 = models.LeadStatus(
            id=TEST_LEAD_STATUS_ID,
            code="new",
            label="New",
            is_active=True,
            sort_order=0
        )
        db.add(status1)
        
        status2 = models.LeadStatus(
            id=TEST_LEAD_STATUS_2_ID,
            code="qualified",
            label="Qualified",
            is_active=True,
            sort_order=1
        )
        db.add(status2)
        db.commit()
        
        # Create test lead with audit logging
        set_audit_actor(TEST_USER_ID)
        lead = models.Lead(
            id=TEST_LEAD_ID,
            title="Test Lead",
            lead_status_id=TEST_LEAD_STATUS_ID,
            owner_user_id=TEST_USER_ID,
            priority_score=5
        )
        db.add(lead)
        db.commit()
        clear_audit_actor()
        
        # Create test company
        company = models.Company(
            id=TEST_COMPANY_ID,
            name="Test Company"
        )
        db.add(company)
        db.commit()
        
        # Create test deal with audit logging
        set_audit_actor(TEST_USER_ID)
        deal = models.Deal(
            id=TEST_DEAL_ID,
            title="Test Deal",
            company_id=TEST_COMPANY_ID
        )
        db.add(deal)
        db.commit()
        clear_audit_actor()
        
        # Create test contact
        contact = models.Contact(
            id=TEST_CONTACT_ID,
            name="Test Contact",
            email="contact@example.com",
            phone="+1234567890"
        )
        db.add(contact)
        db.commit()
        
        # Create test calendar event
        now = datetime.now(timezone.utc)
        calendar_event = models.CalendarEvent(
            google_event_id=f"evt_{uuid.uuid4().hex[:12]}",
            calendar_id="primary",
            summary="Test Meeting",
            description=None,
            start_time=now - timedelta(days=1),
            end_time=now - timedelta(days=1) + timedelta(hours=1),
            status="confirmed",
            organizer_email="testuser@company.com",
            attendees=json.dumps([
                {"email": "testuser@company.com", "responseStatus": "accepted"}
            ])
        )
        db.add(calendar_event)
        db.commit()
        
    finally:
        db.close()
    
    yield
    
    # Cleanup
    Base.metadata.drop_all(bind=engine)
    if os.path.exists("./test_unified_timeline.db"):
        try:
            os.remove("./test_unified_timeline.db")
        except:
            pass


@pytest.fixture
def test_client():
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
def db_session():
    """Provide a session for tests that need to modify data."""
    db = TestingSessionLocal()
    yield db
    db.close()


class TestTimelineEndpointExists:
    """Test that the timeline endpoint is properly registered."""

    def test_timeline_endpoint_responds(self, test_client):
        """Test that timeline endpoint returns a response."""
        response = test_client.get(f"/api/timeline/lead/{TEST_LEAD_ID}")
        assert response.status_code == 200

    def test_timeline_endpoint_invalid_entity_type(self, test_client):
        """Test that invalid entity type returns 422."""
        response = test_client.get(f"/api/timeline/invalid/some-id")
        assert response.status_code == 422


class TestTimelineResponseStructure:
    """Test the timeline response structure."""

    def test_response_has_items_and_pagination(self, test_client):
        """Test that response has items and pagination."""
        response = test_client.get(f"/api/timeline/lead/{TEST_LEAD_ID}")
        assert response.status_code == 200
        data = response.json()

        assert "items" in data
        assert "pagination" in data
        assert isinstance(data["items"], list)

    def test_pagination_structure(self, test_client):
        """Test pagination structure."""
        response = test_client.get(f"/api/timeline/lead/{TEST_LEAD_ID}")
        assert response.status_code == 200
        data = response.json()

        pagination = data["pagination"]
        assert "total" in pagination
        assert "limit" in pagination
        assert "offset" in pagination

    def test_timeline_item_structure(self, test_client):
        """Test timeline item structure."""
        response = test_client.get(f"/api/timeline/lead/{TEST_LEAD_ID}")
        assert response.status_code == 200
        data = response.json()

        # Should have at least audit log from lead creation
        assert len(data["items"]) >= 1

        item = data["items"][0]
        assert "type" in item
        assert "timestamp" in item
        assert "summary" in item
        assert item["type"] in ["meeting", "audit", "email"]


class TestTimelineAuditLogs:
    """Test that audit logs are included in timeline."""

    def test_lead_creation_audit_in_timeline(self, test_client):
        """Test that lead creation audit log appears in timeline."""
        response = test_client.get(f"/api/timeline/lead/{TEST_LEAD_ID}")
        assert response.status_code == 200
        data = response.json()

        # Find audit entries
        audit_items = [item for item in data["items"] if item["type"] == "audit"]
        assert len(audit_items) >= 1

        # Check for create action
        create_items = [
            item for item in audit_items 
            if item["details"].get("action") == "create"
        ]
        assert len(create_items) == 1

    def test_lead_update_audit_in_timeline(self, db_session, test_client):
        """Test that lead update audit log appears in timeline."""
        # Update the lead
        lead = db_session.query(models.Lead).filter(models.Lead.id == TEST_LEAD_ID).first()
        set_audit_actor(TEST_USER_ID)
        lead.title = "Updated Lead Title"
        db_session.commit()
        clear_audit_actor()

        response = test_client.get(f"/api/timeline/lead/{TEST_LEAD_ID}")
        assert response.status_code == 200
        data = response.json()

        # Find audit entries
        audit_items = [item for item in data["items"] if item["type"] == "audit"]
        assert len(audit_items) >= 2  # create + update

    def test_status_change_audit_in_timeline(self, db_session, test_client):
        """Test that status change audit log appears in timeline."""
        # Change lead status
        lead = db_session.query(models.Lead).filter(models.Lead.id == TEST_LEAD_ID).first()
        set_audit_actor(TEST_USER_ID)
        lead.lead_status_id = TEST_LEAD_STATUS_2_ID
        db_session.commit()
        clear_audit_actor()

        response = test_client.get(f"/api/timeline/lead/{TEST_LEAD_ID}")
        assert response.status_code == 200
        data = response.json()

        # Find status change entries
        status_items = [
            item for item in data["items"]
            if item["type"] == "audit" and item["details"].get("action") == "status_change"
        ]
        assert len(status_items) >= 1


class TestTimelinePagination:
    """Test timeline pagination functionality."""

    def test_default_pagination(self, test_client):
        """Test default pagination values."""
        response = test_client.get(f"/api/timeline/lead/{TEST_LEAD_ID}")
        assert response.status_code == 200
        data = response.json()

        assert data["pagination"]["limit"] == 50
        assert data["pagination"]["offset"] == 0

    def test_custom_limit(self, test_client):
        """Test custom limit parameter."""
        response = test_client.get(f"/api/timeline/lead/{TEST_LEAD_ID}?limit=10")
        assert response.status_code == 200
        data = response.json()

        assert data["pagination"]["limit"] == 10
        assert len(data["items"]) <= 10

    def test_custom_offset(self, test_client):
        """Test custom offset parameter."""
        response = test_client.get(f"/api/timeline/lead/{TEST_LEAD_ID}?offset=1")
        assert response.status_code == 200
        data = response.json()

        assert data["pagination"]["offset"] == 1

    def test_limit_validation(self, test_client):
        """Test limit validation (max 200)."""
        response = test_client.get(f"/api/timeline/lead/{TEST_LEAD_ID}?limit=500")
        assert response.status_code == 422  # Validation error


class TestTimelineSorting:
    """Test timeline sorting functionality."""

    def test_timeline_sorted_descending(self, test_client):
        """Test that timeline is sorted by timestamp descending."""
        response = test_client.get(f"/api/timeline/lead/{TEST_LEAD_ID}")
        assert response.status_code == 200
        data = response.json()

        if len(data["items"]) > 1:
            timestamps = [item["timestamp"] for item in data["items"]]
            # Verify descending order
            for i in range(len(timestamps) - 1):
                assert timestamps[i] >= timestamps[i + 1], "Timeline not sorted descending"


class TestTimelineEntityNotFound:
    """Test timeline behavior when entity is not found."""

    def test_lead_not_found(self, test_client):
        """Test 404 when lead doesn't exist."""
        fake_id = str(uuid.uuid4())
        response = test_client.get(f"/api/timeline/lead/{fake_id}")
        assert response.status_code == 404

    def test_deal_not_found(self, test_client):
        """Test 404 when deal doesn't exist."""
        fake_id = str(uuid.uuid4())
        response = test_client.get(f"/api/timeline/deal/{fake_id}")
        assert response.status_code == 404

    def test_contact_not_found(self, test_client):
        """Test 404 when contact doesn't exist."""
        fake_id = str(uuid.uuid4())
        response = test_client.get(f"/api/timeline/contact/{fake_id}")
        assert response.status_code == 404


class TestTimelineAllEntityTypes:
    """Test timeline for all supported entity types."""

    def test_lead_timeline(self, test_client):
        """Test timeline for lead entity."""
        response = test_client.get(f"/api/timeline/lead/{TEST_LEAD_ID}")
        assert response.status_code == 200

    def test_deal_timeline(self, test_client):
        """Test timeline for deal entity."""
        response = test_client.get(f"/api/timeline/deal/{TEST_DEAL_ID}")
        assert response.status_code == 200

    def test_contact_timeline(self, test_client):
        """Test timeline for contact entity."""
        response = test_client.get(f"/api/timeline/contact/{TEST_CONTACT_ID}")
        assert response.status_code == 200


class TestTimelineAuditSummary:
    """Test audit log summary generation."""

    def test_create_summary(self, test_client):
        """Test that create action has correct summary."""
        response = test_client.get(f"/api/timeline/lead/{TEST_LEAD_ID}")
        assert response.status_code == 200
        data = response.json()

        create_items = [
            item for item in data["items"]
            if item["type"] == "audit" and item["details"].get("action") == "create"
        ]
        assert len(create_items) >= 1
        assert "Created" in create_items[0]["summary"]

    def test_update_summary(self, db_session, test_client):
        """Test that update action has correct summary."""
        # Make sure we have an update audit log
        lead = db_session.query(models.Lead).filter(models.Lead.id == TEST_LEAD_ID).first()
        set_audit_actor(TEST_USER_ID)
        lead.priority_score = 99
        db_session.commit()
        clear_audit_actor()

        response = test_client.get(f"/api/timeline/lead/{TEST_LEAD_ID}")
        assert response.status_code == 200
        data = response.json()

        update_items = [
            item for item in data["items"]
            if item["type"] == "audit" and item["details"].get("action") == "update"
        ]
        assert len(update_items) >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
