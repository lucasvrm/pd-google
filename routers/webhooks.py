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
from services.google_drive_real import GoogleDriveRealService
from utils.retry import exponential_backoff_retry
from utils.structured_logging import calendar_logger
import logging

router = APIRouter()
logger = logging.getLogger("pipedesk_drive.webhooks")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/webhooks/google-drive")
async def receive_google_webhook(
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
    """
    
    logger.info(f"Received webhook: channel={x_goog_channel_id} resource={x_goog_resource_id} state={x_goog_resource_state}")

    if not x_goog_channel_id or not x_goog_resource_id:
        raise HTTPException(status_code=400, detail="Missing required headers")

    # 1. Check if it is a Drive Channel
    drive_channel = db.query(models.DriveWebhookChannel).filter(
        models.DriveWebhookChannel.channel_id == x_goog_channel_id
    ).first()

    if drive_channel:
        return await handle_drive_webhook(db, drive_channel, x_goog_resource_state, x_goog_channel_token, x_goog_resource_uri, x_goog_changed)

    # 2. Check if it is a Calendar Channel
    calendar_channel = db.query(models.CalendarSyncState).filter(
        models.CalendarSyncState.channel_id == x_goog_channel_id
    ).first()

    if calendar_channel:
        return await handle_calendar_webhook(db, calendar_channel, x_goog_resource_state, x_goog_channel_token)

    logger.warning(f"Unknown channel: {x_goog_channel_id}")
    # Return 200 to stop retries
    return {"status": "ignored", "reason": "unknown_channel"}


async def handle_drive_webhook(db, channel, state, token, uri, changed):
    """
    Process Google Drive Webhook with Bidirectional Sync
    """
    if not channel.active:
        return {"status": "ignored", "reason": "inactive_channel"}
    
    # Strict webhook token validation
    if config.WEBHOOK_SECRET:
        if token != config.WEBHOOK_SECRET:
            logger.warning(f"Invalid webhook token for Drive channel {channel.channel_id}")
            raise HTTPException(
                status_code=403,
                detail="Invalid webhook token"
            )
    
    if state == "sync":
        logger.info(f"Drive Sync Handshake: {channel.channel_id}")
        return {"status": "ok"}

    # Extract changed resource ID from URI if available
    changed_resource_id = None
    if uri and "/files/" in uri:
        parts = uri.split("/files/")
        if len(parts) > 1:
            # Extract file ID (remove query params)
            changed_resource_id = parts[1].split("?")[0]

    if not changed_resource_id:
        return {"status": "ignored", "reason": "no_resource_id"}

    # --- BIDIRECTIONAL SYNC LOGIC ---
    
    # We use Real service to fetch fresh metadata
    # Note: If USE_MOCK_DRIVE is true, this might fail or need the Mock Service.
    # Assuming production environment for webhooks.
    drive_service = GoogleDriveRealService()

    try:
        # Case 1: Removal or Trash (Soft Delete in DB)
        if state in ["remove", "trash"]:
            # Check Files
            file_record = db.query(models.DriveFile).filter(models.DriveFile.file_id == changed_resource_id).first()
            if file_record:
                file_record.deleted_at = datetime.now(timezone.utc)
                file_record.delete_reason = "external_drive_delete"
                logger.info(f"Sync: Marked file {changed_resource_id} as deleted")

            # Check Folders
            folder_record = db.query(models.DriveFolder).filter(models.DriveFolder.folder_id == changed_resource_id).first()
            if folder_record:
                folder_record.deleted_at = datetime.now(timezone.utc)
                folder_record.delete_reason = "external_drive_delete"
                logger.info(f"Sync: Marked folder {changed_resource_id} as deleted")
            
            db.commit()

        # Case 2: Add or Update (Sync Metadata)
        elif state in ["add", "update", "change"]:
            try:
                # Fetch fresh data from Drive
                g_file = drive_service.get_file(changed_resource_id)
                
                is_folder = g_file.get('mimeType') == 'application/vnd.google-apps.folder'
                
                if is_folder:
                    # Update Folder Logic
                    folder_record = db.query(models.DriveFolder).filter(models.DriveFolder.folder_id == changed_resource_id).first()
                    if folder_record:
                        # Restore if it was deleted
                        if folder_record.deleted_at:
                             folder_record.deleted_at = None
                             folder_record.delete_reason = None
                        
                        # Update URL if changed (unlikely for existing ID but good practice)
                        if g_file.get('webViewLink'):
                            folder_record.folder_url = g_file.get('webViewLink')
                            
                        db.commit()
                        logger.info(f"Sync: Updated folder {g_file.get('name')}")
                else:
                    # Update/Insert File Logic
                    file_record = db.query(models.DriveFile).filter(models.DriveFile.file_id == changed_resource_id).first()
                    
                    parent_id = g_file.get('parents', [None])[0]
                    
                    if file_record:
                        # Update existing file
                        file_record.name = g_file.get('name')
                        file_record.size = int(g_file.get('size', 0))
                        file_record.parent_folder_id = parent_id
                        file_record.mime_type = g_file.get('mimeType')
                        # Restore if deleted
                        file_record.deleted_at = None 
                        file_record.delete_reason = None
                        logger.info(f"Sync: Updated file {g_file.get('name')}")
                    else:
                        # Insert new file (only if we care about the parent)
                        # We generally only track files inside our known structures
                        # But for now, we add it if we got a webhook for it (implies we are watching the folder)
                        new_file = models.DriveFile(
                            file_id=changed_resource_id,
                            parent_folder_id=parent_id,
                            name=g_file.get('name'),
                            mime_type=g_file.get('mimeType'),
                            size=int(g_file.get('size', 0))
                        )
                        db.add(new_file)
                        logger.info(f"Sync: Created local record for file {g_file.get('name')}")
                    
                    db.commit()

            except Exception as e:
                # If 404, it might have been permanently deleted before we could fetch
                logger.error(f"Sync Error fetching file {changed_resource_id}: {e}")

    except Exception as e:
        logger.error(f"Database error during sync: {e}")
        db.rollback()

    # Log the event to audit log
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


async def handle_calendar_webhook(db: Session, channel: models.CalendarSyncState, state: str, token: str):
    """
    Process Calendar Webhook
    """
    calendar_logger.info(
        action="webhook_received",
        status="processing",
        message=f"Processing Calendar webhook for channel {channel.channel_id}",
        resource_state=state
    )

    if not channel.active:
        calendar_logger.warning(
            action="webhook_received",
            status="ignored",
            message=f"Inactive channel: {channel.channel_id}"
        )
        return {"status": "ignored", "reason": "inactive_channel"}

    # Strict webhook token validation
    if config.WEBHOOK_SECRET:
        if token != config.WEBHOOK_SECRET:
            calendar_logger.warning(
                action="webhook_received",
                status="error",
                message=f"Invalid webhook token for Calendar channel {channel.channel_id}"
            )
            raise HTTPException(
                status_code=403,
                detail="Invalid webhook token"
            )

    if state == "sync":
        calendar_logger.info(
            action="webhook_sync",
            status="success",
            message="Calendar sync handshake successful"
        )
        return {"status": "ok"}

    # Trigger Sync Logic
    try:
        service = GoogleCalendarService()
        sync_calendar_events(db, service, channel)
        calendar_logger.info(
            action="webhook_sync",
            status="success",
            message=f"Calendar sync completed for channel {channel.channel_id}"
        )
    except Exception as e:
        calendar_logger.error(
            action="webhook_sync",
            message=f"Error syncing calendar for channel {channel.channel_id}",
            error=e
        )
        return {"status": "error", "detail": str(e)}

    return {"status": "ok", "type": "calendar"}


def sync_calendar_events(db: Session, service: GoogleCalendarService, channel: models.CalendarSyncState):
    """
    Core Two-Way Sync Logic using Sync Token for Calendar.
    """
    calendar_logger.info(
        action="sync",
        status="started",
        message=f"Syncing calendar {channel.calendar_id}",
        has_sync_token=bool(channel.sync_token)
    )

    page_token = None
    new_sync_token = None
    
    # Wrapper function for the API call with retry
    @exponential_backoff_retry(max_retries=3, initial_delay=1.0)
    def fetch_events_page(calendar_id, sync_token, page_token):
        return service.service.events().list(
            calendarId=calendar_id,
            syncToken=sync_token,
            pageToken=page_token,
            singleEvents=True
        ).execute()
    
    while True:
        try:
            result = fetch_events_page(
                calendar_id=channel.calendar_id,
                sync_token=channel.sync_token,
                page_token=page_token
            )
        except Exception as e:
            error_msg = str(e)
            if '410' in error_msg or 'sync token is no longer valid' in error_msg.lower():
                calendar_logger.warning(
                    action="sync",
                    status="warning",
                    message="Sync token invalid (410). Performing full sync.",
                    error_type="SyncTokenExpired"
                )
                channel.sync_token = None
                db.commit()
                continue
            else:
                calendar_logger.error(
                    action="sync",
                    message="Google API Error during sync",
                    error=e
                )
                raise e

        items = result.get('items', [])
        
        for item in items:
            google_id = item.get('id')
            status = item.get('status')

            local_event = db.query(models.CalendarEvent).filter(
                models.CalendarEvent.google_event_id == google_id
            ).first()

            if status == 'cancelled':
                if local_event:
                    local_event.status = 'cancelled'
            else:
                summary = item.get('summary')
                description = item.get('description')
                start_raw = item.get('start', {}).get('dateTime') or item.get('start', {}).get('date')
                end_raw = item.get('end', {}).get('dateTime') or item.get('end', {}).get('date')
                meet_link = item.get('hangoutLink')
                html_link = item.get('htmlLink')
                organizer = item.get('organizer', {}).get('email')

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

    if new_sync_token:
        channel.sync_token = new_sync_token
        channel.updated_at = datetime.now(timezone.utc)
        db.commit()
        calendar_logger.info(
            action="sync",
            status="success",
            message=f"Sync complete. Processed {len(items) if items else 0} items.",
            new_sync_token=bool(new_sync_token)
        )


@router.get("/webhooks/google-drive/status")
def get_webhook_status(db: Session = Depends(get_db)):
    """
    Get status of all active webhook channels (Drive & Calendar).
    """
    active_channels = db.query(models.DriveWebhookChannel).filter(models.DriveWebhookChannel.active == True).count()
    active_calendar_channels = db.query(models.CalendarSyncState).filter(models.CalendarSyncState.active == True).count()
    
    return {
        "message": "Webhook Status",
        "active_drive_channels": active_channels,
        "active_calendar_channels": active_calendar_channels
    }