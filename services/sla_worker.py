"""
SLA Worker Service

Monitors leads for SLA breaches based on last interaction time.
When a lead hasn't been interacted with for longer than the threshold,
it's tagged as "SLA Breach" and an audit log is created.
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

import models
from services.audit_service import set_audit_actor, clear_audit_actor


# Default SLA threshold in days
DEFAULT_SLA_THRESHOLD_DAYS = 7


def _ensure_timezone_aware(dt: Optional[datetime]) -> Optional[datetime]:
    """
    Ensure a datetime is timezone-aware.
    
    Args:
        dt: Datetime that may or may not have timezone info
        
    Returns:
        Timezone-aware datetime or None if input is None
    """
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _calculate_days_since(reference_dt: datetime, target_dt: Optional[datetime]) -> int:
    """
    Calculate days between reference datetime and target datetime.
    Handles timezone-aware and timezone-naive datetimes.
    
    Args:
        reference_dt: Reference datetime (typically now)
        target_dt: Target datetime to calculate difference from
        
    Returns:
        Number of days between the two datetimes
    """
    if target_dt is None:
        return 0
    
    aware_target = _ensure_timezone_aware(target_dt)
    aware_reference = _ensure_timezone_aware(reference_dt)
    
    return (aware_reference - aware_target).days


def check_sla_breaches(
    db: Session,
    threshold_days: int = DEFAULT_SLA_THRESHOLD_DAYS,
    actor_id: str = None
) -> Dict[str, Any]:
    """
    Check for leads that have breached SLA (not interacted with for too long).
    
    Args:
        db: Database session
        threshold_days: Number of days without interaction to trigger SLA breach
        actor_id: Optional user ID to set as actor for audit logs (defaults to system)
    
    Returns:
        Dictionary with results:
        - breached_leads: List of lead IDs that breached SLA
        - tagged_count: Number of leads tagged
        - audit_logs_created: Number of audit logs created
        - threshold_used: The threshold value used
    """
    # Calculate threshold datetime
    threshold_datetime = datetime.now(timezone.utc) - timedelta(days=threshold_days)
    
    # Set audit actor (use system if not provided)
    if actor_id:
        set_audit_actor(actor_id)
    else:
        set_audit_actor("system-sla-worker")
    
    # Query leads that haven't been interacted with beyond threshold
    # Include leads with no last_interaction_at (never interacted)
    forgotten_leads = db.query(models.Lead).filter(
        models.Lead.last_interaction_at <= threshold_datetime
    ).all()
    
    # Also get leads with no interaction at all (NULL last_interaction_at)
    # and older than threshold since creation
    never_interacted = db.query(models.Lead).filter(
        models.Lead.last_interaction_at.is_(None),
        models.Lead.created_at <= threshold_datetime
    ).all()
    
    # Combine both lists
    all_forgotten_leads = forgotten_leads + never_interacted
    
    # Get or create "SLA Breach" tag
    sla_tag = db.query(models.Tag).filter(
        models.Tag.name == "SLA Breach"
    ).first()
    
    if not sla_tag:
        sla_tag = models.Tag(
            id=str(uuid.uuid4()),
            name="SLA Breach",
            color="#FF0000"  # Red color for breach
        )
        db.add(sla_tag)
        db.commit()
    
    breached_lead_ids = []
    tagged_count = 0
    audit_logs_created = 0
    
    for lead in all_forgotten_leads:
        # Check if lead already has the SLA Breach tag
        has_tag = any(tag.id == sla_tag.id for tag in lead.tags)
        
        if not has_tag:
            # Add tag to lead
            lead.tags.append(sla_tag)
            tagged_count += 1
            
            # Create audit log for SLA breach
            audit_log = models.AuditLog(
                entity_type="lead",
                entity_id=lead.id,
                actor_id=actor_id or "system-sla-worker",
                action="sla_breach",
                changes={
                    "sla_status": {
                        "old": "ok",
                        "new": "breached"
                    },
                    "threshold_days": threshold_days,
                    "last_interaction_at": lead.last_interaction_at.isoformat() if lead.last_interaction_at else None,
                    "days_since_interaction": _calculate_days_since(
                        datetime.now(timezone.utc),
                        lead.last_interaction_at or lead.created_at
                    )
                },
                timestamp=datetime.now(timezone.utc)
            )
            db.add(audit_log)
            audit_logs_created += 1
        
        breached_lead_ids.append(lead.id)
    
    # Commit all changes
    db.commit()
    
    # Clear audit actor
    clear_audit_actor()
    
    return {
        "breached_leads": breached_lead_ids,
        "tagged_count": tagged_count,
        "audit_logs_created": audit_logs_created,
        "threshold_used": threshold_days,
        "total_checked": len(all_forgotten_leads)
    }


def get_sla_breach_stats(db: Session) -> Dict[str, Any]:
    """
    Get statistics about SLA breaches.
    
    Args:
        db: Database session
    
    Returns:
        Dictionary with statistics:
        - total_breached: Total number of leads with SLA Breach tag
        - recent_breaches: Number of breaches in last 24 hours
    """
    # Get SLA Breach tag
    sla_tag = db.query(models.Tag).filter(
        models.Tag.name == "SLA Breach"
    ).first()
    
    if not sla_tag:
        return {
            "total_breached": 0,
            "recent_breaches": 0
        }
    
    # Count leads with SLA Breach tag
    total_breached = db.query(models.Lead).join(
        models.LeadTag,
        models.Lead.id == models.LeadTag.lead_id
    ).filter(
        models.LeadTag.tag_id == sla_tag.id
    ).count()
    
    # Count recent breaches (audit logs created in last 24 hours)
    recent_threshold = datetime.now(timezone.utc) - timedelta(hours=24)
    recent_breaches = db.query(models.AuditLog).filter(
        models.AuditLog.action == "sla_breach",
        models.AuditLog.timestamp >= recent_threshold
    ).count()
    
    return {
        "total_breached": total_breached,
        "recent_breaches": recent_breaches
    }


def clear_sla_breach_tag(db: Session, lead_id: str, actor_id: str = None) -> bool:
    """
    Clear the SLA Breach tag from a lead (e.g., after interaction).
    
    Args:
        db: Database session
        lead_id: ID of the lead to clear tag from
        actor_id: Optional user ID for audit log
    
    Returns:
        True if tag was removed, False if lead didn't have the tag
    """
    # Get lead
    lead = db.query(models.Lead).filter(models.Lead.id == lead_id).first()
    if not lead:
        return False
    
    # Get SLA Breach tag
    sla_tag = db.query(models.Tag).filter(
        models.Tag.name == "SLA Breach"
    ).first()
    
    if not sla_tag:
        return False
    
    # Check if lead has the tag
    has_tag = any(tag.id == sla_tag.id for tag in lead.tags)
    
    if has_tag:
        # Remove tag
        lead.tags = [tag for tag in lead.tags if tag.id != sla_tag.id]
        
        # Create audit log
        if actor_id:
            set_audit_actor(actor_id)
        
        audit_log = models.AuditLog(
            entity_type="lead",
            entity_id=lead_id,
            actor_id=actor_id or "system-sla-worker",
            action="sla_breach_resolved",
            changes={
                "sla_status": {
                    "old": "breached",
                    "new": "ok"
                }
            },
            timestamp=datetime.now(timezone.utc)
        )
        db.add(audit_log)
        
        db.commit()
        clear_audit_actor()
        
        return True
    
    return False
