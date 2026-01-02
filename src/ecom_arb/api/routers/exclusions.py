"""Exclusion Rules API endpoints.

Manages persistent exclusion rules that filter out products during crawls.

Rule types:
- country: Exclude products from specific warehouse countries (e.g., "DE", "FR")
- category: Exclude product categories (e.g., "Clothing", "Electronics")
- supplier: Exclude specific suppliers by ID
- keyword: Exclude products containing specific keywords

Endpoints:
- GET /exclusions - List all exclusion rules
- POST /exclusions - Add a new exclusion rule
- DELETE /exclusions/{id} - Remove an exclusion rule
"""

import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ecom_arb.db.base import get_db
from ecom_arb.db.models import ExclusionRule

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/exclusions", tags=["exclusions"])


# --- Request/Response Models ---


class ExclusionRuleCreate(BaseModel):
    """Request to create a new exclusion rule."""

    rule_type: str = Field(
        ...,
        description="Type of rule: country, category, supplier, or keyword",
        pattern="^(country|category|supplier|keyword)$",
    )
    value: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Value to exclude (e.g., 'DE' for country, 'Clothing' for category)",
    )
    reason: str | None = Field(
        None,
        max_length=500,
        description="Optional reason for the exclusion",
    )


class ExclusionRuleResponse(BaseModel):
    """Response for an exclusion rule."""

    id: str
    rule_type: str
    value: str
    reason: str | None
    created_at: datetime

    class Config:
        from_attributes = True


class ExclusionRuleListResponse(BaseModel):
    """Response for listing exclusion rules."""

    items: list[ExclusionRuleResponse]
    total: int


class ExclusionRuleGroupedResponse(BaseModel):
    """Response with rules grouped by type."""

    country: list[ExclusionRuleResponse]
    category: list[ExclusionRuleResponse]
    supplier: list[ExclusionRuleResponse]
    keyword: list[ExclusionRuleResponse]
    total: int


# --- Endpoints ---


@router.get("", response_model=ExclusionRuleListResponse)
async def list_exclusions(
    rule_type: str | None = Query(
        None,
        description="Filter by rule type (country, category, supplier, keyword)",
    ),
    db: AsyncSession = Depends(get_db),
) -> ExclusionRuleListResponse:
    """List all exclusion rules, optionally filtered by type."""
    query = select(ExclusionRule)

    if rule_type:
        query = query.where(ExclusionRule.rule_type == rule_type)

    query = query.order_by(ExclusionRule.rule_type, ExclusionRule.value)

    result = await db.execute(query)
    rules = result.scalars().all()

    return ExclusionRuleListResponse(
        items=[
            ExclusionRuleResponse(
                id=r.id,
                rule_type=r.rule_type,
                value=r.value,
                reason=r.reason,
                created_at=r.created_at,
            )
            for r in rules
        ],
        total=len(rules),
    )


@router.get("/grouped", response_model=ExclusionRuleGroupedResponse)
async def list_exclusions_grouped(
    db: AsyncSession = Depends(get_db),
) -> ExclusionRuleGroupedResponse:
    """List all exclusion rules grouped by type."""
    result = await db.execute(
        select(ExclusionRule).order_by(ExclusionRule.value)
    )
    rules = result.scalars().all()

    grouped: dict[str, list[ExclusionRuleResponse]] = {
        "country": [],
        "category": [],
        "supplier": [],
        "keyword": [],
    }

    for r in rules:
        response = ExclusionRuleResponse(
            id=r.id,
            rule_type=r.rule_type,
            value=r.value,
            reason=r.reason,
            created_at=r.created_at,
        )
        if r.rule_type in grouped:
            grouped[r.rule_type].append(response)

    return ExclusionRuleGroupedResponse(
        country=grouped["country"],
        category=grouped["category"],
        supplier=grouped["supplier"],
        keyword=grouped["keyword"],
        total=len(rules),
    )


