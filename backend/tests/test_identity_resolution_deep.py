import asyncio
import sys
import os
from uuid import UUID
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

# Add root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from shared.config import get_settings
from services.registry.service import registry_service
from services.registry.schemas import IdentityResolutionRequest, ResolutionResult

settings = get_settings()

TENANT_A = "11111111-0000-0000-0000-000000000001"
LAT, LON = 19.04, 72.85

async def test_identity_resolution():
    engine = create_async_engine(settings.DATABASE_URL)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    print("--- IDENTITY RESOLUTION DEEP TEST ---")

    async with factory() as session:
        # Context: Actor is from Asha Welfare
        await session.execute(text(f"SELECT set_config('app.current_tenant_id', '{TENANT_A}', TRUE)"))

        # Scenario 1: Exact Match (already known in Asha)
        # We search exactly where House 1 is.
        req = IdentityResolutionRequest(
            latitude=LAT,
            longitude=LON,
            landmark_tags=["green tree", "blue door"], # Exact tags for House 1
            description_text="Cluster X House 42",
            family_size=3
        )
        
        print("\nTesting Resolution: High Confidence (Existing Household)")
        result: ResolutionResult = await registry_service.resolve_identity(session, req, TENANT_A)
        print(f"Status: {result.status}")
        print(f"Confidence: {result.confidence:.2f}")
        if result.household_id:
            print(f"Resolved Household ID: {result.household_id}")

        # Scenario 2: Cross-Tenant Match (Pragati NGO case)
        # We act as a coordinator who found a family that *might* be in another NGO.
        # But wait, RLS blocks resolution across tenants unless we have platform_admin or cross-tenant links.
        # The resolution service uses a subquery to check for global candidates.
        
        print("\nTesting Resolution: Physical Duplicate (Cross-Tenant Logic)")
        # Shift slightly to test fuzzy/geo
        req_fuzzy = IdentityResolutionRequest(
            latitude=LAT + 0.00005,
            longitude=LON + 0.00005,
            landmark_tags=["green tree"],
            description_text="Sector 4 slums"
        )
        result_fuzzy = await registry_service.resolve_identity(session, req_fuzzy, TENANT_A)
        print(f"Status: {result_fuzzy.status}")
        print(f"Confidence: {result_fuzzy.confidence:.2f}")
        
        # Scenario 3: New Household (Low confidence)
        print("\nTesting Resolution: No Match (New Household)")
        req_new = IdentityResolutionRequest(
            latitude=20.0, longitude=75.0, # Far away
            landmark_tags=["new city"],
            description_text="Brand new location"
        )
        result_new = await registry_service.resolve_identity(session, req_new, TENANT_A)
        print(f"Status: {result_new.status}")
        assert result_new.status == "new_household"

        # scenario 4: History append-only test
        print("\nVerifying History Append-Only rules...")
        hh_id_obj = UUID("33333333-0000-0000-0000-000000000001")
        tenant_a_obj = UUID(TENANT_A)
        # Create a history record via service
        await registry_service._emit_history(
            session, 
            hh_id_obj,
            tenant_a_obj,
            "vulnerability_updated",
            {"old_score": 0.5, "new_score": 0.8}
        )
        await session.commit()
        
        res = await session.execute(text("SELECT event_id FROM household_history WHERE event_type = 'vulnerability_updated'"))
        event_id = res.scalar()
        if event_id:
            try:
                # Try to UPDATE
                await session.execute(
                    text("UPDATE household_history SET event_payload = '{\"hacked\": true}' WHERE event_id = :eid"),
                    {"eid": event_id}
                )
                await session.commit()
                # Check if it was updated
                res = await session.execute(text("SELECT event_payload FROM household_history WHERE event_id = :eid"), {"eid": event_id})
                payload = res.scalar()
                if payload.get("hacked"):
                    print("❌ LEAK: History was UPDATED!")
                else:
                    print("✅ Success: Update rule blocked the modification.")
            except Exception as e:
                print(f"✅ Success: Update blocked with error: {str(e)}")

            try:
                # Try to DELETE
                await session.execute(text("DELETE FROM household_history WHERE event_id = :eid"), {"eid": event_id})
                await session.commit()
                res = await session.execute(text("SELECT COUNT(*) FROM household_history WHERE event_id = :eid"), {"eid": event_id})
                if res.scalar() == 0:
                    print("❌ LEAK: History was DELETED!")
                else:
                    print("✅ Success: Delete rule blocked the removal.")
            except Exception as e:
                print(f"✅ Success: Delete blocked with error: {str(e)}")

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(test_identity_resolution())
