"""Profit calculator API endpoints.

Computes profit margins, break-even units, and ROI given product cost,
selling price, shipping, and ad spend inputs.
"""

from pydantic import BaseModel, Field

from fastapi import APIRouter

router = APIRouter(prefix="/calculator", tags=["calculator"])


class ProfitCalculatorInput(BaseModel):
    """Input for profit calculator."""

    product_cost: float = Field(..., gt=0, description="Cost to source/purchase the product (USD)")
    selling_price: float = Field(..., gt=0, description="Price you'll sell the product at (USD)")
    shipping_cost: float = Field(0.0, ge=0, description="Shipping cost per unit (USD)")
    ad_spend_monthly: float = Field(0.0, ge=0, description="Monthly advertising budget (USD)")
    cpc: float = Field(0.0, ge=0, description="Cost per click for ads (USD)")
    cvr: float = Field(
        0.02, gt=0, le=1.0, description="Conversion rate as decimal (e.g. 0.02 = 2%)"
    )
    payment_fee_rate: float = Field(
        0.03, ge=0, le=1.0, description="Payment processing fee rate (default 3%)"
    )
    refund_rate: float = Field(
        0.08, ge=0, le=1.0, description="Expected refund/return rate (default 8%)"
    )
    fixed_costs_monthly: float = Field(
        0.0, ge=0, description="Monthly fixed costs (tools, subscriptions, etc.)"
    )


class ProfitBreakdown(BaseModel):
    """Detailed profit breakdown per unit."""

    revenue: float = Field(..., description="Revenue per unit (selling price)")
    cogs: float = Field(..., description="Cost of goods sold (product + shipping)")
    gross_profit: float = Field(..., description="Revenue - COGS")
    gross_margin_pct: float = Field(..., description="Gross margin percentage")
    payment_fees: float = Field(..., description="Payment processing fees per unit")
    refund_cost: float = Field(..., description="Expected refund cost per unit")
    net_profit_per_unit: float = Field(..., description="Profit per unit after fees/refunds")
    net_margin_pct: float = Field(..., description="Net margin percentage")


class AdMetrics(BaseModel):
    """Advertising efficiency metrics."""

    cost_per_acquisition: float = Field(..., description="Cost to acquire one customer via ads (CPA)")
    clicks_per_sale: float = Field(..., description="Clicks needed for one sale (1/CVR)")
    monthly_clicks: float = Field(..., description="Total clicks from monthly ad spend")
    monthly_sales_from_ads: float = Field(..., description="Expected sales from ad spend")
    roas: float | None = Field(None, description="Return on ad spend (revenue / ad spend)")
    profit_after_ads_per_unit: float = Field(
        ..., description="Net profit per unit after subtracting CPA"
    )
    ad_profitable: bool = Field(
        ..., description="Whether ads are profitable (profit after CPA > 0)"
    )


class BreakEvenAnalysis(BaseModel):
    """Break-even analysis."""

    break_even_units: int = Field(
        ..., description="Units needed to break even on monthly costs"
    )
    break_even_revenue: float = Field(
        ..., description="Revenue at break-even point"
    )
    monthly_fixed_costs: float = Field(
        ..., description="Total monthly fixed costs (ads + fixed costs)"
    )


class ProfitCalculatorResult(BaseModel):
    """Complete profit calculator output."""

    # Core profit metrics
    profit: ProfitBreakdown

    # Ad metrics (only if ads configured)
    ads: AdMetrics | None = None

    # Break-even analysis
    break_even: BreakEvenAnalysis

    # Summary metrics
    roi_pct: float = Field(
        ..., description="Return on investment percentage per unit"
    )
    max_cpc: float = Field(
        ...,
        description="Maximum CPC you can afford and still be profitable",
    )


