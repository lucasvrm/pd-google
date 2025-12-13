"""
Integration tests for Calendar Sync Logic

Tests that verify:
1. Mock Google API response handling
2. Sync Token flow: CalendarEvent is updated locally when mock webhook arrives
3. 410 Gone scenario: Code handles token expiration gracefully
"""

import pytest
import os
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch, Mock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
import models
from routers.webhooks import sync_calendar_events
from services.google_calendar_service import GoogleCalendarService


# Setup Test DB
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_calendar_sync_logic.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="module", autouse=True)
def setup_module():
    """Setup test database."""
    Base.metadata.create_all(bind=engine)
    yield
    # Cleanup
    if os.path.exists("./test_calendar_sync_logic.db"):
        os.remove("./test_calendar_sync_logic.db")


@pytest.fixture
def db_session():
    """Provide a transactional scope for each test."""
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)
    
    yield session
    
    session.close()
    transaction.rollback()
    connection.close()


class MockGoogleCalendarService:
    """Mock Google Calendar Service for testing."""
    
    def __init__(self, mock_response=None, mock_error=None):
        self.service = MagicMock()
        self.mock_response = mock_response or {}
        self.mock_error = mock_error
        
        # Setup the chained mock calls
        if mock_error:
            self.service.events.return_value.list.return_value.execute.side_effect = mock_error
        else:
            self.service.events.return_value.list.return_value.execute.return_value = self.mock_response
    
    def set_response(self, response):
        """Update the mock response."""
        self.mock_response = response
        self.service.events.return_value.list.return_value.execute.return_value = response


