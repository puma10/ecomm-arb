"""Add crawl_queue and crawl_events tables.

Revision ID: 002
Revises: 001
Create Date: 2026-01-02

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create crawl_queue table
    op.create_table(
        "crawl_queue",
        sa.Column("id", sa.String(50), primary_key=True),
        sa.Column("job_id", sa.String(50), sa.ForeignKey("crawl_jobs.id"), nullable=False, index=True),
        # URL info
        sa.Column("url", sa.String(2000), nullable=False),
        sa.Column("url_type", sa.String(20), nullable=False),  # search, pagination, product
        sa.Column("keyword", sa.String(255), nullable=True),
        # Priority (1=pagination/search, 2=product)
        sa.Column("priority", sa.Integer(), nullable=False, server_default="2"),
        # Status tracking
        sa.Column("status", sa.String(20), nullable=False, server_default="pending", index=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Create crawl_events table
    op.create_table(
        "crawl_events",
        sa.Column("id", sa.String(50), primary_key=True),
        sa.Column("job_id", sa.String(50), sa.ForeignKey("crawl_jobs.id"), nullable=False, index=True),
        sa.Column("queue_item_id", sa.String(50), nullable=True),
        # Event info
        sa.Column("event_type", sa.String(50), nullable=False, index=True),
        sa.Column("url", sa.String(2000), nullable=True),
        sa.Column("keyword", sa.String(255), nullable=True),
        # Flexible metadata
        sa.Column("details", sa.JSON(), nullable=False, server_default="{}"),
        # Timestamp
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, index=True),
    )


def downgrade() -> None:
    op.drop_table("crawl_events")
    op.drop_table("crawl_queue")
