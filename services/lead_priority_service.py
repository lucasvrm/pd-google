from datetime import datetime, timezone
from typing import Optional, Dict, Any

from models import Lead, LeadActivityStats


# Default weights (kept for backward compatibility)
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

# Default thresholds (kept for backward compatibility)
PRIORITY_HOT_THRESHOLD = 70
PRIORITY_WARM_THRESHOLD = 40


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
    lead: Lead, stats: Optional[LeadActivityStats], now: Optional[datetime] = None,
    config: Optional[Dict[str, Any]] = None
) -> int:
    """
    Calculate a priority score (0-100) for a lead.
    
    Args:
        lead: Lead model instance
        stats: LeadActivityStats model instance
        now: Current datetime (for testing)
        config: Optional config dict with weights and thresholds from DB
    """
    # Use provided config or fall back to default weights
    if config is None:
        status_weights = STATUS_WEIGHT
        origin_weights = ORIGIN_WEIGHT
        recency_max = 30.0
        recency_decay = 0.5
        engagement_mult = 0.2
    else:
        weights = config.get("weights", {})
        status_weights = weights.get("status", STATUS_WEIGHT)
        origin_weights = weights.get("origin", ORIGIN_WEIGHT)
        recency_max = weights.get("recency_max", 30.0)
        recency_decay = weights.get("recency_decay_rate", 0.5)
        engagement_mult = weights.get("engagement_multiplier", 0.2)

    status_score = status_weights.get((lead.status or "").lower(), 12)
    origin_score = origin_weights.get((lead.origin or "").lower(), 10)

    days = _days_without_interaction(lead, stats, now)
    if days is None:
        recency_score = 0
    else:
        recency_score = max(0.0, recency_max - min(days, 60) * recency_decay)

    engagement_raw = stats.engagement_score if stats and stats.engagement_score else 0
    engagement_score = _clamp(engagement_raw, 0, 100) * engagement_mult

    total = status_score + origin_score + recency_score + engagement_score
    return int(round(_clamp(total, 0, 100)))


def classify_priority_bucket(score: int, config: Optional[Dict[str, Any]] = None) -> str:
    """
    Classify priority score into bucket (hot/warm/cold).
    
    Args:
        score: Priority score (0-100)
        config: Optional config dict with thresholds from DB
    """
    # Use provided config or fall back to default thresholds
    if config is None:
        hot_threshold = PRIORITY_HOT_THRESHOLD
        warm_threshold = PRIORITY_WARM_THRESHOLD
    else:
        thresholds = config.get("thresholds", {})
        hot_threshold = thresholds.get("hot", PRIORITY_HOT_THRESHOLD)
        warm_threshold = thresholds.get("warm", PRIORITY_WARM_THRESHOLD)
    
    if score >= hot_threshold:
        return "hot"
    if score >= warm_threshold:
        return "warm"
    return "cold"
