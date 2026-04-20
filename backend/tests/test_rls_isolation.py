import asyncio
import sys
import os
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

# Add root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from shared.config import get_settings

settings = get_settings()

TENANT_A = "11111111-0000-0000-0000-000000000001"
TENANT_B = "11111111-0000-0000-0000-000000000002"

async def test_rls():
    engine = create_async_engine(settings.DATABASE_URL)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    print("--- RLS ISOLATION TEST ---")

    async with factory() as session:
        # 1. ACT AS TENANT A
        print(f"Switching context to Tenant A ({TENANT_A})...")
        await session.execute(text(f"SELECT set_config('app.current_tenant_id', '{TENANT_A}', TRUE)"))
        
        # Count households
        result = await session.execute(text("SELECT COUNT(*) FROM households"))
        count_a = result.scalar()
        print(f"Tenant A sees {count_a} households.")

        # Try to see specific ID of Tenant B
        target_b_id = "33333333-0000-0000-0000-000000000003"
        result = await session.execute(
            text("SELECT location_description FROM households WHERE household_id = :hid"),
            {"hid": target_b_id}
        )
        row = result.fetchone()
        if row:
            print(f"❌ LEAK! Tenant A saw Tenant B's household: {row[0]}")
        else:
            print(f"✅ Success: Tenant A cannot see Tenant B's household {target_b_id}")

        # 2. ACT AS TENANT B
        print(f"\nSwitching context to Tenant B ({TENANT_B})...")
        await session.execute(text(f"SELECT set_config('app.current_tenant_id', '{TENANT_B}', TRUE)"))
        
        # Count households
        result = await session.execute(text("SELECT COUNT(*) FROM households"))
        count_b = result.scalar()
        print(f"Tenant B sees {count_b} households.")

        # 3. VERIFY APPEND-ONLY ON HISTORY
        print("\nVerifying Append-Only Ledger...")
        # Get a history record
        res = await session.execute(text("SELECT event_id FROM household_history LIMIT 1"))
        event_id = res.scalar()
        if event_id:
            try:
                await session.execute(
                    text("DELETE FROM household_history WHERE event_id = :eid"),
                    {"eid": event_id}
                )
                await session.commit()
                # Check if still there
                res = await session.execute(
                    text("SELECT COUNT(*) FROM household_history WHERE event_id = :eid"),
                    {"eid": event_id}
                )
                if res.scalar() > 0:
                    print("✅ Success: DELETE rule blocked the deletion (record still exists).")
                else:
                    print("❌ Fail: History record was deleted!")
            except Exception as e:
                print(f"✅ Success: Trigger/Rule blocked deletion with error: {str(e)}")
        else:
            print("⚠️ No history records found to test append-only rules.")

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(test_rls())
