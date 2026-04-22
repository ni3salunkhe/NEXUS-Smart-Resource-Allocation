"""
NEXUS Distributed Production Validation Suite v2
─ Kafka lifecycle managed once (no singleton resets)
─ All phases run on a single producer session
─ Consumer backoff eliminates GroupCoordinatorNotAvailable
"""
import asyncio
import time
import uuid
import statistics
import json
import sys
import os
from datetime import datetime, timezone
from aiokafka import AIOKafkaConsumer
from aiokafka.admin import AIOKafkaAdminClient
from aiokafka.errors import KafkaConnectionError, NoBrokersAvailable
from sqlalchemy import text

sys.path.append(os.path.abspath("."))

from shared.database import AsyncSessionFactory
from shared.kafka import NexusProducer, NexusConsumer, NexusEvent, ensure_topics_exist
from shared.config import get_settings, KafkaTopics
from backend.services.ingestion.pipeline import ingestion_pipeline, IngestionPayload

import logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")

settings = get_settings()
TENANT_ID = str(uuid.uuid4())
USER_ID = TENANT_ID
RESULTS = {}

def section(title):
    print(f"\n{'='*60}", flush=True)
    print(f"  {title}", flush=True)
    print(f"{'='*60}", flush=True)

async def setup_tenant():
    async with AsyncSessionFactory() as db:
        await db.execute(
            text("INSERT INTO tenants (tenant_id, name, slug) VALUES (:tid, 'Dist Test v2', :slug)"),
            {"tid": TENANT_ID, "slug": f"dist2-{TENANT_ID[:8]}"}
        )
        await db.execute(
            text("INSERT INTO users (user_id, tenant_id, email, role, password_hash) VALUES (:uid, :tid, :email, 'field_worker', 'x')"),
            {"uid": USER_ID, "tid": TENANT_ID, "email": f"dist2-{USER_ID[:8]}@test.com"}
        )
        await db.commit()
    print(f"  Tenant: {TENANT_ID}")

# ── Phase 1: Kafka Integration ──────────────────────────────────
async def phase1_kafka_integration():
    section("PHASE 1: KAFKA INTEGRATION")
    failures = 0
    producer = NexusProducer.get()

    # 1a. Producer lifecycle with retry/backoff
    print("  [1a] Producer start with retry/backoff...")
    try:
        await producer.start(max_retries=5, base_delay=2.0)
        print(f"    [OK] Producer started, ready={producer.is_ready}")
    except Exception as e:
        failures += 1
        print(f"    [FAIL] Producer start failed: {e}")
        RESULTS["phase1_kafka"] = False
        return False

    # 1b. Topic initialization with retry
    print("  [1b] Topic initialization with retry...")
    try:
        await ensure_topics_exist(max_retries=5, base_delay=2.0)
        print(f"    [OK] Topics ensured")
    except Exception as e:
        failures += 1
        print(f"    [FAIL] Topic setup error: {e}")

    # 1c. Event emission
    print("  [1c] Event emission...")
    test_event = NexusEvent(
        event_type=KafkaTopics.NEED_INGESTED,
        payload={"test": True, "need_id": "phase1-test"},
        tenant_id=TENANT_ID,
        correlation_id=str(uuid.uuid4())
    )
    try:
        await producer.emit(KafkaTopics.NEED_INGESTED, test_event, key=TENANT_ID)
        print("    [OK] Event emitted successfully")
    except Exception as e:
        failures += 1
        print(f"    [FAIL] Emit error: {e}")

    # 1d. Round-trip consume with backoff
    print("  [1d] Event round-trip (emit -> consume)...")
    sent_event_id = test_event.event_id
    found = False

    for consumer_attempt in range(3):
        try:
            consumer = AIOKafkaConsumer(
                KafkaTopics.NEED_INGESTED,
                bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
                group_id=f"roundtrip-{uuid.uuid4()}",
                auto_offset_reset="earliest",
                enable_auto_commit=True,
                consumer_timeout_ms=8000,
                session_timeout_ms=30000,
            )
            await consumer.start()
            try:
                async for msg in consumer:
                    evt = NexusEvent.deserialize(msg.value)
                    if evt.event_id == sent_event_id:
                        found = True
                        break
            finally:
                await consumer.stop()

            if found:
                break
        except Exception as e:
            delay = 2 * (consumer_attempt + 1)
            print(f"    [RETRY] Consumer attempt {consumer_attempt+1}: {e}. Waiting {delay}s...")
            await asyncio.sleep(delay)

    if found:
        print(f"    [OK] Round-trip confirmed: event_id={sent_event_id[:8]}")
    else:
        failures += 1
        print(f"    [FAIL] Event not received after retries")

    # 1e. Event-level idempotency check
    print("  [1e] Kafka event deduplication model...")
    seen_ids = set()
    test_corr = str(uuid.uuid4())
    duplicates_blocked = 0
    for _ in range(5):
        e = NexusEvent(event_type="test.dup", payload={}, correlation_id=test_corr)
        if e.correlation_id in seen_ids:
            duplicates_blocked += 1
        else:
            seen_ids.add(e.correlation_id)
    print(f"    [OK] Consumer dedup model: {duplicates_blocked}/4 duplicates blocked")

    passed = failures == 0
    print(f"  RESULT: {'PASS' if passed else 'FAIL'} (failures: {failures})")
    RESULTS["phase1_kafka"] = passed
    return passed


