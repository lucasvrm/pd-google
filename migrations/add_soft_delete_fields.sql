-- Migration script for Supabase database
-- Run this directly in the Supabase SQL Editor
-- 
-- IMPORTANT: This script only handles google_drive_folders table in Supabase.
-- The drive_files table is managed in the pd-google backend database.

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
    RAISE NOTICE 'Table google_drive_folders is ready with soft delete support in Supabase.';
END $$;
