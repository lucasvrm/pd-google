
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
from services.permission_service import PermissionService

# Setup Test DB
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_permissions.db"
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
    if os.path.exists("./test_permissions.db"):
        os.remove("./test_permissions.db")

    # Override dependency BEFORE creating tables
    app.dependency_overrides[original_get_db] = override_get_db

    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    # Create test entities
    company = models.Company(id="comp-perm-1", name="Perm Test Company")
    db.add(company)

    lead = models.Lead(id="lead-perm-1", title="Perm Test Lead", qualified_company_id="comp-perm-1")
    db.add(lead)

    deal = models.Deal(id="deal-perm-1", title="Perm Test Deal", company_id="comp-perm-1")
    db.add(deal)

    # Create templates
    tmpl_lead = models.DriveStructureTemplate(name="Lead Perm Tmpl", entity_type="lead", active=True)
    db.add(tmpl_lead)
    db.commit()
    node_lead = models.DriveStructureNode(template_id=tmpl_lead.id, name="Lead Folder", order=0)
    db.add(node_lead)

    tmpl_deal = models.DriveStructureTemplate(name="Deal Perm Tmpl", entity_type="deal", active=True)
    db.add(tmpl_deal)
    db.commit()
    node_deal = models.DriveStructureNode(template_id=tmpl_deal.id, name="Deal Folder", order=0)
    db.add(node_deal)

    db.commit()
    db.close()

def teardown_module(module):
    # Clear ALL dependency overrides to avoid conflicts with other tests
    app.dependency_overrides.clear()
    
    if os.path.exists("./test_permissions.db"):
        os.remove("./test_permissions.db")
    if os.path.exists(MOCK_JSON):
        os.remove(MOCK_JSON)

# Create client AFTER module setup - use fixture
@pytest.fixture(scope="module")
def client():
    # Patch the drive service to use Mock for these tests
    # We also patch USE_MOCK_DRIVE in hierarchy service so it creates the mock service
    mock_service = GoogleDriveService()

    with patch("routers.drive.drive_service", mock_service), \
         patch("services.hierarchy_service.config.USE_MOCK_DRIVE", True), \
         patch("services.hierarchy_service.config.DRIVE_ROOT_FOLDER_ID", "mock-root-id"):
        yield TestClient(app)


class TestPermissionMapping:
    """Test role to permission mapping in PermissionService"""

    def test_admin_role_mapping(self):
        db = TestingSessionLocal()
        perm_service = PermissionService(db)
        
        permission = perm_service.get_drive_permission_from_app_role("admin", "lead")
        assert permission == "owner"
        
        db.close()

    def test_superadmin_role_mapping(self):
        db = TestingSessionLocal()
        perm_service = PermissionService(db)
        
        permission = perm_service.get_drive_permission_from_app_role("superadmin", "deal")
        assert permission == "owner"
        
        db.close()

    def test_super_admin_variant_role_mapping(self):
        """Test super_admin variant maps to owner"""
        db = TestingSessionLocal()
        perm_service = PermissionService(db)
        
        permission = perm_service.get_drive_permission_from_app_role("super_admin", "company")
        assert permission == "owner"
        
        db.close()

    def test_manager_role_mapping(self):
        db = TestingSessionLocal()
        perm_service = PermissionService(db)
        
        permission = perm_service.get_drive_permission_from_app_role("manager", "lead")
        assert permission == "writer"
        
        db.close()

    def test_analyst_role_mapping(self):
        db = TestingSessionLocal()
        perm_service = PermissionService(db)
        
        permission = perm_service.get_drive_permission_from_app_role("analyst", "deal")
        assert permission == "writer"
        
        db.close()

    def test_new_business_role_mapping(self):
        db = TestingSessionLocal()
        perm_service = PermissionService(db)
        
        permission = perm_service.get_drive_permission_from_app_role("new_business", "lead")
        assert permission == "writer"
        
        db.close()

    def test_newbusiness_variant_role_mapping(self):
        """Test newbusiness variant (no underscore) maps to writer"""
        db = TestingSessionLocal()
        perm_service = PermissionService(db)
        
        permission = perm_service.get_drive_permission_from_app_role("newbusiness", "lead")
        assert permission == "writer"
        
        db.close()

    def test_client_role_mapping(self):
        db = TestingSessionLocal()
        perm_service = PermissionService(db)
        
        permission = perm_service.get_drive_permission_from_app_role("client", "deal")
        assert permission == "reader"
        
        db.close()

    def test_customer_role_mapping(self):
        db = TestingSessionLocal()
        perm_service = PermissionService(db)
        
        permission = perm_service.get_drive_permission_from_app_role("customer", "company")
        assert permission == "reader"
        
        db.close()

    def test_unknown_role_defaults_to_reader(self):
        """Test that unknown roles default to reader (least privilege)"""
        db = TestingSessionLocal()
        perm_service = PermissionService(db)
        
        permission = perm_service.get_drive_permission_from_app_role("unknown_role", "lead")
        assert permission == "reader"
        
        db.close()

    def test_empty_role_defaults_to_manager_writer(self):
        """Test that empty role defaults to manager (backward compatibility)"""
        db = TestingSessionLocal()
        perm_service = PermissionService(db)
        
        permission = perm_service.get_drive_permission_from_app_role("", "lead")
        # According to the code, empty role triggers the fallback path which calls get_permission with "manager"
        assert permission == "writer"
        
        db.close()

    def test_none_role_defaults_to_manager_writer(self):
        """Test that None role defaults to manager (backward compatibility)"""
        db = TestingSessionLocal()
        perm_service = PermissionService(db)
        
        permission = perm_service.get_drive_permission_from_app_role(None, "lead")
        assert permission == "writer"
        
        db.close()


