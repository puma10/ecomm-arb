"""Price monitoring API endpoints."""

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func, desc, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ecom_arb.db.base import get_db
from ecom_arb.db.models import (
    AlertCondition,
    AlertStatus,
    PriceAlert,
    PriceHistory,
    PriceSource,
    ScoredProduct,
)

router = APIRouter(prefix="/prices", tags=["prices"])


# ============================================================================
# Schemas
# ============================================================================


class PriceHistoryItem(BaseModel):
    id: str
    product_ref: str
    product_name: str
    price: str  # Decimal as string for JSON
    previous_price: str | None
    source: str
    currency: str
    notes: str | None
    recorded_at: str


class PriceHistoryResponse(BaseModel):
    product_ref: str
    product_name: str
    items: list[PriceHistoryItem]
    total: int
    current_price: str | None
    price_min: str | None
    price_max: str | None
    price_avg: str | None
    price_change_pct: str | None


class PriceComparisonItem(BaseModel):
    product_ref: str
    product_name: str
    current_price: str | None
    previous_price: str | None
    price_change: str | None
    price_change_pct: str | None
    price_min_30d: str | None
    price_max_30d: str | None
    last_updated: str | None
    source: str | None


class PriceComparisonResponse(BaseModel):
    items: list[PriceComparisonItem]
    total: int


class CreateAlertRequest(BaseModel):
    product_ref: str
    product_name: str | None = None
    condition: str  # below, above, change_pct
    threshold: float


class AlertItem(BaseModel):
    id: str
    product_ref: str
    product_name: str
    condition: str
    threshold: str
    status: str
    triggered_at: str | None
    triggered_price: str | None
    created_at: str


class AlertListResponse(BaseModel):
    items: list[AlertItem]
    total: int


class RecordPriceRequest(BaseModel):
    product_ref: str
    product_name: str | None = None
    price: float
    source: str = "manual"
    notes: str | None = None


class PriceStatsResponse(BaseModel):
    total_tracked: int
    total_observations: int
    active_alerts: int
    triggered_alerts: int
    products_with_price_drops: int
    products_with_price_increases: int


# ============================================================================
# Endpoints
# ============================================================================


@router.get("/stats")
async def get_price_stats(db: AsyncSession = Depends(get_db)) -> PriceStatsResponse:
    """Get overall price monitoring statistics."""
    # Total tracked products (distinct product_refs in price_history)
    tracked_q = select(func.count(func.distinct(PriceHistory.product_ref)))
    total_tracked = (await db.execute(tracked_q)).scalar() or 0

    # Total observations
    obs_q = select(func.count(PriceHistory.id))
    total_observations = (await db.execute(obs_q)).scalar() or 0

    # Active alerts
    active_q = select(func.count(PriceAlert.id)).where(
        PriceAlert.status == AlertStatus.ACTIVE
    )
    active_alerts = (await db.execute(active_q)).scalar() or 0

    # Triggered alerts
    triggered_q = select(func.count(PriceAlert.id)).where(
        PriceAlert.status == AlertStatus.TRIGGERED
    )
    triggered_alerts = (await db.execute(triggered_q)).scalar() or 0

    # Price changes: find products with drops and increases
    # Get latest 2 prices per product to compare
    drops = 0
    increases = 0

    # Get all distinct product_refs
    refs_q = select(func.distinct(PriceHistory.product_ref))
    refs = (await db.execute(refs_q)).scalars().all()

    for ref in refs:
        latest_q = (
            select(PriceHistory.price)
            .where(PriceHistory.product_ref == ref)
            .order_by(desc(PriceHistory.recorded_at))
            .limit(2)
        )
        prices = (await db.execute(latest_q)).scalars().all()
        if len(prices) == 2:
            if prices[0] < prices[1]:
                drops += 1
            elif prices[0] > prices[1]:
                increases += 1

    return PriceStatsResponse(
        total_tracked=total_tracked,
        total_observations=total_observations,
        active_alerts=active_alerts,
        triggered_alerts=triggered_alerts,
        products_with_price_drops=drops,
        products_with_price_increases=increases,
    )


