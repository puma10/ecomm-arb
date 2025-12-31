"""Database models for products and orders."""

import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Enum, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from ecom_arb.db.base import Base


class OrderStatus(str, enum.Enum):
    """Order status enumeration."""

    PENDING = "pending"
    PAID = "paid"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    REFUNDED = "refunded"
    CANCELLED = "cancelled"


class SupplierSource(str, enum.Enum):
    """Supplier/fulfillment source."""

    CJ = "cj"
    AMAZON = "amazon"
    ALIEXPRESS = "aliexpress"
    TEMU = "temu"
    EBAY = "ebay"


class Product(Base):
    """Product model for storefront."""

    __tablename__ = "products"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(500))
    description: Mapped[str] = mapped_column(Text, default="")

    # Pricing
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    compare_at_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    cost: Mapped[Decimal] = mapped_column(Numeric(10, 2))  # Our cost from supplier

    # Media
    images: Mapped[list[str]] = mapped_column(JSON, default=list)

    # Supplier info
    supplier_source: Mapped[SupplierSource] = mapped_column(
        Enum(SupplierSource),
        default=SupplierSource.CJ,
    )
    supplier_sku: Mapped[str] = mapped_column(String(255), default="")
    supplier_url: Mapped[str] = mapped_column(String(1000), default="")

    # Shipping
    shipping_cost: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"))
    shipping_days_min: Mapped[int] = mapped_column(default=7)
    shipping_days_max: Mapped[int] = mapped_column(default=14)

    # Status
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    orders: Mapped[list["Order"]] = relationship(back_populates="product")

    def __repr__(self) -> str:
        return f"<Product {self.slug}: {self.name}>"


class ScoredProduct(Base):
    """Scored product from the scoring pipeline."""

    __tablename__ = "scored_products"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Product identification
    source_product_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(500))

    # Source info
    source: Mapped[str] = mapped_column(String(50), default="cj")
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    # Pricing inputs
    product_cost: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    shipping_cost: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    selling_price: Mapped[Decimal] = mapped_column(Numeric(10, 2))

    # Category
    category: Mapped[str] = mapped_column(String(100))

    # Market data
    estimated_cpc: Mapped[Decimal] = mapped_column(Numeric(10, 2))

    # Calculated financials
    cogs: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    gross_margin: Mapped[Decimal] = mapped_column(Numeric(10, 4))
    net_margin: Mapped[Decimal] = mapped_column(Numeric(10, 4))
    max_cpc: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    cpc_buffer: Mapped[Decimal] = mapped_column(Numeric(10, 2))

    # Filter result
    passed_filters: Mapped[bool] = mapped_column(Boolean, default=False)
    rejection_reasons: Mapped[list[str]] = mapped_column(JSON, default=list)

    # Point scoring
    points: Mapped[int | None] = mapped_column(nullable=True)
    point_breakdown: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    rank_score: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)

    # Recommendation
    recommendation: Mapped[str] = mapped_column(String(50), default="REJECT")

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:
        return f"<ScoredProduct {self.source_product_id}: {self.recommendation}>"


class Order(Base):
    """Order model for tracking purchases."""

    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    order_number: Mapped[str] = mapped_column(String(50), unique=True, index=True)

    # Customer info
    email: Mapped[str] = mapped_column(String(255), index=True)

    # Status
    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus),
        default=OrderStatus.PENDING,
    )

    # Product reference
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id"),
    )
    quantity: Mapped[int] = mapped_column(default=1)

    # Pricing
    subtotal: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    shipping_cost: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"))
    total: Mapped[Decimal] = mapped_column(Numeric(10, 2))

    # Shipping address (stored as JSON)
    shipping_address: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    # Payment
    stripe_payment_intent_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    stripe_checkout_session_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Fulfillment
    supplier_order_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tracking_number: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tracking_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    shipped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    product: Mapped["Product"] = relationship(back_populates="orders")

    def __repr__(self) -> str:
        return f"<Order {self.order_number}: {self.status.value}>"
