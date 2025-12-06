# Database Migrations

This folder contains database migration scripts for adding soft delete functionality.

## Option 1: SQL Script (Recommended for Supabase)

**File:** `add_soft_delete_fields.sql`

The easiest way to run the migration on Supabase:

1. Open your Supabase project
2. Go to the **SQL Editor**
3. Copy the contents of `add_soft_delete_fields.sql`
4. Paste and run the script
5. Check the messages to confirm all columns and indexes were created

This script is idempotent - safe to run multiple times. It will skip columns that already exist.

## Option 2: Python Script (For automated deployments)

**File:** `add_soft_delete_fields.py`

This script runs automatically when the application starts (see `main.py`). You can also run it manually:

```bash
python migrations/add_soft_delete_fields.py
```

The Python script is useful for:
- Automated deployments
- CI/CD pipelines
- Local development with SQLite

## What the Migration Does

Adds three columns to `drive_files` and `google_drive_folders` tables:

- `deleted_at` (TIMESTAMP WITH TIME ZONE) - When the item was soft deleted
- `deleted_by` (VARCHAR) - User ID who deleted the item
- `delete_reason` (VARCHAR) - Optional reason for deletion

Also creates indexes on `deleted_at` for efficient filtering of non-deleted items.

## Verification

After running the migration, verify the columns exist:

```sql
-- Check drive_files table
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'drive_files' 
  AND column_name IN ('deleted_at', 'deleted_by', 'delete_reason');

-- Check google_drive_folders table
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'google_drive_folders' 
  AND column_name IN ('deleted_at', 'deleted_by', 'delete_reason');
```

Both queries should return 3 rows each.
