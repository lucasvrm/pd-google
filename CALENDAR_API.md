# Calendar & Google Meet API Documentation

**Version:** 1.1  
**Last Updated:** 2024-12-13  
**Base URL:** `/api/calendar`

---

## Overview

This API provides complete integration with Google Calendar and Google Meet for the frontend application. It enables creating, reading, updating, and deleting calendar events with automatic Meet link generation and comprehensive attendee management.

### Key Features

- ✅ **Create events** with automatic Google Meet link generation
- ✅ **List events** with filtering, pagination, and status management
- ✅ **Retrieve individual events** with complete details
- ✅ **Update events** including attendees and scheduling
- ✅ **Cancel events** with soft delete (status-based)
- ✅ **Automatic synchronization** with Google Calendar via webhooks
- ✅ **Local database mirror** for fast queries and offline access

### Authentication

All endpoints require appropriate authentication credentials. The backend uses a Google Service Account to manage calendar operations on behalf of users.

---

## Data Models

### Attendee

Represents a participant in a calendar event.

```json
{
  "email": "attendee@example.com",
  "responseStatus": "accepted",
  "displayName": "John Doe",
  "organizer": false,
  "self": false,
  "optional": false
}
```

**Fields:**
- `email` (string, required): Email address of the attendee
- `responseStatus` (string, optional): Response status - `needsAction`, `declined`, `tentative`, `accepted`
- `displayName` (string, optional): Display name of the attendee
- `organizer` (boolean, optional): Whether this attendee is the organizer
- `self` (boolean, optional): Whether this attendee is the current user
- `optional` (boolean, optional): Whether attendance is optional

### EventResponse

Standard response format for all calendar events.

```json
{
  "id": 1,
  "google_event_id": "evt_abc123xyz",
  "summary": "Sales Meeting - Client X",
  "description": "Quarterly review and proposal presentation",
  "start_time": "2024-01-15T14:00:00+00:00",
  "end_time": "2024-01-15T15:00:00+00:00",
  "meet_link": "https://meet.google.com/abc-defg-hij",
  "html_link": "https://calendar.google.com/event?eid=abc123",
  "status": "confirmed",
  "organizer_email": "organizer@company.com",
  "attendees": [
    {
      "email": "attendee@example.com",
      "responseStatus": "accepted",
      "displayName": "John Doe"
    }
  ]
}
```

**Fields:**
- `id` (integer): Internal database ID
- `google_event_id` (string): Google Calendar event ID
- `summary` (string): Event title/subject
- `description` (string, nullable): Event details/notes
- `start_time` (datetime): Event start time with timezone
- `end_time` (datetime): Event end time with timezone
- `meet_link` (string, nullable): **Google Meet video conference link** (when available)
- `html_link` (string, nullable): Link to view event in Google Calendar
- `status` (string, nullable): Event status - `confirmed`, `tentative`, `cancelled`
- `organizer_email` (string, nullable): Email of the event organizer
- `attendees` (array): List of attendee objects

---

## Architecture

### Service Layer

The calendar functionality is implemented through the `GoogleCalendarService` class, which handles all interactions with the Google Calendar API. This service is located in `services/google_calendar_service.py`.

#### GoogleCalendarService Methods

##### `__init__(db: Session)`
Initializes the service with database session and Google Service Account authentication.

**Parameters:**
- `db` (Session): SQLAlchemy database session for persistence operations

**Scopes:** `https://www.googleapis.com/auth/calendar`
**Authentication:** Uses `GoogleAuthService` with service account credentials
**Returns:** Service instance ready for API calls with database access

**Example:**
```python
from database import SessionLocal

db = SessionLocal()
service = GoogleCalendarService(db)
```

##### `create_event(event_data: Dict, calendar_id: str = 'primary') -> Dict`
Creates a new event in the specified calendar.

**Parameters:**
- `event_data` (dict): Event data following Google Calendar API format
  - `summary` (string): Event title
  - `description` (string, optional): Event details
  - `start` (dict): Start time with `dateTime` and `timeZone`
  - `end` (dict): End time with `dateTime` and `timeZone`
  - `attendees` (list, optional): List of attendee objects with `email`
  - `conferenceData` (dict, optional): Conference data for Meet link generation
