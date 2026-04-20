"""
Ingestion Pipeline Orchestrator
Sequence for each raw input:
  1. Save raw to S3 (or local in dev)
  2. OCR (if image/audio)
  3. NLP extraction
  4. Identity resolution → household_id
  5. Geocoding
  6. Deduplication check
  7. Write NeedRecord
  8. Route to review queue if needed
  9. Emit Kafka events
"""
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from .processors.nlp          import extract_nlp, NLPOutput
from .processors.geocoding    import geocode_all_locations, GeocodeResult
from .processors.deduplication import (
    check_duplicate, route_to_review_queue,
    should_route_to_review, compute_review_priority,
)

logger = logging.getLogger(__name__)

NLP_CONFIDENCE_REVIEW = 0.75   # below this → human review


@dataclass
class IngestionPayload:
    """Canonical input to the pipeline regardless of source channel."""
    source_type:     str            # "paper"|"whatsapp"|"mobile"|"sms"|"csv"|"webhook"
    tenant_id:       str
    submitted_by:    Optional[str]  # user_id
    raw_text:        Optional[str]  = None
    ocr_text:        Optional[str]  = None    # pre-extracted OCR (from image processor)
    s3_key:          Optional[str]  = None
    raw_metadata:    dict           = None
    reported_at:     Optional[datetime] = None
    # Pre-filled for mobile/structured channels
    prefilled_category:    Optional[str] = None
    prefilled_location:    Optional[str] = None
    prefilled_beneficiary: Optional[int] = None
    known_household_id:    Optional[str] = None
    correlation_id:        Optional[str] = None


@dataclass
class PipelineResult:
    success:           bool
    need_id:           Optional[str]
    raw_id:            Optional[str]
    household_id:      Optional[str]
    household_status:  Optional[str]   # "auto_linked"|"review_required"|"new_household"
    is_duplicate:      bool
    duplicate_of:      Optional[str]
    routed_to_review:  bool
    review_id:         Optional[str]
    nlp_confidence:    float
    error:             Optional[str] = None


