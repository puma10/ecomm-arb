"""Product scanner service - extract product details from supplier URLs.

Takes a supplier URL, fetches the page, parses product data, and returns
structured data suitable for pre-filling the product creation form.
"""

import logging
import re
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from urllib.parse import urlparse

import httpx

from ecom_arb.db.models import SupplierSource
from ecom_arb.services.cj_parser import (
    CJParserError,
    CJProductData,
    parse_product_detail_data,
    transform_cj_data,
)

logger = logging.getLogger(__name__)


class ScanError(Exception):
    """Error during product scanning."""

    def __init__(self, message: str, error_type: str = "scan_error"):
        self.message = message
        self.error_type = error_type
        super().__init__(self.message)


@dataclass
class ScannedProduct:
    """Product data extracted from a supplier URL."""

    # Source info
    supplier_source: str
    supplier_url: str
    supplier_sku: str = ""

    # Product info
    name: str = ""
    description: str = ""
    images: list[str] = field(default_factory=list)

    # Pricing
    cost: Decimal = Decimal("0")
    suggested_price: Decimal = Decimal("0")

    # Shipping
    shipping_days_min: int = 7
    shipping_days_max: int = 14

    # Extra metadata (not directly in Product model, but useful for the UI)
    categories: list[str] = field(default_factory=list)
    weight_grams: int | None = None
    warehouse_country: str | None = None
    inventory_count: int | None = None
    supplier_name: str | None = None
    variants_count: int = 0

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict."""
        d = asdict(self)
        d["cost"] = str(self.cost)
        d["suggested_price"] = str(self.suggested_price)
        return d


# User-Agent that mimics a real browser to avoid basic bot detection
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)


def detect_supplier(url: str) -> SupplierSource | None:
    """Detect supplier from URL hostname.

    Returns None if the URL doesn't match any known supplier.
    """
    hostname = urlparse(url).hostname or ""
    hostname = hostname.lower()

    if "cjdropshipping.com" in hostname:
        return SupplierSource.CJ
    if "aliexpress.com" in hostname or "aliexpress.us" in hostname:
        return SupplierSource.ALIEXPRESS
    if "amazon.com" in hostname or "amazon.co" in hostname:
        return SupplierSource.AMAZON
    if "temu.com" in hostname:
        return SupplierSource.TEMU
    if "ebay.com" in hostname:
        return SupplierSource.EBAY

    return None


async def _fetch_page(url: str) -> str:
    """Fetch a web page with browser-like headers.

    Args:
        url: The URL to fetch.

    Returns:
        HTML content as string.

    Raises:
        ScanError: If the fetch fails.
    """
    headers = {
        "User-Agent": _USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }

    try:
        async with httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            headers=headers,
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.text
    except httpx.TimeoutException as e:
        raise ScanError(
            f"Request timed out fetching {url}",
            error_type="timeout",
        ) from e
    except httpx.HTTPStatusError as e:
        raise ScanError(
            f"HTTP {e.response.status_code} fetching {url}",
            error_type="http_error",
        ) from e
    except httpx.RequestError as e:
        raise ScanError(
            f"Failed to fetch {url}: {e}",
            error_type="network_error",
        ) from e


def _suggest_price(cost: Decimal) -> Decimal:
    """Suggest a retail price based on cost using standard markup.

    Uses a 2.5x-3x markup for products under $20, 2x-2.5x for $20-50,
    and 1.8x-2x for $50+.
    """
    if cost <= 0:
        return Decimal("0")

    if cost < 20:
        multiplier = Decimal("3.0")
    elif cost < 50:
        multiplier = Decimal("2.5")
    else:
        multiplier = Decimal("2.0")

    # Round to nearest .99
    raw = cost * multiplier
    suggested = (raw.quantize(Decimal("1")) - 1) + Decimal("0.99")
    if suggested < cost:
        suggested = cost + Decimal("0.99")

    return suggested.quantize(Decimal("0.01"))


def _extract_cj_images(html: str) -> list[str]:
    """Extract product image URLs from CJ product page HTML.

    CJ stores images in the productDetailData JSON and also in
    img tags with specific patterns.
    """
    images = []
    seen = set()

    # Pattern 1: Look for image URLs in productDetailData
    # CJ image URLs typically look like: https://cbu01.alicdn.com/...
    # or https://img.cjdropshipping.com/...
    img_patterns = [
        r'"(https?://[^"]+\.(?:jpg|jpeg|png|webp)(?:\?[^"]*)?)"',
    ]

    for pattern in img_patterns:
        for match in re.finditer(pattern, html):
            url = match.group(1)
            # Filter to product images (not icons, logos, etc.)
            if any(
                domain in url
                for domain in [
                    "alicdn.com",
                    "cjdropshipping.com",
                    "cbu01.",
                    "cbu02.",
                    "cbu03.",
                    "cbu04.",
                ]
            ):
                if url not in seen:
                    seen.add(url)
                    images.append(url)

    return images[:10]  # Limit to 10 images


def _parse_cj_product(html: str, url: str) -> ScannedProduct:
    """Parse a CJ Dropshipping product page.

    Uses the existing CJ parser infrastructure.
    """
    try:
        raw_data = parse_product_detail_data(html)
    except CJParserError as e:
        raise ScanError(
            f"Could not parse CJ product page: {e}",
            error_type="parse_error",
        ) from e

    cj_data: CJProductData = transform_cj_data(raw_data)

    # Extract images from HTML (parser only gets main image)
    images = _extract_cj_images(html)
    if cj_data.image_url and cj_data.image_url not in images:
        images.insert(0, cj_data.image_url)

    # Use the minimum sell price as cost
    cost = cj_data.sell_price_min if cj_data.sell_price_min > 0 else cj_data.sell_price_max

    # Determine shipping days
    if cj_data.delivery_cycle_days:
        ship_min = max(1, cj_data.delivery_cycle_days - 3)
        ship_max = cj_data.delivery_cycle_days + 5
    elif cj_data.warehouse_country == "US":
        ship_min, ship_max = 3, 7
    else:
        ship_min, ship_max = 7, 21

    return ScannedProduct(
        supplier_source=SupplierSource.CJ.value,
        supplier_url=url,
        supplier_sku=cj_data.sku or cj_data.id,
        name=cj_data.name,
        description=cj_data.description or "",
        images=images,
        cost=cost,
        suggested_price=_suggest_price(cost),
        shipping_days_min=ship_min,
        shipping_days_max=ship_max,
        categories=cj_data.categories,
        weight_grams=cj_data.weight_min,
        warehouse_country=cj_data.warehouse_country,
        inventory_count=cj_data.warehouse_inventory,
        supplier_name=cj_data.supplier_name,
        variants_count=len(cj_data.variants),
    )


async def scan_product_url(url: str) -> ScannedProduct:
    """Scan a supplier URL and extract product details.

    Currently supports:
    - CJ Dropshipping (cjdropshipping.com)

    Args:
        url: The supplier product URL to scan.

    Returns:
        ScannedProduct with extracted details.

    Raises:
        ScanError: If the URL can't be scanned.
    """
    # Validate URL
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.hostname:
        raise ScanError("Invalid URL", error_type="invalid_url")

    # Detect supplier
    supplier = detect_supplier(url)
    if supplier is None:
        raise ScanError(
            f"Unsupported supplier: {parsed.hostname}. "
            "Currently supported: cjdropshipping.com",
            error_type="unsupported_supplier",
        )

    logger.info(f"Scanning {supplier.value} product: {url}")

    # Fetch the page
    html = await _fetch_page(url)

    # Parse based on supplier
    if supplier == SupplierSource.CJ:
        return _parse_cj_product(html, url)

    # Future: add parsers for other suppliers
    raise ScanError(
        f"Parser not yet implemented for {supplier.value}",
        error_type="unsupported_supplier",
    )
