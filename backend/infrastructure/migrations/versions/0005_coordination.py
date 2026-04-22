"""Phase 3: Volunteer Coordination Schema
   volunteers, volunteer_locations, tasks, task_state_log,
   notifications, volunteer_availability, dispatch_attempts

Revision ID: 0005_coordination
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0005_coordination'
down_revision = '0004_intelligence'
branch_labels = None
depends_on = None


def upgrade() -> None:


    # ── TABLE: volunteers ─────────────────────────────────────
    op.create_table(
        "volunteers",
        sa.Column("volunteer_id",         postgresql.UUID(as_uuid=True),
                  server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column("tenant_id",            postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.tenant_id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id",              postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.user_id",    ondelete="SET NULL"), nullable=True),
        # PII in vault
        sa.Column("pii_ref",              postgresql.UUID(as_uuid=True), nullable=True),
        # Profile
        sa.Column("preferred_language",   postgresql.ARRAY(sa.Text), server_default="{}"),
        sa.Column("skills",               postgresql.ARRAY(sa.Text), server_default="{}"),
        sa.Column("skill_proficiency",    postgresql.JSONB, server_default="{}"),
        sa.Column("cultural_context_tags",postgresql.ARRAY(sa.Text), server_default="{}"),
        sa.Column("ngo_affiliations",     postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
                  server_default="{}"),
        # Location
        sa.Column("location_home",        sa.Text, nullable=True),
        sa.Column("location_home_geo",    sa.Text, nullable=True),  # GEOGRAPHY added below
        sa.Column("ward_id",              sa.String(64), nullable=True),
        sa.Column("max_distance_km",      sa.Integer, server_default="10"),
        # Availability
        sa.Column("availability_schedule",postgresql.JSONB, server_default="{}"),
        # e.g. {"mon":["09:00-17:00"],"sat":["all_day"]}
        sa.Column("is_available_now",     sa.Boolean, server_default="FALSE"),
        # Metrics
        sa.Column("total_deployments",    sa.Integer, server_default="0"),
        sa.Column("outcome_rating",       sa.Float,   server_default="0.0"),
        sa.Column("response_rate",        sa.Float,   server_default="1.0"),
        sa.Column("burnout_risk_score",   sa.Float,   server_default="0.0"),
        # Prior household history (for continuity matching)
        sa.Column("prior_households",     postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
                  server_default="{}"),
        # Status
        sa.Column("active",               sa.Boolean, server_default="TRUE"),
        sa.Column("verified",             sa.Boolean, server_default="FALSE"),
        sa.Column("last_deployed_at",     sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_active_at",       sa.TIMESTAMP(timezone=True), nullable=True),
        # Notification channels
        sa.Column("whatsapp_number",      sa.String(20), nullable=True),
        sa.Column("phone_number",         sa.String(20), nullable=True),
        sa.Column("push_token",           sa.Text,       nullable=True),
        sa.Column("preferred_channel",    sa.String(20), server_default="push"),
        # Audit
        sa.Column("created_at",           sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at",           sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()")),
    )
    op.execute("ALTER TABLE volunteers ADD COLUMN location_home_point GEOGRAPHY(POINT,4326)")
    op.execute("ALTER TABLE volunteers ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY volunteers_tenant ON volunteers
        USING (
            tenant_id = current_setting('app.current_tenant_id', TRUE)::UUID
            OR current_setting('app.current_role', TRUE) = 'platform_admin'
        )
    """)

    # ── TABLE: volunteer_locations ────────────────────────────
    # Live GPS pings from mobile app — one row per ping (5-min interval)
    op.create_table(
        "volunteer_locations",
        sa.Column("location_id",   postgresql.UUID(as_uuid=True),
                  server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column("volunteer_id",  postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("volunteers.volunteer_id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id",     postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.tenant_id"), nullable=False),
        sa.Column("pinged_at",     sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()")),
        sa.Column("accuracy_m",    sa.Float, nullable=True),
        sa.Column("battery_pct",   sa.Integer, nullable=True),
    )
    op.execute("ALTER TABLE volunteer_locations ADD COLUMN location_point GEOGRAPHY(POINT,4326)")
    # Latest location view — maintained by trigger
    op.execute("""
        CREATE OR REPLACE FUNCTION fn_update_volunteer_current_location()
        RETURNS TRIGGER AS $$
        BEGIN
            UPDATE volunteers
            SET last_active_at = NOW()
            WHERE volunteer_id = NEW.volunteer_id;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER trg_volunteer_location_ping
        AFTER INSERT ON volunteer_locations
        FOR EACH ROW EXECUTE FUNCTION fn_update_volunteer_current_location();
    """)

    # ── TABLE: volunteer_burnout_log ──────────────────────────
    op.create_table(
        "volunteer_burnout_log",
        sa.Column("log_id",              postgresql.UUID(as_uuid=True),
                  server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column("volunteer_id",        postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("volunteers.volunteer_id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id",           postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.tenant_id"), nullable=False),
        sa.Column("burnout_risk_score",  sa.Float, nullable=False),
        sa.Column("deployments_7d",      sa.Integer),
        sa.Column("deployments_30d",     sa.Integer),
        sa.Column("consecutive_days",    sa.Integer),
        sa.Column("avg_outcome_rating",  sa.Float),
        sa.Column("alert_sent",          sa.Boolean, server_default="FALSE"),
        sa.Column("computed_at",         sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()")),
    )
    op.execute("CREATE RULE burnout_no_update AS ON UPDATE TO volunteer_burnout_log DO INSTEAD NOTHING")
    op.execute("CREATE RULE burnout_no_delete AS ON DELETE TO volunteer_burnout_log DO INSTEAD NOTHING")

    # ── TABLE: tasks ──────────────────────────────────────────
    op.create_table(
        "tasks",
        sa.Column("task_id",              postgresql.UUID(as_uuid=True),
                  server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column("tenant_id",            postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.tenant_id"), nullable=False),
        sa.Column("need_id",              postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("need_records.need_id", ondelete="CASCADE"), nullable=False),
        sa.Column("household_id",         postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("households.household_id", ondelete="SET NULL"), nullable=True),
        sa.Column("assigned_volunteer_id",postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("volunteers.volunteer_id", ondelete="SET NULL"), nullable=True),
        sa.Column("coordinator_id",       postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True),
        # State machine
        sa.Column("status",               sa.Enum(
            "unassigned","dispatched","accepted","in_progress",
            "completed","cancelled","needs_reassignment","closed",
            name="task_status_enum"),
 server_default="unassigned"),
        # Timestamps per state
        sa.Column("dispatched_at",        sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("accepted_at",          sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("started_at",           sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("completed_at",         sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("closed_at",            sa.TIMESTAMP(timezone=True), nullable=True),
        # Outcome
        sa.Column("outcome_status",       sa.Enum(
            "need_fully_met","partially_met","unresolved","follow_up_required",
            name="outcome_status_enum"),
 nullable=True),
        sa.Column("outcome_notes",        sa.Text, nullable=True),
        sa.Column("materials_provided",   postgresql.JSONB, server_default="{}"),
        sa.Column("volunteer_rating",     sa.Float, nullable=True),
        sa.Column("follow_up_required",   sa.Boolean, server_default="FALSE"),
        # Dispatch metadata
        sa.Column("match_score",          sa.Float, nullable=True),
        sa.Column("match_components",     postgresql.JSONB, server_default="{}"),
        sa.Column("dispatch_timeout_min", sa.Integer, server_default="20"),
        sa.Column("cancellation_attempts",sa.Integer, server_default="0"),
        sa.Column("auto_dispatch",        sa.Boolean, server_default="FALSE"),
        # Briefing
        sa.Column("briefing_text",        sa.Text, nullable=True),
        sa.Column("briefing_language",    sa.String(10), nullable=True),
        # Audit
        sa.Column("created_at",           sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at",           sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()")),
    )
    op.execute("ALTER TABLE tasks ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tasks_tenant ON tasks
        USING (
            tenant_id = current_setting('app.current_tenant_id', TRUE)::UUID
            OR current_setting('app.current_role', TRUE) = 'platform_admin'
        )
    """)

    # ── TABLE: task_state_log ─────────────────────────────────
    op.create_table(
        "task_state_log",
        sa.Column("log_id",        postgresql.UUID(as_uuid=True),
                  server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column("task_id",       postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tasks.task_id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id",     postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.tenant_id"), nullable=False),
        sa.Column("from_status",   sa.String(50)),
        sa.Column("to_status",     sa.String(50), nullable=False),
        sa.Column("triggered_by",  postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True),
        sa.Column("notes",         sa.Text, nullable=True),
        sa.Column("transitioned_at",sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()")),
    )
    op.execute("CREATE RULE tsl_no_update AS ON UPDATE TO task_state_log DO INSTEAD NOTHING")
    op.execute("CREATE RULE tsl_no_delete AS ON DELETE TO task_state_log DO INSTEAD NOTHING")
    op.execute("ALTER TABLE task_state_log ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tsl_tenant ON task_state_log
        USING (
            tenant_id = current_setting('app.current_tenant_id', TRUE)::UUID
            OR current_setting('app.current_role', TRUE) = 'platform_admin'
        )
    """)

    # ── TABLE: dispatch_attempts ──────────────────────────────
    op.create_table(
        "dispatch_attempts",
        sa.Column("attempt_id",     postgresql.UUID(as_uuid=True),
                  server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column("task_id",        postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tasks.task_id", ondelete="CASCADE"), nullable=False),
        sa.Column("volunteer_id",   postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("volunteers.volunteer_id"), nullable=False),
        sa.Column("tenant_id",      postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.tenant_id"), nullable=False),
        sa.Column("attempt_number", sa.Integer, server_default="1"),
        sa.Column("match_score",    sa.Float, nullable=True),
        sa.Column("channel_used",   sa.String(20)),
        sa.Column("sent_at",        sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()")),
        sa.Column("responded_at",   sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("outcome",        sa.Enum("accepted","declined","no_response","cancelled",
                                             name="dispatch_outcome_enum"),
 nullable=True),
        sa.Column("decline_reason", sa.Text, nullable=True),
    )
    op.execute("ALTER TABLE dispatch_attempts ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY da_tenant ON dispatch_attempts
        USING (
            tenant_id = current_setting('app.current_tenant_id', TRUE)::UUID
            OR current_setting('app.current_role', TRUE) = 'platform_admin'
        )
    """)

    # ── TABLE: notifications ──────────────────────────────────
    op.create_table(
        "notifications",
        sa.Column("notification_id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column("tenant_id",       postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.tenant_id"), nullable=False),
        sa.Column("task_id",         postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tasks.task_id", ondelete="SET NULL"), nullable=True),
        sa.Column("volunteer_id",    postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("volunteers.volunteer_id", ondelete="SET NULL"), nullable=True),
        sa.Column("recipient_type",  sa.String(30), server_default="volunteer"),
        sa.Column("channel",         sa.Enum("push","whatsapp","sms","email",
                                              name="notification_channel_enum"),
 nullable=False),
        sa.Column("template_key",    sa.String(100), nullable=True),
        sa.Column("message_body",    sa.Text, nullable=False),
        sa.Column("language",        sa.String(10), server_default="en"),
        sa.Column("status",          sa.Enum("pending","sent","delivered","failed","read",
                                              name="notification_status_enum"),
                  server_default="pending"),
        sa.Column("sent_at",         sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("delivered_at",    sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("read_at",         sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("error_detail",    sa.Text, nullable=True),
        sa.Column("external_id",     sa.String(255), nullable=True),
        sa.Column("created_at",      sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()")),
    )
    op.execute("ALTER TABLE notifications ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY notif_tenant ON notifications
        USING (
            tenant_id = current_setting('app.current_tenant_id', TRUE)::UUID
            OR current_setting('app.current_role', TRUE) = 'platform_admin'
        )
    """)

    # ── update_at triggers ────────────────────────────────────
    for tbl in ["volunteers", "tasks"]:
        op.execute(f"""
            CREATE TRIGGER set_updated_at_{tbl}
            BEFORE UPDATE ON {tbl}
            FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();
        """)

    # ── INDEXES ───────────────────────────────────────────────
    op.execute("CREATE INDEX idx_vol_home_geo ON volunteers USING GIST(location_home_point)")
    op.execute("CREATE INDEX idx_volloc_geo   ON volunteer_locations USING GIST(location_point)")
    op.create_index("idx_vol_tenant_active",  "volunteers", ["tenant_id","active","verified"])
    op.create_index("idx_vol_burnout",        "volunteers", ["tenant_id","burnout_risk_score"])
    op.create_index("idx_vol_skills",         "volunteers", ["skills"],
                    postgresql_using="gin")
    op.create_index("idx_tasks_tenant_status","tasks",      ["tenant_id","status"])
    op.create_index("idx_tasks_need",         "tasks",      ["need_id"])
    op.create_index("idx_tasks_volunteer",    "tasks",      ["assigned_volunteer_id","status"])
    op.create_index("idx_tasks_unassigned",   "tasks",      ["tenant_id","status","created_at"],
                    postgresql_where=sa.text("status = 'unassigned'"))
    op.create_index("idx_tsl_task",           "task_state_log",    ["task_id","transitioned_at"])
    op.create_index("idx_da_task",            "dispatch_attempts", ["task_id","attempt_number"])
    op.create_index("idx_notif_vol",          "notifications",     ["volunteer_id","status"])
    op.create_index("idx_volloc_vol",         "volunteer_locations",
                    ["volunteer_id","pinged_at"])
    op.execute("""
        CREATE INDEX idx_vol_tasks_pending ON notifications(task_id)
        WHERE status = 'pending'
    """)


def downgrade() -> None:
    for tbl in ["notifications","dispatch_attempts","task_state_log",
                "tasks","volunteer_burnout_log","volunteer_locations","volunteers"]:
        op.drop_table(tbl)
    for e in ["task_status_enum","notification_channel_enum",
              "notification_status_enum","dispatch_outcome_enum","outcome_status_enum"]:
        op.execute(f"DROP TYPE IF EXISTS {e}")
    op.execute("DROP FUNCTION IF EXISTS fn_update_volunteer_current_location CASCADE")