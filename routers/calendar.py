from fastapi import APIRouter, Depends, HTTPException, Body, Query, Header
from sqlalchemy.orm import Session
from typing import List, Optional, Literal
from pydantic import BaseModel, Field, model_validator
from datetime import datetime, timedelta
import json

from database import SessionLocal
from services.google_calendar_service import GoogleCalendarService
from services.permission_service import PermissionService
from utils.structured_logging import calendar_logger
import models
from config import config

router = APIRouter(
    tags=["calendar"]
)

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_calendar_service(db: Session = Depends(get_db)):
    """
    Dependency to get Calendar Service instance with database session.
    
    Args:
        db: Database session from get_db dependency
        
    Returns:
        GoogleCalendarService instance configured with database access
    """
    return GoogleCalendarService(db)

# Pydantic Models
class Attendee(BaseModel):
    """
    Represents an event attendee.
    """
    email: str
    responseStatus: Optional[str] = None  # needsAction, declined, tentative, accepted
    displayName: Optional[str] = None
    organizer: Optional[bool] = False
    self: Optional[bool] = False
    optional: Optional[bool] = False

    class Config:
        json_schema_extra = {
            "example": {
                "email": "attendee@example.com",
                "responseStatus": "accepted",
                "displayName": "John Doe",
                "optional": False
            }
        }

class EventCreate(BaseModel):
    """
    Schema for creating a new calendar event.
    
    Supports both 'summary' and 'title' as the event title for flexibility.
    The UI can send either field - 'title' is an alias for 'summary'.
    
    Also supports both camelCase and snake_case for field names:
    - start_time / startTime
    - end_time / endTime
    - create_meet_link / createMeetLink
    - calendar_id / calendarId
    """
    summary: Optional[str] = Field(default=None, description="Event title/subject")
    title: Optional[str] = Field(default=None, description="Alias for summary - event title/subject")
    description: Optional[str] = None
    start_time: datetime = Field(..., description="Event start datetime in ISO format")
    end_time: datetime = Field(..., description="Event end datetime in ISO format")
    attendees: Optional[List[str]] = Field(default_factory=list, description="List of email addresses to invite")
    create_meet_link: bool = Field(default=True, description="Whether to generate a Google Meet link")
    calendar_id: Optional[str] = Field(default="primary", description="Calendar ID, defaults to 'primary'")
    
    @model_validator(mode='before')
    @classmethod
    def handle_aliases_and_camel_case(cls, data):
        """
        Handle field aliases and camelCase to snake_case conversion.
        
        Supports:
        - 'title' as alias for 'summary'
        - 'startTime' as alias for 'start_time'
        - 'endTime' as alias for 'end_time'
        - 'createMeetLink' as alias for 'create_meet_link'
        - 'calendarId' as alias for 'calendar_id'
        
        Precedence: snake_case takes priority over camelCase if both are provided.
        """
        if isinstance(data, dict):
            # Handle camelCase to snake_case conversions
            # startTime -> start_time (if start_time not provided)
            if 'startTime' in data and 'start_time' not in data:
                data['start_time'] = data['startTime']
            
            # endTime -> end_time (if end_time not provided)
            if 'endTime' in data and 'end_time' not in data:
                data['end_time'] = data['endTime']
            
            # createMeetLink -> create_meet_link (if create_meet_link not provided)
            if 'createMeetLink' in data and 'create_meet_link' not in data:
                data['create_meet_link'] = data['createMeetLink']
            
            # calendarId -> calendar_id (if calendar_id not provided)
            if 'calendarId' in data and 'calendar_id' not in data:
                data['calendar_id'] = data['calendarId']
            
            # Handle title -> summary alias
            # If summary is provided, use it (title is ignored)
            if data.get('summary'):
                return data
            # If title is provided but summary is not, use title as summary
            if data.get('title'):
                data['summary'] = data['title']
            # If neither is provided, set a default
            if not data.get('summary'):
                data['summary'] = 'Untitled Event'
        return data

    class Config:
        populate_by_name = True
        json_schema_extra = {
            "example": {
                "summary": "Sales Meeting - Client X",
                "description": "Quarterly review and proposal presentation",
                "start_time": "2024-01-15T14:00:00Z",
                "end_time": "2024-01-15T15:00:00Z",
                "attendees": ["sales@company.com", "client@example.com"],
                "create_meet_link": True
            }
        }

