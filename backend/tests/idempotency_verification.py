import asyncio
import uuid
from datetime import datetime, timezone
import sys
import os
from sqlalchemy import text

# Set up path to include backend
sys.path.append(os.path.abspath("."))

from backend.shared.database import AsyncSessionFactory
from backend.services.ingestion.pipeline import ingestion_pipeline, IngestionPayload

async def verify_idempotency():
    print("============================================================")
    print("      NEXUS IDEMPOTENCY VERIFICATION SUITE                  ")
    print("============================================================")
    
    tenant_id = str(uuid.uuid4())
    user_id = tenant_id
    correlation_id = str(uuid.uuid4())
    
    async with AsyncSessionFactory() as db:
        await db.execute(text("INSERT INTO tenants (tenant_id, name, slug) VALUES (:tid, 'Idem Test', :slug)"), {"tid": tenant_id, "slug": f"idem-{tenant_id[:8]}"})
        await db.execute(text("INSERT INTO users (user_id, tenant_id, email, role, password_hash) VALUES (:uid, :tid, :email, 'field_worker', 'x')"), {"uid": user_id, "tid": tenant_id, "email": f"idem-{user_id[:8]}@test.com"})
        await db.commit()

        print(f"\nSubmitting first request (corr_id: {correlation_id})...")
        payload = IngestionPayload(
            source_type="mobile",
            tenant_id=tenant_id,
            submitted_by=user_id,
            raw_text="Emergency water needed",
            correlation_id=correlation_id
        )
        
        res1 = await ingestion_pipeline.run(payload, db)
        await db.commit() # MUST commit for the recovery session to see it
        print(f"  [OK] First Need ID: {res1.need_id}")
        assert res1.success, "First request failed"
        assert res1.need_id is not None, "First request returned no need_id"

        print(f"\nSubmitting duplicate request (same corr_id)...")
        res2 = await ingestion_pipeline.run(payload, db)
        print(f"  [OK] Second Need ID: {res2.need_id}")
        
        assert res2.success, "Second request failed"
        assert res1.need_id == res2.need_id, f"Idempotency failed: {res1.need_id} != {res2.need_id}"
        print(f"  [PASS] Same Need ID returned.")

        # Verify DB count
        count_raw = await db.scalar(text("SELECT COUNT(*) FROM ingestion_raw WHERE correlation_id = :cid"), {"cid": correlation_id})
        count_need = await db.scalar(text("SELECT COUNT(*) FROM need_records WHERE raw_id = (SELECT raw_id FROM ingestion_raw WHERE correlation_id = :cid)"), {"cid": correlation_id})
        
        print(f"  [CHECK] ingestion_raw entries: {count_raw} (Expected 1)")
        print(f"  [CHECK] need_records entries: {count_need} (Expected 1)")
        
        assert count_raw == 1, f"Duplicate ingestion_raw entries: {count_raw}"
        # count_need should be 1 for the specific raw_id
        
    print("\n============================================================")

if __name__ == "__main__":
    asyncio.run(verify_idempotency())