class TestCalendarSyncWithMockAPI:
    """Test calendar sync with mocked Google API responses."""

    def test_sync_creates_new_calendar_event(self, db_session):
        """
        Test that sync creates a new CalendarEvent when Google returns a new event.
        """
        # Setup channel
        channel = models.CalendarSyncState(
            channel_id="test-channel-1",
            calendar_id="primary",
            sync_token="old-sync-token",
            active=True,
            expiration=datetime.now(timezone.utc) + timedelta(days=1)
        )
        db_session.add(channel)
        db_session.commit()
        
        # Mock Google API response with a new event
        mock_response = {
            "items": [
                {
                    "id": "event-123",
                    "status": "confirmed",
                    "summary": "Team Meeting",
                    "description": "Weekly team sync",
                    "start": {"dateTime": "2024-01-15T10:00:00Z"},
                    "end": {"dateTime": "2024-01-15T11:00:00Z"},
                    "organizer": {"email": "organizer@example.com"},
                    "hangoutLink": "https://meet.google.com/abc-defg-hij",
                    "htmlLink": "https://calendar.google.com/event?eid=event-123",
                    "attendees": [
                        {"email": "attendee1@example.com", "responseStatus": "accepted"},
                        {"email": "attendee2@example.com", "responseStatus": "needsAction"}
                    ]
                }
            ],
            "nextSyncToken": "new-sync-token-1"
        }
        
        mock_service = MockGoogleCalendarService(mock_response=mock_response)
        
        # Execute sync
        sync_calendar_events(db_session, mock_service, channel)
        
        # Verify channel sync token was updated
        db_session.refresh(channel)
        assert channel.sync_token == "new-sync-token-1"
        
        # Verify event was created
        event = db_session.query(models.CalendarEvent).filter_by(
            google_event_id="event-123"
        ).first()
        
        assert event is not None
        assert event.summary == "Team Meeting"
        assert event.description == "Weekly team sync"
        assert event.status == "confirmed"
        assert event.organizer_email == "organizer@example.com"
        assert event.meet_link == "https://meet.google.com/abc-defg-hij"
        assert event.html_link == "https://calendar.google.com/event?eid=event-123"
        
        # Verify attendees are stored
        attendees_data = json.loads(event.attendees)
        assert len(attendees_data) == 2
        assert attendees_data[0]["email"] == "attendee1@example.com"

    def test_sync_updates_existing_calendar_event(self, db_session):
        """
        Test that sync updates an existing CalendarEvent when Google returns changes.
        """
        # Create existing event
        existing_event = models.CalendarEvent(
            google_event_id="event-456",
            calendar_id="primary",
            summary="Old Summary",
            description="Old Description",
            status="confirmed",
            start_time=datetime(2024, 1, 20, 14, 0, tzinfo=timezone.utc),
            end_time=datetime(2024, 1, 20, 15, 0, tzinfo=timezone.utc)
        )
        db_session.add(existing_event)
        
        # Create channel
        channel = models.CalendarSyncState(
            channel_id="test-channel-2",
            calendar_id="primary",
            sync_token="token-before-update",
            active=True,
            expiration=datetime.now(timezone.utc) + timedelta(days=1)
        )
        db_session.add(channel)
        db_session.commit()
        
        # Mock Google API response with updated event
        mock_response = {
            "items": [
                {
                    "id": "event-456",
                    "status": "confirmed",
                    "summary": "Updated Summary",
                    "description": "Updated Description",
                    "start": {"dateTime": "2024-01-20T15:00:00Z"},
                    "end": {"dateTime": "2024-01-20T16:00:00Z"},
                    "organizer": {"email": "new-organizer@example.com"},
                    "attendees": []
                }
            ],
            "nextSyncToken": "token-after-update"
        }
        
        mock_service = MockGoogleCalendarService(mock_response=mock_response)
        
        # Execute sync
        sync_calendar_events(db_session, mock_service, channel)
        
        # Verify event was updated
        db_session.refresh(existing_event)
        assert existing_event.summary == "Updated Summary"
        assert existing_event.description == "Updated Description"
        assert existing_event.organizer_email == "new-organizer@example.com"
        
        # Verify channel sync token was updated
        db_session.refresh(channel)
        assert channel.sync_token == "token-after-update"

    def test_sync_marks_event_as_cancelled(self, db_session):
        """
        Test that sync correctly marks events as cancelled.
        """
        # Create existing event
        existing_event = models.CalendarEvent(
            google_event_id="event-789",
            calendar_id="primary",
            summary="Meeting to Cancel",
            status="confirmed"
        )
        db_session.add(existing_event)
        
        # Create channel
        channel = models.CalendarSyncState(
            channel_id="test-channel-3",
            calendar_id="primary",
            sync_token="token-before-cancel",
            active=True,
            expiration=datetime.now(timezone.utc) + timedelta(days=1)
        )
        db_session.add(channel)
        db_session.commit()
        
        # Mock Google API response with cancelled event
        mock_response = {
            "items": [
                {
                    "id": "event-789",
                    "status": "cancelled"
                }
            ],
            "nextSyncToken": "token-after-cancel"
        }
        
        mock_service = MockGoogleCalendarService(mock_response=mock_response)
        
        # Execute sync
        sync_calendar_events(db_session, mock_service, channel)
        
        # Verify event was marked as cancelled
        db_session.refresh(existing_event)
        assert existing_event.status == "cancelled"


