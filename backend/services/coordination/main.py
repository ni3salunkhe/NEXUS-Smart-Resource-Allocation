"""
NEXUS Coordination Service — FastAPI App
Routes:
  Volunteers:
    POST /volunteers               — register volunteer
    GET  /volunteers               — list with filters
    GET  /volunteers/{id}          — profile
    PATCH /volunteers/{id}         — update profile
    POST /volunteers/{id}/location — GPS ping
    GET  /volunteers/{id}/burnout  — burnout score

  Tasks:
    POST /tasks                    — create task from need
    GET  /tasks                    — list by status
    GET  /tasks/{id}               — task detail + state log
    POST /tasks/{id}/dispatch      — match + dispatch volunteer
    POST /tasks/{id}/accept        — volunteer accepts
    POST /tasks/{id}/decline       — volunteer declines
    POST /tasks/{id}/start         — volunteer checks in
    POST /tasks/{id}/complete      — submit outcome
    POST /tasks/{id}/close         — coordinator closes
    GET  /tasks/{id}/matches       — top match candidates

  Notifications:
    POST /webhooks/sms             — inbound SMS/WhatsApp reply
    POST /notifications/send       — manual notification

  Misc:
    POST /dispatch-timeouts/check  — check + handle stale dispatches
    GET  /health
"""
import logging
from typing import Optional, List
from uuid import UUID
from datetime import datetime

from fastapi import FastAPI, Depends, HTTPException, Query, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from asyncpg import UniqueViolationError

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from shared.config import get_settings, KafkaTopics
from shared.database import get_db
from shared.auth import get_current_user, AuthContext, TenantRLSMiddleware, require_permission
from shared.kafka import NexusProducer, NexusEvent
from shared.logging_config import setup_logging, add_global_error_handler

setup_logging("coordination")

from .task_service import task_service, VALID_TRANSITIONS
from .burnout import compute_volunteer_burnout, apply_rest_day_decay, EXCLUDED_THRESHOLD
from .matching.matcher import find_matches
from .notifications.service import (
    dispatch_notification, parse_sms_response,
    handle_whatsapp_webhook, BRIEFING_TEMPLATES,
)

settings = get_settings()
logger   = logging.getLogger(__name__)

