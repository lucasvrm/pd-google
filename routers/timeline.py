"""
Timeline Router - Unified Timeline API

Provides a single endpoint for fetching all activities related to a CRM entity.
Aggregates data from:
- Calendar Events (meetings)
- Audit Logs (entity changes)
- Emails (placeholder for future implementation)

This is the "single source of truth" for the Lead/Deal View timeline.
"""

import json
from datetime import datetime
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import SessionLocal
from auth.dependencies import get_current_user
from auth.jwt import UserContext
from schemas.timeline import (
    TimelineEntry,
    TimelinePagination,
    TimelineResponse,
    TimelineUser,
)
from utils.structured_logging import StructuredLogger
import models

router = APIRouter(
    prefix="/api/timeline",
    tags=["timeline"]
)

# Structured logger for timeline operations
timeline_logger = StructuredLogger(
    service="timeline", logger_name="pipedesk_drive.timeline"
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _fetch_calendar_events(
    db: Session,
    entity_type: str,
    entity_id: str
) -> List[TimelineEntry]:
    """
    Fetch calendar events linked to an entity.
    
    Currently matches events by:
    - Checking if any attendee email matches a contact associated with the entity
    - Future: Match by metadata/description containing entity references
    
    Args:
        db: Database session
        entity_type: Type of entity (lead, deal, contact)
        entity_id: UUID of the entity
        
    Returns:
        List of TimelineEntry objects for calendar events
    """
    entries: List[TimelineEntry] = []
    
    # Get all calendar events (for MVP, we include all events)
    # In production, this should filter by attendee email or metadata
    calendar_events = db.query(models.CalendarEvent).filter(
        models.CalendarEvent.status != 'cancelled'
    ).order_by(models.CalendarEvent.start_time.desc()).all()
    
    # Get entity emails for matching
    entity_emails: set = set()
    
    if entity_type == "lead":
        # Get lead's associated contacts (if any)
        lead = db.query(models.Lead).filter(models.Lead.id == entity_id).first()
        if lead and lead.owner:
            entity_emails.add(lead.owner.email.lower() if lead.owner.email else "")
    elif entity_type == "contact":
        contact = db.query(models.Contact).filter(models.Contact.id == entity_id).first()
        if contact and contact.email:
            entity_emails.add(contact.email.lower())
    
    for event in calendar_events:
        # Check if any attendee matches the entity's emails
        attendee_emails: List[str] = []
        if event.attendees:
            try:
                attendees_data = json.loads(event.attendees)
                attendee_emails = [
                    att.get('email', '').lower() 
                    for att in attendees_data 
                    if att.get('email')
                ]
            except (json.JSONDecodeError, TypeError):
                attendee_emails = []
        
        # For MVP: include event if entity emails match attendees
        # or if description/summary contains the entity_id
        is_related = False
        
        if entity_emails and any(email in entity_emails for email in attendee_emails):
            is_related = True
        
        # Also check if entity_id is mentioned in description (future metadata linking)
        if event.description and entity_id in event.description:
            is_related = True
        
        # For MVP: if no specific matching logic, skip unrelated events
        if not is_related and entity_emails:
            continue
        
        # Build timeline entry
        details = {
            "google_event_id": event.google_event_id,
            "start_time": event.start_time.isoformat() if event.start_time else None,
            "end_time": event.end_time.isoformat() if event.end_time else None,
            "status": event.status,
            "meet_link": event.meet_link,
            "html_link": event.html_link,
            "attendees": attendee_emails,
        }
        
        # Use organizer as the user
        user = None
        if event.organizer_email:
            user = TimelineUser(email=event.organizer_email)
        
        entry = TimelineEntry(
            type="meeting",
            timestamp=event.start_time or event.created_at,
            summary=event.summary or "Calendar Event",
            details=details,
            user=user,
        )
        entries.append(entry)
    
    return entries


def _fetch_audit_logs(
    db: Session,
    entity_type: str,
    entity_id: str
) -> List[TimelineEntry]:
    """
    Fetch audit logs for a specific entity.
    
    Args:
        db: Database session
        entity_type: Type of entity (lead, deal, contact)
        entity_id: UUID of the entity
        
    Returns:
        List of TimelineEntry objects for audit logs
    """
    entries: List[TimelineEntry] = []
    
    audit_logs = db.query(models.AuditLog).filter(
        models.AuditLog.entity_type == entity_type,
        models.AuditLog.entity_id == entity_id
    ).order_by(models.AuditLog.timestamp.desc()).all()
    
    for log in audit_logs:
        # Build summary based on action
        summary = _build_audit_summary(log)
        
        # Build details
        details = {
            "action": log.action,
            "changes": log.changes or {},
        }
        
        # Get user info
        user = None
        if log.actor:
            user = TimelineUser(
                id=log.actor.id,
                name=log.actor.name,
                email=log.actor.email,
            )
        elif log.actor_id:
            user = TimelineUser(id=log.actor_id)
        
        entry = TimelineEntry(
            type="audit",
            timestamp=log.timestamp,
            summary=summary,
            details=details,
            user=user,
        )
        entries.append(entry)
    
    return entries


def _build_audit_summary(log: models.AuditLog) -> str:
    """
    Build a human-readable summary for an audit log entry.
    
    Args:
        log: AuditLog model instance
        
    Returns:
        Human-readable summary string
    """
    action = log.action
    changes = log.changes or {}
    
    if action == "create":
        return f"Created {log.entity_type}"
    
    if action == "delete":
        return f"Deleted {log.entity_type}"
    
    if action == "status_change":
        if "lead_status_id" in changes:
            old_val = changes["lead_status_id"].get("old", "N/A")
            new_val = changes["lead_status_id"].get("new", "N/A")
            return f"Status changed: {old_val} → {new_val}"
        return f"Status changed"
    
    if action == "update":
        changed_fields = list(changes.keys())
        if len(changed_fields) == 1:
            field = changed_fields[0]
            old_val = changes[field].get("old", "N/A")
            new_val = changes[field].get("new", "N/A")
            return f"{field} changed: {old_val} → {new_val}"
        elif changed_fields:
            return f"Updated: {', '.join(changed_fields)}"
        return "Updated"
    
    return f"Action: {action}"


def _fetch_emails_placeholder(
    entity_type: str,
    entity_id: str
) -> List[TimelineEntry]:
    """
    Placeholder for email fetching.
    
    This is a placeholder for future Gmail integration to fetch
    emails related to the entity.
    
    Args:
        entity_type: Type of entity (lead, deal, contact)
        entity_id: UUID of the entity
        
    Returns:
        Empty list (placeholder)
    """
    # TODO: Implement Gmail API integration to fetch emails
    # related to the entity by:
    # - Contact email matching
    # - Thread/conversation linking
    # - Subject/body content matching
    return []


@router.get(
    "/{entity_type}/{entity_id}",
    response_model=TimelineResponse,
    summary="Get Unified Timeline",
    description="Retrieves a unified timeline for a CRM entity, aggregating "
                "calendar events, audit logs, and emails (placeholder) into a "
                "single chronological view sorted by timestamp descending."
)
def get_timeline(
    entity_type: Literal["lead", "deal", "contact"],
    entity_id: str,
    limit: int = Query(50, ge=1, le=200, description="Maximum items to return"),
    offset: int = Query(0, ge=0, description="Number of items to skip"),
    db: Session = Depends(get_db),
    current_user: UserContext = Depends(get_current_user)
):
    """
    Get the unified timeline for an entity.
    
    **Path Parameters:**
    - **entity_type**: Type of entity (lead, deal, or contact)
    - **entity_id**: UUID of the entity
    
    **Query Parameters:**
    - **limit**: Maximum number of timeline items to return (default: 50, max: 200)
    - **offset**: Number of items to skip for pagination (default: 0)
    
    **Returns:**
    - Chronologically ordered list of timeline entries from all sources
    - Each entry includes type, timestamp, summary, details, and user info
    
    **Timeline Entry Types:**
    - **meeting**: Calendar events with meet links and attendees
    - **audit**: Entity changes (create, update, status_change)
    - **email**: Email communications (placeholder for future)
    """
    timeline_logger.info(
        action="get_timeline",
        status="started",
        entity_type=entity_type,
        entity_id=entity_id,
        limit=limit,
        offset=offset
    )
    
    try:
        # Validate entity exists
        entity = None
        if entity_type == "lead":
            entity = db.query(models.Lead).filter(models.Lead.id == entity_id).first()
        elif entity_type == "deal":
            entity = db.query(models.Deal).filter(models.Deal.id == entity_id).first()
        elif entity_type == "contact":
            entity = db.query(models.Contact).filter(models.Contact.id == entity_id).first()
        
        if not entity:
            timeline_logger.warning(
                action="get_timeline",
                status="not_found",
                entity_type=entity_type,
                entity_id=entity_id
            )
            raise HTTPException(
                status_code=404,
                detail=f"{entity_type.capitalize()} with ID {entity_id} not found"
            )
        
        # Fetch all timeline items
        all_entries: List[TimelineEntry] = []
        
        # 1. Fetch calendar events
        calendar_entries = _fetch_calendar_events(db, entity_type, entity_id)
        all_entries.extend(calendar_entries)
        
        # 2. Fetch audit logs
        audit_entries = _fetch_audit_logs(db, entity_type, entity_id)
        all_entries.extend(audit_entries)
        
        # 3. Fetch emails (placeholder)
        email_entries = _fetch_emails_placeholder(entity_type, entity_id)
        all_entries.extend(email_entries)
        
        # Sort all entries by timestamp descending
        all_entries.sort(key=lambda e: e.timestamp, reverse=True)
        
        # Calculate total before pagination
        total = len(all_entries)
        
        # Apply pagination
        paginated_entries = all_entries[offset:offset + limit]
        
        timeline_logger.info(
            action="get_timeline",
            status="success",
            entity_type=entity_type,
            entity_id=entity_id,
            total_items=total,
            returned_items=len(paginated_entries),
            calendar_count=len(calendar_entries),
            audit_count=len(audit_entries),
            email_count=len(email_entries)
        )
        
        return TimelineResponse(
            items=paginated_entries,
            pagination=TimelinePagination(
                total=total,
                limit=limit,
                offset=offset
            )
        )
        
    except HTTPException:
        raise
    except Exception as e:
        timeline_logger.error(
            action="get_timeline",
            status="error",
            entity_type=entity_type,
            entity_id=entity_id,
            error=str(e)
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch timeline: {str(e)}"
        )
