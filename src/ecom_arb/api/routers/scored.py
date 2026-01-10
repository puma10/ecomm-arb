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
from ecom_arb.db.models import Product, ScoredProduct

router = APIRouter(prefix="/products", tags=["scored"])


def slugify(name: str) -> str:
    """Convert product name to URL-friendly slug."""
    import re
    slug = name.lower()
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)
    slug = re.sub(r'[\s_]+', '-', slug)
    slug = re.sub(r'-+', '-', slug)
    return slug.strip('-')[:100]


class ScoredProductListItem(BaseModel):
    """Scored product list item response."""

    id: UUID
    source_product_id: str
    source: str
    source_url: str | None
    name: str
    selling_price: Decimal
    category: str
    cogs: Decimal
    gross_margin: Decimal
    net_margin: Decimal
    # Shipping/logistics
    weight_grams: int | None
    shipping_days_min: int | None
    shipping_days_max: int | None
    warehouse_country: str | None
    # Supplier
    supplier_name: str | None
    inventory_count: int | None
    # Scoring
    points: int | None
    rank_score: Decimal | None
    recommendation: str
    # Association
    crawl_job_id: str | None
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
    monthly_search_volume: int | None
    keyword_analysis: dict[str, Any] | None

    # Amazon competitor data
    amazon_median_price: Decimal | None
    amazon_min_price: Decimal | None
    amazon_avg_review_count: int | None
    amazon_prime_percentage: Decimal | None
    amazon_search_results: dict[str, Any] | None

    # Shipping/logistics data (from supplier)
    weight_grams: int | None
    shipping_days_min: int | None
    shipping_days_max: int | None
    warehouse_country: str | None

    # Supplier data
    supplier_name: str | None
    inventory_count: int | None

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
    crawl_job_id: str | None = Query(
        None,
        description="Filter by crawl job ID",
    ),
    search: str | None = Query(
        None,
        description="Search products by name (case-insensitive)",
    ),
    limit: int = Query(20, ge=1, le=100, description="Maximum number of results"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    db: AsyncSession = Depends(get_db),
) -> ScoredProductListResponse:
    """List scored products with optional filtering.

    Results are sorted by created_at descending (most recent first).
    """
    # Build base query with filters
    def apply_filters(q):
        if recommendation:
            q = q.where(ScoredProduct.recommendation == recommendation)
        if crawl_job_id:
            q = q.where(ScoredProduct.crawl_job_id == crawl_job_id)
        if search:
            # Case-insensitive search on name
            q = q.where(ScoredProduct.name.ilike(f"%{search}%"))
        return q

    # Get total count
    count_query = apply_filters(select(ScoredProduct))
    count_result = await db.execute(count_query)
    total = len(count_result.scalars().all())

    # Get paginated results, sorted by created_at descending (most recent first)
    query = apply_filters(select(ScoredProduct))
    query = query.order_by(desc(ScoredProduct.created_at))
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

    # Use stored shipping data if available, otherwise use defaults
    ship_min = scored_product.shipping_days_min or 7
    ship_max = scored_product.shipping_days_max or 14
    has_fast = ship_max <= 10

    scoring_input = ScoringProduct(
        id=scored_product.source_product_id,
        name=scored_product.name,
        product_cost=float(scored_product.product_cost),
        shipping_cost=float(scored_product.shipping_cost),
        selling_price=float(scored_product.selling_price),
        category=category,
        requires_sizing=False,
        is_fragile=False,
        weight_grams=scored_product.weight_grams or 500,
        supplier_rating=4.8,  # Default value
        supplier_age_months=24,  # Default value
        supplier_feedback_count=1000,  # Default value
        shipping_days_min=ship_min,
        shipping_days_max=ship_max,
        has_fast_shipping=has_fast,
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


class ApproveProductRequest(BaseModel):
    """Request to approve a scored product for the storefront."""

    selling_price: Decimal | None = Field(None, description="Override selling price")
    compare_at_price: Decimal | None = Field(None, description="Compare-at price for discounts")


class ApproveProductResponse(BaseModel):
    """Response after approving a product."""

    success: bool
    product_id: UUID
    slug: str
    message: str


@router.post("/{product_id}/approve", response_model=ApproveProductResponse)
async def approve_product(
    product_id: UUID,
    request: ApproveProductRequest | None = None,
    db: AsyncSession = Depends(get_db),
) -> ApproveProductResponse:
    """Approve a scored product and add it to the storefront.

    Creates a new Product from the ScoredProduct data.
    """
    # Get the scored product
    result = await db.execute(
        select(ScoredProduct).where(ScoredProduct.id == product_id)
    )
    scored = result.scalar_one_or_none()

    if not scored:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scored product not found",
        )

    # Check if already approved (product exists with same source_product_id)
    existing = await db.execute(
        select(Product).where(Product.supplier_sku == scored.source_product_id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Product already approved and in storefront",
        )

    # Create the storefront product
    base_slug = slugify(scored.name)
    slug = base_slug

    # Ensure unique slug
    counter = 1
    while True:
        existing_slug = await db.execute(
            select(Product).where(Product.slug == slug)
        )
        if not existing_slug.scalar_one_or_none():
            break
        slug = f"{base_slug}-{counter}"
        counter += 1

    selling_price = request.selling_price if request and request.selling_price else scored.selling_price
    compare_at = request.compare_at_price if request else None

    product = Product(
        slug=slug,
        name=scored.name,
        description=f"Quality product sourced from {scored.source}.",
        price=selling_price,
        compare_at_price=compare_at,
        cost=scored.product_cost,
        images=[],  # Would need to fetch from source
        supplier_sku=scored.source_product_id,
        supplier_url=scored.source_url or "",
        shipping_cost=scored.shipping_cost,
        shipping_days_min=scored.shipping_days_min or 7,
        shipping_days_max=scored.shipping_days_max or 14,
        active=True,
    )

    db.add(product)
    await db.flush()
    await db.refresh(product)

    return ApproveProductResponse(
        success=True,
        product_id=product.id,
        slug=product.slug,
        message=f"Product approved and added to storefront as '{slug}'",
    )


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def reject_product(
    product_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Reject and delete a scored product.

    This removes the product from consideration.
    """
    result = await db.execute(
        select(ScoredProduct).where(ScoredProduct.id == product_id)
    )
    scored = result.scalar_one_or_none()

    if not scored:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scored product not found",
        )

    await db.delete(scored)
    await db.flush()