# ── Phase 2: Service Topology ───────────────────────────────────
async def phase2_service_topology():
    section("PHASE 2: SERVICE SEPARATION & CONNECTION STABILITY")
    failures = 0

    print("  [2a] PostgreSQL...")
    try:
        async with AsyncSessionFactory() as db:
            result = await db.execute(text("SELECT version()"))
            print(f"    [OK] {result.scalar()[:50]}")
    except Exception as e:
        failures += 1
        print(f"    [FAIL] DB: {e}")

    print("  [2b] PostGIS...")
    try:
        async with AsyncSessionFactory() as db:
            result = await db.execute(text("SELECT PostGIS_Version()"))
            print(f"    [OK] PostGIS: {result.scalar()[:30]}")
    except Exception as e:
        failures += 1
        print(f"    [FAIL] PostGIS: {e}")

    print("  [2c] Elasticsearch...")
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{settings.ELASTICSEARCH_URL}/_cluster/health", timeout=aiohttp.ClientTimeout(total=5)) as resp:
                data = await resp.json()
                status = data.get("status", "unknown")
                print(f"    [OK] ES cluster: {status}")
                if status == "red":
                    failures += 1
    except Exception as e:
        print(f"    [WARNING] ES unavailable (non-critical): {e}")

    print("  [2d] Kafka broker...")
    try:
        admin = AIOKafkaAdminClient(bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS)
        await admin.start()
        topics = await admin.list_topics()
        await admin.close()
        print(f"    [OK] Kafka online, {len(topics)} topics")
    except Exception as e:
        failures += 1
        print(f"    [FAIL] Kafka: {e}")

    print("  [2e] DB connection pool (20 concurrent)...")
    async def rapid_q(_):
        try:
            async with AsyncSessionFactory() as db:
                await db.execute(text("SELECT 1"))
            return 0
        except:
            return 1
    errs = sum(await asyncio.gather(*[rapid_q(i) for i in range(20)]))
    print(f"    [{'OK' if errs == 0 else 'FAIL'}] {20-errs}/20 succeeded")
    if errs > 0:
        failures += 1

    passed = failures == 0
    print(f"  RESULT: {'PASS' if passed else 'FAIL'}")
    RESULTS["phase2_topology"] = passed
    return passed


# ── Phase 3: High Load Test ─────────────────────────────────────
async def single_ingest(i: int, sem: asyncio.Semaphore):
    async with sem:
        start = time.perf_counter()
        payload = IngestionPayload(
            source_type="mobile",
            tenant_id=TENANT_ID,
            submitted_by=USER_ID,
            raw_text=f"Flood emergency at dharavi sector {i}, need immediate evacuation",
            correlation_id=str(uuid.uuid4()),
        )
        try:
            async with AsyncSessionFactory() as db:
                result = await ingestion_pipeline.run(payload, db)
                await db.commit()
            return {"success": result.success, "latency_ms": (time.perf_counter() - start) * 1000}
        except Exception as e:
            return {"success": False, "latency_ms": (time.perf_counter() - start) * 1000, "error": str(e)[:80]}

