"""External service integrations."""

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
from ecom_arb.integrations.google_ads import (
    Campaign,
    CampaignStatus,
    CPCEstimate,
    GoogleAdsClient,
    GoogleAdsConfig,
    GoogleAdsError,
)
from ecom_arb.integrations.keepa import (
    BuyBoxData,
    KeepaClient,
    KeepaConfig,
    KeepaError,
    PricePoint,
    ProductData,
    ProductType,
)

__all__ = [
    # CJ Dropshipping
    "CJConfig",
    "CJDropshippingClient",
    "CJError",
    "FreightOption",
    "Order",
    "OrderStatus",
    "Product",
    "ProductVariant",
    # Google Ads
    "Campaign",
    "CampaignStatus",
    "CPCEstimate",
    "GoogleAdsClient",
    "GoogleAdsConfig",
    "GoogleAdsError",
    # Keepa
    "BuyBoxData",
    "KeepaClient",
    "KeepaConfig",
    "KeepaError",
    "PricePoint",
    "ProductData",
    "ProductType",
]
