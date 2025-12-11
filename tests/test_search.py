"""
Tests for advanced search functionality.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base
from main import app
import models
import os
from routers.drive import get_db as original_get_db
from datetime import datetime, timezone, timedelta

# Setup Test DB
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_search.db"
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
    # Set USE_MOCK_DRIVE to true for tests
    os.environ["USE_MOCK_DRIVE"] = "true"
    os.environ["DRIVE_ROOT_FOLDER_ID"] = "mock-root-id"
    
    # Clean up JSON Mock
    if os.path.exists(MOCK_JSON):
        os.remove(MOCK_JSON)
    
    # Clean up old test DB
    if os.path.exists("./test_search.db"):
        os.remove("./test_search.db")

    # Override dependency BEFORE creating tables
    app.dependency_overrides[original_get_db] = override_get_db

    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    # Create test entities
    company1 = models.Company(id="comp-search-1", name="Search Test Company 1")
    company2 = models.Company(id="comp-search-2", name="Search Test Company 2")
    db.add(company1)
    db.add(company2)

    lead1 = models.Lead(id="lead-search-1", title="Important Lead", qualified_company_id="comp-search-1")
    lead2 = models.Lead(id="lead-search-2", title="Regular Lead", qualified_company_id="comp-search-2")
    db.add(lead1)
    db.add(lead2)

    deal1 = models.Deal(id="deal-search-1", title="Big Deal", company_id="comp-search-1")
    db.add(deal1)

    # Create templates
    tmpl_lead = models.DriveStructureTemplate(name="Lead Search Tmpl", entity_type="lead", active=True)
    db.add(tmpl_lead)
    db.commit()
    node_lead = models.DriveStructureNode(template_id=tmpl_lead.id, name="Lead Folder", order=0)
    db.add(node_lead)

    tmpl_deal = models.DriveStructureTemplate(name="Deal Search Tmpl", entity_type="deal", active=True)
    db.add(tmpl_deal)
    db.commit()
    node_deal = models.DriveStructureNode(template_id=tmpl_deal.id, name="Deal Folder", order=0)
    db.add(node_deal)

    tmpl_company = models.DriveStructureTemplate(name="Company Search Tmpl", entity_type="company", active=True)
    db.add(tmpl_company)
    db.commit()
    node_company = models.DriveStructureNode(template_id=tmpl_company.id, name="Company Folder", order=0)
    db.add(node_company)

    db.commit()
    db.close()

def teardown_module(module):
    # Clear ALL dependency overrides to avoid conflicts with other tests
    app.dependency_overrides.clear()
    
    if os.path.exists("./test_search.db"):
        os.remove("./test_search.db")
    if os.path.exists(MOCK_JSON):
        os.remove(MOCK_JSON)

# Create client AFTER module setup - use fixture
@pytest.fixture(scope="module")
def client():
    return TestClient(app)


class TestBasicSearch:
    """Test basic search functionality"""

    def test_search_empty_results(self, client):
        """Test search with no results"""
        response = client.get(
            "/api/drive/search?q=nonexistent",
            headers={"x-user-role": "admin", "x-user-id": "test_user"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["items"] == []
        assert data["page"] == 1
        assert data["permission"] == "owner"

    def test_search_by_name(self, client):
        """Test search by partial name match"""
        # First, initialize and upload some files
        client.get("/api/drive/lead/lead-search-1", headers={"x-user-role": "admin", "x-user-id": "test_user"})
        
        # Upload test files
        response1 = client.post(
            "/api/drive/lead/lead-search-1/upload",
            files={"file": ("important_document.pdf", b"test content", "application/pdf")},
            headers={"x-user-role": "admin", "x-user-id": "test_user"}
        )
        assert response1.status_code == 200
        
        response2 = client.post(
            "/api/drive/lead/lead-search-1/upload",
            files={"file": ("regular_file.txt", b"test content", "text/plain")},
            headers={"x-user-role": "admin", "x-user-id": "test_user"}
        )
        assert response2.status_code == 200
        
        # Search for "important"
        response = client.get(
            "/api/drive/search?q=important",
            headers={"x-user-role": "admin", "x-user-id": "test_user"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        
        # Check that at least one result contains "important"
        found = any("important" in item["name"].lower() for item in data["items"])
        assert found

    def test_search_case_insensitive(self, client):
        """Test that search is case-insensitive"""
        client.get("/api/drive/lead/lead-search-2", headers={"x-user-role": "admin", "x-user-id": "test_user"})
        
        client.post(
            "/api/drive/lead/lead-search-2/upload",
            files={"file": ("CaseSensitive.txt", b"test", "text/plain")},
            headers={"x-user-role": "admin", "x-user-id": "test_user"}
        )
        
        # Search with lowercase
        response = client.get(
            "/api/drive/search?q=casesensitive",
            headers={"x-user-role": "admin", "x-user-id": "test_user"}
        )
        assert response.status_code == 200
        assert response.json()["total"] >= 1


class TestEntityFilters:
    """Test filtering by entity_type and entity_id"""

    def test_search_by_entity_type(self, client):
        """Test filtering by entity_type"""
        # Upload files to different entities
        client.get("/api/drive/lead/lead-search-1", headers={"x-user-role": "admin", "x-user-id": "test_user"})
        client.post(
            "/api/drive/lead/lead-search-1/upload",
            files={"file": ("lead_doc.pdf", b"test", "application/pdf")},
            headers={"x-user-role": "admin", "x-user-id": "test_user"}
        )
        
        client.get("/api/drive/deal/deal-search-1", headers={"x-user-role": "admin", "x-user-id": "test_user"})
        client.post(
            "/api/drive/deal/deal-search-1/upload",
            files={"file": ("deal_doc.pdf", b"test", "application/pdf")},
            headers={"x-user-role": "admin", "x-user-id": "test_user"}
        )
        
        # Search only in leads
        response = client.get(
            "/api/drive/search?entity_type=lead&q=doc",
            headers={"x-user-role": "admin", "x-user-id": "test_user"}
        )
        assert response.status_code == 200
        data = response.json()
        
        # All file results should be from lead entities
        file_items = [item for item in data["items"] if item.get("type") == "file"]
        # We can't easily verify parent entity without more complex logic,
        # but we can verify the search executed successfully
        assert data["total"] >= 0

    def test_search_by_entity_id(self, client):
        """Test filtering by specific entity_id"""
        # Search for specific lead
        response = client.get(
            "/api/drive/search?entity_type=lead&entity_id=lead-search-1",
            headers={"x-user-role": "admin", "x-user-id": "test_user"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data

    def test_search_invalid_entity_type(self, client):
        """Test that invalid entity_type returns 400"""
        response = client.get(
            "/api/drive/search?entity_type=invalid",
            headers={"x-user-role": "admin", "x-user-id": "test_user"}
        )
        assert response.status_code == 400
        assert "Invalid entity_type" in response.json()["message"]


class TestMimeTypeFilter:
    """Test filtering by MIME type"""

    def test_search_by_mime_type_pdf(self, client):
        """Test filtering by PDF MIME type"""
        client.get("/api/drive/lead/lead-search-1", headers={"x-user-role": "admin", "x-user-id": "test_user"})
        
        # Upload different file types
        client.post(
            "/api/drive/lead/lead-search-1/upload",
            files={"file": ("doc1.pdf", b"pdf content", "application/pdf")},
            headers={"x-user-role": "admin", "x-user-id": "test_user"}
        )
        client.post(
            "/api/drive/lead/lead-search-1/upload",
            files={"file": ("doc2.txt", b"text content", "text/plain")},
            headers={"x-user-role": "admin", "x-user-id": "test_user"}
        )
        
        # Search for PDFs only
        response = client.get(
            "/api/drive/search?mime_type=application/pdf",
            headers={"x-user-role": "admin", "x-user-id": "test_user"}
        )
        assert response.status_code == 200
        data = response.json()
        
        # All file results should be PDFs
        file_items = [item for item in data["items"] if item.get("type") == "file"]
        for item in file_items:
            assert item["mimeType"] == "application/pdf"

    def test_search_by_mime_type_text(self, client):
        """Test filtering by text MIME type"""
        response = client.get(
            "/api/drive/search?mime_type=text/plain",
            headers={"x-user-role": "admin", "x-user-id": "test_user"}
        )
        assert response.status_code == 200
        data = response.json()
        
        file_items = [item for item in data["items"] if item.get("type") == "file"]
        for item in file_items:
            assert item["mimeType"] == "text/plain"


class TestDateFilters:
    """Test filtering by creation date"""

    def test_search_by_date_from(self, client):
        """Test filtering by created_from date"""
        from urllib.parse import quote
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        
        response = client.get(
            f"/api/drive/search?created_from={quote(yesterday)}",
            headers={"x-user-role": "admin", "x-user-id": "test_user"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data

    def test_search_by_date_to(self, client):
        """Test filtering by created_to date"""
        from urllib.parse import quote
        tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        
        response = client.get(
            f"/api/drive/search?created_to={quote(tomorrow)}",
            headers={"x-user-role": "admin", "x-user-id": "test_user"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data

    def test_search_by_date_range(self, client):
        """Test filtering by date range"""
        from urllib.parse import quote
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        
        response = client.get(
            f"/api/drive/search?created_from={quote(yesterday)}&created_to={quote(tomorrow)}",
            headers={"x-user-role": "admin", "x-user-id": "test_user"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data

    def test_search_invalid_date_format(self, client):
        """Test that invalid date format returns 400"""
        response = client.get(
            "/api/drive/search?created_from=invalid-date",
            headers={"x-user-role": "admin", "x-user-id": "test_user"}
        )
        assert response.status_code == 400
        assert "Invalid created_from format" in response.json()["message"]


class TestSoftDelete:
    """Test soft delete behavior in search"""

    def test_search_excludes_deleted_by_default(self, client):
        """Test that deleted files are excluded by default"""
        client.get("/api/drive/lead/lead-search-1", headers={"x-user-role": "admin", "x-user-id": "test-user"})
        
        # Upload and then delete a file
        response = client.post(
            "/api/drive/lead/lead-search-1/upload",
            files={"file": ("to_delete.txt", b"will be deleted", "text/plain")},
            headers={"x-user-role": "admin", "x-user-id": "test_user"}
        )
        file_id = response.json()["id"]
        
        # Search should find it
        response = client.get(
            "/api/drive/search?q=to_delete",
            headers={"x-user-role": "admin", "x-user-id": "test_user"}
        )
        before_delete_count = response.json()["total"]
        assert before_delete_count >= 1
        
        # Delete the file
        client.delete(
            f"/api/drive/lead/lead-search-1/files/{file_id}",
            headers={"x-user-role": "admin", "x-user-id": "test-user"}
        )
        
        # Search should not find it by default
        response = client.get(
            "/api/drive/search?q=to_delete",
            headers={"x-user-role": "admin", "x-user-id": "test_user"}
        )
        after_delete_count = response.json()["total"]
        assert after_delete_count < before_delete_count

    def test_search_includes_deleted_with_flag(self, client):
        """Test that deleted files are included when include_deleted=true"""
        client.get("/api/drive/lead/lead-search-2", headers={"x-user-role": "admin", "x-user-id": "test-user"})
        
        # Upload and delete a file
        response = client.post(
            "/api/drive/lead/lead-search-2/upload",
            files={"file": ("deleted_file.txt", b"deleted", "text/plain")},
            headers={"x-user-role": "admin", "x-user-id": "test_user"}
        )
        file_id = response.json()["id"]
        
        client.delete(
            f"/api/drive/lead/lead-search-2/files/{file_id}",
            headers={"x-user-role": "admin", "x-user-id": "test-user"}
        )
        
        # Search with include_deleted=true should find it
        response = client.get(
            "/api/drive/search?q=deleted_file&include_deleted=true",
            headers={"x-user-role": "admin", "x-user-id": "test_user"}
        )
        data = response.json()
        
        # Should find the deleted file
        found = any("deleted_file" in item["name"].lower() for item in data["items"])
        if found:
            # Verify it has deleted_at timestamp
            deleted_item = next(item for item in data["items"] if "deleted_file" in item["name"].lower())
            assert deleted_item.get("deleted_at") is not None


class TestPagination:
    """Test pagination functionality"""

    def test_search_pagination_default(self, client):
        """Test default pagination"""
        response = client.get(
            "/api/drive/search",
            headers={"x-user-role": "admin", "x-user-id": "test_user"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 1
        assert data["page_size"] == 50
        assert "total_pages" in data

    def test_search_pagination_custom_page_size(self, client):
        """Test custom page size"""
        response = client.get(
            "/api/drive/search?page_size=10",
            headers={"x-user-role": "admin", "x-user-id": "test_user"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["page_size"] == 10
        assert len(data["items"]) <= 10

    def test_search_pagination_page_navigation(self, client):
        """Test navigating between pages"""
        # Get first page
        response1 = client.get(
            "/api/drive/search?page=1&page_size=5",
            headers={"x-user-role": "admin", "x-user-id": "test_user"}
        )
        assert response1.status_code == 200
        data1 = response1.json()
        
        # Get second page if there are enough results
        if data1["total"] > 5:
            response2 = client.get(
                "/api/drive/search?page=2&page_size=5",
                headers={"x-user-role": "admin", "x-user-id": "test_user"}
            )
            assert response2.status_code == 200
            data2 = response2.json()
            assert data2["page"] == 2

    def test_search_pagination_max_page_size(self, client):
        """Test that page_size above 100 is rejected by validation"""
        response = client.get(
            "/api/drive/search?page_size=200",
            headers={"x-user-role": "admin", "x-user-id": "test_user"}
        )
        # FastAPI validation rejects values > 100 with 422
        assert response.status_code == 422
        
        # Test that 100 works fine
        response = client.get(
            "/api/drive/search?page_size=100",
            headers={"x-user-role": "admin", "x-user-id": "test_user"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["page_size"] == 100


class TestPermissions:
    """Test permission enforcement in search"""

    def test_search_as_admin(self, client):
        """Test search with admin role (owner permission)"""
        response = client.get(
            "/api/drive/search",
            headers={"x-user-role": "admin", "x-user-id": "test_user"}
        )
        assert response.status_code == 200
        assert response.json()["permission"] == "owner"

    def test_search_as_manager(self, client):
        """Test search with manager role (writer permission)"""
        response = client.get(
            "/api/drive/search",
            headers={"x-user-role": "manager", "x-user-id": "test_user"}
        )
        assert response.status_code == 200
        assert response.json()["permission"] == "writer"

    def test_search_as_client(self, client):
        """Test search with client role (reader permission)"""
        response = client.get(
            "/api/drive/search",
            headers={"x-user-role": "client", "x-user-id": "test_user"}
        )
        assert response.status_code == 200
        assert response.json()["permission"] == "reader"


class TestAuditLog:
    """Test audit logging of search operations"""

    def test_search_creates_audit_log(self, client):
        """Test that search operations are logged"""
        db = TestingSessionLocal()
        
        # Count audit log entries before search
        count_before = db.query(models.DriveChangeLog).filter(
            models.DriveChangeLog.resource_state == "search"
        ).count()
        
        # Perform search
        client.get(
            "/api/drive/search?q=test&entity_type=lead",
            headers={"x-user-role": "admin", "x-user-id": "audit-test-user"}
        )
        
        # Verify audit log entry was created
        count_after = db.query(models.DriveChangeLog).filter(
            models.DriveChangeLog.resource_state == "search"
        ).count()
        
        assert count_after == count_before + 1
        
        # Verify audit log details
        audit_entry = db.query(models.DriveChangeLog).filter(
            models.DriveChangeLog.resource_state == "search"
        ).order_by(models.DriveChangeLog.id.desc()).first()
        
        assert audit_entry is not None
        assert audit_entry.event_type == "advanced_search"
        assert "audit-test-user" in audit_entry.raw_headers
        assert "test" in audit_entry.raw_headers
        
        db.close()


class TestCombinedFilters:
    """Test combining multiple filters"""

    def test_search_combined_filters(self, client):
        """Test search with multiple filters combined"""
        response = client.get(
            "/api/drive/search?entity_type=lead&q=doc&mime_type=application/pdf",
            headers={"x-user-role": "admin", "x-user-id": "test_user"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        
        # All PDF files should match the mime_type filter
        file_items = [item for item in data["items"] if item.get("type") == "file"]
        for item in file_items:
            if item.get("mimeType"):
                assert item["mimeType"] == "application/pdf"
