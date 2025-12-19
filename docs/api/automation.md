# Automation API

Prefix: `/api/automation`

## Endpoints
- `POST /scan-email/{message_id}` – Scan a single Gmail message for attachments and upload them into the specified lead folder.
- `POST /scan-lead-emails` – Scan recent Gmail messages from a provided email address, saving attachments to the lead folder.

Automation routes validate Gmail read metadata permission and Drive write permission based on the caller’s role. Attachments are saved through Drive services and responses return counts plus any errors encountered.
