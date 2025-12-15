import os
import sys
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import models
from database import Base
from routers import leads

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_leads_sales_view.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


def setup_module(module):
    if os.path.exists("./test_leads_sales_view.db"):
        os.remove("./test_leads_sales_view.db")

    Base.metadata.create_all(bind=engine)

    db = TestingSessionLocal()
    now = datetime.now(timezone.utc)

    owner = models.User(id="user-1", name="Alice Seller", email="alice@example.com")
    owner2 = models.User(id="user-2", name="Bob Manager", email="bob@example.com")
    vip_tag = models.Tag(id="tag-vip", name="VIP", color="#ff0000")
    cold_tag = models.Tag(id="tag-cold", name="Cold", color="#0000ff")

    # Create LeadStatus entries for ordering tests
    status_new = models.LeadStatus(id="new", code="new", label="Novo", sort_order=1)
    status_contacted = models.LeadStatus(id="contacted", code="contacted", label="Contatado", sort_order=2)
    status_qualified = models.LeadStatus(id="qualified", code="qualified", label="Qualificado", sort_order=3)
    status_lost = models.LeadStatus(id="lost", code="lost", label="Perdido", sort_order=4)

    # Lead 1: High engagement without company -> qualify_to_company (rank 5)
    # NOTE: last_interaction_at is set on both Lead and LeadActivityStats to test
    # the coalesce() fallback behavior in the query. Stats is the source of truth.
    lead_hot = models.Lead(
        id="lead-hot",
        title="Hot Lead",
        trade_name="Hot Trade",
        lead_status_id="qualified",
        lead_origin_id="inbound",
        owner_user_id=owner.id,
        priority_score=82,
        created_at=now - timedelta(days=3),
        updated_at=now - timedelta(days=1),
        last_interaction_at=now - timedelta(hours=10),
        address_city="Sao Paulo",
        address_state="SP",
    )
    # Lead 2: Very old interaction, low engagement -> reengage_cold_lead (rank 10)
    lead_cold = models.Lead(
        id="lead-cold",
        title="Cold Lead",
        trade_name="Cold Trade",
        lead_status_id="lost",
        lead_origin_id="outbound",
        owner_user_id=owner.id,
        priority_score=12,
        created_at=now - timedelta(days=90),
        updated_at=now - timedelta(days=80),
        last_interaction_at=now - timedelta(days=45),  # 45 days = cold but not disqualify
    )
    # Lead 3: Medium engagement, no upcoming meeting -> schedule_meeting (rank 6)
    lead_recent = models.Lead(
        id="lead-recent",
        title="Recent Lead",
        trade_name="Recent Trade",
        lead_status_id="contacted",
        lead_origin_id="partner",
        owner_user_id=owner.id,
        priority_score=50,
        created_at=now - timedelta(days=10),
        updated_at=now - timedelta(days=1),
        last_interaction_at=now - timedelta(days=2),
    )
    # Lead 4: Stale interaction (20 days) -> send_follow_up (rank 9)
    lead_old = models.Lead(
        id="lead-old",
        title="Old Lead",
        trade_name="Old Trade",
        lead_status_id="new",
        lead_origin_id="event",
        owner_user_id="user-2",
        priority_score=5,
        created_at=now - timedelta(days=40),
        updated_at=now - timedelta(days=30),
        last_interaction_at=now - timedelta(days=20),
    )

    stats_hot = models.LeadActivityStats(
        lead_id=lead_hot.id,
        engagement_score=85,  # High engagement -> qualify_to_company
        last_interaction_at=now - timedelta(hours=10),
    )
    stats_cold = models.LeadActivityStats(
        lead_id=lead_cold.id,
        engagement_score=10,  # Low engagement
        last_interaction_at=now - timedelta(days=45),  # Cold (>=30 days)
    )
    stats_recent = models.LeadActivityStats(
        lead_id=lead_recent.id,
        engagement_score=55,  # Medium engagement (>=50) -> schedule_meeting
        last_interaction_at=now - timedelta(days=2),
    )
    stats_old = models.LeadActivityStats(
        lead_id=lead_old.id,
        engagement_score=3,
        last_interaction_at=now - timedelta(days=20),  # Stale (>=5) -> send_follow_up
    )

    lead_hot.tags.append(vip_tag)
    lead_cold.tags.append(cold_tag)

    db.add_all(
        [
            owner,
            owner2,
            vip_tag,
            cold_tag,
            status_new,
            status_contacted,
            status_qualified,
            status_lost,
            lead_hot,
            lead_cold,
            lead_recent,
            lead_old,
            stats_hot,
            stats_cold,
            stats_recent,
            stats_old,
        ]
    )
    db.commit()
    db.close()