@router.get("/history/{product_ref}")
async def get_price_history(
    product_ref: str,
    days: int = Query(default=30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
) -> PriceHistoryResponse:
    """Get price history for a specific product."""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    query = (
        select(PriceHistory)
        .where(
            and_(
                PriceHistory.product_ref == product_ref,
                PriceHistory.recorded_at >= since,
            )
        )
        .order_by(PriceHistory.recorded_at.asc())
    )
    result = await db.execute(query)
    records = result.scalars().all()

    # Stats
    stats_q = select(
        func.min(PriceHistory.price),
        func.max(PriceHistory.price),
        func.avg(PriceHistory.price),
    ).where(
        and_(
            PriceHistory.product_ref == product_ref,
            PriceHistory.recorded_at >= since,
        )
    )
    stats = (await db.execute(stats_q)).one_or_none()

    # Current and change
    current_price = None
    price_change_pct = None
    product_name = ""
    if records:
        current_price = str(records[-1].price)
        product_name = records[-1].product_name
        if len(records) >= 2:
            first_price = records[0].price
            last_price = records[-1].price
            if first_price and first_price > 0:
                change = ((last_price - first_price) / first_price) * 100
                price_change_pct = f"{change:.2f}"

    items = [
        PriceHistoryItem(
            id=r.id,
            product_ref=r.product_ref,
            product_name=r.product_name,
            price=str(r.price),
            previous_price=str(r.previous_price) if r.previous_price else None,
            source=r.source.value if isinstance(r.source, PriceSource) else str(r.source),
            currency=r.currency,
            notes=r.notes,
            recorded_at=r.recorded_at.isoformat() if r.recorded_at else "",
        )
        for r in records
    ]

    return PriceHistoryResponse(
        product_ref=product_ref,
        product_name=product_name,
        items=items,
        total=len(items),
        current_price=current_price,
        price_min=str(stats[0]) if stats and stats[0] else None,
        price_max=str(stats[1]) if stats and stats[1] else None,
        price_avg=f"{stats[2]:.2f}" if stats and stats[2] else None,
        price_change_pct=price_change_pct,
    )


@router.get("/comparison")
async def get_price_comparison(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    search: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> PriceComparisonResponse:
    """Get price comparison across all tracked products."""
    # Get distinct product_refs with latest prices
    subq = (
        select(
            PriceHistory.product_ref,
            func.max(PriceHistory.recorded_at).label("latest_at"),
        )
        .group_by(PriceHistory.product_ref)
        .subquery()
    )

    query = (
        select(PriceHistory)
        .join(
            subq,
            and_(
                PriceHistory.product_ref == subq.c.product_ref,
                PriceHistory.recorded_at == subq.c.latest_at,
            ),
        )
    )

    if search:
        query = query.where(PriceHistory.product_name.ilike(f"%{search}%"))

    # Count total
    count_subq = (
        select(func.count(func.distinct(PriceHistory.product_ref)))
    )
    if search:
        count_subq = count_subq.where(PriceHistory.product_name.ilike(f"%{search}%"))
    total = (await db.execute(count_subq)).scalar() or 0

    query = query.order_by(PriceHistory.product_name).offset(offset).limit(limit)
    result = await db.execute(query)
    latest_records = result.scalars().all()

    items = []
    since_30d = datetime.now(timezone.utc) - timedelta(days=30)

    for r in latest_records:
        # Get 30-day min/max
        stats_q = select(
            func.min(PriceHistory.price),
            func.max(PriceHistory.price),
        ).where(
            and_(
                PriceHistory.product_ref == r.product_ref,
                PriceHistory.recorded_at >= since_30d,
            )
        )
        stats = (await db.execute(stats_q)).one_or_none()

        # Price change
        price_change = None
        price_change_pct = None
        if r.previous_price and r.previous_price > 0:
            change = r.price - r.previous_price
            price_change = str(change)
            pct = (change / r.previous_price) * 100
            price_change_pct = f"{pct:.2f}"

        items.append(
            PriceComparisonItem(
                product_ref=r.product_ref,
                product_name=r.product_name,
                current_price=str(r.price),
                previous_price=str(r.previous_price) if r.previous_price else None,
                price_change=price_change,
                price_change_pct=price_change_pct,
                price_min_30d=str(stats[0]) if stats and stats[0] else None,
                price_max_30d=str(stats[1]) if stats and stats[1] else None,
                last_updated=r.recorded_at.isoformat() if r.recorded_at else None,
                source=r.source.value if isinstance(r.source, PriceSource) else str(r.source),
            )
        )

    return PriceComparisonResponse(items=items, total=total)


@router.post("/record")
async def record_price(
    req: RecordPriceRequest,
    db: AsyncSession = Depends(get_db),
) -> PriceHistoryItem:
    """Record a new price observation."""
    # Get previous price for this product
    prev_q = (
        select(PriceHistory.price)
        .where(PriceHistory.product_ref == req.product_ref)
        .order_by(desc(PriceHistory.recorded_at))
        .limit(1)
    )
    prev_price = (await db.execute(prev_q)).scalar()

    # Resolve product name
    product_name = req.product_name or ""
    if not product_name:
        # Try to find from scored_products
        sp_q = select(ScoredProduct.name).where(
            ScoredProduct.source_product_id == req.product_ref
        )
        product_name = (await db.execute(sp_q)).scalar() or req.product_ref

    try:
        source = PriceSource(req.source)
    except ValueError:
        source = PriceSource.MANUAL

    record = PriceHistory(
        id=f"ph-{uuid.uuid4().hex[:12]}",
        product_ref=req.product_ref,
        product_name=product_name,
        price=Decimal(str(req.price)),
        previous_price=prev_price,
        source=source,
        notes=req.notes,
    )
    db.add(record)
    await db.flush()

    # Check alerts
    await _check_alerts(db, req.product_ref, Decimal(str(req.price)), prev_price)

    return PriceHistoryItem(
        id=record.id,
        product_ref=record.product_ref,
        product_name=record.product_name,
        price=str(record.price),
        previous_price=str(record.previous_price) if record.previous_price else None,
        source=record.source.value,
        currency=record.currency,
        notes=record.notes,
        recorded_at=record.recorded_at.isoformat() if record.recorded_at else "",
    )


@router.post("/snapshot")
async def snapshot_scored_products(
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Take a price snapshot of all scored products (for periodic monitoring)."""
    query = select(ScoredProduct).where(ScoredProduct.passed_filters.is_(True))
    result = await db.execute(query)
    products = result.scalars().all()

    recorded = 0
    for p in products:
        # Get previous price
        prev_q = (
            select(PriceHistory.price)
            .where(PriceHistory.product_ref == p.source_product_id)
            .order_by(desc(PriceHistory.recorded_at))
            .limit(1)
        )
        prev_price = (await db.execute(prev_q)).scalar()

        # Skip if price unchanged
        if prev_price and prev_price == p.selling_price:
            continue

        record = PriceHistory(
            id=f"ph-{uuid.uuid4().hex[:12]}",
            product_ref=p.source_product_id,
            product_name=p.name,
            price=p.selling_price,
            previous_price=prev_price,
            source=PriceSource.CRAWL,
        )
        db.add(record)
        recorded += 1

        # Check alerts
        await _check_alerts(db, p.source_product_id, p.selling_price, prev_price)

    await db.flush()
    return {"status": "ok", "products_checked": len(products), "prices_recorded": recorded}


# ============================================================================
# Alerts
# ============================================================================


@router.get("/alerts")
async def list_alerts(
    status: str | None = Query(default=None),
    product_ref: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> AlertListResponse:
    """List price alerts."""
    query = select(PriceAlert).order_by(desc(PriceAlert.created_at))

    if status:
        try:
            alert_status = AlertStatus(status)
            query = query.where(PriceAlert.status == alert_status)
        except ValueError:
            pass

    if product_ref:
        query = query.where(PriceAlert.product_ref == product_ref)

    result = await db.execute(query)
    alerts = result.scalars().all()

    items = [
        AlertItem(
            id=a.id,
            product_ref=a.product_ref,
            product_name=a.product_name,
            condition=a.condition.value if isinstance(a.condition, AlertCondition) else str(a.condition),
            threshold=str(a.threshold),
            status=a.status.value if isinstance(a.status, AlertStatus) else str(a.status),
            triggered_at=a.triggered_at.isoformat() if a.triggered_at else None,
            triggered_price=str(a.triggered_price) if a.triggered_price else None,
            created_at=a.created_at.isoformat() if a.created_at else "",
        )
        for a in alerts
    ]

    return AlertListResponse(items=items, total=len(items))


@router.post("/alerts")
async def create_alert(
    req: CreateAlertRequest,
    db: AsyncSession = Depends(get_db),
) -> AlertItem:
    """Create a new price alert."""
    try:
        condition = AlertCondition(req.condition)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid condition: {req.condition}. Must be: below, above, change_pct",
        )

    product_name = req.product_name or ""
    if not product_name:
        sp_q = select(ScoredProduct.name).where(
            ScoredProduct.source_product_id == req.product_ref
        )
        product_name = (await db.execute(sp_q)).scalar() or req.product_ref

    alert = PriceAlert(
        id=f"pa-{uuid.uuid4().hex[:12]}",
        product_ref=req.product_ref,
        product_name=product_name,
        condition=condition,
        threshold=Decimal(str(req.threshold)),
    )
    db.add(alert)
    await db.flush()

    return AlertItem(
        id=alert.id,
        product_ref=alert.product_ref,
        product_name=alert.product_name,
        condition=alert.condition.value,
        threshold=str(alert.threshold),
        status=alert.status.value,
        triggered_at=None,
        triggered_price=None,
        created_at=alert.created_at.isoformat() if alert.created_at else "",
    )


@router.delete("/alerts/{alert_id}")
async def dismiss_alert(
    alert_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Dismiss (deactivate) an alert."""
    query = select(PriceAlert).where(PriceAlert.id == alert_id)
    result = await db.execute(query)
    alert = result.scalar_one_or_none()

    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    alert.status = AlertStatus.DISMISSED
    await db.flush()
    return {"status": "dismissed", "id": alert_id}


# ============================================================================
# Helpers
# ============================================================================


async def _check_alerts(
    db: AsyncSession,
    product_ref: str,
    current_price: Decimal,
    previous_price: Decimal | None,
) -> None:
    """Check and trigger any matching alerts for a product."""
    query = select(PriceAlert).where(
        and_(
            PriceAlert.product_ref == product_ref,
            PriceAlert.status == AlertStatus.ACTIVE,
        )
    )
    result = await db.execute(query)
    alerts = result.scalars().all()

    now = datetime.now(timezone.utc)

    for alert in alerts:
        triggered = False

        if alert.condition == AlertCondition.BELOW and current_price <= alert.threshold:
            triggered = True
        elif alert.condition == AlertCondition.ABOVE and current_price >= alert.threshold:
            triggered = True
        elif alert.condition == AlertCondition.CHANGE_PCT and previous_price and previous_price > 0:
            change_pct = abs((current_price - previous_price) / previous_price) * 100
            if change_pct >= alert.threshold:
                triggered = True

        if triggered:
            alert.status = AlertStatus.TRIGGERED
            alert.triggered_at = now
            alert.triggered_price = current_price
