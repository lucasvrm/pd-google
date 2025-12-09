# Gmail Send & Draft API

This document describes the write-enabled Gmail endpoints exposed under `/api/gmail`.

## Endpoints

### POST `/api/gmail/send`
- Sends an email message.
- Request body: `SendEmailRequest` (recipients, subject, optional text/HTML bodies, attachments, optional `thread_id`).
- Response: `SentMessage` containing the Gmail message ID, thread ID, and labels returned by Gmail.

### POST `/api/gmail/drafts`
- Creates a new Gmail draft with the provided content.
- Request body: `DraftRequest` (same shape as `SendEmailRequest`).
- Response: `DraftResponse` with the draft ID and underlying message metadata.

### GET `/api/gmail/drafts/{draft_id}`
- Retrieves a draft by ID.
- Response: `DraftResponse` for the requested draft.

### PUT `/api/gmail/drafts/{draft_id}`
- Updates an existing draft with new content.
- Request body: `DraftRequest`.
- Response: updated `DraftResponse`.

### DELETE `/api/gmail/drafts/{draft_id}`
- Deletes the specified draft.
- Response: `{ "status": "deleted", "id": "<draft_id>" }`.

### POST `/api/gmail/messages/{message_id}/labels`
- Adds or removes labels from a Gmail message.
- Request body: `LabelUpdateRequest` with `add_labels` and `remove_labels` arrays.
- Response: `LabelUpdateResponse` containing the message ID and resulting labels.

## Schemas
- `SendEmailRequest` / `DraftRequest`: recipients, subject, bodies, optional attachments (base64 content) and thread association.
- `SentMessage`: minimal information about the sent or draft message (ID, thread, labels).
- `DraftResponse`: draft ID with the associated `SentMessage`.
- `LabelUpdateRequest` and `LabelUpdateResponse`: add/remove label payload and resulting label IDs.
