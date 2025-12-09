"""
Tests for calendar event cleanup job.
"""

import pytest
import os
from datetime import datetime, timedelta, timezone

# Set env before imports
os.environ["USE_MOCK_DRIVE"] = "true"
os.environ["CALENDAR_EVENT_RETENTION_DAYS"] = "180"

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base
import models
from services.scheduler_service import SchedulerService

# Setup Test DB
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_cleanup.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def setup_module(module):
    """Setup test database."""
    Base.metadata.create_all(bind=engine)


def teardown_module(module):
    """Cleanup test database."""
    if os.path.exists("./test_cleanup.db"):
        os.remove("./test_cleanup.db")


def test_cleanup_old_events():
    """Test that old events are marked as cancelled."""
    db = TestingSessionLocal()
    
    # Clear any existing events
    db.query(models.CalendarEvent).delete()
    db.commit()
    
    # Create events at different ages
    now = datetime.now(timezone.utc)
    
    # Recent event (30 days old) - should NOT be cleaned
    recent_event = models.CalendarEvent(
        google_event_id="recent-event",
        summary="Recent Event",
        start_time=now - timedelta(days=30),
        end_time=now - timedelta(days=30, hours=-1),
        status="confirmed"
    )
    db.add(recent_event)
    
    # Old event (200 days old) - SHOULD be cleaned
    old_event = models.CalendarEvent(
        google_event_id="old-event",
        summary="Old Event",
        start_time=now - timedelta(days=200),
        end_time=now - timedelta(days=200, hours=-1),
        status="confirmed"
    )
    db.add(old_event)
    
    # Very old event (365 days old) - SHOULD be cleaned
    very_old_event = models.CalendarEvent(
        google_event_id="very-old-event",
        summary="Very Old Event",
        start_time=now - timedelta(days=365),
        end_time=now - timedelta(days=365, hours=-1),
        status="confirmed"
    )
    db.add(very_old_event)
    
    # Already cancelled event (should not be double-processed)
    cancelled_event = models.CalendarEvent(
        google_event_id="cancelled-event",
        summary="Cancelled Event",
        start_time=now - timedelta(days=250),
        end_time=now - timedelta(days=250, hours=-1),
        status="cancelled"
    )
    db.add(cancelled_event)
    
    db.commit()
    
    # Run cleanup job
    scheduler = SchedulerService()
    count = scheduler.cleanup_old_calendar_events(db)
    
    # Should have cleaned up 2 events (old_event and very_old_event)
    assert count == 2
    
    # Verify the events
    db.refresh(recent_event)
    db.refresh(old_event)
    db.refresh(very_old_event)
    db.refresh(cancelled_event)
    
    # Recent event should still be confirmed
    assert recent_event.status == "confirmed"
    
    # Old events should be cancelled
    assert old_event.status == "cancelled"
    assert very_old_event.status == "cancelled"
    
    # Already cancelled event should remain cancelled
    assert cancelled_event.status == "cancelled"
    
    db.close()


def test_cleanup_with_no_old_events():
    """Test cleanup when there are no old events."""
    db = TestingSessionLocal()
    
    # Clear any existing events
    db.query(models.CalendarEvent).delete()
    db.commit()
    
    # Create only recent events
    now = datetime.now(timezone.utc)
    
    for i in range(5):
        event = models.CalendarEvent(
            google_event_id=f"recent-event-{i}",
            summary=f"Recent Event {i}",
            start_time=now - timedelta(days=i * 10),
            end_time=now - timedelta(days=i * 10, hours=-1),
            status="confirmed"
        )
        db.add(event)
    
    db.commit()
    
    # Run cleanup job
    scheduler = SchedulerService()
    count = scheduler.cleanup_old_calendar_events(db)
    
    # Should have cleaned up 0 events
    assert count == 0
    
    # Verify all events are still confirmed
    events = db.query(models.CalendarEvent).all()
    assert len(events) == 5
    for event in events:
        assert event.status == "confirmed"
    
    db.close()


def test_cleanup_respects_retention_period():
    """Test that cleanup respects the configured retention period."""
    db = TestingSessionLocal()
    
    # Clear any existing events
    db.query(models.CalendarEvent).delete()
    db.commit()
    
    # Create event exactly at retention boundary (180 days)
    now = datetime.now(timezone.utc)
    
    # Event ending 179 days ago (within retention) - should NOT be cleaned
    recent_within_retention = models.CalendarEvent(
        google_event_id="recent-within-retention",
        summary="Recent Within Retention",
        start_time=now - timedelta(days=179, hours=1),
        end_time=now - timedelta(days=179),
        status="confirmed"
    )
    db.add(recent_within_retention)
    
    # Event ending 181 days ago (outside retention) - SHOULD be cleaned
    past_retention = models.CalendarEvent(
        google_event_id="past-retention",
        summary="Past Retention",
        start_time=now - timedelta(days=181, hours=1),
        end_time=now - timedelta(days=181),
        status="confirmed"
    )
    db.add(past_retention)
    
    db.commit()
    
    # Run cleanup job
    scheduler = SchedulerService()
    count = scheduler.cleanup_old_calendar_events(db)
    
    # Should have cleaned up 1 event (past_retention)
    assert count == 1
    
    # Verify
    db.refresh(recent_within_retention)
    db.refresh(past_retention)
    
    # Recent event within retention should still be confirmed
    assert recent_within_retention.status == "confirmed"
    
    # Event past retention should be cancelled
    assert past_retention.status == "cancelled"
    
    db.close()
