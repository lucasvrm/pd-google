-- Migration script to add soft delete fields to DriveFile and DriveFolder tables
-- Run this directly in the Supabase SQL Editor

-- Add soft delete fields to drive_files table
DO $$ 
BEGIN
    -- Add deleted_at column
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'drive_files' AND column_name = 'deleted_at'
    ) THEN
        ALTER TABLE drive_files ADD COLUMN deleted_at TIMESTAMP WITH TIME ZONE;
        RAISE NOTICE 'Added deleted_at to drive_files';
    ELSE
        RAISE NOTICE 'deleted_at already exists in drive_files';
    END IF;

    -- Add deleted_by column
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'drive_files' AND column_name = 'deleted_by'
    ) THEN
        ALTER TABLE drive_files ADD COLUMN deleted_by VARCHAR;
        RAISE NOTICE 'Added deleted_by to drive_files';
    ELSE
        RAISE NOTICE 'deleted_by already exists in drive_files';
    END IF;

    -- Add delete_reason column
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

-- Add soft delete fields to google_drive_folders table
DO $$ 
BEGIN
    -- Add deleted_at column
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'google_drive_folders' AND column_name = 'deleted_at'
    ) THEN
        ALTER TABLE google_drive_folders ADD COLUMN deleted_at TIMESTAMP WITH TIME ZONE;
        RAISE NOTICE 'Added deleted_at to google_drive_folders';
    ELSE
        RAISE NOTICE 'deleted_at already exists in google_drive_folders';
    END IF;

    -- Add deleted_by column
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'google_drive_folders' AND column_name = 'deleted_by'
    ) THEN
        ALTER TABLE google_drive_folders ADD COLUMN deleted_by VARCHAR;
        RAISE NOTICE 'Added deleted_by to google_drive_folders';
    ELSE
        RAISE NOTICE 'deleted_by already exists in google_drive_folders';
    END IF;

    -- Add delete_reason column
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

-- Create indexes for efficient querying of non-deleted items
CREATE INDEX IF NOT EXISTS ix_drive_files_deleted_at ON drive_files (deleted_at);
CREATE INDEX IF NOT EXISTS ix_google_drive_folders_deleted_at ON google_drive_folders (deleted_at);

-- Display success message
DO $$ 
BEGIN
    RAISE NOTICE '✅ Migration completed successfully!';
END $$;
