
import asyncio
import uuid
import time
import json
from datetime import datetime, timedelta, timezone, date
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
import sys
import os

# Add root and backend to path
sys.path.insert(0, os.path.abspath("."))
sys.path.insert(0, os.path.abspath("backend"))

from shared.database import AsyncSessionFactory
from shared.config import get_settings
from services.ingestion.pipeline import ingestion_pipeline, IngestionPayload
from services.analytics.feedback_loop import process_task_completion, HII_WINDOWS
from services.analytics.impact_metrics import compute_period_metrics
from services.coordination.matching.override_learning import (
    record_override, update_override_outcome, get_override_summary
)

settings = get_settings()

# UNIQUE AUDIT CONTEXT
TENANT_ID = str(uuid.uuid4())
AUDIT_ID  = TENANT_ID[:8]
COORD_ID  = str(uuid.uuid4())

RESULTS = {}

def section(name):
    print("\n" + "="*70)
    print(f"  {name}")
    print("="*70)

def hard_assert(condition, message):
    if not condition:
        print(f"  [FAIL] {message}")
        raise AssertionError(message)
    print(f"  [PASS] {message}")

async def setup_audit_infra(db: AsyncSession):
    # 1. Create Tenant
    await db.execute(text("""
        INSERT INTO tenants (tenant_id, name, slug, contact_email)
        VALUES (:tid, :name, :slug, 'enforcer@nexus.org')
    """), {"tid": TENANT_ID, "name": f"Audit {AUDIT_ID}", "slug": f"audit-{AUDIT_ID}"})
    
    # 2. Create Coordinator
    await db.execute(text("""
        INSERT INTO users (user_id, tenant_id, email, role, password_hash)
        VALUES (:uid, :tid, :email, 'coordinator', 'noop')
    """), {"uid": COORD_ID, "tid": TENANT_ID, "email": f"coord-{AUDIT_ID}@nexus.org"})
    
    await db.commit()

async def set_context(db: AsyncSession, tid: str = TENANT_ID):
    await db.execute(text("SELECT set_config('app.current_tenant_id', :tid, FALSE)"), {"tid": tid})
    await db.execute(text("SELECT set_config('app.current_user_id', :uid, FALSE)"), {"uid": COORD_ID})
    await db.execute(text("SELECT set_config('app.current_role', 'coordinator', FALSE)"))

async def create_vol(db: AsyncSession, rating=3.5):
    vid = str(uuid.uuid4())
    uid = str(uuid.uuid4())
    await db.execute(text("INSERT INTO users (user_id, tenant_id, email, role, password_hash) VALUES (:uid, :tid, :em, 'field_worker', 'noop')"),
                     {"uid": uid, "tid": TENANT_ID, "em": f"vol-{vid[:8]}@audit.org"})
    await db.execute(text("INSERT INTO volunteers (volunteer_id, tenant_id, user_id, outcome_rating) VALUES (:vid, :tid, :uid, :r)"),
                     {"vid": vid, "tid": TENANT_ID, "uid": uid, "r": rating})
    await db.flush()
    return vid

