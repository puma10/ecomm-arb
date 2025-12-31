"""Tests for Keepa API client."""

from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from ecom_arb.integrations.keepa import (
    BuyBoxData,
    KeepaClient,
    KeepaConfig,
    KeepaError,
    PricePoint,
    ProductData,
    ProductType,
)


class TestKeepaConfig:
    """Tests for KeepaConfig."""

    def test_valid_config(self):
        """Valid config should initialize without error."""
        config = KeepaConfig(api_key="test-key-123")
        assert config.api_key == "test-key-123"
        assert config.domain == "1"  # Default US
        assert config.timeout == 30

    def test_missing_api_key_raises(self):
        """Missing API key should raise ValueError."""
        with pytest.raises(ValueError, match="api_key is required"):
            KeepaConfig(api_key="")

    def test_custom_domain(self):
        """Should allow custom domain."""
        config = KeepaConfig(api_key="test", domain="3")  # UK
        assert config.domain == "3"


class TestPricePoint:
    """Tests for PricePoint."""

    def test_price_dollars_conversion(self):
        """Should convert cents to dollars."""
        point = PricePoint(
            timestamp=datetime(2024, 1, 1),
            price_cents=2499,
        )
        assert point.price_dollars == Decimal("24.99")

    def test_out_of_stock_price(self):
        """Out of stock should return None for price_dollars."""
        point = PricePoint(
            timestamp=datetime(2024, 1, 1),
            price_cents=-1,
        )
        assert point.price_dollars is None


class TestBuyBoxData:
    """Tests for BuyBoxData."""

    def test_total_price(self):
        """Should calculate total price including shipping."""
        buy_box = BuyBoxData(
            is_amazon=False,
            is_fba=True,
            seller_id="ABC123",
            price_cents=1999,
            shipping_cents=499,
        )
        assert buy_box.total_price_cents == 2498
        assert buy_box.total_price_dollars == Decimal("24.98")


class TestProductData:
    """Tests for ProductData."""

    def test_current_price_dollars(self):
        """Should convert current price to dollars."""
        product = ProductData(
            asin="B08N5WRWNW",
            title="Test Product",
            brand="TestBrand",
            product_group="Electronics",
            current_price_cents=4999,
            current_amazon_price_cents=5299,
            current_new_price_cents=4999,
            current_used_price_cents=3999,
            buy_box=None,
            is_prime_eligible=True,
            is_available=True,
            review_count=150,
            rating=Decimal("4.5"),
            sales_rank=1000,
            price_history=[],
        )
        assert product.current_price_dollars == Decimal("49.99")

    def test_has_amazon_offer(self):
        """Should detect when Amazon is selling."""
        product = ProductData(
            asin="B08N5WRWNW",
            title="Test",
            brand=None,
            product_group=None,
            current_price_cents=4999,
            current_amazon_price_cents=5299,
            current_new_price_cents=4999,
            current_used_price_cents=-1,
            buy_box=None,
            is_prime_eligible=False,
            is_available=True,
            review_count=0,
            rating=None,
            sales_rank=None,
            price_history=[],
        )
        assert product.has_amazon_offer is True

    def test_no_amazon_offer(self):
        """Should detect when Amazon is not selling."""
        product = ProductData(
            asin="B08N5WRWNW",
            title="Test",
            brand=None,
            product_group=None,
            current_price_cents=4999,
            current_amazon_price_cents=-1,
            current_new_price_cents=4999,
            current_used_price_cents=-1,
            buy_box=None,
            is_prime_eligible=False,
            is_available=True,
            review_count=0,
            rating=None,
            sales_rank=None,
            price_history=[],
        )
        assert product.has_amazon_offer is False

    def test_price_90d_low_high(self):
        """Should calculate 90-day low/high prices."""
        history = [
            PricePoint(datetime(2024, 1, 1), 2999),
            PricePoint(datetime(2024, 1, 15), 3499),
            PricePoint(datetime(2024, 2, 1), 2499),  # Low
            PricePoint(datetime(2024, 2, 15), 3999),  # High
            PricePoint(datetime(2024, 3, 1), -1),  # Out of stock
        ]
        product = ProductData(
            asin="B08N5WRWNW",
            title="Test",
            brand=None,
            product_group=None,
            current_price_cents=2999,
            current_amazon_price_cents=-1,
            current_new_price_cents=2999,
            current_used_price_cents=-1,
            buy_box=None,
            is_prime_eligible=False,
            is_available=True,
            review_count=0,
            rating=None,
            sales_rank=None,
            price_history=history,
        )
        assert product.price_90d_low_cents == 2499
        assert product.price_90d_high_cents == 3999


