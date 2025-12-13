# Calendar Two-Way Sync Documentation

## Overview

This document describes the two-way synchronization system for Google Calendar events. The system uses Google's Push Notifications (webhooks) combined with sync tokens to keep the local `CalendarEvent` table in sync with Google Calendar in near real-time.

## Architecture

### Components

1. **Webhook Endpoint** (`/webhooks/google-drive`)
   - Unified endpoint receiving notifications from both Google Drive and Google Calendar
   - Routes calendar notifications to `handle_calendar_webhook()`
   - Validates webhook tokens for security

2. **Sync Handler** (`sync_calendar_events()`)
   - Core synchronization logic using Google's sync tokens
   - Handles incremental syncs and full re-syncs
   - Updates local database with changes from Google Calendar

3. **Database Models**
   - `CalendarSyncState`: Stores sync tokens and channel information
   - `CalendarEvent`: Local mirror of Google Calendar events

## Sync Token Flow

### What are Sync Tokens?

Sync tokens are opaque strings provided by Google Calendar API that represent a specific state of a calendar. They allow efficient incremental synchronization by fetching only changes since the last sync, rather than retrieving all events every time.

### Incremental Sync Process

1. **Initial Sync**
   - First time syncing a calendar (no sync token)
   - Fetch all future events using `timeMin` parameter
   - Google returns events + a `nextSyncToken`
   - Store the sync token in `CalendarSyncState.sync_token`

2. **Incremental Sync (Delta Updates)**
   - Use stored `sync_token` in API call
   - Google returns only changes since last sync:
     - New events
     - Modified events  
     - Cancelled events (status='cancelled')
   - Store the new `nextSyncToken` for next sync

3. **Event Processing**
   - For each event in the response:
     - **If `status == 'cancelled'`**: Mark local event as cancelled
     - **Otherwise**: Upsert (create or update) local event with:
       - summary, description
       - start_time, end_time
       - meet_link, html_link
       - organizer_email, attendees
       - status (confirmed, tentative, cancelled)

### Pagination

Google Calendar API returns results in pages. The sync logic handles pagination automatically:

```python
while True:
    result = fetch_events_page(
        calendar_id=channel.calendar_id,
        sync_token=channel.sync_token,
        page_token=page_token
    )
    
    # Process items...
    
    page_token = result.get('nextPageToken')
    new_sync_token = result.get('nextSyncToken')
    
    if not page_token:
        break  # All pages processed
```

- `nextPageToken`: Continue fetching more results
- `nextSyncToken`: Final token after all pages (only present on last page)

## Error Handling

### 410 Gone - Invalid Sync Token

The most critical error to handle is HTTP 410 (Gone), indicating the sync token is no longer valid. This can happen when:

- Token has expired (tokens expire after a period of inactivity)
- Calendar has been heavily modified
- Google's internal state has changed

#### Recovery Strategy

When a 410 error occurs:

1. **Detect the Error**
   ```python
   except Exception as e:
       error_msg = str(e)
       if '410' in error_msg or 'sync token is no longer valid' in error_msg.lower():
           # Handle invalid token
   ```

2. **Clear the Sync Token**
   ```python
   channel.sync_token = None
   page_token = None  # Reset pagination
   db.commit()
   ```

3. **Perform Full Re-Sync**
   - Fetch all events from current time onwards: `timeMin=datetime.now(timezone.utc).isoformat()`
   - Process all returned events
   - Store new sync token from Google

4. **Log the Event**
   ```python
   calendar_logger.warning(
       action="sync",
       status="warning",
       message="Sync token invalid (410). Performing full re-sync.",
       error_type="SyncTokenExpired"
   )
   ```

### Other Errors

- **403 Forbidden**: Authentication/authorization issues - check service account permissions
- **404 Not Found**: Calendar doesn't exist - deactivate channel
- **429 Rate Limit**: Handled by `exponential_backoff_retry` decorator
- **500/503 Server Errors**: Transient errors, retry with exponential backoff

## Webhook Registration

### Setting Up a Calendar Watch

To receive push notifications, register a webhook channel:

```python
from services.google_calendar_service import GoogleCalendarService

service = GoogleCalendarService(db)
result = service.watch_events(
    channel_id="unique-uuid",
    webhook_url="https://your-domain.com/webhooks/google-drive",
    calendar_id="primary",
    token="your-webhook-secret",
    expiration=None  # Optional: milliseconds timestamp
)
```

### Webhook Channel Lifecycle

