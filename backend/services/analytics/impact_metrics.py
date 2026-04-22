"""
Impact Metrics Aggregator (Phase 5)
Computes all impact_metrics rows for a tenant.
Answers: 'Is this family's situation improving?'
         'Is the organization effective?'
         'What do funders need to see?'
"""
import json
import logging
import statistics
from datetime import datetime, timezone, timedelta, date
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

logger = logging.getLogger(__name__)


async def compute_period_metrics(
    db: AsyncSession,
    tenant_id:   str,
    period_start: date,
    period_end:   date,
    period_type:  str = "monthly",
) -> dict:
    """
    Compute all impact_metrics for a given period.
    Upserts into impact_metrics table.
    """
    p_start = period_start
    p_end   = period_end

    # ── Household metrics ──────────────────────────────────────
    hh_result = await db.execute(
        text("""
            SELECT
                COUNT(DISTINCT nr.household_id) AS households_served,
                COUNT(DISTINCT h.household_id)
                    FILTER (WHERE h.crisis_frequency > 2.0) AS households_chronic,
                COUNT(DISTINCT hii.household_id)
                    FILTER (WHERE hii.trend = 'improving'
                              AND hii.window_days = 30)   AS households_improved,
                AVG(hii.improvement_index)
                    FILTER (WHERE hii.window_days = 30)   AS avg_hii
            FROM need_records nr
            LEFT JOIN households h   ON nr.household_id = h.household_id
            LEFT JOIN household_improvement_index hii
                                     ON hii.household_id = nr.household_id
                                    AND hii.tenant_id    = :tid
                                    AND hii.window_days  = 30
            WHERE nr.tenant_id   = :tid
              AND nr.ingested_at >= :start
              AND nr.ingested_at <  :end
        """),
        {"tid": tenant_id, "start": p_start, "end": p_end}
    )
    hh = hh_result.fetchone()

    # ── Need metrics ───────────────────────────────────────────
    need_result = await db.execute(
        text("""
            SELECT
                COUNT(*)                                               AS needs_reported,
                COUNT(*) FILTER (WHERE nr.status IN ('resolved','closed')) AS needs_resolved,
                AVG(
                    EXTRACT(EPOCH FROM (t.dispatched_at - nr.ingested_at)) / 60.0
                ) FILTER (WHERE t.dispatched_at IS NOT NULL)           AS avg_tta_min
            FROM need_records nr
            LEFT JOIN tasks t ON t.need_id = nr.need_id
            WHERE nr.tenant_id   = :tid
              AND nr.ingested_at >= :start
              AND nr.ingested_at <  :end
        """),
        {"tid": tenant_id, "start": p_start, "end": p_end}
    )
    need = need_result.fetchone()

    # P95 time-to-assignment
    p95_result = await db.execute(
        text("""
            SELECT PERCENTILE_CONT(0.95) WITHIN GROUP (
                ORDER BY EXTRACT(EPOCH FROM (t.dispatched_at - nr.ingested_at)) / 60.0
            ) AS p95_tta
            FROM need_records nr
            JOIN tasks t ON t.need_id = nr.need_id
            WHERE nr.tenant_id   = :tid
              AND nr.ingested_at >= :start
              AND nr.ingested_at <  :end
              AND t.dispatched_at IS NOT NULL
        """),
        {"tid": tenant_id, "start": p_start, "end": p_end}
    )
    p95 = p95_result.fetchone()

    # ── Volunteer metrics ──────────────────────────────────────
    vol_result = await db.execute(
        text("""
            SELECT
                COUNT(DISTINCT t.assigned_volunteer_id) AS volunteers_active,
                COUNT(DISTINCT v.volunteer_id)
                    FILTER (WHERE v.created_at < :start) AS vol_existing,
                COUNT(DISTINCT v.volunteer_id)
                    FILTER (WHERE v.created_at >= :start
                              AND v.last_deployed_at IS NOT NULL) AS vol_retained
            FROM tasks t
            JOIN volunteers v ON t.assigned_volunteer_id = v.volunteer_id
            WHERE t.tenant_id   = :tid
              AND t.created_at >= :start
              AND t.created_at <  :end
              AND t.status      = 'closed'
        """),
        {"tid": tenant_id, "start": p_start, "end": p_end}
    )
    vol = vol_result.fetchone()

    # ── Category breakdown ─────────────────────────────────────
    cat_result = await db.execute(
        text("""
            SELECT category, COUNT(*) AS cnt
            FROM need_records
            WHERE tenant_id   = :tid
              AND ingested_at >= :start
              AND ingested_at <  :end
            GROUP BY category
            ORDER BY cnt DESC
        """),
        {"tid": tenant_id, "start": p_start, "end": p_end}
    )
    cat_breakdown = {r[0]: r[1] for r in cat_result.fetchall() if r and r[0]}

    # ── Ward breakdown ─────────────────────────────────────────
    ward_result = await db.execute(
        text("""
            SELECT ward_id, COUNT(*) AS cnt, AVG(urgency_score) AS avg_urgency
            FROM need_records
            WHERE tenant_id   = :tid
              AND ingested_at >= :start
              AND ingested_at <  :end
              AND ward_id IS NOT NULL
            GROUP BY ward_id
            ORDER BY cnt DESC
            LIMIT 20
        """),
        {"tid": tenant_id, "start": p_start, "end": p_end}
    )
    ward_breakdown = {
        r[0]: {"count": r[1], "avg_urgency": round(float(r[2] or 0), 3)}
        for r in ward_result.fetchall() if r
    }

    # ── Assemble ───────────────────────────────────────────────
    needs_reported = int((need[0] if need else 0) or 0)
    needs_resolved = int((need[1] if need else 0) or 0)
    resolution_rate = needs_resolved / needs_reported if needs_reported > 0 else 0.0

    vol_existing  = int((vol[1] if vol else 1) or 1)
    vol_retained  = int((vol[2] if vol else 0) or 0)
    retention_rate = vol_retained / vol_existing if vol_existing > 0 else 1.0

    metrics = {
        "tenant_id":                  tenant_id,
        "period_start":               p_start,
        "period_end":                 p_end,
        "period_type":                period_type,
        "households_served":          int((hh[0] if hh else 0) or 0),
        "households_chronic":         int((hh[1] if hh else 0) or 0),
        "households_improved":        int((hh[2] if hh else 0) or 0),
        "avg_improvement_index":      round(float((hh[3] if hh else 0) or 0), 4),
        "needs_reported":             needs_reported,
        "needs_resolved":             needs_resolved,
        "needs_resolution_rate":      round(float(resolution_rate or 0), 4),
        "avg_time_to_assignment_min": round(float((need[2] if need else 0) or 0), 2),
        "p95_time_to_assignment_min": round(float((p95[0] if p95 else 0) or 0), 2),
        "volunteers_active":          int((vol[0] if vol else 0) or 0),
        "volunteer_hours":            0.0,   # requires time-tracking (Phase 5 extension)
        "volunteer_retention_rate":   round(retention_rate, 4),
        "cross_ngo_dup_rate":         0.0,   # requires cross-tenant query (linked households)
        "resource_desert_count":      0,     # from latest gap_report
        "category_breakdown":         cat_breakdown,
        "ward_breakdown":             ward_breakdown,
    }

    # Upsert
    await db.execute(
        text("""
            INSERT INTO impact_metrics (
                tenant_id, period_start, period_end, period_type,
                households_served, households_chronic, households_improved, avg_improvement_index,
                needs_reported, needs_resolved, needs_resolution_rate,
                avg_time_to_assignment_min, p95_time_to_assignment_min,
                volunteers_active, volunteer_hours, volunteer_retention_rate,
                cross_ngo_dup_rate, resource_desert_count,
                category_breakdown, ward_breakdown
            )
            VALUES (
                :tenant_id, :period_start, :period_end, :period_type,
                :households_served, :households_chronic, :households_improved, :avg_improvement_index,
                :needs_reported, :needs_resolved, :needs_resolution_rate,
                :avg_time_to_assignment_min, :p95_time_to_assignment_min,
                :volunteers_active, :volunteer_hours, :volunteer_retention_rate,
                :cross_ngo_dup_rate, :resource_desert_count,
                CAST(:cat AS JSONB), CAST(:ward AS JSONB)
            )
            ON CONFLICT (tenant_id, period_start, period_end, period_type) DO UPDATE SET
                households_served          = EXCLUDED.households_served,
                households_chronic         = EXCLUDED.households_chronic,
                households_improved        = EXCLUDED.households_improved,
                avg_improvement_index      = EXCLUDED.avg_improvement_index,
                needs_reported             = EXCLUDED.needs_reported,
                needs_resolved             = EXCLUDED.needs_resolved,
                needs_resolution_rate      = EXCLUDED.needs_resolution_rate,
                avg_time_to_assignment_min = EXCLUDED.avg_time_to_assignment_min,
                p95_time_to_assignment_min = EXCLUDED.p95_time_to_assignment_min,
                volunteers_active          = EXCLUDED.volunteers_active,
                volunteer_retention_rate   = EXCLUDED.volunteer_retention_rate,
                category_breakdown         = EXCLUDED.category_breakdown,
                ward_breakdown             = EXCLUDED.ward_breakdown,
                computed_at                = NOW()
        """),
        {**metrics, "cat": json.dumps(cat_breakdown), "ward": json.dumps(ward_breakdown)}
    )
    return metrics


