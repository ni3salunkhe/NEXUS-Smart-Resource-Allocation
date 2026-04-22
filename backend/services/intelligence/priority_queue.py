"""
Priority Queue Manager
- Maintains ranked list of unassigned needs
- Re-ranks on every urgency score update
- Auto-escalation detection
- Ward stats refresh (every 4h)
- Gap report generation
"""
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from .scoring import UrgencyWeights, should_escalate, VULNERABILITY_FLAGS, calculate_urgency_score, ScoringResult

logger = logging.getLogger(__name__)

# ── Priority queue query ──────────────────────────────────────
PRIORITY_QUEUE_SQL = """
    SELECT
        nr.need_id,
        nr.tenant_id,
        nr.household_id,
        nr.category,
        nr.subcategory,
        nr.description,
        nr.severity_score,
        nr.urgency_score,
        nr.beneficiary_count,
        nr.vulnerability_flags,
        nr.status,
        nr.ward_id,
        nr.source_type,
        nr.ingested_at,
        nr.reported_at,
        nr.nlp_confidence,
        h.crisis_frequency,
        h.vulnerability_score     AS hh_vulnerability_score,
        h.vulnerability_flags     AS hh_vulnerability_flags,
        h.total_needs_reported    AS hh_total_needs,
        h.location_description    AS hh_location_description,
        h.landmark_tags           AS hh_landmark_tags
    FROM need_records nr
    LEFT JOIN households h ON nr.household_id = h.household_id
    WHERE
        nr.tenant_id = :tid
        AND nr.status IN ('unverified','verified')
        AND nr.assigned_task_id IS NULL
        {category_filter}
        {ward_filter}
        {vuln_filter}
    ORDER BY nr.urgency_score DESC, nr.severity_score DESC, nr.ingested_at ASC
    LIMIT :limit OFFSET :offset
"""


async def get_priority_queue(
    db: AsyncSession,
    tenant_id: str,
    limit: int = 20,
    offset: int = 0,
    category: Optional[str] = None,
    ward_id: Optional[str] = None,
    vulnerability_filter: Optional[str] = None,  # "has_child"|"has_elderly"|etc
) -> list[dict]:
    """
    Fetch ranked priority queue of unassigned needs.
    Sorted by urgency_score DESC.
    """
    params: dict = {"tid": tenant_id, "limit": limit, "offset": offset}

    cat_f  = "AND nr.category = :cat"    if category            else ""
    ward_f = "AND nr.ward_id  = :ward"   if ward_id             else ""
    
    # Secure JSONB filtering: Only allow whitelisted keys to prevent SQL injection
    vuln_f = ""
    if vulnerability_filter:
        if vulnerability_filter not in VULNERABILITY_FLAGS:
            logger.warning(f"Rejected invalid vulnerability filter attempt: {vulnerability_filter}")
            raise ValueError(f"Invalid vulnerability filter: {vulnerability_filter}")
        
        # Use parameterized JSONB key access
        vuln_f = "AND (nr.vulnerability_flags->>:v_key)::bool = TRUE"
        params["v_key"] = vulnerability_filter

    if category:
        params["cat"]  = category
    if ward_id:
        params["ward"] = ward_id

    sql = PRIORITY_QUEUE_SQL.format(
        category_filter=cat_f,
        ward_filter=ward_f,
        vuln_filter=vuln_f,
    )
    result = await db.execute(text(sql), params)
    rows = result.fetchall()

    queue = []
    for row in rows:
        item = dict(row._mapping)
        # Add escalation flag
        item["needs_escalation"] = should_escalate(
            urgency_score=item["urgency_score"],
            ingested_at=item.get("ingested_at"),
            status=item["status"],
        )
        queue.append(item)

    return queue


