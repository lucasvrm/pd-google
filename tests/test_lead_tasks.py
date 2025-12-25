"""
Tests for Lead Tasks endpoints.
"""
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

import models
from main import app


client = TestClient(app)


@pytest.fixture
def db_session():
    """Mock database session for testing."""
    from database import SessionLocal
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def sample_lead(db_session):
    """Create a sample lead for testing."""
    lead = models.Lead(
        id=str(uuid.uuid4()),
        title="Test Lead",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(lead)
    db_session.commit()
    db_session.refresh(lead)
    return lead


@pytest.fixture
def sample_template(db_session):
    """Create a sample template for testing."""
    template = models.LeadTaskTemplate(
        id=str(uuid.uuid4()),
        code="test_template",
        label="Test Template",
        description="Test description",
        is_active=True,
        sort_order=1,
    )
    db_session.add(template)
    db_session.commit()
    db_session.refresh(template)
    return template


@pytest.fixture
def inactive_template(db_session):
    """Create an inactive template for testing."""
    template = models.LeadTaskTemplate(
        id=str(uuid.uuid4()),
        code="inactive_template",
        label="Inactive Template",
        description="Inactive template",
        is_active=False,
        sort_order=2,
    )
    db_session.add(template)
    db_session.commit()
    db_session.refresh(template)
    return template


class TestCreateTaskFromTemplate:
    """Tests for POST /api/leads/{lead_id}/tasks/from-template endpoint."""
    
    def test_create_task_from_template_lead_not_found(self):
        """Test creating task with non-existent lead returns 404."""
        fake_lead_id = str(uuid.uuid4())
        fake_template_id = str(uuid.uuid4())
        
        response = client.post(
            f"/api/leads/{fake_lead_id}/tasks/from-template",
            json={
                "template_id": fake_template_id,
                "is_next_action": False,
            }
        )
        
        assert response.status_code == 404
        assert "não encontrado" in response.json()["detail"].lower()
    
    def test_create_task_from_template_template_not_found(self, sample_lead):
        """Test creating task with non-existent template returns 404."""
        fake_template_id = str(uuid.uuid4())
        
        response = client.post(
            f"/api/leads/{sample_lead.id}/tasks/from-template",
            json={
                "template_id": fake_template_id,
                "is_next_action": False,
            }
        )
        
        assert response.status_code == 404
        assert "template" in response.json()["detail"].lower()
        assert "não encontrado" in response.json()["detail"].lower()
    
    def test_create_task_from_inactive_template(self, sample_lead, inactive_template):
        """Test creating task from inactive template returns 400."""
        response = client.post(
            f"/api/leads/{sample_lead.id}/tasks/from-template",
            json={
                "template_id": inactive_template.id,
                "is_next_action": False,
            }
        )
        
        assert response.status_code == 400
        assert "inativo" in response.json()["detail"].lower()
    
    def test_create_task_from_template_success(self, sample_lead, sample_template):
        """Test successful task creation from template."""
        response = client.post(
            f"/api/leads/{sample_lead.id}/tasks/from-template",
            json={
                "template_id": sample_template.id,
                "is_next_action": False,
            }
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["lead_id"] == sample_lead.id
        assert data["template_id"] == sample_template.id
        assert data["title"] == sample_template.label
        assert data["status"] == "pending"
        assert data["is_next_action"] is False
    
    def test_create_task_from_template_with_next_action(self, sample_lead, sample_template):
        """Test successful task creation from template as next action."""
        response = client.post(
            f"/api/leads/{sample_lead.id}/tasks/from-template",
            json={
                "template_id": sample_template.id,
                "is_next_action": True,
            }
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["is_next_action"] is True


class TestCreateLeadTask:
    """Tests for POST /api/leads/{lead_id}/tasks endpoint."""
    
    def test_create_task_lead_not_found(self):
        """Test creating task with non-existent lead returns 404."""
        fake_lead_id = str(uuid.uuid4())
        
        response = client.post(
            f"/api/leads/{fake_lead_id}/tasks",
            json={
                "title": "Test Task",
                "is_next_action": False,
                "status": "pending",
            }
        )
        
        assert response.status_code == 404
        assert "não encontrado" in response.json()["detail"].lower()
    
    def test_create_task_with_invalid_template_id(self, sample_lead):
        """Test creating task with non-existent template_id returns 404."""
        fake_template_id = str(uuid.uuid4())
        
        response = client.post(
            f"/api/leads/{sample_lead.id}/tasks",
            json={
                "title": "Test Task",
                "template_id": fake_template_id,
                "is_next_action": False,
                "status": "pending",
            }
        )
        
        assert response.status_code == 404
        assert "template" in response.json()["detail"].lower()
    
    def test_create_task_success(self, sample_lead):
        """Test successful task creation."""
        response = client.post(
            f"/api/leads/{sample_lead.id}/tasks",
            json={
                "title": "Test Task",
                "description": "Test description",
                "is_next_action": False,
                "status": "pending",
            }
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["lead_id"] == sample_lead.id
        assert data["title"] == "Test Task"
        assert data["status"] == "pending"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