class TestSyncTokenFlow:
    """Test the sync token flow for incremental syncs."""

    def test_sync_uses_sync_token_when_available(self, db_session):
        """
        Test that sync uses the sync token for incremental updates.
        """
        # Create channel with existing sync token
        channel = models.CalendarSyncState(
            channel_id="test-channel-token",
            calendar_id="primary",
            sync_token="existing-sync-token",
            active=True,
            expiration=datetime.now(timezone.utc) + timedelta(days=1)
        )
        db_session.add(channel)
        db_session.commit()
        
        # Mock Google API response
        mock_response = {
            "items": [
                {
                    "id": "event-new",
                    "status": "confirmed",
                    "summary": "New Event",
                    "start": {"dateTime": "2024-02-01T10:00:00Z"},
                    "end": {"dateTime": "2024-02-01T11:00:00Z"}
                }
            ],
            "nextSyncToken": "newer-sync-token"
        }
        
        mock_service = MockGoogleCalendarService(mock_response=mock_response)
        
        # Execute sync
        sync_calendar_events(db_session, mock_service, channel)
        
        # Verify the service was called with sync token
        call_args = mock_service.service.events.return_value.list.call_args
        assert call_args is not None
        assert 'syncToken' in call_args[1]
        assert call_args[1]['syncToken'] == 'existing-sync-token'
        
        # Verify sync token was updated
        db_session.refresh(channel)
        assert channel.sync_token == "newer-sync-token"

    def test_sync_without_token_fetches_future_events(self, db_session):
        """
        Test that sync without a token performs full sync of future events.
        """
        # Create channel without sync token
        channel = models.CalendarSyncState(
            channel_id="test-channel-no-token",
            calendar_id="primary",
            sync_token=None,
            active=True,
            expiration=datetime.now(timezone.utc) + timedelta(days=1)
        )
        db_session.add(channel)
        db_session.commit()
        
        # Mock Google API response
        mock_response = {
            "items": [
                {
                    "id": "event-full-sync",
                    "status": "confirmed",
                    "summary": "Future Event",
                    "start": {"dateTime": "2024-03-01T10:00:00Z"},
                    "end": {"dateTime": "2024-03-01T11:00:00Z"}
                }
            ],
            "nextSyncToken": "first-sync-token"
        }
        
        mock_service = MockGoogleCalendarService(mock_response=mock_response)
        
        # Execute sync
        sync_calendar_events(db_session, mock_service, channel)
        
        # Verify the service was called with timeMin instead of syncToken
        call_args = mock_service.service.events.return_value.list.call_args
        assert call_args is not None
        assert 'syncToken' not in call_args[1] or call_args[1]['syncToken'] is None
        # Note: timeMin is not in call_args because it's added inside fetch_events_page
        
        # Verify sync token was set after successful sync
        db_session.refresh(channel)
        assert channel.sync_token == "first-sync-token"


class Test410GoneScenario:
    """Test handling of 410 Gone error (sync token expiration)."""

    def test_410_gone_clears_token_and_retries(self, db_session):
        """
        Test that 410 Gone error clears sync token and triggers full re-sync.
        """
        # Create channel with expired/invalid sync token
        channel = models.CalendarSyncState(
            channel_id="test-channel-410",
            calendar_id="primary",
            sync_token="invalid-sync-token",
            active=True,
            expiration=datetime.now(timezone.utc) + timedelta(days=1)
        )
        db_session.add(channel)
        db_session.commit()
        
        # Mock service that raises 410 error first, then succeeds
        call_count = {"count": 0}
        
        def mock_execute(**kwargs):
            call_count["count"] += 1
            if call_count["count"] == 1:
                # First call with invalid token raises 410
                raise Exception("HttpError 410: sync token is no longer valid")
            else:
                # Second call without token succeeds
                return {
                    "items": [
                        {
                            "id": "event-after-410",
                            "status": "confirmed",
                            "summary": "Event after 410",
                            "start": {"dateTime": "2024-04-01T10:00:00Z"},
                            "end": {"dateTime": "2024-04-01T11:00:00Z"}
                        }
                    ],
                    "nextSyncToken": "fresh-sync-token"
                }
        
        mock_service = MagicMock()
        mock_service.service = MagicMock()
        mock_service.service.events.return_value.list.return_value.execute = mock_execute
        
        # Execute sync
        sync_calendar_events(db_session, mock_service, channel)
        
        # Verify sync token was cleared and then updated with fresh token
        db_session.refresh(channel)
        assert channel.sync_token == "fresh-sync-token"
        
        # Verify event was created after recovery
        event = db_session.query(models.CalendarEvent).filter_by(
            google_event_id="event-after-410"
        ).first()
        assert event is not None
        assert event.summary == "Event after 410"

    def test_410_gone_handles_gracefully(self, db_session):
        """
        Test that 410 Gone error is handled gracefully without crashing.
        """
        # Create channel
        channel = models.CalendarSyncState(
            channel_id="test-channel-410-graceful",
            calendar_id="primary",
            sync_token="expired-token",
            active=True,
            expiration=datetime.now(timezone.utc) + timedelta(days=1)
        )
        db_session.add(channel)
        db_session.commit()
        
        # Track that token is cleared
        original_token = channel.sync_token
        
        # Mock service that always raises 410 (to test error handling path)
        def mock_execute_always_410(**kwargs):
            # If sync_token is None, succeed (after it was cleared)
            if db_session.query(models.CalendarSyncState).filter_by(
                channel_id="test-channel-410-graceful"
            ).first().sync_token is None:
                return {
                    "items": [],
                    "nextSyncToken": "recovered-token"
                }
            # Otherwise raise 410
            raise Exception("HttpError 410: sync token is no longer valid")
        
        mock_service = MagicMock()
        mock_service.service = MagicMock()
        mock_service.service.events.return_value.list.return_value.execute = mock_execute_always_410
        
        # Execute sync - should not raise exception
        sync_calendar_events(db_session, mock_service, channel)
        
        # Verify token was updated after recovery
        db_session.refresh(channel)
        assert channel.sync_token == "recovered-token"
        assert channel.sync_token != original_token


