"""CJ Dropshipping API client for product sourcing and order fulfillment.

Implements SPIKE-003 requirements:
- Authentication (access token, refresh)
- Product catalog queries
- Freight calculation
- Order creation

API Documentation: https://developers.cjdropshipping.com/
See: PLAN/04_risks_and_spikes.md (SPIKE-003)
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

import requests


class OrderStatus(Enum):
    """Order status values from CJ API."""

    CREATED = "CREATED"
    PENDING = "PENDING"
    IN_CART = "IN_CART"
    UNPAID = "UNPAID"
    UNSHIPPED = "UNSHIPPED"
    SHIPPED = "SHIPPED"
    DELIVERED = "DELIVERED"
    CANCELLED = "CANCELLED"


class CJError(Exception):
    """Wrapper for CJ Dropshipping API errors."""

    def __init__(self, message: str, code: int = 0, request_id: str = ""):
        super().__init__(message)
        self.code = code
        self.request_id = request_id

    def __str__(self) -> str:
        parts = [super().__str__()]
        if self.code:
            parts.append(f"code={self.code}")
        if self.request_id:
            parts.append(f"request_id={self.request_id}")
        return " ".join(parts)


def safe_decimal(val, default=None) -> Optional[Decimal]:
    """Safely parse a value to Decimal, returning default on failure."""
    if val is None or val == "":
        return default
    try:
        return Decimal(str(val))
    except Exception:
        return default


def safe_int(val, default=None) -> Optional[int]:
    """Safely parse a value to int, returning default on failure."""
    if val is None or val == "":
        return default
    try:
        return int(val)
    except Exception:
        return default


@dataclass
class CJConfig:
    """Configuration for CJ Dropshipping API access.

    Attributes:
        api_key: CJ API key in format "CJUserNum@api@[key]"
    """

    api_key: str

    def __post_init__(self):
        """Validate configuration."""
        if not self.api_key:
            raise ValueError("api_key is required")
        # Validate format: CJUserNum@api@[key]
        if not re.match(r"^[A-Za-z0-9]+@api@[A-Za-z0-9]+$", self.api_key):
            raise ValueError("api_key must be in format 'CJUserNum@api@[key]'")


@dataclass
class ProductVariant:
    """Product variant from CJ catalog."""

    vid: str
    name: str
    sku: str
    weight: Decimal
    sell_price: Decimal
    length: Optional[Decimal] = None
    width: Optional[Decimal] = None
    height: Optional[Decimal] = None

    @classmethod
    def from_api_response(cls, data: dict) -> "ProductVariant":
        """Create from API response data."""
        return cls(
            vid=data.get("vid", ""),
            name=data.get("variantNameEn") or data.get("variantName", ""),
            sku=data.get("variantSku", ""),
            weight=safe_decimal(data.get("variantWeight"), Decimal("0")),
            sell_price=safe_decimal(data.get("variantSellPrice"), Decimal("0")),
            length=safe_decimal(data.get("variantLength")),
            width=safe_decimal(data.get("variantWidth")),
            height=safe_decimal(data.get("variantHeight")),
        )


@dataclass
class Product:
    """Product from CJ catalog.

    Contains comprehensive data for product analysis including:
    - Basic product info (name, price, category)
    - Warehouse/inventory data (location, stock levels)
    - Shipping data (costs, delivery times, processing)
    - Supplier data (ID, name, ratings)
    - Sales/quality indicators (listed count, sale status)
    """

    # Core product info
    pid: str
    name: str
    sku: str
    image_url: str
    sell_price: Decimal
    category_id: str
    category_name: str
    weight: Optional[Decimal] = None
    description: Optional[str] = None
    variants: list[ProductVariant] = field(default_factory=list)

    # Supplier info
    supplier_id: Optional[str] = None
    supplier_name: Optional[str] = None

    # Warehouse/inventory info
    warehouse_country: Optional[str] = None  # countryCode - where it ships from (CN, US, etc.)
    warehouse_inventory: Optional[int] = None  # warehouseInventoryNum - total stock
    verified_warehouse: bool = False  # verifiedWarehouse - verified inventory
    total_verified_inventory: Optional[int] = None  # totalVerifiedInventory

    # Shipping/delivery info
    trial_freight: Optional[Decimal] = None  # Estimated shipping cost to US
    is_free_shipping: bool = False  # isFreeShipping or addMarkStatus=1
    freight_discount: Optional[Decimal] = None  # freightDiscount percentage
    delivery_time_hours: Optional[int] = None  # deliveryTime: 24, 48, or 72
    delivery_cycle_days: Optional[int] = None  # deliveryCycle - processing + shipping days

    # Product status/quality
    sale_status: Optional[str] = None  # saleStatus - ON_SALE, OUT_OF_STOCK, etc.
    listed_num: Optional[int] = None  # listedNum - times this has been listed/sold
    product_type: Optional[str] = None  # productType - ORDINARY, POD, etc.

    # Additional raw data for debugging/analysis
    raw_api_data: Optional[dict] = None

    @classmethod
    def from_api_response(cls, data: dict, include_raw: bool = False) -> "Product":
        """Create from API response data.

        Args:
            data: Raw API response dictionary
            include_raw: If True, store raw API data for debugging
        """
        variants = [
            ProductVariant.from_api_response(v)
            for v in data.get("variants", [])
        ]
        # Parse free shipping flag (multiple possible indicators)
        is_free = (
            data.get("isFreeShipping") == True
            or data.get("addMarkStatus") == 1
            or str(data.get("isFreeShipping", "")).lower() == "true"
        )

        return cls(
            # Core info
            pid=data.get("pid", ""),
            name=data.get("productNameEn") or data.get("productName", ""),
            sku=data.get("productSku", ""),
            image_url=data.get("productImage", ""),
            sell_price=safe_decimal(data.get("sellPrice"), Decimal("0")),
            category_id=data.get("categoryId", ""),
            category_name=data.get("categoryName", ""),
            weight=safe_decimal(data.get("productWeight")),
            description=data.get("description"),
            variants=variants,

            # Supplier
            supplier_id=data.get("supplierId"),
            supplier_name=data.get("supplierName"),

            # Warehouse/inventory
            warehouse_country=data.get("countryCode"),
            warehouse_inventory=safe_int(data.get("warehouseInventoryNum")),
            verified_warehouse=data.get("verifiedWarehouse") == True,
            total_verified_inventory=safe_int(data.get("totalVerifiedInventory")),

            # Shipping
            trial_freight=safe_decimal(data.get("trialFreight")),
            is_free_shipping=is_free,
            freight_discount=safe_decimal(data.get("freightDiscount")),
            delivery_time_hours=safe_int(data.get("deliveryTime")),
            delivery_cycle_days=safe_int(data.get("deliveryCycle")),

            # Status/quality
            sale_status=data.get("saleStatus"),
            listed_num=safe_int(data.get("listedNum")),
            product_type=data.get("productType"),

            # Raw data
            raw_api_data=data if include_raw else None,
        )


@dataclass
class FreightOption:
    """Shipping option from freight calculation."""

    name: str
    price: Decimal
    price_cny: Decimal
    delivery_days: str  # e.g., "2-5"

    @classmethod
    def from_api_response(cls, data: dict) -> "FreightOption":
        """Create from API response data."""
        return cls(
            name=data.get("logisticName", ""),
            price=Decimal(str(data.get("logisticPrice", 0))),
            price_cny=Decimal(str(data.get("logisticPriceCn", 0))),
            delivery_days=data.get("logisticAging", ""),
        )


@dataclass
class Order:
    """Order from CJ API."""

    order_id: str
    order_number: str
    status: OrderStatus
    postage_amount: Decimal
    product_amount: Decimal
    order_amount: Decimal
    tracking_number: Optional[str] = None
    shipment_order_id: Optional[str] = None

    @classmethod
    def from_api_response(cls, data: dict) -> "Order":
        """Create from API response data."""
        status_str = data.get("orderStatus", "CREATED")
        try:
            status = OrderStatus(status_str)
        except ValueError:
            status = OrderStatus.PENDING

        return cls(
            order_id=data.get("orderId", ""),
            order_number=data.get("orderNumber", ""),
            status=status,
            postage_amount=Decimal(str(data.get("postageAmount", 0))),
            product_amount=Decimal(str(data.get("productAmount", 0))),
            order_amount=Decimal(str(data.get("orderAmount", 0))),
            tracking_number=data.get("trackNumber"),
            shipment_order_id=data.get("shipmentOrderId"),
        )


class CJDropshippingClient:
    """Client for CJ Dropshipping API operations.

    Provides methods for:
    - Getting access tokens and authentication
    - Querying product catalog
    - Calculating shipping costs
    - Creating and managing orders

    Usage:
        config = CJConfig(api_key=os.getenv("CJ_API_KEY"))
        client = CJDropshippingClient(config)
        client.get_access_token()
        products = client.list_products(keyword="fitness tracker")
    """

    BASE_URL = "https://developers.cjdropshipping.com/api2.0/v1"

    def __init__(self, config: CJConfig):
        """Initialize client with configuration."""
        self.config = config
        self._access_token: Optional[str] = None
        self._refresh_token: Optional[str] = None
        self._token_expires: Optional[datetime] = None

    def _get_headers(self) -> dict:
        """Get request headers with authentication."""
        headers = {"Content-Type": "application/json"}
        if self._access_token:
            headers["CJ-Access-Token"] = self._access_token
        return headers

    def _handle_response(self, response: requests.Response) -> dict:
        """Handle API response and check for errors."""
        try:
            response.raise_for_status()
        except requests.HTTPError as e:
            raise CJError(str(e))

        data = response.json()

        # Check for API-level errors
        # Success: HTTP 200 AND (code=200 OR no code field)
        code = data.get("code", 200)
        if code != 200:
            raise CJError(
                message=data.get("message", "Unknown error"),
                code=code,
                request_id=data.get("requestId", ""),
            )

        return data.get("data")

    def _require_auth(self) -> None:
        """Ensure client is authenticated."""
        if not self._access_token:
            raise CJError("Not authenticated. Call get_access_token() first.")

    # Authentication methods

    def get_access_token(self) -> str:
        """Get access token from CJ API.

        Returns:
            Access token string.

        Raises:
            CJError: If authentication fails.
        """
        url = f"{self.BASE_URL}/authentication/getAccessToken"
        payload = {"apiKey": self.config.api_key}

        response = requests.post(url, json=payload)
        data = self._handle_response(response)

        self._access_token = data.get("accessToken")
        self._refresh_token = data.get("refreshToken")

        if data.get("accessTokenExpiryDate"):
            self._token_expires = datetime.fromisoformat(
                data["accessTokenExpiryDate"].replace("Z", "+00:00")
            )

        return self._access_token

    def refresh_access_token(self) -> str:
        """Refresh access token using refresh token.

        Returns:
            New access token string.

        Raises:
            CJError: If refresh fails.
        """
        if not self._refresh_token:
            raise CJError("No refresh token available. Call get_access_token() first.")

        url = f"{self.BASE_URL}/authentication/refreshAccessToken"
        payload = {"refreshToken": self._refresh_token}

        response = requests.post(url, json=payload)
        data = self._handle_response(response)

        self._access_token = data.get("accessToken")
        self._refresh_token = data.get("refreshToken")

        if data.get("accessTokenExpiryDate"):
            self._token_expires = datetime.fromisoformat(
                data["accessTokenExpiryDate"].replace("Z", "+00:00")
            )

        return self._access_token

    # Product catalog methods

    def list_products(
        self,
        keyword: Optional[str] = None,
        category_id: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
        min_price: Optional[Decimal] = None,
        max_price: Optional[Decimal] = None,
        country_code: Optional[str] = None,
    ) -> list[Product]:
        """List products from CJ catalog.

        Args:
            keyword: Search by product name.
            category_id: Filter by category.
            page: Page number (1-based).
            page_size: Items per page (max 200).
            min_price: Minimum price filter.
            max_price: Maximum price filter.
            country_code: Warehouse location filter.

        Returns:
            List of Product objects.

        Raises:
            CJError: If API call fails.
        """
        self._require_auth()

        url = f"{self.BASE_URL}/product/list"
        params = {
            "pageNum": page,
            "pageSize": min(page_size, 200),
        }

        if keyword:
            params["productNameEn"] = keyword
        if category_id:
            params["categoryId"] = category_id
        if min_price is not None:
            params["minPrice"] = float(min_price)
        if max_price is not None:
            params["maxPrice"] = float(max_price)
        if country_code:
            params["countryCode"] = country_code

        response = requests.get(url, params=params, headers=self._get_headers())
        data = self._handle_response(response)

        products = []
        for item in data.get("list", []):
            products.append(Product.from_api_response(item))

        return products

    def get_product(
        self,
        pid: Optional[str] = None,
        sku: Optional[str] = None,
        country_code: Optional[str] = None,
    ) -> Product:
        """Get product details by ID or SKU.

        Args:
            pid: Product ID.
            sku: Product SKU.
            country_code: Warehouse location filter.

        Returns:
            Product object with variants.

        Raises:
            ValueError: If neither pid nor sku provided.
            CJError: If API call fails.
        """
        self._require_auth()

        if not pid and not sku:
            raise ValueError("Either pid or sku must be provided")

        url = f"{self.BASE_URL}/product/query"
        params = {}

        if pid:
            params["pid"] = pid
        if sku:
            params["productSku"] = sku
        if country_code:
            params["countryCode"] = country_code

        response = requests.get(url, params=params, headers=self._get_headers())
        data = self._handle_response(response)

        return Product.from_api_response(data)

    def get_categories(self) -> list[dict]:
        """Get product categories.

        Returns:
            List of category dictionaries with hierarchy.

        Raises:
            CJError: If API call fails.
        """
        self._require_auth()

        url = f"{self.BASE_URL}/product/getCategory"
        response = requests.get(url, headers=self._get_headers())
        return self._handle_response(response)

    # Freight calculation methods

    def calculate_freight(
        self,
        start_country: str,
        end_country: str,
        products: list[dict],
    ) -> list[FreightOption]:
        """Calculate shipping options and costs.

        Args:
            start_country: Source country code (e.g., "CN").
            end_country: Destination country code (e.g., "US").
            products: List of dicts with "vid" or "sku" and "quantity".

        Returns:
            List of FreightOption objects sorted by price.

        Raises:
            CJError: If API call fails.
        """
        self._require_auth()

        url = f"{self.BASE_URL}/logistic/freightCalculate"
        payload = {
            "startCountryCode": start_country,
            "endCountryCode": end_country,
            "products": products,
        }

        response = requests.post(url, json=payload, headers=self._get_headers())
        data = self._handle_response(response)

        options = [FreightOption.from_api_response(item) for item in data or []]
        return sorted(options, key=lambda x: x.price)

    # Order methods

    def create_order(
        self,
        order_number: str,
        shipping_country_code: str,
        shipping_country: str,
        shipping_province: str,
        shipping_city: str,
        shipping_address: str,
        shipping_zip: str,
        shipping_customer_name: str,
        shipping_phone: str,
        logistic_name: str,
        from_country_code: str,
        products: list[dict],
        shipping_address2: Optional[str] = None,
        shipping_email: Optional[str] = None,
        remark: Optional[str] = None,
    ) -> Order:
        """Create a new order.

        Args:
            order_number: Your order reference number.
            shipping_country_code: Destination country code.
            shipping_country: Destination country name.
            shipping_province: State/province.
            shipping_city: City.
            shipping_address: Street address.
            shipping_zip: Postal code.
            shipping_customer_name: Recipient name.
            shipping_phone: Contact phone.
            logistic_name: Shipping method name from freight calc.
            from_country_code: Source warehouse country.
            products: List of dicts with "vid" and "quantity".
            shipping_address2: Optional address line 2.
            shipping_email: Optional email.
            remark: Optional order notes.

        Returns:
            Created Order object.

        Raises:
            CJError: If order creation fails.
        """
        self._require_auth()

        url = f"{self.BASE_URL}/shopping/order/createOrderV2"
        payload = {
            "orderNumber": order_number,
            "shippingCountryCode": shipping_country_code,
            "shippingCountry": shipping_country,
            "shippingProvince": shipping_province,
            "shippingCity": shipping_city,
            "shippingAddress": shipping_address,
            "shippingZip": shipping_zip,
            "shippingCustomerName": shipping_customer_name,
            "shippingPhone": shipping_phone,
            "logisticName": logistic_name,
            "fromCountryCode": from_country_code,
            "products": products,
        }

        if shipping_address2:
            payload["shippingAddress2"] = shipping_address2
        if shipping_email:
            payload["shippingEmail"] = shipping_email
        if remark:
            payload["remark"] = remark

        response = requests.post(url, json=payload, headers=self._get_headers())
        data = self._handle_response(response)

        return Order.from_api_response(data)

    def get_order(self, order_id: str) -> Order:
        """Get order details.

        Args:
            order_id: CJ order ID.

        Returns:
            Order object with status and tracking.

        Raises:
            CJError: If API call fails.
        """
        self._require_auth()

        url = f"{self.BASE_URL}/shopping/order/getOrderDetail"
        params = {"orderId": order_id}

        response = requests.get(url, params=params, headers=self._get_headers())
        data = self._handle_response(response)

        return Order.from_api_response(data)

    def list_orders(
        self,
        page: int = 1,
        page_size: int = 20,
        status: Optional[OrderStatus] = None,
        order_ids: Optional[list[str]] = None,
    ) -> list[Order]:
        """List orders.

        Args:
            page: Page number (1-based).
            page_size: Items per page.
            status: Filter by order status.
            order_ids: Filter by specific order IDs.

        Returns:
            List of Order objects.

        Raises:
            CJError: If API call fails.
        """
        self._require_auth()

        url = f"{self.BASE_URL}/shopping/order/list"
        params = {
            "pageNum": page,
            "pageSize": page_size,
        }

        if status:
            params["status"] = status.value
        if order_ids:
            params["orderIds"] = ",".join(order_ids)

        response = requests.get(url, params=params, headers=self._get_headers())
        data = self._handle_response(response)

        orders = []
        for item in data.get("list", []):
            orders.append(Order.from_api_response(item))

        return orders

    def confirm_order(self, order_id: str) -> bool:
        """Confirm an order for fulfillment.

        Args:
            order_id: CJ order ID.

        Returns:
            True if successful.

        Raises:
            CJError: If confirmation fails.
        """
        self._require_auth()

        url = f"{self.BASE_URL}/shopping/order/confirmOrder"
        payload = {"orderId": order_id}

        response = requests.patch(url, json=payload, headers=self._get_headers())
        self._handle_response(response)

        return True
