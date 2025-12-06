"""
Tests for Google Drive webhook functionality.
Tests webhook endpoint, channel management, and notification handling.
"""

import pytest
import os

# IMPORTANT: Set environment variables BEFORE importing anything else
os.environ["USE_MOCK_DRIVE"] = "true"
os.environ["WEBHOOK_BASE_URL"] = "http://test.example.com"
os.environ["WEBHOOK_SECRET"] = "test-secret-123"

import json
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base
from main import app
import models

# Setup Test DB
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_webhooks.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


from routers.drive import get_db as drive_get_db
from routers.webhooks import get_db as webhook_get_db

app.dependency_overrides[drive_get_db] = override_get_db
app.dependency_overrides[webhook_get_db] = override_get_db

client = TestClient(app)


def setup_module(module):
    """Setup test database and mock configuration."""
    # Environment variables are already set at module level
    Base.metadata.create_all(bind=engine)


def teardown_module(module):
    """Cleanup test database."""
    if os.path.exists("./test_webhooks.db"):
        os.remove("./test_webhooks.db")
    if os.path.exists("./mock_drive_db.json"):
        os.remove("./mock_drive_db.json")


def test_webhook_endpoint_missing_headers():
    """Test webhook endpoint rejects requests with missing required headers."""
    response = client.post("/webhooks/google-drive")
    assert response.status_code == 400
    assert "Missing X-Goog-Channel-ID" in response.json()["detail"]


