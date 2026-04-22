"""
NEXUS Intelligence Service — FastAPI App
Routes:
  POST /score/{need_id}          — recompute urgency for one need
  POST /score/batch              — recompute for all open needs (tenant)
  GET  /priority-queue           — ranked unassigned needs
  GET  /heatmap                  — geo-grid heatmap data
  GET  /ward-stats               — per-ward urgency aggregates
  GET  /gap-report               — resource desert detection
  POST /gap-report/generate      — trigger gap report generation
  GET  /escalations              — needs needing immediate attention
  GET  /weights                  — tenant urgency weight config
  PUT  /weights                  — update tenant urgency weights
  GET  /score-history/{need_id}  — urgency score log for a need
  GET  /search                   — full-text ES search
  GET  /health
"""
import logging
from typing import Optional
from uuid import UUID

from fastapi import FastAPI, Depends, HTTPException, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import text

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from shared.config import get_settings, KafkaTopics
from shared.database import get_db
from shared.auth import get_current_user, AuthContext, TenantRLSMiddleware, require_permission
from shared.kafka import NexusProducer, NexusEvent

from .scoring import (
    calculate_urgency_score, UrgencyWeights, should_escalate
)
from .priority_queue import (
    get_priority_queue, recompute_need_urgency,
    recompute_all_tenant_urgency, refresh_ward_stats,
    generate_gap_report,
)
from .elasticsearch_service import (
    get_heatmap_data, get_ward_urgency,
    detect_resource_deserts, search_needs,
    ensure_indexes,
)

settings = get_settings()
logger   = logging.getLogger(__name__)