async def get_household_improvement_dashboard(
    db: AsyncSession,
    tenant_id:   str,
    window_days: int = 30,
    limit:       int = 50,
    trend_filter: Optional[str] = None,
) -> list[dict]:
    """
    Fetch household improvement data for coordinator dashboard.
    Sorted by improvement_index ASC (worst-performing first).
    """
    conditions = ["hii.tenant_id = :tid", "hii.window_days = :window"]
    params: dict = {"tid": tenant_id, "window": window_days, "limit": limit}

    if trend_filter:
        conditions.append("hii.trend = :trend")
        params["trend"] = trend_filter

    where = " AND ".join(conditions)
    result = await db.execute(
        text(f"""
            SELECT
                hii.*,
                h.location_description,
                h.ward_id,
                h.vulnerability_flags,
                h.crisis_frequency,
                h.total_needs_reported
            FROM household_improvement_index hii
            JOIN households h ON hii.household_id = h.household_id
            WHERE {where}
            ORDER BY hii.improvement_index ASC, hii.crisis_frequency DESC
            LIMIT :limit
        """),
        params
    )
    return [dict(r._mapping) for r in result.fetchall()]


async def get_volunteer_performance_summary(
    db: AsyncSession,
    tenant_id: str,
    limit:     int = 20,
) -> list[dict]:
    """Volunteer performance for coordinator view — sorted by full_resolution_rate DESC."""
    result = await db.execute(
        text("""
            SELECT
                v.volunteer_id,
                v.total_deployments,
                v.outcome_rating,
                v.response_rate,
                v.burnout_risk_score,
                v.last_deployed_at,
                v.active,
                COUNT(t.task_id) FILTER (WHERE t.status='closed')          AS closed_tasks,
                COUNT(t.task_id) FILTER (WHERE t.outcome_status='need_fully_met')
                                                                             AS fully_met_count,
                CASE WHEN COUNT(t.task_id) FILTER (WHERE t.status='closed') > 0
                    THEN COUNT(t.task_id) FILTER (WHERE t.outcome_status='need_fully_met')
                         ::float /
                         COUNT(t.task_id) FILTER (WHERE t.status='closed')
                    ELSE 0
                END                                                          AS full_resolution_rate
            FROM volunteers v
            LEFT JOIN tasks t ON t.assigned_volunteer_id = v.volunteer_id
                              AND t.tenant_id = :tid
                              AND t.closed_at >= NOW() - INTERVAL '90 days'
            WHERE v.tenant_id = :tid
            GROUP BY v.volunteer_id
            ORDER BY full_resolution_rate DESC, v.total_deployments DESC
            LIMIT :limit
        """),
        {"tid": tenant_id, "limit": limit}
    )
    return [dict(r._mapping) for r in result.fetchall()]


async def get_cross_ngo_duplication_rate(
    db: AsyncSession,
    tenant_id: str,
    days_back: int = 30,
) -> dict:
    """
    Fraction of households served by 2+ organizations in the period.
    Requires global_household_id (cross-tenant links).
    """
    result = await db.execute(
        text("""
            SELECT
                COUNT(DISTINCT nr.household_id)  AS total_households,
                COUNT(DISTINCT h.global_household_id)
                    FILTER (WHERE h.global_household_id IS NOT NULL) AS linked_households
            FROM need_records nr
            JOIN households h ON nr.household_id = h.household_id
            WHERE nr.tenant_id   = :tid
              AND nr.ingested_at >= NOW() - INTERVAL ':days days'
        """.replace(":days", str(days_back))),
        {"tid": tenant_id}
    )
    row = result.fetchone()
    total   = int(row.total_households or 0)
    linked  = int(row.linked_households or 0)
    return {
        "total_households":  total,
        "cross_ngo_linked":  linked,
        "duplication_rate":  round(linked / total, 4) if total > 0 else 0.0,
        "period_days":       days_back,
    }