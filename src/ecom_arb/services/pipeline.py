"""Scoring Pipeline Service - orchestrates product discovery, scoring, and persistence.

Takes discovered products, runs them through the scorer, and saves results to the database.

Usage:
    service = PipelineService(discovery_service, db_session)
    result = await service.run_pipeline(category="outdoor", limit=50)
    print(f"Scored {result.scored_count} products, {result.passed_count} passed filters")
"""

import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ecom_arb.db.models import ScoredProduct
from ecom_arb.scoring.models import Product, ProductScore
from ecom_arb.scoring.scorer import score_product
from ecom_arb.services.discovery import DiscoveryService

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    """Result of a pipeline run."""

    discovered_count: int = 0
    scored_count: int = 0
    passed_count: int = 0
    rejected_count: int = 0
    saved_count: int = 0
    scores: list[ProductScore] = field(default_factory=list)

    @property
    def pass_rate(self) -> float:
        """Percentage of products that passed filters."""
        if self.scored_count == 0:
            return 0.0
        return self.passed_count / self.scored_count


def score_products(products: list[Product]) -> list[ProductScore]:
    """Score a list of products.

    Args:
        products: List of Product models to score.

    Returns:
        List of ProductScore results.
    """
    if not products:
        return []

    scores = []
    for product in products:
        try:
            score = score_product(product)
            scores.append(score)
        except Exception as e:
            logger.error(f"Failed to score product {product.id}: {e}")
            # Continue with other products

    return scores


async def save_scores(
    scores: list[ProductScore],
    session: AsyncSession,
    products: Optional[list[Product]] = None,
) -> list[ScoredProduct]:
    """Save product scores to database.

    Updates existing records if source_product_id already exists (upsert behavior).

    Args:
        scores: List of ProductScore to save.
        session: Database session.
        products: Optional list of original Product models (for additional fields).

    Returns:
        List of saved ScoredProduct records.
    """
    if not scores:
        return []

    # Build product lookup for additional fields
    product_lookup: dict[str, Product] = {}
    if products:
        for p in products:
            product_lookup[p.id] = p

    saved = []

    for score in scores:
        # Get original product for additional fields
        product = product_lookup.get(score.product_id)

        # Check if product already exists
        result = await session.execute(
            select(ScoredProduct).where(ScoredProduct.source_product_id == score.product_id)
        )
        existing = result.scalar_one_or_none()

        if existing:
            # Update existing record
            existing.name = score.product_name
            existing.cogs = Decimal(str(score.cogs))
            existing.gross_margin = Decimal(str(score.gross_margin))
            existing.net_margin = Decimal(str(score.net_margin))
            existing.max_cpc = Decimal(str(score.max_cpc))
            existing.cpc_buffer = Decimal(str(score.cpc_buffer))
            existing.passed_filters = score.passed_filters
            existing.rejection_reasons = score.rejection_reasons
            existing.points = score.points
            existing.point_breakdown = score.point_breakdown
            existing.rank_score = Decimal(str(score.rank_score)) if score.rank_score else None
            existing.recommendation = score.recommendation
            # Update pricing fields if product available
            if product:
                existing.product_cost = Decimal(str(product.product_cost))
                existing.shipping_cost = Decimal(str(product.shipping_cost))
                existing.selling_price = Decimal(str(product.selling_price))
                existing.category = product.category.value
                existing.estimated_cpc = Decimal(str(product.estimated_cpc))
            saved.append(existing)
        else:
            # Create new record
            db_score = ScoredProduct(
                source_product_id=score.product_id,
                name=score.product_name,
                product_cost=Decimal(str(product.product_cost)) if product else Decimal("0"),
                shipping_cost=Decimal(str(product.shipping_cost)) if product else Decimal("0"),
                selling_price=Decimal(str(product.selling_price)) if product else Decimal("0"),
                category=product.category.value if product else "unknown",
                estimated_cpc=Decimal(str(product.estimated_cpc)) if product else Decimal("0"),
                cogs=Decimal(str(score.cogs)),
                gross_margin=Decimal(str(score.gross_margin)),
                net_margin=Decimal(str(score.net_margin)),
                max_cpc=Decimal(str(score.max_cpc)),
                cpc_buffer=Decimal(str(score.cpc_buffer)),
                passed_filters=score.passed_filters,
                rejection_reasons=score.rejection_reasons,
                points=score.points,
                point_breakdown=score.point_breakdown,
                rank_score=Decimal(str(score.rank_score)) if score.rank_score else None,
                recommendation=score.recommendation,
            )
            session.add(db_score)
            saved.append(db_score)

    await session.flush()
    return saved


