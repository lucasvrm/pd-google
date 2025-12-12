import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from datetime import datetime, timedelta, timezone

# Import the application components
from main import app
from database import Base
from models import Lead, LeadActivityStats, Company, User, Tag, LeadTag
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
