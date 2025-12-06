from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime
import json

from database import SessionLocal
from services.google_calendar_service import GoogleCalendarService
import models
from config import config

router = APIRouter(
    prefix="/calendar",
    tags=["calendar"]
)

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_calendar_service():
    if config.USE_MOCK_DRIVE: # Assuming we might want a mock calendar too, but for now using real or failing
         # For MVP, if Mock Drive is used, we might just fail Calendar or need a MockCalendarService
         # But the requirement is integration with Google.
         # We'll use the Real service if creds exist, else it might fail.
         # For safety, let's use the real service class which checks creds inside.
         return GoogleCalendarService()
    return GoogleCalendarService()

# Pydantic Models
class Attendee(BaseModel):
    email: str
    responseStatus: Optional[str] = None

class EventCreate(BaseModel):
    summary: str
    description: Optional[str] = None
    start_time: datetime
    end_time: datetime
    attendees: Optional[List[str]] = [] # List of emails
    create_meet_link: bool = True

class EventUpdate(BaseModel):
    summary: Optional[str] = None
    description: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

class EventResponse(BaseModel):
    id: Optional[int] = None
    google_event_id: str
    summary: str
    description: Optional[str] = None
    start_time: datetime
    end_time: datetime
    meet_link: Optional[str] = None
    html_link: Optional[str] = None
    status: Optional[str] = None

@router.post("/events", response_model=EventResponse, status_code=201)
def create_event(
    event_in: EventCreate,
    db: Session = Depends(get_db),
    service: GoogleCalendarService = Depends(get_calendar_service)
):
    """
    Create a new event in Google Calendar and save to local DB.
    """
    # 1. Prepare Google API payload
    google_event_body = {
        'summary': event_in.summary,
        'description': event_in.description,
        'start': {
            'dateTime': event_in.start_time.isoformat(),
            'timeZone': 'UTC', # Adjust if we want to handle user timezone
        },
        'end': {
            'dateTime': event_in.end_time.isoformat(),
            'timeZone': 'UTC',
        },
        'attendees': [{'email': email} for email in event_in.attendees],
    }

    if event_in.create_meet_link:
        google_event_body['conferenceData'] = {
            'createRequest': {
                'requestId': f"req-{datetime.now().timestamp()}",
                'conferenceSolutionKey': {'type': 'hangoutsMeet'}
            }
        }

    # 2. Call Google API
    try:
        google_event = service.create_event(google_event_body)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Google Calendar API Error: {str(e)}")

    # 3. Extract Data
    google_id = google_event.get('id')
    meet_link = google_event.get('hangoutLink')
    html_link = google_event.get('htmlLink')
    status = google_event.get('status')

    # 4. Save to DB
    db_event = models.CalendarEvent(
        google_event_id=google_id,
        summary=event_in.summary,
        description=event_in.description,
        start_time=event_in.start_time,
        end_time=event_in.end_time,
        meet_link=meet_link,
        html_link=html_link,
        status=status,
        organizer_email=google_event.get('organizer', {}).get('email'),
        attendees=json.dumps(google_event.get('attendees', []))
    )
    db.add(db_event)
    db.commit()
    db.refresh(db_event)

    return EventResponse(
        id=db_event.id,
        google_event_id=db_event.google_event_id,
        summary=db_event.summary,
        description=db_event.description,
        start_time=db_event.start_time,
        end_time=db_event.end_time,
        meet_link=db_event.meet_link,
        html_link=db_event.html_link,
        status=db_event.status
    )

@router.get("/events", response_model=List[EventResponse])
def list_events(
    time_min: Optional[datetime] = None,
    time_max: Optional[datetime] = None,
    db: Session = Depends(get_db)
):
    """
    List events from Local Database (Phase 4).
    Sync is handled via Webhooks.
    """
    query = db.query(models.CalendarEvent).filter(
        models.CalendarEvent.status != 'cancelled'
    )

    if time_min:
        query = query.filter(models.CalendarEvent.start_time >= time_min)
    if time_max:
        query = query.filter(models.CalendarEvent.end_time <= time_max)

    events = query.order_by(models.CalendarEvent.start_time).all()

    response_list = []
    for event in events:
        response_list.append(EventResponse(
            id=event.id,
            google_event_id=event.google_event_id,
            summary=event.summary or "No Title",
            description=event.description,
            start_time=event.start_time,
            end_time=event.end_time,
            meet_link=event.meet_link,
            html_link=event.html_link,
            status=event.status
        ))

    return response_list