app = FastAPI(
    title="NEXUS Intelligence Service",
    version="2.0.0",
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


@app.on_event("startup")
async def startup():
    await NexusProducer.get().start()
    await ensure_indexes(settings.ELASTICSEARCH_URL)


@app.on_event("shutdown")
async def shutdown():
    await NexusProducer.get().stop()


# ── Schemas ───────────────────────────────────────────────────
class WeightUpdateRequest(BaseModel):
    w1_severity:           Optional[float] = Field(None, ge=0, le=1)
    w2_recency:            Optional[float] = Field(None, ge=0, le=1)
    w3_vulnerability:      Optional[float] = Field(None, ge=0, le=1)
    w4_unmet_duration:     Optional[float] = Field(None, ge=0, le=1)
    w5_source_reliability: Optional[float] = Field(None, ge=0, le=1)
    w6_crisis_frequency:   Optional[float] = Field(None, ge=0, le=1)
    w7_coverage_penalty:   Optional[float] = Field(None, ge=0, le=1)
    chronic_threshold:     Optional[float] = Field(None, ge=0)
    chronic_floor:         Optional[float] = Field(None, ge=0, le=1)
    escalation_threshold:  Optional[float] = Field(None, ge=0, le=1)
    escalation_minutes:    Optional[int]   = Field(None, ge=1)
    category_boosts:       Optional[dict]  = None


# ── Urgency scoring ───────────────────────────────────────────
@app.post("/score/{need_id}")
async def score_one_need(
    need_id: UUID,
    ctx: AuthContext = Depends(require_permission("needs:read")),
    db=Depends(get_db),
):
    new_score = await recompute_need_urgency(
        db, str(need_id), ctx.tenant_id, trigger="manual"
    )
    if new_score is None:
        raise HTTPException(status_code=404, detail="Need not found")

    # Emit event
    await NexusProducer.get().emit(
        KafkaTopics.NEED_URGENCY_UPDATED,
        NexusEvent(
            event_type=KafkaTopics.NEED_URGENCY_UPDATED,
            payload={"need_id": str(need_id), "urgency_score": new_score},
            tenant_id=ctx.tenant_id,
            user_id=ctx.user_id,
        ),
        key=str(need_id),
    )
    return {"need_id": str(need_id), "urgency_score": new_score}


@app.post("/score/batch")
async def score_batch(
    background_tasks: BackgroundTasks,
    ctx: AuthContext = Depends(require_permission("needs:read")),
    db=Depends(get_db),
):
    """Recompute urgency for all open needs. Runs in background."""
    count = await recompute_all_tenant_urgency(db, ctx.tenant_id)
    return {"queued": True, "needs_updated": count}


# ── Priority queue ────────────────────────────────────────────
@app.get("/priority-queue")
async def priority_queue(
    limit:                int           = Query(20, le=100),
    offset:               int           = Query(0),
    category:             Optional[str] = Query(None),
    ward_id:              Optional[str] = Query(None),
    vulnerability_filter: Optional[str] = Query(None),
    ctx: AuthContext = Depends(require_permission("needs:read")),
    db=Depends(get_db),
):
    """
    Ranked list of unassigned needs.
    Sorted by urgency_score DESC.
    Includes escalation flag for needs above threshold.
    """
    queue = await get_priority_queue(
        db, ctx.tenant_id,
        limit=limit, offset=offset,
        category=category, ward_id=ward_id,
        vulnerability_filter=vulnerability_filter,
    )
    return {
        "total": len(queue),
        "items": queue,
        "escalations": sum(1 for i in queue if i.get("needs_escalation")),
    }


# ── Escalations ───────────────────────────────────────────────
@app.get("/escalations")
async def get_escalations(
    ctx: AuthContext = Depends(require_permission("needs:read")),
    db=Depends(get_db),
):
    """Needs above escalation threshold that have been unassigned > escalation_minutes."""
    result = await db.execute(
        text("""
            SELECT need_id, category, urgency_score, severity_score,
                   ward_id, ingested_at, beneficiary_count, vulnerability_flags
            FROM need_records
            WHERE tenant_id = :tid
              AND status IN ('unverified','verified')
              AND urgency_score >= 0.90
              AND ingested_at <= NOW() - INTERVAL '2 hours'
            ORDER BY urgency_score DESC
            LIMIT 50
        """),
        {"tid": ctx.tenant_id}
    )
    return [dict(r._mapping) for r in result.fetchall()]


# ── Heatmap ───────────────────────────────────────────────────
@app.get("/heatmap")
async def heatmap(
    category:     Optional[str] = Query(None),
    hours_back:   int           = Query(168),
    geo_precision: int          = Query(7, ge=1, le=12),
    ctx: AuthContext = Depends(require_permission("analytics:read")),
):
    data = await get_heatmap_data(
        tenant_id=ctx.tenant_id,
        category=category,
        hours_back=hours_back,
        geo_precision=geo_precision,
        es_url=settings.ELASTICSEARCH_URL,
    )
    return data


# ── Ward stats ────────────────────────────────────────────────
@app.get("/ward-stats")
async def ward_stats(
    ward_ids: Optional[str] = Query(None, description="Comma-separated ward IDs"),
    ctx: AuthContext = Depends(require_permission("analytics:read")),
    db=Depends(get_db),
):
    """Per-ward urgency stats. Combines DB aggregates + ES geo data."""
    # DB stats
    result = await db.execute(
        text("""
            SELECT *
            FROM ward_stats
            WHERE tenant_id = :tid
            ORDER BY avg_urgency_score DESC
            LIMIT 100
        """),
        {"tid": ctx.tenant_id}
    )
    db_stats = [dict(r._mapping) for r in result.fetchall()]

    # ES live stats
    ward_list = [w.strip() for w in ward_ids.split(",")] if ward_ids else None
    es_stats  = await get_ward_urgency(ctx.tenant_id, ward_list, settings.ELASTICSEARCH_URL)

    return {"db_stats": db_stats, "live_stats": es_stats}


@app.post("/ward-stats/refresh")
async def refresh_wards(
    ctx: AuthContext = Depends(require_permission("analytics:read")),
    db=Depends(get_db),
):
    count = await refresh_ward_stats(db, ctx.tenant_id)
    return {"refreshed": True, "wards_updated": count}


# ── Gap reports ───────────────────────────────────────────────
@app.post("/gap-report/generate")
async def generate_gap(
    ctx: AuthContext = Depends(require_permission("analytics:read")),
    db=Depends(get_db),
):
    report = await generate_gap_report(db, ctx.tenant_id)

    await NexusProducer.get().emit(
        KafkaTopics.GAP_REPORT_GENERATED,
        NexusEvent(
            event_type=KafkaTopics.GAP_REPORT_GENERATED,
            payload={"tenant_id": ctx.tenant_id, "summary": report["summary"]},
            tenant_id=ctx.tenant_id,
        ),
    )
    return report


@app.get("/gap-report")
async def latest_gap_report(
    ctx: AuthContext = Depends(require_permission("analytics:read")),
    db=Depends(get_db),
):
    result = await db.execute(
        text("""
            SELECT report_id, generated_at, desert_wards, top_unmet_needs, summary
            FROM gap_reports
            WHERE tenant_id = :tid
            ORDER BY generated_at DESC
            LIMIT 1
        """),
        {"tid": ctx.tenant_id}
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="No gap report generated yet")
    return dict(row._mapping)


# ── Resource deserts ──────────────────────────────────────────
@app.get("/resource-deserts")
async def resource_deserts(
    urgency_threshold: float = Query(0.70, ge=0, le=1),
    ctx: AuthContext = Depends(require_permission("analytics:read")),
):
    deserts = await detect_resource_deserts(
        ctx.tenant_id, urgency_threshold, settings.ELASTICSEARCH_URL
    )
    return {"deserts": deserts, "count": len(deserts)}


# ── Urgency weight config ─────────────────────────────────────
@app.get("/weights")
async def get_weights(
    ctx: AuthContext = Depends(require_permission("analytics:read")),
    db=Depends(get_db),
):
    result = await db.execute(
        text("SELECT * FROM urgency_weight_configs WHERE tenant_id = :tid"),
        {"tid": ctx.tenant_id}
    )
    row = result.fetchone()
    if not row:
        return UrgencyWeights().__dict__
    return dict(row._mapping)


@app.put("/weights")
async def update_weights(
    body: WeightUpdateRequest,
    ctx: AuthContext = Depends(require_permission("analytics:read")),
    db=Depends(get_db),
):
    ctx.require("ngo_admin")

    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    set_clauses = ", ".join(f"{k} = :{k}" for k in updates)
    updates["tid"] = ctx.tenant_id
    updates["by"]  = ctx.user_id

    await db.execute(
        text(f"""
            UPDATE urgency_weight_configs
            SET {set_clauses}, updated_at = NOW(), updated_by = :by
            WHERE tenant_id = :tid
        """),
        updates
    )
    return {"updated": True}


# ── Score history ─────────────────────────────────────────────
@app.get("/score-history/{need_id}")
async def score_history(
    need_id: UUID,
    limit:   int = Query(20, le=100),
    ctx: AuthContext = Depends(require_permission("needs:read")),
    db=Depends(get_db),
):
    result = await db.execute(
        text("""
            SELECT log_id, score, prev_score, components,
                   t1_severity, t2_recency, t3_vulnerability,
                   t4_unmet_duration, t5_source_reliability,
                   t6_crisis_frequency, t7_coverage_penalty,
                   trigger, computed_at
            FROM urgency_score_log
            WHERE need_id = :nid AND tenant_id = :tid
            ORDER BY computed_at DESC
            LIMIT :limit
        """),
        {"nid": str(need_id), "tid": ctx.tenant_id, "limit": limit}
    )
    return [dict(r._mapping) for r in result.fetchall()]


# ── Full-text search ──────────────────────────────────────────
@app.get("/search")
async def search(
    q:           str           = Query(..., min_length=2),
    category:    Optional[str] = Query(None),
    ward_id:     Optional[str] = Query(None),
    min_urgency: float         = Query(0.0, ge=0, le=1),
    limit:       int           = Query(20, le=100),
    ctx: AuthContext = Depends(require_permission("needs:read")),
):
    results = await search_needs(
        tenant_id   = ctx.tenant_id,
        query_text  = q,
        category    = category,
        ward_id     = ward_id,
        min_urgency = min_urgency,
        limit       = limit,
        es_url      = settings.ELASTICSEARCH_URL,
    )
    return {"results": results, "count": len(results)}


# ── Health ────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"service": "nexus-intelligence", "status": "ok"}