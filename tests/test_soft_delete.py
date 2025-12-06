"""
Tests for soft delete functionality of files and folders.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base
from main import app
import models
import os
from unittest.mock import patch
from services.google_drive_mock import GoogleDriveService
from routers.drive import get_db as original_get_db

# Setup Test DB
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_soft_delete.db"
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
    # Set USE_MOCK_DRIVE to true for tests (though patching config is safer)
    os.environ["USE_MOCK_DRIVE"] = "true"
    
    # Clean up JSON Mock
    if os.path.exists(MOCK_JSON):
        os.remove(MOCK_JSON)
    
    # Clean up old test DB
    if os.path.exists("./test_soft_delete.db"):
        os.remove("./test_soft_delete.db")

    # Override dependency BEFORE creating tables
    app.dependency_overrides[original_get_db] = override_get_db

    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    # Create test entities
    company = models.Company(id="comp-soft-1", name="Soft Delete Test Company")
    db.add(company)

    lead = models.Lead(id="lead-soft-1", title="Soft Delete Test Lead", company_id="comp-soft-1")
    db.add(lead)

    # Create templates
    tmpl_lead = models.DriveStructureTemplate(name="Lead Soft Delete Tmpl", entity_type="lead", active=True)
    db.add(tmpl_lead)
    db.commit()
    node_lead = models.DriveStructureNode(template_id=tmpl_lead.id, name="Lead Folder", order=0)
    db.add(node_lead)

    db.commit()
    db.close()

def teardown_module(module):
    # Clear ALL dependency overrides to avoid conflicts with other tests
    app.dependency_overrides.clear()
    
    if os.path.exists("./test_soft_delete.db"):
        os.remove("./test_soft_delete.db")
    if os.path.exists(MOCK_JSON):
        os.remove(MOCK_JSON)

# Create client AFTER module setup - use fixture
@pytest.fixture(scope="module")
def client():
    mock_service = GoogleDriveService()
    # Patch routers.drive.drive_service AND services.hierarchy_service.config.USE_MOCK_DRIVE
    with patch("routers.drive.drive_service", mock_service), \
         patch("services.hierarchy_service.config.USE_MOCK_DRIVE", True):
        yield TestClient(app)


class TestFileSoftDelete:
    """Test soft delete functionality for files"""

    def test_soft_delete_file_success(self, client):
        """Test successful soft delete of a file"""
        # First, initialize structure and upload a file
        client.get("/drive/lead/lead-soft-1", headers={"x-user-role": "admin", "x-user-id": "user-1"})
        
        # Upload a test file
        file_content = b"Test file content"
        response = client.post(
            "/drive/lead/lead-soft-1/upload",
            files={"file": ("test.txt", file_content, "text/plain")},
            headers={"x-user-role": "admin", "x-user-id": "user-1"}
        )
        assert response.status_code == 200
        uploaded_file = response.json()
        file_id = uploaded_file["id"]
        
        # Soft delete the file
        response = client.delete(
            f"/drive/lead/lead-soft-1/files/{file_id}?reason=Test%20deletion",
            headers={"x-user-role": "admin", "x-user-id": "user-1"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "deleted"
        assert data["file_id"] == file_id
        assert "deleted_at" in data
        assert data["deleted_by"] == "user-1"

    def test_soft_delete_file_not_in_listing(self, client):
        """Test that soft deleted file doesn't appear in default listing"""
        # Initialize and upload
        client.get("/drive/lead/lead-soft-1", headers={"x-user-role": "admin", "x-user-id": "user-2"})
        
        file_content = b"Test file 2"
        response = client.post(
            "/drive/lead/lead-soft-1/upload",
            files={"file": ("test2.txt", file_content, "text/plain")},
            headers={"x-user-role": "admin", "x-user-id": "user-2"}
        )
        file_id = response.json()["id"]
        
        # Verify file is in listing before deletion
        response = client.get("/drive/lead/lead-soft-1", headers={"x-user-role": "admin", "x-user-id": "user-2"})
        files_before = response.json()["files"]
        file_ids_before = [f["id"] for f in files_before]
        assert file_id in file_ids_before
        
        # Soft delete
        client.delete(
            f"/drive/lead/lead-soft-1/files/{file_id}",
            headers={"x-user-role": "admin", "x-user-id": "user-2"}
        )
        
        # Verify file is NOT in listing after deletion
        response = client.get("/drive/lead/lead-soft-1", headers={"x-user-role": "admin", "x-user-id": "user-2"})
        files_after = response.json()["files"]
        file_ids_after = [f["id"] for f in files_after]
        assert file_id not in file_ids_after

    def test_soft_delete_file_with_include_deleted(self, client):
        """Test that soft deleted file appears when include_deleted=true"""
        # Upload file
        client.get("/drive/lead/lead-soft-1", headers={"x-user-role": "admin", "x-user-id": "user-3"})
        
        file_content = b"Test file 3"
        response = client.post(
            "/drive/lead/lead-soft-1/upload",
            files={"file": ("test3.txt", file_content, "text/plain")},
            headers={"x-user-role": "admin", "x-user-id": "user-3"}
        )
        file_id = response.json()["id"]
        
        # Soft delete
        client.delete(
            f"/drive/lead/lead-soft-1/files/{file_id}",
            headers={"x-user-role": "admin", "x-user-id": "user-3"}
        )
        
        # Verify file is NOT in default listing
        response = client.get("/drive/lead/lead-soft-1", headers={"x-user-role": "admin", "x-user-id": "user-3"})
        file_ids = [f["id"] for f in response.json()["files"]]
        assert file_id not in file_ids
        
        # Verify file IS in listing with include_deleted=true
        response = client.get("/drive/lead/lead-soft-1?include_deleted=true", headers={"x-user-role": "admin", "x-user-id": "user-3"})
        file_ids = [f["id"] for f in response.json()["files"]]
        assert file_id in file_ids

    def test_soft_delete_file_permission_denied(self, client):
        """Test that reader role cannot soft delete files"""
        # Upload file as admin
        client.get("/drive/lead/lead-soft-1", headers={"x-user-role": "admin", "x-user-id": "admin-user"})
        
        file_content = b"Test file 4"
        response = client.post(
            "/drive/lead/lead-soft-1/upload",
            files={"file": ("test4.txt", file_content, "text/plain")},
            headers={"x-user-role": "admin", "x-user-id": "admin-user"}
        )
        file_id = response.json()["id"]
        
        # Try to delete as reader
        response = client.delete(
            f"/drive/lead/lead-soft-1/files/{file_id}",
            headers={"x-user-role": "client", "x-user-id": "reader-user"}
        )
        assert response.status_code == 403
        assert "does not have permission" in response.json()["detail"]

    def test_soft_delete_file_not_found(self, client):
        """Test soft delete of non-existent file"""
        response = client.delete(
            "/drive/lead/lead-soft-1/files/non-existent-file-id",
            headers={"x-user-role": "admin", "x-user-id": "user-5"}
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_soft_delete_file_already_deleted(self, client):
        """Test soft delete of already deleted file"""
        # Upload file
        client.get("/drive/lead/lead-soft-1", headers={"x-user-role": "admin", "x-user-id": "user-6"})
        
        file_content = b"Test file 5"
        response = client.post(
            "/drive/lead/lead-soft-1/upload",
            files={"file": ("test5.txt", file_content, "text/plain")},
            headers={"x-user-role": "admin", "x-user-id": "user-6"}
        )
        file_id = response.json()["id"]
        
        # First deletion
        response = client.delete(
            f"/drive/lead/lead-soft-1/files/{file_id}",
            headers={"x-user-role": "admin", "x-user-id": "user-6"}
        )
        assert response.status_code == 200
        
        # Second deletion attempt
        response = client.delete(
            f"/drive/lead/lead-soft-1/files/{file_id}",
            headers={"x-user-role": "admin", "x-user-id": "user-6"}
        )
        assert response.status_code == 400
        assert "already marked as deleted" in response.json()["detail"]

    def test_soft_delete_file_writer_role(self, client):
        """Test that writer role can soft delete files"""
        # Upload file as manager
        client.get("/drive/lead/lead-soft-1", headers={"x-user-role": "manager", "x-user-id": "manager-user"})
        
        file_content = b"Test file 6"
        response = client.post(
            "/drive/lead/lead-soft-1/upload",
            files={"file": ("test6.txt", file_content, "text/plain")},
            headers={"x-user-role": "manager", "x-user-id": "manager-user"}
        )
        file_id = response.json()["id"]
        
        # Delete as manager (writer role)
        response = client.delete(
            f"/drive/lead/lead-soft-1/files/{file_id}",
            headers={"x-user-role": "manager", "x-user-id": "manager-user"}
        )
        assert response.status_code == 200
        assert response.json()["status"] == "deleted"


class TestFolderSoftDelete:
    """Test soft delete functionality for folders"""

    def test_soft_delete_folder_success(self, client):
        """Test successful soft delete of a folder"""
        # Initialize structure and create a folder
        client.get("/drive/lead/lead-soft-1", headers={"x-user-role": "admin", "x-user-id": "user-7"})
        
        response = client.post(
            "/drive/lead/lead-soft-1/folder",
            json={"name": "Test Folder for Deletion"},
            headers={"x-user-role": "admin", "x-user-id": "user-7"}
        )
        assert response.status_code == 200
        folder_id = response.json()["id"]
        
        # Soft delete the folder
        response = client.delete(
            f"/drive/lead/lead-soft-1/folders/{folder_id}?reason=Test%20folder%20deletion",
            headers={"x-user-role": "admin", "x-user-id": "user-7"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "deleted"
        assert data["folder_id"] == folder_id
        assert "deleted_at" in data

    def test_soft_delete_folder_permission_denied(self, client):
        """Test that reader role cannot soft delete folders"""
        # Create folder as admin
        client.get("/drive/lead/lead-soft-1", headers={"x-user-role": "admin", "x-user-id": "admin-user"})
        
        response = client.post(
            "/drive/lead/lead-soft-1/folder",
            json={"name": "Test Folder 2"},
            headers={"x-user-role": "admin", "x-user-id": "admin-user"}
        )
        folder_id = response.json()["id"]
        
        # Try to delete as reader
        response = client.delete(
            f"/drive/lead/lead-soft-1/folders/{folder_id}",
            headers={"x-user-role": "client", "x-user-id": "reader-user"}
        )
        assert response.status_code == 403
        assert "does not have permission" in response.json()["detail"]

    def test_soft_delete_folder_writer_role(self, client):
        """Test that writer role (analyst) can soft delete folders"""
        # Create folder as analyst
        client.get("/drive/lead/lead-soft-1", headers={"x-user-role": "analyst", "x-user-id": "analyst-user"})
        
        response = client.post(
            "/drive/lead/lead-soft-1/folder",
            json={"name": "Analyst Test Folder"},
            headers={"x-user-role": "analyst", "x-user-id": "analyst-user"}
        )
        folder_id = response.json()["id"]
        
        # Delete as analyst
        response = client.delete(
            f"/drive/lead/lead-soft-1/folders/{folder_id}",
            headers={"x-user-role": "analyst", "x-user-id": "analyst-user"}
        )
        assert response.status_code == 200
        assert response.json()["status"] == "deleted"


class TestSoftDeleteAuditLog:
    """Test audit log integration for soft delete operations"""

    def test_soft_delete_creates_audit_log(self, client):
        """Test that soft delete creates an audit log entry"""
        db = TestingSessionLocal()
        
        # Upload and delete file
        client.get("/drive/lead/lead-soft-1", headers={"x-user-role": "admin", "x-user-id": "user-8"})
        
        file_content = b"Audit test file"
        response = client.post(
            "/drive/lead/lead-soft-1/upload",
            files={"file": ("audit_test.txt", file_content, "text/plain")},
            headers={"x-user-role": "admin", "x-user-id": "user-8"}
        )
        file_id = response.json()["id"]
        
        # Count audit log entries before deletion
        count_before = db.query(models.DriveChangeLog).filter(
            models.DriveChangeLog.resource_state == "soft_delete"
        ).count()
        
        # Soft delete
        client.delete(
            f"/drive/lead/lead-soft-1/files/{file_id}?reason=Audit%20test",
            headers={"x-user-role": "admin", "x-user-id": "user-8"}
        )
        
        # Verify audit log entry was created
        count_after = db.query(models.DriveChangeLog).filter(
            models.DriveChangeLog.resource_state == "soft_delete"
        ).count()
        
        assert count_after == count_before + 1
        
        # Verify audit log details
        audit_entry = db.query(models.DriveChangeLog).filter(
            models.DriveChangeLog.changed_resource_id == file_id,
            models.DriveChangeLog.resource_state == "soft_delete"
        ).first()
        
        assert audit_entry is not None
        assert audit_entry.event_type == "file_soft_delete"
        assert "user-8" in audit_entry.raw_headers
        assert "Audit test" in audit_entry.raw_headers
        
        db.close()
