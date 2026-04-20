"""
Geocoding Processor
Pipeline: location text → (lat, lon, ward_id, confidence)
Stage 1: Cache lookup (PostgreSQL geocoding_cache)
Stage 2: Custom landmark table (informal names → coordinates)
Stage 3: Google Maps Geocoding API
Stage 4: Fallback to ward centroid if available
"""
import logging
import os
from dataclasses import dataclass
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

logger = logging.getLogger(__name__)

try:
    import googlemaps
    GMAPS_AVAILABLE = True
except ImportError:
    GMAPS_AVAILABLE = False
    logger.warning("googlemaps not installed — Google Maps geocoding disabled")


@dataclass
class GeocodeResult:
    latitude:   Optional[float]
    longitude:  Optional[float]
    ward_id:    Optional[str]
    confidence: float          # 0.0 – 1.0
    resolved_by: str           # "cache" | "custom" | "google" | "ward_centroid" | "none"
    formatted_address: Optional[str] = None


# ── Custom landmark table (seed data) ────────────────────────
# In production: this is a DB table managed by field coordinators.
# Format: {normalized_landmark: (lat, lon, ward_id)}
LANDMARK_TABLE: dict[str, tuple[float, float, str]] = {
    # Mumbai examples
    "dharavi":              (19.0450, 72.8527, "K-East"),
    "kurla":                (19.0728, 72.8826, "L"),
    "govandi":              (19.0565, 72.9267, "M-East"),
    "mankhurd":             (19.0519, 72.9302, "M-East"),
    "chembur":              (19.0621, 72.8997, "M-East"),
    "bandra east":          (19.0542, 72.8434, "H-East"),
    "andheri east":         (19.1136, 72.8697, "K-West"),
    "malad":                (19.1863, 72.8484, "P-North"),
    "borivali":             (19.2307, 72.8567, "R-North"),
    # Generic landmark hints
    "near dargah":          None,
    "near masjid":          None,
    "near church":          None,
    "near temple":          None,
    "near pump":            None,
}


