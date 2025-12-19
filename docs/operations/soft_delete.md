# Soft deletion

Drive items and qualified leads are soft deleted to preserve history and auditability.

## Drive files and folders
- Endpoints `DELETE /drive/{entity_type}/{entity_id}/files/{file_id}` and `DELETE /drive/{entity_type}/{entity_id}/folders/{folder_id}` mark records as deleted by setting `deleted_at`, `deleted_by`, and `delete_reason` on `DriveFile`/`DriveFolder`.
- Listings (`GET /api/drive/{entity_type}/{entity_id}`) hide soft-deleted entries unless `include_deleted=true` is provided.
- Cache entries for the parent folder are invalidated after deletion; Drive content itself remains intact in Google Drive.
- Audit entries are written to `DriveChangeLog` with `event_type` reflecting the operation.

## Lead qualification soft delete
- Leads carry `deleted_at` and `qualified_at` fields; qualified leads are filtered from `/api/leads/sales-view` unless explicitly requested.
- Migration scripts `migrations/add_lead_soft_delete.py` and `migrations/add_qualification_fields.py` add the required columns.
- Audit logging tracks `deleted_at` and qualification timestamps through `services.audit_service` hooks.