- `calendar_id` (string): Target calendar ID (default: 'primary')

**Returns:** Dictionary containing the created event data from Google Calendar API, including:
- `id`: Google event ID
- `hangoutLink`: Google Meet link (if requested)
- `htmlLink`: Calendar view link
- `status`: Event status

**Features:**
- Automatic Google Meet link generation with `conferenceDataVersion=1`
- Retry logic with exponential backoff
- Error handling for API failures

**Example:**
```python
event_data = {
    'summary': 'Team Meeting',
    'description': 'Weekly sync',
    'start': {'dateTime': '2024-01-15T10:00:00Z', 'timeZone': 'UTC'},
    'end': {'dateTime': '2024-01-15T11:00:00Z', 'timeZone': 'UTC'},
    'attendees': [{'email': 'user@example.com'}],
    'conferenceData': {
        'createRequest': {
            'requestId': 'req-123',
            'conferenceSolutionKey': {'type': 'hangoutsMeet'}
        }
    }
}
result = service.create_event(event_data)
```

##### `list_events(calendar_id: str = 'primary', time_min: Optional[str] = None, time_max: Optional[str] = None, sync_token: Optional[str] = None) -> Dict`
Lists events from the calendar with optional filtering and sync support.

**Parameters:**
- `calendar_id` (string): Calendar ID to query (default: 'primary')
- `time_min` (string, optional): Start time filter (ISO 8601 format)
- `time_max` (string, optional): End time filter (ISO 8601 format)
- `sync_token` (string, optional): Token for incremental sync

**Returns:** Dictionary containing:
- `items`: List of event objects
- `nextSyncToken`: Token for next incremental sync
- `nextPageToken`: Token for pagination

**Features:**
- Incremental sync support using sync tokens
- Single event expansion for recurring events
- Time-based filtering
- Ordered by start time

**Example:**
```python
# List events in time range
events = service.list_events(
    time_min='2024-01-01T00:00:00Z',
    time_max='2024-01-31T23:59:59Z'
)

# Incremental sync
events = service.list_events(sync_token='prev_token_here')
```

##### `get_event(event_id: str, calendar_id: str = 'primary') -> Dict`
Retrieves a single event by ID.

**Parameters:**
- `event_id` (string): Google Calendar event ID
- `calendar_id` (string): Calendar ID (default: 'primary')

**Returns:** Dictionary containing complete event data

**Example:**
```python
event = service.get_event('event_id_123')
```

##### `update_event(event_id: str, event_data: Dict, calendar_id: str = 'primary') -> Dict`
Updates an existing event using PATCH semantics (partial update).

**Parameters:**
- `event_id` (string): Google Calendar event ID
- `event_data` (dict): Fields to update (only provided fields are modified)
- `calendar_id` (string): Calendar ID (default: 'primary')

**Returns:** Dictionary containing the updated event data

**Features:**
- Partial updates (PATCH semantics)
- Retry logic with exponential backoff
- Preserves unmodified fields

**Example:**
```python
updates = {
    'summary': 'Updated Meeting Title',
    'start': {'dateTime': '2024-01-15T15:00:00Z', 'timeZone': 'UTC'}
}
result = service.update_event('event_id_123', updates)
```

##### `delete_event(event_id: str, calendar_id: str = 'primary')`
Deletes (cancels) an event from the calendar.

**Parameters:**
- `event_id` (string): Google Calendar event ID
- `calendar_id` (string): Calendar ID (default: 'primary')

**Returns:** Empty response on success

**Features:**
- Sends cancellation notifications to attendees
- Retry logic for transient failures
- Handles already-deleted events gracefully

**Example:**
```python
service.delete_event('event_id_123')
```

##### `watch_events(channel_id: str, webhook_url: str, calendar_id: str = 'primary', token: Optional[str] = None, expiration: Optional[int] = None) -> Dict`
Registers a webhook channel for calendar change notifications.

**Parameters:**
- `channel_id` (string): Unique identifier for the channel (UUID recommended)
- `webhook_url` (string): Public HTTPS URL to receive notifications
- `calendar_id` (string): Calendar to watch (default: 'primary')
- `token` (string, optional): Secret token for webhook validation
- `expiration` (int, optional): Channel expiration time in milliseconds

