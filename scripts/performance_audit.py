import asyncio
import uuid
import random
from datetime import datetime, timezone
import sys
import os
from sqlalchemy import text

# Set up path to include backend
sys.path.append(os.path.abspath("."))

from backend.shared.database import AsyncSessionFactory
from backend.services.ingestion.pipeline import ingestion_pipeline, IngestionPayload

async def performance_audit():
    print("============================================================")
    print("      NEXUS PERFORMANCE & IDEMPOTENCY FINAL AUDIT           ")
    print("============================================================")
    
    tenant_id = str(uuid.uuid4())
    user_id = tenant_id
    
    async with AsyncSessionFactory() as db:
        await db.execute(text("INSERT INTO tenants (tenant_id, name, slug, contact_email) VALUES (:tid, 'Perf Tenant', :slug, 'perf@test.com')"), {"tid": tenant_id, "slug": f"perf-{tenant_id[:8]}"})
        await db.execute(text("INSERT INTO users (user_id, tenant_id, email, role, password_hash) VALUES (:uid, :tid, :email, 'field_worker', 'x')"), {"uid": user_id, "tid": tenant_id, "email": f"perf-{user_id[:8]}@test.com"})
        await db.commit()

    # --- IDEMPOTENCY TEST ---
    print("\nTesting Idempotency (Same Correlation ID)...")
    corr_id = str(uuid.uuid4())
    payload = IngestionPayload(
        source_type="mobile", tenant_id=tenant_id, submitted_by=user_id,
        raw_text="Test idempotency", correlation_id=corr_id
    )
    
    async with AsyncSessionFactory() as db:
        r1 = await ingestion_pipeline.run(payload, db)
        r2 = await ingestion_pipeline.run(payload, db)
        if r1.need_id == r2.need_id and r1.need_id is not None:
            print(f"  [PASS] Idempotency maintained: Need ID {r1.need_id}")
        else:
            print(f"  [FAIL] Idempotency BROKEN: R1={r1.need_id}, R2={r2.need_id}")

    # --- CONCURRENCY STRESS ---
    print("\nTesting High Concurrency (100 requests)...")
    
    async def task(i):
        async with AsyncSessionFactory() as db:
            p = IngestionPayload(
                source_type="mobile", tenant_id=tenant_id, submitted_by=user_id,
                raw_text=f"Stress test message {i}", reported_at=datetime.now(timezone.utc)
            )
            return await ingestion_pipeline.run(p, db)

    start_time = datetime.now()
    tasks = [task(i) for i in range(100)]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    end_time = datetime.now()
    
    successes = [r for r in results if not isinstance(r, Exception) and r.success]
    failures = [r for r in results if isinstance(r, Exception) or not r.success]
    
    duration = (end_time - start_time).total_seconds()
    print(f"  Results: {len(successes)} Success, {len(failures)} Failure")
    print(f"  Throughput: {len(tasks)/duration:.2f} req/s")
    
    if failures:
        print(f"  First failure: {failures[0]}")

    print("\n============================================================")

if __name__ == "__main__":
    asyncio.run(performance_audit())