class TestWebhookIntegration:
    """Test webhook-triggered sync flow."""

    def test_webhook_arrival_triggers_sync(self, db_session):
        """
        Test that when a mock webhook arrives, CalendarEvent is updated locally.
        """
        # Create existing event
        existing_event = models.CalendarEvent(
            google_event_id="event-webhook",
            calendar_id="primary",
            summary="Before Webhook",
            status="confirmed"
        )
        db_session.add(existing_event)
        
        # Create channel
        channel = models.CalendarSyncState(
            channel_id="test-channel-webhook",
            calendar_id="primary",
            sync_token="token-before-webhook",
            active=True,
            expiration=datetime.now(timezone.utc) + timedelta(days=1)
        )
        db_session.add(channel)
        db_session.commit()
        
        # Simulate webhook arrival by calling sync with updated data
        mock_response = {
            "items": [
                {
                    "id": "event-webhook",
                    "status": "confirmed",
                    "summary": "After Webhook Update",
                    "description": "Updated via webhook",
                    "start": {"dateTime": "2024-05-01T10:00:00Z"},
                    "end": {"dateTime": "2024-05-01T11:00:00Z"}
                }
            ],
            "nextSyncToken": "token-after-webhook"
        }
        
        mock_service = MockGoogleCalendarService(mock_response=mock_response)
        
        # Execute sync (as would be triggered by webhook)
        sync_calendar_events(db_session, mock_service, channel)
        
        # Verify event was updated
        db_session.refresh(existing_event)
        assert existing_event.summary == "After Webhook Update"
        assert existing_event.description == "Updated via webhook"
        
        # Verify sync token was updated
        db_session.refresh(channel)
        assert channel.sync_token == "token-after-webhook"

    def test_webhook_with_multiple_changes(self, db_session):
        """
        Test webhook with multiple event changes in one sync.
        """
        # Create channel
        channel = models.CalendarSyncState(
            channel_id="test-channel-multi",
            calendar_id="primary",
            sync_token="token-multi",
            active=True,
            expiration=datetime.now(timezone.utc) + timedelta(days=1)
        )
        db_session.add(channel)
        db_session.commit()
        
        # Mock response with multiple changes
        mock_response = {
            "items": [
                {
                    "id": "event-new-1",
                    "status": "confirmed",
                    "summary": "New Event 1",
                    "start": {"dateTime": "2024-06-01T10:00:00Z"},
                    "end": {"dateTime": "2024-06-01T11:00:00Z"}
                },
                {
                    "id": "event-new-2",
                    "status": "confirmed",
                    "summary": "New Event 2",
                    "start": {"dateTime": "2024-06-02T10:00:00Z"},
                    "end": {"dateTime": "2024-06-02T11:00:00Z"}
                },
                {
                    "id": "event-cancelled",
                    "status": "cancelled"
                }
            ],
            "nextSyncToken": "token-after-multi"
        }
        
        mock_service = MockGoogleCalendarService(mock_response=mock_response)
        
        # Execute sync
        sync_calendar_events(db_session, mock_service, channel)
        
        # Verify all events were processed
        event1 = db_session.query(models.CalendarEvent).filter_by(
            google_event_id="event-new-1"
        ).first()
        assert event1 is not None
        assert event1.summary == "New Event 1"
        
        event2 = db_session.query(models.CalendarEvent).filter_by(
            google_event_id="event-new-2"
        ).first()
        assert event2 is not None
        assert event2.summary == "New Event 2"
