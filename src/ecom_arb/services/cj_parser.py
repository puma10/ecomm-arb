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


class ProductRemovedError(CJParserError):
    """Exception raised when a product has been removed from CJ."""

    pass


def _detect_removed_product(html: str) -> bool:
    """Check if the HTML indicates a removed product.

    CJ shows "Product removed" message for discontinued products.
    Only triggers if productDetailData is empty/missing AND removal text is shown.

    Note: "Product removed" appears in i18n translation JSON on ALL pages,
    so we must check for actual removal indicators, not just the text.
    """
    # Check for empty productDetailData (strongest signal)
    if re.search(r"productDetailData\s*=\s*\{\s*\}", html):
        return True

    # Check for visible removal message (with context to avoid i18n matches)
    # Real removal shows: "Product removed. You may post a sourcing request"
    removal_with_context = [
        r"Product removed\.\s*You may",  # Actual removal message
        r"<[^>]*>Product removed<",  # In HTML element (not JSON)
        r">\s*Product removed\s*<",  # Between HTML tags
        r"Product has been removed",
        r"This product is no longer available",
    ]
    for pattern in removal_with_context:
        if re.search(pattern, html, re.IGNORECASE):
            return True

    return False


def _detect_bot_block(html: str) -> bool:
    """Check if the HTML indicates bot detection or blocking.

    Note: Words like "captcha", "cloudflare", "blocked" appear in i18n strings
    on ALL CJ pages, so we check for actual blocking indicators, not just words.
    """
    # Check for actual Cloudflare challenge page (has specific structure)
    if re.search(r"<title>.*(?:Attention Required|Just a moment).*</title>", html, re.IGNORECASE):
        return True

    # Check for actual CAPTCHA challenge elements
    if re.search(r'class="[^"]*captcha[^"]*"', html, re.IGNORECASE):
        return True

    # Check for Cloudflare challenge form
    if re.search(r'action=".*cloudflare.*challenge', html, re.IGNORECASE):
        return True

    # Check for explicit access denied pages
    if re.search(r"<title>.*Access Denied.*</title>", html, re.IGNORECASE):
        return True

    # Check for very short pages that are likely error/block pages
    # Valid CJ product pages are typically > 50KB
    if len(html) < 5000 and re.search(r"blocked|denied|forbidden", html, re.IGNORECASE):
        return True

    return False


def parse_product_detail_data(html: str) -> dict[str, Any]:
    """Extract productDetailData from CJ product page HTML.

    The product data is embedded in a JavaScript variable:
    window.productDetailData = {...}

    Args:
        html: The HTML content of the product page

    Returns:
        Parsed JSON data as dictionary

    Raises:
        ProductRemovedError: If product has been removed from CJ
        CJParserError: If data cannot be found or parsed
    """
    # First check for removed products
    if _detect_removed_product(html):
        raise ProductRemovedError("Product has been removed from CJ")

    # Check for bot blocking
    if _detect_bot_block(html):
        # Log HTML snippet for debugging
        snippet = html[:500] if len(html) > 500 else html
        logger.warning(f"Possible bot block detected. HTML snippet: {snippet[:200]}")
        raise CJParserError("Bot detection page returned")

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
        # Log HTML snippet for debugging
        snippet = html[:1000] if len(html) > 1000 else html
        # Check if HTML looks like a valid CJ page
        has_cj_elements = "cjdropshipping" in html.lower() or "dropshipping" in html.lower()
        logger.warning(
            f"productDetailData not found. "
            f"HTML length: {len(html)}, has_cj_elements: {has_cj_elements}, "
            f"snippet: {snippet[:300]}"
        )
        raise CJParserError("productDetailData not found in HTML")

    # Extract JSON with balanced braces
    json_str = _extract_json_with_balanced_braces(html, start_pos)

    if not json_str or len(json_str) < 10:
        raise CJParserError("productDetailData is empty (product may be removed)")

    # Fix JavaScript-specific syntax
    json_str = _fix_javascript_json(json_str)

    try:
        data = json.loads(json_str)
        # Validate that we have actual product data
        if not data or not data.get("id"):
            raise CJParserError("productDetailData is empty (product may be removed)")
        return data
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
    # Prefer English name over Chinese name
    # CJ uses different field names: nameEn, productNameEn, entryNameEn for English
    name = (
        data.get("nameEn")
        or data.get("productNameEn")
        or data.get("entryNameEn")
        or data.get("name")
        or data.get("productName")
        or ""
    )
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


@dataclass
class SearchResultsData:
    """Parsed search results with pagination info."""

    product_urls: list[str]
    total_pages: int
    total_records: int


def extract_pagination_info(html: str) -> tuple[int, int]:
    """Extract pagination info from CJ search results HTML.

    Looks for patterns like:
    - "219 Records" for total count
    - "of 4" or "of 12" for total pages

    Args:
        html: The HTML content of the search results page

    Returns:
        Tuple of (total_pages, total_records)
    """
    total_pages = 1
    total_records = 0

    # Pattern for total records: "219 Records"
    records_match = re.search(r'(\d+)\s*Records', html)
    if records_match:
        total_records = int(records_match.group(1))

    # Pattern for total pages: "of 4" or "of 12" in pagination
    # Look for patterns like: "of 4" or "of&nbsp;4" or ">4</a>" at end of pagination
    pages_patterns = [
        r'of\s+(\d+)',  # "of 4"
        r'of&nbsp;(\d+)',  # "of&nbsp;4"
        r'pageNum=(\d+)[^>]*>\s*>>\s*</a>',  # Last page link
    ]

    for pattern in pages_patterns:
        match = re.search(pattern, html)
        if match:
            total_pages = int(match.group(1))
            break

    # If we have records but couldn't find pages, estimate (CJ shows ~60 per page)
    if total_records > 0 and total_pages == 1:
        total_pages = max(1, (total_records + 59) // 60)

    logger.info(f"Pagination: {total_pages} pages, {total_records} records")
    return total_pages, total_records


def parse_search_results_html(html: str) -> SearchResultsData:
    """Extract product URLs and pagination from CJ search results page HTML.

    Args:
        html: The HTML content of the search results page

    Returns:
        SearchResultsData with product URLs and pagination info
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

    # Extract pagination info
    total_pages, total_records = extract_pagination_info(html)

    logger.info(f"Found {len(product_urls)} unique product URLs in search results")
    return SearchResultsData(
        product_urls=product_urls,
        total_pages=total_pages,
        total_records=total_records,
    )


async def parse_cj_search_results(html_url: str) -> SearchResultsData:
    """Fetch and parse CJ search results page.

    Args:
        html_url: URL to the stored HTML (from SerpWatch webhook)

    Returns:
        SearchResultsData with product URLs and pagination info

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
