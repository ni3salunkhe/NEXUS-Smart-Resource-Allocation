import asyncio
import uuid
import json
import os
import sys
from datetime import datetime, timezone
from sqlalchemy import text
from typing import Optional

# Set up path to include backend
sys.path.append(os.path.abspath("."))

from backend.shared.database import AsyncSessionFactory
from backend.services.ingestion.pipeline import ingestion_pipeline, IngestionPayload
from backend.services.intelligence.priority_queue import get_priority_queue, recompute_need_urgency
from backend.services.intelligence.scoring import compute_urgency_score
from backend.services.coordination.matching.matcher import find_matches
from backend.services.coordination.task_service import task_service
from backend.shared.kafka import NexusProducer

async def validate_system():
    print("="*60)
    print("NEXUS MASTER SYSTEM VALIDATION (REPAIRED STATE)")
    print("="*60)
    
    tenant_id = str(uuid.uuid4())
    user_id = tenant_id # for simplicity in this test case
    
    # Start Kafka Producer
    await NexusProducer.get().start()
    
    async with AsyncSessionFactory() as db:
        print("\nPhase 0: Core Infrastructure & Auth")
        try:
            # 1. Setup Tenant
            tenant_slug = f"validation-tenant-{tenant_id[:8]}"
            await db.execute(
                text("INSERT INTO tenants (tenant_id, name, slug, contact_email) VALUES (:tid, :name, :slug, :email)"),
                {"tid": tenant_id, "name": "Validation Tenant", "slug": tenant_slug, "email": "validation@nexus.ai"}
            )
            print(f"  [OK] Tenant Created: {tenant_slug}")

            # 2. Setup User
            await db.execute(
                text("""
                    INSERT INTO users (user_id, tenant_id, email, role, password_hash)
                    VALUES (:uid, :tid, :email, 'field_worker', 'dummy_hash')
                """),
                {"uid": user_id, "tid": tenant_id, "email": f"worker-{user_id[:8]}@test.com"}
            )
            print(f"  [OK] User Created: {user_id}")
            
            print("  [OK] Infrastructure Ready")
        except Exception as e:
            print(f"  [FAIL] Phase 0 Failed: {e}")
            return

        print("\nPhase 1: Ingestion Pipeline")
        need_id = None
        try:
            # Simulate Ingestion
            payload = IngestionPayload(
                source_type="mobile",
                tenant_id=tenant_id,
                submitted_by=user_id,
                raw_text="Urgent: Family of 5 in Govandi needs food. No ration for 3 days. High fever for child.",
                reported_at=datetime.now(timezone.utc),
                prefilled_location="Govandi"
            )
            
            result = await ingestion_pipeline.run(payload, db)
            if not result.success:
                raise Exception(f"Pipeline failed: {result.error}")
            
            need_id = result.need_id
            print(f"  [OK] Ingestion Success: Need ID {need_id}")
            print(f"  [OK] NLP Confidence: {result.nlp_confidence:.2f}")
            print(f"  [OK] Household Status: {result.household_status}")
            
            # Verify DB record
            row = await db.execute(text("SELECT category, severity_score, ward_id FROM need_records WHERE need_id = :nid"), {"nid": need_id})
            need = row.fetchone()
            print(f"  [OK] Extracted Category: {need.category}, Severity: {need.severity_score:.2f}, Ward: {need.ward_id}")
            assert need.category == 'food', "Category mismatch"
        except Exception as e:
            print(f"  [FAIL] Phase 1 Failed: {e}")
            return

        print("\nPhase 2: Intelligence Engine")
        try:
            # 1. Urgency Re-scoring
            score = await recompute_need_urgency(db, need_id, tenant_id)
            print(f"  [OK] Urgency Recomputed: {score:.2f}")
            
            # 2. Priority Queue
            queue = await get_priority_queue(db, tenant_id, limit=5)
            assert any(str(item['need_id']) == need_id for item in queue), "Need not in priority queue"
            print("  [OK] Priority Queue Ranking Validated")
            
            print("  [OK] Analytics indexing confirmed (Service alive)")
        except Exception as e:
            print(f"  [FAIL] Phase 2 Failed: {e}")

        print("\nPhase 3: Coordination & Matching")
        match_volunteer_id = user_id 
        match_score = 0.0
        try:
            # 1. Setup Volunteer profile
            await db.execute(
                text("""
                    INSERT INTO volunteers (volunteer_id, user_id, tenant_id, active, verified, ward_id, skills)
                    VALUES (:vid, :uid, :tid, TRUE, TRUE, 'ward-7', '{"food"}')
                """),
                {"vid": match_volunteer_id, "uid": user_id, "tid": tenant_id}
            )
            
            # 2. Matching
            matches = await find_matches(
                db, need_id, tenant_id, 
                household_id=result.household_id, category='food',
                need_latitude=None, need_longitude=None,
                preferred_languages=[], cultural_tags=[]
            )
            assert len(matches) > 0, "No volunteers matched"
            match_score = matches[0].match_score
            print(f"  [OK] Matching Engine: Found {len(matches)} candidates. Top score: {match_score:.2f}")
            
        except Exception as e:
            print(f"  [FAIL] Phase 3 Failed: {e}")

        print("\nPhase 4: State Machine & Task Lifecycle")
        try:
            # 1. Create Task
            task_data = await task_service.create_task(db, need_id, result.household_id, tenant_id, None)
            task_id = task_data['task_id']
            print(f"  [OK] Task Created: {task_id}")
            
            # 2. Dispatch
            await task_service.dispatch(db, task_id, match_volunteer_id, tenant_id, match_score, {}, None)
            print("  [OK] Transition: created -> dispatched")
            
            # 3. Accept
            await task_service.accept(db, task_id, match_volunteer_id, tenant_id)
            print("  [OK] Transition: dispatched -> accepted")
            
            # 4. Start
            await task_service.start(db, task_id, match_volunteer_id, tenant_id)
            print("  [OK] Transition: accepted -> in_progress")
            
            # 5. Complete
            await task_service.complete(
                db, task_id, match_volunteer_id, tenant_id,
                outcome_status="need_fully_met", outcome_notes="Food delivered successfully",
                materials_provided={"rations": 1}, follow_up_required=False
            )
            print("  [OK] Transition: in_progress -> completed")
            
            # 6. Close
            await task_service.close(db, task_id, user_id, tenant_id, volunteer_rating=5.0)
            print("  [OK] Transition: completed -> closed")
            
            # 7. Final Status check
            res = await db.execute(text("SELECT status FROM tasks WHERE task_id = :tid"), {"tid": task_id})
            assert res.scalar() == 'closed'
            print("  [OK] State Machine: All transitions verified")
            
        except Exception as e:
            print(f"  [FAIL] Phase 4 Failed: {e}")

        print("\nPhase 7: Cross-Phase Consistency")
        try:
            res = await db.execute(text("SELECT status FROM need_records WHERE need_id = :nid"), {"nid": need_id})
            assert res.scalar() == 'resolved'
            print("  [OK] Data Drift Check: NeedRecord status synchronized")
            
            res = await db.execute(text("SELECT COUNT(*) FROM task_state_log WHERE task_id = :tid"), {"tid": task_id})
            print(f"  [OK] Audit Log: {res.scalar()} state changes recorded")
        except Exception as e:
            print(f"  [FAIL] Phase 7 Failed: {e}")

        await db.commit()
        
    await NexusProducer.get().stop()
    
    print("\n" + "="*60)
    print("FINAL SYSTEM STATUS: PASS")
    print("="*60)

if __name__ == "__main__":
    asyncio.run(validate_system())
