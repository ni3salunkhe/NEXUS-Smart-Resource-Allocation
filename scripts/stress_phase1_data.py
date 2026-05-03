import asyncio
import uuid
from datetime import datetime, timezone
import sys
import os

sys.path.append(os.path.abspath("."))

from sqlalchemy import text
from backend.shared.database import AsyncSessionFactory
from backend.services.ingestion.pipeline import ingestion_pipeline, IngestionPayload
from backend.services.intelligence.scoring import compute_urgency_score
from backend.services.coordination.matching.matcher import match_candidates

# ----------------------------
# ASSERT HELPERS
# ----------------------------

def assert_true(condition, message):
    if not condition:
        raise AssertionError(message)

# ----------------------------
# TEST CASES
# ----------------------------

CASES = [
    {
        "name": "Contradictory Signals",
        "text": "CRITICAL EMERGENCY. Everything is fine. No one is hurt.",
    },
    {
        "name": "Extremely Long Text",
        "text": "HELP " * 1000,
    },
    {
        "name": "Multilingual",
        "text": "Need food खाना चाहिए तातडीची मदत urgent help required.",
    },
    {
        "name": "Ambiguous Location",
        "text": "Near red building Mumbai",
    },
    {
        "name": "SQL Injection",
        "text": "Help me'); DROP TABLE users; --",
    }
]

# ----------------------------
# CORE TEST
# ----------------------------

async def run_full_adversarial_test():
    print("🔥 FULL SYSTEM ADVERSARIAL TEST")

    tenant_id = str(uuid.uuid4())
    user_id = tenant_id

    async with AsyncSessionFactory() as db:

        # Setup tenant + user
        await db.execute(
            text("INSERT INTO tenants (tenant_id, name, slug) VALUES (:tid, 'Stress Tenant', :slug)"),
            {"tid": tenant_id, "slug": f"stress-{tenant_id[:8]}"}
        )

        await db.execute(
            text("INSERT INTO users (user_id, tenant_id, email, role, password_hash) VALUES (:uid, :tid, :email, 'field_worker', 'x')"),
            {"uid": user_id, "tid": tenant_id, "email": f"stress-{user_id[:8]}@test.com"}
        )

        await db.commit()

        for case in CASES:
            print(f"\n🧪 Testing: {case['name']}")

            payload = IngestionPayload(
                source_type="mobile",
                tenant_id=tenant_id,
                submitted_by=user_id,
                raw_text=case["text"],
                reported_at=datetime.now(timezone.utc)
            )

            # ---- Phase 1 ----
            result = await ingestion_pipeline.run(payload, db)

            assert_true(result is not None, "Pipeline returned None")

            if not result.success:
                print(f"⚠️ Handled failure: {result.error}")
                continue

            need_id = result.need_id
            print(f"✅ Ingestion OK: {need_id}")

            # ---- Validate DB Insert ----
            row = await db.execute(
                text("SELECT * FROM need_records WHERE need_id = :nid"),
                {"nid": need_id}
            )
            record = row.fetchone()

            assert_true(record is not None, "Need not inserted")

            # ---- Phase 2: Scoring ----
            score = await compute_urgency_score(need_id, db)
            print(f"📊 Score: {score}")

            assert_true(0 <= score <= 1, "Invalid score range")

            # ---- Phase 3: Matching ----
            matches = await match_candidates(need_id, db)
            print(f"🤝 Matches: {len(matches)}")

            assert_true(matches is not None, "Matching failed")

        print("\n✅ ALL TESTS COMPLETED")

# ----------------------------
# CONCURRENCY TEST
# ----------------------------

async def run_concurrent_test():
    print("\n⚡ CONCURRENCY TEST")

    async def fire():
        await run_full_adversarial_test()

    await asyncio.gather(*[fire() for _ in range(5)])

# ----------------------------
# ENTRY
# ----------------------------

if __name__ == "__main__":
    asyncio.run(run_concurrent_test())