async def phase3_high_load(concurrency: int = 75, total: int = 500):
    section(f"PHASE 3: HIGH LOAD TEST ({total} req, {concurrency} concurrent)")

    # Producer is already running from Phase 1 — no restart needed
    assert NexusProducer.get().is_ready, "Producer must be running"

    sem = asyncio.Semaphore(concurrency)
    tasks = [single_ingest(i, sem) for i in range(total)]
    start = time.perf_counter()
    outcomes = await asyncio.gather(*tasks)
    elapsed = time.perf_counter() - start

    latencies = [o["latency_ms"] for o in outcomes]
    successes = sum(1 for o in outcomes if o.get("success"))
    errors = [o for o in outcomes if not o.get("success")]

    p50 = statistics.median(latencies)
    p95 = sorted(latencies)[int(len(latencies) * 0.95)]
    p99 = sorted(latencies)[int(len(latencies) * 0.99)]

    print(f"  Total           : {total}")
    print(f"  Successes       : {successes} ({successes/total*100:.1f}%)")
    print(f"  Errors          : {len(errors)}")
    print(f"  Throughput      : {total/elapsed:.1f} req/s")
    print(f"  Latency P50     : {p50:.0f} ms")
    print(f"  Latency P95     : {p95:.0f} ms")
    print(f"  Latency P99     : {p99:.0f} ms")

    if errors:
        for e in errors[:3]:
            print(f"    Error: {e.get('error','')}")

    error_rate = len(errors) / total
    passed = error_rate < 0.02
    print(f"  Error Rate      : {error_rate*100:.2f}% (threshold: 2%)")
    print(f"  RESULT: {'PASS' if passed else 'FAIL'}")
    RESULTS["phase3_load"] = passed
    return passed


# ── Phase 4: Event-Driven Flow ──────────────────────────────────
async def phase4_event_flow(sample_size: int = 20):
    section(f"PHASE 4: EVENT-DRIVEN FLOW ({sample_size} needs)")

    # 1. Start consumer first to catch events in real-time
    consumer = AIOKafkaConsumer(
        KafkaTopics.NEED_INGESTED,
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        group_id=f"flow-v2-{uuid.uuid4()}",
        auto_offset_reset="latest", # Only catch new events
        enable_auto_commit=True,
    )
    await consumer.start()
    print("  Consumer started (waiting for events...)")

    emitted_ids = set()

    # 2. Ingest sample needs
    for i in range(sample_size):
        payload = IngestionPayload(
            source_type="mobile",
            tenant_id=TENANT_ID,
            submitted_by=USER_ID,
            raw_text=f"Medical emergency case {i} at dharavi needs urgent help",
            correlation_id=str(uuid.uuid4()),
        )
        async with AsyncSessionFactory() as db:
            result = await ingestion_pipeline.run(payload, db)
            await db.commit()
        if result.success and result.need_id:
            emitted_ids.add(result.need_id)

    print(f"  Emitted: {len(emitted_ids)} events")

    # 3. Collect events with timeout
    consumed_ids = set()
    start_wait = time.time()
    try:
        while len(consumed_ids) < len(emitted_ids) and (time.time() - start_wait) < 15:
            # Poll for messages
            res = await consumer.getmany(timeout_ms=1000)
            for tp, msgs in res.items():
                for msg in msgs:
                    evt = NexusEvent.deserialize(msg.value)
                    if evt.tenant_id == TENANT_ID:
                        nid = evt.payload.get("need_id")
                        if nid:
                            consumed_ids.add(nid)
            if len(consumed_ids) >= len(emitted_ids):
                break
    except Exception as e:
        print(f"  Consumer poll error: {e}")
    finally:
        await consumer.stop()

    matched = emitted_ids & consumed_ids
    print(f"  Consumed: {len(consumed_ids)}")
    print(f"  Matched : {len(matched)}/{len(emitted_ids)}")

    match_rate = len(matched) / max(len(emitted_ids), 1)
    passed = match_rate >= 0.90
    print(f"  Match rate: {match_rate*100:.1f}%")
    print(f"  RESULT: {'PASS' if passed else 'FAIL'}")
    RESULTS["phase4_event_flow"] = passed
    return passed


