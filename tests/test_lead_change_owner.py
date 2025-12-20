"""
Tests for Lead change-owner functionality.

Tests that:
1. change_lead_owner endpoint correctly changes the lead owner
2. Previous owner is added as a member when addPreviousOwnerAsMember=True
3. Proper validation of lead existence, new owner existence and status
4. Permission checks (only owner, manager, admin can change)
5. Audit log entries are created with action="lead.owner_changed"
"""

import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from main import app
from database import Base
from models import Lead, User, LeadMember, AuditLog
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


class TestChangeOwnerEndpoint:
    """Test the POST /{lead_id}/change-owner endpoint."""

    def test_change_owner_success(self, client, db_session):
        """Successfully change a lead's owner."""
        # Setup: Create a lead and users
        owner1 = User(id="owner-1", name="Owner 1", email="owner1@test.com", is_active=True)
        owner2 = User(id="owner-2", name="Owner 2", email="owner2@test.com", is_active=True)
        lead = Lead(
            id="lead-change-owner",
            title="Test Lead",
            owner_user_id="owner-1",
            priority_score=50,
        )
        db_session.add_all([owner1, owner2, lead])
        db_session.commit()

        # Execute: Change owner (as the current owner)
        response = client.post(
            "/api/leads/lead-change-owner/change-owner",
            json={
                "newOwnerId": "owner-2",
                "addPreviousOwnerAsMember": True,
                "currentUserId": "owner-1"
            },
            headers={"x-user-id": "owner-1", "x-user-role": "sales"}
        )

        # Verify response
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "owner_changed"
        assert body["lead_id"] == "lead-change-owner"
        assert body["previous_owner_id"] == "owner-1"
        assert body["new_owner_id"] == "owner-2"
        assert body["previous_owner_added_as_member"] is True
        assert "changed_at" in body
        assert body["changed_by"] == "owner-1"

    def test_change_owner_adds_previous_owner_as_member(self, client, db_session):
        """Previous owner should be added as a collaborator when flag is True."""
        # Setup
        owner1 = User(id="user-1", name="User 1", email="user1@test.com", is_active=True)
        owner2 = User(id="user-2", name="User 2", email="user2@test.com", is_active=True)
        lead = Lead(
            id="lead-member-test",
            title="Test Lead",
            owner_user_id="user-1",
            priority_score=50,
        )
        db_session.add_all([owner1, owner2, lead])
        db_session.commit()

        # Execute
        response = client.post(
            "/api/leads/lead-member-test/change-owner",
            json={
                "newOwnerId": "user-2",
                "addPreviousOwnerAsMember": True,
                "currentUserId": "user-1"
            },
            headers={"x-user-id": "user-1", "x-user-role": "sales"}
        )
        assert response.status_code == 200

        # Verify member was added
        member = db_session.query(LeadMember).filter(
            LeadMember.lead_id == "lead-member-test",
            LeadMember.user_id == "user-1"
        ).first()
        assert member is not None
        assert member.role == "collaborator"

    def test_change_owner_skips_member_when_flag_is_false(self, client, db_session):
        """Previous owner should NOT be added as a member when flag is False."""
        # Setup
        owner1 = User(id="user-a", name="User A", email="usera@test.com", is_active=True)
        owner2 = User(id="user-b", name="User B", email="userb@test.com", is_active=True)
        lead = Lead(
            id="lead-no-member-test",
            title="Test Lead",
            owner_user_id="user-a",
            priority_score=50,
        )
        db_session.add_all([owner1, owner2, lead])
        db_session.commit()

        # Execute
        response = client.post(
            "/api/leads/lead-no-member-test/change-owner",
            json={
                "newOwnerId": "user-b",
                "addPreviousOwnerAsMember": False,
                "currentUserId": "user-a"
            },
            headers={"x-user-id": "user-a", "x-user-role": "sales"}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["previous_owner_added_as_member"] is False

        # Verify no member was added
        member = db_session.query(LeadMember).filter(
            LeadMember.lead_id == "lead-no-member-test",
            LeadMember.user_id == "user-a"
        ).first()
        assert member is None

    def test_change_owner_nonexistent_lead_returns_404(self, client, db_session):
        """Changing owner of non-existent lead should return 404."""
        owner = User(id="user-x", name="User X", email="userx@test.com", is_active=True)
        db_session.add(owner)
        db_session.commit()

        response = client.post(
            "/api/leads/nonexistent-lead/change-owner",
            json={
                "newOwnerId": "user-x",
                "addPreviousOwnerAsMember": True,
                "currentUserId": "user-x"
            },
            headers={"x-user-id": "user-x", "x-user-role": "admin"}
        )
        assert response.status_code == 404
        assert "not found" in response.json()["message"].lower()

    def test_change_owner_nonexistent_new_owner_returns_404(self, client, db_session):
        """Changing owner to non-existent user should return 404."""
        owner = User(id="user-y", name="User Y", email="usery@test.com", is_active=True)
        lead = Lead(
            id="lead-exists",
            title="Existing Lead",
            owner_user_id="user-y",
            priority_score=50,
        )
        db_session.add_all([owner, lead])
        db_session.commit()

        response = client.post(
            "/api/leads/lead-exists/change-owner",
            json={
                "newOwnerId": "nonexistent-user",
                "addPreviousOwnerAsMember": True,
                "currentUserId": "user-y"
            },
            headers={"x-user-id": "user-y", "x-user-role": "sales"}
        )
        assert response.status_code == 404
        assert "not found" in response.json()["message"].lower()

    def test_change_owner_inactive_new_owner_returns_400(self, client, db_session):
        """Changing owner to inactive user should return 400."""
        owner = User(id="active-user", name="Active User", email="active@test.com", is_active=True)
        inactive_user = User(id="inactive-user", name="Inactive User", email="inactive@test.com", is_active=False)
        lead = Lead(
            id="lead-for-inactive",
            title="Test Lead",
            owner_user_id="active-user",
            priority_score=50,
        )
        db_session.add_all([owner, inactive_user, lead])
        db_session.commit()

        response = client.post(
            "/api/leads/lead-for-inactive/change-owner",
            json={
                "newOwnerId": "inactive-user",
                "addPreviousOwnerAsMember": True,
                "currentUserId": "active-user"
            },
            headers={"x-user-id": "active-user", "x-user-role": "sales"}
        )
        assert response.status_code == 400
        assert "inactive" in response.json()["message"].lower()

    def test_change_owner_same_owner_returns_400(self, client, db_session):
        """Changing owner to the same user should return 400."""
        owner = User(id="same-user", name="Same User", email="same@test.com", is_active=True)
        lead = Lead(
            id="lead-same-owner",
            title="Test Lead",
            owner_user_id="same-user",
            priority_score=50,
        )
        db_session.add_all([owner, lead])
        db_session.commit()

        response = client.post(
            "/api/leads/lead-same-owner/change-owner",
            json={
                "newOwnerId": "same-user",
                "addPreviousOwnerAsMember": True,
                "currentUserId": "same-user"
            },
            headers={"x-user-id": "same-user", "x-user-role": "sales"}
        )
        assert response.status_code == 400
        assert "same" in response.json()["message"].lower()

    def test_change_owner_permission_denied_for_non_owner(self, client, db_session):
        """Non-owner without manager/admin role should get 403."""
        owner = User(id="real-owner", name="Real Owner", email="realowner@test.com", is_active=True)
        other_user = User(id="other-user", name="Other User", email="other@test.com", is_active=True)
        new_owner = User(id="new-user", name="New User", email="new@test.com", is_active=True)
        lead = Lead(
            id="lead-perm-test",
            title="Test Lead",
            owner_user_id="real-owner",
            priority_score=50,
        )
        db_session.add_all([owner, other_user, new_owner, lead])
        db_session.commit()

        # Try to change as someone who is not the owner and has sales role
        response = client.post(
            "/api/leads/lead-perm-test/change-owner",
            json={
                "newOwnerId": "new-user",
                "addPreviousOwnerAsMember": True,
                "currentUserId": "other-user"
            },
            headers={"x-user-id": "other-user", "x-user-role": "sales"}
        )
        assert response.status_code == 403
        assert "permission" in response.json()["message"].lower()

    def test_change_owner_manager_can_change(self, client, db_session):
        """Manager should be able to change ownership even if not owner."""
        owner = User(id="lead-owner", name="Lead Owner", email="leadowner@test.com", is_active=True)
        manager = User(id="manager-user", name="Manager", email="manager@test.com", is_active=True)
        new_owner = User(id="new-owner", name="New Owner", email="newowner@test.com", is_active=True)
        lead = Lead(
            id="lead-manager-test",
            title="Test Lead",
            owner_user_id="lead-owner",
            priority_score=50,
        )
        db_session.add_all([owner, manager, new_owner, lead])
        db_session.commit()

        # Manager can change ownership
        response = client.post(
            "/api/leads/lead-manager-test/change-owner",
            json={
                "newOwnerId": "new-owner",
                "addPreviousOwnerAsMember": True,
                "currentUserId": "manager-user"
            },
            headers={"x-user-id": "manager-user", "x-user-role": "manager"}
        )
        assert response.status_code == 200

    def test_change_owner_admin_can_change(self, client, db_session):
        """Admin should be able to change ownership even if not owner."""
        owner = User(id="orig-owner", name="Original Owner", email="origowner@test.com", is_active=True)
        admin = User(id="admin-user", name="Admin", email="admin@test.com", is_active=True)
        new_owner = User(id="another-owner", name="Another Owner", email="another@test.com", is_active=True)
        lead = Lead(
            id="lead-admin-test",
            title="Test Lead",
            owner_user_id="orig-owner",
            priority_score=50,
        )
        db_session.add_all([owner, admin, new_owner, lead])
        db_session.commit()

        # Admin can change ownership
        response = client.post(
            "/api/leads/lead-admin-test/change-owner",
            json={
                "newOwnerId": "another-owner",
                "addPreviousOwnerAsMember": False,
                "currentUserId": "admin-user"
            },
            headers={"x-user-id": "admin-user", "x-user-role": "admin"}
        )
        assert response.status_code == 200

    def test_change_owner_deleted_lead_returns_400(self, client, db_session):
        """Changing owner of deleted lead should return 400."""
        now = datetime.now(timezone.utc)
        owner = User(id="owner-deleted", name="Owner", email="ownerdel@test.com", is_active=True)
        new_owner = User(id="new-owner-deleted", name="New Owner", email="newownerdel@test.com", is_active=True)
        lead = Lead(
            id="deleted-lead",
            title="Deleted Lead",
            owner_user_id="owner-deleted",
            priority_score=50,
            deleted_at=now,
        )
        db_session.add_all([owner, new_owner, lead])
        db_session.commit()

        response = client.post(
            "/api/leads/deleted-lead/change-owner",
            json={
                "newOwnerId": "new-owner-deleted",
                "addPreviousOwnerAsMember": True,
                "currentUserId": "owner-deleted"
            },
            headers={"x-user-id": "owner-deleted", "x-user-role": "admin"}
        )
        assert response.status_code == 400
        assert "deleted" in response.json()["message"].lower() or "qualified" in response.json()["message"].lower()


class TestChangeOwnerAuditLog:
    """Test audit log entries for lead ownership changes."""

    def test_change_owner_creates_audit_log(self, client, db_session):
        """Changing lead owner should create an audit log entry."""
        # Setup
        owner1 = User(id="audit-owner-1", name="Owner 1", email="auditowner1@test.com", is_active=True)
        owner2 = User(id="audit-owner-2", name="Owner 2", email="auditowner2@test.com", is_active=True)
        lead = Lead(
            id="audit-lead-change",
            title="Audit Test Lead",
            owner_user_id="audit-owner-1",
            priority_score=50,
        )
        db_session.add_all([owner1, owner2, lead])
        db_session.commit()

        # Change owner
        response = client.post(
            "/api/leads/audit-lead-change/change-owner",
            json={
                "newOwnerId": "audit-owner-2",
                "addPreviousOwnerAsMember": True,
                "currentUserId": "audit-owner-1"
            },
            headers={"x-user-id": "audit-owner-1", "x-user-role": "sales"}
        )
        assert response.status_code == 200

        # Check audit log
        audit_logs = db_session.query(AuditLog).filter(
            AuditLog.entity_type == "lead",
            AuditLog.entity_id == "audit-lead-change",
            AuditLog.action == "lead.owner_changed"
        ).all()

        assert len(audit_logs) >= 1
        log = audit_logs[0]
        assert "owner_user_id" in log.changes
        assert log.changes["owner_user_id"]["old"] == "audit-owner-1"
        assert log.changes["owner_user_id"]["new"] == "audit-owner-2"
        assert log.actor_id == "audit-owner-1"


class TestChangeOwnerMemberDuplication:
    """Test that duplicate members are not added."""

    def test_change_owner_does_not_duplicate_member(self, client, db_session):
        """If previous owner is already a member, should not add again."""
        # Setup
        owner1 = User(id="dup-owner-1", name="Owner 1", email="dupowner1@test.com", is_active=True)
        owner2 = User(id="dup-owner-2", name="Owner 2", email="dupowner2@test.com", is_active=True)
        lead = Lead(
            id="dup-lead-test",
            title="Duplicate Test Lead",
            owner_user_id="dup-owner-1",
            priority_score=50,
        )
        db_session.add_all([owner1, owner2, lead])
        db_session.commit()

        # Pre-add owner1 as a member
        existing_member = LeadMember(
            lead_id="dup-lead-test",
            user_id="dup-owner-1",
            role="collaborator",
        )
        db_session.add(existing_member)
        db_session.commit()

        # Change owner (should not add duplicate)
        response = client.post(
            "/api/leads/dup-lead-test/change-owner",
            json={
                "newOwnerId": "dup-owner-2",
                "addPreviousOwnerAsMember": True,
                "currentUserId": "dup-owner-1"
            },
            headers={"x-user-id": "dup-owner-1", "x-user-role": "sales"}
        )
        assert response.status_code == 200
        body = response.json()
        # Should not add again since already a member
        assert body["previous_owner_added_as_member"] is False

        # Verify only one member entry
        members = db_session.query(LeadMember).filter(
            LeadMember.lead_id == "dup-lead-test",
            LeadMember.user_id == "dup-owner-1"
        ).all()
        assert len(members) == 1
