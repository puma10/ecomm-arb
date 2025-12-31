"""Scored Products API endpoints.

Endpoints for viewing and managing product scores from the scoring pipeline.

Endpoints:
- GET /products/scored - list scored products (filterable by recommendation)
- GET /products/{id}/score - get score details for a product
- POST /products/{id}/rescore - trigger rescore for a product
"""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ecom_arb.db.base import get_db
from ecom_arb.db.models import ScoredProduct

router = APIRouter(prefix="/products", tags=["scored"])


class ScoredProductListItem(BaseModel):
    """Scored product list item response."""

    id: UUID
    source_product_id: str
    source: str
    name: str
    selling_price: Decimal
    category: str
    gross_margin: Decimal
    net_margin: Decimal
    points: int | None
    rank_score: Decimal | None
    recommendation: str
    created_at: datetime

    class Config:
        from_attributes = True


class ScoredProductListResponse(BaseModel):
    """Response for list of scored products."""

    items: list[ScoredProductListItem]
    total: int
    limit: int
    offset: int


class ScoredProductResponse(BaseModel):
    """Full scored product response with all details."""

    id: UUID
    source_product_id: str
    source: str
    source_url: str | None
    name: str

    # Pricing inputs
    product_cost: Decimal
    shipping_cost: Decimal
    selling_price: Decimal
    category: str
    estimated_cpc: Decimal

    # Calculated financials
    cogs: Decimal
    gross_margin: Decimal
    net_margin: Decimal
    max_cpc: Decimal
    cpc_buffer: Decimal

    # Filter result
    passed_filters: bool
    rejection_reasons: list[str]

    # Point scoring
    points: int | None
    point_breakdown: dict[str, Any] | None
    rank_score: Decimal | None

    # Recommendation
    recommendation: str

    # Timestamps
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


@router.get("/scored", response_model=ScoredProductListResponse)
async def list_scored_products(
    recommendation: str | None = Query(
        None,
        description="Filter by recommendation (STRONG BUY, VIABLE, MARGINAL, WEAK, REJECT)",
    ),
    limit: int = Query(20, ge=1, le=100, description="Maximum number of results"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    db: AsyncSession = Depends(get_db),
) -> ScoredProductListResponse:
    """List scored products with optional filtering.

    Results are sorted by rank_score descending (highest ranked first).
    """
    # Build query
    query = select(ScoredProduct)

    if recommendation:
        query = query.where(ScoredProduct.recommendation == recommendation)

    # Get total count
    count_query = select(ScoredProduct)
    if recommendation:
        count_query = count_query.where(ScoredProduct.recommendation == recommendation)
    count_result = await db.execute(count_query)
    total = len(count_result.scalars().all())

    # Get paginated results, sorted by rank_score descending
    query = query.order_by(desc(ScoredProduct.rank_score))
    query = query.offset(offset).limit(limit)

    result = await db.execute(query)
    products = result.scalars().all()

    return ScoredProductListResponse(
        items=[ScoredProductListItem.model_validate(p) for p in products],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{product_id}/score", response_model=ScoredProductResponse)
async def get_product_score(
    product_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> ScoredProduct:
    """Get score details for a specific product."""
    result = await db.execute(
        select(ScoredProduct).where(ScoredProduct.id == product_id)
    )
    product = result.scalar_one_or_none()

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scored product not found",
        )

    return product


@router.post("/{product_id}/rescore", response_model=ScoredProductResponse)
async def rescore_product(
    product_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> ScoredProduct:
    """Trigger a rescore for a specific product.

    This recalculates all scoring metrics based on current data.
    """
    from ecom_arb.scoring.models import Product as ScoringProduct
    from ecom_arb.scoring.models import ProductCategory
    from ecom_arb.scoring.scorer import score_product

    # Get the scored product
    result = await db.execute(
        select(ScoredProduct).where(ScoredProduct.id == product_id)
    )
    scored_product = result.scalar_one_or_none()

    if not scored_product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scored product not found",
        )

    # Convert to scoring input model
    # Note: Some fields have defaults since ScoredProduct doesn't store all input data
    try:
        category = ProductCategory(scored_product.category)
    except ValueError:
        category = ProductCategory.HOME_DECOR  # Default fallback

    scoring_input = ScoringProduct(
        id=scored_product.source_product_id,
        name=scored_product.name,
        product_cost=float(scored_product.product_cost),
        shipping_cost=float(scored_product.shipping_cost),
        selling_price=float(scored_product.selling_price),
        category=category,
        requires_sizing=False,
        is_fragile=False,
        weight_grams=500,  # Default value
        supplier_rating=4.8,  # Default value
        supplier_age_months=24,  # Default value
        supplier_feedback_count=1000,  # Default value
        shipping_days_min=7,
        shipping_days_max=14,
        has_fast_shipping=True,
        estimated_cpc=float(scored_product.estimated_cpc),
        monthly_search_volume=1000,  # Default value
        amazon_prime_exists=False,  # Default value
        amazon_review_count=0,  # Default value
        source=scored_product.source,
        source_url=scored_product.source_url,
    )

    # Run scoring
    score_result = score_product(scoring_input)

    # Update scored product with new results
    scored_product.cogs = Decimal(str(score_result.cogs))
    scored_product.gross_margin = Decimal(str(score_result.gross_margin))
    scored_product.net_margin = Decimal(str(score_result.net_margin))
    scored_product.max_cpc = Decimal(str(score_result.max_cpc))
    scored_product.cpc_buffer = Decimal(str(score_result.cpc_buffer))
    scored_product.passed_filters = score_result.passed_filters
    scored_product.rejection_reasons = score_result.rejection_reasons
    scored_product.points = score_result.points
    scored_product.point_breakdown = score_result.point_breakdown
    scored_product.rank_score = (
        Decimal(str(score_result.rank_score)) if score_result.rank_score else None
    )
    scored_product.recommendation = score_result.recommendation

    await db.flush()
    await db.refresh(scored_product)

    return scored_product
