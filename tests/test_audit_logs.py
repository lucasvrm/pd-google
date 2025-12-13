"""
Audit Log Tests

Tests for the audit log system that tracks changes to critical CRM entities.
"""

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from database import Base
import models
from services.audit_service import (
    set_audit_actor,
    get_audit_actor,
    clear_audit_actor,
    register_audit_listeners,
    LEAD_AUDIT_FIELDS,
    DEAL_AUDIT_FIELDS,
)
import os
import uuid
from datetime import datetime, timezone


# Setup Test DB
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_audit_logs.db"

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})

@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="module", autouse=True)
def setup_module():
    """Setup test database and register audit listeners."""
    Base.metadata.create_all(bind=engine)
    register_audit_listeners()
    yield
    # Cleanup
    if os.path.exists("./test_audit_logs.db"):
        os.remove("./test_audit_logs.db")


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
    """Create a test user for testing."""
    user = models.User(
        id=str(uuid.uuid4()),
        name="Test User",
        email="test@example.com"
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
        code="qualified",
        label="Qualified",
        is_active=True,
        sort_order=1
    )
    db_session.add(status)
    db_session.commit()
    return status


@pytest.fixture
def test_company(db_session):
    """Create a test company."""
    company = models.Company(
        id=str(uuid.uuid4()),
        name="Test Company"
    )
    db_session.add(company)
    db_session.commit()
    return company


class TestAuditContext:
    """Test audit context management."""

    def test_set_and_get_audit_actor(self):
        """Test setting and getting audit actor."""
        test_user_id = str(uuid.uuid4())
        set_audit_actor(test_user_id)
        assert get_audit_actor() == test_user_id
        clear_audit_actor()
        assert get_audit_actor() is None

    def test_clear_audit_actor(self):
        """Test clearing audit actor."""
        set_audit_actor(str(uuid.uuid4()))
        clear_audit_actor()
        assert get_audit_actor() is None


class TestLeadAuditLogs:
    """Test audit logging for Lead model."""

    def test_lead_creation_audit_log(self, db_session, test_user, test_lead_status):
        """Test that lead creation generates an audit log."""
        set_audit_actor(test_user.id)
        
        # Create a new lead
        lead = models.Lead(
            id=str(uuid.uuid4()),
            title="Test Lead",
            lead_status_id=test_lead_status.id,
            owner_user_id=test_user.id,
            priority_score=5
        )
        db_session.add(lead)
        db_session.commit()
        
        # Check audit log was created
        audit_logs = db_session.query(models.AuditLog).filter_by(
            entity_type="lead",
            entity_id=lead.id
        ).all()
        
        assert len(audit_logs) == 1
        audit_log = audit_logs[0]
        assert audit_log.action == "create"
        assert audit_log.actor_id == test_user.id
        assert audit_log.changes is not None
        
        # Check that tracked fields are in changes
        changes = audit_log.changes
        assert "title" in changes or "owner_user_id" in changes
        
        clear_audit_actor()

    def test_lead_update_audit_log(self, db_session, test_user, test_lead_status):
        """Test that lead updates generate audit logs."""
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
        
        # Clear audit logs from creation
        db_session.query(models.AuditLog).filter_by(
            entity_type="lead",
            entity_id=lead.id
        ).delete()
        db_session.commit()
        
        # Update the lead
        lead.title = "Updated Title"
        lead.priority_score = 8
        db_session.commit()
        
        # Check audit log was created
        audit_logs = db_session.query(models.AuditLog).filter_by(
            entity_type="lead",
            entity_id=lead.id,
            action="update"
        ).all()
        
        assert len(audit_logs) == 1
        audit_log = audit_logs[0]
        assert audit_log.actor_id == test_user.id
        
        # Check changes
        changes = audit_log.changes
        assert "title" in changes
        assert changes["title"]["old"] == "Original Title"
        assert changes["title"]["new"] == "Updated Title"
        assert "priority_score" in changes
        assert changes["priority_score"]["old"] == "3"
        assert changes["priority_score"]["new"] == "8"
        
        clear_audit_actor()

    def test_lead_status_change_audit_log(
        self, db_session, test_user, test_lead_status, another_lead_status
    ):
        """Test that lead status changes are logged as 'status_change' action."""
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
        
        # Clear creation audit log
        db_session.query(models.AuditLog).filter_by(
            entity_type="lead",
            entity_id=lead.id
        ).delete()
        db_session.commit()
        
        # Change status
        lead.lead_status_id = another_lead_status.id
        db_session.commit()
        
        # Check audit log
        audit_logs = db_session.query(models.AuditLog).filter_by(
            entity_type="lead",
            entity_id=lead.id,
            action="status_change"
        ).all()
        
        assert len(audit_logs) == 1
        audit_log = audit_logs[0]
        assert audit_log.actor_id == test_user.id
        
        # Check status change is recorded
        changes = audit_log.changes
        assert "lead_status_id" in changes
        assert changes["lead_status_id"]["old"] == test_lead_status.id
        assert changes["lead_status_id"]["new"] == another_lead_status.id
        
        clear_audit_actor()

    def test_lead_no_audit_for_non_tracked_fields(self, db_session, test_user, test_lead_status):
        """Test that changes to non-tracked fields don't create audit logs."""
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
        
        # Clear creation audit log
        db_session.query(models.AuditLog).filter_by(
            entity_type="lead",
            entity_id=lead.id
        ).delete()
        db_session.commit()
        
        # Update updated_at timestamp only (not in tracked fields)
        lead.updated_at = datetime.now(timezone.utc)
        db_session.commit()
        
        # No new audit log should be created
        audit_logs = db_session.query(models.AuditLog).filter_by(
            entity_type="lead",
            entity_id=lead.id
        ).all()
        
        assert len(audit_logs) == 0
        
        clear_audit_actor()