def teardown_module(module):
    if os.path.exists("./test_leads_sales_view.db"):
        os.remove("./test_leads_sales_view.db")


def test_sales_view_endpoint_returns_ordered_leads():
    db = TestingSessionLocal()
    try:
        result = leads.sales_view(page=1, page_size=10, db=db)
    finally:
        db.close()

    body = result.model_dump()

    # Updated assertions for new structure
    assert body["pagination"]["total"] == 4
    assert body["pagination"]["per_page"] == 10
    assert len(body["data"]) == 4

    first, second = body["data"][:2]

    assert first["priority_score"] >= second["priority_score"]
    assert first["id"] == "lead-hot"
    assert first["priority_bucket"] == "hot"
    assert any(tag["name"] == "VIP" for tag in first["tags"])
    assert first["owner_user_id"] == "user-1"
    assert first["owner"]["name"] == "Alice Seller"
    assert first["next_action"]["code"] == "qualify_to_company"
    assert "Engajamento alto" in first["next_action"]["reason"]
    assert body["data"][1]["priority_bucket"] in {"warm", "cold"}
    assert body["data"][1]["owner"]["name"] == "Alice Seller"
    # With updated test data, lead-recent has engagement 55 -> schedule_meeting
    assert body["data"][1]["next_action"]["code"] in ["schedule_meeting", "send_follow_up"]

    assert any(
        route.path == "/api/leads/sales-view" and "GET" in route.methods
        for route in leads.router.routes
    )


def test_sales_view_filters_recent_and_priority():
    db = TestingSessionLocal()
    try:
        result = leads.sales_view(
            page=1,
            page_size=10,
            has_recent_interaction=True,
            min_priority_score=40,
            db=db,
        )
    finally:
        db.close()

    body = result.model_dump()
    ids = [item["id"] for item in body["data"]]

    assert "lead-hot" in ids
    assert "lead-recent" in ids
    assert "lead-cold" not in ids
    assert all(item["priority_score"] >= 40 for item in body["data"])


def test_sales_view_filter_by_owner_and_ordering():
    db = TestingSessionLocal()
    try:
        result = leads.sales_view(
            page=1,
            page_size=10,
            owner="user-2",
            order_by="last_interaction",
            db=db,
        )
    finally:
        db.close()

    body = result.model_dump()
    assert body["pagination"]["total"] == 1
    assert body["data"][0]["id"] == "lead-old"


def test_sales_view_pagination_page_2():
    db = TestingSessionLocal()
    try:
        # We have 4 items. page_size=2.
        # Page 1 should have 2 items.
        # Page 2 should have 2 items.

        # Page 1
        result1 = leads.sales_view(page=1, page_size=2, db=db)
        body1 = result1.model_dump()
        assert len(body1["data"]) == 2
        assert body1["pagination"]["total"] == 4

        # Page 2
        result2 = leads.sales_view(page=2, page_size=2, db=db)
        body2 = result2.model_dump()
        assert len(body2["data"]) == 2
        assert body2["pagination"]["total"] == 4

        # Verify items are different
        ids1 = {item["id"] for item in body1["data"]}
        ids2 = {item["id"] for item in body2["data"]}
        assert ids1.isdisjoint(ids2)

    finally:
        db.close()


