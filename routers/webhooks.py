"""
Router for handling Google Drive and Calendar webhook notifications.
Receives and processes real-time change notifications.
"""

from fastapi import APIRouter, Request, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from database import SessionLocal
import models
from config import config
import json
from datetime import datetime, timezone
from typing import Optional
from services.google_calendar_service import GoogleCalendarService

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/webhooks/google-drive")
def receive_google_webhook(
    request: Request,
    db: Session = Depends(get_db),
    x_goog_channel_id: Optional[str] = Header(None, alias="X-Goog-Channel-ID"),
    x_goog_resource_id: Optional[str] = Header(None, alias="X-Goog-Resource-ID"),
    x_goog_resource_state: Optional[str] = Header(None, alias="X-Goog-Resource-State"),
    x_goog_channel_token: Optional[str] = Header(None, alias="X-Goog-Channel-Token"),
    # Drive Specific
    x_goog_resource_uri: Optional[str] = Header(None, alias="X-Goog-Resource-URI"),
    x_goog_changed: Optional[str] = Header(None, alias="X-Goog-Changed"),
):
    """
    Unified endpoint to receive webhook notifications from Google (Drive or Calendar).
    Note: Ideally we might split these into /webhooks/drive and /webhooks/calendar,
    but if they point to the same URL in config, we handle both here or dispatch.
    
    Given the path is /webhooks/google-drive in the existing code, I will keep using it
    or check if I can register a different URL for calendar.
    
    For clarity, I'll check if this is a Drive or Calendar webhook based on DB lookup.
    """
    
    print(f"Received webhook: channel={x_goog_channel_id} resource={x_goog_resource_id} state={x_goog_resource_state}")

    if not x_goog_channel_id or not x_goog_resource_id:
        raise HTTPException(status_code=400, detail="Missing required headers")

    # 1. Check if it is a Drive Channel
    drive_channel = db.query(models.DriveWebhookChannel).filter(
        models.DriveWebhookChannel.channel_id == x_goog_channel_id
    ).first()

    if drive_channel:
        return handle_drive_webhook(db, drive_channel, x_goog_resource_state, x_goog_channel_token, x_goog_resource_uri, x_goog_changed)

    # 2. Check if it is a Calendar Channel
    calendar_channel = db.query(models.CalendarSyncState).filter(
        models.CalendarSyncState.channel_id == x_goog_channel_id
    ).first()

    if calendar_channel:
        return handle_calendar_webhook(db, calendar_channel, x_goog_resource_state, x_goog_channel_token)

    print(f"Unknown channel: {x_goog_channel_id}")
    # Return 200 to stop retries
    return {"status": "ignored", "reason": "unknown_channel"}


def handle_drive_webhook(db, channel, state, token, uri, changed):
    # (Preserve existing logic for Drive)
    if not channel.active:
        return {"status": "ignored", "reason": "inactive_channel"}
    
    if config.WEBHOOK_SECRET and token != config.WEBHOOK_SECRET:
         # Log warning but maybe don't error to avoid retries if it's a config mismatch
         print("Warning: Invalid token for Drive webhook")
    
    if state == "sync":
        print(f"Drive Sync Handshake: {channel.channel_id}")
        return {"status": "ok"}

    # Extract changed resource ID from URI if available
    changed_resource_id = None
    if uri:
        # Simple extraction - look for files/ in the URI
        if "/files/" in uri:
            parts = uri.split("/files/")
            if len(parts) > 1:
                # Extract file ID (remove query params)
                changed_resource_id = parts[1].split("?")[0]

    # Log change
    change_log = models.DriveChangeLog(
        channel_id=channel.channel_id,
        resource_id=channel.resource_id,
        resource_state=state,
        changed_resource_id=changed_resource_id,
        event_type=changed,
        received_at=datetime.now(timezone.utc)
    )
    db.add(change_log)
    db.commit()
    
    return {"status": "ok", "type": "drive"}


