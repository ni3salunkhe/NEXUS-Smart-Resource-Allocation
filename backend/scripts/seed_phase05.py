import asyncio
import sys
import os
from uuid import UUID
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

# Add root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from shared.config import get_settings

settings = get_settings()

TENANTS = [
    {
        "tenant_id": "11111111-0000-0000-0000-000000000001",
        "name": "Asha Welfare Trust",
        "slug": "asha-welfare",
    },
    {
        "tenant_id": "11111111-0000-0000-0000-000000000002",
        "name": "Pragati NGO Mumbai",
        "slug": "pragati-mumbai",
    },
]

# Shared coordinates for Slum Cluster X (Dharavi-ish)
LAT, LON = 19.04, 72.85

HOUSEHOLDS = [
    # Asha Welfare House 1
    {
        "household_id": "33333333-0000-0000-0000-000000000001",
        "tenant_id": "11111111-0000-0000-0000-000000000001",
        "ward_id": "WARD-L",
        "location_description": "Cluster X, House 42, near Green Tree",
        "landmark_tags": ["green tree", "blue door"],
        "lat": LAT, "lon": LON,
        "dwelling": "temporary",
    },
    # Asha Welfare House 2 (Physically close to House 1)
    {
        "household_id": "33333333-0000-0000-0000-000000000002",
        "tenant_id": "11111111-0000-0000-0000-000000000001",
        "ward_id": "WARD-L",
        "location_description": "Cluster X, House 44, across Green Tree",
        "landmark_tags": ["green tree", "red fence"],
        "lat": LAT + 0.0001, "lon": LON + 0.0001,
        "dwelling": "semi_permanent",
    },
    # Pragati NGO House 3 (Same physical family as Asha House 1, but different tenant)
    {
        "household_id": "33333333-0000-0000-0000-000000000003",
        "tenant_id": "11111111-0000-0000-0000-000000000002",
        "ward_id": "WARD-L",
        "location_description": "Sector 4, near the Green Tree",
        "landmark_tags": ["green tree"],
        "lat": LAT, "lon": LON,
        "dwelling": "temporary",
    },
]

MEMBERS = [
    # Members for House 1
    {"hh_id": HOUSEHOLDS[0]["household_id"], "role": "head", "age": "adult", "gender": "male", "primary": True},
    {"hh_id": HOUSEHOLDS[0]["household_id"], "role": "spouse", "age": "adult", "gender": "female", "primary": False},
    {"hh_id": HOUSEHOLDS[0]["household_id"], "role": "child", "age": "child", "gender": "female", "primary": False},
    # Members for House 2
    {"hh_id": HOUSEHOLDS[1]["household_id"], "role": "head", "age": "elderly", "gender": "female", "primary": True},
    # Members for House 3 (Similar to House 1)
    {"hh_id": HOUSEHOLDS[2]["household_id"], "role": "head", "age": "adult", "gender": "male", "primary": True},
]

async def seed_phase05():
    engine = create_async_engine(settings.DATABASE_URL)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as session:
        async with session.begin():
            # Bypass RLS for seeding
            await session.execute(text("SELECT set_config('app.current_role', 'platform_admin', TRUE)"))

            print("Seeding Households...")
            for hh in HOUSEHOLDS:
                await session.execute(
                    text("""
                        INSERT INTO households (
                            household_id, tenant_id, ward_id, 
                            location_geo, location_description, landmark_tags,
                            dwelling_type, status
                        ) VALUES (
                            :household_id, :tenant_id, :ward_id,
                            ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography,
                            :location_description, :landmark_tags,
                            :dwelling, 'active'
                        ) ON CONFLICT (household_id) DO NOTHING
                    """),
                    hh
                )

            print("Seeding Members...")
            for m in MEMBERS:
                await session.execute(
                    text("""
                        INSERT INTO household_members (
                            household_id, role_in_household, age_bracket, gender, is_primary_contact
                        ) VALUES (
                            :hh_id, :role, :age, :gender, :primary
                        )
                    """),
                    m
                )
    
    await engine.dispose()
    print("Phase 0.5 Seeding Complete.")

if __name__ == "__main__":
    asyncio.run(seed_phase05())