class TestPermissionEndpoints:
    """Test that endpoints enforce permissions correctly"""

    def test_writer_can_access_get_endpoint(self, client):
        """Test that writer role (manager) can access GET endpoint"""
        response = client.get("/api/drive/lead/lead-perm-1", headers={"x-user-id": "u1", "x-user-role": "manager"})
        assert response.status_code == 200
        data = response.json()
        assert data["permission"] == "writer"

    def test_reader_can_access_get_endpoint(self, client):
        """Test that reader role (client) can access GET endpoint"""
        response = client.get("/api/drive/lead/lead-perm-1", headers={"x-user-id": "u2", "x-user-role": "client"})
        assert response.status_code == 200
        data = response.json()
        assert data["permission"] == "reader"

    def test_owner_can_access_get_endpoint(self, client):
        """Test that owner role (admin) can access GET endpoint"""
        response = client.get("/api/drive/deal/deal-perm-1", headers={"x-user-id": "u3", "x-user-role": "admin"})
        assert response.status_code == 200
        data = response.json()
        assert data["permission"] == "owner"

    def test_writer_can_create_folder(self, client):
        """Test that writer role can create folders"""
        # First, initialize structure with GET
        client.get("/api/drive/lead/lead-perm-1", headers={"x-user-id": "u1", "x-user-role": "manager"})
        
        # Then create folder
        response = client.post(
            "/api/drive/lead/lead-perm-1/folder",
            json={"name": "Writer Test Folder"},
            headers={"x-user-id": "u1", "x-user-role": "manager"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Writer Test Folder"

    def test_owner_can_create_folder(self, client):
        """Test that owner role can create folders"""
        # First, initialize structure with GET
        client.get("/api/drive/deal/deal-perm-1", headers={"x-user-id": "u3", "x-user-role": "admin"})
        
        # Then create folder
        response = client.post(
            "/api/drive/deal/deal-perm-1/folder",
            json={"name": "Owner Test Folder"},
            headers={"x-user-id": "u3", "x-user-role": "admin"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Owner Test Folder"

    def test_reader_blocked_from_create_folder(self, client):
        """Test that reader role is blocked from creating folders"""
        # First, initialize structure with GET using a writer role
        client.get("/api/drive/lead/lead-perm-1", headers={"x-user-id": "u3", "x-user-role": "admin"})
        
        # Then try to create folder as reader
        response = client.post(
            "/api/drive/lead/lead-perm-1/folder",
            json={"name": "Reader Blocked Folder"},
            headers={"x-user-id": "u2", "x-user-role": "client"}
        )
        assert response.status_code == 403
        assert "does not have permission" in response.json()["detail"]

    def test_analyst_can_create_folder(self, client):
        """Test that analyst role (writer) can create folders"""
        # First, initialize structure with GET
        client.get("/api/drive/deal/deal-perm-1", headers={"x-user-id": "u4", "x-user-role": "analyst"})
        
        # Then create folder
        response = client.post(
            "/api/drive/deal/deal-perm-1/folder",
            json={"name": "Analyst Test Folder"},
            headers={"x-user-id": "u4", "x-user-role": "analyst"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Analyst Test Folder"

    def test_new_business_can_create_folder(self, client):
        """Test that new_business role (writer) can create folders"""
        # First, initialize structure with GET
        client.get("/api/drive/lead/lead-perm-1", headers={"x-user-id": "u5", "x-user-role": "new_business"})
        
        # Then create folder
        response = client.post(
            "/api/drive/lead/lead-perm-1/folder",
            json={"name": "New Business Test Folder"},
            headers={"x-user-id": "u5", "x-user-role": "new_business"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "New Business Test Folder"

    def test_customer_blocked_from_create_folder(self, client):
        """Test that customer role (reader) is blocked from creating folders"""
        # First, initialize structure with GET using a writer role
        client.get("/api/drive/deal/deal-perm-1", headers={"x-user-id": "u3", "x-user-role": "admin"})
        
        # Then try to create folder as customer
        response = client.post(
            "/api/drive/deal/deal-perm-1/folder",
            json={"name": "Customer Blocked Folder"},
            headers={"x-user-id": "u6", "x-user-role": "customer"}
        )
        assert response.status_code == 403
        assert "does not have permission" in response.json()["detail"]
