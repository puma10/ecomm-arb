"""CJ Dropshipping HTML parser for extracting product data.

Parses HTML pages fetched by SerpWatch to extract:
- Product details from productDetailData JSON
- Product URLs from search result pages
"""

import json
import logging
import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class CJParserError(Exception):
    """Exception raised for CJ parsing errors."""

    pass


@dataclass
class CJVariant:
    """CJ product variant data."""

    sku: str
    sell_price: Decimal
    retail_price: Decimal | None = None
    weight: int | None = None
    pack_weight: int | None = None
    vid: str | None = None


@dataclass
class CJProductData:
    """Parsed CJ product data from HTML."""

    id: str
    name: str
    sku: str | None = None
    sell_price_min: Decimal = Decimal("0")
    sell_price_max: Decimal = Decimal("0")
    weight_min: int | None = None
    weight_max: int | None = None
    list_count: int = 0
    supplier_id: str | None = None
    supplier_name: str | None = None
    categories: list[str] = field(default_factory=list)
    variants: list[CJVariant] = field(default_factory=list)
    warehouse_country: str | None = None
    warehouse_inventory: int | None = None
    is_free_shipping: bool = False
    delivery_cycle_days: int | None = None
    image_url: str | None = None
    description: str | None = None


def extract_product_id(url: str) -> str | None:
    """Extract CJ product ID from URL.

    CJ URLs follow the pattern: https://cjdropshipping.com/product/name-here-p-{id}.html

    Args:
        url: CJ product URL

    Returns:
        Product ID string or None if not found
    """
    match = re.search(r"-p-(\d+)\.html", url)
    return match.group(1) if match else None


async def fetch_html(html_url: str) -> str:
    """Fetch HTML content from SerpWatch storage URL.

    The HTML is stored with Brotli compression by SerpWatch.

    Args:
        html_url: URL to the stored HTML (from SerpWatch webhook)

    Returns:
        Decompressed HTML string

    Raises:
        CJParserError: If fetch or decompression fails
    """
    try:
        import brotli
    except ImportError as e:
        raise CJParserError("brotli package not installed. Run: pip install brotli") from e

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(html_url)
            response.raise_for_status()

            # Try Brotli decompression first, fall back to raw content
            # SerpWatch may or may not compress depending on the response
            try:
                html = brotli.decompress(response.content).decode("utf-8")
                logger.debug(f"Decompressed Brotli content from {html_url}")
            except Exception as decomp_err:
                # Not Brotli compressed or decompression failed, use as-is
                logger.debug(f"Brotli decompression failed ({decomp_err}), using raw content")
                html = response.text

            return html

    except httpx.HTTPError as e:
        raise CJParserError(f"Failed to fetch HTML: {e}") from e
    except Exception as e:
        raise CJParserError(f"Error processing HTML: {e}") from e


def _extract_json_with_balanced_braces(text: str, start_pos: int) -> str:
    """Extract JSON object using balanced brace matching.

    Args:
        text: The full text containing JSON
        start_pos: Position of the opening brace

    Returns:
        The extracted JSON string
    """
    depth = 0
    end_pos = start_pos

    for i, char in enumerate(text[start_pos:], start_pos):
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                end_pos = i + 1
                break

    return text[start_pos:end_pos]


def _fix_javascript_json(json_str: str) -> str:
    """Fix JavaScript-specific syntax to valid JSON.

    Args:
        json_str: JavaScript object literal string

    Returns:
        Valid JSON string
    """
    # Replace undefined with null
    json_str = re.sub(r":(\s*)undefined", r":\1null", json_str)
    # Remove trailing commas (common in JS)
    json_str = re.sub(r",(\s*[}\]])", r"\1", json_str)
    return json_str


