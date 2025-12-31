"""Initial migration - products and orders.

Revision ID: 001
Revises:
Create Date: 2024-12-31

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create supplier_source enum
    supplier_source_enum = postgresql.ENUM(
        "cj", "amazon", "aliexpress", "temu", "ebay",
        name="suppliersource",
        create_type=False,
    )
    supplier_source_enum.create(op.get_bind(), checkfirst=True)

    # Create order_status enum
    order_status_enum = postgresql.ENUM(
        "pending", "paid", "processing", "shipped", "delivered", "refunded", "cancelled",
        name="orderstatus",
        create_type=False,
    )
    order_status_enum.create(op.get_bind(), checkfirst=True)

    # Create products table
    op.create_table(
        "products",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("slug", sa.String(255), nullable=False, unique=True, index=True),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        # Pricing
        sa.Column("price", sa.Numeric(10, 2), nullable=False),
        sa.Column("compare_at_price", sa.Numeric(10, 2), nullable=True),
        sa.Column("cost", sa.Numeric(10, 2), nullable=False),
        # Media
        sa.Column("images", postgresql.JSON(), nullable=False, server_default="[]"),
        # Supplier info
        sa.Column(
            "supplier_source",
            postgresql.ENUM("cj", "amazon", "aliexpress", "temu", "ebay", name="suppliersource", create_type=False),
            nullable=False,
            server_default="cj",
        ),
        sa.Column("supplier_sku", sa.String(255), nullable=False, server_default=""),
        sa.Column("supplier_url", sa.String(1000), nullable=False, server_default=""),
        # Shipping
        sa.Column("shipping_cost", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("shipping_days_min", sa.Integer(), nullable=False, server_default="7"),
        sa.Column("shipping_days_max", sa.Integer(), nullable=False, server_default="14"),
        # Status
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Create orders table
    op.create_table(
        "orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("order_number", sa.String(50), nullable=False, unique=True, index=True),
        # Customer
        sa.Column("email", sa.String(255), nullable=False, index=True),
        # Status
        sa.Column(
            "status",
            postgresql.ENUM("pending", "paid", "processing", "shipped", "delivered", "refunded", "cancelled", name="orderstatus", create_type=False),
            nullable=False,
            server_default="pending",
        ),
        # Product
        sa.Column("product_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        # Pricing
        sa.Column("subtotal", sa.Numeric(10, 2), nullable=False),
        sa.Column("shipping_cost", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("total", sa.Numeric(10, 2), nullable=False),
        # Shipping address
        sa.Column("shipping_address", postgresql.JSON(), nullable=False, server_default="{}"),
        # Payment
        sa.Column("stripe_payment_intent_id", sa.String(255), nullable=True),
        sa.Column("stripe_checkout_session_id", sa.String(255), nullable=True),
        # Fulfillment
        sa.Column("supplier_order_id", sa.String(255), nullable=True),
        sa.Column("tracking_number", sa.String(255), nullable=True),
        sa.Column("tracking_url", sa.String(1000), nullable=True),
        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("shipped_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("orders")
    op.drop_table("products")

    # Drop enums
    op.execute("DROP TYPE IF EXISTS orderstatus")
    op.execute("DROP TYPE IF EXISTS suppliersource")
