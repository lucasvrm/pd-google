
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
    response = client.post("/calendar/events", json={
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
    response = client.get("/calendar/events")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert data[0]["summary"] == "Test Meeting"

def test_update_event():
    # First create an event to update
    create_res = client.post("/calendar/events", json={
        "summary": "To Update",
        "start_time": "2023-10-28T10:00:00",
        "end_time": "2023-10-28T11:00:00"
    })
    event_id = create_res.json()["id"]

    # Update it
    response = client.patch(f"/calendar/events/{event_id}", json={
        "summary": "Updated Title"
    })

    assert response.status_code == 200

    # Verify in list
    get_res = client.get("/calendar/events")
    found = False
    for evt in get_res.json():
        if evt["id"] == event_id:
            assert evt["summary"] == "Updated Title"
            found = True
    assert found

def test_delete_event():
    # Create event to delete
    create_res = client.post("/calendar/events", json={
        "summary": "To Delete",
        "start_time": "2023-10-29T10:00:00",
        "end_time": "2023-10-29T11:00:00"
    })
    event_id = create_res.json()["id"]

    # Delete it
    response = client.delete(f"/calendar/events/{event_id}")
    assert response.status_code == 200

    # Verify status is cancelled in DB (Soft Delete behavior in router)
    # The router code says: db_event.status = 'cancelled'

    # Let's verify via GET
    # The GET endpoint filters out cancelled events:
    # query = db.query(models.CalendarEvent).filter(models.CalendarEvent.status != 'cancelled')

    get_res = client.get("/calendar/events")
    for evt in get_res.json():
        assert evt["id"] != event_id

def test_watch_calendar():
    response = client.post("/calendar/watch")
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "watching"
    assert data["channel_id"] is not None
    assert data["resource_id"] == "res-mock-123"

def test_get_event_by_id():
    """Test retrieving a specific event by its ID"""
    # Create an event first
    create_res = client.post("/calendar/events", json={
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
    response = client.get(f"/calendar/events/{event_id}")
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
    response = client.get("/calendar/events/999999")
    assert response.status_code == 404

def test_list_events_with_pagination():
    """Test listing events with pagination parameters"""
    # Create multiple events
    for i in range(5):
        client.post("/calendar/events", json={
            "summary": f"Event {i}",
            "start_time": f"2023-11-{10+i:02d}T10:00:00",
            "end_time": f"2023-11-{10+i:02d}T11:00:00"
        })
    
    # Test with limit
    response = client.get("/calendar/events?limit=3")
    assert response.status_code == 200
    data = response.json()
    assert len(data) <= 3
    
    # Test with offset
    response = client.get("/calendar/events?limit=2&offset=2")
    assert response.status_code == 200
    data = response.json()
    assert len(data) <= 2

def test_list_events_with_status_filter():
    """Test filtering events by status"""
    # Create and then cancel an event
    create_res = client.post("/calendar/events", json={
        "summary": "Event to Cancel",
        "start_time": "2023-11-20T10:00:00",
        "end_time": "2023-11-20T11:00:00"
    })
    event_id = create_res.json()["id"]
    client.delete(f"/calendar/events/{event_id}")
    
    # List without filter should not include cancelled
    response = client.get("/calendar/events")
    assert response.status_code == 200
    for evt in response.json():
        assert evt["status"] != "cancelled"
    
    # List with cancelled filter should include it
    response = client.get("/calendar/events?status=cancelled")
    assert response.status_code == 200
    cancelled_events = response.json()
    assert any(evt["id"] == event_id for evt in cancelled_events)

def test_update_event_with_attendees():
    """Test updating event with new attendees"""
    # Create event
    create_res = client.post("/calendar/events", json={
        "summary": "Meeting",
        "start_time": "2023-11-25T10:00:00",
        "end_time": "2023-11-25T11:00:00",
        "attendees": ["user1@example.com"]
    })
    event_id = create_res.json()["id"]
    
    # Update with new attendees
    response = client.patch(f"/calendar/events/{event_id}", json={
        "attendees": ["user1@example.com", "user2@example.com", "user3@example.com"]
    })
    assert response.status_code == 200
    data = response.json()
    assert len(data["attendees"]) == 3

def test_event_response_includes_all_fields():
    """Test that event responses include all required fields"""
    response = client.post("/calendar/events", json={
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
