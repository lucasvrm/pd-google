import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from datetime import datetime, timedelta, timezone

# Import the application components
from main import app
from database import Base
from models import Lead, LeadActivityStats, Company, User, Tag, LeadTag, EntityTag
from routers import leads

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

def test_sales_view_success(client):
    """Test that the endpoint returns 200 OK with valid data."""
    db = TestingSessionLocal()

    # create dependencies
    user = User(id="user1", name="Test User", email="test@example.com")
    company = Company(id="comp1", name="Test Corp")
    tag = Tag(id="tag1", name="Urgente", color="#ff0000")
    lead = Lead(
        id="lead1",
        title="Big Deal", # maps to legal_name
        trade_name="Big Deal Trade",
        lead_status_id="new",
        lead_origin_id="inbound",
        owner_user_id="user1",
        qualified_company_id="comp1",
        priority_score=50,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )

    db.add(tag)
    db.add(user)
    db.add(company)
    db.add(lead)
    db.commit()

    lead_tag = LeadTag(lead_id=lead.id, tag_id=tag.id)
    db.add(lead_tag)
    db.commit()
    db.close()

    response = client.get("/api/leads/sales-view?page=1&pageSize=10&order_by=priority")
    assert response.status_code == 200, f"Response text: {response.text}"
    assert response.headers["content-type"].startswith("application/json")
    data = response.json()
    assert "data" in data
    assert "pagination" in data
    assert len(data["data"]) == 1
    assert data["data"][0]["id"] == "lead1"
    assert data["data"][0]["owner_user_id"] == "user1"
    assert data["data"][0]["owner"]["name"] == "Test User"
    assert data["data"][0]["primary_contact"] is None
    assert data["data"][0]["priority_description"] == "Prioridade média"

    tags = data["data"][0]["tags"]
    assert tags == [{"id": "tag1", "name": "Urgente", "color": "#ff0000"}]

    next_action = data["data"][0]["next_action"]
    assert set(next_action.keys()) == {"code", "label", "reason"}
    assert isinstance(next_action["label"], str)

def test_sales_view_owner_me_uses_authenticated_user(client):
    """owner=me should resolve to the authenticated user id."""
    db = TestingSessionLocal()

    user1_id = "user1"
    user2_id = "user2"
    lead1_id = "lead1"
    lead2_id = "lead2"
    user1 = User(id=user1_id, name="User One", email="one@example.com")
    user2 = User(id=user2_id, name="User Two", email="two@example.com")
    lead1 = Lead(id=lead1_id, title="Lead One", owner_user_id=user1_id)
    lead2 = Lead(id=lead2_id, title="Lead Two", owner_user_id=user2_id)

    db.add_all([user1, user2, lead1, lead2])
    db.commit()
    db.close()

    response = client.get(
        "/api/leads/sales-view?page=1&pageSize=10&owner=me",
        headers={"x-user-id": user1_id},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["data"]) == 1
    assert body["data"][0]["owner_user_id"] == user1_id
    assert body["data"][0]["id"] == lead1_id

def test_sales_view_owner_me_requires_authentication(client):
    """owner=me without credentials should not raise 500 and should return 401 JSON error."""
    response = client.get("/api/leads/sales-view?page=1&pageSize=10&owner=me")
    assert response.status_code == 401
    body = response.json()
    assert body["code"] == "unauthorized"
    assert body["error"] == "Authentication required for owner=me filter"
    assert body["message"] == "Authentication required for owner=me filter"

def test_sales_view_owner_ids_filter(client):
    """ownerIds filter should be applied without errors."""
    db = TestingSessionLocal()

    user1_id = "user1"
    user2_id = "user2"
    user1 = User(id=user1_id, name="User One", email="one@example.com")
    user2 = User(id=user2_id, name="User Two", email="two@example.com")
    lead1 = Lead(id="lead1", title="Lead One", owner_user_id=user1_id)
    lead2 = Lead(id="lead2", title="Lead Two", owner_user_id=user2_id)

    db.add_all([user1, user2, lead1, lead2])
    db.commit()
    db.close()

    response = client.get(
        "/api/leads/sales-view?page=1&pageSize=10&ownerIds=user2"
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["data"]) == 1
    assert body["data"][0]["owner_user_id"] == user2_id

