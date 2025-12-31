"""Tests for Scoring Pipeline Service.

Tests cover:
- Score and save products to DB
- Run full pipeline (discovery → scoring → save)
- Filter handling (rejected products)
- Error handling
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from ecom_arb.db.base import Base
from ecom_arb.db.models import ScoredProduct
from ecom_arb.scoring.models import Product, ProductCategory, ProductScore
from ecom_arb.services.pipeline import (
    PipelineService,
    PipelineResult,
    score_products,
    save_scores,
)


# Test fixtures
@pytest.fixture
def sample_product() -> Product:
    """Create a sample scoring Product that passes all filters.

    Key filter thresholds:
    - CPC buffer >= 1.5x (with 1.3x new account multiplier)
    - Gross margin >= 65%
    - Price $50-$200
    - CPC <= $0.75

    This product is designed to pass:
    - COGS = $20 + $5 = $25
    - Gross margin = (120 - 25) / 120 = 79%
    - Net margin = 79% - 3% - 8% - 0.5% = 67.5%
    - Max CPC = 1% * 120 * 0.675 = $0.81
    - Estimated CPC with multiplier = 0.30 * 1.3 = $0.39
    - CPC buffer = 0.81 / 0.39 = 2.08x (passes 1.5x threshold)
    """
    return Product(
        id="test-123",
        name="Fitness Tracker Band",
        product_cost=20.00,
        shipping_cost=5.00,
        selling_price=120.00,
        category=ProductCategory.OUTDOOR,
        requires_sizing=False,
        is_fragile=False,
        weight_grams=50,
        supplier_rating=4.8,
        supplier_age_months=24,
        supplier_feedback_count=10000,
        shipping_days_min=7,
        shipping_days_max=14,
        has_fast_shipping=True,
        estimated_cpc=0.30,
        monthly_search_volume=5000,
        amazon_prime_exists=False,
        amazon_review_count=0,
        source="cj",
    )


@pytest.fixture
def sample_products(sample_product: Product) -> list[Product]:
    """Create multiple sample products."""
    # Product that passes filters
    passing = sample_product.model_copy()
    passing.id = "pass-001"

    # Product that fails filters (CPC too high - over $0.75 threshold)
    failing = sample_product.model_copy()
    failing.id = "fail-001"
    failing.estimated_cpc = 0.90  # Over 0.75 threshold, will be rejected

    return [passing, failing]


@pytest_asyncio.fixture
async def db_session():
    """Create in-memory SQLite session for testing."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session() as session:
        yield session

    await engine.dispose()


class TestScoreProducts:
    """Test product scoring."""

    def test_score_single_product(self, sample_product: Product):
        """Score a single product."""
        scores = score_products([sample_product])

        assert len(scores) == 1
        assert scores[0].product_id == "test-123"
        assert scores[0].passed_filters is True
        assert scores[0].recommendation != "REJECT"

    def test_score_multiple_products(self, sample_products: list[Product]):
        """Score multiple products, some pass and some fail."""
        scores = score_products(sample_products)

        assert len(scores) == 2

        # First product should pass
        passing_score = next(s for s in scores if s.product_id == "pass-001")
        assert passing_score.passed_filters is True

        # Second product should fail (high CPC)
        failing_score = next(s for s in scores if s.product_id == "fail-001")
        assert failing_score.passed_filters is False
        assert "CPC" in str(failing_score.rejection_reasons)

    def test_score_empty_list(self):
        """Empty input returns empty output."""
        scores = score_products([])
        assert scores == []


