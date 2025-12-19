# Data models

The service uses SQLAlchemy models defined in `models.py`. Key tables the backend writes to:

- **DriveWebhookChannel** – Active webhook channels for Drive notifications.
- **DriveFolder / DriveFile** – Mappings between CRM entities and Google Drive folders/files, including soft-delete markers.
- **DriveStructureTemplate / DriveStructureNode** – Optional templates for constructing folder hierarchies.
- **Lead / Deal / Contact** – Entity metadata used for permission checks and timeline enrichment.
- **LeadTag / EntityTag / Tag** – Tagging tables for leads and other entities.
- **LeadActivityStats** – Aggregated metrics for leads consumed by SLA/priority workers.
- **DriveChangeLog** – Audit trail for Drive operations (uploads, renames, soft deletes, webhook sync results).
- **CalendarSyncState / CalendarEvent** – Local store of calendar channels and event metadata mirrored from Google Calendar.
- **AuditLog** – Change history for leads and deals captured via `services.audit_service` listeners.

`init_db.py` can be used to create tables for fresh installations; runtime migrations add soft-delete fields and lead tag tables when enabled.