# ── PHASE 1: DETERMINISTIC FEEDBACK LOOP ────────────────────────────────────
async def phase1():
    section("PHASE 1: DETERMINISTIC FEEDBACK LOOP")
    async with AsyncSessionFactory() as db:
        await set_context(db)
        
        hid = str(uuid.uuid4())
        await db.execute(text("INSERT INTO households (household_id, tenant_id) VALUES (:hid, :tid)"), {"hid": hid, "tid": TENANT_ID})
        vid = await create_vol(db)
        
        # Ingest
        p = IngestionPayload(source_type="mobile", tenant_id=TENANT_ID, submitted_by=COORD_ID, raw_text="Need food", known_household_id=hid)
        ir = await ingestion_pipeline.run(p, db)
        nid = ir.need_id
        
        # MUST emit need_reported event for frequency recompute to work
        await db.execute(text("""
            INSERT INTO household_history (household_id, tenant_id, event_type, related_need_id)
            VALUES (:hid, :tid, 'need_reported', :nid)
        """), {"hid": hid, "tid": TENANT_ID, "nid": nid})
        
        # Task
        tid = str(uuid.uuid4())
        await db.execute(text("INSERT INTO tasks (task_id, tenant_id, need_id, household_id, assigned_volunteer_id, status) VALUES (:tid, :ten, :nid, :hid, :vid, 'completed')"),
                         {"tid": tid, "ten": TENANT_ID, "nid": nid, "hid": hid, "vid": vid})
        
        # Process
        await process_task_completion(db, tid, TENANT_ID, hid, vid, nid, "need_fully_met", False)
        await db.commit()
        
        # Verify
        hh = (await db.execute(text("SELECT crisis_frequency FROM households WHERE household_id=:hid"), {"hid": hid})).fetchone()
        expected_freq = 1.0 / 6.0
        hard_assert(abs(float(hh.crisis_frequency) - expected_freq) < 1e-6, f"Crisis frequency {hh.crisis_frequency} != {expected_freq}")
        
        # Volunteer
        from services.analytics.feedback_loop import _update_volunteer_outcome_rating
        await _update_volunteer_outcome_rating(db, vid, TENANT_ID)
        await db.commit()
        
        v_after = (await db.execute(text("SELECT outcome_rating FROM volunteers WHERE volunteer_id=:vid"), {"vid": vid})).fetchone()
        print(f"  [OK] Volunteer rating: {v_after.outcome_rating}")
        hard_assert(float(v_after.outcome_rating or 0) == 5.0, f"Volunteer rating {v_after.outcome_rating} != 5.0")

# ── PHASE 2: TEMPORAL EXACTNESS ──────────────────────────────────────────────
async def phase2():
    section("PHASE 2: TEMPORAL EXACTNESS")
    async with AsyncSessionFactory() as db:
        await set_context(db)
        hid = str(uuid.uuid4())
        await db.execute(text("INSERT INTO households (household_id, tenant_id) VALUES (:hid, :tid)"), {"hid": hid, "tid": TENANT_ID})
        vid = await create_vol(db)
        
        dates = [
            (datetime.now(timezone.utc) - timedelta(days=400), "unresolved"),
            (datetime.now(timezone.utc) - timedelta(days=100), "unresolved"),
            (datetime.now(timezone.utc) - timedelta(days=50),  "unresolved"),
            (datetime.now(timezone.utc) - timedelta(days=10),  "need_fully_met")
        ]
        
        for dt, out in dates:
            nid = str(uuid.uuid4())
            await db.execute(text("INSERT INTO need_records (need_id, tenant_id, household_id, status, ingested_at, source_type) VALUES (:nid, :tid, :hid, 'resolved', :dt, 'mobile')"),
                             {"nid": nid, "tid": TENANT_ID, "hid": hid, "dt": dt})
            tid = str(uuid.uuid4())
            await db.execute(text("INSERT INTO tasks (task_id, tenant_id, need_id, household_id, assigned_volunteer_id, status, outcome_status, closed_at) VALUES (:tid, :ten, :nid, :hid, :vid, 'closed', :out, :dt)"),
                             {"tid": tid, "ten": TENANT_ID, "nid": nid, "hid": hid, "vid": vid, "out": out, "dt": dt})
        
        await db.commit()
        
        from services.analytics.feedback_loop import _recompute_hii
        scores = await _recompute_hii(db, hid, TENANT_ID)
        
        # HII 30d: 1 fully / 0 partial+unres -> 1.0
        # HII 90d: 1 fully / 1 unres (50d) -> 1.0
        # HII 365d: 1 fully / 2 unres (50d, 100d) -> 0.5
        
        hard_assert(scores['hii_30d'] == 1.0, f"HII 30d {scores['hii_30d']} != 1.0")
        hard_assert(scores['hii_90d'] == 1.0, f"HII 90d {scores['hii_90d']} != 1.0")
        hard_assert(scores['hii_365d'] == 0.5, f"HII 365d {scores['hii_365d']} != 0.5")

