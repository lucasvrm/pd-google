-- Migration to create lead_tags table for compatibility with existing ORM
-- tags table is assumed to exist (Supabase managed)

-- 1. Create lead_tags table
-- Using UUID for lead_id to match Supabase leads.id type
-- Using UUID for tag_id to match Supabase tags.id type
CREATE TABLE IF NOT EXISTS lead_tags (
    lead_id UUID NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    tag_id UUID NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (lead_id, tag_id)
);

-- 2. Create index on tag_id for reverse lookups
CREATE INDEX IF NOT EXISTS idx_lead_tags_tag_id ON lead_tags(tag_id);
