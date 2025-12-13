"""
Audit Service - Tracks changes to critical CRM entities.

This service provides:
1. SQLAlchemy event hooks for automatic audit logging
2. Helper functions to extract field changes
3. Context management for tracking the actor (user) making changes

Critical fields tracked for Leads:
- owner_user_id (ownership changes)
- lead_status_id (status transitions)
- lead_origin_id (origin changes)
- title (legal name changes)
- trade_name
- priority_score
- qualified_company_id (qualification)
- qualified_master_deal_id (deal conversion)
- address_city, address_state

Critical fields tracked for Deals:
- title (client name)
- company_id (company association)
"""

from datetime import datetime, timezone
from typing import Optional, Dict, Any, Set
from sqlalchemy import event, inspect
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import get_history

# Thread-local storage for tracking the current actor
import threading
_audit_context = threading.local()


def set_audit_actor(user_id: Optional[str]) -> None:
    """
    Set the current user ID for audit logging context.
    Should be called at the start of request processing.
    
    Args:
        user_id: UUID of the user making the change, or None if system-initiated
    """
    _audit_context.actor_id = user_id


def get_audit_actor() -> Optional[str]:
    """
    Get the current user ID from audit logging context.
    
    Returns:
        User ID if set, None otherwise
    """
    return getattr(_audit_context, 'actor_id', None)


def clear_audit_actor() -> None:
    """Clear the audit actor context."""
    if hasattr(_audit_context, 'actor_id'):
        delattr(_audit_context, 'actor_id')


# Fields to track for each entity type
LEAD_AUDIT_FIELDS: Set[str] = {
    "owner_user_id",
    "lead_status_id",
    "lead_origin_id",
    "title",
    "trade_name",
    "priority_score",
    "qualified_company_id",
    "qualified_master_deal_id",
    "address_city",
    "address_state",
}

DEAL_AUDIT_FIELDS: Set[str] = {
    "title",  # Attribute name (maps to 'client_name' database column in Deal model)
    "company_id",
}


def extract_changes(target, tracked_fields: Set[str]) -> Dict[str, Dict[str, Any]]:
    """
    Extract field changes from SQLAlchemy object.
    
    Args:
        target: SQLAlchemy model instance
        tracked_fields: Set of field names to track
        
    Returns:
        Dictionary mapping field names to {old: value, new: value}
    
    Note:
        This function works best when expire_on_commit=False is set on the session,
        otherwise old values may not be available after commits.
    """
    changes = {}
    
    for field in tracked_fields:
        # Use get_history to properly capture old and new values
        history = get_history(target, field)
        
        if history and history.has_changes():
            # For before_update events:
            # - deleted contains the old value being replaced
            # - added contains the new value being set
            
            # Get old value (what's being deleted/replaced)
            old_value = None
            if history.deleted:
                old_value = history.deleted[0]
            
            # Get new value (what's being added)
            new_value = None
            if history.added:
                new_value = history.added[0]
            
            # Only record if there's an actual change
            if old_value != new_value:
                # Preserve data types for primitives, convert complex objects to strings
                def serialize_value(val):
                    if val is None or isinstance(val, (str, int, float, bool)):
                        return val
                    return str(val)
                
                changes[field] = {
                    "old": serialize_value(old_value),
                    "new": serialize_value(new_value),
                }
    
    return changes


def create_audit_log(
    session: Session,
    entity_type: str,
    entity_id: str,
    action: str,
    changes: Optional[Dict[str, Dict[str, Any]]] = None,
    actor_id: Optional[str] = None
) -> None:
    """
    Create an audit log entry.
    
    Args:
        session: SQLAlchemy session to use for insertion
        entity_type: Type of entity (e.g., "lead", "deal")
        entity_id: UUID of the entity
        action: Action performed (e.g., "create", "update", "delete")
        changes: Dictionary of field changes
        actor_id: User ID who performed the action (defaults to context actor)
    """
    from models import AuditLog
    
    if actor_id is None:
        actor_id = get_audit_actor()
    
    audit_log = AuditLog(
        entity_type=entity_type,
        entity_id=entity_id,
        actor_id=actor_id,
        action=action,
        changes=changes or {},
        timestamp=datetime.now(timezone.utc)
    )
    
    session.add(audit_log)
    # Note: Session commit is handled by the caller


