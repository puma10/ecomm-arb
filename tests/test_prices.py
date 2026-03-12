"""Tests for the price monitoring API."""

import pytest
from httpx import ASGITransport, AsyncClient

from ecom_arb.api.app import app


class TestPriceStats:
    """Tests for GET /prices/stats endpoint."""

    @pytest.mark.asyncio
    async def test_get_price_stats_empty(self, test_db):
        """Returns zero counts when no data exists."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/prices/stats")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_tracked"] == 0
        assert data["total_observations"] == 0
        assert data["active_alerts"] == 0


class TestRecordPrice:
    """Tests for POST /prices/record endpoint."""

    @pytest.mark.asyncio
    async def test_record_price(self, test_db):
        """Records a price observation."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/prices/record",
                json={
                    "product_ref": "test-product-001",
                    "product_name": "Test Widget",
                    "price": 29.99,
                    "source": "manual",
                    "notes": "Initial price",
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["product_ref"] == "test-product-001"
        assert data["price"] == "29.99"
        assert data["source"] == "manual"
        assert data["previous_price"] is None

    @pytest.mark.asyncio
    async def test_record_price_tracks_previous(self, test_db):
        """Second price captures previous price."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            # First price
            await client.post(
                "/api/prices/record",
                json={
                    "product_ref": "test-product-002",
                    "product_name": "Another Widget",
                    "price": 50.00,
                },
            )
            # Commit needed between requests since test_db doesn't auto-commit
            await test_db.commit()

            # Second price
            resp = await client.post(
                "/api/prices/record",
                json={
                    "product_ref": "test-product-002",
                    "price": 45.00,
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert float(data["price"]) == 45.00
        assert float(data["previous_price"]) == 50.00


class TestPriceHistory:
    """Tests for GET /prices/history/{product_ref} endpoint."""

    @pytest.mark.asyncio
    async def test_get_price_history(self, test_db):
        """Returns history for a product."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            for price in [10.00, 12.00, 11.50]:
                await client.post(
                    "/api/prices/record",
                    json={
                        "product_ref": "test-product-003",
                        "product_name": "History Widget",
                        "price": price,
                    },
                )
                await test_db.commit()

            resp = await client.get("/api/prices/history/test-product-003?days=30")

        assert resp.status_code == 200
        data = resp.json()
        assert data["product_ref"] == "test-product-003"
        assert data["total"] == 3
        assert len(data["items"]) == 3
        assert data["current_price"] is not None


class TestPriceComparison:
    """Tests for GET /prices/comparison endpoint."""

    @pytest.mark.asyncio
    async def test_get_price_comparison(self, test_db):
        """Returns comparison across products."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post(
                "/api/prices/record",
                json={"product_ref": "comp-001", "product_name": "Widget A", "price": 20.00},
            )
            await test_db.commit()
            await client.post(
                "/api/prices/record",
                json={"product_ref": "comp-002", "product_name": "Widget B", "price": 35.00},
            )
            await test_db.commit()

            resp = await client.get("/api/prices/comparison")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 2
        assert len(data["items"]) >= 2


class TestAlerts:
    """Tests for price alert endpoints."""

    @pytest.mark.asyncio
    async def test_create_and_list_alerts(self, test_db):
        """Creates and lists price alerts."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/prices/alerts",
                json={
                    "product_ref": "alert-product-001",
                    "product_name": "Alert Widget",
                    "condition": "below",
                    "threshold": 25.00,
                },
            )
            assert resp.status_code == 200
            alert = resp.json()
            assert alert["product_ref"] == "alert-product-001"
            assert alert["condition"] == "below"
            assert alert["status"] == "active"

            await test_db.commit()

            resp = await client.get("/api/prices/alerts")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1

    @pytest.mark.asyncio
    async def test_dismiss_alert(self, test_db):
        """Dismisses a price alert."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/prices/alerts",
                json={
                    "product_ref": "dismiss-product",
                    "condition": "above",
                    "threshold": 100.00,
                },
            )
            alert_id = resp.json()["id"]
            await test_db.commit()

            resp = await client.delete(f"/api/prices/alerts/{alert_id}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "dismissed"

    @pytest.mark.asyncio
    async def test_alert_triggers_on_price_below(self, test_db):
        """Alert triggers when price drops below threshold."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            # Create alert for price below $20
            await client.post(
                "/api/prices/alerts",
                json={
                    "product_ref": "trigger-product",
                    "product_name": "Trigger Widget",
                    "condition": "below",
                    "threshold": 20.00,
                },
            )
            await test_db.commit()

            # Record price above threshold
            await client.post(
                "/api/prices/record",
                json={"product_ref": "trigger-product", "price": 25.00},
            )
            await test_db.commit()

            # Verify still active
            resp = await client.get("/api/prices/alerts?product_ref=trigger-product")
            alerts = resp.json()["items"]
            assert any(a["status"] == "active" for a in alerts)

            # Record price below threshold
            await client.post(
                "/api/prices/record",
                json={"product_ref": "trigger-product", "price": 18.00},
            )
            await test_db.commit()

            # Verify triggered
            resp = await client.get("/api/prices/alerts?product_ref=trigger-product")
            alerts = resp.json()["items"]
            assert any(a["status"] == "triggered" for a in alerts)

    @pytest.mark.asyncio
    async def test_invalid_alert_condition(self, test_db):
        """Invalid condition returns 400."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/prices/alerts",
                json={
                    "product_ref": "test",
                    "condition": "invalid",
                    "threshold": 10.00,
                },
            )

        assert resp.status_code == 400


class TestSnapshot:
    """Tests for POST /prices/snapshot endpoint."""

    @pytest.mark.asyncio
    async def test_snapshot_endpoint(self, test_db):
        """Snapshot returns ok."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post("/api/prices/snapshot")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "products_checked" in data
        assert "prices_recorded" in data
