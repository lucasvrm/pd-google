from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Optional

from email.utils import parsedate_to_datetime
from sqlalchemy.orm import Session

import models
from services.crm_contact_service import CRMContactService
from services.google_gmail_service import GoogleGmailService
from utils.structured_logging import StructuredLogger


logger = logging.getLogger("pipedesk_drive.lead_engagement")
engagement_logger = StructuredLogger(
    service="lead_engagement", logger_name="pipedesk_drive.lead_engagement"
)


EMAIL_RECEIVED_SCORE = 3
EMAIL_SENT_SCORE = 2
EVENT_FUTURE_SCORE = 4
EVENT_PAST_SCORE = 2
GMAIL_MAX_RESULTS = 200


@dataclass
class LeadEngagement:
    lead_id: str
    last_email_at: Optional[datetime] = None
    last_event_at: Optional[datetime] = None
    last_interaction_at: Optional[datetime] = None
    total_emails: int = 0
    total_events: int = 0
    total_interactions: int = 0
    engagement_score: int = 0


def _normalize_dt(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _extract_emails(raw_value: Optional[str]) -> list[str]:
    if not raw_value:
        return []

    emails: list[str] = []
    for part in raw_value.split(","):
        value = part.strip()
        if "<" in value and ">" in value:
            value = value.split("<", 1)[1].split(">", 1)[0].strip()
        if value:
            emails.append(value.lower())
    return emails


def _parse_gmail_direction(headers: dict[str, str], contact_set: set[str]) -> Optional[str]:
    from_email = _extract_emails(headers.get("from"))
    to_emails = _extract_emails(headers.get("to"))
    cc_emails = _extract_emails(headers.get("cc"))
    bcc_emails = _extract_emails(headers.get("bcc"))

    if any(email in contact_set for email in from_email):
        return "received"

    for email in to_emails + cc_emails + bcc_emails:
        if email in contact_set:
            return "sent"

    return None


def _parse_message_datetime(headers: dict[str, str]) -> Optional[datetime]:
    try:
        dt = parsedate_to_datetime(headers.get("date", ""))
        return _normalize_dt(dt)
    except Exception:
        return None


def _score_event(event_time: Optional[datetime], now: datetime) -> int:
    if event_time is None:
        return EVENT_PAST_SCORE
    event_time = _normalize_dt(event_time)
    if event_time and event_time >= now:
        return EVENT_FUTURE_SCORE
    return EVENT_PAST_SCORE


def compute_lead_engagement(
    lead_id: str,
    db: Session,
    gmail_service: Optional[GoogleGmailService] = None,
    contact_service: Optional[CRMContactService] = None,
    now: Optional[datetime] = None,
) -> LeadEngagement:
    """Collect email and calendar engagement for a lead."""

    now = _normalize_dt(now or datetime.now(timezone.utc)) or datetime.now(timezone.utc)
    contact_service = contact_service or CRMContactService(db)
    gmail_service = gmail_service or GoogleGmailService()

    contact_emails = contact_service.get_entity_contact_emails("lead", lead_id)
    contact_set = set(email.lower().strip() for email in contact_emails)

    engagement = LeadEngagement(lead_id=lead_id)

    if not contact_set:
        return engagement

    # --- Emails ---
    try:
        query_parts = [f"from:{email} OR to:{email}" for email in contact_set]
        gmail_query = " OR ".join(query_parts)

        response = gmail_service.list_messages(
            query=gmail_query, max_results=GMAIL_MAX_RESULTS
        )
        for meta in response.get("messages", []):
            msg = gmail_service.get_message(meta.get("id"))
            headers = gmail_service._parse_headers(  # type: ignore[attr-defined]
                msg.get("payload", {}).get("headers", [])
            )

            direction = _parse_gmail_direction(headers, contact_set)
            if direction is None:
                continue

            msg_dt = _parse_message_datetime(headers)
            engagement.total_emails += 1
            engagement.engagement_score += (
                EMAIL_RECEIVED_SCORE if direction == "received" else EMAIL_SENT_SCORE
            )

            if msg_dt and (
                engagement.last_email_at is None or msg_dt > engagement.last_email_at
            ):
                engagement.last_email_at = msg_dt

    except Exception as exc:  # pragma: no cover - integration error handling
        engagement_logger.error(
            action="compute_lead_engagement",
            message="Failed to aggregate Gmail messages",
            error=exc,
            entity_type="lead",
            entity_id=lead_id,
        )

    # --- Calendar Events ---
    try:
        calendar_query = db.query(models.CalendarEvent).filter(
            models.CalendarEvent.status != "cancelled"
        )
        events: Iterable[models.CalendarEvent] = (
            calendar_query.order_by(models.CalendarEvent.start_time.desc()).all()
        )

        for event in events:
            attendees_data = []
            if event.attendees:
                try:
                    attendees_data = json.loads(event.attendees)
                except (json.JSONDecodeError, TypeError):
                    attendees_data = []

            matched = False
            for attendee in attendees_data:
                attendee_email = attendee.get("email", "").lower().strip()
                if attendee_email and attendee_email in contact_set:
                    matched = True
                    break

            organizer_email = (event.organizer_email or "").lower().strip()
            if organizer_email and organizer_email in contact_set:
                matched = True

            if not matched:
                continue

            engagement.total_events += 1
            event_time = event.start_time or event.end_time
            event_time = _normalize_dt(event_time)
            engagement.engagement_score += _score_event(event_time, now)

            if event_time and (
                engagement.last_event_at is None or event_time > engagement.last_event_at
            ):
                engagement.last_event_at = event_time

    except Exception as exc:  # pragma: no cover - integration error handling
        engagement_logger.error(
            action="compute_lead_engagement",
            message="Failed to aggregate calendar events",
            error=exc,
            entity_type="lead",
            entity_id=lead_id,
        )

    engagement.last_interaction_at = max(
        [dt for dt in [engagement.last_email_at, engagement.last_event_at] if dt is not None],
        default=None,
    )
    engagement.total_interactions = engagement.total_emails + engagement.total_events

    return engagement

