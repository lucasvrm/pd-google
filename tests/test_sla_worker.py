"""
Integration tests for SLA Worker

Tests that verify:
1. Forgotten leads (last_interaction > threshold) are detected
2. check_sla_breaches creates "SLA Breach" tag and audit log
3. SLA breach stats are accurate
4. SLA breach resolution works correctly
"""

import pytest
import os
import uuid
from datetime import datetime, timedelta, timezone
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from database import Base
import models
from services.sla_worker import (
    check_sla_breaches,
    get_sla_breach_stats,
    clear_sla_breach_tag,
    DEFAULT_SLA_THRESHOLD_DAYS
)
from services.audit_service import register_audit_listeners


# Setup Test DB
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_sla_worker.db"
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
    if os.path.exists("./test_sla_worker.db"):
        os.remove("./test_sla_worker.db")


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


class TestSLABreachDetection:
    """Test SLA breach detection for forgotten leads."""

    def test_detects_forgotten_lead_beyond_threshold(self, db_session, test_user, test_lead_status):
        """
        Test that a lead with last_interaction beyond threshold is detected as SLA breach.
        """
        # Create a forgotten lead (last interaction 10 days ago)
        forgotten_lead = models.Lead(
            id=str(uuid.uuid4()),
            title="Forgotten Lead",
            lead_status_id=test_lead_status.id,
            owner_user_id=test_user.id,
            last_interaction_at=datetime.now(timezone.utc) - timedelta(days=10),
            created_at=datetime.now(timezone.utc) - timedelta(days=30)
        )
        db_session.add(forgotten_lead)
        db_session.commit()
        
        # Run SLA check with 7-day threshold
        result = check_sla_breaches(db_session, threshold_days=7, actor_id=test_user.id)
        
        # Verify lead was detected
        assert forgotten_lead.id in result["breached_leads"]
        assert result["tagged_count"] >= 1
        assert result["audit_logs_created"] >= 1
        assert result["threshold_used"] == 7

    def test_ignores_recent_lead_within_threshold(self, db_session, test_user, test_lead_status):
        """
        Test that a lead with recent interaction is NOT flagged as SLA breach.
        """
        # Create a recent lead (last interaction 3 days ago)
        recent_lead = models.Lead(
            id=str(uuid.uuid4()),
            title="Recent Lead",
            lead_status_id=test_lead_status.id,
            owner_user_id=test_user.id,
            last_interaction_at=datetime.now(timezone.utc) - timedelta(days=3),
            created_at=datetime.now(timezone.utc) - timedelta(days=5)
        )
        db_session.add(recent_lead)
        db_session.commit()
        
        # Run SLA check with 7-day threshold
        result = check_sla_breaches(db_session, threshold_days=7, actor_id=test_user.id)
        
        # Verify lead was NOT detected
        assert recent_lead.id not in result["breached_leads"]

    def test_detects_never_interacted_lead(self, db_session, test_user, test_lead_status):
        """
        Test that a lead with no interaction history and old creation date is detected.
        """
        # Create a lead with no interaction (NULL last_interaction_at)
        old_lead = models.Lead(
            id=str(uuid.uuid4()),
            title="Never Contacted Lead",
            lead_status_id=test_lead_status.id,
            owner_user_id=test_user.id,
            last_interaction_at=None,
            created_at=datetime.now(timezone.utc) - timedelta(days=15)
        )
        db_session.add(old_lead)
        db_session.commit()
        
        # Run SLA check with 7-day threshold
        result = check_sla_breaches(db_session, threshold_days=7, actor_id=test_user.id)
        
        # Verify lead was detected
        assert old_lead.id in result["breached_leads"]

    def test_multiple_forgotten_leads(self, db_session, test_user, test_lead_status):
        """
        Test detection of multiple forgotten leads.
        """
        # Create multiple forgotten leads
        forgotten_leads = []
        for i in range(5):
            lead = models.Lead(
                id=str(uuid.uuid4()),
                title=f"Forgotten Lead {i}",
                lead_status_id=test_lead_status.id,
                owner_user_id=test_user.id,
                last_interaction_at=datetime.now(timezone.utc) - timedelta(days=10 + i),
                created_at=datetime.now(timezone.utc) - timedelta(days=30)
            )
            db_session.add(lead)
            forgotten_leads.append(lead)
        
        db_session.commit()
        
        # Run SLA check
        result = check_sla_breaches(db_session, threshold_days=7, actor_id=test_user.id)
        
        # Verify all leads were detected
        for lead in forgotten_leads:
            assert lead.id in result["breached_leads"]
        
        assert result["tagged_count"] == 5
        assert result["audit_logs_created"] == 5


