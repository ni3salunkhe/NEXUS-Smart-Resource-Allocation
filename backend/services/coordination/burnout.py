"""
Burnout Risk Scoring Engine
Formula:
  burnout = 0.35 × deployment_frequency_7d   (normalised 0→1)
           + 0.25 × deployment_frequency_30d  (normalised to monthly baseline)
           + 0.20 × consecutive_days_deployed  (0→1, resets on any rest day)
           + 0.20 × (1 − avg_outcome_rating/5) (poor outcomes signal overextension)

Thresholds:
  >= 0.80  → excluded from auto-dispatch, coordinator alert, check-in prompt
  >= 0.65  → soft warning in coordinator UI, deployment allowed
  >= 0.50  → 'moderate load' label in volunteer list
  decay:   -0.15 per rest day
"""
import logging
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

logger = logging.getLogger(__name__)

# ── Weights ───────────────────────────────────────────────────
W_FREQ_7D   = 0.35
W_FREQ_30D  = 0.25
W_CONSEC    = 0.20
W_OUTCOME   = 0.20
DECAY_PER_REST_DAY = 0.15

# Normalisation baselines
MAX_DEPLOYS_7D  = 7   # 1/day = 1.0
MAX_DEPLOYS_30D = 20  # sustainable monthly load
MAX_CONSEC_DAYS = 7   # 7 consecutive = 1.0

# Thresholds
EXCLUDED_THRESHOLD = 0.80
WARNING_THRESHOLD  = 0.65
MODERATE_THRESHOLD = 0.50


@dataclass
class BurnoutResult:
    score:                float
    deployments_7d:       int
    deployments_30d:      int
    consecutive_days:     int
    avg_outcome_rating:   float
    is_excluded:          bool    # >= 0.80
    is_warning:           bool    # >= 0.65
    is_moderate:          bool    # >= 0.50
    label:                str


def _compute_score(
    deployments_7d:     int,
    deployments_30d:    int,
    consecutive_days:   int,
    avg_outcome_rating: float,
) -> float:
    t1 = min(1.0, deployments_7d  / MAX_DEPLOYS_7D)
    t2 = min(1.0, deployments_30d / MAX_DEPLOYS_30D)
    t3 = min(1.0, consecutive_days / MAX_CONSEC_DAYS)
    t4 = max(0.0, 1.0 - (avg_outcome_rating / 5.0))

    return (
        W_FREQ_7D  * t1 +
        W_FREQ_30D * t2 +
        W_CONSEC   * t3 +
        W_OUTCOME  * t4
    )


def _label(score: float) -> str:
    if score >= EXCLUDED_THRESHOLD:
        return "critical"
    if score >= WARNING_THRESHOLD:
        return "warning"
    if score >= MODERATE_THRESHOLD:
        return "moderate"
    return "healthy"


async def compute_volunteer_burnout(
    db: AsyncSession,
    volunteer_id: str,
    tenant_id: str,
) -> BurnoutResult:
    """
    Compute burnout risk for one volunteer.
    Reads task history. Persists to volunteer_burnout_log.
    Updates volunteers.burnout_risk_score.
    """
    now = datetime.now(timezone.utc)

    # Deployments in last 7d and 30d
    result = await db.execute(
        text("""
            SELECT
                COUNT(*) FILTER (WHERE t.completed_at >= NOW() - INTERVAL '7 days')  AS d7,
                COUNT(*) FILTER (WHERE t.completed_at >= NOW() - INTERVAL '30 days') AS d30,
                AVG(t.volunteer_rating) FILTER (WHERE t.volunteer_rating IS NOT NULL) AS avg_rating
            FROM tasks t
            WHERE t.assigned_volunteer_id = :vid
              AND t.tenant_id             = :tid
              AND t.status                = 'completed'
        """),
        {"vid": volunteer_id, "tid": tenant_id}
    )
    row = result.fetchone()
    d7          = int(row.d7  or 0)
    d30         = int(row.d30 or 0)
    avg_rating  = float(row.avg_rating or 3.5)  # neutral default

    # Consecutive deployment days (look back up to 30 days)
    consec_result = await db.execute(
        text("""
            SELECT DATE(completed_at AT TIME ZONE 'UTC') AS deploy_date
            FROM tasks
            WHERE assigned_volunteer_id = :vid
              AND tenant_id             = :tid
              AND status                = 'completed'
              AND completed_at         >= NOW() - INTERVAL '30 days'
            GROUP BY deploy_date
            ORDER BY deploy_date DESC
        """),
        {"vid": volunteer_id, "tid": tenant_id}
    )
    deploy_dates = [row.deploy_date for row in consec_result.fetchall()]
    consecutive  = _count_consecutive(deploy_dates, now.date())

    score = _compute_score(d7, d30, consecutive, avg_rating)
    score = max(0.0, min(1.0, score))

    label       = _label(score)
    is_excluded = score >= EXCLUDED_THRESHOLD
    is_warning  = score >= WARNING_THRESHOLD
    is_moderate = score >= MODERATE_THRESHOLD

    # Persist to log
    await db.execute(
        text("""
            INSERT INTO volunteer_burnout_log
                (volunteer_id, tenant_id, burnout_risk_score,
                 deployments_7d, deployments_30d, consecutive_days, avg_outcome_rating,
                 alert_sent)
            VALUES (:vid, :tid, :score, :d7, :d30, :consec, :rating, :alert)
        """),
        {
            "vid":    volunteer_id,
            "tid":    tenant_id,
            "score":  score,
            "d7":     d7,
            "d30":    d30,
            "consec": consecutive,
            "rating": avg_rating,
            "alert":  is_excluded,
        }
    )

    # Update volunteer record
    await db.execute(
        text("""
            UPDATE volunteers
            SET burnout_risk_score = :score, updated_at = NOW()
            WHERE volunteer_id = :vid AND tenant_id = :tid
        """),
        {"score": score, "vid": volunteer_id, "tid": tenant_id}
    )

    return BurnoutResult(
        score=score,
        deployments_7d=d7,
        deployments_30d=d30,
        consecutive_days=consecutive,
        avg_outcome_rating=avg_rating,
        is_excluded=is_excluded,
        is_warning=is_warning,
        is_moderate=is_moderate,
        label=label,
    )


def _count_consecutive(deploy_dates: list, today) -> int:
    """Count consecutive deployment days ending at or before today."""
    if not deploy_dates:
        return 0

    from datetime import date
    consecutive = 0
    check_date  = today

    for d in deploy_dates:
        if isinstance(d, str):
            d = date.fromisoformat(d)
        if d == check_date:
            consecutive += 1
            check_date  = check_date - timedelta(days=1)
        elif d < check_date:
            break   # gap found — stop

    return consecutive


def apply_rest_day_decay(current_score: float, rest_days: int) -> float:
    """Score decays by DECAY_PER_REST_DAY for each day without a deployment."""
    return max(0.0, current_score - (DECAY_PER_REST_DAY * rest_days))