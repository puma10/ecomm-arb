"""Pytest fixtures for database testing."""

from collections.abc import AsyncGenerator
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ecom_arb.api.app import app
from ecom_arb.db.base import Base, get_db


# Use SQLite in-memory for tests
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def test_db() -> AsyncGenerator[AsyncSession, None]:
    """Provide a test database session with isolated transactions.

    Creates an in-memory SQLite database, creates all tables,
    and yields a session. Overrides app's get_db dependency.
    """
    # Create test engine
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
    )

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Create session
    async_session_maker = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session_maker() as session:
        # Override app's get_db dependency
        async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

        app.dependency_overrides[get_db] = override_get_db

        try:
            yield session
        finally:
            # Clean up
            app.dependency_overrides.clear()
            await session.rollback()

    # Drop all tables after test
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()
