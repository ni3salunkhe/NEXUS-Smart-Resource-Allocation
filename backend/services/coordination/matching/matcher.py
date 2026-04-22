"""
Multi-Factor Volunteer Matching Engine
Stages:
  1. Hard filters  â€” PostGIS radius, active, verified, burnout < 0.80, availability
  2. Soft scoring  â€” cosine similarity on capability vectors
  3. Boosters      â€” continuity (+0.15), language (+0.10), cultural (+0.05/tag)
  4. Fatigue penalty â€” -0.10/consecutive day (last 5 days)
  5. Rank + return top 3 candidates
"""
import math
import logging
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

logger = logging.getLogger(__name__)

# â”€â”€ Booster / penalty constants â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
CONTINUITY_BOOST    = 0.15   # prior household relationship
LANGUAGE_BOOST      = 0.10   # exact language match
CULTURAL_BOOST_PER  = 0.05   # per matching cultural tag (max 3 tags)
FATIGUE_PENALTY_PER = 0.10   # per consecutive deployment day (last 5d)
MAX_FATIGUE_DAYS    = 5
BURNOUT_EXCLUDE     = 0.80   # hard exclude above this

# Skill weights for cosine similarity
SKILL_WEIGHTS: dict[str, float] = {
    "medical":      1.5,
    "legal":        1.4,
    "counselling":  1.3,
    "construction": 1.1,
    "logistics":    1.0,
    "language":     1.0,
    "transport":    0.9,
    "tech":         0.8,
    "other":        0.7,
}

# Category â†’ required skills hint
CATEGORY_SKILL_HINTS: dict[str, list[str]] = {
    "health":       ["medical", "counselling"],
    "mental_health":["counselling", "medical"],
    "legal":        ["legal"],
    "shelter":      ["construction", "logistics"],
    "food":         ["logistics", "transport"],
    "water":        ["logistics"],
    "education":    ["counselling"],
    "livelihood":   ["legal", "counselling"],
    "hygiene":      ["logistics"],
    "other":        [],
}


@dataclass
class MatchCandidate:
    volunteer_id:     str
    match_score:      float
    cosine_score:     float
    boosts_applied:   dict
    fatigue_penalty:  float
    distance_km:      float
    volunteer_data:   dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "volunteer_id":    self.volunteer_id,
            "match_score":     round(self.match_score, 4),
            "cosine_score":    round(self.cosine_score, 4),
            "boosts_applied":  self.boosts_applied,
            "fatigue_penalty": round(self.fatigue_penalty, 4),
            "distance_km":     round(self.distance_km, 2),
        }


# â”€â”€ Vector builders â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def _build_requirement_vector(
    category:            Optional[str],
    subcategory:         Optional[str],
    preferred_languages: list[str],
    cultural_tags:       list[str],
) -> dict[str, float]:
    """
    Build a requirement vector from a need's characteristics.
    Dimensions: skills (weighted), language flags, cultural flags.
    """
    vec: dict[str, float] = {}

    # Skill dimensions from category hint
    required_skills = CATEGORY_SKILL_HINTS.get(category or "other", [])
    for skill in required_skills:
        vec[f"skill:{skill}"] = SKILL_WEIGHTS.get(skill, 1.0)

    # Language dimensions
    for lang in preferred_languages:
        vec[f"lang:{lang}"] = 1.0

    # Cultural tag dimensions
    for tag in cultural_tags:
        vec[f"culture:{tag}"] = 0.8

    return vec


def _build_capability_vector(
    skills:               list[str],
    skill_proficiency:    dict,
    preferred_language:   list[str],
    cultural_context_tags:list[str],
) -> dict[str, float]:
    """
    Build a capability vector from a volunteer's profile.
    """
    vec: dict[str, float] = {}

    # Skill dimensions
    for skill in skills:
        base    = SKILL_WEIGHTS.get(skill, 0.7)
        proficiency_map = {"beginner": 0.5, "trained": 0.8, "certified": 1.0, "expert": 1.0}
        prof    = proficiency_map.get(
            str(skill_proficiency.get(skill, "trained")).lower(), 0.8
        )
        vec[f"skill:{skill}"] = base * prof

    # Language dimensions
    for lang in preferred_language:
        vec[f"lang:{lang}"] = 1.0

    # Cultural tag dimensions
    for tag in cultural_context_tags:
        vec[f"culture:{tag}"] = 0.8

    return vec


