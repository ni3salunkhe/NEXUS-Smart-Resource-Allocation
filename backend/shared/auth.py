from datetime import datetime, timedelta, timezone
from typing import Optional, Any
import hashlib
import secrets
import logging

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
import bcrypt as _bcrypt
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from .config import get_settings
from .database import get_db

logger = logging.getLogger(__name__)
settings = get_settings()

bearer_scheme = HTTPBearer(auto_error=False)


# ── Password utils ────────────────────────────────────────────
def hash_password(password: str) -> str:
    return _bcrypt.hashpw(password.encode(), _bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return _bcrypt.checkpw(plain.encode(), hashed.encode())


# ── JWT utils ─────────────────────────────────────────────────
def create_access_token(
    user_id: str,
    tenant_id: Optional[str],
    role: str,
    extra: dict[str, Any] = {},
) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {
        "sub":       user_id,
        "tenant_id": str(tenant_id) if tenant_id else None,
        "role":      role,
        "exp":       expire,
        "iat":       datetime.now(timezone.utc),
        "type":      "access",
        **extra,
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token() -> tuple[str, str]:
    """Returns (raw_token, hashed_token)."""
    raw = secrets.token_urlsafe(64)
    hashed = hashlib.sha256(raw.encode()).hexdigest()
    return raw, hashed


def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM]
        )
        return payload
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {e}",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ── Role permission map ───────────────────────────────────────
ROLE_PERMISSIONS: dict[str, set[str]] = {
    "platform_admin": {"*"},  # all permissions
    "ngo_admin": {
        "tenants:read", "tenants:update",
        "users:create", "users:read", "users:update", "users:delete",
        "households:*", "needs:*", "tasks:*", "volunteers:*",
        "analytics:read", "exports:create", "cross_tenant:manage",
    },
    "coordinator": {
        "users:create", "users:read",
        "households:*", "needs:*", "tasks:*", "volunteers:*",
        "analytics:read",
    },
    "field_worker": {
        "households:read", "households:create",
        "needs:create", "needs:read",
        "tasks:read", "tasks:update_own",
    },
    "funder_readonly": {
        "analytics:read", "exports:read_anonymized",
    },
}


def has_permission(role: str, permission: str) -> bool:
    perms = ROLE_PERMISSIONS.get(role, set())
    if "*" in perms:
        return True
    if permission in perms:
        return True
    # wildcard resource match: "households:*"
    resource = permission.split(":")[0]
    return f"{resource}:*" in perms


# ── FastAPI auth dependency ───────────────────────────────────
class AuthContext:
    def __init__(
        self,
        user_id: str,
        tenant_id: Optional[str],
        role: str,
        email: Optional[str] = None,
    ):
        self.user_id   = user_id
        self.tenant_id = tenant_id
        self.role      = role
        self.email     = email

    def require(self, permission: str) -> None:
        if not has_permission(self.role, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {permission}",
            )


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> AuthContext:
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_token(credentials.credentials)

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
        )

    jwt_tenant_id = payload.get("tenant_id")

    # Platform admins have no tenant in JWT. Allow X-Tenant-ID header override.
    if not jwt_tenant_id:
        header_tenant = request.headers.get("X-Tenant-ID")
        if header_tenant and header_tenant not in ("", "null", "undefined"):
            jwt_tenant_id = header_tenant

    ctx = AuthContext(
        user_id=payload["sub"],
        tenant_id=jwt_tenant_id,
        role=payload["role"],
    )

    # Inject into request state for RLS middleware
    request.state.tenant_id = ctx.tenant_id
    request.state.user_id   = ctx.user_id
    request.state.role       = ctx.role

    return ctx



def require_permission(permission: str):
    """FastAPI dependency factory for permission checks."""
    async def _check(ctx: AuthContext = Depends(get_current_user)) -> AuthContext:
        ctx.require(permission)
        return ctx
    return _check


# ── RLS middleware ────────────────────────────────────────────
class TenantRLSMiddleware:
    """
    Injects tenant context into request state BEFORE route handler.
    Works alongside get_current_user dependency.
    Used for routes that need DB access before explicit auth.
    """
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            from starlette.requests import Request
            request = Request(scope, receive)
            # Default: no tenant context
            request.state.tenant_id = None
            request.state.user_id   = None
            request.state.role       = "anonymous"
        await self.app(scope, receive, send)