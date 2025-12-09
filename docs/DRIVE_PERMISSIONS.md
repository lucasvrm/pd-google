# Drive Permissions and File Movement

This document describes the new API surface for managing Google Drive permissions and moving items within an entity's Drive hierarchy.

## Endpoints

### List permissions
- **GET** `/drive/{entity_type}/{entity_id}/files/{file_id}/permissions`
- Returns the permissions configured on the target Drive file/folder.
- Requires at least writer permissions on the entity.

### Add permission
- **POST** `/drive/{entity_type}/{entity_id}/files/{file_id}/permissions`
- Body: `{"email": "user@example.com", "role": "writer", "type": "user"}`
- Creates a new permission entry for the specified collaborator.

### Update permission
- **PUT** `/drive/{entity_type}/{entity_id}/files/{file_id}/permissions/{permission_id}`
- Body: `{"role": "reader"}`
- Updates the role for an existing permission.

### Delete permission
- **DELETE** `/drive/{entity_type}/{entity_id}/files/{file_id}/permissions/{permission_id}`
- Removes a permission entry from the target item.

### Move item
- **PUT** `/drive/{entity_type}/{entity_id}/files/{file_id}/move`
- Body: `{"destination_parent_id": "<folder_id>"}`
- Moves a file/folder within the validated entity hierarchy.

### Rename item
- **PUT** `/drive/{entity_type}/{entity_id}/files/{file_id}/rename`
- Body: `{"new_name": "New Name"}`
- Renames a Drive item after validating hierarchy membership.

## Validation rules
- `entity_type` must be one of `company`, `lead`, or `deal`.
- The authenticated user must have write-level permissions for the entity.
- Target items and destination folders must reside within the entity's Drive hierarchy; otherwise a `403` is returned.

## Services
- The `DrivePermissionsService` delegates to the configured Drive backend (mock or real) to perform permission, move, and rename operations.
- Mocked implementations persist data in `mock_drive_db.json` and now track permissions per file/folder for testing.
