"""Admin API endpoints for pipeline operations.

Endpoints:
- POST /admin/discover - Run product discovery and scoring
- POST /admin/seed-demo - Seed demo scored products for testing
- GET /admin/settings - Get scoring settings
- PUT /admin/settings - Update scoring settings
"""

import logging
import os
import random
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ecom_arb.db.base import get_db
from ecom_arb.db.models import ScoredProduct, ScoringSettings
from ecom_arb.scoring.models import Product, ProductCategory, ScoringConfig
from ecom_arb.scoring.scorer import score_product

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


class DiscoverRequest(BaseModel):
    """Request to discover and score products."""

    keywords: list[str] = Field(
        default=["garden tools", "kitchen gadgets", "pet supplies"],
        description="Keywords to search for products",
    )
    limit_per_keyword: int = Field(
        default=10, ge=1, le=50, description="Max products per keyword"
    )


class DiscoverResponse(BaseModel):
    """Response from discovery operation."""

    status: str
    message: str
    discovered: int = 0
    scored: int = 0
    passed: int = 0


class SeedDemoRequest(BaseModel):
    """Request to seed demo products."""

    count: int = Field(default=20, ge=1, le=100, description="Number of demo products")


class SeedDemoResponse(BaseModel):
    """Response from seeding demo products."""

    status: str
    message: str
    created: int


# Demo product templates for seeding
# Format: (name, category, product_cost, selling_price)
# Filters require: min $50 price, 65% gross margin, max $0.75 CPC, 1.5x CPC buffer
DEMO_PRODUCTS = [
    # Strong candidates - high margin, good price
    ("Premium Garden Tool Set 10pc", ProductCategory.GARDEN, 12.0, 89.99),
    ("Professional Kitchen Knife Set", ProductCategory.KITCHEN, 15.0, 99.99),
    ("Deluxe Pet Grooming Kit", ProductCategory.PET, 10.0, 79.99),
    ("Smart LED Desk Lamp Pro", ProductCategory.OFFICE, 14.0, 89.99),
    ("Ultra Camping Hammock Deluxe", ProductCategory.OUTDOOR, 11.0, 84.99),
    # Good candidates
    ("Leather Bound Journal Set", ProductCategory.CRAFTS, 8.0, 69.99),
    ("Heavy Duty Drill Kit", ProductCategory.TOOLS, 18.0, 119.99),
    ("Boho Wall Decor Collection", ProductCategory.HOME_DECOR, 9.0, 74.99),
    ("Premium Silicone Bakeware Set", ProductCategory.KITCHEN, 7.0, 59.99),
    ("Dog Training Master Kit", ProductCategory.PET, 6.0, 54.99),
    # Medium candidates
    ("Ergonomic Chair Cushion Pro", ProductCategory.OFFICE, 10.0, 69.99),
    ("Hiking Backpack 50L Pro", ProductCategory.OUTDOOR, 16.0, 99.99),
    ("Complete Embroidery Kit", ProductCategory.CRAFTS, 9.0, 64.99),
    ("Professional Screwdriver Set", ProductCategory.TOOLS, 12.0, 79.99),
    ("Modern Floating Shelf Set", ProductCategory.HOME_DECOR, 11.0, 74.99),
    # Marginal candidates - tighter margins
    ("Cast Iron Cookware Set", ProductCategory.KITCHEN, 20.0, 89.99),
    ("Interactive Cat Toy Bundle", ProductCategory.PET, 12.0, 59.99),
    ("Solar Garden Light Set 12pc", ProductCategory.GARDEN, 15.0, 79.99),
    ("Desk Organizer System", ProductCategory.OFFICE, 13.0, 64.99),
    ("Camping Stove Portable Pro", ProductCategory.OUTDOOR, 18.0, 84.99),
    # Weak candidates - lower margins
    ("Artist Watercolor Set", ProductCategory.CRAFTS, 16.0, 69.99),
    ("Mechanic Tool Set 50pc", ProductCategory.TOOLS, 25.0, 99.99),
    ("Decorative Pillow Collection", ProductCategory.HOME_DECOR, 18.0, 74.99),
    ("Bamboo Kitchen Set", ProductCategory.KITCHEN, 14.0, 59.99),
    ("Smart Pet Feeder System", ProductCategory.PET, 22.0, 89.99),
]


