-- Updated idempotent script to align local schema with live leads & reference tables
-- Run this in local Postgres when you quiser ter um ambiente parecido com o Supabase.

-- 1. Ensure lookup tables exist ---------------------------------------------
CREATE TABLE IF NOT EXISTS lead_statuses (
    id TEXT PRIMARY KEY,
    code TEXT UNIQUE,
    label TEXT,
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS lead_origins (
    id TEXT PRIMARY KEY,
    code TEXT UNIQUE,
    label TEXT,
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. Ensure master_deals table exists for FK references (minimal stub) ------
CREATE TABLE IF NOT EXISTS master_deals (
    id TEXT PRIMARY KEY,
    client_name TEXT
);

-- 3. Ensure leads table exists with new columns ------------------------------
CREATE TABLE IF NOT EXISTS leads (
    id TEXT PRIMARY KEY,
    legal_name TEXT,
    trade_name TEXT,
    lead_status_id TEXT REFERENCES lead_statuses(id),
    lead_origin_id TEXT REFERENCES lead_origins(id),
    owner_user_id TEXT,
    qualified_company_id TEXT,
    qualified_master_deal_id TEXT REFERENCES master_deals(id),
    address_city TEXT,
    address_state TEXT,
    last_interaction_at TIMESTAMPTZ,
    priority_score INTEGER DEFAULT 0,
    disqualified_at TIMESTAMPTZ,
    disqualification_reason TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 4. Add or adjust columns idempotently -------------------------------------
DO $$
BEGIN
    -- New/renamed columns
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='lead_status_id') THEN
        ALTER TABLE leads ADD COLUMN lead_status_id TEXT REFERENCES lead_statuses(id);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='lead_origin_id') THEN
        ALTER TABLE leads ADD COLUMN lead_origin_id TEXT REFERENCES lead_origins(id);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='owner_user_id') THEN
        ALTER TABLE leads ADD COLUMN owner_user_id TEXT;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='qualified_master_deal_id') THEN
        ALTER TABLE leads ADD COLUMN qualified_master_deal_id TEXT REFERENCES master_deals(id);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='address_city') THEN
        ALTER TABLE leads ADD COLUMN address_city TEXT;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='address_state') THEN
        ALTER TABLE leads ADD COLUMN address_state TEXT;
    END IF;

    -- Disqualification tracking columns
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='disqualified_at') THEN
        ALTER TABLE leads ADD COLUMN disqualified_at TIMESTAMPTZ;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='disqualification_reason') THEN
        ALTER TABLE leads ADD COLUMN disqualification_reason TEXT;
    END IF;

    -- Legacy columns to drop if present
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='owner_id') THEN
        ALTER TABLE leads DROP COLUMN owner_id;
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='primary_contact_id') THEN
        ALTER TABLE leads DROP COLUMN primary_contact_id;
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='status') THEN
        ALTER TABLE leads DROP COLUMN status;
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='origin') THEN
        ALTER TABLE leads DROP COLUMN origin;
    END IF;
END $$;

-- 5. Ensure lead_activity_stats still present --------------------------------
CREATE TABLE IF NOT EXISTS lead_activity_stats (
    lead_id TEXT PRIMARY KEY REFERENCES leads(id),
    engagement_score INTEGER DEFAULT 0,
    last_interaction_at TIMESTAMPTZ,
    last_email_at TIMESTAMPTZ,
    last_event_at TIMESTAMPTZ,
    next_scheduled_event_at TIMESTAMPTZ,
    total_emails INTEGER DEFAULT 0,
    total_events INTEGER DEFAULT 0,
    total_interactions INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 6. Add columns to lead_activity_stats idempotently --------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='lead_activity_stats' AND column_name='next_scheduled_event_at') THEN
        ALTER TABLE lead_activity_stats ADD COLUMN next_scheduled_event_at TIMESTAMPTZ;
    END IF;
END $$;

-- 7. Create indexes for new columns (idempotent) ------------------------------
CREATE INDEX IF NOT EXISTS idx_leads_disqualified_at ON leads(disqualified_at);
CREATE INDEX IF NOT EXISTS idx_lead_activity_stats_next_scheduled_event_at ON lead_activity_stats(next_scheduled_event_at);
