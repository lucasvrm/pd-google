-- Migration to create entity_tags table for polymorphic tag associations
-- This table is the source of truth for entity-tag relationships used by the frontend
-- tags table is assumed to exist (Supabase managed)

-- 1. Create entity_tags table
-- Using UUID for entity_id to match Supabase entity types (leads.id, deals.id, etc.)
-- Using UUID for tag_id to match Supabase tags.id type
CREATE TABLE IF NOT EXISTS entity_tags (
    id SERIAL PRIMARY KEY,
    entity_type TEXT NOT NULL,
    entity_id UUID NOT NULL,
    tag_id UUID NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    UNIQUE (entity_type, entity_id, tag_id)
);

-- 2. Create indexes for efficient lookups
CREATE INDEX IF NOT EXISTS idx_entity_tags_entity_type ON entity_tags(entity_type);
CREATE INDEX IF NOT EXISTS idx_entity_tags_entity_id ON entity_tags(entity_id);
CREATE INDEX IF NOT EXISTS idx_entity_tags_tag_id ON entity_tags(tag_id);
CREATE INDEX IF NOT EXISTS idx_entity_tags_composite ON entity_tags(entity_type, entity_id);
