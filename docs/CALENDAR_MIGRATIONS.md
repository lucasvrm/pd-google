# Calendar Database Migrations Summary

## Overview
This document describes the database schema changes required for the Calendar integration (Phase 2 - Hardening).

## Migration Files

### 1. calendar_tables.sql
**Location**: `/migrations/calendar_tables.sql`
**Status**: ✅ Created, needs execution
**Description**: Creates the core Calendar tables

**Tables Created**:

#### calendar_sync_states
Stores webhook channel registration information for Calendar synchronization.

```sql
CREATE TABLE IF NOT EXISTS calendar_sync_states (
    id SERIAL PRIMARY KEY,
    resource_id VARCHAR(255),
    channel_id VARCHAR(255) UNIQUE,
    calendar_id VARCHAR(255) DEFAULT 'primary',
    sync_token VARCHAR(255),
    expiration TIMESTAMP,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP
);
```

**Columns**:
- `id`: Primary key
- `resource_id`: Google Calendar resource ID
- `channel_id`: UUID for webhook channel
- `calendar_id`: Calendar ID (default: 'primary')
- `sync_token`: Token for incremental sync
- `expiration`: When webhook channel expires
- `active`: Whether channel is active
- `created_at`: Creation timestamp
- `updated_at`: Last update timestamp

#### calendar_events
Stores synchronized calendar events from Google Calendar.

```sql
CREATE TABLE IF NOT EXISTS calendar_events (
    id SERIAL PRIMARY KEY,
    google_event_id VARCHAR(255) UNIQUE NOT NULL,
    calendar_id VARCHAR(255) DEFAULT 'primary',
    summary VARCHAR(255),
    description TEXT,
    start_time TIMESTAMP WITH TIME ZONE,
    end_time TIMESTAMP WITH TIME ZONE,
    meet_link VARCHAR(255),
    html_link VARCHAR(255),
    status VARCHAR(50),
    organizer_email VARCHAR(255),
    attendees JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

**Columns**:
- `id`: Primary key
- `google_event_id`: Unique event ID from Google Calendar
- `calendar_id`: Calendar ID (default: 'primary')
- `summary`: Event title
- `description`: Event description
- `start_time`: Event start time (with timezone)
- `end_time`: Event end time (with timezone)
- `meet_link`: Google Meet video conference link
- `html_link`: Link to view event in Google Calendar
- `status`: Event status (confirmed, tentative, cancelled)
- `organizer_email`: Email of event organizer
- `attendees`: JSON array of attendee objects
- `created_at`: Creation timestamp
- `updated_at`: Last update timestamp

**Indexes** (recommended but not in migration file):
```sql
CREATE INDEX idx_calendar_events_status ON calendar_events(status);
CREATE INDEX idx_calendar_events_start_time ON calendar_events(start_time);
CREATE INDEX idx_calendar_events_end_time ON calendar_events(end_time);
CREATE INDEX idx_calendar_sync_states_expiration ON calendar_sync_states(expiration);
CREATE INDEX idx_calendar_sync_states_active ON calendar_sync_states(active);
```

## Execution Instructions

### For PostgreSQL (Production)

1. **Connect to your database**:
```bash
psql postgresql://user:password@host:5432/database
```

2. **Execute the migration**:
```bash
\i migrations/calendar_tables.sql
```

OR directly via command line:
```bash
psql postgresql://user:password@host:5432/database < migrations/calendar_tables.sql
```

3. **Verify tables were created**:
```sql
\dt calendar_*
```

Expected output:
```
             List of relations
 Schema |         Name          | Type  | Owner
--------+-----------------------+-------+-------
 public | calendar_events       | table | user
 public | calendar_sync_states  | table | user
```

4. **(Optional) Create recommended indexes**:
```sql
CREATE INDEX idx_calendar_events_status ON calendar_events(status);
CREATE INDEX idx_calendar_events_start_time ON calendar_events(start_time);
CREATE INDEX idx_calendar_events_end_time ON calendar_events(end_time);
CREATE INDEX idx_calendar_sync_states_expiration ON calendar_sync_states(expiration);
CREATE INDEX idx_calendar_sync_states_active ON calendar_sync_states(active);
```

### For SQLite (Development/Testing)

The migration SQL is compatible with SQLite. Run:

```bash
sqlite3 pd_google.db < migrations/calendar_tables.sql
```

**Note**: Change `SERIAL` to `INTEGER` and `JSONB` to `TEXT` for SQLite if needed. The application's ORM (SQLAlchemy) handles these differences automatically.

### Verification

After running migrations, verify the schema:

```sql
-- Check calendar_events structure
SELECT column_name, data_type, is_nullable 
FROM information_schema.columns 
WHERE table_name = 'calendar_events';

-- Check calendar_sync_states structure
SELECT column_name, data_type, is_nullable 
FROM information_schema.columns 
WHERE table_name = 'calendar_sync_states';

-- Verify tables are empty (initial state)
SELECT COUNT(*) FROM calendar_events;
SELECT COUNT(*) FROM calendar_sync_states;
```

## Integration with Existing Migrations

### Existing Migration Files

1. **add_soft_delete_fields.py**
   - Adds soft delete fields to Drive tables
   - Status: Already executed
   - Not related to Calendar tables

2. **ensure_templates.py**
   - Sets up Drive folder templates
   - Status: Already executed
   - Not related to Calendar tables

### Migration Order

The Calendar migrations are independent and can be run at any time. Recommended order:

1. ✅ `add_soft_delete_fields.py` (already executed)
2. ✅ `ensure_templates.py` (already executed)
3. 🆕 `calendar_tables.sql` (needs execution)

## Rollback Instructions

To rollback Calendar tables (if needed):

```sql
DROP TABLE IF EXISTS calendar_events CASCADE;
DROP TABLE IF EXISTS calendar_sync_states CASCADE;
```

⚠️ **Warning**: This will delete all calendar event data. Back up data before rolling back.

## Data Migration

If you need to preserve existing data:

1. **Backup before migration**:
```bash
pg_dump -U user -h host -d database -t calendar_events -t calendar_sync_states > calendar_backup.sql
```

2. **Restore after migration**:
```bash
psql -U user -h host -d database < calendar_backup.sql
```

## Monitoring Migration Success

After executing migrations:

1. **Check application logs** on startup:
```
Database migrations completed successfully
```

2. **Call health endpoint**:
```bash
curl http://your-api/health/calendar
```

Should return:
```json
{
  "service": "calendar",
  "status": "healthy" or "degraded",
  "active_channels": 0,
  "event_count": 0,
  ...
}
```

3. **Test creating a watch channel**:
```bash
curl -X POST http://your-api/api/calendar/watch
```

Should return 201 with channel details.

## Troubleshooting

### "relation calendar_events does not exist"
- Migration not executed yet
- Run `migrations/calendar_tables.sql`

### "column attendees does not exist"
- Old migration file version
- Re-run migration or add column manually:
```sql
ALTER TABLE calendar_events ADD COLUMN attendees JSONB;
```

### "duplicate key value violates unique constraint"
- Migration already run
- No action needed

### Permission errors
- Ensure database user has CREATE TABLE privileges
```sql
GRANT CREATE ON SCHEMA public TO your_user;
```

## Future Migrations

Planned future migrations:
- [ ] Add indexes for performance optimization
- [ ] Add calendar_id foreign key constraints (if multi-calendar support is added)
- [ ] Add event recurrence tables (if recurring events support is added)

## Contact

For migration issues or questions, contact the development team.

Last updated: 2025-12-08
