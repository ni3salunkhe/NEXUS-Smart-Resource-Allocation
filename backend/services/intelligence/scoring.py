"""
Urgency Scoring Engine
Formula:
  U = w1 Ã— severity_score
    + w2 Ã— recency_factor          (logarithmic time decay)
    + w3 Ã— vulnerability_multiplier (compound from household flags)
    + w4 Ã— unmet_duration_score    (escalates every 24h unaddressed)
    + w5 Ã— source_reliability      (field worker track record)
    + w6 Ã— crisis_frequency_score  (from household history)
    - w7 Ã— resource_coverage       (penalises over-served areas)

Score range: 0.0 â€“ 1.0
Chronic floor: households with crisis_frequency > threshold never score below floor.
"""
import math
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

VULNERABILITY_FLAGS = ["elderly_head", "disabled_members", "infants", "has_child", "pregnant_woman"]

# â”€â”€ Default weight configuration â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
@dataclass
class UrgencyWeights:
    w1_severity:           float = 0.25
    w2_recency:            float = 0.15
    w3_vulnerability:      float = 0.20
    w4_unmet_duration:     float = 0.15
    w5_source_reliability: float = 0.10
    w6_crisis_frequency:   float = 0.10
    w7_coverage_penalty:   float = 0.05
    
    # Category boosts (JSONB: {food: 1.2, health: 1.5, ...})
    category_boosts:       dict  = field(default_factory=dict)
    
    # Thresholds
    chronic_threshold:     float = 3.0   # > 3 crises in 30d
    chronic_floor:         float = 0.4   # min score for chronic
    escalation_threshold:  float = 0.85  # trigger alerts
    escalation_minutes:    int   = 60    # alert if unassigned for > 60m

@dataclass
class ScoringResult:
    final_score:       float
    components:        dict
    is_chronic:        bool
    requires_alert:    bool

# â”€â”€ Internal logic â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def calculate_urgency_score(
    severity_score:      float,
    reported_at:         datetime,
    ingested_at:         datetime,
    status:              str,
    vulnerability_flags: dict,
    vulnerability_score: float,
    crisis_frequency:    float,
    source_type:         str,
    category:            str,
    weights:             Optional[UrgencyWeights] = None,
) -> ScoringResult:
    """
    Synchronous core scoring logic.
    Renamed from compute_urgency_score to avoid conflict with legacy adapter.
    """
    w = weights or UrgencyWeights()
    
    # 1. Severity (0.25)
    s_term = severity_score * w.w1_severity

    # 2. Recency (0.15)
    # Logarithmic decay: 1.0 at 0m, 0.5 at 4h, 0.1 at 24h
    now = datetime.now(timezone.utc)
    if reported_at is None:
        r_term = 1.0 * w.w2_recency
    else:
        if reported_at.tzinfo is None:
            reported_at = reported_at.replace(tzinfo=timezone.utc)
        age_hours = (now - reported_at).total_seconds() / 3600.0
        r_term = (1.0 / (1.0 + math.log1p(age_hours * 2))) * w.w2_recency

    # 3. Vulnerability (0.20)
    # Composite of explicit score + multiplier from flags
    vuln_mult = 1.0
    if vulnerability_flags.get("elderly_head"): vuln_mult += 0.1
    if vulnerability_flags.get("disabled_members"): vuln_mult += 0.1
    if vulnerability_flags.get("infants"): vuln_mult += 0.1
    v_term = min(1.0, vulnerability_score * vuln_mult) * w.w3_vulnerability

    # 4. Unmet Duration (0.15)
    # Escalates if status is still 'unverified' or 'verified' (unassigned)
    if ingested_at is None:
        u_term = 1.0 * w.w4_unmet_duration
    else:
        if ingested_at.tzinfo is None:
            ingested_at = ingested_at.replace(tzinfo=timezone.utc)
        wait_hours = (now - ingested_at).total_seconds() / 3600.0
        u_term = min(1.0, (wait_hours / 48.0)) * w.w4_unmet_duration

    # 5. Source Reliability (0.10)
    src_map = {"field_worker": 1.0, "mobile": 0.8, "whatsapp": 0.6, "sms": 0.4, "paper": 0.3}
    src_score = src_map.get(source_type, 0.5)
    src_term = src_score * w.w5_source_reliability

    # 6. Crisis Frequency (0.10)
    f_term = min(1.0, (crisis_frequency / 5.0)) * w.w6_crisis_frequency

    # 7. Resource Coverage (0.05 penalty stub)
    c_term = 0.0 # TODO: Integrate with ES density analytics

    # Final Composite
    total = s_term + r_term + v_term + u_term + src_term + f_term - c_term
    final = max(0.0, min(1.0, total))

    # Chronic protection
    is_chronic = crisis_frequency >= w.chronic_threshold
    if is_chronic:
        final = max(final, w.chronic_floor)

    return ScoringResult(
        final_score=round(final, 4),
        components={
            "severity": round(s_term, 3),
            "recency":  round(r_term, 3),
            "vulnerability": round(v_term, 3),
            "duration": round(u_term, 3),
            "source":   round(src_term, 3),
            "frequency": round(f_term, 3),
        },
        is_chronic=is_chronic,
        requires_alert=(final >= w.escalation_threshold)
    )


# â”€â”€ Legacy Adapter â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
async def compute_urgency_score(need_id: str, db: AsyncSession) -> float:
    """
    ADAPTER for legacy validation contract.
    Fetches data and calls the modern synchronous calculator.
    """
    row = await db.execute(
        text("""
            SELECT 
                severity_score, reported_at, ingested_at, status, 
                vulnerability_flags, urgency_score as last_vuln_score,
                category, source_type
            FROM need_records WHERE need_id = :nid
        """),
        {"nid": need_id}
    )
    need = row.fetchone()
    if not need:
        return 0.5

    res = calculate_urgency_score(
        severity_score=need.severity_score,
        reported_at=need.reported_at,
        ingested_at=need.ingested_at,
        status=need.status,
        vulnerability_flags=need.vulnerability_flags or {},
        vulnerability_score=need.last_vuln_score or 0.5,
        crisis_frequency=0.0, # Stub for adapter
        source_type=need.source_type,
        category=need.category or "other"
    )
    # Guard: Contract integrity check
    if not hasattr(res, 'final_score'):
        logger.critical(f"CONTRACT BREACH: compute_urgency_score for {need_id} returned invalid object")
        return 0.5
    return res.final_score


def should_escalate(
    urgency_score: float,
    ingested_at: Optional[datetime],
    status: str,
    weights: Optional[UrgencyWeights] = None,
) -> bool:
    """
    Returns True if this need requires immediate coordinator alert.
    Condition: score >= escalation_threshold AND unaddressed > escalation_minutes.
    """
    w = weights or UrgencyWeights()

    if urgency_score < w.escalation_threshold:
        return False
    if status not in ("unverified", "verified"):
        return False
    if ingested_at is None:
        return True

    now = datetime.now(timezone.utc)
    if ingested_at.tzinfo is None:
        ingested_at = ingested_at.replace(tzinfo=timezone.utc)

    minutes_old = (now - ingested_at).total_seconds() / 60.0
    return minutes_old >= w.escalation_minutes