def parse_product_detail_data(html: str) -> dict[str, Any]:
    """Extract productDetailData from CJ product page HTML.

    The product data is embedded in a JavaScript variable:
    window.productDetailData = {...}

    Args:
        html: The HTML content of the product page

    Returns:
        Parsed JSON data as dictionary

    Raises:
        CJParserError: If data cannot be found or parsed
    """
    # Find productDetailData assignment
    patterns = [
        r"productDetailData\s*=\s*",
        r"window\.productDetailData\s*=\s*",
        r'"productDetailData"\s*:\s*',
    ]

    start_pos = -1
    for pattern in patterns:
        match = re.search(pattern, html)
        if match:
            # Find the opening brace after the pattern
            search_start = match.end()
            brace_pos = html.find("{", search_start)
            if brace_pos != -1 and brace_pos - search_start < 20:  # Reasonable distance
                start_pos = brace_pos
                break

    if start_pos == -1:
        raise CJParserError("productDetailData not found in HTML")

    # Extract JSON with balanced braces
    json_str = _extract_json_with_balanced_braces(html, start_pos)

    if not json_str or len(json_str) < 10:
        raise CJParserError("Failed to extract productDetailData JSON")

    # Fix JavaScript-specific syntax
    json_str = _fix_javascript_json(json_str)

    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        # Log a snippet for debugging
        snippet = json_str[:500] if len(json_str) > 500 else json_str
        logger.error(f"Failed to parse productDetailData JSON: {e}\nSnippet: {snippet}")
        raise CJParserError(f"Failed to parse productDetailData: {e}") from e


def transform_cj_data(data: dict[str, Any]) -> CJProductData:
    """Transform raw CJ productDetailData to our data model.

    Args:
        data: Raw parsed JSON from productDetailData

    Returns:
        CJProductData object with normalized fields
    """
    # Extract basic info
    product_id = str(data.get("id", data.get("productId", data.get("pid", ""))))
    name = data.get("name", data.get("productNameEn", data.get("productName", "")))
    sku = data.get("sku", data.get("productSku", ""))

    # Extract pricing - handle None and invalid values
    sell_price = data.get("sellPrice") or data.get("sellPriceMin") or 0
    try:
        sell_price_min = Decimal(str(data.get("sellPriceMin") or sell_price or 0))
    except Exception:
        sell_price_min = Decimal("0")
    try:
        sell_price_max = Decimal(str(data.get("sellPriceMax") or sell_price or 0))
    except Exception:
        sell_price_max = sell_price_min

    # Extract weight - handle float strings like "1350.00"
    weight = data.get("weight") or data.get("productWeight")
    try:
        weight_min = int(float(weight)) if weight else None
    except (ValueError, TypeError):
        weight_min = None
    weight_max_val = data.get("weightMax") or weight
    try:
        weight_max = int(float(weight_max_val)) if weight_max_val else None
    except (ValueError, TypeError):
        weight_max = weight_min

    # Extract supplier info
    supplier_id = data.get("supplierId", data.get("supplierID"))
    supplier_name = data.get("supplierName")

    # Extract categories
    categories = []
    cat_data = data.get("category", data.get("categories", []))
    if isinstance(cat_data, list):
        for cat in cat_data:
            if isinstance(cat, dict):
                categories.append(cat.get("name", cat.get("categoryNameEn", "")))
            elif isinstance(cat, str):
                categories.append(cat)
    elif isinstance(cat_data, str):
        categories = [cat_data]

    # Extract category name from nested structure
    if not categories:
        category_name = data.get("categoryName", data.get("categoryNameEn"))
        if category_name:
            categories = [category_name]

    # Extract variants
    variants = []
    variant_data = data.get("variants", data.get("variantList", []))
    for var in variant_data:
        if isinstance(var, dict):
            variant = CJVariant(
                sku=var.get("sku", var.get("variantSku", "")),
                sell_price=Decimal(str(var.get("sellPrice", var.get("variantSellPrice", 0)))),
                retail_price=Decimal(str(var.get("retailPrice", 0))) if var.get("retailPrice") else None,
                weight=int(var.get("weight", var.get("variantWeight", 0))) if var.get("weight") or var.get("variantWeight") else None,
                pack_weight=int(var.get("packWeight", 0)) if var.get("packWeight") else None,
                vid=var.get("vid", var.get("variantId")),
            )
            variants.append(variant)

    # Extract warehouse/shipping info
    warehouse_country = data.get("warehouseCountry", data.get("warehouseCountryCode"))
    warehouse_inventory = data.get("warehouseInventory", data.get("inventory"))
    if warehouse_inventory and isinstance(warehouse_inventory, str):
        try:
            warehouse_inventory = int(warehouse_inventory)
        except ValueError:
            warehouse_inventory = None

    is_free_shipping = bool(data.get("isFreeShipping", data.get("freeShipping", False)))
    delivery_cycle = data.get("deliveryCycleDays", data.get("deliveryCycle"))
    delivery_cycle_days = int(delivery_cycle) if delivery_cycle else None

    # Extract image
    image_url = data.get("imageUrl", data.get("productImage", data.get("mainImage")))

    # Extract list count (number of times product has been listed)
    list_count = int(data.get("listCount", data.get("listedNum", 0)))

    return CJProductData(
        id=product_id,
        name=name,
        sku=sku,
        sell_price_min=sell_price_min,
        sell_price_max=sell_price_max,
        weight_min=weight_min,
        weight_max=weight_max,
        list_count=list_count,
        supplier_id=supplier_id,
        supplier_name=supplier_name,
        categories=categories,
        variants=variants,
        warehouse_country=warehouse_country,
        warehouse_inventory=warehouse_inventory,
        is_free_shipping=is_free_shipping,
        delivery_cycle_days=delivery_cycle_days,
        image_url=image_url,
    )


