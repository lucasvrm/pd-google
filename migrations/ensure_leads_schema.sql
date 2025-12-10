-- Idempotent script to ensure 'leads' table schema is correct for sales-view
-- Run this in Supabase SQL Editor

-- 1. Ensure 'leads' table exists
CREATE TABLE IF NOT EXISTS leads (
    id TEXT PRIMARY KEY,
    legal_name TEXT,
    trade_name TEXT,
    status TEXT,
    origin TEXT,
    owner_id TEXT, -- Assuming linked to auth.users or custom users table
    primary_contact_id TEXT,
    qualified_company_id TEXT,
    last_interaction_at TIMESTAMPTZ,
    priority_score INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. Add columns if they don't exist (Idempotent ALTER TABLE)
DO $$
BEGIN
    -- legal_name (mapped from title in code)
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='legal_name') THEN
        ALTER TABLE leads ADD COLUMN legal_name TEXT;
    END IF;

    -- priority_score
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='priority_score') THEN
        ALTER TABLE leads ADD COLUMN priority_score INTEGER DEFAULT 0;
    END IF;

    -- last_interaction_at
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='last_interaction_at') THEN
        ALTER TABLE leads ADD COLUMN last_interaction_at TIMESTAMPTZ;
    END IF;

    -- created_at
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='created_at') THEN
        ALTER TABLE leads ADD COLUMN created_at TIMESTAMPTZ DEFAULT NOW();
    END IF;

    -- updated_at
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='updated_at') THEN
        ALTER TABLE leads ADD COLUMN updated_at TIMESTAMPTZ DEFAULT NOW();
    END IF;

    -- owner_id
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='owner_id') THEN
        ALTER TABLE leads ADD COLUMN owner_id TEXT;
    END IF;

    -- status
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='status') THEN
        ALTER TABLE leads ADD COLUMN status TEXT;
    END IF;

    -- origin
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='origin') THEN
        ALTER TABLE leads ADD COLUMN origin TEXT;
    END IF;

END $$;

-- 3. Ensure 'lead_activity_stats' table exists
CREATE TABLE IF NOT EXISTS lead_activity_stats (
    lead_id TEXT PRIMARY KEY REFERENCES leads(id),
    engagement_score INTEGER DEFAULT 0,
    last_interaction_at TIMESTAMPTZ,
    last_email_at TIMESTAMPTZ,
    last_event_at TIMESTAMPTZ,
    total_emails INTEGER DEFAULT 0,
    total_events INTEGER DEFAULT 0,
    total_interactions INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 4. Add columns to lead_activity_stats if missing
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='lead_activity_stats' AND column_name='engagement_score') THEN
        ALTER TABLE lead_activity_stats ADD COLUMN engagement_score INTEGER DEFAULT 0;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='lead_activity_stats' AND column_name='last_interaction_at') THEN
        ALTER TABLE lead_activity_stats ADD COLUMN last_interaction_at TIMESTAMPTZ;
    END IF;
END $$;
