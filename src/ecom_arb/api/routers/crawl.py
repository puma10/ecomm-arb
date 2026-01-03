"""Crawl API endpoints for CJ Dropshipping product discovery.

Manages crawl jobs that use SerpWatch Browser API to scrape CJ Dropshipping
at scale, processing results through webhooks.

Endpoints:
- POST /crawl/start - Start a new crawl job
- GET /crawl/{job_id} - Get crawl job status and progress
- GET /crawl/jobs - List recent crawl jobs
- POST /crawl/webhook - Receive SerpWatch postback (webhook)
- DELETE /crawl/{job_id} - Cancel a crawl job
"""

import logging
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ecom_arb.db.base import get_db
from ecom_arb.db.models import (
    CrawlJob,
    CrawlJobStatus,
    ExclusionRule,
    ScoredProduct,
)
from ecom_arb.integrations.serpwatch import (
    SerpWatchError,
    parse_post_id,
    parse_webhook_payload,
    submit_url,
)
from ecom_arb.services.cj_parser import (
    CJParserError,
    ProductRemovedError,
    SearchResultsData,
    extract_product_id,
    fetch_and_parse_cj_product,
    generate_search_url,
    parse_cj_search_results,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/crawl", tags=["crawl"])


# --- Request/Response Models ---


class CrawlConfig(BaseModel):
    """Configuration for a crawl job."""

    keywords: list[str] = Field(..., min_length=1, description="Keywords to search for")
    price_min: float = Field(0, ge=0, description="Minimum product price")
    price_max: float = Field(1000, ge=0, description="Maximum product price")
    include_warehouses: list[str] = Field(
        default_factory=list,
        description="Warehouses to include (empty = all)",
    )
    exclude_warehouses: list[str] = Field(
        default_factory=list,
        description="Warehouses to exclude",
    )
    include_categories: list[str] = Field(
        default_factory=list,
        description="Categories to include (empty = all)",
    )
    exclude_categories: list[str] = Field(
        default_factory=list,
        description="Categories to exclude",
    )


class CrawlJobResponse(BaseModel):
    """Response for a crawl job."""

    id: str
    status: str
    config: dict[str, Any]
    progress: dict[str, Any]
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None

    class Config:
        from_attributes = True


class CrawlJobListResponse(BaseModel):
    """Response for listing crawl jobs."""

    items: list[CrawlJobResponse]
    total: int


class StartCrawlResponse(BaseModel):
    """Response when starting a new crawl."""

    job_id: str
    status: str
    message: str
    search_urls_submitted: int


class WebhookResponse(BaseModel):
    """Response for webhook endpoint."""

    status: str
    message: str


# --- Helper Functions ---


def _get_default_progress() -> dict[str, int]:
    """Get default progress tracking structure."""
    return {
        "search_urls_submitted": 0,
        "search_urls_completed": 0,
        "product_urls_found": 0,
        "product_urls_skipped_existing": 0,
        "product_urls_submitted": 0,
        "product_urls_completed": 0,
        "products_parsed": 0,
        "products_skipped_filtered": 0,
        "products_scored": 0,
        "products_passed_scoring": 0,
        "errors": 0,
    }


async def _get_exclusion_rules(db: AsyncSession) -> dict[str, set[str]]:
    """Get all exclusion rules grouped by type."""
    result = await db.execute(select(ExclusionRule))
    rules = result.scalars().all()

    grouped: dict[str, set[str]] = {
        "country": set(),
        "category": set(),
        "supplier": set(),
        "keyword": set(),
    }

    for rule in rules:
        if rule.rule_type in grouped:
            grouped[rule.rule_type].add(rule.value.lower())

    return grouped


async def _filter_new_product_urls(
    product_urls: list[str],
    db: AsyncSession,
) -> tuple[list[str], int]:
    """Filter out URLs for products already in database.

    Returns:
        Tuple of (new_urls, skipped_count)
    """
    if not product_urls:
        return [], 0

    # Extract product IDs from URLs
    url_to_id = {}
    for url in product_urls:
        pid = extract_product_id(url)
        if pid:
            url_to_id[url] = pid

    if not url_to_id:
        return product_urls, 0

    product_ids = list(url_to_id.values())

    # Query existing products
    result = await db.execute(
        select(ScoredProduct.source_product_id).where(
            ScoredProduct.source_product_id.in_(product_ids)
        )
    )
    existing_ids = set(row[0] for row in result.fetchall())

    # Filter to only new URLs
    new_urls = [url for url, pid in url_to_id.items() if pid not in existing_ids]
    skipped_count = len(url_to_id) - len(new_urls)

    return new_urls, skipped_count


async def _update_job_progress(
    job_id: str,
    updates: dict[str, int],
    db: AsyncSession,
) -> None:
    """Update crawl job progress counters."""
    result = await db.execute(select(CrawlJob).where(CrawlJob.id == job_id))
    job = result.scalar_one_or_none()

    if not job:
        logger.warning(f"Job {job_id} not found for progress update")
        return

    progress = dict(job.progress) if job.progress else _get_default_progress()

    for key, value in updates.items():
        if key.startswith("+"):
            # Increment
            actual_key = key[1:]
            progress[actual_key] = progress.get(actual_key, 0) + value
        else:
            # Set
            progress[key] = value

    await db.execute(
        update(CrawlJob).where(CrawlJob.id == job_id).values(progress=progress)
    )


async def _check_job_completion(job_id: str, db: AsyncSession) -> None:
    """Check if a crawl job is complete and update status if so.

    Completion requires:
    - All search pages completed (including dynamically added pages)
    - All product URLs completed
    - At least one search completed (to avoid premature completion)
    """
    result = await db.execute(select(CrawlJob).where(CrawlJob.id == job_id))
    job = result.scalar_one_or_none()

    if not job or job.status != CrawlJobStatus.RUNNING:
        return

    progress = job.progress or {}

    search_submitted = progress.get("search_urls_submitted", 0)
    search_completed = progress.get("search_urls_completed", 0)
    products_submitted = progress.get("product_urls_submitted", 0)
    products_completed = progress.get("product_urls_completed", 0)

    # Need at least one search completed before checking completion
    if search_completed == 0:
        return

    search_done = search_completed >= search_submitted
    products_done = products_completed >= products_submitted

    # Log progress periodically
    logger.debug(
        f"Job {job_id} progress: search {search_completed}/{search_submitted}, "
        f"products {products_completed}/{products_submitted}"
    )

    if search_done and products_done:
        # Final tally
        passed = progress.get("products_passed_scoring", 0)
        scored = progress.get("products_scored", 0)

        await db.execute(
            update(CrawlJob)
            .where(CrawlJob.id == job_id)
            .values(
                status=CrawlJobStatus.COMPLETED,
                completed_at=datetime.utcnow(),
            )
        )
        logger.info(f"Crawl job {job_id} completed: {passed}/{scored} products passed scoring")
        await _add_job_log(
            job_id, "info",
            f"✓ Crawl completed! {passed} products passed scoring out of {scored} scored",
            db
        )


async def _add_job_log(
    job_id: str,
    level: str,
    message: str,
    db: AsyncSession,
    max_logs: int = 200,
) -> None:
    """Add a log entry to a crawl job.

    Args:
        job_id: The crawl job ID
        level: Log level (info, warn, error, debug)
        message: Log message
        db: Database session
        max_logs: Maximum number of logs to keep (older ones are trimmed)
    """
    result = await db.execute(select(CrawlJob).where(CrawlJob.id == job_id))
    job = result.scalar_one_or_none()

    if not job:
        return

    logs = list(job.logs) if job.logs else []

    # Add new log entry
    logs.append({
        "ts": datetime.utcnow().isoformat(),
        "level": level,
        "msg": message,
    })

    # Trim to max_logs (keep most recent)
    if len(logs) > max_logs:
        logs = logs[-max_logs:]

    await db.execute(
        update(CrawlJob).where(CrawlJob.id == job_id).values(logs=logs)
    )


# --- Endpoints ---


@router.post("/start", response_model=StartCrawlResponse)
async def start_crawl(
    config: CrawlConfig,
    db: AsyncSession = Depends(get_db),
) -> StartCrawlResponse:
    """Start a new crawl job.

    Creates a crawl job and submits search URLs to SerpWatch for fetching.
    Results will be received via the webhook endpoint.
    """
    # Generate job ID
    job_id = str(uuid.uuid4())[:8]

    # Get exclusion rules and merge with config
    exclusions = await _get_exclusion_rules(db)

    # Merge exclusions into config
    full_config = config.model_dump()
    full_config["exclude_warehouses"] = list(
        set(config.exclude_warehouses)
        | {c.upper() for c in exclusions.get("country", set())}
    )
    full_config["exclude_categories"] = list(
        set(config.exclude_categories) | exclusions.get("category", set())
    )

    # Create crawl job with initial log
    initial_logs = [{
        "ts": datetime.utcnow().isoformat(),
        "level": "info",
        "msg": f"Starting crawl for keywords: {', '.join(config.keywords)}",
    }]

    job = CrawlJob(
        id=job_id,
        status=CrawlJobStatus.PENDING,
        config=full_config,
        progress=_get_default_progress(),
        logs=initial_logs,
    )
    db.add(job)
    await db.flush()

    # Generate search URLs from keywords (page 1 for each)
    search_urls = []
    for keyword in config.keywords:
        url = generate_search_url(keyword, page=1)
        search_urls.append(url)

    # Submit search URLs to SerpWatch
    # Index encoding: keyword_index * 1000 + page_num (page 1 for initial)
    submitted = 0
    for keyword_index, url in enumerate(search_urls):
        try:
            index = keyword_index * 1000 + 1  # keyword_index * 1000 + page 1
            await submit_url(url, job_id, "search", index)
            submitted += 1
            await _add_job_log(job_id, "info", f"Submitted search: {config.keywords[keyword_index]}", db)
        except SerpWatchError as e:
            logger.error(f"Failed to submit search URL {url}: {e}")
            await _add_job_log(job_id, "error", f"Failed to submit search: {e}", db)

    if submitted == 0:
        # All submissions failed
        job.status = CrawlJobStatus.FAILED
        job.error_message = "Failed to submit any search URLs to SerpWatch"
        await db.flush()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to submit search URLs to SerpWatch",
        )

    # Update job status
    job.status = CrawlJobStatus.RUNNING
    job.started_at = datetime.utcnow()
    job.progress = {
        **_get_default_progress(),
        "search_urls_submitted": submitted,
    }
    await db.flush()

    return StartCrawlResponse(
        job_id=job_id,
        status="running",
        message=f"Started crawl job with {submitted} search URLs",
        search_urls_submitted=submitted,
    )


