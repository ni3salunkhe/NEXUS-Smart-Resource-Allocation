from typing import Optional
from fastapi import FastAPI, Depends, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from sqlalchemy import text
from datetime import datetime, timedelta, timezone
import hashlib
import logging

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from shared.config import get_settings
from shared.database import get_db, check_db_health
from shared.auth import (
    hash_password, verify_password,
    create_access_token, create_refresh_token, decode_token,
    get_current_user, AuthContext, TenantRLSMiddleware,
)
from shared.logging_config import setup_logging, add_global_error_handler

setup_logging("auth")
logger = logging.getLogger(__name__)
settings = get_settings()

app = FastAPI(
    title="NEXUS Auth Service",
    version="2.0.0",
    docs_url="/docs" if settings.DEBUG else None,
)
add_global_error_handler(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(TenantRLSMiddleware)

@app.on_event("startup")
async def ensure_system_admin():
    """Create system admin if no users exist."""
    # M13: Warn loudly if default password is still in use
    if settings.SYSTEM_ADMIN_PASSWORD == "admin123":
        logger.critical(
            "\n" + "="*70 +
            "\n[SECURITY] SYSTEM_ADMIN_PASSWORD is still the default 'admin123'!" +
            "\n          Change this via environment variable before production!" +
            "\n" + "="*70
        )

    from shared.database import AsyncSessionFactory
    async with AsyncSessionFactory() as db:
        result = await db.execute(text("SELECT user_id FROM users WHERE role = 'platform_admin' LIMIT 1"))
        admin = result.fetchone()

        if not admin:
            logger.info("No platform_admin found. Creating system admin...")
            pw_hash = hash_password(settings.SYSTEM_ADMIN_PASSWORD)
            await db.execute(
                text("""
                    INSERT INTO users (email, password_hash, role, display_name, is_active)
                    VALUES (:email, :pw_hash, 'platform_admin', 'System Admin', true)
                """),
                {"email": settings.SYSTEM_ADMIN_EMAIL, "pw_hash": pw_hash}
            )
            await db.commit()
            logger.info(f"System admin created with email: {settings.SYSTEM_ADMIN_EMAIL}")


# ── Schemas ───────────────────────────────────────────────────
class LoginRequest(BaseModel):
    email: str
    password: str
    tenant_slug: Optional[str] = None  # None = platform admin login


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user_id: str
    role: str
    tenant_id: Optional[str] = None
    tenant_name: Optional[str] = None
    expires_in: int  # seconds


class RefreshRequest(BaseModel):
    refresh_token: str


class RegisterUserRequest(BaseModel):
    email: EmailStr
    password: str
    name: str
    role: str = "field_worker"
    preferred_language: str = "en"


class UserResponse(BaseModel):
    user_id: str
    email: str
    role: str
    tenant_id: Optional[str] = None
    is_active: bool
    created_at: datetime


class TenantCreateRequest(BaseModel):
    name: str
    slug: str
    contact_email: EmailStr
    plan_tier: str = "standard"


class SignupRequest(BaseModel):
    email: EmailStr
    password: str
    display_name: str
    tenant_id: str
    role: str = "volunteer"


class PublicTenantResponse(BaseModel):
    tenant_id: str
    name: str
    slug: str


# ── Routes ────────────────────────────────────────────────────
@app.post("/auth/login", response_model=LoginResponse)
async def login(
    body: LoginRequest,
    request: Request,
    db=Depends(get_db),
):
    # Resolve tenant
    tenant_id = None
    if body.tenant_slug:
        result = await db.execute(
            text("SELECT tenant_id FROM tenants WHERE slug = :slug AND active = TRUE"),
            {"slug": body.tenant_slug}
        )
        row = result.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Tenant not found")
        tenant_id = str(row.tenant_id)

    # Fetch user and tenant name
    query = """
        SELECT u.user_id, u.password_hash, u.role, u.is_active, u.tenant_id, t.name as tenant_name
        FROM users u
        LEFT JOIN tenants t ON u.tenant_id = t.tenant_id
        WHERE u.email = :email
        AND (u.tenant_id = :tenant_id OR (:tenant_id IS NULL AND u.tenant_id IS NULL))
    """
    result = await db.execute(
        text(query),
        {"email": body.email, "tenant_id": tenant_id}
    )
    user = result.fetchone()

    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")

    # Create tokens
    access_token = create_access_token(
        user_id=str(user.user_id),
        tenant_id=user.tenant_id,
        role=user.role,
    )
    raw_refresh, hashed_refresh = create_refresh_token()

    # Store refresh token
    expires = datetime.now(timezone.utc) + timedelta(
        days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS
    )
    await db.execute(
        text("""
            INSERT INTO refresh_tokens(user_id, token_hash, expires_at, device_fingerprint)
            VALUES (:user_id, :hash, :expires, :device)
        """),
        {
            "user_id": str(user.user_id),
            "hash": hashed_refresh,
            "expires": expires,
            "device": request.headers.get("User-Agent", "")[:255],
        }
    )

    # Update last login
    await db.execute(
        text("UPDATE users SET last_login_at = NOW() WHERE user_id = :uid"),
        {"uid": str(user.user_id)}
    )

    return LoginResponse(
        access_token=access_token,
        refresh_token=raw_refresh,
        user_id=str(user.user_id),
        role=user.role,
        tenant_id=str(user.tenant_id) if user.tenant_id else None,
        tenant_name=user.tenant_name,
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@app.post("/auth/refresh", response_model=LoginResponse)
async def refresh_token(body: RefreshRequest, db=Depends(get_db)):
    hashed = hashlib.sha256(body.refresh_token.encode()).hexdigest()

    result = await db.execute(
        text("""
            SELECT rt.token_id, rt.user_id, rt.expires_at,
                   u.role, u.tenant_id, u.is_active
            FROM refresh_tokens rt
            JOIN users u ON rt.user_id = u.user_id
            WHERE rt.token_hash = :hash AND rt.revoked = FALSE
        """),
        {"hash": hashed}
    )
    token_row = result.fetchone()

    if not token_row:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    if token_row.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Refresh token expired")

    if not token_row.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")

    # Rotate refresh token (revoke old, issue new)
    await db.execute(
        text("UPDATE refresh_tokens SET revoked = TRUE, revoked_at = NOW() WHERE token_id = :tid"),
        {"tid": str(token_row.token_id)}
    )

    new_access = create_access_token(
        user_id=str(token_row.user_id),
        tenant_id=token_row.tenant_id,
        role=token_row.role,
    )
    raw_refresh, hashed_refresh = create_refresh_token()
    expires = datetime.now(timezone.utc) + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)

    await db.execute(
        text("""
            INSERT INTO refresh_tokens(user_id, token_hash, expires_at)
            VALUES (:user_id, :hash, :expires)
        """),
        {"user_id": str(token_row.user_id), "hash": hashed_refresh, "expires": expires}
    )

    return LoginResponse(
        access_token=new_access,
        refresh_token=raw_refresh,
        user_id=str(token_row.user_id),
        role=token_row.role,
        tenant_id=str(token_row.tenant_id) if token_row.tenant_id else None,
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@app.post("/auth/signup", status_code=status.HTTP_201_CREATED)
async def signup(body: SignupRequest, db=Depends(get_db)):
    # Check if email exists
    result = await db.execute(
        text("SELECT user_id FROM users WHERE email = :email"),
        {"email": body.email}
    )
    if result.fetchone():
        raise HTTPException(status_code=409, detail="Email already registered")

    # Verify tenant
    result = await db.execute(
        text("SELECT name FROM tenants WHERE tenant_id = :tid"),
        {"tid": body.tenant_id}
    )
    tenant = result.fetchone()
    if not tenant:
        raise HTTPException(status_code=404, detail="Organization not found")

    # Create user
    pw_hash = hash_password(body.password)
    result = await db.execute(
        text("""
            INSERT INTO users (tenant_id, email, password_hash, display_name, role, is_active)
            VALUES (:tid, :email, :pw_hash, :name, :role, true)
            RETURNING user_id
        """),
        {
            "tid": body.tenant_id,
            "email": body.email,
            "pw_hash": pw_hash,
            "name": body.display_name,
            "role": body.role,
        }
    )
    user_row = result.fetchone()
    user_id = str(user_row.user_id)
    await db.commit()

    # Tokens
    access_token = create_access_token(
        user_id=user_id,
        tenant_id=body.tenant_id,
        role=body.role,
    )
    raw_refresh, hashed_refresh = create_refresh_token()
    
    expires = datetime.now(timezone.utc) + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    await db.execute(
        text("INSERT INTO refresh_tokens (user_id, token_hash, expires_at) VALUES (:uid, :hash, :exp)"),
        {"uid": user_id, "hash": hashed_refresh, "exp": expires}
    )
    await db.commit()

    return {
        "access_token": access_token,
        "refresh_token": raw_refresh,
        "user_id": user_id,
        "display_name": body.display_name,
        "role": body.role,
        "tenant_id": body.tenant_id,
        "org_name": tenant.name
    }


@app.get("/auth/tenants/public", response_model=list[PublicTenantResponse])
async def list_tenants_public(db=Depends(get_db)):
    result = await db.execute(text("SELECT tenant_id, name, slug FROM tenants WHERE active = TRUE ORDER BY name ASC"))
    rows = result.fetchall()
    return [
        {
            "tenant_id": str(r.tenant_id),
            "name": r.name,
            "slug": r.slug
        } for r in rows
    ]


@app.post("/auth/logout")
async def logout(
    body: RefreshRequest,
    ctx: AuthContext = Depends(get_current_user),
    db=Depends(get_db),
):
    hashed = hashlib.sha256(body.refresh_token.encode()).hexdigest()
    await db.execute(
        text("""
            UPDATE refresh_tokens
            SET revoked = TRUE, revoked_at = NOW()
            WHERE token_hash = :hash AND user_id = :uid
        """),
        {"hash": hashed, "uid": ctx.user_id}
    )
    return {"detail": "Logged out"}


@app.get("/tenants", response_model=list)
async def list_tenants(
    ctx: AuthContext = Depends(get_current_user),
    db=Depends(get_db),
):
    ctx.require("platform_admin")
    result = await db.execute(text("SELECT tenant_id, name, slug, contact_email, plan_tier, created_at FROM tenants ORDER BY created_at DESC"))
    rows = result.fetchall()
    return [
        {
            "tenant_id": str(r.tenant_id),
            "name": r.name,
            "slug": r.slug,
            "contact_email": r.contact_email,
            "plan_tier": r.plan_tier,
            "created_at": r.created_at.isoformat()
        } for r in rows
    ]


@app.post("/tenants", response_model=dict)
async def create_tenant(
    body: TenantCreateRequest,
    ctx: AuthContext = Depends(get_current_user),
    db=Depends(get_db),
):
    ctx.require("platform_admin")  # only platform admin creates tenants

    result = await db.execute(
        text("""
            INSERT INTO tenants(name, slug, contact_email, plan_tier)
            VALUES (:name, :slug, :email, :plan)
            RETURNING tenant_id, name, slug, created_at
        """),
        {"name": body.name, "slug": body.slug, "email": body.contact_email, "plan": body.plan_tier}
    )
    row = result.fetchone()
    return {
        "tenant_id": str(row.tenant_id),
        "name": row.name,
        "slug": row.slug,
        "created_at": row.created_at.isoformat(),
    }


@app.post("/users", response_model=UserResponse)
async def create_user(
    body: RegisterUserRequest,
    ctx: AuthContext = Depends(get_current_user),
    db=Depends(get_db),
):
    ctx.require("users:create")

    result = await db.execute(
        text("""
            INSERT INTO users(tenant_id, email, password_hash, role, preferred_language)
            VALUES (:tenant_id, :email, :pw_hash, :role, :lang)
            RETURNING user_id, email, role, tenant_id, is_active, created_at
        """),
        {
            "tenant_id": ctx.tenant_id,
            "email": body.email,
            "pw_hash": hash_password(body.password),
            "role": body.role,
            "lang": body.preferred_language,
        }
    )
    row = result.fetchone()
    return UserResponse(
        user_id=str(row.user_id),
        email=row.email,
        role=row.role,
        tenant_id=str(row.tenant_id) if row.tenant_id else None,
        is_active=row.is_active,
        created_at=row.created_at,
    )


@app.get("/users/me", response_model=UserResponse)
async def get_me(
    ctx: AuthContext = Depends(get_current_user),
    db=Depends(get_db),
):
    result = await db.execute(
        text("SELECT user_id, email, role, tenant_id, is_active, created_at FROM users WHERE user_id = :uid"),
        {"uid": ctx.user_id}
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    return UserResponse(
        user_id=str(row.user_id),
        email=row.email,
        role=row.role,
        tenant_id=str(row.tenant_id) if row.tenant_id else None,
        is_active=row.is_active,
        created_at=row.created_at,
    )


@app.get("/health")
async def health():
    db_status = await check_db_health()
    return {
        "service": "nexus-auth",
        "status": "ok" if db_status.get("postgres") == "ok" else "degraded",
        "dependencies": db_status,
    }