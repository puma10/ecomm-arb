"""Product Discovery Service - fetches and enriches products for scoring.

Orchestrates data from multiple sources:
- CJ Dropshipping: product catalog, costs, shipping
- Keepa: Amazon competition data
- Google Ads: CPC estimates, search volume

Converts raw data into scoring.models.Product for the scoring pipeline.
"""

import asyncio
import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from ecom_arb.integrations.cj_dropshipping import (
    CJConfig,
    CJDropshippingClient,
    FreightOption,
    Product as CJProduct,
)
from ecom_arb.integrations.google_ads import (
    CPCEstimate,
    GoogleAdsClient,
    GoogleAdsConfig,
    GoogleAdsError,
)
from ecom_arb.integrations.keepa import (
    KeepaClient,
    KeepaConfig,
    KeepaError,
    ProductData as KeepaProduct,
)
from ecom_arb.scoring.models import Product, ProductCategory

logger = logging.getLogger(__name__)


# Category mapping from CJ categories to our scoring categories
CJ_CATEGORY_MAP: dict[str, ProductCategory] = {
    # Tools & Hardware
    "tools": ProductCategory.TOOLS,
    "hardware": ProductCategory.TOOLS,
    "hand tools": ProductCategory.TOOLS,
    "power tools": ProductCategory.TOOLS,
    # Crafts
    "arts": ProductCategory.CRAFTS,
    "crafts": ProductCategory.CRAFTS,
    "sewing": ProductCategory.CRAFTS,
    "knitting": ProductCategory.CRAFTS,
    # Office
    "office": ProductCategory.OFFICE,
    "stationery": ProductCategory.OFFICE,
    "desk": ProductCategory.OFFICE,
    # Outdoor
    "outdoor": ProductCategory.OUTDOOR,
    "camping": ProductCategory.OUTDOOR,
    "hiking": ProductCategory.OUTDOOR,
    "fishing": ProductCategory.OUTDOOR,
    "sports": ProductCategory.OUTDOOR,
    # Pet
    "pet": ProductCategory.PET,
    "dog": ProductCategory.PET,
    "cat": ProductCategory.PET,
    # Home Decor
    "home decor": ProductCategory.HOME_DECOR,
    "decoration": ProductCategory.HOME_DECOR,
    "wall art": ProductCategory.HOME_DECOR,
    # Kitchen
    "kitchen": ProductCategory.KITCHEN,
    "cooking": ProductCategory.KITCHEN,
    "dining": ProductCategory.KITCHEN,
    # Jewelry
    "jewelry": ProductCategory.JEWELRY,
    "watches": ProductCategory.JEWELRY,
    # Garden
    "garden": ProductCategory.GARDEN,
    "plants": ProductCategory.GARDEN,
    "lawn": ProductCategory.GARDEN,
    # High risk - map but will be filtered
    "clothing": ProductCategory.APPAREL,
    "apparel": ProductCategory.APPAREL,
    "fashion": ProductCategory.APPAREL,
    "shoes": ProductCategory.SHOES,
    "footwear": ProductCategory.SHOES,
    "electronics": ProductCategory.ELECTRONICS,
    "phones": ProductCategory.ELECTRONICS,
    "computers": ProductCategory.ELECTRONICS,
}


@dataclass
class DiscoveredProduct:
    """Product with enriched data from all sources."""

    # CJ data
    cj_product: CJProduct
    freight: Optional[FreightOption]

    # Keepa data (Amazon competition)
    keepa_data: Optional[KeepaProduct]
    amazon_asin: Optional[str]

    # Google Ads data
    cpc_estimate: Optional[CPCEstimate]

    # Derived fields
    category: ProductCategory
    selling_price: Decimal  # Our price (markup from CJ)

    def to_scoring_product(self) -> Product:
        """Convert to scoring Product model."""
        # Calculate shipping days from freight
        shipping_min, shipping_max = 7, 21  # Defaults
        if self.freight and self.freight.delivery_days:
            try:
                parts = self.freight.delivery_days.split("-")
                if len(parts) == 2:
                    shipping_min = int(parts[0])
                    shipping_max = int(parts[1])
                elif len(parts) == 1:
                    shipping_min = shipping_max = int(parts[0])
            except ValueError:
                pass

        # Amazon competition data
        amazon_prime = False
        amazon_reviews = 0
        if self.keepa_data:
            amazon_prime = self.keepa_data.is_prime_eligible or (
                self.keepa_data.buy_box is not None
                and self.keepa_data.buy_box.is_amazon
            )
            amazon_reviews = self.keepa_data.review_count

        # CPC and search volume
        estimated_cpc = 0.50  # Default
        search_volume = 1000  # Default
        if self.cpc_estimate:
            estimated_cpc = float(self.cpc_estimate.avg_cpc)
            search_volume = self.cpc_estimate.avg_monthly_searches

        # Weight (CJ gives grams, we need grams)
        weight = 500  # Default 500g
        if self.cj_product.weight:
            weight = int(self.cj_product.weight)

        return Product(
            id=self.cj_product.pid,
            name=self.cj_product.name,
            product_cost=float(self.cj_product.sell_price),
            shipping_cost=float(self.freight.price) if self.freight else 5.0,
            selling_price=float(self.selling_price),
            category=self.category,
            requires_sizing=False,  # Could be improved with category detection
            is_fragile=False,  # Could be improved
            weight_grams=weight,
            supplier_rating=4.8,  # CJ doesn't expose this directly
            supplier_age_months=24,  # CJ is established
            supplier_feedback_count=10000,  # CJ is established
            shipping_days_min=shipping_min,
            shipping_days_max=shipping_max,
            has_fast_shipping=shipping_max <= 14,
            estimated_cpc=estimated_cpc,
            monthly_search_volume=search_volume,
            amazon_prime_exists=amazon_prime,
            amazon_review_count=amazon_reviews,
            source="cj",
            source_url=f"https://cjdropshipping.com/product/{self.cj_product.pid}",
        )


