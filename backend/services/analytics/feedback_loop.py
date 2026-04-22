"""
Feedback Loop Processor (Phase 5)
Outcome of every completed task triggers:
  1. Urgency score recompute for remaining household needs
  2. crisis_frequency recompute on household
  3. Household improvement index recompute
  4. Volunteer burnout score recompute
  5. household_history ledger event
  6. impact_metrics aggregation update

This module is the 'closed loop' — the answer to
'Is this family's situation improving?' becomes computable.
"""
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

logger = logging.getLogger(__name__)

# HII window sizes to compute
HII_WINDOWS = [30, 90, 365]


# ── Main feedback processor ───────────────────────────────────
async def process_task_completion(
    db: AsyncSession,
    task_id:        str,
    tenant_id:      str,
    household_id:   Optional[str],
    volunteer_id:   str,
    need_id:        str,
    outcome_status: str,
    follow_up_required: bool,
) -> dict:
    """
    Central feedback orchestrator.
    Called immediately after a task is marked 'completed'.
    Returns summary of all signals updated.
    """
    results = {}

    # 0. Update task with outcome and derived rating if not present
    rating = 5.0 if outcome_status == "need_fully_met" else 3.0 if outcome_status == "partially_met" else 1.0
    await db.execute(
        text("""
            UPDATE tasks 
            SET status = 'closed', 
                outcome_status = :outcome,
                volunteer_rating = COALESCE(volunteer_rating, :rating),
                closed_at = NOW()
            WHERE task_id = :tid
        """),
        {"outcome": outcome_status, "rating": rating, "tid": task_id}
    )

    # 1. Recompute household crisis_frequency
    if household_id:
        freq = await _recompute_crisis_frequency(db, household_id, tenant_id)
        results["crisis_frequency"] = freq

    # 2. Recompute urgency scores for all open needs of this household
    if household_id:
        urgency_count = await _recompute_household_urgency(db, household_id, tenant_id)
        results["urgency_recomputed"] = urgency_count

    # 3. Recompute household improvement index
    if household_id:
        hii_scores = await _recompute_hii(db, household_id, tenant_id)
        results["hii"] = hii_scores

    # 4. Emit household_history ledger event
    if household_id:
        await _emit_hh_history(db, household_id, tenant_id, task_id, need_id,
                               outcome_status, volunteer_id)

    # 5. Recompute volunteer burnout (imported inline to avoid circular)
    from services.coordination.burnout import compute_volunteer_burnout
    burnout = await compute_volunteer_burnout(db, volunteer_id, tenant_id)
    results["burnout_score"] = burnout.score
    results["burnout_label"] = burnout.label

    # 6. Update volunteer's outcome_rating rolling average
    await _update_volunteer_outcome_rating(db, volunteer_id, tenant_id)
    results["volunteer_updated"] = True

    # 7. If follow-up required, create new NeedRecord
    if follow_up_required:
        new_need_id = await _create_follow_up_need(db, need_id, household_id, tenant_id)
        results["follow_up_need_id"] = new_need_id

    # 8. Record feedback event for async processing
    await _record_feedback_event(db, tenant_id, task_id, household_id,
                                 volunteer_id, need_id, outcome_status, results)

    return results


# ── Signal updaters ───────────────────────────────────────────
async def _recompute_crisis_frequency(
    db: AsyncSession, household_id: str, tenant_id: str
) -> float:
    """Rolling 6-month needs/month for household."""
    result = await db.execute(
        text("""
            SELECT COUNT(*) AS cnt
            FROM household_history
            WHERE household_id = :hid
              AND tenant_id    = :tid
              AND event_type   = 'need_reported'
              AND event_timestamp >= NOW() - INTERVAL '6 months'
        """),
        {"hid": household_id, "tid": tenant_id}
    )
    row   = result.fetchone()
    freq  = float((row[0] if row else 0) or 0) / 6.0

    await db.execute(
        text("""
            UPDATE households SET crisis_frequency = :freq, updated_at = NOW()
            WHERE household_id = :hid AND tenant_id = :tid
        """),
        {"freq": freq, "hid": household_id, "tid": tenant_id}
    )
    return freq


