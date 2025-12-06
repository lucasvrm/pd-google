
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base
from main import app
import models
import os
import json
from routers.drive import get_db

# Setup Test DB
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_template.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


client = None  # Will be set in setup_module

MOCK_JSON = "mock_drive_db.json"

def setup_module(module):
    # Override dependency for this module
    app.dependency_overrides[get_db] = override_get_db
    
    # Clean up JSON Mock
    if os.path.exists(MOCK_JSON):
        os.remove(MOCK_JSON)

    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    # Create a Deal Template with nested structure
    # Root: "01. Phase 1"
    #   Child: "01.01 Step A"

    tmpl = models.DriveStructureTemplate(name="Nested Deal Tmpl", entity_type="deal", active=True)
    db.add(tmpl)
    db.commit()

    parent = models.DriveStructureNode(template_id=tmpl.id, name="01. Phase 1", order=0)
    db.add(parent)
    db.commit()

    child = models.DriveStructureNode(template_id=tmpl.id, name="01.01 Step A", parent_id=parent.id, order=0)
    db.add(child)

    # Mock Deal & Company
    comp = models.Company(id="c1", name="C1")
    db.add(comp)
    deal = models.Deal(id="d1", title="D1", company_id="c1")
    db.add(deal)

    db.commit()
    db.close()
    
    # Create TestClient after override is in place
    global client
    client = TestClient(app)

def teardown_module(module):
    # Reset overrides
    if get_db in app.dependency_overrides:
        del app.dependency_overrides[get_db]
    
    if os.path.exists("./test_template.db"):
        os.remove("./test_template.db")
    if os.path.exists(MOCK_JSON):
        os.remove(MOCK_JSON)

def test_template_recursion():
    # Calling GET /drive/deal/d1 should trigger creation

    response = client.get("/drive/deal/d1", headers={"x-user-role": "admin"})
    assert response.status_code == 200, response.text
    data = response.json()
    files = data["files"]
    print(f"DEBUG: Files returned: {json.dumps(files, indent=2)}")

    # Verify Parent Exists
    parent_folder = next((f for f in files if f["name"] == "01. Phase 1"), None)
    assert parent_folder is not None

    # Now verify the child exists inside the parent
    # We need to manually check the mock DB because the API doesn't expose a 'search' or deep list
    with open(MOCK_JSON, "r") as f:
        mock_db = json.load(f)

    parent_id = parent_folder["id"]

    # Look for folder with parent_id = parent_id and name = "01.01 Step A"
    child_found = False
    for fid, folder in mock_db["folders"].items():
        if folder["name"] == "01.01 Step A" and parent_id in folder["parents"]:
            child_found = True
            break

    assert child_found, "Child folder '01.01 Step A' was not found inside '01. Phase 1'"
