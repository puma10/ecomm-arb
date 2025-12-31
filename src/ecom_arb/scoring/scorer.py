"""Point scoring system for ranking products.

Scoring factors from Requirements (REQ-005):
| Factor           | Max Points |
|------------------|------------|
| CPC Score        | 20         |
| Margin Score     | 20         |
| AOV Score        | 15         |
| Competition Score| 15         |
| Search Volume    | 10         |
| Refund Risk      | 10         |
| Shipping         | 5          |
| Niche Passion    | 5          |

Total possible: 100 points

Rank Score = (Point Score × 0.6) + (CPC Buffer × 25)
"""

from ecom_arb.scoring.calculator import (
    calculate_cogs,
    calculate_cpc_buffer,
    calculate_gross_margin,
    calculate_max_cpc,
    calculate_net_margin,
)
from ecom_arb.scoring.filters import apply_hard_filters
from ecom_arb.scoring.models import (
    CATEGORY_REFUND_RATES,
    Product,
    ProductCategory,
    ProductScore,
    ScoringConfig,
)


# Categories considered "passion niches" (enthusiasts willing to pay more, wait longer)
PASSION_NICHE_CATEGORIES: set[ProductCategory] = {
    ProductCategory.CRAFTS,
    ProductCategory.OUTDOOR,
    ProductCategory.PET,
    ProductCategory.GARDEN,
}


def calculate_points(
    product: Product,
    config: ScoringConfig | None = None,
) -> tuple[int, dict[str, int]]:
    """Calculate point score for a product.

    Args:
        product: Product to score
        config: Scoring configuration

    Returns:
        Tuple of (total_points, breakdown_dict)
    """
    if config is None:
        config = ScoringConfig()

    breakdown: dict[str, int] = {}

    # --- CPC Score (20 points max) ---
    # Lower CPC is better
    # < $0.30 = 20, $0.30-0.50 = 15, $0.50-0.75 = 10
    if product.estimated_cpc < 0.30:
        breakdown["cpc"] = 20
    elif product.estimated_cpc < 0.50:
        breakdown["cpc"] = 15
    elif product.estimated_cpc < 0.75:
        breakdown["cpc"] = 10
    else:
        breakdown["cpc"] = 5  # Still some points even at higher CPC

    # --- Margin Score (20 points max) ---
    # Higher margin is better
    # > 75% = 20, 70-75% = 15, 65-70% = 10, < 65% = 5
    gross_margin = calculate_gross_margin(product)
    if gross_margin > 0.75:
        breakdown["margin"] = 20
    elif gross_margin > 0.70:
        breakdown["margin"] = 15
    elif gross_margin > 0.65:
        breakdown["margin"] = 10
    else:
        breakdown["margin"] = 5

    # --- AOV Score (15 points max) ---
    # Higher AOV is better (more margin room)
    # $100-150 = 15, $75-100 = 12, $50-75 = 8, < $50 = 3
    if 100 <= product.selling_price <= 150:
        breakdown["aov"] = 15
    elif 75 <= product.selling_price < 100:
        breakdown["aov"] = 12
    elif 50 <= product.selling_price < 75:
        breakdown["aov"] = 8
    else:
        breakdown["aov"] = 3

    # --- Competition Score (15 points max) ---
    # Less Amazon competition is better
    # No Amazon Prime = 15, Weak (< 50 reviews) = 10, Medium (< 200) = 5, Strong = 0
    if not product.amazon_prime_exists:
        breakdown["competition"] = 15
    elif product.amazon_review_count < 50:
        breakdown["competition"] = 10
    elif product.amazon_review_count < 200:
        breakdown["competition"] = 5
    else:
        breakdown["competition"] = 0

    # --- Search Volume Score (10 points max) ---
    # Higher volume is better (but not too high = too competitive)
    # 1k-10k = 10, 500-1k = 7, 100-500 = 4, < 100 = 2, > 10k = 5 (too competitive)
    if 1000 <= product.monthly_search_volume <= 10000:
        breakdown["volume"] = 10
    elif 500 <= product.monthly_search_volume < 1000:
        breakdown["volume"] = 7
    elif 100 <= product.monthly_search_volume < 500:
        breakdown["volume"] = 4
    elif product.monthly_search_volume > 10000:
        breakdown["volume"] = 5  # Too competitive
    else:
        breakdown["volume"] = 2

    # --- Refund Risk Score (10 points max) ---
    # Lower refund rate categories are better
    refund_rate = CATEGORY_REFUND_RATES.get(product.category, 0.08)
    if refund_rate <= 0.05:
        breakdown["refund_risk"] = 10  # Low risk
    elif refund_rate <= 0.08:
        breakdown["refund_risk"] = 7  # Medium risk
    elif refund_rate <= 0.10:
        breakdown["refund_risk"] = 4  # Higher risk
    else:
        breakdown["refund_risk"] = 0  # High risk (apparel, shoes)

    # --- Shipping Score (5 points max) ---
    # Faster/lighter shipping is better
    # < 500g, not fragile = 5, else = 2
    if product.weight_grams < 500 and not product.is_fragile:
        breakdown["shipping"] = 5
    elif product.weight_grams < 1000:
        breakdown["shipping"] = 3
    else:
        breakdown["shipping"] = 2

    # --- Niche Passion Score (5 points max) ---
    # Hobbyist/enthusiast categories get bonus
    if product.category in PASSION_NICHE_CATEGORIES:
        breakdown["passion"] = 5
    else:
        breakdown["passion"] = 2

    total = sum(breakdown.values())
    return total, breakdown


def score_product(
    product: Product,
    config: ScoringConfig | None = None,
) -> ProductScore:
    """Calculate complete score for a product.

    This is the main entry point for scoring a product.
    It calculates all financials, applies filters, and computes points.

    Args:
        product: Product to score
        config: Scoring configuration

    Returns:
        Complete ProductScore with all calculations
    """
    if config is None:
        config = ScoringConfig()

    # Calculate financials
    cogs = calculate_cogs(product)
    gross_margin = calculate_gross_margin(product)
    net_margin = calculate_net_margin(product, config)
    max_cpc = calculate_max_cpc(product, config)
    cpc_buffer = calculate_cpc_buffer(product, config)

    # Apply hard filters
    filter_result = apply_hard_filters(product, config)

    # Initialize score
    score = ProductScore(
        product_id=product.id,
        product_name=product.name,
        cogs=round(cogs, 2),
        gross_margin=round(gross_margin, 4),
        net_margin=round(net_margin, 4),
        max_cpc=round(max_cpc, 2),
        cpc_buffer=round(cpc_buffer, 2),
        passed_filters=filter_result.passed,
        rejection_reasons=filter_result.reasons,
        recommendation="REJECT",  # Default, will update below
    )

    # If passed filters, calculate points and rank
    if filter_result.passed:
        points, breakdown = calculate_points(product, config)
        rank_score = (points * 0.6) + (cpc_buffer * 25)

        score.points = points
        score.point_breakdown = breakdown
        score.rank_score = round(rank_score, 2)

        # Determine recommendation based on rank score
        if rank_score >= 95:
            score.recommendation = "STRONG BUY"
        elif rank_score >= 75:
            score.recommendation = "VIABLE"
        elif rank_score >= 60:
            score.recommendation = "MARGINAL"
        else:
            score.recommendation = "WEAK"

    return score
