import asyncio
import logging
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from elasticsearch import AsyncElasticsearch
from motor.motor_asyncio import AsyncIOMotorClient
import redis.asyncio as redis
from aiokafka import AIOKafkaProducer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("infra_check")

# Mock settings for check
DB_URL = "postgresql+asyncpg://nexus:nexus_secret@localhost:6432/nexus"
ES_URL = "http://localhost:9200"
MONGO_URL = "mongodb://nexus:nexus_secret@localhost:27017/nexus_ingestion?authSource=admin"
REDIS_URL = "redis://localhost:6379/0"
KAFKA_SERVERS = "localhost:9092"

async def check_postgres():
    try:
        engine = create_async_engine(DB_URL)
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("✅ Postgres/PgBouncer: OK")
        return True
    except Exception as e:
        logger.error(f"❌ Postgres: FAILED ({e})")
        return False

async def check_elasticsearch():
    try:
        es = AsyncElasticsearch([ES_URL])
        if await es.ping():
            logger.info("✅ Elasticsearch: OK")
            return True
        else:
            logger.error("❌ Elasticsearch: PING FAILED")
            return False
    except Exception as e:
        logger.error(f"❌ Elasticsearch: FAILED ({e})")
        return False

async def check_mongodb():
    try:
        client = AsyncIOMotorClient(MONGO_URL)
        await client.admin.command('ping')
        logger.info("✅ MongoDB: OK")
        return True
    except Exception as e:
        logger.error(f"❌ MongoDB: FAILED ({e})")
        return False

async def check_redis():
    try:
        r = redis.from_url(REDIS_URL)
        await r.ping()
        logger.info("✅ Redis: OK")
        return True
    except Exception as e:
        logger.error(f"❌ Redis: FAILED ({e})")
        return False

async def check_kafka():
    try:
        producer = AIOKafkaProducer(bootstrap_servers=KAFKA_SERVERS)
        await producer.start()
        await producer.stop()
        logger.info("✅ Kafka: OK")
        return True
    except Exception as e:
        logger.error(f"❌ Kafka: FAILED ({e})")
        return False

async def main():
    logger.info("Starting Infrastructure Connectivity Audit...")
    results = await asyncio.gather(
        check_postgres(),
        check_elasticsearch(),
        check_mongodb(),
        check_redis(),
        check_kafka()
    )
    if all(results):
        logger.info("\n🏆 ALL INFRASTRUCTURE SERVICES ARE REACHABLE")
    else:
        logger.error("\n⚠️ ONE OR MORE SERVICES ARE UNREACHABLE")

if __name__ == "__main__":
    asyncio.run(main())
