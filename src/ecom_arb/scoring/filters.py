"""Hard filters for product rejection.

Products that fail any hard filter are immediately rejected.
These represent non-negotiable requirements from the North Star.
"""

from dataclasses import dataclass, field

from ecom_arb.scoring.calculator import (
    calculate_cpc_buffer,
    calculate_gross_margin,
)
from ecom_arb.scoring.models import (
    RESTRICTED_CATEGORIES,
    Product,
    ScoringConfig,
)


@dataclass
class FilterResult:
    """Result of applying hard filters to a product."""

    passed: bool
    reasons: list[str] = field(default_factory=list)

    def add_rejection(self, reason: str) -> None:
        """Add a rejection reason."""
        self.passed = False
        self.reasons.append(reason)


def apply_hard_filters(
    product: Product,
    config: ScoringConfig | None = None,
) -> FilterResult:
    """Apply all hard filters to a product.

    Hard filters from requirements (REQ-002):
    - Estimated CPC > $0.75
    - Gross margin < 65%
    - Selling price < $50 or > $200
    - Restricted category
    - Shipping time > 30 days
    - Requires sizing
    - Fragile/breakable
    - Amazon Prime competitor with 500+ reviews
    - Supplier rating < 4.6
    - Supplier age < 12 months
    - Supplier feedback < 500
    - No fast shipping option
    - CPC buffer < 1.5
    - Weight > 2kg

    Args:
        product: Product to evaluate
        config: Scoring configuration (uses defaults if None)

    Returns:
        FilterResult with pass/fail and rejection reasons
    """
    if config is None:
        config = ScoringConfig()

    result = FilterResult(passed=True)

    # --- Category Filters ---

    if product.category in RESTRICTED_CATEGORIES:
        result.add_rejection(f"Restricted category: {product.category.value}")

    # --- Pricing Filters ---

    if product.selling_price < config.min_selling_price:
        result.add_rejection(
            f"Selling price ${product.selling_price:.2f} < "
            f"minimum ${config.min_selling_price:.2f}"
        )

    if product.selling_price > config.max_selling_price:
        result.add_rejection(
            f"Selling price ${product.selling_price:.2f} > "
            f"maximum ${config.max_selling_price:.2f}"
        )

    gross_margin = calculate_gross_margin(product)
    if gross_margin < config.min_gross_margin:
        result.add_rejection(
            f"Gross margin {gross_margin:.1%} < minimum {config.min_gross_margin:.1%}"
        )

    # --- CPC Filters ---

    if product.estimated_cpc > config.max_cpc_threshold:
        result.add_rejection(
            f"Estimated CPC ${product.estimated_cpc:.2f} > "
            f"maximum ${config.max_cpc_threshold:.2f}"
        )

    cpc_buffer = calculate_cpc_buffer(product, config)
    if cpc_buffer < config.min_cpc_buffer:
        result.add_rejection(
            f"CPC buffer {cpc_buffer:.2f}x < minimum {config.min_cpc_buffer:.2f}x"
        )

    # --- Product Attribute Filters ---

    if product.requires_sizing:
        result.add_rejection("Product requires sizing (high return risk)")

    if product.is_fragile:
        result.add_rejection("Product is fragile (damage claim risk)")

    if product.weight_grams > config.max_weight_grams:
        result.add_rejection(
            f"Weight {product.weight_grams}g > maximum {config.max_weight_grams}g"
        )

    # --- Shipping Filters ---

    if product.shipping_days_max > config.max_shipping_days:
        result.add_rejection(
            f"Max shipping {product.shipping_days_max} days > "
            f"limit {config.max_shipping_days} days"
        )

    if not product.has_fast_shipping:
        result.add_rejection("No fast shipping option (ePacket/AliExpress Standard)")

    # --- Supplier Filters ---

    if product.supplier_rating < config.min_supplier_rating:
        result.add_rejection(
            f"Supplier rating {product.supplier_rating} < "
            f"minimum {config.min_supplier_rating}"
        )

    if product.supplier_age_months < config.min_supplier_age_months:
        result.add_rejection(
            f"Supplier age {product.supplier_age_months} months < "
            f"minimum {config.min_supplier_age_months} months"
        )

    if product.supplier_feedback_count < config.min_supplier_feedback:
        result.add_rejection(
            f"Supplier feedback {product.supplier_feedback_count} < "
            f"minimum {config.min_supplier_feedback}"
        )

    # --- Competition Filters ---

    if (
        product.amazon_prime_exists
        and product.amazon_review_count > config.max_amazon_reviews_for_competition
    ):
        result.add_rejection(
            f"Amazon Prime competitor with {product.amazon_review_count} reviews "
            f"(> {config.max_amazon_reviews_for_competition})"
        )

    return result
