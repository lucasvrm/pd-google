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
    contact = models.Contact(
        id="contact-1",
        name="Bob Buyer",
        email="bob@example.com",
        phone="555-0100",
    )
    vip_tag = models.Tag(name="VIP", color="#ff0000")
    cold_tag = models.Tag(name="Cold", color="#0000ff")

    lead_hot = models.Lead(
        id="lead-hot",
        title="Hot Lead",
        trade_name="Hot Trade",
        status="qualified",
        origin="inbound",
        owner_id=owner.id,
        primary_contact_id=contact.id,
        created_at=now - timedelta(days=3),
        updated_at=now - timedelta(days=1),
    )
    lead_cold = models.Lead(
        id="lead-cold",
        title="Cold Lead",
        trade_name="Cold Trade",
        status="lost",
        origin="outbound",
        owner_id=owner.id,
        created_at=now - timedelta(days=90),
        updated_at=now - timedelta(days=80),
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

    lead_hot.tags.append(vip_tag)
    lead_cold.tags.append(cold_tag)

    db.add_all(
        [owner, contact, vip_tag, cold_tag, lead_hot, lead_cold, stats_hot, stats_cold]
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

    assert body["total"] == 2
    assert body["page"] == 1
    assert body["page_size"] == 10
    assert len(body["items"]) == 2

    first, second = body["items"]

    assert first["priority_score"] >= second["priority_score"]
    assert first["id"] == "lead-hot"
    assert first["priority_bucket"] == "hot"
    assert "VIP" in first["tags"]
    assert body["items"][1]["priority_bucket"] == "cold"
    assert body["items"][1]["owner"]["name"] == "Alice Seller"

    assert any(
        route.path == "/api/leads/sales-view" and "GET" in route.methods
        for route in leads.router.routes
    )