class TestSaveScores:
    """Test saving scores to database."""

    @pytest.mark.asyncio
    async def test_save_scores_to_db(self, sample_product: Product, db_session: AsyncSession):
        """Save scores to database."""
        scores = score_products([sample_product])

        saved = await save_scores(scores, db_session)

        assert len(saved) == 1
        assert saved[0].source_product_id == "test-123"

        # Verify in database
        from sqlalchemy import select
        result = await db_session.execute(
            select(ScoredProduct).where(ScoredProduct.source_product_id == "test-123")
        )
        db_score = result.scalar_one()
        assert db_score.name == "Fitness Tracker Band"
        assert db_score.passed_filters is True

    @pytest.mark.asyncio
    async def test_save_updates_existing(self, sample_product: Product, db_session: AsyncSession):
        """Saving same product twice updates instead of duplicating."""
        scores = score_products([sample_product])

        # Save twice
        await save_scores(scores, db_session)
        await save_scores(scores, db_session)

        # Should only have one record
        from sqlalchemy import select, func
        result = await db_session.execute(
            select(func.count()).select_from(ScoredProduct)
        )
        count = result.scalar()
        assert count == 1

    @pytest.mark.asyncio
    async def test_save_rejected_products(self, sample_products: list[Product], db_session: AsyncSession):
        """Rejected products are also saved (for tracking)."""
        scores = score_products(sample_products)

        saved = await save_scores(scores, db_session)

        # Both products should be saved
        assert len(saved) == 2

        # Find the rejected one
        rejected = next(s for s in saved if s.source_product_id == "fail-001")
        assert rejected.passed_filters is False
        assert rejected.recommendation == "REJECT"


class TestPipelineService:
    """Test the full pipeline service."""

    @pytest.fixture
    def mock_discovery_service(self, sample_product: Product):
        """Mock DiscoveryService."""
        mock = MagicMock()

        # Create mock DiscoveredProduct
        mock_discovered = MagicMock()
        mock_discovered.to_scoring_product.return_value = sample_product

        mock.discover_products.return_value = [mock_discovered]
        return mock

    @pytest.mark.asyncio
    async def test_run_pipeline(self, mock_discovery_service, db_session: AsyncSession):
        """Run full pipeline: discover → score → save."""
        service = PipelineService(
            discovery_service=mock_discovery_service,
            db_session=db_session,
        )

        result = await service.run_pipeline(category="outdoor", limit=10)

        assert isinstance(result, PipelineResult)
        assert result.discovered_count == 1
        assert result.scored_count == 1
        assert result.saved_count == 1

    @pytest.mark.asyncio
    async def test_run_pipeline_filters_rejected(
        self, mock_discovery_service, sample_products: list[Product], db_session: AsyncSession
    ):
        """Pipeline counts rejected products correctly."""
        # Setup mock to return both passing and failing products
        mock_discovered = []
        for p in sample_products:
            mock_dp = MagicMock()
            mock_dp.to_scoring_product.return_value = p
            mock_discovered.append(mock_dp)

        mock_discovery_service.discover_products.return_value = mock_discovered

        service = PipelineService(
            discovery_service=mock_discovery_service,
            db_session=db_session,
        )

        result = await service.run_pipeline()

        assert result.discovered_count == 2
        assert result.passed_count == 1
        assert result.rejected_count == 1

    @pytest.mark.asyncio
    async def test_score_and_save_products(self, sample_products: list[Product], db_session: AsyncSession):
        """Test score_and_save convenience method."""
        service = PipelineService(
            discovery_service=MagicMock(),  # Not used in this method
            db_session=db_session,
        )

        result = await service.score_and_save(sample_products)

        assert result.scored_count == 2
        assert result.passed_count == 1
        assert result.rejected_count == 1
        assert len(result.scores) == 2


class TestPipelineResult:
    """Test PipelineResult data class."""

    def test_result_summary(self):
        """Result provides useful summary."""
        result = PipelineResult(
            discovered_count=100,
            scored_count=100,
            passed_count=25,
            rejected_count=75,
            saved_count=100,
            scores=[],
        )

        assert result.pass_rate == 0.25
        assert result.discovered_count == 100

    def test_result_empty(self):
        """Empty result handles edge cases."""
        result = PipelineResult(
            discovered_count=0,
            scored_count=0,
            passed_count=0,
            rejected_count=0,
            saved_count=0,
            scores=[],
        )

        assert result.pass_rate == 0.0