def test_sales_view_null_values(client):
    """Test resilience against NULL values in DB."""
    db = TestingSessionLocal()

    # Lead with minimal fields (many nulls)
    lead = Lead(
        id="lead_nulls",
        title="Null Lead",
        # status None
        # origin None
        # owner_user_id None
        # priority_score Default 0
    )
    db.add(lead)
    db.commit()
    db.close()

    response = client.get("/api/leads/sales-view?page=1&pageSize=10")
    assert response.status_code == 200, f"Should handle nulls gracefully. Error: {response.text}"
    data = response.json()
    item = data["data"][0]
    assert item["legal_name"] == "Null Lead"
    assert item["lead_status_id"] is None
    assert item["owner"] is None
    assert item["tags"] == []
    assert item["primary_contact"] is None
    assert item["priority_description"] == "Baixa prioridade"

def test_sales_view_invalid_params(client):
    """Test 422 response for invalid parameters with normalized error shape."""
    response = client.get("/api/leads/sales-view?page=-1")
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/json")
    body = response.json()
    assert body["error"] == "Validation error"
    assert body["code"] == "validation_error"
    assert body["message"] == "Validation error"
    assert "details" in body
    assert isinstance(body["details"], list) and len(body["details"]) > 0

    # Test invalid order_by - should fallback to default ordering without error
    response = client.get("/api/leads/sales-view?order_by=invalid_field")
    assert response.status_code == 200
    body = response.json()
    assert "data" in body

def test_chaos_scenario_missing_stats(client):
    """Simulate a scenario where stats might be joined but missing."""
    db = TestingSessionLocal()

    lead = Lead(
        id="chaos_lead",
        title="Chaos Lead",
        priority_score=None
    )
    db.add(lead)
    db.commit()

    # We do NOT add stats. The outerjoin should handle it.

    response = client.get("/api/leads/sales-view")
    assert response.status_code == 200, f"Chaos failed: {response.text}"


def test_sales_view_internal_error_is_json(client):
    """Simulate an internal error and ensure JSON error contract is returned."""

    def faulty_db():
        class FaultySession:
            def query(self, *_, **__):
                raise Exception("boom")

            def close(self):
                pass

        yield FaultySession()

    original = app.dependency_overrides.get(leads.get_db)
    app.dependency_overrides[leads.get_db] = faulty_db
    try:
        response = client.get("/api/leads/sales-view")
        assert response.status_code == 500
        assert response.headers["content-type"].startswith("application/json")
        body = response.json()
        assert body["error"] == "sales_view_error"
        assert body["code"] == "sales_view_error"
        assert "message" in body and isinstance(body["message"], str)
    finally:
        if original is not None:
            app.dependency_overrides[leads.get_db] = original
        else:
            del app.dependency_overrides[leads.get_db]


def test_sales_view_priority_filter(client):
    """priority filter should honor hot/warm/cold buckets."""
    db = TestingSessionLocal()

    hot_lead = Lead(
        id="lead_hot",
        title="Hot Lead",
        priority_score=85,
    )
    warm_lead = Lead(
        id="lead_warm",
        title="Warm Lead",
        priority_score=55,
    )
    cold_lead = Lead(
        id="lead_cold",
        title="Cold Lead",
        priority_score=10,
    )

    db.add_all([hot_lead, warm_lead, cold_lead])
    db.commit()
    db.close()

    response = client.get("/api/leads/sales-view?priority=hot")
    assert response.status_code == 200
    body = response.json()
    ids = [item["id"] for item in body["data"]]
    assert ids == ["lead_hot"]

    response = client.get("/api/leads/sales-view?priority=warm")
    assert response.status_code == 200
    body = response.json()
    ids = [item["id"] for item in body["data"]]
    assert ids == ["lead_warm"]

    response = client.get("/api/leads/sales-view?priority=cold")
    assert response.status_code == 200
    body = response.json()
    ids = [item["id"] for item in body["data"]]
    assert set(ids) == {"lead_cold"}


def test_sales_view_days_without_interaction_filter(client):
    """days_without_interaction should return leads without interaction for at least N days."""
    db = TestingSessionLocal()
    now = datetime.now(timezone.utc)

    stale_lead = Lead(
        id="stale_lead",
        title="Stale Lead",
        last_interaction_at=now - timedelta(days=10),
    )
    fresh_lead = Lead(
        id="fresh_lead",
        title="Fresh Lead",
        last_interaction_at=now - timedelta(days=2),
    )

    db.add_all([stale_lead, fresh_lead])
    db.commit()
    db.close()

    response = client.get("/api/leads/sales-view?days_without_interaction=7")
    assert response.status_code == 200
    body = response.json()
    ids = [item["id"] for item in body["data"]]
    assert ids == ["stale_lead"]


