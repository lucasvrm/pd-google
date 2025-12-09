"""
CRM Communication Router
Provides aggregated endpoints for viewing emails and calendar events 
associated with CRM entities (Company/Lead/Deal).
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Header
from sqlalchemy.orm import Session
from typing import List, Literal, Optional, Tuple
from datetime import datetime
import json

from database import SessionLocal
from services.google_gmail_service import GoogleGmailService
from services.crm_contact_service import CRMContactService
from services.permission_service import PermissionService
from schemas.crm_communication import (
    EmailSummaryForCRM,
    EventSummaryForCRM,
    EmailListForCRMResponse,
    EventListForCRMResponse
)
from utils.structured_logging import StructuredLogger
import models

# Create structured logger for CRM communication
crm_comm_logger = StructuredLogger(
    service="crm_communication", 
    logger_name="pipedesk_drive.crm_communication"
)

router = APIRouter(
    prefix="/crm",
    tags=["crm-communication"]
)


# Dependencies
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_gmail_service():
    """Dependency to get Gmail service instance."""
    return GoogleGmailService()


def get_contact_service(db: Session = Depends(get_db)):
    """Dependency to get CRM contact service instance."""
    return CRMContactService(db)


def validate_entity_type(entity_type: str) -> str:
    """Validate and normalize entity type."""
    entity_type = entity_type.lower()
    if entity_type not in ["company", "lead", "deal"]:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid entity_type. Must be one of: company, lead, deal"
        )
    return entity_type


def verify_entity_exists(
    entity_type: str, 
    entity_id: str, 
    db: Session
) -> bool:
    """Verify that the entity exists in the database."""
    entity_type = entity_type.lower()
    
    if entity_type == "company":
        entity = db.query(models.Company).filter(models.Company.id == entity_id).first()
    elif entity_type == "lead":
        entity = db.query(models.Lead).filter(models.Lead.id == entity_id).first()
    elif entity_type == "deal":
        entity = db.query(models.Deal).filter(models.Deal.id == entity_id).first()
    else:
        return False
    
    if not entity:
        raise HTTPException(
            status_code=404,
            detail=f"{entity_type.capitalize()} with id {entity_id} not found"
        )
    
    return True


def extract_email_addresses(email_string: Optional[str]) -> List[str]:
    """
    Extract individual email addresses from a comma-separated string.
    Returns normalized (lowercase, stripped) email addresses.
    """
    if not email_string:
        return []
    
    # Simple parsing - split by comma and clean
    emails = []
    for part in email_string.split(','):
        # Remove angle brackets and extract email if present (e.g., "Name <email@example.com>")
        if '<' in part and '>' in part:
            email = part.split('<')[1].split('>')[0].strip().lower()
        else:
            email = part.strip().lower()
        
        if email and '@' in email:
            emails.append(email)
    
    return emails


def email_contains_contacts(
    from_email: Optional[str],
    to_email: Optional[str],
    cc_email: Optional[str],
    bcc_email: Optional[str],
    contact_emails: List[str]
) -> Tuple[bool, List[str]]:
    """
    Check if any contact emails appear in the email's from/to/cc/bcc fields.
    Returns (matches_found, list_of_matched_contacts).
    """
    if not contact_emails:
        return False, []
    
    # Normalize contact emails
    contact_set = set(email.lower().strip() for email in contact_emails)
    matched = set()
    
    # Check all email fields
    for field in [from_email, to_email, cc_email, bcc_email]:
        if field:
            field_emails = extract_email_addresses(field)
            for email in field_emails:
                if email in contact_set:
                    matched.add(email)
    
    return len(matched) > 0, sorted(list(matched))


@router.get(
    "/{entity_type}/{entity_id}/emails",
    response_model=EmailListForCRMResponse,
    summary="Get Emails for CRM Entity",
    description="Retrieves emails associated with a CRM entity (Company/Lead/Deal) based on contact email addresses."
)
def get_entity_emails(
    entity_type: Literal["company", "lead", "deal"],
    entity_id: str,
    limit: int = Query(50, ge=1, le=100, description="Maximum number of results (1-100)"),
    offset: int = Query(0, ge=0, description="Number of results to skip for pagination"),
    time_min: Optional[str] = Query(None, description="Filter emails after this date (YYYY-MM-DD)"),
    time_max: Optional[str] = Query(None, description="Filter emails before this date (YYYY-MM-DD)"),
    x_user_role: Optional[str] = Header(None, alias="x-user-role"),
    db: Session = Depends(get_db),
    gmail_service: GoogleGmailService = Depends(get_gmail_service),
    contact_service: CRMContactService = Depends(get_contact_service)
):
    """
    Get emails associated with a CRM entity.
    
    **Path Parameters:**
    - **entity_type**: Type of CRM entity (company, lead, or deal)
    - **entity_id**: UUID of the entity
    
    **Query Parameters:**
    - **limit**: Maximum number of results to return (default: 50, max: 100)
    - **offset**: Number of results to skip for pagination (default: 0)
    - **time_min**: Filter emails after this date (YYYY-MM-DD format)
    - **time_max**: Filter emails before this date (YYYY-MM-DD format)
    
    **Returns:**
    - List of email summaries where entity contacts appear in from/to/cc/bcc
    - Each email includes which contact emails matched
    - Total count and pagination information
    
    **Association Strategy:**
    - Retrieves contact email addresses from the entity (and related entities)
    - Searches Gmail for messages containing any of these contact emails
    - Returns emails where contacts appear as sender or recipient
    
    **Note:**
    - Access requires crm_read_communications permission
    - Email body content respects gmail_read_body permission
    
    **Example:**
    - GET /api/crm/company/comp-123/emails?limit=10&offset=0
    """
    # Check CRM communication permissions
    crm_perms = PermissionService.get_crm_permissions_for_role(x_user_role)
    
    if not crm_perms.crm_read_communications:
        crm_comm_logger.warning(
            action="get_entity_emails",
            status="access_denied",
            message=f"User role '{x_user_role}' does not have crm_read_communications permission",
            entity_type=entity_type,
            entity_id=entity_id,
            role=x_user_role
        )
        raise HTTPException(
            status_code=403,
            detail="Access denied: Insufficient permissions to access CRM communications"
        )
    
    # Also check Gmail permissions to respect email body restrictions
    gmail_perms = PermissionService.get_permissions_for_role(x_user_role)
    
    crm_comm_logger.info(
        action="get_entity_emails",
        status="authorized",
        entity_type=entity_type,
        entity_id=entity_id,
        role=x_user_role,
        gmail_read_body=gmail_perms.gmail_read_body
    )
    
    # Validate entity type
    entity_type = validate_entity_type(entity_type)
    
    # Verify entity exists
    verify_entity_exists(entity_type, entity_id, db)
    
    # Get contact emails for this entity
    contact_emails = contact_service.get_entity_contact_emails(entity_type, entity_id)
    
    if not contact_emails:
        crm_comm_logger.warning(
            action="get_entity_emails",
            status="no_contacts",
            message=f"No contact emails found for {entity_type} {entity_id}",
            entity_type=entity_type,
            entity_id=entity_id
        )
        return EmailListForCRMResponse(
            emails=[],
            total=0,
            limit=limit,
            offset=offset
        )
    
    # Build Gmail search query to find emails with these contacts
    # Search for emails where any contact appears in from/to/cc/bcc
    email_queries = [f"from:{email} OR to:{email}" for email in contact_emails]
    gmail_query = " OR ".join(email_queries)
    
    # Add date filters if provided
    if time_min:
        gmail_query += f" after:{time_min}"
    if time_max:
        gmail_query += f" before:{time_max}"
    
    try:
        # Get messages from Gmail
        # Note: Gmail API doesn't support offset-based pagination
        # We'll fetch more results and filter client-side for now
        max_fetch = min(offset + limit * 2, 500)  # Fetch extra to account for filtering
        
        result = gmail_service.list_messages(
            query=gmail_query,
            max_results=max_fetch
        )
        
        emails = []
        for msg_ref in result.get('messages', []):
            msg_data = gmail_service.get_message(msg_ref['id'], format='full')
            
            # Parse message headers
            headers = gmail_service._parse_headers(
                msg_data.get('payload', {}).get('headers', [])
            )
            
            # Check if this message contains our contact emails
            matches_found, matched_contacts = email_contains_contacts(
                headers.get('from'),
                headers.get('to'),
                headers.get('cc'),
                headers.get('bcc'),
                contact_emails
            )
            
            if matches_found:
                # Check for attachments
                attachments = gmail_service._extract_attachments(
                    msg_data.get('payload', {})
                )
                has_attachments = len(attachments) > 0
                
                # Parse internal date
                internal_date = None
                if 'internalDate' in msg_data:
                    try:
                        internal_date = datetime.fromtimestamp(
                            int(msg_data['internalDate']) / 1000
                        )
                    except (ValueError, TypeError):
                        pass
                
                # EmailSummaryForCRM uses snippet (which doesn't contain full email body)
                # This respects Gmail permission restrictions at the CRM layer
                emails.append(EmailSummaryForCRM(
                    id=msg_data.get('id', ''),
                    thread_id=msg_data.get('threadId', ''),
                    subject=headers.get('subject'),
                    from_email=headers.get('from'),
                    to_email=headers.get('to'),
                    cc_email=headers.get('cc'),
                    snippet=msg_data.get('snippet'),
                    internal_date=internal_date,
                    has_attachments=has_attachments,
                    matched_contacts=matched_contacts
                ))
        
        # Apply offset and limit
        total = len(emails)
        paginated_emails = emails[offset:offset + limit]
        
        crm_comm_logger.info(
            action="get_entity_emails",
            status="success",
            message=f"Found {total} emails for {entity_type} {entity_id}",
            entity_type=entity_type,
            entity_id=entity_id,
            total_emails=total,
            contact_count=len(contact_emails),
            returned_count=len(paginated_emails)
        )
        
        return EmailListForCRMResponse(
            emails=paginated_emails,
            total=total,
            limit=limit,
            offset=offset
        )
    
    except Exception as e:
        crm_comm_logger.error(
            action="get_entity_emails",
            message=f"Failed to get emails for {entity_type} {entity_id}",
            error=e,
            entity_type=entity_type,
            entity_id=entity_id
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve emails: {str(e)}"
        )


@router.get(
    "/{entity_type}/{entity_id}/events",
    response_model=EventListForCRMResponse,
    summary="Get Events for CRM Entity",
    description="Retrieves calendar events associated with a CRM entity (Company/Lead/Deal) based on contact email addresses."
)
def get_entity_events(
    entity_type: Literal["company", "lead", "deal"],
    entity_id: str,
    limit: int = Query(50, ge=1, le=100, description="Maximum number of results (1-100)"),
    offset: int = Query(0, ge=0, description="Number of results to skip for pagination"),
    time_min: Optional[datetime] = Query(None, description="Filter events starting after this datetime"),
    time_max: Optional[datetime] = Query(None, description="Filter events ending before this datetime"),
    status: Optional[Literal["confirmed", "tentative", "cancelled"]] = Query(
        None,
        description="Filter by event status"
    ),
    x_user_role: Optional[str] = Header(None, alias="x-user-role"),
    db: Session = Depends(get_db),
    contact_service: CRMContactService = Depends(get_contact_service)
):
    """
    Get calendar events associated with a CRM entity.
    
    **Path Parameters:**
    - **entity_type**: Type of CRM entity (company, lead, or deal)
    - **entity_id**: UUID of the entity
    
    **Query Parameters:**
    - **limit**: Maximum number of results to return (default: 50, max: 100)
    - **offset**: Number of results to skip for pagination (default: 0)
    - **time_min**: Filter events starting after this datetime (ISO format)
    - **time_max**: Filter events ending before this datetime (ISO format)
    - **status**: Filter by event status (confirmed, tentative, cancelled)
    
    **Returns:**
    - List of event summaries where entity contacts appear as attendees
    - Each event includes which contact emails matched
    - Total count and pagination information
    
    **Association Strategy:**
    - Retrieves contact email addresses from the entity (and related entities)
    - Queries local calendar events database
    - Returns events where contacts appear in the attendees list
    
    **Note:**
    - Access requires crm_read_communications permission
    - Event details (description, attendees, meet_link) respect calendar_read_details permission
    
    **Example:**
    - GET /api/crm/lead/lead-001/events?limit=10&offset=0
    """
    # Check CRM communication permissions
    crm_perms = PermissionService.get_crm_permissions_for_role(x_user_role)
    
    if not crm_perms.crm_read_communications:
        crm_comm_logger.warning(
            action="get_entity_events",
            status="access_denied",
            message=f"User role '{x_user_role}' does not have crm_read_communications permission",
            entity_type=entity_type,
            entity_id=entity_id,
            role=x_user_role
        )
        raise HTTPException(
            status_code=403,
            detail="Access denied: Insufficient permissions to access CRM communications"
        )
    
    # Also check Calendar permissions to respect event detail restrictions
    calendar_perms = PermissionService.get_calendar_permissions_for_role(x_user_role)
    
    crm_comm_logger.info(
        action="get_entity_events",
        status="authorized",
        entity_type=entity_type,
        entity_id=entity_id,
        role=x_user_role,
        calendar_read_details=calendar_perms.calendar_read_details
    )
    
    # Validate entity type
    entity_type = validate_entity_type(entity_type)
    
    # Verify entity exists
    verify_entity_exists(entity_type, entity_id, db)
    
    # Get contact emails for this entity
    contact_emails = contact_service.get_entity_contact_emails(entity_type, entity_id)
    
    if not contact_emails:
        crm_comm_logger.warning(
            action="get_entity_events",
            status="no_contacts",
            message=f"No contact emails found for {entity_type} {entity_id}",
            entity_type=entity_type,
            entity_id=entity_id
        )
        return EventListForCRMResponse(
            events=[],
            total=0,
            limit=limit,
            offset=offset
        )
    
    # Normalize contact emails for comparison
    contact_set = set(email.lower().strip() for email in contact_emails)
    
    try:
        # Query calendar events
        query = db.query(models.CalendarEvent)
        
        # Apply status filter
        if status:
            query = query.filter(models.CalendarEvent.status == status)
        else:
            # By default, exclude cancelled events
            query = query.filter(models.CalendarEvent.status != 'cancelled')
        
        # Apply time filters
        if time_min:
            query = query.filter(models.CalendarEvent.start_time >= time_min)
        if time_max:
            query = query.filter(models.CalendarEvent.end_time <= time_max)
        
        # Get all events (we'll filter by attendees in Python)
        all_events = query.order_by(models.CalendarEvent.start_time.desc()).all()
        
        # Filter events by attendees
        matched_events = []
        for event in all_events:
            # Parse attendees from JSON
            attendees_data = []
            if event.attendees:
                try:
                    attendees_data = json.loads(event.attendees)
                except (json.JSONDecodeError, TypeError):
                    attendees_data = []
            
            # Check if any contact email is in attendees
            matched_contacts = []
            for attendee in attendees_data:
                attendee_email = attendee.get('email', '').lower().strip()
                if attendee_email in contact_set:
                    matched_contacts.append(attendee_email)
            
            # If we found matching contacts, include this event
            if matched_contacts:
                matched_events.append((event, matched_contacts))
        
        # Apply pagination
        total = len(matched_events)
        paginated_events = matched_events[offset:offset + limit]
        
        # Build response with permission-based field redaction
        events_response = []
        for event, matched_contacts in paginated_events:
            events_response.append(EventSummaryForCRM(
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
                matched_contacts=sorted(matched_contacts)
            ))
        
        crm_comm_logger.info(
            action="get_entity_events",
            status="success",
            message=f"Found {total} events for {entity_type} {entity_id}",
            entity_type=entity_type,
            entity_id=entity_id,
            total_events=total,
            contact_count=len(contact_emails),
            returned_count=len(events_response),
            details_redacted=not calendar_perms.calendar_read_details
        )
        
        return EventListForCRMResponse(
            events=events_response,
            total=total,
            limit=limit,
            offset=offset
        )
    
    except Exception as e:
        crm_comm_logger.error(
            action="get_entity_events",
            message=f"Failed to get events for {entity_type} {entity_id}",
            error=e,
            entity_type=entity_type,
            entity_id=entity_id
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve events: {str(e)}"
        )