def test_sales_view_order_by_status():
    """Test ordering by status (LeadStatus.sort_order)."""
    db = TestingSessionLocal()
    try:
        # Ascending order (status sort_order: new=1, contacted=2, qualified=3, lost=4)
        result = leads.sales_view(page=1, page_size=10, order_by="status", db=db)
        body = result.model_dump()

        assert body["pagination"]["total"] == 4
        # First should be "new" (sort_order=1), last should be "lost" (sort_order=4)
        ids = [item["id"] for item in body["data"]]
        assert ids[0] == "lead-old"  # status=new (sort_order=1)
        assert ids[-1] == "lead-cold"  # status=lost (sort_order=4)

        # Descending order
        result_desc = leads.sales_view(page=1, page_size=10, order_by="-status", db=db)
        body_desc = result_desc.model_dump()
        ids_desc = [item["id"] for item in body_desc["data"]]
        assert ids_desc[0] == "lead-cold"  # status=lost (sort_order=4) first in desc
        assert ids_desc[-1] == "lead-old"  # status=new (sort_order=1) last in desc

    finally:
        db.close()


def test_sales_view_order_by_status_deterministic_tiebreaker():
    """Test that order_by=status uses created_at as a tie-breaker for deterministic ordering.
    
    When multiple leads share the same status, they should be ordered by created_at
    (newer leads first in ascending status order, older leads first in descending status order).
    """
    db = TestingSessionLocal()
    try:
        now = datetime.now(timezone.utc)
        
        # Create two leads with the SAME status but different created_at and priority_score
        # This tests that:
        # 1. Status sort_order is the PRIMARY sort criterion (not priority_score)
        # 2. created_at is used as a tie-breaker for deterministic ordering
        lead_same_status_older = models.Lead(
            id="lead-same-status-older",
            title="Same Status Older",
            lead_status_id="contacted",  # sort_order=2
            priority_score=90,  # Higher priority, but should be ordered by created_at, not priority
            created_at=now - timedelta(days=5),  # Older
        )
        lead_same_status_newer = models.Lead(
            id="lead-same-status-newer",
            title="Same Status Newer",
            lead_status_id="contacted",  # sort_order=2 (same status)
            priority_score=10,  # Lower priority, but should appear first due to newer created_at
            created_at=now - timedelta(days=1),  # Newer
        )
        
        db.add_all([lead_same_status_older, lead_same_status_newer])
        db.commit()
        
        # Ascending order by status: within same status, newer leads should come first (desc created_at)
        result = leads.sales_view(page=1, page_size=20, order_by="status", db=db)
        body = result.model_dump()
        
        # Filter to only the leads with "contacted" status
        contacted_leads = [item for item in body["data"] if item["lead_status_id"] == "contacted"]
        contacted_ids = [item["id"] for item in contacted_leads]
        
        # Within same status, newer (more recent created_at) should come first
        # lead-same-status-newer (created 1 day ago) should come before lead-same-status-older (created 5 days ago)
        assert "lead-same-status-newer" in contacted_ids
        assert "lead-same-status-older" in contacted_ids
        newer_idx = contacted_ids.index("lead-same-status-newer")
        older_idx = contacted_ids.index("lead-same-status-older")
        assert newer_idx < older_idx, (
            f"Newer lead should come before older lead within same status. "
            f"Got newer at {newer_idx}, older at {older_idx}"
        )
        
        # Descending order by status: within same status, older leads should come first (asc created_at)
        result_desc = leads.sales_view(page=1, page_size=20, order_by="-status", db=db)
        body_desc = result_desc.model_dump()
        
        contacted_leads_desc = [item for item in body_desc["data"] if item["lead_status_id"] == "contacted"]
        contacted_ids_desc = [item["id"] for item in contacted_leads_desc]
        
        # In descending status order, within same status, older (earlier created_at) should come first
        newer_idx_desc = contacted_ids_desc.index("lead-same-status-newer")
        older_idx_desc = contacted_ids_desc.index("lead-same-status-older")
        assert older_idx_desc < newer_idx_desc, (
            f"Older lead should come before newer lead in descending order. "
            f"Got older at {older_idx_desc}, newer at {newer_idx_desc}"
        )
        
        # Clean up
        db.query(models.Lead).filter(models.Lead.id.in_(["lead-same-status-older", "lead-same-status-newer"])).delete(synchronize_session=False)
        db.commit()
        
    finally:
        db.close()


