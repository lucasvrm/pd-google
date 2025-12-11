-- Migration to create lead_tags table for compatibility with existing ORM
-- tags table is assumed to exist (Supabase managed)

-- 1. Create lead_tags table
CREATE TABLE IF NOT EXISTS lead_tags (
    lead_id TEXT NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (lead_id, tag_id)
);

-- 2. Create index on tag_id for reverse lookups
CREATE INDEX IF NOT EXISTS idx_lead_tags_tag_id ON lead_tags(tag_id);
