"""
Tests for Lead soft delete functionality.

Tests that:
1. Leads with deleted_at set are excluded from sales-view
2. Audit log entries are created when leads are soft deleted
"""

import pytest
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from main import app
from database import Base
from models import Lead, LeadActivityStats, User, AuditLog
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


class TestLeadSoftDeleteInSalesView:
    """Test that soft deleted leads are excluded from sales-view."""

    def test_active_leads_are_returned(self, client):
        """Active leads (without deleted_at) should be returned in sales-view."""
        db = TestingSessionLocal()
        try:
            lead = Lead(
                id="lead-active",
                title="Active Lead",
                priority_score=50,
            )
            db.add(lead)
            db.commit()
        finally:
            db.close()

        response = client.get("/api/leads/sales-view")
        assert response.status_code == 200
        body = response.json()
        ids = [item["id"] for item in body["data"]]
        assert "lead-active" in ids

    def test_soft_deleted_leads_are_excluded(self, client):
        """Leads with deleted_at set should be excluded from sales-view."""
        db = TestingSessionLocal()
        now = datetime.now(timezone.utc)
        try:
            active_lead = Lead(
                id="lead-active-2",
                title="Active Lead 2",
                priority_score=60,
            )
            deleted_lead = Lead(
                id="lead-deleted",
                title="Deleted Lead",
                priority_score=70,
                deleted_at=now,  # Soft deleted
            )
            db.add_all([active_lead, deleted_lead])
            db.commit()
        finally:
            db.close()

        response = client.get("/api/leads/sales-view")
        assert response.status_code == 200
        body = response.json()
        ids = [item["id"] for item in body["data"]]
        
        assert "lead-active-2" in ids
        assert "lead-deleted" not in ids
        assert body["pagination"]["total"] == 1

    def test_multiple_deleted_leads_excluded(self, client):
        """Multiple soft deleted leads should all be excluded."""
        db = TestingSessionLocal()
        now = datetime.now(timezone.utc)
        try:
            leads_to_add = [
                Lead(id="lead-active-a", title="Active A", priority_score=50),
                Lead(id="lead-active-b", title="Active B", priority_score=60),
                Lead(id="lead-deleted-x", title="Deleted X", priority_score=70, deleted_at=now),
                Lead(id="lead-deleted-y", title="Deleted Y", priority_score=80, deleted_at=now - timedelta(days=1)),
                Lead(id="lead-deleted-z", title="Deleted Z", priority_score=90, deleted_at=now - timedelta(hours=1)),
            ]
            db.add_all(leads_to_add)
            db.commit()
        finally:
            db.close()

        response = client.get("/api/leads/sales-view")
        assert response.status_code == 200
        body = response.json()
        ids = [item["id"] for item in body["data"]]
        
        # Only active leads should be returned
        assert set(ids) == {"lead-active-a", "lead-active-b"}
        assert body["pagination"]["total"] == 2

    def test_filters_work_with_soft_delete(self, client):
        """Filters should respect soft delete (deleted leads still excluded)."""
        db = TestingSessionLocal()
        now = datetime.now(timezone.utc)
        try:
            user = User(id="user-owner", name="Owner User", email="owner@example.com")
            
            active_lead = Lead(
                id="lead-owned-active",
                title="Owned Active",
                owner_user_id="user-owner",
                priority_score=50,
            )
            deleted_lead = Lead(
                id="lead-owned-deleted",
                title="Owned Deleted",
                owner_user_id="user-owner",
                priority_score=70,
                deleted_at=now,
            )
            db.add_all([user, active_lead, deleted_lead])
            db.commit()
        finally:
            db.close()

        # Filter by owner - should only return active lead
        response = client.get("/api/leads/sales-view?owner=user-owner")
        assert response.status_code == 200
        body = response.json()
        ids = [item["id"] for item in body["data"]]
        
        assert "lead-owned-active" in ids
        assert "lead-owned-deleted" not in ids


class TestLeadSoftDeleteAuditLog:
    """Test that audit log entries are created when leads are soft deleted."""

    def test_soft_delete_creates_audit_log(self, client):
        """Setting deleted_at should create an audit log entry with action='soft_delete'."""
        db = TestingSessionLocal()
        now = datetime.now(timezone.utc)
        
        try:
            # Register audit listeners
            register_audit_listeners()
            
            # Create a lead
            lead = Lead(
                id="lead-audit-test",
                title="Audit Test Lead",
                priority_score=50,
            )
            db.add(lead)
            db.commit()
            
            # Set audit actor
            set_audit_actor("test-user-123")
            
            # Soft delete the lead
            lead.deleted_at = now
            db.commit()
            
            # Clear audit actor
            clear_audit_actor()
            
            # Check audit log
            audit_logs = db.query(AuditLog).filter(
                AuditLog.entity_type == "lead",
                AuditLog.entity_id == "lead-audit-test",
                AuditLog.action == "soft_delete"
            ).all()
            
            assert len(audit_logs) >= 1
            
            # Verify the audit log entry
            soft_delete_log = next(
                (log for log in audit_logs if log.action == "soft_delete"),
                None
            )
            assert soft_delete_log is not None
            assert soft_delete_log.actor_id == "test-user-123"
            assert "deleted_at" in soft_delete_log.changes
            assert soft_delete_log.changes["deleted_at"]["old"] is None
            
        finally:
            db.close()

    def test_regular_update_does_not_trigger_soft_delete_action(self, client):
        """Regular updates should use 'update' action, not 'soft_delete'."""
        db = TestingSessionLocal()
        
        try:
            # Register audit listeners (safe to call multiple times - SQLAlchemy handles duplicates)
            register_audit_listeners()
            
            # Create a lead
            lead = Lead(
                id="lead-regular-update",
                title="Regular Update Lead",
                priority_score=50,
            )
            db.add(lead)
            db.commit()
            
            # Set audit actor
            set_audit_actor("test-user-456")
            
            # Regular update (not soft delete)
            lead.priority_score = 75
            db.commit()
            
            # Clear audit actor
            clear_audit_actor()
            
            # Check audit log
            update_logs = db.query(AuditLog).filter(
                AuditLog.entity_type == "lead",
                AuditLog.entity_id == "lead-regular-update",
                AuditLog.action == "update"
            ).all()
            
            # There should be at least one update log
            assert len(update_logs) >= 1
            
            # No soft_delete logs should exist for this lead
            soft_delete_logs = db.query(AuditLog).filter(
                AuditLog.entity_type == "lead",
                AuditLog.entity_id == "lead-regular-update",
                AuditLog.action == "soft_delete"
            ).all()
            
            assert len(soft_delete_logs) == 0
            
        finally:
            db.close()
