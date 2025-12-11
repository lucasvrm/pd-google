
import os
# Set environment variables BEFORE any other imports
os.environ["USE_MOCK_DRIVE"] = "true"
os.environ["DRIVE_ROOT_FOLDER_ID"] = "mock-root-id"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base
from main import app
import models
import json
import io
from routers.drive import get_db as original_get_db

# Setup Test DB
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_upload_flow.db"
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
    # Clean up JSON Mock
    if os.path.exists(MOCK_JSON):
        os.remove(MOCK_JSON)
    
    # Clean up old test DB
    if os.path.exists("./test_upload_flow.db"):
        os.remove("./test_upload_flow.db")

    # Override dependency BEFORE creating tables
    app.dependency_overrides[original_get_db] = override_get_db

    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    # Create test entities
    company = models.Company(id="comp-upload-1", name="Upload Test Company")
    db.add(company)

    lead = models.Lead(id="lead-upload-1", title="Upload Test Lead", qualified_company_id="comp-upload-1")
    db.add(lead)

    deal = models.Deal(id="deal-upload-1", title="Upload Test Deal", company_id="comp-upload-1")
    db.add(deal)

    # Create templates with nested structure
    tmpl_lead = models.DriveStructureTemplate(name="Lead Upload Tmpl", entity_type="lead", active=True)
    db.add(tmpl_lead)
    db.commit()
    
    # Create parent and child nodes
    parent_node = models.DriveStructureNode(template_id=tmpl_lead.id, name="Documents", order=0)
    db.add(parent_node)
    db.commit()
    
    child_node = models.DriveStructureNode(
        template_id=tmpl_lead.id, 
        name="Contracts", 
        parent_id=parent_node.id, 
        order=0
    )
    db.add(child_node)

    tmpl_deal = models.DriveStructureTemplate(name="Deal Upload Tmpl", entity_type="deal", active=True)
    db.add(tmpl_deal)
    db.commit()
    node_deal = models.DriveStructureNode(template_id=tmpl_deal.id, name="Files", order=0)
    db.add(node_deal)

    db.commit()
    db.close()

def teardown_module(module):
    # Clear ALL dependency overrides to avoid conflicts with other tests
    app.dependency_overrides.clear()
    
    if os.path.exists("./test_upload_flow.db"):
        os.remove("./test_upload_flow.db")
    if os.path.exists(MOCK_JSON):
        os.remove(MOCK_JSON)

# Create client AFTER module setup - use fixture
@pytest.fixture(scope="module")
def client():
    return TestClient(app)