def test_sales_view_updates_last_interaction_on_lead_change(client):
    """Any meaningful lead update should refresh last_interaction_at for Sales View ordering."""
    db = TestingSessionLocal()
    now = datetime.now(timezone.utc)
    older = now - timedelta(days=5)

    try:
        user = User(id="owner-change", name="Owner Change")
        stale_lead = Lead(
            id="stale_interaction",
            title="Stale Lead",
            last_interaction_at=older,
            updated_at=older,
        )
        recent_lead = Lead(
            id="recent_interaction",
            title="Recent Lead",
            last_interaction_at=now - timedelta(days=1),
        )

        db.add_all([user, stale_lead, recent_lead])
        db.commit()

        # Changing the owner should count as an interaction and refresh timestamps
        update_started = datetime.now(timezone.utc)
        stale_lead.owner_user_id = user.id
        db.commit()
    finally:
        db.close()

    response = client.get("/api/leads/sales-view?order_by=last_interaction")
    assert response.status_code == 200
    body = response.json()
    assert body["data"][0]["id"] == "stale_interaction"

    last_interaction = datetime.fromisoformat(
        body["data"][0]["last_interaction_at"].replace("Z", "+00:00")
    )
    assert last_interaction >= update_started
    assert last_interaction <= datetime.now(timezone.utc) + timedelta(minutes=5)


def test_sales_view_owner_me_priority_and_days_filter(client):
    """Combined filters should work together (owner=me + priority + days_without_interaction)."""
    db = TestingSessionLocal()
    now = datetime.now(timezone.utc)
    try:
        owner = User(id="owner-me", name="Owner Me")
        other = User(id="owner-other", name="Owner Other")

        hot_stale = Lead(
            id="lead_hot_stale",
            title="Hot Stale",
            owner_user_id=owner.id,
            priority_score=90,
            last_interaction_at=now - timedelta(days=10),
        )
        warm_stale = Lead(
            id="lead_warm_stale",
            title="Warm Stale",
            owner_user_id=owner.id,
            priority_score=50,
            last_interaction_at=now - timedelta(days=10),
        )
        hot_other = Lead(
            id="lead_hot_other",
            title="Hot Other",
            owner_user_id=other.id,
            priority_score=95,
            last_interaction_at=now - timedelta(days=10),
        )

        db.add_all([owner, other, hot_stale, warm_stale, hot_other])
        db.commit()
    finally:
        db.close()

    response = client.get(
        "/api/leads/sales-view?owner=me&priority=hot&days_without_interaction=7",
        headers={"x-user-id": "owner-me"},
    )
    assert response.status_code == 200
    body = response.json()
    ids = [item["id"] for item in body["data"]]
    assert ids == ["lead_hot_stale"]


def test_sales_view_search_filter(client):
    """Test text search filters leads by legal_name or trade_name."""
    db = TestingSessionLocal()
    try:
        lead1 = Lead(
            id="lead_search_1",
            title="ABC Consulting Ltd",  # maps to legal_name
            trade_name="ABC",
            priority_score=50,
        )
        lead2 = Lead(
            id="lead_search_2",
            title="XYZ Solutions",
            trade_name="Best XYZ Corp",
            priority_score=60,
        )
        lead3 = Lead(
            id="lead_search_3",
            title="Omega Industries",
            trade_name="Omega",
            priority_score=70,
        )

        db.add_all([lead1, lead2, lead3])
        db.commit()
    finally:
        db.close()

    # Test search by legal_name (partial match, case-insensitive)
    response = client.get("/api/leads/sales-view?search=abc")
    assert response.status_code == 200
    body = response.json()
    ids = [item["id"] for item in body["data"]]
    assert "lead_search_1" in ids
    assert "lead_search_2" not in ids
    assert "lead_search_3" not in ids

    # Test search by trade_name (partial match)
    response = client.get("/api/leads/sales-view?search=xyz")
    assert response.status_code == 200
    body = response.json()
    ids = [item["id"] for item in body["data"]]
    assert "lead_search_2" in ids

    # Test with q parameter (legacy alias)
    response = client.get("/api/leads/sales-view?q=omega")
    assert response.status_code == 200
    body = response.json()
    ids = [item["id"] for item in body["data"]]
    assert "lead_search_3" in ids


