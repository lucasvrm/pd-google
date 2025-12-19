# Drive API

Base prefix: `/api`

## Endpoints
- `GET /drive/{entity_type}/{entity_id}` – Ensure entity hierarchy exists (company/lead/deal), list contents with pagination and breadcrumbs, and return effective Drive permission for the requester. Set `include_deleted=true` to surface soft-deleted records.
- `POST /drive/{entity_type}/{entity_id}/folder` – Create a subfolder under the entity root or a validated descendant.
- `POST /drive/{entity_type}/{entity_id}/upload` – Upload a file to Drive and persist metadata in `DriveFile`.
- `PUT /drive/{entity_type}/{entity_id}/files/{file_id}/rename` – Rename a file or folder after lineage verification.
- `PUT /drive/{entity_type}/{entity_id}/files/{file_id}/move` – Move a file/folder to another descendant folder within the same hierarchy.
- `GET /drive/{entity_type}/{entity_id}/files/{file_id}/permissions` – List permissions for a Drive item via `DrivePermissionsService`.
- `POST /drive/{entity_type}/{entity_id}/files/{file_id}/permissions` – Add a permission (role/email) to a Drive item.
- `PUT /drive/{entity_type}/{entity_id}/files/{file_id}/permissions/{permission_id}` – Update an existing permission role.
- `DELETE /drive/{entity_type}/{entity_id}/files/{file_id}/permissions/{permission_id}` – Remove a permission.
- `DELETE /drive/{entity_type}/{entity_id}/files/{file_id}` – Soft delete a file.
- `DELETE /drive/{entity_type}/{entity_id}/folders/{folder_id}` – Soft delete a folder (admin/manager only).
- `GET /drive/search` – Cached search wrapper over Drive.
- `POST /drive/sync-name` – Sync Drive folder/file names with entity labels.
- `POST /drive/{entity_type}/{entity_id}/repair` – Rebuild mapping metadata for an entity hierarchy using current Drive state.

## Permissions
`services.permission_service.PermissionService` maps JWT roles to Drive roles. Reader permissions block write operations; destructive folder deletes require manager or admin roles via dependency guards.

## Backends
- Real Drive client: `services.google_drive_real.GoogleDriveRealService`
- Mock Drive client: `services.google_drive_mock.GoogleDriveService`

The chosen backend is controlled by `USE_MOCK_DRIVE`. Webhook synchronization always uses the real client.
