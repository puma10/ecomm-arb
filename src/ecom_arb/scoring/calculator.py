"""Core financial calculations for product scoring.

Formulas from North Star Card:
    COGS = Product Cost + Shipping Cost
    Gross Margin = (Selling Price - COGS) / Selling Price
    Net Margin = Gross Margin - Payment Fees - Refund Rate - Chargeback Rate
    Max CPC = CVR × Selling Price × Net Margin
    CPC Buffer = Max CPC / (Estimated CPC × CPC Multiplier)
"""

from ecom_arb.scoring.models import (
    CATEGORY_REFUND_RATES,
    Product,
    ScoringConfig,
)


def calculate_cogs(product: Product) -> float:
    """Calculate Cost of Goods Sold.

    COGS = Product Cost + Shipping Cost

    Args:
        product: Product with cost and shipping data

    Returns:
        Total COGS in USD
    """
    return product.product_cost + product.shipping_cost


def calculate_gross_margin(product: Product) -> float:
    """Calculate gross margin percentage.

    Gross Margin = (Selling Price - COGS) / Selling Price

    Args:
        product: Product with pricing data

    Returns:
        Gross margin as decimal (e.g., 0.65 = 65%)
    """
    cogs = calculate_cogs(product)
    if product.selling_price <= 0:
        return 0.0
    return (product.selling_price - cogs) / product.selling_price


def calculate_net_margin(
    product: Product,
    config: ScoringConfig | None = None,
) -> float:
    """Calculate net margin after all deductions.

    Net Margin = Gross Margin - Payment Fees - Refund Rate - Chargeback Rate

    Args:
        product: Product with pricing and category data
        config: Scoring configuration (uses defaults if None)

    Returns:
        Net margin as decimal (e.g., 0.50 = 50%)
    """
    if config is None:
        config = ScoringConfig()

    gross_margin = calculate_gross_margin(product)

    # Get refund rate for category, fall back to default
    refund_rate = CATEGORY_REFUND_RATES.get(
        product.category,
        config.default_refund_rate,
    )

    net_margin = (
        gross_margin
        - config.payment_fee_rate
        - refund_rate
        - config.chargeback_rate
    )

    return net_margin


def calculate_max_cpc(
    product: Product,
    config: ScoringConfig | None = None,
) -> float:
    """Calculate maximum CPC we can afford.

    Max CPC = CVR × Selling Price × Net Margin

    Args:
        product: Product with pricing data
        config: Scoring configuration (uses defaults if None)

    Returns:
        Maximum CPC in USD
    """
    if config is None:
        config = ScoringConfig()

    net_margin = calculate_net_margin(product, config)

    max_cpc = config.cvr * product.selling_price * net_margin

    return max(0.0, max_cpc)  # Can't be negative


def calculate_cpc_buffer(
    product: Product,
    config: ScoringConfig | None = None,
) -> float:
    """Calculate CPC buffer ratio.

    CPC Buffer = Max CPC / (Estimated CPC × CPC Multiplier)

    A buffer > 1.5 means we have room for error.
    A buffer < 1.0 means we'll lose money at estimated CPC.

    Args:
        product: Product with CPC estimate
        config: Scoring configuration (uses defaults if None)

    Returns:
        CPC buffer ratio (e.g., 1.5 = 50% buffer)
    """
    if config is None:
        config = ScoringConfig()

    max_cpc = calculate_max_cpc(product, config)

    # Apply new account penalty multiplier to estimated CPC
    adjusted_cpc = product.estimated_cpc * config.cpc_multiplier

    if adjusted_cpc <= 0:
        return float("inf")  # No competition is infinitely good

    return max_cpc / adjusted_cpc
