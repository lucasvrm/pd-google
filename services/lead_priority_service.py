from datetime import datetime, timezone
from typing import Dict, Any, Optional

from models import Lead

# Default thresholds (kept for backward compatibility)
PRIORITY_HOT_THRESHOLD = 70
PRIORITY_WARM_THRESHOLD = 40


def _clamp(value: float, minimum: float = 0, maximum: float = 100) -> float:
    return max(minimum, min(maximum, value))


def calculate_lead_priority(
    lead: Lead, now: Optional[datetime] = None, config: Optional[Dict[str, Any]] = None
) -> int:
    """
    Calculate a priority score (0-100) for a lead.
    
    Args:
        lead: Lead object with relationships to lead_status, lead_origin, activity_stats
        now: Current datetime for recency calculation (defaults to UTC now)
        config: Priority configuration dict with 'scoring' section. If None, caller should provide it.
    
    Returns:
        Integer priority score between minScore and maxScore (default 0-100)
    """
    if config is None:
        # Function is pure - config must be provided by caller
        raise ValueError("config parameter is required")
    
    scoring = config.get("scoring", {})
    recency_max_points = scoring.get("recencyMaxPoints", 40)
    stale_days = scoring.get("staleDays", 30)
    upcoming_meeting_points = scoring.get("upcomingMeetingPoints", 25)
    min_score = scoring.get("minScore", 0)
    max_score = scoring.get("maxScore", 100)
    
    # Status points from relationship
    status_points = 0
    if lead.lead_status and hasattr(lead.lead_status, "priority_weight"):
        status_points = lead.lead_status.priority_weight or 0
    
    # Origin points from relationship
    origin_points = 0
    if lead.lead_origin and hasattr(lead.lead_origin, "priority_weight"):
        origin_points = lead.lead_origin.priority_weight or 0
    
    # Recency points based on last interaction
    recency_points = 0
    reference = None
    stats = lead.activity_stats
    if stats and stats.last_interaction_at:
        reference = stats.last_interaction_at
    elif getattr(lead, "last_interaction_at", None):
        reference = lead.last_interaction_at
    elif lead.updated_at:
        reference = lead.updated_at
    else:
        reference = lead.created_at
    
    if reference is not None:
        if reference.tzinfo is None:
            reference = reference.replace(tzinfo=timezone.utc)
        
        now = now or datetime.now(timezone.utc)
        days = max(0, (now - reference).days)
        
        # Calculate decay factor: 1.0 at 0 days, 0.0 at stale_days or more
        if stale_days > 0:
            factor = max(0.0, 1.0 - days / stale_days)
            recency_points = round(factor * recency_max_points)
        else:
            recency_points = 0
    
    # Meeting points if there's an upcoming meeting
    meeting_points = 0
    if stats and getattr(stats, "next_scheduled_event_at", None):
        # Check if meeting is in the future
        now = now or datetime.now(timezone.utc)
        next_event = stats.next_scheduled_event_at
        if next_event.tzinfo is None:
            next_event = next_event.replace(tzinfo=timezone.utc)
        if next_event > now:
            meeting_points = upcoming_meeting_points
    
    # Total score
    score = status_points + origin_points + recency_points + meeting_points
    
    # Clamp to configured range
    return int(round(_clamp(score, min_score, max_score)))


def classify_priority_bucket(score: int, config: Dict[str, Any]) -> str:
    """
    Classify priority score into a bucket (hot/warm/cold).
    
    Args:
        score: Priority score
        config: Priority configuration dict with 'thresholds' section
    
    Returns:
        Bucket name: "hot", "warm", or "cold"
    """
    thresholds = config.get("thresholds", {})
    hot_threshold = thresholds.get("hot", 70)
    warm_threshold = thresholds.get("warm", 40)
    
    if score >= hot_threshold:
        return "hot"
    if score >= warm_threshold:
        return "warm"
    return "cold"