class TestDealAuditLogs:
    """Test audit logging for Deal model."""

    def test_deal_creation_audit_log(self, db_session, test_user, test_company):
        """Test that deal creation generates an audit log."""
        set_audit_actor(test_user.id)
        
        # Create a deal
        deal = models.Deal(
            id=str(uuid.uuid4()),
            title="Test Deal",
            company_id=test_company.id
        )
        db_session.add(deal)
        db_session.commit()
        
        # Check audit log was created
        audit_logs = db_session.query(models.AuditLog).filter_by(
            entity_type="deal",
            entity_id=deal.id
        ).all()
        
        assert len(audit_logs) == 1
        audit_log = audit_logs[0]
        assert audit_log.action == "create"
        assert audit_log.actor_id == test_user.id
        
        clear_audit_actor()

    def test_deal_update_audit_log(self, db_session, test_user, test_company):
        """Test that deal updates generate audit logs."""
        set_audit_actor(test_user.id)
        
        # Create a deal
        deal = models.Deal(
            id=str(uuid.uuid4()),
            title="Original Deal Name",
            company_id=test_company.id
        )
        db_session.add(deal)
        db_session.commit()
        
        # Clear creation audit log
        db_session.query(models.AuditLog).filter_by(
            entity_type="deal",
            entity_id=deal.id
        ).delete()
        db_session.commit()
        
        # Update the deal
        deal.title = "Updated Deal Name"
        db_session.commit()
        
        # Check audit log
        audit_logs = db_session.query(models.AuditLog).filter_by(
            entity_type="deal",
            entity_id=deal.id,
            action="update"
        ).all()
        
        assert len(audit_logs) == 1
        audit_log = audit_logs[0]
        assert audit_log.actor_id == test_user.id
        
        # Check changes
        changes = audit_log.changes
        assert "title" in changes
        assert changes["title"]["old"] == "Original Deal Name"
        assert changes["title"]["new"] == "Updated Deal Name"
        
        clear_audit_actor()


class TestAuditLogQuery:
    """Test querying audit logs."""

    def test_query_audit_logs_by_entity(self, db_session, test_user, test_lead_status):
        """Test querying audit logs for a specific entity."""
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
        
        # Update it multiple times
        lead.title = "Updated Title 1"
        db_session.commit()
        
        lead.priority_score = 10
        db_session.commit()
        
        # Query all audit logs for this lead
        audit_logs = db_session.query(models.AuditLog).filter_by(
            entity_type="lead",
            entity_id=lead.id
        ).order_by(models.AuditLog.timestamp).all()
        
        # Should have 3 logs: create + 2 updates
        assert len(audit_logs) >= 3
        assert audit_logs[0].action == "create"
        
        clear_audit_actor()

    def test_query_audit_logs_by_actor(self, db_session, test_user, test_lead_status):
        """Test querying audit logs by actor."""
        set_audit_actor(test_user.id)
        
        # Create multiple leads
        for i in range(3):
            lead = models.Lead(
                id=str(uuid.uuid4()),
                title=f"Test Lead {i}",
                lead_status_id=test_lead_status.id,
                owner_user_id=test_user.id
            )
            db_session.add(lead)
        db_session.commit()
        
        # Query all audit logs by this user
        audit_logs = db_session.query(models.AuditLog).filter_by(
            actor_id=test_user.id
        ).all()
        
        assert len(audit_logs) >= 3
        
        clear_audit_actor()
