import asyncio
import uuid
import json
from datetime import datetime, timezone
from sqlalchemy import text
from backend.shared.database import AsyncSessionFactory
from backend.services.intelligence.priority_queue import get_priority_queue, recompute_need_urgency
from backend.services.coordination.matching.matcher import find_matches
from backend.services.coordination.task_service import task_service

async def validate_system():
    print("Starting Repaired NEXUS E2E Validation...")
    
    async with AsyncSessionFactory() as db:
        # 1. Setup Tenant
        tenant_id = str(uuid.uuid4())
        tenant_slug = f"test-tenant-{tenant_id[:8]}"
        await db.execute(
            text("INSERT INTO tenants (tenant_id, name, slug, contact_email) VALUES (:tid, :name, :slug, :email)"),
            {"tid": tenant_id, "name": "Audit Test Tenant", "slug": tenant_slug, "email": "audit@nexus.ai"}
        )
        print(f"Created Tenant: {tenant_slug}")

        # 2. Setup User + Volunteer (Same ID for test convenience)
        user_id = str(uuid.uuid4())
        vol_id  = user_id 
        
        await db.execute(
            text("""
                INSERT INTO users (user_id, tenant_id, email, role, password_hash)
                VALUES (:uid, :tid, :email, 'field_worker', 'dummy_hash')
            """),
            {"uid": user_id, "tid": tenant_id, "email": f"vol-{user_id[:8]}@test.com"}
        )
        await db.execute(
            text("""
                INSERT INTO volunteers (volunteer_id, user_id, tenant_id, active, verified, ward_id, skills)
                VALUES (:vid, :uid, :tid, TRUE, TRUE, 'ward-7', '{"food"}')
            """),
            {"vid": vol_id, "uid": user_id, "tid": tenant_id}
        )
        print("Created User + Volunteer record")

        # 3. Setup Household
        hh_id = str(uuid.uuid4())
        await db.execute(
            text("INSERT INTO households (household_id, tenant_id, ward_id, location_description) VALUES (:hid, :tid, 'ward-7', 'Near the big oak tree')"),
            {"hid": hh_id, "tid": tenant_id}
        )
        print("Created Household")

        # 4. Inject Need
        need_id = str(uuid.uuid4())
        await db.execute(
            text("""
                INSERT INTO need_records (need_id, tenant_id, household_id, category, description, severity_score, status, ward_id, source_type)
                VALUES (:nid, :tid, :hid, 'food', 'Acute food shortage for 5 people', 0.8, 'verified', 'ward-7', 'mobile')
            """),
            {"nid": need_id, "tid": tenant_id, "hid": hh_id}
        )
        print("Injected High-Severity Need")
        await db.commit()

        # 5. Validate Intelligence (Scoring)
        score = await recompute_need_urgency(db, need_id, tenant_id)
        print(f"Intelligence Scoring: Urgency Score = {score:.2f}")

        # 6. Validate Priority Queue
        queue = await get_priority_queue(db, tenant_id, limit=10)
        assert len(queue) > 0
        print("Priority Queue Ranking: Verified")

        # 7. Validate Matching
        matches = await find_matches(
            db, 
            need_id, 
            tenant_id,
            household_id=hh_id,
            category='food',
            need_latitude=None,
            need_longitude=None,
            preferred_languages=[],
            cultural_tags=[]
        )
        assert len(matches) > 0
        match = matches[0]
        print(f"Matching Engine: Found matches. Top score: {match.match_score:.2f}")

        # 8. Validate Task Lifecycle
        task_data = await task_service.create_task(db, need_id, hh_id, tenant_id, None)
        task_id = task_data['task_id']
        print(f"Task Lifecycle: Created Task {task_id}")

        await task_service.dispatch(
            db, task_id, vol_id, tenant_id, 
            match_score=match.match_score, 
            match_components=match.boosts_applied, 
            coordinator_id=None
        )
        print(f"Task Lifecycle: Dispatched to Volunteer {vol_id}")

        await task_service.accept(db, task_id, vol_id, tenant_id)
        print("Task Lifecycle: Accepted by Volunteer")

        # Verify final state
        res = await db.execute(text("SELECT status FROM tasks WHERE task_id = :tid"), {"tid": task_id})
        status = res.scalar()
        assert status == 'accepted'
        
        await db.commit()
        print("\nFULL SYSTEM E2E VALIDATION: PASS")

if __name__ == "__main__":
    asyncio.run(validate_system())