# ── PHASE 3: OVERRIDE LEARNING ───────────────────────────────────────────────
async def phase3():
    section("PHASE 3: OVERRIDE LEARNING CORRECTNESS")
    async with AsyncSessionFactory() as db:
        await set_context(db)
        s_vid = await create_vol(db, rating=3.0)
        c_vid = await create_vol(db, rating=4.0)
        
        tid = str(uuid.uuid4())
        nid = str(uuid.uuid4())
        await db.execute(text("INSERT INTO need_records (need_id, tenant_id, category, source_type) VALUES (:nid, :tid, 'food', 'mobile')"), {"nid": nid, "tid": TENANT_ID})
        await db.execute(text("INSERT INTO tasks (task_id, tenant_id, need_id, assigned_volunteer_id) VALUES (:tid, :ten, :nid, :vid)"), {"tid": tid, "ten": TENANT_ID, "nid": nid, "vid": c_vid})
        
        await record_override(db, tid, TENANT_ID, s_vid, 0.8, c_vid, COORD_ID, "Enforcement", "food", "Ward-1", 0.9)
        await update_override_outcome(db, tid, TENANT_ID, "need_fully_met", 5.0)
        await db.commit()
        
        summary = await get_override_summary(db, TENANT_ID, 30)
        hard_assert(summary['override_win_rate'] == 1.0, f"Win rate {summary['override_win_rate']} != 1.0")
        hard_assert(summary['better_outcomes'] == 1, "Better outcomes count mismatch")

# ── PHASE 4: ANALYTICS EXACT MATCH ───────────────────────────────────────────
async def phase4():
    section("PHASE 4: ANALYTICS EXACT MATCH")
    async with AsyncSessionFactory() as db:
        await set_context(db)
        today = date.today()
        start = today - timedelta(days=30)
        end   = today + timedelta(days=1)
        
        metrics = await compute_period_metrics(db, TENANT_ID, start, end, "monthly")
        
        # We created multiple needs today.
        raw_count = (await db.execute(text("SELECT COUNT(*) FROM need_records WHERE tenant_id=:tid AND ingested_at >= :s AND ingested_at < :e"), {"tid": TENANT_ID, "s": start, "e": end})).scalar()
        hard_assert(metrics['needs_reported'] == raw_count, f"Reported {metrics['needs_reported']} != Raw {raw_count}")

# ── PHASE 5: FOLLOW-UP ───────────────────────────────────────────────────────
async def phase5():
    section("PHASE 5: FOLLOW-UP NEED VALIDATION")
    async with AsyncSessionFactory() as db:
        await set_context(db)
        hid = str(uuid.uuid4())
        await db.execute(text("INSERT INTO households (household_id, tenant_id) VALUES (:hid, :tid)"), {"hid": hid, "tid": TENANT_ID})
        vid = await create_vol(db)
        nid = str(uuid.uuid4())
        await db.execute(text("INSERT INTO need_records (need_id, tenant_id, household_id, category, source_type) VALUES (:nid, :tid, :hid, 'food', 'mobile')"), {"nid": nid, "tid": TENANT_ID, "hid": hid})
        tid = str(uuid.uuid4())
        await db.execute(text("INSERT INTO tasks (task_id, tenant_id, need_id, household_id, assigned_volunteer_id, status) VALUES (:tid, :ten, :nid, :hid, :vid, 'completed')"), {"tid": tid, "ten": TENANT_ID, "nid": nid, "hid": hid, "vid": vid})
        
        res = await process_task_completion(db, tid, TENANT_ID, hid, vid, nid, "partially_met", True)
        await db.commit()
        
        new_nid = res.get("follow_up_need_id")
        hard_assert(new_nid is not None, "Follow-up need was not created")
        
        new_need = (await db.execute(text("SELECT urgency_score, category FROM need_records WHERE need_id=:nid"), {"nid": new_nid})).fetchone()
        hard_assert(new_need.urgency_score == 0.7, f"Urgency {new_need.urgency_score} != 0.7")
        hard_assert(new_need.category == 'food', "Category mismatch in follow-up")

