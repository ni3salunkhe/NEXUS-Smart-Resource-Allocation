"""
NEXUS Ingestion Gateway — FastAPI App
Routes:
  POST /ingest/mobile       — structured form submission
  POST /ingest/text         — raw text (WhatsApp/SMS body)
  POST /ingest/image        — paper survey photo
  POST /ingest/csv          — bulk CSV upload
  POST /ingest/webhook      — external NGO systems
  POST /ingest/audio        — voice note transcript
  GET  /review              — review queue (coordinator)
  POST /review/{id}/approve
  POST /review/{id}/reject
  GET  /needs               — need records list
  GET  /needs/{id}          — single need record
  GET  /health
"""
import json
import logging
import io
import csv as csv_module
from typing import Optional, List
from uuid import UUID
from datetime import datetime

from fastapi import (
    FastAPI, Depends, HTTPException, UploadFile, File,
    Query, Request, status, BackgroundTasks
)
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import text

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from shared.config import get_settings
from shared.database import get_db
from shared.auth import get_current_user, AuthContext, TenantRLSMiddleware, require_permission
from shared.kafka import NexusProducer, NexusEvent
from shared.config import KafkaTopics

from .pipeline import ingestion_pipeline, IngestionPayload

settings = get_settings()
logger   = logging.getLogger(__name__)

app = FastAPI(
    title="NEXUS Ingestion Gateway",
    version="2.0.0",
    docs_url="/docs" if settings.DEBUG else None,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(TenantRLSMiddleware)


@app.on_event("startup")
async def startup():
    await NexusProducer.get().start()


@app.on_event("shutdown")
async def shutdown():
    await NexusProducer.get().stop()


# ── Input schemas ─────────────────────────────────────────────
class MobileFormSubmission(BaseModel):
    category:         str
    description:      str
    location_text:    Optional[str]  = None
    latitude:         Optional[float] = None
    longitude:        Optional[float] = None
    beneficiary_count: Optional[int] = None
    known_household_id: Optional[str] = None
    reported_at:      Optional[datetime] = None
    language:         str = "en"
    vulnerability_flags: dict = {}


class TextSubmission(BaseModel):
    text:             str
    source:           str = "whatsapp"   # "whatsapp" | "sms"
    sender_phone:     Optional[str] = None
    known_household_id: Optional[str] = None
    reported_at:      Optional[datetime] = None
    language_hint:    Optional[str]  = None


class WebhookSubmission(BaseModel):
    source_system:    str
    records:          List[dict]
    api_version:      str = "v1"


class ReviewDecision(BaseModel):
    notes:             Optional[str] = None
    corrected_data:    Optional[dict] = None
    link_to_household: Optional[str] = None


async def _emit_need_created(need_id: str, tenant_id: str, user_id: str, meta: dict):
    try:
        await NexusProducer.get().emit(
            KafkaTopics.NEED_CREATED,
            NexusEvent(
                event_type=KafkaTopics.NEED_CREATED,
                payload={"need_id": need_id, **meta},
                tenant_id=tenant_id,
                user_id=user_id,
            ),
            key=need_id,
        )
    except Exception as e:
        logger.error(f"Kafka emit failed (non-fatal): {e}")


# ── CHANNEL: Mobile Form ──────────────────────────────────────
@app.post("/ingest/mobile", status_code=201)
async def ingest_mobile_form(
    body: MobileFormSubmission,
    background_tasks: BackgroundTasks,
    ctx: AuthContext = Depends(require_permission("needs:create")),
    db=Depends(get_db),
):
    """Structured digital form from mobile app — highest data quality path."""
    payload = IngestionPayload(
        source_type           = "mobile",
        tenant_id             = ctx.tenant_id,
        submitted_by          = ctx.user_id,
        raw_text              = body.description,
        prefilled_category    = body.category,
        prefilled_location    = body.location_text,
        prefilled_beneficiary = body.beneficiary_count,
        known_household_id    = body.known_household_id,
        reported_at           = body.reported_at,
        raw_metadata          = {
            "language": body.language,
            "lat": body.latitude,
            "lon": body.longitude,
            "vulnerability_flags": body.vulnerability_flags,
        },
    )
    result = await ingestion_pipeline.run(payload, db)
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)

    if result.need_id:
        background_tasks.add_task(
            _emit_need_created, result.need_id, ctx.tenant_id, ctx.user_id,
            {"source": "mobile", "category": body.category}
        )

    return _pipeline_result_response(result)


