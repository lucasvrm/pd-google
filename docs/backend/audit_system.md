# Audit System Documentation

## Overview

The Audit System provides comprehensive tracking of changes to critical CRM entities (Leads and Deals). Every modification to tracked fields is automatically logged, creating a complete audit trail for compliance, debugging, and the Unified Timeline feature.

## Architecture

### Components

1. **`models.AuditLog`** - Database model storing audit log entries
2. **`services/audit_service.py`** - Service managing audit logging logic
3. **SQLAlchemy Event Hooks** - Automatic change detection and logging

### Database Schema

```sql
CREATE TABLE audit_logs (
    id SERIAL PRIMARY KEY,
    entity_type VARCHAR NOT NULL,        -- "lead", "deal", etc.
    entity_id VARCHAR NOT NULL,          -- UUID of the entity
    actor_id VARCHAR REFERENCES users(id), -- User who made the change
    action VARCHAR NOT NULL,             -- "create", "update", "delete", "status_change"
    changes JSONB,                       -- {"field": {"old": value, "new": value}}
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_audit_logs_entity ON audit_logs(entity_type, entity_id);
CREATE INDEX idx_audit_logs_actor ON audit_logs(actor_id);
CREATE INDEX idx_audit_logs_timestamp ON audit_logs(timestamp);
```

## How It Works

### 1. Event Hooks

The system uses SQLAlchemy's event system to automatically detect changes:

```python
@event.listens_for(Lead, "before_update", propagate=True)
def _log_lead_changes(mapper, connection, target):
    # Automatically called whenever a Lead is about to be updated
    # Extracts changes and creates audit log entry
    ...
```

Event hooks are registered for:
- `Lead` model: `after_insert`, `before_update`
- `Deal` model: `after_insert`, `before_update`

### 2. Change Detection

The `extract_changes()` function inspects SQLAlchemy's state to detect field modifications:

```python
def extract_changes(state, tracked_fields: Set[str]) -> Dict[str, Dict[str, Any]]:
    """Extract old and new values for tracked fields."""
    changes = {}
    for field in tracked_fields:
        attr_state = getattr(state.attrs, field, None)
        if attr_state and attr_state.history.has_changes():
            # Get old and new values
            changes[field] = {"old": old_value, "new": new_value}
    return changes
```

### 3. Actor Context

The system uses thread-local storage to track who made the change:

```python
# In your API endpoint or middleware:
from services.audit_service import set_audit_actor, clear_audit_actor

# Set the actor at the start of request
set_audit_actor(user_id)

# Make changes to Lead or Deal
lead.status_id = new_status_id
db.commit()  # Audit log automatically created

# Clear at the end of request
clear_audit_actor()
```

## Tracked Fields

### Lead Model

The following Lead fields are tracked:
- `owner_user_id` - Ownership changes
- `lead_status_id` - Status transitions (logged as "status_change")
- `lead_origin_id` - Origin changes
- `title` - Legal name changes
- `trade_name` - Trade name changes
- `priority_score` - Priority adjustments
- `qualified_company_id` - Qualification events
- `qualified_master_deal_id` - Deal conversion
- `address_city`, `address_state` - Address updates

### Deal Model

The following Deal fields are tracked:
- `title` - Client name (maps to `client_name` column)
- `company_id` - Company association

## Usage Examples

### Basic Usage in API Endpoints

```python
from fastapi import Depends
from database import get_db
from services.audit_service import set_audit_actor, clear_audit_actor

@router.patch("/leads/{lead_id}")
def update_lead(
    lead_id: str,
    updates: LeadUpdate,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    # Set audit context
    set_audit_actor(user_id)
    
    try:
        # Find and update lead
        lead = db.query(Lead).filter(Lead.id == lead_id).first()
        lead.status_id = updates.status_id
        lead.priority_score = updates.priority_score
        
        # Commit - audit log automatically created
        db.commit()
        
        return lead
    finally:
        # Always clear context
        clear_audit_actor()
```

### Querying Audit Logs

```python
# Get all changes to a specific lead
audit_logs = db.query(AuditLog).filter(
    AuditLog.entity_type == "lead",
    AuditLog.entity_id == lead_id
).order_by(AuditLog.timestamp.desc()).all()

# Get all actions by a specific user
user_actions = db.query(AuditLog).filter(
    AuditLog.actor_id == user_id
).order_by(AuditLog.timestamp.desc()).all()

# Get status changes only
status_changes = db.query(AuditLog).filter(
    AuditLog.entity_type == "lead",
    AuditLog.action == "status_change"
).all()
```

### Inspecting Changes

