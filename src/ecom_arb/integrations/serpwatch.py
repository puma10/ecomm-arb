"""SerpWatch Browser API client for web scraping.

SerpWatch provides a browser-based scraping API that fetches pages with a real browser
and posts the HTML back to a webhook URL.
"""

import logging
import os
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# API Configuration
SERPWATCH_API_KEY = os.getenv(
    "SERPWATCH_API_KEY",
    "Z55_HNYlHuF08a6YKQPyTJ297jyXAUSdE-Pt0YIfuNr5_1jM",
)
SERPWATCH_BASE_URL = "https://engine.v2.serpwatch.io/api"


def _get_webhook_base_url() -> str:
    """Get webhook base URL from settings (loads .env properly)."""
    from ecom_arb.config import get_settings
    return get_settings().webhook_base_url


class SerpWatchError(Exception):
    """Exception raised for SerpWatch API errors."""

    def __init__(self, message: str, status_code: int | None = None, response: dict | None = None):
        self.message = message
        self.status_code = status_code
        self.response = response
        super().__init__(self.message)


@dataclass
class SerpWatchSubmitResponse:
    """Response from submitting a URL to SerpWatch."""

    success: bool
    request_id: str | None = None
    error: str | None = None


async def submit_url(
    url: str,
    crawl_job_id: str,
    url_type: str,
    index: int,
    device: str = "desktop",
) -> SerpWatchSubmitResponse:
    """Submit a URL to SerpWatch Browser API for fetching.

    Args:
        url: The URL to fetch (CJ Dropshipping URL)
        crawl_job_id: Our crawl job ID for tracking
        url_type: Type of URL - "search" or "product"
        index: Index number for tracking multiple URLs
        device: Device type for browser emulation (default: desktop)

    Returns:
        SerpWatchSubmitResponse with success status and request_id

    Raises:
        SerpWatchError: If the API request fails
    """
    post_id = f"crawl-{crawl_job_id}-{url_type}-{index}"
    webhook_base = _get_webhook_base_url()
    postback_url = f"{webhook_base}/api/crawl/webhook"

    payload = {
        "url": url,
        "device": device,
        "postback_url": postback_url,
        "post_id": post_id,
    }

    logger.info(f"Submitting URL to SerpWatch: {url} (post_id={post_id})")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{SERPWATCH_BASE_URL}/v2/browser",
                headers={
                    "Authorization": f"Bearer {SERPWATCH_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )

            if response.status_code >= 400:
                error_text = response.text
                logger.error(f"SerpWatch API error: {response.status_code} - {error_text}")
                raise SerpWatchError(
                    f"SerpWatch API error: {error_text}",
                    status_code=response.status_code,
                    response={"error": error_text},
                )

            result = response.json()
            logger.debug(f"SerpWatch response: {result}")

            # Extract request_id from response
            request_id = result.get("request_id") or result.get("id")

            return SerpWatchSubmitResponse(
                success=True,
                request_id=request_id,
            )

    except httpx.TimeoutException as e:
        logger.error(f"SerpWatch request timeout: {e}")
        raise SerpWatchError(f"Request timeout: {e}") from e
    except httpx.HTTPError as e:
        logger.error(f"SerpWatch HTTP error: {e}")
        raise SerpWatchError(f"HTTP error: {e}") from e


async def submit_urls_batch(
    urls: list[tuple[str, str, int]],
    crawl_job_id: str,
) -> list[SerpWatchSubmitResponse]:
    """Submit multiple URLs to SerpWatch.

    Args:
        urls: List of tuples (url, url_type, index)
        crawl_job_id: Our crawl job ID for tracking

    Returns:
        List of SerpWatchSubmitResponse for each URL
    """
    results = []
    for url, url_type, index in urls:
        try:
            result = await submit_url(url, crawl_job_id, url_type, index)
            results.append(result)
        except SerpWatchError as e:
            logger.error(f"Failed to submit URL {url}: {e}")
            results.append(SerpWatchSubmitResponse(success=False, error=str(e)))

    return results


def parse_post_id(post_id: str) -> tuple[str, str, int] | None:
    """Parse a post_id to extract crawl job info.

    Args:
        post_id: The post_id from SerpWatch webhook (format: crawl-{job_id}-{type}-{index})

    Returns:
        Tuple of (job_id, url_type, index) or None if invalid format
    """
    if not post_id or not post_id.startswith("crawl-"):
        return None

    parts = post_id.split("-")
    if len(parts) < 4:
        return None

    try:
        # Format: crawl-{job_id}-{type}-{index}
        # Job ID might contain dashes, so we need to be careful
        # The last two parts are type and index
        url_type = parts[-2]
        index = int(parts[-1])
        job_id = "-".join(parts[1:-2])
        return (job_id, url_type, index)
    except (ValueError, IndexError):
        return None


@dataclass
class WebhookResult:
    """Parsed result from SerpWatch webhook payload."""

    success: bool
    url: str
    html_url: str | None
    post_id: str
    request_id: str | None
    error: str | None = None


def parse_webhook_payload(payload: dict[str, Any]) -> list[WebhookResult]:
    """Parse the webhook payload from SerpWatch.

    Args:
        payload: The JSON payload from SerpWatch webhook

    Returns:
        List of WebhookResult objects
    """
    results = []

    # Handle both single result and multiple results
    raw_results = payload.get("results", [])
    if not raw_results and "success" in payload:
        # Single result format
        raw_results = [payload]

    for item in raw_results:
        result = WebhookResult(
            success=item.get("success", False),
            url=item.get("url", ""),
            html_url=item.get("html"),
            post_id=item.get("post_id", ""),
            request_id=item.get("request_id"),
            error=item.get("error"),
        )
        results.append(result)

    return results
