# ACTION PLAN: PipeDesk Google Drive Backend - Expanded Integration Roadmap

This document outlines the comprehensive execution plan for integrating the `pd-google` backend with Google Calendar, Google Meet, and implementing Core CRM features including Audit Logs, Unified Timeline, and Security/RBAC.

## Strategic Priorities (THE "BIG 3")
1. **Auditability:** Every critical change (Lead, Deal) must be traceable via comprehensive Audit Logs
2. **Unified Timeline:** Sales users need a single view merging Emails, Calendar Events, and Audit Logs
3. **Security:** Real RBAC (Role-Based Access Control) validating JWT tokens, not just headers

## Phase Summary
*   **Phase 1: Foundation (Current)** - Calendar Models and Service implementation
*   **Phase 2: CRM Core - Audit & Security (High Priority)** - Audit Logs and RBAC implementation
*   **Phase 3: Unified Timeline (High Priority)** - Aggregation endpoint for unified view
*   **Phase 4: Calendar Sync & Features** - Two-way sync and advanced calendar features
*   **Phase 5: Future/Medium Priority** - SLA Queues, Telemetry, Advanced Automation

---

## Phase Breakdown

### Phase 1: Foundation (COMPLETED ✅)
**Objective:** Establish calendar infrastructure with database models and service implementation.

**Status:** ✅ **COMPLETE**

*   **Completed Tasks:**
    1.  ✅ **SQL Migration:** Tables `calendar_events` and `calendar_sync_states` created in Supabase
    2.  ✅ **Python Models:** `CalendarSyncState` and `CalendarEvent` models added to `models.py` with SQLAlchemy mappings
    3.  ✅ **Google Calendar Service:** Complete implementation in `services/google_calendar_service.py` with:
        *   `create_event()` - Creates events with Meet link generation
        *   `list_events()` - Fetches events with time filtering and sync token support
        *   `get_event()` - Retrieves individual event details
        *   `update_event()` - Updates existing events
        *   `delete_event()` - Cancels/deletes events
        *   `watch_events()` - Registers webhook channels for sync
        *   `stop_channel()` - Stops webhook channels
    4.  ✅ **Calendar Router:** Full CRUD API implementation in `routers/calendar.py` with:
        *   POST `/calendar/events` - Create events with Meet links
        *   GET `/calendar/events` - List events with filters and pagination
        *   GET `/calendar/events/{id}` - Get event details
        *   PATCH `/calendar/events/{id}` - Update events
        *   DELETE `/calendar/events/{id}` - Cancel events (soft delete)
        *   POST `/calendar/watch` - Register webhook channel
    5.  ✅ **Scope Configuration:** Google Calendar scopes properly configured
    6.  ✅ **Meet Link Generation:** Automatic Google Meet link creation with `conferenceData`

*   **Dependencies:** Supabase database access, Google Service Account with Calendar API enabled
*   **Completion Criteria:** All calendar CRUD operations functional with local database persistence
*   **Documentation:** `CALENDAR_API.md`, `CALENDAR_INTEGRATION_STATUS.md`

---

### Phase 2: CRM Core - Audit & Security (HIGH PRIORITY 🔴)
**Objective:** Implement comprehensive audit logging and real RBAC security for enterprise CRM operations.

**Status:** 🔴 **PENDING - HIGH PRIORITY**

*   **Tasks:**
    1.  **Audit Log Models:**
        *   Create `AuditLog` model in `models.py` tracking:
            - Entity type (Lead, Deal, Contact, etc.)
            - Action type (CREATE, UPDATE, DELETE, STATUS_CHANGE)
            - User who made the change
            - Timestamp
            - Before/After values (JSON)
            - IP address and user agent
        *   Create `LeadAuditLog` and `DealAuditLog` specialized tables
    
    2.  **SQLAlchemy Event Hooks:**
        *   Implement `@event.listens_for` hooks on Lead and Deal models
        *   Capture before_update, before_insert, before_delete events
        *   Automatically log all field changes with old and new values
    
    3.  **RBAC Implementation:**
        *   Create `services/rbac_service.py` with JWT validation
        *   Implement FastAPI dependencies for role checking:
            - `require_admin()` - Admin-only endpoints
            - `require_manager()` - Manager and above
            - `require_authenticated()` - Any authenticated user
        *   Add JWT token validation (not just header reading)
        *   Create role hierarchy: Admin > Manager > Sales > Viewer
    
    4.  **Audit Log API:**
        *   Create `routers/audit_logs.py` with endpoints:
            - GET `/audit-logs` - List all audit logs (admin only)
            - GET `/audit-logs/entity/{type}/{id}` - Get logs for specific entity
            - GET `/audit-logs/user/{user_id}` - Get logs by user
        *   Implement filtering by date range, entity type, action type
    
    5.  **Security Middleware:**
        *   Add JWT validation middleware to main.py
        *   Implement rate limiting for API endpoints
        *   Add request logging for security monitoring

