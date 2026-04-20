from fastapi import FastAPI, Depends, HTTPException, status, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
from uuid import UUID

import sys, os
# Adjust path to reach shared/ from current directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from shared.config import get_settings
from shared.database import get_db
from shared.auth import get_current_user, AuthContext, TenantRLSMiddleware
from .schemas import (
    HouseholdCreate, HouseholdUpdate, HouseholdResponse, 
    ConsentCreate, ConsentResponse, 
    CrossTenantLinkCreate, CrossTenantLinkResponse,
    MergeRequest, SearchRequest,
    IdentityResolutionRequest, ResolutionResult,
    HouseholdHistoryResponse
)
from .service import registry_service

settings = get_settings()

app = FastAPI(
    title="NEXUS Household Registry Service",
    version="0.5.0",
    docs_url="/docs" if settings.DEBUG else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(TenantRLSMiddleware)

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

@app.get("/health")
async def health():
    return {"status": "ok", "service": "nexus-registry"}