class TestKeepaClient:
    """Tests for KeepaClient."""

    @pytest.fixture
    def client(self):
        """Create a test client."""
        config = KeepaConfig(api_key="test-key")
        return KeepaClient(config)

    def test_keepa_time_conversion(self, client):
        """Should convert Keepa time to datetime."""
        # Keepa time is minutes since 2011-01-01
        # 1 year = 525600 minutes
        result = client._keepa_time_to_datetime(525600)
        expected = datetime(2012, 1, 1)
        assert result == expected

    def test_parse_price_history(self, client):
        """Should parse Keepa CSV price data."""
        # CSV format: [time1, price1, time2, price2, ...]
        csv_data = [
            None,  # Index 0: Amazon
            [525600, 2999, 525601, 3499, 525602, -1],  # Index 1: New
        ]
        history = client._parse_price_history(csv_data, 1)

        assert len(history) == 3
        assert history[0].price_cents == 2999
        assert history[1].price_cents == 3499
        assert history[2].price_cents == -1  # Out of stock

    @patch.object(KeepaClient, "_request")
    def test_get_tokens_left(self, mock_request, client):
        """Should return remaining tokens."""
        mock_request.return_value = {"tokensLeft": 500}

        tokens = client.get_tokens_left()

        assert tokens == 500
        mock_request.assert_called_once()

    @patch.object(KeepaClient, "_request")
    def test_get_products(self, mock_request, client):
        """Should parse product response."""
        mock_request.return_value = {
            "products": [
                {
                    "asin": "B08N5WRWNW",
                    "title": "Test Product",
                    "brand": "TestBrand",
                    "productGroup": "Electronics",
                    "rating": 45,  # 4.5 stars
                    "reviewCount": 150,
                    "stats": {
                        "current": [5299, 4999, 3999, 1000],  # Amazon, New, Used, Rank
                    },
                    "csv": [
                        [525600, 5299],  # Amazon prices
                        [525600, 4999, 525601, 5199],  # New prices
                    ],
                }
            ]
        }

        products = client.get_products(["B08N5WRWNW"])

        assert len(products) == 1
        product = products[0]
        assert product.asin == "B08N5WRWNW"
        assert product.title == "Test Product"
        assert product.brand == "TestBrand"
        assert product.current_amazon_price_cents == 5299
        assert product.current_new_price_cents == 4999
        assert product.rating == Decimal("4.5")
        assert product.review_count == 150
        assert product.sales_rank == 1000

    @patch.object(KeepaClient, "_request")
    def test_get_product_single(self, mock_request, client):
        """Should get single product."""
        mock_request.return_value = {
            "products": [
                {
                    "asin": "B08N5WRWNW",
                    "title": "Test",
                    "stats": {"current": [2999, 2999, -1, 500]},
                }
            ]
        }

        product = client.get_product("B08N5WRWNW")

        assert product is not None
        assert product.asin == "B08N5WRWNW"

    @patch.object(KeepaClient, "_request")
    def test_get_product_not_found(self, mock_request, client):
        """Should return None for non-existent product."""
        mock_request.return_value = {"products": []}

        product = client.get_product("INVALID123")

        assert product is None

    @patch.object(KeepaClient, "_request")
    def test_check_competition_with_amazon(self, mock_request, client):
        """Should detect Amazon competition."""
        mock_request.return_value = {
            "products": [
                {
                    "asin": "B08N5WRWNW",
                    "title": "Test",
                    "stats": {"current": [2999, 2999, -1, 500]},
                    "buyBoxSellerIdHistory": [525600, "ATVPDKIKX0DER"],  # Amazon US
                    "csv": [None] * 19,  # 19 price types
                }
            ]
        }

        result = client.check_competition("B08N5WRWNW")

        assert result["has_amazon"] is True
        assert result["is_competitive"] is True

    @patch.object(KeepaClient, "_request")
    def test_check_competition_no_amazon(self, mock_request, client):
        """Should detect when Amazon is not competing."""
        mock_request.return_value = {
            "products": [
                {
                    "asin": "B08N5WRWNW",
                    "title": "Test",
                    "stats": {"current": [-1, 2999, -1, 500]},  # No Amazon price
                }
            ]
        }

        result = client.check_competition("B08N5WRWNW")

        assert result["has_amazon"] is False

    def test_max_asins_validation(self, client):
        """Should reject more than 100 ASINs."""
        asins = [f"B{i:09d}" for i in range(101)]

        with pytest.raises(ValueError, match="Maximum 100 ASINs"):
            client.get_products(asins)


class TestKeepaError:
    """Tests for KeepaError."""

    def test_error_with_tokens(self):
        """Should store tokens_left."""
        error = KeepaError("Test error", tokens_left=100)
        assert str(error) == "Test error"
        assert error.tokens_left == 100

    def test_rate_limit_error(self):
        """Should flag rate limit errors."""
        error = KeepaError("Rate limited", tokens_left=0, is_rate_limit=True)
        assert error.is_rate_limit is True
