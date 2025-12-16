"""
Tests for Lead qualification functionality.

Tests that:
1. qualify_lead endpoint correctly qualifies leads and soft deletes them
2. Qualified leads are excluded from sales-view
3. Critical fields are migrated from Lead to Deal
4. Audit log entries are created with action="qualify_and_soft_delete"
5. Validation rules are respected (already deleted, disqualified leads)
"""

import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from main import app
from database import Base
from models import Lead, Deal, User, AuditLog, Tag, LeadTag
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


class TestQualifyLeadEndpoint:
    """Test the POST /{lead_id}/qualify endpoint."""

    def test_qualify_lead_success(self, client, db_session):
        """Successfully qualify a lead links it to a deal and soft deletes it."""
        # Setup: Create a lead and a deal
        lead = Lead(
            id="lead-qualify-test",
            title="Test Lead for Qualification",
            trade_name="Test Trade Name",
            priority_score=50,
        )
        deal = Deal(
            id="deal-target",
            title="Target Deal",
        )
        db_session.add_all([lead, deal])
        db_session.commit()

        # Execute: Qualify the lead
        response = client.post(
            "/api/leads/lead-qualify-test/qualify",
            json={"deal_id": "deal-target"}
        )

        # Verify response
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "qualified"
        assert body["lead_id"] == "lead-qualify-test"
        assert body["deal_id"] == "deal-target"
        assert "qualified_at" in body
        assert "deleted_at" in body
        assert body["migrated_fields"]["legal_name"] == "Test Lead for Qualification"
        assert body["migrated_fields"]["trade_name"] == "Test Trade Name"

    def test_qualified_lead_excluded_from_sales_view(self, client, db_session):
        """Qualified leads should not appear in sales-view."""
        # Setup: Create leads and a deal
        active_lead = Lead(
            id="lead-active",
            title="Active Lead",
            priority_score=60,
        )
        qualified_lead = Lead(
            id="lead-to-qualify",
            title="Lead to Qualify",
            priority_score=70,
        )
        deal = Deal(
            id="deal-1",
            title="Target Deal 1",
        )
        db_session.add_all([active_lead, qualified_lead, deal])
        db_session.commit()

        # Verify both leads appear initially
        response = client.get("/api/leads/sales-view")
        assert response.status_code == 200
        ids_before = [item["id"] for item in response.json()["data"]]
        assert "lead-active" in ids_before
        assert "lead-to-qualify" in ids_before

        # Qualify the lead
        response = client.post(
            "/api/leads/lead-to-qualify/qualify",
            json={"deal_id": "deal-1"}
        )
        assert response.status_code == 200

        # Verify qualified lead is excluded
        response = client.get("/api/leads/sales-view")
        assert response.status_code == 200
        ids_after = [item["id"] for item in response.json()["data"]]
        assert "lead-active" in ids_after
        assert "lead-to-qualify" not in ids_after

    def test_qualify_lead_migrates_fields_to_deal(self, client, db_session):
        """Qualifying a lead should migrate critical fields to the deal."""
        # Setup: Create a lead with all migrateable fields
        user = User(id="user-owner", name="Test Owner", email="owner@test.com")
        lead = Lead(
            id="lead-with-fields",
            title="Company Legal Name",
            trade_name="Company Trade Name",
            owner_user_id="user-owner",
            description="Important lead description",
            priority_score=80,
        )
        deal = Deal(
            id="deal-empty",
            title="Empty Deal",
        )
        db_session.add_all([user, lead, deal])
        db_session.commit()

        # Qualify the lead
        response = client.post(
            "/api/leads/lead-with-fields/qualify",
            json={"deal_id": "deal-empty"}
        )
        assert response.status_code == 200

        # Verify deal was updated
        db_session.expire_all()
        updated_deal = db_session.query(Deal).filter(Deal.id == "deal-empty").first()
        assert updated_deal.legal_name == "Company Legal Name"
        assert updated_deal.trade_name == "Company Trade Name"
        assert updated_deal.owner_user_id == "user-owner"
        assert updated_deal.description == "Important lead description"

    def test_qualify_lead_preserves_existing_deal_fields(self, client, db_session):
        """Qualifying should not overwrite existing deal fields."""
        # Setup: Create a lead and a deal with existing data
        lead = Lead(
            id="lead-migrate",
            title="Lead Legal Name",
            trade_name="Lead Trade Name",
            priority_score=50,
        )
        deal = Deal(
            id="deal-with-data",
            title="Deal Client Name",
            legal_name="Existing Legal Name",  # Should not be overwritten
            trade_name="Existing Trade Name",  # Should not be overwritten
        )
        db_session.add_all([lead, deal])
        db_session.commit()

        # Qualify the lead
        response = client.post(
            "/api/leads/lead-migrate/qualify",
            json={"deal_id": "deal-with-data"}
        )
        assert response.status_code == 200

        # Verify deal fields were preserved
        db_session.expire_all()
        updated_deal = db_session.query(Deal).filter(Deal.id == "deal-with-data").first()
        assert updated_deal.legal_name == "Existing Legal Name"  # Preserved
        assert updated_deal.trade_name == "Existing Trade Name"  # Preserved

    def test_qualify_nonexistent_lead_returns_404(self, client, db_session):
        """Attempting to qualify a non-existent lead should return 404."""
        deal = Deal(id="deal-exists", title="Existing Deal")
        db_session.add(deal)
        db_session.commit()

        response = client.post(
            "/api/leads/nonexistent-lead/qualify",
            json={"deal_id": "deal-exists"}
        )
        assert response.status_code == 404
        assert "not found" in response.json()["message"].lower()

    def test_qualify_with_nonexistent_deal_returns_404(self, client, db_session):
        """Attempting to qualify to a non-existent deal should return 404."""
        lead = Lead(id="lead-exists", title="Existing Lead", priority_score=50)
        db_session.add(lead)
        db_session.commit()

        response = client.post(
            "/api/leads/lead-exists/qualify",
            json={"deal_id": "nonexistent-deal"}
        )
        assert response.status_code == 404
        assert "not found" in response.json()["message"].lower()

    def test_qualify_already_qualified_lead_returns_400(self, client, db_session):
        """Attempting to qualify an already qualified lead should return 400."""
        now = datetime.now(timezone.utc)
        lead = Lead(
            id="lead-already-qualified",
            title="Already Qualified Lead",
            priority_score=50,
            deleted_at=now,  # Already soft deleted
        )
        deal = Deal(id="deal-2", title="Another Deal")
        db_session.add_all([lead, deal])
        db_session.commit()

        response = client.post(
            "/api/leads/lead-already-qualified/qualify",
            json={"deal_id": "deal-2"}
        )
        assert response.status_code == 400
        assert "already qualified" in response.json()["message"].lower()

    def test_qualify_disqualified_lead_returns_400(self, client, db_session):
        """Attempting to qualify a disqualified lead should return 400."""
        now = datetime.now(timezone.utc)
        lead = Lead(
            id="lead-disqualified",
            title="Disqualified Lead",
            priority_score=50,
            disqualified_at=now,
            disqualification_reason="Not a good fit",
        )
        deal = Deal(id="deal-3", title="Deal 3")
        db_session.add_all([lead, deal])
        db_session.commit()

        response = client.post(
            "/api/leads/lead-disqualified/qualify",
            json={"deal_id": "deal-3"}
        )
        assert response.status_code == 400
        assert "disqualified" in response.json()["message"].lower()