async def _recompute_household_urgency(
    db: AsyncSession, household_id: str, tenant_id: str
) -> int:
    """Recompute urgency for all open needs of this household."""
    result = await db.execute(
        text("""
            SELECT need_id FROM need_records
            WHERE household_id = :hid
              AND tenant_id    = :tid
              AND status NOT IN ('resolved','closed','duplicate')
        """),
        {"hid": household_id, "tid": tenant_id}
    )
    need_ids = [str(r.need_id) for r in result.fetchall()]

    count = 0
    for nid in need_ids:
        try:
            from services.intelligence.priority_queue import recompute_need_urgency
            await recompute_need_urgency(db, nid, tenant_id, trigger="outcome")
            count += 1
        except Exception as e:
            logger.warning(f"Urgency recompute failed for {nid}: {e}")

    return count


async def _recompute_hii(
    db: AsyncSession, household_id: str, tenant_id: str
) -> dict:
    """
    Household Improvement Index for each window (30/90/365 days).
    HII = fully_met / (partially_met + unresolved)  — higher is better.
    """
    scores = {}
    for window in HII_WINDOWS:
        result = await db.execute(
            text(f"""
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE t.outcome_status = 'need_fully_met')    AS fully_met,
                    COUNT(*) FILTER (WHERE t.outcome_status = 'partially_met')     AS partially_met,
                    COUNT(*) FILTER (WHERE t.outcome_status = 'unresolved')        AS unresolved
                FROM tasks t
                JOIN need_records nr ON t.need_id = nr.need_id
                WHERE nr.household_id = :hid
                  AND t.tenant_id     = :tid
                  AND t.status        = 'closed'
                  AND t.closed_at    >= NOW() - INTERVAL '{window} days'
            """),
            {"hid": household_id, "tid": tenant_id}
        )
        row = result.fetchone()

        total        = int(row.total or 0)
        fully_met    = int(row.fully_met or 0)
        partially    = int(row.partially_met or 0)
        unresolved   = int(row.unresolved or 0)
        denominator  = partially + unresolved

        hii = fully_met / denominator if denominator > 0 else (1.0 if fully_met > 0 else 0.0)

        # Determine trend vs previous window
        trend = _compute_trend(fully_met, partially, unresolved, total)

        await db.execute(
            text("""
                INSERT INTO household_improvement_index (
                    household_id, tenant_id, window_days,
                    total_needs, fully_met, partially_met, unresolved,
                    improvement_index, trend
                )
                VALUES (
                    :hid, :tid, :window,
                    :total, :fully, :partial, :unresolved,
                    :hii, :trend
                )
            """),
            {
                "hid": household_id, "tid": tenant_id, "window": window,
                "total": total, "fully": fully_met,
                "partial": partially, "unresolved": unresolved,
                "hii": round(hii, 4), "trend": trend,
            }
        )
        scores[f"hii_{window}d"] = round(hii, 4)

    return scores


def _compute_trend(fully_met: int, partially: int, unresolved: int, total: int) -> str:
    """Compute simple trend label."""
    if total < 2:
        return "insufficient_data"
    if fully_met == 0 and (partially + unresolved) > 0:
        return "worsening"
    hii = fully_met / (partially + unresolved) if (partially + unresolved) > 0 else 1.0
    if hii >= 1.5:
        return "improving"
    if hii >= 0.8:
        return "stable"
    return "worsening"


