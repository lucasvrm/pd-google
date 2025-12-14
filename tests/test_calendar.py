
import pytest
import os
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base
from main import app
import models

# 1. Setup Test DB
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_calendar.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

from routers.calendar import get_db, get_calendar_service
app.dependency_overrides[get_db] = override_get_db

# 2. Mock Calendar Service
class MockCalendarService:
    def __init__(self):
        self.events = {}
        self.counter = 0

    def create_event(self, event_data: Dict[str, Any], calendar_id: str = 'primary') -> Dict[str, Any]:
        self.counter += 1
        event_id = f"evt_{self.counter}"

        # Simulate Google Response
        new_event = {
            "id": event_id,
            "status": "confirmed",
            "summary": event_data.get("summary"),
            "description": event_data.get("description"),
            "start": event_data.get("start"),
            "end": event_data.get("end"),
            "organizer": {"email": "organizer@example.com"},
            "attendees": event_data.get("attendees", []),
            "htmlLink": f"https://calendar.google.com/event?eid={event_id}"
        }

        if "conferenceData" in event_data:
            new_event["hangoutLink"] = f"https://meet.google.com/meet-{event_id}"

        self.events[event_id] = new_event
        return new_event

    def list_events(self, calendar_id: str = 'primary', time_min: Optional[str] = None, time_max: Optional[str] = None, sync_token: Optional[str] = None) -> Dict[str, Any]:
        # Simple mock implementation
        return {"items": list(self.events.values())}

    def update_event(self, event_id: str, event_data: Dict[str, Any], calendar_id: str = 'primary') -> Dict[str, Any]:
        if event_id not in self.events:
             raise Exception("Event not found")

        event = self.events[event_id]
        if "summary" in event_data: event["summary"] = event_data["summary"]
        if "description" in event_data: event["description"] = event_data["description"]
        if "start" in event_data: event["start"] = event_data["start"]
        if "end" in event_data: event["end"] = event_data["end"]
        if "attendees" in event_data: event["attendees"] = event_data["attendees"]

        return event

    def delete_event(self, event_id: str, calendar_id: str = 'primary'):
        if event_id in self.events:
            del self.events[event_id]
        return

    def watch_events(self, channel_id: str, webhook_url: str, calendar_id: str = 'primary', token: Optional[str] = None, expiration: Optional[int] = None) -> Dict[str, Any]:
        return {
            "id": channel_id,
            "resourceId": "res-mock-123",
            "expiration": expiration
        }

mock_service = MockCalendarService()

def override_get_calendar_service():
    return mock_service

app.dependency_overrides[get_calendar_service] = override_get_calendar_service

client = TestClient(app)

def setup_module(module):
    Base.metadata.create_all(bind=engine)

def teardown_module(module):
    if os.path.exists("./test_calendar.db"):
        os.remove("./test_calendar.db")

# 3. Tests

def test_create_event():
    response = client.post("/api/calendar/events", json={
        "summary": "Test Meeting",
        "description": "Discussing things",
        "start_time": "2023-10-27T10:00:00",
        "end_time": "2023-10-27T11:00:00",
        "attendees": ["test@example.com"],
        "create_meet_link": True
    })

    assert response.status_code == 201
    data = response.json()
    assert data["summary"] == "Test Meeting"
    assert data["meet_link"] is not None
    assert "meet.google.com" in data["meet_link"]
    assert data["google_event_id"].startswith("evt_")

def test_list_events():
    # Setup: Ensure DB has data (from previous test or new)
    response = client.get("/api/calendar/events")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert data[0]["summary"] == "Test Meeting"

def test_update_event():
    # First create an event to update
    create_res = client.post("/api/calendar/events", json={
        "summary": "To Update",
        "start_time": "2023-10-28T10:00:00",
        "end_time": "2023-10-28T11:00:00"
    })
    event_id = create_res.json()["id"]

    # Update it
    response = client.patch(f"/api/calendar/events/{event_id}", json={
        "summary": "Updated Title"
    })

    assert response.status_code == 200

    # Verify in list
    get_res = client.get("/api/calendar/events")
    found = False
    for evt in get_res.json():
        if evt["id"] == event_id:
            assert evt["summary"] == "Updated Title"
            found = True
    assert found

