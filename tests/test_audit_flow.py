"""
Integration tests for Audit Flow

Tests that verify:
1. Lead updates trigger AuditLog entries
2. Timeline endpoint correctly returns and formats audit logs
"""

import pytest
import os
import uuid
from datetime import datetime, timezone
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from database import Base
import models
from services.audit_service import (
    set_audit_actor,
    clear_audit_actor,
    register_audit_listeners,
)
from main import app


# Setup Test DB
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_audit_flow.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})

@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)


@pytest.fixture(scope="module", autouse=True)
def setup_module():
    """Setup test database and register audit listeners."""
    Base.metadata.create_all(bind=engine)
    register_audit_listeners()
    yield
    # Cleanup
    if os.path.exists("./test_audit_flow.db"):
        os.remove("./test_audit_flow.db")


@pytest.fixture
def db_session():
    """Provide a transactional scope for each test."""
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)
    
    yield session
    
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def test_user(db_session):
    """Create a test user."""
    user = models.User(
        id=str(uuid.uuid4()),
        name="Test User",
        email="testuser@example.com"
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def test_lead_status(db_session):
    """Create a test lead status."""
    status = models.LeadStatus(
        id=str(uuid.uuid4()),
        code="new",
        label="New",
        is_active=True,
        sort_order=0
    )
    db_session.add(status)
    db_session.commit()
    return status


@pytest.fixture
def another_lead_status(db_session):
    """Create another test lead status."""
    status = models.LeadStatus(
        id=str(uuid.uuid4()),
        code="contacted",
        label="Contacted",
        is_active=True,
        sort_order=1
    )
    db_session.add(status)
    db_session.commit()
    return status


class TestAuditFlowIntegration:
    """Integration tests for audit logging flow."""

    def test_lead_update_creates_audit_log(self, db_session, test_user, test_lead_status):
        """
        Test that updating a Lead triggers an AuditLog entry.
        
        This verifies the SQLAlchemy event listener is working correctly.
        """
        set_audit_actor(test_user.id)
        
        # Create a lead
        lead = models.Lead(
            id=str(uuid.uuid4()),
            title="Initial Company Name",
            lead_status_id=test_lead_status.id,
            owner_user_id=test_user.id,
            priority_score=5
        )
        db_session.add(lead)
        db_session.commit()
        lead_id = lead.id
        
        # Clear creation audit log
        db_session.query(models.AuditLog).filter_by(
            entity_type="lead",
            entity_id=lead_id
        ).delete()
        db_session.commit()
        
        # Update the lead's title and priority
        lead.title = "Updated Company Name"
        lead.priority_score = 10
        db_session.commit()
        
        # Verify audit log was created
        audit_logs = db_session.query(models.AuditLog).filter_by(
            entity_type="lead",
            entity_id=lead_id,
            action="update"
        ).all()
        
        assert len(audit_logs) == 1
        audit_log = audit_logs[0]
        
        # Verify actor
        assert audit_log.actor_id == test_user.id
        
        # Verify changes are captured
        changes = audit_log.changes
        assert "title" in changes
        assert changes["title"]["old"] == "Initial Company Name"
        assert changes["title"]["new"] == "Updated Company Name"
        assert "priority_score" in changes
        assert changes["priority_score"]["old"] == 5
        assert changes["priority_score"]["new"] == 10
        
        clear_audit_actor()

    def test_lead_status_change_creates_audit_log(
        self, db_session, test_user, test_lead_status, another_lead_status
    ):
        """
        Test that changing lead status creates an audit log with action='status_change'.
        """
        set_audit_actor(test_user.id)
        
        # Create a lead
        lead = models.Lead(
            id=str(uuid.uuid4()),
            title="Test Lead",
            lead_status_id=test_lead_status.id,
            owner_user_id=test_user.id
        )
        db_session.add(lead)
        db_session.commit()
        lead_id = lead.id
        
        # Clear creation audit log
        db_session.query(models.AuditLog).filter_by(
            entity_type="lead",
            entity_id=lead_id
        ).delete()
        db_session.commit()
        
        # Change status
        lead.lead_status_id = another_lead_status.id
        db_session.commit()
        
        # Verify audit log
        audit_logs = db_session.query(models.AuditLog).filter_by(
            entity_type="lead",
            entity_id=lead_id,
            action="status_change"
        ).all()
        
        assert len(audit_logs) == 1
        audit_log = audit_logs[0]
        assert audit_log.actor_id == test_user.id
        
        # Verify status change is recorded
        changes = audit_log.changes
        assert "lead_status_id" in changes
        assert changes["lead_status_id"]["old"] == test_lead_status.id
        assert changes["lead_status_id"]["new"] == another_lead_status.id
        
        clear_audit_actor()

    def test_multiple_updates_create_multiple_audit_logs(
        self, db_session, test_user, test_lead_status
    ):
        """
        Test that multiple updates create separate audit log entries.
        """
        set_audit_actor(test_user.id)
        
        # Create a lead
        lead = models.Lead(
            id=str(uuid.uuid4()),
            title="Original Title",
            lead_status_id=test_lead_status.id,
            owner_user_id=test_user.id,
            priority_score=3
        )
        db_session.add(lead)
        db_session.commit()
        lead_id = lead.id
        
        # Clear creation audit log
        db_session.query(models.AuditLog).filter_by(
            entity_type="lead",
            entity_id=lead_id
        ).delete()
        db_session.commit()
        
        # First update
        lead.title = "First Update"
        db_session.commit()
        
        # Second update
        lead.priority_score = 8
        db_session.commit()
        
        # Third update
        lead.title = "Second Update"
        db_session.commit()
        
        # Verify all audit logs were created
        audit_logs = db_session.query(models.AuditLog).filter_by(
            entity_type="lead",
            entity_id=lead_id,
            action="update"
        ).order_by(models.AuditLog.timestamp).all()
        
        assert len(audit_logs) == 3
        
        # Verify first update
        assert "title" in audit_logs[0].changes
        assert audit_logs[0].changes["title"]["new"] == "First Update"
        
        # Verify second update
        assert "priority_score" in audit_logs[1].changes
        assert audit_logs[1].changes["priority_score"]["new"] == 8
        
        # Verify third update
        assert "title" in audit_logs[2].changes
        assert audit_logs[2].changes["title"]["new"] == "Second Update"
        
        clear_audit_actor()


class TestTimelineEndpointIntegration:
    """Integration tests for Timeline endpoint with audit logs."""

    def test_timeline_endpoint_returns_audit_logs(
        self, db_session, test_user, test_lead_status
    ):
        """
        Test that the Timeline endpoint returns audit logs correctly formatted.
        """
        set_audit_actor(test_user.id)
        
        # Create a lead
        lead = models.Lead(
            id=str(uuid.uuid4()),
            title="Test Lead for Timeline",
            lead_status_id=test_lead_status.id,
            owner_user_id=test_user.id,
            priority_score=5
        )
        db_session.add(lead)
        db_session.commit()
        lead_id = lead.id
        
        # Update the lead to create audit logs
        lead.title = "Updated Lead Title"
        db_session.commit()
        
        lead.priority_score = 10
        db_session.commit()
        
        clear_audit_actor()
        
        # Override database dependency for FastAPI
        def override_get_db():
            try:
                yield db_session
            finally:
                pass
        
        from routers.timeline import get_db
        app.dependency_overrides[get_db] = override_get_db
        
        # Make request to timeline endpoint
        client = TestClient(app)
        response = client.get(
            f"/api/timeline/lead/{lead_id}",
            headers={"x-user-id": test_user.id, "x-user-role": "admin"}
        )
        
        # Clean up override
        app.dependency_overrides.clear()
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "items" in data
        assert "pagination" in data
        
        # Filter audit entries
        audit_entries = [item for item in data["items"] if item["type"] == "audit"]
        
        # Should have at least 2 audit entries (2 updates, creation might be there too)
        assert len(audit_entries) >= 2
        
        # Verify audit entry structure
        for entry in audit_entries:
            assert "type" in entry
            assert entry["type"] == "audit"
            assert "timestamp" in entry
            assert "summary" in entry
            assert "details" in entry
            assert "action" in entry["details"]
            assert "changes" in entry["details"]
            
            # Verify user information is included
            if entry.get("user"):
                assert "id" in entry["user"]

    def test_timeline_endpoint_formats_audit_summary(
        self, db_session, test_user, test_lead_status, another_lead_status
    ):
        """
        Test that the Timeline endpoint formats audit log summaries correctly.
        """
        set_audit_actor(test_user.id)
        
        # Create a lead
        lead = models.Lead(
            id=str(uuid.uuid4()),
            title="Test Lead",
            lead_status_id=test_lead_status.id,
            owner_user_id=test_user.id
        )
        db_session.add(lead)
        db_session.commit()
        lead_id = lead.id
        
        # Clear creation audit log for cleaner test
        db_session.query(models.AuditLog).filter_by(
            entity_type="lead",
            entity_id=lead_id
        ).delete()
        db_session.commit()
        
        # Change status to create a status_change audit log
        lead.lead_status_id = another_lead_status.id
        db_session.commit()
        
        clear_audit_actor()
        
        # Override database dependency
        def override_get_db():
            try:
                yield db_session
            finally:
                pass
        
        from routers.timeline import get_db
        app.dependency_overrides[get_db] = override_get_db
        
        # Make request to timeline endpoint
        client = TestClient(app)
        response = client.get(
            f"/api/timeline/lead/{lead_id}",
            headers={"x-user-id": test_user.id, "x-user-role": "admin"}
        )
        
        # Clean up override
        app.dependency_overrides.clear()
        
        assert response.status_code == 200
        data = response.json()
        
        # Find the status change audit entry
        audit_entries = [
            item for item in data["items"]
            if item["type"] == "audit" and item["details"]["action"] == "status_change"
        ]
        
        assert len(audit_entries) >= 1
        status_change_entry = audit_entries[0]
        
        # Verify summary contains meaningful information
        assert "summary" in status_change_entry
        # Summary should mention status change
        assert "status" in status_change_entry["summary"].lower() or "changed" in status_change_entry["summary"].lower()
