"""Tests for the product scanner service.

Tests cover:
- URL validation and supplier detection
- CJ product page parsing
- Price suggestion logic
- API endpoint integration
"""

from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from ecom_arb.services.product_scanner import (
    ScanError,
    ScannedProduct,
    _suggest_price,
    detect_supplier,
    scan_product_url,
)
from ecom_arb.db.models import SupplierSource


class TestDetectSupplier:
    """Tests for supplier detection from URLs."""

    def test_cj_dropshipping(self):
        assert detect_supplier("https://cjdropshipping.com/product/test-p-123.html") == SupplierSource.CJ

    def test_cj_with_www(self):
        assert detect_supplier("https://www.cjdropshipping.com/product/test-p-123.html") == SupplierSource.CJ

    def test_aliexpress(self):
        assert detect_supplier("https://www.aliexpress.com/item/123.html") == SupplierSource.ALIEXPRESS

    def test_aliexpress_us(self):
        assert detect_supplier("https://aliexpress.us/item/123.html") == SupplierSource.ALIEXPRESS

    def test_amazon(self):
        assert detect_supplier("https://www.amazon.com/dp/B001234") == SupplierSource.AMAZON

    def test_temu(self):
        assert detect_supplier("https://www.temu.com/product-123.html") == SupplierSource.TEMU

    def test_ebay(self):
        assert detect_supplier("https://www.ebay.com/itm/123456") == SupplierSource.EBAY

    def test_unknown_supplier(self):
        assert detect_supplier("https://example.com/product") is None

    def test_empty_url(self):
        assert detect_supplier("") is None


class TestSuggestPrice:
    """Tests for price suggestion logic."""

    def test_low_cost_3x_markup(self):
        """Products under $20 get ~3x markup."""
        price = _suggest_price(Decimal("10"))
        assert price == Decimal("29.99")

    def test_mid_cost_2_5x_markup(self):
        """Products $20-50 get ~2.5x markup."""
        price = _suggest_price(Decimal("30"))
        assert price == Decimal("74.99")

    def test_high_cost_2x_markup(self):
        """Products $50+ get ~2x markup."""
        price = _suggest_price(Decimal("60"))
        assert price == Decimal("119.99")

    def test_zero_cost(self):
        assert _suggest_price(Decimal("0")) == Decimal("0")

    def test_negative_cost(self):
        assert _suggest_price(Decimal("-5")) == Decimal("0")

    def test_very_small_cost(self):
        """Very cheap products still get a reasonable suggestion."""
        price = _suggest_price(Decimal("1"))
        assert price > Decimal("1")


class TestScanProductUrl:
    """Tests for the main scan_product_url function."""

    @pytest.mark.asyncio
    async def test_invalid_url(self):
        """Invalid URLs raise ScanError."""
        with pytest.raises(ScanError, match="Invalid URL"):
            await scan_product_url("not-a-url")

    @pytest.mark.asyncio
    async def test_unsupported_supplier(self):
        """Unknown suppliers raise ScanError."""
        with pytest.raises(ScanError, match="Unsupported supplier"):
            await scan_product_url("https://unknown-store.com/product/123")

    @pytest.mark.asyncio
    async def test_cj_product_scan(self):
        """Scanning a CJ URL fetches and parses the product."""
        mock_html = _build_cj_product_html(
            product_id="12345",
            name="Test LED Light Strip",
            sell_price_min=8.50,
            sell_price_max=12.00,
            sku="CJ-LED-001",
            warehouse_country="US",
            delivery_cycle_days=5,
        )

        with patch(
            "ecom_arb.services.product_scanner._fetch_page",
            new_callable=AsyncMock,
            return_value=mock_html,
        ):
            result = await scan_product_url(
                "https://cjdropshipping.com/product/test-led-light-strip-p-12345.html"
            )

        assert isinstance(result, ScannedProduct)
        assert result.supplier_source == "cj"
        assert result.name == "Test LED Light Strip"
        assert result.cost == Decimal("8.5")
        assert result.suggested_price > result.cost
        assert result.supplier_sku == "CJ-LED-001"
        assert result.warehouse_country == "US"
        assert result.shipping_days_min >= 1
        assert result.shipping_days_max > result.shipping_days_min

    @pytest.mark.asyncio
    async def test_cj_removed_product(self):
        """Removed CJ products raise ScanError."""
        mock_html = '<html><script>window.productDetailData = {}</script></html>'

        with patch(
            "ecom_arb.services.product_scanner._fetch_page",
            new_callable=AsyncMock,
            return_value=mock_html,
        ):
            with pytest.raises(ScanError, match="parse"):
                await scan_product_url(
                    "https://cjdropshipping.com/product/removed-p-99999.html"
                )

    @pytest.mark.asyncio
    async def test_network_timeout(self):
        """Network timeouts are handled gracefully."""
        import httpx

        with patch(
            "ecom_arb.services.product_scanner._fetch_page",
            new_callable=AsyncMock,
            side_effect=ScanError("Request timed out", error_type="timeout"),
        ):
            with pytest.raises(ScanError, match="timed out"):
                await scan_product_url(
                    "https://cjdropshipping.com/product/slow-p-11111.html"
                )

    @pytest.mark.asyncio
    async def test_to_dict_serialization(self):
        """ScannedProduct.to_dict() returns JSON-serializable data."""
        product = ScannedProduct(
            supplier_source="cj",
            supplier_url="https://example.com",
            supplier_sku="SKU-1",
            name="Test Product",
            cost=Decimal("10.50"),
            suggested_price=Decimal("29.99"),
        )

        d = product.to_dict()
        assert d["cost"] == "10.50"
        assert d["suggested_price"] == "29.99"
        assert d["supplier_source"] == "cj"


def _build_cj_product_html(
    product_id: str = "12345",
    name: str = "Test Product",
    sell_price_min: float = 10.0,
    sell_price_max: float = 15.0,
    sku: str = "CJ-TEST-001",
    warehouse_country: str = "CN",
    delivery_cycle_days: int = 10,
    image_url: str = "https://cbu01.alicdn.com/test-image.jpg",
) -> str:
    """Build a minimal CJ product page HTML for testing."""
    return f"""
    <html>
    <head><title>{name} - CJ Dropshipping</title></head>
    <body>
    <script>
    window.productDetailData = {{
        "id": "{product_id}",
        "nameEn": "{name}",
        "sku": "{sku}",
        "sellPrice": {sell_price_min},
        "sellPriceMin": {sell_price_min},
        "sellPriceMax": {sell_price_max},
        "weight": 200,
        "warehouseCountry": "{warehouse_country}",
        "warehouseInventory": 500,
        "deliveryCycleDays": {delivery_cycle_days},
        "imageUrl": "{image_url}",
        "isFreeShipping": false,
        "category": [{{"name": "LED Lights"}}],
        "variants": [
            {{"sku": "{sku}-V1", "sellPrice": {sell_price_min}, "weight": 200}}
        ]
    }};
    </script>
    </body>
    </html>
    """