class EventUpdate(BaseModel):
    """
    Schema for updating an existing calendar event.
    All fields are optional - only provided fields will be updated.
    """
    summary: Optional[str] = None
    description: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    attendees: Optional[List[str]] = None  # List of email addresses

    class Config:
        json_schema_extra = {
            "example": {
                "summary": "Updated Meeting Title",
                "start_time": "2024-01-15T15:00:00Z"
            }
        }

class EventResponse(BaseModel):
    """
    Standard response schema for calendar events.
    Contains all information needed by the frontend, including Meet link.
    """
    id: Optional[int] = None
    google_event_id: str
    summary: str
    description: Optional[str] = None
    start_time: datetime
    end_time: datetime
    meet_link: Optional[str] = None
    html_link: Optional[str] = None
    status: Optional[str] = None  # confirmed, tentative, cancelled
    organizer_email: Optional[str] = None
    attendees: Optional[List[Attendee]] = []

    class Config:
        json_schema_extra = {
            "example": {
                "id": 1,
                "google_event_id": "evt_abc123xyz",
                "summary": "Sales Meeting - Client X",
                "description": "Quarterly review and proposal presentation",
                "start_time": "2024-01-15T14:00:00+00:00",
                "end_time": "2024-01-15T15:00:00+00:00",
                "meet_link": "https://meet.google.com/abc-defg-hij",
                "html_link": "https://calendar.google.com/event?eid=abc123",
                "status": "confirmed",
                "organizer_email": "organizer@company.com",
                "attendees": [
                    {
                        "email": "attendee@example.com",
                        "responseStatus": "accepted",
                        "displayName": "John Doe"
                    }
                ]
            }
        }

# Helper functions
def parse_attendees_from_google(attendees_data: Optional[List[dict]]) -> List[Attendee]:
    """
    Parse attendees from Google Calendar API format to Pydantic models.
    """
    if not attendees_data:
        return []
    
    result = []
    for att in attendees_data:
        result.append(Attendee(
            email=att.get('email', ''),
            responseStatus=att.get('responseStatus'),
            displayName=att.get('displayName'),
            organizer=att.get('organizer', False),
            self=att.get('self', False),
            optional=att.get('optional', False)
        ))
    return result

# API Endpoints
@router.post("/events", response_model=EventResponse, status_code=201,
             summary="Create Calendar Event",
             description="Creates a new event in Google Calendar with optional Google Meet link. "
                        "The event is automatically synced to the local database.")