@router.patch("/events/{event_id}")
def update_event(
    event_id: str, # Google ID or DB ID? Requirements imply managing by ID. Let's assume DB ID for URL, but we need Google ID.
    event_in: EventUpdate,
    db: Session = Depends(get_db),
    service: GoogleCalendarService = Depends(get_calendar_service)
):
    """
    Update an event. Accepts DB ID.
    """
    # Find in DB first to get Google ID
    # Note: If we passed Google ID in URL, we wouldn't need DB lookup, but typical REST uses internal ID.
    # Let's try to support both or stick to Internal ID.

    # Check if event_id is numeric (DB ID)
    db_event = None
    if event_id.isdigit():
        db_event = db.query(models.CalendarEvent).filter(models.CalendarEvent.id == int(event_id)).first()

    if not db_event:
        # Try finding by google_id
        db_event = db.query(models.CalendarEvent).filter(models.CalendarEvent.google_event_id == event_id).first()

    if not db_event:
        raise HTTPException(status_code=404, detail="Event not found")

    # Prepare update body
    body = {}
    if event_in.summary: body['summary'] = event_in.summary
    if event_in.description: body['description'] = event_in.description
    if event_in.start_time:
        body['start'] = {'dateTime': event_in.start_time.isoformat(), 'timeZone': 'UTC'}
    if event_in.end_time:
        body['end'] = {'dateTime': event_in.end_time.isoformat(), 'timeZone': 'UTC'}

    if not body:
         return {"message": "No changes requested"}

    # Update Google
    try:
        updated_google = service.update_event(db_event.google_event_id, body)
    except Exception as e:
         raise HTTPException(status_code=500, detail=f"Google API Error: {str(e)}")

    # Update DB
    if event_in.summary: db_event.summary = event_in.summary
    if event_in.description: db_event.description = event_in.description
    if event_in.start_time: db_event.start_time = event_in.start_time
    if event_in.end_time: db_event.end_time = event_in.end_time

    db.commit()

    return {"status": "updated", "google_event": updated_google}

@router.delete("/events/{event_id}")
def delete_event(
    event_id: str,
    db: Session = Depends(get_db),
    service: GoogleCalendarService = Depends(get_calendar_service)
):
    # Find in DB
    db_event = None
    if event_id.isdigit():
        db_event = db.query(models.CalendarEvent).filter(models.CalendarEvent.id == int(event_id)).first()
    else:
        db_event = db.query(models.CalendarEvent).filter(models.CalendarEvent.google_event_id == event_id).first()

    if not db_event:
        raise HTTPException(status_code=404, detail="Event not found")

    # Delete from Google
    try:
        service.delete_event(db_event.google_event_id)
    except Exception as e:
        # If 410 gone, we just update local
         print(f"Delete warning: {e}")

    # Update DB status (Soft delete or status cancelled)
    db_event.status = 'cancelled'
    # Optional: db.delete(db_event) if we want hard delete
    db.commit()

    return {"status": "cancelled"}

@router.post("/watch", status_code=201)
def watch_calendar(
    db: Session = Depends(get_db),
    service: GoogleCalendarService = Depends(get_calendar_service)
):
    """
    Manually register a webhook channel for the primary calendar.
    For development/testing purposes.
    """
    import uuid
    from config import config

    channel_id = str(uuid.uuid4())
    webhook_url = f"{config.WEBHOOK_BASE_URL}/webhooks/google-drive" # reusing same endpoint URL

    # 7 days expiration (Google max is usually ~1 month, but let's be safe)
    # Expiration is in milliseconds
    expiration_ms = int((datetime.now().timestamp() + 7 * 24 * 3600) * 1000)

    try:
        response = service.watch_events(
            channel_id=channel_id,
            webhook_url=webhook_url,
            token=config.WEBHOOK_SECRET,
            expiration=expiration_ms
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to watch calendar: {e}")

    # Save to Sync State
    sync_state = models.CalendarSyncState(
        channel_id=channel_id,
        resource_id=response.get('resourceId'),
        calendar_id='primary',
        expiration=datetime.fromtimestamp(int(response.get('expiration', expiration_ms)) / 1000),
        active=True
    )
    db.add(sync_state)
    db.commit()

    return {
        "status": "watching",
        "channel_id": channel_id,
        "resource_id": response.get('resourceId'),
        "expiration": response.get('expiration')
    }
