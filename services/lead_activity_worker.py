import logging
import time
from datetime import datetime, timezone

from sqlalchemy.orm import Session

import models
from database import SessionLocal
from services.crm_contact_service import CRMContactService
from services.google_gmail_service import GoogleGmailService
from services.lead_engagement_service import compute_lead_engagement
from utils.structured_logging import StructuredLogger


activity_logger = StructuredLogger(
    service="lead_activity", logger_name="pipedesk_drive.lead_activity"
)
logger = logging.getLogger("pipedesk_drive.lead_activity")


class LeadActivityWorker:
    """Worker that refreshes engagement stats for active leads."""

    def __init__(self, session_factory=SessionLocal):
        self.session_factory = session_factory

    def _process_lead(
        self,
        db: Session,
        lead: models.Lead,
        gmail_service: GoogleGmailService,
        contact_service: CRMContactService,
    ) -> None:
        stats = compute_lead_engagement(
            lead_id=lead.id,
            db=db,
            gmail_service=gmail_service,
            contact_service=contact_service,
        )

        existing = (
            db.query(models.LeadActivityStats)
            .filter(models.LeadActivityStats.lead_id == lead.id)
            .first()
        )

        if existing is None:
            existing = models.LeadActivityStats(lead_id=lead.id)
            db.add(existing)

        existing.engagement_score = stats.engagement_score
        existing.last_interaction_at = stats.last_interaction_at
        existing.last_email_at = stats.last_email_at
        existing.last_event_at = stats.last_event_at
        existing.total_emails = stats.total_emails
        existing.total_events = stats.total_events
        existing.total_interactions = stats.total_interactions

        lead.last_interaction_at = stats.last_interaction_at
        lead.updated_at = lead.updated_at or datetime.now(timezone.utc)

    def run(self) -> None:
        started = time.time()
        processed = 0
        errors: list[str] = []

        db = self.session_factory()
        try:
            leads = db.query(models.Lead).all()
            gmail_service = GoogleGmailService()
            contact_service = CRMContactService(db)

            for lead in leads:
                try:
                    self._process_lead(db, lead, gmail_service, contact_service)
                    db.commit()
                    processed += 1
                except Exception as exc:  # pragma: no cover - worker error path
                    db.rollback()
                    errors.append(lead.id)
                    activity_logger.error(
                        action="lead_activity_stats",
                        message="Failed processing lead",
                        error=exc,
                        entity_type="lead",
                        entity_id=lead.id,
                    )

        finally:
            db.close()

        duration = time.time() - started
        activity_logger.info(
            action="lead_activity_stats",
            status="completed",
            message="Lead activity refresh finished",
            processed=processed,
            errors=len(errors),
            duration_seconds=round(duration, 2),
        )

