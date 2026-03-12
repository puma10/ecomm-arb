"""Product API endpoints."""

import logging
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ecom_arb.db import Product, get_db
from ecom_arb.db.models import SupplierSource
from ecom_arb.services.product_scanner import ScanError, scan_product_url

logger = logging.getLogger(__name__)

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


class ProductListResponse(BaseModel):
    """Response for list of products."""

    items: list[ProductResponse]
    total: int


class ScanUrlRequest(BaseModel):
    """Request to scan a supplier URL for product details."""

    url: str


class ScannedProductResponse(BaseModel):
    """Response with extracted product details from a supplier URL."""

    # Source
    supplier_source: str
    supplier_url: str
    supplier_sku: str

    # Product info
    name: str
    description: str
    images: list[str]

    # Pricing
    cost: Decimal
    suggested_price: Decimal

    # Shipping
    shipping_days_min: int
    shipping_days_max: int

    # Metadata
    categories: list[str]
    weight_grams: int | None
    warehouse_country: str | None
    inventory_count: int | None
    supplier_name: str | None
    variants_count: int


@router.post("/scan-url", response_model=ScannedProductResponse)
async def scan_url(request: ScanUrlRequest) -> ScannedProductResponse:
    """Scan a supplier URL and extract product details.

    Takes a supplier product URL (e.g. CJ Dropshipping), fetches the page,
    parses product data, and returns structured data for pre-filling the
    product creation form.
    """
    try:
        result = await scan_product_url(request.url)
    except ScanError as e:
        logger.warning(f"Scan failed for {request.url}: {e.message}")
        status_code = status.HTTP_400_BAD_REQUEST
        if e.error_type == "timeout":
            status_code = status.HTTP_504_GATEWAY_TIMEOUT
        elif e.error_type == "unsupported_supplier":
            status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
        raise HTTPException(status_code=status_code, detail=e.message)

    return ScannedProductResponse(**result.to_dict())


@router.get("", response_model=ProductListResponse)
async def list_products(
    db: AsyncSession = Depends(get_db),
) -> ProductListResponse:
    """List all active products for the storefront."""
    result = await db.execute(
        select(Product).where(Product.active == True).order_by(Product.created_at.desc())  # noqa: E712
    )
    products = result.scalars().all()

    return ProductListResponse(
        items=[ProductResponse.model_validate(p) for p in products],
        total=len(products),
    )


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
