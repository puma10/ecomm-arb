"""Tests for Product Discovery Service."""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from ecom_arb.integrations.cj_dropshipping import (
    CJConfig,
    FreightOption,
    Product as CJProduct,
)
from ecom_arb.integrations.google_ads import CPCEstimate
from ecom_arb.integrations.keepa import BuyBoxData, ProductData as KeepaProduct
from ecom_arb.scoring.models import ProductCategory
from ecom_arb.services.discovery import DiscoveredProduct, DiscoveryService


class TestDiscoveredProduct:
    """Tests for DiscoveredProduct."""

    @pytest.fixture
    def cj_product(self):
        """Sample CJ product."""
        return CJProduct(
            pid="CJ123",
            name="Garden Tool Set",
            sku="SKU123",
            image_url="https://example.com/img.jpg",
            sell_price=Decimal("25.99"),
            category_id="garden",
            category_name="Garden Tools",
            weight=Decimal("800"),
            variants=[],
        )

    @pytest.fixture
    def freight(self):
        """Sample freight option."""
        return FreightOption(
            name="ePacket",
            price=Decimal("4.99"),
            price_cny=Decimal("35.00"),
            delivery_days="7-14",
        )

    def test_to_scoring_product_basic(self, cj_product, freight):
        """Should convert to scoring Product with basic data."""
        discovered = DiscoveredProduct(
            cj_product=cj_product,
            freight=freight,
            keepa_data=None,
            amazon_asin=None,
            cpc_estimate=None,
            category=ProductCategory.GARDEN,
            selling_price=Decimal("64.99"),
        )

        product = discovered.to_scoring_product()

        assert product.id == "CJ123"
        assert product.name == "Garden Tool Set"
        assert product.product_cost == 25.99
        assert product.shipping_cost == 4.99
        assert product.selling_price == 64.99
        assert product.category == ProductCategory.GARDEN
        assert product.weight_grams == 800
        assert product.shipping_days_min == 7
        assert product.shipping_days_max == 14
        assert product.source == "cj"

    def test_to_scoring_product_with_amazon_data(self, cj_product, freight):
        """Should include Amazon competition data from Keepa."""
        keepa_data = KeepaProduct(
            asin="B08TEST123",
            title="Similar Product",
            brand="TestBrand",
            product_group="Garden",
            current_price_cents=5999,
            current_amazon_price_cents=5499,
            current_new_price_cents=5999,
            current_used_price_cents=-1,
            buy_box=BuyBoxData(
                is_amazon=True,
                is_fba=True,
                seller_id=None,
                price_cents=5499,
                shipping_cents=0,
            ),
            is_prime_eligible=True,
            is_available=True,
            review_count=150,
            rating=Decimal("4.5"),
            sales_rank=5000,
            price_history=[],
        )

        discovered = DiscoveredProduct(
            cj_product=cj_product,
            freight=freight,
            keepa_data=keepa_data,
            amazon_asin="B08TEST123",
            cpc_estimate=None,
            category=ProductCategory.GARDEN,
            selling_price=Decimal("64.99"),
        )

        product = discovered.to_scoring_product()

        assert product.amazon_prime_exists is True
        assert product.amazon_review_count == 150

    def test_to_scoring_product_with_cpc_data(self, cj_product, freight):
        """Should include CPC data from Google Ads."""
        cpc_estimate = CPCEstimate(
            keyword="garden tools",
            avg_monthly_searches=5000,
            competition="MEDIUM",
            low_cpc=Decimal("0.35"),
            high_cpc=Decimal("0.75"),
        )

        discovered = DiscoveredProduct(
            cj_product=cj_product,
            freight=freight,
            keepa_data=None,
            amazon_asin=None,
            cpc_estimate=cpc_estimate,
            category=ProductCategory.GARDEN,
            selling_price=Decimal("64.99"),
        )

        product = discovered.to_scoring_product()

        assert product.estimated_cpc == 0.55  # avg of 0.35 and 0.75
        assert product.monthly_search_volume == 5000

    def test_shipping_days_parsing(self, cj_product):
        """Should parse various shipping day formats."""
        # Single value
        freight = FreightOption(
            name="Express",
            price=Decimal("9.99"),
            price_cny=Decimal("70.00"),
            delivery_days="5",
        )

        discovered = DiscoveredProduct(
            cj_product=cj_product,
            freight=freight,
            keepa_data=None,
            amazon_asin=None,
            cpc_estimate=None,
            category=ProductCategory.GARDEN,
            selling_price=Decimal("64.99"),
        )

        product = discovered.to_scoring_product()
        assert product.shipping_days_min == 5
        assert product.shipping_days_max == 5


