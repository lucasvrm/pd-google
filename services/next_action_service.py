from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional


STALE_INTERACTION_DAYS = 5
HIGH_ENGAGEMENT_SCORE = 70
NEW_LEAD_MAX_AGE_DAYS = 14


def _normalize_datetime(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def suggest_next_action(lead: Any, stats: Any, now: Optional[datetime] = None) -> Dict[str, str]:
    """Suggest the next action for a lead based on recency and engagement."""

    current_time = _normalize_datetime(now or datetime.now(timezone.utc)) or datetime.now(
        timezone.utc
    )

    created_at = _normalize_datetime(getattr(lead, "created_at", None)) or current_time
    lead_age_days = max((current_time - created_at).days, 0)

    last_event_at = _normalize_datetime(getattr(stats, "last_event_at", None)) if stats else None
    if last_event_at and last_event_at > current_time:
        return {
            "code": "prepare_for_meeting",
            "label": "Preparar para reunião",
            "reason": f"Reunião futura agendada para {last_event_at.date()}",
        }

    last_interaction = getattr(stats, "last_interaction_at", None) if stats else None
    if last_interaction is None:
        last_interaction = getattr(lead, "last_interaction_at", None)
    last_interaction = _normalize_datetime(last_interaction)

    if last_interaction is None:
        reason = "Lead novo sem interação" if lead_age_days <= NEW_LEAD_MAX_AGE_DAYS else "Nenhuma interação registrada"
        return {"code": "call_first_time", "label": "Fazer primeira ligação", "reason": reason}

    days_since_interaction = max((current_time - last_interaction).days, 0)

    engagement_score = getattr(stats, "engagement_score", 0) if stats else 0
    has_deal = getattr(lead, "qualified_company_id", None) is not None
    if engagement_score >= HIGH_ENGAGEMENT_SCORE and not has_deal:
        return {
            "code": "qualify_to_company",
            "label": "Qualificar para empresa",
            "reason": f"Engajamento alto ({engagement_score}) sem empresa qualificada",
        }

    if days_since_interaction >= STALE_INTERACTION_DAYS:
        return {
            "code": "send_follow_up",
            "label": "Enviar follow-up",
            "reason": f"Última interação há {days_since_interaction} dias",
        }

    return {
        "code": "send_follow_up",
        "label": "Enviar follow-up",
        "reason": "Manter relacionamento ativo",
    }

