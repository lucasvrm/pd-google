# Soft Delete Implementation Summary

## Overview
This implementation adds soft delete functionality to the PipeDesk Google Drive backend, allowing files and folders to be marked as deleted without physical removal from Google Drive.

## Database Schema Responsibilities

### `drive_files` (Owned by `pd-google`)
- The `drive_files` table is fully managed by this repository (`pd-google`).
- Schema changes, including soft delete fields, are handled by:
    - `init_db.py`: For new installations.
    - `migrations/add_soft_delete_fields.py`: For existing installations.

### `google_drive_folders` (Owned by Supabase / Main App)
- The `google_drive_folders` table schema is managed by the main application's Supabase migrations (`supabase/migrations/`).
- **`pd-google` does NOT modify this table's schema.**
- It relies on the main application to ensure the `deleted_at`, `deleted_by`, and `delete_reason` columns exist.

## Changes Made

### 1. Database Schema Updates
**Models Extended:**
- `DriveFile` and `DriveFolder` models in `models.py` now reflect the schema with:
  - `deleted_at`: DateTime field (nullable) - timestamp when item was deleted
  - `deleted_by`: String field (nullable) - user ID who performed deletion
  - `delete_reason`: String field (nullable) - optional reason for deletion

**Migration Script (`pd-google` side):**
- Updated `migrations/add_soft_delete_fields.py` to **only** add columns to `drive_files`.
- Safe to run on existing databases (idempotent).

### 2. API Endpoints

#### New DELETE Endpoints
1. **`DELETE /drive/{entity_type}/{entity_id}/files/{file_id}`**
   - Soft deletes a file
   - Query param: `reason` (optional)
   - Requires write permission (writer or owner role)
   - Returns: `{status, file_id, deleted_at, deleted_by}`

2. **`DELETE /drive/{entity_type}/{entity_id}/folders/{folder_id}`**
   - Soft deletes a folder
   - Query param: `reason` (optional)
   - Requires write permission (writer or owner role)
   - Returns: `{status, folder_id, deleted_at, deleted_by}`

#### Modified Endpoints
**`GET /drive/{entity_type}/{entity_id}`**
- Now filters out soft-deleted items by default
- New query parameter: `include_deleted=true` to show deleted items
- Useful for administrative purposes

### 3. Security Features
- Permission checks: Only users with write permission (writer/owner) can soft delete
- JSON injection prevention: Properly serializes user input using `json.dumps()`
- Audit logging: All soft delete operations logged to `DriveChangeLog`
- Validation: Checks entity existence, prevents duplicate deletion

### 4. Cache Integration
- Automatically invalidates cache when items are soft deleted
- Ensures listings reflect deletions immediately
- Uses existing `CacheService` infrastructure

### 5. Audit Trail
Each soft delete operation creates an audit log entry in `DriveChangeLog`.

### 6. Comprehensive Testing
Created `tests/test_soft_delete.py` with 11 tests covering file and folder operations, permissions, filtering, and audit logs.

## Migration Instructions

### For New Installations
1. **Backend (`pd-google`)**: Run `python init_db.py`. This creates all tables, including `drive_files` with soft delete columns.
2. **Database (`Supabase`)**: Ensure the standard Supabase migrations have run to create/update `google_drive_folders`.

### For Existing Installations

#### 1. Update `drive_files` (pd-google)
Run the migration script to update the `drive_files` table:
```bash
python migrations/add_soft_delete_fields.py
```
This script adds the necessary columns and indexes to `drive_files`. It ignores `google_drive_folders`.

#### 2. Update `google_drive_folders` (Supabase)
Ensure the corresponding migration has been applied in your Supabase project (main application) to add soft delete fields to `google_drive_folders`. Do **not** attempt to modify this table from `pd-google`.

## Testing

### Run Soft Delete Tests
```bash
USE_MOCK_DRIVE=true python -m pytest tests/test_soft_delete.py -v
```

### Run All Core Tests
```bash
USE_MOCK_DRIVE=true python -m pytest tests/test_soft_delete.py tests/test_permissions.py tests/test_hierarchy.py tests/test_upload_flow.py -v
```