class DiscoveryService:
    """Service for discovering and enriching products.

    Usage:
        service = DiscoveryService(cj_config, keepa_config, google_ads_config)
        products = service.discover_products(category="pet", limit=50)
        scoring_products = [p.to_scoring_product() for p in products]
    """

    # Default markup from CJ cost to selling price
    DEFAULT_MARKUP = Decimal("2.5")  # 2.5x markup

    def __init__(
        self,
        cj_config: CJConfig,
        keepa_config: Optional[KeepaConfig] = None,
        google_ads_config: Optional[GoogleAdsConfig] = None,
        markup: Decimal = DEFAULT_MARKUP,
    ):
        """Initialize with API configurations.

        Args:
            cj_config: CJ Dropshipping API config (required)
            keepa_config: Keepa API config (optional, for Amazon data)
            google_ads_config: Google Ads API config (optional, for CPC data)
            markup: Price markup multiplier (default 2.5x)
        """
        self.cj_client = CJDropshippingClient(cj_config)
        self.keepa_client = KeepaClient(keepa_config) if keepa_config else None
        self.google_ads_client = (
            GoogleAdsClient(google_ads_config) if google_ads_config else None
        )
        self.markup = markup

    def _map_category(self, cj_category: str) -> ProductCategory:
        """Map CJ category to scoring ProductCategory."""
        category_lower = cj_category.lower()

        # Try direct match
        if category_lower in CJ_CATEGORY_MAP:
            return CJ_CATEGORY_MAP[category_lower]

        # Try partial match
        for key, value in CJ_CATEGORY_MAP.items():
            if key in category_lower or category_lower in key:
                return value

        # Default to home decor (medium risk)
        return ProductCategory.HOME_DECOR

    def _calculate_selling_price(self, cj_product: CJProduct) -> Decimal:
        """Calculate selling price with markup."""
        base_price = cj_product.sell_price * self.markup

        # Round to .99 pricing
        rounded = int(base_price) + Decimal("0.99")
        return rounded

    def discover_products(
        self,
        category: Optional[str] = None,
        limit: int = 50,
        enrich_amazon: bool = True,
        enrich_cpc: bool = True,
    ) -> list[DiscoveredProduct]:
        """Discover products from CJ and enrich with external data.

        Args:
            category: CJ category to search (optional)
            limit: Max products to return
            enrich_amazon: Fetch Amazon competition data from Keepa
            enrich_cpc: Fetch CPC estimates from Google Ads

        Returns:
            List of DiscoveredProduct with enriched data
        """
        # Fetch products from CJ
        logger.info(f"Fetching products from CJ (category={category}, limit={limit})")
        cj_products = self.cj_client.get_products(
            category_id=category,
            page_size=min(limit, 100),
        )

        if not cj_products:
            logger.warning("No products found from CJ")
            return []

        logger.info(f"Found {len(cj_products)} products from CJ")

        # Get freight for each product
        products_with_freight: list[tuple[CJProduct, Optional[FreightOption]]] = []
        for product in cj_products[:limit]:
            try:
                freight_options = self.cj_client.calculate_freight(
                    product_id=product.pid,
                    quantity=1,
                    country_code="US",
                )
                # Pick cheapest option
                freight = min(freight_options, key=lambda f: f.price) if freight_options else None
            except Exception as e:
                logger.warning(f"Failed to get freight for {product.pid}: {e}")
                freight = None

            products_with_freight.append((product, freight))

        # Batch enrich with Keepa (Amazon data)
        keepa_data: dict[str, KeepaProduct] = {}
        if enrich_amazon and self.keepa_client:
            # For now, we'd need ASINs to look up. In practice, you'd have a mapping
            # or search by product name. Skipping for now as Keepa needs ASINs.
            logger.info("Keepa enrichment requires ASINs - skipping for CJ products")

        # Batch enrich with Google Ads (CPC data)
        cpc_data: dict[str, CPCEstimate] = {}
        if enrich_cpc and self.google_ads_client:
            # Extract keywords from product names
            keywords = [p.name.split()[0:3] for p, _ in products_with_freight]
            keywords = [" ".join(kw) for kw in keywords]

            try:
                logger.info(f"Fetching CPC estimates for {len(keywords)} keywords")
                estimates = self.google_ads_client.get_keyword_cpc_estimates(keywords)
                for est in estimates:
                    cpc_data[est.keyword.lower()] = est
            except GoogleAdsError as e:
                logger.warning(f"Failed to get CPC estimates: {e}")

        # Build discovered products
        discovered = []
        for cj_product, freight in products_with_freight:
            category = self._map_category(cj_product.category_name)
            selling_price = self._calculate_selling_price(cj_product)

            # Find matching CPC estimate
            product_keywords = " ".join(cj_product.name.split()[0:3]).lower()
            cpc_estimate = cpc_data.get(product_keywords)

            discovered.append(
                DiscoveredProduct(
                    cj_product=cj_product,
                    freight=freight,
                    keepa_data=None,  # Would be populated if we had ASINs
                    amazon_asin=None,
                    cpc_estimate=cpc_estimate,
                    category=category,
                    selling_price=selling_price,
                )
            )

        logger.info(f"Discovered {len(discovered)} products")
        return discovered

    def discover_by_keywords(
        self,
        keywords: list[str],
        limit_per_keyword: int = 10,
    ) -> list[DiscoveredProduct]:
        """Discover products by searching keywords.

        Args:
            keywords: List of keywords to search
            limit_per_keyword: Max products per keyword

        Returns:
            List of DiscoveredProduct (deduplicated by product ID)
        """
        all_products: dict[str, DiscoveredProduct] = {}

        for keyword in keywords:
            logger.info(f"Searching for keyword: {keyword}")
            try:
                # Search CJ by keyword
                cj_products = self.cj_client.search_products(
                    keyword=keyword,
                    page_size=limit_per_keyword,
                )

                for cj_product in cj_products:
                    if cj_product.pid in all_products:
                        continue  # Skip duplicates

                    # Get freight
                    try:
                        freight_options = self.cj_client.calculate_freight(
                            product_id=cj_product.pid,
                            quantity=1,
                            country_code="US",
                        )
                        freight = (
                            min(freight_options, key=lambda f: f.price)
                            if freight_options
                            else None
                        )
                    except Exception:
                        freight = None

                    category = self._map_category(cj_product.category_name)
                    selling_price = self._calculate_selling_price(cj_product)

                    all_products[cj_product.pid] = DiscoveredProduct(
                        cj_product=cj_product,
                        freight=freight,
                        keepa_data=None,
                        amazon_asin=None,
                        cpc_estimate=None,
                        category=category,
                        selling_price=selling_price,
                    )

            except Exception as e:
                logger.warning(f"Failed to search for keyword '{keyword}': {e}")

        return list(all_products.values())

    def enrich_with_amazon_data(
        self,
        products: list[DiscoveredProduct],
        asin_map: dict[str, str],
    ) -> list[DiscoveredProduct]:
        """Enrich products with Amazon competition data.

        Args:
            products: Products to enrich
            asin_map: Mapping of product ID to Amazon ASIN

        Returns:
            Products with Keepa data populated
        """
        if not self.keepa_client:
            logger.warning("Keepa client not configured - skipping Amazon enrichment")
            return products

        # Get ASINs for products
        asins_to_lookup = []
        product_by_asin: dict[str, DiscoveredProduct] = {}

        for product in products:
            asin = asin_map.get(product.cj_product.pid)
            if asin:
                asins_to_lookup.append(asin)
                product_by_asin[asin] = product
                product.amazon_asin = asin

        if not asins_to_lookup:
            return products

        # Batch lookup (Keepa supports up to 100 at a time)
        try:
            keepa_products = self.keepa_client.get_products(asins_to_lookup[:100])
            for keepa_product in keepa_products:
                if keepa_product.asin in product_by_asin:
                    product_by_asin[keepa_product.asin].keepa_data = keepa_product
        except KeepaError as e:
            logger.warning(f"Failed to get Keepa data: {e}")

        return products

    def close(self):
        """Close API clients."""
        if self.keepa_client:
            self.keepa_client.close()
