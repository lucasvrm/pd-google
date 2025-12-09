"""
Tests for health check endpoints.
"""

import pytest
import os
from datetime import datetime, timedelta, timezone

# Set env before imports
os.environ["USE_MOCK_DRIVE"] = "true"

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base
from main import app
import models
from services.health_service import HealthService

# Setup Test DB
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_health.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


from routers.health import get_db as health_get_db
app.dependency_overrides[health_get_db] = override_get_db

client = TestClient(app)


@pytest.fixture(autouse=True)
def mock_health_connectivity(monkeypatch):
    """Avoid external API calls during health tests by mocking connectivity checks."""
    monkeypatch.setattr(
        HealthService,
        "_check_calendar_connectivity",
        lambda self: {"reachable": True, "detail": "mock"},
    )
    monkeypatch.setattr(
        HealthService,
        "_check_gmail_connectivity",
        lambda self: {"reachable": True, "auth_ok": True, "detail": "mock"},
    )
    yield


def setup_module(module):
    """Setup test database."""
    Base.metadata.create_all(bind=engine)


def teardown_module(module):
    """Cleanup test database."""
    if os.path.exists("./test_health.db"):
        os.remove("./test_health.db")


def test_health_check_with_active_channels():
    """Test health check when system has active channels and events."""
    db = TestingSessionLocal()
    
    # Clear existing data
    db.query(models.CalendarEvent).delete()
    db.query(models.CalendarSyncState).delete()
    db.commit()
    
    # Create an active channel
    now = datetime.now(timezone.utc)
    channel = models.CalendarSyncState(
        channel_id="test-channel-health",
        resource_id="test-resource",
        calendar_id="primary",
        expiration=now + timedelta(hours=24),
        active=True,
        updated_at=now
    )
    db.add(channel)
    
    # Create some events
    for i in range(5):
        event = models.CalendarEvent(
            google_event_id=f"event-{i}",
            summary=f"Test Event {i}",
            start_time=now + timedelta(days=i),
            end_time=now + timedelta(days=i, hours=1),
            status="confirmed"
        )
        db.add(event)
    
    db.commit()
    db.close()
    
    # Call health check
    response = client.get("/health/calendar")
    assert response.status_code == 200
    
    data = response.json()
    assert data["service"] == "calendar"
    assert data["status"] == "healthy"
    assert data["active_channels"] == 1
    assert data["event_count"] == 5
    assert data["last_sync"] is not None
    assert data["oldest_event"] is not None
    assert data["newest_event"] is not None
    assert "webhook_queue" in data
    assert "issues" not in data


def test_health_check_with_no_channels():
    """Test health check when there are no active channels."""
    db = TestingSessionLocal()
    
    # Clear existing data
    db.query(models.CalendarEvent).delete()
    db.query(models.CalendarSyncState).delete()
    db.commit()
    
    # Create some events but no channels
    now = datetime.now(timezone.utc)
    event = models.CalendarEvent(
        google_event_id="event-no-channel",
        summary="Test Event",
        start_time=now,
        end_time=now + timedelta(hours=1),
        status="confirmed"
    )
    db.add(event)
    db.commit()
    db.close()
    
    # Call health check
    response = client.get("/health/calendar")
    assert response.status_code == 200
    
    data = response.json()
    assert data["service"] == "calendar"
    assert data["status"] == "degraded"
    assert data["active_channels"] == 0
    assert data["event_count"] == 1
    assert "No active webhook channels" in data["issues"]


def test_health_check_with_expired_channels():
    """Test health check when channels are expired."""
    db = TestingSessionLocal()
    
    # Clear existing data
    db.query(models.CalendarEvent).delete()
    db.query(models.CalendarSyncState).delete()
    db.commit()
    
    # Create an expired channel
    now = datetime.now(timezone.utc)
    channel = models.CalendarSyncState(
        channel_id="test-channel-expired",
        resource_id="test-resource-expired",
        calendar_id="primary",
        expiration=now - timedelta(hours=1),  # Expired 1 hour ago
        active=True,
        updated_at=now - timedelta(hours=2)
    )
    db.add(channel)
    db.commit()
    db.close()
    
    # Call health check
    response = client.get("/health/calendar")
    assert response.status_code == 200
    
    data = response.json()
    assert data["service"] == "calendar"
    assert data["status"] == "degraded"
    assert data["active_channels"] == 0  # Expired channels are not counted
    assert "No active webhook channels" in data["issues"]


