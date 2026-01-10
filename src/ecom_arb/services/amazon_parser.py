"""Amazon search results HTML parser.

Parses Amazon search result pages fetched by SerpWatch to extract:
- Product prices
- Review counts
- Prime eligibility
- ASINs

Used for competitive price analysis.
"""

import logging
import re
from dataclasses import dataclass
from decimal import Decimal

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class AmazonParserError(Exception):
    """Exception raised for Amazon parsing errors."""

    pass


@dataclass
class AmazonProduct:
    """Parsed Amazon product from search results."""

    asin: str
    title: str
    price: Decimal | None  # Current price in USD
    original_price: Decimal | None  # Strike-through price if on sale
    review_count: int
    rating: float | None  # 1-5 scale
    is_prime: bool
    is_sponsored: bool
    position: int  # Position in search results


@dataclass
class AmazonSearchResults:
    """Parsed Amazon search results page."""

    keyword: str
    products: list[AmazonProduct]
    total_results: int | None

    @property
    def median_price(self) -> Decimal | None:
        """Get median price of non-sponsored products."""
        prices = [p.price for p in self.products if p.price and not p.is_sponsored]
        if not prices:
            return None
        sorted_prices = sorted(prices)
        n = len(sorted_prices)
        if n % 2 == 0:
            return (sorted_prices[n // 2 - 1] + sorted_prices[n // 2]) / 2
        return sorted_prices[n // 2]

    @property
    def avg_price(self) -> Decimal | None:
        """Get average price of non-sponsored products."""
        prices = [p.price for p in self.products if p.price and not p.is_sponsored]
        if not prices:
            return None
        return sum(prices) / len(prices)

    @property
    def min_price(self) -> Decimal | None:
        """Get minimum price of non-sponsored products."""
        prices = [p.price for p in self.products if p.price and not p.is_sponsored]
        return min(prices) if prices else None

    @property
    def max_price(self) -> Decimal | None:
        """Get maximum price of non-sponsored products."""
        prices = [p.price for p in self.products if p.price and not p.is_sponsored]
        return max(prices) if prices else None

    @property
    def avg_review_count(self) -> int:
        """Get average review count of non-sponsored products."""
        counts = [p.review_count for p in self.products if not p.is_sponsored]
        return int(sum(counts) / len(counts)) if counts else 0

    @property
    def prime_percentage(self) -> float:
        """Get percentage of products with Prime."""
        non_sponsored = [p for p in self.products if not p.is_sponsored]
        if not non_sponsored:
            return 0.0
        prime_count = sum(1 for p in non_sponsored if p.is_prime)
        return prime_count / len(non_sponsored)


def build_amazon_search_url(keywords: str, page: int = 1) -> str:
    """Build Amazon search URL from keywords.

    Args:
        keywords: Search keywords (will be URL-encoded)
        page: Page number (1-indexed)

    Returns:
        Amazon search URL (forced to US locale)
    """
    # URL encode the keywords
    encoded = keywords.replace(" ", "+")
    # Force US locale with multiple parameters:
    # - language=en_US: English language
    # - currency=USD: US Dollar pricing
    # - ref=nb_sb_noss: Standard search reference
    url = f"https://www.amazon.com/s?k={encoded}&language=en_US&currency=USD&ref=nb_sb_noss"
    if page > 1:
        url += f"&page={page}"
    return url


async def fetch_html(html_url: str) -> str:
    """Fetch HTML content from SerpWatch storage URL.

    Args:
        html_url: URL to the stored HTML (from SerpWatch webhook)

    Returns:
        Decompressed HTML string

    Raises:
        AmazonParserError: If fetch or decompression fails
    """
    try:
        import brotli
    except ImportError as e:
        raise AmazonParserError("brotli package not installed") from e

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(html_url)
            response.raise_for_status()

            # Try Brotli decompression first, fall back to raw content
            try:
                html = brotli.decompress(response.content).decode("utf-8")
            except Exception:
                html = response.text

            return html

    except httpx.HTTPError as e:
        raise AmazonParserError(f"Failed to fetch HTML: {e}") from e


def _parse_price(price_str: str | None) -> Decimal | None:
    """Parse price string to Decimal.

    Handles formats like:
    - "$29.99" (US)
    - "$1,299.00" (US with comma)
    - "29.99" (plain number)
    - "29,99 €" (European with comma as decimal)
    - "1.299,99 €" (European with period as thousands separator)
    """
    if not price_str:
        return None

    # Check if European format (comma as decimal separator)
    # European format: uses comma for decimal, period for thousands
    # Example: "1.299,99 €" or "29,99 €"
    if "," in price_str and "." in price_str:
        # Period before comma = European (1.299,99)
        if price_str.rfind(".") < price_str.rfind(","):
            # Remove periods (thousands), replace comma with period
            cleaned = price_str.replace(".", "").replace(",", ".")
            cleaned = re.sub(r"[^\d.]", "", cleaned)
        else:
            # US format with comma as thousands separator
            cleaned = re.sub(r"[^\d.]", "", price_str)
    elif "," in price_str and "." not in price_str:
        # Only comma, likely European decimal separator
        cleaned = price_str.replace(",", ".")
        cleaned = re.sub(r"[^\d.]", "", cleaned)
    else:
        # US format or plain number
        cleaned = re.sub(r"[^\d.]", "", price_str)

    if not cleaned or cleaned == ".":
        return None

    try:
        return Decimal(cleaned)
    except Exception:
        return None


def _parse_review_count(count_str: str | None) -> int:
    """Parse review count string to int.

    Handles formats like:
    - "1,234"
    - "12K"
    - "1.2K"
    """
    if not count_str:
        return 0

    count_str = count_str.strip().upper()

    # Handle K suffix (thousands)
    if "K" in count_str:
        try:
            num = float(count_str.replace("K", "").replace(",", ""))
            return int(num * 1000)
        except ValueError:
            return 0

    # Handle M suffix (millions)
    if "M" in count_str:
        try:
            num = float(count_str.replace("M", "").replace(",", ""))
            return int(num * 1000000)
        except ValueError:
            return 0

    # Regular number
    try:
        return int(count_str.replace(",", ""))
    except ValueError:
        return 0


def _parse_rating(rating_str: str | None) -> float | None:
    """Parse rating string to float.

    Handles formats like:
    - "4.5 out of 5 stars"
    - "4.5"
    """
    if not rating_str:
        return None

    # Extract first number
    match = re.search(r"(\d+\.?\d*)", rating_str)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None


def parse_search_results(html: str, keyword: str) -> AmazonSearchResults:
    """Parse Amazon search results HTML.

    Args:
        html: Raw HTML from Amazon search page
        keyword: The search keyword used

    Returns:
        AmazonSearchResults with extracted products
    """
    soup = BeautifulSoup(html, "html.parser")
    products = []
    position = 0

    # Find all search result items
    # Amazon uses data-component-type="s-search-result" for product cards
    result_items = soup.find_all("div", {"data-component-type": "s-search-result"})

    for item in result_items:
        position += 1

        # Extract ASIN from data-asin attribute
        asin = item.get("data-asin", "")
        if not asin:
            continue

        # Check if sponsored
        is_sponsored = False
        sponsored_elem = item.find("span", string=re.compile(r"Sponsored", re.I))
        if sponsored_elem:
            is_sponsored = True

        # Extract title
        title_elem = item.find("h2")
        title = ""
        if title_elem:
            title_link = title_elem.find("a")
            if title_link:
                title = title_link.get_text(strip=True)
            else:
                title = title_elem.get_text(strip=True)

        # Extract price - look for the whole price span
        price = None
        original_price = None

        # Current price
        # Note: Amazon's HTML has nested spans like:
        # <span class="a-price-whole">59<span class="a-price-decimal">.</span></span>
        # So we need to extract just the digits from price_whole
        price_whole = item.find("span", class_="a-price-whole")
        price_fraction = item.find("span", class_="a-price-fraction")
        if price_whole:
            # Extract only digits from the whole part (ignores nested spans)
            whole_text = "".join(c for c in price_whole.get_text(strip=True) if c.isdigit())
            if whole_text:
                if price_fraction:
                    fraction_text = "".join(c for c in price_fraction.get_text(strip=True) if c.isdigit())
                    price_text = f"{whole_text}.{fraction_text}"
                else:
                    price_text = f"{whole_text}.00"
                price = _parse_price(price_text)

        # Original/strike-through price
        original_elem = item.find("span", class_="a-text-price")
        if original_elem:
            original_price = _parse_price(original_elem.get_text(strip=True))

        # Extract rating
        rating = None
        rating_elem = item.find("span", class_="a-icon-alt")
        if rating_elem:
            rating = _parse_rating(rating_elem.get_text())

        # Extract review count
        review_count = 0
        # Look for the link that contains review count
        review_link = item.find("a", href=re.compile(r"#customerReviews"))
        if review_link:
            review_span = review_link.find("span", class_="a-size-base")
            if review_span:
                review_count = _parse_review_count(review_span.get_text())

        # Alternative: look for aria-label with review count
        if review_count == 0:
            review_elem = item.find("span", {"aria-label": re.compile(r"\d+.*rating")})
            if review_elem:
                # Extract from aria-label like "4.5 out of 5 stars 1,234 ratings"
                label = review_elem.get("aria-label", "")
                match = re.search(r"([\d,]+)\s*rating", label)
                if match:
                    review_count = _parse_review_count(match.group(1))

        # Check for Prime
        is_prime = False
        prime_elem = item.find("i", class_=re.compile(r"a-icon-prime"))
        if prime_elem:
            is_prime = True

        products.append(
            AmazonProduct(
                asin=asin,
                title=title,
                price=price,
                original_price=original_price,
                review_count=review_count,
                rating=rating,
                is_prime=is_prime,
                is_sponsored=is_sponsored,
                position=position,
            )
        )

    # Try to extract total results count
    total_results = None
    results_info = soup.find("span", {"data-component-type": "s-result-info-bar"})
    if results_info:
        match = re.search(r"([\d,]+)\s+results", results_info.get_text())
        if match:
            total_results = int(match.group(1).replace(",", ""))

    logger.info(
        f"Parsed {len(products)} products from Amazon search for '{keyword}'"
    )

    return AmazonSearchResults(
        keyword=keyword,
        products=products,
        total_results=total_results,
    )


async def parse_amazon_search_from_url(html_url: str, keyword: str) -> AmazonSearchResults:
    """Fetch and parse Amazon search results.

    Args:
        html_url: URL to the stored HTML (from SerpWatch webhook)
        keyword: The search keyword used

    Returns:
        AmazonSearchResults with extracted products
    """
    html = await fetch_html(html_url)
    return parse_search_results(html, keyword)


async def scrape_amazon_direct(keyword: str, page: int = 1) -> AmazonSearchResults:
    """Scrape Amazon search results using ScraperAPI.

    Uses ScraperAPI to fetch Amazon pages with US geo-targeting,
    automatic CAPTCHA solving, and anti-bot bypass.

    Args:
        keyword: Search keyword
        page: Page number (1-indexed)

    Returns:
        AmazonSearchResults with extracted products

    Raises:
        AmazonParserError: If fetch or parsing fails
    """
    from urllib.parse import urlencode

    from ecom_arb.config import get_settings

    settings = get_settings()
    api_key = settings.scraperapi_key

    if not api_key:
        raise AmazonParserError("SCRAPERAPI_KEY not configured")

    # Build Amazon search URL
    amazon_url = build_amazon_search_url(keyword, page)

    # Build ScraperAPI request URL
    # country_code=us ensures US geo-targeting for USD pricing
    params = {
        "api_key": api_key,
        "url": amazon_url,
        "country_code": "us",
    }
    scraper_url = f"http://api.scraperapi.com?{urlencode(params)}"

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            logger.info(f"Fetching Amazon via ScraperAPI: {keyword} (page {page})")
            response = await client.get(scraper_url)
            response.raise_for_status()
            html = response.text

            # Check for CAPTCHA (shouldn't happen with ScraperAPI but just in case)
            if "Enter the characters you see below" in html:
                raise AmazonParserError("Amazon CAPTCHA detected - ScraperAPI failed to solve")

            # Verify we got US pricing
            if "$" not in html and "USD" not in html:
                logger.warning("Response may not contain USD pricing")

            return parse_search_results(html, keyword)

    except httpx.HTTPStatusError as e:
        raise AmazonParserError(f"ScraperAPI returned HTTP {e.response.status_code}") from e
    except httpx.RequestError as e:
        raise AmazonParserError(f"ScraperAPI request failed: {e}") from e