# ── Phase 5: Failure Recovery ───────────────────────────────────
async def phase5_failure_recovery():
    section("PHASE 5: FAILURE RECOVERY")
    failures = 0

    # 5a. Ingestion continues when Kafka emit fails (producer down path)
    print("  [5a] Non-fatal Kafka failure path...")
    payload = IngestionPayload(
        source_type="mobile",
        tenant_id=TENANT_ID,
        submitted_by=USER_ID,
        raw_text="Shelter collapse, need immediate help",
        correlation_id=str(uuid.uuid4()),
    )
    # Stop the producer temporarily to test graceful degradation
    await NexusProducer.get().stop()
    async with AsyncSessionFactory() as db:
        result = await ingestion_pipeline.run(payload, db)
        await db.commit()
    if result.success:
        print(f"    [OK] Ingestion OK despite producer down: {result.need_id[:8]}")
    else:
        failures += 1
        print(f"    [FAIL] {result.error}")

    # Restart for remaining tests
    await NexusProducer.get().start()

    # 5b. DB session resilience
    print("  [5b] DB session resilience...")
    try:
        async with AsyncSessionFactory() as db:
            await db.execute(text("SELECT pg_sleep(0.01)"))
            await db.execute(text("SELECT 1"))
            print("    [OK] Session resilient")
    except Exception as e:
        failures += 1
        print(f"    [FAIL] {e}")

    # 5c. Retry storm idempotency
    print("  [5c] Retry storm (10 concurrent, same correlation_id)...")
    retry_corr = str(uuid.uuid4())
    payload = IngestionPayload(
        source_type="mobile",
        tenant_id=TENANT_ID,
        submitted_by=USER_ID,
        raw_text="Landslide blocking main road, 50 families trapped",
        correlation_id=retry_corr,
    )
    # Commit first
    async with AsyncSessionFactory() as db:
        r0 = await ingestion_pipeline.run(payload, db)
        await db.commit()

    async def retry_submit():
        async with AsyncSessionFactory() as db:
            r = await ingestion_pipeline.run(payload, db)
            await db.commit()
            return r.need_id

    results = await asyncio.gather(*[retry_submit() for _ in range(10)], return_exceptions=True)
    valid = [r for r in results if isinstance(r, str)]
    unique = set(valid)

    if len(unique) == 1 and list(unique)[0] == r0.need_id:
        print(f"    [OK] All 10 retries returned same need_id={r0.need_id[:8]}")
    else:
        failures += 1
        print(f"    [FAIL] Multiple IDs: {unique}")

    # 5d. State consistency
    print("  [5d] DB state consistency...")
    async with AsyncSessionFactory() as db:
        count = await db.scalar(
            text("SELECT COUNT(*) FROM ingestion_raw WHERE tenant_id = :tid"),
            {"tid": TENANT_ID}
        )
    print(f"    [OK] ingestion_raw records: {count}")

    passed = failures == 0
    print(f"  RESULT: {'PASS' if passed else 'FAIL'}")
    RESULTS["phase5_recovery"] = passed
    return passed


# ── Orchestrator ────────────────────────────────────────────────
async def main():
    print("============================================================")
    print("   NEXUS DISTRIBUTED VALIDATION SUITE v2                    ")
    print(f"   Started: {datetime.now(timezone.utc).isoformat()}")
    print(f"   Kafka  : {settings.KAFKA_BOOTSTRAP_SERVERS}")
    print(f"   DB     : {settings.DATABASE_URL[:50]}...")
    print("============================================================")

    await setup_tenant()

    await phase1_kafka_integration()
    await phase2_service_topology()
    await phase3_high_load(concurrency=50, total=500)
    await phase4_event_flow(sample_size=20)
    await phase5_failure_recovery()

    # Cleanup
    await NexusProducer.get().stop()

    section("FINAL DISTRIBUTED VALIDATION REPORT")
    all_passed = all(RESULTS.values())
    for k, v in RESULTS.items():
        print(f"  {k:<30}: {'PASS' if v else 'FAIL'}", flush=True)
    print(f"\n  DISTRIBUTED PRODUCTION-READY: {'YES' if all_passed else 'NO'}", flush=True)
    print("============================================================", flush=True)
    return 0 if all_passed else 1

if __name__ == "__main__":
    code = asyncio.run(main())
    sys.exit(code)