*   **Dependencies:** JWT token configuration in Supabase, User management setup
*   **Completion Criteria:** 
    - All Lead/Deal changes automatically logged
    - JWT tokens properly validated
    - Role-based access control functional
    - Audit logs queryable via API
*   **Risks:** Performance impact on high-volume operations (mitigate with async logging)

---

### Phase 3: Unified Timeline (HIGH PRIORITY 🔴)
**Objective:** Provide sales users with a single, chronological view of all customer interactions.

**Status:** 🔴 **PENDING - HIGH PRIORITY**

*   **Tasks:**
    1.  **Timeline Aggregation Service:**
        *   Create `services/timeline_service.py` with methods:
            - `get_unified_timeline(entity_id, entity_type)` - Aggregates all events
            - `get_timeline_by_date_range(start, end)` - Time-filtered view
        *   Merge data from multiple sources:
            - Email threads (from Gmail API)
            - Calendar events (from calendar_events table)
            - Audit logs (from audit_log tables)
            - Status changes and notes
    
    2.  **Timeline API Router:**
        *   Create `routers/timeline.py` with endpoints:
            - GET `/timeline/{entity_type}/{entity_id}` - Get unified timeline
            - GET `/timeline/lead/{lead_id}` - Lead-specific timeline
            - GET `/timeline/deal/{deal_id}` - Deal-specific timeline
        *   Support pagination and filtering
        *   Return normalized timeline entries with:
            - Timestamp
            - Event type (email, calendar, audit, note)
            - Summary/description
            - User who performed action
            - Links to full details
    
    3.  **Timeline Entry Schema:**
        *   Create `schemas/timeline.py` with unified timeline entry model
        *   Ensure consistent structure across all event types
        *   Include metadata for frontend rendering
    
    4.  **Performance Optimization:**
        *   Index database tables for timeline queries
        *   Implement caching for frequently accessed timelines
        *   Use database-level pagination

*   **Dependencies:** Phase 2 (Audit Logs) completed, existing Gmail and Calendar data
*   **Completion Criteria:** 
    - Single API call returns all interactions for an entity
    - Timeline properly ordered by timestamp
    - All event types properly represented
    - Response time under 500ms for typical queries
*   **Risks:** Query performance with large datasets (mitigate with proper indexing)

---

### Phase 4: Calendar Sync & Features (MEDIUM PRIORITY 🟡)
**Objective:** Implement two-way synchronization and advanced calendar features.

**Status:** 🟡 **PARTIALLY COMPLETE - MEDIUM PRIORITY**

*   **Tasks:**
    1.  ✅ **Webhook Infrastructure:** Basic webhook channel registration implemented
    2.  **Webhook Handler Enhancement:**
        *   Enhance `routers/webhooks.py` to handle calendar notifications
        *   Implement sync token-based incremental sync
        *   Handle Google notification types: sync, add, remove, update
    3.  **Sync Logic:**
        *   Retrieve sync_token from database
        *   Call `events().list(syncToken=...)` for delta sync
        *   Update `calendar_events` table (insert/update/soft-delete)
        *   Store new `nextSyncToken`
    4.  **Channel Renewal:**
        *   Create scheduled job to renew webhook channels before expiration
        *   Implement in `services/scheduler_service.py`
    5.  **Conflict Resolution:**
        *   Detect and prevent sync loops
        *   Implement last-write-wins strategy
        *   Log sync conflicts for manual review