@router.post("", response_model=ExclusionRuleResponse, status_code=status.HTTP_201_CREATED)
async def add_exclusion(
    rule: ExclusionRuleCreate,
    db: AsyncSession = Depends(get_db),
) -> ExclusionRuleResponse:
    """Add a new exclusion rule.

    Rules are unique by (rule_type, value) combination.
    """
    # Generate ID
    rule_id = str(uuid.uuid4())[:8]

    # Normalize value based on type
    normalized_value = rule.value.strip()
    if rule.rule_type == "country":
        normalized_value = normalized_value.upper()[:2]  # Country codes are 2 chars
    elif rule.rule_type in ("category", "keyword"):
        normalized_value = normalized_value.lower()

    exclusion = ExclusionRule(
        id=rule_id,
        rule_type=rule.rule_type,
        value=normalized_value,
        reason=rule.reason,
    )

    try:
        db.add(exclusion)
        await db.flush()
        await db.refresh(exclusion)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Exclusion rule already exists: {rule.rule_type}={normalized_value}",
        )

    logger.info(f"Added exclusion rule: {rule.rule_type}={normalized_value}")

    return ExclusionRuleResponse(
        id=exclusion.id,
        rule_type=exclusion.rule_type,
        value=exclusion.value,
        reason=exclusion.reason,
        created_at=exclusion.created_at,
    )


@router.post("/bulk", response_model=ExclusionRuleListResponse, status_code=status.HTTP_201_CREATED)
async def add_exclusions_bulk(
    rules: list[ExclusionRuleCreate],
    db: AsyncSession = Depends(get_db),
) -> ExclusionRuleListResponse:
    """Add multiple exclusion rules at once.

    Skips rules that already exist.
    """
    created_rules = []
    skipped = 0

    for rule in rules:
        # Generate ID
        rule_id = str(uuid.uuid4())[:8]

        # Normalize value
        normalized_value = rule.value.strip()
        if rule.rule_type == "country":
            normalized_value = normalized_value.upper()[:2]
        elif rule.rule_type in ("category", "keyword"):
            normalized_value = normalized_value.lower()

        # Check if exists
        existing = await db.execute(
            select(ExclusionRule).where(
                ExclusionRule.rule_type == rule.rule_type,
                ExclusionRule.value == normalized_value,
            )
        )
        if existing.scalar_one_or_none():
            skipped += 1
            continue

        exclusion = ExclusionRule(
            id=rule_id,
            rule_type=rule.rule_type,
            value=normalized_value,
            reason=rule.reason,
        )
        db.add(exclusion)
        created_rules.append(exclusion)

    await db.flush()

    # Refresh all created rules
    for exclusion in created_rules:
        await db.refresh(exclusion)

    logger.info(f"Bulk added {len(created_rules)} exclusion rules ({skipped} skipped)")

    return ExclusionRuleListResponse(
        items=[
            ExclusionRuleResponse(
                id=r.id,
                rule_type=r.rule_type,
                value=r.value,
                reason=r.reason,
                created_at=r.created_at,
            )
            for r in created_rules
        ],
        total=len(created_rules),
    )


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_exclusion(
    rule_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Remove an exclusion rule by ID."""
    result = await db.execute(
        select(ExclusionRule).where(ExclusionRule.id == rule_id)
    )
    rule = result.scalar_one_or_none()

    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Exclusion rule not found",
        )

    await db.delete(rule)
    await db.flush()

    logger.info(f"Removed exclusion rule: {rule.rule_type}={rule.value}")


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def clear_exclusions(
    rule_type: str | None = Query(
        None,
        description="Only clear rules of this type",
    ),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Clear all exclusion rules, optionally filtered by type.

    Use with caution - this removes all matching rules.
    """
    from sqlalchemy import delete

    query = delete(ExclusionRule)

    if rule_type:
        query = query.where(ExclusionRule.rule_type == rule_type)

    result = await db.execute(query)
    await db.flush()

    deleted = result.rowcount
    logger.info(f"Cleared {deleted} exclusion rules (type={rule_type or 'all'})")
