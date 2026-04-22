"""
Override Learning Engine (Phase 4)
Every time a coordinator overrides the algorithm's top suggestion:
  1. Record the override with full context
  2. When task closes, update override with outcome
  3. Aggregate patterns → adjust matching weight signals
  4. Expose override analytics for coordinator transparency
"""
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

logger = logging.getLogger(__name__)


@dataclass
class OverridePattern:
    """Aggregated pattern from override history."""
    category:          Optional[str]
    ward_id:           Optional[str]
    override_count:    int
    avg_urgency:       float
    avg_rating_algo:   float   # rating when algo suggestion was used
    avg_rating_override: float # rating when coordinator overrode
    override_win_rate: float   # fraction where override was better outcome


async def record_override(
    db: AsyncSession,
    task_id:          str,
    tenant_id:        str,
    suggested_vol_id: Optional[str],
    suggested_score:  Optional[float],
    chosen_vol_id:    str,
    coordinator_id:   str,
    override_reason:  str,
    need_category:    Optional[str],
    need_ward_id:     Optional[str],
    need_urgency:     Optional[float],
) -> str:
    """Record a coordinator override decision. Returns override_id."""
    result = await db.execute(
        text("""
            INSERT INTO match_override_log (
                task_id, tenant_id,
                suggested_vol_id, suggested_score,
                chosen_vol_id, coordinator_id, override_reason,
                need_category, need_ward_id, need_urgency
            )
            VALUES (
                :task_id, :tid,
                :sug_vol, :sug_score,
                :chosen, :coord, :reason,
                :cat, :ward, :urgency
            )
            RETURNING override_id
        """),
        {
            "task_id":   task_id,
            "tid":       tenant_id,
            "sug_vol":   suggested_vol_id,
            "sug_score": suggested_score,
            "chosen":    chosen_vol_id,
            "coord":     coordinator_id,
            "reason":    override_reason,
            "cat":       need_category,
            "ward":      need_ward_id,
            "urgency":   need_urgency,
        }
    )
    return str(result.fetchone().override_id)


async def update_override_outcome(
    db: AsyncSession,
    task_id:          str,
    tenant_id:        str,
    task_outcome:     str,
    volunteer_rating: Optional[float],
) -> None:
    """
    Called when a task closes. Updates override record with outcome.
    Computes override_was_better by comparing volunteer_rating
    against the historical avg_outcome_rating of the suggested volunteer.
    """
    # Find the override record for this task
    override_row = await db.execute(
        text("""
            SELECT override_id, suggested_vol_id, chosen_vol_id
            FROM match_override_log
            WHERE task_id = :tid AND tenant_id = :ten
            ORDER BY created_at DESC
            LIMIT 1
        """),
        {"tid": task_id, "ten": tenant_id}
    )
    override = override_row.fetchone()
    if not override:
        return

    override_was_better = None
    if volunteer_rating is not None and override.suggested_vol_id:
        # Compare chosen volunteer's task rating vs suggested volunteer's historical avg
        sug_rating_row = await db.execute(
            text("""
                SELECT AVG(volunteer_rating) AS avg_rating
                FROM tasks
                WHERE assigned_volunteer_id = :vid
                  AND tenant_id             = :ten
                  AND volunteer_rating IS NOT NULL
                  AND status = 'closed'
            """),
            {"vid": str(override.suggested_vol_id), "ten": tenant_id}
        )
        sug_avg = sug_rating_row.fetchone()
        sug_rating = float(sug_avg.avg_rating or 3.5)
        override_was_better = volunteer_rating > sug_rating

    await db.execute(
        text("""
            UPDATE match_override_log SET
                task_outcome       = :outcome,
                volunteer_rating   = :rating,
                override_was_better= :better,
                outcome_updated_at = NOW()
            WHERE override_id = :oid
        """),
        {
            "outcome": task_outcome,
            "rating":  volunteer_rating,
            "better":  override_was_better,
            "oid":     str(override.override_id),
        }
    )


async def get_override_patterns(
    db: AsyncSession,
    tenant_id: str,
    days_back:  int = 90,
) -> list[dict]:
    """
    Aggregate override patterns by category + ward.
    Used by coordinator dashboard to show 'the algorithm tends to underperform here'.
    """
    result = await db.execute(
        text("""
            SELECT
                need_category,
                need_ward_id,
                COUNT(*)                                          AS override_count,
                AVG(need_urgency)                                 AS avg_urgency,
                AVG(volunteer_rating) FILTER (WHERE override_was_better = FALSE)
                                                                  AS avg_rating_algo,
                AVG(volunteer_rating) FILTER (WHERE override_was_better = TRUE)
                                                                  AS avg_rating_override,
                COALESCE(
                    AVG(CASE WHEN override_was_better THEN 1.0 ELSE 0.0 END)
                    FILTER (WHERE override_was_better IS NOT NULL),
                    0
                )                                                 AS override_win_rate
            FROM match_override_log
            WHERE tenant_id  = :tid
              AND created_at >= NOW() - INTERVAL ':days days'
            GROUP BY need_category, need_ward_id
            HAVING COUNT(*) >= 3
            ORDER BY override_count DESC
            LIMIT 20
        """.replace(":days", str(days_back)),  # safe — integer only
        {"tid": tenant_id})
    )
    return [dict(r._mapping) for r in result.fetchall()]


async def get_override_summary(
    db: AsyncSession,
    tenant_id: str,
    days_back:  int = 30,
) -> dict:
    """High-level override stats for coordinator dashboard."""
    result = await db.execute(
        text(f"""
            SELECT
                COUNT(*)                                               AS total_overrides,
                COUNT(*) FILTER (WHERE override_was_better = TRUE)    AS better_outcomes,
                COUNT(*) FILTER (WHERE override_was_better = FALSE)   AS worse_outcomes,
                COUNT(*) FILTER (WHERE override_was_better IS NULL)   AS pending_outcome,
                AVG(volunteer_rating) FILTER (WHERE override_was_better IS NOT NULL) AS avg_rating
            FROM match_override_log
            WHERE tenant_id  = :tid
              AND created_at >= NOW() - INTERVAL '{days_back} days'
        """),
        {"tid": tenant_id}
    )
    row = result.fetchone()
    if not row:
        return {}

    total = int(row.total_overrides or 0)
    better = int(row.better_outcomes or 0)
    return {
        "total_overrides":   total,
        "better_outcomes":   better,
        "worse_outcomes":    int(row.worse_outcomes or 0),
        "pending_outcome":   int(row.pending_outcome or 0),
        "override_win_rate": round(better / total, 3) if total > 0 else None,
        "avg_volunteer_rating": round(float(row.avg_rating or 0), 2),
        "period_days":       days_back,
    }