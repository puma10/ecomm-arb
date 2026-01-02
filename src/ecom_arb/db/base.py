"""Database connection and session management."""

from collections.abc import AsyncGenerator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from ecom_arb.config import get_settings


class Base(DeclarativeBase):
    """SQLAlchemy declarative base."""

    pass


settings = get_settings()

# SQLite needs special handling for concurrency
connect_args = {}
if "sqlite" in settings.database_url:
    connect_args = {
        "timeout": 30,  # Wait up to 30 seconds for lock
        "check_same_thread": False,
    }

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_pre_ping=True,
    connect_args=connect_args,
)


# Enable WAL mode for SQLite (better concurrency)
@event.listens_for(engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """Enable WAL mode and other SQLite optimizations."""
    if "sqlite" in settings.database_url:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")  # 30 second timeout
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()


async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for getting async database sessions."""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