def _cosine_similarity(a: dict[str, float], b: dict[str, float]) -> float:
    """Cosine similarity between two sparse vectors."""
    if not a or not b:
        return 0.0

    keys  = set(a) | set(b)
    dot   = sum(a.get(k, 0) * b.get(k, 0) for k in keys)
    norm_a = math.sqrt(sum(v**2 for v in a.values()))
    norm_b = math.sqrt(sum(v**2 for v in b.values()))

    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# â”€â”€ Main matching entry point â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
async def find_matches(
    db: AsyncSession,
    need_id:              str,
    tenant_id:            str,
    household_id:         Optional[str],
    category:             Optional[str],
    need_latitude:        Optional[float],
    need_longitude:       Optional[float],
    preferred_languages:  list[str],
    cultural_tags:        list[str],
    radius_km:            int   = 15,
    top_n:                int   = 3,
) -> list[MatchCandidate]:
    """
    Full matching pipeline: hard filter â†’ cosine â†’ boost â†’ rank.
    Returns top_n candidates sorted by match_score DESC.
    """
    # â”€â”€ Stage 1: Hard filter + geo query â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    geo_filter = ""
    params: dict = {
        "tid":     tenant_id,
        "burnout": BURNOUT_EXCLUDE,
    }

    if need_latitude is not None and need_longitude is not None:
        geo_filter = """
            AND ST_DWithin(
                v.location_home_point::geography,
                ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography,
                :radius_m
            )
        """
        params["lat"]      = need_latitude
        params["lon"]      = need_longitude
        params["radius_m"] = radius_km * 1000

    candidate_sql = f"""
        SELECT
            v.volunteer_id,
            v.skills,
            v.skill_proficiency,
            v.preferred_language,
            v.cultural_context_tags,
            v.prior_households,
            v.burnout_risk_score,
            v.max_distance_km,
            v.last_deployed_at,
            v.outcome_rating,
            v.preferred_channel,
            v.whatsapp_number,
            v.phone_number,
            v.push_token,
            CASE
                WHEN :has_geo THEN
                    ST_Distance(
                        v.location_home_point::geography,
                        ST_SetSRID(ST_MakePoint(:lon2, :lat2), 4326)::geography
                    ) / 1000.0
                ELSE 0
            END AS distance_km
        FROM volunteers v
        WHERE
            v.tenant_id           = :tid
            AND v.active          = TRUE
            AND v.verified        = TRUE
            AND v.burnout_risk_score < :burnout
            {geo_filter}
            -- Exclude volunteers already dispatched on an active task
            AND NOT EXISTS (
                SELECT 1 FROM tasks t2
                WHERE t2.assigned_volunteer_id = v.volunteer_id
                  AND t2.tenant_id             = :tid
                  AND t2.status IN ('dispatched','accepted','in_progress')
            )
        ORDER BY distance_km ASC
        LIMIT 30
    """
    has_geo = need_latitude is not None and need_longitude is not None
    params["has_geo"] = has_geo
    params["lat2"]    = need_latitude  or 0
    params["lon2"]    = need_longitude or 0

    result = await db.execute(text(candidate_sql), params)
    rows   = result.fetchall()

    if not rows:
        logger.info(f"No candidates found for need {need_id}")
        return []

    # â”€â”€ Stage 2: Cosine similarity â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    req_vec = _build_requirement_vector(
        category, None, preferred_languages, cultural_tags
    )

    now        = datetime.now(timezone.utc)
    candidates = []

    for row in rows:
        vol = dict(row._mapping)

        cap_vec = _build_capability_vector(
            skills               = list(vol.get("skills") or []),
            skill_proficiency    = vol.get("skill_proficiency") or {},
            preferred_language   = list(vol.get("preferred_language") or []),
            cultural_context_tags= list(vol.get("cultural_context_tags") or []),
        )

        cosine = _cosine_similarity(req_vec, cap_vec)

        # â”€â”€ Stage 3: Boosters â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        boosts = {}

        # Continuity: prior household relationship
        prior = list(vol.get("prior_households") or [])
        if household_id and household_id in [str(p) for p in prior]:
            cosine += CONTINUITY_BOOST
            boosts["continuity"] = CONTINUITY_BOOST

        # Language: exact match with need's preferred language
        vol_langs = [str(l) for l in (vol.get("preferred_language") or [])]
        lang_match = any(lang in vol_langs for lang in preferred_languages)
        if lang_match and preferred_languages:
            cosine += LANGUAGE_BOOST
            boosts["language"] = LANGUAGE_BOOST

        # Cultural context tags
        vol_tags      = set(str(t) for t in (vol.get("cultural_context_tags") or []))
        need_tags     = set(cultural_tags)
        matching_tags = vol_tags & need_tags
        if matching_tags:
            boost = min(len(matching_tags), 3) * CULTURAL_BOOST_PER
            cosine += boost
            boosts["cultural"] = boost

        # â”€â”€ Stage 4: Fatigue penalty â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        last_deployed = vol.get("last_deployed_at")
        consec_days   = 0
        if last_deployed:
            if last_deployed.tzinfo is None:
                last_deployed = last_deployed.replace(tzinfo=timezone.utc)
            days_since = (now - last_deployed).days
            if days_since < MAX_FATIGUE_DAYS:
                consec_days = MAX_FATIGUE_DAYS - days_since
        fatigue_penalty = consec_days * FATIGUE_PENALTY_PER
        cosine -= fatigue_penalty

        # Clamp to [0, 1]
        final_score = max(0.0, min(1.0, cosine))

        candidates.append(MatchCandidate(
            volunteer_id    = str(vol["volunteer_id"]),
            match_score     = final_score,
            cosine_score    = _cosine_similarity(req_vec, cap_vec),
            boosts_applied  = boosts,
            fatigue_penalty = fatigue_penalty,
            distance_km     = float(vol.get("distance_km") or 0),
            volunteer_data  = {
                "preferred_channel": vol.get("preferred_channel"),
                "whatsapp_number":   vol.get("whatsapp_number"),
                "phone_number":      vol.get("phone_number"),
                "push_token":        vol.get("push_token"),
                "outcome_rating":    vol.get("outcome_rating"),
                "burnout_risk_score":vol.get("burnout_risk_score"),
            },
        ))

    # Sort by match_score DESC, then distance ASC (tiebreak)
    candidates.sort(key=lambda c: (-c.match_score, c.distance_km))
    return candidates[:top_n]
# â”€â”€ Contract Adapter â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
from sqlalchemy import text
async def match_candidates(need_id: str, db: AsyncSession) -> list:
    """Adapter for legacy validation contract."""
    row = await db.execute(
        text("SELECT tenant_id, household_id, category, ST_X(location_point::geometry) as lon, ST_Y(location_point::geometry) as lat FROM need_records WHERE need_id = :nid"),
        {"nid": need_id}
    )
    need = row.fetchone()
    if not need: return []
    matches = await find_matches(
        db=db, need_id=need_id, tenant_id=str(need.tenant_id),
        household_id=str(need.household_id) if need.household_id else None,
        category=need.category, need_latitude=need.lat, need_longitude=need.lon,
        preferred_languages=[], cultural_tags=[]
    )
    # Guard: Contract integrity check
    if not isinstance(matches, list):
        logger.critical(f"CONTRACT BREACH: match_candidates for {need_id} returned {type(matches)}")
        return []
    return matches
