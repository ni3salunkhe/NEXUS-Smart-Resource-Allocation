-- NEXUS Phase 0.5 Baseline Schema
-- Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Enums
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'user_role') THEN
        CREATE TYPE user_role AS ENUM ('field_worker','coordinator','ngo_admin','funder_readonly','platform_admin');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'dwelling_type_enum') THEN
        CREATE TYPE dwelling_type_enum AS ENUM ('permanent','semi_permanent','temporary','open_space');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'economic_tier_enum') THEN
        CREATE TYPE economic_tier_enum AS ENUM ('below_poverty','marginal','low','medium');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'household_status_enum') THEN
        CREATE TYPE household_status_enum AS ENUM ('active','relocated','dissolved','merged_away','opted_out');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'member_role_enum') THEN
        CREATE TYPE member_role_enum AS ENUM ('head','spouse','child','parent','dependent','other');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'age_bracket_enum') THEN
        CREATE TYPE age_bracket_enum AS ENUM ('infant','child','youth','adult','elderly');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'gender_enum') THEN
        CREATE TYPE gender_enum AS ENUM ('male','female','non_binary','prefer_not_to_say');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'consent_type_enum') THEN
        CREATE TYPE consent_type_enum AS ENUM ('data_collection','location_sharing','cross_org_linking','analytics','photo');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'consent_method_enum') THEN
        CREATE TYPE consent_method_enum AS ENUM ('verbal_witnessed','signed_form','digital_app');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'link_method_enum') THEN
        CREATE TYPE link_method_enum AS ENUM ('auto_matched','coordinator_confirmed','household_confirmed');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'link_status_enum') THEN
        CREATE TYPE link_status_enum AS ENUM ('proposed','active','rejected','revoked');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'hh_event_type_enum') THEN
        CREATE TYPE hh_event_type_enum AS ENUM (
            'need_reported','need_resolved','task_dispatched','task_completed',
            'member_added','member_removed','vulnerability_updated','consent_changed',
            'assistance_received','location_updated','merged','linked','opted_out'
        );
    END IF;
END $$;

-- Tables
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

CREATE TABLE IF NOT EXISTS household_history (
    event_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    household_id UUID NOT NULL REFERENCES households(household_id) ON DELETE CASCADE,
    event_type hh_event_type_enum NOT NULL,
    event_timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    event_payload JSONB DEFAULT '{}',
    related_need_id UUID,
    related_task_id UUID,
    triggered_by UUID REFERENCES users(user_id) ON DELETE SET NULL,
    tenant_id UUID NOT NULL REFERENCES tenants(tenant_id)
);

-- RLS Policies
ALTER TABLE tenants ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_view_self ON tenants USING (tenant_id = current_setting('app.current_tenant_id', TRUE)::UUID OR current_setting('app.current_role', TRUE) = 'platform_admin');

ALTER TABLE users ENABLE ROW LEVEL SECURITY;
CREATE POLICY users_isolation ON users USING (tenant_id = current_setting('app.current_tenant_id', TRUE)::UUID OR current_setting('app.current_role', TRUE) = 'platform_admin');

ALTER TABLE households ENABLE ROW LEVEL SECURITY;
CREATE POLICY households_isolation ON households USING (tenant_id = current_setting('app.current_tenant_id', TRUE)::UUID OR current_setting('app.current_role', TRUE) = 'platform_admin');

ALTER TABLE household_members ENABLE ROW LEVEL SECURITY;
CREATE POLICY members_isolation ON household_members USING (household_id IN (SELECT household_id FROM households WHERE tenant_id = current_setting('app.current_tenant_id', TRUE)::UUID) OR current_setting('app.current_role', TRUE) = 'platform_admin');

ALTER TABLE household_history ENABLE ROW LEVEL SECURITY;
CREATE POLICY history_isolation ON household_history USING (tenant_id = current_setting('app.current_tenant_id', TRUE)::UUID OR current_setting('app.current_role', TRUE) = 'platform_admin');

-- Audit Triggers (if audit_log exists)
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
    CREATE TRIGGER audit_households AFTER INSERT OR UPDATE OR DELETE ON households FOR EACH ROW EXECUTE FUNCTION fn_audit_trigger();
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- Append-only rules for history (security logic)
CREATE RULE hh_history_no_update AS ON UPDATE TO household_history DO INSTEAD NOTHING;
CREATE RULE hh_history_no_delete AS ON DELETE TO household_history DO INSTEAD NOTHING;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'idx_households_geo') THEN
        CREATE INDEX idx_households_geo ON households USING GIST(location_geo);
    END IF;
END $$;