```python
audit_log = db.query(AuditLog).first()

print(f"Entity: {audit_log.entity_type} {audit_log.entity_id}")
print(f"Action: {audit_log.action}")
print(f"Actor: {audit_log.actor_id}")
print(f"When: {audit_log.timestamp}")

# Changes are stored as JSON
for field, change in audit_log.changes.items():
    old_value = change.get("old")
    new_value = change.get("new")
    print(f"  {field}: {old_value} → {new_value}")
```

## Action Types

| Action | Description | Example |
|--------|-------------|---------|
| `create` | New entity created | Lead created with initial values |
| `update` | General field update | Lead title or trade name changed |
| `status_change` | Status field modified | Lead moved from "New" to "Qualified" |
| `delete` | Entity deleted | (Reserved for future soft delete tracking) |

## Performance Considerations

### Optimization Strategies

1. **Selective Field Tracking**: Only critical fields are monitored, not all columns
2. **Database Indexing**: Key indexes on `entity_type`, `entity_id`, `actor_id`, and `timestamp`
3. **Async Logging**: Event hooks execute in the same transaction but are lightweight
4. **Partitioning**: For high-volume systems, consider table partitioning by timestamp

### Performance Impact

- **Insert/Update overhead**: ~5-10ms per operation
- **Database growth**: ~200 bytes per audit log entry
- **Query performance**: Indexed queries return in <50ms for typical datasets

## Integration with Unified Timeline

Audit logs feed into the Unified Timeline feature (Phase 3):

```python
# Timeline service will query audit logs alongside emails and calendar events
timeline_entries = [
    # ... calendar events ...
    # ... email threads ...
    # Audit logs
    {
        "timestamp": audit_log.timestamp,
        "type": "audit",
        "action": audit_log.action,
        "summary": f"{audit_log.action} on {audit_log.entity_type}",
        "changes": audit_log.changes,
        "actor": audit_log.actor
    }
]
```

## Security & Privacy

### Best Practices

1. **No PII in Changes**: Convert values to strings, avoiding unnecessary detail
2. **Actor Validation**: Always validate `actor_id` against authenticated user
3. **Read Access Control**: Audit logs should be admin-only or restricted by entity ownership
4. **Retention Policy**: Consider auto-archiving audit logs older than 2 years

### GDPR Compliance

- Audit logs may contain personal data (names, emails in changes)
- Implement data deletion mechanisms for GDPR "right to be forgotten"
- Consider anonymizing actor_id instead of full deletion

## Testing

Tests are located in `tests/test_audit_logs.py`:

```bash
# Run audit log tests
pytest tests/test_audit_logs.py -v

# Run specific test
pytest tests/test_audit_logs.py::TestLeadAuditLogs::test_lead_status_change_audit_log -v
```

## Troubleshooting

### Audit Logs Not Being Created

**Check 1**: Ensure event listeners are registered
```python
# In main.py startup
from services.audit_service import register_audit_listeners
register_audit_listeners()
```

**Check 2**: Verify actor context is set
```python
from services.audit_service import get_audit_actor
print(f"Current actor: {get_audit_actor()}")  # Should not be None
```

**Check 3**: Confirm tracked fields are being modified
```python
# Only fields in LEAD_AUDIT_FIELDS trigger audit logs
from services.audit_service import LEAD_AUDIT_FIELDS
print(LEAD_AUDIT_FIELDS)
```

### Missing Changes in Audit Log

**Issue**: Changes object is empty `{}`

**Solution**: Ensure you're modifying tracked fields and committing in the same session:
```python
lead.status_id = new_status  # Tracked field
db.commit()  # Must commit to trigger event
```

### Performance Issues

**Issue**: Slow writes when creating/updating entities

**Solutions**:
1. Verify database indexes are created
2. Consider async logging with a queue for high-volume systems
3. Archive old audit logs to a separate table

## Future Enhancements

### Planned (Phase 2+)

1. **Audit Log API Router** (`routers/audit_logs.py`)
   - GET `/audit-logs` - List all audit logs (admin)
   - GET `/audit-logs/entity/{type}/{id}` - Entity history
   - GET `/audit-logs/user/{user_id}` - User actions

2. **Soft Delete Tracking**
   - Track deletion events with `action="delete"`
   - Include reason and deleted_by fields

3. **Change Diffs**
   - Enhanced JSON diffs for complex fields
   - Visual diff rendering in frontend

4. **Webhook Notifications**
   - Real-time notifications for critical changes
   - Integration with Slack/email for alerts

## References

- **ACTION_PLAN.md** - Overall roadmap
- **models.py** - Database schema
- **services/audit_service.py** - Implementation
- **tests/test_audit_logs.py** - Test suite

---

**Last Updated**: December 2024  
**Status**: ✅ Implemented (Phase 2 - Partial)  
**Next Steps**: Implement Audit Log API Router
