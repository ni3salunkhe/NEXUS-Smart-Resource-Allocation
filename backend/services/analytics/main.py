"""
NEXUS Analytics Service — FastAPI App
Routes:
  GET  /metrics/impact           — period impact metrics
  POST /metrics/compute          — trigger metric computation
  GET  /households/improvement   — HII dashboard (worst first)
  GET  /volunteers/performance   — volunteer performance table
  GET  /overrides/summary        — coordinator override analytics
  GET  /overrides/patterns       — where algorithm underperforms
  GET  /duplication-rate         — cross-NGO duplication stats
  POST /feedback/process/{task_id} — trigger feedback loop manually
  GET  /funder-report            — anonymized funder-facing metrics
  GET  /health
"""
import logging
from datetime import date, timedelta
from typing import Optional
from uuid import UUID

from fastapi import FastAPI, Depends, HTTPException, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import text

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from shared.config import get_settings, KafkaTopics
from shared.database import get_db
from shared.auth import get_current_user, AuthContext, TenantRLSMiddleware, require_permission
from shared.kafka import NexusProducer, NexusEvent
from shared.logging_config import setup_logging, add_global_error_handler

setup_logging("analytics")

from .impact_metrics import (
    compute_period_metrics, get_household_improvement_dashboard,
    get_volunteer_performance_summary, get_cross_ngo_duplication_rate,
)
from .feedback_loop import process_task_completion
import httpx

settings = get_settings()
logger   = logging.getLogger(__name__)

