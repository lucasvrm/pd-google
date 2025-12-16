-- Migration: Create qualify_lead RPC function for Supabase
-- Purpose: Provides a stored procedure to qualify leads, setting qualified_at and deleted_at,
--          and logging the action to the audit_logs table.
-- Date: 2025-12-16

-- ============================================================================
-- 1. Add qualified_at column to leads table (if not exists)
-- ============================================================================
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'leads' AND column_name = 'qualified_at'
    ) THEN
        ALTER TABLE leads ADD COLUMN qualified_at TIMESTAMPTZ;
    END IF;
END $$;

-- Create index for qualified_at column (idempotent)
CREATE INDEX IF NOT EXISTS idx_leads_qualified_at ON leads(qualified_at);

-- ============================================================================
-- 2. Create or Replace the qualify_lead RPC function
-- ============================================================================
-- This function qualifies a lead by:
--   1. Setting qualified_at to current timestamp
--   2. Setting deleted_at to current timestamp (soft delete for qualified leads)
--   3. Optionally updating qualified_company_id if company data is provided
--   4. Creating an audit log entry with action 'qualify_lead'
--
-- Parameters:
--   p_lead_id: UUID of the lead to qualify
--   p_new_company_data: JSONB with optional company data (can include qualified_company_id)
--   p_user_id: UUID of the user performing the qualification
--
-- Returns: VOID
-- Raises: Exception if lead not found or already qualified
-- ============================================================================

CREATE OR REPLACE FUNCTION qualify_lead(
    p_lead_id UUID,
    p_new_company_data JSONB,
    p_user_id UUID
)
RETURNS VOID
LANGUAGE plpgsql
AS $$
DECLARE
    v_lead_exists BOOLEAN;
    v_already_qualified BOOLEAN;
    v_qualified_company_id TEXT;
    v_old_values JSONB;
    v_new_values JSONB;
    v_now TIMESTAMPTZ := NOW();
BEGIN
    -- Check if lead exists
    SELECT EXISTS(SELECT 1 FROM leads WHERE id = p_lead_id::TEXT) INTO v_lead_exists;
    IF NOT v_lead_exists THEN
        RAISE EXCEPTION 'Lead with id % not found', p_lead_id;
    END IF;

    -- Check if already qualified (has qualified_at or deleted_at set)
    SELECT (qualified_at IS NOT NULL OR deleted_at IS NOT NULL)
    INTO v_already_qualified
    FROM leads
    WHERE id = p_lead_id::TEXT;

    IF v_already_qualified THEN
        RAISE EXCEPTION 'Lead % is already qualified or deleted', p_lead_id;
    END IF;

    -- Extract qualified_company_id from company data if provided
    IF p_new_company_data IS NOT NULL AND p_new_company_data ? 'qualified_company_id' THEN
        v_qualified_company_id := p_new_company_data->>'qualified_company_id';
    END IF;

    -- Capture old values for audit log
    SELECT jsonb_build_object(
        'qualified_at', qualified_at,
        'deleted_at', deleted_at,
        'qualified_company_id', qualified_company_id
    ) INTO v_old_values
    FROM leads
    WHERE id = p_lead_id::TEXT;

    -- Update the lead: set qualified_at and deleted_at simultaneously
    UPDATE leads
    SET qualified_at = v_now,
        deleted_at = v_now,
        qualified_company_id = COALESCE(v_qualified_company_id, qualified_company_id),
        updated_at = v_now
    WHERE id = p_lead_id::TEXT;

    -- Build new values for audit log
    v_new_values := jsonb_build_object(
        'qualified_at', jsonb_build_object('old', v_old_values->>'qualified_at', 'new', v_now::TEXT),
        'deleted_at', jsonb_build_object('old', v_old_values->>'deleted_at', 'new', v_now::TEXT)
    );

    -- Add company data to changes if provided
    IF v_qualified_company_id IS NOT NULL THEN
        v_new_values := v_new_values || jsonb_build_object(
            'qualified_company_id', jsonb_build_object(
                'old', v_old_values->>'qualified_company_id',
                'new', v_qualified_company_id
            )
        );
    END IF;

    -- Insert audit log entry
    INSERT INTO audit_logs (
        entity_type,
        entity_id,
        actor_id,
        action,
        changes,
        timestamp
    ) VALUES (
        'lead',
        p_lead_id::TEXT,
        p_user_id::TEXT,
        'qualify_lead',
        v_new_values,
        v_now
    );

    -- All operations within this function run in a single transaction.
    -- If any step fails, PostgreSQL automatically rolls back all changes.
END;
$$;

-- ============================================================================
-- 3. Grant execute permission to authenticated users (Supabase pattern)
-- ============================================================================
-- Note: Adjust the role name based on your Supabase setup.
-- Common roles: authenticated, anon, service_role
-- ============================================================================

-- Grant to authenticated users (typical Supabase setup)
GRANT EXECUTE ON FUNCTION qualify_lead(UUID, JSONB, UUID) TO authenticated;

-- Grant to service_role for backend calls
GRANT EXECUTE ON FUNCTION qualify_lead(UUID, JSONB, UUID) TO service_role;

-- ============================================================================
-- USAGE EXAMPLES:
-- ============================================================================
-- 
-- 1. Basic qualification (no company data):
--    SELECT qualify_lead(
--        'lead-uuid-here'::UUID,
--        NULL,
--        'user-uuid-here'::UUID
--    );
--
-- 2. Qualification with company association:
--    SELECT qualify_lead(
--        'lead-uuid-here'::UUID,
--        '{"qualified_company_id": "company-uuid-here"}'::JSONB,
--        'user-uuid-here'::UUID
--    );
--
-- 3. Test via Supabase Console:
--    In SQL Editor, run:
--    SELECT qualify_lead(
--        (SELECT id FROM leads LIMIT 1)::UUID,
--        '{"qualified_company_id": null}'::JSONB,
--        (SELECT id FROM users LIMIT 1)::UUID
--    );
--
-- ============================================================================
-- ROLLBACK SCRIPT (if needed):
-- ============================================================================
-- 
-- DROP FUNCTION IF EXISTS qualify_lead(UUID, JSONB, UUID);
-- ALTER TABLE leads DROP COLUMN IF EXISTS qualified_at;
-- DROP INDEX IF EXISTS idx_leads_qualified_at;
--
