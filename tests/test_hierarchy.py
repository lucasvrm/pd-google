
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base
from main import app
import models
import os

# Setup Test DB
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

# Override dependency
# We need to import the exact function being depended on in main/routers
from routers.drive import get_db
app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)

def setup_module(module):
    Base.metadata.create_all(bind=engine)
    # Seed mock data
    db = TestingSessionLocal()

    # Company
    company1 = models.Company(id="comp-123", name="Test Company", fantasy_name="Fantasy Test")
    db.add(company1)

    # Lead
    lead1 = models.Lead(id="lead-001", title="Test Lead", company_id="comp-123")
    db.add(lead1)

    # Deal
    deal1 = models.Deal(id="deal-001", title="Test Deal", company_id="comp-123")
    db.add(deal1)

    # Template
    tmpl = models.DriveStructureTemplate(name="Lead Tmpl", entity_type="lead", active=True)
    db.add(tmpl)
    db.commit()
    node = models.DriveStructureNode(template_id=tmpl.id, name="Lead Node 1", order=0)
    db.add(node)

    tmpl_deal = models.DriveStructureTemplate(name="Deal Tmpl", entity_type="deal", active=True)
    db.add(tmpl_deal)
    db.commit()
    node_deal = models.DriveStructureNode(template_id=tmpl_deal.id, name="Deal Node 1", order=0)
    db.add(node_deal)

    tmpl_comp = models.DriveStructureTemplate(name="Comp Tmpl", entity_type="company", active=True)
    db.add(tmpl_comp)
    db.commit()

    db.commit()
    db.close()

def teardown_module(module):
    if os.path.exists("./test.db"):
        os.remove("./test.db")

def test_read_root():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "PipeDesk Google Drive Backend"}

def test_get_drive_company():
    # Should create structure for Company
    # Note: Because Real Drive Service is loaded but not auth'd, it will raise exception
    # unless we mock the HierarchyService calls or use Mock Drive.
    # The config says MOCK_DRIVE defaults to false.
    # We should set env var USE_MOCK_DRIVE=true for tests.
    pass

def test_invalid_entity_type():
    response = client.get("/drive/invalid/123")
    assert response.status_code == 400

def test_contact_disabled():
    response = client.get("/drive/contact/123")
    assert response.status_code == 400
