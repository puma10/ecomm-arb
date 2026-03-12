"""Add price_history and price_alerts tables.

Revision ID: 003
Revises: 002
Create Date: 2026-03-12

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create price_history table
    op.create_table(
        "price_history",
        sa.Column("id", sa.String(50), primary_key=True),
        sa.Column("product_ref", sa.String(255), nullable=False, index=True),
        sa.Column("product_name", sa.String(500), server_default=""),
        sa.Column("price", sa.Numeric(10, 2), nullable=False),
        sa.Column("previous_price", sa.Numeric(10, 2), nullable=True),
        sa.Column("source", sa.String(20), nullable=False, server_default="crawl"),
        sa.Column("currency", sa.String(3), server_default="USD"),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            index=True,
        ),
    )
    op.create_index(
        "ix_price_history_product_recorded",
        "price_history",
        ["product_ref", "recorded_at"],
    )

    # Create price_alerts table
    op.create_table(
        "price_alerts",
        sa.Column("id", sa.String(50), primary_key=True),
        sa.Column("product_ref", sa.String(255), nullable=False, index=True),
        sa.Column("product_name", sa.String(500), server_default=""),
        sa.Column("condition", sa.String(20), nullable=False),
        sa.Column("threshold", sa.Numeric(10, 2), nullable=False),
        sa.Column("status", sa.String(20), server_default="active"),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("triggered_price", sa.Numeric(10, 2), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("price_alerts")
    op.drop_index("ix_price_history_product_recorded", table_name="price_history")
    op.drop_table("price_history")
