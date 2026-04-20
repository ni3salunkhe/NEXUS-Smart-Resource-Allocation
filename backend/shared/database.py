from sqlalchemy.ext.asyncio import (
    AsyncSession, AsyncEngine,
    create_async_engine, async_sessionmaker
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text, event
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional
import logging

from .config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class Base(DeclarativeBase):
    pass


# ── Primary (read-write) engine ───────────────────────────────
engine: AsyncEngine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_timeout=settings.DB_POOL_TIMEOUT,
    pool_pre_ping=True,
    echo=settings.DEBUG,
)

# ── Read replica engine ───────────────────────────────────────
replica_engine: AsyncEngine = create_async_engine(
    settings.DATABASE_URL_REPLICA,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_pre_ping=True,
    echo=False,
)

AsyncSessionFactory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

ReplicaSessionFactory = async_sessionmaker(
    replica_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def _set_rls_context(
    session: AsyncSession,
    tenant_id: Optional[str],
    user_id: Optional[str],
    role: Optional[str],
) -> None:
    """
    Inject tenant + user context into PostgreSQL session.
    Row Level Security policies read these settings.
    """
    await session.execute(
        text("""
            SELECT
                set_config('app.current_tenant_id', :tenant_id, TRUE),
                set_config('app.current_user_id',   :user_id,   TRUE),
                set_config('app.current_role',       :role,      TRUE)
        """),
        {
            "tenant_id": str(tenant_id) if tenant_id else "",
            "user_id":   str(user_id)   if user_id   else "",
            "role":      role or "",
        }
    )


@asynccontextmanager
async def get_db_session(
    tenant_id: Optional[str] = None,
    user_id: Optional[str] = None,
    role: Optional[str] = None,
) -> AsyncGenerator[AsyncSession, None]:
    """
    Primary DB session with RLS context.
    Usage:
        async with get_db_session(tenant_id=tid, user_id=uid, role=r) as db:
            result = await db.execute(...)
    """
    async with AsyncSessionFactory() as session:
        async with session.begin():
            await _set_rls_context(session, tenant_id, user_id, role)
            try:
                yield session
            except Exception:
                await session.rollback()
                raise


@asynccontextmanager
async def get_replica_session(
    tenant_id: Optional[str] = None,
    user_id: Optional[str] = None,
    role: Optional[str] = None,
) -> AsyncGenerator[AsyncSession, None]:
    """
    Read-only replica session. Use for analytics and reports.
    """
    async with ReplicaSessionFactory() as session:
        await _set_rls_context(session, tenant_id, user_id, role)
        try:
            yield session
        except Exception:
            raise


# ── FastAPI dependency ────────────────────────────────────────
async def get_db(request) -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency. Extracts tenant/user from request state
    (populated by auth middleware).
    """
    tenant_id = getattr(request.state, "tenant_id", None)
    user_id   = getattr(request.state, "user_id",   None)
    role      = getattr(request.state, "role",       None)

    async with get_db_session(
        tenant_id=tenant_id,
        user_id=user_id,
        role=role
    ) as session:
        yield session


async def check_db_health() -> dict:
    try:
        async with AsyncSessionFactory() as session:
            result = await session.execute(text("SELECT 1"))
            return {"postgres": "ok", "version": str(result.scalar())}
    except Exception as e:
        return {"postgres": "error", "detail": str(e)}