@router.post("/discover", response_model=DiscoverResponse)
async def discover_products(
    request: DiscoverRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> DiscoverResponse:
    """Discover and score products from CJ Dropshipping.

    Requires CJ_API_KEY environment variable to be set.
    This runs the discovery in the background.
    """
    import os

    if not os.getenv("CJ_API_KEY"):
        raise HTTPException(
            status_code=400,
            detail="CJ_API_KEY not configured. Use /admin/seed-demo for testing.",
        )

    # Would run discovery in background
    # For now, return info about configuration
    return DiscoverResponse(
        status="error",
        message="Discovery requires API keys. Use /admin/seed-demo for testing.",
    )


@router.post("/seed-demo", response_model=SeedDemoResponse)
async def seed_demo_products(
    request: SeedDemoRequest,
    db: AsyncSession = Depends(get_db),
) -> SeedDemoResponse:
    """Seed demo scored products for testing the admin dashboard.

    Creates sample products with realistic scoring data.
    Uses real Google Ads CPC data when available.
    """
    # Get current scoring settings
    settings = await get_or_create_settings(db)
    scoring_config = settings_to_scoring_config(settings)

    # Try to fetch real CPC data from Google Ads
    real_cpc_data: dict[str, float] = {}
    google_ads_available = False

    try:
        from ecom_arb.integrations.google_ads import GoogleAdsClient, GoogleAdsConfig

        required_vars = [
            "GOOGLE_ADS_CLIENT_ID",
            "GOOGLE_ADS_CLIENT_SECRET",
            "GOOGLE_ADS_REFRESH_TOKEN",
            "GOOGLE_ADS_DEVELOPER_TOKEN",
            "GOOGLE_ADS_CUSTOMER_ID",
        ]

        if all(os.getenv(var) for var in required_vars):
            config = GoogleAdsConfig(
                client_id=os.getenv("GOOGLE_ADS_CLIENT_ID", ""),
                client_secret=os.getenv("GOOGLE_ADS_CLIENT_SECRET", ""),
                refresh_token=os.getenv("GOOGLE_ADS_REFRESH_TOKEN", ""),
                developer_token=os.getenv("GOOGLE_ADS_DEVELOPER_TOKEN", ""),
                customer_id=os.getenv("GOOGLE_ADS_CUSTOMER_ID", ""),
            )

            # Extract unique keywords from product names (limit to 20 - API max)
            keywords = list(set(
                name.split(" - ")[0].lower().replace("premium ", "").replace("deluxe ", "")
                    .replace("professional ", "").replace("pro", "").replace("ultra ", "")
                    .replace("heavy duty ", "").replace("smart ", "").replace("modern ", "")
                    .strip()
                for name, _, _, _ in DEMO_PRODUCTS
            ))[:20]

            logger.info(f"Fetching real CPC for {len(keywords)} keywords: {keywords}")

            client = GoogleAdsClient(config)
            estimates = client.get_keyword_cpc_estimates(keywords)

            for est in estimates:
                # Use average CPC for scoring
                real_cpc_data[est.keyword.lower()] = float(est.avg_cpc)

            google_ads_available = True
            logger.info(f"Got real CPC for {len(real_cpc_data)} keywords")

    except Exception as e:
        logger.warning(f"Could not fetch real CPC data: {e}")

    created = 0

    for i in range(request.count):
        # Pick a random template
        template = DEMO_PRODUCTS[i % len(DEMO_PRODUCTS)]
        name, category, base_cost, base_price = template

        # Add some variation
        cost_var = random.uniform(0.9, 1.1)
        price_var = random.uniform(0.95, 1.05)

        product_cost = round(base_cost * cost_var, 2)
        shipping_cost = round(random.uniform(2.0, 5.0), 2)  # Lower shipping
        selling_price = round(base_price * price_var, 2)

        # Vary quality tier to get different recommendations
        quality_tier = i % 5  # 0-4, lower is better

        # Try to get real CPC from Google Ads
        keyword_match = name.split(" - ")[0].lower().replace("premium ", "").replace("deluxe ", "") \
            .replace("professional ", "").replace("pro", "").replace("ultra ", "") \
            .replace("heavy duty ", "").replace("smart ", "").replace("modern ", "").strip()

        # Find best matching keyword
        real_cpc = None
        for kw, cpc in real_cpc_data.items():
            if kw in keyword_match or keyword_match in kw:
                real_cpc = cpc
                break

        if real_cpc is not None:
            # Use real CPC with tier-based variation
            tier_multipliers = [0.6, 0.8, 1.0, 1.2, 1.5]  # Vary by tier
            estimated_cpc = round(real_cpc * tier_multipliers[quality_tier] * random.uniform(0.9, 1.1), 2)
        else:
            # Fallback to demo data
            if quality_tier == 0:
                estimated_cpc = round(random.uniform(0.15, 0.35), 2)
            elif quality_tier == 1:
                estimated_cpc = round(random.uniform(0.30, 0.50), 2)
            elif quality_tier == 2:
                estimated_cpc = round(random.uniform(0.45, 0.65), 2)
            elif quality_tier == 3:
                estimated_cpc = round(random.uniform(0.55, 0.80), 2)
            else:
                estimated_cpc = round(random.uniform(0.80, 1.50), 2)

        # Set other tier-based attributes
        if quality_tier == 0:  # Best - STRONG BUY candidates
            ship_min, ship_max = 3, 7
            amazon_prime = False
            amazon_reviews = random.randint(0, 30)
        elif quality_tier == 1:  # Good - VIABLE candidates
            ship_min, ship_max = 5, 10
            amazon_prime = False
            amazon_reviews = random.randint(20, 100)
        elif quality_tier == 2:  # OK - MARGINAL candidates
            ship_min, ship_max = 7, 12
            amazon_prime = random.choice([True, False])
            amazon_reviews = random.randint(50, 200)
        elif quality_tier == 3:  # Weak - WEAK candidates
            ship_min, ship_max = 10, 16
            amazon_prime = True
            amazon_reviews = random.randint(100, 400)
        else:  # Bad - REJECT candidates
            ship_min, ship_max = 14, 21
            amazon_prime = True
            amazon_reviews = random.randint(300, 1000)

        # Create scoring Product
        product = Product(
            id=f"demo-{i+1:04d}",
            name=f"{name} - Variant {i+1}",
            product_cost=product_cost,
            shipping_cost=shipping_cost,
            selling_price=selling_price,
            category=category,
            requires_sizing=False,
            is_fragile=False,
            weight_grams=random.randint(200, 1500),
            supplier_rating=round(random.uniform(4.6, 5.0), 1),
            supplier_age_months=random.randint(18, 60),
            supplier_feedback_count=random.randint(1000, 5000),
            shipping_days_min=ship_min,
            shipping_days_max=ship_max,
            has_fast_shipping=ship_max <= 10,
            estimated_cpc=estimated_cpc,
            monthly_search_volume=random.randint(1000, 15000),
            amazon_prime_exists=amazon_prime,
            amazon_review_count=amazon_reviews,
            source="demo",
            source_url=f"https://example.com/product/demo-{i+1}",
        )

        # Score with current settings
        score = score_product(product, scoring_config)

        # Save to database
        scored_product = ScoredProduct(
            source_product_id=product.id,
            name=product.name,
            source="demo" if not google_ads_available else "demo+gads",
            source_url=product.source_url,
            product_cost=Decimal(str(product.product_cost)),
            shipping_cost=Decimal(str(product.shipping_cost)),
            selling_price=Decimal(str(product.selling_price)),
            category=category.value,
            estimated_cpc=Decimal(str(product.estimated_cpc)),
            cogs=Decimal(str(score.cogs)),
            gross_margin=Decimal(str(score.gross_margin)),
            net_margin=Decimal(str(score.net_margin)),
            max_cpc=Decimal(str(score.max_cpc)),
            cpc_buffer=Decimal(str(score.cpc_buffer)),
            passed_filters=score.passed_filters,
            rejection_reasons=score.rejection_reasons,
            points=score.points,
            point_breakdown=score.point_breakdown,
            rank_score=Decimal(str(score.rank_score)) if score.rank_score else None,
            recommendation=score.recommendation,
        )

        db.add(scored_product)
        created += 1

    await db.commit()

    cpc_source = "real Google Ads CPC" if google_ads_available else "demo CPC data"
    return SeedDemoResponse(
        status="success",
        message=f"Created {created} demo scored products using {cpc_source}",
        created=created,
    )


@router.delete("/scored-products", status_code=204)
async def clear_scored_products(
    db: AsyncSession = Depends(get_db),
) -> None:
    """Clear all scored products (for testing)."""
    from sqlalchemy import delete

    await db.execute(delete(ScoredProduct))
    await db.commit()


class KeywordCPCRequest(BaseModel):
    """Request to get CPC estimates for keywords."""

    keywords: list[str] = Field(
        default=["garden tools", "kitchen knife set", "pet grooming"],
        description="Keywords to check CPC for",
    )


class KeywordCPCItem(BaseModel):
    """CPC estimate for a single keyword."""

    keyword: str
    avg_monthly_searches: int
    competition: str
    low_cpc: float
    high_cpc: float
    avg_cpc: float


class KeywordCPCResponse(BaseModel):
    """Response with CPC estimates."""

    status: str
    keywords: list[KeywordCPCItem]
    message: str = ""


@router.post("/keyword-cpc", response_model=KeywordCPCResponse)
async def get_keyword_cpc(
    request: KeywordCPCRequest,
) -> KeywordCPCResponse:
    """Get real CPC estimates from Google Ads Keyword Planner.

    Requires Google Ads API credentials to be configured:
    - GOOGLE_ADS_CLIENT_ID
    - GOOGLE_ADS_CLIENT_SECRET
    - GOOGLE_ADS_REFRESH_TOKEN
    - GOOGLE_ADS_DEVELOPER_TOKEN
    - GOOGLE_ADS_CUSTOMER_ID
    """
    import os

    from ecom_arb.integrations.google_ads import GoogleAdsClient, GoogleAdsConfig, GoogleAdsError

    # Check for required environment variables
    required_vars = [
        "GOOGLE_ADS_CLIENT_ID",
        "GOOGLE_ADS_CLIENT_SECRET",
        "GOOGLE_ADS_REFRESH_TOKEN",
        "GOOGLE_ADS_DEVELOPER_TOKEN",
        "GOOGLE_ADS_CUSTOMER_ID",
    ]

    missing = [var for var in required_vars if not os.getenv(var)]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Missing Google Ads credentials: {', '.join(missing)}",
        )

    try:
        config = GoogleAdsConfig(
            client_id=os.getenv("GOOGLE_ADS_CLIENT_ID", ""),
            client_secret=os.getenv("GOOGLE_ADS_CLIENT_SECRET", ""),
            refresh_token=os.getenv("GOOGLE_ADS_REFRESH_TOKEN", ""),
            developer_token=os.getenv("GOOGLE_ADS_DEVELOPER_TOKEN", ""),
            customer_id=os.getenv("GOOGLE_ADS_CUSTOMER_ID", ""),
        )

        client = GoogleAdsClient(config)
        estimates = client.get_keyword_cpc_estimates(request.keywords)

        return KeywordCPCResponse(
            status="success",
            keywords=[
                KeywordCPCItem(
                    keyword=est.keyword,
                    avg_monthly_searches=est.avg_monthly_searches,
                    competition=est.competition,
                    low_cpc=float(est.low_cpc),
                    high_cpc=float(est.high_cpc),
                    avg_cpc=float(est.avg_cpc),
                )
                for est in estimates
            ],
            message=f"Retrieved CPC data for {len(estimates)} keywords",
        )

    except GoogleAdsError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Google Ads API error: {str(e)}",
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching CPC data: {str(e)}",
        )


