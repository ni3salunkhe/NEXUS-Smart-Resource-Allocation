"""
Identity Resolution Engine — 4-Stage Cascade
Stage 1: Exact signal match     (confidence >= 0.95 → AUTO-LINK)
Stage 2: Geospatial cluster     (PostGIS 50m radius → candidate list)
Stage 3: Fuzzy attribute match  (Jaccard landmarks + vulnerability cosine + text embedding)
Stage 4: Composite scoring      (weighted ensemble → threshold decision)
"""
import logging
import math
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from .schemas import (
    IdentityResolutionRequest, ResolutionResult, CandidateMatch, HouseholdResponse
)

logger = logging.getLogger(__name__)

# ── Thresholds ────────────────────────────────────────────────
AUTO_LINK_THRESHOLD    = 0.80   # >= auto-link
REVIEW_THRESHOLD       = 0.55   # 0.55-0.79 → coordinator review
# < 0.55 → new household

# Stage weights in composite
W_GEO      = 0.30
W_LANDMARK = 0.25
W_VULN     = 0.20
W_TEXT     = 0.15
W_SIZE     = 0.10


def _jaccard(a: list, b: list) -> float:
    """Jaccard similarity between two tag lists."""
    if not a and not b:
        return 0.0
    sa, sb = set(a), set(b)
    intersection = len(sa & sb)
    union = len(sa | sb)
    return intersection / union if union > 0 else 0.0


def _vulnerability_cosine(a: dict, b: dict) -> float:
    """Cosine similarity between two vulnerability flag dicts (binary vectors)."""
    keys = list(set(a) | set(b))
    if not keys:
        return 0.0
    va = [float(a.get(k, False)) for k in keys]
    vb = [float(b.get(k, False)) for k in keys]
    dot = sum(x * y for x, y in zip(va, vb))
    norm_a = math.sqrt(sum(x**2 for x in va))
    norm_b = math.sqrt(sum(x**2 for x in vb))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _family_size_score(req_size: Optional[int], hh_size: int) -> float:
    """How close is the reported family size to the stored one."""
    if req_size is None:
        return 0.5  # neutral
    diff = abs(req_size - hh_size)
    if diff == 0:
        return 1.0
    if diff <= 1:
        return 0.8
    if diff <= 2:
        return 0.5
    return 0.1


def _distance_score(distance_m: Optional[float]) -> float:
    """Convert metres to a 0-1 score. 0m=1.0, 50m=0.5, 100m=0.0."""
    if distance_m is None:
        return 0.0
    return max(0.0, 1.0 - (distance_m / 100.0))


async def _stage1_exact(
    db: AsyncSession,
    req: IdentityResolutionRequest,
    tenant_id: str,
) -> Optional[CandidateMatch]:
    """Phone number or known household_id → instant link."""

    # Known ID shortcut
    if req.known_household_id:
        result = await db.execute(
            text("SELECT household_id, total_members FROM households WHERE household_id = :hid AND tenant_id = :tid"),
            {"hid": str(req.known_household_id), "tid": tenant_id}
        )
        row = result.fetchone()
        if row:
            return CandidateMatch(
                household_id=row.household_id,
                confidence=0.98,
                match_stage=1,
                match_signals={"known_household_id": True},
            )

    # Phone number lookup via PII vault reference
    # In production: query pii_vault service. Here: stub returning None.
    # Uncomment when PII vault is live:
    # if req.phone_number:
    #     pii_ref = await pii_vault.resolve_phone(req.phone_number)
    #     if pii_ref:
    #         member_row = await db.execute(...)

    return None


async def _stage2_geospatial(
    db: AsyncSession,
    req: IdentityResolutionRequest,
    tenant_id: str,
    radius_m: int = 50,
) -> list[dict]:
    """PostGIS radius query → candidate rows within radius_m metres."""

    if req.latitude is None or req.longitude is None:
        return []

    result = await db.execute(
        text("""
            SELECT
                household_id,
                total_members,
                vulnerability_flags,
                landmark_tags,
                location_description,
                dwelling_type,
                vulnerability_score,
                ST_Distance(
                    location_geo::geography,
                    ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography
                ) AS distance_m
            FROM households
            WHERE
                tenant_id = :tid
                AND status = 'active'
                AND location_geo IS NOT NULL
                AND ST_DWithin(
                    location_geo::geography,
                    ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography,
                    :radius
                )
            ORDER BY distance_m ASC
            LIMIT 10
        """),
        {
            "lat": req.latitude,
            "lon": req.longitude,
            "tid": tenant_id,
            "radius": radius_m,
        }
    )
    return [dict(r._mapping) for r in result.fetchall()]