*   **Dependencies:** Public webhook URL (Render deployment)
*   **Completion Criteria:** 
    - Changes in Google Calendar reflected in database within seconds
    - No sync loops or duplicate events
    - Automatic channel renewal working
*   **Risks:** Sync loops (mitigate with change detection before write)

---

### Phase 5: Future/Medium Priority (PLANNED 🔵)
**Objective:** Advanced features and automation for enhanced productivity.

**Status:** 🔵 **PLANNED**

*   **Planned Features:**
    1.  **SLA Queue Management:**
        *   Automatic lead assignment based on response time
        *   SLA violation alerts
        *   Queue priority algorithms
    
    2.  **Advanced Telemetry:**
        *   Performance metrics dashboard
        *   User activity analytics
        *   API usage monitoring
    
    3.  **Gmail Attachment Automation:**
        *   Automatic Drive folder creation for email attachments
        *   Smart file organization
        *   Attachment preview in timeline
    
    4.  **Meeting Intelligence:**
        *   Automatic meeting notes from calendar descriptions
        *   Pre-meeting preparation reminders
        *   Post-meeting follow-up tasks
    
    5.  **Advanced Search:**
        *   Full-text search across emails, calendar events, and notes
        *   Search filters by date, user, entity type
        *   Search result highlighting

*   **Dependencies:** Phases 1-4 completed and stable
*   **Prioritization:** Based on user feedback and business value

---

## API Contracts

### Calendar API Endpoints (Phase 1 - IMPLEMENTED ✅)

#### 1. Create Event (with Meet)
*   **Endpoint:** `POST /calendar/events`
*   **Status:** ✅ Implemented
*   **Request Body:**
    ```json
    {
      "summary": "Demo Product",
      "description": "Product presentation for client...",
      "start_time": "2023-10-27T10:00:00-03:00",
      "end_time": "2023-10-27T11:00:00-03:00",
      "attendees": ["client@email.com"],
      "create_meet_link": true
    }
    ```
*   **Response:** JSON with `id`, `google_event_id`, `meet_link`, `status`

#### 2. List Events
*   **Endpoint:** `GET /calendar/events`
*   **Status:** ✅ Implemented (reads from local DB)
*   **Query Params:** `time_min`, `time_max`, `status`, `limit`, `offset`
*   **Response:** Array of events from local database

#### 3. Update Event
*   **Endpoint:** `PATCH /calendar/events/{id}`
*   **Status:** ✅ Implemented
*   **Request Body:** Partial fields (`start_time`, `summary`, etc.)

#### 4. Cancel Event
*   **Endpoint:** `DELETE /calendar/events/{id}`
*   **Status:** ✅ Implemented
*   **Behavior:** Soft delete (status set to `cancelled`)

### Audit Log API Endpoints (Phase 2 - PLANNED 🔴)

#### 1. List All Audit Logs (Admin Only)
*   **Endpoint:** `GET /audit-logs`
*   **Status:** 🔴 Not Implemented
*   **Query Params:** `entity_type`, `action_type`, `user_id`, `start_date`, `end_date`, `limit`, `offset`
*   **Response:** Paginated list of audit log entries

#### 2. Get Entity Audit History
*   **Endpoint:** `GET /audit-logs/entity/{entity_type}/{entity_id}`
*   **Status:** 🔴 Not Implemented
*   **Response:** All audit logs for specific entity (Lead, Deal, etc.)

#### 3. Get User Activity
*   **Endpoint:** `GET /audit-logs/user/{user_id}`
*   **Status:** 🔴 Not Implemented
*   **Response:** All actions performed by specific user

### Unified Timeline API (Phase 3 - PLANNED 🔴)

#### 1. Get Unified Timeline
*   **Endpoint:** `GET /timeline/{entity_type}/{entity_id}`
*   **Status:** 🔴 Not Implemented
*   **Response:** Chronologically ordered timeline entries from all sources
    ```json
    {
      "items": [
        {
          "timestamp": "2024-01-15T14:00:00Z",
          "event_type": "calendar",
          "summary": "Sales Meeting",
          "details": {...},
          "user": {...}
        },
        {
          "timestamp": "2024-01-14T10:30:00Z",
          "event_type": "email",
          "summary": "Re: Product inquiry",
          "details": {...},
          "user": {...}
        },
        {
          "timestamp": "2024-01-13T16:45:00Z",
          "event_type": "audit",
          "summary": "Status changed: New → Qualified",
          "details": {...},
          "user": {...}
        }
      ],
      "pagination": {...}
    }
    ```

