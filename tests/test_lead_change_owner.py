"""
Tests for Lead change owner functionality.

Tests that:
1. change_lead_owner endpoint correctly transfers ownership
2. Validation rules are respected (lead exists, new owner exists, different owner)
3. Permission rules are enforced (only owner, manager, admin can change)
4. Audit log entries are created with action="lead.owner_changed"
"""

import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from main import app
from database import Base
from models import Lead, User, AuditLog
from routers import leads
from services.audit_service import register_audit_listeners, set_audit_actor, clear_audit_actor

# Setup in-memory SQLite database with StaticPool to share state across threads/connections
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# Dependency override
def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


app.dependency_overrides[leads.get_db] = override_get_db


@pytest.fixture(scope="function", autouse=True)
def init_db():
    """Initialize the database schema before each test."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def db_session():
    """Provide a database session for test setup."""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


class TestChangeLeadOwnerEndpoint:
    """Test the POST /{lead_id}/change-owner endpoint."""

    def test_change_owner_success_as_admin(self, client, db_session):
        """Successfully change lead owner as admin."""
        # Setup: Create a lead with owner and a new owner
        original_owner = User(id="user-original", name="Original Owner", email="original@test.com")
        new_owner = User(id="user-new", name="New Owner", email="new@test.com")
        lead = Lead(
            id="lead-change-owner-test",
            title="Test Lead for Change Owner",
            owner_user_id="user-original",
            priority_score=50,
        )
        db_session.add_all([original_owner, new_owner, lead])
        db_session.commit()

        # Execute: Change owner as admin
        response = client.post(
            "/api/leads/lead-change-owner-test/change-owner",
            json={
                "new_owner_id": "user-new",
                "current_user_id": "admin-user",
            },
            headers={"x-user-id": "admin-user", "x-user-role": "admin"}
        )

        # Verify response
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "success"
        assert body["lead_id"] == "lead-change-owner-test"
        assert body["previous_owner_id"] == "user-original"
        assert body["new_owner_id"] == "user-new"
        assert body["changed_by"] == "admin-user"
        assert "changed_at" in body

    def test_change_owner_success_as_current_owner(self, client, db_session):
        """Current owner can transfer their own lead."""
        # Setup
        original_owner = User(id="user-owner-transfer", name="Original Owner", email="original@test.com")
        new_owner = User(id="user-recipient", name="New Owner", email="new@test.com")
        lead = Lead(
            id="lead-owner-transfer",
            title="Lead to Transfer",
            owner_user_id="user-owner-transfer",
            priority_score=60,
        )
        db_session.add_all([original_owner, new_owner, lead])
        db_session.commit()

        # Execute: Change owner as the current owner (sales role)
        response = client.post(
            "/api/leads/lead-owner-transfer/change-owner",
            json={
                "new_owner_id": "user-recipient",
                "current_user_id": "user-owner-transfer",
            },
            headers={"x-user-id": "user-owner-transfer", "x-user-role": "sales"}
        )

        # Verify response
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "success"
        assert body["new_owner_id"] == "user-recipient"

    def test_change_owner_success_as_manager(self, client, db_session):
        """Manager can change ownership of any lead."""
        # Setup
        original_owner = User(id="user-sales", name="Sales User", email="sales@test.com")
        new_owner = User(id="user-other-sales", name="Other Sales", email="other@test.com")
        manager = User(id="user-manager", name="Manager", email="manager@test.com")
        lead = Lead(
            id="lead-manager-change",
            title="Lead for Manager Change",
            owner_user_id="user-sales",
            priority_score=70,
        )
        db_session.add_all([original_owner, new_owner, manager, lead])
        db_session.commit()

        # Execute: Change owner as manager
        response = client.post(
            "/api/leads/lead-manager-change/change-owner",
            json={
                "new_owner_id": "user-other-sales",
                "current_user_id": "user-manager",
            },
            headers={"x-user-id": "user-manager", "x-user-role": "manager"}
        )

        # Verify response
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "success"

    def test_change_owner_nonexistent_lead_returns_404(self, client, db_session):
        """Attempting to change owner of non-existent lead returns 404."""
        new_owner = User(id="user-exists", name="Existing User", email="exists@test.com")
        db_session.add(new_owner)
        db_session.commit()

        response = client.post(
            "/api/leads/nonexistent-lead/change-owner",
            json={
                "new_owner_id": "user-exists",
                "current_user_id": "admin-user",
            },
            headers={"x-user-id": "admin-user", "x-user-role": "admin"}
        )
        assert response.status_code == 404
        assert "not found" in response.json()["message"].lower()

    def test_change_owner_nonexistent_new_owner_returns_404(self, client, db_session):
        """Attempting to change to non-existent owner returns 404."""
        original_owner = User(id="user-original", name="Original Owner", email="original@test.com")
        lead = Lead(
            id="lead-exists",
            title="Existing Lead",
            owner_user_id="user-original",
            priority_score=50,
        )
        db_session.add_all([original_owner, lead])
        db_session.commit()

        response = client.post(
            "/api/leads/lead-exists/change-owner",
            json={
                "new_owner_id": "nonexistent-user",
                "current_user_id": "admin-user",
            },
            headers={"x-user-id": "admin-user", "x-user-role": "admin"}
        )
        assert response.status_code == 404
        assert "not found" in response.json()["message"].lower()

    def test_change_owner_same_owner_returns_400(self, client, db_session):
        """Attempting to change to the same owner returns 400."""
        owner = User(id="user-same", name="Same Owner", email="same@test.com")
        lead = Lead(
            id="lead-same-owner",
            title="Lead with Same Owner",
            owner_user_id="user-same",
            priority_score=50,
        )
        db_session.add_all([owner, lead])
        db_session.commit()

        response = client.post(
            "/api/leads/lead-same-owner/change-owner",
            json={
                "new_owner_id": "user-same",
                "current_user_id": "admin-user",
            },
            headers={"x-user-id": "admin-user", "x-user-role": "admin"}
        )
        assert response.status_code == 400
        assert "same" in response.json()["message"].lower()

    def test_change_owner_unauthorized_user_returns_403(self, client, db_session):
        """Non-owner sales user cannot change another user's lead."""
        original_owner = User(id="user-owner", name="Lead Owner", email="owner@test.com")
        new_owner = User(id="user-new-owner", name="New Owner", email="new@test.com")
        other_user = User(id="user-other", name="Other User", email="other@test.com")
        lead = Lead(
            id="lead-unauthorized",
            title="Lead for Unauthorized Test",
            owner_user_id="user-owner",
            priority_score=50,
        )
        db_session.add_all([original_owner, new_owner, other_user, lead])
        db_session.commit()

        # Execute: Attempt to change owner as a different sales user (not owner)
        response = client.post(
            "/api/leads/lead-unauthorized/change-owner",
            json={
                "new_owner_id": "user-new-owner",
                "current_user_id": "user-other",
            },
            headers={"x-user-id": "user-other", "x-user-role": "sales"}
        )

        assert response.status_code == 403
        assert "owner" in response.json()["message"].lower() or "manager" in response.json()["message"].lower()

    def test_change_owner_updates_lead_in_database(self, client, db_session):
        """Change owner actually updates the lead in the database."""
        original_owner = User(id="user-db-original", name="Original", email="original@test.com")
        new_owner = User(id="user-db-new", name="New", email="new@test.com")
        lead = Lead(
            id="lead-db-update",
            title="Lead for DB Update",
            owner_user_id="user-db-original",
            priority_score=50,
        )
        db_session.add_all([original_owner, new_owner, lead])
        db_session.commit()

        # Execute
        response = client.post(
            "/api/leads/lead-db-update/change-owner",
            json={
                "new_owner_id": "user-db-new",
                "current_user_id": "admin-user",
            },
            headers={"x-user-id": "admin-user", "x-user-role": "admin"}
        )
        assert response.status_code == 200

        # Verify database update
        db_session.expire_all()
        updated_lead = db_session.query(Lead).filter(Lead.id == "lead-db-update").first()
        assert updated_lead.owner_user_id == "user-db-new"

    def test_change_owner_lead_without_owner(self, client, db_session):
        """Changing owner of a lead that has no current owner."""
        new_owner = User(id="user-new-assign", name="New Owner", email="new@test.com")
        lead = Lead(
            id="lead-no-owner",
            title="Lead without Owner",
            owner_user_id=None,
            priority_score=50,
        )
        db_session.add_all([new_owner, lead])
        db_session.commit()

        # Execute: Assign owner as admin
        response = client.post(
            "/api/leads/lead-no-owner/change-owner",
            json={
                "new_owner_id": "user-new-assign",
                "current_user_id": "admin-user",
            },
            headers={"x-user-id": "admin-user", "x-user-role": "admin"}
        )

        assert response.status_code == 200
        body = response.json()
        assert body["previous_owner_id"] is None
        assert body["new_owner_id"] == "user-new-assign"


