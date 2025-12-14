from __future__ import annotations

"""
Next Action Service - Sprint 2/3

Suggests the best next action for a lead based on engagement, timing, and state.

PRECEDENCE RULES (lower = higher priority):
  1. prepare_for_meeting     - Future meeting scheduled (last_event_at > now)
  2. post_meeting_follow_up  - Recent past meeting without subsequent interaction
  3. call_first_time         - No interaction at all (new lead)
  4. handoff_to_deal         - Qualified company exists but no master deal linked
  5. qualify_to_company      - High engagement (>=70) without qualified company
  6. schedule_meeting        - Engaged lead without upcoming meeting
  7. call_again              - Recent call that needs follow-up (within call window)
  8. send_value_asset        - Engaged lead that hasn't received recent value content
  9. send_follow_up          - Stale interaction (>= STALE_INTERACTION_DAYS)
 10. reengage_cold_lead      - Very cold lead (long without interaction, moderate engagement)
 11. disqualify              - Very long without interaction, low engagement, no company/deal

Labels (PT-BR):
  - prepare_for_meeting     -> "Preparar para reunião"
  - post_meeting_follow_up  -> "Follow-up pós-reunião"
  - call_first_time         -> "Fazer primeira ligação"
  - handoff_to_deal         -> "Fazer handoff (para deal)"
  - qualify_to_company      -> "Qualificar para empresa"
  - schedule_meeting        -> "Agendar reunião"
  - call_again              -> "Ligar novamente"
  - send_value_asset        -> "Enviar material / valor"
  - send_follow_up          -> "Enviar follow-up"
  - reengage_cold_lead      -> "Reengajar lead frio"
  - disqualify              -> "Desqualificar / encerrar"
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional


# Configuration thresholds
STALE_INTERACTION_DAYS = 5
HIGH_ENGAGEMENT_SCORE = 70
MEDIUM_ENGAGEMENT_SCORE = 40
NEW_LEAD_MAX_AGE_DAYS = 14
# For schedule_meeting: if engaged but no meeting in next N days
SCHEDULE_MEETING_ENGAGEMENT_THRESHOLD = 50
# For call_again: last call within N days
CALL_AGAIN_WINDOW_DAYS = 7
# For send_value_asset: last value asset older than N days
VALUE_ASSET_STALE_DAYS = 14
# For post_meeting_follow_up: meeting happened within last N days
POST_MEETING_WINDOW_DAYS = 3
# For reengage_cold_lead: no interaction for N days
COLD_LEAD_DAYS = 30
# For disqualify: no interaction for N days + low engagement
DISQUALIFY_DAYS = 60


def _normalize_datetime(value: Any) -> Optional[datetime]:
    """Normalize datetime values to timezone-aware UTC datetime objects."""
    if value is None:
        return None

    if isinstance(value, str):
        try:
            # Try parsing ISO format
            value = datetime.fromisoformat(value)
        except ValueError:
            return None

    if not isinstance(value, datetime):
        return None

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def suggest_next_action(lead: Any, stats: Any, now: Optional[datetime] = None) -> Dict[str, str]:
    """
    Suggest the next action for a lead based on recency and engagement.

    Args:
        lead: Lead model instance with fields like qualified_company_id, qualified_master_deal_id, created_at
        stats: LeadActivityStats instance with fields like last_event_at, last_interaction_at, engagement_score
        now: Optional datetime for testing; defaults to current UTC time

    Returns:
        Dict with keys: code, label, reason
    """

    current_time = _normalize_datetime(now or datetime.now(timezone.utc)) or datetime.now(
        timezone.utc
    )

    created_at = _normalize_datetime(getattr(lead, "created_at", None)) or current_time
    # Ensure created_at is not in the future relative to current_time to avoid negative days
    lead_age_days = max((current_time - created_at).days, 0)

    # Extract stats fields with safe fallbacks
    last_event_at = _normalize_datetime(getattr(stats, "last_event_at", None)) if stats else None
    next_scheduled_event_at = _normalize_datetime(getattr(stats, "next_scheduled_event_at", None)) if stats else None
    engagement_score = getattr(stats, "engagement_score", 0) if stats else 0

    # Try to get last_interaction_at from stats first, then from lead
    last_interaction = getattr(stats, "last_interaction_at", None) if stats else None
    if last_interaction is None:
        last_interaction = getattr(lead, "last_interaction_at", None)
    last_interaction = _normalize_datetime(last_interaction)

    # Optional fields that may exist after Sprint 1 migrations
    last_call_at = _normalize_datetime(getattr(stats, "last_call_at", None)) if stats else None
    last_value_asset_at = _normalize_datetime(getattr(stats, "last_value_asset_at", None)) if stats else None

    # Lead qualification state
    has_qualified_company = getattr(lead, "qualified_company_id", None) is not None
    has_qualified_master_deal = getattr(lead, "qualified_master_deal_id", None) is not None
    is_disqualified = getattr(lead, "disqualified_at", None) is not None

    # Calculate days since last interaction
    days_since_interaction = max((current_time - last_interaction).days, 0) if last_interaction else None

    # ----- PRECEDENCE 1: prepare_for_meeting (future event scheduled) -----
    # Check both last_event_at (legacy) and next_scheduled_event_at (new)
    future_event = None
    if next_scheduled_event_at and next_scheduled_event_at > current_time:
        future_event = next_scheduled_event_at
    elif last_event_at and last_event_at > current_time:
        future_event = last_event_at

    if future_event:
        return {
            "code": "prepare_for_meeting",
            "label": "Preparar para reunião",
            "reason": f"Reunião futura agendada para {future_event.date()}",
        }

    # ----- PRECEDENCE 2: post_meeting_follow_up (recent past meeting, no interaction after) -----
    if last_event_at and last_event_at <= current_time:
        days_since_meeting = (current_time - last_event_at).days
        # Meeting happened within POST_MEETING_WINDOW_DAYS
        if days_since_meeting <= POST_MEETING_WINDOW_DAYS:
            # No interaction after the meeting (or interaction was before meeting)
            if last_interaction is None or last_interaction <= last_event_at:
                return {
                    "code": "post_meeting_follow_up",
                    "label": "Follow-up pós-reunião",
                    "reason": f"Reunião ocorrida há {days_since_meeting} dia(s), sem interação posterior",
                }

    # ----- PRECEDENCE 3: call_first_time (no interaction at all) -----
    if last_interaction is None:
        reason = "Lead novo sem interação" if lead_age_days <= NEW_LEAD_MAX_AGE_DAYS else "Nenhuma interação registrada"
        return {"code": "call_first_time", "label": "Fazer primeira ligação", "reason": reason}

    # ----- PRECEDENCE 4: handoff_to_deal (qualified_company_id != null, qualified_master_deal_id == null) -----
    if has_qualified_company and not has_qualified_master_deal and not is_disqualified:
        return {
            "code": "handoff_to_deal",
            "label": "Fazer handoff (para deal)",
            "reason": "Empresa qualificada sem deal vinculado",
        }

    # ----- PRECEDENCE 5: qualify_to_company (high engagement, no qualified company) -----
    if engagement_score >= HIGH_ENGAGEMENT_SCORE and not has_qualified_company:
        return {
            "code": "qualify_to_company",
            "label": "Qualificar para empresa",
            "reason": f"Engajamento alto ({engagement_score}) sem empresa qualificada",
        }

    # ----- PRECEDENCE 6: schedule_meeting (engaged lead without upcoming meeting) -----
    if engagement_score >= SCHEDULE_MEETING_ENGAGEMENT_THRESHOLD:
        has_upcoming_meeting = (
            (next_scheduled_event_at and next_scheduled_event_at > current_time) or
            (last_event_at and last_event_at > current_time)
        )
        if not has_upcoming_meeting:
            return {
                "code": "schedule_meeting",
                "label": "Agendar reunião",
                "reason": f"Engajamento médio-alto ({engagement_score}) sem reunião agendada",
            }

    # ----- PRECEDENCE 7: call_again (if last_call_at exists and within window) -----
    if last_call_at:
        days_since_call = (current_time - last_call_at).days
        if days_since_call <= CALL_AGAIN_WINDOW_DAYS:
            return {
                "code": "call_again",
                "label": "Ligar novamente",
                "reason": f"Última ligação há {days_since_call} dia(s)",
            }

    # ----- PRECEDENCE 8: send_value_asset (if last_value_asset_at old/missing and lead engaged) -----
    if engagement_score >= MEDIUM_ENGAGEMENT_SCORE:
        if last_value_asset_at is None:
            return {
                "code": "send_value_asset",
                "label": "Enviar material / valor",
                "reason": "Lead engajado sem material de valor enviado",
            }
        days_since_value_asset = (current_time - last_value_asset_at).days
        if days_since_value_asset >= VALUE_ASSET_STALE_DAYS:
            return {
                "code": "send_value_asset",
                "label": "Enviar material / valor",
                "reason": f"Último material enviado há {days_since_value_asset} dias",
            }

    # ----- PRECEDENCE 9: send_follow_up (stale interaction >= STALE_INTERACTION_DAYS) -----
    if days_since_interaction is not None and days_since_interaction >= STALE_INTERACTION_DAYS:
        # Check if should escalate to reengage or disqualify
        if days_since_interaction >= DISQUALIFY_DAYS:
            # ----- PRECEDENCE 11: disqualify (very long without interaction, low engagement) -----
            # Only suggest disqualify if no company/deal and low engagement
            if not has_qualified_company and not has_qualified_master_deal and not is_disqualified:
                if engagement_score < MEDIUM_ENGAGEMENT_SCORE:
                    return {
                        "code": "disqualify",
                        "label": "Desqualificar / encerrar",
                        "reason": f"Sem interação há {days_since_interaction} dias, engajamento baixo ({engagement_score})",
                    }
        elif days_since_interaction >= COLD_LEAD_DAYS:
            # ----- PRECEDENCE 10: reengage_cold_lead (cold but not disqualifiable) -----
            return {
                "code": "reengage_cold_lead",
                "label": "Reengajar lead frio",
                "reason": f"Sem interação há {days_since_interaction} dias",
            }

        # Standard stale follow-up
        return {
            "code": "send_follow_up",
            "label": "Enviar follow-up",
            "reason": f"Última interação há {days_since_interaction} dias",
        }

    # ----- DEFAULT: send_follow_up (keep relationship active) -----
    return {
        "code": "send_follow_up",
        "label": "Enviar follow-up",
        "reason": "Manter relacionamento ativo",
    }