def _calculate_profit(input: ProfitCalculatorInput) -> ProfitCalculatorResult:
    """Pure function to calculate profit metrics."""

    # Per-unit calculations
    revenue = input.selling_price
    cogs = input.product_cost + input.shipping_cost
    gross_profit = revenue - cogs
    gross_margin_pct = (gross_profit / revenue * 100) if revenue > 0 else 0.0

    payment_fees = revenue * input.payment_fee_rate
    refund_cost = revenue * input.refund_rate
    net_profit_per_unit = gross_profit - payment_fees - refund_cost
    net_margin_pct = (net_profit_per_unit / revenue * 100) if revenue > 0 else 0.0

    profit = ProfitBreakdown(
        revenue=round(revenue, 2),
        cogs=round(cogs, 2),
        gross_profit=round(gross_profit, 2),
        gross_margin_pct=round(gross_margin_pct, 1),
        payment_fees=round(payment_fees, 2),
        refund_cost=round(refund_cost, 2),
        net_profit_per_unit=round(net_profit_per_unit, 2),
        net_margin_pct=round(net_margin_pct, 1),
    )

    # Ad metrics
    ads = None
    if input.cpc > 0 and input.ad_spend_monthly > 0:
        clicks_per_sale = 1.0 / input.cvr
        cpa = input.cpc * clicks_per_sale
        monthly_clicks = input.ad_spend_monthly / input.cpc
        monthly_sales = monthly_clicks * input.cvr
        monthly_revenue = monthly_sales * revenue
        roas = (monthly_revenue / input.ad_spend_monthly) if input.ad_spend_monthly > 0 else None
        profit_after_ads = net_profit_per_unit - cpa

        ads = AdMetrics(
            cost_per_acquisition=round(cpa, 2),
            clicks_per_sale=round(clicks_per_sale, 1),
            monthly_clicks=round(monthly_clicks, 0),
            monthly_sales_from_ads=round(monthly_sales, 1),
            roas=round(roas, 2) if roas is not None else None,
            profit_after_ads_per_unit=round(profit_after_ads, 2),
            ad_profitable=profit_after_ads > 0,
        )

    # Break-even analysis
    monthly_fixed = input.ad_spend_monthly + input.fixed_costs_monthly
    effective_profit = net_profit_per_unit
    if ads:
        effective_profit = ads.profit_after_ads_per_unit

    if effective_profit > 0:
        break_even_units = int(
            -(-monthly_fixed // effective_profit)  # ceiling division
        ) if monthly_fixed > 0 else 0
    else:
        # Not profitable per unit, can't break even
        break_even_units = -1  # signals impossible

    break_even_revenue = break_even_units * revenue if break_even_units >= 0 else 0.0

    break_even = BreakEvenAnalysis(
        break_even_units=break_even_units,
        break_even_revenue=round(break_even_revenue, 2),
        monthly_fixed_costs=round(monthly_fixed, 2),
    )

    # ROI per unit (based on COGS investment)
    roi_pct = (net_profit_per_unit / cogs * 100) if cogs > 0 else 0.0

    # Max CPC: most you can pay per click and break even
    # max_cpc = net_profit_per_unit * CVR
    max_cpc = net_profit_per_unit * input.cvr if net_profit_per_unit > 0 else 0.0

    return ProfitCalculatorResult(
        profit=profit,
        ads=ads,
        break_even=break_even,
        roi_pct=round(roi_pct, 1),
        max_cpc=round(max_cpc, 2),
    )


@router.post("/profit", response_model=ProfitCalculatorResult)
async def calculate_profit(
    input: ProfitCalculatorInput,
) -> ProfitCalculatorResult:
    """Calculate profit margins, break-even units, and ROI.

    Given product cost, selling price, shipping, and ad spend inputs,
    returns a complete profitability analysis including:
    - Per-unit profit breakdown (gross/net margins)
    - Advertising metrics (CPA, ROAS, ad profitability)
    - Break-even analysis (units needed to cover monthly costs)
    - ROI and maximum affordable CPC
    """
    return _calculate_profit(input)
