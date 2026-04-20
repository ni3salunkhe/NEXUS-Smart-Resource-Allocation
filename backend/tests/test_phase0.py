"""
NEXUS Phase 0 — Validation Tests
Tests: JWT auth, RBAC permissions, tenant isolation, RLS, audit trail
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.auth.main import app
from shared.auth import (
    create_access_token, decode_token, hash_password, verify_password,
    has_permission, ROLE_PERMISSIONS,
)
from shared.config import get_settings

settings = get_settings()


# ── Auth unit tests ───────────────────────────────────────────
class TestPasswordHashing:
    def test_hash_and_verify(self):
        pw = "my_secure_password_123"
        hashed = hash_password(pw)
        assert verify_password(pw, hashed)
        assert not verify_password("wrong_password", hashed)

    def test_different_hashes_same_password(self):
        pw = "same_password"
        h1 = hash_password(pw)
        h2 = hash_password(pw)
        assert h1 != h2  # bcrypt uses random salt


class TestJWTTokens:
    def test_create_and_decode_access_token(self):
        token = create_access_token(
            user_id="user-123",
            tenant_id="tenant-456",
            role="coordinator",
        )
        assert token is not None
        payload = decode_token(token)
        assert payload["sub"] == "user-123"
        assert payload["tenant_id"] == "tenant-456"
        assert payload["role"] == "coordinator"
        assert payload["type"] == "access"

    def test_decode_invalid_token_raises(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            decode_token("invalid.token.here")
        assert exc.value.status_code == 401

    def test_platform_admin_null_tenant(self):
        token = create_access_token(
            user_id="admin-001",
            tenant_id=None,
            role="platform_admin",
        )
        payload = decode_token(token)
        assert payload["tenant_id"] is None
        assert payload["role"] == "platform_admin"


# ── RBAC permission tests ─────────────────────────────────────
class TestRBAC:
    @pytest.mark.parametrize("role,permission,expected", [
        ("platform_admin", "households:delete", True),
        ("platform_admin", "any_random_permission", True),
        ("ngo_admin", "households:create", True),
        ("ngo_admin", "households:read", True),
        ("coordinator", "needs:create", True),
        ("coordinator", "tenants:delete", False),
        ("field_worker", "needs:create", True),
        ("field_worker", "needs:delete", False),
        ("field_worker", "analytics:read", False),
        ("funder_readonly", "analytics:read", True),
        ("funder_readonly", "needs:create", False),
    ])
    def test_permissions(self, role, permission, expected):
        assert has_permission(role, permission) == expected

    def test_wildcard_resource(self):
        # coordinator has households:*
        assert has_permission("coordinator", "households:create")
        assert has_permission("coordinator", "households:delete")
        assert has_permission("coordinator", "households:custom_action")

    def test_all_roles_defined(self):
        required_roles = {"platform_admin", "ngo_admin", "coordinator",
                          "field_worker", "funder_readonly"}
        assert required_roles.issubset(set(ROLE_PERMISSIONS.keys()))


# ── API integration tests (mocked DB) ────────────────────────
@pytest.mark.asyncio
class TestAuthAPI:
    @pytest_asyncio.fixture
    async def client(self):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as c:
            yield c

    async def test_health_endpoint(self, client):
        with patch("services.auth.main.check_db_health",
                   return_value={"postgres": "ok"}):
            resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["service"] == "nexus-auth"

    async def test_login_invalid_credentials(self, client):
        # SQLAlchemy async: await db.execute() returns a Result object,
        # then result.fetchone() is synchronous
        mock_result = MagicMock()
        mock_result.fetchone.return_value = None

        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result

        async def mock_get_db():
            yield mock_db

        from shared.database import get_db
        app.dependency_overrides[get_db] = mock_get_db
        try:
            resp = await client.post("/auth/login", json={
                "email": "wrong@test.com",
                "password": "wrongpass",
            })
        finally:
            app.dependency_overrides.pop(get_db, None)
        assert resp.status_code == 401

    async def test_protected_endpoint_no_token(self, client):
        resp = await client.get("/users/me")
        assert resp.status_code == 401

    async def test_protected_endpoint_invalid_token(self, client):
        resp = await client.get(
            "/users/me",
            headers={"Authorization": "Bearer invalid.token.here"}
        )
        assert resp.status_code == 401


# ── Tenant isolation tests ────────────────────────────────────
class TestTenantIsolation:
    def test_different_tenants_get_different_tokens(self):
        t1 = create_access_token("u1", "tenant-A", "coordinator")
        t2 = create_access_token("u2", "tenant-B", "coordinator")
        p1 = decode_token(t1)
        p2 = decode_token(t2)
        assert p1["tenant_id"] != p2["tenant_id"]
        assert p1["sub"] != p2["sub"]

    def test_auth_context_require_raises_for_missing_permission(self):
        from shared.auth import AuthContext
        from fastapi import HTTPException

        ctx = AuthContext(user_id="u1", tenant_id="t1", role="field_worker")
        with pytest.raises(HTTPException) as exc:
            ctx.require("analytics:read")
        assert exc.value.status_code == 403


# ── Kafka event tests ─────────────────────────────────────────
class TestKafkaEvents:
    def test_event_serialization_roundtrip(self):
        from shared.kafka import NexusEvent
        event = NexusEvent(
            event_type="need.created",
            payload={"need_id": "abc-123", "category": "food"},
            tenant_id="tenant-001",
            user_id="user-001",
        )
        serialized = event.serialize()
        assert isinstance(serialized, bytes)

        restored = NexusEvent.deserialize(serialized)
        assert restored.event_type == "need.created"
        assert restored.payload["need_id"] == "abc-123"
        assert restored.tenant_id == "tenant-001"
        assert restored.event_id == event.event_id

    def test_event_has_required_fields(self):
        from shared.kafka import NexusEvent
        event = NexusEvent(event_type="test.event", payload={})
        d = event.to_dict()
        for field in ["event_id", "event_type", "payload", "tenant_id",
                      "user_id", "correlation_id", "timestamp"]:
            assert field in d


# ── Run validation ────────────────────────────────────────────
if __name__ == "__main__":
    import subprocess
    result = subprocess.run(
        ["python", "-m", "pytest", __file__, "-v", "--tb=short"],
        cwd=os.path.join(os.path.dirname(__file__), "..")
    )
    sys.exit(result.returncode)