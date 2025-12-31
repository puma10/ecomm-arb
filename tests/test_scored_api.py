"""Tests for Scored Products API endpoints.

Endpoints:
- GET /products/scored - list scored products (filterable by recommendation)
- GET /products/{id}/score - get score details for a product
- POST /products/{id}/rescore - trigger rescore for a product

See: ecom-arb-vd4
"""

from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from ecom_arb.api.app import app
from ecom_arb.db.base import get_db
from ecom_arb.db.models import ScoredProduct


@pytest.fixture
def sample_scored_product_data():
    """Sample scored product data."""
    return {
        "source_product_id": "cj-product-123",
        "source": "cj",
        "name": "Premium Fitness Tracker",
        "product_cost": Decimal("15.00"),
        "shipping_cost": Decimal("3.50"),
        "selling_price": Decimal("79.99"),
        "category": "outdoor",
        "cogs": Decimal("18.50"),
        "gross_margin": Decimal("0.7688"),
        "net_margin": Decimal("0.6200"),
        "max_cpc": Decimal("0.62"),
        "cpc_buffer": Decimal("2.07"),
        "estimated_cpc": Decimal("0.30"),
        "passed_filters": True,
        "rejection_reasons": [],
        "points": 78,
        "point_breakdown": {
            "cpc": 20,
            "margin": 15,
            "aov": 12,
            "competition": 15,
            "volume": 7,
            "refund_risk": 4,
            "shipping": 3,
            "passion": 2,
        },
        "rank_score": Decimal("98.55"),
        "recommendation": "STRONG BUY",
    }