**Returns:** Dictionary containing:
- `id`: Channel ID
- `resourceId`: Google-assigned resource ID
- `expiration`: Channel expiration timestamp
- `kind`: Resource type

**Features:**
- Enables real-time sync via webhooks
- Automatic sync token management
- Secure webhook validation

**Example:**
```python
import uuid
channel_id = str(uuid.uuid4())
result = service.watch_events(
    channel_id=channel_id,
    webhook_url='https://api.example.com/webhooks/calendar',
    token='secret_token_123',
    expiration=int((datetime.now().timestamp() + 7*24*3600) * 1000)
)
```

##### `stop_channel(channel_id: str, resource_id: str)`
Stops an active webhook channel.

**Parameters:**
- `channel_id` (string): Channel ID from watch registration
- `resource_id` (string): Google resource ID from watch response

**Returns:** Empty response on success

**Example:**
```python
service.stop_channel('channel_uuid', 'resource_id_from_google')
```

### Error Handling

All service methods include:
- **Exponential Backoff Retry:** 3 retries with increasing delay for transient failures
- **Exception Handling:** Graceful handling of Google API errors
- **Authentication Checks:** Validates service account configuration before API calls

Common error scenarios:
- `404 Not Found`: Event doesn't exist or was deleted
- `410 Gone`: Sync token expired (requires full sync)
- `403 Forbidden`: Insufficient permissions
- `500 Internal Server Error`: Google API temporary failure (retries automatically)

---

## API Endpoints

### 1. Create Calendar Event

Creates a new event in Google Calendar with optional Google Meet link generation.
Supports quick actions with flexible field naming.

**Endpoint:** `POST /api/calendar/events`

**Request Body:**

```json
{
  "summary": "Sales Meeting - Client X",
  "description": "Quarterly review and proposal presentation",
  "start_time": "2024-01-15T14:00:00Z",
  "end_time": "2024-01-15T15:00:00Z",
  "attendees": ["sales@company.com", "client@example.com"],
  "create_meet_link": true,
  "calendar_id": "primary"
}
```

**Request Fields:**
- `summary` (string, optional): Event title/subject. If not provided, defaults to "Untitled Event"
- `title` (string, optional): Alias for `summary` - the UI can send either field
- `description` (string, optional): Event details/notes
- `start_time` (datetime, required): Event start time in ISO 8601 format
- `end_time` (datetime, required): Event end time in ISO 8601 format
- `attendees` (array of strings, optional): List of attendee email addresses
- `create_meet_link` (boolean, optional, default: `true`): Whether to generate a Google Meet link
- `calendar_id` (string, optional, default: `"primary"`): Calendar ID to create the event in

**Quick Action Example (minimal payload):**

```json
{
  "title": "Quick Meeting",
  "start_time": "2024-01-15T14:00:00Z",
  "end_time": "2024-01-15T15:00:00Z"
}
```

**Response:** `201 Created`

```json
{
  "id": 1,
  "google_event_id": "evt_abc123xyz",
  "summary": "Sales Meeting - Client X",
  "description": "Quarterly review and proposal presentation",
  "start_time": "2024-01-15T14:00:00+00:00",
  "end_time": "2024-01-15T15:00:00+00:00",
  "meet_link": "https://meet.google.com/abc-defg-hij",
  "html_link": "https://calendar.google.com/event?eid=abc123",
  "status": "confirmed",
  "organizer_email": "organizer@company.com",
  "attendees": [
    {
      "email": "sales@company.com",
      "responseStatus": "needsAction"
    },
    {
      "email": "client@example.com",
      "responseStatus": "needsAction"
    }
  ]
}
```

**How to Get the Meet Link:**
The `meet_link` field in the response contains the Google Meet video conference URL. This link is automatically generated when `create_meet_link` is `true` (default). Store this URL to display to users or create calendar invitations.

**Error Responses:**
- `500 Internal Server Error`: Google Calendar API error

---

### 2. List Calendar Events

Retrieves calendar events from the local database mirror with filtering and pagination.
Supports quick actions context with entity type and ID parameters.

**Endpoint:** `GET /api/calendar/events`

