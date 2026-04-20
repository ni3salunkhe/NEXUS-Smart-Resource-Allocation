import asyncio, os, sys, traceback
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from sqlalchemy import text
from services.ingestion.pipeline import ingestion_pipeline, IngestionPayload
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from shared.config import get_settings

async def test_case_a():
    engine = create_async_engine(get_settings().DATABASE_URL.replace("postgresql+asyncpg", "postgresql+asyncpg"), echo=False)
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with SessionLocal() as db:
        await db.execute(text("SELECT set_config('app.current_tenant_id', '11111111-0000-0000-0000-000000000001', TRUE)"))
        payload = IngestionPayload(
            source_type="mobile",
            tenant_id="11111111-0000-0000-0000-000000000001",
            submitted_by="22222222-0000-0000-0000-000000000001",
            raw_text="Family of 4 needs ration.",
            prefilled_category="food",
            prefilled_beneficiary=4
        )
        try:
            res = await ingestion_pipeline.run(payload, db)
            with open("myerror.txt", "w") as f:
                f.write(f"SUCCESS: {res.success}, ERR: {res.error}")
        except Exception as e:
            with open("myerror.txt", "w") as f:
                f.write(traceback.format_exc())

if __name__ == "__main__":
    asyncio.run(test_case_a())