---

## Authentication & Authorization Strategy

### Service Account Model (Phase 1 - IMPLEMENTED ✅)
The system uses a **Google Service Account** as the "organizer" for all calendar events.

1.  **No OAuth Required:** Users don't need to authenticate with Google
2.  **Automatic Invitations:** Users and clients are invited to events via email
3.  **Flow:**
    *   Backend authenticates with `GOOGLE_SERVICE_ACCOUNT_JSON`
    *   Backend creates events in Service Account's primary calendar
    *   Backend adds attendees to event
    *   Google sends invitation emails with Meet links
4.  **Security:**
    *   Service Account JSON never leaves the server
    *   No user tokens stored
    *   Backend acts as central authority

### RBAC Implementation (Phase 2 - PLANNED 🔴)

#### Role Hierarchy
1.  **Admin** - Full system access, audit log access, user management
2.  **Manager** - Lead/Deal management, team oversight, reporting
3.  **Sales** - Own leads/deals, calendar, email
4.  **Viewer** - Read-only access

#### JWT Validation
*   **Current:** Header-based role checking (`x-user-role`)
*   **Target:** JWT token validation with Supabase
*   **Implementation:** FastAPI dependencies for each role level

---

## Security & Logging Guidelines

### Logging Best Practices (IMPLEMENTED ✅)
*   ✅ Log `event_id`, `calendar_id`, HTTP status codes
*   ✅ Structured logging with `utils/structured_logging.py`
*   ✅ No PII in application logs (emails, names redacted where possible)
*   ✅ Error tracking with context

### Security Measures

#### Current (Phase 1) ✅
*   ✅ Service Account credentials secured in environment variables
*   ✅ Input validation on API endpoints
*   ✅ Soft delete for events (no hard deletes)
*   ✅ CORS configuration in main.py

#### Planned (Phase 2) 🔴
*   🔴 JWT token validation
*   🔴 Role-based endpoint protection
*   🔴 Rate limiting per user/IP
*   🔴 Webhook signature verification
*   🔴 Request audit trail
*   🔴 SQL injection prevention (parameterized queries)

---

## Dependencies & Infrastructure

### Required Services
*   **Database:** PostgreSQL (Supabase)
*   **Google APIs:** Calendar API, Gmail API, Drive API
*   **Authentication:** Supabase Auth (JWT)
*   **Deployment:** Render.com (or similar with public webhook URL)

### Environment Variables
*   `GOOGLE_SERVICE_ACCOUNT_JSON` - Service account credentials
*   `DATABASE_URL` - PostgreSQL connection string
*   `SUPABASE_URL` - Supabase project URL
*   `SUPABASE_KEY` - Supabase API key
*   `WEBHOOK_BASE_URL` - Public webhook URL for Google notifications
*   `WEBHOOK_SECRET` - Secret token for webhook validation
*   `JWT_SECRET` - Secret for JWT token validation (Phase 2)

### Python Dependencies
*   `fastapi` - Web framework
*   `sqlalchemy` - ORM
*   `google-api-python-client` - Google APIs
*   `google-auth` - Google authentication
*   `pydantic` - Data validation
*   `psycopg2` - PostgreSQL driver

---

## Migration & Deployment Notes

### Database Migrations
*   **Phase 1:** Calendar tables created (✅ Complete)
*   **Phase 2:** Audit log tables required
*   **Phase 3:** Timeline indexes required