class TestUploadFlow:
    """Test complete upload flow via API"""

    def test_upload_small_file_to_lead(self, client):
        """Test uploading a small file to a lead entity"""
        # Step 1: Initialize folder structure
        response = client.get("/api/drive/lead/lead-upload-1", headers={"x-user-role": "admin", "x-user-id": "test_user"})
        assert response.status_code == 200
        
        # Step 2: Upload a small file
        file_content = b"This is a test file content"
        file_name = "test_document.txt"
        
        files = {
            "file": (file_name, io.BytesIO(file_content), "text/plain")
        }
        
        response = client.post(
            "/api/drive/lead/lead-upload-1/upload",
            files=files,
            headers={"x-user-role": "admin", "x-user-id": "test_user"}
        )
        
        # Step 3: Verify response
        assert response.status_code == 200
        data = response.json()
        
        # Verify metadata
        assert data["name"] == file_name
        assert data["mimeType"] == "text/plain"
        assert data["size"] == len(file_content)
        assert "id" in data
        assert "createdTime" in data
        
        # Step 4: Verify file appears in the folder structure
        # Get the entity folder from database
        db = TestingSessionLocal()
        entity_folder = db.query(models.DriveFolder).filter(
            models.DriveFolder.entity_type == "lead",
            models.DriveFolder.entity_id == "lead-upload-1"
        ).first()
        
        assert entity_folder is not None
        
        # Verify the file is in the correct parent folder
        assert "parents" in data
        assert entity_folder.folder_id in data["parents"]
        
        # Verify file is recorded in database
        file_record = db.query(models.DriveFile).filter(
            models.DriveFile.file_id == data["id"]
        ).first()
        
        assert file_record is not None
        assert file_record.name == file_name
        assert file_record.mime_type == "text/plain"
        assert file_record.size == len(file_content)
        assert file_record.parent_folder_id == entity_folder.folder_id
        
        db.close()

    def test_upload_file_to_deal(self, client):
        """Test uploading a file to a deal entity"""
        # Step 1: Initialize folder structure
        response = client.get("/api/drive/deal/deal-upload-1", headers={"x-user-role": "manager", "x-user-id": "test_user"})
        assert response.status_code == 200
        
        # Step 2: Upload a file
        file_content = b"Deal file content"
        file_name = "deal_contract.pdf"
        
        files = {
            "file": (file_name, io.BytesIO(file_content), "application/pdf")
        }
        
        response = client.post(
            "/api/drive/deal/deal-upload-1/upload",
            files=files,
            headers={"x-user-role": "manager", "x-user-id": "test_user"}
        )
        
        # Step 3: Verify response
        assert response.status_code == 200
        data = response.json()
        
        # Verify metadata
        assert data["name"] == file_name
        assert data["mimeType"] == "application/pdf"
        assert data["size"] == len(file_content)
        
        # Step 4: Verify file structure
        db = TestingSessionLocal()
        entity_folder = db.query(models.DriveFolder).filter(
            models.DriveFolder.entity_type == "deal",
            models.DriveFolder.entity_id == "deal-upload-1"
        ).first()
        
        assert entity_folder is not None
        assert entity_folder.folder_id in data["parents"]
        
        db.close()

    def test_upload_without_role_uses_default_permission(self, client):
        """Test that upload without role header uses fallback permission"""
        # Initialize structure first
        client.get("/api/drive/lead/lead-upload-1", headers={"x-user-role": "admin", "x-user-id": "test_user"})
        
        # Upload without role header
        file_content = b"No role file"
        files = {
            "file": ("norole.txt", io.BytesIO(file_content), "text/plain")
        }
        
        response = client.post(
            "/api/drive/lead/lead-upload-1/upload",
            files=files
        )
        
        # Should succeed with default (manager/writer) permission
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "norole.txt"

    def test_upload_blocked_for_reader_role(self, client):
        """Test that reader role is blocked from uploading files"""
        # Initialize structure first
        client.get("/api/drive/deal/deal-upload-1", headers={"x-user-role": "admin", "x-user-id": "test_user"})
        
        # Try to upload as reader
        file_content = b"Should be blocked"
        files = {
            "file": ("blocked.txt", io.BytesIO(file_content), "text/plain")
        }
        
        response = client.post(
            "/api/drive/deal/deal-upload-1/upload",
            files=files,
            headers={"x-user-role": "client", "x-user-id": "test_user"}
        )

        # Should be forbidden
        assert response.status_code == 403
        assert "does not have permission" in response.json()["message"]

    def test_upload_to_nonexistent_entity_fails(self, client):
        """Test that upload to non-existent entity fails gracefully"""
        file_content = b"Test content"
        files = {
            "file": ("test.txt", io.BytesIO(file_content), "text/plain")
        }
        
        response = client.post(
            "/api/drive/lead/nonexistent-lead/upload",
            files=files,
            headers={"x-user-role": "admin", "x-user-id": "test_user"}
        )

        # Should fail because structure was never initialized
        assert response.status_code == 404
        assert "not found" in response.json()["message"].lower()

    def test_upload_file_metadata_persists_in_mock_drive(self, client):
        """Test that uploaded file metadata is stored in mock drive JSON"""
        # Initialize and upload
        client.get("/api/drive/lead/lead-upload-1", headers={"x-user-role": "admin", "x-user-id": "test_user"})
        
        file_content = b"Persistent content"
        file_name = "persistent.txt"
        files = {
            "file": (file_name, io.BytesIO(file_content), "text/plain")
        }
        
        response = client.post(
            "/api/drive/lead/lead-upload-1/upload",
            files=files,
            headers={"x-user-role": "admin", "x-user-id": "test_user"}
        )
        
        assert response.status_code == 200
        file_id = response.json()["id"]
        
        # Verify in mock drive JSON
        with open(MOCK_JSON, "r") as f:
            mock_db = json.load(f)
        
        assert file_id in mock_db["files"]
        file_meta = mock_db["files"][file_id]
        assert file_meta["name"] == file_name
        assert file_meta["mimeType"] == "text/plain"
        assert file_meta["size"] == len(file_content)

    def test_multiple_file_uploads(self, client):
        """Test uploading multiple files to the same entity"""
        # Initialize structure
        client.get("/api/drive/deal/deal-upload-1", headers={"x-user-role": "admin", "x-user-id": "test_user"})
        
        # Upload first file
        files1 = {
            "file": ("file1.txt", io.BytesIO(b"Content 1"), "text/plain")
        }
        response1 = client.post(
            "/api/drive/deal/deal-upload-1/upload",
            files=files1,
            headers={"x-user-role": "admin", "x-user-id": "test_user"}
        )
        assert response1.status_code == 200
        
        # Upload second file
        files2 = {
            "file": ("file2.txt", io.BytesIO(b"Content 2"), "text/plain")
        }
        response2 = client.post(
            "/api/drive/deal/deal-upload-1/upload",
            files=files2,
            headers={"x-user-role": "admin", "x-user-id": "test_user"}
        )
        assert response2.status_code == 200
        
        # Verify both files exist in database
        db = TestingSessionLocal()
        file_count = db.query(models.DriveFile).filter(
            models.DriveFile.name.in_(["file1.txt", "file2.txt"])
        ).count()
        assert file_count == 2
        
        db.close()

    def test_upload_analyst_role(self, client):
        """Test that analyst role (writer) can upload files"""
        # Initialize structure
        client.get("/api/drive/lead/lead-upload-1", headers={"x-user-role": "analyst", "x-user-id": "test_user"})
        
        # Upload file as analyst
        file_content = b"Analyst upload"
        files = {
            "file": ("analyst_file.txt", io.BytesIO(file_content), "text/plain")
        }
        
        response = client.post(
            "/api/drive/lead/lead-upload-1/upload",
            files=files,
            headers={"x-user-role": "analyst", "x-user-id": "test_user"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "analyst_file.txt"

    def test_upload_new_business_role(self, client):
        """Test that new_business role (writer) can upload files"""
        # Initialize structure
        client.get("/api/drive/deal/deal-upload-1", headers={"x-user-role": "new_business", "x-user-id": "test_user"})
        
        # Upload file as new_business
        file_content = b"New business upload"
        files = {
            "file": ("nb_file.txt", io.BytesIO(file_content), "text/plain")
        }
        
        response = client.post(
            "/api/drive/deal/deal-upload-1/upload",
            files=files,
            headers={"x-user-role": "new_business", "x-user-id": "test_user"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "nb_file.txt"