1. **Registration**
   - Create `CalendarSyncState` record with `channel_id` and `resource_id`
   - Store initial sync token (if available)
   - Set `active=True` and `expiration` timestamp

2. **Receiving Notifications**
   - Google sends POST to webhook URL with headers:
     - `X-Goog-Channel-ID`: Your channel identifier
     - `X-Goog-Resource-ID`: Google's resource identifier
     - `X-Goog-Resource-State`: Notification type ('sync', 'exists', 'not_exists')
     - `X-Goog-Channel-Token`: Your validation token

3. **Channel Expiration**
   - Channels expire after ~1 week by default
   - Implement scheduled renewal before expiration
   - See `services/scheduler_service.py` for renewal logic

## Webhook Security

### Token Validation

Every webhook request must include a valid channel token:

```python
def _validate_token_or_raise(token: Optional[str]):
    """Validate webhook secrets using shared service helper."""
    try:
        WebhookService.validate_webhook_secret(token)
    except ValueError as exc:
        logger.warning(f"Invalid webhook token provided: {exc}")
        raise HTTPException(status_code=403, detail=str(exc))
```

- Token stored in environment variable: `WEBHOOK_SECRET`
- Validates `X-Goog-Channel-Token` header matches secret
- Returns 403 Forbidden for invalid tokens

### HTTPS Requirement

Google Calendar webhooks **require HTTPS** in production. The webhook URL must:
- Use HTTPS protocol
- Have a valid SSL certificate
- Be publicly accessible

## Webhook Notification Types

### 1. Sync Notification

Initial handshake when channel is first registered.

**Headers:**
```
X-Goog-Resource-State: sync
```

**Response:**
```json
{"status": "ok"}
```

**Action:** Log success, no sync needed

### 2. Exists Notification  

Calendar has changes available.

**Headers:**
```
X-Goog-Resource-State: exists
```

**Action:** Trigger `sync_calendar_events()` to fetch changes

### 3. Not Exists Notification

Resource no longer exists (calendar deleted).

**Headers:**
```
X-Goog-Resource-State: not_exists
```

**Action:** Deactivate channel, clean up local data

## Database Schema

### CalendarSyncState

Stores webhook channel information and sync state.

| Column | Type | Description |
|--------|------|-------------|
| id | Integer | Primary key |
| channel_id | String | Unique channel identifier (UUID) |
| resource_id | String | Google's resource ID |
| calendar_id | String | Google Calendar ID (default: 'primary') |
| sync_token | String | Sync token for incremental updates |
| expiration | DateTime | Channel expiration timestamp |
| active | Boolean | Whether channel is active |
| created_at | DateTime | Channel creation time |
| updated_at | DateTime | Last sync time |

### CalendarEvent

Local mirror of Google Calendar events.

| Column | Type | Description |
|--------|------|-------------|
| id | Integer | Primary key |
| google_event_id | String | Google's event ID (unique) |
| calendar_id | String | Calendar ID |
| summary | String | Event title |
| description | Text | Event description |
| start_time | DateTime | Event start (timezone-aware) |
| end_time | DateTime | Event end (timezone-aware) |
| meet_link | String | Google Meet link |
| html_link | String | Calendar event link |
| status | String | confirmed, tentative, cancelled |
| organizer_email | String | Event organizer |
| attendees | Text | JSON array of attendees |
| created_at | DateTime | Local record creation |
| updated_at | DateTime | Local record last update |

## Performance Considerations

### Database Commits

The sync logic commits after each page of results:

```python
# Commit after each page to avoid losing work if later pages fail
db.commit()
```

This ensures partial progress is saved even if later pages fail.

### Query Optimization

When checking for existing events:

```python
local_event = db.query(models.CalendarEvent).filter(
    models.CalendarEvent.google_event_id == google_id
).first()
```

Ensure `google_event_id` is indexed:

```sql
CREATE INDEX idx_calendar_events_google_event_id 
ON calendar_events(google_event_id);
```

### Logging

Structured logging provides observability without performance impact:

```python
calendar_logger.info(
    action="sync_event",
    status="updated",
    message=f"Updated local event {google_id}"
)
```

## Testing

### Unit Tests

See `tests/test_calendar_sync.py` for comprehensive tests:

1. **test_sync_calendar_events_upsert**: Event creation and updates
2. **test_sync_calendar_events_cancellation**: Cancelled events
3. **test_sync_calendar_410_gone**: Invalid sync token recovery

