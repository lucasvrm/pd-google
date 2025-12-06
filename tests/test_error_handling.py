
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base
from main import app
import models
import os
import io

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
    
    # Clean up JSON Mock
    if os.path.exists(MOCK_JSON):
        os.remove(MOCK_JSON)

    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    # Create test data
    company = models.Company(id="comp-error-test", name="Error Test Company")
    db.add(company)

    deal = models.Deal(id="deal-error-test", title="Error Test Deal", company_id="comp-error-test")
    db.add(deal)

    lead = models.Lead(id="lead-error-test", title="Error Test Lead", company_id="comp-error-test")
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
    response = client.get("/drive/invalid_type/some-id", headers={"x-user-role": "admin"})
    
    assert response.status_code == 400
    assert response.headers["content-type"] == "application/json"
    
    data = response.json()
    assert "detail" in data
    assert "Invalid entity_type" in data["detail"]
    assert "company" in data["detail"] or "lead" in data["detail"] or "deal" in data["detail"]


def test_contact_entity_type_disabled():
    """Test that 'contact' entity type is properly disabled and returns 400"""
    response = client.get("/drive/contact/some-id", headers={"x-user-role": "admin"})
    
    assert response.status_code == 400
    assert response.headers["content-type"] == "application/json"
    
    data = response.json()
    assert "detail" in data
    assert "Invalid entity_type" in data["detail"]


def test_nonexistent_entity_returns_404():
    """Test that accessing a non-existent entity UUID returns 404"""
    # Use a UUID that doesn't exist in the database
    non_existent_id = "00000000-0000-0000-0000-000000000000"
    
    response = client.get(f"/drive/deal/{non_existent_id}", headers={"x-user-role": "admin"})
    
    # Should return 404 since the deal doesn't exist
    assert response.status_code == 404
    assert response.headers["content-type"] == "application/json"
    
    data = response.json()
    assert "detail" in data
    # The error message should indicate the entity was not found
    assert "not found" in data["detail"].lower()


def test_reader_role_cannot_create_folder():
    """Test that a user with reader role cannot create a folder (403 error)"""
    # First, initialize the structure by calling GET
    response = client.get("/drive/deal/deal-error-test", headers={"x-user-role": "admin"})
    assert response.status_code == 200
    
    # Now try to create a folder with reader role (client role maps to reader)
    response = client.post(
        "/drive/deal/deal-error-test/folder",
        json={"name": "Unauthorized Folder"},
        headers={"x-user-role": "client"}
    )
    
    assert response.status_code == 403
    assert response.headers["content-type"] == "application/json"
    
    data = response.json()
    assert "detail" in data
    assert "permission" in data["detail"].lower()


def test_reader_role_cannot_upload_file():
    """Test that a user with reader role cannot upload files (403 error)"""
    # First, initialize the structure by calling GET
    response = client.get("/drive/lead/lead-error-test", headers={"x-user-role": "admin"})
    assert response.status_code == 200
    
    # Create a fake file for upload
    fake_file = io.BytesIO(b"test file content")
    
    # Try to upload with reader role (customer role maps to reader)
    response = client.post(
        "/drive/lead/lead-error-test/upload",
        files={"file": ("test.txt", fake_file, "text/plain")},
        headers={"x-user-role": "customer"}
    )
    
    assert response.status_code == 403
    assert response.headers["content-type"] == "application/json"
    
    data = response.json()
    assert "detail" in data
    assert "permission" in data["detail"].lower()


def test_error_response_format_consistency():
    """Test that all error responses have consistent JSON format with 'detail' field"""
    # Test various error scenarios and verify they all return consistent format
    
    # 1. Invalid entity type
    response1 = client.get("/drive/invalid/123", headers={"x-user-role": "admin"})
    assert response1.status_code == 400
    data1 = response1.json()
    assert "detail" in data1
    assert isinstance(data1["detail"], str)
    
    # 2. Non-existent entity
    response2 = client.get("/drive/deal/nonexistent-id", headers={"x-user-role": "admin"})
    assert response2.status_code == 404
    data2 = response2.json()
    assert "detail" in data2
    assert isinstance(data2["detail"], str)
    
    # 3. Permission denied
    # First create structure
    client.get("/drive/company/comp-error-test", headers={"x-user-role": "admin"})
    
    # Try to create folder without permission
    response3 = client.post(
        "/drive/company/comp-error-test/folder",
        json={"name": "Test Folder"},
        headers={"x-user-role": "client"}
    )
    assert response3.status_code == 403
    data3 = response3.json()
    assert "detail" in data3
    assert isinstance(data3["detail"], str)
    
    # All responses should be JSON with 'detail' field containing error message
    assert all([
        response1.headers["content-type"] == "application/json",
        response2.headers["content-type"] == "application/json",
        response3.headers["content-type"] == "application/json"
    ])