def test_sales_view_order_by_status_replaces_priority():
    """Test that order_by=status replaces priority_score as the primary sorting criterion.
    
    This test verifies that when order_by=status is specified, leads are sorted by
    LeadStatus.sort_order, NOT by priority_score. A lead with higher priority but
    lower-urgency status should come AFTER a lead with lower priority but higher-urgency status.
    """
    db = TestingSessionLocal()
    try:
        now = datetime.now(timezone.utc)
        
        # Create leads with:
        # - lead-high-priority-low-urgency: priority_score=95, status=lost (sort_order=4, low urgency)
        # - lead-low-priority-high-urgency: priority_score=5, status=new (sort_order=1, high urgency)
        lead_high_priority = models.Lead(
            id="lead-high-priority-low-urgency",
            title="High Priority Low Urgency",
            lead_status_id="lost",  # sort_order=4 (low urgency)
            priority_score=95,  # High priority
            created_at=now - timedelta(days=2),
        )
        lead_low_priority = models.Lead(
            id="lead-low-priority-high-urgency",
            title="Low Priority High Urgency",
            lead_status_id="new",  # sort_order=1 (high urgency)
            priority_score=5,  # Low priority
            created_at=now - timedelta(days=1),
        )
        
        db.add_all([lead_high_priority, lead_low_priority])
        db.commit()
        
        # When ordering by status (ascending), the low-priority lead with high-urgency status
        # should come BEFORE the high-priority lead with low-urgency status
        result = leads.sales_view(page=1, page_size=20, order_by="status", db=db)
        body = result.model_dump()
        
        ids = [item["id"] for item in body["data"]]
        
        # Find indices
        high_priority_idx = ids.index("lead-high-priority-low-urgency")
        low_priority_idx = ids.index("lead-low-priority-high-urgency")
        
        # Low-priority lead (with high-urgency status) should come before high-priority lead
        assert low_priority_idx < high_priority_idx, (
            f"Status ordering should override priority. Expected low-priority-high-urgency lead "
            f"before high-priority-low-urgency lead. Got indices: low={low_priority_idx}, high={high_priority_idx}"
        )
        
        # Clean up
        db.query(models.Lead).filter(models.Lead.id.in_(["lead-high-priority-low-urgency", "lead-low-priority-high-urgency"])).delete(synchronize_session=False)
        db.commit()
        
    finally:
        db.close()


def test_sales_view_order_by_owner():
    """Test ordering by owner name (User.name)."""
    db = TestingSessionLocal()
    try:
        # Ascending order: Alice Seller comes before Bob Manager alphabetically (A < B)
        result = leads.sales_view(page=1, page_size=10, order_by="owner", db=db)
        body = result.model_dump()

        assert body["pagination"]["total"] == 4
        # Alice's leads should come before Bob's leads
        owner_names = [item["owner"]["name"] if item["owner"] else None for item in body["data"]]
        
        # Find index where owner changes from Alice to Bob
        alice_leads = [i for i, name in enumerate(owner_names) if name == "Alice Seller"]
        bob_leads = [i for i, name in enumerate(owner_names) if name == "Bob Manager"]
        
        # All Alice's leads should come before Bob's in ascending order
        if alice_leads and bob_leads:
            assert max(alice_leads) < min(bob_leads)

        # Descending order
        result_desc = leads.sales_view(page=1, page_size=10, order_by="-owner", db=db)
        body_desc = result_desc.model_dump()
        owner_names_desc = [item["owner"]["name"] if item["owner"] else None for item in body_desc["data"]]
        
        # Bob's leads should come before Alice's in descending order
        alice_leads_desc = [i for i, name in enumerate(owner_names_desc) if name == "Alice Seller"]
        bob_leads_desc = [i for i, name in enumerate(owner_names_desc) if name == "Bob Manager"]
        
        if alice_leads_desc and bob_leads_desc:
            assert max(bob_leads_desc) < min(alice_leads_desc)

    finally:
        db.close()


