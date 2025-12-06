"""
Router for handling Google Drive webhook notifications.
Receives and processes real-time change notifications from Google Drive.
"""

from fastapi import APIRouter, Request, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from database import SessionLocal
import models
from config import config
import json
from datetime import datetime, timezone
from typing import Optional

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/webhooks/google-drive")
async def receive_google_drive_webhook(
    request: Request,
    db: Session = Depends(get_db),
    x_goog_channel_id: Optional[str] = Header(None, alias="X-Goog-Channel-ID"),
    x_goog_channel_token: Optional[str] = Header(None, alias="X-Goog-Channel-Token"),
    x_goog_resource_id: Optional[str] = Header(None, alias="X-Goog-Resource-ID"),
    x_goog_resource_state: Optional[str] = Header(None, alias="X-Goog-Resource-State"),
    x_goog_resource_uri: Optional[str] = Header(None, alias="X-Goog-Resource-URI"),
    x_goog_message_number: Optional[str] = Header(None, alias="X-Goog-Message-Number"),
    x_goog_changed: Optional[str] = Header(None, alias="X-Goog-Changed"),
):
    """
    Endpoint to receive webhook notifications from Google Drive.
    
    Google Drive sends notifications with special headers:
    - X-Goog-Channel-ID: Unique channel identifier
    - X-Goog-Resource-ID: Unique resource identifier
    - X-Goog-Resource-State: Type of event (sync, add, remove, update, trash, untrash, change)
    - X-Goog-Resource-URI: URI of the resource being watched
    - X-Goog-Message-Number: Sequential message number
    - X-Goog-Channel-Token: Optional token for verification
    - X-Goog-Changed: Comma-separated list of changed properties
    
    States:
    - sync: Initial sync notification when channel is created
    - add/remove/update/change: File/folder modifications
    - trash/untrash: Trash operations
    """
    
    print(f"Received webhook notification: state={x_goog_resource_state}, channel={x_goog_channel_id}")
    
    # Validate required headers
    if not x_goog_channel_id:
        raise HTTPException(status_code=400, detail="Missing X-Goog-Channel-ID header")
    
    if not x_goog_resource_id:
        raise HTTPException(status_code=400, detail="Missing X-Goog-Resource-ID header")
    
    if not x_goog_resource_state:
        raise HTTPException(status_code=400, detail="Missing X-Goog-Resource-State header")
    
    # Verify channel exists and is active
    channel = db.query(models.DriveWebhookChannel).filter(
        models.DriveWebhookChannel.channel_id == x_goog_channel_id,
        models.DriveWebhookChannel.resource_id == x_goog_resource_id,
        models.DriveWebhookChannel.active == True
    ).first()
    
    if not channel:
        print(f"Warning: Received notification for unknown or inactive channel: {x_goog_channel_id}")
        # Return 200 to avoid Google retrying, but log the issue
        return {"status": "ignored", "reason": "unknown_or_inactive_channel"}
    
    # Verify token if configured
    if config.WEBHOOK_SECRET and x_goog_channel_token != config.WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="Invalid webhook token")
    
    # Handle sync notification (initial handshake)
    if x_goog_resource_state == "sync":
        print(f"Sync notification received for channel {x_goog_channel_id}")
        return {"status": "ok", "message": "sync acknowledged"}
    
    # Collect all headers for logging
    headers_dict = {
        "X-Goog-Channel-ID": x_goog_channel_id,
        "X-Goog-Resource-ID": x_goog_resource_id,
        "X-Goog-Resource-State": x_goog_resource_state,
        "X-Goog-Resource-URI": x_goog_resource_uri,
        "X-Goog-Message-Number": x_goog_message_number,
        "X-Goog-Changed": x_goog_changed,
    }
    
    # Extract changed resource ID from URI if available
    # The URI is typically: https://www.googleapis.com/drive/v3/files/{fileId}?alt=json
    changed_resource_id = None
    if x_goog_resource_uri:
        # Simple extraction - look for files/ in the URI
        if "/files/" in x_goog_resource_uri:
            parts = x_goog_resource_uri.split("/files/")
            if len(parts) > 1:
                # Extract file ID (remove query params)
                changed_resource_id = parts[1].split("?")[0]
    
    # Log the change event
    change_log = models.DriveChangeLog(
        channel_id=x_goog_channel_id,
        resource_id=x_goog_resource_id,
        resource_state=x_goog_resource_state,
        changed_resource_id=changed_resource_id,
        event_type=x_goog_changed,
        raw_headers=json.dumps(headers_dict),
        received_at=datetime.now(timezone.utc)
    )
    
    db.add(change_log)
    db.commit()
    
    print(f"Logged change event: {x_goog_resource_state} for resource {changed_resource_id or 'unknown'}")
    
    # Map to internal entities if possible
    # Find which DriveFolder/DriveFile this relates to
    if changed_resource_id:
        # Check if it's a folder we're tracking
        drive_folder = db.query(models.DriveFolder).filter(
            models.DriveFolder.folder_id == changed_resource_id
        ).first()
        
        if drive_folder:
            print(f"Change affects tracked folder: entity_type={drive_folder.entity_type}, entity_id={drive_folder.entity_id}")
        
        # Check if it's a file we're tracking
        drive_file = db.query(models.DriveFile).filter(
            models.DriveFile.file_id == changed_resource_id
        ).first()
        
        if drive_file:
            print(f"Change affects tracked file: {drive_file.name}")
    
    # Return success response
    return {
        "status": "ok",
        "message": "notification received and logged",
        "resource_state": x_goog_resource_state,
        "channel_id": x_goog_channel_id
    }


@router.get("/webhooks/google-drive/status")
def get_webhook_status(db: Session = Depends(get_db)):
    """
    Get status of all active webhook channels.
    Useful for monitoring and debugging.
    """
    from services.webhook_service import WebhookService
    
    webhook_service = WebhookService(db)
    active_channels = webhook_service.get_active_channels()
    
    return {
        "active_channels": len(active_channels),
        "channels": [
            {
                "channel_id": ch.channel_id,
                "watched_resource": ch.watched_resource_id,
                "resource_type": ch.resource_type,
                "expires_at": ch.expires_at.isoformat(),
                "created_at": ch.created_at.isoformat()
            }
            for ch in active_channels
        ]
    }
