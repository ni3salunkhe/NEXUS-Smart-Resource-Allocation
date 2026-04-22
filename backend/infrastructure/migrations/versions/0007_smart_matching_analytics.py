"""Phase 4+5: Smart Matching, Feedback Loop & Analytics Schema

Revision ID: 0007
Revises: 0006
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None


def upgrade() -> None:

    op.create_table(
        "match_override_log",
        sa.Column("override_id",       postgresql.UUID(as_uuid=True),
                  server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column("task_id",           postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tasks.task_id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id",         postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.tenant_id"), nullable=False),
        sa.Column("suggested_vol_id",  postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("suggested_score",   sa.Float, nullable=True),
        sa.Column("chosen_vol_id",     postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("volunteers.volunteer_id", ondelete="SET NULL"), nullable=False),
        sa.Column("override_reason",   sa.Text, nullable=True),
        sa.Column("coordinator_id",    postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True),
        sa.Column("need_category",     sa.String(50), nullable=True),
        sa.Column("need_ward_id",      sa.String(64), nullable=True),
        sa.Column("need_urgency",      sa.Float, nullable=True),
        sa.Column("task_outcome",      sa.String(50), nullable=True),
        sa.Column("volunteer_rating",  sa.Float, nullable=True),
        sa.Column("override_was_better", sa.Boolean, nullable=True),
        sa.Column("created_at",        sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()")),
        sa.Column("outcome_updated_at",sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.execute("CREATE RULE mol_no_delete AS ON DELETE TO match_override_log DO INSTEAD NOTHING")
    op.execute("CREATE RULE mol_no_update AS ON UPDATE TO match_override_log DO INSTEAD NOTHING")
    op.execute("ALTER TABLE match_override_log ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY mol_tenant ON match_override_log USING (
            tenant_id = current_setting('app.current_tenant_id', TRUE)::UUID
            OR current_setting('app.current_role', TRUE) = 'platform_admin'
        )
    """)

    op.create_table(
        "volunteer_performance_snapshots",
        sa.Column("snapshot_id",         postgresql.UUID(as_uuid=True),
                  server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column("volunteer_id",         postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("volunteers.volunteer_id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id",            postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.tenant_id"), nullable=False),
        sa.Column("snapshot_date",        sa.Date, nullable=False),
        sa.Column("total_deployments",    sa.Integer, server_default="0"),
        sa.Column("deployments_30d",      sa.Integer, server_default="0"),
        sa.Column("avg_outcome_rating",   sa.Float,   server_default="0.0"),
        sa.Column("full_resolution_rate", sa.Float,   server_default="0.0"),
        sa.Column("response_rate",        sa.Float,   server_default="1.0"),
        sa.Column("burnout_risk_score",   sa.Float,   server_default="0.0"),
        sa.Column("categories_served",    postgresql.ARRAY(sa.Text), server_default="{}"),
        sa.Column("wards_served",         postgresql.ARRAY(sa.Text), server_default="{}"),
        sa.UniqueConstraint("volunteer_id","snapshot_date", name="uq_vol_snapshot"),
    )
    op.execute("ALTER TABLE volunteer_performance_snapshots ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY vps_tenant ON volunteer_performance_snapshots USING (
            tenant_id = current_setting('app.current_tenant_id', TRUE)::UUID
            OR current_setting('app.current_role', TRUE) = 'platform_admin'
        )
    """)

    op.create_table(
        "household_improvement_index",
        sa.Column("index_id",          postgresql.UUID(as_uuid=True),
                  server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column("household_id",      postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("households.household_id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id",         postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.tenant_id"), nullable=False),
        sa.Column("computed_at",       sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()")),
        sa.Column("window_days",       sa.Integer, nullable=False),
        sa.Column("total_needs",       sa.Integer, server_default="0"),
        sa.Column("fully_met",         sa.Integer, server_default="0"),
        sa.Column("partially_met",     sa.Integer, server_default="0"),
        sa.Column("unresolved",        sa.Integer, server_default="0"),
        sa.Column("improvement_index", sa.Float, server_default="0.0"),
        sa.Column("crisis_frequency",  sa.Float, server_default="0.0"),
        sa.Column("trend",             sa.String(20), nullable=True),
    )
    op.execute("ALTER TABLE household_improvement_index ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY hii_tenant ON household_improvement_index USING (
            tenant_id = current_setting('app.current_tenant_id', TRUE)::UUID
            OR current_setting('app.current_role', TRUE) = 'platform_admin'
        )
    """)

    op.create_table(
        "impact_metrics",
        sa.Column("metric_id",               postgresql.UUID(as_uuid=True),
                  server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column("tenant_id",               postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.tenant_id"), nullable=False),
        sa.Column("period_start",            sa.Date, nullable=False),
        sa.Column("period_end",              sa.Date, nullable=False),
        sa.Column("period_type",             sa.String(20), nullable=False),
        sa.Column("households_served",       sa.Integer, server_default="0"),
        sa.Column("households_chronic",      sa.Integer, server_default="0"),
        sa.Column("households_improved",     sa.Integer, server_default="0"),
        sa.Column("avg_improvement_index",   sa.Float,   server_default="0.0"),
        sa.Column("needs_reported",          sa.Integer, server_default="0"),
        sa.Column("needs_resolved",          sa.Integer, server_default="0"),
        sa.Column("needs_resolution_rate",   sa.Float,   server_default="0.0"),
        sa.Column("avg_time_to_assignment_min", sa.Float, server_default="0.0"),
        sa.Column("p95_time_to_assignment_min", sa.Float, server_default="0.0"),
        sa.Column("volunteers_active",       sa.Integer, server_default="0"),
        sa.Column("volunteer_hours",         sa.Float,   server_default="0.0"),
        sa.Column("volunteer_retention_rate",sa.Float,   server_default="0.0"),
        sa.Column("cross_ngo_dup_rate",      sa.Float,   server_default="0.0"),
        sa.Column("resource_desert_count",   sa.Integer, server_default="0"),
        sa.Column("category_breakdown",      postgresql.JSONB, server_default="{}"),
        sa.Column("ward_breakdown",          postgresql.JSONB, server_default="{}"),
        sa.Column("computed_at",             sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()")),
        sa.UniqueConstraint("tenant_id","period_start","period_end","period_type",
                            name="uq_impact_period"),
    )
    op.execute("ALTER TABLE impact_metrics ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY im_tenant ON impact_metrics USING (
            tenant_id = current_setting('app.current_tenant_id', TRUE)::UUID
            OR current_setting('app.current_role', TRUE) = 'platform_admin'
        )
    """)

    op.create_table(
        "feedback_events",
        sa.Column("event_id",     postgresql.UUID(as_uuid=True),
                  server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column("tenant_id",    postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.tenant_id"), nullable=False),
        sa.Column("event_type",   sa.String(80), nullable=False),
        sa.Column("source_id",    postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("household_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("volunteer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("need_id",      postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("payload",      postgresql.JSONB, server_default="{}"),
        sa.Column("processed",    sa.Boolean, server_default="FALSE"),
        sa.Column("processed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at",   sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()")),
    )
    op.execute("ALTER TABLE feedback_events ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY fe_tenant ON feedback_events USING (
            tenant_id = current_setting('app.current_tenant_id', TRUE)::UUID
            OR current_setting('app.current_role', TRUE) = 'platform_admin'
        )
    """)

    op.create_table(
        "funder_report_configs",
        sa.Column("config_id",         postgresql.UUID(as_uuid=True),
                  server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column("tenant_id",         postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.tenant_id"), nullable=False),
        sa.Column("report_name",       sa.String(200), nullable=False),
        sa.Column("schedule",          sa.String(20), server_default="monthly"),
        sa.Column("metrics_included",  postgresql.ARRAY(sa.Text), server_default="{}"),
        sa.Column("anonymized",        sa.Boolean, server_default="TRUE"),
        sa.Column("recipient_emails",  postgresql.ARRAY(sa.Text), server_default="{}"),
        sa.Column("last_generated_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at",        sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()")),
    )
    op.execute("ALTER TABLE funder_report_configs ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY frc_tenant ON funder_report_configs USING (
            tenant_id = current_setting('app.current_tenant_id', TRUE)::UUID
            OR current_setting('app.current_role', TRUE) = 'platform_admin'
        )
    """)

    # INDEXES
    op.create_index("idx_mol_task",    "match_override_log", ["task_id"])
    op.create_index("idx_mol_tenant",  "match_override_log", ["tenant_id","created_at"])
    op.create_index("idx_vps_vol",     "volunteer_performance_snapshots",
                    ["volunteer_id","snapshot_date"])
    op.create_index("idx_hii_hh",      "household_improvement_index",
                    ["household_id","window_days","computed_at"])
    op.create_index("idx_hii_tenant",  "household_improvement_index",
                    ["tenant_id","improvement_index"])
    op.create_index("idx_im_period",   "impact_metrics",
                    ["tenant_id","period_type","period_start"])
    op.create_index("idx_fe_unproc",   "feedback_events",
                    ["tenant_id","processed","created_at"],
                    postgresql_where=sa.text("processed = FALSE"))
    op.create_index("idx_fe_household","feedback_events", ["household_id"])


def downgrade() -> None:
    for tbl in ["funder_report_configs","feedback_events","impact_metrics",
                "household_improvement_index","volunteer_performance_snapshots",
                "match_override_log"]:
        op.drop_table(tbl)