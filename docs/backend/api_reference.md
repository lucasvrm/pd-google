# API Reference

This document provides a reference for all REST API endpoints available in the PipeDesk Google Drive Backend.

---

## Timeline API

The Unified Timeline API provides a single endpoint for fetching all activities related to a CRM entity, aggregating data from calendar events, audit logs, and Gmail emails.

### GET /api/timeline/{entity_type}/{entity_id}

**Summary:** Get Unified Timeline

Retrieves a unified timeline for a CRM entity, aggregating calendar events, audit logs, and Gmail emails into a single chronological view sorted by timestamp descending.

**Path Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `entity_type` | string | Yes | Type of entity: `lead`, `deal`, or `contact` |
| `entity_id` | string | Yes | UUID of the entity |

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | integer | 50 | Maximum items to return (min: 1, max: 200) |
| `offset` | integer | 0 | Number of items to skip for pagination |

**Response Format:**

```json
{
  "items": [
    {
      "type": "meeting | audit | email",
      "timestamp": "2024-01-15T14:00:00Z",
      "summary": "Human-readable summary",
      "details": { ... },
      "user": {
        "id": "user-uuid",
        "name": "User Name",
        "email": "user@example.com"
      }
    }
  ],
  "pagination": {
    "total": 25,
    "limit": 50,
    "offset": 0
  }
}
```

**Timeline Entry Types:**

| Type | Description | Details Fields |
|------|-------------|----------------|
| `meeting` | Calendar events | `google_event_id`, `start_time`, `end_time`, `status`, `meet_link`, `html_link`, `attendees` |
| `audit` | Entity changes | `action`, `changes` (with old/new values) |
| `email` | Gmail emails | `message_id`, `thread_id`, `subject`, `from`, `to`, `cc`, `bcc`, `snippet`, `labels` |

**Email Matching Logic:**

For **leads**, emails are matched using:
1. Contact emails linked to the lead via `lead_contacts` table (to/from matching)
2. Company domain matching when applicable (e.g., `*@clientcompany.com`)

For **contacts**, emails are matched using:
1. The contact's own email address (to/from matching)

**Graceful Degradation:**

If Gmail is unavailable or misconfigured, the timeline will still return calendar events and audit logs without causing an error. Email entries will simply be empty.

**Example Request:**

```bash
curl -X GET "http://localhost:8000/api/timeline/lead/123e4567-e89b-12d3-a456-426614174000?limit=20&offset=0" \
  -H "Authorization: Bearer <token>"
```

**Example Response:**

```json
{
  "items": [
    {
      "type": "email",
      "timestamp": "2024-01-16T09:15:00Z",
      "summary": "Re: Product Inquiry",
      "details": {
        "message_id": "18b2f3a8d4c5e1f2",
        "thread_id": "18b2f3a8d4c5e1f2",
        "subject": "Re: Product Inquiry",
        "from": "client@clientcompany.com",
        "to": ["sales@ourcompany.com"],
        "cc": null,
        "bcc": null,
        "snippet": "Thank you for your response. We would like to schedule a demo...",
        "labels": ["INBOX", "IMPORTANT"]
      },
      "user": {
        "id": null,
        "name": null,
        "email": "client@clientcompany.com"
      }
    },
    {
      "type": "meeting",
      "timestamp": "2024-01-15T14:00:00Z",
      "summary": "Sales Meeting - Client Review",
      "details": {
        "google_event_id": "evt_abc123",
        "start_time": "2024-01-15T14:00:00Z",
        "end_time": "2024-01-15T15:00:00Z",
        "status": "confirmed",
        "meet_link": "https://meet.google.com/abc-defg-hij",
        "html_link": "https://calendar.google.com/event?eid=abc123",
        "attendees": ["client@example.com"]
      },
      "user": {
        "id": null,
        "name": null,
        "email": "organizer@company.com"
      }
    },
    {
      "type": "audit",
      "timestamp": "2024-01-14T10:30:00Z",
      "summary": "Status changed: status-new-id → status-qualified-id",
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
    }
  ],
  "pagination": {
    "total": 25,
    "limit": 20,
    "offset": 0
  }
}
```

**Error Responses:**

| Status | Code | Description |
|--------|------|-------------|
| 404 | Not Found | Entity with specified ID not found |
| 422 | Validation Error | Invalid entity_type or missing required parameters |
| 500 | Internal Server Error | Failed to fetch timeline |

---

## Related Documentation

- [Audit System](./audit_system.md) - Audit logging implementation details
- [Calendar API](../../CALENDAR_API.md) - Google Calendar integration
- [Drive Adapter](./api_drive_adapter.md) - Drive items endpoint documentation
- [Gmail API](../../GMAIL_API.md) - Gmail integration documentation