# ===== SQLAlchemy Event Hooks =====

def _log_lead_changes(mapper, connection, target):
    """
    Event hook for Lead updates. Automatically logs changes to tracked fields.
    Uses before_update to capture old values before they're changed.
    """
    from models import AuditLog
    
    changes = extract_changes(target, LEAD_AUDIT_FIELDS)
    
    # Only create audit log if there are actual changes to tracked fields
    if not changes:
        return
    
    # Determine action based on changes
    action = "update"
    if "lead_status_id" in changes:
        action = "status_change"
    
    # Insert directly via connection to avoid flush cycle issues.
    # Using session.add() during a before_update event can cause
    # "Usage of the 'Session.add()' operation is not currently supported
    # within the execution stage of the flush process" warnings.
    # Direct connection execution ensures the audit log is created
    # in the same transaction without interfering with the flush.
    timestamp = datetime.now(timezone.utc)
    actor_id = get_audit_actor()
    
    connection.execute(
        AuditLog.__table__.insert().values(
            entity_type="lead",
            entity_id=str(target.id),
            actor_id=actor_id,
            action=action,
            changes=changes,
            timestamp=timestamp
        )
    )


def _log_lead_insert(mapper, connection, target):
    """
    Event hook for Lead creation. Logs the creation event.
    Uses after_insert since we need the ID to be generated.
    """
    from models import AuditLog
    
    # For inserts, we log all tracked fields as "new" values
    changes = {}
    for field in LEAD_AUDIT_FIELDS:
        value = getattr(target, field, None)
        if value is not None:
            changes[field] = {
                "old": None,
                "new": str(value)
            }
    
    # Insert directly via connection
    timestamp = datetime.now(timezone.utc)
    actor_id = get_audit_actor()
    
    connection.execute(
        AuditLog.__table__.insert().values(
            entity_type="lead",
            entity_id=str(target.id),
            actor_id=actor_id,
            action="create",
            changes=changes,
            timestamp=timestamp
        )
    )


def _log_deal_changes(mapper, connection, target):
    """
    Event hook for Deal updates. Automatically logs changes to tracked fields.
    Uses before_update to capture old values before they're changed.
    """
    from models import AuditLog
    
    changes = extract_changes(target, DEAL_AUDIT_FIELDS)
    
    # Only create audit log if there are actual changes to tracked fields
    if not changes:
        return
    
    # Insert directly via connection
    timestamp = datetime.now(timezone.utc)
    actor_id = get_audit_actor()
    
    connection.execute(
        AuditLog.__table__.insert().values(
            entity_type="deal",
            entity_id=str(target.id),
            actor_id=actor_id,
            action="update",
            changes=changes,
            timestamp=timestamp
        )
    )


def _log_deal_insert(mapper, connection, target):
    """
    Event hook for Deal creation. Logs the creation event.
    Uses after_insert since we need the ID to be generated.
    """
    from models import AuditLog
    
    # For inserts, we log all tracked fields as "new" values
    changes = {}
    for field in DEAL_AUDIT_FIELDS:
        value = getattr(target, field, None)
        if value is not None:
            changes[field] = {
                "old": None,
                "new": str(value)
            }
    
    # Insert directly via connection
    timestamp = datetime.now(timezone.utc)
    actor_id = get_audit_actor()
    
    connection.execute(
        AuditLog.__table__.insert().values(
            entity_type="deal",
            entity_id=str(target.id),
            actor_id=actor_id,
            action="create",
            changes=changes,
            timestamp=timestamp
        )
    )


def register_audit_listeners() -> None:
    """
    Register all audit log event listeners.
    Should be called once at application startup.
    
    Note: Uses insert=True to ensure audit listeners run before other listeners,
    preserving access to the original field values.
    """
    from models import Lead, Deal
    
    # Register Lead listeners with insert=True to run first
    # Use before_update to capture old values before they change
    event.listen(Lead, "before_update", _log_lead_changes, propagate=True, insert=True)
    # Use after_insert since we need the ID to be generated
    event.listen(Lead, "after_insert", _log_lead_insert, propagate=True)
    
    # Register Deal listeners
    event.listen(Deal, "before_update", _log_deal_changes, propagate=True, insert=True)
    event.listen(Deal, "after_insert", _log_deal_insert, propagate=True)