class IngestionPipeline:

    async def run(
        self,
        payload: IngestionPayload,
        db: AsyncSession,
    ) -> PipelineResult:
        raw_id = None
        try:
            raw_id = await self._save_raw(db, payload)
            return await self._process(db, payload, raw_id)
        except Exception as e:
            logger.error(f"Pipeline error raw_id={raw_id}: {e}", exc_info=True)
            if raw_id:
                await db.execute(
                    text("UPDATE ingestion_raw SET status='failed', processing_error=:err WHERE raw_id=:rid"),
                    {"err": str(e)[:500], "rid": raw_id}
                )
            return PipelineResult(
                success=False, need_id=None, raw_id=raw_id,
                household_id=None, household_status=None,
                is_duplicate=False, duplicate_of=None,
                routed_to_review=False, review_id=None,
                nlp_confidence=0.0, error=str(e),
            )

    async def _save_raw(self, db: AsyncSession, payload: IngestionPayload) -> str:
        """Stage 0: persist raw record."""
        result = await db.execute(
            text("""
                INSERT INTO ingestion_raw
                    (tenant_id, source_type, s3_key, raw_text, raw_metadata,
                     submitted_by, status, correlation_id)
                VALUES
                    (:tid, :stype, :s3, :raw_text, CAST(:meta AS JSONB),
                     :by, 'processing', :corr)
                RETURNING raw_id
            """),
            {
                "tid":      payload.tenant_id,
                "stype":    payload.source_type,
                "s3":       payload.s3_key,
                "raw_text": payload.raw_text or payload.ocr_text,
                "meta":     json.dumps(payload.raw_metadata or {}),
                "by":       payload.submitted_by,
                "corr":     payload.correlation_id or str(uuid.uuid4()),
            }
        )
        return str(result.fetchone().raw_id)

    async def _process(
        self,
        db: AsyncSession,
        payload: IngestionPayload,
        raw_id: str,
    ) -> PipelineResult:
        # ── Step 1: NLP extraction ────────────────────────────
        text_to_process = payload.ocr_text or payload.raw_text or ""
        nlp: NLPOutput = extract_nlp(text_to_process)

        # Override with pre-filled fields from structured channels (mobile forms)
        if payload.prefilled_category:
            nlp.category   = payload.prefilled_category
            nlp.confidence = max(nlp.confidence, 0.85)  # structured input is reliable

        if payload.prefilled_beneficiary:
            nlp.beneficiary_count = payload.prefilled_beneficiary

        # ── Step 2: Geocoding ─────────────────────────────────
        geo: GeocodeResult
        if payload.prefilled_location:
            from .processors.geocoding import geocode_location
            geo = await geocode_location(payload.prefilled_location, db)
        elif nlp.locations:
            geo = await geocode_all_locations(nlp.locations, db)
        else:
            from .processors.geocoding import GeocodeResult as GR
            geo = GR(None, None, None, 0.0, "none")

        # ── Step 3: Household identity resolution ─────────────
        household_id     = payload.known_household_id
        household_status = "known" if household_id else None

        if not household_id:
            from services.registry.identity_resolution import (
                resolve_household, IdentityResolutionRequest
            )
            ir_req = _build_ir_request(payload, nlp, geo)
            ir_req.tenant_id = payload.tenant_id
            resolution = await resolve_household(db, ir_req, payload.tenant_id)
            household_status = resolution.status
            household_id     = str(resolution.household_id) if resolution.household_id else None

        # ── Step 4: Deduplication ─────────────────────────────
        dedup = await check_duplicate(
            db,
            tenant_id    = payload.tenant_id,
            household_id = household_id,
            category     = nlp.category,
            description  = nlp.description_normalized or text_to_process[:500],
            ingested_at  = datetime.now(timezone.utc),
        )

        if dedup.is_duplicate:
            await db.execute(
                text("UPDATE ingestion_raw SET status='duplicate' WHERE raw_id=:rid"),
                {"rid": raw_id}
            )
            return PipelineResult(
                success=True, need_id=None, raw_id=raw_id,
                household_id=household_id, household_status=household_status,
                is_duplicate=True, duplicate_of=dedup.duplicate_of,
                routed_to_review=False, review_id=None,
                nlp_confidence=nlp.confidence,
            )

        # ── Step 5: Write NeedRecord ──────────────────────────
        need_status = "verified" if nlp.confidence >= NLP_CONFIDENCE_REVIEW else "unverified"
        loc_wkt = (
            f"ST_SetSRID(ST_MakePoint({geo.longitude},{geo.latitude}),4326)::geography"
            if geo.latitude is not None else "NULL"
        )

        need_result = await db.execute(
            text(f"""
                INSERT INTO need_records (
                    tenant_id, household_id, raw_id, source_type, s3_raw_ref,
                    reported_by, reported_at, ingested_at,
                    location_point, ward_id,
                    category, subcategory,
                    description, description_original, language_detected,
                    severity_score, urgency_score,
                    beneficiary_count, vulnerability_flags,
                    nlp_confidence, nlp_entities,
                    geocoding_confidence, household_resolution,
                    status
                )
                VALUES (
                    :tid, :hh_id, :raw_id, :stype, :s3,
                    :by, :rep_at, NOW(),
                    {loc_wkt}, :ward,
                    :cat, :subcat,
                    :desc, :desc_orig, :lang,
                    :sev, :sev,
                    :benef, CAST(:vuln AS JSONB),
                    :nlp_conf, CAST(:entities AS JSONB),
                    :geo_conf, :hh_status,
                    :status
                )
                RETURNING need_id
            """),
            {
                "tid":      payload.tenant_id,
                "hh_id":    household_id,
                "raw_id":   raw_id,
                "stype":    payload.source_type,
                "s3":       payload.s3_key,
                "by":       payload.submitted_by,
                "rep_at":   payload.reported_at or datetime.now(timezone.utc),
                "ward":     geo.ward_id,
                "cat":      nlp.category,
                "subcat":   nlp.subcategory,
                "desc":     nlp.description_normalized or text_to_process[:1000],
                "desc_orig":payload.raw_text or text_to_process[:1000],
                "lang":     nlp.language_detected,
                "sev":      nlp.severity_score,
                "benef":    nlp.beneficiary_count,
                "vuln":     json.dumps(nlp.vulnerability_flags),
                "nlp_conf": nlp.confidence,
                "entities": json.dumps(nlp.entities_raw),
                "geo_conf": geo.confidence,
                "hh_status":household_status,
                "status":   need_status,
            }
        )
        need_id = str(need_result.fetchone().need_id)

        # ── Step 6: Update raw record ─────────────────────────
        await db.execute(
            text("""
                UPDATE ingestion_raw
                SET status='processed', processed_at=NOW(),
                    ocr_text=:ocr, nlp_output=CAST(:nlp AS JSONB)
                WHERE raw_id=:rid
            """),
            {
                "rid": raw_id,
                "ocr": payload.ocr_text,
                "nlp": json.dumps({
                    "category":   nlp.category,
                    "confidence": nlp.confidence,
                    "severity":   nlp.severity_score,
                }),
            }
        )

        # ── Step 7: Route to review queue if needed ───────────
        review_hints = []
        if household_status == "review_required":
            review_hints.append("household_resolution")
        if nlp.confidence < NLP_CONFIDENCE_REVIEW:
            review_hints.append("low_nlp_confidence")

        review_id = None
        if should_route_to_review(nlp.confidence, review_hints):
            priority = compute_review_priority(
                nlp_confidence=nlp.confidence,
                severity_score=nlp.severity_score,
                has_household=household_id is not None,
            )
            review_id = await route_to_review_queue(
                db,
                tenant_id   = payload.tenant_id,
                raw_id      = raw_id,
                need_id     = need_id,
                review_type = review_hints[0] if review_hints else "low_nlp_confidence",
                review_data = {
                    "nlp_confidence":   nlp.confidence,
                    "household_status": household_status,
                    "review_hints":     review_hints,
                    "candidates":       [],
                },
                priority = priority,
            )

        return PipelineResult(
            success=True,
            need_id=need_id,
            raw_id=raw_id,
            household_id=household_id,
            household_status=household_status,
            is_duplicate=False,
            duplicate_of=None,
            routed_to_review=review_id is not None,
            review_id=review_id,
            nlp_confidence=nlp.confidence,
        )


def _build_ir_request(payload, nlp, geo):
    """Build IdentityResolutionRequest from pipeline context."""
    from services.registry.schemas import IdentityResolutionRequest

    # Collect landmark tags from all location entities
    all_tags = []
    for loc in nlp.locations:
        all_tags.extend(loc.landmark_tags)

    location_desc = None
    if nlp.locations:
        location_desc = nlp.locations[0].text

    return IdentityResolutionRequest(
        latitude          = geo.latitude,
        longitude         = geo.longitude,
        location_description = location_desc,
        landmark_tags     = list(set(all_tags))[:10],
        family_size       = nlp.beneficiary_count if nlp.beneficiary_count > 1 else None,
        vulnerability_flags = nlp.vulnerability_flags,
        description_text  = nlp.description_normalized,
        tenant_id         = payload.tenant_id,
    )


# Singleton
ingestion_pipeline = IngestionPipeline()