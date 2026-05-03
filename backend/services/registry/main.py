from fastapi import FastAPI, Depends, HTTPException, status, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
from uuid import UUID

import sys, os
# Adjust path to reach shared/ from current directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from shared.config import get_settings
from shared.database import get_db
from shared.auth import get_current_user, AuthContext, TenantRLSMiddleware, require_permission
from shared.logging_config import setup_logging, add_global_error_handler
from .schemas import (
    HouseholdCreate, HouseholdUpdate, HouseholdResponse, 
    ConsentCreate, ConsentResponse, 
    CrossTenantLinkCreate, CrossTenantLinkResponse,
    MergeRequest, SearchRequest,
    IdentityResolutionRequest, ResolutionResult,
    HouseholdHistoryResponse, GlobalSearchResponse, WardStat, PartnershipPolicy
)
from .service import registry_service

setup_logging("registry")

settings = get_settings()

app = FastAPI(
    title="NEXUS Household Registry Service",
    version="0.5.0",
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

# ── Auth Endpoints ────────────────────────────────────────────

from pydantic import BaseModel as PydanticBaseModel
from shared.auth import (
    verify_password, create_access_token, create_refresh_token, decode_token,
    hash_password
)
from sqlalchemy import text as sa_text
import hashlib

class LoginRequest(PydanticBaseModel):
    email: str
    password: str

class RefreshRequest(PydanticBaseModel):
    refresh_token: str

class SignupRequest(PydanticBaseModel):
    email: str
    password: str
    display_name: str
    tenant_id: str
    role: str = "volunteer"


@app.post("/auth/signup", status_code=201)
async def auth_signup(body: SignupRequest, db=Depends(get_db)):
    """Register a new user and return JWT + refresh token."""
    # Check email uniqueness
    existing = await db.execute(
        sa_text("SELECT user_id FROM users WHERE email = :email"),
        {"email": body.email}
    )
    if existing.fetchone():
        raise HTTPException(status_code=409, detail="Email already registered")

    # Verify tenant exists
    try:
        tenant_row = await db.execute(
            sa_text("SELECT name FROM tenants WHERE tenant_id = :tid"),
            {"tid": body.tenant_id}
        )
        tenant = tenant_row.fetchone()
        if not tenant:
            raise HTTPException(status_code=404, detail="Organization not found")
    except Exception as e:
        if "invalid input for query argument" in str(e) or "invalid UUID" in str(e):
            raise HTTPException(status_code=400, detail="Invalid Organization ID format. Must be a valid UUID.")
        raise

    # Hash password and insert user
    pw_hash = hash_password(body.password)
    result = await db.execute(
        sa_text("""
            INSERT INTO users (tenant_id, email, password_hash, display_name, role, is_active)
            VALUES (:tid, :email, :pw_hash, :display_name, :role, true)
            RETURNING user_id
        """),
        {
            "tid": body.tenant_id,
            "email": body.email,
            "pw_hash": pw_hash,
            "role": body.role,
        }
    )
    row = result.fetchone()
    user_id = str(row.user_id)

    # Issue JWT
    jwt_token = create_access_token(
        user_id=user_id,
        tenant_id=body.tenant_id,
        role=body.role,
        extra={"display_name": body.email},
    )
    raw_refresh, hashed_refresh = create_refresh_token()

    await db.execute(
        sa_text("""
            INSERT INTO refresh_tokens (user_id, token_hash, expires_at)
            VALUES (:uid, :hash, NOW() + INTERVAL '30 days')
        """),
        {"uid": user_id, "hash": hashed_refresh}
    )
    await db.commit()

    return {
        "jwt": jwt_token,
        "refresh_token": raw_refresh,
        "user_id": user_id,
        "display_name": body.email,
        "role": body.role,
        "tenant_id": body.tenant_id,
        "org_name": tenant.name,
        "ward_ids": [],
    }

@app.post("/auth/login")
async def auth_login(body: LoginRequest, db=Depends(get_db)):
    """Authenticate user and return JWT + refresh token."""
    result = await db.execute(
        sa_text("""
            SELECT user_id, tenant_id, password_hash, role
            FROM users WHERE email = :email AND is_active = true
        """),
        {"email": body.email}
    )
    user = result.fetchone()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # Fetch org name
    org_row = await db.execute(
        sa_text("SELECT name FROM tenants WHERE tenant_id = :tid"),
        {"tid": str(user.tenant_id)}
    )
    org = org_row.fetchone()

    # Fetch ward_ids for user
    ward_row = await db.execute(
        sa_text("SELECT ward_ids FROM user_ward_assignments WHERE user_id = :uid"),
        {"uid": str(user.user_id)}
    )
    ward = ward_row.fetchone()
    ward_ids = ward.ward_ids if ward else []

    jwt_token = create_access_token(
        user_id=str(user.user_id),
        tenant_id=str(user.tenant_id),
        role=user.role,
        extra={"display_name": body.email},
    )
    raw_refresh, hashed_refresh = create_refresh_token()

    # Store refresh token hash
    await db.execute(
        sa_text("""
            INSERT INTO refresh_tokens (user_id, token_hash, expires_at)
            VALUES (:uid, :hash, NOW() + INTERVAL '30 days')
            ON CONFLICT (user_id) DO UPDATE SET token_hash = :hash, expires_at = NOW() + INTERVAL '30 days'
        """),
        {"uid": str(user.user_id), "hash": hashed_refresh}
    )
    await db.commit()

    return {
        "jwt": jwt_token,
        "refresh_token": raw_refresh,
        "user_id": str(user.user_id),
        "display_name": body.email,
        "role": user.role,
        "tenant_id": str(user.tenant_id),
        "org_name": org.name if org else "Unknown",
        "ward_ids": ward_ids or [],
    }


@app.post("/auth/refresh")
async def auth_refresh(body: RefreshRequest, db=Depends(get_db)):
    """Exchange refresh token for new JWT + rotated refresh token."""
    import secrets, hashlib as hl
    token_hash = hl.sha256(body.refresh_token.encode()).hexdigest()
    result = await db.execute(
        sa_text("""
            SELECT rt.token_id, rt.user_id, u.tenant_id, u.role, u.display_name
            FROM refresh_tokens rt
            JOIN users u ON rt.user_id = u.user_id
            WHERE rt.token_hash = :hash AND rt.expires_at > NOW()
        """),
        {"hash": token_hash}
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    # H4: Rotate — generate a new refresh token, invalidate the old one
    new_raw    = secrets.token_urlsafe(64)
    new_hash   = hl.sha256(new_raw.encode()).hexdigest()
    await db.execute(
        sa_text("""
            UPDATE refresh_tokens
            SET token_hash = :new_hash,
                expires_at  = NOW() + INTERVAL '30 days',
                updated_at  = NOW()
            WHERE token_id = :tid
        """),
        {"new_hash": new_hash, "tid": str(row.token_id)}
    )
    await db.commit()

    jwt_token = create_access_token(
        user_id=str(row.user_id),
        tenant_id=str(row.tenant_id),
        role=row.role,
        extra={"display_name": row.display_name},
    )

    return {
        "jwt":           jwt_token,
        "refresh_token": new_raw,        # rotated token returned to client
        "user_id":       str(row.user_id),
        "tenant_id":     str(row.tenant_id),
        "role":          row.role,
        "display_name":  row.display_name,
    }


# ── Household CRUD ────────────────────────────────────────────

@app.post("/households", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_household(
    data: HouseholdCreate,
    ctx: AuthContext = Depends(get_current_user),
    db=Depends(get_db)
):
    ctx.require("households:create")
    return await registry_service.create_household(db, data, ctx.tenant_id, ctx.user_id)

@app.get("/households", response_model=List[HouseholdResponse])
async def search_households(
    ward_id: Optional[str] = None,
    landmark: Optional[str] = None,
    status: str = "active",
    has_child: Optional[bool] = None,
    has_elderly: Optional[bool] = None,
    min_vuln_score: Optional[float] = None,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    radius: int = 500,
    limit: int = 20,
    offset: int = 0,
    ctx: AuthContext = Depends(get_current_user),
    db=Depends(get_db)
):
    ctx.require("households:read")
    req = SearchRequest(
        ward_id=ward_id,
        landmark=landmark,
        status=status,
        has_child=has_child,
        has_elderly=has_elderly,
        min_vuln_score=min_vuln_score,
        latitude=lat,
        longitude=lon,
        radius_m=radius,
        limit=limit,
        offset=offset
    )
    return await registry_service.search_households(db, req, ctx.tenant_id)

@app.get("/households/{household_id}", response_model=HouseholdResponse)
async def get_household(
    household_id: UUID,
    include_members: bool = True,
    ctx: AuthContext = Depends(get_current_user),
    db=Depends(get_db)
):
    ctx.require("households:read")
    hh = await registry_service.get_household(db, str(household_id), ctx.tenant_id, include_members)
    if not hh:
        raise HTTPException(status_code=404, detail="Household not found")
    return hh

@app.patch("/households/{household_id}", response_model=dict)
async def update_household(
    household_id: UUID,
    data: HouseholdUpdate,
    ctx: AuthContext = Depends(get_current_user),
    db=Depends(get_db)
):
    ctx.require("households:update")
    return await registry_service.update_household(db, str(household_id), data, ctx.tenant_id, ctx.user_id)

@app.post("/households/merge", response_model=dict)
async def merge_households(
    req: MergeRequest,
    ctx: AuthContext = Depends(get_current_user),
    db=Depends(get_db)
):
    ctx.require("households:merge")
    return await registry_service.merge_households(db, req, ctx.tenant_id, ctx.user_id)

# ── Consent ───────────────────────────────────────────────────

@app.post("/households/{household_id}/consent", response_model=dict)
async def add_consent(
    household_id: UUID,
    data: ConsentCreate,
    ctx: AuthContext = Depends(get_current_user),
    db=Depends(get_db)
):
    ctx.require("households:update")
    return await registry_service.add_consent(db, str(household_id), data, ctx.tenant_id, ctx.user_id)

@app.delete("/households/{household_id}/consent/{consent_id}", response_model=dict)
async def revoke_consent(
    household_id: UUID,
    consent_id: UUID,
    reason: str = "",
    ctx: AuthContext = Depends(get_current_user),
    db=Depends(get_db)
):
    ctx.require("households:update")
    return await registry_service.revoke_consent(db, str(consent_id), str(household_id), ctx.tenant_id, ctx.user_id, reason)

@app.post("/households/{household_id}/opt-out", response_model=dict)
async def opt_out(
    household_id: UUID,
    ctx: AuthContext = Depends(get_current_user),
    db=Depends(get_db)
):
    ctx.require("households:update")
    return await registry_service.opt_out(db, str(household_id), ctx.tenant_id)


@app.get("/households/{household_id}/consent", response_model=List[ConsentResponse])
async def get_all_consent(
    household_id: UUID,
    ctx: AuthContext = Depends(get_current_user),
    db=Depends(get_db)
):
    """GAP-06: Bulk fetch all active consent for a household."""
    ctx.require("households:read")
    return await registry_service.get_all_consent(db, str(household_id), ctx.tenant_id)

# ── Cross-Tenant Linking ──────────────────────────────────────

@app.post("/households/{household_id}/links", response_model=dict)
async def propose_link(
    household_id: UUID,
    data: CrossTenantLinkCreate,
    ctx: AuthContext = Depends(get_current_user),
    db=Depends(get_db)
):
    ctx.require("cross_tenant:manage")
    return await registry_service.propose_cross_tenant_link(db, str(household_id), data, ctx.tenant_id, ctx.user_id)

@app.post("/links/{link_id}/approve", response_model=dict)
async def approve_link(
    link_id: UUID,
    ctx: AuthContext = Depends(get_current_user),
    db=Depends(get_db)
):
    ctx.require("cross_tenant:manage")
    return await registry_service.approve_cross_tenant_link(db, str(link_id), ctx.user_id)

# ── Identity Resolution ───────────────────────────────────────

@app.post("/resolve", response_model=ResolutionResult)
async def resolve_identity(
    req: IdentityResolutionRequest,
    ctx: AuthContext = Depends(get_current_user),
    db=Depends(get_db)
):
    ctx.require("households:read")
    return await registry_service.resolve_identity(db, req, ctx.tenant_id)

# ── History ───────────────────────────────────────────────────

@app.get("/households/{household_id}/history", response_model=List[HouseholdHistoryResponse])
async def get_history(
    household_id: UUID,
    limit: int = 50,
    event_type: Optional[str] = None,
    ctx: AuthContext = Depends(get_current_user),
    db=Depends(get_db)
):
    ctx.require("households:read")
    return await registry_service.get_history(db, str(household_id), ctx.tenant_id, limit, event_type)


# ── Global Search ─────────────────────────────────────────────
@app.get("/search/global", response_model=GlobalSearchResponse)
async def global_search(
    q: str = Query(...),
    ctx: AuthContext = Depends(get_current_user),
    db=Depends(get_db)
):
    """
    GAP-02: Unified search across Needs, Households, Volunteers.
    Aggregates ES and DB results.
    """
    ctx.require("households:read")
    return await registry_service.global_search(db, q, ctx.tenant_id)


# ── Wards ─────────────────────────────────────────────────────
@app.get("/wards", response_model=List[WardStat])
async def list_wards(
    ctx: AuthContext = Depends(get_current_user),
    db=Depends(get_db)
):
    """GAP-09: List wards with summary stats."""
    ctx.require("households:read")
    return await registry_service.list_wards(db, ctx.tenant_id)


# ── Settings & Policy ─────────────────────────────────────────
@app.get("/settings/cross-tenant-policies", response_model=List[PartnershipPolicy])
async def get_policies(
    ctx: AuthContext = Depends(require_permission("tenants:update")),
    db=Depends(get_db)
):
    """GAP-10: Get per-partner sharing policies."""
    return await registry_service.get_partnerships(db, ctx.tenant_id)


@app.patch("/settings/cross-tenant-policies/{partner_id}")
async def update_policy(
    partner_id: UUID,
    policy: PartnershipPolicy,
    ctx: AuthContext = Depends(require_permission("tenants:update")),
    db=Depends(get_db)
):
    """GAP-10: Update sharing policy for a specific partner."""
    return await registry_service.update_partnership(db, ctx.tenant_id, str(partner_id), policy)

@app.get("/health")
async def health():
    return {"status": "ok", "service": "nexus-registry"}
