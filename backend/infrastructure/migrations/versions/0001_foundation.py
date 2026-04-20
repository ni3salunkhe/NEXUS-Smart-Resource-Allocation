"""Phase 0: Foundation schema
   tenants, users, refresh_tokens, audit_log, RLS policies

Revision ID: 0001_foundation
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0001_foundation'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Extensions
    op.execute("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\"")
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    # ── user_role enum ────────────────────────────────────────
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE user_role AS ENUM (
                'field_worker','coordinator','ngo_admin',
                'funder_readonly','platform_admin'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)

    # ── tenants ───────────────────────────────────────────────
    op.create_table(
        "tenants",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False, unique=True),
        sa.Column("contact_email", sa.String(255), nullable=False),
        sa.Column("plan_tier", sa.String(50), server_default="standard"),
        sa.Column("cross_tenant_linking_policy", sa.String(50), server_default="coordinator_only"),
        sa.Column("settings", postgresql.JSONB, server_default="{}"),
        sa.Column("active", sa.Boolean, server_default="TRUE"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()")),
    )
    op.execute("ALTER TABLE tenants ENABLE ROW LEVEL SECURITY")

    # ── users ─────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.tenant_id", ondelete="CASCADE"), nullable=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("name_encrypted", sa.LargeBinary, nullable=True),
        sa.Column("phone_encrypted", sa.LargeBinary, nullable=True),
        sa.Column("role", sa.Enum("field_worker","coordinator","ngo_admin",
                                   "funder_readonly","platform_admin",
                                   name="user_role"), nullable=False),
        sa.Column("preferred_language", sa.String(10), server_default="en"),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean, server_default="TRUE"),
        sa.Column("last_login_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()")),
        sa.UniqueConstraint("tenant_id", "email", name="uq_users_tenant_email"),
    )
    op.execute("ALTER TABLE users ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation_users ON users
        USING (
            tenant_id = current_setting('app.current_tenant_id', TRUE)::UUID
            OR current_setting('app.current_role', TRUE) = 'platform_admin'
            OR current_setting('app.current_tenant_id', TRUE) = ''
        )
    """)

    # ── refresh_tokens ────────────────────────────────────────
    op.create_table(
        "refresh_tokens",
        sa.Column("token_id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(255), nullable=False, unique=True),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("revoked", sa.Boolean, server_default="FALSE"),
        sa.Column("revoked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("issued_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("device_fingerprint", sa.String(255), nullable=True),
    )

    # ── audit_log ─────────────────────────────────────────────
    op.create_table(
        "audit_log",
        sa.Column("event_id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("resource_type", sa.String(100), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("before_snapshot", postgresql.JSONB, nullable=True),
        sa.Column("after_snapshot", postgresql.JSONB, nullable=True),
        sa.Column("ip_address", postgresql.INET, nullable=True),
        sa.Column("user_agent", sa.Text, nullable=True),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_timestamp", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()")),
    )
    # Append-only rules
    op.execute("CREATE RULE audit_log_no_update AS ON UPDATE TO audit_log DO INSTEAD NOTHING")
    op.execute("CREATE RULE audit_log_no_delete AS ON DELETE TO audit_log DO INSTEAD NOTHING")

    # ── Audit trigger function ────────────────────────────────
    op.execute("""
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
    """)

    # Attach audit to users
    op.execute("""
        CREATE TRIGGER audit_users
        AFTER INSERT OR UPDATE OR DELETE ON users
        FOR EACH ROW EXECUTE FUNCTION fn_audit_trigger()
    """)

    # ── updated_at trigger ────────────────────────────────────
    op.execute("""
        CREATE OR REPLACE FUNCTION fn_set_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
        $$ LANGUAGE plpgsql;
    """)
    for tbl in ["tenants", "users"]:
        op.execute(f"""
            CREATE TRIGGER set_updated_at_{tbl}
            BEFORE UPDATE ON {tbl}
            FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at()
        """)

    # ── Indexes ───────────────────────────────────────────────
    op.create_index("idx_users_tenant",   "users",     ["tenant_id"])
    op.create_index("idx_users_role",     "users",     ["tenant_id", "role"])
    op.create_index("idx_audit_tenant",   "audit_log", ["tenant_id", "event_timestamp"])
    op.create_index("idx_audit_user",     "audit_log", ["user_id",   "event_timestamp"])
    op.create_index("idx_audit_resource", "audit_log", ["resource_type", "resource_id"])
    op.create_index("idx_refresh_hash",   "refresh_tokens", ["token_hash"],
                    postgresql_where=sa.text("revoked = FALSE"))


def downgrade() -> None:
    for tbl in ["refresh_tokens", "audit_log", "users", "tenants"]:
        op.drop_table(tbl)
    op.execute("DROP TYPE IF EXISTS user_role")
    op.execute("DROP FUNCTION IF EXISTS fn_audit_trigger CASCADE")
    op.execute("DROP FUNCTION IF EXISTS fn_set_updated_at CASCADE")