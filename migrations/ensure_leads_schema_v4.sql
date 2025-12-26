-- Updated idempotent script to align local schema with live leads & reference tables
-- Adds system_settings table for lead_priority_config and priority_weight columns
-- Run this in local Postgres when you want an environment aligned with Supabase.

-- 1. Ensure lookup tables exist ---------------------------------------------
CREATE TABLE IF NOT EXISTS lead_statuses (
    id TEXT PRIMARY KEY,
    code TEXT UNIQUE,
    label TEXT,
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    sort_order INTEGER DEFAULT 0,
    priority_weight INTEGER DEFAULT 12,  -- NEW: Weight for priority calculation
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS lead_origins (
    id TEXT PRIMARY KEY,
    code TEXT UNIQUE,
    label TEXT,
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    sort_order INTEGER DEFAULT 0,
    priority_weight INTEGER DEFAULT 10,  -- NEW: Weight for priority calculation
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
    qualified_at TIMESTAMPTZ,
    deleted_at TIMESTAMPTZ,
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 4. Ensure system_settings table exists (NEW) -------------------------------
CREATE TABLE IF NOT EXISTS system_settings (
    key TEXT PRIMARY KEY,
    value JSONB NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 5. Seed default lead_priority_config (NEW) ---------------------------------
-- This config matches the default hardcoded behavior
INSERT INTO system_settings (key, value, description)
VALUES (
    'lead_priority_config',
    '{
        "weights": {
            "status": {
                "new": 18,
                "contacted": 22,
                "qualified": 26,
                "proposal": 28,
                "won": 30,
                "lost": 5
            },
            "origin": {
                "inbound": 20,
                "referral": 18,
                "partner": 16,
                "event": 15,
                "outbound": 12
            },
            "recency_max": 30.0,
            "recency_decay_rate": 0.5,
            "engagement_multiplier": 0.2
        },
        "thresholds": {
            "hot": 70,
            "warm": 40
        }
    }'::jsonb,
    'Lead priority calculation configuration with weights and thresholds'
)
ON CONFLICT (key) DO NOTHING;

-- 6. Seed default lead statuses with priority weights (if empty) -------------
INSERT INTO lead_statuses (id, code, label, sort_order, priority_weight)
VALUES
    ('new', 'new', 'Novo', 1, 18),
    ('contacted', 'contacted', 'Contatado', 2, 22),
    ('qualified', 'qualified', 'Qualificado', 3, 26),
    ('proposal', 'proposal', 'Proposta', 4, 28),
    ('won', 'won', 'Ganho', 5, 30),
    ('lost', 'lost', 'Perdido', 6, 5)
ON CONFLICT (id) DO NOTHING;

-- 7. Seed default lead origins with priority weights (if empty) --------------
INSERT INTO lead_origins (id, code, label, sort_order, priority_weight)
VALUES
    ('inbound', 'inbound', 'Inbound', 1, 20),
    ('referral', 'referral', 'Indicação', 2, 18),
    ('partner', 'partner', 'Parceiro', 3, 16),
    ('event', 'event', 'Evento', 4, 15),
    ('outbound', 'outbound', 'Outbound', 5, 12)
ON CONFLICT (id) DO NOTHING;

-- 8. Add indexes for performance --------------------------------------------
CREATE INDEX IF NOT EXISTS idx_leads_priority_score ON leads(priority_score);
CREATE INDEX IF NOT EXISTS idx_leads_last_interaction ON leads(last_interaction_at);
CREATE INDEX IF NOT EXISTS idx_leads_deleted_at ON leads(deleted_at);
CREATE INDEX IF NOT EXISTS idx_leads_qualified_at ON leads(qualified_at);
