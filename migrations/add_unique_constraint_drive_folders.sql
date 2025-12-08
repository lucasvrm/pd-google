-- Migration: Add unique constraint to google_drive_folders table
-- This ensures that each entity (company, lead, deal) can only have one folder mapping
-- preventing duplicate folder creation during concurrent requests.

-- Step 1: Delete duplicate records, keeping only the oldest record for each (entity_type, entity_id) pair
-- This uses a Common Table Expression (CTE) to identify duplicates
WITH duplicates AS (
    SELECT 
        id,
        entity_type,
        entity_id,
        ROW_NUMBER() OVER (
            PARTITION BY entity_type, entity_id 
            ORDER BY created_at ASC, id ASC
        ) AS row_num
    FROM google_drive_folders
)
DELETE FROM google_drive_folders
WHERE id IN (
    SELECT id 
    FROM duplicates 
    WHERE row_num > 1
);

-- Step 2: Create unique index on (entity_type, entity_id) to prevent future duplicates
-- This ensures database-level enforcement of the uniqueness constraint
CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_entity_mapping 
ON google_drive_folders (entity_type, entity_id);

-- Note: The constraint name follows PostgreSQL naming conventions
-- For SQLite compatibility, we use CREATE UNIQUE INDEX instead of ALTER TABLE ADD CONSTRAINT
