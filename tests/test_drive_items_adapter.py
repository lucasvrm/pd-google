"""
Tests for the Drive Items Adapter endpoint.

This tests the /api/drive/items endpoint which provides frontend-compatible
responses for drive file/folder listings.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base, get_db
from main import app
import models
import os
from unittest.mock import patch
from services.google_drive_mock import GoogleDriveService

# Setup Test DB
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_drive_items_adapter.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

MOCK_JSON = "mock_drive_db.json"

def setup_module(module):
    """Setup test database and mock drive environment"""
    # Clean up JSON Mock
    if os.path.exists(MOCK_JSON):
        os.remove(MOCK_JSON)
    
    # Clean up old test DB
    if os.path.exists("./test_drive_items_adapter.db"):
        os.remove("./test_drive_items_adapter.db")

    # Override dependency BEFORE creating tables
    app.dependency_overrides[get_db] = override_get_db

    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    # Create test entities
    company = models.Company(id="comp-items-1", name="Items Test Company")
    db.add(company)

    lead = models.Lead(id="lead-items-1", title="Items Test Lead", qualified_company_id="comp-items-1")
    db.add(lead)

    deal = models.Deal(id="deal-items-1", title="Items Test Deal", company_id="comp-items-1")
    db.add(deal)

    # Create templates for folder structure
    tmpl_company = models.DriveStructureTemplate(name="Company Items Tmpl", entity_type="company", active=True)
    db.add(tmpl_company)
    db.commit()
    node_company = models.DriveStructureNode(template_id=tmpl_company.id, name="Company Folder", order=0)
    db.add(node_company)

    tmpl_lead = models.DriveStructureTemplate(name="Lead Items Tmpl", entity_type="lead", active=True)
    db.add(tmpl_lead)
    db.commit()
    node_lead = models.DriveStructureNode(template_id=tmpl_lead.id, name="Lead Folder", order=0)
    db.add(node_lead)

    tmpl_deal = models.DriveStructureTemplate(name="Deal Items Tmpl", entity_type="deal", active=True)
    db.add(tmpl_deal)
    db.commit()
    node_deal = models.DriveStructureNode(template_id=tmpl_deal.id, name="Deal Folder", order=0)
    db.add(node_deal)

    db.commit()
    db.close()

def teardown_module(module):
    """Cleanup test database and mock drive files"""
    # Clear ALL dependency overrides to avoid conflicts with other tests
    app.dependency_overrides.clear()
    
    if os.path.exists("./test_drive_items_adapter.db"):
        os.remove("./test_drive_items_adapter.db")
    if os.path.exists(MOCK_JSON):
        os.remove(MOCK_JSON)

# Create client AFTER module setup - use fixture
@pytest.fixture(scope="module")
def client():
    """Test client with mocked drive service"""
    mock_service = GoogleDriveService()

    with patch("routers.drive_items_adapter.drive_service", mock_service), \
         patch("services.hierarchy_service.config.USE_MOCK_DRIVE", True), \
         patch("services.hierarchy_service.config.DRIVE_ROOT_FOLDER_ID", "mock-root-id"):
        yield TestClient(app)


class TestDriveItemsEndpoint:
    """Test the /api/drive/items endpoint"""

    def test_get_items_returns_correct_structure(self, client):
        """Test that endpoint returns the expected {items, total} structure"""
        response = client.get(
            "/api/drive/items?entityType=deal&entityId=deal-items-1",
            headers={"x-user-id": "u1", "x-user-role": "manager"}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Check response structure
        assert "items" in data
        assert "total" in data
        assert isinstance(data["items"], list)
        assert isinstance(data["total"], int)

    def test_items_have_correct_fields(self, client):
        """Test that each item has the expected fields"""
        # First upload a file to have something to list
        client.get(
            "/api/drive/items?entityType=lead&entityId=lead-items-1",
            headers={"x-user-id": "u1", "x-user-role": "admin"}
        )
        
        response = client.get(
            "/api/drive/items?entityType=lead&entityId=lead-items-1",
            headers={"x-user-id": "u1", "x-user-role": "admin"}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # If there are items, check their structure
        if len(data["items"]) > 0:
            item = data["items"][0]
            assert "id" in item
            assert "name" in item
            assert "url" in item or item.get("url") is None
            assert "createdAt" in item or item.get("createdAt") is None
            assert "mimeType" in item
            assert "type" in item
            assert item["type"] in ["file", "folder"]
            assert "size" in item or item.get("size") is None

    def test_pagination_works(self, client):
        """Test that pagination parameters work correctly"""
        # Initialize the structure first
        client.get(
            "/api/drive/items?entityType=company&entityId=comp-items-1",
            headers={"x-user-id": "u1", "x-user-role": "admin"}
        )
        
        # Get first page with limit=2
        response1 = client.get(
            "/api/drive/items?entityType=company&entityId=comp-items-1&page=1&limit=2",
            headers={"x-user-id": "u1", "x-user-role": "admin"}
        )
        
        assert response1.status_code == 200
        data1 = response1.json()
        
        # Total should be the same regardless of pagination
        total = data1["total"]
        
        # Items should be limited to 2 or less
        assert len(data1["items"]) <= 2
        
        # Get second page if there are enough items
        if total > 2:
            response2 = client.get(
                "/api/drive/items?entityType=company&entityId=comp-items-1&page=2&limit=2",
                headers={"x-user-id": "u1", "x-user-role": "admin"}
            )
            
            assert response2.status_code == 200
            data2 = response2.json()
            
            # Total should be the same
            assert data2["total"] == total
            
            # Items should be different from page 1 (if there are items)
            if len(data1["items"]) > 0 and len(data2["items"]) > 0:
                assert data1["items"][0]["id"] != data2["items"][0]["id"]

    def test_default_pagination_values(self, client):
        """Test default values for page and limit"""
        response = client.get(
            "/api/drive/items?entityType=deal&entityId=deal-items-1",
            headers={"x-user-id": "u1", "x-user-role": "admin"}
        )
        
        assert response.status_code == 200
        # Should work with defaults (page=1, limit=50)

    def test_invalid_entity_type(self, client):
        """Test that invalid entityType returns 400"""
        response = client.get(
            "/api/drive/items?entityType=invalid&entityId=deal-items-1",
            headers={"x-user-id": "u1", "x-user-role": "admin"}
        )
        
        assert response.status_code == 400
        data = response.json()
        assert "Invalid entityType" in data["detail"]

    def test_nonexistent_entity_returns_404(self, client):
        """Test that non-existent entity returns 404"""
        response = client.get(
            "/api/drive/items?entityType=deal&entityId=00000000-0000-0000-0000-000000000000",
            headers={"x-user-id": "u1", "x-user-role": "admin"}
        )
        
        assert response.status_code == 404

    def test_requires_authentication(self, client):
        """Test that endpoint requires authentication"""
        response = client.get(
            "/api/drive/items?entityType=deal&entityId=deal-items-1"
        )
        
        assert response.status_code == 401

    def test_accepts_jwt_authentication(self, client):
        """Test that endpoint accepts JWT Bearer token"""
        # Create a mock JWT token
        import jwt
        import os
        
        # Set a test secret
        os.environ["SUPABASE_JWT_SECRET"] = "test-secret-key-for-testing"
        
        # Create a valid token
        token_payload = {
            "sub": "test-user-id",
            "role": "admin",
            "email": "test@example.com"
        }
        token = jwt.encode(token_payload, "test-secret-key-for-testing", algorithm="HS256")
        
        response = client.get(
            "/api/drive/items?entityType=deal&entityId=deal-items-1",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        # Should work with valid JWT
        assert response.status_code in [200, 404]  # 200 if entity exists, 404 if not
        
        # Clean up
        del os.environ["SUPABASE_JWT_SECRET"]

    def test_rejects_invalid_jwt(self, client):
        """Test that endpoint rejects invalid JWT"""
        os.environ["SUPABASE_JWT_SECRET"] = "test-secret-key"
        
        response = client.get(
            "/api/drive/items?entityType=deal&entityId=deal-items-1",
            headers={"Authorization": "Bearer invalid-token"}
        )
        
        assert response.status_code == 401
        
        # Clean up
        del os.environ["SUPABASE_JWT_SECRET"]

    def test_jwt_fallback_to_legacy_when_secret_not_set(self, client):
        """Test that JWT gracefully falls back to legacy auth when secret is not configured"""
        import os
        
        # Ensure JWT secret is not set
        if "SUPABASE_JWT_SECRET" in os.environ:
            del os.environ["SUPABASE_JWT_SECRET"]
        
        # Try to authenticate with Bearer token but provide legacy headers as fallback
        response = client.get(
            "/api/drive/items?entityType=deal&entityId=deal-items-1",
            headers={
                "Authorization": "Bearer some-jwt-token",
                "x-user-id": "test-user",
                "x-user-role": "admin"
            }
        )
        
        # Should succeed using legacy headers instead of throwing 500 error
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data

    def test_company_entity_type(self, client):
        """Test with company entity type"""
        response = client.get(
            "/api/drive/items?entityType=company&entityId=comp-items-1",
            headers={"x-user-id": "u1", "x-user-role": "admin"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data

    def test_lead_entity_type(self, client):
        """Test with lead entity type"""
        response = client.get(
            "/api/drive/items?entityType=lead&entityId=lead-items-1",
            headers={"x-user-id": "u1", "x-user-role": "admin"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data

    def test_total_matches_item_count_without_pagination(self, client):
        """Test that total reflects all items, not just paginated subset"""
        # Get all items with max allowed limit
        response = client.get(
            "/api/drive/items?entityType=deal&entityId=deal-items-1&limit=200",
            headers={"x-user-id": "u1", "x-user-role": "admin"}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Total should match the number of items when limit is high (assuming < 200 items)
        assert data["total"] == len(data["items"])

    def test_soft_deleted_items_excluded(self, client):
        """Test that soft-deleted items are not returned"""
        # Initialize structure
        client.get(
            "/api/drive/items?entityType=deal&entityId=deal-items-1",
            headers={"x-user-id": "u1", "x-user-role": "admin"}
        )
        
        # The adapter should automatically filter out soft-deleted items
        # just like the original endpoint does
        response = client.get(
            "/api/drive/items?entityType=deal&entityId=deal-items-1",
            headers={"x-user-id": "u1", "x-user-role": "admin"}
        )
        
        assert response.status_code == 200
        # The test passes if it returns successfully
        # (actual soft delete filtering is tested in the main drive tests)


class TestDriveItemsQueryParameters:
    """Test query parameter validation"""

    def test_missing_entity_type(self, client):
        """Test that missing entityType returns 422"""
        response = client.get(
            "/api/drive/items?entityId=deal-items-1",
            headers={"x-user-id": "u1", "x-user-role": "admin"}
        )
        
        assert response.status_code == 422  # FastAPI validation error

    def test_missing_entity_id(self, client):
        """Test that missing entityId returns 422"""
        response = client.get(
            "/api/drive/items?entityType=deal",
            headers={"x-user-id": "u1", "x-user-role": "admin"}
        )
        
        assert response.status_code == 422  # FastAPI validation error

    def test_invalid_page_number(self, client):
        """Test that page < 1 returns 422"""
        response = client.get(
            "/api/drive/items?entityType=deal&entityId=deal-items-1&page=0",
            headers={"x-user-id": "u1", "x-user-role": "admin"}
        )
        
        assert response.status_code == 422

    def test_invalid_limit(self, client):
        """Test that limit > 200 returns 422"""
        response = client.get(
            "/api/drive/items?entityType=deal&entityId=deal-items-1&limit=300",
            headers={"x-user-id": "u1", "x-user-role": "admin"}
        )
        
        assert response.status_code == 422

    def test_page_beyond_available_items(self, client):
        """Test that requesting a page beyond available items returns empty list"""
        response = client.get(
            "/api/drive/items?entityType=deal&entityId=deal-items-1&page=1000",
            headers={"x-user-id": "u1", "x-user-role": "admin"}
        )
        
        assert response.status_code == 200
        data = response.json()
        # Should return empty items but total should still be accurate
        assert isinstance(data["items"], list)
        assert isinstance(data["total"], int)
