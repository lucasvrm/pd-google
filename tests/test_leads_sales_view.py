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
        last_interaction_at=now - timedelta(days=70),
    )
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
        engagement_score=85,
        last_interaction_at=now - timedelta(hours=10),
    )
    stats_cold = models.LeadActivityStats(
        lead_id=lead_cold.id,
        engagement_score=10,
        last_interaction_at=now - timedelta(days=70),
    )
    stats_recent = models.LeadActivityStats(
        lead_id=lead_recent.id,
        engagement_score=30,
        last_interaction_at=now - timedelta(days=2),
    )
    stats_old = models.LeadActivityStats(
        lead_id=lead_old.id,
        engagement_score=3,
        last_interaction_at=now - timedelta(days=20),
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
    assert body["data"][1]["next_action"]["code"] == "send_follow_up"

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
    """Test ordering by next_action (urgency ranking)."""
    db = TestingSessionLocal()
    try:
        # Ascending order (most urgent first)
        result = leads.sales_view(page=1, page_size=10, order_by="next_action", db=db)
        body = result.model_dump()

        assert body["pagination"]["total"] == 4
        
        # Based on test data:
        # - lead-hot: high engagement (85) with no deal -> qualify_to_company (rank 3)
        # - lead-cold: stale interaction (70 days) -> send_follow_up (rank 4)
        # - lead-recent: stale interaction (2 days < 5) -> send_follow_up (rank 5)
        # - lead-old: stale interaction (20 days) -> send_follow_up (rank 4)
        
        next_actions = [item["next_action"]["code"] for item in body["data"]]
        
        # The order should group by action code priority
        # qualify_to_company leads should come first, then send_follow_up
        qualify_indices = [i for i, code in enumerate(next_actions) if code == "qualify_to_company"]
        follow_up_indices = [i for i, code in enumerate(next_actions) if code == "send_follow_up"]
        
        if qualify_indices and follow_up_indices:
            assert max(qualify_indices) < min(follow_up_indices)

        # Descending order (least urgent first)
        result_desc = leads.sales_view(page=1, page_size=10, order_by="-next_action", db=db)
        body_desc = result_desc.model_dump()
        
        next_actions_desc = [item["next_action"]["code"] for item in body_desc["data"]]
        
        # In descending order, send_follow_up should come before qualify_to_company
        qualify_indices_desc = [i for i, code in enumerate(next_actions_desc) if code == "qualify_to_company"]
        follow_up_indices_desc = [i for i, code in enumerate(next_actions_desc) if code == "send_follow_up"]
        
        if qualify_indices_desc and follow_up_indices_desc:
            assert max(follow_up_indices_desc) < min(qualify_indices_desc)

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