@router.get("/jobs", response_model=CrawlJobListResponse)
async def list_crawl_jobs(
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> CrawlJobListResponse:
    """List recent crawl jobs."""
    result = await db.execute(
        select(CrawlJob).order_by(desc(CrawlJob.created_at)).limit(limit)
    )
    jobs = result.scalars().all()

    return CrawlJobListResponse(
        items=[
            CrawlJobResponse(
                id=j.id,
                status=j.status.value,
                config=j.config,
                progress=j.progress,
                error_message=j.error_message,
                created_at=j.created_at,
                started_at=j.started_at,
                completed_at=j.completed_at,
            )
            for j in jobs
        ],
        total=len(jobs),
    )


@router.get("/{job_id}", response_model=CrawlJobResponse)
async def get_crawl_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
) -> CrawlJobResponse:
    """Get crawl job status and progress."""
    result = await db.execute(select(CrawlJob).where(CrawlJob.id == job_id))
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Crawl job not found",
        )

    return CrawlJobResponse(
        id=job.id,
        status=job.status.value,
        config=job.config,
        progress=job.progress,
        error_message=job.error_message,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
    )


class CrawlLogEntry(BaseModel):
    """A single log entry."""

    ts: str
    level: str
    msg: str


class CrawlLogsResponse(BaseModel):
    """Response for crawl job logs."""

    job_id: str
    logs: list[CrawlLogEntry]