class TestQualifyLeadAuditLog:
    """Test audit log entries for lead qualification."""

    def test_qualify_lead_creates_audit_log(self, client, db_session):
        """Qualifying a lead should create an audit log entry."""
        # Register audit listeners
        register_audit_listeners()

        # Setup
        lead = Lead(
            id="lead-audit-qualify",
            title="Audit Test Lead",
            priority_score=50,
        )
        deal = Deal(id="deal-audit", title="Audit Deal")
        db_session.add_all([lead, deal])
        db_session.commit()

        # Qualify the lead
        response = client.post(
            "/api/leads/lead-audit-qualify/qualify",
            json={"deal_id": "deal-audit"}
        )
        assert response.status_code == 200

        # Check audit log
        audit_logs = db_session.query(AuditLog).filter(
            AuditLog.entity_type == "lead",
            AuditLog.entity_id == "lead-audit-qualify",
            AuditLog.action == "qualify_and_soft_delete"
        ).all()

        assert len(audit_logs) >= 1

        # Verify the audit log entry
        log = audit_logs[0]
        assert "qualified_at" in log.changes
        assert "deleted_at" in log.changes
        assert log.changes["qualified_at"]["old"] is None
        assert log.changes["deleted_at"]["old"] is None

    def test_qualify_lead_audit_includes_deal_link(self, client, db_session):
        """Audit log should include qualified_master_deal_id change."""
        # Register audit listeners
        register_audit_listeners()

        # Setup
        lead = Lead(
            id="lead-audit-deal-link",
            title="Deal Link Test Lead",
            priority_score=50,
        )
        deal = Deal(id="deal-link-test", title="Link Test Deal")
        db_session.add_all([lead, deal])
        db_session.commit()

        # Qualify the lead
        response = client.post(
            "/api/leads/lead-audit-deal-link/qualify",
            json={"deal_id": "deal-link-test"}
        )
        assert response.status_code == 200

        # Check audit log for qualified_master_deal_id
        audit_logs = db_session.query(AuditLog).filter(
            AuditLog.entity_type == "lead",
            AuditLog.entity_id == "lead-audit-deal-link"
        ).all()

        # Find the qualification audit log
        qualify_log = next(
            (log for log in audit_logs if log.action == "qualify_and_soft_delete"),
            None
        )
        assert qualify_log is not None
        assert "qualified_master_deal_id" in qualify_log.changes
        assert qualify_log.changes["qualified_master_deal_id"]["new"] == "deal-link-test"


class TestQualifyLeadWithTags:
    """Test that tags are properly tracked during qualification."""

    def test_qualify_lead_includes_tags_in_response(self, client, db_session):
        """Response should include tag IDs that were associated with the lead."""
        # Setup: Create lead with tags
        tag1 = Tag(id="tag-1", name="Important", color="#ff0000")
        tag2 = Tag(id="tag-2", name="VIP", color="#00ff00")
        lead = Lead(
            id="lead-with-tags",
            title="Lead with Tags",
            priority_score=50,
        )
        db_session.add_all([tag1, tag2, lead])
        db_session.commit()

        # Link tags to lead
        lead_tag1 = LeadTag(lead_id="lead-with-tags", tag_id="tag-1")
        lead_tag2 = LeadTag(lead_id="lead-with-tags", tag_id="tag-2")
        db_session.add_all([lead_tag1, lead_tag2])
        db_session.commit()

        # Create deal
        deal = Deal(id="deal-tags", title="Deal for Tags")
        db_session.add(deal)
        db_session.commit()

        # Qualify the lead
        response = client.post(
            "/api/leads/lead-with-tags/qualify",
            json={"deal_id": "deal-tags"}
        )
        assert response.status_code == 200
        body = response.json()

        # Verify tags are in response
        assert "tags" in body["migrated_fields"]
        assert set(body["migrated_fields"]["tags"]) == {"tag-1", "tag-2"}