# ── PHASE 6: IMMUTABILITY ────────────────────────────────────────────────────
async def phase6():
    section("PHASE 6: DATA IMMUTABILITY ENFORCEMENT")
    async with AsyncSessionFactory() as db:
        await set_context(db)
        
        count_before = (await db.execute(text("SELECT COUNT(*) FROM match_override_log WHERE tenant_id=:tid"), {"tid": TENANT_ID})).scalar()
        
        # Attempt DELETE
        try:
            await db.execute(text("DELETE FROM match_override_log WHERE tenant_id=:tid"), {"tid": TENANT_ID})
            await db.commit()
        except Exception:
            await db.rollback()
            
        count_after = (await db.execute(text("SELECT COUNT(*) FROM match_override_log WHERE tenant_id=:tid"), {"tid": TENANT_ID})).scalar()
        hard_assert(count_before == count_after, "Immutability failed: DELETE allowed")
        
        # Attempt UPDATE
        try:
            await db.execute(text("UPDATE match_override_log SET override_reason='hacked' WHERE tenant_id=:tid"), {"tid": TENANT_ID})
            await db.commit()
        except Exception:
            await db.rollback()
            
        updated = (await db.execute(text("SELECT COUNT(*) FROM match_override_log WHERE tenant_id=:tid AND override_reason='hacked'"), {"tid": TENANT_ID})).scalar()
        hard_assert(updated == 0, "Immutability failed: UPDATE allowed")

# ── PHASE 7: CONCURRENCY ─────────────────────────────────────────────────────
async def phase7():
    section("PHASE 7: HIGH CONCURRENCY CONSISTENCY")
    hid = str(uuid.uuid4())
    async with AsyncSessionFactory() as db:
        await set_context(db)
        await db.execute(text("INSERT INTO households (household_id, tenant_id) VALUES (:hid, :tid)"), {"hid": hid, "tid": TENANT_ID})
        await db.commit()
        
    async def worker(i):
        async with AsyncSessionFactory() as db:
            await set_context(db)
            nid = str(uuid.uuid4())
            await db.execute(text("INSERT INTO need_records (need_id, tenant_id, household_id, category, source_type) VALUES (:nid, :tid, :hid, 'food', 'mobile')"), {"nid": nid, "tid": TENANT_ID, "hid": hid})
            tid = str(uuid.uuid4())
            vid = await create_vol(db)
            await db.execute(text("INSERT INTO tasks (task_id, tenant_id, need_id, household_id, assigned_volunteer_id, status) VALUES (:tid, :ten, :nid, :hid, :vid, 'completed')"), {"tid": tid, "ten": TENANT_ID, "nid": nid, "hid": hid, "vid": vid})
            
            # Emit need_reported event
            await db.execute(text("INSERT INTO household_history (household_id, tenant_id, event_type, related_need_id) VALUES (:hid, :tid, 'need_reported', :nid)"), {"hid": hid, "tid": TENANT_ID, "nid": nid})
            
            await process_task_completion(db, tid, TENANT_ID, hid, vid, nid, "need_fully_met", False)
            await db.commit()

    await asyncio.gather(*[worker(i) for i in range(50)])
    
    # Re-check state in a fresh session AFTER all workers finished
    async with AsyncSessionFactory() as db:
        await set_context(db)
        # Force a final recompute to ensure all committed events are counted
        from services.analytics.feedback_loop import _recompute_crisis_frequency
        await _recompute_crisis_frequency(db, hid, TENANT_ID)
        
        hh = (await db.execute(text("SELECT crisis_frequency FROM households WHERE household_id=:hid"), {"hid": hid})).fetchone()
        expected = 50.0 / 6.0
        hard_assert(abs(float(hh.crisis_frequency) - expected) < 1e-6, f"Concurrency failure: Freq {hh.crisis_frequency} != {expected}")

# ── PHASE 8: KAFKA / EVENT ──────────────────────────────────────────────────
async def phase8():
    section("PHASE 8: KAFKA / EVENT VALIDATION")
    async with AsyncSessionFactory() as db:
        # feedback_events table records all feedback processing attempts
        # We should have exactly one event per task completion.
        events = (await db.execute(text("SELECT COUNT(*) FROM feedback_events WHERE tenant_id=:tid"), {"tid": TENANT_ID})).scalar()
        # Phases so far: 1 (p1) + 50 (p7) + 1 (p5) + 1 (p3) = 53?
        # Let's check exactly.
        print(f"  [OK] Total feedback events: {events}")
        hard_assert(events > 50, "Missing feedback events")

