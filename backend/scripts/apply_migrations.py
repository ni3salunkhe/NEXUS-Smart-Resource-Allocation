import asyncio
import sys
import os
from sqlalchemy.ext.asyncio import create_async_engine

# Add root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from shared.config import get_settings

async def main():
    settings = get_settings()
    # Use sync connection for migration to avoid complex async issues with raw cursors
    from sqlalchemy import create_engine, text
    
    # Convert async url to sync
    sync_url = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
    engine = create_engine(sync_url)
    
    foundation_sql = """
    -- FOUNDATION
    CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
    CREATE EXTENSION IF NOT EXISTS postgis;
    CREATE EXTENSION IF NOT EXISTS pg_trgm;
    CREATE EXTENSION IF NOT EXISTS pgcrypto;

    DO $$ BEGIN
        CREATE TYPE user_role AS ENUM (
            'field_worker','coordinator','ngo_admin',
            'funder_readonly','platform_admin'
        );
    EXCEPTION WHEN duplicate_object THEN NULL;
    END $$;

    CREATE TABLE IF NOT EXISTS tenants (
        tenant_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        name VARCHAR(255) NOT NULL,
        slug VARCHAR(100) NOT NULL UNIQUE,
        contact_email VARCHAR(255) NOT NULL,
        plan_tier VARCHAR(50) DEFAULT 'standard',
        cross_tenant_linking_policy VARCHAR(50) DEFAULT 'coordinator_only',
        settings JSONB DEFAULT '{}',
        active BOOLEAN DEFAULT TRUE,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    );
    ALTER TABLE tenants ENABLE ROW LEVEL SECURITY;

    CREATE TABLE IF NOT EXISTS users (
        user_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        tenant_id UUID REFERENCES tenants(tenant_id) ON DELETE CASCADE,
        email VARCHAR(255) NOT NULL,
        name_encrypted BYTEA,
        phone_encrypted BYTEA,
        role user_role NOT NULL,
        preferred_language VARCHAR(10) DEFAULT 'en',
        password_hash VARCHAR(255) NOT NULL,
        is_active BOOLEAN DEFAULT TRUE,
        last_login_at TIMESTAMP WITH TIME ZONE,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        UNIQUE(tenant_id, email)
    );
    ALTER TABLE users ENABLE ROW LEVEL SECURITY;

    CREATE TABLE IF NOT EXISTS audit_log (
        event_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        tenant_id UUID,
        user_id UUID,
        action VARCHAR(50) NOT NULL,
        resource_type VARCHAR(100) NOT NULL,
        resource_id UUID,
        before_snapshot JSONB,
        after_snapshot JSONB,
        ip_address INET,
        user_agent TEXT,
        request_id UUID,
        event_timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    );

    CREATE OR REPLACE FUNCTION fn_audit_trigger()
    RETURNS TRIGGER AS $$
    DECLARE
        v_action VARCHAR(50);
        v_before JSONB;
        v_after  JSONB;
        v_res_id UUID;
    BEGIN
        IF TG_OP = 'INSERT' THEN
            v_action := 'CREATE'; v_before := NULL; v_after := to_jsonb(NEW);
            v_res_id := (to_jsonb(NEW) ->> (TG_TABLE_NAME || '_id'))::UUID;
        ELSIF TG_OP = 'UPDATE' THEN
            v_action := 'UPDATE'; v_before := to_jsonb(OLD); v_after := to_jsonb(NEW);
            v_res_id := (to_jsonb(NEW) ->> (TG_TABLE_NAME || '_id'))::UUID;
        ELSIF TG_OP = 'DELETE' THEN
            v_action := 'DELETE'; v_before := to_jsonb(OLD); v_after := NULL;
            v_res_id := (to_jsonb(OLD) ->> (TG_TABLE_NAME || '_id'))::UUID;
        END IF;
        INSERT INTO audit_log(tenant_id, user_id, action, resource_type, resource_id, before_snapshot, after_snapshot)
        VALUES (
            NULLIF(current_setting('app.current_tenant_id', TRUE), '')::UUID,
            NULLIF(current_setting('app.current_user_id',   TRUE), '')::UUID,
            v_action, TG_TABLE_NAME, v_res_id, v_before, v_after
        );
        RETURN COALESCE(NEW, OLD);
    END;
    $$ LANGUAGE plpgsql SECURITY DEFINER;

    DO $$ BEGIN
        CREATE TRIGGER audit_users
        AFTER INSERT OR UPDATE OR DELETE ON users
        FOR EACH ROW EXECUTE FUNCTION fn_audit_trigger();
    EXCEPTION WHEN duplicate_object THEN NULL; END $$;

    CREATE OR REPLACE FUNCTION fn_set_updated_at()
    RETURNS TRIGGER AS $$
    BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
    $$ LANGUAGE plpgsql;

    DO $$ BEGIN
        CREATE TRIGGER set_updated_at_tenants BEFORE UPDATE ON tenants FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();
    EXCEPTION WHEN duplicate_object THEN NULL; END $$;

    DO $$ BEGIN
        CREATE TRIGGER set_updated_at_users BEFORE UPDATE ON users FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();
    EXCEPTION WHEN duplicate_object THEN NULL; END $$;
    """

    registry_sql = """
    -- REGISTRY
    DO $$ BEGIN
        CREATE TYPE dwelling_type_enum AS ENUM ('permanent','semi_permanent','temporary','open_space');
        CREATE TYPE economic_tier_enum AS ENUM ('below_poverty','marginal','low','medium');
        CREATE TYPE household_status_enum AS ENUM ('active','relocated','dissolved','merged_away','opted_out');
        CREATE TYPE member_role_enum AS ENUM ('head','spouse','child','parent','dependent','other');
        CREATE TYPE age_bracket_enum AS ENUM ('infant','child','youth','adult','elderly');
        CREATE TYPE gender_enum AS ENUM ('male','female','non_binary','prefer_not_to_say');
        CREATE TYPE consent_type_enum AS ENUM ('data_collection','location_sharing','cross_org_linking','analytics','photo');
        CREATE TYPE consent_method_enum AS ENUM ('verbal_witnessed','signed_form','digital_app');
        CREATE TYPE link_method_enum AS ENUM ('auto_matched','coordinator_confirmed','household_confirmed');
        CREATE TYPE link_status_enum AS ENUM ('proposed','active','rejected','revoked');
        CREATE TYPE hh_event_type_enum AS ENUM (
            'need_reported','need_resolved','task_dispatched','task_completed',
            'member_added','member_removed','vulnerability_updated','consent_changed',
            'assistance_received','location_updated','merged','linked','opted_out'
        );
    EXCEPTION WHEN duplicate_object THEN NULL; END $$;

    CREATE TABLE IF NOT EXISTS households (
        household_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        global_household_id UUID,
        tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
        ward_id VARCHAR(64),
        location TEXT,
        location_confidence FLOAT DEFAULT 0.5,
        location_description TEXT,
        landmark_tags TEXT[] DEFAULT '{}',
        dwelling_type dwelling_type_enum,
        total_members INTEGER DEFAULT 0,
        vulnerability_score FLOAT DEFAULT 0.0,
        vulnerability_flags JSONB DEFAULT '{"has_child":false,"has_elderly":false,"has_disabled":false,"has_pregnant":false,"chronic_illness":false,"single_parent":false}',
        economic_tier economic_tier_enum,
        total_needs_reported INTEGER DEFAULT 0,
        total_tasks_completed INTEGER DEFAULT 0,
        last_need_reported_at TIMESTAMP WITH TIME ZONE,
        last_assistance_at TIMESTAMP WITH TIME ZONE,
        total_assistance_value NUMERIC(12, 2) DEFAULT 0.00,
        assistance_categories TEXT[] DEFAULT '{}',
        crisis_frequency FLOAT DEFAULT 0.0,
        status household_status_enum DEFAULT 'active',
        merged_into UUID,
        merge_reason TEXT,
        data_quality_score FLOAT DEFAULT 0.5,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        created_by UUID REFERENCES users(user_id) ON DELETE SET NULL,
        location_geo GEOGRAPHY(POINT, 4326)
    );
    ALTER TABLE households ENABLE ROW LEVEL SECURITY;

    CREATE TABLE IF NOT EXISTS household_members (
        member_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        household_id UUID NOT NULL REFERENCES households(household_id) ON DELETE CASCADE,
        role_in_household member_role_enum,
        age_bracket age_bracket_enum,
        gender gender_enum,
        is_primary_contact BOOLEAN DEFAULT FALSE,
        vulnerability_flags JSONB DEFAULT '{"disabled":false,"chronic_illness":false,"pregnant":false,"malnourished":false,"mental_health":false}',
        pii_ref UUID,
        is_present BOOLEAN DEFAULT TRUE,
        added_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        removed_at TIMESTAMP WITH TIME ZONE,
        added_by UUID REFERENCES users(user_id) ON DELETE SET NULL
    );
    ALTER TABLE household_members ENABLE ROW LEVEL SECURITY;

    CREATE OR REPLACE FUNCTION fn_recompute_member_count()
    RETURNS TRIGGER AS $$
    BEGIN
        UPDATE households
        SET total_members = (
            SELECT COUNT(*) FROM household_members
            WHERE household_id = COALESCE(NEW.household_id, OLD.household_id)
            AND removed_at IS NULL
        ),
        updated_at = NOW()
        WHERE household_id = COALESCE(NEW.household_id, OLD.household_id);
        RETURN COALESCE(NEW, OLD);
    END;
    $$ LANGUAGE plpgsql;

    DO $$ BEGIN
        CREATE TRIGGER trg_recompute_member_count AFTER INSERT OR UPDATE OR DELETE ON household_members FOR EACH ROW EXECUTE FUNCTION fn_recompute_member_count();
    EXCEPTION WHEN duplicate_object THEN NULL; END $$;

    CREATE OR REPLACE FUNCTION fn_recompute_vulnerability()
    RETURNS TRIGGER AS $$
    DECLARE
        v_hh_id UUID := COALESCE(NEW.household_id, OLD.household_id);
        v_score  FLOAT := 0.0;
        v_flags  JSONB := '{}'::JSONB;
    BEGIN
        SELECT
            LEAST(1.0,
                (CASE WHEN bool_or((vulnerability_flags->>'disabled')::bool)    THEN 0.25 ELSE 0 END) +
                (CASE WHEN bool_or((vulnerability_flags->>'pregnant')::bool)    THEN 0.20 ELSE 0 END) +
                (CASE WHEN bool_or((vulnerability_flags->>'malnourished')::bool) THEN 0.25 ELSE 0 END) +
                (CASE WHEN bool_or((vulnerability_flags->>'mental_health')::bool) THEN 0.15 ELSE 0 END) +
                (CASE WHEN bool_or((vulnerability_flags->>'chronic_illness')::bool) THEN 0.15 ELSE 0 END)
            ),
            jsonb_build_object(
                'has_child',     bool_or(age_bracket = 'child' OR age_bracket = 'infant'),
                'has_elderly',   bool_or(age_bracket = 'elderly'),
                'has_disabled',  bool_or((vulnerability_flags->>'disabled')::bool),
                'has_pregnant',  bool_or((vulnerability_flags->>'pregnant')::bool),
                'chronic_illness', bool_or((vulnerability_flags->>'chronic_illness')::bool),
                'single_parent', (
                    COUNT(*) FILTER (WHERE role_in_household = 'head') = 1
                    AND COUNT(*) FILTER (WHERE age_bracket IN ('child','infant')) > 0
                )
            )
        INTO v_score, v_flags
        FROM household_members
        WHERE household_id = v_hh_id AND removed_at IS NULL;

        UPDATE households
        SET vulnerability_score = COALESCE(v_score, 0.0),
            vulnerability_flags = COALESCE(v_flags, '{}'::JSONB),
            updated_at = NOW()
        WHERE household_id = v_hh_id;
        RETURN COALESCE(NEW, OLD);
    END;
    $$ LANGUAGE plpgsql;

    DO $$ BEGIN
        CREATE TRIGGER trg_recompute_vulnerability AFTER INSERT OR UPDATE OR DELETE ON household_members FOR EACH ROW EXECUTE FUNCTION fn_recompute_vulnerability();
    EXCEPTION WHEN duplicate_object THEN NULL; END $$;
    """

    with engine.connect() as conn:
        print("Applying Foundation schema...")
        conn.execute(text(foundation_sql))
        print("Applying Registry schema...")
        conn.execute(text(registry_sql))
        conn.commit()
    
    print("All migrations applied successfully via sync driver.")

if __name__ == "__main__":
    asyncio.run(main())
