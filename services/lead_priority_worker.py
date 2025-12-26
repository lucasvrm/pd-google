import logging
import time
from typing import Optional

from sqlalchemy.orm import joinedload

import models
from database import SessionLocal
from services.lead_priority_service import calculate_lead_priority, classify_priority_bucket
from services.lead_priority_config_service import get_lead_priority_config
from services.feature_flags_service import is_auto_priority_enabled
from utils.structured_logging import StructuredLogger


priority_logger = StructuredLogger(
    service="lead_priority", logger_name="pipedesk_drive.lead_priority"
)
logger = logging.getLogger("pipedesk_drive.lead_priority")


class LeadPriorityWorker:
    """Worker that keeps lead priority scores in sync."""

    def __init__(self, session_factory=SessionLocal):
        self.session_factory = session_factory

    def run(self) -> None:
        # ========== NOVO: Verificar feature flag ==========
        db_check = self.session_factory()
        try:
            if not is_auto_priority_enabled(db_check):
                priority_logger.info(
                    action="lead_priority_score",
                    status="skipped",
                    message="Cálculo automático de prioridade desabilitado (feature_lead_auto_priority=false)",
                )
                return
            
            # ========== NOVO: Carregar config uma vez ==========
            priority_config = get_lead_priority_config(db_check)
            # ========== FIM NOVO ==========
        finally:
            db_check.close()
        # ========== FIM NOVO ==========

        started = time.time()
        processed = 0
        errors = 0
        errors_by_lead: list[str] = []

        db = self.session_factory()
        try:
            # ========== MODIFICADO: Eager-load lead_status e lead_origin ==========
            leads = (
                db.query(models.Lead)
                .options(
                    joinedload(models.Lead.activity_stats),
                    joinedload(models.Lead.lead_status),
                    joinedload(models.Lead.lead_origin),
                )
                .all()
            )
            # ========== FIM MODIFICADO ==========

            for lead in leads:
                try:
                    stats: Optional[models.LeadActivityStats] = lead.activity_stats
                    # ========== MODIFICADO: Passar config e calcular bucket ==========
                    score = calculate_lead_priority(lead, stats, config=priority_config)
                    bucket = classify_priority_bucket(score, config=priority_config)
                    lead.priority_score = score
                    # Optionally store bucket if there's a column for it:
                    # lead.priority_bucket = bucket
                    # ========== FIM MODIFICADO ==========
                    processed += 1
                except Exception as exc:  # pragma: no cover - worker error path
                    errors += 1
                    errors_by_lead.append(lead.id)
                    priority_logger.error(
                        action="lead_priority_score",
                        message="Failed to refresh lead priority",
                        error=exc,
                        entity_type="lead",
                        entity_id=lead.id,
                    )

            db.commit()
        finally:
            db.close()

        duration = time.time() - started
        priority_logger.info(
            action="lead_priority_score",
            status="completed",
            message="Lead priority refresh finished",
            processed=processed,
            errors=errors,
            errors_by_lead=errors_by_lead,
            duration_seconds=round(duration, 2),
        )

