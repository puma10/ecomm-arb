#!/usr/bin/env python3
"""Initialize the database with tables."""

import asyncio

from ecom_arb.db.base import Base, engine


async def init_db() -> None:
    """Create all tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Database initialized!")


if __name__ == "__main__":
    asyncio.run(init_db())
