"""Phase 0.5: Household & Beneficiary Registry
   households, household_members, household_consent,
   household_cross_tenant_links, household_history

Revision ID: 0002_household_registry
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0002_household_registry'
down_revision = '0001_foundation'
branch_labels = None
depends_on = None


def upgrade() -> None:

    # ── ENUMS ─────────────────────────────────────────────────
    for name, values in [
        ("dwelling_type_enum",   ["permanent","semi_permanent","temporary","open_space"]),
        ("economic_tier_enum",   ["below_poverty","marginal","low","medium"]),
        ("household_status_enum",["active","relocated","dissolved","merged_away","opted_out"]),
        ("member_role_enum",     ["head","spouse","child","parent","dependent","other"]),
        ("age_bracket_enum",     ["infant","child","youth","adult","elderly"]),
        ("gender_enum",          ["male","female","non_binary","prefer_not_to_say"]),
        ("consent_type_enum",    ["data_collection","location_sharing",
                                  "cross_org_linking","analytics","photo"]),
        ("consent_method_enum",  ["verbal_witnessed","signed_form","digital_app"]),
        ("link_method_enum",     ["auto_matched","coordinator_confirmed","household_confirmed"]),
        ("link_status_enum",     ["proposed","active","rejected","revoked"]),
        ("hh_event_type_enum",   [
            "need_reported","need_resolved","task_dispatched","task_completed",
            "member_added","member_removed","vulnerability_updated","consent_changed",
            "assistance_received","location_updated","merged","linked","opted_out",
        ]),
    ]:
        vals = ", ".join(f"'{v}'" for v in values)
        op.execute(f"""
            DO $$ BEGIN
                CREATE TYPE {name} AS ENUM ({vals});
            EXCEPTION WHEN duplicate_object THEN NULL;
            END $$;
        """)

    # ── TABLE: households ─────────────────────────────────────
    op.create_table(
        "households",
        sa.Column("household_id",          postgresql.UUID(as_uuid=True),
                  server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column("global_household_id",   postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("tenant_id",             postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.tenant_id", ondelete="CASCADE"), nullable=False),
        sa.Column("ward_id",               sa.String(64),  nullable=True),
        # Geospatial
        sa.Column("location",              sa.Text, nullable=True),   # stored as WKT; PostGIS GEOGRAPHY(POINT,4326)
        sa.Column("location_confidence",   sa.Float, server_default="0.5"),
        sa.Column("location_description",  sa.Text,  nullable=True),
        sa.Column("landmark_tags",         postgresql.ARRAY(sa.Text), server_default="{}"),
        # Physical
        sa.Column("dwelling_type",         sa.Enum("permanent","semi_permanent","temporary",
                                                    "open_space", name="dwelling_type_enum"),
                  nullable=True),
        # Demographics (denormalised)
        sa.Column("total_members",         sa.Integer, server_default="0"),
        sa.Column("vulnerability_score",   sa.Float,   server_default="0.0"),
        sa.Column("vulnerability_flags",   postgresql.JSONB,
                  server_default='{"has_child":false,"has_elderly":false,"has_disabled":false,'
                                  '"has_pregnant":false,"chronic_illness":false,"single_parent":false}'),
        sa.Column("economic_tier",         sa.Enum("below_poverty","marginal","low","medium",
                                                    name="economic_tier_enum"), nullable=True),
        # Assistance tracking
        sa.Column("total_needs_reported",  sa.Integer, server_default="0"),
        sa.Column("total_tasks_completed", sa.Integer, server_default="0"),
        sa.Column("last_need_reported_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_assistance_at",    sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("total_assistance_value",sa.Numeric(12, 2), server_default="0.00"),
        sa.Column("assistance_categories", postgresql.ARRAY(sa.Text), server_default="{}"),
        sa.Column("crisis_frequency",      sa.Float, server_default="0.0"),
        # Status
        sa.Column("status",                sa.Enum("active","relocated","dissolved",
                                                    "merged_away","opted_out",
                                                    name="household_status_enum"),
                  server_default="active"),
        sa.Column("merged_into",           postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("merge_reason",          sa.Text, nullable=True),
        sa.Column("data_quality_score",    sa.Float, server_default="0.5"),
        # Audit
        sa.Column("created_at",            sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at",            sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()")),
        sa.Column("created_by",            postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True),
    )

    # PostGIS: add real geography column (ALTER TABLE after creation)
    op.execute("""
        ALTER TABLE households
        ADD COLUMN location_geo GEOGRAPHY(POINT, 4326);
    """)

    op.execute("ALTER TABLE households ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY hh_tenant_isolation ON households
        USING (
            tenant_id = current_setting('app.current_tenant_id', TRUE)::UUID
            OR current_setting('app.current_role', TRUE) = 'platform_admin'
        )
    """)

    # ── TABLE: household_members ──────────────────────────────
    op.create_table(
        "household_members",
        sa.Column("member_id",           postgresql.UUID(as_uuid=True),
                  server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column("household_id",        postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("households.household_id", ondelete="CASCADE"), nullable=False),
        sa.Column("role_in_household",   sa.Enum("head","spouse","child","parent",
                                                  "dependent","other",
                                                  name="member_role_enum"), nullable=True),
        sa.Column("age_bracket",         sa.Enum("infant","child","youth","adult","elderly",
                                                  name="age_bracket_enum"), nullable=True),
        sa.Column("gender",              sa.Enum("male","female","non_binary","prefer_not_to_say",
                                                  name="gender_enum"), nullable=True),
        sa.Column("is_primary_contact",  sa.Boolean, server_default="FALSE"),
        sa.Column("vulnerability_flags", postgresql.JSONB,
                  server_default='{"disabled":false,"chronic_illness":false,'
                                  '"pregnant":false,"malnourished":false,"mental_health":false}'),
        sa.Column("pii_ref",             postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_present",          sa.Boolean, server_default="TRUE"),
        sa.Column("added_at",            sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()")),
        sa.Column("removed_at",          sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("added_by",            postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True),
    )
    op.execute("ALTER TABLE household_members ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY hh_members_tenant_isolation ON household_members
        USING (
            household_id IN (
                SELECT household_id FROM households
                WHERE tenant_id = current_setting('app.current_tenant_id', TRUE)::UUID
            )
            OR current_setting('app.current_role', TRUE) = 'platform_admin'
        )
    """)

    # ── TABLE: household_consent ──────────────────────────────
    op.create_table(
        "household_consent",
        sa.Column("consent_id",          postgresql.UUID(as_uuid=True),
                  server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column("household_id",        postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("households.household_id", ondelete="CASCADE"), nullable=False),
        sa.Column("primary_contact_ref", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("household_members.member_id", ondelete="SET NULL"), nullable=True),
        sa.Column("consent_type",        sa.Enum("data_collection","location_sharing",
                                                  "cross_org_linking","analytics","photo",
                                                  name="consent_type_enum"), nullable=False),
        sa.Column("scope",               postgresql.JSONB,
                  server_default='{"tenants_allowed":[],"purposes":[],"data_fields_allowed":[]}'),
        sa.Column("granted_at",          sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()")),
        sa.Column("expires_at",          sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("revoked_at",          sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("revocation_reason",   sa.Text, nullable=True),
        sa.Column("collected_by",        postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True),
        sa.Column("collection_method",   sa.Enum("verbal_witnessed","signed_form","digital_app",
                                                  name="consent_method_enum"), nullable=True),
        sa.Column("language_used",       sa.String(10), nullable=True),
        sa.Column("opt_out",             sa.Boolean, server_default="FALSE"),
        sa.Column("opt_out_scope",       postgresql.ARRAY(sa.Text), server_default="{}"),
    )
    op.execute("ALTER TABLE household_consent ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY hh_consent_tenant_isolation ON household_consent
        USING (
            household_id IN (
                SELECT household_id FROM households
                WHERE tenant_id = current_setting('app.current_tenant_id', TRUE)::UUID
            )
            OR current_setting('app.current_role', TRUE) = 'platform_admin'
        )
    """)

    # ── TABLE: household_cross_tenant_links ───────────────────
    op.create_table(
        "household_cross_tenant_links",
        sa.Column("link_id",               postgresql.UUID(as_uuid=True),
                  server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column("household_id_tenant_a", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("households.household_id", ondelete="CASCADE"), nullable=False),
        sa.Column("household_id_tenant_b", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("households.household_id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_a",              postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.tenant_id"), nullable=False),
        sa.Column("tenant_b",              postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.tenant_id"), nullable=False),
        sa.Column("global_household_id",   postgresql.UUID(as_uuid=True),
                  server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("link_confidence",       sa.Float, nullable=False),
        sa.Column("link_method",           sa.Enum("auto_matched","coordinator_confirmed",
                                                    "household_confirmed", name="link_method_enum"),
                  nullable=False),
        sa.Column("link_status",           sa.Enum("proposed","active","rejected","revoked",
                                                    name="link_status_enum"),
                  server_default="proposed"),
        sa.Column("consent_id_a",          postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("household_consent.consent_id"), nullable=True),
        sa.Column("consent_id_b",          postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("household_consent.consent_id"), nullable=True),
        sa.Column("fields_shared",         postgresql.ARRAY(sa.Text), server_default="{}"),
        sa.Column("created_at",            sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()")),
        sa.Column("approved_at",           sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("approved_by",           postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True),
    )

    # ── TABLE: household_history (APPEND-ONLY) ────────────────
    op.create_table(
        "household_history",
        sa.Column("event_id",        postgresql.UUID(as_uuid=True),
                  server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column("household_id",    postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("households.household_id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type",      sa.Enum(
            "need_reported","need_resolved","task_dispatched","task_completed",
            "member_added","member_removed","vulnerability_updated","consent_changed",
            "assistance_received","location_updated","merged","linked","opted_out",
            name="hh_event_type_enum"), nullable=False),
        sa.Column("event_timestamp", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()")),
        sa.Column("event_payload",   postgresql.JSONB, server_default="{}"),
        sa.Column("related_need_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("related_task_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("triggered_by",    postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True),
        sa.Column("tenant_id",       postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.tenant_id"), nullable=False),
    )
    # Append-only enforcement
    op.execute("CREATE RULE hh_history_no_update AS ON UPDATE TO household_history DO INSTEAD NOTHING")
    op.execute("CREATE RULE hh_history_no_delete AS ON DELETE TO household_history DO INSTEAD NOTHING")
    op.execute("ALTER TABLE household_history ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY hh_history_tenant_isolation ON household_history
        USING (
            tenant_id = current_setting('app.current_tenant_id', TRUE)::UUID
            OR current_setting('app.current_role', TRUE) = 'platform_admin'
        )
    """)

    # ── TRIGGERS ──────────────────────────────────────────────

    # Auto-recompute total_members on household_members change
    op.execute("""
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
    """)
    op.execute("""
        CREATE TRIGGER trg_recompute_member_count
        AFTER INSERT OR UPDATE OR DELETE ON household_members
        FOR EACH ROW EXECUTE FUNCTION fn_recompute_member_count();
    """)

    # Auto-recompute vulnerability_score from member flags
    op.execute("""
        CREATE OR REPLACE FUNCTION fn_recompute_vulnerability()
        RETURNS TRIGGER AS $$
        DECLARE
            v_hh_id UUID := COALESCE(NEW.household_id, OLD.household_id);
            v_score  FLOAT := 0.0;
            v_flags  JSONB := '{}'::JSONB;
        BEGIN
            SELECT
                LEAST(1.0,
                    (CASE WHEN bool_or((flags->>'disabled')::bool)    THEN 0.25 ELSE 0 END) +
                    (CASE WHEN bool_or((flags->>'pregnant')::bool)    THEN 0.20 ELSE 0 END) +
                    (CASE WHEN bool_or((flags->>'malnourished')::bool)THEN 0.25 ELSE 0 END) +
                    (CASE WHEN bool_or((flags->>'mental_health')::bool) THEN 0.15 ELSE 0 END) +
                    (CASE WHEN bool_or((flags->>'chronic_illness')::bool) THEN 0.15 ELSE 0 END)
                ),
                jsonb_build_object(
                    'has_child',     bool_or(age_bracket = 'child' OR age_bracket = 'infant'),
                    'has_elderly',   bool_or(age_bracket = 'elderly'),
                    'has_disabled',  bool_or((flags->>'disabled')::bool),
                    'has_pregnant',  bool_or((flags->>'pregnant')::bool),
                    'chronic_illness', bool_or((flags->>'chronic_illness')::bool),
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
    """)
    op.execute("""
        CREATE TRIGGER trg_recompute_vulnerability
        AFTER INSERT OR UPDATE OR DELETE ON household_members
        FOR EACH ROW EXECUTE FUNCTION fn_recompute_vulnerability();
    """)

    # Auto updated_at for households
    op.execute("""
        CREATE TRIGGER set_updated_at_households
        BEFORE UPDATE ON households
        FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();
    """)

    # ── INDEXES ───────────────────────────────────────────────

    # Spatial index (PostGIS)
    op.execute("CREATE INDEX idx_households_geo ON households USING GIST(location_geo)")
    # Tenant + status
    op.create_index("idx_households_tenant_status", "households", ["tenant_id","status"])
    # Ward-level queries
    op.create_index("idx_households_ward",          "households", ["tenant_id","ward_id"])
    # Global household ID for cross-tenant linking
    op.create_index("idx_households_global_id",     "households", ["global_household_id"],
                    postgresql_where=sa.text("global_household_id IS NOT NULL"))
    # Fuzzy text search on location_description
    op.execute("""
        CREATE INDEX idx_households_location_trgm
        ON households USING GIN(location_description gin_trgm_ops)
    """)
    # Landmark tags GIN
    op.execute("CREATE INDEX idx_households_landmarks ON households USING GIN(landmark_tags)")
    # Vulnerability flags GIN
    op.execute("CREATE INDEX idx_households_vuln ON households USING GIN(vulnerability_flags)")
    # Members
    op.create_index("idx_hh_members_household",  "household_members", ["household_id"])
    op.create_index("idx_hh_members_present",    "household_members", ["household_id","is_present"])
    # Consent
    op.create_index("idx_consent_household",     "household_consent", ["household_id"])
    op.execute("""
        CREATE INDEX idx_consent_active ON household_consent(household_id)
        WHERE revoked_at IS NULL AND opt_out = FALSE
    """)
    # History
    op.create_index("idx_hh_history_household",  "household_history",
                    ["household_id","event_timestamp"])
    op.create_index("idx_hh_history_tenant",     "household_history",
                    ["tenant_id","event_timestamp"])
    op.create_index("idx_hh_history_type",       "household_history",
                    ["household_id","event_type"])
    # Cross-tenant links
    op.create_index("idx_ctl_tenant_a", "household_cross_tenant_links", ["tenant_a","link_status"])
    op.create_index("idx_ctl_tenant_b", "household_cross_tenant_links", ["tenant_b","link_status"])
    op.create_index("idx_ctl_global",   "household_cross_tenant_links", ["global_household_id"])


def downgrade() -> None:
    for tbl in ["household_history", "household_cross_tenant_links",
                "household_consent", "household_members", "households"]:
        op.drop_table(tbl)
    for enum in ["dwelling_type_enum","economic_tier_enum","household_status_enum",
                 "member_role_enum","age_bracket_enum","gender_enum","consent_type_enum",
                 "consent_method_enum","link_method_enum","link_status_enum","hh_event_type_enum"]:
        op.execute(f"DROP TYPE IF EXISTS {enum}")
    op.execute("DROP FUNCTION IF EXISTS fn_recompute_member_count CASCADE")
    op.execute("DROP FUNCTION IF EXISTS fn_recompute_vulnerability CASCADE")