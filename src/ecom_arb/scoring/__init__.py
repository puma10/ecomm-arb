"""Product scoring module."""

from ecom_arb.scoring.calculator import (
    calculate_cogs,
    calculate_cpc_buffer,
    calculate_gross_margin,
    calculate_max_cpc,
    calculate_net_margin,
)
from ecom_arb.scoring.filters import FilterResult, apply_hard_filters
from ecom_arb.scoring.models import Product, ProductScore, ScoringConfig
from ecom_arb.scoring.scorer import calculate_points, score_product

__all__ = [
    # Models
    "Product",
    "ProductScore",
    "ScoringConfig",
    # Calculator
    "calculate_cogs",
    "calculate_gross_margin",
    "calculate_net_margin",
    "calculate_max_cpc",
    "calculate_cpc_buffer",
    # Filters
    "FilterResult",
    "apply_hard_filters",
    # Scorer
    "calculate_points",
    "score_product",
]
