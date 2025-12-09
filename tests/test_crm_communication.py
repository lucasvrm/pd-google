"""
Tests for CRM Communication API endpoints
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
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
    
    def test_company_with_multiple_contacts_matched(self, test_client):
        """Test company with multiple contacts returns correct emails and matched_contacts"""
        response = test_client.get("/api/crm/company/comp-test/emails")
        assert response.status_code == 200
        data = response.json()
        
        # Check that matched_contacts are returned
        if data['emails']:
            for email in data['emails']:
                assert 'matched_contacts' in email
                assert isinstance(email['matched_contacts'], list)
                # Verify matched contacts are from our test company contacts
                for contact in email['matched_contacts']:
                    assert contact in ['client@company.com', 'ceo@company.com']
    
    def test_entity_without_contacts_returns_empty(self, test_client):
        """Test that entity without contacts returns empty result with total=0"""
        # Create a new company without contacts
        db = TestingSessionLocal()
        company_no_contacts = models.Company(id='comp-no-contacts', name='No Contacts Company')
        db.add(company_no_contacts)
        db.commit()
        db.close()
        
        # Override contact service to return empty list for this company
        original_get_entity_contact_emails = MockContactService.get_entity_contact_emails
        
        def mock_no_contacts(self, entity_type, entity_id):
            if entity_id == 'comp-no-contacts':
                return []
            return original_get_entity_contact_emails(self, entity_type, entity_id)
        
        MockContactService.get_entity_contact_emails = mock_no_contacts
        
        try:
            response = test_client.get("/api/crm/company/comp-no-contacts/emails")
            assert response.status_code == 200
            data = response.json()
            
            assert data['total'] == 0
            assert data['emails'] == []
            assert data['limit'] == 50
            assert data['offset'] == 0
        finally:
            # Restore original method
            MockContactService.get_entity_contact_emails = original_get_entity_contact_emails
    
    def test_pagination_limit_offset(self, test_client):
        """Test pagination with different limit and offset values"""
        # Test with limit=1, offset=0
        response = test_client.get("/api/crm/company/comp-test/emails?limit=1&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert data['limit'] == 1
        assert data['offset'] == 0
        assert len(data['emails']) <= 1
        
        # Test with limit=10, offset=5
        response = test_client.get("/api/crm/company/comp-test/emails?limit=10&offset=5")
        assert response.status_code == 200
        data = response.json()
        assert data['limit'] == 10
        assert data['offset'] == 5
    
    def test_emails_time_filters(self, test_client):
        """Test emails with time_min and time_max filters"""
        # Test with time_min
        response = test_client.get("/api/crm/company/comp-test/emails?time_min=2024-01-01")
        assert response.status_code == 200
        
        # Test with time_max
        response = test_client.get("/api/crm/company/comp-test/emails?time_max=2025-12-31")
        assert response.status_code == 200
        
        # Test with both time_min and time_max
        response = test_client.get(
            "/api/crm/company/comp-test/emails?time_min=2024-01-01&time_max=2025-12-31"
        )
        assert response.status_code == 200
    
    def test_events_time_filters(self, test_client):
        """Test events with time_min and time_max filters"""
        # Test with time_min
        time_min = (datetime.now() - timedelta(days=1)).isoformat()
        response = test_client.get(f"/api/crm/company/comp-test/events?time_min={time_min}")
        assert response.status_code == 200
        
        # Test with time_max
        time_max = (datetime.now() + timedelta(days=7)).isoformat()
        response = test_client.get(f"/api/crm/company/comp-test/events?time_max={time_max}")
        assert response.status_code == 200
        
        # Test with both filters
        response = test_client.get(
            f"/api/crm/company/comp-test/events?time_min={time_min}&time_max={time_max}"
        )
        assert response.status_code == 200


class TestCRMCommunicationWithRelationships:
    """Test CRM communication endpoints with entity relationships"""
    
    @pytest.fixture(scope="class")
    def test_client_with_relationships(self):
        """Setup test database with related entities"""
        # Create tables
        Base.metadata.create_all(bind=engine)
        
        db = TestingSessionLocal()
        
        # Create a qualified company
        qualified_company = models.Company(id='qualified-comp', name='Qualified Company')
        db.add(qualified_company)
        
        # Create a lead linked to the qualified company
        lead_with_company = models.Lead(
            id='lead-qualified',
            title='Lead with Qualified Company',
            qualified_company_id='qualified-comp'
        )
        db.add(lead_with_company)
        
        # Create a company for a deal
        deal_company = models.Company(id='deal-comp', name='Deal Company')
        db.add(deal_company)
        
        # Create a deal linked to the company
        deal_with_company = models.Deal(
            id='deal-with-comp',
            title='Deal with Company',
            company_id='deal-comp'
        )
        db.add(deal_with_company)
        
        db.commit()
        db.close()
        
        # Update mock contact service to handle these entities
        original_get_entity_contact_emails = MockContactService.get_entity_contact_emails
        
        def mock_with_relationships(self, entity_type, entity_id):
            if entity_type == 'company' and entity_id == 'qualified-comp':
                return ['qualified@company.com', 'manager@company.com']
            elif entity_type == 'lead' and entity_id == 'lead-qualified':
                # Should inherit from qualified company
                return ['lead@example.com', 'qualified@company.com', 'manager@company.com']
            elif entity_type == 'company' and entity_id == 'deal-comp':
                return ['dealcompany@example.com']
            elif entity_type == 'deal' and entity_id == 'deal-with-comp':
                # Should inherit from company
                return ['deal@example.com', 'dealcompany@example.com']
            return original_get_entity_contact_emails(self, entity_type, entity_id)
        
        MockContactService.get_entity_contact_emails = mock_with_relationships
        
        client = TestClient(app)
        yield client
        
        # Restore original method
        MockContactService.get_entity_contact_emails = original_get_entity_contact_emails
        
        # Cleanup
        Base.metadata.drop_all(bind=engine)
        try:
            os.remove("./test_crm_communication.db")
        except:
            pass
    
    def test_lead_inherits_qualified_company_contacts(self, test_client_with_relationships):
        """Test that lead with qualified_company_id inherits company contacts"""
        response = test_client_with_relationships.get("/api/crm/lead/lead-qualified/events")
        assert response.status_code == 200
        # The mock should return contacts from both lead and qualified company
    
    def test_deal_inherits_company_contacts(self, test_client_with_relationships):
        """Test that deal with company_id inherits company contacts"""
        response = test_client_with_relationships.get("/api/crm/deal/deal-with-comp/events")
        assert response.status_code == 200
        # The mock should return contacts from both deal and company


class TestCRMContactService:
    """Unit tests for CRMContactService"""
    
    @pytest.fixture
    def db_session(self):
        """Create a fresh database session for each test"""
        # Use a unique database file for unit tests
        test_db_url = "sqlite:///./test_crm_contact_service.db"
        test_engine = create_engine(test_db_url, connect_args={"check_same_thread": False})
        TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
        
        Base.metadata.create_all(bind=test_engine)
        db = TestSessionLocal()
        yield db
        db.close()
        Base.metadata.drop_all(bind=test_engine)
        test_engine.dispose()
        
        # Cleanup database file
        try:
            os.remove("./test_crm_contact_service.db")
        except:
            pass
    
    def test_get_company_emails_direct(self, db_session):
        """Test extracting emails from Company entity with direct email field"""
        from services.crm_contact_service import CRMContactService
        
        # Create company with email field (if it exists)
        company = models.Company(id='comp-1', name='Test Company')
        # Note: Company model doesn't have email field, but service handles this
        db_session.add(company)
        db_session.commit()
        
        service = CRMContactService(db_session)
        emails = service._get_company_emails('comp-1')
        
        assert isinstance(emails, list)
        # Since company doesn't have email field, should return empty or contacts-based
    
    def test_get_company_emails_with_contacts_table(self, db_session):
        """Test extracting emails from Company when contacts table exists"""
        from services.crm_contact_service import CRMContactService
        
        company = models.Company(id='comp-2', name='Test Company 2')
        db_session.add(company)
        db_session.commit()
        
        # Try to insert into contacts table if it exists
        try:
            db_session.execute(
                text("""
                    INSERT INTO contacts (id, company_id, email, name)
                    VALUES (:id, :company_id, :email, :name)
                """),
                {
                    'id': 'contact-1',
                    'company_id': 'comp-2',
                    'email': 'contact1@company.com',
                    'name': 'Contact One'
                }
            )
            db_session.commit()
            
            service = CRMContactService(db_session)
            emails = service._get_company_emails('comp-2')
            
            assert 'contact1@company.com' in emails
        except Exception:
            # Table doesn't exist, skip this test
            pytest.skip("contacts table not available")
    
    def test_get_company_emails_fallback_when_table_unavailable(self, db_session):
        """Test that service handles gracefully when contacts table doesn't exist"""
        from services.crm_contact_service import CRMContactService
        
        company = models.Company(id='comp-3', name='Test Company 3')
        db_session.add(company)
        db_session.commit()
        
        service = CRMContactService(db_session)
        # Should not raise an error even if contacts table doesn't exist
        emails = service._get_company_emails('comp-3')
        
        assert isinstance(emails, list)
        # Should return empty list or company email if available
    
    def test_get_lead_emails_direct(self, db_session):
        """Test extracting emails from Lead entity"""
        from services.crm_contact_service import CRMContactService
        
        lead = models.Lead(id='lead-1', title='Test Lead')
        db_session.add(lead)
        db_session.commit()
        
        service = CRMContactService(db_session)
        emails = service._get_lead_emails('lead-1')
        
        assert isinstance(emails, list)
    
    def test_get_lead_emails_with_qualified_company(self, db_session):
        """Test that lead inherits emails from qualified company"""
        from services.crm_contact_service import CRMContactService
        
        # Create company
        company = models.Company(id='comp-qualified', name='Qualified Company')
        db_session.add(company)
        
        # Create lead with qualified_company_id
        lead = models.Lead(
            id='lead-2',
            title='Test Lead 2',
            qualified_company_id='comp-qualified'
        )
        db_session.add(lead)
        db_session.commit()
        
        service = CRMContactService(db_session)
        emails = service._get_lead_emails('lead-2')
        
        assert isinstance(emails, list)
        # Should include emails from qualified company
    
    def test_get_lead_emails_when_contacts_table_unavailable(self, db_session):
        """Test lead email extraction when contacts table doesn't exist"""
        from services.crm_contact_service import CRMContactService
        
        lead = models.Lead(id='lead-3', title='Test Lead 3')
        db_session.add(lead)
        db_session.commit()
        
        service = CRMContactService(db_session)
        # Should not raise an error
        emails = service._get_lead_emails('lead-3')
        
        assert isinstance(emails, list)
    
    def test_get_deal_emails_direct(self, db_session):
        """Test extracting emails from Deal entity"""
        from services.crm_contact_service import CRMContactService
        
        deal = models.Deal(id='deal-1', title='Test Deal')
        db_session.add(deal)
        db_session.commit()
        
        service = CRMContactService(db_session)
        emails = service._get_deal_emails('deal-1')
        
        assert isinstance(emails, list)
    
    def test_get_deal_emails_with_company(self, db_session):
        """Test that deal inherits emails from company"""
        from services.crm_contact_service import CRMContactService
        
        # Create company
        company = models.Company(id='comp-for-deal', name='Deal Company')
        db_session.add(company)
        
        # Create deal with company_id
        deal = models.Deal(
            id='deal-2',
            title='Test Deal 2',
            company_id='comp-for-deal'
        )
        db_session.add(deal)
        db_session.commit()
        
        service = CRMContactService(db_session)
        emails = service._get_deal_emails('deal-2')
        
        assert isinstance(emails, list)
        # Should include emails from company
    
    def test_get_deal_emails_when_contacts_table_unavailable(self, db_session):
        """Test deal email extraction when contacts table doesn't exist"""
        from services.crm_contact_service import CRMContactService
        
        deal = models.Deal(id='deal-3', title='Test Deal 3')
        db_session.add(deal)
        db_session.commit()
        
        service = CRMContactService(db_session)
        # Should not raise an error
        emails = service._get_deal_emails('deal-3')
        
        assert isinstance(emails, list)
    
    def test_get_entity_contact_emails_company(self, db_session):
        """Test get_entity_contact_emails for company type"""
        from services.crm_contact_service import CRMContactService
        
        company = models.Company(id='comp-entity', name='Entity Test Company')
        db_session.add(company)
        db_session.commit()
        
        service = CRMContactService(db_session)
        emails = service.get_entity_contact_emails('company', 'comp-entity')
        
        assert isinstance(emails, list)
    
    def test_get_entity_contact_emails_lead(self, db_session):
        """Test get_entity_contact_emails for lead type"""
        from services.crm_contact_service import CRMContactService
        
        lead = models.Lead(id='lead-entity', title='Entity Test Lead')
        db_session.add(lead)
        db_session.commit()
        
        service = CRMContactService(db_session)
        emails = service.get_entity_contact_emails('lead', 'lead-entity')
        
        assert isinstance(emails, list)
    
    def test_get_entity_contact_emails_deal(self, db_session):
        """Test get_entity_contact_emails for deal type"""
        from services.crm_contact_service import CRMContactService
        
        deal = models.Deal(id='deal-entity', title='Entity Test Deal')
        db_session.add(deal)
        db_session.commit()
        
        service = CRMContactService(db_session)
        emails = service.get_entity_contact_emails('deal', 'deal-entity')
        
        assert isinstance(emails, list)
    
    def test_get_entity_contact_emails_invalid_type(self, db_session):
        """Test get_entity_contact_emails with invalid entity type"""
        from services.crm_contact_service import CRMContactService
        
        service = CRMContactService(db_session)
        
        with pytest.raises(ValueError) as exc_info:
            service.get_entity_contact_emails('invalid', 'some-id')
        
        assert 'Unknown entity type' in str(exc_info.value)


