"""Tests for the profit calculator API."""

import pytest
from httpx import ASGITransport, AsyncClient

from ecom_arb.api.app import app
from ecom_arb.api.routers.calculator import _calculate_profit, ProfitCalculatorInput


# ── Unit tests for _calculate_profit ────────────────────────────────


class TestCalculateProfit:
    """Unit tests for the pure calculation function."""

    def test_basic_profit(self):
        """Basic profitable product."""
        input = ProfitCalculatorInput(
            product_cost=15,
            selling_price=50,
            shipping_cost=5,
            ad_spend_monthly=0,
            cpc=0,
            cvr=0.02,
            payment_fee_rate=0.03,
            refund_rate=0.08,
            fixed_costs_monthly=0,
        )
        result = _calculate_profit(input)

        assert result.profit.revenue == 50.0
        assert result.profit.cogs == 20.0  # 15 + 5
        assert result.profit.gross_profit == 30.0  # 50 - 20
        assert result.profit.gross_margin_pct == 60.0
        # Payment fees: 50 * 0.03 = 1.50
        assert result.profit.payment_fees == 1.50
        # Refund cost: 50 * 0.08 = 4.00
        assert result.profit.refund_cost == 4.00
        # Net profit: 30 - 1.50 - 4.00 = 24.50
        assert result.profit.net_profit_per_unit == 24.50
        assert result.ads is None
        assert result.roi_pct > 0

    def test_unprofitable_product(self):
        """Product where costs exceed revenue."""
        input = ProfitCalculatorInput(
            product_cost=45,
            selling_price=50,
            shipping_cost=10,
            ad_spend_monthly=0,
            cpc=0,
            cvr=0.02,
            payment_fee_rate=0.03,
            refund_rate=0.08,
            fixed_costs_monthly=0,
        )
        result = _calculate_profit(input)

        # COGS = 55, revenue = 50, so gross_profit = -5
        assert result.profit.cogs == 55.0
        assert result.profit.gross_profit == -5.0
        assert result.profit.net_profit_per_unit < 0

    def test_with_ads(self):
        """Test with ad spend configured."""
        input = ProfitCalculatorInput(
            product_cost=10,
            selling_price=50,
            shipping_cost=5,
            ad_spend_monthly=500,
            cpc=0.50,
            cvr=0.02,
            payment_fee_rate=0.03,
            refund_rate=0.08,
            fixed_costs_monthly=0,
        )
        result = _calculate_profit(input)

        assert result.ads is not None
        # CPA = CPC / CVR = 0.50 / 0.02 = 25.00
        assert result.ads.cost_per_acquisition == 25.0
        # Clicks per sale = 1 / 0.02 = 50
        assert result.ads.clicks_per_sale == 50.0
        # Monthly clicks = 500 / 0.50 = 1000
        assert result.ads.monthly_clicks == 1000
        # Monthly sales = 1000 * 0.02 = 20
        assert result.ads.monthly_sales_from_ads == 20.0
        # ROAS = (20 * 50) / 500 = 2.0
        assert result.ads.roas == 2.0

    def test_break_even_with_fixed_costs(self):
        """Break-even when there are fixed costs."""
        input = ProfitCalculatorInput(
            product_cost=10,
            selling_price=50,
            shipping_cost=5,
            ad_spend_monthly=500,
            cpc=0.50,
            cvr=0.02,
            payment_fee_rate=0.03,
            refund_rate=0.08,
            fixed_costs_monthly=100,
        )
        result = _calculate_profit(input)

        # Monthly fixed = 500 (ads) + 100 (fixed) = 600
        assert result.break_even.monthly_fixed_costs == 600.0
        assert result.break_even.break_even_units > 0

    def test_break_even_impossible(self):
        """Break-even impossible when unit profit is negative."""
        input = ProfitCalculatorInput(
            product_cost=45,
            selling_price=50,
            shipping_cost=10,
            ad_spend_monthly=500,
            cpc=0.50,
            cvr=0.02,
            payment_fee_rate=0.03,
            refund_rate=0.08,
            fixed_costs_monthly=0,
        )
        result = _calculate_profit(input)

        assert result.break_even.break_even_units == -1

    def test_zero_fixed_costs_zero_break_even(self):
        """No fixed costs means break-even is 0 units."""
        input = ProfitCalculatorInput(
            product_cost=10,
            selling_price=50,
            shipping_cost=5,
            ad_spend_monthly=0,
            cpc=0,
            cvr=0.02,
            payment_fee_rate=0.03,
            refund_rate=0.08,
            fixed_costs_monthly=0,
        )
        result = _calculate_profit(input)

        assert result.break_even.break_even_units == 0

    def test_max_cpc_calculation(self):
        """Max CPC = net_profit_per_unit * CVR."""
        input = ProfitCalculatorInput(
            product_cost=10,
            selling_price=100,
            shipping_cost=5,
            ad_spend_monthly=0,
            cpc=0,
            cvr=0.02,
            payment_fee_rate=0.03,
            refund_rate=0.08,
            fixed_costs_monthly=0,
        )
        result = _calculate_profit(input)

        # Net profit = 100 - 15 - 3 - 8 = 74
        # Max CPC = 74 * 0.02 = 1.48
        assert result.max_cpc == 1.48

    def test_no_ads_when_cpc_zero(self):
        """No ad metrics when CPC is zero."""
        input = ProfitCalculatorInput(
            product_cost=10,
            selling_price=50,
            shipping_cost=5,
            ad_spend_monthly=500,
            cpc=0,
            cvr=0.02,
            payment_fee_rate=0.03,
            refund_rate=0.08,
            fixed_costs_monthly=0,
        )
        result = _calculate_profit(input)

        assert result.ads is None


# ── API endpoint tests ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_calculator_endpoint():
    """Test the /calculator/profit endpoint."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/calculator/profit",
            json={
                "product_cost": 15,
                "selling_price": 49.99,
                "shipping_cost": 5,
                "ad_spend_monthly": 500,
                "cpc": 0.5,
                "cvr": 0.02,
                "payment_fee_rate": 0.03,
                "refund_rate": 0.08,
                "fixed_costs_monthly": 0,
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert "profit" in data
    assert "break_even" in data
    assert "roi_pct" in data
    assert "max_cpc" in data
    assert data["profit"]["revenue"] == 49.99
    assert data["ads"] is not None


@pytest.mark.asyncio
async def test_calculator_validation_error():
    """Test validation errors on bad input."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/calculator/profit",
            json={
                "product_cost": -5,  # Invalid: must be > 0
                "selling_price": 50,
            },
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_calculator_minimal_input():
    """Test with only required fields."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/calculator/profit",
            json={
                "product_cost": 10,
                "selling_price": 50,
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["profit"]["cogs"] == 10.0  # No shipping
    assert data["ads"] is None  # No ad spend