# --- Settings API ---


class ScoringSettingsResponse(BaseModel):
    """Response with current scoring settings."""

    # Fee assumptions
    payment_fee_rate: float = Field(description="Payment processor fee (e.g., 0.03 = 3%)")
    chargeback_rate: float = Field(description="Expected chargeback rate")
    default_refund_rate: float = Field(description="Default refund rate if category unknown")
    cvr: float = Field(description="Assumed conversion rate")
    cpc_multiplier: float = Field(description="CPC multiplier for new accounts")

    # Hard filter thresholds
    max_cpc_threshold: float = Field(description="Reject if estimated CPC > this")
    min_gross_margin: float = Field(description="Reject if gross margin < this")
    min_selling_price: float = Field(description="Reject if selling price < this")
    max_selling_price: float = Field(description="Reject if selling price > this")
    max_shipping_days: int = Field(description="Reject if shipping > this days")
    min_supplier_rating: float = Field(description="Reject if supplier rating < this")
    min_supplier_age_months: int = Field(description="Reject if supplier < this months old")
    min_supplier_feedback: int = Field(description="Reject if supplier feedback < this")
    max_amazon_reviews_for_competition: int = Field(
        description="Reject if Amazon Prime competitor has > this reviews"
    )
    min_cpc_buffer: float = Field(description="Reject if CPC buffer < this")
    max_weight_grams: int = Field(description="Reject if weight > this grams")


