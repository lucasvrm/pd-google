# Gmail API

Prefix: `/api/gmail`

## Read operations
- `GET /messages` – List messages with search query, label, sender/recipient filters, date ranges, pagination.
- `GET /messages/{message_id}` – Fetch message detail including parsed headers, bodies, attachments, and web link.
- `GET /threads` – List threads with participant rollups and attachment flags.
- `GET /threads/{thread_id}` – Get a full thread with messages expanded.
- `GET /labels` – List available labels.
- `GET /messages/{message_id}/attachments/{attachment_id}` – Download an attachment.

## Write operations
- `POST /messages/send` – Send an email with optional attachments and inline content.
- `POST /drafts` – Create a draft.
- `POST /drafts/{draft_id}/send` – Send a draft.
- `PUT /messages/{message_id}/labels` – Update labels on a message.

`services.google_gmail_service.GoogleGmailService` handles read access (impersonating `GOOGLE_IMPERSONATE_EMAIL`), while `services.gmail_service.GmailService` handles send/draft operations. Permissions are validated via `PermissionService` before executing writes.
