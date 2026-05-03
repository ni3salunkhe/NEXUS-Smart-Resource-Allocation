import asyncio
import time
import uuid
import sys
import os
from sqlalchemy import text

# Set up path to include backend
sys.path.append(os.path.abspath("."))

from backend.shared.database import AsyncSessionFactory
from backend.services.intelligence.scoring import compute_urgency_score
from backend.services.coordination.matching.matcher import match_candidates

async def run_performance_audit():
    print("============================================================")
    print("      NEXUS PERFORMANCE AUDIT                               ")
    print("============================================================")
    
    tenant_id = str(uuid.uuid4())
    need_id = str(uuid.uuid4())
    
    async with AsyncSessionFactory() as db:
        # Setup test data
        await db.execute(text("INSERT INTO tenants (tenant_id, name, slug) VALUES (:tid, 'Perf Test', :slug)"), {"tid": tenant_id, "slug": f"perf-{tenant_id[:8]}"})
        await db.execute(text("""
            INSERT INTO need_records (need_id, tenant_id, status, source_type, reported_at, ingested_at, severity_score, urgency_score, location_point)
            VALUES (:nid, :tid, 'unverified', 'mobile', NOW(), NOW(), 0.5, 0.5, ST_SetSRID(ST_MakePoint(72.8777, 19.0760), 4326))
        """), {"nid": need_id, "tid": tenant_id})
        await db.commit()

        # 1. Scoring Adapter Latency
        start = time.perf_counter()
        for _ in range(100):
            await compute_urgency_score(need_id, db)
        end = time.perf_counter()
        avg_scoring = (end - start) / 100.0
        print(f"  Scoring Adapter Latency: {avg_scoring*1000:.3f} ms / call")

        # 2. Matcher Adapter Latency
        start = time.perf_counter()
        for _ in range(10):
            await match_candidates(need_id, db)
        end = time.perf_counter()
        avg_matching = (end - start) / 10.0
        print(f"  Matcher Adapter Latency: {avg_matching*1000:.3f} ms / call")

    print("\n============================================================")

if __name__ == "__main__":
    asyncio.run(run_performance_audit())