# ── Recompute urgency for a single need ───────────────────────
async def recompute_need_urgency(
    db: AsyncSession,
    need_id: str,
    tenant_id: str,
    trigger: str = "schedule",
) -> Optional[float]:
    """
    Full urgency recompute for one need record.
    Fetches all required inputs, runs compute_urgency_score, persists result.
    """
    from .scoring import calculate_urgency_score, UrgencyWeights

    # Fetch need + household + ward stats in one query
    result = await db.execute(
        text("""
            SELECT
                nr.need_id, nr.severity_score, nr.source_type,
                nr.category, nr.status, nr.ingested_at, nr.reported_at,
                nr.vulnerability_flags AS need_vuln_flags,
                nr.urgency_score AS prev_score,
                h.vulnerability_score, h.vulnerability_flags AS hh_vuln_flags,
                h.crisis_frequency,
                ws.coverage_ratio, ws.active_tasks_count
            FROM need_records nr
            LEFT JOIN households h  ON nr.household_id = h.household_id
            LEFT JOIN ward_stats ws ON nr.ward_id = ws.ward_id
                                    AND ws.tenant_id = nr.tenant_id
            WHERE nr.need_id = :nid AND nr.tenant_id = :tid
        """),
        {"nid": need_id, "tid": tenant_id}
    )
    row = result.fetchone()
    if not row:
        return None

    # Load tenant urgency weight config
    cfg = await _load_weights(db, tenant_id)

    # Merge need + household vulnerability flags
    need_vf = row.need_vuln_flags or {}
    hh_vf   = row.hh_vuln_flags   or {}
    merged_vf = {k: need_vf.get(k, False) or hh_vf.get(k, False)
                 for k in set(need_vf) | set(hh_vf)}

    components: ScoringResult = calculate_urgency_score(
        severity_score       = row.severity_score or 0.5,
        reported_at          = row.reported_at,
        ingested_at          = row.ingested_at,
        status               = row.status,
        vulnerability_flags  = merged_vf,
        vulnerability_score  = row.vulnerability_score or 0.0,
        crisis_frequency     = row.crisis_frequency or 0.0,
        source_type          = row.source_type or "mobile",
        category             = row.category,
        weights              = cfg,
    )

    new_score = components.final_score

    # Update need_record
    await db.execute(
        text("UPDATE need_records SET urgency_score = :score, updated_at = NOW() WHERE need_id = :nid"),
        {"score": new_score, "nid": need_id}
    )

    # Append to urgency_score_log
    await db.execute(
        text("""
            INSERT INTO urgency_score_log (
                need_id, tenant_id, score, prev_score, components,
                t1_severity, t2_recency, t3_vulnerability, t4_unmet_duration,
                t5_source_reliability, t6_crisis_frequency, t7_coverage_penalty,
                trigger
            )
            VALUES (
                :nid, :tid, :score, :prev, CAST(:components AS JSONB),
                :t1, :t2, :t3, :t4, :t5, :t6, :t7, :trigger
            )
        """),
        {
            "nid":        need_id,
            "tid":        tenant_id,
            "score":      new_score,
            "prev":       row.prev_score,
            "components": json.dumps(components.components),
            "t1": components.components.get("severity", 0),
            "t2": components.components.get("recency", 0),
            "t3": components.components.get("vulnerability", 0),
            "t4": components.components.get("duration", 0),
            "t5": components.components.get("source", 0),
            "t6": components.components.get("frequency", 0),
            "t7": 0.0,
            "trigger": trigger,
        }
    )

    return new_score


import asyncio

async def recompute_all_tenant_urgency(
    db: AsyncSession,
    tenant_id: str,
    chunk_size: int = 50,
) -> int:
    """
    Batch recompute for all open needs in a tenant.
    Uses chunking and asyncio yielding to prevent event-loop starvation.
    """
    result = await db.execute(
        text("""
            SELECT need_id FROM need_records
            WHERE tenant_id = :tid AND status IN ('unverified','verified','assigned','in_progress')
        """),
        {"tid": tenant_id}
    )
    need_ids = [str(r.need_id) for r in result.fetchall()]

    count = 0
    # Process in chunks to avoid locking the loop or DB for too long
    for i in range(0, len(need_ids), chunk_size):
        chunk = need_ids[i:i + chunk_size]
        
        # Parallelize the chunk processing
        tasks = [recompute_need_urgency(db, nid, tenant_id, trigger="schedule") for nid in chunk]
        chunk_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for res in chunk_results:
            if isinstance(res, Exception):
                logger.error(f"Error recomputing urgency in batch: {res}")
            elif res is not None:
                count += 1
        
        # Commit every chunk to persist progress and release locks
        await db.commit()
        
        # Yield to event loop between chunks
        await asyncio.sleep(0.01)

    logger.info(f"Batch recompute complete: {count} needs updated for tenant {tenant_id}")
    return count


