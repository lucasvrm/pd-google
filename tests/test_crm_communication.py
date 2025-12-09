"""
Tests for CRM Communication API endpoints
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timedelta
import json

# Import app and dependencies
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app
from database import Base
from routers.crm_communication import get_db, get_gmail_service, get_contact_service
import models


# Setup test database
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_crm_communication.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


# Mock Gmail Service
class MockGmailService:
    def __init__(self):
        self.messages = self._create_test_messages()
    
    def _create_test_messages(self):
        """Create test messages for different scenarios"""
        return {
            'msg1': {
                'id': 'msg1',
                'threadId': 'thread1',
                'snippet': 'Test message from client',
                'internalDate': str(int(datetime.now().timestamp() * 1000)),
                'payload': {
                    'headers': [
                        {'name': 'Subject', 'value': 'Test Subject'},
                        {'name': 'From', 'value': 'client@company.com'},
                        {'name': 'To', 'value': 'sales@ourcompany.com'},
                    ],
                    'parts': []
                }
            },
            'msg2': {
                'id': 'msg2',
                'threadId': 'thread2',
                'snippet': 'Another test message',
                'internalDate': str(int((datetime.now() - timedelta(days=1)).timestamp() * 1000)),
                'payload': {
                    'headers': [
                        {'name': 'Subject', 'value': 'Follow up'},
                        {'name': 'From', 'value': 'sales@ourcompany.com'},
                        {'name': 'To', 'value': 'client@company.com'},
                        {'name': 'Cc', 'value': 'ceo@company.com'},
                    ],
                    'parts': []
                }
            }
        }
    
    def list_messages(self, query=None, label_ids=None, max_results=100, page_token=None):
        """Mock list messages - return messages that match the query"""
        messages = []
        
        # Simple query parsing for testing
        if query and 'client@company.com' in query:
            messages = [{'id': 'msg1'}, {'id': 'msg2'}]
        
        return {
            'messages': messages,
            'resultSizeEstimate': len(messages)
        }
    
    def get_message(self, message_id, format='full'):
        """Mock get message"""
        return self.messages.get(message_id, {})
    
    def _parse_headers(self, headers):
        """Parse headers list into dict"""
        result = {}
        for header in headers:
            name = header.get('name', '').lower()
            value = header.get('value', '')
            result[name] = value
        return result
    
    def _extract_attachments(self, payload):
        """Mock extract attachments"""
        return []


def override_get_gmail_service():
    return MockGmailService()


# Mock Contact Service
class MockContactService:
    def __init__(self, db):
        self.db = db
    
    def get_entity_contact_emails(self, entity_type, entity_id):
        """Return predefined contact emails for testing"""
        if entity_type == 'company' and entity_id == 'comp-test':
            return ['client@company.com', 'ceo@company.com']
        elif entity_type == 'lead' and entity_id == 'lead-test':
            return ['lead@example.com']
        elif entity_type == 'deal' and entity_id == 'deal-test':
            return ['deal@example.com']
        return []


def override_get_contact_service(db=None):
    return MockContactService(db)


# Apply overrides
app.dependency_overrides[get_db] = override_get_db
app.dependency_overrides[get_gmail_service] = override_get_gmail_service
app.dependency_overrides[get_contact_service] = override_get_contact_service


@pytest.fixture(scope="module")
def test_client():
    # Create tables
    Base.metadata.create_all(bind=engine)
    
    # Seed test data
    db = TestingSessionLocal()
    
    # Add test company
    company = models.Company(id='comp-test', name='Test Company')
    db.add(company)
    
    # Add test lead
    lead = models.Lead(id='lead-test', title='Test Lead')
    db.add(lead)
    
    # Add test deal
    deal = models.Deal(id='deal-test', title='Test Deal')
    db.add(deal)
    
    # Add test calendar events
    event1 = models.CalendarEvent(
        google_event_id='event1',
        summary='Test Meeting',
        start_time=datetime.now(),
        end_time=datetime.now() + timedelta(hours=1),
        status='confirmed',
        attendees=json.dumps([
            {'email': 'client@company.com', 'responseStatus': 'accepted'}
        ])
    )
    db.add(event1)
    
    event2 = models.CalendarEvent(
        google_event_id='event2',
        summary='Another Meeting',
        start_time=datetime.now() + timedelta(days=1),
        end_time=datetime.now() + timedelta(days=1, hours=1),
        status='confirmed',
        attendees=json.dumps([
            {'email': 'ceo@company.com', 'responseStatus': 'tentative'},
            {'email': 'other@example.com', 'responseStatus': 'accepted'}
        ])
    )
    db.add(event2)
    
    db.commit()
    db.close()
    
    client = TestClient(app)
    yield client
    
    # Cleanup
    Base.metadata.drop_all(bind=engine)
    try:
        os.remove("./test_crm_communication.db")
    except:
        pass


class TestCRMCommunicationEndpoints:
    
    def test_get_company_emails_success(self, test_client):
        """Test getting emails for a company"""
        response = test_client.get("/api/crm/company/comp-test/emails")
        assert response.status_code == 200
        data = response.json()
        
        assert 'emails' in data
        assert 'total' in data
        assert 'limit' in data
        assert 'offset' in data
        assert isinstance(data['emails'], list)
    
    def test_get_company_emails_with_pagination(self, test_client):
        """Test pagination parameters"""
        response = test_client.get("/api/crm/company/comp-test/emails?limit=10&offset=0")
        assert response.status_code == 200
        data = response.json()
        
        assert data['limit'] == 10
        assert data['offset'] == 0
    
    def test_get_company_events_success(self, test_client):
        """Test getting events for a company"""
        response = test_client.get("/api/crm/company/comp-test/events")
        assert response.status_code == 200
        data = response.json()
        
        assert 'events' in data
        assert 'total' in data
        assert data['total'] >= 0
        
        # Check if events contain matched_contacts field
        if data['events']:
            assert 'matched_contacts' in data['events'][0]
    
    def test_get_lead_events_success(self, test_client):
        """Test getting events for a lead"""
        response = test_client.get("/api/crm/lead/lead-test/events")
        assert response.status_code == 200
        data = response.json()
        assert 'events' in data
    
    def test_invalid_entity_type(self, test_client):
        """Test with invalid entity type"""
        response = test_client.get("/api/crm/invalid/test-id/emails")
        # FastAPI returns 422 for invalid Literal values (Pydantic validation)
        assert response.status_code == 422
        # The error detail is in a different format for validation errors
        assert 'detail' in response.json()
    
    def test_entity_not_found(self, test_client):
        """Test with non-existent entity"""
        response = test_client.get("/api/crm/company/nonexistent/emails")
        assert response.status_code == 404
        assert 'not found' in response.json()['detail']
    
    def test_events_with_status_filter(self, test_client):
        """Test filtering events by status"""
        response = test_client.get("/api/crm/company/comp-test/events?status=confirmed")
        assert response.status_code == 200
        data = response.json()
        
        # All returned events should have status='confirmed'
        for event in data['events']:
            assert event['status'] == 'confirmed'
    
    def test_emails_with_date_filter(self, test_client):
        """Test filtering emails by date"""
        response = test_client.get("/api/crm/company/comp-test/emails?time_min=2024-01-01")
        assert response.status_code == 200
        # Should not raise an error
    
    def test_response_schema_emails(self, test_client):
        """Test that email response matches schema"""
        response = test_client.get("/api/crm/company/comp-test/emails")
        assert response.status_code == 200
        data = response.json()
        
        # Check response structure
        required_fields = ['emails', 'total', 'limit', 'offset']
        for field in required_fields:
            assert field in data
        
        # Check email object structure if emails exist
        if data['emails']:
            email = data['emails'][0]
            email_fields = ['id', 'thread_id', 'subject', 'matched_contacts']
            for field in email_fields:
                assert field in email
    
    def test_response_schema_events(self, test_client):
        """Test that event response matches schema"""
        response = test_client.get("/api/crm/company/comp-test/events")
        assert response.status_code == 200
        data = response.json()
        
        # Check response structure
        required_fields = ['events', 'total', 'limit', 'offset']
        for field in required_fields:
            assert field in data
        
        # Check event object structure if events exist
        if data['events']:
            event = data['events'][0]
            event_fields = ['id', 'google_event_id', 'summary', 'start_time', 'end_time', 'matched_contacts']
            for field in event_fields:
                assert field in event


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
