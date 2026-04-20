"""
Deduplication Engine
Two levels:
  1. Record-level: same household + category + within 48h + text similarity > 0.85
  2. Semantic:     embedding cosine similarity across recent needs (stub for prod)
"""
import logging
import re
import math
from dataclasses import dataclass
from typing import Optional
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

logger = logging.getLogger(__name__)

DUPLICATE_WINDOW_HOURS  = 48
SIMILARITY_THRESHOLD    = 0.75   # Jaccard on normalized word tokens
NLP_CONFIDENCE_REVIEW   = 0.75   # below this → human review queue


@dataclass
class DedupResult:
    is_duplicate:        bool
    duplicate_of:        Optional[str]   # need_id of original
    similarity_score:    float
    reason:              str


# ── Text similarity (Jaccard on word tokens) ──────────────────
def _tokenize(text: str) -> set[str]:
    """Lowercase, strip punctuation, tokenize."""
    text = text.lower()
    text = re.sub(r'[^\w\s]', ' ', text)
    tokens = set(text.split())
    # Remove short stop-words
    stopwords = {"the","a","an","is","in","at","on","of","to","and","or","for","with","this"}
    return tokens - stopwords


def _jaccard_sim(a: str, b: str) -> float:
    ta, tb = _tokenize(a), _tokenize(b)
    if not ta and not tb:
        return 0.0
    inter = len(ta & tb)
    union = len(ta | tb)
    return inter / union if union > 0 else 0.0


# ── Record-level deduplication ────────────────────────────────
async def check_duplicate(
    db: AsyncSession,
    tenant_id: str,
    household_id: Optional[str],
    category: Optional[str],
    description: Optional[str],
    ingested_at: Optional[datetime] = None,
) -> DedupResult:
    """
    Check if an incoming need is a duplicate of an existing record.
    Conditions:
      - Same tenant + same household + same category
      - Reported within 48-hour window
      - Description similarity > SIMILARITY_THRESHOLD
    """
    if not household_id or not category or not description:
        return DedupResult(False, None, 0.0, "insufficient_data")

    window_start = (ingested_at or datetime.now(timezone.utc)) - timedelta(hours=DUPLICATE_WINDOW_HOURS)

    # Fetch recent needs for same household + category
    result = await db.execute(
        text("""
            SELECT need_id, description, ingested_at
            FROM need_records
            WHERE tenant_id    = :tid
              AND household_id = :hh_id
              AND category     = :cat
              AND status       NOT IN ('closed', 'duplicate')
              AND ingested_at  >= :window_start
            ORDER BY ingested_at DESC
            LIMIT 10
        """),
        {
            "tid":          tenant_id,
            "hh_id":        household_id,
            "cat":          category,
            "window_start": window_start,
        }
    )
    rows = result.fetchall()

    if not rows:
        return DedupResult(False, None, 0.0, "no_recent_matches")

    # Find highest-similarity match
    best_score   = 0.0
    best_need_id = None

    for row in rows:
        if not row.description:
            continue
        sim = _jaccard_sim(description, row.description)
        if sim > best_score:
            best_score   = sim
            best_need_id = str(row.need_id)

    if best_score >= SIMILARITY_THRESHOLD:
        logger.info(
            f"DUPLICATE detected: sim={best_score:.3f} → {best_need_id}"
        )
        return DedupResult(
            is_duplicate=True,
            duplicate_of=best_need_id,
            similarity_score=best_score,
            reason=f"same_household_category_recent_similar_{best_score:.2f}",
        )

    return DedupResult(False, None, best_score, "below_threshold")


# ── Review queue routing ──────────────────────────────────────
async def route_to_review_queue(
    db: AsyncSession,
    tenant_id: str,
    raw_id: Optional[str],
    need_id: Optional[str],
    review_type: str,
    review_data: dict,
    priority: int = 5,
) -> str:
    """Insert a record into review_queue. Returns review_id."""
    import json
    result = await db.execute(
        text("""
            INSERT INTO review_queue
                (tenant_id, raw_id, need_id, review_type, review_data, priority)
            VALUES
                (:tid, :raw_id, :need_id, :rtype, CAST(:data AS JSONB), :priority)
            RETURNING review_id
        """),
        {
            "tid":      tenant_id,
            "raw_id":   raw_id,
            "need_id":  need_id,
            "rtype":    review_type,
            "data":     json.dumps(review_data),
            "priority": priority,
        }
    )
    row = result.fetchone()
    return str(row.review_id)


def should_route_to_review(nlp_confidence: float, review_type_hints: list[str]) -> bool:
    """Return True if this record needs human review."""
    if nlp_confidence < NLP_CONFIDENCE_REVIEW:
        return True
    return len(review_type_hints) > 0


def compute_review_priority(
    nlp_confidence: float,
    severity_score: float,
    has_household: bool,
) -> int:
    """
    Priority 1 (highest) – 10 (lowest).
    High severity + low confidence = highest priority for review.
    """
    score = (1 - nlp_confidence) * 0.5 + severity_score * 0.5
    if not has_household:
        score += 0.2

    if score >= 0.8:
        return 1
    if score >= 0.6:
        return 2
    if score >= 0.4:
        return 3
    if score >= 0.2:
        return 5
    return 8