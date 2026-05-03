import asyncio
import bcrypt
from sqlalchemy import text
from shared.database import AsyncSessionFactory
from shared.config import get_settings

async def reset_admin():
    settings = get_settings()
    async with AsyncSessionFactory() as db:
        pw_hash = bcrypt.hashpw(settings.SYSTEM_ADMIN_PASSWORD.encode(), bcrypt.gensalt()).decode()
        await db.execute(
            text("UPDATE users SET email = :email, password_hash = :hash WHERE role = 'platform_admin'"),
            {"email": settings.SYSTEM_ADMIN_EMAIL, "hash": pw_hash}
        )
        await db.commit()
        print(f"Admin reset to {settings.SYSTEM_ADMIN_EMAIL}")

if __name__ == "__main__":
    asyncio.run(reset_admin())
