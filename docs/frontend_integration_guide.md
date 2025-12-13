# Frontend Integration Guide

This guide provides everything the Frontend team needs to integrate with the PipeDesk Google Backend API. It covers the Timeline API, Calendar API, and explains our real-time synchronization approach.

## Table of Contents

- [Timeline API](#timeline-api)
- [Calendar API](#calendar-api)
- [Real-time Synchronization](#real-time-synchronization)
- [Authentication](#authentication)
- [Error Handling](#error-handling)

---

## Timeline API

The Timeline API provides a unified, chronological view of all activities related to a CRM entity (Lead, Deal, or Contact). It aggregates data from multiple sources into a single endpoint.

### Endpoint

```
GET /api/timeline/{entity_type}/{entity_id}
```

### Path Parameters

| Parameter     | Type   | Description                              |
|---------------|--------|------------------------------------------|
| `entity_type` | string | Type of entity: `lead`, `deal`, `contact` |
| `entity_id`   | string | UUID of the entity                       |

### Query Parameters

| Parameter | Type    | Default | Description                                    |
|-----------|---------|---------|------------------------------------------------|
| `limit`   | integer | 50      | Maximum items to return (1-200)                |
| `offset`  | integer | 0       | Number of items to skip for pagination         |

### Response Structure

```typescript
interface TimelineResponse {
  items: TimelineEntry[];
  pagination: {
    total: number;
    limit: number;
    offset: number;
  };
}

interface TimelineEntry {
  type: "meeting" | "audit" | "email";
  timestamp: string;  // ISO 8601 datetime
  summary: string;
  details: Record<string, any> | null;
  user: TimelineUser | null;
}

interface TimelineUser {
  id?: string;
  name?: string;
  email?: string;
}
```

### Example Request

```bash
curl -X GET "https://api.pipedesk.com/api/timeline/lead/lead-abc-123?limit=20&offset=0" \
  -H "Authorization: Bearer <token>" \
  -H "x-user-role: admin"
```

### Example Response (Mixed Types)

```json
{
  "items": [
    {
      "type": "meeting",
      "timestamp": "2024-01-15T14:00:00Z",
      "summary": "Sales Meeting - Client Review",
      "details": {
        "google_event_id": "evt_abc123xyz",
        "start_time": "2024-01-15T14:00:00Z",
        "end_time": "2024-01-15T15:00:00Z",
        "status": "confirmed",
        "meet_link": "https://meet.google.com/abc-defg-hij",
        "html_link": "https://calendar.google.com/event?eid=abc123",
        "attendees": ["client@example.com", "sales@company.com"]
      },
      "user": {
        "id": "user-123",
        "name": "John Doe",
        "email": "john@company.com"
      }
    },
    {
      "type": "email",
      "timestamp": "2024-01-14T16:45:00Z",
      "summary": "Re: Product inquiry - Follow up",
      "details": {
        "subject": "Re: Product inquiry - Follow up",
        "from": "client@example.com",
        "to": ["sales@company.com"]
      },
      "user": null
    },
    {
      "type": "audit",
      "timestamp": "2024-01-14T10:30:00Z",
      "summary": "Status changed: New → Qualified",
      "details": {
        "action": "status_change",
        "changes": {
          "lead_status_id": {
            "old": "status-new-id",
            "new": "status-qualified-id"
          }
        }
      },
      "user": {
        "id": "user-456",
        "name": "Jane Smith",
        "email": "jane@company.com"
      }
    },
    {
      "type": "audit",
      "timestamp": "2024-01-10T09:00:00Z",
      "summary": "Created lead",
      "details": {
        "action": "create",
        "changes": {}
      },
      "user": {
        "id": "user-456",
        "name": "Jane Smith",
        "email": "jane@company.com"
      }
    }
  ],
  "pagination": {
    "total": 4,
    "limit": 20,
    "offset": 0
  }
}
```

### Timeline Entry Types

| Type      | Description                                                    | Details Fields                                                                 |
|-----------|----------------------------------------------------------------|--------------------------------------------------------------------------------|
| `meeting` | Calendar events (Google Calendar)                              | `google_event_id`, `start_time`, `end_time`, `status`, `meet_link`, `attendees` |
| `email`   | Email communications (Gmail)                                   | `subject`, `from`, `to`                                                        |
| `audit`   | Entity changes (create, update, status_change, delete)         | `action`, `changes`                                                            |

### Frontend Implementation Example

```typescript
import { useEffect, useState } from 'react';

interface TimelineEntry {
  type: 'meeting' | 'audit' | 'email';
  timestamp: string;
  summary: string;
  details: Record<string, any> | null;
  user: { id?: string; name?: string; email?: string } | null;
}

interface TimelineResponse {
  items: TimelineEntry[];
  pagination: { total: number; limit: number; offset: number };
}

async function fetchTimeline(
  entityType: 'lead' | 'deal' | 'contact',
  entityId: string,
  limit = 20,
  offset = 0
): Promise<TimelineResponse> {
  const response = await fetch(
    `/api/timeline/${entityType}/${entityId}?limit=${limit}&offset=${offset}`,
    {
      headers: {
        'Authorization': `Bearer ${getToken()}`,
        'x-user-role': getUserRole()
      }
    }
  );
  
  if (!response.ok) {
    throw new Error(`Timeline fetch failed: ${response.statusText}`);
  }
  
  return response.json();
}

function TimelineComponent({ entityType, entityId }: Props) {
  const [timeline, setTimeline] = useState<TimelineResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchTimeline(entityType, entityId)
      .then(setTimeline)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [entityType, entityId]);

  if (loading) return <Spinner />;

  return (
    <div className="timeline">
      {timeline?.items.map((item, index) => (
        <TimelineItem key={index} entry={item} />
      ))}
    </div>
  );
}
```

---

## Calendar API

The Calendar API allows you to create, list, and manage calendar events with Google Meet integration.

### Base URL

```
/api/calendar
```

### List Events

Retrieve calendar events from the local database mirror (synced from Google Calendar).

```
GET /api/calendar/events
```

#### Query Parameters

| Parameter  | Type     | Default | Description                                         |
|------------|----------|---------|-----------------------------------------------------|
| `time_min` | datetime | null    | Filter events starting after this datetime          |
| `time_max` | datetime | null    | Filter events ending before this datetime           |
| `status`   | string   | null    | Filter by status: `confirmed`, `tentative`, `cancelled` |
| `limit`    | integer  | 100     | Maximum results (1-500)                             |
| `offset`   | integer  | 0       | Number of results to skip                           |

#### Example Request

```bash
curl -X GET "https://api.pipedesk.com/api/calendar/events?limit=10&time_min=2024-01-01T00:00:00Z" \
  -H "Authorization: Bearer <token>" \
  -H "x-user-role: manager"
```

#### Example Response

```json
[
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
        "email": "client@example.com",
        "responseStatus": "accepted",
        "displayName": "Client Name"
      },
      {
        "email": "sales@company.com",
        "responseStatus": "accepted",
        "displayName": "Sales Rep"
      }
    ]
  }
]
```

### Create Event with Google Meet Link

Create a new calendar event with an automatically generated Google Meet link.

```
POST /api/calendar/events
```

#### Request Body

```typescript
interface EventCreate {
  summary: string;              // Event title (required)
  description?: string;         // Event details
  start_time: string;          // ISO 8601 datetime (required)
  end_time: string;            // ISO 8601 datetime (required)
  attendees?: string[];        // List of email addresses
  create_meet_link?: boolean;  // Generate Meet link (default: true)
}
```

#### Example Request

```bash
curl -X POST "https://api.pipedesk.com/api/calendar/events" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "summary": "Sales Meeting - Client X",
    "description": "Quarterly review and proposal presentation",
    "start_time": "2024-01-15T14:00:00Z",
    "end_time": "2024-01-15T15:00:00Z",
    "attendees": ["sales@company.com", "client@example.com"],
    "create_meet_link": true
  }'
```

#### Example Response (with Meet Link)

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
      "responseStatus": "needsAction",
      "displayName": null
    },
    {
      "email": "client@example.com",
      "responseStatus": "needsAction",
      "displayName": null
    }
  ]
}
```

**Important:** The `meet_link` field contains the Google Meet video conference link when `create_meet_link` is set to `true` (default). This link can be shared with attendees for the video call.

### Get Event Details

```
GET /api/calendar/events/{event_id}
```

### Update Event

```
PATCH /api/calendar/events/{event_id}
```

### Cancel Event

```
DELETE /api/calendar/events/{event_id}
```

Performs a soft delete - the event is marked as `cancelled` but not permanently deleted.

---

## Real-time Synchronization

### No Polling Required

**The Frontend does not need to poll Google APIs directly.** Our backend handles all synchronization automatically through webhooks.

### How It Works

```
┌─────────────────┐      Webhook       ┌─────────────────┐
│  Google APIs    │  ─────────────────> │  PipeDesk API   │
│  (Calendar,     │  Real-time         │  Backend        │
│   Drive, Gmail) │  Notifications     │                 │
└─────────────────┘                    └────────┬────────┘
                                                │
                                                │ Synced Data
                                                ▼
                                       ┌─────────────────┐
                                       │    Database     │
                                       │   (PostgreSQL)  │
                                       └────────┬────────┘
                                                │
                                                │ Query
                                                ▼
                                       ┌─────────────────┐
                                       │    Frontend     │
                                       │   Application   │
                                       └─────────────────┘
```

### What This Means for Frontend

1. **Use our API endpoints** - All data is already synchronized to our database
2. **No Google API calls needed** - The backend handles Google API communication
3. **Fresh data guaranteed** - Webhooks trigger immediate sync when changes occur
4. **Simplified implementation** - No need to handle OAuth tokens for Google

### Synced Data Sources

| Source          | Sync Method                    | Endpoint to Use                  |
|-----------------|--------------------------------|----------------------------------|
| Calendar Events | Webhook + Sync Token           | `GET /api/calendar/events`       |
| Gmail Messages  | Webhook notifications          | `GET /api/crm/{type}/{id}/emails` |
| Drive Files     | Webhook + Bidirectional Sync   | `GET /drive/{type}/{id}`         |
| Audit Logs      | Internal logging               | `GET /api/timeline/{type}/{id}`  |

### Best Practices

1. **Fetch from our API**: Always query our endpoints instead of Google directly
2. **Use pagination**: For large datasets, use `limit` and `offset` parameters
3. **Cache responses**: Implement client-side caching with reasonable TTL (e.g., 1 minute)
4. **Handle stale data gracefully**: Data is near real-time but may have brief delays

---

## Authentication

### Required Headers

| Header          | Description                                      |
|-----------------|--------------------------------------------------|
| `Authorization` | Bearer token: `Bearer <jwt_token>`               |
| `x-user-role`   | User's role: `admin`, `manager`, `analyst`, etc. |
| `x-user-id`     | (Optional) User UUID for audit logging           |

### Role-Based Access

Different roles have different access levels:

| Role           | Timeline | Calendar (Details) | Drive (Write) |
|----------------|----------|-------------------|---------------|
| `admin`        | ✅ Full   | ✅ Full            | ✅ Yes         |
| `superadmin`   | ✅ Full   | ✅ Full            | ✅ Yes         |
| `manager`      | ✅ Full   | ✅ Full            | ✅ Yes         |
| `analyst`      | ✅ Full   | ✅ Full            | ❌ No          |
| `new_business` | ✅ Full   | ✅ Full            | ❌ No          |
| `client`       | ❌ No     | ⚠️ Limited         | ❌ No          |
| `customer`     | ❌ No     | ⚠️ Limited         | ❌ No          |

---

## Error Handling

### Standard Error Response

```json
{
  "error": true,
  "code": "NOT_FOUND",
  "message": "Lead with ID lead-xyz not found",
  "details": null
}
```

### Common Error Codes

| HTTP Status | Code                | Description                          |
|-------------|---------------------|--------------------------------------|
| 400         | `BAD_REQUEST`       | Invalid request parameters           |
| 401         | `UNAUTHORIZED`      | Missing or invalid authentication    |
| 403         | `FORBIDDEN`         | Insufficient permissions             |
| 404         | `NOT_FOUND`         | Resource not found                   |
| 500         | `INTERNAL_ERROR`    | Server error                         |

### Frontend Error Handling Example

```typescript
async function apiRequest<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...options,
    headers: {
      'Authorization': `Bearer ${getToken()}`,
      'x-user-role': getUserRole(),
      ...options?.headers
    }
  });

  if (!response.ok) {
    const error = await response.json();
    
    switch (response.status) {
      case 401:
        // Redirect to login
        redirectToLogin();
        break;
      case 403:
        // Show permission denied message
        showError('You do not have permission to perform this action');
        break;
      case 404:
        // Show not found message
        showError(error.message || 'Resource not found');
        break;
      default:
        // Show generic error
        showError('An error occurred. Please try again.');
    }
    
    throw new Error(error.message);
  }

  return response.json();
}
```

---

## Quick Reference

### Most Used Endpoints

| Use Case                    | Method | Endpoint                                    |
|-----------------------------|--------|---------------------------------------------|
| Get entity timeline         | GET    | `/api/timeline/{type}/{id}`                 |
| List calendar events        | GET    | `/api/calendar/events`                      |
| Create event with Meet link | POST   | `/api/calendar/events`                      |
| Get event details           | GET    | `/api/calendar/events/{id}`                 |
| List entity files           | GET    | `/drive/{type}/{id}`                        |
| Health check                | GET    | `/health`                                   |

### TypeScript Types

```typescript
// Timeline
type TimelineEntryType = 'meeting' | 'audit' | 'email';
type EntityType = 'lead' | 'deal' | 'contact';

// Calendar
type EventStatus = 'confirmed' | 'tentative' | 'cancelled';
type AttendeeResponseStatus = 'needsAction' | 'declined' | 'tentative' | 'accepted';

// Roles
type UserRole = 'admin' | 'superadmin' | 'manager' | 'analyst' | 'new_business' | 'client' | 'customer';
```

---

## Support

For questions or issues with the API integration, contact the Backend team or refer to:

- [API Error Handling Documentation](./API_ERROR_HANDLING.md)
- [CRM Timeline API Details](./CRM_TIMELINE_API.md)
- [Health API Documentation](./HEALTH_API.md)
