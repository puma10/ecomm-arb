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

# Cache CJ client to avoid repeated auth calls
_cj_client_cache: dict = {"client": None, "expires": None}

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
    skipped: int = 0
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
    db: AsyncSession = Depends(get_db),
) -> DiscoverResponse:
    """Discover and score products from CJ Dropshipping.

    Requires CJ_API_KEY environment variable to be set.
    Searches CJ for products, calculates shipping, gets real CPC, and scores.
    """
    from datetime import datetime, timedelta
    from ecom_arb.config import get_settings
    from ecom_arb.integrations.cj_dropshipping import CJDropshippingClient, CJConfig, CJError

    app_settings = get_settings()
    cj_api_key = app_settings.cj_api_key
    if not cj_api_key:
        raise HTTPException(
            status_code=400,
            detail="CJ_API_KEY not configured. Use /admin/seed-demo for testing.",
        )

    # Use cached client if available and not expired
    global _cj_client_cache
    now = datetime.now()

    if _cj_client_cache["client"] and _cj_client_cache["expires"] and now < _cj_client_cache["expires"]:
        cj_client = _cj_client_cache["client"]
        logger.info("Using cached CJ client")
    else:
        # Initialize new CJ client
        try:
            config = CJConfig(api_key=cj_api_key)
            cj_client = CJDropshippingClient(config)
            cj_client.get_access_token()
            # Cache for 1 hour (tokens are valid longer, but be safe)
            _cj_client_cache["client"] = cj_client
            _cj_client_cache["expires"] = now + timedelta(hours=1)
            logger.info("Created new CJ client, cached for 1 hour")
        except (ValueError, CJError) as e:
            error_msg = str(e)
            if "429" in error_msg:
                raise HTTPException(
                    status_code=429,
                    detail="CJ API rate limit exceeded. CJ allows 30 requests/second. Wait 1-2 minutes and try again.",
                )
            raise HTTPException(status_code=400, detail=f"CJ API error: {error_msg}")

    # Get current scoring settings
    settings = await get_or_create_settings(db)
    scoring_config = settings_to_scoring_config(settings)

    # Try to set up Google Ads client for real CPC
    google_ads_client = None
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
            gads_config = GoogleAdsConfig(
                client_id=os.getenv("GOOGLE_ADS_CLIENT_ID", ""),
                client_secret=os.getenv("GOOGLE_ADS_CLIENT_SECRET", ""),
                refresh_token=os.getenv("GOOGLE_ADS_REFRESH_TOKEN", ""),
                developer_token=os.getenv("GOOGLE_ADS_DEVELOPER_TOKEN", ""),
                customer_id=os.getenv("GOOGLE_ADS_CUSTOMER_ID", ""),
            )
            google_ads_client = GoogleAdsClient(gads_config)
            logger.info("Google Ads client configured for real CPC")
    except Exception as e:
        logger.warning(f"Could not configure Google Ads: {e}")

    discovered = 0
    skipped = 0
    scored = 0
    passed = 0
    errors = []

    for keyword in request.keywords:
        try:
            # Search CJ for products
            cj_products = cj_client.list_products(
                keyword=keyword,
                page=1,
                page_size=request.limit_per_keyword,
            )
            discovered += len(cj_products)
            logger.info(f"Found {len(cj_products)} products for '{keyword}'")

            # Collect keywords for CPC lookup (batch to reduce API calls)
            product_keywords = []
            for cj_prod in cj_products:
                # Extract key terms from product name for CPC lookup
                clean_name = cj_prod.name.lower()
                for prefix in ["premium", "professional", "deluxe", "ultra", "smart"]:
                    clean_name = clean_name.replace(prefix, "")
                product_keywords.append(clean_name.strip()[:50])

            # Get real CPC data if available
            cpc_estimates: dict[str, float] = {}
            search_volume_estimates: dict[str, int] = {}
            if google_ads_client and product_keywords:
                try:
                    # Limit to 20 keywords per API call
                    unique_keywords = list(set(product_keywords))[:20]
                    estimates = google_ads_client.get_keyword_cpc_estimates(unique_keywords)
                    for est in estimates:
                        cpc_estimates[est.keyword.lower()] = float(est.avg_cpc)
                        search_volume_estimates[est.keyword.lower()] = est.avg_monthly_searches
                except Exception as e:
                    logger.warning(f"Could not fetch CPC for '{keyword}': {e}")

            # EU country codes to filter out
            eu_countries = {
                "DE", "FR", "IT", "ES", "NL", "PL", "BE", "AT", "SE", "DK",
                "FI", "IE", "PT", "CZ", "RO", "HU", "SK", "BG", "HR", "SI",
                "LT", "LV", "EE", "CY", "LU", "MT", "GR", "UK", "GB"
            }

            for cj_prod in cj_products:
                try:
                    # Skip EU warehouse products
                    warehouse = cj_prod.warehouse_country or "CN"
                    if warehouse.upper() in eu_countries:
                        logger.debug(f"Skipping EU product {cj_prod.pid}: warehouse={warehouse}")
                        continue

                    # Skip if already in database (check early to avoid wasted work)
                    from sqlalchemy import select
                    existing = await db.execute(
                        select(ScoredProduct).where(
                            ScoredProduct.source_product_id == cj_prod.pid
                        )
                    )
                    if existing.scalar_one_or_none():
                        skipped += 1
                        logger.debug(f"Skipping existing product {cj_prod.pid}")
                        continue

                    # Calculate shipping cost to US
                    # Priority: 1) Free shipping, 2) trial_freight from API, 3) freight API call, 4) fallback
                    if cj_prod.is_free_shipping:
                        shipping_cost = Decimal("0.00")
                        logger.debug(f"Free shipping for {cj_prod.pid}")
                    elif cj_prod.trial_freight and cj_prod.trial_freight > 0:
                        shipping_cost = cj_prod.trial_freight
                        logger.debug(f"Using trial_freight ${shipping_cost} for {cj_prod.pid}")
                    elif cj_prod.variants:
                        # Try freight API as fallback
                        shipping_cost = Decimal("8.00")  # Default if API fails
                        try:
                            freight_options = cj_client.calculate_freight(
                                start_country="CN",
                                end_country="US",
                                products=[{"vid": cj_prod.variants[0].vid, "quantity": 1}],
                            )
                            if freight_options:
                                shipping_cost = freight_options[0].price
                                logger.debug(f"Freight API: ${shipping_cost} for {cj_prod.pid}")
                        except CJError as e:
                            logger.debug(f"Freight calc failed for {cj_prod.pid}: {e}")
                    else:
                        # No shipping info available - estimate by weight
                        weight_kg = float(cj_prod.weight or 500) / 1000
                        shipping_cost = Decimal(str(round(3.0 + weight_kg * 5.0, 2)))  # $3 base + $5/kg
                        logger.debug(f"Estimated shipping ${shipping_cost} for {cj_prod.pid} ({weight_kg}kg)")

                    # Calculate shipping time based on warehouse location
                    warehouse = cj_prod.warehouse_country or "CN"
                    if warehouse == "US":
                        # US warehouse: fast domestic shipping
                        ship_days_min = 3
                        ship_days_max = 7
                        has_fast = True
                    elif warehouse in ["CN", "HK"]:
                        # China/HK warehouse: standard international
                        if cj_prod.delivery_cycle_days:
                            # Use CJ's delivery cycle if available
                            ship_days_min = max(7, cj_prod.delivery_cycle_days - 3)
                            ship_days_max = cj_prod.delivery_cycle_days + 5
                        else:
                            ship_days_min = 10
                            ship_days_max = 20
                        has_fast = False
                    else:
                        # Other warehouses (EU, etc.)
                        ship_days_min = 7
                        ship_days_max = 15
                        has_fast = False

                    # Add dispatch time if available (24/48/72 hours)
                    if cj_prod.delivery_time_hours:
                        dispatch_days = cj_prod.delivery_time_hours // 24
                        ship_days_min += dispatch_days
                        ship_days_max += dispatch_days

                    # Determine selling price (markup from cost)
                    product_cost = float(cj_prod.sell_price)
                    # Target ~70% margin: selling_price = cost / 0.30
                    selling_price = round(product_cost / 0.30, 2)
                    # Ensure minimum price
                    selling_price = max(selling_price, float(scoring_config.min_selling_price))

                    # Get CPC estimate and search volume
                    clean_name = cj_prod.name.lower()
                    for prefix in ["premium", "professional", "deluxe", "ultra", "smart"]:
                        clean_name = clean_name.replace(prefix, "")
                    clean_name = clean_name.strip()[:50]

                    estimated_cpc = cpc_estimates.get(clean_name, 0.50)  # Default fallback
                    search_volume = search_volume_estimates.get(clean_name, 1000)  # Default fallback

                    # Map CJ category to our categories
                    category = _map_cj_category(cj_prod.category_name)

                    # Determine supplier quality based on CJ data
                    # Use listed_num as a proxy for supplier reliability
                    if cj_prod.listed_num and cj_prod.listed_num > 1000:
                        supplier_rating = 4.9
                        supplier_feedback = cj_prod.listed_num
                    elif cj_prod.listed_num and cj_prod.listed_num > 100:
                        supplier_rating = 4.7
                        supplier_feedback = cj_prod.listed_num * 5
                    else:
                        supplier_rating = 4.5
                        supplier_feedback = 500

                    # Create scoring product
                    product = Product(
                        id=cj_prod.pid,
                        name=cj_prod.name,
                        product_cost=product_cost,
                        shipping_cost=float(shipping_cost),
                        selling_price=selling_price,
                        category=category,
                        requires_sizing=False,
                        is_fragile=False,
                        weight_grams=int(cj_prod.weight) if cj_prod.weight else 500,  # CJ returns weight in grams
                        supplier_rating=supplier_rating,
                        supplier_age_months=24,  # CJ doesn't expose this
                        supplier_feedback_count=supplier_feedback,
                        shipping_days_min=ship_days_min,
                        shipping_days_max=ship_days_max,
                        has_fast_shipping=has_fast,
                        estimated_cpc=estimated_cpc,
                        monthly_search_volume=search_volume,
                        amazon_prime_exists=False,
                        amazon_review_count=0,
                        source="cj_dropshipping",
                        source_url=f"https://cjdropshipping.com/search?keyword={cj_prod.pid}",
                    )

                    # Score the product
                    score = score_product(product, scoring_config)
                    scored += 1

                    if score.passed_filters:
                        passed += 1

                    # Save to database with comprehensive CJ data
                    scored_product = ScoredProduct(
                        source_product_id=cj_prod.pid,
                        name=cj_prod.name,
                        source="cj_dropshipping",
                        source_url=f"https://cjdropshipping.com/search?keyword={cj_prod.pid}",
                        product_cost=Decimal(str(product_cost)),
                        shipping_cost=shipping_cost,
                        selling_price=Decimal(str(selling_price)),
                        category=category.value,
                        estimated_cpc=Decimal(str(estimated_cpc)),
                        monthly_search_volume=search_volume,
                        # CJ logistics data
                        weight_grams=int(cj_prod.weight) if cj_prod.weight else None,
                        shipping_days_min=ship_days_min,
                        shipping_days_max=ship_days_max,
                        warehouse_country=warehouse,
                        # CJ supplier data
                        supplier_name=cj_prod.supplier_name,
                        inventory_count=cj_prod.warehouse_inventory,
                        # Calculated scores
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

                except Exception as e:
                    logger.warning(f"Error processing product {cj_prod.pid}: {e}")
                    errors.append(str(e))

        except CJError as e:
            error_msg = str(e)
            logger.error(f"CJ API error for keyword '{keyword}': {error_msg}")
            if "429" in error_msg:
                errors.append(f"Rate limited on '{keyword}' - wait 1-2 min")
            else:
                errors.append(f"CJ error for '{keyword}': {error_msg}")

    await db.commit()

    cpc_source = "real Google Ads CPC" if google_ads_client else "estimated CPC"
    error_msg = f" ({len(errors)} errors)" if errors else ""

    skipped_msg = f", {skipped} already in DB" if skipped else ""
    return DiscoverResponse(
        status="success",
        message=f"Discovered {discovered}, scored {scored}, {passed} passed{skipped_msg} using {cpc_source}{error_msg}",
        discovered=discovered,
        skipped=skipped,
        scored=scored,
        passed=passed,
    )


def _map_cj_category(cj_category: str) -> ProductCategory:
    """Map CJ category name to our ProductCategory enum."""
    cj_lower = cj_category.lower()

    if any(x in cj_lower for x in ["garden", "outdoor", "patio"]):
        return ProductCategory.GARDEN
    elif any(x in cj_lower for x in ["kitchen", "cook", "bake"]):
        return ProductCategory.KITCHEN
    elif any(x in cj_lower for x in ["pet", "dog", "cat"]):
        return ProductCategory.PET
    elif any(x in cj_lower for x in ["office", "desk", "work"]):
        return ProductCategory.OFFICE
    elif any(x in cj_lower for x in ["craft", "art", "sewing"]):
        return ProductCategory.CRAFTS
    elif any(x in cj_lower for x in ["tool", "hardware"]):
        return ProductCategory.TOOLS
    elif any(x in cj_lower for x in ["camp", "hike", "outdoor", "sport"]):
        return ProductCategory.OUTDOOR
    elif any(x in cj_lower for x in ["home", "decor", "furniture"]):
        return ProductCategory.HOME_DECOR
    else:
        return ProductCategory.HOME_DECOR  # Default


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
            monthly_search_volume=product.monthly_search_volume,
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


class EnrichSearchVolumeRequest(BaseModel):
    """Request to enrich products with search volume data."""

    limit: int = Field(default=10, description="Number of products to enrich")


class EnrichSearchVolumeResponse(BaseModel):
    """Response with enrichment results."""

    status: str
    enriched: int
    message: str


@router.post("/enrich-search-volume", response_model=EnrichSearchVolumeResponse)
async def enrich_search_volume(
    request: EnrichSearchVolumeRequest,
    db: AsyncSession = Depends(get_db),
) -> EnrichSearchVolumeResponse:
    """Enrich products with keyword analysis using AI + Google Ads.

    1. Uses Claude CLI to extract relevant search keywords from product names
    2. Gets CPC and search volume for each keyword from Google Ads
    3. Stores the full keyword analysis and picks the best keyword metrics
    """
    import json
    import os
    import subprocess
    from pathlib import Path

    from dotenv import load_dotenv
    from sqlalchemy import select

    from ecom_arb.integrations.google_ads import GoogleAdsClient, GoogleAdsConfig, GoogleAdsError

    # Load .env file
    env_file = Path(__file__).parent.parent.parent.parent.parent / ".env"
    load_dotenv(env_file)

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
            detail=f"Missing credentials: {', '.join(missing)}",
        )

    def ask_claude(prompt: str) -> str:
        """Call Claude CLI to get a response."""
        result = subprocess.run(
            ["claude", "-p", prompt, "--output-format", "text"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        return result.stdout.strip()

    try:
        # Initialize Google Ads client
        gads_config = GoogleAdsConfig(
            client_id=os.getenv("GOOGLE_ADS_CLIENT_ID", ""),
            client_secret=os.getenv("GOOGLE_ADS_CLIENT_SECRET", ""),
            refresh_token=os.getenv("GOOGLE_ADS_REFRESH_TOKEN", ""),
            developer_token=os.getenv("GOOGLE_ADS_DEVELOPER_TOKEN", ""),
            customer_id=os.getenv("GOOGLE_ADS_CUSTOMER_ID", ""),
        )
        gads_client = GoogleAdsClient(gads_config)

        # Get the most recent products
        result = await db.execute(
            select(ScoredProduct)
            .order_by(ScoredProduct.created_at.desc())
            .limit(request.limit)
        )
        products = result.scalars().all()

        if not products:
            return EnrichSearchVolumeResponse(
                status="success",
                enriched=0,
                message="No products to enrich",
            )

        enriched = 0

        for product in products:
            # Step 1: Use AI to extract keywords
            prompt = f"""Extract 3-5 Google Ads search keywords that a US shopper would use to find this product.
Focus on keywords that would have search volume - generic terms people actually search for.

Product: {product.name}
Category: {product.category}

Return ONLY a JSON array of keywords, nothing else. Example: ["keyword1", "keyword2", "keyword3"]"""

            response = ask_claude(prompt)

            try:
                # Extract JSON from response (may have extra text)
                import re
                json_match = re.search(r'\[.*?\]', response, re.DOTALL)
                if json_match:
                    keywords = json.loads(json_match.group())
                else:
                    keywords = [product.name[:50]]
                if not isinstance(keywords, list):
                    keywords = [product.name[:50]]
            except (json.JSONDecodeError, AttributeError):
                keywords = [product.name[:50]]

            # Step 2: Get CPC and volume from Google Ads
            estimates = gads_client.get_keyword_cpc_estimates(keywords[:5])

            # Step 3: Build keyword analysis
            keyword_data = []
            best_cpc = 0.0
            best_volume = 0

            for est in estimates:
                kw_info = {
                    "keyword": est.keyword,
                    "cpc": float(est.avg_cpc),
                    "search_volume": est.avg_monthly_searches,
                    "competition": est.competition,
                }
                keyword_data.append(kw_info)

                # Track the keyword with highest search volume
                if est.avg_monthly_searches > best_volume:
                    best_volume = est.avg_monthly_searches
                    best_cpc = float(est.avg_cpc)

            # Step 4: Update product
            product.keyword_analysis = {
                "keywords_searched": keywords,
                "results": keyword_data,
                "best_keyword": max(keyword_data, key=lambda x: x["search_volume"])["keyword"] if keyword_data else None,
            }
            product.estimated_cpc = Decimal(str(best_cpc)) if best_cpc > 0 else product.estimated_cpc
            product.monthly_search_volume = best_volume if best_volume > 0 else product.monthly_search_volume

            enriched += 1

        await db.commit()

        return EnrichSearchVolumeResponse(
            status="success",
            enriched=enriched,
            message=f"Enriched {enriched}/{len(products)} products with AI keyword analysis",
        )

    except GoogleAdsError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Google Ads API error: {str(e)}",
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(
            status_code=500,
            detail="Claude CLI timed out",
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error enriching products: {str(e)}",
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


# ============================================================================
# Amazon Price Enrichment
# ============================================================================


class EnrichAmazonRequest(BaseModel):
    """Request to enrich products with Amazon pricing data."""

    product_ids: list[str] | None = Field(
        None, description="Specific product IDs to enrich. If None, enriches recent products."
    )
    limit: int = Field(default=10, ge=1, le=50, description="Number of products to enrich")


class EnrichAmazonResponse(BaseModel):
    """Response from Amazon enrichment."""

    status: str
    submitted: int
    message: str


@router.post("/enrich-amazon-prices", response_model=EnrichAmazonResponse)
async def enrich_amazon_prices(
    request: EnrichAmazonRequest | None = None,
    db: AsyncSession = Depends(get_db),
) -> EnrichAmazonResponse:
    """Fetch Amazon competitor pricing directly using US residential proxy.

    This endpoint:
    1. Gets products that need Amazon pricing
    2. Extracts the best keyword from keyword_analysis
    3. Fetches Amazon search results directly with US proxy (guaranteed USD pricing)
    4. Updates product with Amazon pricing data immediately

    Use the product_ids parameter to enrich specific products,
    or leave empty to enrich the most recent products without Amazon data.
    """
    from sqlalchemy import desc, select

    from ecom_arb.services.amazon_parser import scrape_amazon_direct, AmazonParserError

    limit = request.limit if request else 10

    # Build query for products to enrich
    query = select(ScoredProduct)

    if request and request.product_ids:
        # Specific products requested
        from uuid import UUID
        uuids = [UUID(pid) for pid in request.product_ids]
        query = query.where(ScoredProduct.id.in_(uuids))
    else:
        # Get recent products without Amazon data that have keyword analysis
        query = query.where(
            ScoredProduct.amazon_median_price.is_(None),
            ScoredProduct.keyword_analysis.isnot(None),
        )

    query = query.order_by(desc(ScoredProduct.created_at)).limit(limit)

    result = await db.execute(query)
    products = result.scalars().all()

    if not products:
        return EnrichAmazonResponse(
            status="no_products",
            submitted=0,
            message="No products found that need Amazon enrichment",
        )

    enriched = 0
    for product in products:
        # Get best keyword from keyword_analysis
        keyword = None
        if product.keyword_analysis:
            keyword = product.keyword_analysis.get("best_keyword")
            if not keyword:
                # Fall back to first keyword searched
                keywords_searched = product.keyword_analysis.get("keywords_searched", [])
                if keywords_searched:
                    keyword = keywords_searched[0]

        if not keyword:
            # Fall back to product name
            keyword = product.name[:50]

        # Fetch Amazon search results directly with US proxy
        try:
            results = await scrape_amazon_direct(keyword)

            # Update product with Amazon pricing data
            if results.products:
                product.amazon_median_price = results.median_price
                product.amazon_min_price = results.min_price
                product.amazon_avg_review_count = results.avg_review_count
                product.amazon_prime_percentage = Decimal(str(results.prime_percentage))
                product.amazon_search_results = {
                    "total_results": results.total_results or len(results.products),
                    "avg_price": float(results.avg_price) if results.avg_price else None,
                    "max_price": float(results.max_price) if results.max_price else None,
                }

                enriched += 1
                logger.info(
                    f"Enriched product {product.id}: median=${results.median_price}, "
                    f"min=${results.min_price}, "
                    f"reviews={results.avg_review_count}, prime={results.prime_percentage:.0%}"
                )
            else:
                logger.warning(f"No Amazon results for product {product.id}: {keyword}")

        except AmazonParserError as e:
            logger.error(f"Failed to fetch Amazon data for {product.id}: {e}")

    # Commit all updates
    await db.commit()

    return EnrichAmazonResponse(
        status="enriched",
        submitted=enriched,
        message=f"Enriched {enriched} products with Amazon pricing data (USD).",
    )
