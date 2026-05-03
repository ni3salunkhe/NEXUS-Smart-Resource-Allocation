import asyncio
import uuid
import json
import random
from datetime import datetime, timezone, timedelta
import sys
import os
from sqlalchemy import text

# Set up path to include backend
sys.path.append(os.path.abspath("."))

from backend.shared.database import AsyncSessionFactory
from backend.services.ingestion.pipeline import ingestion_pipeline, IngestionPayload
from backend.services.intelligence.scoring import compute_urgency_score, UrgencyWeights
from backend.services.intelligence.priority_queue import recompute_need_urgency
from backend.services.coordination.matching.matcher import find_matches
from backend.services.coordination.task_service import task_service

# ----------------------------
# LOGGING SETUP
# ----------------------------
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("AdversarialAuditV2")

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
# FUNCTIONAL ADVERSARIAL TEST
# ----------------------------
async def run_functional_adversarial_test():
    print("============================================================")
    print("      NEXUS FUNCTIONAL ADVERSARIAL AUDIT (V2)               ")
    print("============================================================")

    tenant_id = str(uuid.uuid4())
    user_id = tenant_id

    async with AsyncSessionFactory() as db:
        # Setup tenant + user
        await db.execute(
            text("INSERT INTO tenants (tenant_id, name, slug, contact_email) VALUES (:tid, 'Stress Tenant', :slug, 'audit@test.com')"),
            {"tid": tenant_id, "slug": f"stress-{tenant_id[:8]}"}
        )
        await db.execute(
            text("INSERT INTO users (user_id, tenant_id, email, role, password_hash) VALUES (:uid, :tid, :email, 'field_worker', 'x')"),
            {"uid": user_id, "tid": tenant_id, "email": f"audit-{user_id[:8]}@test.com"}
        )
        await db.commit()

        for case in CASES:
            print(f"\nTesting Case: {case['name']}")

            payload = IngestionPayload(
                source_type="mobile",
                tenant_id=tenant_id,
                submitted_by=user_id,
                raw_text=case["text"],
                reported_at=datetime.now(timezone.utc)
            )

            # ---- Phase 1: Ingestion ----
            result = await ingestion_pipeline.run(payload, db)
            if not result.success:
                print(f"  Handled failure: {result.error}")
                continue

            need_id = result.need_id
            print(f"  Ingestion OK: {need_id}")

            # ---- Phase 2: Scoring ----
            score = await recompute_need_urgency(db, need_id, tenant_id)
            print(f"  Score: {score}")

            if not (0 <= score <= 1):
                 print(f"  ERROR: Score out of bounds: {score}")

            # ---- Phase 3: Matching ----
            matches = await find_matches(
                db, need_id, tenant_id, 
                household_id=result.household_id, category=None,
                need_latitude=None, need_longitude=None,
                preferred_languages=[], cultural_tags=[]
            )
            print(f"  Matches Found: {len(matches)}")

        print("\nALL FUNCTIONAL TESTS COMPLETED")

if __name__ == "__main__":
    asyncio.run(run_functional_adversarial_test())
