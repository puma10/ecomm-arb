"""Keepa API client for Amazon product data.

Implements SPIKE-004 requirements (using Keepa as Amazon PA-API alternative):
- Product lookup by ASIN
- Price history
- Buy box data
- Prime status

See: PLAN/04_risks_and_spikes.md (SPIKE-004)
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Optional

import httpx


class KeepaError(Exception):
    """Wrapper for Keepa API errors."""

    def __init__(self, message: str, tokens_left: int = -1, is_rate_limit: bool = False):
        super().__init__(message)
        self.tokens_left = tokens_left
        self.is_rate_limit = is_rate_limit


class ProductType(Enum):
    """Amazon product condition types."""

    NEW = "NEW"
    USED = "USED"
    REFURBISHED = "REFURBISHED"
    COLLECTIBLE = "COLLECTIBLE"


@dataclass
class PricePoint:
    """A single price point in history."""

    timestamp: datetime
    price_cents: int  # Price in cents, -1 = out of stock

    @property
    def price_dollars(self) -> Optional[Decimal]:
        """Price in dollars, None if out of stock."""
        if self.price_cents < 0:
            return None
        return Decimal(self.price_cents) / 100


@dataclass
class BuyBoxData:
    """Buy box information for a product."""

    is_amazon: bool  # Amazon is the buy box winner
    is_fba: bool  # FBA seller has buy box
    seller_id: Optional[str]
    price_cents: int
    shipping_cents: int

    @property
    def total_price_cents(self) -> int:
        """Total price including shipping."""
        return self.price_cents + self.shipping_cents

    @property
    def total_price_dollars(self) -> Decimal:
        """Total price in dollars."""
        return Decimal(self.total_price_cents) / 100


@dataclass
class ProductData:
    """Amazon product data from Keepa."""

    asin: str
    title: str
    brand: Optional[str]
    product_group: Optional[str]  # Category

    # Current prices (cents, -1 = unavailable)
    current_price_cents: int
    current_amazon_price_cents: int  # Amazon as seller
    current_new_price_cents: int  # Lowest new offer
    current_used_price_cents: int  # Lowest used

    # Buy box
    buy_box: Optional[BuyBoxData]

    # Status flags
    is_prime_eligible: bool
    is_available: bool

    # Stats
    review_count: int
    rating: Optional[Decimal]  # 0-5 scale
    sales_rank: Optional[int]

    # Price history (last 90 days)
    price_history: list[PricePoint]

    @property
    def current_price_dollars(self) -> Optional[Decimal]:
        """Current price in dollars, None if unavailable."""
        if self.current_price_cents < 0:
            return None
        return Decimal(self.current_price_cents) / 100

    @property
    def has_amazon_offer(self) -> bool:
        """Whether Amazon is selling this product."""
        return self.current_amazon_price_cents > 0

    @property
    def price_90d_low_cents(self) -> Optional[int]:
        """Lowest price in last 90 days."""
        valid_prices = [p.price_cents for p in self.price_history if p.price_cents > 0]
        return min(valid_prices) if valid_prices else None

    @property
    def price_90d_high_cents(self) -> Optional[int]:
        """Highest price in last 90 days."""
        valid_prices = [p.price_cents for p in self.price_history if p.price_cents > 0]
        return max(valid_prices) if valid_prices else None


@dataclass
class KeepaConfig:
    """Configuration for Keepa API access."""

    api_key: str
    domain: str = "1"  # 1 = amazon.com (US)
    timeout: int = 30

    def __post_init__(self):
        """Validate configuration."""
        if not self.api_key:
            raise ValueError("api_key is required")


class KeepaClient:
    """Client for Keepa API operations.

    Provides methods for:
    - Getting product data by ASIN
    - Price history lookup
    - Buy box analysis
    - Prime eligibility check

    Usage:
        config = KeepaConfig(api_key="your-api-key")
        client = KeepaClient(config)
        product = client.get_product("B08N5WRWNW")
    """

    BASE_URL = "https://api.keepa.com"

    # Keepa time offset (minutes since 2011-01-01)
    KEEPA_EPOCH = datetime(2011, 1, 1)

    # Price type indices in Keepa data arrays
    PRICE_TYPE_AMAZON = 0
    PRICE_TYPE_NEW = 1
    PRICE_TYPE_USED = 2
    PRICE_TYPE_SALES_RANK = 3
    PRICE_TYPE_LIST_PRICE = 4
    PRICE_TYPE_NEW_FBM = 7  # New FBM shipping
    PRICE_TYPE_BUY_BOX = 18

    def __init__(self, config: KeepaConfig):
        """Initialize client with configuration."""
        self.config = config
        self._client = httpx.Client(timeout=config.timeout)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self._client.close()

    def close(self):
        """Close the HTTP client."""
        self._client.close()

    def _keepa_time_to_datetime(self, keepa_minutes: int) -> datetime:
        """Convert Keepa time (minutes since 2011-01-01) to datetime."""
        return self.KEEPA_EPOCH + timedelta(minutes=keepa_minutes)

    def _parse_price_history(self, csv_data: Optional[list], price_type: int) -> list[PricePoint]:
        """Parse Keepa CSV price history data."""
        if not csv_data or price_type >= len(csv_data) or not csv_data[price_type]:
            return []

        data = csv_data[price_type]
        history = []

        # Data is pairs of [time, price, time, price, ...]
        for i in range(0, len(data) - 1, 2):
            keepa_time = data[i]
            price = data[i + 1]

            if keepa_time is not None and price is not None:
                history.append(
                    PricePoint(
                        timestamp=self._keepa_time_to_datetime(keepa_time),
                        price_cents=price if price >= 0 else -1,
                    )
                )

        return history

    def _parse_buy_box(self, product: dict) -> Optional[BuyBoxData]:
        """Parse buy box data from product response."""
        # Check for buy box seller info
        buy_box_seller = product.get("buyBoxSellerIdHistory")
        if not buy_box_seller or len(buy_box_seller) < 2:
            return None

        # Get current buy box seller (last entry)
        current_seller = buy_box_seller[-1] if buy_box_seller else None

        # Get buy box price from CSV data
        csv = product.get("csv")
        buy_box_price = -1
        if csv and len(csv) > self.PRICE_TYPE_BUY_BOX and csv[self.PRICE_TYPE_BUY_BOX]:
            prices = csv[self.PRICE_TYPE_BUY_BOX]
            if len(prices) >= 2:
                buy_box_price = prices[-1] if prices[-1] is not None else -1

        if buy_box_price < 0:
            return None

        is_amazon = current_seller == "ATVPDKIKX0DER"  # Amazon US seller ID

        return BuyBoxData(
            is_amazon=is_amazon,
            is_fba=product.get("fbaFees") is not None,
            seller_id=current_seller if not is_amazon else None,
            price_cents=buy_box_price,
            shipping_cents=0,  # Buy box typically includes shipping
        )

    def _request(self, endpoint: str, params: dict) -> dict:
        """Make API request."""
        params["key"] = self.config.api_key

        response = self._client.get(
            f"{self.BASE_URL}/{endpoint}",
            params=params,
        )

        if response.status_code == 429:
            raise KeepaError(
                "Rate limit exceeded",
                tokens_left=0,
                is_rate_limit=True,
            )

        if response.status_code != 200:
            raise KeepaError(f"API error: {response.status_code} - {response.text}")

        data = response.json()

        # Check for API errors
        if "error" in data:
            error = data["error"]
            raise KeepaError(
                f"Keepa error: {error.get('message', 'Unknown error')}",
                tokens_left=data.get("tokensLeft", -1),
            )

        return data

    def get_tokens_left(self) -> int:
        """Get remaining API tokens.

        Returns:
            Number of tokens remaining.

        Raises:
            KeepaError: If API call fails.
        """
        data = self._request("token", {"domain": self.config.domain})
        return data.get("tokensLeft", 0)

    def get_product(self, asin: str) -> Optional[ProductData]:
        """Get product data by ASIN.

        Args:
            asin: Amazon Standard Identification Number.

        Returns:
            ProductData object or None if not found.

        Raises:
            KeepaError: If API call fails.
        """
        return self.get_products([asin])[0] if self.get_products([asin]) else None

    def get_products(self, asins: list[str]) -> list[ProductData]:
        """Get product data for multiple ASINs.

        Args:
            asins: List of ASINs (max 100).

        Returns:
            List of ProductData objects.

        Raises:
            KeepaError: If API call fails.
            ValueError: If more than 100 ASINs provided.
        """
        if len(asins) > 100:
            raise ValueError("Maximum 100 ASINs per request")

        if not asins:
            return []

        data = self._request(
            "product",
            {
                "domain": self.config.domain,
                "asin": ",".join(asins),
                "stats": "90",  # Include 90-day stats
                "buybox": "1",  # Include buy box data
                "history": "1",  # Include price history
            },
        )

        products = []
        for product in data.get("products", []):
            # Get current prices from stats
            stats = product.get("stats", {})
            current = stats.get("current", [])

            # Extract prices (index matches PRICE_TYPE_* constants)
            amazon_price = current[self.PRICE_TYPE_AMAZON] if len(current) > self.PRICE_TYPE_AMAZON else -1
            new_price = current[self.PRICE_TYPE_NEW] if len(current) > self.PRICE_TYPE_NEW else -1
            used_price = current[self.PRICE_TYPE_USED] if len(current) > self.PRICE_TYPE_USED else -1
            sales_rank = current[self.PRICE_TYPE_SALES_RANK] if len(current) > self.PRICE_TYPE_SALES_RANK else None

            # Determine current price (prefer buy box, then amazon, then new)
            buy_box = self._parse_buy_box(product)
            if buy_box and buy_box.price_cents > 0:
                current_price = buy_box.price_cents
            elif amazon_price and amazon_price > 0:
                current_price = amazon_price
            elif new_price and new_price > 0:
                current_price = new_price
            else:
                current_price = -1

            # Parse price history (use NEW prices for arbitrage)
            price_history = self._parse_price_history(
                product.get("csv"),
                self.PRICE_TYPE_NEW,
            )

            # Check Prime eligibility
            is_prime = product.get("isPrimeExclusive", False) or (
                buy_box is not None and buy_box.is_fba
            )

            # Rating is stored as integer (45 = 4.5 stars)
            rating_int = product.get("rating")
            rating = Decimal(rating_int) / 10 if rating_int else None

            products.append(
                ProductData(
                    asin=product.get("asin", ""),
                    title=product.get("title", ""),
                    brand=product.get("brand"),
                    product_group=product.get("productGroup"),
                    current_price_cents=current_price if current_price else -1,
                    current_amazon_price_cents=amazon_price if amazon_price else -1,
                    current_new_price_cents=new_price if new_price else -1,
                    current_used_price_cents=used_price if used_price else -1,
                    buy_box=buy_box,
                    is_prime_eligible=is_prime,
                    is_available=current_price > 0,
                    review_count=product.get("reviewCount", 0) or 0,
                    rating=rating,
                    sales_rank=sales_rank if sales_rank and sales_rank > 0 else None,
                    price_history=price_history,
                )
            )

        return products

    def get_price_history(
        self,
        asin: str,
        days: int = 90,
        product_type: ProductType = ProductType.NEW,
    ) -> list[PricePoint]:
        """Get price history for a product.

        Args:
            asin: Amazon Standard Identification Number.
            days: Number of days of history (max 365).
            product_type: Type of prices to fetch.

        Returns:
            List of PricePoint objects.

        Raises:
            KeepaError: If API call fails.
        """
        # Map product type to Keepa price type index
        type_map = {
            ProductType.NEW: self.PRICE_TYPE_NEW,
            ProductType.USED: self.PRICE_TYPE_USED,
            ProductType.REFURBISHED: self.PRICE_TYPE_USED,  # Keepa groups with used
            ProductType.COLLECTIBLE: self.PRICE_TYPE_USED,
        }

        data = self._request(
            "product",
            {
                "domain": self.config.domain,
                "asin": asin,
                "stats": str(min(days, 365)),
                "history": "1",
            },
        )

        products = data.get("products", [])
        if not products:
            return []

        price_type = type_map.get(product_type, self.PRICE_TYPE_NEW)
        return self._parse_price_history(products[0].get("csv"), price_type)

    def check_competition(self, asin: str) -> dict:
        """Check Amazon competition for a product.

        Args:
            asin: Amazon Standard Identification Number.

        Returns:
            Dict with competition analysis:
            - has_amazon: Amazon is selling
            - has_fba: FBA sellers present
            - buy_box_price: Current buy box price
            - seller_count: Number of sellers
            - is_competitive: True if hard to compete

        Raises:
            KeepaError: If API call fails.
        """
        products = self.get_products([asin])
        if not products:
            return {
                "has_amazon": False,
                "has_fba": False,
                "buy_box_price": None,
                "seller_count": 0,
                "is_competitive": False,
            }

        product = products[0]

        return {
            "has_amazon": product.has_amazon_offer,
            "has_fba": product.buy_box.is_fba if product.buy_box else False,
            "buy_box_price": product.buy_box.total_price_dollars if product.buy_box else None,
            "seller_count": product.review_count,  # Proxy for popularity
            "is_competitive": product.has_amazon_offer or (
                product.buy_box is not None and product.buy_box.is_fba
            ),
        }
