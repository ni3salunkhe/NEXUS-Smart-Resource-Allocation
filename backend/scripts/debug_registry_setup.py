import asyncio
import sys
import os
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

# Add root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from shared.config import get_settings

async def main():
    settings = get_settings()
    # Use sync connection for migration to avoid complex async issues with raw cursors
    from sqlalchemy import create_engine
    
    # Convert async url to sync
    sync_url = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
    engine = create_engine(sync_url)
    
    registry_sql = """
    -- REGISTRY ENUMS
    DO $$ BEGIN
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

    -- REGISTRY TABLES
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
    
    DO $$ BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'idx_households_geo') THEN
            CREATE INDEX idx_households_geo ON households USING GIST(location_geo);
        END IF;
    END $$;

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
    """

    with engine.connect() as conn:
        print("Applying Simplified Registry schema...")
        # Split by semicolon to avoid multi-statement parameter parsing issues
        # and escape colons manually where needed
        for statement in registry_sql.split(";"):
            stmt = statement.strip()
            if stmt:
                # Escape colons for SQLAlchemy
                stmt = stmt.replace(":", "\\:")
                conn.execute(text(stmt))
        conn.commit()
    
    print("Simplified Registry schema applied.")

if __name__ == "__main__":
    asyncio.run(main())