# ── CHANNEL: Text (WhatsApp/SMS) ──────────────────────────────
@app.post("/ingest/text", status_code=201)
async def ingest_text(
    body: TextSubmission,
    background_tasks: BackgroundTasks,
    ctx: AuthContext = Depends(require_permission("needs:create")),
    db=Depends(get_db),
):
    payload = IngestionPayload(
        source_type        = body.source,
        tenant_id          = ctx.tenant_id,
        submitted_by       = ctx.user_id,
        raw_text           = body.text,
        known_household_id = body.known_household_id,
        reported_at        = body.reported_at,
        raw_metadata       = {
            "sender_phone":  body.sender_phone,
            "language_hint": body.language_hint,
        },
    )
    result = await ingestion_pipeline.run(payload, db)
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)

    if result.need_id:
        background_tasks.add_task(
            _emit_need_created, result.need_id, ctx.tenant_id, ctx.user_id,
            {"source": body.source}
        )
    return _pipeline_result_response(result)


# ── CHANNEL: Image (paper survey photo) ───────────────────────
@app.post("/ingest/image", status_code=201)
async def ingest_image(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    language_hints: str = Query("en,hi"),
    known_household_id: Optional[str] = Query(None),
    ctx: AuthContext = Depends(require_permission("needs:create")),
    db=Depends(get_db),
):
    """Paper survey photo — OCR → NLP → pipeline."""
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    image_bytes = await file.read()
    hints = [h.strip() for h in language_hints.split(",")]

    # OCR
    from .processors.ocr import extract_text_from_image
    ocr_result = await extract_text_from_image(image_bytes, hints)

    if not ocr_result.text.strip():
        raise HTTPException(status_code=422, detail="OCR produced no text from image")

    # Upload raw to S3 (stub — write to /tmp in dev)
    s3_key = await _store_raw_image(image_bytes, ctx.tenant_id)

    payload = IngestionPayload(
        source_type        = "paper",
        tenant_id          = ctx.tenant_id,
        submitted_by       = ctx.user_id,
        ocr_text           = ocr_result.text,
        s3_key             = s3_key,
        known_household_id = known_household_id,
        raw_metadata       = {
            "ocr_engine":     ocr_result.engine_used,
            "ocr_confidence": ocr_result.confidence,
            "filename":       file.filename,
        },
    )
    result = await ingestion_pipeline.run(payload, db)
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)

    if result.need_id:
        background_tasks.add_task(
            _emit_need_created, result.need_id, ctx.tenant_id, ctx.user_id,
            {"source": "paper", "ocr_confidence": ocr_result.confidence}
        )
    return _pipeline_result_response(result)