class ScoringSettingsUpdate(BaseModel):
    """Request to update scoring settings."""

    # Fee assumptions (optional)
    payment_fee_rate: Optional[float] = Field(None, ge=0, le=1)
    chargeback_rate: Optional[float] = Field(None, ge=0, le=1)
    default_refund_rate: Optional[float] = Field(None, ge=0, le=1)
    cvr: Optional[float] = Field(None, ge=0, le=1)
    cpc_multiplier: Optional[float] = Field(None, ge=1, le=5)

    # Hard filter thresholds (optional)
    max_cpc_threshold: Optional[float] = Field(None, ge=0)
    min_gross_margin: Optional[float] = Field(None, ge=0, le=1)
    min_selling_price: Optional[float] = Field(None, ge=0)
    max_selling_price: Optional[float] = Field(None, ge=0)
    max_shipping_days: Optional[int] = Field(None, ge=1, le=90)
    min_supplier_rating: Optional[float] = Field(None, ge=0, le=5)
    min_supplier_age_months: Optional[int] = Field(None, ge=0)
    min_supplier_feedback: Optional[int] = Field(None, ge=0)
    max_amazon_reviews_for_competition: Optional[int] = Field(None, ge=0)
    min_cpc_buffer: Optional[float] = Field(None, ge=0)
    max_weight_grams: Optional[int] = Field(None, ge=0)


