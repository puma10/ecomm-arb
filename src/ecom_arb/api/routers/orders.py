"""Order API endpoints."""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ecom_arb.db import Order, OrderStatus, get_db

router = APIRouter(prefix="/orders", tags=["orders"])


class ProductSummary(BaseModel):
    """Minimal product info for order display."""

    name: str
    images: list[str]


class OrderResponse(BaseModel):
    """Order response schema."""

    id: UUID
    order_number: str
    status: OrderStatus
    quantity: int
    subtotal: Decimal
    shipping_cost: Decimal
    total: Decimal
    shipping_address: dict[str, Any]
    tracking_number: str | None
    tracking_url: str | None
    created_at: datetime
    paid_at: datetime | None
    shipped_at: datetime | None
    product: ProductSummary

    class Config:
        from_attributes = True


class OrderLookupRequest(BaseModel):
    """Order lookup by email + order number."""

    email: EmailStr
    order_number: str


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> Order:
    """Get order by ID."""
    result = await db.execute(
        select(Order).where(Order.id == order_id).options(selectinload(Order.product))
    )
    order = result.scalar_one_or_none()

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found",
        )

    return order


@router.post("/lookup", response_model=OrderResponse)
async def lookup_order(
    lookup_data: OrderLookupRequest,
    db: AsyncSession = Depends(get_db),
) -> Order:
    """Lookup order by email and order number."""
    result = await db.execute(
        select(Order)
        .where(
            Order.email == lookup_data.email,
            Order.order_number == lookup_data.order_number,
        )
        .options(selectinload(Order.product))
    )
    order = result.scalar_one_or_none()

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found. Please check your email and order number.",
        )

    return order
