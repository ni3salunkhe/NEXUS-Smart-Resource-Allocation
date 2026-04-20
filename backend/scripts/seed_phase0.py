"""
NEXUS Phase 0 — Dev Seed Script
Seeds: 2 NGO tenants, users per role, basic config
"""
import asyncio
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import text
import bcrypt
from shared.config import get_settings

settings = get_settings()

TENANTS = [
    {
        "tenant_id": "11111111-0000-0000-0000-000000000001",
        "name": "Asha Welfare Trust",
        "slug": "asha-welfare",
        "contact_email": "coordinator@asha.org",
        "plan_tier": "standard",
    },
    {
        "tenant_id": "11111111-0000-0000-0000-000000000002",
        "name": "Pragati NGO Mumbai",
        "slug": "pragati-mumbai",
        "contact_email": "coordinator@pragati.org",
        "plan_tier": "standard",
    },
]

USERS = [
    # Asha Welfare
    {
        "user_id": "22222222-0000-0000-0000-000000000001",
        "tenant_id": "11111111-0000-0000-0000-000000000001",
        "email": "admin@asha.org",
        "password": "test_admin_123",
        "role": "ngo_admin",
        "preferred_language": "en",
    },
    {
        "user_id": "22222222-0000-0000-0000-000000000002",
        "tenant_id": "11111111-0000-0000-0000-000000000001",
        "email": "coord@asha.org",
        "password": "test_coord_123",
        "role": "coordinator",
        "preferred_language": "hi",
    },
    {
        "user_id": "22222222-0000-0000-0000-000000000003",
        "tenant_id": "11111111-0000-0000-0000-000000000001",
        "email": "field1@asha.org",
        "password": "test_field_123",
        "role": "field_worker",
        "preferred_language": "mr",
    },
    {
        "user_id": "22222222-0000-0000-0000-000000000004",
        "tenant_id": "11111111-0000-0000-0000-000000000001",
        "email": "funder@asha.org",
        "password": "test_funder_123",
        "role": "funder_readonly",
        "preferred_language": "en",
    },
    # Pragati NGO
    {
        "user_id": "22222222-0000-0000-0000-000000000005",
        "tenant_id": "11111111-0000-0000-0000-000000000002",
        "email": "admin@pragati.org",
        "password": "test_admin_123",
        "role": "ngo_admin",
        "preferred_language": "mr",
    },
    {
        "user_id": "22222222-0000-0000-0000-000000000006",
        "tenant_id": "11111111-0000-0000-0000-000000000002",
        "email": "coord@pragati.org",
        "password": "test_coord_123",
        "role": "coordinator",
        "preferred_language": "hi",
    },
]


async def seed():
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as session:
        async with session.begin():
            # No RLS for seed (admin operation)
            await session.execute(text("SELECT set_config('app.current_role', 'platform_admin', TRUE)"))

            print("Seeding tenants...")
            for t in TENANTS:
                await session.execute(
                    text("""
                        INSERT INTO tenants(tenant_id, name, slug, contact_email, plan_tier)
                        VALUES (:tenant_id, :name, :slug, :contact_email, :plan_tier)
                        ON CONFLICT (slug) DO NOTHING
                    """),
                    t
                )
            print(f"  {len(TENANTS)} tenants seeded.")

            print("Seeding users...")
            for u in USERS:
                await session.execute(
                    text("""
                        INSERT INTO users(user_id, tenant_id, email, password_hash, role, preferred_language)
                        VALUES (:user_id, :tenant_id, :email, :pw_hash, :role, :lang)
                        ON CONFLICT (tenant_id, email) DO NOTHING
                    """),
                    {
                        "user_id": u["user_id"],
                        "tenant_id": u["tenant_id"],
                        "email": u["email"],
                        "pw_hash": bcrypt.hashpw(u["password"].encode(), bcrypt.gensalt()).decode("utf-8"),
                        "role": u["role"],
                        "lang": u["preferred_language"],
                    }
                )
            print(f"  {len(USERS)} users seeded.")

    await engine.dispose()
    print("\nSeed complete.")
    print("\nTest credentials:")
    for u in USERS:
        print(f"  {u['role']:16s}  {u['email']:30s}  password: {u['password']}")


if __name__ == "__main__":
    asyncio.run(seed())