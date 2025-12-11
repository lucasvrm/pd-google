import os
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
    vip_tag = models.Tag(name="VIP", color="#ff0000")
    cold_tag = models.Tag(name="Cold", color="#0000ff")

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
            vip_tag,
            cold_tag,
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
    assert "VIP" in first["tags"]
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
