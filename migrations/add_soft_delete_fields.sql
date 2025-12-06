-- Migration script to add soft delete fields to DriveFile and DriveFolder tables
-- Run this directly in the Supabase SQL Editor
-- This script will create tables if they don't exist, or add missing columns if they do

-- Create drive_files table if it doesn't exist
CREATE TABLE IF NOT EXISTS drive_files (
    id SERIAL PRIMARY KEY,
    file_id VARCHAR UNIQUE NOT NULL,
    parent_folder_id VARCHAR,
    name VARCHAR,
    mime_type VARCHAR,
    size INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    deleted_at TIMESTAMP WITH TIME ZONE,
    deleted_by VARCHAR,
    delete_reason VARCHAR
);

-- Create indexes for drive_files
CREATE INDEX IF NOT EXISTS ix_drive_files_file_id ON drive_files (file_id);
CREATE INDEX IF NOT EXISTS ix_drive_files_parent_folder_id ON drive_files (parent_folder_id);
CREATE INDEX IF NOT EXISTS ix_drive_files_deleted_at ON drive_files (deleted_at);

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

-- If tables already existed, add missing soft delete columns to drive_files
DO $$ 
BEGIN
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
END $$;

-- If tables already existed, add missing soft delete columns to google_drive_folders
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
    RAISE NOTICE 'Tables drive_files and google_drive_folders are ready with soft delete support.';
END $$;
