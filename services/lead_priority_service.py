from datetime import datetime, timezone
from typing import Optional

from models import Lead, LeadActivityStats


STATUS_WEIGHT = {
    "new": 18,
    "contacted": 22,
    "qualified": 26,
    "proposal": 28,
    "won": 30,
    "lost": 5,
}

ORIGIN_WEIGHT = {
    "inbound": 20,
    "referral": 18,
    "partner": 16,
    "event": 15,
    "outbound": 12,
}


def _clamp(value: float, minimum: float = 0, maximum: float = 100) -> float:
    return max(minimum, min(maximum, value))


def _days_without_interaction(
    lead: Lead, stats: Optional[LeadActivityStats], now: Optional[datetime]
) -> Optional[int]:
    reference = None
    if stats and stats.last_interaction_at:
        reference = stats.last_interaction_at
    elif getattr(lead, "last_interaction_at", None):
        reference = lead.last_interaction_at  # type: ignore[attr-defined]
    elif lead.updated_at:
        reference = lead.updated_at
    else:
        reference = lead.created_at

    if reference is None:
        return None

    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)

    now = now or datetime.now(timezone.utc)
    delta = now - reference
    return max(0, delta.days)


def calculate_lead_priority(
    lead: Lead, stats: Optional[LeadActivityStats], now: Optional[datetime] = None
) -> int:
    """Calculate a priority score (0-100) for a lead."""

    status_score = STATUS_WEIGHT.get((lead.status or "").lower(), 12)
    origin_score = ORIGIN_WEIGHT.get((lead.origin or "").lower(), 10)

    days = _days_without_interaction(lead, stats, now)
    if days is None:
        recency_score = 0
    else:
        recency_score = max(0.0, 30.0 - min(days, 60) * 0.5)

    engagement_raw = stats.engagement_score if stats and stats.engagement_score else 0
    engagement_score = _clamp(engagement_raw, 0, 100) * 0.2

    total = status_score + origin_score + recency_score + engagement_score
    return int(round(_clamp(total, 0, 100)))


def classify_priority_bucket(score: int) -> str:
    if score >= 70:
        return "hot"
    if score >= 40:
        return "warm"
    return "cold"