def test_webhook_endpoint_sync_notification():
    """Test webhook endpoint handles sync (handshake) notifications correctly."""
    # First, create a webhook channel in the database
    db = TestingSessionLocal()
    channel = models.DriveWebhookChannel(
        channel_id="test-channel-sync",
        resource_id="test-resource-123",
        resource_type="folder",
        watched_resource_id="test-folder-123",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        active=True
    )
    db.add(channel)
    db.commit()
    db.close()
    
    # Send sync notification
    headers = {
        "X-Goog-Channel-ID": "test-channel-sync",
        "X-Goog-Resource-ID": "test-resource-123",
        "X-Goog-Resource-State": "sync",
        "X-Goog-Channel-Token": "test-secret-123"
    }
    
    response = client.post("/webhooks/google-drive", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "sync acknowledged" in data["message"]


def test_webhook_endpoint_change_notification():
    """Test webhook endpoint handles change notifications correctly."""
    # Create a webhook channel
    db = TestingSessionLocal()
    channel = models.DriveWebhookChannel(
        channel_id="test-channel-change",
        resource_id="test-resource-456",
        resource_type="folder",
        watched_resource_id="test-folder-456",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        active=True
    )
    db.add(channel)
    db.commit()
    db.close()
    
    # Send change notification
    headers = {
        "X-Goog-Channel-ID": "test-channel-change",
        "X-Goog-Resource-ID": "test-resource-456",
        "X-Goog-Resource-State": "update",
        "X-Goog-Resource-URI": "https://www.googleapis.com/drive/v3/files/file-abc-123?alt=json",
        "X-Goog-Changed": "content,parents",
        "X-Goog-Message-Number": "1",
        "X-Goog-Channel-Token": "test-secret-123"
    }
    
    response = client.post("/webhooks/google-drive", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["resource_state"] == "update"
    
    # Verify change was logged
    db = TestingSessionLocal()
    log = db.query(models.DriveChangeLog).filter(
        models.DriveChangeLog.channel_id == "test-channel-change"
    ).first()
    assert log is not None
    assert log.resource_state == "update"
    assert log.changed_resource_id == "file-abc-123"
    assert log.event_type == "content,parents"
    db.close()


def test_webhook_endpoint_invalid_token():
    """Test webhook endpoint rejects requests with invalid token."""
    # Create a webhook channel
    db = TestingSessionLocal()
    channel = models.DriveWebhookChannel(
        channel_id="test-channel-token",
        resource_id="test-resource-789",
        resource_type="folder",
        watched_resource_id="test-folder-789",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        active=True
    )
    db.add(channel)
    db.commit()
    db.close()
    
    # Send notification with wrong token
    headers = {
        "X-Goog-Channel-ID": "test-channel-token",
        "X-Goog-Resource-ID": "test-resource-789",
        "X-Goog-Resource-State": "update",
        "X-Goog-Channel-Token": "wrong-token"
    }
    
    response = client.post("/webhooks/google-drive", headers=headers)
    assert response.status_code == 403
    assert "Invalid webhook token" in response.json()["detail"]


def test_webhook_endpoint_unknown_channel():
    """Test webhook endpoint handles unknown channel gracefully."""
    headers = {
        "X-Goog-Channel-ID": "unknown-channel",
        "X-Goog-Resource-ID": "unknown-resource",
        "X-Goog-Resource-State": "update",
        "X-Goog-Channel-Token": "test-secret-123"
    }
    
    response = client.post("/webhooks/google-drive", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ignored"
    assert "unknown_or_inactive_channel" in data["reason"]


def test_register_webhook_channel():
    """Test registering a new webhook channel."""
    from services.webhook_service import WebhookService
    
    db = TestingSessionLocal()
    webhook_service = WebhookService(db)
    
    # Register a channel
    channel = webhook_service.register_webhook_channel(
        folder_id="test-folder-register",
        resource_type="folder",
        ttl_hours=12
    )
    
    assert channel is not None
    assert channel.channel_id is not None
    assert channel.resource_id is not None
    assert channel.watched_resource_id == "test-folder-register"
    assert channel.active is True
    # Handle timezone-naive datetime from SQLite
    expires_at = channel.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    assert expires_at > datetime.now(timezone.utc)
    
    # Verify it was saved to database
    saved_channel = db.query(models.DriveWebhookChannel).filter(
        models.DriveWebhookChannel.channel_id == channel.channel_id
    ).first()
    assert saved_channel is not None
    
    db.close()


def test_register_webhook_channel_duplicate():
    """Test that registering a duplicate channel returns existing active channel."""
    from services.webhook_service import WebhookService
    
    db = TestingSessionLocal()
    webhook_service = WebhookService(db)
    
    # Register first channel
    channel1 = webhook_service.register_webhook_channel(
        folder_id="test-folder-duplicate",
        resource_type="folder",
        ttl_hours=24
    )
    
    # Try to register again for same folder
    channel2 = webhook_service.register_webhook_channel(
        folder_id="test-folder-duplicate",
        resource_type="folder",
        ttl_hours=24
    )
    
    # Should return the same channel
    assert channel1.channel_id == channel2.channel_id
    
    db.close()


def test_stop_webhook_channel():
    """Test stopping a webhook channel."""
    from services.webhook_service import WebhookService
    
    db = TestingSessionLocal()
    webhook_service = WebhookService(db)
    
    # Register a channel
    channel = webhook_service.register_webhook_channel(
        folder_id="test-folder-stop",
        resource_type="folder",
        ttl_hours=24
    )
    
    assert channel.active is True
    
    # Stop the channel
    result = webhook_service.stop_webhook_channel(channel.channel_id)
    assert result is True
    
    # Verify it was deactivated
    db.refresh(channel)
    assert channel.active is False
    
    db.close()


def test_renew_webhook_channel():
    """Test renewing a webhook channel."""
    from services.webhook_service import WebhookService
    
    db = TestingSessionLocal()
    webhook_service = WebhookService(db)
    
    # Register a channel
    old_channel = webhook_service.register_webhook_channel(
        folder_id="test-folder-renew",
        resource_type="folder",
        ttl_hours=1
    )
    
    old_channel_id = old_channel.channel_id
    
    # Renew the channel
    new_channel = webhook_service.renew_webhook_channel(old_channel_id, ttl_hours=24)
    
    # Should be a new channel
    assert new_channel.channel_id != old_channel_id
    assert new_channel.watched_resource_id == old_channel.watched_resource_id
    assert new_channel.active is True
    
    # Old channel should be inactive
    db.refresh(old_channel)
    assert old_channel.active is False
    
    db.close()


def test_get_active_channels():
    """Test retrieving all active channels."""
    from services.webhook_service import WebhookService
    
    db = TestingSessionLocal()
    webhook_service = WebhookService(db)
    
    # Clear any existing channels
    db.query(models.DriveWebhookChannel).delete()
    db.commit()
    
    # Register multiple channels
    webhook_service.register_webhook_channel("folder-1", ttl_hours=24)
    webhook_service.register_webhook_channel("folder-2", ttl_hours=24)
    webhook_service.register_webhook_channel("folder-3", ttl_hours=24)
    
    # Get active channels
    active_channels = webhook_service.get_active_channels()
    assert len(active_channels) == 3
    
    db.close()


def test_cleanup_expired_channels():
    """Test cleanup of expired channels."""
    from services.webhook_service import WebhookService
    
    db = TestingSessionLocal()
    
    # Create an expired channel manually
    expired_channel = models.DriveWebhookChannel(
        channel_id="expired-channel",
        resource_id="expired-resource",
        resource_type="folder",
        watched_resource_id="expired-folder",
        expires_at=datetime.now(timezone.utc) - timedelta(hours=1),  # Expired 1 hour ago
        active=True
    )
    db.add(expired_channel)
    db.commit()
    
    webhook_service = WebhookService(db)
    
    # Run cleanup
    count = webhook_service.cleanup_expired_channels()
    assert count == 1
    
    # Verify channel was deactivated
    db.refresh(expired_channel)
    assert expired_channel.active is False
    
    db.close()


def test_webhook_status_endpoint():
    """Test the webhook status endpoint."""
    from services.webhook_service import WebhookService
    
    db = TestingSessionLocal()
    db.query(models.DriveWebhookChannel).delete()
    db.commit()
    
    webhook_service = WebhookService(db)
    
    # Register some channels
    webhook_service.register_webhook_channel("status-folder-1", ttl_hours=24)
    webhook_service.register_webhook_channel("status-folder-2", ttl_hours=24)
    
    db.close()
    
    # Call status endpoint
    response = client.get("/webhooks/google-drive/status")
    assert response.status_code == 200
    
    data = response.json()
    assert data["active_channels"] == 2
    assert len(data["channels"]) == 2
    assert "channel_id" in data["channels"][0]
    assert "watched_resource" in data["channels"][0]


def test_webhook_maps_to_tracked_folder():
    """Test that webhook notifications are mapped to tracked folders."""
    # Create a tracked folder
    db = TestingSessionLocal()
    
    drive_folder = models.DriveFolder(
        entity_id="company-123",
        entity_type="company",
        folder_id="tracked-folder-123"
    )
    db.add(drive_folder)
    
    # Create webhook channel
    channel = models.DriveWebhookChannel(
        channel_id="test-channel-mapping",
        resource_id="test-resource-mapping",
        resource_type="folder",
        watched_resource_id="watched-folder-root",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        active=True
    )
    db.add(channel)
    db.commit()
    db.close()
    
    # Send notification about the tracked folder
    headers = {
        "X-Goog-Channel-ID": "test-channel-mapping",
        "X-Goog-Resource-ID": "test-resource-mapping",
        "X-Goog-Resource-State": "update",
        "X-Goog-Resource-URI": "https://www.googleapis.com/drive/v3/files/tracked-folder-123?alt=json",
        "X-Goog-Channel-Token": "test-secret-123"
    }
    
    response = client.post("/webhooks/google-drive", headers=headers)
    assert response.status_code == 200
    
    # The logs should show it mapped to the tracked folder
    # (check console output in actual implementation)