### Integration Tests

See `tests/test_webhooks.py`:

1. **test_calendar_webhook_with_valid_token**: Valid webhook processing
2. **test_calendar_webhook_with_invalid_token**: Token validation
3. **test_webhook_endpoint_sync_notification**: Sync handshake

### Manual Testing

1. **Create Event in Google Calendar**
   - Create event manually in Google Calendar UI
   - Wait for webhook notification (~30 seconds)
   - Verify event appears in local database

2. **Update Event**
   - Modify event in Google Calendar
   - Verify changes reflected locally

3. **Cancel Event**
   - Delete event in Google Calendar
   - Verify local event status becomes 'cancelled'

4. **Simulate 410 Error**
   - Manually corrupt sync token in database
   - Trigger webhook notification
   - Verify full re-sync occurs

## Troubleshooting

### Webhooks Not Received

**Symptoms:** Events created in Google Calendar not syncing

**Checks:**
1. Verify webhook URL is publicly accessible (HTTPS)
2. Check channel is active: `SELECT * FROM calendar_sync_states WHERE active=true`
3. Verify channel hasn't expired
4. Check application logs for errors
5. Test webhook endpoint manually:
   ```bash
   curl -X POST https://your-domain.com/webhooks/google-drive \
     -H "X-Goog-Channel-ID: your-channel-id" \
     -H "X-Goog-Resource-ID: your-resource-id" \
     -H "X-Goog-Resource-State: exists" \
     -H "X-Goog-Channel-Token: your-secret"
   ```

### Sync Token Keeps Expiring

**Symptoms:** Frequent 410 errors, constant full re-syncs

**Possible Causes:**
1. Channels not being renewed before expiration
2. Calendar has excessive changes
3. Token not being properly saved after sync

**Solutions:**
1. Implement channel renewal scheduler (see Phase 4 in ACTION_PLAN.md)
2. Reduce time between syncs
3. Verify `db.commit()` is called after updating sync token

### Duplicate Events

**Symptoms:** Same event appears multiple times in database

**Checks:**
1. Verify `google_event_id` is unique in database schema
2. Check for race conditions in concurrent webhook handlers
3. Review sync logic for proper upsert behavior

**Solution:**
```sql
ALTER TABLE calendar_events 
ADD CONSTRAINT calendar_events_google_event_id_unique 
UNIQUE (google_event_id);
```

### Events Not Updating

**Symptoms:** Local events don't reflect Google Calendar changes

**Checks:**
1. Verify sync token is being updated after successful sync
2. Check webhook channel is active
3. Review logs for sync errors
4. Verify event ID matching logic

## Best Practices

### 1. Always Use Sync Tokens

Never fetch all events on every sync. Always use sync tokens for efficiency:

✅ **Good:**
```python
result = service.list_events(
    calendar_id="primary",
    sync_token=stored_token
)
```

❌ **Bad:**
```python
result = service.list_events(
    calendar_id="primary",
    time_min=thirty_days_ago
)
```

### 2. Handle 410 Gracefully

Always handle sync token expiration:

```python
try:
    result = fetch_with_sync_token()
except HttpError410:
    # Clear token, perform full sync
    perform_full_sync()
```

### 3. Validate Webhook Tokens

Always validate webhook tokens to prevent unauthorized access:

```python
_validate_token_or_raise(x_goog_channel_token)
```

### 4. Log Everything

Use structured logging for observability:

```python
calendar_logger.info(
    action="sync",
    status="success",
    details={"events_processed": count}
)
```

### 5. Commit Frequently

Commit database changes after each page to avoid data loss:

```python
# Process page
db.commit()
```

### 6. Monitor Channel Expiration

Implement automated channel renewal before expiration:

```python
# Run daily
scheduler_service.renew_expiring_channels(db)
```

## References

- [Google Calendar API - Push Notifications](https://developers.google.com/calendar/api/guides/push)
- [Google Calendar API - Sync](https://developers.google.com/calendar/api/guides/sync)
- [Google Calendar API - Events.list](https://developers.google.com/calendar/api/v3/reference/events/list)
- [Google Calendar API - Events.watch](https://developers.google.com/calendar/api/v3/reference/events/watch)

## Related Documentation

- `ACTION_PLAN.md` - Phase 4: Calendar Sync & Features
- `CALENDAR_API.md` - Calendar API endpoints
- `docs/backend/database_schema.md` - Database schema details
- `docs/backend/api_reference.md` - API reference documentation
