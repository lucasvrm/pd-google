# Database Schema Documentation

## Overview

This document describes the database schema for the PipeDesk Google Drive Backend integration, including all SQLAlchemy ORM models defined in `models.py`. The schema supports Google Drive integration, Google Calendar synchronization, CRM entities, and webhook channels for real-time updates.

**Database Engine**: PostgreSQL (Supabase) for production, SQLite for development/testing  
**ORM**: SQLAlchemy (Sync)  
**Migration Strategy**: SQL scripts in `/migrations/` directory

---

## Table of Contents

1. [Calendar Tables](#calendar-tables)
   - [calendar_sync_states](#calendar_sync_states)
   - [calendar_events](#calendar_events)
2. [Drive Tables](#drive-tables)
   - [drive_webhook_channels](#drive_webhook_channels)
   - [google_drive_folders](#google_drive_folders)
   - [drive_files](#drive_files)
   - [drive_change_logs](#drive_change_logs)
3. [Drive Template Tables](#drive-template-tables)
   - [drive_structure_templates](#drive_structure_templates)
   - [drive_structure_nodes](#drive_structure_nodes)
4. [CRM Tables](#crm-tables)
   - [companies](#companies)
   - [users](#users)
   - [contacts](#contacts)
   - [lead_contacts](#lead_contacts)
   - [leads](#leads)
   - [master_deals](#master_deals)
   - [tags](#tags)
   - [lead_tags](#lead_tags)
   - [lead_statuses](#lead_statuses)
   - [lead_origins](#lead_origins)
   - [lead_activity_stats](#lead_activity_stats)
5. [Authorization Tables](#authorization-tables)
   - [user_roles](#user_roles)

---

## Calendar Tables

### calendar_sync_states

**Purpose**: Stores webhook channel registration information and sync tokens for Google Calendar. Enables incremental synchronization by tracking changes since the last sync, avoiding the need to fetch all events on every sync operation.

**Why do we need this?**: Google Calendar's Push Notifications API requires webhook channels to be registered. Each channel has a unique ID and expiration time. The `sync_token` allows the application to request only events that have changed since the last sync, significantly improving performance and reducing API quota usage.

**Model**: `CalendarSyncState`  
**Table Name**: `calendar_sync_states`

| Column        | Type               | Constraints                  | Description                                           |
|---------------|--------------------|-----------------------------|-------------------------------------------------------|
| id            | Integer            | PRIMARY KEY, INDEX          | Auto-incrementing unique identifier                   |
| resource_id   | String             |                             | Resource ID returned by Google when channel is created |
| channel_id    | String             | UNIQUE, INDEX               | Our UUID for the webhook channel (used for verification) |
| calendar_id   | String             | DEFAULT 'primary'           | ID of the monitored calendar (typically 'primary')    |
| sync_token    | String             |                             | Token for fetching incremental changes from Google    |
| expiration    | DateTime(TZ)       |                             | When the webhook channel expires (~7 days from creation) |
| active        | Boolean            | DEFAULT True                | Whether the channel is currently active               |
| created_at    | DateTime(TZ)       | SERVER_DEFAULT now()        | Record creation timestamp                             |
| updated_at    | DateTime(TZ)       | ON UPDATE now()             | Last update timestamp                                 |

**Indexes**:
- Primary: `id`
- Unique: `channel_id`
- Recommended: `expiration` (for finding channels needing renewal), `active` (for filtering active channels)

**Usage Pattern**:
1. When registering a webhook with Google, create a new record with a unique `channel_id`
2. Google returns a `resource_id` which we store
3. After each successful sync, update the `sync_token` with the `nextSyncToken` from Google's response
4. Monitor `expiration` and renew channels before they expire
5. Set `active=False` when a channel is stopped or expires

**Related Operations**:
- Channel registration: `services/google_calendar_service.py::watch_calendar()`
- Incremental sync: `services/google_calendar_service.py::sync_events()`
- Channel renewal: Scheduled job to renew before expiration

---

### calendar_events

**Purpose**: Local mirror of Google Calendar events. Stores event data locally to enable fast queries without hitting the Google Calendar API on every read, and to maintain a historical record even if events are deleted from Google.

**Why do we need a local mirror?**: 
- **Performance**: Reading from the local database is orders of magnitude faster than calling the Google Calendar API
- **Availability**: The application can continue displaying calendar data even if Google's API is temporarily unavailable
- **Cost**: Reduces API quota usage by serving reads from the local database
- **Analytics**: Enables complex queries and analytics on calendar data without expensive API calls
- **Audit Trail**: Maintains a record of events even after they're deleted from Google Calendar

**Model**: `CalendarEvent`  
**Table Name**: `calendar_events`

| Column           | Type               | Constraints                  | Description                                           |
|------------------|--------------------|-----------------------------|-------------------------------------------------------|
| id               | Integer            | PRIMARY KEY, INDEX          | Auto-incrementing unique identifier                   |
| google_event_id  | String             | UNIQUE, INDEX, NOT NULL     | Event ID from Google Calendar (e.g., "abc123xyz")    |
| calendar_id      | String             | DEFAULT 'primary'           | Calendar this event belongs to                        |
| summary          | String             |                             | Event title/summary                                   |
| description      | Text               |                             | Event description (can be long)                       |
| start_time       | DateTime(TZ)       |                             | Event start time with timezone                        |
| end_time         | DateTime(TZ)       |                             | Event end time with timezone                          |
| meet_link        | String             |                             | Google Meet video conference link (if created)        |
| html_link        | String             |                             | Link to view event in Google Calendar web UI          |
| status           | String             |                             | Event status: "confirmed", "tentative", or "cancelled" |
| organizer_email  | String             |                             | Email of the event organizer                          |
| attendees        | Text               |                             | JSON string of attendee objects (for SQLite compatibility) |
| created_at       | DateTime(TZ)       | SERVER_DEFAULT now()        | Record creation timestamp                             |
| updated_at       | DateTime(TZ)       | SERVER_DEFAULT & ON UPDATE  | Last update timestamp                                 |

**Indexes**:
- Primary: `id`
- Unique: `google_event_id` (ensures each Google event is stored once)
- Recommended: `status` (for filtering by event status), `start_time` & `end_time` (for date range queries)

**Attendees Format**: Stored as JSON string for maximum database compatibility:
```json
[
  {"email": "user@example.com", "responseStatus": "accepted"},
  {"email": "client@example.com", "responseStatus": "needsAction"}
]
```

**Sync Strategy**:
1. **Initial Sync**: When webhook is first set up, perform a full sync of recent events
2. **Incremental Sync**: When webhook notification received, use `sync_token` to fetch only changes
3. **Insert/Update**: Create or update event based on `google_event_id`
4. **Soft Delete**: When Google event is deleted, update `status` to "cancelled" (preserves history)

**Usage Patterns**:
- Creating events: Insert immediately after successful Google API call
- Listing events: Query local DB with date filters (fast, no API call)
- Syncing changes: Update/insert events received via webhook
- Cleanup: Periodic job to archive old cancelled events

**Related Operations**:
- Event creation: `routers/calendar.py::create_event()`
- Event listing: `routers/calendar.py::list_events()` (reads from DB)
- Event sync: Webhook handler in `routers/webhooks.py`

---

## Drive Tables

### drive_webhook_channels

**Purpose**: Stores Google Drive webhook notification channels for real-time file/folder change notifications.

**Model**: `DriveWebhookChannel`  
**Table Name**: `drive_webhook_channels`

| Column               | Type               | Constraints                  | Description                                           |
|----------------------|--------------------|-----------------------------|-------------------------------------------------------|
| id                   | Integer            | PRIMARY KEY, INDEX          | Auto-incrementing unique identifier                   |
| channel_id           | String             | UNIQUE, INDEX               | Unique channel identifier                             |
| resource_id          | String             | INDEX                       | Resource ID returned by Google                        |
| resource_type        | String             | DEFAULT 'folder'            | Type of resource being watched: "folder" or "file"    |
| watched_resource_id  | String             | INDEX                       | ID of the Drive folder/file being watched             |
| expires_at           | DateTime(TZ)       |                             | Channel expiration timestamp                          |
| active               | Boolean            | DEFAULT True, INDEX         | Whether channel is active                             |
| created_at           | DateTime(TZ)       | SERVER_DEFAULT now()        | Record creation timestamp                             |
| updated_at           | DateTime(TZ)       | ON UPDATE now()             | Last update timestamp                                 |

**Usage**: Similar to Calendar webhooks, but for Drive resources. Channels expire and must be renewed periodically.

---

### google_drive_folders

**Purpose**: Maps CRM entities (companies, leads, deals, contacts) to their corresponding Google Drive folders.

**Model**: `DriveFolder`  
**Table Name**: `google_drive_folders`

| Column        | Type               | Constraints                  | Description                                           |
|---------------|--------------------|-----------------------------|-------------------------------------------------------|
| id            | Integer            | PRIMARY KEY, INDEX          | Auto-incrementing unique identifier                   |
| entity_id     | String             | INDEX                       | ID of the CRM entity (company, lead, deal, contact)   |
| entity_type   | String             | INDEX                       | Type: "company", "lead", "deal", or "contact"         |
| folder_id     | String             | UNIQUE, INDEX               | Google Drive folder ID                                |
| folder_url    | String             |                             | User-friendly URL to the folder in Google Drive       |
| created_at    | DateTime(TZ)       | SERVER_DEFAULT now()        | Record creation timestamp                             |
| deleted_at    | DateTime(TZ)       | NULLABLE, INDEX             | Soft delete timestamp (NULL = not deleted)            |
| deleted_by    | String             | NULLABLE                    | User ID who performed the deletion                    |
| delete_reason | String             | NULLABLE                    | Reason for deletion                                   |

**Soft Delete**: Uses `deleted_at` field for soft deletion, allowing recovery and audit trails.

---

### drive_files

**Purpose**: Tracks files stored in Google Drive, linked to their parent folders.

**Model**: `DriveFile`  
**Table Name**: `drive_files`

| Column           | Type               | Constraints                  | Description                                           |
|------------------|--------------------|-----------------------------|-------------------------------------------------------|
| id               | Integer            | PRIMARY KEY, INDEX          | Auto-incrementing unique identifier                   |
| file_id          | String             | UNIQUE, INDEX               | Google Drive file ID                                  |
| parent_folder_id | String             | INDEX                       | Parent folder ID in Drive                             |
| name             | String             |                             | File name                                             |
| mime_type        | String             |                             | MIME type (e.g., "application/pdf")                   |
| size             | Integer            |                             | File size in bytes                                    |
| created_at       | DateTime(TZ)       | SERVER_DEFAULT now()        | Record creation timestamp                             |
| deleted_at       | DateTime(TZ)       | NULLABLE, INDEX             | Soft delete timestamp                                 |
| deleted_by       | String             | NULLABLE                    | User ID who deleted the file                          |
| delete_reason    | String             | NULLABLE                    | Reason for deletion                                   |

**Soft Delete**: Supports soft deletion for audit and recovery purposes.

---

### drive_change_logs

**Purpose**: Audit log for Drive changes received via webhooks. Records all change notifications from Google Drive.

**Model**: `DriveChangeLog`  
**Table Name**: `drive_change_logs`

| Column               | Type               | Constraints                  | Description                                           |
|----------------------|--------------------|-----------------------------|-------------------------------------------------------|
| id                   | Integer            | PRIMARY KEY, INDEX          | Auto-incrementing unique identifier                   |
| channel_id           | String             | INDEX                       | Channel that received the notification                |
| resource_id          | String             | INDEX                       | Resource ID from Google                               |
| resource_state       | String             |                             | State: "sync", "add", "remove", "update", "trash", etc. |
| changed_resource_id  | String             | INDEX, NULLABLE             | Drive file/folder ID that changed                     |
| event_type           | String             | NULLABLE                    | Additional event information                          |
| received_at          | DateTime(TZ)       | SERVER_DEFAULT now()        | When notification was received                        |
| raw_headers          | Text               | NULLABLE                    | JSON string of all webhook headers (for debugging)    |

**Usage**: Debugging webhook issues, auditing changes, and understanding Drive activity patterns.

---

## Drive Template Tables

### drive_structure_templates

**Purpose**: Defines reusable folder structure templates for different entity types.

**Model**: `DriveStructureTemplate`  
**Table Name**: `drive_structure_templates`

| Column      | Type               | Constraints                  | Description                                           |
|-------------|--------------------|-----------------------------|-------------------------------------------------------|
| id          | Integer            | PRIMARY KEY, INDEX          | Auto-incrementing unique identifier                   |
| name        | String             | UNIQUE                      | Template name (e.g., "Company Standard")              |
| entity_type | String             | INDEX                       | Entity type: "company", "lead", "deal", etc.          |
| active      | Boolean            | DEFAULT True                | Whether template is currently active                  |

**Relationships**: 
- `nodes`: One-to-many relationship with `DriveStructureNode`

---

### drive_structure_nodes

**Purpose**: Defines the hierarchical structure of folders within a template.

**Model**: `DriveStructureNode`  
**Table Name**: `drive_structure_nodes`

| Column       | Type               | Constraints                  | Description                                           |
|--------------|--------------------|-----------------------------|-------------------------------------------------------|
| id           | Integer            | PRIMARY KEY, INDEX          | Auto-incrementing unique identifier                   |
| template_id  | Integer            | FOREIGN KEY (templates.id)  | Template this node belongs to                         |
| parent_id    | Integer            | FOREIGN KEY (nodes.id), NULL| Parent node ID (NULL for root nodes)                  |
| name         | String             |                             | Folder name (can contain placeholders like {{year}})  |
| order        | Integer            | DEFAULT 0                   | Display/creation order                                |

**Relationships**: 
- `template`: Many-to-one relationship with `DriveStructureTemplate`

**Placeholder Support**: Node names can contain placeholders like `{{year}}`, `{{entity_name}}`, etc.

---

## CRM Tables

### companies

**Purpose**: Represents companies in the CRM system (mapped from main Supabase database).

**Model**: `Company`  
**Table Name**: `companies`

| Column | Type   | Constraints    | Description              |
|--------|--------|----------------|--------------------------|
| id     | String | PRIMARY KEY    | UUID                     |
| name   | String |                | Company name (Razão Social) |

---

### users

**Purpose**: System users (mapped from Supabase Auth).

**Model**: `User`  
**Table Name**: `users`

| Column | Type   | Constraints    | Description       |
|--------|--------|----------------|-------------------|
| id     | String | PRIMARY KEY    | User UUID         |
| name   | String |                | User's full name  |
| email  | String | NULLABLE       | User's email      |

---

### contacts

**Purpose**: Contact persons in the CRM.

**Model**: `Contact`  
**Table Name**: `contacts`

| Column | Type   | Constraints    | Description        |
|--------|--------|----------------|--------------------|
| id     | String | PRIMARY KEY    | Contact UUID       |
| name   | String |                | Contact name       |
| email  | String | NULLABLE       | Contact email      |
| phone  | String | NULLABLE       | Contact phone      |
| role   | String | NULLABLE       | Contact role/title (e.g., "CEO", "Manager") |

---

### lead_contacts

**Purpose**: Junction table mapping leads to contacts. Tracks which contacts are associated with which leads and which contact is the primary one for each lead.

**Model**: `LeadContact`  
**Table Name**: `lead_contacts`

| Column     | Type         | Constraints                     | Description                                    |
|------------|--------------|---------------------------------|------------------------------------------------|
| lead_id    | String       | FK(leads.id), PK               | Lead UUID                                      |
| contact_id | String       | FK(contacts.id), PK            | Contact UUID                                   |
| is_primary | Boolean      | DEFAULT False                   | Whether this contact is the primary contact for the lead |
| added_at   | DateTime(TZ) | SERVER_DEFAULT now()           | When the contact was linked to the lead        |

**Composite Primary Key**: (`lead_id`, `contact_id`)

**Relationships**:
- `contact`: Many-to-one with `Contact`

**Usage**:
- The primary contact for a lead is determined by `is_primary=true`
- If no contact has `is_primary=true`, the first contact (ordered by `added_at`) is used as fallback
- Used by the Sales View endpoint to populate the `primary_contact` field

---

### leads

**Purpose**: Sales leads with comprehensive tracking and relationship data.

**Model**: `Lead`  
**Table Name**: `leads`

| Column                      | Type         | Constraints                     | Description                                    |
|-----------------------------|--------------|---------------------------------|------------------------------------------------|
| id                          | String       | PRIMARY KEY                     | Lead UUID                                      |
| title (→ legal_name)        | String       |                                 | Legal name of the lead (column: legal_name)    |
| trade_name                  | String       | NULLABLE                        | Trade name                                     |
| lead_status_id              | String       | FK(lead_statuses.id), NULLABLE  | Current status                                 |
| lead_origin_id              | String       | FK(lead_origins.id), NULLABLE   | Origin/source                                  |
| owner_user_id               | String       | FK(users.id), NULLABLE          | Assigned user                                  |
| qualified_company_id        | String       | FK(companies.id), NULLABLE      | If qualified, linked company                   |
| qualified_master_deal_id    | String       | FK(master_deals.id), NULLABLE   | If qualified, linked deal                      |
| address_city                | String       | NULLABLE                        | City                                           |
| address_state               | String       | NULLABLE                        | State                                          |
| last_interaction_at         | DateTime(TZ) | NULLABLE, INDEX                 | Last meaningful interaction                    |
| priority_score              | Integer      | DEFAULT 0, INDEX                | Calculated priority score                      |
| disqualified_at             | DateTime(TZ) | NULLABLE, INDEX                 | When lead was disqualified/lost                |
| disqualification_reason     | Text         | NULLABLE                        | Reason for disqualification                    |
| qualified_at                | DateTime(TZ) | NULLABLE, INDEX                 | When lead was successfully qualified           |
| deleted_at                  | DateTime(TZ) | NULLABLE, INDEX                 | Soft delete timestamp (set when qualified)     |
| created_at                  | DateTime(TZ) | SERVER_DEFAULT now()            | Creation timestamp                             |
| updated_at                  | DateTime(TZ) | SERVER_DEFAULT & ON UPDATE      | Last update timestamp                          |

**Special Features**:
- **Automatic Interaction Tracking**: The `before_update` event listener automatically updates `last_interaction_at` when tracked fields change
- **Property Mapping**: `title` attribute maps to `legal_name` column for compatibility
- **Tracked Fields**: Changes to specific fields (status, owner, priority, etc.) trigger interaction timestamp updates
- **Soft Delete for Qualification**: When a lead is qualified, both `qualified_at` and `deleted_at` are set, hiding the lead from `/api/leads/sales-view`

**Relationships**:
- `company`: Many-to-one with `Company`
- `owner`: Many-to-one with `User`
- `lead_status`: Many-to-one with `LeadStatus`
- `lead_origin`: Many-to-one with `LeadOrigin`
- `qualified_master_deal`: Many-to-one with `Deal`
- `activity_stats`: One-to-one with `LeadActivityStats`
- `tags`: Many-to-many with `Tag` through `lead_tags`

**Supabase RPC Functions**:
- `qualify_lead(p_lead_id UUID, p_new_company_data JSONB, p_user_id UUID)`: Qualifies a lead by setting `qualified_at` and `deleted_at`, and creates an audit log entry with action `'qualify_lead'`.

---

### master_deals

**Purpose**: Master deals (opportunities) in the CRM.

**Model**: `Deal`  
**Table Name**: `master_deals`

| Column               | Type   | Constraints              | Description                              |
|----------------------|--------|--------------------------|------------------------------------------|
| id                   | String | PRIMARY KEY              | Deal UUID                                |
| title (→ client_name)| String |                          | Client name (column: client_name)        |
| company_id           | String | FK(companies.id), NULL   | Associated company                       |

**Relationships**:
- `company`: Many-to-one with `Company`

---

### tags

**Purpose**: Tags that can be applied to leads for categorization.

**Model**: `Tag`  
**Table Name**: `tags`

| Column | Type   | Constraints       | Description      |
|--------|--------|-------------------|------------------|
| id     | String | PRIMARY KEY, INDEX| Tag UUID         |
| name   | String | UNIQUE            | Tag name         |
| color  | String | NULLABLE          | Display color    |

**Relationships**:
- `leads`: Many-to-many with `Lead` through `lead_tags`

---

### lead_tags

**Purpose**: Junction table for the many-to-many relationship between leads and tags.

**Model**: `LeadTag`  
**Table Name**: `lead_tags`

| Column  | Type   | Constraints         | Description |
|---------|--------|---------------------|-------------|
| lead_id | String | FK(leads.id), PK    | Lead UUID   |
| tag_id  | String | FK(tags.id), PK     | Tag UUID    |

**Composite Primary Key**: (`lead_id`, `tag_id`)

---

### lead_statuses

**Purpose**: Defines available lead statuses (e.g., "New", "Qualified", "Lost").

**Model**: `LeadStatus`  
**Table Name**: `lead_statuses`

| Column      | Type         | Constraints           | Description                     |
|-------------|--------------|-----------------------|---------------------------------|
| id          | String       | PRIMARY KEY           | Status UUID                     |
| code        | String       | UNIQUE, NOT NULL      | Status code (e.g., "NEW")       |
| label       | String       | NOT NULL              | Display label                   |
| description | Text         | NULLABLE              | Status description              |
| is_active   | Boolean      | DEFAULT True          | Whether status is active        |
| sort_order  | Integer      | DEFAULT 0             | Display order                   |
| created_at  | DateTime(TZ) | SERVER_DEFAULT now()  | Creation timestamp              |

---

### lead_origins

**Purpose**: Defines lead origin/source types (e.g., "Website", "Referral", "Cold Call").

**Model**: `LeadOrigin`  
**Table Name**: `lead_origins`

| Column      | Type         | Constraints           | Description                     |
|-------------|--------------|-----------------------|---------------------------------|
| id          | String       | PRIMARY KEY           | Origin UUID                     |
| code        | String       | UNIQUE, NOT NULL      | Origin code                     |
| label       | String       | NOT NULL              | Display label                   |
| description | Text         | NULLABLE              | Origin description              |
| is_active   | Boolean      | DEFAULT True          | Whether origin is active        |
| sort_order  | Integer      | DEFAULT 0             | Display order                   |
| created_at  | DateTime(TZ) | SERVER_DEFAULT now()  | Creation timestamp              |

---

### lead_activity_stats

**Purpose**: Aggregate statistics for lead engagement and activity.

**Model**: `LeadActivityStats`  
**Table Name**: `lead_activity_stats`

| Column               | Type         | Constraints              | Description                           |
|----------------------|--------------|--------------------------|---------------------------------------|
| lead_id              | String       | FK(leads.id), PK         | Lead UUID (one-to-one)                |
| engagement_score     | Integer      | DEFAULT 0                | Calculated engagement score           |
| last_interaction_at  | DateTime(TZ) | NULLABLE                 | Last interaction timestamp            |
| last_email_at        | DateTime(TZ) | NULLABLE                 | Last email interaction                |
| last_event_at        | DateTime(TZ) | NULLABLE                 | Last calendar event                   |
| total_emails         | Integer      | DEFAULT 0                | Total email count                     |
| total_events         | Integer      | DEFAULT 0                | Total calendar events                 |
| total_interactions   | Integer      | DEFAULT 0                | Total interactions                    |
| created_at           | DateTime(TZ) | SERVER_DEFAULT now()     | Creation timestamp                    |
| updated_at           | DateTime(TZ) | SERVER_DEFAULT & UPDATE  | Last update timestamp                 |

**Relationships**:
- `lead`: One-to-one with `Lead`

**Special Features**: Automatically updated when lead interaction fields change via the `before_update` event listener.

---

## Authorization Tables

### user_roles

**Purpose**: Simplified role-based access control (RBAC) for MVP.

**Model**: `UserRole`  
**Table Name**: `user_roles`

| Column  | Type    | Constraints    | Description                              |
|---------|---------|----------------|------------------------------------------|
| id      | Integer | PRIMARY KEY    | Auto-incrementing unique identifier      |
| user_id | String  | INDEX          | User ID from Supabase Auth               |
| role    | String  |                | Role: "admin", "manager", or "sales"     |

---

## Database Conventions

### Naming Conventions
- **Tables**: Snake_case, plural (e.g., `calendar_events`, `drive_files`)
- **Columns**: Snake_case (e.g., `google_event_id`, `created_at`)
- **Indexes**: Prefix with `idx_` (e.g., `idx_calendar_events_status`)
- **Foreign Keys**: Suffix with `_id` (e.g., `lead_status_id`)

### Timestamp Conventions
- All timestamp columns use `DateTime(timezone=True)` for timezone awareness
- `created_at`: Set once at record creation using `server_default=func.now()`
- `updated_at`: Automatically updated on record modification using `onupdate=func.now()`

### Soft Delete Pattern
- **Deletion Marker**: `deleted_at` (NULL = active, timestamp = deleted)
- **Audit Fields**: `deleted_by` (user ID), `delete_reason` (optional explanation)
- **Queries**: Always filter WHERE `deleted_at IS NULL` for active records
- **Benefits**: Recovery capability, audit trail, no referential integrity issues

### JSON Data Storage
- **PostgreSQL**: Use `JSONB` type for efficient querying
- **SQLite**: Use `Text` type, store JSON as string
- **SQLAlchemy**: Use `Text` type in models for maximum compatibility (application handles JSON serialization)

### Index Strategy
- **Primary Keys**: Always indexed automatically
- **Foreign Keys**: Explicitly indexed for join performance
- **Common Filters**: Index fields frequently used in WHERE clauses (e.g., `status`, `active`)
- **Date Ranges**: Index timestamp columns used in range queries (e.g., `start_time`, `end_time`)
- **Uniqueness**: Use unique indexes to enforce business constraints (e.g., `google_event_id`)

---

## Event Listeners

### Lead Interaction Tracking

**Trigger**: `before_update` on `Lead` model  
**Function**: `update_lead_interaction_on_change()`

**Purpose**: Automatically updates interaction timestamps when meaningful lead fields change.

**Tracked Fields**:
- `owner_user_id`
- `lead_status_id`
- `lead_origin_id`
- `title` (legal_name)
- `trade_name`
- `priority_score`
- `qualified_company_id`
- `qualified_master_deal_id`
- `address_city`
- `address_state`

**Behavior**:
1. Detects changes to tracked fields before the database flush
2. Sets `updated_at` to current UTC timestamp
3. Sets `last_interaction_at` to current UTC timestamp (if not explicitly set)
4. If `activity_stats` relationship exists, also updates `last_interaction_at` on stats record

**Benefits**: Ensures consistent tracking of lead activity without requiring explicit calls in business logic.

---

## Migration Strategy

### Current Approach
- **SQL Scripts**: Manual SQL scripts in `/migrations/` directory
- **Execution**: Run manually against database (PostgreSQL or SQLite)
- **Tracking**: Document execution in migration markdown files

### Migration Files
1. `add_soft_delete_fields.py` - Adds soft delete columns to Drive tables
2. `ensure_templates.py` - Sets up default Drive folder templates
3. `calendar_tables.sql` - Creates Calendar tables (see `docs/CALENDAR_MIGRATIONS.md`)

### Best Practices
1. **Always backup** before running migrations
2. **Test in development** before production
3. **Document** each migration with purpose and rollback instructions
4. **Version control** all migration scripts
5. **Verify** schema after migration with health checks

---

## Performance Considerations

### Calendar Events
- **Read Heavy**: Most operations read from local DB, not Google API
- **Index Strategy**: Index on `status`, `start_time`, `end_time` for common queries
- **Retention**: Archive old events (>6 months) to keep table size manageable
- **Sync Efficiency**: Use `sync_token` for incremental updates (fetches only changes)

### Drive Files
- **Large Tables**: Can grow very large; consider partitioning by date in future
- **Soft Delete**: Periodically archive old deleted records to separate table
- **Indexes**: Ensure `file_id` and `parent_folder_id` are indexed for performance

### Leads
- **Hot Table**: Frequently updated; ensure `updated_at` and `last_interaction_at` are indexed
- **Stats Caching**: `lead_activity_stats` provides pre-calculated aggregates to avoid expensive joins
- **Event Listener**: Automatic tracking adds minimal overhead but ensures consistency

---

## Security Considerations

### Sensitive Data
- **No Credentials**: Never store Google API credentials or tokens in database
- **Email PII**: Consider encryption at rest for email addresses if required by compliance
- **Audit Logs**: Use change logs for security auditing and incident response

### Access Control
- **Row-Level Security**: Consider implementing RLS in PostgreSQL for multi-tenant isolation
- **User Roles**: Simple RBAC implemented via `user_roles` table
- **Soft Delete**: Prevents accidental data loss while maintaining security audit trail

### Webhook Security
- **Channel Tokens**: Validate `X-Goog-Channel-Token` header on webhook receipts
- **HTTPS Only**: All webhook endpoints must use HTTPS in production
- **Rate Limiting**: Implement rate limiting on webhook endpoints to prevent DoS

---

## Future Enhancements

### Planned
- [ ] Add indexes for Calendar tables (status, start_time, end_time)
- [ ] Implement recurring events support (separate table for recurrence rules)
- [ ] Add multi-calendar support (beyond 'primary')
- [ ] Implement table partitioning for large tables (events, change logs)
- [ ] Add database-level encryption for sensitive fields

### Under Consideration
- [ ] Switch to Alembic for automatic migration generation
- [ ] Implement full-text search indexes for event summaries
- [ ] Add materialized views for complex analytics queries
- [ ] Implement event sourcing pattern for critical tables

---

## Related Documentation

- [ACTION_PLAN.md](../../ACTION_PLAN.md) - Strategic roadmap for Calendar integration
- [CALENDAR_MIGRATIONS.md](../CALENDAR_MIGRATIONS.md) - Detailed migration instructions
- [CALENDAR_ENV_VARS.md](../CALENDAR_ENV_VARS.md) - Environment variables for Calendar
- [API Reference](./api_reference.md) - API endpoint documentation (if exists)

---

**Last Updated**: 2025-12-13  
**Schema Version**: 1.1 (Calendar Phase 1)  
**Database ORM**: SQLAlchemy 1.4+  
**Maintainer**: PipeDesk Development Team