app = FastAPI(
    title="NEXUS Coordination Service",
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
async def startup():
    await NexusProducer.get().start()


@app.on_event("shutdown")
async def shutdown():
    await NexusProducer.get().stop()


# ── Schemas ───────────────────────────────────────────────────
class VolunteerCreate(BaseModel):
    preferred_language:    List[str]        = []
    skills:                List[str]        = []
    skill_proficiency:     dict             = {}
    cultural_context_tags: List[str]        = []
    max_distance_km:       int              = 10
    availability_schedule: dict             = {}
    ward_id:               Optional[str]   = None
    whatsapp_number:       Optional[str]   = None
    phone_number:          Optional[str]   = None
    preferred_channel:     str             = "push"
    latitude:              Optional[float] = None
    longitude:             Optional[float] = None
    tenant_id:             Optional[UUID]  = None # Only used by platform_admin
    skill_verification:    dict             = {}


class VolunteerUpdate(BaseModel):
    preferred_language:    Optional[List[str]] = None
    skills:                Optional[List[str]] = None
    skill_proficiency:     Optional[dict]      = None
    cultural_context_tags: Optional[List[str]] = None
    max_distance_km:       Optional[int]       = None
    availability_schedule: Optional[dict]      = None
    whatsapp_number:       Optional[str]       = None
    phone_number:          Optional[str]       = None
    preferred_channel:     Optional[str]       = None
    active:                Optional[bool]      = None


class LocationPing(BaseModel):
    latitude:    float
    longitude:   float
    accuracy_m:  Optional[float] = None
    battery_pct: Optional[int]   = None


class TaskCreateRequest(BaseModel):
    need_id:        str
    household_id:   Optional[str] = None


class DispatchRequest(BaseModel):
    volunteer_id:   str
    auto_dispatch:  bool            = False
    briefing_language: str          = "en"


class CompleteRequest(BaseModel):
    outcome_status:     str
    outcome_notes:      str         = ""
    materials_provided: dict        = {}
    follow_up_required: bool        = False


class CloseRequest(BaseModel):
    volunteer_rating: Optional[float] = Field(None, ge=1, le=5)


class DeclineRequest(BaseModel):
    reason: str = ""


class SMSWebhook(BaseModel):
    From:  str
    Body:  str
    # Twilio sends these field names


# ── GAP Endpoints Schemas ─────────────────────────────────────
class OverrideRecordRequest(BaseModel):
    task_id:          UUID
    suggested_vol_id: Optional[UUID] = None
    suggested_score:  Optional[float] = None
    chosen_vol_id:    UUID
    override_reason:  str


class AvailabilityResponse(BaseModel):
    volunteer_id:      UUID
    is_available_now:  bool
    burnout_risk_score: float
    active_tasks:      int
    schedule:          dict


class NotificationPreferencesUpdate(BaseModel):
    preferred_channel: str
    whatsapp_number:   Optional[str] = None
    phone_number:      Optional[str] = None
    push_token:        Optional[str] = None


class BriefingPreviewRequest(BaseModel):
    language: str = "en"
    variables: dict = {}


# ── VOLUNTEERS ────────────────────────────────────────────────
@app.post("/volunteers", status_code=201)
async def create_volunteer(
    body: VolunteerCreate,
    ctx: AuthContext = Depends(require_permission("volunteers:create")),
    db=Depends(get_db),
):
    # Determine effective tenant_id
    effective_tid = ctx.tenant_id
    if ctx.role == 'platform_admin' and body.tenant_id:
        effective_tid = str(body.tenant_id)
        
    if not effective_tid:
        raise HTTPException(
            status_code=400, 
            detail="Organization context missing. System Administrators must specify a 'tenant_id' to register volunteers."
        )

    import json
    loc_clause = ""
    params: dict = {
        "tid":      effective_tid,
        "uid":      ctx.user_id,
        "langs":    body.preferred_language,
        "skills":   body.skills,
        "prof":     json.dumps(body.skill_proficiency),
        "verif":    json.dumps(body.skill_verification),
        "tags":     body.cultural_context_tags,
        "dist":     body.max_distance_km,
        "avail":    json.dumps(body.availability_schedule),
        "ward":     body.ward_id,
        "wa_num":   body.whatsapp_number,
        "ph_num":   body.phone_number,
        "channel":  body.preferred_channel,
    }

    try:
        result = await db.execute(
            text(f"""
                INSERT INTO volunteers (
                    tenant_id, user_id, preferred_language, skills, skill_proficiency,
                    skill_verification,
                    cultural_context_tags, max_distance_km, availability_schedule,
                    ward_id, whatsapp_number, phone_number, preferred_channel
                )
                VALUES (
                    :tid, :uid, CAST(:langs AS text[]), CAST(:skills AS text[]), CAST(:prof AS JSONB),
                    CAST(:verif AS JSONB),
                    CAST(:tags AS text[]), :dist, CAST(:avail AS JSONB),
                    :ward, :wa_num, :ph_num, :channel
                )
                RETURNING volunteer_id, created_at
            """),
            params
        )
        row = result.fetchone()
        vid = str(row.volunteer_id)
        
        if body.latitude and body.longitude:
            loc_wkt = f"POINT({body.longitude} {body.latitude})"
            await db.execute(
                text("UPDATE volunteers SET location_home_point = ST_GeographyFromText(:loc_wkt) WHERE volunteer_id=:vid"),
                {"loc_wkt": loc_wkt, "vid": vid}
            )
            
        await db.commit()
        return {"volunteer_id": vid, "created_at": row.created_at.isoformat()}
        
    except IntegrityError as e:
        await db.rollback()
        if "unique constraint \"volunteers_user_id_key\"" in str(e).lower():
            raise HTTPException(
                status_code=400,
                detail="Volunteer profile already exists for this user account."
            )
        raise e
    except Exception as e:
        await db.rollback()
        raise e


@app.get("/volunteers")
async def list_volunteers(
    active:    Optional[bool] = Query(None),
    verified:  Optional[bool] = Query(None),
    ward_id:   Optional[str]  = Query(None),
    skill:     Optional[str]  = Query(None),
    limit:     int             = Query(20, le=100),
    offset:    int             = Query(0),
    ctx: AuthContext = Depends(require_permission("volunteers:read")),
    db=Depends(get_db),
):
    conditions = []
    params: dict = {"limit": limit, "offset": offset}

    if ctx.role != 'platform_admin':
        conditions.append("tenant_id = :tid")
        params["tid"] = ctx.tenant_id
    else:
        # Platform admin can filter by tenant_id if provided (could add query param later)
        pass

    if not conditions:
        conditions.append("1=1")

    if active  is not None:
        conditions.append("active = :active"); params["active"] = active
    if verified is not None:
        conditions.append("verified = :verified"); params["verified"] = verified
    if ward_id:
        conditions.append("ward_id = :ward"); params["ward"] = ward_id
    if skill:
        conditions.append(":skill = ANY(skills)"); params["skill"] = skill

    where = " AND ".join(conditions)
    result = await db.execute(
        text(f"""
            SELECT volunteer_id, tenant_id, user_id, preferred_language, skills,
                   cultural_context_tags, max_distance_km, ward_id, active, verified,
                   burnout_risk_score, total_deployments, outcome_rating, response_rate,
                   is_available_now, last_deployed_at, last_active_at,
                   preferred_channel, created_at
            FROM volunteers WHERE {where}
            ORDER BY burnout_risk_score ASC, outcome_rating DESC
            LIMIT :limit OFFSET :offset
        """),
        params
    )
    return [dict(r._mapping) for r in result.fetchall()]


@app.get("/volunteers/{volunteer_id}")
async def get_volunteer(
    volunteer_id: UUID,
    ctx: AuthContext = Depends(require_permission("volunteers:read")),
    db=Depends(get_db),
):
    query = "SELECT * FROM volunteers WHERE volunteer_id=:vid"
    params = {"vid": str(volunteer_id)}
    
    if ctx.role != 'platform_admin':
        query += " AND tenant_id=:tid"
        params["tid"] = ctx.tenant_id

    result = await db.execute(text(query), params)
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Volunteer not found")
    return dict(row._mapping)


@app.patch("/volunteers/{volunteer_id}")
async def update_volunteer(
    volunteer_id: UUID,
    body: VolunteerUpdate,
    ctx: AuthContext = Depends(require_permission("volunteers:update")),
    db=Depends(get_db),
):
    import json
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    set_parts, params = [], {"vid": str(volunteer_id), "tid": ctx.tenant_id}
    for k, v in updates.items():
        if k == "preferred_language":
            set_parts.append("preferred_language = :langs::text[]")
            params["langs"] = "{" + ",".join(v) + "}"
        elif k == "skills":
            set_parts.append("skills = :skills::text[]")
            params["skills"] = "{" + ",".join(v) + "}"
        elif k == "cultural_context_tags":
            set_parts.append("cultural_context_tags = :tags::text[]")
            params["tags"] = "{" + ",".join(v) + "}"
        elif k in ("skill_proficiency", "availability_schedule"):
            set_parts.append(f"{k} = CAST(:{k} AS JSONB)")
            params[k] = json.dumps(v)
        else:
            set_parts.append(f"{k} = :{k}")
            params[k] = v

    await db.execute(
        text(f"UPDATE volunteers SET {', '.join(set_parts)}, updated_at=NOW() WHERE volunteer_id=:vid AND tenant_id=:tid"),
        params
    )
    return {"updated": True}


@app.post("/volunteers/{volunteer_id}/location")
async def record_location(
    volunteer_id: UUID,
    body: LocationPing,
    ctx: AuthContext = Depends(require_permission("volunteers:update")),
    db=Depends(get_db),
):
    """GPS ping from mobile app. Every 5 minutes when volunteer is active."""
    await db.execute(
        text("""
            INSERT INTO volunteer_locations
                (volunteer_id, tenant_id, location_point, accuracy_m, battery_pct)
            VALUES (
                :vid, :tid,
                ST_GeographyFromText(:wkt),
                :acc, :bat
            )
        """),
        {
            "vid": str(volunteer_id),
            "tid": ctx.tenant_id,
            "wkt": f"POINT({body.longitude} {body.latitude})",
            "acc": body.accuracy_m,
            "bat": body.battery_pct,
        }
    )
    await db.commit()  # H5: persist location immediately

    try:
        await NexusProducer.get().emit(
            KafkaTopics.VOLUNTEER_LOCATION_UPDATED,
            NexusEvent(
                event_type=KafkaTopics.VOLUNTEER_LOCATION_UPDATED,
                payload={
                    "volunteer_id": str(volunteer_id),
                    "lat": body.latitude, "lon": body.longitude,
                },
                tenant_id=ctx.tenant_id,
            ),
            key=str(volunteer_id),
        )
    except Exception as _ke:
        logger.warning(f"Kafka emit skipped (degraded mode): {_ke}")
    return {"recorded": True}


@app.get("/volunteers/{volunteer_id}/burnout")
async def get_burnout(
    volunteer_id: UUID,
    ctx: AuthContext = Depends(require_permission("volunteers:read")),
    db=Depends(get_db),
):
    result = await compute_volunteer_burnout(db, str(volunteer_id), ctx.tenant_id)
    return {
        "volunteer_id":      str(volunteer_id),
        "burnout_risk_score":result.score,
        "label":             result.label,
        "deployments_7d":    result.deployments_7d,
        "deployments_30d":   result.deployments_30d,
        "consecutive_days":  result.consecutive_days,
        "avg_outcome_rating":result.avg_outcome_rating,
        "is_excluded":       result.is_excluded,
        "is_warning":        result.is_warning,
    }


# ── TASKS ─────────────────────────────────────────────────────
@app.post("/tasks", status_code=201)
async def create_task(
    body: TaskCreateRequest,
    ctx: AuthContext = Depends(require_permission("tasks:create")),
    db=Depends(get_db),
):
    result = await task_service.create_task(
        db, body.need_id, body.household_id, ctx.tenant_id, ctx.user_id
    )
    try:
        await NexusProducer.get().emit(
            KafkaTopics.TASK_CREATED,
            NexusEvent(event_type=KafkaTopics.TASK_CREATED,
                       payload=result, tenant_id=ctx.tenant_id, user_id=ctx.user_id),
            key=result["task_id"],
        )
    except Exception as _ke:
        logger.warning(f"Kafka emit skipped (degraded mode): {_ke}")
    return result


@app.get("/tasks")
async def list_tasks(
    status:     Optional[str] = Query(None),
    limit:      int            = Query(20, le=100),
    offset:     int            = Query(0),
    ctx: AuthContext = Depends(require_permission("tasks:read")),
    db=Depends(get_db),
):
    cond   = ["tenant_id=:tid"]
    params = {"tid": ctx.tenant_id, "limit": limit, "offset": offset}
    if status:
        cond.append("status=:status"); params["status"] = status

    result = await db.execute(
        text(f"""
            SELECT task_id, need_id, household_id, assigned_volunteer_id,
                   status, dispatched_at, accepted_at, completed_at, closed_at,
                   outcome_status, volunteer_rating, follow_up_required,
                   match_score, cancellation_attempts, created_at
            FROM tasks WHERE {' AND '.join(cond)}
            ORDER BY created_at DESC LIMIT :limit OFFSET :offset
        """),
        params
    )
    return [dict(r._mapping) for r in result.fetchall()]


@app.get("/tasks/{task_id}")
async def get_task(
    task_id: UUID,
    ctx: AuthContext = Depends(require_permission("tasks:read")),
    db=Depends(get_db),
):
    task = await task_service.get_task(db, str(task_id), ctx.tenant_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    task["state_log"] = await task_service.get_state_log(db, str(task_id), ctx.tenant_id)
    return task


@app.get("/tasks/{task_id}/matches")
async def get_matches(
    task_id:   UUID,
    radius_km: int = Query(15, ge=1, le=100),
    ctx: AuthContext = Depends(require_permission("tasks:read")),
    db=Depends(get_db),
):
    """Return top volunteer matches for a task (coordinator sees before approving)."""
    task = await task_service.get_task(db, str(task_id), ctx.tenant_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Fetch need details for matching inputs
    need_row = await db.execute(
        text("""
            SELECT category, vulnerability_flags, ward_id,
                   ST_Y(location_point::geometry) AS lat,
                   ST_X(location_point::geometry) AS lon
            FROM need_records WHERE need_id=:nid AND tenant_id=:tid
        """),
        {"nid": str(task["need_id"]), "tid": ctx.tenant_id}
    )
    need = need_row.fetchone()
    if not need:
        raise HTTPException(status_code=404, detail="Need record not found")

    vf   = need.vulnerability_flags or {}
    langs = [lang for flag, lang in [("has_child","hi"),("has_elderly","mr")] if vf.get(flag)]

    candidates = await find_matches(
        db            = db,
        need_id       = str(task["need_id"]),
        tenant_id     = ctx.tenant_id,
        household_id  = str(task.get("household_id", "")) if task.get("household_id") else None,
        category      = need.category,
        need_latitude = need.lat,
        need_longitude= need.lon,
        preferred_languages = langs or ["en"],
        cultural_tags = [],
        radius_km     = radius_km,
    )
    return {"task_id": str(task_id), "candidates": [c.to_dict() for c in candidates]}


@app.post("/tasks/{task_id}/dispatch")
async def dispatch_task(
    task_id:          UUID,
    body:             DispatchRequest,
    background_tasks: BackgroundTasks,
    ctx: AuthContext = Depends(require_permission("tasks:update")),
    db=Depends(get_db),
):
    task = await task_service.get_task(db, str(task_id), ctx.tenant_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Fetch volunteer details for notification
    vol_row = await db.execute(
        text("SELECT * FROM volunteers WHERE volunteer_id=:vid AND tenant_id=:tid"),
        {"vid": body.volunteer_id, "tid": ctx.tenant_id}
    )
    vol = vol_row.fetchone()
    if not vol:
        raise HTTPException(status_code=404, detail="Volunteer not found")

    if vol.burnout_risk_score >= EXCLUDED_THRESHOLD:
        raise HTTPException(status_code=409,
                            detail=f"Volunteer burnout score {vol.burnout_risk_score:.2f} >= {EXCLUDED_THRESHOLD}. Cannot dispatch.")

    # Compute final match score
    need_row = await db.execute(
        text("SELECT category FROM need_records WHERE need_id=:nid"),
        {"nid": str(task["need_id"])}
    )
    need = need_row.fetchone()

    candidates = await find_matches(
        db=db, need_id=str(task["need_id"]), tenant_id=ctx.tenant_id,
        household_id=str(task.get("household_id")) if task.get("household_id") else None,
        category=need.category if need else None,
        need_latitude=None, need_longitude=None,
        preferred_languages=["en"], cultural_tags=[],
    )
    score = next((c.match_score for c in candidates if c.volunteer_id == body.volunteer_id), 0.5)
    comps = next((c.to_dict() for c in candidates if c.volunteer_id == body.volunteer_id), {})

    # Generate briefing
    need_desc_row = await db.execute(
        text("SELECT category, description, beneficiary_count, ward_id FROM need_records WHERE need_id=:nid"),
        {"nid": str(task["need_id"])}
    )
    nd = need_desc_row.fetchone()
    brief_vars = {
        "category":        nd.category if nd else "general",
        "location":        nd.ward_id  if nd else "location TBD",
        "beneficiary_count": nd.beneficiary_count if nd else 1,
        "description":     (nd.description or "")[:200] if nd else "",
    }
    from .notifications.service import _build_message
    briefing = _build_message("dispatch", body.briefing_language, brief_vars)

    result = await task_service.dispatch(
        db, str(task_id), body.volunteer_id, ctx.tenant_id,
        score, comps, ctx.user_id, briefing, body.briefing_language,
    )

    # Send notification in background
    vol_dict = dict(vol._mapping)
    background_tasks.add_task(
        dispatch_notification,
        db=db, task_id=str(task_id), volunteer_id=body.volunteer_id,
        tenant_id=ctx.tenant_id, template_key="dispatch",
        language=body.briefing_language, variables=brief_vars,
        push_token=vol_dict.get("push_token"),
        whatsapp_number=vol_dict.get("whatsapp_number"),
        phone_number=vol_dict.get("phone_number"),
        preferred_channel=vol_dict.get("preferred_channel", "push"),
    )

    try:
        await NexusProducer.get().emit(
            KafkaTopics.TASK_DISPATCHED,
            NexusEvent(event_type=KafkaTopics.TASK_DISPATCHED,
                       payload={**result, "match_score": score},
                       tenant_id=ctx.tenant_id, user_id=ctx.user_id),
            key=str(task_id),
        )
    except Exception as _ke:
        logger.warning(f"Kafka emit skipped (degraded mode): {_ke}")
    return result


@app.post("/tasks/{task_id}/accept")
async def accept_task(
    task_id: UUID,
    volunteer_id: str = Query(...),
    ctx: AuthContext = Depends(require_permission("tasks:update")),
    db=Depends(get_db),
):
    result = await task_service.accept(db, str(task_id), volunteer_id, ctx.tenant_id)
    try:
        await NexusProducer.get().emit(
            KafkaTopics.TASK_ACCEPTED,
            NexusEvent(event_type=KafkaTopics.TASK_ACCEPTED, payload=result,
                       tenant_id=ctx.tenant_id, user_id=volunteer_id),
            key=str(task_id),
        )
    except Exception as _ke:
        logger.warning(f"Kafka emit skipped (degraded mode): {_ke}")
    return result


@app.post("/tasks/{task_id}/decline")
async def decline_task(
    task_id: UUID,
    volunteer_id: str = Query(...),
    body: DeclineRequest = DeclineRequest(),
    ctx: AuthContext = Depends(require_permission("tasks:update")),
    db=Depends(get_db),
):
    return await task_service.decline(db, str(task_id), volunteer_id, ctx.tenant_id, body.reason)


@app.post("/tasks/{task_id}/start")
async def start_task(
    task_id: UUID,
    volunteer_id: str = Query(...),
    ctx: AuthContext = Depends(require_permission("tasks:update")),
    db=Depends(get_db),
):
    result = await task_service.start(db, str(task_id), volunteer_id, ctx.tenant_id)
    try:
        await NexusProducer.get().emit(
            KafkaTopics.TASK_STARTED,
            NexusEvent(event_type=KafkaTopics.TASK_STARTED, payload=result,
                       tenant_id=ctx.tenant_id, user_id=volunteer_id),
            key=str(task_id),
        )
    except Exception as _ke:
        logger.warning(f"Kafka emit skipped (degraded mode): {_ke}")
    return result


@app.post("/tasks/{task_id}/complete")
async def complete_task(
    task_id: UUID,
    volunteer_id: str = Query(...),
    body: CompleteRequest = ...,
    ctx: AuthContext = Depends(require_permission("tasks:update")),
    db=Depends(get_db),
):
    result = await task_service.complete(
        db, str(task_id), volunteer_id, ctx.tenant_id,
        body.outcome_status, body.outcome_notes,
        body.materials_provided, body.follow_up_required,
    )
    try:
        await NexusProducer.get().emit(
            KafkaTopics.TASK_COMPLETED,
            NexusEvent(event_type=KafkaTopics.TASK_COMPLETED, payload=result,
                       tenant_id=ctx.tenant_id, user_id=volunteer_id),
            key=str(task_id),
        )
    except Exception as _ke:
        logger.warning(f"Kafka emit skipped (degraded mode): {_ke}")
    return result


@app.post("/tasks/{task_id}/close")
async def close_task(
    task_id: UUID,
    body: CloseRequest,
    ctx: AuthContext = Depends(require_permission("tasks:update")),
    db=Depends(get_db),
):
    return await task_service.close(
        db, str(task_id), ctx.user_id, ctx.tenant_id, body.volunteer_rating
    )


# ── Webhooks ──────────────────────────────────────────────────
@app.post("/webhooks/sms")
async def sms_webhook(
    body: SMSWebhook,
    ctx: AuthContext = Depends(require_permission("tasks:update")),
    db=Depends(get_db),
):
    """Twilio inbound webhook: process volunteer reply."""
    result = await handle_whatsapp_webhook(
        db, body.From, body.Body, ctx.tenant_id
    )
    if result.get("action") == "accept":
        await task_service.accept(db, result["task_id"], result["volunteer_id"], ctx.tenant_id)
    elif result.get("action") == "decline":
        await task_service.decline(
            db, result["task_id"], result["volunteer_id"],
            ctx.tenant_id, result.get("reason", ""),
        )
    return result


# ── GAP-01: Override Recording ────────────────────────────────
@app.post("/coordination/overrides/record", status_code=201)
async def record_coordinator_override(
    body: OverrideRecordRequest,
    ctx: AuthContext = Depends(require_permission("tasks:update")),
    db=Depends(get_db),
):
    """
    GAP-01: Record a coordinator override decision.
    Atomic with task assignment if done via UI.
    """
    from .matching.override_learning import record_override

    # Verify task exists
    task = await task_service.get_task(db, str(body.task_id), ctx.tenant_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Fetch need details for context
    need_row = await db.execute(
        text("SELECT category, ward_id, urgency_score FROM need_records WHERE need_id=:nid"),
        {"nid": str(task["need_id"])}
    )
    need = need_row.fetchone()

    override_id = await record_override(
        db               = db,
        task_id          = str(body.task_id),
        tenant_id        = ctx.tenant_id,
        suggested_vol_id = str(body.suggested_vol_id) if body.suggested_vol_id else None,
        suggested_score  = body.suggested_score,
        chosen_vol_id    = str(body.chosen_vol_id),
        coordinator_id   = ctx.user_id,
        override_reason  = body.override_reason,
        need_category    = need.category if need else None,
        need_ward_id     = need.ward_id if need else None,
        need_urgency     = need.urgency_score if need else None,
    )

    await db.commit()
    return {"override_id": override_id, "status": "recorded"}


# ── GAP-03: Volunteer Availability ────────────────────────────
@app.get("/volunteers/{volunteer_id}/availability", response_model=AvailabilityResponse)
async def get_volunteer_availability(
    volunteer_id: UUID,
    ctx: AuthContext = Depends(require_permission("volunteers:read")),
    db=Depends(get_db),
):
    """GAP-03: Compute real-time availability and burnout risk."""
    vol_row = await db.execute(
        text("SELECT * FROM volunteers WHERE volunteer_id=:vid AND tenant_id=:tid"),
        {"vid": str(volunteer_id), "tid": ctx.tenant_id}
    )
    vol = vol_row.fetchone()
    if not vol:
        raise HTTPException(status_code=404, detail="Volunteer not found")

    # Count active tasks
    task_count_row = await db.execute(
        text("SELECT COUNT(*) FROM tasks WHERE assigned_volunteer_id=:vid AND status IN ('dispatched', 'accepted', 'in_progress')"),
        {"vid": str(volunteer_id)}
    )
    active_tasks = task_count_row.scalar()

    # Burnout score
    burnout = await compute_volunteer_burnout(db, str(volunteer_id), ctx.tenant_id)

    return AvailabilityResponse(
        volunteer_id       = volunteer_id,
        is_available_now   = vol.is_available_now and active_tasks == 0,
        burnout_risk_score = burnout.score,
        active_tasks       = active_tasks,
        schedule           = vol.availability_schedule or {},
    )


# ── GAP-05: Notification Preferences ──────────────────────────
@app.get("/volunteers/{volunteer_id}/notifications")
async def get_notification_prefs(
    volunteer_id: UUID,
    ctx: AuthContext = Depends(require_permission("volunteers:read")),
    db=Depends(get_db),
):
    """GAP-05: Fetch only notification configuration."""
    result = await db.execute(
        text("""
            SELECT preferred_channel, whatsapp_number, phone_number, push_token
            FROM volunteers WHERE volunteer_id=:vid AND tenant_id=:tid
        """),
        {"vid": str(volunteer_id), "tid": ctx.tenant_id}
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Volunteer not found")
    return dict(row._mapping)


@app.post("/volunteers/{volunteer_id}/notifications/test")
async def test_notification(
    volunteer_id: UUID,
    ctx: AuthContext = Depends(require_permission("volunteers:update")),
    db=Depends(get_db),
):
    """GAP-05: Trigger a test notification."""
    vol_row = await db.execute(
        text("SELECT * FROM volunteers WHERE volunteer_id=:vid AND tenant_id=:tid"),
        {"vid": str(volunteer_id), "tid": ctx.tenant_id}
    )
    vol = vol_row.fetchone()
    if not vol:
        raise HTTPException(status_code=404, detail="Volunteer not found")

    res = await dispatch_notification(
        db              = db,
        task_id         = "test_id",
        volunteer_id    = str(volunteer_id),
        tenant_id       = ctx.tenant_id,
        template_key    = "reminder",
        language        = vol.preferred_language[0] if vol.preferred_language else "en",
        variables       = {"location": "Test Location"},
        push_token      = vol.push_token,
        whatsapp_number = vol.whatsapp_number,
        phone_number    = vol.phone_number,
        preferred_channel = vol.preferred_channel,
    )
    return {"sent": res.sent, "channel": res.channel, "error": res.error}


# ── GAP-07: Task Briefing Preview ─────────────────────────────
@app.post("/tasks/{task_id}/briefing/preview")
async def preview_briefing(
    task_id: UUID,
    body: BriefingPreviewRequest,
    ctx: AuthContext = Depends(require_permission("tasks:read")),
    db=Depends(get_db),
):
    """GAP-07: Preview rendered briefing message without sending."""
    from .notifications.service import _build_message

    # Reuse variables from task/need if not provided
    if not body.variables:
        task = await task_service.get_task(db, str(task_id), ctx.tenant_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        need_row = await db.execute(
            text("SELECT category, ward_id, beneficiary_count, description FROM need_records WHERE need_id=:nid"),
            {"nid": str(task["need_id"])}
        )
        nd = need_row.fetchone()
        if nd:
            body.variables = {
                "category":        nd.category,
                "location":        nd.ward_id,
                "beneficiary_count": nd.beneficiary_count,
                "description":     (nd.description or "")[:200],
            }

    message = _build_message("dispatch", body.language, body.variables)
    return {
        "message":   message,
        "variables": body.variables,
        "language":  body.language
    }


# ── Maintenance ───────────────────────────────────────────────
@app.post("/dispatch-timeouts/check")
async def check_timeouts(
    ctx: AuthContext = Depends(require_permission("tasks:update")),
    db=Depends(get_db),
):
    timed_out = await task_service.check_dispatch_timeouts(db, ctx.tenant_id)
    return {"timed_out": timed_out, "count": len(timed_out)}


# ── Health ────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"service": "nexus-coordination", "status": "ok"}