# ── CHANNEL: CSV bulk upload ──────────────────────────────────
@app.post("/ingest/csv", status_code=202)
async def ingest_csv(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    ctx: AuthContext = Depends(require_permission("needs:create")),
    db=Depends(get_db),
):
    """
    Bulk CSV upload. Required columns: description, category (optional), location (optional).
    Processes up to 500 rows; larger files queued as background job.
    """
    content = await file.read()
    text_content = content.decode("utf-8-sig")   # handle BOM
    reader = csv_module.DictReader(io.StringIO(text_content))

    if "description" not in (reader.fieldnames or []):
        raise HTTPException(status_code=400, detail="CSV must have a 'description' column")

    rows = list(reader)
    if len(rows) > 500:
        raise HTTPException(status_code=413, detail="Max 500 rows per upload. Use bulk import API for larger files.")

    results = []
    for i, row in enumerate(rows):
        try:
            payload = IngestionPayload(
                source_type            = "csv",
                tenant_id              = ctx.tenant_id,
                submitted_by           = ctx.user_id,
                raw_text               = row.get("description", "").strip(),
                prefilled_category     = row.get("category", "").strip() or None,
                prefilled_location     = row.get("location", "").strip() or None,
                prefilled_beneficiary  = int(row["beneficiary_count"]) if row.get("beneficiary_count", "").strip().isdigit() else None,
                known_household_id     = row.get("household_id", "").strip() or None,
                raw_metadata           = {"csv_row": i + 2},
            )
            result = await ingestion_pipeline.run(payload, db)
            results.append({
                "row": i + 2,
                "status": "ok" if result.success else "error",
                "need_id": result.need_id,
                "duplicate": result.is_duplicate,
            })
        except Exception as e:
            results.append({"row": i + 2, "status": "error", "error": str(e)})

    ok_count   = sum(1 for r in results if r["status"] == "ok")
    dup_count  = sum(1 for r in results if r.get("duplicate"))
    err_count  = sum(1 for r in results if r["status"] == "error")

    return {
        "total": len(rows),
        "processed": ok_count,
        "duplicates": dup_count,
        "errors": err_count,
        "rows": results,
    }


# ── CHANNEL: Webhook (external NGO systems) ───────────────────
@app.post("/ingest/webhook", status_code=202)
async def ingest_webhook(
    request: Request,
    body: WebhookSubmission,
    background_tasks: BackgroundTasks,
    ctx: AuthContext = Depends(require_permission("needs:create")),
    db=Depends(get_db),
):
    """External NGO system push. HMAC validation done by API Gateway layer."""
    if len(body.records) > 100:
        raise HTTPException(status_code=413, detail="Max 100 records per webhook call")

    results = []
    for rec in body.records:
        try:
            payload = IngestionPayload(
                source_type  = "webhook",
                tenant_id    = ctx.tenant_id,
                submitted_by = ctx.user_id,
                raw_text     = rec.get("description", ""),
                raw_metadata = {"source_system": body.source_system, "record": rec},
                prefilled_category = rec.get("category"),
                prefilled_location = rec.get("location"),
            )
            result = await ingestion_pipeline.run(payload, db)
            results.append({"status": "ok", "need_id": result.need_id, "duplicate": result.is_duplicate})
        except Exception as e:
            results.append({"status": "error", "error": str(e)})

    return {"accepted": len(results), "results": results}


# ── Review Queue ──────────────────────────────────────────────
@app.get("/review")
async def get_review_queue(
    limit: int  = Query(20, le=100),
    review_type: Optional[str] = Query(None),
    ctx: AuthContext = Depends(require_permission("needs:read")),
    db=Depends(get_db),
):
    conditions = ["rq.tenant_id = :tid", "rq.status = 'pending'"]
    params: dict = {"tid": ctx.tenant_id, "limit": limit}

    if review_type:
        conditions.append("rq.review_type = :rtype")
        params["rtype"] = review_type

    where = " AND ".join(conditions)
    result = await db.execute(
        text(f"""
            SELECT rq.*, nr.description, nr.category, nr.severity_score
            FROM review_queue rq
            LEFT JOIN need_records nr ON rq.need_id = nr.need_id
            WHERE {where}
            ORDER BY rq.priority ASC, rq.created_at ASC
            LIMIT :limit
        """),
        params
    )
    return [dict(r._mapping) for r in result.fetchall()]


@app.post("/review/{review_id}/approve")
async def approve_review(
    review_id: UUID,
    body: ReviewDecision,
    ctx: AuthContext = Depends(require_permission("needs:read")),
    db=Depends(get_db),
):
    await db.execute(
        text("""
            UPDATE review_queue
            SET status='approved', reviewed_by=:by, review_notes=:notes, resolved_at=NOW()
            WHERE review_id=:rid AND tenant_id=:tid
        """),
        {"rid": str(review_id), "tid": ctx.tenant_id, "by": ctx.user_id, "notes": body.notes}
    )

    if body.link_to_household:
        # Link need to household
        review = await db.execute(
            text("SELECT need_id FROM review_queue WHERE review_id=:rid"),
            {"rid": str(review_id)}
        )
        row = review.fetchone()
        if row and row.need_id:
            await db.execute(
                text("""
                    UPDATE need_records
                    SET household_id=:hh_id, status='verified', verified_by=:by, verified_at=NOW()
                    WHERE need_id=:nid
                """),
                {"hh_id": body.link_to_household, "by": ctx.user_id, "nid": str(row.need_id)}
            )

    return {"approved": True, "review_id": str(review_id)}