class TestListScoredProducts:
    """Tests for GET /products/scored endpoint."""

    @pytest.mark.asyncio
    async def test_list_scored_products_empty(self, test_db):
        """Returns empty list when no scored products exist."""
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/products/scored")

        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_list_scored_products_returns_products(
        self, test_db, sample_scored_product_data
    ):
        """Returns list of scored products."""
        # Create a scored product in DB
        product = ScoredProduct(**sample_scored_product_data)
        test_db.add(product)
        await test_db.flush()

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/products/scored")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["name"] == "Premium Fitness Tracker"
        assert data["items"][0]["recommendation"] == "STRONG BUY"

    @pytest.mark.asyncio
    async def test_list_scored_products_filter_by_recommendation(
        self, test_db, sample_scored_product_data
    ):
        """Filters products by recommendation level."""
        # Create products with different recommendations
        strong_buy = ScoredProduct(**sample_scored_product_data)
        test_db.add(strong_buy)

        viable_data = sample_scored_product_data.copy()
        viable_data["source_product_id"] = "cj-product-456"
        viable_data["recommendation"] = "VIABLE"
        viable_data["rank_score"] = Decimal("80.00")
        viable = ScoredProduct(**viable_data)
        test_db.add(viable)

        await test_db.flush()

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get(
                "/api/products/scored",
                params={"recommendation": "STRONG BUY"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["recommendation"] == "STRONG BUY"

    @pytest.mark.asyncio
    async def test_list_scored_products_pagination(
        self, test_db, sample_scored_product_data
    ):
        """Supports pagination with limit and offset."""
        # Create multiple products
        for i in range(5):
            product_data = sample_scored_product_data.copy()
            product_data["source_product_id"] = f"cj-product-{i}"
            product_data["name"] = f"Product {i}"
            product = ScoredProduct(**product_data)
            test_db.add(product)

        await test_db.flush()

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get(
                "/api/products/scored",
                params={"limit": 2, "offset": 2},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 5
        assert len(data["items"]) == 2

    @pytest.mark.asyncio
    async def test_list_scored_products_sorted_by_rank(
        self, test_db, sample_scored_product_data
    ):
        """Products are sorted by rank_score descending."""
        # Create products with different rank scores
        for i, rank in enumerate([75.0, 95.0, 85.0]):
            product_data = sample_scored_product_data.copy()
            product_data["source_product_id"] = f"cj-product-{i}"
            product_data["rank_score"] = Decimal(str(rank))
            product = ScoredProduct(**product_data)
            test_db.add(product)

        await test_db.flush()

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/products/scored")

        assert response.status_code == 200
        data = response.json()
        rank_scores = [item["rank_score"] for item in data["items"]]
        assert rank_scores == sorted(rank_scores, reverse=True)


class TestGetProductScore:
    """Tests for GET /products/{id}/score endpoint."""

    @pytest.mark.asyncio
    async def test_get_product_score_success(
        self, test_db, sample_scored_product_data
    ):
        """Returns score details for a product."""
        product = ScoredProduct(**sample_scored_product_data)
        test_db.add(product)
        await test_db.flush()
        await test_db.refresh(product)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get(f"/api/products/{product.id}/score")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(product.id)
        assert data["name"] == "Premium Fitness Tracker"
        assert float(data["gross_margin"]) == pytest.approx(0.7688, rel=0.01)
        assert float(data["net_margin"]) == pytest.approx(0.62, rel=0.01)
        assert data["points"] == 78
        assert "point_breakdown" in data
        assert data["recommendation"] == "STRONG BUY"

    @pytest.mark.asyncio
    async def test_get_product_score_not_found(self, test_db):
        """Returns 404 for non-existent product."""
        fake_id = uuid4()

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get(f"/api/products/{fake_id}/score")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_get_product_score_includes_financials(
        self, test_db, sample_scored_product_data
    ):
        """Score includes financial calculations."""
        product = ScoredProduct(**sample_scored_product_data)
        test_db.add(product)
        await test_db.flush()
        await test_db.refresh(product)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get(f"/api/products/{product.id}/score")

        assert response.status_code == 200
        data = response.json()
        assert "cogs" in data
        assert "max_cpc" in data
        assert "cpc_buffer" in data
        assert "estimated_cpc" in data


class TestRescoreProduct:
    """Tests for POST /products/{id}/rescore endpoint."""

    @pytest.mark.asyncio
    async def test_rescore_product_success(
        self, test_db, sample_scored_product_data
    ):
        """Rescores a product and updates the record."""
        product = ScoredProduct(**sample_scored_product_data)
        test_db.add(product)
        await test_db.flush()
        await test_db.refresh(product)

        original_updated_at = product.updated_at

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(f"/api/products/{product.id}/rescore")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(product.id)
        assert "recommendation" in data

    @pytest.mark.asyncio
    async def test_rescore_product_not_found(self, test_db):
        """Returns 404 for non-existent product."""
        fake_id = uuid4()

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(f"/api/products/{fake_id}/rescore")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_rescore_rejected_product(self, test_db, sample_scored_product_data):
        """Can rescore a previously rejected product."""
        rejected_data = sample_scored_product_data.copy()
        rejected_data["passed_filters"] = False
        rejected_data["rejection_reasons"] = ["CPC too high"]
        rejected_data["recommendation"] = "REJECT"
        rejected_data["points"] = None
        rejected_data["rank_score"] = None

        product = ScoredProduct(**rejected_data)
        test_db.add(product)
        await test_db.flush()
        await test_db.refresh(product)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(f"/api/products/{product.id}/rescore")

        assert response.status_code == 200


class TestScoredProductResponse:
    """Tests for response schema validation."""

    @pytest.mark.asyncio
    async def test_response_includes_required_fields(
        self, test_db, sample_scored_product_data
    ):
        """Response includes all required fields."""
        product = ScoredProduct(**sample_scored_product_data)
        test_db.add(product)
        await test_db.flush()
        await test_db.refresh(product)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get(f"/api/products/{product.id}/score")

        assert response.status_code == 200
        data = response.json()

        required_fields = [
            "id",
            "source_product_id",
            "source",
            "name",
            "selling_price",
            "category",
            "cogs",
            "gross_margin",
            "net_margin",
            "max_cpc",
            "cpc_buffer",
            "passed_filters",
            "recommendation",
            "created_at",
            "updated_at",
        ]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"
