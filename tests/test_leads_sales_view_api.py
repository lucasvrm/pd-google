import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from datetime import datetime, timezone

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
    assert body == {
        "error": "Validation error",
        "code": "validation_error",
        "details": body["details"],
    }
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
        assert body["error"] in {"sales_view_error", "internal_server_error"}
        assert body["code"] == body["error"]
        assert "message" in body and isinstance(body["message"], str)
    finally:
        if original is not None:
            app.dependency_overrides[leads.get_db] = original
        else:
            del app.dependency_overrides[leads.get_db]