def test_health_check_with_empty_system():
    """Test health check when system has no data."""
    db = TestingSessionLocal()
    
    # Clear all data
    db.query(models.CalendarEvent).delete()
    db.query(models.CalendarSyncState).delete()
    db.commit()
    db.close()
    
    # Call health check
    response = client.get("/health/calendar")
    assert response.status_code == 200
    
    data = response.json()
    assert data["service"] == "calendar"
    assert data["status"] == "degraded"
    assert data["active_channels"] == 0
    assert data["event_count"] == 0
    assert data["last_sync"] is None
    assert data["oldest_event"] is None
    assert data["newest_event"] is None
    assert len(data["issues"]) >= 2  # At least "No active channels" and "No sync activity"


def test_health_check_excludes_cancelled_events():
    """Test that health check doesn't count cancelled events."""
    db = TestingSessionLocal()
    
    # Clear existing data
    db.query(models.CalendarEvent).delete()
    db.query(models.CalendarSyncState).delete()
    db.commit()
    
    # Create active channel
    now = datetime.now(timezone.utc)
    channel = models.CalendarSyncState(
        channel_id="test-channel-cancelled",
        resource_id="test-resource-cancelled",
        calendar_id="primary",
        expiration=now + timedelta(hours=24),
        active=True,
        updated_at=now
    )
    db.add(channel)
    
    # Create mix of confirmed and cancelled events
    for i in range(3):
        event = models.CalendarEvent(
            google_event_id=f"confirmed-event-{i}",
            summary=f"Confirmed Event {i}",
            start_time=now + timedelta(days=i),
            end_time=now + timedelta(days=i, hours=1),
            status="confirmed"
        )
        db.add(event)
    
    for i in range(2):
        event = models.CalendarEvent(
            google_event_id=f"cancelled-event-{i}",
            summary=f"Cancelled Event {i}",
            start_time=now + timedelta(days=i + 10),
            end_time=now + timedelta(days=i + 10, hours=1),
            status="cancelled"
        )
        db.add(event)
    
    db.commit()
    db.close()
    
    # Call health check
    response = client.get("/health/calendar")
    assert response.status_code == 200
    
    data = response.json()
    assert data["service"] == "calendar"
    assert data["status"] == "healthy"
    assert data["event_count"] == 3  # Only confirmed events


# Gmail Health Check Tests

def test_gmail_health_check_healthy():
    """Test Gmail health check when service is properly configured."""
    # Note: This test uses mock credentials via environment variable
    response = client.get("/health/gmail")
    assert response.status_code == 200
    
    data = response.json()
    assert data["service"] == "gmail"
    assert "status" in data
    assert data["status"] in ["healthy", "degraded", "unhealthy"]
    assert "auth_ok" in data
    assert "api_reachable" in data
    assert "timestamp" in data
    assert "configured_scopes" in data
    
    # If credentials are configured correctly, auth should be OK
    if os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON"):
        assert isinstance(data["auth_ok"], bool)


def test_gmail_health_check_no_credentials(monkeypatch):
    """Test Gmail health check when credentials are missing."""
    monkeypatch.setattr(
        HealthService,
        "_check_gmail_connectivity",
        lambda self: {"reachable": False, "auth_ok": False, "detail": "missing credentials"},
    )

    response = client.get("/health/gmail")
    assert response.status_code == 200

    data = response.json()
    assert data["service"] == "gmail"
    assert data["status"] == "degraded"
    assert data["auth_ok"] is False
    assert "issues" in data
    assert any("credentials" in issue.lower() for issue in data["issues"])


def test_general_health_check():
    """Test general health check endpoint that aggregates all services."""
    response = client.get("/health")
    assert response.status_code == 200
    
    data = response.json()
    assert "overall_status" in data
    assert data["overall_status"] in ["healthy", "degraded", "unhealthy"]
    assert "timestamp" in data
    assert "services" in data
    
    # Check calendar service data
    assert "calendar" in data["services"]
    assert "status" in data["services"]["calendar"]
    
    # Check gmail service data
    assert "gmail" in data["services"]
    assert "status" in data["services"]["gmail"]
    assert "auth_ok" in data["services"]["gmail"]
    assert "api_reachable" in data["services"]["gmail"]


def test_general_health_status_aggregation():
    """Test that general health correctly aggregates service statuses."""
    # Clear calendar data to force degraded status
    db = TestingSessionLocal()
    db.query(models.CalendarEvent).delete()
    db.query(models.CalendarSyncState).delete()
    db.commit()
    db.close()
    
    response = client.get("/health")
    assert response.status_code == 200
    
    data = response.json()
    # With no calendar channels, calendar should be degraded
    # Overall status should reflect this
    assert data["services"]["calendar"]["status"] == "degraded"
    
    # Overall status should be at least degraded
    assert data["overall_status"] in ["degraded", "unhealthy"]
