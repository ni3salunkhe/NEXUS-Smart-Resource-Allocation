import asyncio
import os
import sys
from uuid import uuid4
from datetime import datetime, timezone, timedelta
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text

from shared.config import get_settings
from services.ingestion.pipeline import ingestion_pipeline, IngestionPayload
from services.ingestion.processors.nlp import extract_nlp

settings = get_settings()

TENANT_ID = "11111111-0000-0000-0000-000000000001"
USER_ID = "22222222-0000-0000-0000-000000000001"

async def setup_test_data(session: AsyncSession):
    # Ensure tenant exists
    await session.execute(
        text("INSERT INTO tenants (tenant_id, name, slug, contact_email) VALUES (:tid, 'Test NGO', 'test-ngo', 'test@test.com') ON CONFLICT DO NOTHING"),
        {"tid": TENANT_ID}
    )
    # Ensure user exists
    await session.execute(
        text("INSERT INTO users (user_id, tenant_id, email, password_hash, role) VALUES (:uid, :tid, 'test@user.com', 'hash', 'field_worker') ON CONFLICT DO NOTHING"),
        {"uid": USER_ID, "tid": TENANT_ID}
    )
    # RLS context
    await session.execute(text(f"SELECT set_config('app.current_tenant_id', '{TENANT_ID}', TRUE)"))
    await session.execute(text(f"SELECT set_config('app.current_user_id', '{USER_ID}', TRUE)"))
    await session.commit()