def test_sales_view_tags_filter_via_entity_tags(client):
    """Test filtering leads by tags using entity_tags table."""
    db = TestingSessionLocal()
    try:
        tag1 = Tag(id="tag-urgent", name="Urgent", color="#ff0000")
        tag2 = Tag(id="tag-vip", name="VIP", color="#00ff00")
        tag3 = Tag(id="tag-cold", name="Cold", color="#0000ff")

        lead1 = Lead(id="lead_tag_1", title="Lead With Urgent Tag")
        lead2 = Lead(id="lead_tag_2", title="Lead With VIP Tag")
        lead3 = Lead(id="lead_tag_3", title="Lead Without Tags")

        db.add_all([tag1, tag2, tag3, lead1, lead2, lead3])
        db.commit()

        # Create entity_tags associations
        entity_tag1 = EntityTag(entity_type="lead", entity_id="lead_tag_1", tag_id="tag-urgent")
        entity_tag2 = EntityTag(entity_type="lead", entity_id="lead_tag_2", tag_id="tag-vip")
        entity_tag3 = EntityTag(entity_type="lead", entity_id="lead_tag_1", tag_id="tag-cold")

        db.add_all([entity_tag1, entity_tag2, entity_tag3])
        db.commit()
    finally:
        db.close()

    # Test filtering by a single tag
    response = client.get("/api/leads/sales-view?tags=tag-urgent")
    assert response.status_code == 200
    body = response.json()
    ids = [item["id"] for item in body["data"]]
    assert "lead_tag_1" in ids
    assert "lead_tag_2" not in ids
    assert "lead_tag_3" not in ids

    # Test filtering by multiple tags (CSV)
    response = client.get("/api/leads/sales-view?tags=tag-urgent,tag-vip")
    assert response.status_code == 200
    body = response.json()
    ids = [item["id"] for item in body["data"]]
    assert "lead_tag_1" in ids
    assert "lead_tag_2" in ids
    assert "lead_tag_3" not in ids


def test_sales_view_tags_returned_from_entity_tags(client):
    """Test that tags in response come from entity_tags (source of truth)."""
    db = TestingSessionLocal()
    try:
        tag_entity = Tag(id="tag-from-entity", name="EntityTag", color="#ff00ff")

        lead = Lead(id="lead_entity_tag", title="Lead With Entity Tags")

        db.add_all([tag_entity, lead])
        db.commit()

        # Add tag via entity_tags (source of truth)
        entity_tag = EntityTag(entity_type="lead", entity_id="lead_entity_tag", tag_id="tag-from-entity")
        db.add(entity_tag)
        db.commit()
    finally:
        db.close()

    response = client.get("/api/leads/sales-view")
    assert response.status_code == 200
    body = response.json()
    lead_data = next((item for item in body["data"] if item["id"] == "lead_entity_tag"), None)
    assert lead_data is not None
    assert len(lead_data["tags"]) == 1
    assert lead_data["tags"][0]["id"] == "tag-from-entity"
    assert lead_data["tags"][0]["name"] == "EntityTag"


def test_sales_view_search_and_tags_combined(client):
    """Test combining search and tags filters."""
    db = TestingSessionLocal()
    try:
        tag = Tag(id="tag-premium", name="Premium", color="#gold")
        lead1 = Lead(id="lead_combo_1", title="Premium Client ABC")
        lead2 = Lead(id="lead_combo_2", title="Premium Client XYZ")
        lead3 = Lead(id="lead_combo_3", title="Regular Client ABC")

        db.add_all([tag, lead1, lead2, lead3])
        db.commit()

        # Only lead1 has the premium tag
        entity_tag = EntityTag(entity_type="lead", entity_id="lead_combo_1", tag_id="tag-premium")
        db.add(entity_tag)
        db.commit()
    finally:
        db.close()

    # Search for "ABC" with Premium tag - should only return lead_combo_1
    response = client.get("/api/leads/sales-view?search=ABC&tags=tag-premium")
    assert response.status_code == 200
    body = response.json()
    ids = [item["id"] for item in body["data"]]
    assert ids == ["lead_combo_1"]
