"""
Comprehensive tests for sales view backend functionality.
Tests cover: filtering, ordering, pagination, next_action enrichment.
"""
import os
import sys
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import models
from database import Base
from routers import leads
from services.next_action_service import suggest_next_action

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_sales_backend.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def setup_module(module):
    if os.path.exists("./test_sales_backend.db"):
        os.remove("./test_sales_backend.db")

    Base.metadata.create_all(bind=engine)

    db = TestingSessionLocal()
    now = datetime.now(timezone.utc)

    # Create users
    owner1 = models.User(id="owner-1", name="Alice", email="alice@example.com")
    owner2 = models.User(id="owner-2", name="Bob", email="bob@example.com")
    
    # Create leads with various statuses, origins, and priorities
    lead1 = models.Lead(
        id="lead-1",
        title="Lead 1",
        trade_name="Trade 1",
        lead_status_id="new",
        lead_origin_id="inbound",
        owner_user_id=owner1.id,
        priority_score=80,
        created_at=now - timedelta(days=5),
        last_interaction_at=now - timedelta(days=1),
    )
    lead2 = models.Lead(
        id="lead-2",
        title="Lead 2",
        trade_name="Trade 2",
        lead_status_id="contacted",
        lead_origin_id="outbound",
        owner_user_id=owner1.id,
        priority_score=50,
        created_at=now - timedelta(days=10),
        last_interaction_at=now - timedelta(days=3),
    )
    lead3 = models.Lead(
        id="lead-3",
        title="Lead 3",
        trade_name="Trade 3",
        lead_status_id="qualified",
        lead_origin_id="partner",
        owner_user_id=owner2.id,
        priority_score=90,
        created_at=now - timedelta(days=2),
        last_interaction_at=now - timedelta(hours=5),
    )
    lead4 = models.Lead(
        id="lead-4",
        title="Lead 4",
        trade_name="Trade 4",
        lead_status_id="lost",
        lead_origin_id="inbound",
        owner_user_id=owner2.id,
        priority_score=20,
        created_at=now - timedelta(days=30),
        last_interaction_at=now - timedelta(days=25),
    )
    
    # Create activity stats
    stats1 = models.LeadActivityStats(
        lead_id=lead1.id,
        engagement_score=75,
        last_interaction_at=now - timedelta(days=1),
    )
    stats2 = models.LeadActivityStats(
        lead_id=lead2.id,
        engagement_score=40,
        last_interaction_at=now - timedelta(days=3),
    )
    stats3 = models.LeadActivityStats(
        lead_id=lead3.id,
        engagement_score=85,
        last_interaction_at=now - timedelta(hours=5),
    )
    stats4 = models.LeadActivityStats(
        lead_id=lead4.id,
        engagement_score=10,
        last_interaction_at=now - timedelta(days=25),
    )

    db.add_all([
        owner1, owner2,
        lead1, lead2, lead3, lead4,
        stats1, stats2, stats3, stats4
    ])
    db.commit()
    db.close()


def teardown_module(module):
    if os.path.exists("./test_sales_backend.db"):
        os.remove("./test_sales_backend.db")


def test_suggest_next_action_first_call():
    """Test suggest_next_action for lead without interaction."""
    now = datetime(2024, 1, 10, tzinfo=timezone.utc)
    
    class MockLead:
        id = "test-lead"
        created_at = now - timedelta(days=3)
        qualified_company_id = None
    
    class MockStats:
        last_interaction_at = None
        last_event_at = None
        engagement_score = 0
    
    result = suggest_next_action(MockLead(), MockStats(), now=now)
    
    assert result["code"] == "call_first_time"
    assert "Lead novo" in result["reason"]


def test_suggest_next_action_follow_up():
    """Test suggest_next_action for stale interaction."""
    now = datetime(2024, 1, 10, tzinfo=timezone.utc)
    
    class MockLead:
        id = "test-lead"
        created_at = now - timedelta(days=10)
        qualified_company_id = None
    
    class MockStats:
        last_interaction_at = now - timedelta(days=7)
        last_event_at = None
        engagement_score = 30
    
    result = suggest_next_action(MockLead(), MockStats(), now=now)
    
    assert result["code"] == "send_follow_up"
    assert "7 dias" in result["reason"]


def test_suggest_next_action_prepare_meeting():
    """Test suggest_next_action for future meeting."""
    now = datetime(2024, 1, 10, tzinfo=timezone.utc)
    
    class MockLead:
        id = "test-lead"
        created_at = now - timedelta(days=5)
        qualified_company_id = None
    
    class MockStats:
        last_interaction_at = now - timedelta(days=2)
        last_event_at = now + timedelta(days=3)
        engagement_score = 60
    
    result = suggest_next_action(MockLead(), MockStats(), now=now)
    
    assert result["code"] == "prepare_for_meeting"
    assert "Reunião futura" in result["reason"]