def test_sales_view_order_by_next_action():
    """Test ordering by next_action (urgency ranking).
    
    Test data ranking based on Sprint 2/3 precedence:
    - lead-hot: engagement 85 (high), no company -> qualify_to_company (rank 5)
    - lead-recent: engagement 55 (medium+), no meeting -> schedule_meeting (rank 6)
    - lead-old: stale 20 days (5 <= x < 30) -> send_follow_up (rank 9)
    - lead-cold: cold 45 days (30 <= x < 60) -> reengage_cold_lead (rank 10)
    
    Expected ascending order: lead-hot, lead-recent, lead-old, lead-cold
    """
    db = TestingSessionLocal()
    try:
        # Ascending order (most urgent first)
        result = leads.sales_view(page=1, page_size=10, order_by="next_action", db=db)
        body = result.model_dump()

        assert body["pagination"]["total"] == 4
        
        # Get IDs in order
        ids = [item["id"] for item in body["data"]]
        next_actions = [item["next_action"]["code"] for item in body["data"]]
        
        # Verify that the leads are grouped correctly by action priority
        # qualify_to_company (rank 5) should come before schedule_meeting (rank 6)
        qualify_indices = [i for i, code in enumerate(next_actions) if code == "qualify_to_company"]
        schedule_indices = [i for i, code in enumerate(next_actions) if code == "schedule_meeting"]
        follow_up_indices = [i for i, code in enumerate(next_actions) if code == "send_follow_up"]
        reengage_indices = [i for i, code in enumerate(next_actions) if code == "reengage_cold_lead"]
        
        # qualify_to_company leads should come first
        if qualify_indices and schedule_indices:
            assert max(qualify_indices) < min(schedule_indices), (
                f"qualify_to_company should come before schedule_meeting: {next_actions}"
            )
        
        # schedule_meeting should come before send_follow_up
        if schedule_indices and follow_up_indices:
            assert max(schedule_indices) < min(follow_up_indices), (
                f"schedule_meeting should come before send_follow_up: {next_actions}"
            )
        
        # send_follow_up should come before reengage_cold_lead
        if follow_up_indices and reengage_indices:
            assert max(follow_up_indices) < min(reengage_indices), (
                f"send_follow_up should come before reengage_cold_lead: {next_actions}"
            )

        # Descending order (least urgent first)
        result_desc = leads.sales_view(page=1, page_size=10, order_by="-next_action", db=db)
        body_desc = result_desc.model_dump()
        
        next_actions_desc = [item["next_action"]["code"] for item in body_desc["data"]]
        
        # In descending order, reengage_cold_lead should come before send_follow_up
        reengage_indices_desc = [i for i, code in enumerate(next_actions_desc) if code == "reengage_cold_lead"]
        follow_up_indices_desc = [i for i, code in enumerate(next_actions_desc) if code == "send_follow_up"]
        
        if reengage_indices_desc and follow_up_indices_desc:
            assert max(reengage_indices_desc) < min(follow_up_indices_desc), (
                f"In desc order, reengage_cold_lead should come before send_follow_up: {next_actions_desc}"
            )

    finally:
        db.close()


def test_sales_view_order_by_invalid_falls_back_to_priority():
    """Test that invalid order_by falls back to priority."""
    db = TestingSessionLocal()
    try:
        result = leads.sales_view(page=1, page_size=10, order_by="invalid_field", db=db)
        body = result.model_dump()

        assert body["pagination"]["total"] == 4
        # Should fall back to priority ordering (highest priority_score first)
        first, second = body["data"][:2]
        assert first["priority_score"] >= second["priority_score"]

    finally:
        db.close()


