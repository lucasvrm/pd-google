# Calendar Environment Variables Documentation

## Required Environment Variables

### GOOGLE_SERVICE_ACCOUNT_JSON
- **Type**: String (JSON)
- **Required**: Yes
- **Description**: Google Service Account credentials for Calendar API access
- **Format**: JSON string containing service account key
- **Example**: 
```json
{
  "type": "service_account",
  "project_id": "your-project-id",
  "private_key_id": "key-id",
  "private_key": "-----BEGIN PRIVATE KEY-----\n...",
  "client_email": "service-account@project.iam.gserviceaccount.com",
  "client_id": "12345",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token"
}
```
- **Notes**: The service account must have Calendar API enabled and appropriate permissions

## Webhook Configuration

### WEBHOOK_BASE_URL
- **Type**: String (URL)
- **Required**: Yes (for production)
- **Default**: `http://localhost:8000`
- **Description**: Public URL where the application is accessible for receiving webhooks
- **Example**: `https://pipedesk-drive-backend.onrender.com`
- **Notes**: 
  - Must be publicly accessible for Google to send webhook notifications
  - Used for constructing webhook callback URLs
  - Should use HTTPS in production

### WEBHOOK_SECRET
- **Type**: String
- **Required**: Recommended
- **Default**: `None`
- **Description**: Secret token for validating webhook requests
- **Example**: `my-secure-random-token-123`
- **Notes**:
  - When set, webhook requests without matching token will receive 403 Forbidden
  - Use a strong, random value
  - Keep this secret secure and rotate periodically
  - If not set, webhook token validation is disabled (not recommended for production)

## Calendar-Specific Configuration

### CALENDAR_EVENT_RETENTION_DAYS
- **Type**: Integer
- **Required**: No
- **Default**: `180` (6 months)
- **Description**: Number of days to retain calendar events before archiving/cleanup
- **Example**: `365` (1 year), `90` (3 months)
- **Notes**:
  - Events with end_time older than this many days will be marked as cancelled
  - Cleanup job runs daily via scheduler
  - Minimum recommended: 90 days
  - Value of 0 or negative disables cleanup (not recommended)

## Database Configuration

### DATABASE_URL
- **Type**: String (Connection String)
- **Required**: Yes
- **Description**: Database connection string for PostgreSQL or SQLite
- **Format (PostgreSQL)**: `postgresql://user:password@host:port/database`
- **Format (SQLite)**: `sqlite:///./database.db`
- **Example**: `postgresql://dbuser:dbpass@localhost:5432/pipedesk_calendar`
- **Notes**: 
  - PostgreSQL recommended for production
  - SQLite acceptable for development/testing
  - Ensure database has calendar_events and calendar_sync_states tables (see migrations)

## Optional Configuration

### USE_MOCK_DRIVE
- **Type**: Boolean
- **Required**: No
- **Default**: `false`
- **Description**: Enable mock mode for development/testing
- **Values**: `true`, `false`
- **Notes**: When true, Calendar API calls will be mocked (useful for testing without real Google credentials)

### REDIS_URL
- **Type**: String (Connection String)
- **Required**: No (but recommended for production)
- **Default**: `redis://localhost:6379/0`
- **Description**: Redis connection string for caching
- **Example**: `redis://redis-host:6379/0`
- **Notes**: Used for Drive caching, not critical for Calendar but improves overall performance

### REDIS_CACHE_ENABLED
- **Type**: Boolean
- **Required**: No
- **Default**: `true`
- **Description**: Enable/disable Redis caching
- **Values**: `true`, `false`

## Complete Example Configuration

### Production (.env)
```bash
# Google Service Account
GOOGLE_SERVICE_ACCOUNT_JSON={"type":"service_account",...}

# Webhook Configuration
WEBHOOK_BASE_URL=https://api.yourcompany.com
WEBHOOK_SECRET=your-secret-webhook-token-here

# Calendar Settings
CALENDAR_EVENT_RETENTION_DAYS=180

# Database
DATABASE_URL=postgresql://dbuser:dbpass@postgres-host:5432/pipedesk

# Optional
REDIS_URL=redis://redis-host:6379/0
REDIS_CACHE_ENABLED=true
USE_MOCK_DRIVE=false
```

### Development (.env)
```bash
# Google Service Account (can use test account)
GOOGLE_SERVICE_ACCOUNT_JSON={"type":"service_account",...}

# Webhook Configuration
WEBHOOK_BASE_URL=http://localhost:8000
WEBHOOK_SECRET=test-secret-123

# Calendar Settings
CALENDAR_EVENT_RETENTION_DAYS=90

# Database (SQLite for local dev)
DATABASE_URL=sqlite:///./pd_google.db

# Optional
USE_MOCK_DRIVE=true
REDIS_CACHE_ENABLED=false
```

## Verifying Configuration

After setting environment variables, you can verify the Calendar setup:

1. **Check Health Endpoint**:
```bash
curl http://localhost:8000/health/calendar
```

Expected response should show:
- `status: "healthy"` or `"degraded"`
- `active_channels` count
- `event_count` in database

2. **Test Webhook Token** (if WEBHOOK_SECRET is set):
```bash
# Should return 403 with wrong token
curl -X POST http://localhost:8000/webhooks/google-drive \
  -H "X-Goog-Channel-ID: test" \
  -H "X-Goog-Resource-ID: test" \
  -H "X-Goog-Resource-State: sync" \
  -H "X-Goog-Channel-Token: wrong-token"
```

3. **Check Scheduler Jobs**:
Look for these log messages on startup:
```
Scheduler started.
```

And periodic executions:
```
Running channel renewal job...
Running calendar event cleanup job...
```

## Troubleshooting

### "GOOGLE_SERVICE_ACCOUNT_JSON is missing or invalid"
- Ensure the env var is set
- Verify the JSON is valid (use a JSON validator)
- Check that the service account has Calendar API enabled

### Webhook notifications not received
- Verify `WEBHOOK_BASE_URL` is publicly accessible
- Ensure domain is verified in Google Cloud Console
- Check `WEBHOOK_SECRET` matches what was used when registering the channel

### Events not being cleaned up
- Check `CALENDAR_EVENT_RETENTION_DAYS` is set correctly
- Verify scheduler is running (check logs)
- Cleanup job runs once every 24 hours

### "No active webhook channels" in health check
- Register a webhook channel using POST /api/calendar/watch
- Check that channels haven't expired (they expire after ~7 days)
- Scheduler should auto-renew channels every 6 hours

## Security Best Practices

1. **Always set WEBHOOK_SECRET in production** - prevents unauthorized webhook calls
2. **Use HTTPS for WEBHOOK_BASE_URL** - ensures secure communication
3. **Rotate WEBHOOK_SECRET periodically** - good security hygiene
4. **Secure GOOGLE_SERVICE_ACCOUNT_JSON** - never commit to source control
5. **Use strong DATABASE_URL credentials** - follow database security best practices
6. **Limit service account permissions** - grant only necessary Calendar scopes