def _stage3_fuzzy(req: IdentityResolutionRequest, candidate: dict) -> dict:
    """Compute fuzzy attribute scores for a single candidate."""
    scores = {}

    # Landmark Jaccard
    scores["landmark"] = _jaccard(
        req.landmark_tags,
        candidate.get("landmark_tags") or []
    )

    # Vulnerability cosine
    scores["vulnerability"] = _vulnerability_cosine(
        req.vulnerability_flags,
        candidate.get("vulnerability_flags") or {}
    )

    # Family size
    scores["family_size"] = _family_size_score(
        req.family_size,
        candidate.get("total_members", 0)
    )

    # Dwelling type match
    req_dwell = req.dwelling_type
    cand_dwell = candidate.get("dwelling_type")
    if req_dwell and cand_dwell:
        scores["dwelling_type"] = 1.0 if req_dwell == cand_dwell else 0.2
    else:
        scores["dwelling_type"] = 0.5  # neutral if unknown

    # Text similarity: simple Jaccard on word tokens (sentence-BERT in prod)
    if req.description_text and candidate.get("location_description"):
        req_words  = set(req.description_text.lower().split())
        cand_words = set(candidate["location_description"].lower().split())
        scores["text"] = _jaccard(list(req_words), list(cand_words))
    else:
        scores["text"] = 0.0

    return scores


def _stage4_composite(
    geo_score:   float,
    fuzzy_scores: dict,
) -> float:
    """Weighted ensemble → final confidence score."""
    return (
        W_GEO      * geo_score +
        W_LANDMARK * fuzzy_scores.get("landmark", 0) +
        W_VULN     * fuzzy_scores.get("vulnerability", 0) +
        W_TEXT     * fuzzy_scores.get("text", 0) +
        W_SIZE     * fuzzy_scores.get("family_size", 0)
    )


async def resolve_household(
    db: AsyncSession,
    req: IdentityResolutionRequest,
    tenant_id: str,
) -> ResolutionResult:
    """
    Entry point for the 4-stage identity resolution cascade.
    Returns: ResolutionResult with status, household_id, confidence, candidates.
    """
    resolution_id = str(uuid4())

    # ── Stage 1: Exact match ──────────────────────────────────
    exact = await _stage1_exact(db, req, tenant_id)
    if exact and exact.confidence >= 0.95:
        logger.info(f"[Resolution {resolution_id}] Stage 1 AUTO-LINK → {exact.household_id}")
        return ResolutionResult(
            status="auto_linked",
            household_id=exact.household_id,
            confidence=exact.confidence,
            candidates=[exact],
            resolution_id=resolution_id,
        )

    # ── Stage 2: Geospatial cluster ───────────────────────────
    geo_candidates = await _stage2_geospatial(db, req, tenant_id)

    if not geo_candidates:
        logger.info(f"[Resolution {resolution_id}] No geo candidates → new household")
        return ResolutionResult(
            status="new_household",
            household_id=None,
            confidence=0.0,
            candidates=[],
            resolution_id=resolution_id,
        )

    # ── Stage 3 + 4: Fuzzy + Composite ────────────────────────
    scored: list[CandidateMatch] = []

    for cand in geo_candidates:
        dist_m = float(cand["distance_m"])
        geo_s  = _distance_score(dist_m)
        fuzzy  = _stage3_fuzzy(req, cand)
        comp   = _stage4_composite(geo_s, fuzzy)

        signals = {
            "geo_distance_m":  round(dist_m, 1),
            "geo_score":       round(geo_s, 3),
            "landmark_score":  round(fuzzy.get("landmark", 0), 3),
            "vuln_score":      round(fuzzy.get("vulnerability", 0), 3),
            "text_score":      round(fuzzy.get("text", 0), 3),
            "family_size_score": round(fuzzy.get("family_size", 0), 3),
            "composite":       round(comp, 3),
        }

        scored.append(CandidateMatch(
            household_id=cand["household_id"],
            confidence=comp,
            match_stage=4,
            match_signals=signals,
            distance_m=dist_m,
        ))

    # Sort by composite descending
    scored.sort(key=lambda c: c.confidence, reverse=True)
    top = scored[0]

    if top.confidence >= AUTO_LINK_THRESHOLD:
        logger.info(
            f"[Resolution {resolution_id}] Stage 4 AUTO-LINK conf={top.confidence:.3f} "
            f"→ {top.household_id}"
        )
        return ResolutionResult(
            status="auto_linked",
            household_id=top.household_id,
            confidence=top.confidence,
            candidates=scored[:3],
            resolution_id=resolution_id,
        )

    if top.confidence >= REVIEW_THRESHOLD:
        logger.info(
            f"[Resolution {resolution_id}] REVIEW REQUIRED conf={top.confidence:.3f}"
        )
        return ResolutionResult(
            status="review_required",
            household_id=None,
            confidence=top.confidence,
            candidates=scored[:3],
            resolution_id=resolution_id,
        )

    logger.info(
        f"[Resolution {resolution_id}] NEW HOUSEHOLD conf={top.confidence:.3f} (below threshold)"
    )
    return ResolutionResult(
        status="new_household",
        household_id=None,
        confidence=top.confidence,
        candidates=scored[:3],
        resolution_id=resolution_id,
    )