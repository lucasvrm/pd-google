# Calendar API

Prefix: `/api/calendar`

## Endpoints
- `POST /events` – Create an event (supports aliases for camelCase fields, optional Meet link creation). Saves event metadata locally.
- `GET /events` – List events with optional filtering, pagination, and quick-action helpers (`entityType`, `entityId`, `calendarId`).
- `GET /events/{id}` – Retrieve a single event by local database ID or Google event ID.
- `PATCH /events/{id}` – Update summary/description/times/attendees.
- `DELETE /events/{id}` – Cancel an event (soft delete pattern using Calendar API cancelation).
- `POST /watch` – Register a webhook channel for Calendar change notifications using `WEBHOOK_BASE_URL` and `WEBHOOK_SECRET`.

## Data handling
Created or fetched events are stored in `CalendarEvent`. Channels are tracked in `CalendarSyncState` and refreshed via webhook handler in `routers/webhooks.py` to keep local data in sync.
