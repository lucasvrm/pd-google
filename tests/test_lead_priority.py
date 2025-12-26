import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import models
from services.lead_priority_service import calculate_lead_priority, classify_priority_bucket
from database import Base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Create test database
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_lead_priority.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def setup_module(module):
    """Set up test database with required LeadStatus and LeadOrigin records."""
    if os.path.exists("./test_lead_priority.db"):
        os.remove("./test_lead_priority.db")
    
    Base.metadata.create_all(bind=engine)
    
    db = TestingSessionLocal()
    
    # Create LeadStatus records
    status_qualified = models.LeadStatus(id="qualified", code="qualified", label="Qualified", sort_order=1)
    status_lost = models.LeadStatus(id="lost", code="lost", label="Lost", sort_order=2)
    
    # Create LeadOrigin records
    origin_inbound = models.LeadOrigin(id="inbound", code="inbound", label="Inbound", sort_order=1)
    origin_outbound = models.LeadOrigin(id="outbound", code="outbound", label="Outbound", sort_order=2)
    
    db.add_all([status_qualified, status_lost, origin_inbound, origin_outbound])
    db.commit()
    db.close()


def teardown_module(module):
    """Clean up test database."""
    if os.path.exists("./test_lead_priority.db"):
        os.remove("./test_lead_priority.db")


def test_calculate_lead_priority_rewards_recent_engagement():
    db = TestingSessionLocal()
    try:
        now = datetime(2024, 1, 10, tzinfo=timezone.utc)
        lead = models.Lead(
            id="lead-priority-1",
            title="Lead Priority",
            lead_status_id="qualified",
            lead_origin_id="inbound",
            created_at=now - timedelta(days=5),
            updated_at=now - timedelta(days=2),
        )
        db.add(lead)
        db.flush()
        
        stats = models.LeadActivityStats(
            lead_id=lead.id,
            engagement_score=80,
            last_interaction_at=now - timedelta(days=1),
        )
        db.add(stats)
        db.commit()
        
        # Refresh to load relationships
        db.refresh(lead)

        score = calculate_lead_priority(lead, stats, now=now)

        assert 70 <= score <= 100
        assert classify_priority_bucket(score) == "hot"
    finally:
        db.close()


def test_calculate_lead_priority_penalizes_stale_leads():
    db = TestingSessionLocal()
    try:
        now = datetime(2024, 1, 10, tzinfo=timezone.utc)
        lead = models.Lead(
            id="lead-priority-2",
            title="Lead Priority Cold",
            lead_status_id="lost",
            lead_origin_id="outbound",
            created_at=now - timedelta(days=120),
            updated_at=now - timedelta(days=90),
        )
        db.add(lead)
        db.flush()
        
        stats = models.LeadActivityStats(
            lead_id=lead.id,
            engagement_score=5,
            last_interaction_at=now - timedelta(days=80),
        )
        db.add(stats)
        db.commit()
        
        # Refresh to load relationships
        db.refresh(lead)

        score = calculate_lead_priority(lead, stats, now=now)

        assert score < 40
        assert classify_priority_bucket(score) == "cold"
    finally:
        db.close()
