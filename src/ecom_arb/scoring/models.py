"""Data models for product scoring."""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ProductCategory(str, Enum):
    """Product categories with associated refund risk."""

    # Low risk (5-6%)
    TOOLS = "tools"
    CRAFTS = "crafts"
    OFFICE = "office"
    OUTDOOR = "outdoor"
    PET = "pet"

    # Medium risk (8-10%)
    HOME_DECOR = "home_decor"
    KITCHEN = "kitchen"
    JEWELRY = "jewelry"
    GARDEN = "garden"

    # High risk (12-18%) - should be filtered out
    APPAREL = "apparel"
    SHOES = "shoes"
    ELECTRONICS = "electronics"

    # Restricted (reject)
    SUPPLEMENTS = "supplements"
    COSMETICS = "cosmetics"
    FOOD = "food"
    MEDICAL = "medical"
    WEAPONS = "weapons"
    CHILDREN = "children"


# Refund rates by category
CATEGORY_REFUND_RATES: dict[ProductCategory, float] = {
    # Low risk
    ProductCategory.TOOLS: 0.05,
    ProductCategory.CRAFTS: 0.05,
    ProductCategory.OFFICE: 0.04,
    ProductCategory.OUTDOOR: 0.06,
    ProductCategory.PET: 0.06,
    # Medium risk
    ProductCategory.HOME_DECOR: 0.08,
    ProductCategory.KITCHEN: 0.08,
    ProductCategory.JEWELRY: 0.10,
    ProductCategory.GARDEN: 0.08,
    # High risk
    ProductCategory.APPAREL: 0.15,
    ProductCategory.SHOES: 0.18,
    ProductCategory.ELECTRONICS: 0.12,
    # Restricted (won't be used, but defined for completeness)
    ProductCategory.SUPPLEMENTS: 0.15,
    ProductCategory.COSMETICS: 0.12,
    ProductCategory.FOOD: 0.10,
    ProductCategory.MEDICAL: 0.10,
    ProductCategory.WEAPONS: 0.05,
    ProductCategory.CHILDREN: 0.12,
}

# Restricted categories that should always be rejected
RESTRICTED_CATEGORIES: set[ProductCategory] = {
    ProductCategory.SUPPLEMENTS,
    ProductCategory.COSMETICS,
    ProductCategory.FOOD,
    ProductCategory.MEDICAL,
    ProductCategory.WEAPONS,
    ProductCategory.CHILDREN,
}


class Product(BaseModel):
    """Input product data for scoring."""

    # Identification
    id: str = Field(..., description="Unique product identifier")
    name: str = Field(..., description="Product name/title")

    # Pricing
    product_cost: float = Field(..., gt=0, description="Cost to purchase from supplier (USD)")
    shipping_cost: float = Field(..., ge=0, description="Shipping cost to customer (USD)")
    selling_price: float = Field(..., gt=0, description="Price we'll sell at (USD)")

    # Category and attributes
    category: ProductCategory = Field(..., description="Product category")
    requires_sizing: bool = Field(False, description="Does product require size selection?")
    is_fragile: bool = Field(False, description="Is product fragile/breakable?")
    weight_grams: int = Field(..., ge=0, description="Product weight in grams")

    # Supplier info
    supplier_rating: float = Field(..., ge=0, le=5, description="Supplier store rating (0-5)")
    supplier_age_months: int = Field(..., ge=0, description="Supplier store age in months")
    supplier_feedback_count: int = Field(..., ge=0, description="Number of supplier feedbacks")

    # Shipping
    shipping_days_min: int = Field(..., ge=0, description="Minimum shipping days")
    shipping_days_max: int = Field(..., ge=0, description="Maximum shipping days")
    has_fast_shipping: bool = Field(True, description="Has ePacket/AliExpress Standard option")

    # Market data
    estimated_cpc: float = Field(..., gt=0, description="Estimated CPC from Keyword Planner (USD)")
    monthly_search_volume: int = Field(..., ge=0, description="Monthly search volume for keywords")

    # Competition
    amazon_prime_exists: bool = Field(False, description="Does Amazon Prime competitor exist?")
    amazon_review_count: int = Field(0, ge=0, description="Amazon competitor review count")

    # Optional metadata
    source: Optional[str] = Field(None, description="Data source (cj, aliexpress, amazon, etc.)")
    source_url: Optional[str] = Field(None, description="URL to product on source platform")


class ScoringConfig(BaseModel):
    """Configuration for scoring calculations."""

    # Fee assumptions
    payment_fee_rate: float = Field(0.03, description="Payment processor fee (default 3%)")
    chargeback_rate: float = Field(0.005, description="Expected chargeback rate (default 0.5%)")
    default_refund_rate: float = Field(0.08, description="Default refund rate if category unknown")

    # CVR assumption
    cvr: float = Field(0.01, description="Assumed conversion rate (default 1%)")

    # CPC multiplier for new accounts
    cpc_multiplier: float = Field(1.3, description="Multiplier for new account CPC penalty")

    # Hard filter thresholds
    max_cpc_threshold: float = Field(0.75, description="Reject if estimated CPC > this")
    min_gross_margin: float = Field(0.65, description="Reject if gross margin < this")
    min_selling_price: float = Field(50.0, description="Reject if selling price < this")
    max_selling_price: float = Field(200.0, description="Reject if selling price > this")
    max_shipping_days: int = Field(30, description="Reject if shipping > this days")
    min_supplier_rating: float = Field(4.6, description="Reject if supplier rating < this")
    min_supplier_age_months: int = Field(12, description="Reject if supplier < this months old")
    min_supplier_feedback: int = Field(500, description="Reject if supplier feedback < this")
    max_amazon_reviews_for_competition: int = Field(
        500, description="Reject if Amazon Prime competitor has > this reviews"
    )
    min_cpc_buffer: float = Field(1.5, description="Reject if CPC buffer < this")
    max_weight_grams: int = Field(2000, description="Reject if weight > this grams")


class ProductScore(BaseModel):
    """Calculated score for a product."""

    # Product reference
    product_id: str
    product_name: str

    # Calculated financials
    cogs: float = Field(..., description="Cost of goods sold (product + shipping)")
    gross_margin: float = Field(..., description="Gross margin percentage")
    net_margin: float = Field(..., description="Net margin after fees/refunds/chargebacks")
    max_cpc: float = Field(..., description="Maximum CPC we can afford")
    cpc_buffer: float = Field(..., description="Ratio of max CPC to estimated CPC")

    # Filter result
    passed_filters: bool = Field(..., description="Did product pass all hard filters?")
    rejection_reasons: list[str] = Field(
        default_factory=list, description="Reasons for rejection if failed"
    )

    # Point scoring (only if passed filters)
    points: Optional[int] = Field(None, description="Total points (0-100)")
    point_breakdown: Optional[dict[str, int]] = Field(
        None, description="Points by category"
    )

    # Final ranking
    rank_score: Optional[float] = Field(
        None, description="Combined score for ranking (points * 0.6 + cpc_buffer * 25)"
    )

    # Recommendation
    recommendation: str = Field(..., description="STRONG BUY, VIABLE, MARGINAL, or REJECT")
