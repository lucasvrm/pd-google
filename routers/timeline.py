"""
Timeline Router - Unified Timeline API

Provides a single endpoint for fetching all activities related to a CRM entity.
Aggregates data from:
- Calendar Events (meetings)
- Audit Logs (entity changes)
- Emails (Gmail integration)

This is the "single source of truth" for the Lead/Deal View timeline.
"""

import json
import traceback
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional, Set, Union

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
from services.google_gmail_service import GoogleGmailService

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


def _validate_uuid(value: str, field_name: str = "entity_id") -> None:
    """
    Validate that a string is a valid UUID.

    Raises:
        HTTPException(400) if invalid
    """
    try:
        uuid.UUID(value)
    except Exception:
        timeline_logger.warning(
            action="validate_uuid",
            status="invalid",
            message=f"Invalid UUID for {field_name}",
            field_name=field_name,
            value_preview=str(value)[:80] if value else None,
        )
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {field_name}: must be a UUID"
        )


def _safe_parse_timestamp(value: Union[datetime, str, None]) -> Optional[datetime]:
    """
    Safely parse a timestamp value into a datetime object.

    Args:
        value: Can be datetime, str (ISO format), or None

    Returns:
        datetime object or None if parsing fails
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            # Handle ISO format strings
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            # Ensure tz-aware
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed
        except (ValueError, AttributeError):
            timeline_logger.warning(
                action="parse_timestamp",
                status="failed",
                message="Failed to parse timestamp",
                value=str(value)[:100],
            )
            return None
    return None


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
        models.CalendarEvent.status != "cancelled"
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
        try:
            # Check if any attendee matches the entity's emails
            attendee_emails: List[str] = []
            if event.attendees:
                try:
                    attendees_data = json.loads(event.attendees)
                    attendee_emails = [
                        att.get("email", "").lower()
                        for att in attendees_data
                        if att.get("email")
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

            # For MVP: if no specific matching logic, skip unrelated events when we have entity emails
            if not is_related and entity_emails:
                continue

            # Safely parse start and end times
            start_time = _safe_parse_timestamp(event.start_time)
            end_time = _safe_parse_timestamp(event.end_time)
            created_at = _safe_parse_timestamp(event.created_at)

            # Build timeline entry
            details = {
                "google_event_id": event.google_event_id,
                "start_time": start_time.isoformat() if start_time else None,
                "end_time": end_time.isoformat() if end_time else None,
                "status": event.status,
                "meet_link": event.meet_link,
                "html_link": event.html_link,
                "attendees": attendee_emails,
            }

            # Use organizer as the user
            user = None
            if event.organizer_email:
                user = TimelineUser(email=event.organizer_email)

            # Determine timestamp - use start_time, fall back to created_at, then current time
            event_timestamp = start_time or created_at or datetime.now(timezone.utc)

            entry = TimelineEntry(
                type="meeting",
                timestamp=event_timestamp,
                summary=event.summary or "Calendar Event",
                details=details,
                user=user,
            )
            entries.append(entry)
        except Exception as e:
            # Log error but continue processing other events
            timeline_logger.warning(
                action="fetch_calendar_event",
                status="skipped",
                message="Failed to process calendar event; skipping",
                event_id=getattr(event, "id", "unknown"),
                error_type=type(e).__name__,
                error_message=str(e),
            )
            continue

    return entries


def _safe_parse_changes(changes: Union[Dict[str, Any], str, None]) -> Dict[str, Any]:
    """
    Safely parse the changes field from an audit log.

    Args:
        changes: Can be dict, str (JSON), or None

    Returns:
        dict of changes, or empty dict if parsing fails
    """
    if changes is None:
        return {}
    if isinstance(changes, dict):
        return changes
    if isinstance(changes, str):
        try:
            parsed = json.loads(changes)
            if isinstance(parsed, dict):
                return parsed
            return {}
        except (json.JSONDecodeError, TypeError):
            timeline_logger.warning(
                action="parse_changes",
                status="failed",
                message="Failed to parse audit changes JSON",
                changes_preview=str(changes)[:100],
            )
            return {}
    return {}


def _build_audit_summary(log: models.AuditLog, changes: Optional[Dict[str, Any]] = None) -> str:
    """
    Build a human-readable summary for an audit log entry.

    Args:
        log: AuditLog model instance
        changes: Pre-parsed changes dict (optional, uses log.changes if not provided)

    Returns:
        Human-readable summary string
    """
    action = log.action

    # Use provided changes or parse from log
    if changes is None:
        changes = _safe_parse_changes(log.changes)

    if action == "create":
        return f"Created {log.entity_type}"

    if action == "delete":
        return f"Deleted {log.entity_type}"

    if action == "status_change":
        if "lead_status_id" in changes:
            status_change = changes.get("lead_status_id", {})
            if isinstance(status_change, dict):
                old_val = status_change.get("old", "N/A")
                new_val = status_change.get("new", "N/A")
                return f"Status changed: {old_val} → {new_val}"
        return "Status changed"

    if action == "update":
        changed_fields = list(changes.keys())
        if len(changed_fields) == 1:
            field = changed_fields[0]
            field_change = changes.get(field, {})
            if isinstance(field_change, dict):
                old_val = field_change.get("old", "N/A")
                new_val = field_change.get("new", "N/A")
                return f"{field} changed: {old_val} → {new_val}"
            return f"{field} changed"
        elif changed_fields:
            return f"Updated: {', '.join(changed_fields)}"
        return "Updated"

    return f"Action: {action}"


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
        try:
            # Safely parse the changes field
            changes = _safe_parse_changes(log.changes)

            # Build summary based on action (pass parsed changes)
            summary = _build_audit_summary(log, changes)

            # Build details
            details = {
                "action": log.action,
                "changes": changes,
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

            # Safely parse timestamp
            log_timestamp = _safe_parse_timestamp(log.timestamp)
            if log_timestamp is None:
                # Skip entry if timestamp is invalid
                timeline_logger.warning(
                    action="fetch_audit_log",
                    status="skipped_invalid_timestamp",
                    message="Audit log timestamp is invalid; skipping",
                    log_id=getattr(log, "id", "unknown"),
                )
                continue

            entry = TimelineEntry(
                type="audit",
                timestamp=log_timestamp,
                summary=summary,
                details=details,
                user=user,
            )
            entries.append(entry)
        except Exception as e:
            # Log error but continue processing other logs
            timeline_logger.warning(
                action="fetch_audit_log",
                status="skipped",
                message="Failed to process audit log; skipping",
                log_id=getattr(log, "id", "unknown"),
                error_type=type(e).__name__,
                error_message=str(e),
            )
            continue

    return entries


def _extract_email_domain(email: str) -> Optional[str]:
    """
    Extract the domain from an email address.

    Args:
        email: Email address string

    Returns:
        Domain string (lowercase) or None if invalid
    """
    if not email or "@" not in email:
        return None
    try:
        # Handle "Name <email@domain.com>" format
        if "<" in email and ">" in email:
            email = email.split("<")[1].split(">")[0]
        return email.strip().lower().split("@")[1]
    except (IndexError, AttributeError):
        return None


def _get_lead_contact_emails(db: Session, lead_id: str) -> Set[str]:
    """
    Get all contact emails associated with a lead.

    Args:
        db: Database session
        lead_id: UUID of the lead

    Returns:
        Set of lowercase email addresses
    """
    emails: Set[str] = set()

    # Get contacts linked to this lead via lead_contacts junction table
    lead_contacts = db.query(models.LeadContact).filter(
        models.LeadContact.lead_id == lead_id
    ).all()

    for lc in lead_contacts:
        if lc.contact and lc.contact.email:
            emails.add(lc.contact.email.strip().lower())

    return emails


def _get_lead_company_domain(db: Session, lead_id: str) -> Optional[str]:
    """
    Get the company domain associated with a lead.

    This is used for matching emails by domain when no direct contact email matches.
    Extracts the domain from the lead's contacts, preferring non-generic email domains.

    Args:
        db: Database session
        lead_id: UUID of the lead

    Returns:
        Company domain (lowercase) or None
    """
    lead = db.query(models.Lead).filter(models.Lead.id == lead_id).first()
    if not lead:
        return None

    # Extract domain from the lead's contacts (non-generic domains)
    lead_contacts = db.query(models.LeadContact).filter(
        models.LeadContact.lead_id == lead_id
    ).all()

    for lc in lead_contacts:
        if lc.contact and lc.contact.email:
            domain = _extract_email_domain(lc.contact.email)
            if domain and not domain.endswith(("gmail.com", "outlook.com", "hotmail.com", "yahoo.com")):
                return domain

    return None


def _build_gmail_search_query(emails: Set[str], company_domain: Optional[str] = None) -> Optional[str]:
    """
    Build a Gmail search query to find emails related to the given contacts.

    Args:
        emails: Set of email addresses to search for
        company_domain: Optional company domain for broader matching

    Returns:
        Gmail search query string or None if no valid search criteria
    """
    if not emails and not company_domain:
        return None

    query_parts: List[str] = []

    # Add specific email addresses
    for email in emails:
        # Search for emails from or to these contacts
        query_parts.append(f"(from:{email} OR to:{email})")

    # Add company domain matching if available and not a generic domain
    if company_domain:
        query_parts.append(f"(from:*@{company_domain} OR to:*@{company_domain})")

    if not query_parts:
        return None

    # Combine with OR to get all related emails
    return " OR ".join(query_parts)


def _parse_email_addresses(header_value: Optional[str]) -> List[str]:
    """
    Parse email addresses from a header value.

    Handles formats like:
    - "email@example.com"
    - "Name <email@example.com>"
    - "email1@example.com, email2@example.com"

    Args:
        header_value: Raw header value from email

    Returns:
        List of email addresses (lowercase)
    """
    if not header_value:
        return []

    emails: List[str] = []
    # Split by comma for multiple addresses
    parts = header_value.split(",")

    for part in parts:
        part = part.strip()
        if "<" in part and ">" in part:
            # Extract email from "Name <email@example.com>" format
            try:
                email = part.split("<")[1].split(">")[0].strip().lower()
                if email:
                    emails.append(email)
            except IndexError:
                continue
        elif "@" in part:
            # Plain email address
            emails.append(part.strip().lower())

    return emails


def _fetch_emails_from_gmail(
    db: Session,
    entity_type: str,
    entity_id: str,
    max_results: int = 50
) -> List[TimelineEntry]:
    """
    Fetch emails from Gmail related to the entity.

    For leads, this searches for emails to/from/cc/bcc contacts associated with the lead.
    Also matches by company domain when applicable.

    Args:
        db: Database session
        entity_type: Type of entity (lead, deal, contact)
        entity_id: UUID of the entity
        max_results: Maximum number of emails to fetch

    Returns:
        List of TimelineEntry objects for emails
    """
    entries: List[TimelineEntry] = []

    # Get contact emails based on entity type
    contact_emails: Set[str] = set()
    company_domain: Optional[str] = None

    if entity_type == "lead":
        contact_emails = _get_lead_contact_emails(db, entity_id)
        company_domain = _get_lead_company_domain(db, entity_id)
    elif entity_type == "contact":
        # For contacts, search by the contact's own email
        contact = db.query(models.Contact).filter(models.Contact.id == entity_id).first()
        if contact and contact.email:
            contact_emails.add(contact.email.strip().lower())
    # For deals, we could expand to search by company contacts (future enhancement)

    # Build Gmail search query
    search_query = _build_gmail_search_query(contact_emails, company_domain)

    if not search_query:
        timeline_logger.info(
            action="fetch_emails",
            status="skipped",
            message="No contact emails found for entity",
            entity_type=entity_type,
            entity_id=entity_id,
        )
        return []

    try:
        # Initialize Gmail service
        gmail_service = GoogleGmailService()

        # Check if service is properly configured
        gmail_service._check_auth()

        timeline_logger.info(
            action="fetch_emails",
            status="searching",
            message="Searching Gmail for related emails",
            entity_type=entity_type,
            entity_id=entity_id,
            contact_count=len(contact_emails),
            has_company_domain=bool(company_domain),
        )

        # Search for messages
        result = gmail_service.list_messages(
            query=search_query,
            max_results=max_results
        )

        messages = result.get("messages", [])

        if not messages:
            timeline_logger.info(
                action="fetch_emails",
                status="no_results",
                message="No emails found matching search criteria",
                entity_type=entity_type,
                entity_id=entity_id,
            )
            return []

        # Fetch message details and convert to timeline entries
        for msg_ref in messages:
            try:
                msg_data = gmail_service.get_message(msg_ref["id"], format="metadata")
                headers = gmail_service._parse_headers(
                    msg_data.get("payload", {}).get("headers", [])
                )

                # Parse timestamp from internal date
                timestamp: Optional[datetime] = None
                if "internalDate" in msg_data:
                    try:
                        timestamp = datetime.fromtimestamp(
                            int(msg_data["internalDate"]) / 1000,
                            tz=timezone.utc
                        )
                    except (ValueError, TypeError):
                        timestamp = None

                if not timestamp:
                    # Skip messages without valid timestamp
                    continue

                # Parse email addresses
                from_emails = _parse_email_addresses(headers.get("from"))
                to_emails = _parse_email_addresses(headers.get("to"))
                cc_emails = _parse_email_addresses(headers.get("cc"))
                bcc_emails = _parse_email_addresses(headers.get("bcc"))

                # Build timeline entry
                subject = headers.get("subject", "(No Subject)")
                snippet = msg_data.get("snippet", "")

                details = {
                    "message_id": msg_data.get("id"),
                    "thread_id": msg_data.get("threadId"),
                    "subject": subject,
                    "from": from_emails[0] if from_emails else None,
                    "to": to_emails,
                    "cc": cc_emails if cc_emails else None,
                    "bcc": bcc_emails if bcc_emails else None,
                    "snippet": snippet,
                    "labels": msg_data.get("labelIds", []),
                }

                # Build user from sender
                user = None
                if from_emails:
                    user = TimelineUser(email=from_emails[0])

                entry = TimelineEntry(
                    type="email",
                    timestamp=timestamp,
                    summary=subject,
                    details=details,
                    user=user,
                )
                entries.append(entry)

            except Exception as msg_error:
                timeline_logger.warning(
                    action="fetch_email_message",
                    status="skipped",
                    message="Failed to process email message; skipping",
                    message_id=msg_ref.get("id", "unknown"),
                    error_type=type(msg_error).__name__,
                    error_message=str(msg_error),
                )
                continue

        timeline_logger.info(
            action="fetch_emails",
            status="success",
            message=f"Fetched {len(entries)} emails from Gmail",
            entity_type=entity_type,
            entity_id=entity_id,
            email_count=len(entries),
        )

    except Exception as e:
        timeline_logger.warning(
            action="fetch_emails",
            status="failed",
            message="Failed to fetch emails from Gmail; continuing without email entries",
            entity_type=entity_type,
            entity_id=entity_id,
            error_type=type(e).__name__,
            error_message=str(e),
        )
        # Return empty list on failure - graceful degradation
        return []

    return entries


@router.get(
    "/{entity_type}/{entity_id}",
    response_model=TimelineResponse,
    summary="Get Unified Timeline",
    description="Retrieves a unified timeline for a CRM entity, aggregating "
                "calendar events, audit logs, and Gmail emails into a "
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
    - **email**: Gmail email communications with subject, from/to/cc/bcc, snippet, message_id, thread_id
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
        # Validate UUID format early to avoid downstream crashes / ambiguous DB errors
        _validate_uuid(entity_id, "entity_id")

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
                message="Entity not found",
                entity_type=entity_type,
                entity_id=entity_id
            )
            raise HTTPException(
                status_code=404,
                detail=f"{entity_type.capitalize()} with ID {entity_id} not found"
            )

        # Fetch all timeline items with graceful degradation per source
        all_entries: List[TimelineEntry] = []

        calendar_entries: List[TimelineEntry] = []
        audit_entries: List[TimelineEntry] = []
        email_entries: List[TimelineEntry] = []

        # 1. Fetch calendar events
        try:
            calendar_entries = _fetch_calendar_events(db, entity_type, entity_id)
        except Exception as source_exc:
            timeline_logger.warning(
                action="get_timeline_calendar",
                status="degraded",
                message="Calendar source failed; continuing without calendar entries",
                entity_type=entity_type,
                entity_id=entity_id,
                error_type=type(source_exc).__name__,
                error_message=str(source_exc),
            )
            calendar_entries = []

        all_entries.extend(calendar_entries)

        # 2. Fetch audit logs
        try:
            audit_entries = _fetch_audit_logs(db, entity_type, entity_id)
        except Exception as source_exc:
            timeline_logger.warning(
                action="get_timeline_audit",
                status="degraded",
                message="Audit source failed; continuing without audit entries",
                entity_type=entity_type,
                entity_id=entity_id,
                error_type=type(source_exc).__name__,
                error_message=str(source_exc),
            )
            audit_entries = []

        all_entries.extend(audit_entries)

        # 3. Fetch emails from Gmail
        try:
            email_entries = _fetch_emails_from_gmail(db, entity_type, entity_id)
        except Exception as source_exc:
            timeline_logger.warning(
                action="get_timeline_email",
                status="degraded",
                message="Email source failed; continuing without email entries",
                entity_type=entity_type,
                entity_id=entity_id,
                error_type=type(source_exc).__name__,
                error_message=str(source_exc),
            )
            email_entries = []

        all_entries.extend(email_entries)

        # Sort all entries by timestamp descending (defensive: handle any unexpected None or naive timestamps)
        def _sort_key(entry: TimelineEntry) -> datetime:
            ts = getattr(entry, "timestamp", None)
            if isinstance(ts, datetime):
                # Ensure timezone-aware for consistent sorting
                if ts.tzinfo is None:
                    return ts.replace(tzinfo=timezone.utc)
                return ts
            return datetime.min.replace(tzinfo=timezone.utc)

        all_entries.sort(key=_sort_key, reverse=True)

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
        # IMPORTANT: StructuredLogger.error() requires message= and optionally error=
        timeline_logger.error(
            action="get_timeline",
            message="Unhandled exception in get_timeline",
            error=e,
            entity_type=entity_type,
            entity_id=entity_id,
            limit=limit,
            offset=offset,
            traceback=traceback.format_exc(),
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to fetch timeline"
        )