**Query Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `timeMin` | datetime | No | -30 days* | Filter events starting after this datetime (ISO 8601). *Defaults to 30 days ago when using entity context |
| `timeMax` | datetime | No | +90 days* | Filter events ending before this datetime (ISO 8601). *Defaults to 90 days from now when using entity context |
| `entityType` | string | No | - | Entity type for quick actions context (`company`, `lead`, `deal`, `contact`) |
| `entityId` | string | No | - | Entity ID for quick actions context |
| `calendarId` | string | No | `primary` | Calendar ID to query |
| `status` | string | No | - | Filter by event status (`confirmed`, `tentative`, `cancelled`) |
| `limit` | integer | No | 100 | Maximum number of results (max: 500) |
| `offset` | integer | No | 0 | Number of results to skip for pagination |

**Example Requests:**

```bash
# Get all upcoming events
GET /api/calendar/events

# Quick action: Get events for a lead (with safe time defaults)
GET /api/calendar/events?entityType=lead&entityId=lead-123

# Quick action: Get events for a deal with custom calendar
GET /api/calendar/events?entityType=deal&entityId=deal-456&calendarId=primary

# Get events in January 2024
GET /api/calendar/events?timeMin=2024-01-01T00:00:00Z&timeMax=2024-02-01T00:00:00Z

# Get cancelled events
GET /api/calendar/events?status=cancelled

# Pagination: Get events 20-40
GET /api/calendar/events?limit=20&offset=20
```

**Response:** `200 OK`

```json
[
  {
    "id": 1,
    "google_event_id": "evt_abc123xyz",
    "summary": "Sales Meeting - Client X",
    "start_time": "2024-01-15T14:00:00+00:00",
    "end_time": "2024-01-15T15:00:00+00:00",
    "meet_link": "https://meet.google.com/abc-defg-hij",
    "html_link": "https://calendar.google.com/event?eid=abc123",
    "status": "confirmed",
    "organizer_email": "organizer@company.com",
    "attendees": [...]
  },
  {
    "id": 2,
    "google_event_id": "evt_def456uvw",
    "summary": "Team Standup",
    "start_time": "2024-01-16T09:00:00+00:00",
    "end_time": "2024-01-16T09:30:00+00:00",
    "meet_link": "https://meet.google.com/def-ghij-klm",
    "status": "confirmed",
    "attendees": [...]
  }
]
```

**Notes:**
- By default, cancelled events are excluded from results unless explicitly requested via `status=cancelled`
- Events are ordered by start time (earliest first)
- The local database is synchronized from Google Calendar via webhooks
- When `entityType` and `entityId` are provided, safe time defaults are applied (last 30 days to +90 days)
- The `calendarId` parameter defaults to "primary" when not specified

---

### 3. Get Event Details

Retrieves complete details of a specific calendar event by ID.

**Endpoint:** `GET /api/calendar/events/{event_id}`

**Path Parameters:**
- `event_id` (string, required): Internal database ID or Google event ID

**Example Requests:**

```bash
# Get by internal ID
GET /api/calendar/events/1

# Get by Google event ID
GET /api/calendar/events/evt_abc123xyz
```

**Response:** `200 OK`

```json
{
  "id": 1,
  "google_event_id": "evt_abc123xyz",
  "summary": "Sales Meeting - Client X",
  "description": "Quarterly review and proposal presentation",
  "start_time": "2024-01-15T14:00:00+00:00",
  "end_time": "2024-01-15T15:00:00+00:00",
  "meet_link": "https://meet.google.com/abc-defg-hij",
  "html_link": "https://calendar.google.com/event?eid=abc123",
  "status": "confirmed",
  "organizer_email": "organizer@company.com",
  "attendees": [
    {
      "email": "sales@company.com",
      "responseStatus": "accepted",
      "displayName": "Sales Team"
    },
    {
      "email": "client@example.com",
      "responseStatus": "tentative",
      "displayName": "Client Contact"
    }
  ]
}
```

**Meet Link Location:**
The `meet_link` field contains the Google Meet video conference URL. This field will be `null` if no Meet link was generated during event creation.

**Error Responses:**
- `404 Not Found`: Event not found