class TestSLABreachTagging:
    """Test that SLA breaches create correct tags and audit logs."""

    def test_creates_sla_breach_tag(self, db_session, test_user, test_lead_status):
        """
        Test that check_sla_breaches creates "SLA Breach" tag.
        """
        # Create forgotten lead
        lead = models.Lead(
            id=str(uuid.uuid4()),
            title="Test Lead",
            lead_status_id=test_lead_status.id,
            owner_user_id=test_user.id,
            last_interaction_at=datetime.now(timezone.utc) - timedelta(days=10)
        )
        db_session.add(lead)
        db_session.commit()
        
        # Run SLA check
        check_sla_breaches(db_session, threshold_days=7, actor_id=test_user.id)
        
        # Verify tag exists
        sla_tag = db_session.query(models.Tag).filter(
            models.Tag.name == "SLA Breach"
        ).first()
        
        assert sla_tag is not None
        assert sla_tag.name == "SLA Breach"
        assert sla_tag.color == "#FF0000"

    def test_adds_sla_breach_tag_to_lead(self, db_session, test_user, test_lead_status):
        """
        Test that the SLA Breach tag is added to forgotten leads.
        """
        # Create forgotten lead
        lead = models.Lead(
            id=str(uuid.uuid4()),
            title="Test Lead",
            lead_status_id=test_lead_status.id,
            owner_user_id=test_user.id,
            last_interaction_at=datetime.now(timezone.utc) - timedelta(days=10)
        )
        db_session.add(lead)
        db_session.commit()
        
        # Run SLA check
        check_sla_breaches(db_session, threshold_days=7, actor_id=test_user.id)
        
        # Refresh lead to get updated tags
        db_session.refresh(lead)
        
        # Verify lead has SLA Breach tag
        tag_names = [tag.name for tag in lead.tags]
        assert "SLA Breach" in tag_names

    def test_creates_audit_log_for_breach(self, db_session, test_user, test_lead_status):
        """
        Test that an audit log is created for SLA breach.
        """
        # Create forgotten lead
        lead = models.Lead(
            id=str(uuid.uuid4()),
            title="Test Lead",
            lead_status_id=test_lead_status.id,
            owner_user_id=test_user.id,
            last_interaction_at=datetime.now(timezone.utc) - timedelta(days=10)
        )
        db_session.add(lead)
        db_session.commit()
        lead_id = lead.id
        
        # Run SLA check
        check_sla_breaches(db_session, threshold_days=7, actor_id=test_user.id)
        
        # Verify audit log was created
        audit_logs = db_session.query(models.AuditLog).filter(
            models.AuditLog.entity_type == "lead",
            models.AuditLog.entity_id == lead_id,
            models.AuditLog.action == "sla_breach"
        ).all()
        
        assert len(audit_logs) == 1
        audit_log = audit_logs[0]
        
        # Verify audit log details
        assert audit_log.actor_id == test_user.id
        assert audit_log.changes is not None
        assert "sla_status" in audit_log.changes
        assert audit_log.changes["sla_status"]["old"] == "ok"
        assert audit_log.changes["sla_status"]["new"] == "breached"
        assert "threshold_days" in audit_log.changes
        assert audit_log.changes["threshold_days"] == 7

    def test_does_not_duplicate_tag_on_rerun(self, db_session, test_user, test_lead_status):
        """
        Test that running check_sla_breaches multiple times doesn't duplicate tags.
        """
        # Create forgotten lead
        lead = models.Lead(
            id=str(uuid.uuid4()),
            title="Test Lead",
            lead_status_id=test_lead_status.id,
            owner_user_id=test_user.id,
            last_interaction_at=datetime.now(timezone.utc) - timedelta(days=10)
        )
        db_session.add(lead)
        db_session.commit()
        
        # Run SLA check first time
        result1 = check_sla_breaches(db_session, threshold_days=7, actor_id=test_user.id)
        assert result1["tagged_count"] == 1
        
        # Run SLA check second time
        result2 = check_sla_breaches(db_session, threshold_days=7, actor_id=test_user.id)
        assert result2["tagged_count"] == 0  # Already tagged, so no new tags
        
        # Verify lead still has only one SLA Breach tag
        db_session.refresh(lead)
        sla_tags = [tag for tag in lead.tags if tag.name == "SLA Breach"]
        assert len(sla_tags) == 1