def test_sales_view_order_by_next_action_with_call_again():
    """Test that rank 7 (call_again) is applied in SQL ordering when last_call_at is set.
    
    This test creates a lead with last_call_at within the CALL_AGAIN_WINDOW_DAYS (7 days)
    to verify that the SQL CASE ranks it correctly.
    """
    db = TestingSessionLocal()
    try:
        now = datetime.now(timezone.utc)
        
        # Create a lead with recent call (should get rank 7: call_again)
        lead_call = models.Lead(
            id="lead-call-again",
            title="Call Again Lead",
            trade_name="Call Trade",
            lead_status_id="contacted",
            owner_user_id="user-1",
            priority_score=35,
            created_at=now - timedelta(days=5),
            updated_at=now - timedelta(days=1),
            last_interaction_at=now - timedelta(days=3),
        )
        stats_call = models.LeadActivityStats(
            lead_id="lead-call-again",
            engagement_score=30,  # Below schedule_meeting threshold (50)
            last_interaction_at=now - timedelta(days=3),
            last_call_at=now - timedelta(days=3),  # Within 7-day call window -> rank 7
        )
        
        db.add_all([lead_call, stats_call])
        db.commit()
        
        # Query with order_by=next_action
        result = leads.sales_view(page=1, page_size=20, order_by="next_action", db=db)
        body = result.model_dump()
        
        # Find the lead and verify it has call_again action
        lead_data = next((item for item in body["data"] if item["id"] == "lead-call-again"), None)
        assert lead_data is not None, "lead-call-again should be in results"
        assert lead_data["next_action"]["code"] == "call_again", (
            f"Expected call_again but got {lead_data['next_action']['code']}"
        )
        
        # Clean up
        db.query(models.LeadActivityStats).filter(
            models.LeadActivityStats.lead_id == "lead-call-again"
        ).delete()
        db.query(models.Lead).filter(models.Lead.id == "lead-call-again").delete()
        db.commit()
        
    finally:
        db.close()


def test_sales_view_order_by_next_action_with_send_value_asset():
    """Test that rank 8 (send_value_asset) is applied in SQL ordering.
    
    This test creates a lead with engagement >= MEDIUM_ENGAGEMENT_SCORE (40)
    and no last_value_asset_at, which should trigger send_value_asset (rank 8).
    """
    db = TestingSessionLocal()
    try:
        now = datetime.now(timezone.utc)
        
        # Create a lead that should get rank 8: send_value_asset
        # Conditions: engagement >= 40, no last_value_asset_at, no recent call
        lead_value = models.Lead(
            id="lead-value-asset",
            title="Value Asset Lead",
            trade_name="Value Trade",
            lead_status_id="contacted",
            owner_user_id="user-2",
            priority_score=45,
            created_at=now - timedelta(days=10),
            updated_at=now - timedelta(days=1),
            last_interaction_at=now - timedelta(days=2),
        )
        stats_value = models.LeadActivityStats(
            lead_id="lead-value-asset",
            engagement_score=42,  # Below schedule_meeting (50) but >= medium (40)
            last_interaction_at=now - timedelta(days=2),
            last_call_at=None,  # No recent call
            last_value_asset_at=None,  # Never sent -> rank 8
        )
        
        db.add_all([lead_value, stats_value])
        db.commit()
        
        # Query with order_by=next_action
        result = leads.sales_view(page=1, page_size=20, order_by="next_action", db=db)
        body = result.model_dump()
        
        # Find the lead and verify it has send_value_asset action
        lead_data = next((item for item in body["data"] if item["id"] == "lead-value-asset"), None)
        assert lead_data is not None, "lead-value-asset should be in results"
        assert lead_data["next_action"]["code"] == "send_value_asset", (
            f"Expected send_value_asset but got {lead_data['next_action']['code']}"
        )
        
        # Clean up
        db.query(models.LeadActivityStats).filter(
            models.LeadActivityStats.lead_id == "lead-value-asset"
        ).delete()
        db.query(models.Lead).filter(models.Lead.id == "lead-value-asset").delete()
        db.commit()
        
    finally:
        db.close()