async def fetch_and_parse_cj_product(html_url: str) -> CJProductData:
    """Fetch and parse a CJ product page.

    Args:
        html_url: URL to the stored HTML (from SerpWatch webhook)

    Returns:
        CJProductData with extracted product information

    Raises:
        CJParserError: If fetch or parsing fails
    """
    html = await fetch_html(html_url)
    data = parse_product_detail_data(html)
    return transform_cj_data(data)


def parse_search_results_html(html: str) -> list[str]:
    """Extract product URLs from CJ search results page HTML.

    Args:
        html: The HTML content of the search results page

    Returns:
        List of product page URLs
    """
    product_urls = []

    # Pattern for CJ product URLs
    # Example: /product/some-product-name-p-1234567890.html
    url_pattern = re.compile(r'href="(/product/[^"]*-p-\d+\.html)"')

    matches = url_pattern.findall(html)
    seen = set()

    for path in matches:
        # Convert relative to absolute URL
        full_url = f"https://cjdropshipping.com{path}"

        # Deduplicate
        if full_url not in seen:
            seen.add(full_url)
            product_urls.append(full_url)

    logger.info(f"Found {len(product_urls)} unique product URLs in search results")
    return product_urls


async def parse_cj_search_results(html_url: str) -> list[str]:
    """Fetch and parse CJ search results page.

    Args:
        html_url: URL to the stored HTML (from SerpWatch webhook)

    Returns:
        List of product page URLs found in search results

    Raises:
        CJParserError: If fetch or parsing fails
    """
    html = await fetch_html(html_url)
    return parse_search_results_html(html)


def generate_search_url(keyword: str, page: int = 1) -> str:
    """Generate a CJ Dropshipping search URL for a keyword.

    Args:
        keyword: Search keyword
        page: Page number (default: 1)

    Returns:
        Full search URL
    """
    # URL encode the keyword (replace spaces with +)
    encoded_keyword = keyword.replace(" ", "+")
    base_url = f"https://cjdropshipping.com/search/{encoded_keyword}.html"

    if page > 1:
        return f"{base_url}?pageNum={page}"

    return base_url