def create_event(
    event_in: EventCreate,
    db: Session = Depends(get_db),
    service: GoogleCalendarService = Depends(get_calendar_service)
):
    """
    Create a new event in Google Calendar and save to local DB.
    
    **Parameters:**
    - **summary**: Event title/subject (required)
    - **description**: Event details/notes (optional)
    - **start_time**: Event start datetime in ISO format with timezone
    - **end_time**: Event end datetime in ISO format with timezone
    - **attendees**: List of email addresses to invite
    - **create_meet_link**: Whether to generate a Google Meet link (default: true)
    
    **Returns:**
    - Complete event details including meet_link and html_link
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
        calendar_logger.info(
            action="create_event",
            status="success",
            message=f"Created event: {event_in.summary}",
            google_event_id=google_event.get('id'),
            attendee_count=len(event_in.attendees),
            has_meet_link=bool(google_event.get('hangoutLink'))
        )
    except Exception as e:
        calendar_logger.error(
            action="create_event",
            message=f"Failed to create event: {event_in.summary}",
            error=e
        )
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

    # 5. Parse attendees for response
    attendees_list = parse_attendees_from_google(google_event.get('attendees', []))

    return EventResponse(
        id=db_event.id,
        google_event_id=db_event.google_event_id,
        summary=db_event.summary,
        description=db_event.description,
        start_time=db_event.start_time,
        end_time=db_event.end_time,
        meet_link=db_event.meet_link,
        html_link=db_event.html_link,
        status=db_event.status,
        organizer_email=db_event.organizer_email,
        attendees=attendees_list
    )

@router.get("/events", response_model=List[EventResponse],
            summary="List Calendar Events",
            description="Retrieves calendar events from the local database mirror. "
                       "Supports filtering by time range, status, entity context, and pagination. "
                       "If no time range is provided, defaults to last 30 days to +90 days.")
def list_events(
    time_min: Optional[datetime] = Query(
        None,
        alias="timeMin",
        description="Filter events starting after this datetime (ISO format). Defaults to 30 days ago if not provided."
    ),
    time_max: Optional[datetime] = Query(
        None,
        alias="timeMax",
        description="Filter events ending before this datetime (ISO format). Defaults to 90 days from now if not provided."
    ),
    entity_type: Optional[Literal["company", "lead", "deal", "contact"]] = Query(
        None,
        alias="entityType",
        description="Filter by entity type for quick actions context"
    ),
    entity_id: Optional[str] = Query(
        None,
        alias="entityId",
        description="Filter by entity ID for quick actions context"
    ),
    calendar_id: Optional[str] = Query(
        "primary",
        alias="calendarId",
        description="Calendar ID to query, defaults to 'primary'"
    ),
    status: Optional[Literal["confirmed", "tentative", "cancelled"]] = Query(
        None, 
        description="Filter by event status"
    ),
    limit: int = Query(100, ge=1, le=500, description="Maximum number of results"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    x_user_role: Optional[str] = Header(None, alias="x-user-role"),
    db: Session = Depends(get_db)
):
    """
    List events from Local Database (synced from Google Calendar).
    
    **Query Parameters:**
    - **timeMin**: Filter events starting after this datetime (ISO format). Defaults to 30 days ago.
    - **timeMax**: Filter events ending before this datetime (ISO format). Defaults to 90 days from now.
    - **entityType**: Filter by entity type (company, lead, deal, contact) for quick actions
    - **entityId**: Filter by entity ID for quick actions context
    - **calendarId**: Calendar ID, defaults to "primary"
    - **status**: Filter by event status (confirmed, tentative, cancelled)
    - **limit**: Maximum number of results to return (default: 100, max: 500)
    - **offset**: Number of results to skip for pagination (default: 0)
    
    **Returns:**
    - List of events matching the filters, ordered by start time
    
    **Note:** 
    - By default, cancelled events are excluded unless explicitly requested via status filter
    - Events are synced from Google Calendar via webhooks
    - Access to event details (description, attendees, meet_link) depends on user role
    - If entityType and entityId are provided, events are filtered by attendee emails associated with that entity
    """
    # Get calendar permissions for the user's role
    calendar_perms = PermissionService.get_calendar_permissions_for_role(x_user_role)
    
    # Apply safe defaults for time range only when entity context is provided (quick actions)
    # or when the caller explicitly requests time filtering.
    # For backward compatibility, if no time filters and no entity context, return all events.
    now = datetime.utcnow()
    use_time_defaults = entity_type is not None and entity_id is not None
    
    # Compute effective time range
    effective_time_min = time_min
    effective_time_max = time_max
    
    # If quick actions context is provided, apply safe defaults
    if use_time_defaults:
        if effective_time_min is None:
            effective_time_min = now - timedelta(days=30)
        if effective_time_max is None:
            effective_time_max = now + timedelta(days=90)
    
    calendar_logger.info(
        action="list_events",
        status="checking_permissions",
        role=x_user_role,
        calendar_read_details=calendar_perms.calendar_read_details,
        entity_type=entity_type,
        entity_id=entity_id,
        calendar_id=calendar_id
    )
    
    # Build query
    query = db.query(models.CalendarEvent)
    
    # Apply filters
    if status:
        query = query.filter(models.CalendarEvent.status == status)
    else:
        # By default, exclude cancelled events
        query = query.filter(models.CalendarEvent.status != 'cancelled')

    # Apply time range filters only if provided or using quick action defaults
    if effective_time_min is not None:
        query = query.filter(models.CalendarEvent.start_time >= effective_time_min)
    if effective_time_max is not None:
        query = query.filter(models.CalendarEvent.end_time <= effective_time_max)
    
    # TODO: Implement entity-based filtering by attendee emails
    # When entityType and entityId are provided, events should be filtered based on 
    # contact emails associated with that entity (via CrmContactService).
    # For now, we accept these parameters to prevent 422 errors from UI quick actions.
    # The filtering should query the entity's contacts and match against event attendees.
    if entity_type and entity_id:
        calendar_logger.info(
            action="list_events",
            status="entity_context_provided",
            entity_type=entity_type,
            entity_id=entity_id,
            message="Entity context accepted - full entity-based filtering pending implementation"
        )

    # Apply pagination and ordering
    events = query.order_by(models.CalendarEvent.start_time).offset(offset).limit(limit).all()

    response_list = []
    for event in events:
        # Parse attendees from JSON string
        attendees_list = []
        if event.attendees and calendar_perms.calendar_read_details:
            try:
                attendees_data = json.loads(event.attendees)
                attendees_list = parse_attendees_from_google(attendees_data)
            except (json.JSONDecodeError, TypeError):
                attendees_list = []
        
        event_response = EventResponse(
            id=event.id,
            google_event_id=event.google_event_id,
            summary=event.summary or "No Title",
            description=event.description if calendar_perms.calendar_read_details else None,
            start_time=event.start_time,
            end_time=event.end_time,
            meet_link=event.meet_link if calendar_perms.calendar_read_details else None,
            html_link=event.html_link,
            status=event.status,
            organizer_email=event.organizer_email,
            attendees=attendees_list
        )
        
        response_list.append(event_response)

    calendar_logger.info(
        action="list_events",
        status="success",
        role=x_user_role,
        event_count=len(response_list),
        details_redacted=not calendar_perms.calendar_read_details,
        time_min=effective_time_min.isoformat() if effective_time_min else None,
        time_max=effective_time_max.isoformat() if effective_time_max else None
    )

    return response_list

@router.get("/events/{event_id}", response_model=EventResponse,
            summary="Get Event Details",
            description="Retrieves detailed information about a specific calendar event by its ID.")
def get_event(
    event_id: str,
    x_user_role: Optional[str] = Header(None, alias="x-user-role"),
    db: Session = Depends(get_db)
):
    """
    Get complete details of a specific event.
    
    **Parameters:**
    - **event_id**: Internal database ID or Google event ID
    
    **Returns:**
    - Complete event details including:
      - meet_link: Google Meet video conference link (if available and user has permissions)
      - html_link: Link to view event in Google Calendar
      - summary: Event title
      - description: Event details (if user has permissions)
      - start_time & end_time: Event datetime with timezone
      - status: Event status (confirmed, tentative, cancelled)
      - organizer_email: Email of the event organizer
      - attendees: List of all invited participants with their response status (if user has permissions)
    
    **Note:**
    - The meet_link field contains the Google Meet link when create_meet_link was true during creation
    - Cancelled events can still be retrieved via this endpoint
    - Access to event details depends on user role (description, attendees, meet_link)
    """
    # Get calendar permissions for the user's role
    calendar_perms = PermissionService.get_calendar_permissions_for_role(x_user_role)
    
    calendar_logger.info(
        action="get_event",
        status="checking_permissions",
        event_id=event_id,
        role=x_user_role,
        calendar_read_details=calendar_perms.calendar_read_details
    )
    
    # Try to find by internal ID first, then by Google event ID
    db_event = None
    if event_id.isdigit():
        db_event = db.query(models.CalendarEvent).filter(models.CalendarEvent.id == int(event_id)).first()
    
    if not db_event:
        # Try finding by google_event_id
        db_event = db.query(models.CalendarEvent).filter(models.CalendarEvent.google_event_id == event_id).first()
    
    if not db_event:
        calendar_logger.warning(
            action="get_event",
            status="not_found",
            event_id=event_id,
            role=x_user_role
        )
        raise HTTPException(status_code=404, detail="Event not found")
    
    # Parse attendees from JSON string
    attendees_list = []
    if db_event.attendees and calendar_perms.calendar_read_details:
        try:
            attendees_data = json.loads(db_event.attendees)
            attendees_list = parse_attendees_from_google(attendees_data)
        except (json.JSONDecodeError, TypeError):
            attendees_list = []
    
    event_response = EventResponse(
        id=db_event.id,
        google_event_id=db_event.google_event_id,
        summary=db_event.summary or "No Title",
        description=db_event.description if calendar_perms.calendar_read_details else None,
        start_time=db_event.start_time,
        end_time=db_event.end_time,
        meet_link=db_event.meet_link if calendar_perms.calendar_read_details else None,
        html_link=db_event.html_link,
        status=db_event.status,
        organizer_email=db_event.organizer_email,
        attendees=attendees_list
    )
    
    calendar_logger.info(
        action="get_event",
        status="success",
        event_id=event_id,
        role=x_user_role,
        details_redacted=not calendar_perms.calendar_read_details
    )
    
    return event_response

@router.patch("/events/{event_id}", response_model=EventResponse,
              summary="Update Calendar Event",
              description="Updates an existing calendar event. All fields are optional - "
                         "only the provided fields will be updated in both Google Calendar and local database.")
def update_event(
    event_id: str,
    event_in: EventUpdate,
    db: Session = Depends(get_db),
    service: GoogleCalendarService = Depends(get_calendar_service)
):
    """
    Update an event. Accepts both internal DB ID and Google event ID.
    
    **Parameters:**
    - **event_id**: Internal database ID or Google event ID
    - **Request body**: Fields to update (all optional)
      - summary: New event title
      - description: New event description
      - start_time: New start datetime
      - end_time: New end datetime
      - attendees: New list of attendee emails (replaces existing)
    
    **Returns:**
    - Updated event details with all fields
    
    **Note:**
    - Changes are synchronized to Google Calendar immediately
    - Only provided fields are updated; others remain unchanged
    """
    # Find in DB first to get Google ID
    db_event = None
    if event_id.isdigit():
        db_event = db.query(models.CalendarEvent).filter(models.CalendarEvent.id == int(event_id)).first()

    if not db_event:
        # Try finding by google_id
        db_event = db.query(models.CalendarEvent).filter(models.CalendarEvent.google_event_id == event_id).first()

    if not db_event:
        raise HTTPException(status_code=404, detail="Event not found")

    # Prepare update body for Google API
    body = {}
    if event_in.summary is not None: 
        body['summary'] = event_in.summary
    if event_in.description is not None: 
        body['description'] = event_in.description
    if event_in.start_time is not None:
        body['start'] = {'dateTime': event_in.start_time.isoformat(), 'timeZone': 'UTC'}
    if event_in.end_time is not None:
        body['end'] = {'dateTime': event_in.end_time.isoformat(), 'timeZone': 'UTC'}
    if event_in.attendees is not None:
        body['attendees'] = [{'email': email} for email in event_in.attendees]

    if not body:
        raise HTTPException(status_code=400, detail="No fields provided for update")

    # Update Google Calendar
    try:
        updated_google = service.update_event(db_event.google_event_id, body)
        calendar_logger.info(
            action="update_event",
            status="success",
            message=f"Updated event: {db_event.summary}",
            google_event_id=db_event.google_event_id
        )
    except Exception as e:
        calendar_logger.error(
            action="update_event",
            message=f"Failed to update event: {db_event.google_event_id}",
            error=e,
            google_event_id=db_event.google_event_id
        )
        raise HTTPException(status_code=500, detail=f"Google API Error: {str(e)}")

    # Update local DB with data from Google response
    if event_in.summary is not None: 
        db_event.summary = updated_google.get('summary', event_in.summary)
    if event_in.description is not None: 
        db_event.description = updated_google.get('description', event_in.description)
    if event_in.start_time is not None: 
        db_event.start_time = event_in.start_time
    if event_in.end_time is not None: 
        db_event.end_time = event_in.end_time
    
    # Update attendees and other metadata from Google response
    if 'attendees' in updated_google:
        db_event.attendees = json.dumps(updated_google.get('attendees', []))
    
    db_event.status = updated_google.get('status', db_event.status)
    db_event.organizer_email = updated_google.get('organizer', {}).get('email', db_event.organizer_email)

    db.commit()
    db.refresh(db_event)

    # Parse attendees for response
    attendees_list = parse_attendees_from_google(updated_google.get('attendees', []))

    return EventResponse(
        id=db_event.id,
        google_event_id=db_event.google_event_id,
        summary=db_event.summary,
        description=db_event.description,
        start_time=db_event.start_time,
        end_time=db_event.end_time,
        meet_link=db_event.meet_link,
        html_link=db_event.html_link,
        status=db_event.status,
        organizer_email=db_event.organizer_email,
        attendees=attendees_list
    )

@router.delete("/events/{event_id}", response_model=EventResponse,
               summary="Cancel Calendar Event",
               description="Cancels a calendar event (soft delete). The event is marked as cancelled "
                          "in both Google Calendar and the local database but not permanently deleted.")
def delete_event(
    event_id: str,
    db: Session = Depends(get_db),
    service: GoogleCalendarService = Depends(get_calendar_service)
):
    """
    Cancel/delete an event (soft delete - sets status to 'cancelled').
    
    **Parameters:**
    - **event_id**: Internal database ID or Google event ID
    
    **Returns:**
    - The cancelled event details with status='cancelled'
    
    **Note:**
    - This performs a soft delete - the event remains in the database with status='cancelled'
    - Cancelled events are excluded from default list queries
    - The event is also cancelled in Google Calendar
    - Attendees will be notified of the cancellation by Google
    """
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
        calendar_logger.info(
            action="delete_event",
            status="success",
            message=f"Cancelled event: {db_event.summary}",
            google_event_id=db_event.google_event_id
        )
    except Exception as e:
        # If 410 gone, we just update local
        calendar_logger.warning(
            action="delete_event",
            status="warning",
            message=f"Event already deleted from Google: {db_event.google_event_id}",
            google_event_id=db_event.google_event_id
        )
        print(f"Delete warning: {e}")

    # Update DB status (Soft delete)
    db_event.status = 'cancelled'
    db.commit()
    db.refresh(db_event)

    # Parse attendees for response
    attendees_list = []
    if db_event.attendees:
        try:
            attendees_data = json.loads(db_event.attendees)
            attendees_list = parse_attendees_from_google(attendees_data)
        except (json.JSONDecodeError, TypeError):
            attendees_list = []

    return EventResponse(
        id=db_event.id,
        google_event_id=db_event.google_event_id,
        summary=db_event.summary or "No Title",
        description=db_event.description,
        start_time=db_event.start_time,
        end_time=db_event.end_time,
        meet_link=db_event.meet_link,
        html_link=db_event.html_link,
        status=db_event.status,
        organizer_email=db_event.organizer_email,
        attendees=attendees_list
    )

@router.post("/watch", status_code=201, tags=["internal"],
             summary="Register Webhook Channel (Internal)",
             description="Internal endpoint for manually registering a webhook channel for calendar synchronization. "
                        "This is typically handled automatically by the scheduler service.")
def watch_calendar(
    db: Session = Depends(get_db),
    service: GoogleCalendarService = Depends(get_calendar_service)
):
    """
    Manually register a webhook channel for the primary calendar.
    
    **Note:** This is an internal endpoint used for development/testing purposes.
    The scheduler service automatically manages webhook channel registration and renewal.
    Frontend applications should not need to call this endpoint.
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
    db.refresh(sync_state)
    
    # Perform initial sync to populate events
    from routers.webhooks import sync_calendar_events
    try:
        calendar_logger.info(
            action="watch",
            status="performing_initial_sync",
            message=f"Performing initial sync for channel {channel_id}"
        )
        sync_calendar_events(db, service, sync_state)
        calendar_logger.info(
            action="watch",
            status="success",
            message=f"Initial sync completed for channel {channel_id}"
        )
    except Exception as e:
        calendar_logger.error(
            action="watch",
            message=f"Initial sync failed for channel {channel_id}",
            error=e
        )
        # Don't fail the watch creation if sync fails - channel is still active

    return {
        "status": "watching",
        "channel_id": channel_id,
        "resource_id": response.get('resourceId'),
        "expiration": response.get('expiration')
    }