def test_suggest_next_action_qualify():
    """Test suggest_next_action for high engagement without deal."""
    now = datetime(2024, 1, 10, tzinfo=timezone.utc)
    
    class MockLead:
        id = "test-lead"
        created_at = now - timedelta(days=5)
        qualified_company_id = None
    
    class MockStats:
        last_interaction_at = now - timedelta(days=1)
        last_event_at = None
        engagement_score = 85
    
    result = suggest_next_action(MockLead(), MockStats(), now=now)
    
    assert result["code"] == "qualify_to_company"
    assert "Engajamento alto" in result["reason"]


def test_suggest_next_action_monitor():
    """Test suggest_next_action for active engagement - now suggests schedule_meeting.
    
    With Sprint 2/3 changes, engagement_score >= 50 without an upcoming meeting
    triggers 'schedule_meeting' (precedence 6) instead of 'send_follow_up'.
    """
    now = datetime(2024, 1, 10, tzinfo=timezone.utc)
    
    class MockLead:
        id = "test-lead"
        created_at = now - timedelta(days=5)
        qualified_company_id = None
        qualified_master_deal_id = None
        disqualified_at = None
    
    class MockStats:
        last_interaction_at = now - timedelta(days=2)
        last_event_at = None
        next_scheduled_event_at = None
        last_call_at = None
        last_value_asset_at = None
        engagement_score = 50
    
    result = suggest_next_action(MockLead(), MockStats(), now=now)
    
    # With engagement >= 50 and no meeting, we now get schedule_meeting
    assert result["code"] == "schedule_meeting"
    assert "reunião" in result["reason"].lower()


def test_sales_view_attaches_next_action_and_metrics():
    """Test that sales_view endpoint enriches leads with next_action."""
    db = TestingSessionLocal()
    try:
        result = leads.sales_view(page=1, page_size=10, db=db)
        body = result.model_dump()
        
        # Verify next_action is present
        assert len(body["data"]) > 0
        for item in body["data"]:
            assert "next_action" in item
            assert "code" in item["next_action"]
            assert "label" in item["next_action"]
            assert "reason" in item["next_action"]
        
        # Verify pagination metadata
        assert "pagination" in body
        assert body["pagination"]["total"] == 4
        assert body["pagination"]["per_page"] == 10
        assert body["pagination"]["page"] == 1
    finally:
        db.close()


def test_sales_view_filter_by_single_owner():
    """Test filtering by a single owner."""
    db = TestingSessionLocal()
    try:
        result = leads.sales_view(page=1, page_size=10, owner="owner-1", db=db)
        body = result.model_dump()
        
        # Should return 2 leads (lead-1 and lead-2)
        assert body["pagination"]["total"] == 2
        ids = [item["id"] for item in body["data"]]
        assert "lead-1" in ids
        assert "lead-2" in ids
    finally:
        db.close()


def test_sales_view_filter_by_multiple_owners():
    """Test filtering by multiple owners (CSV)."""
    db = TestingSessionLocal()
    try:
        result = leads.sales_view(page=1, page_size=10, owner_ids="owner-1,owner-2", db=db)
        body = result.model_dump()
        
        # Should return all 4 leads
        assert body["pagination"]["total"] == 4
    finally:
        db.close()


def test_sales_view_filter_by_status():
    """Test filtering by status."""
    db = TestingSessionLocal()
    try:
        result = leads.sales_view(page=1, page_size=10, status="new", db=db)
        body = result.model_dump()
        
        assert body["pagination"]["total"] == 1
        assert body["data"][0]["id"] == "lead-1"
        assert body["data"][0]["lead_status_id"] == "new"
    finally:
        db.close()


def test_sales_view_filter_by_multiple_statuses():
    """Test filtering by multiple statuses (CSV)."""
    db = TestingSessionLocal()
    try:
        result = leads.sales_view(page=1, page_size=10, status="new,contacted", db=db)
        body = result.model_dump()
        
        # Should return 2 leads (lead-1 and lead-2)
        assert body["pagination"]["total"] == 2
        ids = [item["id"] for item in body["data"]]
        assert "lead-1" in ids
        assert "lead-2" in ids
    finally:
        db.close()


def test_sales_view_filter_by_origin():
    """Test filtering by origin."""
    db = TestingSessionLocal()
    try:
        result = leads.sales_view(page=1, page_size=10, origin="inbound", db=db)
        body = result.model_dump()
        
        # Should return 2 leads (lead-1 and lead-4)
        assert body["pagination"]["total"] == 2
        ids = [item["id"] for item in body["data"]]
        assert "lead-1" in ids
        assert "lead-4" in ids
    finally:
        db.close()