# ── Ward stats refresh ────────────────────────────────────────
async def refresh_ward_stats(db: AsyncSession, tenant_id: str) -> int:
    """
    Recompute per-ward aggregates. Called every 4 hours by scheduler.
    Returns number of wards updated.
    """
    result = await db.execute(
        text("""
            SELECT
                ward_id,
                COUNT(*)                                          AS open_needs,
                AVG(urgency_score)                               AS avg_urgency,
                MAX(urgency_score)                               AS max_urgency,
                COUNT(*) FILTER (WHERE status IN ('assigned','in_progress'))
                                                                  AS active_tasks,
                jsonb_object_agg(COALESCE(category,'other'),
                    category_count)                              AS cat_breakdown
            FROM (
                SELECT
                    ward_id, urgency_score, status, category,
                    COUNT(*) OVER (PARTITION BY ward_id, category) AS category_count
                FROM need_records
                WHERE tenant_id = :tid
                  AND status NOT IN ('closed','resolved','duplicate')
                  AND ward_id IS NOT NULL
            ) sub
            GROUP BY ward_id
        """),
        {"tid": tenant_id}
    )
    rows = result.fetchall()

    for row in rows:
        open_n  = row.open_needs   or 0
        active  = row.active_tasks or 0
        coverage = (active / open_n) if open_n > 0 else 1.0
        is_desert = (row.avg_urgency or 0) >= 0.70 and active == 0

        await db.execute(
            text("""
                INSERT INTO ward_stats (
                    tenant_id, ward_id,
                    total_needs_open, avg_urgency_score, max_urgency_score,
                    active_tasks_count, coverage_ratio, is_resource_desert,
                    category_breakdown, computed_at
                )
                VALUES (
                    :tid, :ward,
                    :open, :avg, :max,
                    :tasks, :cov, :desert,
                    CAST(:cat AS JSONB), NOW()
                )
                ON CONFLICT (tenant_id, ward_id) DO UPDATE SET
                    total_needs_open   = EXCLUDED.total_needs_open,
                    avg_urgency_score  = EXCLUDED.avg_urgency_score,
                    max_urgency_score  = EXCLUDED.max_urgency_score,
                    active_tasks_count = EXCLUDED.active_tasks_count,
                    coverage_ratio     = EXCLUDED.coverage_ratio,
                    is_resource_desert = EXCLUDED.is_resource_desert,
                    category_breakdown = EXCLUDED.category_breakdown,
                    computed_at        = NOW()
            """),
            {
                "tid":    tenant_id,
                "ward":   row.ward_id,
                "open":   open_n,
                "avg":    row.avg_urgency or 0.0,
                "max":    row.max_urgency or 0.0,
                "tasks":  active,
                "cov":    coverage,
                "desert": is_desert,
                "cat":    json.dumps(row.cat_breakdown or {}),
            }
        )

    logger.info(f"Ward stats refreshed: {len(rows)} wards for tenant {tenant_id}")
    return len(rows)


# ── Gap report generator ──────────────────────────────────────
async def generate_gap_report(db: AsyncSession, tenant_id: str) -> dict:
    """
    Identify resource deserts and top unmet high-urgency needs.
    Persists to gap_reports table and returns report dict.
    """
    # Desert wards
    desert_result = await db.execute(
        text("""
            SELECT ward_id, total_needs_open, avg_urgency_score, active_tasks_count
            FROM ward_stats
            WHERE tenant_id = :tid AND is_resource_desert = TRUE
            ORDER BY avg_urgency_score DESC
            LIMIT 20
        """),
        {"tid": tenant_id}
    )
    desert_wards = [dict(r._mapping) for r in desert_result.fetchall()]

    # Top unmet high-urgency needs
    unmet_result = await db.execute(
        text("""
            SELECT need_id, category, urgency_score, severity_score,
                   ward_id, beneficiary_count, ingested_at
            FROM need_records
            WHERE tenant_id = :tid
              AND status IN ('unverified','verified')
              AND urgency_score >= 0.75
            ORDER BY urgency_score DESC
            LIMIT 10
        """),
        {"tid": tenant_id}
    )
    top_unmet = [dict(r._mapping) for r in unmet_result.fetchall()]

    summary = {
        "desert_ward_count":   len(desert_wards),
        "top_unmet_count":     len(top_unmet),
        "generated_at":        datetime.now(timezone.utc).isoformat(),
    }

    # Persist
    await db.execute(
        text("""
            INSERT INTO gap_reports (tenant_id, desert_wards, top_unmet_needs, summary)
            VALUES (:tid, CAST(:deserts AS JSONB), CAST(:unmet AS JSONB), CAST(:summary AS JSONB))
        """),
        {
            "tid":     tenant_id,
            "deserts": json.dumps(desert_wards, default=str),
            "unmet":   json.dumps(top_unmet,    default=str),
            "summary": json.dumps(summary),
        }
    )

    return {"desert_wards": desert_wards, "top_unmet": top_unmet, "summary": summary}


# ── Load tenant weight config ─────────────────────────────────
async def _load_weights(db: AsyncSession, tenant_id: str) -> UrgencyWeights:
    result = await db.execute(
        text("""
            SELECT w1_severity, w2_recency, w3_vulnerability, w4_unmet_duration,
                   w5_source_reliability, w6_crisis_frequency, w7_coverage_penalty,
                   chronic_threshold, chronic_floor, escalation_threshold,
                   escalation_minutes, category_boosts
            FROM urgency_weight_configs
            WHERE tenant_id = :tid
        """),
        {"tid": tenant_id}
    )
    row = result.fetchone()
    if not row:
        return UrgencyWeights()

    return UrgencyWeights(
        w1_severity           = row.w1_severity,
        w2_recency            = row.w2_recency,
        w3_vulnerability      = row.w3_vulnerability,
        w4_unmet_duration     = row.w4_unmet_duration,
        w5_source_reliability = row.w5_source_reliability,
        w6_crisis_frequency   = row.w6_crisis_frequency,
        w7_coverage_penalty   = row.w7_coverage_penalty,
        chronic_threshold     = row.chronic_threshold,
        chronic_floor         = row.chronic_floor,
        escalation_threshold  = row.escalation_threshold,
        escalation_minutes    = row.escalation_minutes,
        category_boosts       = row.category_boosts or {},
    )