async def _emit_hh_history(
    db: AsyncSession,
    household_id: str,
    tenant_id: str,
    task_id: str,
    need_id: str,
    outcome_status: str,
    volunteer_id: str,
) -> None:
    """Append task_completed event to household_history ledger."""
    # Resolve user_id from volunteer_id for FK consistency
    res = await db.execute(
        text("SELECT user_id FROM volunteers WHERE volunteer_id = :vid"),
        {"vid": volunteer_id}
    )
    user_id = res.scalar() or volunteer_id # fallback if no user_id, but might fail FK
    
    await db.execute(
        text("""
            INSERT INTO household_history (
                household_id, tenant_id, event_type,
                event_payload, related_need_id, related_task_id, triggered_by
            )
            VALUES (
                :hid, :tid, 'task_completed',
                CAST(:payload AS JSONB), :need_id, :task_id, :by
            )
        """),
        {
            "hid":     household_id,
            "tid":     tenant_id,
            "payload": json.dumps({"outcome_status": outcome_status}),
            "need_id": need_id,
            "task_id": task_id,
            "by":      user_id,
        }
    )


async def _update_volunteer_outcome_rating(
    db: AsyncSession, volunteer_id: str, tenant_id: str
) -> None:
    """Rolling average of volunteer_rating from closed tasks."""
    await db.execute(
        text("""
            UPDATE volunteers v
            SET outcome_rating = (
                SELECT COALESCE(AVG(volunteer_rating), 3.5)
                FROM tasks
                WHERE assigned_volunteer_id = :vid
                  AND tenant_id             = :tid
                  AND volunteer_rating IS NOT NULL
                  AND status = 'closed'
                  AND closed_at >= NOW() - INTERVAL '90 days'
            ),
            updated_at = NOW()
            WHERE volunteer_id = :vid AND tenant_id = :tid
        """),
        {"vid": volunteer_id, "tid": tenant_id}
    )


async def _create_follow_up_need(
    db: AsyncSession,
    original_need_id: str,
    household_id: Optional[str],
    tenant_id: str,
) -> Optional[str]:
    """
    Create a follow-up NeedRecord when volunteer reports follow_up_required=True.
    Pre-verified, enters priority queue immediately.
    """
    orig = await db.execute(
        text("""
            SELECT category, subcategory, ward_id, beneficiary_count,
                   vulnerability_flags, source_type
            FROM need_records WHERE need_id = :nid AND tenant_id = :tid
        """),
        {"nid": original_need_id, "tid": tenant_id}
    )
    row = orig.fetchone()
    if not row:
        return None

    result = await db.execute(
        text("""
            INSERT INTO need_records (
                tenant_id, household_id, source_type,
                category, subcategory, ward_id,
                beneficiary_count, vulnerability_flags,
                description, status, urgency_score, severity_score
            )
            VALUES (
                :tid, :hid, 'mobile',
                :cat, :sub, :ward,
                :benef, CAST(:vuln AS JSONB),
                :desc, 'verified', 0.7, 0.6
            )
            RETURNING need_id
        """),
        {
            "tid":   tenant_id,
            "hid":   household_id,
            "cat":   row.category,
            "sub":   row.subcategory,
            "ward":  row.ward_id,
            "benef": row.beneficiary_count,
            "vuln":  json.dumps(row.vulnerability_flags or {}),
            "desc":  f"Follow-up from need {original_need_id}",
        }
    )
    new_id = str(result.fetchone().need_id)
    logger.info(f"Follow-up need created: {new_id} from {original_need_id}")
    return new_id


async def _record_feedback_event(
    db: AsyncSession,
    tenant_id: str,
    task_id: str,
    household_id: Optional[str],
    volunteer_id: str,
    need_id: str,
    outcome_status: str,
    results: dict,
) -> None:
    await db.execute(
        text("""
            INSERT INTO feedback_events (
                tenant_id, event_type, source_id,
                household_id, volunteer_id, need_id, payload
            )
            VALUES (
                :tid, 'task_completed', :source,
                :hid, :vid, :nid, CAST(:payload AS JSONB)
            )
        """),
        {
            "tid":     tenant_id,
            "source":  task_id,
            "hid":     household_id,
            "vid":     volunteer_id,
            "nid":     need_id,
            "payload": json.dumps({
                "outcome_status": outcome_status,
                **{k: str(v) for k, v in results.items()},
            }),
        }
    )