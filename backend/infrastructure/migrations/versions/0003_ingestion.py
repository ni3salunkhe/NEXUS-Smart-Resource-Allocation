"""Phase 1: Core Ingestion Schema
   ingestion_raw, need_records, review_queue, geocoding_cache

Revision ID: 0003_ingestion
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0003_ingestion'
down_revision = '0002_household_registry'
branch_labels = None
depends_on = None


def upgrade() -> None:

    # ── ENUMS ─────────────────────────────────────────────────
    for name, values in [
        ("source_type_enum", [
            "paper","whatsapp","mobile","sms","csv","webhook","audio"
        ]),
        ("need_category_enum", [
            "food","health","shelter","education","livelihood",
            "water","mental_health","legal","hygiene","other"
        ]),
        ("need_status_enum", [
            "unverified","verified","assigned",
            "in_progress","resolved","closed","duplicate"
        ]),
        ("review_status_enum", [
            "pending","approved","rejected","needs_info"
        ]),
        ("ingestion_status_enum", [
            "received","processing","processed","failed","duplicate"
        ]),
    ]:
        vals = ", ".join(f"'{v}'" for v in values)
        op.execute(f"""
            DO $$ BEGIN
                CREATE TYPE {name} AS ENUM ({vals});
            EXCEPTION WHEN duplicate_object THEN NULL;
            END $$;
        """)

    # ── TABLE: ingestion_raw ──────────────────────────────────
    # Staging table; one row per raw input before processing
    op.create_table(
        "ingestion_raw",
        sa.Column("raw_id",           postgresql.UUID(as_uuid=True),
                  server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column("tenant_id",        postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.tenant_id"), nullable=False),
        sa.Column("source_type",      sa.Enum(*["paper","whatsapp","mobile","sms",
                                                 "csv","webhook","audio"],
                                               name="source_type_enum"), nullable=False),
        sa.Column("s3_key",           sa.Text, nullable=True),        # raw artifact pointer
        sa.Column("raw_text",         sa.Text, nullable=True),        # for text channels
        sa.Column("raw_metadata",     postgresql.JSONB, server_default="{}"),
        sa.Column("submitted_by",     postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True),
        sa.Column("submitted_at",     sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()")),
        sa.Column("status",           sa.Enum(*["received","processing","processed",
                                                 "failed","duplicate"],
                                               name="ingestion_status_enum"),
                  server_default="received"),
        sa.Column("processing_error", sa.Text, nullable=True),
        sa.Column("ocr_text",         sa.Text, nullable=True),
        sa.Column("nlp_output",       postgresql.JSONB, nullable=True),
        sa.Column("processed_at",     sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("correlation_id",   postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.execute("ALTER TABLE ingestion_raw ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY ingestion_raw_tenant ON ingestion_raw
        USING (
            tenant_id = current_setting('app.current_tenant_id', TRUE)::UUID
            OR current_setting('app.current_role', TRUE) = 'platform_admin'
        )
    """)

    # ── TABLE: need_records ───────────────────────────────────
    op.create_table(
        "need_records",
        sa.Column("need_id",              postgresql.UUID(as_uuid=True),
                  server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column("tenant_id",            postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.tenant_id"), nullable=False),
        sa.Column("household_id",         postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("households.household_id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("raw_id",               postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("ingestion_raw.raw_id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("source_type",          sa.Enum(*["paper","whatsapp","mobile","sms",
                                                     "csv","webhook","audio"],
                                                   name="source_type_enum"), nullable=False),
        sa.Column("s3_raw_ref",           sa.Text, nullable=True),
        sa.Column("reported_by",          postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True),
        sa.Column("reported_at",          sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("ingested_at",          sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()")),
        # Location
        sa.Column("location_geo",         sa.Text, nullable=True),   # GEOGRAPHY added below
        sa.Column("ward_id",              sa.String(64), nullable=True),
        # Classification
        sa.Column("category",             sa.Enum(*["food","health","shelter","education",
                                                     "livelihood","water","mental_health",
                                                     "legal","hygiene","other"],
                                                   name="need_category_enum"),
                  nullable=True),
        sa.Column("subcategory",          sa.Text, nullable=True),
        sa.Column("description",          sa.Text, nullable=True),      # normalized English
        sa.Column("description_original", sa.Text, nullable=True),      # original language
        sa.Column("language_detected",    sa.String(10), nullable=True),
        # Scoring
        sa.Column("severity_score",       sa.Float, server_default="0.5"),
        sa.Column("urgency_score",        sa.Float, server_default="0.5"),
        sa.Column("beneficiary_count",    sa.Integer, server_default="1"),
        sa.Column("vulnerability_flags",  postgresql.JSONB, server_default="{}"),
        # Processing metadata
        sa.Column("nlp_confidence",       sa.Float, server_default="0.0"),
        sa.Column("nlp_entities",         postgresql.JSONB, server_default="{}"),
        sa.Column("geocoding_confidence", sa.Float, server_default="0.0"),
        sa.Column("household_resolution", sa.String(50), nullable=True),
        # Status
        sa.Column("status",               sa.Enum(*["unverified","verified","assigned",
                                                     "in_progress","resolved","closed","duplicate"],
                                                   name="need_status_enum"),
                  server_default="unverified"),
        sa.Column("assigned_task_id",     postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("verified_by",          postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True),
        sa.Column("verified_at",          sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("duplicate_of",         postgresql.UUID(as_uuid=True), nullable=True),
        # Audit
        sa.Column("created_at",           sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at",           sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()")),
    )
    op.execute("ALTER TABLE need_records ADD COLUMN location_point GEOGRAPHY(POINT, 4326)")
    op.execute("ALTER TABLE need_records ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY need_records_tenant ON need_records
        USING (
            tenant_id = current_setting('app.current_tenant_id', TRUE)::UUID
            OR current_setting('app.current_role', TRUE) = 'platform_admin'
        )
    """)

    # ── TABLE: review_queue ───────────────────────────────────
    op.create_table(
        "review_queue",
        sa.Column("review_id",        postgresql.UUID(as_uuid=True),
                  server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column("tenant_id",        postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.tenant_id"), nullable=False),
        sa.Column("raw_id",           postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("ingestion_raw.raw_id"), nullable=True),
        sa.Column("need_id",          postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("need_records.need_id"), nullable=True),
        sa.Column("review_type",      sa.String(50), nullable=False),
        # "low_nlp_confidence" | "household_resolution" | "duplicate_suspect"
        sa.Column("review_data",      postgresql.JSONB, server_default="{}"),
        sa.Column("status",           sa.Enum("pending","approved","rejected","needs_info",
                                               name="review_status_enum"),
                  server_default="pending"),
        sa.Column("assigned_to",      postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True),
        sa.Column("reviewed_by",      postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True),
        sa.Column("review_notes",     sa.Text, nullable=True),
        sa.Column("created_at",       sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()")),
        sa.Column("resolved_at",      sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("priority",         sa.Integer, server_default="5"),
    )
    op.execute("ALTER TABLE review_queue ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY review_queue_tenant ON review_queue
        USING (
            tenant_id = current_setting('app.current_tenant_id', TRUE)::UUID
            OR current_setting('app.current_role', TRUE) = 'platform_admin'
        )
    """)

    # ── TABLE: geocoding_cache ────────────────────────────────
    op.create_table(
        "geocoding_cache",
        sa.Column("cache_id",     postgresql.UUID(as_uuid=True),
                  server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column("input_text",   sa.Text, nullable=False, unique=True),
        sa.Column("latitude",     sa.Float, nullable=True),
        sa.Column("longitude",    sa.Float, nullable=True),
        sa.Column("confidence",   sa.Float, server_default="0.0"),
        sa.Column("ward_id",      sa.String(64), nullable=True),
        sa.Column("resolved_by",  sa.String(50), nullable=True),  # "google"|"custom"|"manual"
        sa.Column("hit_count",    sa.Integer, server_default="1"),
        sa.Column("created_at",   sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("last_used_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()")),
    )

    # ── TRIGGERS ──────────────────────────────────────────────
    op.execute("""
        CREATE TRIGGER set_updated_at_need_records
        BEFORE UPDATE ON need_records
        FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();
    """)

    # ── INDEXES ───────────────────────────────────────────────
    op.execute("CREATE INDEX idx_need_location   ON need_records USING GIST(location_point)")
    op.create_index("idx_need_tenant_status", "need_records", ["tenant_id","status"])
    op.create_index("idx_need_tenant_cat",    "need_records", ["tenant_id","category"])
    op.create_index("idx_need_household",     "need_records", ["household_id"])
    op.create_index("idx_need_urgency",       "need_records", ["tenant_id","urgency_score"])
    op.create_index("idx_need_ward",          "need_records", ["tenant_id","ward_id"])
    op.create_index("idx_need_ingested",      "need_records", ["tenant_id","ingested_at"])
    op.execute("""
        CREATE INDEX idx_need_description_trgm
        ON need_records USING GIN(description gin_trgm_ops)
    """)
    op.create_index("idx_review_pending",  "review_queue",
                    ["tenant_id","status","priority"],
                    postgresql_where=sa.text("status = 'pending'"))
    op.create_index("idx_geocache_input",  "geocoding_cache", ["input_text"])
    op.create_index("idx_ingestion_status","ingestion_raw",   ["tenant_id","status"])


def downgrade() -> None:
    for tbl in ["geocoding_cache","review_queue","need_records","ingestion_raw"]:
        op.drop_table(tbl)
    for e in ["source_type_enum","need_category_enum",
              "need_status_enum","review_status_enum","ingestion_status_enum"]:
        op.execute(f"DROP TYPE IF EXISTS {e}")