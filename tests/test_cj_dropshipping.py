"""Tests for CJ Dropshipping API client.

Tests cover:
- Authentication (access token, refresh)
- Product catalog queries
- Freight calculation
- Order creation

See: PLAN/04_risks_and_spikes.md (SPIKE-003)
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from ecom_arb.integrations.cj_dropshipping import (
    CJConfig,
    CJDropshippingClient,
    CJError,
    FreightOption,
    Order,
    OrderStatus,
    Product,
    ProductVariant,
)


class TestCJConfig:
    """Tests for CJConfig dataclass."""

    def test_valid_config(self):
        """Config with all required fields is valid."""
        config = CJConfig(api_key="CJ123@api@abc123def456")
        assert config.api_key == "CJ123@api@abc123def456"

    def test_missing_api_key_raises(self):
        """Config without api_key raises ValueError."""
        with pytest.raises(ValueError, match="api_key is required"):
            CJConfig(api_key="")

    def test_invalid_api_key_format_raises(self):
        """Config with invalid api_key format raises ValueError."""
        with pytest.raises(ValueError, match="api_key must be in format"):
            CJConfig(api_key="invalid-key-format")


class TestCJDropshippingClient:
    """Tests for CJDropshippingClient."""

    @pytest.fixture
    def config(self):
        """Valid CJ config."""
        return CJConfig(api_key="CJ123@api@abc123def456")

    @pytest.fixture
    def mock_response(self):
        """Create mock response factory."""
        def _make_response(data, code=200, result=True, message="Success"):
            response = MagicMock()
            response.status_code = 200
            response.json.return_value = {
                "code": code,
                "result": result,
                "message": message,
                "data": data,
                "requestId": "test-request-id",
            }
            return response
        return _make_response

    # Authentication tests

    @patch("ecom_arb.integrations.cj_dropshipping.requests.post")
    def test_get_access_token_success(self, mock_post, config, mock_response):
        """Successfully gets access token."""
        mock_post.return_value = mock_response({
            "accessToken": "test-access-token",
            "accessTokenExpiryDate": "2025-01-15T00:00:00Z",
            "refreshToken": "test-refresh-token",
            "refreshTokenExpiryDate": "2025-06-15T00:00:00Z",
        })

        client = CJDropshippingClient(config)
        token = client.get_access_token()

        assert token == "test-access-token"
        assert client._access_token == "test-access-token"
        assert client._refresh_token == "test-refresh-token"

    @patch("ecom_arb.integrations.cj_dropshipping.requests.post")
    def test_get_access_token_failure(self, mock_post, config, mock_response):
        """Failed auth raises CJError."""
        mock_post.return_value = mock_response(
            None, code=1600100, result=False, message="Invalid API key"
        )

        client = CJDropshippingClient(config)
        with pytest.raises(CJError, match="Invalid API key"):
            client.get_access_token()

    @patch("ecom_arb.integrations.cj_dropshipping.requests.post")
    def test_refresh_access_token(self, mock_post, config, mock_response):
        """Successfully refreshes access token."""
        mock_post.return_value = mock_response({
            "accessToken": "new-access-token",
            "accessTokenExpiryDate": "2025-01-30T00:00:00Z",
            "refreshToken": "new-refresh-token",
            "refreshTokenExpiryDate": "2025-07-01T00:00:00Z",
        })

        client = CJDropshippingClient(config)
        client._refresh_token = "old-refresh-token"
        token = client.refresh_access_token()

        assert token == "new-access-token"
        assert client._access_token == "new-access-token"

    # Product catalog tests

    @patch("ecom_arb.integrations.cj_dropshipping.requests.get")
    def test_list_products_success(self, mock_get, config, mock_response):
        """Successfully lists products."""
        mock_get.return_value = mock_response({
            "pageNum": 1,
            "pageSize": 20,
            "total": 100,
            "list": [
                {
                    "pid": "product-123",
                    "productName": "Test Product",
                    "productNameEn": "Test Product EN",
                    "productSku": "SKU-123",
                    "productImage": "https://example.com/image.jpg",
                    "sellPrice": 19.99,
                    "categoryId": "cat-1",
                    "categoryName": "Electronics",
                    "listedNum": 500,
                    "supplierId": "sup-1",
                    "supplierName": "Test Supplier",
                },
            ],
        })

        client = CJDropshippingClient(config)
        client._access_token = "test-token"
        products = client.list_products(page=1, page_size=20)

        assert len(products) == 1
        assert products[0].pid == "product-123"
        assert products[0].name == "Test Product EN"
        assert products[0].sku == "SKU-123"
        assert products[0].sell_price == Decimal("19.99")

    @patch("ecom_arb.integrations.cj_dropshipping.requests.get")
    def test_list_products_with_keyword(self, mock_get, config, mock_response):
        """Lists products filtered by keyword."""
        mock_get.return_value = mock_response({
            "pageNum": 1,
            "pageSize": 20,
            "total": 5,
            "list": [],
        })

        client = CJDropshippingClient(config)
        client._access_token = "test-token"
        client.list_products(keyword="fitness tracker")

        call_args = mock_get.call_args
        params = call_args.kwargs.get("params", {})
        assert "productNameEn" in params and params["productNameEn"] == "fitness tracker"

    @patch("ecom_arb.integrations.cj_dropshipping.requests.get")
    def test_get_product_by_id(self, mock_get, config, mock_response):
        """Gets product by ID with variants."""
        mock_get.return_value = mock_response({
            "pid": "product-123",
            "productName": "Test Product",
            "productNameEn": "Test Product EN",
            "productSku": "SKU-123",
            "productImage": "https://example.com/image.jpg",
            "productWeight": 0.5,
            "productType": "NORMAL",
            "categoryId": "cat-1",
            "categoryName": "Electronics",
            "description": "Product description",
            "variants": [
                {
                    "vid": "variant-1",
                    "variantName": "Black",
                    "variantNameEn": "Black",
                    "variantSku": "SKU-123-BLK",
                    "variantWeight": 0.5,
                    "variantSellPrice": 19.99,
                },
            ],
        })

        client = CJDropshippingClient(config)
        client._access_token = "test-token"
        product = client.get_product(pid="product-123")

        assert product.pid == "product-123"
        assert len(product.variants) == 1
        assert product.variants[0].vid == "variant-1"
        assert product.variants[0].sell_price == Decimal("19.99")

    @patch("ecom_arb.integrations.cj_dropshipping.requests.get")
    def test_get_product_by_sku(self, mock_get, config, mock_response):
        """Gets product by SKU."""
        mock_get.return_value = mock_response({
            "pid": "product-123",
            "productName": "Test Product",
            "productNameEn": "Test Product EN",
            "productSku": "SKU-123",
            "productImage": "https://example.com/image.jpg",
            "productWeight": 0.5,
            "productType": "NORMAL",
            "categoryId": "cat-1",
            "categoryName": "Electronics",
            "variants": [],
        })

        client = CJDropshippingClient(config)
        client._access_token = "test-token"
        product = client.get_product(sku="SKU-123")

        assert product.sku == "SKU-123"

    def test_get_product_requires_id_or_sku(self, config):
        """get_product requires either pid or sku."""
        client = CJDropshippingClient(config)
        client._access_token = "test-token"

        with pytest.raises(ValueError, match="Either pid or sku must be provided"):
            client.get_product()

    # Freight calculation tests

    @patch("ecom_arb.integrations.cj_dropshipping.requests.post")
    def test_calculate_freight_success(self, mock_post, config, mock_response):
        """Successfully calculates freight options."""
        mock_post.return_value = mock_response([
            {
                "logisticName": "USPS+",
                "logisticPrice": 4.71,
                "logisticPriceCn": 30.54,
                "logisticAging": "2-5",
            },
            {
                "logisticName": "CJPacket Ordinary",
                "logisticPrice": 2.50,
                "logisticPriceCn": 16.20,
                "logisticAging": "7-15",
            },
        ])

        client = CJDropshippingClient(config)
        client._access_token = "test-token"
        options = client.calculate_freight(
            start_country="CN",
            end_country="US",
            products=[{"vid": "variant-1", "quantity": 2}],
        )

        assert len(options) == 2
        # Sorted by price ascending, so CJPacket (2.50) comes first
        assert options[0].name == "CJPacket Ordinary"
        assert options[0].price == Decimal("2.50")
        assert options[0].delivery_days == "7-15"
        # USPS+ is second (4.71)
        assert options[1].name == "USPS+"
        assert options[1].price == Decimal("4.71")

    @patch("ecom_arb.integrations.cj_dropshipping.requests.post")
    def test_calculate_freight_with_sku(self, mock_post, config, mock_response):
        """Calculates freight using SKU instead of variant ID."""
        mock_post.return_value = mock_response([
            {
                "logisticName": "Standard",
                "logisticPrice": 3.00,
                "logisticPriceCn": 19.50,
                "logisticAging": "5-10",
            },
        ])

        client = CJDropshippingClient(config)
        client._access_token = "test-token"
        options = client.calculate_freight(
            start_country="CN",
            end_country="US",
            products=[{"sku": "SKU-123", "quantity": 1}],
        )

        assert len(options) == 1

    # Order creation tests

    @patch("ecom_arb.integrations.cj_dropshipping.requests.post")
    def test_create_order_success(self, mock_post, config, mock_response):
        """Successfully creates an order."""
        mock_post.return_value = mock_response({
            "orderId": "order-123",
            "orderNumber": "ORD-2025-001",
            "shipmentOrderId": "ship-456",
            "postageAmount": 4.71,
            "productAmount": 19.99,
            "orderAmount": 24.70,
            "orderStatus": "CREATED",
            "productInfoList": [
                {"vid": "variant-1", "quantity": 1},
            ],
        })

        client = CJDropshippingClient(config)
        client._access_token = "test-token"
        order = client.create_order(
            order_number="ORD-2025-001",
            shipping_country_code="US",
            shipping_country="United States",
            shipping_province="California",
            shipping_city="Los Angeles",
            shipping_address="123 Main St",
            shipping_zip="90001",
            shipping_customer_name="John Doe",
            shipping_phone="555-1234",
            logistic_name="USPS+",
            from_country_code="CN",
            products=[{"vid": "variant-1", "quantity": 1}],
        )

        assert order.order_id == "order-123"
        assert order.order_number == "ORD-2025-001"
        assert order.postage_amount == Decimal("4.71")
        assert order.product_amount == Decimal("19.99")
        assert order.order_amount == Decimal("24.70")
        assert order.status == OrderStatus.CREATED

    @patch("ecom_arb.integrations.cj_dropshipping.requests.post")
    def test_create_order_validation_error(self, mock_post, config, mock_response):
        """Order with invalid data raises CJError."""
        mock_post.return_value = mock_response(
            None, code=1600100, result=False, message="Param error"
        )

        client = CJDropshippingClient(config)
        client._access_token = "test-token"

        with pytest.raises(CJError, match="Param error"):
            client.create_order(
                order_number="ORD-2025-001",
                shipping_country_code="XX",  # Invalid country
                shipping_country="Invalid",
                shipping_province="Invalid",
                shipping_city="Invalid",
                shipping_address="Invalid",
                shipping_zip="00000",
                shipping_customer_name="Test",
                shipping_phone="000",
                logistic_name="USPS+",
                from_country_code="CN",
                products=[{"vid": "variant-1", "quantity": 1}],
            )

    # Order query tests

    @patch("ecom_arb.integrations.cj_dropshipping.requests.get")
    def test_get_order_success(self, mock_get, config, mock_response):
        """Successfully gets order details."""
        mock_get.return_value = mock_response({
            "orderId": "order-123",
            "orderNumber": "ORD-2025-001",
            "orderStatus": "SHIPPED",
            "trackNumber": "TRACK123456",
            "postageAmount": 4.71,
            "productAmount": 19.99,
            "orderAmount": 24.70,
        })

        client = CJDropshippingClient(config)
        client._access_token = "test-token"
        order = client.get_order(order_id="order-123")

        assert order.order_id == "order-123"
        assert order.status == OrderStatus.SHIPPED
        assert order.tracking_number == "TRACK123456"

    @patch("ecom_arb.integrations.cj_dropshipping.requests.get")
    def test_list_orders_success(self, mock_get, config, mock_response):
        """Successfully lists orders."""
        mock_get.return_value = mock_response({
            "pageNum": 1,
            "pageSize": 20,
            "total": 2,
            "list": [
                {
                    "orderId": "order-1",
                    "orderNumber": "ORD-001",
                    "orderStatus": "CREATED",
                    "postageAmount": 4.71,
                    "productAmount": 19.99,
                    "orderAmount": 24.70,
                },
                {
                    "orderId": "order-2",
                    "orderNumber": "ORD-002",
                    "orderStatus": "SHIPPED",
                    "trackNumber": "TRACK789",
                    "postageAmount": 5.00,
                    "productAmount": 29.99,
                    "orderAmount": 34.99,
                },
            ],
        })

        client = CJDropshippingClient(config)
        client._access_token = "test-token"
        orders = client.list_orders(page=1, page_size=20)

        assert len(orders) == 2
        assert orders[0].order_id == "order-1"
        assert orders[1].tracking_number == "TRACK789"

    # Error handling tests

    @patch("ecom_arb.integrations.cj_dropshipping.requests.get")
    def test_api_error_response(self, mock_get, config, mock_response):
        """API error response raises CJError with details."""
        mock_get.return_value = mock_response(
            None,
            code=1600100,
            result=False,
            message="Product not found",
        )

        client = CJDropshippingClient(config)
        client._access_token = "test-token"

        with pytest.raises(CJError) as exc_info:
            client.get_product(pid="invalid-id")

        assert "Product not found" in str(exc_info.value)
        assert exc_info.value.code == 1600100

    @patch("ecom_arb.integrations.cj_dropshipping.requests.get")
    def test_requires_authentication(self, mock_get, config):
        """API calls without token raise CJError."""
        client = CJDropshippingClient(config)
        # No token set

        with pytest.raises(CJError, match="Not authenticated"):
            client.list_products()

    @patch("ecom_arb.integrations.cj_dropshipping.requests.get")
    def test_http_error_handling(self, mock_get, config):
        """HTTP errors are wrapped in CJError."""
        import requests as req
        mock_get.return_value = MagicMock()
        mock_get.return_value.status_code = 500
        mock_get.return_value.raise_for_status.side_effect = req.HTTPError("Server error")

        client = CJDropshippingClient(config)
        client._access_token = "test-token"

        with pytest.raises(CJError, match="Server error"):
            client.list_products()


class TestProductVariant:
    """Tests for ProductVariant dataclass."""

    def test_from_api_response(self):
        """Creates variant from API response data."""
        data = {
            "vid": "v-123",
            "variantName": "Black / Large",
            "variantNameEn": "Black / Large",
            "variantSku": "SKU-BLK-L",
            "variantWeight": 0.5,
            "variantSellPrice": 19.99,
        }

        variant = ProductVariant.from_api_response(data)

        assert variant.vid == "v-123"
        assert variant.name == "Black / Large"
        assert variant.sku == "SKU-BLK-L"
        assert variant.weight == Decimal("0.5")
        assert variant.sell_price == Decimal("19.99")


class TestFreightOption:
    """Tests for FreightOption dataclass."""

    def test_from_api_response(self):
        """Creates freight option from API response."""
        data = {
            "logisticName": "USPS+",
            "logisticPrice": 4.71,
            "logisticPriceCn": 30.54,
            "logisticAging": "2-5",
        }

        option = FreightOption.from_api_response(data)

        assert option.name == "USPS+"
        assert option.price == Decimal("4.71")
        assert option.price_cny == Decimal("30.54")
        assert option.delivery_days == "2-5"


class TestOrderStatus:
    """Tests for OrderStatus enum."""

    def test_status_values(self):
        """OrderStatus has expected values."""
        assert OrderStatus.CREATED.value == "CREATED"
        assert OrderStatus.PENDING.value == "PENDING"
        assert OrderStatus.SHIPPED.value == "SHIPPED"
        assert OrderStatus.DELIVERED.value == "DELIVERED"
        assert OrderStatus.CANCELLED.value == "CANCELLED"
