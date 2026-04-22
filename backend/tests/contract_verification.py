import asyncio
import uuid
from datetime import datetime, timezone
import sys
import os
from sqlalchemy import text

# Set up path to include backend
sys.path.append(os.path.abspath("."))

from backend.shared.database import AsyncSessionFactory
from backend.services.intelligence.scoring import compute_urgency_score
from backend.services.coordination.matching.matcher import match_candidates

async def verify_contracts():
    print("============================================================")
    print("      NEXUS CONTRACT VERIFICATION SUITE                     ")
    print("============================================================")
    
    tenant_id = str(uuid.uuid4())
    need_id = str(uuid.uuid4())
    
    async with AsyncSessionFactory() as db:
        # Setup test data
        await db.execute(text("INSERT INTO tenants (tenant_id, name, slug) VALUES (:tid, 'Contract Test', :slug)"), {"tid": tenant_id, "slug": f"contract-{tenant_id[:8]}"})
        await db.execute(text("""
            INSERT INTO need_records (need_id, tenant_id, status, source_type, reported_at, ingested_at, severity_score, urgency_score)
            VALUES (:nid, :tid, 'unverified', 'mobile', NOW(), NOW(), 0.5, 0.5)
        """), {"nid": need_id, "tid": tenant_id})
        await db.commit()

        # 1. Verify Scoring Contract
        print("\nVerifying Scoring Adapter Contract...")
        try:
            score = await compute_urgency_score(need_id, db)
            print(f"  [OK] Signature: compute_urgency_score(need_id, db) -> float")
            assert isinstance(score, float), f"Expected float, got {type(score)}"
            assert 0 <= score <= 1, f"Score {score} out of bounds"
            print(f"  [OK] Return Type: float ({score})")
        except Exception as e:
            print(f"  [FAIL] Scoring Contract Broken: {e}")

        # 2. Verify Matcher Contract
        print("\nVerifying Matcher Adapter Contract...")
        try:
            matches = await match_candidates(need_id, db)
            print(f"  [OK] Signature: match_candidates(need_id, db) -> list")
            assert isinstance(matches, list), f"Expected list, got {type(matches)}"
            print(f"  [OK] Return Type: list (count: {len(matches)})")
        except Exception as e:
            print(f"  [FAIL] Matcher Contract Broken: {e}")

    print("\n============================================================")

if __name__ == "__main__":
    asyncio.run(verify_contracts())