async def run_crucible_tests():
    engine = create_async_engine(settings.DATABASE_URL.replace("postgresql+asyncpg", "postgresql+asyncpg"), echo=False)
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    
    print("================== PHASE 1 PIPELINE AUDIT ==================")
    async with SessionLocal() as session:
        await setup_test_data(session)

    # We will use individual sessions per pipeline run as it's closer to HTTP request behavior
    
    # --- Case A: Clean structured input
    print("\n--- CASE A: Clean Structured Input ---")
    async with SessionLocal() as db:
        await db.execute(text(f"SELECT set_config('app.current_tenant_id', '{TENANT_ID}', TRUE)"))
        payload = IngestionPayload(
            source_type="mobile",
            tenant_id=TENANT_ID,
            submitted_by=USER_ID,
            raw_text="Family of 4 living near Kurla needs ration.",
            prefilled_category="food",
            prefilled_location="Kurla",
            prefilled_beneficiary=4
        )
        res_a = await ingestion_pipeline.run(payload, db)
        await db.commit()
        print(res_a)
        assert res_a.success is True
        assert res_a.is_duplicate is False
        assert res_a.need_id is not None
        # Verify db insert
        rs = await db.execute(text("SELECT category, beneficiary_count, status FROM need_records WHERE need_id = :nid"), {"nid": res_a.need_id})
        row = rs.fetchone()
        print(f"DB Record: {row}")
        assert row.category == "food"
        assert row.beneficiary_count == 4
        assert row.status == "verified" # NLP confidence high due to prefilled fields

    # --- Case B: Noisy OCR input
    print("\n--- CASE B: Noisy OCR Input ---")
    async with SessionLocal() as db:
        await db.execute(text(f"SELECT set_config('app.current_tenant_id', '{TENANT_ID}', TRUE)"))
        payload = IngestionPayload(
            source_type="paper",
            tenant_id=TENANT_ID,
            submitted_by=USER_ID,
            ocr_text="!!g1bb3r1sh t3xt th4t m4k3s n0 s3ns3!! @#%^&*()"
        )
        res_b = await ingestion_pipeline.run(payload, db)
        await db.commit()
        print(res_b)
        assert res_b.success is True
        assert res_b.nlp_confidence < 0.75
        assert res_b.routed_to_review is True
        
    # --- Case C: Multilingual input
    print("\n--- CASE C: Multilingual Input ---")
    async with SessionLocal() as db:
        await db.execute(text(f"SELECT set_config('app.current_tenant_id', '{TENANT_ID}', TRUE)"))
        payload = IngestionPayload(
            source_type="whatsapp",
            tenant_id=TENANT_ID,
            submitted_by=USER_ID,
            raw_text="bacha bimar hai usko bukhar hai, dawa chahiye"
        )
        res_c = await ingestion_pipeline.run(payload, db)
        await db.commit()
        print(res_c)
        assert res_c.success is True
        
        rs = await db.execute(text("SELECT category, language_detected FROM need_records WHERE need_id = :nid"), {"nid": res_c.need_id})
        row = rs.fetchone()
        print(f"DB Record: {row}")
        assert row.category == "health"

    # --- Case D: Rapid Duplicates
    print("\n--- CASE D: Deduplication Check ---")
    async with SessionLocal() as db:
        await db.execute(text(f"SELECT set_config('app.current_tenant_id', '{TENANT_ID}', TRUE)"))
        payload_1 = IngestionPayload(
            source_type="whatsapp",
            tenant_id=TENANT_ID,
            submitted_by=USER_ID,
            raw_text="Water pipeline is broken near dharavi we need drinking water asap",
            known_household_id="33333333-0000-0000-0000-000000000001" # Fake HH
        )
        res_d1 = await ingestion_pipeline.run(payload_1, db)
        await db.commit()
        
        payload_2 = IngestionPayload(
            source_type="whatsapp",
            tenant_id=TENANT_ID,
            submitted_by=USER_ID,
            raw_text="Water pipeline broken near dharavi we need drinking water urgently",
            known_household_id="33333333-0000-0000-0000-000000000001"
        )
        res_d2 = await ingestion_pipeline.run(payload_2, db)
        await db.commit()
        
        print(f"\n[Case D] Original: {res_d1}\n")
        print(f"[Case D] Duplicate: {res_d2}\n")
        if not res_d2.is_duplicate:
            print("[Case D FAILURE] Expected is_duplicate=True, got False")
        if res_d2.duplicate_of != res_d1.need_id:
            print(f"[Case D FAILURE] Expected duplicate_of={res_d1.need_id}, got {res_d2.duplicate_of}")

    # --- Case E: Missing Location
    print("\n--- CASE E: Missing Location Fallback ---")
    async with SessionLocal() as db:
        await db.execute(text(f"SELECT set_config('app.current_tenant_id', '{TENANT_ID}', TRUE)"))
        payload = IngestionPayload(
            source_type="whatsapp",
            tenant_id=TENANT_ID,
            submitted_by=USER_ID,
            raw_text="Family starving without food for three days."
        )
        res_e = await ingestion_pipeline.run(payload, db)
        await db.commit()
        print(res_e)
        assert res_e.success is True
        rs = await db.execute(text("SELECT ward_id, ST_AsText(location_point) as coords FROM need_records WHERE need_id = :nid"), {"nid": res_e.need_id})
        row = rs.fetchone()
        print(f"DB Record: {row}")
        assert row.coords is None

    # --- Case F: High Severity Signals
    print("\n--- CASE F: High Severity Routing ---")
    async with SessionLocal() as db:
        await db.execute(text(f"SELECT set_config('app.current_tenant_id', '{TENANT_ID}', TRUE)"))
        payload = IngestionPayload(
            source_type="sms",
            tenant_id=TENANT_ID,
            submitted_by=USER_ID,
            raw_text="Dying, emergency, life-threatening situation. No food, collapsing."
        )
        res_f = await ingestion_pipeline.run(payload, db)
        await db.commit()
        print(res_f)
        assert res_f.success is True
        
        rs = await db.execute(text("SELECT severity_score FROM need_records WHERE need_id = :nid"), {"nid": res_f.need_id})
        row = rs.fetchone()
        print(f"DB Record: {row}")
        assert row.severity_score >= 0.90
        
        if res_f.routed_to_review:
            rs_rev = await db.execute(text("SELECT priority FROM review_queue WHERE review_id = :rid"), {"rid": res_f.review_id})
            row_rev = rs_rev.fetchone()
            print(f"Review Priority: {row_rev.priority}")
            assert row_rev.priority <= 2 # High priority

    await engine.dispose()
    print("\n================== FULL AUDIT COMPLETE ==================")

if __name__ == "__main__":
    asyncio.run(run_crucible_tests())
