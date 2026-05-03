import asyncio
import logging
import sys
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from elasticsearch import AsyncElasticsearch
from motor.motor_asyncio import AsyncIOMotorClient
import redis.asyncio as redis
from aiokafka import AIOKafkaProducer

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("SystemValidator")

async def check_postgres():
    try:
        # PgBouncer port 6432
        engine = create_async_engine("postgresql+asyncpg://nexus:nexus_secret@localhost:6432/nexus")
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return "Postgres/PgBouncer", "OK", ""
    except Exception as e:
        return "Postgres/PgBouncer", "FAIL", str(e)

async def check_elasticsearch():
    try:
        es = AsyncElasticsearch(["http://localhost:9200"])
        # Ping might fail if ES is still booting or misconfigured
        if await es.ping():
            return "Elasticsearch", "OK", ""
        else:
            return "Elasticsearch", "FAIL", "Ping returned False"
    except Exception as e:
        return "Elasticsearch", "FAIL", str(e)

async def check_mongodb():
    try:
        client = AsyncIOMotorClient("mongodb://nexus:nexus_secret@localhost:27017/nexus_ingestion?authSource=admin")
        await client.admin.command('ping')
        return "MongoDB", "OK", ""
    except Exception as e:
        return "MongoDB", "FAIL", str(e)

async def check_redis():
    try:
        r = redis.from_url("redis://localhost:6379/0")
        await r.ping()
        return "Redis", "OK", ""
    except Exception as e:
        return "Redis", "FAIL", str(e)

async def check_kafka():
    try:
        # AIOKafkaProducer starts the discovery process
        producer = AIOKafkaProducer(bootstrap_servers="localhost:9092")
        await asyncio.wait_for(producer.start(), timeout=10.0)
        await producer.stop()
        return "Kafka", "OK", ""
    except Exception as e:
        return "Kafka", "FAIL", str(e)

async def run_audit():
    logger.info("INITIATING NEXUS INFRASTRUCTURE AUDIT...")
    tasks = [
        check_postgres(),
        check_elasticsearch(),
        check_mongodb(),
        check_redis(),
        check_kafka()
    ]
    results = await asyncio.gather(*tasks)
    
    print("\n" + "="*60)
    print(f"{'SERVICE':<25} | {'STATUS':<10} | {'ERROR'}")
    print("-" * 60)
    for service, status, error in results:
        err_msg = (error[:45] + '...') if len(error) > 45 else error
        print(f"{service:<25} | {status:<10} | {err_msg}")
    print("="*60 + "\n")

    if all(r[1] == "OK" for r in results):
        logger.info("AUDIT SUCCESS: ALL CRITICAL SERVICES REACHABLE")
    else:
        logger.error("AUDIT WARNING: ONE OR MORE INTEGRATION FAILURES DETECTED")

if __name__ == "__main__":
    asyncio.run(run_audit())