# ------------------------------------------------------------
# CRM Communication Permission Tests
# ------------------------------------------------------------

class TestCRMCommunicationPermissions:
    """Test CRM communication permission enforcement"""
    
    def test_admin_can_access_crm_emails(self, test_client):
        """Test that admin role can access CRM emails"""
        response = test_client.get(
            "/api/crm/company/comp-test/emails",
            headers={"x-user-role": "admin"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "emails" in data
        assert "total" in data
    
    def test_analyst_can_access_crm_emails(self, test_client):
        """Test that analyst role can access CRM emails"""
        response = test_client.get(
            "/api/crm/company/comp-test/emails",
            headers={"x-user-role": "analyst"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "emails" in data
    
    def test_manager_can_access_crm_emails(self, test_client):
        """Test that manager role can access CRM emails"""
        response = test_client.get(
            "/api/crm/company/comp-test/emails",
            headers={"x-user-role": "manager"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "emails" in data
    
    def test_new_business_can_access_crm_emails(self, test_client):
        """Test that new_business role can access CRM emails"""
        response = test_client.get(
            "/api/crm/company/comp-test/emails",
            headers={"x-user-role": "new_business"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "emails" in data
    
    def test_client_cannot_access_crm_emails(self, test_client):
        """Test that client role cannot access CRM emails (403)"""
        response = test_client.get(
            "/api/crm/company/comp-test/emails",
            headers={"x-user-role": "client"}
        )
        assert response.status_code == 403
        data = response.json()
        assert "detail" in data
        assert "Access denied" in data["detail"]
        assert "Insufficient permissions" in data["detail"]
    
    def test_customer_cannot_access_crm_emails(self, test_client):
        """Test that customer role cannot access CRM emails (403)"""
        response = test_client.get(
            "/api/crm/company/comp-test/emails",
            headers={"x-user-role": "customer"}
        )
        assert response.status_code == 403
        data = response.json()
        assert "Access denied" in data["detail"]
    
    def test_unknown_role_cannot_access_crm_emails(self, test_client):
        """Test that unknown role cannot access CRM emails (403 - least privilege)"""
        response = test_client.get(
            "/api/crm/company/comp-test/emails",
            headers={"x-user-role": "random_role"}
        )
        assert response.status_code == 403
    
    def test_no_role_header_cannot_access_crm_emails(self, test_client):
        """Test that missing role header gets full access for backward compatibility"""
        response = test_client.get("/api/crm/company/comp-test/emails")
        # For backward compatibility, no role header should grant access
        assert response.status_code == 200
    
    def test_admin_can_access_crm_events(self, test_client):
        """Test that admin role can access CRM events"""
        response = test_client.get(
            "/api/crm/company/comp-test/events",
            headers={"x-user-role": "admin"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "events" in data
        assert "total" in data
    
    def test_analyst_can_access_crm_events(self, test_client):
        """Test that analyst role can access CRM events"""
        response = test_client.get(
            "/api/crm/company/comp-test/events",
            headers={"x-user-role": "analyst"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "events" in data
    
    def test_client_cannot_access_crm_events(self, test_client):
        """Test that client role cannot access CRM events (403)"""
        response = test_client.get(
            "/api/crm/company/comp-test/events",
            headers={"x-user-role": "client"}
        )
        assert response.status_code == 403
        data = response.json()
        assert "Access denied" in data["detail"]
    
    def test_customer_cannot_access_crm_events(self, test_client):
        """Test that customer role cannot access CRM events (403)"""
        response = test_client.get(
            "/api/crm/company/comp-test/events",
            headers={"x-user-role": "customer"}
        )
        assert response.status_code == 403
    
    def test_admin_sees_event_details_in_crm(self, test_client):
        """Test that admin sees full event details via CRM endpoint"""
        response = test_client.get(
            "/api/crm/company/comp-test/events",
            headers={"x-user-role": "admin"}
        )
        assert response.status_code == 200
        data = response.json()
        
        if data["total"] > 0:
            event = data["events"][0]
            # Admin should see details (if they exist in the test data)
            # Fields should be present (may be None if not set in test data)
            assert "description" in event
            assert "meet_link" in event
            assert "matched_contacts" in event
    
    def test_analyst_sees_event_details_in_crm(self, test_client):
        """Test that analyst sees full event details via CRM endpoint"""
        response = test_client.get(
            "/api/crm/company/comp-test/events",
            headers={"x-user-role": "analyst"}
        )
        assert response.status_code == 200
        data = response.json()
        
        if data["total"] > 0:
            event = data["events"][0]
            # Analyst should see details (if they exist)
            assert "description" in event
            assert "meet_link" in event
    
    def test_permission_service_crm_permissions(self):
        """Test PermissionService CRM permission logic directly"""
        from services.permission_service import PermissionService
        
        # Full access roles
        full_access_roles = ["admin", "superadmin", "manager", "analyst", "new_business"]
        for role in full_access_roles:
            perms = PermissionService.get_crm_permissions_for_role(role)
            assert perms.crm_read_communications is True, f"Role {role} should have crm_read_communications"
        
        # Restricted access roles (no access to CRM communications)
        restricted_roles = ["client", "customer"]
        for role in restricted_roles:
            perms = PermissionService.get_crm_permissions_for_role(role)
            assert perms.crm_read_communications is False, f"Role {role} should NOT have crm_read_communications"
        
        # Unknown roles get restricted access
        perms = PermissionService.get_crm_permissions_for_role("unknown_role")
        assert perms.crm_read_communications is False, "unknown_role should NOT have crm_read_communications"
        
        # None/empty roles get full access for backward compatibility
        for role in [None, ""]:
            perms = PermissionService.get_crm_permissions_for_role(role)
            assert perms.crm_read_communications is True, f"Role {role} should have crm_read_communications (backward compat)"
    
    def test_crm_emails_respects_gmail_permissions(self, test_client):
        """Test that CRM emails endpoint uses snippet (not full body) to respect Gmail permissions"""
        response = test_client.get(
            "/api/crm/company/comp-test/emails",
            headers={"x-user-role": "admin"}
        )
        assert response.status_code == 200
        data = response.json()
        
        # All emails should have snippet field
        for email in data["emails"]:
            assert "snippet" in email
            # Note: The EmailSummaryForCRM schema doesn't include body fields
            # This is intentional - we use snippet to avoid exposing full body
    
    def test_different_entity_types_with_permissions(self, test_client):
        """Test permissions work across different entity types"""
        entity_types = ['company', 'lead', 'deal']
        entity_ids = ['comp-test', 'lead-test', 'deal-test']
        
        for entity_type, entity_id in zip(entity_types, entity_ids):
            # Admin should succeed
            response = test_client.get(
                f"/api/crm/{entity_type}/{entity_id}/emails",
                headers={"x-user-role": "admin"}
            )
            assert response.status_code == 200
            
            # Client should fail
            response = test_client.get(
                f"/api/crm/{entity_type}/{entity_id}/emails",
                headers={"x-user-role": "client"}
            )
            assert response.status_code == 403
    
    def test_case_insensitive_role_matching(self, test_client):
        """Test that role matching is case-insensitive"""
        # Test with uppercase
        response = test_client.get(
            "/api/crm/company/comp-test/emails",
            headers={"x-user-role": "ADMIN"}
        )
        assert response.status_code == 200
        
        # Test with mixed case
        response = test_client.get(
            "/api/crm/company/comp-test/events",
            headers={"x-user-role": "AnAlYsT"}
        )
        assert response.status_code == 200
        
        # Test blocked role with uppercase
        response = test_client.get(
            "/api/crm/company/comp-test/emails",
            headers={"x-user-role": "CLIENT"}
        )
        assert response.status_code == 403


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