### Backward Compatibility
*   Existing endpoints preserved during Phase 2-5 implementation
*   New RBAC layer will be additive (won't break existing clients initially)
*   Deprecation warnings before removing header-based auth

### Rollout Strategy
1.  **Phase 1:** Already deployed and functional
2.  **Phase 2:** Deploy audit logging first, then RBAC (can be feature-flagged)
3.  **Phase 3:** Timeline API as new endpoint (no breaking changes)
4.  **Phase 4:** Enhanced sync (transparent to frontend)
5.  **Phase 5:** Feature-by-feature rollout

---

## Testing Strategy

### Phase 1 (IMPLEMENTED ✅)
*   ✅ Unit tests for calendar service methods
*   ✅ Integration tests for calendar endpoints
*   ✅ Sync state management tests
*   Located in: `tests/test_calendar.py`, `tests/test_calendar_sync.py`

### Phase 2 (PLANNED 🔴)
*   Unit tests for audit log hooks
*   Integration tests for RBAC dependencies
*   JWT validation tests
*   Role permission matrix tests

### Phase 3 (PLANNED 🔴)
*   Timeline aggregation tests
*   Performance tests for large datasets
*   Pagination tests

### Phase 4 (PLANNED 🔴)
*   Webhook handling tests
*   Sync loop prevention tests
*   Channel renewal tests

---

## Documentation Updates Required

### Completed (Phase 1) ✅
*   ✅ `CALENDAR_API.md` - Complete calendar API documentation
*   ✅ `CALENDAR_INTEGRATION_STATUS.md` - Implementation status
*   ✅ `docs/backend/database_schema.md` - Database schema documentation
*   ✅ `docs/CALENDAR_MIGRATIONS.md` - Migration scripts

### Pending (Phase 2-5) 🔴
*   🔴 `docs/AUDIT_LOG_API.md` - Audit log API documentation
*   🔴 `docs/RBAC_GUIDE.md` - RBAC implementation guide
*   🔴 `docs/TIMELINE_API.md` - Unified timeline API
*   🔴 `docs/ARCHITECTURE_EVOLUTION.md` - Strategic pivot explanation
*   🔴 Update `README.md` with new features

---

## Risk Management

### Technical Risks
1.  **Performance Impact (Phase 2):**
    - Risk: Audit logging may slow down write operations
    - Mitigation: Async logging, database indexing, batch writes
2.  **Sync Loops (Phase 4):**
    - Risk: Bidirectional sync may create infinite loops
    - Mitigation: Change detection, timestamp comparison, sync flags
3.  **JWT Migration (Phase 2):**
    - Risk: Breaking existing clients during RBAC rollout
    - Mitigation: Parallel authentication support, gradual migration, feature flags

### Business Risks
1.  **Scope Creep:**
    - Risk: Additional features delaying high-priority items
    - Mitigation: Strict phase prioritization, "must-have" vs "nice-to-have" classification
2.  **User Adoption:**
    - Risk: Users not utilizing new audit/timeline features
    - Mitigation: User training, UI/UX optimization, clear value demonstration

---

## Next Immediate Actions

### For Phase 2 (Audit & Security) - START HERE 🔴
1.  Create `AuditLog` model in `models.py`
2.  Implement SQLAlchemy event listeners for Lead/Deal models
3.  Create `services/rbac_service.py` with JWT validation
4.  Add RBAC dependencies to existing endpoints
5.  Create `routers/audit_logs.py` with admin-only endpoints
6.  Write tests for audit logging and RBAC
7.  Update documentation

### For Phase 3 (Unified Timeline) - AFTER PHASE 2 🔴
1.  Create `services/timeline_service.py` with aggregation logic
2.  Create `routers/timeline.py` with timeline endpoints
3.  Create `schemas/timeline.py` for response models
4.  Implement database indexes for performance
5.  Add caching layer for frequently accessed timelines
6.  Write tests for timeline aggregation
7.  Create `docs/TIMELINE_API.md`

---

## Conclusion

This action plan represents a strategic evolution from a calendar-focused integration to a comprehensive CRM platform with enterprise-grade features. The phases are prioritized to deliver maximum business value:

- **Phase 1** provides the foundation with working calendar integration ✅
- **Phase 2** adds critical auditability and security 🔴
- **Phase 3** enhances UX with unified timeline view 🔴
- **Phase 4** completes calendar sync for real-time updates 🟡
- **Phase 5** adds advanced features based on user feedback 🔵

The plan maintains backward compatibility while enabling gradual rollout of new capabilities.