**Notes:**
- This endpoint returns complete event details including all attendees
- Cancelled events can still be retrieved via this endpoint
- Use this endpoint to get the most up-to-date event information

---

### 4. Update Calendar Event

Updates an existing calendar event. All fields are optional - only provided fields will be updated.

**Endpoint:** `PATCH /api/calendar/events/{event_id}`

**Path Parameters:**
- `event_id` (string, required): Internal database ID or Google event ID

**Request Body:**

```json
{
  "summary": "Updated Meeting Title",
  "description": "Updated description",
  "start_time": "2024-01-15T15:00:00Z",
  "end_time": "2024-01-15T16:00:00Z",
  "attendees": ["sales@company.com", "client@example.com", "manager@company.com"]
}
```

**Request Fields (all optional):**
- `summary` (string): New event title
- `description` (string): New event description
- `start_time` (datetime): New start time
- `end_time` (datetime): New end time
- `attendees` (array of strings): New list of attendee emails (replaces existing)

**Example Requests:**

```bash
# Update only the title
PATCH /api/calendar/events/1
{
  "summary": "New Title"
}

# Update time and attendees
PATCH /api/calendar/events/evt_abc123xyz
{
  "start_time": "2024-01-15T16:00:00Z",
  "end_time": "2024-01-15T17:00:00Z",
  "attendees": ["new@example.com"]
}
```

**Response:** `200 OK`

Returns the complete updated event with `EventResponse` format (same as GET endpoint).

**Error Responses:**
- `400 Bad Request`: No fields provided for update
- `404 Not Found`: Event not found
- `500 Internal Server Error`: Google Calendar API error

**Notes:**
- Changes are synchronized to Google Calendar immediately
- Only provided fields are updated; others remain unchanged
- When updating attendees, the entire list is replaced (not merged)
- The `meet_link` cannot be added or removed after creation

---

### 5. Cancel Calendar Event

Cancels a calendar event (soft delete). The event is marked as cancelled but not permanently deleted.

**Endpoint:** `DELETE /api/calendar/events/{event_id}`

**Path Parameters:**
- `event_id` (string, required): Internal database ID or Google event ID

**Example Requests:**

```bash
# Cancel by internal ID
DELETE /api/calendar/events/1

# Cancel by Google event ID
DELETE /api/calendar/events/evt_abc123xyz
```

**Response:** `200 OK`

Returns the cancelled event with `status: "cancelled"`:

```json
{
  "id": 1,
  "google_event_id": "evt_abc123xyz",
  "summary": "Sales Meeting - Client X",
  "description": "Quarterly review and proposal presentation",
  "start_time": "2024-01-15T14:00:00+00:00",
  "end_time": "2024-01-15T15:00:00+00:00",
  "meet_link": "https://meet.google.com/abc-defg-hij",
  "html_link": "https://calendar.google.com/event?eid=abc123",
  "status": "cancelled",
  "organizer_email": "organizer@company.com",
  "attendees": [...]
}
```

**Error Responses:**
- `404 Not Found`: Event not found

**Notes:**
- This performs a soft delete - the event remains in the database with `status='cancelled'`
- Cancelled events are excluded from default list queries
- The event is also cancelled in Google Calendar
- Attendees will be notified of the cancellation by Google
- The Meet link remains in the response but may no longer be accessible

---

## Common Use Cases

### Creating a Meeting with Google Meet

```javascript
// Frontend example
const response = await fetch('/api/calendar/events', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    summary: 'Client Presentation',
    description: 'Q4 results presentation',
    start_time: '2024-01-20T14:00:00Z',
    end_time: '2024-01-20T15:00:00Z',
    attendees: ['client@example.com', 'sales@company.com'],
    create_meet_link: true
  })
});

const event = await response.json();
console.log('Meet Link:', event.meet_link);
// Output: https://meet.google.com/abc-defg-hij
```

### Displaying Meet Link to Users

The `meet_link` field is the primary way to access the Google Meet video conference:

```javascript
// Get event details
const event = await fetch('/api/calendar/events/1').then(r => r.json());

// Display to user
if (event.meet_link) {
  showButton('Join Meeting', event.meet_link);
} else {
  showMessage('No video conference available');
}

// Also available:
// event.html_link - Opens event in Google Calendar
```

