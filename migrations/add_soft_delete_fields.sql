-- Migration script for Supabase/PostgreSQL database
-- Run this directly in the Supabase SQL Editor
-- 
-- This script adds soft delete fields to both:
-- - google_drive_folders (shared with main app)
-- - drive_files (pd-google backend table)
--
-- If drive_files doesn't exist yet, it will be created by init_db.py
-- This script is safe to run even if drive_files doesn't exist (uses IF EXISTS)

-- Create google_drive_folders table if it doesn't exist
CREATE TABLE IF NOT EXISTS google_drive_folders (
    id SERIAL PRIMARY KEY,
    entity_id VARCHAR,
    entity_type VARCHAR,
    folder_id VARCHAR UNIQUE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    deleted_at TIMESTAMP WITH TIME ZONE,
    deleted_by VARCHAR,
    delete_reason VARCHAR
);

-- Create indexes for google_drive_folders
CREATE INDEX IF NOT EXISTS ix_google_drive_folders_entity_id ON google_drive_folders (entity_id);
CREATE INDEX IF NOT EXISTS ix_google_drive_folders_entity_type ON google_drive_folders (entity_type);
CREATE INDEX IF NOT EXISTS ix_google_drive_folders_folder_id ON google_drive_folders (folder_id);
CREATE INDEX IF NOT EXISTS ix_google_drive_folders_deleted_at ON google_drive_folders (deleted_at);

-- If table already existed, add missing soft delete columns
DO $$ 
BEGIN
    -- Add deleted_at column if missing
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'google_drive_folders' AND column_name = 'deleted_at'
    ) THEN
        ALTER TABLE google_drive_folders ADD COLUMN deleted_at TIMESTAMP WITH TIME ZONE;
        RAISE NOTICE 'Added deleted_at to google_drive_folders';
    ELSE
        RAISE NOTICE 'deleted_at already exists in google_drive_folders';
    END IF;

    -- Add deleted_by column if missing
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'google_drive_folders' AND column_name = 'deleted_by'
    ) THEN
        ALTER TABLE google_drive_folders ADD COLUMN deleted_by VARCHAR;
        RAISE NOTICE 'Added deleted_by to google_drive_folders';
    ELSE
        RAISE NOTICE 'deleted_by already exists in google_drive_folders';
    END IF;

    -- Add delete_reason column if missing
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'google_drive_folders' AND column_name = 'delete_reason'
    ) THEN
        ALTER TABLE google_drive_folders ADD COLUMN delete_reason VARCHAR;
        RAISE NOTICE 'Added delete_reason to google_drive_folders';
    ELSE
        RAISE NOTICE 'delete_reason already exists in google_drive_folders';
    END IF;
END $$;

-- Display success message
DO $$ 
BEGIN
    RAISE NOTICE '✅ Migration completed successfully!';
    RAISE NOTICE 'Table google_drive_folders is ready with soft delete support.';
END $$;

-- ========================================================================
-- PART 2: Add soft delete fields to drive_files table (if it exists)
-- ========================================================================
-- Note: drive_files table is created by pd-google backend via init_db.py
-- If it doesn't exist yet, these statements will be skipped gracefully.

-- Add soft delete columns to drive_files if table exists
DO $$ 
BEGIN
    -- Check if drive_files table exists
    IF EXISTS (
        SELECT 1 FROM information_schema.tables 
        WHERE table_name = 'drive_files'
    ) THEN
        RAISE NOTICE 'Found drive_files table, adding soft delete fields...';
        
        -- Add deleted_at column if missing
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns 
            WHERE table_name = 'drive_files' AND column_name = 'deleted_at'
        ) THEN
            ALTER TABLE drive_files ADD COLUMN deleted_at TIMESTAMP WITH TIME ZONE;
            RAISE NOTICE 'Added deleted_at to drive_files';
        ELSE
            RAISE NOTICE 'deleted_at already exists in drive_files';
        END IF;

        -- Add deleted_by column if missing
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns 
            WHERE table_name = 'drive_files' AND column_name = 'deleted_by'
        ) THEN
            ALTER TABLE drive_files ADD COLUMN deleted_by VARCHAR;
            RAISE NOTICE 'Added deleted_by to drive_files';
        ELSE
            RAISE NOTICE 'deleted_by already exists in drive_files';
        END IF;

        -- Add delete_reason column if missing
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns 
            WHERE table_name = 'drive_files' AND column_name = 'delete_reason'
        ) THEN
            ALTER TABLE drive_files ADD COLUMN delete_reason VARCHAR;
            RAISE NOTICE 'Added delete_reason to drive_files';
        ELSE
            RAISE NOTICE 'delete_reason already exists in drive_files';
        END IF;
        
        -- Create index on deleted_at for efficient filtering
        CREATE INDEX IF NOT EXISTS ix_drive_files_deleted_at ON drive_files (deleted_at);
        RAISE NOTICE 'Index created on drive_files.deleted_at';
        
        RAISE NOTICE '✅ drive_files table updated with soft delete support!';
    ELSE
        RAISE NOTICE 'ℹ️  drive_files table not found (will be created by init_db.py)';
    END IF;
END $$;

-- Display final success message
DO $$ 
BEGIN
    RAISE NOTICE '';
    RAISE NOTICE '========================================';
    RAISE NOTICE '✅ MIGRATION COMPLETED SUCCESSFULLY!';
    RAISE NOTICE '========================================';
    RAISE NOTICE 'Soft delete fields added to:';
    RAISE NOTICE '  - google_drive_folders ✓';
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'drive_files') THEN
        RAISE NOTICE '  - drive_files ✓';
    ELSE
        RAISE NOTICE '  - drive_files (pending init_db.py)';
    END IF;
    RAISE NOTICE '';
END $$;