async def get_or_create_settings(db: AsyncSession) -> ScoringSettings:
    """Get or create scoring settings singleton."""
    from sqlalchemy import select

    result = await db.execute(select(ScoringSettings).where(ScoringSettings.id == 1))
    settings = result.scalar_one_or_none()

    if not settings:
        settings = ScoringSettings(id=1)
        db.add(settings)
        await db.commit()
        await db.refresh(settings)

    return settings


@router.get("/settings", response_model=ScoringSettingsResponse)
async def get_settings(
    db: AsyncSession = Depends(get_db),
) -> ScoringSettingsResponse:
    """Get current scoring settings."""
    settings = await get_or_create_settings(db)

    return ScoringSettingsResponse(
        payment_fee_rate=float(settings.payment_fee_rate),
        chargeback_rate=float(settings.chargeback_rate),
        default_refund_rate=float(settings.default_refund_rate),
        cvr=float(settings.cvr),
        cpc_multiplier=float(settings.cpc_multiplier),
        max_cpc_threshold=float(settings.max_cpc_threshold),
        min_gross_margin=float(settings.min_gross_margin),
        min_selling_price=float(settings.min_selling_price),
        max_selling_price=float(settings.max_selling_price),
        max_shipping_days=settings.max_shipping_days,
        min_supplier_rating=float(settings.min_supplier_rating),
        min_supplier_age_months=settings.min_supplier_age_months,
        min_supplier_feedback=settings.min_supplier_feedback,
        max_amazon_reviews_for_competition=settings.max_amazon_reviews_for_competition,
        min_cpc_buffer=float(settings.min_cpc_buffer),
        max_weight_grams=settings.max_weight_grams,
    )