app = FastAPI(
    title="NEXUS Analytics Service",
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


# ── Impact Metrics ────────────────────────────────────────────
@app.post("/metrics/compute")
async def compute_metrics(
    period_start: date = Query(None),
    period_end:   date = Query(None),
    period_type:  str  = Query("monthly"),
    ctx: AuthContext = Depends(require_permission("analytics:read")),
    db=Depends(get_db),
):
    if not period_start:
        period_end   = date.today()
        period_start = period_end - timedelta(days=30)

    metrics = await compute_period_metrics(
        db, ctx.tenant_id, period_start, period_end, period_type
    )
    return metrics


@app.get("/metrics/impact")
async def get_impact_metrics(
    period_type: str = Query("monthly"),
    limit:       int = Query(12, le=36),
    ctx: AuthContext = Depends(require_permission("analytics:read")),
    db=Depends(get_db),
):
    result = await db.execute(
        text("""
            SELECT * FROM impact_metrics
            WHERE tenant_id = :tid AND period_type = :ptype
            ORDER BY period_start DESC
            LIMIT :limit
        """),
        {"tid": ctx.tenant_id, "ptype": period_type, "limit": limit}
    )
    return [dict(r._mapping) for r in result.fetchall()]


# ── Household Improvement Index ───────────────────────────────
@app.get("/households/improvement")
async def household_improvement(
    window_days:  int           = Query(30, ge=1),
    trend_filter: Optional[str] = Query(None),
    limit:        int           = Query(50, le=200),
    ctx: AuthContext = Depends(require_permission("analytics:read")),
    db=Depends(get_db),
):
    """
    Household improvement dashboard.
    Sorted by improvement_index ASC — worst-performing households first.
    Use this to identify families where assistance is not working.
    """
    data = await get_household_improvement_dashboard(
        db, ctx.tenant_id, window_days, limit, trend_filter
    )
    return {
        "window_days": window_days,
        "count":       len(data),
        "items":       data,
    }


@app.get("/households/{household_id}/improvement")
async def single_household_improvement(
    household_id: UUID,
    ctx: AuthContext = Depends(require_permission("analytics:read")),
    db=Depends(get_db),
):
    result = await db.execute(
        text("""
            SELECT * FROM household_improvement_index
            WHERE household_id = :hid AND tenant_id = :tid
            ORDER BY window_days ASC, computed_at DESC
        """),
        {"hid": str(household_id), "tid": ctx.tenant_id}
    )
    rows = result.fetchall()
    if not rows:
        raise HTTPException(status_code=404, detail="No HII data for this household")

    # Latest per window
    by_window: dict[int, dict] = {}
    for row in rows:
        d = dict(row._mapping)
        w = d["window_days"]
        if w not in by_window:
            by_window[w] = d

    return {
        "household_id": str(household_id),
        "windows":      by_window,
        "summary":      {
            "trend_30d":  by_window.get(30,  {}).get("trend"),
            "trend_90d":  by_window.get(90,  {}).get("trend"),
            "trend_365d": by_window.get(365, {}).get("trend"),
            "hii_30d":    by_window.get(30,  {}).get("improvement_index"),
        }
    }


# ── Volunteer Performance ─────────────────────────────────────
@app.get("/volunteers/performance")
async def volunteer_performance(
    limit: int = Query(20, le=100),
    ctx: AuthContext = Depends(require_permission("analytics:read")),
    db=Depends(get_db),
):
    data = await get_volunteer_performance_summary(db, ctx.tenant_id, limit)
    return {"count": len(data), "volunteers": data}


@app.get("/volunteers/{volunteer_id}/performance")
async def single_volunteer_performance(
    volunteer_id: UUID,
    ctx: AuthContext = Depends(require_permission("analytics:read")),
    db=Depends(get_db),
):
    result = await db.execute(
        text("""
            SELECT
                t.outcome_status, COUNT(*) AS cnt, AVG(t.volunteer_rating) AS avg_rating
            FROM tasks t
            WHERE t.assigned_volunteer_id = :vid
              AND t.tenant_id             = :tid
              AND t.status                = 'closed'
            GROUP BY t.outcome_status
        """),
        {"vid": str(volunteer_id), "tid": ctx.tenant_id}
    )
    breakdown = {r.outcome_status: {"count": r.cnt, "avg_rating": float(r.avg_rating or 0)}
                 for r in result.fetchall() if r.outcome_status}

    snapshots = await db.execute(
        text("""
            SELECT * FROM volunteer_performance_snapshots
            WHERE volunteer_id = :vid AND tenant_id = :tid
            ORDER BY snapshot_date DESC LIMIT 12
        """),
        {"vid": str(volunteer_id), "tid": ctx.tenant_id}
    )
    return {
        "volunteer_id": str(volunteer_id),
        "outcome_breakdown": breakdown,
        "snapshots": [dict(r._mapping) for r in snapshots.fetchall()],
    }


# ── Override Analytics ────────────────────────────────────────
@app.get("/overrides/summary")
async def override_summary(
    days_back: int = Query(30, ge=7),
    ctx: AuthContext = Depends(require_permission("analytics:read")),
    db=Depends(get_db),
):
    """How often do coordinators override the algorithm, and does it help?"""
    import httpx
    coord_url = settings.COORDINATION_URL if hasattr(settings, "COORDINATION_URL") else "http://localhost:8003"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{coord_url}/coordination/overrides/summary",
                headers={"X-Tenant-ID": ctx.tenant_id},
                params={"days_back": days_back}
            )
            if resp.status_code == 200:
                return resp.json()
    except Exception as e:
        logger.warning(f"Coordination summary call failed (degraded mode): {e}")
    return {}


@app.get("/overrides/patterns")
async def override_patterns(
    days_back: int = Query(90, ge=30),
    ctx: AuthContext = Depends(require_permission("analytics:read")),
    db=Depends(get_db),
):
    """
    Where does the algorithm consistently underperform?
    Returns category+ward combinations with high override rates.
    """
    import httpx
    coord_url = settings.COORDINATION_URL if hasattr(settings, "COORDINATION_URL") else "http://localhost:8003"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{coord_url}/coordination/overrides/patterns",
                headers={"X-Tenant-ID": ctx.tenant_id},
                params={"days_back": days_back}
            )
            if resp.status_code == 200:
                return resp.json()
    except Exception as e:
        logger.warning(f"Coordination patterns call failed (degraded mode): {e}")
    return []


