import psycopg2, os, sys
sys.path.insert(0, '.')
from shared.config import get_settings

s = get_settings()
url = s.DATABASE_URL.replace('postgresql+asyncpg://', 'postgresql://')
conn = psycopg2.connect(url)
conn.autocommit = True
cur = conn.cursor()

sql = """
    DO $$ BEGIN
        CREATE TYPE source_type_enum AS ENUM ('paper','whatsapp','mobile','sms','csv','webhook','audio');
    EXCEPTION WHEN duplicate_object THEN NULL; END $$;

    DO $$ BEGIN
        CREATE TYPE need_category_enum AS ENUM ('food','health','shelter','education','livelihood','water','mental_health','legal','hygiene','other');
    EXCEPTION WHEN duplicate_object THEN NULL; END $$;

    DO $$ BEGIN
        CREATE TYPE need_status_enum AS ENUM ('unverified','verified','assigned','in_progress','resolved','closed','duplicate');
    EXCEPTION WHEN duplicate_object THEN NULL; END $$;

    DO $$ BEGIN
        CREATE TYPE review_status_enum AS ENUM ('pending','approved','rejected','needs_info');
    EXCEPTION WHEN duplicate_object THEN NULL; END $$;

    DO $$ BEGIN
        CREATE TYPE ingestion_status_enum AS ENUM ('received','processing','processed','failed','duplicate');
    EXCEPTION WHEN duplicate_object THEN NULL; END $$;

    CREATE TABLE IF NOT EXISTS ingestion_raw (
        raw_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        tenant_id UUID NOT NULL REFERENCES tenants(tenant_id),
        source_type source_type_enum NOT NULL,
        s3_key TEXT,
        raw_text TEXT,
        raw_metadata JSONB DEFAULT '{}',
        submitted_by UUID REFERENCES users(user_id) ON DELETE SET NULL,
        submitted_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        status ingestion_status_enum DEFAULT 'received',
        processing_error TEXT,
        ocr_text TEXT,
        nlp_output JSONB,
        processed_at TIMESTAMP WITH TIME ZONE,
        correlation_id UUID
    );

    CREATE TABLE IF NOT EXISTS need_records (
        need_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        tenant_id UUID NOT NULL REFERENCES tenants(tenant_id),
        household_id UUID REFERENCES households(household_id) ON DELETE SET NULL,
        raw_id UUID REFERENCES ingestion_raw(raw_id) ON DELETE SET NULL,
        source_type source_type_enum NOT NULL,
        s3_raw_ref TEXT,
        reported_by UUID REFERENCES users(user_id) ON DELETE SET NULL,
        reported_at TIMESTAMP WITH TIME ZONE,
        ingested_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        location_point GEOGRAPHY(POINT, 4326),
        ward_id VARCHAR(64),
        category need_category_enum,
        subcategory TEXT,
        description TEXT,
        description_original TEXT,
        language_detected VARCHAR(10),
        severity_score FLOAT DEFAULT 0.5,
        urgency_score FLOAT DEFAULT 0.5,
        beneficiary_count INTEGER DEFAULT 1,
        vulnerability_flags JSONB DEFAULT '{}',
        nlp_confidence FLOAT DEFAULT 0.0,
        nlp_entities JSONB DEFAULT '{}',
        geocoding_confidence FLOAT DEFAULT 0.0,
        household_resolution VARCHAR(50),
        status need_status_enum DEFAULT 'unverified',
        assigned_task_id UUID,
        verified_by UUID REFERENCES users(user_id) ON DELETE SET NULL,
        verified_at TIMESTAMP WITH TIME ZONE,
        duplicate_of UUID,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS review_queue (
        review_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        tenant_id UUID NOT NULL REFERENCES tenants(tenant_id),
        raw_id UUID REFERENCES ingestion_raw(raw_id),
        need_id UUID REFERENCES need_records(need_id),
        review_type VARCHAR(50) NOT NULL,
        review_data JSONB DEFAULT '{}',
        status review_status_enum DEFAULT 'pending',
        assigned_to UUID REFERENCES users(user_id) ON DELETE SET NULL,
        reviewed_by UUID REFERENCES users(user_id) ON DELETE SET NULL,
        review_notes TEXT,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        resolved_at TIMESTAMP WITH TIME ZONE,
        priority INTEGER DEFAULT 5
    );

    CREATE TABLE IF NOT EXISTS geocoding_cache (
        cache_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        input_text TEXT NOT NULL UNIQUE,
        latitude FLOAT,
        longitude FLOAT,
        confidence FLOAT DEFAULT 0.0,
        ward_id VARCHAR(64),
        resolved_by VARCHAR(50),
        hit_count INTEGER DEFAULT 1,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        last_used_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    );

    ALTER TABLE ingestion_raw ENABLE ROW LEVEL SECURITY;
    DO $$ BEGIN
        CREATE POLICY ingestion_raw_tenant ON ingestion_raw USING (
            tenant_id = current_setting('app.current_tenant_id', TRUE)::UUID
            OR current_setting('app.current_role', TRUE) = 'platform_admin'
        );
    EXCEPTION WHEN duplicate_object THEN NULL; END $$;

    ALTER TABLE need_records ENABLE ROW LEVEL SECURITY;
    DO $$ BEGIN
        CREATE POLICY need_records_tenant ON need_records USING (
            tenant_id = current_setting('app.current_tenant_id', TRUE)::UUID
            OR current_setting('app.current_role', TRUE) = 'platform_admin'
        );
    EXCEPTION WHEN duplicate_object THEN NULL; END $$;

    ALTER TABLE review_queue ENABLE ROW LEVEL SECURITY;
    DO $$ BEGIN
        CREATE POLICY review_queue_tenant ON review_queue USING (
            tenant_id = current_setting('app.current_tenant_id', TRUE)::UUID
            OR current_setting('app.current_role', TRUE) = 'platform_admin'
        );
    EXCEPTION WHEN duplicate_object THEN NULL; END $$;
"""

try:
    cur.execute(sql)
    print("Phase 01 DB SCHEMA INITIALIZED")
except Exception as e:
    print(f"ERROR: {e}")