@router.get("/{job_id}/logs", response_model=CrawlLogsResponse)
async def get_crawl_logs(
    job_id: str,
    since: int = Query(0, ge=0, description="Return logs after this index"),
    db: AsyncSession = Depends(get_db),
) -> CrawlLogsResponse:
    """Get logs for a crawl job.

    Use the 'since' parameter for polling - pass the current log count
    to only receive new logs.
    """
    result = await db.execute(select(CrawlJob).where(CrawlJob.id == job_id))
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Crawl job not found",
        )

    logs = job.logs or []

    # Return logs after 'since' index
    new_logs = logs[since:] if since < len(logs) else []

    return CrawlLogsResponse(
        job_id=job_id,
        logs=[CrawlLogEntry(**log) for log in new_logs],
    )


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_crawl_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Cancel a running crawl job."""
    result = await db.execute(select(CrawlJob).where(CrawlJob.id == job_id))
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Crawl job not found",
        )

    if job.status not in (CrawlJobStatus.PENDING, CrawlJobStatus.RUNNING):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel job in {job.status.value} status",
        )

    job.status = CrawlJobStatus.CANCELLED
    job.completed_at = datetime.utcnow()
    await db.flush()


@router.post("/webhook", response_model=WebhookResponse)
async def crawl_webhook(
    payload: dict[str, Any],
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> WebhookResponse:
    """Receive SerpWatch postback with scraped HTML.

    This endpoint processes results from SerpWatch:
    - For search results: extracts product URLs and submits them for fetching
    - For product pages: parses product data, filters, scores, and stores

    Must respond quickly (< 5s) to avoid SerpWatch timeouts.
    Heavy processing is done in background tasks.
    """
    logger.info(f"Received webhook payload: {payload.get('status', 'unknown')}")

    # Parse webhook payload
    results = parse_webhook_payload(payload)

    if not results:
        return WebhookResponse(status="ok", message="No results in payload")

    processed = 0
    errors = 0

    for result in results:
        if not result.success or not result.html_url:
            logger.warning(f"Skipping failed result: {result.error}")
            errors += 1
            continue

        # Parse post_id to get job info
        parsed = parse_post_id(result.post_id)
        if not parsed:
            logger.warning(f"Invalid post_id format: {result.post_id}")
            errors += 1
            continue

        job_id, url_type, index = parsed

        # Check if job exists and is running
        job_result = await db.execute(select(CrawlJob).where(CrawlJob.id == job_id))
        job = job_result.scalar_one_or_none()

        if not job:
            logger.warning(f"Job {job_id} not found")
            continue

        if job.status == CrawlJobStatus.CANCELLED:
            logger.info(f"Job {job_id} was cancelled, skipping result")
            continue

        # Process based on URL type
        if url_type == "search":
            # Schedule search processing in background
            background_tasks.add_task(
                _process_search_result,
                job_id=job_id,
                html_url=result.html_url,
                index=index,
            )
            processed += 1

        elif url_type == "product":
            # Schedule product processing in background
            background_tasks.add_task(
                _process_product_result,
                job_id=job_id,
                html_url=result.html_url,
                original_url=result.url,
                index=index,
            )
            processed += 1

        else:
            logger.warning(f"Unknown URL type: {url_type}")

    return WebhookResponse(
        status="ok",
        message=f"Queued {processed} results for processing ({errors} errors)",
    )


# --- Background Task Functions ---


async def _process_search_result(
    job_id: str,
    html_url: str,
    index: int,
) -> None:
    """Process search result HTML in background.

    Extracts product URLs and submits new ones to SerpWatch.
    If this is page 1, also submits additional pages for crawling.

    Args:
        job_id: The crawl job ID
        html_url: URL to the stored HTML from SerpWatch
        index: Index encoding keyword_index and page_num as: keyword_index * 1000 + page_num
    """
    from ecom_arb.db.base import async_session_maker

    # Decode index: keyword_index * 1000 + page_num
    keyword_index = index // 1000
    page_num = index % 1000
    if page_num == 0:
        page_num = 1  # Legacy format compatibility

    async with async_session_maker() as db:
        try:
            # Parse search results (now includes pagination info)
            search_data = await parse_cj_search_results(html_url)
            product_urls = search_data.product_urls
            total_pages = search_data.total_pages

            # Get job config for filtering
            result = await db.execute(select(CrawlJob).where(CrawlJob.id == job_id))
            job = result.scalar_one_or_none()

            if not job or job.status == CrawlJobStatus.CANCELLED:
                return

            config = job.config or {}
            keywords = config.get("keywords", [])
            keyword = keywords[keyword_index] if keyword_index < len(keywords) else f"search_{keyword_index}"

            logger.info(f"Job {job_id}: Found {len(product_urls)} products in '{keyword}' page {page_num}/{total_pages}")
            await _add_job_log(
                job_id, "info",
                f"Search '{keyword}' page {page_num}: {len(product_urls)} products (total pages: {total_pages})",
                db
            )

            # If this is page 1 and there are more pages, submit pages 2-N
            if page_num == 1 and total_pages > 1:
                pages_to_submit = min(total_pages, 10)  # Cap at 10 pages per keyword
                additional_pages = 0

                for page in range(2, pages_to_submit + 1):
                    try:
                        page_url = generate_search_url(keyword, page)
                        # Encode as: keyword_index * 1000 + page_num
                        page_index = keyword_index * 1000 + page
                        await submit_url(page_url, job_id, "search", page_index)
                        additional_pages += 1
                    except SerpWatchError as e:
                        logger.error(f"Failed to submit page {page} for '{keyword}': {e}")

                if additional_pages > 0:
                    await _update_job_progress(job_id, {"+search_urls_submitted": additional_pages}, db)
                    await _add_job_log(job_id, "info", f"Queued {additional_pages} additional pages for '{keyword}'", db)

            # Filter out already-existing products
            new_urls, skipped = await _filter_new_product_urls(product_urls, db)
            logger.info(f"Job {job_id}: {len(new_urls)} new URLs ({skipped} skipped - already in DB)")
            if skipped > 0:
                await _add_job_log(job_id, "info", f"Skipped {skipped} existing products", db)

            # Update progress
            await _update_job_progress(
                job_id,
                {
                    "+search_urls_completed": 1,
                    "+product_urls_found": len(product_urls),
                    "+product_urls_skipped_existing": skipped,
                },
                db,
            )

            # Submit new product URLs to SerpWatch
            submitted = 0
            current_progress = await db.execute(select(CrawlJob).where(CrawlJob.id == job_id))
            current_job = current_progress.scalar_one_or_none()
            base_index = current_job.progress.get("product_urls_submitted", 0) if current_job else 0

            for i, url in enumerate(new_urls):
                try:
                    await submit_url(url, job_id, "product", base_index + i)
                    submitted += 1
                except SerpWatchError as e:
                    logger.error(f"Failed to submit product URL: {e}")

            await _update_job_progress(job_id, {"+product_urls_submitted": submitted}, db)
            if submitted > 0:
                await _add_job_log(job_id, "info", f"Queued {submitted} products for fetching", db)

            # Check if job is complete
            await _check_job_completion(job_id, db)

            await db.commit()

        except CJParserError as e:
            logger.error(f"Job {job_id}: Search parse error: {e}")
            await _update_job_progress(job_id, {"+errors": 1, "+search_urls_completed": 1}, db)
            await _add_job_log(job_id, "error", f"Search parse error: {str(e)[:50]}", db)
            await db.commit()
        except Exception as e:
            logger.exception(f"Job {job_id}: Unexpected error processing search: {e}")
            await _update_job_progress(job_id, {"+errors": 1}, db)
            await db.commit()


async def _process_product_result(
    job_id: str,
    html_url: str,
    original_url: str,
    index: int,
) -> None:
    """Process product page HTML in background.

    Parses product data, applies filters, scores, and stores in database.
    """
    from ecom_arb.db.base import async_session_maker
    from ecom_arb.scoring.models import Product as ScoringProduct
    from ecom_arb.scoring.models import ProductCategory, ScoringConfig
    from ecom_arb.scoring.scorer import score_product

    async with async_session_maker() as db:
        try:
            # Parse product data
            product_data = await fetch_and_parse_cj_product(html_url)
            logger.info(f"Job {job_id}: Parsed product {product_data.id}: {product_data.name}")

            # Get job config
            result = await db.execute(select(CrawlJob).where(CrawlJob.id == job_id))
            job = result.scalar_one_or_none()

            if not job or job.status == CrawlJobStatus.CANCELLED:
                return

            config = job.config or {}

            # Safety dedup check - skip if already in database
            existing = await db.execute(
                select(ScoredProduct).where(
                    ScoredProduct.source_product_id == product_data.id
                )
            )
            if existing.scalar_one_or_none():
                logger.info(f"Job {job_id}: Product {product_data.id} already exists, skipping")
                await _update_job_progress(
                    job_id,
                    {"+product_urls_completed": 1, "+products_skipped_filtered": 1},
                    db,
                )
                await db.commit()
                return

            await _update_job_progress(job_id, {"+products_parsed": 1}, db)

            # Apply filters
            filtered_reason = _apply_crawl_filters(product_data, config)
            if filtered_reason:
                logger.debug(f"Job {job_id}: Product {product_data.id} filtered: {filtered_reason}")
                await _update_job_progress(
                    job_id,
                    {"+product_urls_completed": 1, "+products_skipped_filtered": 1},
                    db,
                )
                await _check_job_completion(job_id, db)
                await db.commit()
                return

            # Create scoring input
            sell_price = float(product_data.sell_price_min)
            # Calculate selling price with ~70% target margin
            selling_price = round(sell_price / 0.30, 2)
            selling_price = max(selling_price, 50.0)  # Minimum $50

            # Map category
            category = _map_category(product_data.categories)

            # Estimate shipping
            warehouse = product_data.warehouse_country or "CN"
            if warehouse == "US":
                ship_min, ship_max = 3, 7
                shipping_cost = 5.0
            else:
                ship_min, ship_max = 10, 20
                shipping_cost = 8.0

            scoring_input = ScoringProduct(
                id=product_data.id,
                name=product_data.name,
                product_cost=sell_price,
                shipping_cost=shipping_cost,
                selling_price=selling_price,
                category=category,
                requires_sizing=False,
                is_fragile=False,
                weight_grams=product_data.weight_min or 500,
                supplier_rating=4.7,
                supplier_age_months=24,
                supplier_feedback_count=product_data.list_count * 5 if product_data.list_count else 500,
                shipping_days_min=ship_min,
                shipping_days_max=ship_max,
                has_fast_shipping=ship_max <= 10,
                estimated_cpc=0.50,  # Default CPC
                monthly_search_volume=1000,
                amazon_prime_exists=False,
                amazon_review_count=0,
                source="cj_crawl",
                source_url=original_url,
            )

            # Score product
            score = score_product(scoring_input)

            # Store in database
            scored_product = ScoredProduct(
                source_product_id=product_data.id,
                name=product_data.name,
                crawl_job_id=job_id,  # Associate with crawl job
                source="cj_crawl",
                source_url=original_url,
                product_cost=Decimal(str(sell_price)),
                shipping_cost=Decimal(str(shipping_cost)),
                selling_price=Decimal(str(selling_price)),
                category=category.value,
                estimated_cpc=Decimal("0.50"),
                weight_grams=product_data.weight_min,
                shipping_days_min=ship_min,
                shipping_days_max=ship_max,
                warehouse_country=warehouse,
                supplier_name=product_data.supplier_name,
                inventory_count=product_data.warehouse_inventory,
                cogs=Decimal(str(score.cogs)),
                gross_margin=Decimal(str(score.gross_margin)),
                net_margin=Decimal(str(score.net_margin)),
                max_cpc=Decimal(str(score.max_cpc)),
                cpc_buffer=Decimal(str(score.cpc_buffer)),
                passed_filters=score.passed_filters,
                rejection_reasons=score.rejection_reasons,
                points=score.points,
                point_breakdown=score.point_breakdown,
                rank_score=Decimal(str(score.rank_score)) if score.rank_score else None,
                recommendation=score.recommendation,
            )

            db.add(scored_product)

            # Update progress
            passed = 1 if score.passed_filters else 0
            await _update_job_progress(
                job_id,
                {
                    "+product_urls_completed": 1,
                    "+products_scored": 1,
                    "+products_passed_scoring": passed,
                },
                db,
            )

            # Check completion
            await _check_job_completion(job_id, db)

            await db.commit()
            logger.info(
                f"Job {job_id}: Scored product {product_data.id} - {score.recommendation}"
            )

            # Log based on result
            short_name = product_data.name[:30] + "..." if len(product_data.name) > 30 else product_data.name
            if score.passed_filters:
                await _add_job_log(job_id, "info", f"✓ PASSED: {short_name} (margin: {score.gross_margin:.1f}%)", db)
            else:
                await _add_job_log(job_id, "warn", f"✗ Rejected: {short_name}", db)

        except ProductRemovedError as e:
            # Product was removed from CJ - this is expected and not an error
            logger.debug(f"Job {job_id}: Product removed from CJ: {original_url}")
            await _update_job_progress(
                job_id, {"+product_urls_completed": 1, "+products_skipped_filtered": 1}, db
            )
            await _check_job_completion(job_id, db)
            await db.commit()
        except CJParserError as e:
            logger.error(f"Job {job_id}: Product parse error: {e}")
            await _update_job_progress(
                job_id, {"+errors": 1, "+product_urls_completed": 1}, db
            )
            await _add_job_log(job_id, "error", f"Parse error: {str(e)[:50]}", db)
            await _check_job_completion(job_id, db)
            await db.commit()
        except Exception as e:
            logger.exception(f"Job {job_id}: Unexpected error processing product: {e}")
            await _update_job_progress(
                job_id, {"+errors": 1, "+product_urls_completed": 1}, db
            )
            await _check_job_completion(job_id, db)
            await db.commit()


def _apply_crawl_filters(
    product: Any,
    config: dict[str, Any],
) -> str | None:
    """Apply crawl config filters to product.

    Returns:
        Rejection reason string if filtered out, None if passes
    """
    # Price filter
    price_min = config.get("price_min", 0)
    price_max = config.get("price_max", 1000)

    sell_price = float(product.sell_price_min)
    if sell_price < price_min:
        return f"Price ${sell_price} below minimum ${price_min}"
    if sell_price > price_max:
        return f"Price ${sell_price} above maximum ${price_max}"

    # Warehouse filter
    warehouse = (product.warehouse_country or "CN").upper()
    include_warehouses = config.get("include_warehouses", [])
    exclude_warehouses = config.get("exclude_warehouses", [])

    if include_warehouses and warehouse not in [w.upper() for w in include_warehouses]:
        return f"Warehouse {warehouse} not in include list"
    if warehouse in [w.upper() for w in exclude_warehouses]:
        return f"Warehouse {warehouse} in exclude list"

    # Category filter
    categories = [c.lower() for c in (product.categories or [])]
    include_categories = [c.lower() for c in config.get("include_categories", [])]
    exclude_categories = [c.lower() for c in config.get("exclude_categories", [])]

    if include_categories:
        if not any(cat in include_categories for cat in categories):
            return f"Categories {categories} not in include list"

    for cat in categories:
        if cat in exclude_categories:
            return f"Category {cat} in exclude list"

    return None


def _map_category(categories: list[str]) -> "ProductCategory":
    """Map CJ categories to our ProductCategory enum."""
    from ecom_arb.scoring.models import ProductCategory

    if not categories:
        return ProductCategory.HOME_DECOR

    combined = " ".join(categories).lower()

    if any(x in combined for x in ["garden", "outdoor", "patio"]):
        return ProductCategory.GARDEN
    elif any(x in combined for x in ["kitchen", "cook", "bake"]):
        return ProductCategory.KITCHEN
    elif any(x in combined for x in ["pet", "dog", "cat"]):
        return ProductCategory.PET
    elif any(x in combined for x in ["office", "desk", "work"]):
        return ProductCategory.OFFICE
    elif any(x in combined for x in ["craft", "art", "sewing"]):
        return ProductCategory.CRAFTS
    elif any(x in combined for x in ["tool", "hardware"]):
        return ProductCategory.TOOLS
    elif any(x in combined for x in ["camp", "hike", "sport"]):
        return ProductCategory.OUTDOOR
    elif any(x in combined for x in ["home", "decor", "furniture"]):
        return ProductCategory.HOME_DECOR
    else:
        return ProductCategory.HOME_DECOR