def test_sales_view_filter_by_multiple_origins():
    """Test filtering by multiple origins (CSV)."""
    db = TestingSessionLocal()
    try:
        result = leads.sales_view(page=1, page_size=10, origin="inbound,partner", db=db)
        body = result.model_dump()
        
        # Should return 3 leads (lead-1, lead-3, lead-4)
        assert body["pagination"]["total"] == 3
        ids = [item["id"] for item in body["data"]]
        assert "lead-1" in ids
        assert "lead-3" in ids
        assert "lead-4" in ids
    finally:
        db.close()


def test_sales_view_order_by_priority_desc():
    """Test ordering by priority (default descending)."""
    db = TestingSessionLocal()
    try:
        result = leads.sales_view(page=1, page_size=10, order_by="priority", db=db)
        body = result.model_dump()
        
        # Should be ordered: lead-3 (90), lead-1 (80), lead-2 (50), lead-4 (20)
        ids = [item["id"] for item in body["data"]]
        assert ids[0] == "lead-3"
        assert ids[1] == "lead-1"
        assert ids[2] == "lead-2"
        assert ids[3] == "lead-4"
    finally:
        db.close()


def test_sales_view_order_by_priority_asc():
    """Test ordering by priority ascending with - prefix (lowest first)."""
    db = TestingSessionLocal()
    try:
        result = leads.sales_view(page=1, page_size=10, order_by="-priority", db=db)
        body = result.model_dump()
        
        # With - prefix, should reverse default order: lead-4 (20), lead-2 (50), lead-1 (80), lead-3 (90)
        # But current implementation treats "priority" as default desc, so "-priority" means asc
        # This results in: lead-4 (20), lead-2 (50), lead-1 (80), lead-3 (90)
        ids = [item["id"] for item in body["data"]]
        scores = [item["priority_score"] for item in body["data"]]
        # Verify ascending order
        for i in range(len(scores) - 1):
            assert scores[i] <= scores[i + 1], f"Scores should be in ascending order, got {scores}"
    finally:
        db.close()


def test_sales_view_order_by_last_interaction():
    """Test ordering by last_interaction (most recent first)."""
    db = TestingSessionLocal()
    try:
        result = leads.sales_view(page=1, page_size=10, order_by="last_interaction", db=db)
        body = result.model_dump()
        
        # Should be ordered by most recent: lead-3, lead-1, lead-2, lead-4
        ids = [item["id"] for item in body["data"]]
        assert ids[0] == "lead-3"
        assert ids[1] == "lead-1"
        assert ids[2] == "lead-2"
    finally:
        db.close()


def test_sales_view_pagination_first_page():
    """Test pagination - first page."""
    db = TestingSessionLocal()
    try:
        result = leads.sales_view(page=1, page_size=2, db=db)
        body = result.model_dump()
        
        assert len(body["data"]) == 2
        assert body["pagination"]["total"] == 4
        assert body["pagination"]["page"] == 1
        assert body["pagination"]["per_page"] == 2
    finally:
        db.close()


def test_sales_view_pagination_second_page():
    """Test pagination - second page."""
    db = TestingSessionLocal()
    try:
        result = leads.sales_view(page=2, page_size=2, db=db)
        body = result.model_dump()
        
        assert len(body["data"]) == 2
        assert body["pagination"]["total"] == 4
        assert body["pagination"]["page"] == 2
        assert body["pagination"]["per_page"] == 2
    finally:
        db.close()


def test_sales_view_pagination_out_of_range():
    """Test pagination - page out of range returns empty data with correct page number."""
    db = TestingSessionLocal()
    try:
        result = leads.sales_view(page=10, page_size=2, db=db)
        body = result.model_dump()
        
        # Should return empty data but pagination.page should be 10
        assert len(body["data"]) == 0
        assert body["pagination"]["total"] == 4
        assert body["pagination"]["page"] == 10
        assert body["pagination"]["per_page"] == 2
    finally:
        db.close()


def test_sales_view_combined_filters():
    """Test combining multiple filters."""
    db = TestingSessionLocal()
    try:
        result = leads.sales_view(
            page=1,
            page_size=10,
            owner="owner-1",
            status="new,contacted",
            db=db
        )
        body = result.model_dump()
        
        # Should return 2 leads (lead-1 and lead-2) owned by owner-1 with status new or contacted
        assert body["pagination"]["total"] == 2
        ids = [item["id"] for item in body["data"]]
        assert "lead-1" in ids
        assert "lead-2" in ids
    finally:
        db.close()