# ── Cross-NGO Duplication ─────────────────────────────────────
@app.get("/duplication-rate")
async def duplication_rate(
    days_back: int = Query(30, ge=7),
    ctx: AuthContext = Depends(require_permission("analytics:read")),
    db=Depends(get_db),
):
    return await get_cross_ngo_duplication_rate(db, ctx.tenant_id, days_back)


# ── Feedback Loop ─────────────────────────────────────────────
@app.post("/feedback/process/{task_id}")
async def trigger_feedback(
    task_id: UUID,
    background_tasks: BackgroundTasks,
    ctx: AuthContext = Depends(require_permission("analytics:read")),
    db=Depends(get_db),
):
    """Manually trigger feedback loop for a completed task."""
    task_row = await db.execute(
        text("""
            SELECT task_id, need_id, household_id, assigned_volunteer_id,
                   outcome_status, follow_up_required, status
            FROM tasks WHERE task_id = :tid AND tenant_id = :ten
        """),
        {"tid": str(task_id), "ten": ctx.tenant_id}
    )
    task = task_row.fetchone()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status not in ("completed", "closed"):
        raise HTTPException(status_code=409, detail="Task not yet completed")

    results = await process_task_completion(
        db,
        task_id        = str(task.task_id),
        tenant_id      = ctx.tenant_id,
        household_id   = str(task.household_id) if task.household_id else None,
        volunteer_id   = str(task.assigned_volunteer_id),
        need_id        = str(task.need_id),
        outcome_status = task.outcome_status or "unresolved",
        follow_up_required = task.follow_up_required or False,
    )
    return {"task_id": str(task_id), "feedback_results": results}


# ── Feedback event queue ──────────────────────────────────────
@app.get("/feedback/pending")
async def pending_feedback_events(
    limit: int = Query(20, le=100),
    ctx: AuthContext = Depends(require_permission("analytics:read")),
    db=Depends(get_db),
):
    result = await db.execute(
        text("""
            SELECT * FROM feedback_events
            WHERE tenant_id = :tid AND processed = FALSE
            ORDER BY created_at ASC
            LIMIT :limit
        """),
        {"tid": ctx.tenant_id, "limit": limit}
    )
    return [dict(r._mapping) for r in result.fetchall()]


# ── Funder Report ─────────────────────────────────────────────
@app.get("/funder-report")
async def funder_report(
    period_months: int = Query(3, ge=1, le=12),
    ctx: AuthContext = Depends(require_permission("analytics:read")),
    db=Depends(get_db),
):
    """
    Anonymized impact report for funders.
    No PII. No individual records. Aggregates only.
    """
    end   = date.today()
    start = end - timedelta(days=period_months * 30)

    # Latest computed metrics
    metrics = await db.execute(
        text("""
            SELECT * FROM impact_metrics
            WHERE tenant_id  = :tid
              AND period_type = 'monthly'
              AND period_start >= :start
            ORDER BY period_start ASC
        """),
        {"tid": ctx.tenant_id, "start": start.isoformat()}
    )
    rows = [dict(r._mapping) for r in metrics.fetchall()]

    # HII distribution
    hii_dist = await db.execute(
        text("""
            SELECT trend, COUNT(*) AS cnt
            FROM household_improvement_index
            WHERE tenant_id  = :tid AND window_days = 30
              AND computed_at >= :start
            GROUP BY trend
        """),
        {"tid": ctx.tenant_id, "start": start.isoformat()}
    )
    trend_counts = {r.trend: r.cnt for r in hii_dist.fetchall() if r.trend}

    return {
        "report_period": {"start": start.isoformat(), "end": end.isoformat()},
        "months_covered": period_months,
        "monthly_metrics": rows,
        "household_trend_distribution": trend_counts,
        "note": "All data is anonymized. No personal information is included.",
        "generated_at": date.today().isoformat(),
    }


# ── Health ────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"service": "nexus-analytics", "status": "ok"}