@router.put("/settings", response_model=ScoringSettingsResponse)
async def update_settings(
    request: ScoringSettingsUpdate,
    db: AsyncSession = Depends(get_db),
) -> ScoringSettingsResponse:
    """Update scoring settings."""
    settings = await get_or_create_settings(db)

    # Update only provided fields
    update_data = request.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if value is not None:
            setattr(settings, field, Decimal(str(value)) if isinstance(value, float) else value)

    await db.commit()
    await db.refresh(settings)

    return ScoringSettingsResponse(
        payment_fee_rate=float(settings.payment_fee_rate),
        chargeback_rate=float(settings.chargeback_rate),
        default_refund_rate=float(settings.default_refund_rate),
        cvr=float(settings.cvr),
        cpc_multiplier=float(settings.cpc_multiplier),
        max_cpc_threshold=float(settings.max_cpc_threshold),
        min_gross_margin=float(settings.min_gross_margin),
        min_selling_price=float(settings.min_selling_price),
        max_selling_price=float(settings.max_selling_price),
        max_shipping_days=settings.max_shipping_days,
        min_supplier_rating=float(settings.min_supplier_rating),
        min_supplier_age_months=settings.min_supplier_age_months,
        min_supplier_feedback=settings.min_supplier_feedback,
        max_amazon_reviews_for_competition=settings.max_amazon_reviews_for_competition,
        min_cpc_buffer=float(settings.min_cpc_buffer),
        max_weight_grams=settings.max_weight_grams,
    )


def settings_to_scoring_config(settings: ScoringSettings) -> ScoringConfig:
    """Convert database settings to ScoringConfig for the scorer."""
    return ScoringConfig(
        payment_fee_rate=float(settings.payment_fee_rate),
        chargeback_rate=float(settings.chargeback_rate),
        default_refund_rate=float(settings.default_refund_rate),
        cvr=float(settings.cvr),
        cpc_multiplier=float(settings.cpc_multiplier),
        max_cpc_threshold=float(settings.max_cpc_threshold),
        min_gross_margin=float(settings.min_gross_margin),
        min_selling_price=float(settings.min_selling_price),
        max_selling_price=float(settings.max_selling_price),
        max_shipping_days=settings.max_shipping_days,
        min_supplier_rating=float(settings.min_supplier_rating),
        min_supplier_age_months=settings.min_supplier_age_months,
        min_supplier_feedback=settings.min_supplier_feedback,
        max_amazon_reviews_for_competition=settings.max_amazon_reviews_for_competition,
        min_cpc_buffer=float(settings.min_cpc_buffer),
        max_weight_grams=settings.max_weight_grams,
    )