class TestChangeLeadOwnerAuditLog:
    """Test audit log entries for lead owner changes."""

    def test_change_owner_creates_audit_log(self, client, db_session):
        """Changing lead owner should create an audit log entry."""
        # Register audit listeners
        register_audit_listeners()

        # Setup
        original_owner = User(id="user-audit-original", name="Original", email="original@test.com")
        new_owner = User(id="user-audit-new", name="New", email="new@test.com")
        lead = Lead(
            id="lead-audit-change",
            title="Audit Test Lead",
            owner_user_id="user-audit-original",
            priority_score=50,
        )
        db_session.add_all([original_owner, new_owner, lead])
        db_session.commit()

        # Change owner
        response = client.post(
            "/api/leads/lead-audit-change/change-owner",
            json={
                "new_owner_id": "user-audit-new",
                "current_user_id": "admin-user",
            },
            headers={"x-user-id": "admin-user", "x-user-role": "admin"}
        )
        assert response.status_code == 200

        # Check audit log
        audit_logs = db_session.query(AuditLog).filter(
            AuditLog.entity_type == "lead",
            AuditLog.entity_id == "lead-audit-change",
            AuditLog.action == "lead.owner_changed"
        ).all()

        assert len(audit_logs) >= 1

        # Verify the audit log entry
        log = audit_logs[0]
        assert "owner_user_id" in log.changes
        assert log.changes["owner_user_id"]["old"] == "user-audit-original"
        assert log.changes["owner_user_id"]["new"] == "user-audit-new"

    def test_change_owner_audit_includes_changed_by(self, client, db_session):
        """Audit log should include who made the change."""
        # Register audit listeners
        register_audit_listeners()

        # Setup
        original_owner = User(id="user-changed-by-original", name="Original", email="original@test.com")
        new_owner = User(id="user-changed-by-new", name="New", email="new@test.com")
        lead = Lead(
            id="lead-changed-by-test",
            title="Changed By Test Lead",
            owner_user_id="user-changed-by-original",
            priority_score=50,
        )
        db_session.add_all([original_owner, new_owner, lead])
        db_session.commit()

        # Change owner
        response = client.post(
            "/api/leads/lead-changed-by-test/change-owner",
            json={
                "new_owner_id": "user-changed-by-new",
                "current_user_id": "specific-admin-user",
            },
            headers={"x-user-id": "specific-admin-user", "x-user-role": "admin"}
        )
        assert response.status_code == 200

        # Check audit log for changed_by
        audit_logs = db_session.query(AuditLog).filter(
            AuditLog.entity_type == "lead",
            AuditLog.entity_id == "lead-changed-by-test",
            AuditLog.action == "lead.owner_changed"
        ).all()

        assert len(audit_logs) >= 1
        log = audit_logs[0]
        assert "changed_by" in log.changes
        assert log.changes["changed_by"] == "specific-admin-user"
