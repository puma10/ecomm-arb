"""Residential proxy service with geo-targeting support.

Supports multiple proxy providers with automatic geo-targeting configuration.
"""

import logging
import secrets
from urllib.parse import urlparse

from ecom_arb.config import get_settings

logger = logging.getLogger(__name__)


def get_proxy(country_code: str = "us") -> dict | None:
    """Get proxy config for geo-targeted requests.

    Args:
        country_code: ISO 3166-1 alpha-2 country code (default: "us")

    Returns:
        Proxy dict for httpx, or None if no proxy configured
    """
    settings = get_settings()
    proxy_url = settings.residential_proxy_url

    if not proxy_url:
        logger.warning("No RESIDENTIAL_PROXY_URL configured - requests will use direct connection")
        return None

    parsed = urlparse(proxy_url)
    host = parsed.netloc.split("@")[-1] if "@" in parsed.netloc else parsed.netloc
    username = parsed.username or ""
    password = parsed.password or ""
    scheme = parsed.scheme or "http"

    # Generate unique session ID for sticky sessions
    session_id = secrets.token_urlsafe(8)
    country = country_code.lower()

    # Provider-specific geo-targeting formats
    host_lower = host.lower()

    if "packetstream" in host_lower:
        # PacketStream: password_country-{cc}_session-{id}
        password = f"{password}_country-{country}_session-{session_id}"
    elif "brightdata" in host_lower or "luminati" in host_lower:
        # BrightData: username-country-{cc}-session-{id}
        username = f"{username}-country-{country}-session-{session_id}"
    elif "oxylabs" in host_lower:
        # Oxylabs: customer-{user}-cc-{cc}-sessid-{id}
        username = f"customer-{username}-cc-{country}-sessid-{session_id}"
    elif "smartproxy" in host_lower:
        # Smartproxy: user-country-{cc}-session-{id}
        username = f"{username}-country-{country}-session-{session_id}"
    elif "iproyal" in host_lower:
        # IPRoyal: username_country-{cc}_session-{id}
        username = f"{username}_country-{country}_session-{session_id}"
    else:
        # Generic format - try password suffix (common pattern)
        password = f"{password}_country-{country}_session-{session_id}"
        logger.info(f"Using generic proxy format for {host}")

    proxy_url = f"{scheme}://{username}:{password}@{host}"

    return {
        "http://": proxy_url,
        "https://": proxy_url,
    }


def get_us_proxy() -> dict | None:
    """Convenience function for US-targeted proxy."""
    return get_proxy("us")
