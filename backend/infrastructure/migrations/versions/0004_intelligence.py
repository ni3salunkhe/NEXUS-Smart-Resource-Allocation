"""Phase 2: Intelligence Engine Schema
   urgency_score_log, priority_queue_snapshots, gap_reports,
   ward_stats, urgency_weight_configs

Revision ID: 0004_intelligence
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0004_intelligence'
down_revision = '0003_ingestion'
branch_labels = None
depends_on = None


def upgrade() -> None:

    # ── TABLE: urgency_weight_configs ─────────────────────────
    # Per-tenant configurable weights for the urgency formula
    op.create_table(
        "urgency_weight_configs",
        sa.Column("config_id",    postgresql.UUID(as_uuid=True),
                  server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column("tenant_id",    postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.tenant_id", ondelete="CASCADE"),
                  nullable=False, unique=True),
        sa.Column("w1_severity",          sa.Float, server_default="0.25"),
        sa.Column("w2_recency",           sa.Float, server_default="0.15"),
        sa.Column("w3_vulnerability",     sa.Float, server_default="0.20"),
        sa.Column("w4_unmet_duration",    sa.Float, server_default="0.15"),
        sa.Column("w5_source_reliability",sa.Float, server_default="0.10"),
        sa.Column("w6_crisis_frequency",  sa.Float, server_default="0.10"),
        sa.Column("w7_coverage_penalty",  sa.Float, server_default="0.05"),
        # Category boosts (JSONB: {food: 1.2, health: 1.5, ...})
        sa.Column("category_boosts",      postgresql.JSONB, server_default="{}"),
        # Urgency floor for chronic households (crisis_frequency > threshold)
        sa.Column("chronic_threshold",    sa.Float, server_default="2.0"),
        sa.Column("chronic_floor",        sa.Float, server_default="0.40"),
        # Auto-escalation threshold
        sa.Column("escalation_threshold", sa.Float, server_default="0.90"),
        sa.Column("escalation_minutes",   sa.Integer, server_default="120"),
        sa.Column("updated_at",           sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()")),
        sa.Column("updated_by",           postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True),
    )
    op.execute("ALTER TABLE urgency_weight_configs ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY uwc_tenant ON urgency_weight_configs
        USING (
            tenant_id = current_setting('app.current_tenant_id', TRUE)::UUID
            OR current_setting('app.current_role', TRUE) = 'platform_admin'
        )
    """)

    # ── TABLE: urgency_score_log ──────────────────────────────
    # Immutable log of every urgency score computation
    op.create_table(
        "urgency_score_log",
        sa.Column("log_id",        postgresql.UUID(as_uuid=True),
                  server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column("need_id",       postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("need_records.need_id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id",     postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.tenant_id"), nullable=False),
        sa.Column("score",         sa.Float, nullable=False),
        sa.Column("prev_score",    sa.Float, nullable=True),
        sa.Column("components",    postgresql.JSONB, server_default="{}"),
        # Individual term values
        sa.Column("t1_severity",         sa.Float),
        sa.Column("t2_recency",          sa.Float),
        sa.Column("t3_vulnerability",    sa.Float),
        sa.Column("t4_unmet_duration",   sa.Float),
        sa.Column("t5_source_reliability",sa.Float),
        sa.Column("t6_crisis_frequency", sa.Float),
        sa.Column("t7_coverage_penalty", sa.Float),
        sa.Column("trigger",       sa.String(50)),   # "need_created"|"need_updated"|"schedule"|"outcome"
        sa.Column("computed_at",   sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()")),
    )
    op.execute("CREATE RULE usl_no_update AS ON UPDATE TO urgency_score_log DO INSTEAD NOTHING")
    op.execute("CREATE RULE usl_no_delete AS ON DELETE TO urgency_score_log DO INSTEAD NOTHING")
    op.execute("ALTER TABLE urgency_score_log ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY usl_tenant ON urgency_score_log
        USING (
            tenant_id = current_setting('app.current_tenant_id', TRUE)::UUID
            OR current_setting('app.current_role', TRUE) = 'platform_admin'
        )
    """)

    # ── TABLE: ward_stats ─────────────────────────────────────
    # Materialized per-ward aggregates (refreshed every 4h by scheduler)
    op.create_table(
        "ward_stats",
        sa.Column("stat_id",             postgresql.UUID(as_uuid=True),
                  server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column("tenant_id",           postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.tenant_id"), nullable=False),
        sa.Column("ward_id",             sa.String(64), nullable=False),
        sa.Column("computed_at",         sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()")),
        sa.Column("total_needs_open",    sa.Integer, server_default="0"),
        sa.Column("total_needs_30d",     sa.Integer, server_default="0"),
        sa.Column("avg_urgency_score",   sa.Float,   server_default="0.0"),
        sa.Column("max_urgency_score",   sa.Float,   server_default="0.0"),
        sa.Column("category_breakdown",  postgresql.JSONB, server_default="{}"),
        sa.Column("active_tasks_count",  sa.Integer, server_default="0"),
        sa.Column("coverage_ratio",      sa.Float,   server_default="0.0"),
        # coverage_ratio = active_tasks / open_needs  (0=desert, 1=fully covered)
        sa.Column("is_resource_desert",  sa.Boolean, server_default="FALSE"),
        # Top-quartile urgency with zero active tasks
        sa.Column("chronic_household_count", sa.Integer, server_default="0"),
        sa.Column("centroid_lat",        sa.Float, nullable=True),
        sa.Column("centroid_lon",        sa.Float, nullable=True),
        sa.UniqueConstraint("tenant_id", "ward_id", name="uq_ward_stats_tenant_ward"),
    )
    op.execute("ALTER TABLE ward_stats ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY ws_tenant ON ward_stats
        USING (
            tenant_id = current_setting('app.current_tenant_id', TRUE)::UUID
            OR current_setting('app.current_role', TRUE) = 'platform_admin'
        )
    """)

    # ── TABLE: gap_reports ────────────────────────────────────
    op.create_table(
        "gap_reports",
        sa.Column("report_id",      postgresql.UUID(as_uuid=True),
                  server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column("tenant_id",      postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.tenant_id"), nullable=False),
        sa.Column("generated_at",   sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()")),
        sa.Column("desert_wards",   postgresql.JSONB, server_default="[]"),
        sa.Column("top_unmet_needs",postgresql.JSONB, server_default="[]"),
        sa.Column("summary",        postgresql.JSONB, server_default="{}"),
    )
    op.execute("ALTER TABLE gap_reports ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY gr_tenant ON gap_reports
        USING (
            tenant_id = current_setting('app.current_tenant_id', TRUE)::UUID
            OR current_setting('app.current_role', TRUE) = 'platform_admin'
        )
    """)

    # ── INDEXES ───────────────────────────────────────────────
    op.create_index("idx_usl_need",     "urgency_score_log", ["need_id", "computed_at"])
    op.create_index("idx_usl_tenant",   "urgency_score_log", ["tenant_id", "computed_at"])
    op.create_index("idx_ws_tenant",    "ward_stats",        ["tenant_id"])
    op.create_index("idx_ws_desert",    "ward_stats",        ["tenant_id","is_resource_desert"])
    op.create_index("idx_gap_tenant",   "gap_reports",       ["tenant_id","generated_at"])

    # ── Seed default urgency config for existing tenants ──────
    op.execute("""
        INSERT INTO urgency_weight_configs (tenant_id)
        SELECT tenant_id FROM tenants
        ON CONFLICT DO NOTHING
    """)

    # ── Trigger: auto-insert default config for new tenants ──
    op.execute("""
        CREATE OR REPLACE FUNCTION fn_seed_urgency_config()
        RETURNS TRIGGER AS $$
        BEGIN
            INSERT INTO urgency_weight_configs(tenant_id)
            VALUES (NEW.tenant_id)
            ON CONFLICT DO NOTHING;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER trg_seed_urgency_config
        AFTER INSERT ON tenants
        FOR EACH ROW EXECUTE FUNCTION fn_seed_urgency_config();
    """)


def downgrade() -> None:
    for tbl in ["gap_reports","ward_stats","urgency_score_log","urgency_weight_configs"]:
        op.drop_table(tbl)
    op.execute("DROP FUNCTION IF EXISTS fn_seed_urgency_config CASCADE")