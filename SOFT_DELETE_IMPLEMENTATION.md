# Soft Delete Implementation Summary

## Overview
This implementation adds soft delete functionality to the PipeDesk Google Drive backend, allowing files and folders to be marked as deleted without physical removal from Google Drive.

Additionally, **Leads** support soft delete for qualified leads - when a lead is marked as "qualified", it sets `deleted_at` and is excluded from normal queries (e.g., `/api/leads/sales-view`).

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

### `leads` (Owned by Supabase / Main App)
- The `leads` table schema is managed by the main application's Supabase migrations.
- **Migration script for leads soft delete:** `migrations/add_lead_soft_delete.py`
- Adds the `deleted_at` column to the `leads` table for soft delete functionality.
- Qualified leads have `deleted_at` set and are excluded from `/api/leads/sales-view`.

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

---

## Lead Soft Delete Implementation

### Overview
Leads that are "qualified" (status changed to qualified) are soft deleted by setting the `deleted_at` field. This removes them from the sales view while preserving historical data.

### Changes Made

#### 1. Model Update (`models.py`)
- Added `deleted_at` field (DateTime, nullable, indexed) to the `Lead` model
- Added `qualified_at` field (DateTime, nullable, indexed) to track when lead was qualified
- Added `description` field (Text, nullable) for lead notes
- Leads with `deleted_at` set are considered "soft deleted"
- Updated `Deal` model to include fields migrated from Lead during qualification:
  - `legal_name` - Razão Social from Lead
  - `trade_name` - Nome Fantasia from Lead
  - `owner_user_id` - Owner from Lead
  - `description` - Description from Lead

#### 2. Query Filter (`routers/leads.py`)
- Modified `/api/leads/sales-view` to filter out leads where `deleted_at IS NOT NULL`
- Excludes leads whose `lead_statuses.code = 'qualified'` even when `qualified_at` is `NULL` (include via `includeQualified=true`)
- This is applied automatically to all queries, ensuring soft deleted leads are never returned

#### 3. Audit Service (`services/audit_service.py`)
- Added `deleted_at` to `LEAD_AUDIT_FIELDS` for tracking changes
- Added `qualified_at` to `LEAD_AUDIT_FIELDS` for tracking qualification timestamp
- Added `description` to `LEAD_AUDIT_FIELDS` for tracking description changes
- Updated `_log_lead_changes` to detect qualification operations and log them with `action="qualify_and_soft_delete"`
- Added migrated fields to `DEAL_AUDIT_FIELDS` (legal_name, trade_name, owner_user_id, description)

#### 4. Migration Scripts
- `migrations/add_lead_soft_delete.py` - Adds `deleted_at` column to `leads` table
- `migrations/add_qualification_fields.py` - Adds qualification-related columns:
  - `leads.qualified_at` - Qualification timestamp
  - `leads.description` - Lead description
  - `master_deals.legal_name` - Legal name from Lead
  - `master_deals.trade_name` - Trade name from Lead
  - `master_deals.owner_user_id` - Owner from Lead
  - `master_deals.description` - Description from Lead

### Testing
Created `tests/test_lead_soft_delete.py` with 6 tests:
- Active leads are returned in sales-view
- Soft deleted leads are excluded from sales-view
- Multiple deleted leads are all excluded
- Filters work correctly with soft delete
- Soft delete creates audit log with `action="soft_delete"`
- Regular updates don't trigger soft delete action

Created `tests/test_lead_qualification.py` with comprehensive tests for:
- Successful lead qualification
- Qualified leads excluded from sales-view
- Field migration from Lead to Deal
- Preserving existing Deal fields
- Validation for non-existent leads/deals
- Preventing re-qualification of already qualified leads
- Preventing qualification of disqualified leads
- Audit log creation with `action="qualify_and_soft_delete"`
- Tag ID tracking in response

### Usage

#### Qualifying a Lead via API (Recommended)
Use the new qualification endpoint:

```http
POST /api/leads/{lead_id}/qualify
Content-Type: application/json

{
  "deal_id": "uuid-of-target-deal"
}
```

Response:
```json
{
  "status": "qualified",
  "lead_id": "uuid-of-lead",
  "deal_id": "uuid-of-deal",
  "qualified_at": "2024-01-15T10:30:00Z",
  "deleted_at": "2024-01-15T10:30:00Z",
  "migrated_fields": {
    "legal_name": "Company Legal Name",
    "trade_name": "Company Trade Name",
    "owner_user_id": "uuid-of-owner",
    "description": "Lead description",
    "tags": ["tag-id-1", "tag-id-2"]
  }
}
```

This will:
1. Set `qualified_at` and `deleted_at` to the current timestamp
2. Link the lead to the specified deal via `qualified_master_deal_id`
3. Migrate critical fields (legal_name, trade_name, owner_user_id, description) to the deal
4. Create an audit log entry with `action="qualify_and_soft_delete"`
5. Exclude the lead from `/api/leads/sales-view` queries

#### Manual Qualification (Legacy)
To qualify a lead manually (soft delete it), set both fields:

```python
from datetime import datetime, timezone

now = datetime.now(timezone.utc)
lead.qualified_at = now  # Marks qualification
lead.deleted_at = now    # Removes from views
lead.qualified_master_deal_id = deal_id  # Links to deal
db.commit()
```

---

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

#### 3. Update `leads` (pd-google)
Run the migration script to update the `leads` table:
```bash
python migrations/add_lead_soft_delete.py
```
This script adds the `deleted_at` column and index to the `leads` table.

## Testing

### Run Drive Soft Delete Tests
```bash
USE_MOCK_DRIVE=true python -m pytest tests/test_soft_delete.py -v
```

### Run Lead Soft Delete Tests
```bash
python -m pytest tests/test_lead_soft_delete.py -v
```

### Run All Core Tests
```bash
USE_MOCK_DRIVE=true python -m pytest tests/test_soft_delete.py tests/test_lead_soft_delete.py tests/test_permissions.py tests/test_hierarchy.py tests/test_upload_flow.py -v
```
