
import pytest
import os
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base
import models
from routers.webhooks import sync_calendar_events

# 1. Setup Test DB
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_calendar_sync.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def setup_module(module):
    Base.metadata.create_all(bind=engine)

def teardown_module(module):
    if os.path.exists("./test_calendar_sync.db"):
        os.remove("./test_calendar_sync.db")

# 2. Mock Google Service
class MockGoogleService:
    def __init__(self):
        self.service = MagicMock()
        self.service.events.return_value.list.return_value.execute.return_value = {}

# 3. Tests

def test_sync_calendar_events_upsert():
    """
    Test that events are created/updated locally when Google returns them.
    """
    db = TestingSessionLocal()

    # Setup Channel
    channel = models.CalendarSyncState(
        channel_id="chan-1",
        calendar_id="primary",
        sync_token="old-token"
    )
    db.add(channel)
    db.commit()

    # Mock Service Response
    mock_service = MockGoogleService()
    mock_response = {
        "items": [
            {
                "id": "evt-1",
                "status": "confirmed",
                "summary": "New Meeting",
                "start": {"dateTime": "2023-11-01T10:00:00Z"},
                "end": {"dateTime": "2023-11-01T11:00:00Z"},
                "organizer": {"email": "boss@example.com"}
            }
        ],
        "nextSyncToken": "new-token"
    }
    mock_service.service.events.return_value.list.return_value.execute.return_value = mock_response

    # Execute Sync
    sync_calendar_events(db, mock_service, channel)

    # Verify Channel Update
    db.refresh(channel)
    assert channel.sync_token == "new-token"

    # Verify Event Creation
    event = db.query(models.CalendarEvent).filter_by(google_event_id="evt-1").first()
    assert event is not None
    assert event.summary == "New Meeting"
    assert event.status == "confirmed"

    # Test Update
    mock_response_update = {
        "items": [
            {
                "id": "evt-1",
                "status": "confirmed",
                "summary": "Updated Meeting",
                # missing times should be handled safely if partial, but Google sends full resource usually
                "start": {"dateTime": "2023-11-01T10:00:00Z"},
                "end": {"dateTime": "2023-11-01T11:00:00Z"},
            }
        ],
        "nextSyncToken": "newer-token"
    }
    mock_service.service.events.return_value.list.return_value.execute.return_value = mock_response_update

    sync_calendar_events(db, mock_service, channel)

    db.refresh(event)
    assert event.summary == "Updated Meeting"
    assert channel.sync_token == "newer-token"

    db.close()

def test_sync_calendar_events_cancellation():
    """
    Test that cancelled events are marked correctly.
    """
    db = TestingSessionLocal()

    # Setup Event and Channel
    event = models.CalendarEvent(
        google_event_id="evt-cancel",
        summary="To Cancel",
        status="confirmed"
    )
    db.add(event)

    channel = models.CalendarSyncState(
        channel_id="chan-cancel",
        sync_token="token-1"
    )
    db.add(channel)
    db.commit()

    # Mock Response
    mock_service = MockGoogleService()
    mock_response = {
        "items": [
            {
                "id": "evt-cancel",
                "status": "cancelled"
            }
        ],
        "nextSyncToken": "token-2"
    }
    mock_service.service.events.return_value.list.return_value.execute.return_value = mock_response

    sync_calendar_events(db, mock_service, channel)

    db.refresh(event)
    assert event.status == "cancelled"

    db.close()

def test_sync_calendar_410_gone():
    """
    Test handling of 410 Gone (Invalid Sync Token).
    Should clear token and retry (we mock retry by checking calls).
    """
    db = TestingSessionLocal()

    channel = models.CalendarSyncState(
        channel_id="chan-410",
        sync_token="bad-token"
    )
    db.add(channel)
    db.commit()

    mock_service = MockGoogleService()

    # Define side effect: First call raises 410, Second call succeeds
    def side_effect(**kwargs):
        if kwargs.get('syncToken') == "bad_token" or kwargs.get('syncToken') == "bad-token":
            # Simulate 410 Exception
            raise Exception("HttpError 410 ... sync token is no longer valid")
        else:
            return {
                "items": [],
                "nextSyncToken": "fresh-token"
            }

    mock_service.service.events.return_value.list.return_value.execute.side_effect = side_effect

    sync_calendar_events(db, mock_service, channel)

    db.refresh(channel)
    # Token should be updated to "fresh-token"
    assert channel.sync_token == "fresh-token"

    db.close()

@patch("services.scheduler_service.GoogleCalendarService")
def test_scheduler_renew_logic(MockServiceClass):
    """
    Test the logic for finding and renewing expiring channels.
    """
    from services.scheduler_service import scheduler_service

    db = TestingSessionLocal()

    # Setup expiring channel
    expiring = models.CalendarSyncState(
        channel_id="expiring-chan",
        resource_id="res-1",
        expiration=datetime.now(timezone.utc) + timedelta(hours=1), # Expires soon
        active=True
    )
    db.add(expiring)
    db.commit()

    # Mock Service Instance
    mock_instance = MockServiceClass.return_value
    mock_instance.watch_events.return_value = {
        "resourceId": "res-new",
        "expiration": "1700000000000" # Dummy ms timestamp
    }

    # Inject mock into scheduler instance
    scheduler_service.calendar_service = mock_instance

    # Run renewal logic
    scheduler_service.renew_expiring_channels(db)

    # Verify DB update
    db.refresh(expiring)
    assert expiring.resource_id == "res-new"
    # assert expiring.channel_id != "expiring-chan" # It generates a new UUID

    # Verify Service Calls
    mock_instance.stop_channel.assert_called_with("expiring-chan", "res-1")
    mock_instance.watch_events.assert_called()

    db.close()
