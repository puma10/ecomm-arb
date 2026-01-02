"""FastAPI application."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

# Configure logging
logging.basicConfig(level=logging.INFO)
logging.getLogger("ecom_arb").setLevel(logging.DEBUG)
from fastapi.middleware.cors import CORSMiddleware

from ecom_arb.api.routers import admin, checkout, crawl, exclusions, orders, products, scored
from ecom_arb.config import get_settings
from ecom_arb.db.base import Base, engine

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create database tables on startup."""
    # Import all models to ensure they're registered with Base
    from ecom_arb.db import models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield

app = FastAPI(
    title="ecom-arb API",
    description="E-commerce arbitrage storefront API",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/api/docs" if settings.debug else None,
    redoc_url="/api/redoc" if settings.debug else None,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
# scored router must come before products to avoid /{slug} catching /scored
app.include_router(scored.router, prefix=settings.api_prefix)
app.include_router(products.router, prefix=settings.api_prefix)
app.include_router(checkout.router, prefix=settings.api_prefix)
app.include_router(orders.router, prefix=settings.api_prefix)
app.include_router(admin.router, prefix=settings.api_prefix)
app.include_router(crawl.router, prefix=settings.api_prefix)
app.include_router(exclusions.router, prefix=settings.api_prefix)


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy"}