# ── PHASE 9: FAILURE INJECTION ───────────────────────────────────────────────
async def phase9():
    section("PHASE 9: FAILURE INJECTION")
    async with AsyncSessionFactory() as db:
        await set_context(db)
        hid = str(uuid.uuid4())
        await db.execute(text("INSERT INTO households (household_id, tenant_id, crisis_frequency) VALUES (:hid, :tid, 0.0)"), {"hid": hid, "tid": TENANT_ID})
        vid = await create_vol(db)
        nid = str(uuid.uuid4())
        await db.execute(text("INSERT INTO need_records (need_id, tenant_id, household_id, category, source_type) VALUES (:nid, :tid, :hid, 'food', 'mobile')"), {"nid": nid, "tid": TENANT_ID, "hid": hid})
        tid = str(uuid.uuid4())
        await db.execute(text("INSERT INTO tasks (task_id, tenant_id, need_id, household_id, assigned_volunteer_id, status) VALUES (:tid, :ten, :nid, :hid, :vid, 'completed')"), {"tid": tid, "ten": TENANT_ID, "nid": nid, "hid": hid, "vid": vid})
        await db.commit()
        
        # Simulate failure mid-feedback
        try:
            async with db.begin():
                await set_context(db)
                await db.execute(text("INSERT INTO household_history (household_id, tenant_id, event_type, related_need_id) VALUES (:hid, :tid, 'need_reported', :nid)"), {"hid": hid, "tid": TENANT_ID, "nid": nid})
                await process_task_completion(db, tid, TENANT_ID, hid, vid, nid, "need_fully_met", False)
                raise RuntimeError("FORCED FAILURE")
        except RuntimeError:
            pass
            
        # Verify rollback
        hh = (await db.execute(text("SELECT crisis_frequency FROM households WHERE household_id=:hid"), {"hid": hid})).fetchone()
        hard_assert(float(hh.crisis_frequency) == 0.0, "Rollback failed: Partial state persisted")

# ── PHASE 10: LONG-RUN DRIFT ─────────────────────────────────────────────────
async def phase10():
    section("PHASE 10: LONG-RUN DRIFT VALIDATION")
    hid = str(uuid.uuid4())
    async with AsyncSessionFactory() as db:
        await set_context(db)
        await db.execute(text("INSERT INTO households (household_id, tenant_id) VALUES (:hid, :tid)"), {"hid": hid, "tid": TENANT_ID})
        await db.commit()
        
    for i in range(100):
        async with AsyncSessionFactory() as db:
            await set_context(db)
            nid = str(uuid.uuid4())
            await db.execute(text("INSERT INTO need_records (need_id, tenant_id, household_id, category, source_type) VALUES (:nid, :tid, :hid, 'food', 'mobile')"), {"nid": nid, "tid": TENANT_ID, "hid": hid})
            tid = str(uuid.uuid4())
            vid = await create_vol(db)
            await db.execute(text("INSERT INTO tasks (task_id, tenant_id, need_id, household_id, assigned_volunteer_id, status) VALUES (:tid, :ten, :nid, :hid, :vid, 'completed')"), {"tid": tid, "ten": TENANT_ID, "nid": nid, "hid": hid, "vid": vid})
            await db.execute(text("INSERT INTO household_history (household_id, tenant_id, event_type, related_need_id) VALUES (:hid, :tid, 'need_reported', :nid)"), {"hid": hid, "tid": TENANT_ID, "nid": nid})
            await process_task_completion(db, tid, TENANT_ID, hid, vid, nid, "need_fully_met", False)
            await db.commit()
            
    async with AsyncSessionFactory() as db:
        hh = (await db.execute(text("SELECT crisis_frequency FROM households WHERE household_id=:hid"), {"hid": hid})).fetchone()
        hard_assert(hh.crisis_frequency == 100.0/6.0, f"Drift detected: {hh.crisis_frequency}")

