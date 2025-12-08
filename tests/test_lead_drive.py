
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base
from main import app
import models
import os
import time
from unittest.mock import patch, MagicMock
from services.google_drive_mock import GoogleDriveService

# Import dependencies
import database
import routers.drive

# Setup Test DB
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_lead_drive.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

# Override dependencies
app.dependency_overrides[database.get_db] = override_get_db
app.dependency_overrides[routers.drive.get_db] = override_get_db

@pytest.fixture(scope="module")
def client():
    # Setup DB
    if os.path.exists("./test_lead_drive.db"):
        os.remove("./test_lead_drive.db")

    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    # Create Company
    company = models.Company(id="comp-lead-test", name="Lead Test Company")
    db.add(company)

    # Create Lead
    lead = models.Lead(id="lead-test-1", title="My Awesome Lead", qualified_company_id="comp-lead-test")
    db.add(lead)

    # Create Template
    lead_template = models.DriveStructureTemplate(name="Lead Template", entity_type="lead", active=True)
    db.add(lead_template)
    db.commit()

    # Create Nodes
    nodes = ["00. Admin", "01. Materials"]
    for i, name in enumerate(nodes):
        node = models.DriveStructureNode(template_id=lead_template.id, name=name, order=i)
        db.add(node)

    db.commit()
    db.close()

    # Mock Drive Service
    mock_service = GoogleDriveService()

    # Clean mock file
    if os.path.exists("mock_drive_db.json"):
        os.remove("mock_drive_db.json")

    # We need to patch database.SessionLocal so background tasks use the test DB
    with patch("routers.drive.drive_service", mock_service), \
         patch("routers.drive_items_adapter.drive_service", mock_service), \
         patch("services.hierarchy_service.config.USE_MOCK_DRIVE", True), \
         patch("services.hierarchy_service.config.DRIVE_ROOT_FOLDER_ID", "mock-root-id"), \
         patch("services.hierarchy_service.get_drive_service", return_value=mock_service), \
         patch("database.SessionLocal", TestingSessionLocal):

        with TestClient(app) as c:
            yield c

    # Teardown
    if os.path.exists("./test_lead_drive.db"):
        os.remove("./test_lead_drive.db")
    if os.path.exists("mock_drive_db.json"):
        os.remove("mock_drive_db.json")

def test_ensure_lead_structure_on_get(client):
    """
    Test that calling GET /api/drive/lead/{id} creates the folder structure.
    """
    headers = {"x-user-id": "u1", "x-user-role": "admin"}
    response = client.get("/api/drive/lead/lead-test-1", headers=headers)

    assert response.status_code == 200, f"Response: {response.text}"

    # Initial response might be empty because template application is a background task
    # We call it again to verify populated structure
    # Since TestClient runs synchronous, we might need a small delay or just rely on the fact
    # that background tasks are executed.

    # In Starlette TestClient, background tasks are executed *after* the response is yielded.
    # So immediately after the `client.get` returns, the background task SHOULD have run (synchronously in the same thread usually).
    # But let's check.

    response = client.get("/api/drive/lead/lead-test-1", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "files" in data

    file_names = [f["name"] for f in data["files"]]
    assert "00. Admin" in file_names
    assert "01. Materials" in file_names

def test_adapter_items_lead(client):
    """
    Test the /api/drive/items adapter for leads.
    """
    headers = {"x-user-id": "u1", "x-user-role": "manager"}
    response = client.get("/api/drive/items?entityType=lead&entityId=lead-test-1", headers=headers)

    assert response.status_code == 200, f"Response: {response.text}"
    data = response.json()

    assert "items" in data
    # Should definitely be populated now
    assert len(data["items"]) >= 2
    item_names = [i["name"] for i in data["items"]]
    assert "00. Admin" in item_names

def test_permissions_lead(client):
    """
    Test permissions for Leads.
    """
    # Admin -> Owner (can write)
    headers_admin = {"x-user-id": "u1", "x-user-role": "admin"}
    resp = client.post("/api/drive/lead/lead-test-1/folder", json={"name": "Admin Folder"}, headers=headers_admin)
    assert resp.status_code == 200, f"Response: {resp.text}"

    # Client -> Reader (cannot write)
    headers_client = {"x-user-id": "u2", "x-user-role": "client"}
    resp = client.post("/api/drive/lead/lead-test-1/folder", json={"name": "Client Folder"}, headers=headers_client)
    assert resp.status_code == 403

def test_sync_name_lead(client):
    """
    Test syncing the lead name.
    """
    # 1. Update Lead name in DB
    db = TestingSessionLocal()
    lead = db.query(models.Lead).filter_by(id="lead-test-1").first()
    lead.title = "Renamed Lead"
    db.commit()
    db.close()

    # 2. Call Sync Endpoint
    headers = {"x-user-id": "u1", "x-user-role": "admin"}
    payload = {"entity_type": "lead", "entity_id": "lead-test-1"}
    resp = client.post("/api/drive/sync-name", json=payload, headers=headers)

    assert resp.status_code == 200, f"Response: {resp.text}"
    assert resp.json()["status"] == "synced"

def test_repair_structure_lead(client):
    """
    Test repair endpoint for lead.
    """
    headers = {"x-user-id": "u1", "x-user-role": "admin"}
    resp = client.post("/api/drive/lead/lead-test-1/repair", headers=headers)
    assert resp.status_code == 200, f"Response: {resp.text}"
    assert resp.json()["status"] == "repaired"
