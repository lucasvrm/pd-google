
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base
from main import app
import models
import os
import io
from config import config

# Setup Test DB
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_error_handling.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

from routers.drive import get_db
app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)

MOCK_JSON = "mock_drive_db.json"

def setup_module(module):
    """Setup test database and mock drive environment"""
    # Set environment variable for mock drive
    os.environ["USE_MOCK_DRIVE"] = "true"
    os.environ["DRIVE_ROOT_FOLDER_ID"] = "mock-root-id"
    config.USE_MOCK_DRIVE = True
    config.DRIVE_ROOT_FOLDER_ID = os.environ["DRIVE_ROOT_FOLDER_ID"]

    # Clean up JSON Mock
    if os.path.exists(MOCK_JSON):
        os.remove(MOCK_JSON)

    if os.path.exists("./test_error_handling.db"):
        os.remove("./test_error_handling.db")

    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    # Create test data
    company = models.Company(id="comp-error-test", name="Error Test Company")
    db.add(company)

    deal = models.Deal(id="deal-error-test", title="Error Test Deal", company_id="comp-error-test")
    db.add(deal)

    lead = models.Lead(id="lead-error-test", title="Error Test Lead", qualified_company_id="comp-error-test")
    db.add(lead)

    db.commit()
    db.close()

def teardown_module(module):
    """Cleanup test database and mock drive files"""
    if os.path.exists("./test_error_handling.db"):
        os.remove("./test_error_handling.db")
    if os.path.exists(MOCK_JSON):
        os.remove(MOCK_JSON)


def test_invalid_entity_type():
    """Test that accessing /drive with an invalid entity_type returns 400 with proper error message"""
    # Test with completely invalid entity type
    response = client.get("/api/drive/invalid_type/some-id", headers={"x-user-role": "admin", "x-user-id": "test_user"})
    
    assert response.status_code == 400
    assert response.headers["content-type"] == "application/json"

    data = response.json()
    assert data["code"] == "bad_request"
    assert "Invalid entity_type" in data["message"]
    assert "company" in data["message"] or "lead" in data["message"] or "deal" in data["message"]


def test_contact_entity_type_disabled():
    """Test that 'contact' entity type is properly disabled and returns 400"""
    response = client.get("/api/drive/contact/some-id", headers={"x-user-role": "admin", "x-user-id": "test_user"})
    
    assert response.status_code == 400
    assert response.headers["content-type"] == "application/json"

    data = response.json()
    assert data["code"] == "bad_request"
    assert "Invalid entity_type" in data["message"]


def test_nonexistent_entity_returns_404():
    """Test that accessing a non-existent entity UUID returns 404"""
    # Use a UUID that doesn't exist in the database
    non_existent_id = "00000000-0000-0000-0000-000000000000"
    
    response = client.get(f"/api/drive/deal/{non_existent_id}", headers={"x-user-role": "admin", "x-user-id": "test_user"})
    
    # Should return 404 since the deal doesn't exist
    assert response.status_code == 404
    assert response.headers["content-type"] == "application/json"

    data = response.json()
    assert data["code"] == "not_found"
    # The error message should indicate the entity was not found
    assert "not found" in data["message"].lower()


def test_reader_role_cannot_create_folder():
    """Test that a user with reader role cannot create a folder (403 error)"""
    # First, initialize the structure by calling GET
    response = client.get("/api/drive/deal/deal-error-test", headers={"x-user-role": "admin", "x-user-id": "test_user"})
    assert response.status_code == 200
    
    # Now try to create a folder with reader role (client role maps to reader)
    response = client.post(
        "/api/drive/deal/deal-error-test/folder",
        json={"name": "Unauthorized Folder"},
        headers={"x-user-role": "client", "x-user-id": "test_user"}
    )
    
    assert response.status_code == 403
    assert response.headers["content-type"] == "application/json"

    data = response.json()
    assert data["code"] == "forbidden"
    assert "permission" in data["message"].lower()


def test_reader_role_cannot_upload_file():
    """Test that a user with reader role cannot upload files (403 error)"""
    # First, initialize the structure by calling GET
    response = client.get("/api/drive/lead/lead-error-test", headers={"x-user-role": "admin", "x-user-id": "test_user"})
    assert response.status_code == 200
    
    # Create a fake file for upload
    fake_file = io.BytesIO(b"test file content")

    # Try to upload with reader role (customer role maps to reader)
    response = client.post(
        "/api/drive/lead/lead-error-test/upload",
        files={"file": ("test.txt", fake_file, "text/plain")},
        headers={"x-user-role": "customer", "x-user-id": "test_user"}
    )
    
    assert response.status_code == 403
    assert response.headers["content-type"] == "application/json"

    data = response.json()
    assert data["code"] == "forbidden"
    assert "permission" in data["message"].lower()


def test_error_response_format_consistency():
    """Test that all error responses have consistent JSON format with 'detail' field"""
    # Test various error scenarios and verify they all return consistent format
    
    # 1. Invalid entity type
    response1 = client.get("/api/drive/invalid/123", headers={"x-user-role": "admin", "x-user-id": "test_user"})
    assert response1.status_code == 400
    data1 = response1.json()
    assert data1["code"] == "bad_request"
    assert isinstance(data1["message"], str)
    
    # 2. Non-existent entity
    response2 = client.get("/api/drive/deal/nonexistent-id", headers={"x-user-role": "admin", "x-user-id": "test_user"})
    assert response2.status_code == 404
    data2 = response2.json()
    assert data2["code"] == "not_found"
    assert isinstance(data2["message"], str)
    
    # 3. Permission denied
    # First create structure
    client.get("/api/drive/company/comp-error-test", headers={"x-user-role": "admin", "x-user-id": "test_user"})
    
    # Try to create folder without permission
    response3 = client.post(
        "/api/drive/company/comp-error-test/folder",
        json={"name": "Test Folder"},
        headers={"x-user-role": "client", "x-user-id": "test_user"}
    )
    assert response3.status_code == 403
    data3 = response3.json()
    assert data3["code"] == "forbidden"
    assert isinstance(data3["message"], str)

    # All responses should be JSON with error envelope containing error message
    assert all([
        response1.headers["content-type"] == "application/json",
        response2.headers["content-type"] == "application/json",
        response3.headers["content-type"] == "application/json"
    ])