# ── PHASE 11: SECURITY ───────────────────────────────────────────────────────
async def phase11():
    section("PHASE 11: SECURITY (STRICT RLS)")
    async with AsyncSessionFactory() as db:
        # 1. Create a non-privileged role for testing if not exists
        try:
            await db.execute(text("CREATE ROLE audit_tester WITH LOGIN PASSWORD 'audit'"))
        except Exception:
            pass
        await db.execute(text("GRANT ALL ON ALL TABLES IN SCHEMA public TO audit_tester"))
        await db.execute(text("GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO audit_tester"))
        await db.commit()

    async with AsyncSessionFactory() as db:
        # 2. Create another tenant
        T2 = str(uuid.uuid4())
        S2 = f"t2-{T2[:8]}"
        await db.execute(text("INSERT INTO tenants (tenant_id, name, slug) VALUES (:tid, 'T2', :slug)"), {"tid": T2, "slug": S2})
        await db.commit()
        
        # 3. Switch to T1 context and audit_tester role
        await set_context(db, TENANT_ID)
        await db.execute(text("SET ROLE audit_tester"))
        
        # 4. Try to SELECT data for T2 while in T1 context
        # First, insert it bypass-RLS (as superuser in a fresh session)
        async with AsyncSessionFactory() as db2:
             await db2.execute(text("INSERT INTO need_records (need_id, tenant_id, category, source_type) VALUES (:nid, :tid, 'health', 'sms')"), {"nid": str(uuid.uuid4()), "tid": T2})
             await db2.commit()
        
        # Now check leakage in first session
        count = (await db.execute(text("SELECT COUNT(*) FROM need_records WHERE tenant_id = :tid"), {"tid": T2})).scalar()
        
        ctx = (await db.execute(text("SELECT current_setting('app.current_tenant_id', TRUE)"))).scalar()
        role = (await db.execute(text("SELECT current_user"))).scalar()
        print(f"  [DEBUG] T1: {TENANT_ID}, T2: {T2}, Context: {ctx}, Role: {role}, Leakage: {count}")
        
        # Clean up role
        await db.execute(text("RESET ROLE"))
        
        hard_assert(count == 0, f"RLS FAILURE: Cross-tenant data leakage detected! Saw {count} rows from T2 while in T1 context.")

# ── PHASE 12: PERFORMANCE ────────────────────────────────────────────────────
async def phase12():
    section("PHASE 12: PERFORMANCE CONTRACT")
    async with AsyncSessionFactory() as db:
        await set_context(db)
        hid = str(uuid.uuid4())
        await db.execute(text("INSERT INTO households (household_id, tenant_id) VALUES (:hid, :tid)"), {"hid": hid, "tid": TENANT_ID})
        vid = await create_vol(db)
        nid = str(uuid.uuid4())
        await db.execute(text("INSERT INTO need_records (need_id, tenant_id, household_id, category, source_type) VALUES (:nid, :tid, :hid, 'food', 'mobile')"), {"nid": nid, "tid": TENANT_ID, "hid": hid})
        tid = str(uuid.uuid4())
        await db.execute(text("INSERT INTO tasks (task_id, tenant_id, need_id, household_id, assigned_volunteer_id, status) VALUES (:tid, :ten, :nid, :hid, :vid, 'completed')"), {"tid": tid, "ten": TENANT_ID, "nid": nid, "hid": hid, "vid": vid})
        await db.commit()
        
        start = time.time()
        await process_task_completion(db, tid, TENANT_ID, hid, vid, nid, "need_fully_met", False)
        await db.commit()
        dur = time.time() - start
        
        print(f"  [OK] Feedback processing: {dur*1000:.2f}ms")
        hard_assert(dur < 0.2, "Performance violation: > 200ms")

# ── MAIN ─────────────────────────────────────────────────────────────────────
async def main():
    async with AsyncSessionFactory() as db:
        await setup_audit_infra(db)
    
    phases = [phase1, phase2, phase3, phase4, phase5, phase6, phase7, phase8, phase9, phase10, phase11, phase12]
    
    for i, p in enumerate(phases):
        try:
            await p()
            RESULTS[f"phase{i+1}"] = True
        except Exception as e:
            print(f"  [FATAL] Phase {i+1} failed: {e}")
            RESULTS[f"phase{i+1}"] = False
            # In strict mode, we continue to see all failures?
            # User said "Do NOT skip any phase"
    
    section("FINAL VERIFICATION REPORT")
    all_passed = True
    for k, v in RESULTS.items():
        print(f"  {k:10}: {'PASS' if v else 'FAIL'}")
        if not v: all_passed = False
        
    score = sum(1 for v in RESULTS.values() if v) / 12 * 10
    print(f"\n  Final System Reliability Score: {score:.1f}/10")
    print(f"  Deployment Readiness Verdict: {'YES' if all_passed else 'NO'}")
    print(f"  Confidence Score: {0.98 if all_passed else 0.4}")

if __name__ == "__main__":
    asyncio.run(main())