class PipelineService:
    """Service for running the scoring pipeline.

    Orchestrates:
    1. Product discovery (from CJ, enriched with Keepa/Google Ads)
    2. Scoring (applying filters and point scoring)
    3. Persistence (saving to database)

    Usage:
        service = PipelineService(discovery_service, db_session)
        result = await service.run_pipeline(category="pet", limit=50)
    """

    def __init__(
        self,
        discovery_service: DiscoveryService,
        db_session: AsyncSession,
    ):
        """Initialize pipeline service.

        Args:
            discovery_service: Service for discovering products.
            db_session: Async database session.
        """
        self.discovery = discovery_service
        self.session = db_session

    async def run_pipeline(
        self,
        category: Optional[str] = None,
        limit: int = 50,
        enrich_amazon: bool = True,
        enrich_cpc: bool = True,
    ) -> PipelineResult:
        """Run the full pipeline: discover → score → save.

        Args:
            category: CJ category to search (optional).
            limit: Maximum products to process.
            enrich_amazon: Fetch Amazon competition data.
            enrich_cpc: Fetch CPC estimates.

        Returns:
            PipelineResult with counts and scores.
        """
        result = PipelineResult()

        # Step 1: Discover products
        logger.info(f"Discovering products (category={category}, limit={limit})")
        discovered = self.discovery.discover_products(
            category=category,
            limit=limit,
            enrich_amazon=enrich_amazon,
            enrich_cpc=enrich_cpc,
        )
        result.discovered_count = len(discovered)

        if not discovered:
            logger.warning("No products discovered")
            return result

        # Step 2: Convert to scoring Products
        products = [d.to_scoring_product() for d in discovered]

        # Step 3: Score products
        logger.info(f"Scoring {len(products)} products")
        scores = score_products(products)
        result.scored_count = len(scores)
        result.scores = scores

        # Count passed/rejected
        result.passed_count = sum(1 for s in scores if s.passed_filters)
        result.rejected_count = result.scored_count - result.passed_count

        logger.info(
            f"Scored {result.scored_count} products: "
            f"{result.passed_count} passed, {result.rejected_count} rejected"
        )

        # Step 4: Save to database
        logger.info("Saving scores to database")
        saved = await save_scores(scores, self.session, products)
        result.saved_count = len(saved)

        return result

    async def score_and_save(
        self,
        products: list[Product],
    ) -> PipelineResult:
        """Score and save a list of products (no discovery step).

        Useful when you already have products and just want to score them.

        Args:
            products: List of Product models to score.

        Returns:
            PipelineResult with counts and scores.
        """
        result = PipelineResult()

        # Score products
        scores = score_products(products)
        result.scored_count = len(scores)
        result.scores = scores

        # Count passed/rejected
        result.passed_count = sum(1 for s in scores if s.passed_filters)
        result.rejected_count = result.scored_count - result.passed_count

        # Save to database (pass products for additional fields)
        saved = await save_scores(scores, self.session, products)
        result.saved_count = len(saved)

        return result

    async def get_top_products(
        self,
        limit: int = 10,
        min_rank_score: Optional[float] = None,
    ) -> list[ScoredProduct]:
        """Get top scored products from database.

        Args:
            limit: Maximum products to return.
            min_rank_score: Minimum rank score filter.

        Returns:
            List of top ScoredProduct records.
        """
        query = (
            select(ScoredProduct)
            .where(ScoredProduct.passed_filters == True)  # noqa: E712
            .order_by(ScoredProduct.rank_score.desc())
            .limit(limit)
        )

        if min_rank_score is not None:
            query = query.where(ScoredProduct.rank_score >= min_rank_score)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_product_score(self, product_id: str) -> Optional[ScoredProduct]:
        """Get score for a specific product.

        Args:
            product_id: Product ID to look up.

        Returns:
            ScoredProduct or None if not found.
        """
        result = await self.session.execute(
            select(ScoredProduct).where(ScoredProduct.source_product_id == product_id)
        )
        return result.scalar_one_or_none()