### Listing Today's Meetings

```javascript
const today = new Date();
const tomorrow = new Date(today);
tomorrow.setDate(tomorrow.getDate() + 1);

const response = await fetch(
  `/api/calendar/events?time_min=${today.toISOString()}&time_max=${tomorrow.toISOString()}`
);
const events = await response.json();

// Display events with Meet links
events.forEach(event => {
  console.log(`${event.summary}: ${event.meet_link || 'No Meet link'}`);
});
```

### Pagination Example

```javascript
// Load events in pages of 20
const page = 0;
const pageSize = 20;
const offset = page * pageSize;

const response = await fetch(
  `/api/calendar/events?limit=${pageSize}&offset=${offset}`
);
const events = await response.json();

// Next page
const nextOffset = (page + 1) * pageSize;
```

### Updating Attendees

```javascript
// Add a new attendee to existing event
const event = await fetch('/api/calendar/events/1').then(r => r.json());

// Update with new attendee list
await fetch('/api/calendar/events/1', {
  method: 'PATCH',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    attendees: [
      ...event.attendees.map(a => a.email),
      'newperson@example.com'
    ]
  })
});
```

---

## Error Handling

All endpoints follow standard HTTP status codes:

| Status Code | Meaning | Common Causes |
|-------------|---------|---------------|
| 200 OK | Success | Request processed successfully |
| 201 Created | Created | Event created successfully |
| 400 Bad Request | Invalid input | Missing required fields, invalid datetime format |
| 404 Not Found | Not found | Event ID doesn't exist |
| 500 Internal Server Error | Server error | Google Calendar API error, database error |

**Error Response Format:**

```json
{
  "detail": "Event not found"
}
```

---

## Data Synchronization

### How Synchronization Works

1. **Event Creation**: Events are created in Google Calendar first, then saved to local database
2. **Webhook Updates**: Google sends notifications when events change
3. **Local Mirror**: The local database provides fast access to event data
4. **Automatic Sync**: Changes in Google Calendar are automatically reflected in the local database

### Sync Timing

- **Create/Update/Delete**: Immediate synchronization with Google Calendar
- **External Changes**: Synchronized within seconds via webhooks
- **List Queries**: Read from local database (no API calls to Google)

### Important Notes

- The local database is the source of truth for listing events
- Individual event details are always current (stored in DB)
- Webhooks keep the local mirror up-to-date automatically
- No manual sync required from the frontend

---

## Best Practices

### 1. Use Internal IDs for References

Always use the `id` field (internal database ID) for storing references in your application, not the `google_event_id`.

### 2. Handle Null Meet Links

Not all events will have a `meet_link`. Always check if it exists before displaying:

```javascript
if (event.meet_link) {
  // Display meet link
} else {
  // Event doesn't have a video conference
}
```

### 3. Timezone Handling

All datetime values are returned in UTC with timezone offset (e.g., `2024-01-15T14:00:00+00:00`). Convert to user's local timezone in the frontend:

```javascript
const localTime = new Date(event.start_time).toLocaleString();
```

### 4. Pagination for Large Lists

Always use pagination when displaying event lists to avoid performance issues:

```javascript
// Good: Paginated
GET /api/calendar/events?limit=50&offset=0

// Avoid: Loading all events
GET /api/calendar/events
```

### 5. Filter by Status

Remember that cancelled events are hidden by default. To show them:

```javascript
// Show only cancelled events
GET /api/calendar/events?status=cancelled

// Show all events (including cancelled)
// Make two requests and combine results
```

### 6. Update Only Changed Fields

When updating events, only send fields that actually changed:

```javascript
// Good: Only update title
PATCH /api/calendar/events/1
{ "summary": "New Title" }

// Avoid: Sending all fields every time
PATCH /api/calendar/events/1
{ 
  "summary": "Same",
  "description": "Same",
  "start_time": "Same",
  ...
}
```

---

## Support & Contact

For API issues or questions:
- Review the OpenAPI/Swagger documentation at `/docs`
- Check application logs for detailed error messages
- Contact the backend development team

---

**Document Version:** 1.0  
**Last Updated:** December 8, 2024  
**Maintained by:** Backend Development Team