def _normalize_location_text(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    import re
    text = text.lower()
    text = re.sub(r'[^\w\s]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _lookup_custom_landmarks(location_text: str) -> Optional[GeocodeResult]:
    """Check custom landmark table for known informal location names."""
    normalized = _normalize_location_text(location_text)
    for landmark, coords in LANDMARK_TABLE.items():
        if landmark in normalized:
            if coords:
                lat, lon, ward = coords
                return GeocodeResult(
                    latitude=lat,
                    longitude=lon,
                    ward_id=ward,
                    confidence=0.75,
                    resolved_by="custom",
                    formatted_address=landmark,
                )
    return None


async def _lookup_cache(
    db: AsyncSession,
    location_text: str,
) -> Optional[GeocodeResult]:
    """Check geocoding_cache table."""
    normalized = _normalize_location_text(location_text)
    result = await db.execute(
        text("""
            SELECT latitude, longitude, ward_id, confidence, resolved_by, input_text
            FROM geocoding_cache
            WHERE input_text = :txt
        """),
        {"txt": normalized}
    )
    row = result.fetchone()
    if not row or row.latitude is None:
        return None

    # Bump hit count
    await db.execute(
        text("UPDATE geocoding_cache SET hit_count = hit_count + 1, last_used_at = NOW() WHERE input_text = :txt"),
        {"txt": normalized}
    )

    return GeocodeResult(
        latitude=row.latitude,
        longitude=row.longitude,
        ward_id=row.ward_id,
        confidence=row.confidence,
        resolved_by="cache",
    )


async def _save_to_cache(
    db: AsyncSession,
    location_text: str,
    result: GeocodeResult,
) -> None:
    normalized = _normalize_location_text(location_text)
    await db.execute(
        text("""
            INSERT INTO geocoding_cache
                (input_text, latitude, longitude, ward_id, confidence, resolved_by)
            VALUES (:txt, :lat, :lon, :ward, :conf, :by)
            ON CONFLICT (input_text) DO UPDATE
            SET latitude = EXCLUDED.latitude,
                longitude = EXCLUDED.longitude,
                confidence = EXCLUDED.confidence,
                hit_count = geocoding_cache.hit_count + 1,
                last_used_at = NOW()
        """),
        {
            "txt":  normalized,
            "lat":  result.latitude,
            "lon":  result.longitude,
            "ward": result.ward_id,
            "conf": result.confidence,
            "by":   result.resolved_by,
        }
    )


def _geocode_via_google(
    location_text: str,
    region_hint: str = "IN",
) -> Optional[GeocodeResult]:
    """Google Maps Geocoding API."""
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not api_key or not GMAPS_AVAILABLE:
        return None

    try:
        gmaps = googlemaps.Client(key=api_key)
        geocode_result = gmaps.geocode(
            location_text,
            region=region_hint,
            components={"country": "IN"},
        )

        if not geocode_result:
            return None

        best = geocode_result[0]
        loc  = best["geometry"]["location"]

        # Extract ward/administrative area
        ward_id = None
        for comp in best.get("address_components", []):
            if "sublocality" in comp["types"] or "sublocality_level_1" in comp["types"]:
                ward_id = comp["long_name"]
                break

        # Confidence by location_type
        loc_type_conf = {
            "ROOFTOP": 0.95,
            "RANGE_INTERPOLATED": 0.80,
            "GEOMETRIC_CENTER": 0.70,
            "APPROXIMATE": 0.55,
        }
        loc_type = best["geometry"].get("location_type", "APPROXIMATE")
        confidence = loc_type_conf.get(loc_type, 0.50)

        return GeocodeResult(
            latitude=loc["lat"],
            longitude=loc["lng"],
            ward_id=ward_id,
            confidence=confidence,
            resolved_by="google",
            formatted_address=best.get("formatted_address"),
        )
    except Exception as e:
        logger.error(f"Google Maps geocoding failed: {e}")
        return None


# ── Main geocoding entry point ────────────────────────────────
async def geocode_location(
    location_text: str,
    db: Optional[AsyncSession] = None,
    region_hint: str = "IN",
) -> GeocodeResult:
    """
    Full geocoding pipeline with cache + fallback chain.
    location_text: informal description, landmark, or address string
    """
    if not location_text or not location_text.strip():
        return GeocodeResult(None, None, None, 0.0, "none")

    # Stage 1: DB cache (skip if no DB session)
    if db:
        cached = await _lookup_cache(db, location_text)
        if cached:
            logger.debug(f"Geocode cache hit: '{location_text[:40]}'")
            return cached

    # Stage 2: Custom landmark table
    custom = _lookup_custom_landmarks(location_text)
    if custom:
        if db:
            await _save_to_cache(db, location_text, custom)
        return custom

    # Stage 3: Google Maps API
    google = _geocode_via_google(location_text, region_hint)
    if google and google.confidence >= 0.5:
        if db:
            await _save_to_cache(db, location_text, google)
        return google

    # Stage 4: No result — return null with zero confidence
    logger.warning(f"Geocoding failed for: '{location_text[:60]}'")
    return GeocodeResult(None, None, None, 0.0, "none")


async def geocode_all_locations(
    location_entities: list,
    db: Optional[AsyncSession] = None,
) -> GeocodeResult:
    """
    Geocode a list of LocationEntity objects (from NLP),
    return the highest-confidence result.
    """
    best: Optional[GeocodeResult] = None

    for loc_entity in location_entities:
        text_to_try = loc_entity.text
        result = await geocode_location(text_to_try, db)
        if best is None or result.confidence > best.confidence:
            best = result
        if best and best.confidence >= 0.80:
            break  # good enough

    return best or GeocodeResult(None, None, None, 0.0, "none")