class TestSLABreachStats:
    """Test SLA breach statistics."""

    def test_get_sla_breach_stats(self, db_session, test_user, test_lead_status):
        """
        Test getting SLA breach statistics.
        """
        # Create and breach some leads
        for i in range(3):
            lead = models.Lead(
                id=str(uuid.uuid4()),
                title=f"Lead {i}",
                lead_status_id=test_lead_status.id,
                owner_user_id=test_user.id,
                last_interaction_at=datetime.now(timezone.utc) - timedelta(days=10)
            )
            db_session.add(lead)
        
        db_session.commit()
        
        # Run SLA check
        check_sla_breaches(db_session, threshold_days=7, actor_id=test_user.id)
        
        # Get stats
        stats = get_sla_breach_stats(db_session)
        
        assert stats["total_breached"] == 3
        assert stats["recent_breaches"] == 3


class TestSLABreachResolution:
    """Test clearing SLA breach tags."""

    def test_clear_sla_breach_tag(self, db_session, test_user, test_lead_status):
        """
        Test clearing SLA breach tag from a lead.
        """
        from services.audit_service import set_audit_actor, clear_audit_actor
        
        # Set audit actor before creating lead
        set_audit_actor(test_user.id)
        
        # Create and breach a lead
        lead = models.Lead(
            id=str(uuid.uuid4()),
            title="Test Lead",
            lead_status_id=test_lead_status.id,
            owner_user_id=test_user.id,
            last_interaction_at=datetime.now(timezone.utc) - timedelta(days=10)
        )
        db_session.add(lead)
        db_session.commit()
        
        clear_audit_actor()
        
        # Breach the lead
        check_sla_breaches(db_session, threshold_days=7, actor_id=test_user.id)
        
        # Verify lead has tag
        db_session.refresh(lead)
        tag_names = [tag.name for tag in lead.tags]
        assert "SLA Breach" in tag_names
        
        # Clear the tag
        result = clear_sla_breach_tag(db_session, lead.id, actor_id=test_user.id)
        assert result is True
        
        # Verify tag was removed
        db_session.refresh(lead)
        tag_names = [tag.name for tag in lead.tags]
        assert "SLA Breach" not in tag_names

    def test_clear_creates_resolution_audit_log(self, db_session, test_user, test_lead_status):
        """
        Test that clearing SLA breach creates a resolution audit log.
        """
        from services.audit_service import set_audit_actor, clear_audit_actor
        
        # Set audit actor before creating lead
        set_audit_actor(test_user.id)
        
        # Create and breach a lead
        lead = models.Lead(
            id=str(uuid.uuid4()),
            title="Test Lead",
            lead_status_id=test_lead_status.id,
            owner_user_id=test_user.id,
            last_interaction_at=datetime.now(timezone.utc) - timedelta(days=10)
        )
        db_session.add(lead)
        db_session.commit()
        lead_id = lead.id
        
        clear_audit_actor()
        
        # Breach the lead
        check_sla_breaches(db_session, threshold_days=7, actor_id=test_user.id)
        
        # Clear the tag
        clear_sla_breach_tag(db_session, lead_id, actor_id=test_user.id)
        
        # Verify resolution audit log was created
        audit_logs = db_session.query(models.AuditLog).filter(
            models.AuditLog.entity_type == "lead",
            models.AuditLog.entity_id == lead_id,
            models.AuditLog.action == "sla_breach_resolved"
        ).all()
        
        assert len(audit_logs) == 1
        audit_log = audit_logs[0]
        
        assert audit_log.actor_id == test_user.id
        assert audit_log.changes["sla_status"]["old"] == "breached"
        assert audit_log.changes["sla_status"]["new"] == "ok"


