
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base
from main import app
import models
import os
import json

# Setup Test DB
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_template_creation.db"
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
    # Company
    company = models.Company(id="comp-template-test", name="Template Test Company")
    db.add(company)

    # Deal
    deal = models.Deal(id="deal-template-test", title="Template Test Deal", company_id="comp-template-test")
    db.add(deal)

    # Lead
    lead = models.Lead(id="lead-template-test", title="Template Test Lead", company_id="comp-template-test")
    db.add(lead)

    db.commit()
    db.close()

def teardown_module(module):
    """Cleanup test database and mock drive files"""
    if os.path.exists("./test_template_creation.db"):
        os.remove("./test_template_creation.db")
    if os.path.exists(MOCK_JSON):
        os.remove(MOCK_JSON)


def test_create_simple_template_structure():
    """Test creating a simple template structure in the database"""
    db = TestingSessionLocal()
    
    # Create a simple template for company with 2 root-level folders
    template = models.DriveStructureTemplate(
        name="Simple Company Template",
        entity_type="company",
        active=True
    )
    db.add(template)
    db.commit()
    db.refresh(template)

    # Add two simple nodes (no nesting)
    node1 = models.DriveStructureNode(
        template_id=template.id,
        name="01. Documents",
        order=0
    )
    db.add(node1)

    node2 = models.DriveStructureNode(
        template_id=template.id,
        name="02. Archive",
        order=1
    )
    db.add(node2)
    
    db.commit()

    # Verify template was created
    saved_template = db.query(models.DriveStructureTemplate).filter_by(
        name="Simple Company Template"
    ).first()
    assert saved_template is not None
    assert saved_template.entity_type == "company"
    assert saved_template.active is True

    # Verify nodes were created
    nodes = db.query(models.DriveStructureNode).filter_by(
        template_id=template.id
    ).order_by(models.DriveStructureNode.order).all()
    
    assert len(nodes) == 2
    assert nodes[0].name == "01. Documents"
    assert nodes[0].parent_id is None
    assert nodes[1].name == "02. Archive"
    assert nodes[1].parent_id is None
    
    db.close()


def test_create_nested_template_structure():
    """Test creating a nested template structure in the database"""
    db = TestingSessionLocal()
    
    # Create a nested template for lead
    template = models.DriveStructureTemplate(
        name="Nested Lead Template",
        entity_type="lead",
        active=True
    )
    db.add(template)
    db.commit()
    db.refresh(template)

    # Add parent node
    parent = models.DriveStructureNode(
        template_id=template.id,
        name="01. Main Folder",
        order=0
    )
    db.add(parent)
    db.commit()
    db.refresh(parent)

    # Add child nodes
    child1 = models.DriveStructureNode(
        template_id=template.id,
        name="01.01 Subfolder A",
        parent_id=parent.id,
        order=0
    )
    db.add(child1)

    child2 = models.DriveStructureNode(
        template_id=template.id,
        name="01.02 Subfolder B",
        parent_id=parent.id,
        order=1
    )
    db.add(child2)
    
    db.commit()

    # Verify template structure
    saved_template = db.query(models.DriveStructureTemplate).filter_by(
        name="Nested Lead Template"
    ).first()
    assert saved_template is not None
    assert saved_template.entity_type == "lead"

    # Verify parent node
    parent_nodes = db.query(models.DriveStructureNode).filter_by(
        template_id=template.id,
        parent_id=None
    ).all()
    assert len(parent_nodes) == 1
    assert parent_nodes[0].name == "01. Main Folder"

    # Verify child nodes
    child_nodes = db.query(models.DriveStructureNode).filter_by(
        template_id=template.id,
        parent_id=parent.id
    ).order_by(models.DriveStructureNode.order).all()
    
    assert len(child_nodes) == 2
    assert child_nodes[0].name == "01.01 Subfolder A"
    assert child_nodes[1].name == "01.02 Subfolder B"
    
    db.close()


def test_template_application_on_deal_creation():
    """Test that GET /drive/deal/{id} triggers template application and folder creation in Mock Drive"""
    db = TestingSessionLocal()
    
    # Create a template for deals
    template = models.DriveStructureTemplate(
        name="Deal Application Template",
        entity_type="deal",
        active=True
    )
    db.add(template)
    db.commit()
    db.refresh(template)

    # Add template nodes
    node1 = models.DriveStructureNode(
        template_id=template.id,
        name="00. Admin",
        order=0
    )
    db.add(node1)
    db.commit()
    db.refresh(node1)

    node2 = models.DriveStructureNode(
        template_id=template.id,
        name="01. Documentation",
        order=1
    )
    db.add(node2)
    db.commit()
    db.refresh(node2)

    # Add a nested folder
    child = models.DriveStructureNode(
        template_id=template.id,
        name="01.01 Contracts",
        parent_id=node2.id,
        order=0
    )
    db.add(child)
    db.commit()

    db.close()

    # Trigger structure creation by calling the endpoint
    response = client.get("/drive/deal/deal-template-test", headers={"x-user-role": "admin"})
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    
    data = response.json()
    assert "files" in data
    assert "permission" in data
    assert data["permission"] == "owner"  # admin role should get owner permission

    files = data["files"]
    
    # Verify that template folders were created
    folder_names = [f["name"] for f in files]
    assert "00. Admin" in folder_names, f"Expected '00. Admin' in {folder_names}"
    assert "01. Documentation" in folder_names, f"Expected '01. Documentation' in {folder_names}"

    # Verify nesting by checking the mock drive database directly
    with open(MOCK_JSON, "r") as f:
        mock_db = json.load(f)

    # Find the "01. Documentation" folder
    doc_folder = next((f for f in files if f["name"] == "01. Documentation"), None)
    assert doc_folder is not None, "Could not find '01. Documentation' folder"
    doc_folder_id = doc_folder["id"]

    # Verify the nested "01.01 Contracts" folder exists inside "01. Documentation"
    child_found = False
    for folder_id, folder in mock_db["folders"].items():
        if folder["name"] == "01.01 Contracts" and doc_folder_id in folder["parents"]:
            child_found = True
            break

    assert child_found, "Nested folder '01.01 Contracts' was not found inside '01. Documentation'"