@app.post("/review/{review_id}/reject")
async def reject_review(
    review_id: UUID,
    body: ReviewDecision,
    ctx: AuthContext = Depends(require_permission("needs:read")),
    db=Depends(get_db),
):
    await db.execute(
        text("""
            UPDATE review_queue
            SET status='rejected', reviewed_by=:by, review_notes=:notes, resolved_at=NOW()
            WHERE review_id=:rid AND tenant_id=:tid
        """),
        {"rid": str(review_id), "tid": ctx.tenant_id, "by": ctx.user_id, "notes": body.notes}
    )
    return {"rejected": True, "review_id": str(review_id)}


# ── Need records ──────────────────────────────────────────────
@app.get("/needs")
async def list_needs(
    status: Optional[str]   = Query(None),
    category: Optional[str] = Query(None),
    ward_id: Optional[str]  = Query(None),
    limit: int               = Query(20, le=100),
    offset: int              = Query(0),
    ctx: AuthContext = Depends(require_permission("needs:read")),
    db=Depends(get_db),
):
    conditions = ["tenant_id = :tid"]
    params: dict = {"tid": ctx.tenant_id, "limit": limit, "offset": offset}

    if status:
        conditions.append("status = :status")
        params["status"] = status
    if category:
        conditions.append("category = :cat")
        params["cat"] = category
    if ward_id:
        conditions.append("ward_id = :ward")
        params["ward"] = ward_id

    where = " AND ".join(conditions)
    result = await db.execute(
        text(f"""
            SELECT need_id, tenant_id, household_id, source_type,
                   category, subcategory, description, language_detected,
                   severity_score, urgency_score, beneficiary_count,
                   vulnerability_flags, nlp_confidence, status,
                   ward_id, ingested_at, created_at
            FROM need_records
            WHERE {where}
            ORDER BY urgency_score DESC, ingested_at DESC
            LIMIT :limit OFFSET :offset
        """),
        params
    )
    return [dict(r._mapping) for r in result.fetchall()]


@app.get("/needs/{need_id}")
async def get_need(
    need_id: UUID,
    ctx: AuthContext = Depends(require_permission("needs:read")),
    db=Depends(get_db),
):
    result = await db.execute(
        text("SELECT * FROM need_records WHERE need_id=:nid AND tenant_id=:tid"),
        {"nid": str(need_id), "tid": ctx.tenant_id}
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Need not found")
    return dict(row._mapping)


# ── Health ────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"service": "nexus-ingestion", "status": "ok"}


# ── Helpers ───────────────────────────────────────────────────
async def _store_raw_image(image_bytes: bytes, tenant_id: str) -> str:
    """
    Store raw image. In production: upload to S3.
    In dev: write to /tmp and return a fake key.
    """
    import hashlib, os
    digest  = hashlib.md5(image_bytes).hexdigest()
    s3_key  = f"raw/{tenant_id}/{digest}.png"
    tmp_path = f"/tmp/nexus_{digest}.png"
    with open(tmp_path, "wb") as f:
        f.write(image_bytes)
    return s3_key


def _pipeline_result_response(result) -> dict:
    return {
        "need_id":         result.need_id,
        "raw_id":          result.raw_id,
        "household_id":    result.household_id,
        "household_status":result.household_status,
        "is_duplicate":    result.is_duplicate,
        "duplicate_of":    result.duplicate_of,
        "routed_to_review":result.routed_to_review,
        "review_id":       result.review_id,
        "nlp_confidence":  result.nlp_confidence,
    }