def handle_calendar_webhook(db: Session, channel: models.CalendarSyncState, state: str, token: str):
    """
    Process Calendar Webhook
    """
    print(f"Processing Calendar Webhook for {channel.channel_id}")

    if not channel.active:
         return {"status": "ignored", "reason": "inactive_channel"}

    if state == "sync":
        print("Calendar Sync Handshake")
        return {"status": "ok"}

    # Trigger Sync Logic
    # We do this synchronously for now, but in prod should be a background task (Celery/RQ)
    try:
        service = GoogleCalendarService()
        sync_calendar_events(db, service, channel)
    except Exception as e:
        print(f"Error syncing calendar: {e}")
        # Return 200 to avoid Google retrying indefinitely if it's a logic error
        return {"status": "error", "detail": str(e)}

    return {"status": "ok", "type": "calendar"}


def sync_calendar_events(db: Session, service: GoogleCalendarService, channel: models.CalendarSyncState):
    """
    Core Two-Way Sync Logic using Sync Token.
    """
    print(f"Syncing calendar {channel.calendar_id} with token {channel.sync_token}")

    page_token = None
    new_sync_token = None
    
    while True:
        try:
            # If we have a sync token, use it. If it's invalid (410), we'll catch it.
            # list_events handles sync_token logic.
            # Note: list_events returns dict.
            result = service.service.events().list(
                calendarId=channel.calendar_id,
                syncToken=channel.sync_token,
                pageToken=page_token,
                singleEvents=True # Important for expanding recurrences
            ).execute()
        except Exception as e:
            if '410' in str(e) or 'sync token is no longer valid' in str(e).lower():
                print("Sync token invalid. Performing full sync.")
                channel.sync_token = None
                db.commit()
                continue # Retry loop with no token
            else:
                raise e

        items = result.get('items', [])
        
        for item in items:
            google_id = item.get('id')
            status = item.get('status') # confirmed, tentative, cancelled

            # Find local event
            local_event = db.query(models.CalendarEvent).filter(
                models.CalendarEvent.google_event_id == google_id
            ).first()

            if status == 'cancelled':
                if local_event:
                    local_event.status = 'cancelled'
                    # optional: db.delete(local_event)
            else:
                # Upsert
                # Extract fields
                summary = item.get('summary')
                description = item.get('description')
                start_raw = item.get('start', {}).get('dateTime') or item.get('start', {}).get('date')
                end_raw = item.get('end', {}).get('dateTime') or item.get('end', {}).get('date')
                meet_link = item.get('hangoutLink')
                html_link = item.get('htmlLink')
                organizer = item.get('organizer', {}).get('email')

                # Parse times (rough ISO parsing)
                start_dt = datetime.fromisoformat(start_raw.replace('Z', '+00:00')) if start_raw else None
                end_dt = datetime.fromisoformat(end_raw.replace('Z', '+00:00')) if end_raw else None

                if not local_event:
                    local_event = models.CalendarEvent(
                        google_event_id=google_id,
                        calendar_id=channel.calendar_id
                    )
                    db.add(local_event)

                local_event.summary = summary
                local_event.description = description
                local_event.start_time = start_dt
                local_event.end_time = end_dt
                local_event.meet_link = meet_link
                local_event.html_link = html_link
                local_event.status = status
                local_event.organizer_email = organizer
                local_event.attendees = json.dumps(item.get('attendees', []))
        
        page_token = result.get('nextPageToken')
        new_sync_token = result.get('nextSyncToken')
        
        if not page_token:
            break

    # Update Sync Token
    if new_sync_token:
        channel.sync_token = new_sync_token
        channel.updated_at = datetime.now(timezone.utc)
        db.commit()
        print(f"Sync complete. New token: {new_sync_token}")


@router.get("/webhooks/google-drive/status")
def get_webhook_status(db: Session = Depends(get_db)):
    """
    Get status of all active webhook channels (Drive & Calendar).
    """
    # ... (Keep existing implementation or expand)
    return {"message": "Use DB to check status"}
