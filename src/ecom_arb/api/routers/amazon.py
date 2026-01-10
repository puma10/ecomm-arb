"""Amazon webhook endpoints for processing SerpWatch results.

Endpoints:
- POST /amazon/webhook - Receive SerpWatch postback with Amazon search results
"""

import logging
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ecom_arb.db.base import get_db
from ecom_arb.db.models import ScoredProduct
from ecom_arb.integrations.serpwatch import parse_webhook_payload
from ecom_arb.services.amazon_parser import parse_amazon_search_from_url

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/amazon", tags=["amazon"])


class WebhookResponse(BaseModel):
    """Response for webhook endpoints."""

    status: str
    message: str


def parse_amazon_post_id(post_id: str) -> tuple[str, str, int] | None:
    """Parse Amazon post_id to extract product info.

    Format: crawl-amazon-{product_id}-search-{index}

    Returns:
        Tuple of (product_id, url_type, index) or None if invalid
    """
    if not post_id:
        return None

    # Format is: crawl-amazon-{uuid}-search-0
    parts = post_id.split("-")
    if len(parts) < 4:
        return None

    # Check if this is an Amazon request
    if parts[1] != "amazon":
        return None

    try:
        url_type = parts[-2]
        index = int(parts[-1])
        # Product ID is everything between "amazon-" and "-search-"
        product_id = "-".join(parts[2:-2])
        return (product_id, url_type, index)
    except (ValueError, IndexError):
        return None


async def process_amazon_results(
    product_id: str,
    html_url: str,
    keyword: str,
) -> None:
    """Process Amazon search results in background.

    Args:
        product_id: UUID of the scored product
        html_url: URL to the stored HTML from SerpWatch
        keyword: The search keyword used
    """
    from ecom_arb.db.base import async_session_maker

    async with async_session_maker() as db:
        try:
            # Parse Amazon results
            results = await parse_amazon_search_from_url(html_url, keyword)

            logger.info(
                f"Parsed Amazon results for {product_id}: "
                f"{len(results.products)} products, "
                f"median=${results.median_price}, min=${results.min_price}"
            )

            # Update the scored product
            stmt = select(ScoredProduct).where(ScoredProduct.id == UUID(product_id))
            result = await db.execute(stmt)
            product = result.scalar_one_or_none()

            if not product:
                logger.error(f"Product {product_id} not found")
                return

            # Store Amazon data
            product.amazon_median_price = (
                Decimal(str(results.median_price)) if results.median_price else None
            )
            product.amazon_min_price = (
                Decimal(str(results.min_price)) if results.min_price else None
            )
            product.amazon_avg_review_count = results.avg_review_count
            product.amazon_prime_percentage = (
                Decimal(str(round(results.prime_percentage * 100, 2)))
            )

            # Store full results for UI
            product.amazon_search_results = {
                "keyword": results.keyword,
                "total_results": results.total_results,
                "median_price": float(results.median_price) if results.median_price else None,
                "min_price": float(results.min_price) if results.min_price else None,
                "max_price": float(results.max_price) if results.max_price else None,
                "avg_price": float(results.avg_price) if results.avg_price else None,
                "avg_review_count": results.avg_review_count,
                "prime_percentage": round(results.prime_percentage * 100, 1),
                "products": [
                    {
                        "asin": p.asin,
                        "title": p.title[:100] if p.title else "",
                        "price": float(p.price) if p.price else None,
                        "review_count": p.review_count,
                        "rating": p.rating,
                        "is_prime": p.is_prime,
                        "is_sponsored": p.is_sponsored,
                        "position": p.position,
                    }
                    for p in results.products[:20]  # Limit to top 20
                ],
            }

            await db.commit()
            logger.info(f"Updated product {product_id} with Amazon pricing data")

        except Exception as e:
            logger.exception(f"Error processing Amazon results for {product_id}: {e}")


@router.post("/webhook", response_model=WebhookResponse)
async def amazon_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> WebhookResponse:
    """Receive SerpWatch postback with Amazon search results.

    This endpoint processes results from Amazon searches:
    - Parses the HTML to extract product prices
    - Updates the scored product with Amazon pricing data
    """
    try:
        payload = await request.json()
    except Exception as e:
        logger.error(f"Failed to parse webhook payload: {e}")
        return WebhookResponse(status="error", message="Invalid JSON payload")

    logger.debug(f"Amazon webhook received: {payload}")

    # Parse webhook results
    results = parse_webhook_payload(payload)

    for result in results:
        if not result.success:
            logger.warning(f"Amazon fetch failed: {result.error}")
            continue

        # Parse post_id to get product info
        parsed = parse_amazon_post_id(result.post_id)
        if not parsed:
            logger.warning(f"Invalid Amazon post_id: {result.post_id}")
            continue

        product_id, url_type, index = parsed

        if url_type != "search":
            logger.warning(f"Unexpected Amazon URL type: {url_type}")
            continue

        if not result.html_url:
            logger.warning(f"No HTML URL for Amazon result: {result.post_id}")
            continue

        # Get the keyword from the product's keyword_analysis
        stmt = select(ScoredProduct).where(ScoredProduct.id == UUID(product_id))
        db_result = await db.execute(stmt)
        product = db_result.scalar_one_or_none()

        keyword = "unknown"
        if product and product.keyword_analysis:
            keyword = product.keyword_analysis.get("best_keyword", "unknown")

        # Process results in background
        background_tasks.add_task(
            process_amazon_results,
            product_id,
            result.html_url,
            keyword,
        )

    return WebhookResponse(
        status="ok",
        message=f"Processing {len(results)} Amazon result(s)",
    )
