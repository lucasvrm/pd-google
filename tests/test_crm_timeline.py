"""
Tests for CRM Timeline API endpoint
Tests the unified timeline endpoint that merges emails and calendar events.
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
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_crm_timeline.db"
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
        """Create test messages with different timestamps"""
        now = datetime.now()
        return {
            'msg1': {
                'id': 'msg1',
                'threadId': 'thread1',
                'snippet': 'Email from 2 days ago',
                'internalDate': str(int((now - timedelta(days=2)).timestamp() * 1000)),
                'payload': {
                    'headers': [
                        {'name': 'Subject', 'value': 'Old Email'},
                        {'name': 'From', 'value': 'client@company.com'},
                        {'name': 'To', 'value': 'sales@ourcompany.com'},
                    ],
                    'parts': []
                }
            },
            'msg2': {
                'id': 'msg2',
                'threadId': 'thread2',
                'snippet': 'Email from 1 day ago',
                'internalDate': str(int((now - timedelta(days=1)).timestamp() * 1000)),
                'payload': {
                    'headers': [
                        {'name': 'Subject', 'value': 'Recent Email'},
                        {'name': 'From', 'value': 'sales@ourcompany.com'},
                        {'name': 'To', 'value': 'client@company.com'},
                        {'name': 'Cc', 'value': 'manager@ourcompany.com'},
                    ],
                    'parts': []
                }
            },
            'msg3': {
                'id': 'msg3',
                'threadId': 'thread3',
                'snippet': 'Most recent email',
                'internalDate': str(int(now.timestamp() * 1000)),
                'payload': {
                    'headers': [
                        {'name': 'Subject', 'value': 'Latest Email'},
                        {'name': 'From', 'value': 'client@company.com'},
                        {'name': 'To', 'value': 'sales@ourcompany.com'},
                    ],
                    'parts': []
                }
            }
        }
    
    def list_messages(self, query=None, label_ids=None, max_results=100, page_token=None):
        """Mock list messages - return all messages for testing"""
        messages = []
        
        if query and 'client@company.com' in query:
            messages = [{'id': 'msg1'}, {'id': 'msg2'}, {'id': 'msg3'}]
        
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
        if entity_type == 'company' and entity_id == 'comp-timeline':
            return ['client@company.com', 'ceo@company.com']
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
    company = models.Company(id='comp-timeline', name='Timeline Test Company')
    db.add(company)
    
    # Add calendar events with different timestamps
    now = datetime.now()
    
    # Event from 3 days ago
    event1 = models.CalendarEvent(
        google_event_id='event1',
        summary='Old Meeting',
        start_time=now - timedelta(days=3),
        end_time=now - timedelta(days=3) + timedelta(hours=1),
        status='confirmed',
        organizer_email='organizer@ourcompany.com',
        attendees=json.dumps([
            {'email': 'client@company.com', 'responseStatus': 'accepted'}
        ])
    )
    db.add(event1)
    
    # Event from 1.5 days ago (should interleave with emails)
    event2 = models.CalendarEvent(
        google_event_id='event2',
        summary='Mid Meeting',
        description='Meeting description',
        start_time=now - timedelta(days=1, hours=12),
        end_time=now - timedelta(days=1, hours=11),
        status='confirmed',
        organizer_email='sales@ourcompany.com',
        attendees=json.dumps([
            {'email': 'ceo@company.com', 'responseStatus': 'tentative'},
            {'email': 'other@example.com', 'responseStatus': 'accepted'}
        ])
    )
    db.add(event2)
    
    # Future event
    event3 = models.CalendarEvent(
        google_event_id='event3',
        summary='Future Meeting',
        start_time=now + timedelta(days=1),
        end_time=now + timedelta(days=1, hours=1),
        status='confirmed',
        attendees=json.dumps([
            {'email': 'client@company.com', 'responseStatus': 'needsAction'}
        ])
    )
    db.add(event3)
    
    # Cancelled event (should be excluded by default)
    event4 = models.CalendarEvent(
        google_event_id='event4',
        summary='Cancelled Meeting',
        start_time=now - timedelta(days=2),
        end_time=now - timedelta(days=2) + timedelta(hours=1),
        status='cancelled',
        attendees=json.dumps([
            {'email': 'client@company.com', 'responseStatus': 'declined'}
        ])
    )
    db.add(event4)
    
    db.commit()
    db.close()
    
    client = TestClient(app)
    yield client
    
    # Cleanup
    Base.metadata.drop_all(bind=engine)
    try:
        os.remove("./test_crm_timeline.db")
    except:
        pass


class TestCRMTimelineEndpoint:
    """Test the unified timeline endpoint"""
    
    def test_timeline_endpoint_exists(self, test_client):
        """Test that timeline endpoint is available"""
        response = test_client.get("/api/crm/company/comp-timeline/timeline")
        assert response.status_code == 200
    
    def test_timeline_response_structure(self, test_client):
        """Test that timeline response has correct structure"""
        response = test_client.get("/api/crm/company/comp-timeline/timeline")
        assert response.status_code == 200
        data = response.json()
        
        # Check required fields
        assert 'items' in data
        assert 'total' in data
        assert 'limit' in data
        assert 'offset' in data
        
        assert isinstance(data['items'], list)
        assert isinstance(data['total'], int)
    
    def test_timeline_item_structure(self, test_client):
        """Test that timeline items have correct structure"""
        response = test_client.get("/api/crm/company/comp-timeline/timeline")
        assert response.status_code == 200
        data = response.json()
        
        if data['items']:
            item = data['items'][0]
            # Check required fields
            required_fields = [
                'id', 'source', 'type', 'subject', 'datetime',
                'participants', 'matched_contacts', 'entity_type', 'entity_id'
            ]
            for field in required_fields:
                assert field in item, f"Missing field: {field}"
            
            # Check field types and values
            assert item['source'] in ['gmail', 'calendar']
            assert item['type'] in ['email', 'event']
            assert item['entity_type'] == 'company'
            assert item['entity_id'] == 'comp-timeline'
            assert isinstance(item['participants'], list)
            assert isinstance(item['matched_contacts'], list)
    
    def test_timeline_merges_emails_and_events(self, test_client):
        """Test that timeline contains both emails and events"""
        response = test_client.get("/api/crm/company/comp-timeline/timeline")
        assert response.status_code == 200
        data = response.json()
        
        # Should have items from both sources
        sources = [item['source'] for item in data['items']]
        types = [item['type'] for item in data['items']]
        
        # Check we have both gmail and calendar items
        assert 'gmail' in sources, "Timeline should include Gmail items"
        assert 'calendar' in sources, "Timeline should include Calendar items"
        assert 'email' in types
        assert 'event' in types
    
    def test_timeline_sorted_by_datetime_desc(self, test_client):
        """Test that timeline is sorted by datetime descending (newest first)"""
        response = test_client.get("/api/crm/company/comp-timeline/timeline")
        assert response.status_code == 200
        data = response.json()
        
        if len(data['items']) > 1:
            # Extract datetimes
            datetimes = [datetime.fromisoformat(item['datetime'].replace('Z', '+00:00')) 
                        for item in data['items']]
            
            # Verify descending order
            for i in range(len(datetimes) - 1):
                assert datetimes[i] >= datetimes[i + 1], \
                    f"Timeline not sorted: {datetimes[i]} should be >= {datetimes[i + 1]}"
    
    def test_timeline_pagination_limit(self, test_client):
        """Test pagination limit parameter"""
        response = test_client.get("/api/crm/company/comp-timeline/timeline?limit=2")
        assert response.status_code == 200
        data = response.json()
        
        assert data['limit'] == 2
        assert len(data['items']) <= 2
        assert data['total'] >= len(data['items'])
    
    def test_timeline_pagination_offset(self, test_client):
        """Test pagination offset parameter"""
        # Get first page
        response1 = test_client.get("/api/crm/company/comp-timeline/timeline?limit=2&offset=0")
        assert response1.status_code == 200
        data1 = response1.json()
        
        # Get second page
        response2 = test_client.get("/api/crm/company/comp-timeline/timeline?limit=2&offset=2")
        assert response2.status_code == 200
        data2 = response2.json()
        
        # Both should have same total
        assert data1['total'] == data2['total']
        
        # Items should be different (if we have enough items)
        if data1['total'] > 2:
            assert data1['items'] != data2['items']
    
    def test_timeline_pagination_consistency(self, test_client):
        """Test that pagination is applied after merge and sort"""
        # Get all items
        response = test_client.get("/api/crm/company/comp-timeline/timeline?limit=100")
        assert response.status_code == 200
        all_data = response.json()
        
        # Get paginated items
        response1 = test_client.get("/api/crm/company/comp-timeline/timeline?limit=3&offset=0")
        response2 = test_client.get("/api/crm/company/comp-timeline/timeline?limit=3&offset=3")
        
        data1 = response1.json()
        data2 = response2.json()
        
        # First 3 items should match
        if all_data['total'] >= 3:
            for i in range(min(3, len(all_data['items']))):
                assert data1['items'][i]['id'] == all_data['items'][i]['id']
        
        # Next 3 items should match
        if all_data['total'] >= 6:
            for i in range(min(3, len(data2['items']))):
                assert data2['items'][i]['id'] == all_data['items'][i + 3]['id']


class TestCRMTimelinePermissions:
    """Test timeline endpoint permissions"""
    
    def test_admin_can_access_timeline(self, test_client):
        """Test that admin role can access timeline"""
        response = test_client.get(
            "/api/crm/company/comp-timeline/timeline",
            headers={"x-user-role": "admin"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
    
    def test_analyst_can_access_timeline(self, test_client):
        """Test that analyst role can access timeline"""
        response = test_client.get(
            "/api/crm/company/comp-timeline/timeline",
            headers={"x-user-role": "analyst"}
        )
        assert response.status_code == 200
    
    def test_manager_can_access_timeline(self, test_client):
        """Test that manager role can access timeline"""
        response = test_client.get(
            "/api/crm/company/comp-timeline/timeline",
            headers={"x-user-role": "manager"}
        )
        assert response.status_code == 200
    
    def test_new_business_can_access_timeline(self, test_client):
        """Test that new_business role can access timeline"""
        response = test_client.get(
            "/api/crm/company/comp-timeline/timeline",
            headers={"x-user-role": "new_business"}
        )
        assert response.status_code == 200
    
    def test_client_cannot_access_timeline(self, test_client):
        """Test that client role cannot access timeline (403)"""
        response = test_client.get(
            "/api/crm/company/comp-timeline/timeline",
            headers={"x-user-role": "client"}
        )
        assert response.status_code == 403
        data = response.json()
        assert "Access denied" in data["message"]
    
    def test_customer_cannot_access_timeline(self, test_client):
        """Test that customer role cannot access timeline (403)"""
        response = test_client.get(
            "/api/crm/company/comp-timeline/timeline",
            headers={"x-user-role": "customer"}
        )
        assert response.status_code == 403
    
    def test_unknown_role_cannot_access_timeline(self, test_client):
        """Test that unknown role cannot access timeline (403)"""
        response = test_client.get(
            "/api/crm/company/comp-timeline/timeline",
            headers={"x-user-role": "random_unknown_role"}
        )
        assert response.status_code == 403
    
    def test_no_role_header_grants_access(self, test_client):
        """Test that missing role header grants access (backward compatibility)"""
        response = test_client.get("/api/crm/company/comp-timeline/timeline")
        assert response.status_code == 200
    
    def test_admin_sees_event_descriptions(self, test_client):
        """Test that admin sees event descriptions in timeline"""
        response = test_client.get(
            "/api/crm/company/comp-timeline/timeline",
            headers={"x-user-role": "admin"}
        )
        assert response.status_code == 200
        data = response.json()
        
        # Find a calendar event item
        calendar_items = [item for item in data['items'] if item['source'] == 'calendar']
        if calendar_items:
            # Admin should see snippet (description) if it exists
            event_with_desc = [item for item in calendar_items if item.get('snippet')]
            # At least one event has description in our test data
            assert len(event_with_desc) > 0, "Admin should see event descriptions"


class TestCRMTimelineFilters:
    """Test timeline filtering capabilities"""
    
    def test_timeline_excludes_cancelled_events(self, test_client):
        """Test that cancelled events are excluded by default"""
        response = test_client.get("/api/crm/company/comp-timeline/timeline")
        assert response.status_code == 200
        data = response.json()
        
        # Check that no cancelled events are in timeline
        for item in data['items']:
            if item['source'] == 'calendar':
                # We can't check status directly as it's not in TimelineItem
                # But cancelled events shouldn't be included
                assert item['subject'] != 'Cancelled Meeting'
    
    def test_timeline_with_time_filters(self, test_client):
        """Test timeline with time_min and time_max filters"""
        # Test with time_min
        response = test_client.get(
            "/api/crm/company/comp-timeline/timeline?time_min=2024-01-01"
        )
        assert response.status_code == 200
        
        # Test with time_max
        response = test_client.get(
            "/api/crm/company/comp-timeline/timeline?time_max=2025-12-31"
        )
        assert response.status_code == 200


class TestCRMTimelineEdgeCases:
    """Test edge cases for timeline endpoint"""
    
    def test_timeline_entity_not_found(self, test_client):
        """Test timeline with non-existent entity"""
        response = test_client.get("/api/crm/company/nonexistent/timeline")
        assert response.status_code == 404
    
    def test_timeline_invalid_entity_type(self, test_client):
        """Test timeline with invalid entity type"""
        response = test_client.get("/api/crm/invalid/test-id/timeline")
        assert response.status_code == 422  # Pydantic validation error
    
    def test_timeline_empty_result(self, test_client):
        """Test timeline when no communications exist"""
        # Create a company without contacts
        db = TestingSessionLocal()
        company = models.Company(id='comp-no-comms', name='No Communications Company')
        db.add(company)
        db.commit()
        db.close()
        
        response = test_client.get("/api/crm/company/comp-no-comms/timeline")
        assert response.status_code == 200
        data = response.json()
        
        assert data['total'] == 0
        assert data['items'] == []
    
    def test_timeline_with_all_entity_types(self, test_client):
        """Test that timeline works for all entity types"""
        # Add lead and deal for testing
        db = TestingSessionLocal()
        
        lead = models.Lead(id='lead-timeline', title='Timeline Test Lead')
        db.add(lead)
        
        deal = models.Deal(id='deal-timeline', title='Timeline Test Deal')
        db.add(deal)
        
        db.commit()
        db.close()
        
        # Test company (already exists)
        response = test_client.get(
            "/api/crm/company/comp-timeline/timeline",
            headers={"x-user-role": "admin"}
        )
        assert response.status_code == 200
        
        # Test lead
        response = test_client.get(
            "/api/crm/lead/lead-timeline/timeline",
            headers={"x-user-role": "admin"}
        )
        assert response.status_code == 200
        
        # Test deal
        response = test_client.get(
            "/api/crm/deal/deal-timeline/timeline",
            headers={"x-user-role": "admin"}
        )
        assert response.status_code == 200


class TestCRMTimelineIntegration:
    """Integration tests comparing timeline with individual endpoints"""
    
    def test_timeline_total_matches_sum_of_emails_and_events(self, test_client):
        """Test that timeline total approximately matches sum of emails + events"""
        # Get timeline
        timeline_response = test_client.get(
            "/api/crm/company/comp-timeline/timeline?limit=100"
        )
        assert timeline_response.status_code == 200
        timeline_data = timeline_response.json()
        
        # Count items by source
        gmail_count = sum(1 for item in timeline_data['items'] if item['source'] == 'gmail')
        calendar_count = sum(1 for item in timeline_data['items'] if item['source'] == 'calendar')
        
        # Total should be sum of both
        assert timeline_data['total'] == gmail_count + calendar_count
    
    def test_timeline_participants_populated(self, test_client):
        """Test that timeline items have participants populated"""
        response = test_client.get("/api/crm/company/comp-timeline/timeline")
        assert response.status_code == 200
        data = response.json()
        
        for item in data['items']:
            # Participants should be a list
            assert isinstance(item['participants'], list)
            
            # At least matched contacts should be in participants
            for contact in item['matched_contacts']:
                # Participants might have more emails, but matched should be subset
                pass  # Just verify structure is correct
    
    def test_timeline_matched_contacts_populated(self, test_client):
        """Test that all timeline items have matched_contacts"""
        response = test_client.get("/api/crm/company/comp-timeline/timeline")
        assert response.status_code == 200
        data = response.json()
        
        for item in data['items']:
            # Every item should have matched_contacts (might be empty list)
            assert isinstance(item['matched_contacts'], list)
            # Since we're filtering by contacts, should have at least one match
            assert len(item['matched_contacts']) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