class TestDiscoveryService:
    """Tests for DiscoveryService."""

    @pytest.fixture
    def mock_cj_config(self):
        """Mock CJ config that passes validation."""
        with patch.object(CJConfig, "__post_init__"):
            return CJConfig(api_key="TEST123@api@KEY456")

    def test_map_category_direct_match(self, mock_cj_config):
        """Should map known categories."""
        with patch("ecom_arb.services.discovery.CJDropshippingClient"):
            service = DiscoveryService(mock_cj_config)

        assert service._map_category("pet") == ProductCategory.PET
        assert service._map_category("tools") == ProductCategory.TOOLS
        assert service._map_category("garden") == ProductCategory.GARDEN

    def test_map_category_partial_match(self, mock_cj_config):
        """Should match partial category names."""
        with patch("ecom_arb.services.discovery.CJDropshippingClient"):
            service = DiscoveryService(mock_cj_config)

        assert service._map_category("pet supplies") == ProductCategory.PET
        assert service._map_category("outdoor camping gear") == ProductCategory.OUTDOOR

    def test_map_category_unknown(self, mock_cj_config):
        """Should default to HOME_DECOR for unknown categories."""
        with patch("ecom_arb.services.discovery.CJDropshippingClient"):
            service = DiscoveryService(mock_cj_config)

        assert service._map_category("xyz random stuff") == ProductCategory.HOME_DECOR

    def test_calculate_selling_price(self, mock_cj_config):
        """Should apply markup and round to .99."""
        with patch("ecom_arb.services.discovery.CJDropshippingClient"):
            service = DiscoveryService(mock_cj_config, markup=Decimal("2.5"))

        cj_product = CJProduct(
            pid="TEST1",
            name="Test",
            sku="SKU1",
            image_url="",
            sell_price=Decimal("20.00"),  # 20 * 2.5 = 50 -> 50.99
            category_id="",
            category_name="",
            variants=[],
        )

        price = service._calculate_selling_price(cj_product)
        assert price == Decimal("50.99")

    @patch("ecom_arb.services.discovery.CJDropshippingClient")
    def test_discover_products_empty(self, mock_cj_class, mock_cj_config):
        """Should return empty list when no products found."""
        mock_cj = MagicMock()
        mock_cj.get_products.return_value = []
        mock_cj_class.return_value = mock_cj

        service = DiscoveryService(mock_cj_config)
        products = service.discover_products(category="pet", limit=10)

        assert products == []
        mock_cj.get_products.assert_called_once()

    @patch("ecom_arb.services.discovery.CJDropshippingClient")
    def test_discover_products_with_freight(self, mock_cj_class, mock_cj_config):
        """Should fetch freight for each product."""
        mock_cj = MagicMock()
        mock_cj.get_products.return_value = [
            CJProduct(
                pid="P1",
                name="Product 1",
                sku="SKU1",
                image_url="",
                sell_price=Decimal("10.00"),
                category_id="pet",
                category_name="Pet Supplies",
                variants=[],
            )
        ]
        mock_cj.calculate_freight.return_value = [
            FreightOption(
                name="Standard",
                price=Decimal("3.99"),
                price_cny=Decimal("28.00"),
                delivery_days="10-20",
            )
        ]
        mock_cj_class.return_value = mock_cj

        service = DiscoveryService(mock_cj_config)
        products = service.discover_products(limit=1)

        assert len(products) == 1
        assert products[0].freight is not None
        assert products[0].freight.price == Decimal("3.99")

    @patch("ecom_arb.services.discovery.CJDropshippingClient")
    def test_discover_products_freight_failure(self, mock_cj_class, mock_cj_config):
        """Should handle freight calculation failures gracefully."""
        mock_cj = MagicMock()
        mock_cj.get_products.return_value = [
            CJProduct(
                pid="P1",
                name="Product 1",
                sku="SKU1",
                image_url="",
                sell_price=Decimal("10.00"),
                category_id="pet",
                category_name="Pet",
                variants=[],
            )
        ]
        mock_cj.calculate_freight.side_effect = Exception("API Error")
        mock_cj_class.return_value = mock_cj

        service = DiscoveryService(mock_cj_config)
        products = service.discover_products(limit=1)

        assert len(products) == 1
        assert products[0].freight is None  # Graceful failure
