"""Product API endpoints."""

from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ecom_arb.db import Product, get_db
from ecom_arb.db.models import SupplierSource

router = APIRouter(prefix="/products", tags=["products"])


class ProductResponse(BaseModel):
    """Product response schema."""

    id: UUID
    slug: str
    name: str
    description: str
    price: Decimal
    compare_at_price: Decimal | None
    images: list[str]
    shipping_days_min: int
    shipping_days_max: int

    class Config:
        from_attributes = True


class ProductCreate(BaseModel):
    """Product creation schema (admin use)."""

    slug: str
    name: str
    description: str = ""
    price: Decimal
    compare_at_price: Decimal | None = None
    cost: Decimal
    images: list[str] = []
    supplier_source: SupplierSource = SupplierSource.CJ
    supplier_sku: str = ""
    supplier_url: str = ""
    shipping_cost: Decimal = Decimal("0")
    shipping_days_min: int = 7
    shipping_days_max: int = 14


@router.get("/{slug}", response_model=ProductResponse)
async def get_product(
    slug: str,
    db: AsyncSession = Depends(get_db),
) -> Product:
    """Get a product by slug for the landing page."""
    result = await db.execute(
        select(Product).where(Product.slug == slug, Product.active == True)  # noqa: E712
    )
    product = result.scalar_one_or_none()

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )

    return product


@router.post("", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
async def create_product(
    product_data: ProductCreate,
    db: AsyncSession = Depends(get_db),
) -> Product:
    """Create a new product (admin endpoint)."""
    # Check if slug already exists
    result = await db.execute(select(Product).where(Product.slug == product_data.slug))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Product with this slug already exists",
        )

    product = Product(**product_data.model_dump())
    db.add(product)
    await db.flush()
    await db.refresh(product)

    return product