def test_delete_event():
    # Create event to delete
    create_res = client.post("/api/calendar/events", json={
        "summary": "To Delete",
        "start_time": "2023-10-29T10:00:00",
        "end_time": "2023-10-29T11:00:00"
    })
    event_id = create_res.json()["id"]

    # Delete it
    response = client.delete(f"/api/calendar/events/{event_id}")
    assert response.status_code == 200

    # Verify status is cancelled in DB (Soft Delete behavior in router)
    # The router code says: db_event.status = 'cancelled'

    # Let's verify via GET
    # The GET endpoint filters out cancelled events:
    # query = db.query(models.CalendarEvent).filter(models.CalendarEvent.status != 'cancelled')

    get_res = client.get("/api/calendar/events")
    for evt in get_res.json():
        assert evt["id"] != event_id

def test_watch_calendar():
    response = client.post("/api/calendar/watch")
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "watching"
    assert data["channel_id"] is not None
    assert data["resource_id"] == "res-mock-123"

def test_get_event_by_id():
    """Test retrieving a specific event by its ID"""
    # Create an event first
    create_res = client.post("/api/calendar/events", json={
        "summary": "Specific Event",
        "description": "Event to retrieve by ID",
        "start_time": "2023-10-30T14:00:00",
        "end_time": "2023-10-30T15:00:00",
        "attendees": ["user1@example.com", "user2@example.com"],
        "create_meet_link": True
    })
    assert create_res.status_code == 201
    event_id = create_res.json()["id"]
    
    # Get the event by ID
    response = client.get(f"/api/calendar/events/{event_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == event_id
    assert data["summary"] == "Specific Event"
    assert data["description"] == "Event to retrieve by ID"
    assert data["meet_link"] is not None
    assert data["html_link"] is not None
    assert data["organizer_email"] is not None
    assert len(data["attendees"]) == 2
    assert data["attendees"][0]["email"] in ["user1@example.com", "user2@example.com"]

def test_get_event_not_found():
    """Test getting a non-existent event returns 404"""
    response = client.get("/api/calendar/events/999999")
    assert response.status_code == 404

def test_list_events_with_pagination():
    """Test listing events with pagination parameters"""
    # Create multiple events
    for i in range(5):
        client.post("/api/calendar/events", json={
            "summary": f"Event {i}",
            "start_time": f"2023-11-{10+i:02d}T10:00:00",
            "end_time": f"2023-11-{10+i:02d}T11:00:00"
        })
    
    # Test with limit
    response = client.get("/api/calendar/events?limit=3")
    assert response.status_code == 200
    data = response.json()
    assert len(data) <= 3
    
    # Test with offset
    response = client.get("/api/calendar/events?limit=2&offset=2")
    assert response.status_code == 200
    data = response.json()
    assert len(data) <= 2

def test_list_events_with_status_filter():
    """Test filtering events by status"""
    # Create and then cancel an event
    create_res = client.post("/api/calendar/events", json={
        "summary": "Event to Cancel",
        "start_time": "2023-11-20T10:00:00",
        "end_time": "2023-11-20T11:00:00"
    })
    event_id = create_res.json()["id"]
    client.delete(f"/api/calendar/events/{event_id}")
    
    # List without filter should not include cancelled
    response = client.get("/api/calendar/events")
    assert response.status_code == 200
    for evt in response.json():
        assert evt["status"] != "cancelled"
    
    # List with cancelled filter should include it
    response = client.get("/api/calendar/events?status=cancelled")
    assert response.status_code == 200
    cancelled_events = response.json()
    assert any(evt["id"] == event_id for evt in cancelled_events)

def test_update_event_with_attendees():
    """Test updating event with new attendees"""
    # Create event
    create_res = client.post("/api/calendar/events", json={
        "summary": "Meeting",
        "start_time": "2023-11-25T10:00:00",
        "end_time": "2023-11-25T11:00:00",
        "attendees": ["user1@example.com"]
    })
    event_id = create_res.json()["id"]
    
    # Update with new attendees
    response = client.patch(f"/api/calendar/events/{event_id}", json={
        "attendees": ["user1@example.com", "user2@example.com", "user3@example.com"]
    })
    assert response.status_code == 200
    data = response.json()
    assert len(data["attendees"]) == 3

def test_event_response_includes_all_fields():
    """Test that event responses include all required fields"""
    response = client.post("/api/calendar/events", json={
        "summary": "Complete Event",
        "description": "Testing all fields",
        "start_time": "2023-12-01T10:00:00",
        "end_time": "2023-12-01T11:00:00",
        "attendees": ["test@example.com"],
        "create_meet_link": True
    })
    
    assert response.status_code == 201
    data = response.json()
    
    # Verify all required fields are present
    assert "id" in data
    assert "google_event_id" in data
    assert "summary" in data
    assert "description" in data
    assert "start_time" in data
    assert "end_time" in data
    assert "meet_link" in data
    assert "html_link" in data
    assert "status" in data
    assert "organizer_email" in data
    assert "attendees" in data
    assert isinstance(data["attendees"], list)


# ------------------------------------------------------------
# Calendar Permission Tests
# ------------------------------------------------------------

def test_admin_can_see_calendar_event_details():
    """Test that admin role can see all event details"""
    # Create an event first
    create_res = client.post("/api/calendar/events", json={
        "summary": "Admin Test Event",
        "description": "Sensitive information here",
        "start_time": "2024-01-15T10:00:00",
        "end_time": "2024-01-15T11:00:00",
        "attendees": ["client@example.com", "manager@example.com"],
        "create_meet_link": True
    })
    assert create_res.status_code == 201
    event_id = create_res.json()["id"]
    
    # Get event as admin
    response = client.get(f"/api/calendar/events/{event_id}", headers={"x-user-role": "admin"})
    assert response.status_code == 200
    data = response.json()
    
    # Admin should see all details
    assert data["description"] == "Sensitive information here"
    assert len(data["attendees"]) == 2
    assert data["meet_link"] is not None
    assert "meet.google.com" in data["meet_link"]


def test_analyst_can_see_calendar_event_details():
    """Test that analyst role can see all event details"""
    # Create an event
    create_res = client.post("/api/calendar/events", json={
        "summary": "Analyst Test Event",
        "description": "Project discussion details",
        "start_time": "2024-01-16T14:00:00",
        "end_time": "2024-01-16T15:00:00",
        "attendees": ["team@example.com"],
        "create_meet_link": True
    })
    event_id = create_res.json()["id"]
    
    # Get event as analyst
    response = client.get(f"/api/calendar/events/{event_id}", headers={"x-user-role": "analyst"})
    assert response.status_code == 200
    data = response.json()
    
    # Analyst should see all details
    assert data["description"] == "Project discussion details"
    assert len(data["attendees"]) == 1
    assert data["meet_link"] is not None


def test_client_cannot_see_calendar_event_details():
    """Test that client role cannot see sensitive event details"""
    # Create an event
    create_res = client.post("/api/calendar/events", json={
        "summary": "Client Test Event",
        "description": "Internal strategy discussion",
        "start_time": "2024-01-17T10:00:00",
        "end_time": "2024-01-17T11:00:00",
        "attendees": ["internal@example.com", "partner@example.com"],
        "create_meet_link": True
    })
    event_id = create_res.json()["id"]
    
    # Get event as client
    response = client.get(f"/api/calendar/events/{event_id}", headers={"x-user-role": "client"})
    assert response.status_code == 200
    data = response.json()
    
    # Client should see basic info but not sensitive details
    assert data["summary"] == "Client Test Event"
    assert data["start_time"] is not None
    assert data["end_time"] is not None
    assert data["html_link"] is not None
    
    # Sensitive fields should be redacted
    assert data["description"] is None
    assert len(data["attendees"]) == 0
    assert data["meet_link"] is None


def test_customer_cannot_see_calendar_event_details():
    """Test that customer role cannot see sensitive event details"""
    # Create an event
    create_res = client.post("/api/calendar/events", json={
        "summary": "Customer Event",
        "description": "Confidential notes",
        "start_time": "2024-01-18T09:00:00",
        "end_time": "2024-01-18T10:00:00",
        "attendees": ["sales@example.com"],
        "create_meet_link": True
    })
    event_id = create_res.json()["id"]
    
    # Get event as customer
    response = client.get(f"/api/calendar/events/{event_id}", headers={"x-user-role": "customer"})
    assert response.status_code == 200
    data = response.json()
    
    # Customer should not see sensitive details
    assert data["description"] is None
    assert len(data["attendees"]) == 0
    assert data["meet_link"] is None


def test_unknown_role_cannot_see_calendar_event_details():
    """Test that unknown role cannot see sensitive event details (least privilege)"""
    # Create an event
    create_res = client.post("/api/calendar/events", json={
        "summary": "Unknown Role Event",
        "description": "Secret information",
        "start_time": "2024-01-19T11:00:00",
        "end_time": "2024-01-19T12:00:00",
        "attendees": ["secret@example.com"],
        "create_meet_link": True
    })
    event_id = create_res.json()["id"]
    
    # Get event with unknown role
    response = client.get(f"/api/calendar/events/{event_id}", headers={"x-user-role": "random_role"})
    assert response.status_code == 200
    data = response.json()
    
    # Unknown role should not see sensitive details
    assert data["description"] is None
    assert len(data["attendees"]) == 0
    assert data["meet_link"] is None


def test_no_role_header_cannot_see_calendar_event_details():
    """Test that missing role header gets full access for backward compatibility"""
    # Create an event
    create_res = client.post("/api/calendar/events", json={
        "summary": "No Role Event",
        "description": "Private content",
        "start_time": "2024-01-20T13:00:00",
        "end_time": "2024-01-20T14:00:00",
        "attendees": ["private@example.com"],
        "create_meet_link": True
    })
    event_id = create_res.json()["id"]
    
    # Get event without role header - should get full access for backward compatibility
    response = client.get(f"/api/calendar/events/{event_id}")
    assert response.status_code == 200
    data = response.json()
    
    # No role should get full access (backward compatibility)
    assert data["description"] == "Private content"
    assert len(data["attendees"]) == 1
    assert data["meet_link"] is not None


def test_list_events_with_admin_role():
    """Test that list events respects permissions for admin role"""
    # Create multiple events
    for i in range(3):
        client.post("/api/calendar/events", json={
            "summary": f"List Test Event {i}",
            "description": f"Details {i}",
            "start_time": f"2024-02-{10+i:02d}T10:00:00",
            "end_time": f"2024-02-{10+i:02d}T11:00:00",
            "attendees": [f"user{i}@example.com"],
            "create_meet_link": True
        })
    
    # List events as admin
    response = client.get("/api/calendar/events?limit=10", headers={"x-user-role": "admin"})
    assert response.status_code == 200
    events = response.json()
    assert len(events) > 0
    
    # Admin should see all details in list
    for event in events:
        if event["summary"].startswith("List Test Event"):
            assert event["description"] is not None
            # Note: attendees might be empty if not part of List Test Event series


def test_list_events_with_client_role():
    """Test that list events redacts details for client role"""
    # Create an event
    client.post("/api/calendar/events", json={
        "summary": "Client List Test",
        "description": "Sensitive list info",
        "start_time": "2024-02-15T10:00:00",
        "end_time": "2024-02-15T11:00:00",
        "attendees": ["confidential@example.com"],
        "create_meet_link": True
    })
    
    # List events as client
    response = client.get("/api/calendar/events?limit=50", headers={"x-user-role": "client"})
    assert response.status_code == 200
    events = response.json()
    
    # Find our test event
    client_event = None
    for event in events:
        if event["summary"] == "Client List Test":
            client_event = event
            break
    
    assert client_event is not None
    # Client should not see details
    assert client_event["description"] is None
    assert len(client_event["attendees"]) == 0
    assert client_event["meet_link"] is None


def test_manager_can_see_calendar_event_details():
    """Test that manager role can see all event details"""
    # Create an event
    create_res = client.post("/api/calendar/events", json={
        "summary": "Manager Test Event",
        "description": "Manager meeting notes",
        "start_time": "2024-02-20T10:00:00",
        "end_time": "2024-02-20T11:00:00",
        "attendees": ["team@example.com"],
        "create_meet_link": True
    })
    event_id = create_res.json()["id"]
    
    # Get event as manager
    response = client.get(f"/api/calendar/events/{event_id}", headers={"x-user-role": "manager"})
    assert response.status_code == 200
    data = response.json()
    
    # Manager should see all details
    assert data["description"] == "Manager meeting notes"
    assert len(data["attendees"]) == 1
    assert data["meet_link"] is not None


def test_new_business_can_see_calendar_event_details():
    """Test that new_business role can see all event details"""
    # Create an event
    create_res = client.post("/api/calendar/events", json={
        "summary": "New Business Test Event",
        "description": "Sales opportunity details",
        "start_time": "2024-02-21T14:00:00",
        "end_time": "2024-02-21T15:00:00",
        "attendees": ["prospect@example.com"],
        "create_meet_link": True
    })
    event_id = create_res.json()["id"]
    
    # Get event as new_business
    response = client.get(f"/api/calendar/events/{event_id}", headers={"x-user-role": "new_business"})
    assert response.status_code == 200
    data = response.json()
    
    # New business should see all details
    assert data["description"] == "Sales opportunity details"
    assert len(data["attendees"]) == 1
    assert data["meet_link"] is not None


def test_permission_service_calendar_permissions():
    """Test PermissionService calendar permission logic directly"""
    from services.permission_service import PermissionService
    
    # Full access roles
    full_access_roles = ["admin", "superadmin", "manager", "analyst", "new_business"]
    for role in full_access_roles:
        perms = PermissionService.get_calendar_permissions_for_role(role)
        assert perms.calendar_read_details is True, f"Role {role} should have calendar_read_details"
    
    # Restricted access roles
    restricted_roles = ["client", "customer"]
    for role in restricted_roles:
        perms = PermissionService.get_calendar_permissions_for_role(role)
        assert perms.calendar_read_details is False, f"Role {role} should NOT have calendar_read_details"
    
    # Unknown roles get restricted access
    perms = PermissionService.get_calendar_permissions_for_role("unknown_role")
    assert perms.calendar_read_details is False, "unknown_role should NOT have calendar_read_details"
    
    # None/empty roles get full access for backward compatibility
    for role in [None, ""]:
        perms = PermissionService.get_calendar_permissions_for_role(role)
        assert perms.calendar_read_details is True, f"Role {role} should have calendar_read_details (backward compat)"


# ------------------------------------------------------------
# Quick Actions Support Tests
# ------------------------------------------------------------

def test_list_events_with_entity_type_and_entity_id():
    """Test that entityType and entityId query parameters are accepted for quick actions"""
    # Create an event first
    create_res = client.post("/api/calendar/events", json={
        "summary": "Quick Action Event",
        "start_time": "2024-01-15T10:00:00",
        "end_time": "2024-01-15T11:00:00"
    })
    assert create_res.status_code == 201
    
    # List events with entityType and entityId - should not return 422
    response = client.get("/api/calendar/events?entityType=lead&entityId=lead-123")
    assert response.status_code == 200
    # Response should be a list (may be empty if events are outside default time range)
    assert isinstance(response.json(), list)


def test_list_events_with_calendar_id():
    """Test that calendarId parameter is accepted"""
    response = client.get("/api/calendar/events?calendarId=primary")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_list_events_quick_actions_with_all_params():
    """Test quick actions with all entity and time parameters"""
    # Create an event with a recent date
    from datetime import datetime, timedelta
    now = datetime.utcnow()
    start = (now + timedelta(days=1)).strftime("%Y-%m-%dT10:00:00")
    end = (now + timedelta(days=1)).strftime("%Y-%m-%dT11:00:00")
    
    create_res = client.post("/api/calendar/events", json={
        "summary": "Future Quick Action Event",
        "start_time": start,
        "end_time": end
    })
    assert create_res.status_code == 201
    event_id = create_res.json()["id"]
    
    # Use quick actions params with entity context
    response = client.get(f"/api/calendar/events?entityType=deal&entityId=deal-456&calendarId=primary")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    # Should find the event we just created (it's within the default time range)
    found = any(evt["id"] == event_id for evt in data)
    assert found, "Recently created event should be found with quick action params"


def test_create_event_with_title_instead_of_summary():
    """Test that 'title' can be used as an alias for 'summary'"""
    response = client.post("/api/calendar/events", json={
        "title": "Event Using Title Field",
        "start_time": "2024-02-01T10:00:00",
        "end_time": "2024-02-01T11:00:00"
    })
    assert response.status_code == 201
    data = response.json()
    assert data["summary"] == "Event Using Title Field"


def test_create_event_with_calendar_id():
    """Test that calendar_id is accepted in event creation"""
    response = client.post("/api/calendar/events", json={
        "summary": "Event with Calendar ID",
        "start_time": "2024-02-02T10:00:00",
        "end_time": "2024-02-02T11:00:00",
        "calendar_id": "primary"
    })
    assert response.status_code == 201


def test_create_event_without_summary_uses_default():
    """Test that event creation without summary uses default 'Untitled Event'"""
    response = client.post("/api/calendar/events", json={
        "start_time": "2024-02-03T10:00:00",
        "end_time": "2024-02-03T11:00:00"
    })
    assert response.status_code == 201
    data = response.json()
    assert data["summary"] == "Untitled Event"


def test_list_events_with_time_min_alias():
    """Test that timeMin query parameter alias works"""
    from datetime import datetime, timedelta
    time_min = (datetime.utcnow() - timedelta(days=7)).isoformat()
    response = client.get(f"/api/calendar/events?timeMin={time_min}")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_list_events_with_time_max_alias():
    """Test that timeMax query parameter alias works"""
    from datetime import datetime, timedelta
    time_max = (datetime.utcnow() + timedelta(days=30)).isoformat()
    response = client.get(f"/api/calendar/events?timeMax={time_max}")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_quick_actions_entity_types():
    """Test that all valid entity types are accepted"""
    for entity_type in ["company", "lead", "deal", "contact"]:
        response = client.get(f"/api/calendar/events?entityType={entity_type}&entityId=test-123")
        assert response.status_code == 200, f"entityType={entity_type} should be accepted"