class TestSLAWorkerIntegration:
    """Full integration test for SLA worker flow."""

    def test_full_sla_workflow(self, db_session, test_user, test_lead_status):
        """
        Test the complete SLA workflow:
        1. Seed a forgotten lead
        2. Run check_sla_breaches
        3. Verify tag and audit log
        4. Resolve the breach
        5. Verify resolution
        """
        from services.audit_service import set_audit_actor, clear_audit_actor
        
        # Set audit actor before creating lead
        set_audit_actor(test_user.id)
        
        # Step 1: Seed a forgotten lead
        forgotten_lead = models.Lead(
            id=str(uuid.uuid4()),
            title="Forgotten Lead",
            lead_status_id=test_lead_status.id,
            owner_user_id=test_user.id,
            last_interaction_at=datetime.now(timezone.utc) - timedelta(days=10),
            priority_score=5
        )
        db_session.add(forgotten_lead)
        db_session.commit()
        lead_id = forgotten_lead.id
        
        clear_audit_actor()
        
        # Step 2: Run check_sla_breaches manually
        result = check_sla_breaches(db_session, threshold_days=7, actor_id=test_user.id)
        
        # Step 3: Assert that the lead received the "SLA Breach" tag/audit log
        assert lead_id in result["breached_leads"]
        assert result["tagged_count"] >= 1
        assert result["audit_logs_created"] >= 1
        
        # Verify tag
        db_session.refresh(forgotten_lead)
        tag_names = [tag.name for tag in forgotten_lead.tags]
        assert "SLA Breach" in tag_names
        
        # Verify audit log
        audit_logs = db_session.query(models.AuditLog).filter(
            models.AuditLog.entity_type == "lead",
            models.AuditLog.entity_id == lead_id,
            models.AuditLog.action == "sla_breach"
        ).all()
        assert len(audit_logs) == 1
        
        # Step 4: Simulate interaction and resolve breach
        forgotten_lead.last_interaction_at = datetime.now(timezone.utc)
        db_session.commit()
        
        clear_sla_breach_tag(db_session, lead_id, actor_id=test_user.id)
        
        # Step 5: Verify resolution
        db_session.refresh(forgotten_lead)
        tag_names = [tag.name for tag in forgotten_lead.tags]
        assert "SLA Breach" not in tag_names
        
        # Verify resolution audit log
        resolution_logs = db_session.query(models.AuditLog).filter(
            models.AuditLog.entity_type == "lead",
            models.AuditLog.entity_id == lead_id,
            models.AuditLog.action == "sla_breach_resolved"
        ).all()
        assert len(resolution_logs) == 1

    def test_custom_threshold(self, db_session, test_user, test_lead_status):
        """
        Test SLA check with custom threshold value.
        """
        from services.audit_service import set_audit_actor, clear_audit_actor
        
        # Set audit actor before creating lead
        set_audit_actor(test_user.id)
        
        # Create lead with 5 days since last interaction
        lead = models.Lead(
            id=str(uuid.uuid4()),
            title="Lead 5 days old",
            lead_status_id=test_lead_status.id,
            owner_user_id=test_user.id,
            last_interaction_at=datetime.now(timezone.utc) - timedelta(days=5)
        )
        db_session.add(lead)
        db_session.commit()
        
        clear_audit_actor()
        
        # Run with 3-day threshold (should breach)
        result1 = check_sla_breaches(db_session, threshold_days=3, actor_id=test_user.id)
        assert lead.id in result1["breached_leads"]
        
        # Clear the tag for next test
        db_session.query(models.LeadTag).filter(
            models.LeadTag.lead_id == lead.id
        ).delete()
        db_session.commit()
        
        # Run with 7-day threshold (should NOT breach)
        result2 = check_sla_breaches(db_session, threshold_days=7, actor_id=test_user.id)
        assert lead.id not in result2["breached_leads"]
