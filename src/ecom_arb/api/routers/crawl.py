"""Crawl API endpoints for CJ Dropshipping product discovery.

Manages crawl jobs that use SerpWatch Browser API to scrape CJ Dropshipping
at scale, processing results through webhooks.

Architecture:
- Queue-based URL processing with delays for anti-bot resilience
- Webhook-driven processing with delayed background submissions
- Retry logic with jittered exponential backoff

Endpoints:
- POST /crawl/start - Start a new crawl job
- GET /crawl/{job_id} - Get crawl job status and progress
- GET /crawl/jobs - List recent crawl jobs
- POST /crawl/webhook - Receive SerpWatch postback (webhook)
- DELETE /crawl/{job_id} - Cancel a crawl job
- GET /crawl/{job_id}/events - Get crawl events for debugging
- GET /crawl/{job_id}/timeline - Get submission timeline
"""

import asyncio
import logging
import os
import random
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ecom_arb.db.base import get_db
from ecom_arb.db.models import (
    CrawlEvent,
    CrawlJob,
    CrawlJobStatus,
    CrawlQueue,
    CrawlQueueStatus,
    CrawlQueueUrlType,
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

# Queue configuration
QUEUE_MIN_THRESHOLD = 15  # Min items before starting submissions
SUBMISSION_DELAY_MIN = 5.0  # Min seconds between submissions
SUBMISSION_DELAY_MAX = 15.0  # Max seconds between submissions
RETRY_BASE_DELAY = 15 * 60  # 15 minutes base for retry
RETRY_JITTER_MAX = 5 * 60  # 0-5 minutes jitter
MAX_RETRIES = 3

# Debug directory for blocked HTML
BLOCKED_HTML_DIR = "data/debug/blocked_html"

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


# --- Queue Helper Functions ---


async def _add_to_queue(
    job_id: str,
    url: str,
    url_type: CrawlQueueUrlType,
    keyword: str | None,
    db: AsyncSession,
    priority: int = 2,
) -> str:
    """Add a URL to the crawl queue.

    Returns:
        The queue item ID
    """
    # Use hex without dashes to avoid breaking post_id parsing
    queue_id = uuid.uuid4().hex[:12]
    queue_item = CrawlQueue(
        id=queue_id,
        job_id=job_id,
        url=url,
        url_type=url_type,
        keyword=keyword,
        priority=priority,
        status=CrawlQueueStatus.PENDING,
    )
    db.add(queue_item)
    return queue_id


async def _log_crawl_event(
    job_id: str,
    event_type: str,
    db: AsyncSession,
    queue_item_id: str | None = None,
    url: str | None = None,
    keyword: str | None = None,
    details: dict | None = None,
) -> None:
    """Log a crawl event for debugging."""
    event = CrawlEvent(
        id=uuid.uuid4().hex[:12],
        job_id=job_id,
        queue_item_id=queue_item_id,
        event_type=event_type,
        url=url,
        keyword=keyword,
        details=details or {},
    )
    db.add(event)


async def _get_queue_stats(job_id: str, db: AsyncSession) -> dict[str, int]:
    """Get queue statistics for a job."""
    result = await db.execute(
        select(CrawlQueue.status, func.count(CrawlQueue.id))
        .where(CrawlQueue.job_id == job_id)
        .group_by(CrawlQueue.status)
    )
    stats = {row[0].value: row[1] for row in result.fetchall()}
    return {
        "pending": stats.get("pending", 0),
        "submitted": stats.get("submitted", 0),
        "completed": stats.get("completed", 0),
        "failed": stats.get("failed", 0),
    }


async def _get_pending_count(job_id: str, db: AsyncSession) -> int:
    """Get count of pending queue items ready to submit."""
    result = await db.execute(
        select(func.count(CrawlQueue.id))
        .where(CrawlQueue.job_id == job_id)
        .where(CrawlQueue.status == CrawlQueueStatus.PENDING)
        .where(
            (CrawlQueue.next_attempt_at.is_(None)) |
            (CrawlQueue.next_attempt_at <= datetime.utcnow())
        )
    )
    return result.scalar() or 0


async def _handle_queue_failure(
    queue_item: CrawlQueue,
    error_message: str,
    db: AsyncSession,
) -> None:
    """Handle a queue item failure with retry logic."""
    queue_item.retry_count += 1
    queue_item.error_message = error_message

    if queue_item.retry_count > MAX_RETRIES:
        # Max retries exceeded - give up
        queue_item.status = CrawlQueueStatus.FAILED
        queue_item.completed_at = datetime.utcnow()
        logger.warning(f"Queue item {queue_item.id} failed after {MAX_RETRIES} retries: {error_message}")

        await _log_crawl_event(
            queue_item.job_id, "fail", db,
            queue_item_id=queue_item.id,
            url=queue_item.url,
            keyword=queue_item.keyword,
            details={"total_retries": queue_item.retry_count, "last_error": error_message},
        )
    else:
        # Schedule retry with jittered exponential backoff
        jitter = random.uniform(0, RETRY_JITTER_MAX)
        delay_seconds = RETRY_BASE_DELAY * (2 ** (queue_item.retry_count - 1)) + jitter

        queue_item.status = CrawlQueueStatus.PENDING
        queue_item.next_attempt_at = datetime.utcnow() + timedelta(seconds=delay_seconds)

        logger.info(
            f"Queue item {queue_item.id} retry {queue_item.retry_count}, "
            f"next attempt in {delay_seconds/60:.1f} minutes"
        )

        await _log_crawl_event(
            queue_item.job_id, "retry", db,
            queue_item_id=queue_item.id,
            url=queue_item.url,
            keyword=queue_item.keyword,
            details={
                "retry_count": queue_item.retry_count,
                "next_attempt_at": queue_item.next_attempt_at.isoformat(),
                "delay_minutes": delay_seconds / 60,
            },
        )


def _save_blocked_html(job_id: str, queue_item_id: str, html: str, reason: str) -> str | None:
    """Save blocked page HTML for debugging. Returns filepath or None."""
    try:
        os.makedirs(BLOCKED_HTML_DIR, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{job_id}_{queue_item_id}.html"
        filepath = os.path.join(BLOCKED_HTML_DIR, filename)

        with open(filepath, "w") as f:
            f.write(f"<!-- BLOCKED: {reason} -->\n")
            f.write(f"<!-- Job: {job_id}, Queue Item: {queue_item_id} -->\n")
            f.write(f"<!-- Timestamp: {timestamp} -->\n\n")
            f.write(html)

        logger.info(f"Saved blocked HTML to {filepath}")
        return filepath
    except Exception as e:
        logger.error(f"Failed to save blocked HTML: {e}")
        return None


async def _check_queue_completion(job_id: str, db: AsyncSession) -> None:
    """Check if a crawl job is complete based on queue state."""
    stats = await _get_queue_stats(job_id, db)

    pending = stats.get("pending", 0)
    submitted = stats.get("submitted", 0)

    if pending == 0 and submitted == 0:
        # All items completed or failed
        completed = stats.get("completed", 0)
        failed = stats.get("failed", 0)

        await db.execute(
            update(CrawlJob)
            .where(CrawlJob.id == job_id)
            .values(
                status=CrawlJobStatus.COMPLETED,
                completed_at=datetime.utcnow(),
            )
        )
        logger.info(f"Crawl job {job_id} complete: {completed} succeeded, {failed} failed")
        await _add_job_log(
            job_id, "info",
            f"✓ Crawl completed! {completed} URLs processed, {failed} failed",
            db,
        )


async def _resolve_cj_redirect(url: str) -> str | None:
    """Resolve CJ product URL redirects.

    CJ product URLs like /product/-p-{id}.html redirect to /product/{name}-p-{id}.html.
    We need to follow the redirect to get the actual page URL.

    Args:
        url: CJ product URL

    Returns:
        Resolved URL or None if resolution failed
    """
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            # Use HEAD request to just get the final URL without downloading content
            response = await client.head(url)
            final_url = str(response.url)
            return final_url
    except Exception as e:
        logger.warning(f"Failed to resolve redirect for {url}: {e}")
        return None


async def _submit_next_from_queue(job_id: str, delay: float = 0) -> None:
    """Submit the next URL from the queue with delay.

    This is a background task that:
    1. Waits for the specified delay
    2. Gets the next ready URL from queue (priority-sorted, randomized)
    3. Submits to SerpWatch
    4. Schedules itself again if more items pending
    """
    from ecom_arb.db.base import async_session_maker

    # Wait for delay
    if delay > 0:
        await asyncio.sleep(delay)

    async with async_session_maker() as db:
        try:
            # Check if job is still running
            job_result = await db.execute(select(CrawlJob).where(CrawlJob.id == job_id))
            job = job_result.scalar_one_or_none()

            if not job or job.status != CrawlJobStatus.RUNNING:
                logger.debug(f"Job {job_id} not running, stopping queue submission")
                return

            # Get next ready URL (priority-sorted, then random)
            # Priority 1 = search/pagination, Priority 2 = product
            result = await db.execute(
                select(CrawlQueue)
                .where(CrawlQueue.job_id == job_id)
                .where(CrawlQueue.status == CrawlQueueStatus.PENDING)
                .where(
                    (CrawlQueue.next_attempt_at.is_(None)) |
                    (CrawlQueue.next_attempt_at <= datetime.utcnow())
                )
                .order_by(CrawlQueue.priority.asc(), func.random())
                .limit(1)
            )
            queue_item = result.scalar_one_or_none()

            if not queue_item:
                # No ready items - check if any are waiting for retry
                retry_result = await db.execute(
                    select(func.count(CrawlQueue.id))
                    .where(CrawlQueue.job_id == job_id)
                    .where(CrawlQueue.status == CrawlQueueStatus.PENDING)
                    .where(CrawlQueue.next_attempt_at > datetime.utcnow())
                )
                waiting_for_retry = retry_result.scalar() or 0

                if waiting_for_retry > 0:
                    # Schedule check again in 1 minute
                    logger.debug(f"Job {job_id}: {waiting_for_retry} items waiting for retry")
                    asyncio.create_task(_submit_next_from_queue(job_id, delay=60))
                else:
                    # Check completion
                    await _check_queue_completion(job_id, db)
                    await db.commit()
                return

            # Submit to SerpWatch
            # Note: Don't pre-resolve redirects - CJ blocks non-browser requests with validation page.
            # SerpWatch's browser will follow the 301 redirect natively.
            try:
                await submit_url(
                    queue_item.url,
                    job_id,
                    queue_item.url_type.value,
                    queue_item.id,  # Use queue ID as index
                )
                queue_item.status = CrawlQueueStatus.SUBMITTED
                queue_item.submitted_at = datetime.utcnow()

                await _log_crawl_event(
                    job_id, "submit", db,
                    queue_item_id=queue_item.id,
                    url=queue_item.url,
                    keyword=queue_item.keyword,
                    details={
                        "delay_seconds": delay,
                        "url_type": queue_item.url_type.value,
                        "retry_count": queue_item.retry_count,
                    },
                )

                # Also log to job logs for UI
                keyword_display = queue_item.keyword or queue_item.url_type.value
                await _add_job_log(
                    job_id, "info",
                    f"Submitted {queue_item.url_type.value}: {keyword_display} (delay={delay:.1f}s)",
                    db,
                )

                # Log to terminal
                print(f">>> SUBMITTED: {keyword_display} (delay={delay:.1f}s)", flush=True)
                logger.info(f"Job {job_id}: Submitted {queue_item.url_type.value} URL (delay={delay:.1f}s)")

            except SerpWatchError as e:
                logger.error(f"Job {job_id}: Failed to submit URL: {e}")
                await _handle_queue_failure(queue_item, str(e), db)

            await db.commit()

            # Schedule next submission with random delay
            pending_count = await _get_pending_count(job_id, db)
            if pending_count > 0:
                next_delay = random.uniform(SUBMISSION_DELAY_MIN, SUBMISSION_DELAY_MAX)
                asyncio.create_task(_submit_next_from_queue(job_id, delay=next_delay))

        except Exception as e:
            logger.exception(f"Job {job_id}: Error in queue submission: {e}")
            await db.rollback()


# --- Endpoints ---


@router.post("/start", response_model=StartCrawlResponse)
async def start_crawl(
    config: CrawlConfig,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> StartCrawlResponse:
    """Start a new crawl job.

    Creates a crawl job and queues search URLs for fetching.
    URLs are submitted to SerpWatch with delays for anti-bot resilience.
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
        "msg": f"Starting crawl for keywords: {', '.join(config.keywords)} (queue-based)",
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

    # Add search URLs to queue (priority 1 for searches)
    queued = 0
    for keyword in config.keywords:
        url = generate_search_url(keyword, page=1)
        await _add_to_queue(
            job_id=job_id,
            url=url,
            url_type=CrawlQueueUrlType.SEARCH,
            keyword=keyword,
            db=db,
            priority=1,  # High priority for searches
        )
        queued += 1
        await _add_job_log(job_id, "info", f"Queued search: {keyword}", db)

    if queued == 0:
        job.status = CrawlJobStatus.FAILED
        job.error_message = "No keywords provided"
        await db.flush()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No keywords provided",
        )

    # Update job status
    job.status = CrawlJobStatus.RUNNING
    job.started_at = datetime.utcnow()
    await db.flush()

    # Kickstart: schedule first submission immediately
    asyncio.create_task(_submit_next_from_queue(job_id, delay=0))

    await _add_job_log(
        job_id, "info",
        f"Queued {queued} searches. Starting submissions with {SUBMISSION_DELAY_MIN}-{SUBMISSION_DELAY_MAX}s delays.",
        db,
    )

    return StartCrawlResponse(
        job_id=job_id,
        status="running",
        message=f"Started crawl job with {queued} search URLs queued",
        search_urls_submitted=queued,
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
    - For Amazon requests: routes to Amazon handler
    - For search results: extracts product URLs and adds them to queue
    - For product pages: parses product data, filters, scores, and stores
    - Updates queue item status and schedules next submission

    Must respond quickly (< 5s) to avoid SerpWatch timeouts.
    Heavy processing is done in background tasks.
    """
    logger.info(f"Received webhook payload: {payload.get('status', 'unknown')}")

    # Check if this is an Amazon request and forward to Amazon handler
    results_peek = parse_webhook_payload(payload)
    if results_peek:
        first_post_id = results_peek[0].post_id
        if first_post_id and "-amazon-" in first_post_id:
            logger.info(f"Detected Amazon webhook, forwarding to Amazon handler")
            from ecom_arb.api.routers.amazon import amazon_webhook, parse_amazon_post_id
            from fastapi import Request
            from starlette.requests import Request as StarletteRequest

            # Process Amazon results
            for result in results_peek:
                parsed = parse_amazon_post_id(result.post_id)
                if not parsed:
                    logger.warning(f"Invalid Amazon post_id: {result.post_id}")
                    continue

                product_id, url_type, index = parsed

                if not result.success or not result.html_url:
                    logger.warning(f"Amazon fetch failed: {result.error}")
                    continue

                # Get keyword from product
                from ecom_arb.db.models import ScoredProduct
                from uuid import UUID
                stmt = select(ScoredProduct).where(ScoredProduct.id == UUID(product_id))
                db_result = await db.execute(stmt)
                product = db_result.scalar_one_or_none()

                keyword = "unknown"
                if product and product.keyword_analysis:
                    keyword = product.keyword_analysis.get("best_keyword", "unknown")

                # Process in background
                from ecom_arb.api.routers.amazon import process_amazon_results
                background_tasks.add_task(
                    process_amazon_results,
                    product_id,
                    result.html_url,
                    keyword,
                )

            return WebhookResponse(status="ok", message=f"Forwarded {len(results_peek)} Amazon result(s)")

    # Parse webhook payload
    results = parse_webhook_payload(payload)

    if not results:
        return WebhookResponse(status="ok", message="No results in payload")

    processed = 0
    errors = 0

    for result in results:
        # Parse post_id to get job info and queue_item_id
        parsed = parse_post_id(result.post_id)
        if not parsed:
            logger.warning(f"Invalid post_id format: {result.post_id}")
            errors += 1
            continue

        job_id, url_type, queue_item_id = parsed

        # Look up queue item
        queue_result = await db.execute(
            select(CrawlQueue).where(CrawlQueue.id == queue_item_id)
        )
        queue_item = queue_result.scalar_one_or_none()

        if not queue_item:
            logger.warning(f"Queue item {queue_item_id} not found")
            errors += 1
            continue

        # Check if job exists and is running
        job_result = await db.execute(select(CrawlJob).where(CrawlJob.id == job_id))
        job = job_result.scalar_one_or_none()

        if not job:
            logger.warning(f"Job {job_id} not found")
            continue

        if job.status == CrawlJobStatus.CANCELLED:
            logger.info(f"Job {job_id} was cancelled, skipping result")
            queue_item.status = CrawlQueueStatus.FAILED
            queue_item.error_message = "Job cancelled"
            continue

        # Log webhook receipt
        await _log_crawl_event(
            job_id, "webhook", db,
            queue_item_id=queue_item_id,
            url=queue_item.url,
            keyword=queue_item.keyword,
            details={"success": result.success, "error": result.error},
        )

        # Log to job logs for UI
        keyword_display = queue_item.keyword or queue_item.url_type.value
        if result.success:
            print(f">>> WEBHOOK OK: {keyword_display}", flush=True)
            await _add_job_log(job_id, "info", f"Received: {keyword_display}", db)
        else:
            print(f">>> WEBHOOK FAIL: {keyword_display} - {result.error}", flush=True)
            await _add_job_log(job_id, "warn", f"Failed: {keyword_display} - {result.error}", db)

        # Handle failed result
        if not result.success or not result.html_url:
            logger.warning(f"Failed result for {queue_item_id}: {result.error}")
            await _handle_queue_failure(queue_item, result.error or "Unknown error", db)
            errors += 1
            await db.commit()
            # Schedule next submission
            asyncio.create_task(_submit_next_from_queue(job_id, delay=random.uniform(SUBMISSION_DELAY_MIN, SUBMISSION_DELAY_MAX)))
            continue

        # Process based on URL type
        if url_type in ("search", "pagination"):
            # Schedule search processing in background
            background_tasks.add_task(
                _process_search_result_queued,
                job_id=job_id,
                queue_item_id=queue_item_id,
                html_url=result.html_url,
            )
            processed += 1

        elif url_type == "product":
            # Schedule product processing in background
            background_tasks.add_task(
                _process_product_result_queued,
                job_id=job_id,
                queue_item_id=queue_item_id,
                html_url=result.html_url,
                original_url=result.url,
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
                monthly_search_volume=1000,  # Default until Google Ads lookup
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


# --- Queue-Aware Background Task Functions ---


async def _process_search_result_queued(
    job_id: str,
    queue_item_id: str,
    html_url: str,
) -> None:
    """Process search result HTML with queue-based workflow.

    Extracts product URLs and adds them to queue with delays.
    Also queues additional pagination pages if found.
    """
    from ecom_arb.db.base import async_session_maker

    async with async_session_maker() as db:
        try:
            # Get the queue item
            result = await db.execute(
                select(CrawlQueue).where(CrawlQueue.id == queue_item_id)
            )
            queue_item = result.scalar_one_or_none()

            if not queue_item:
                logger.warning(f"Queue item {queue_item_id} not found")
                return

            # Parse search results
            search_data = await parse_cj_search_results(html_url)
            product_urls = search_data.product_urls
            total_pages = search_data.total_pages

            # Get job config
            job_result = await db.execute(select(CrawlJob).where(CrawlJob.id == job_id))
            job = job_result.scalar_one_or_none()

            if not job or job.status == CrawlJobStatus.CANCELLED:
                queue_item.status = CrawlQueueStatus.FAILED
                queue_item.error_message = "Job cancelled or not found"
                await db.commit()
                return

            keyword = queue_item.keyword or "unknown"

            logger.info(f"Job {job_id}: Found {len(product_urls)} products in '{keyword}' (total pages: {total_pages})")
            await _add_job_log(
                job_id, "info",
                f"Search '{keyword}': {len(product_urls)} products found (total pages: {total_pages})",
                db
            )

            # Mark this queue item as completed
            queue_item.status = CrawlQueueStatus.COMPLETED
            queue_item.completed_at = datetime.utcnow()

            await _log_crawl_event(
                job_id, "parse_ok", db,
                queue_item_id=queue_item_id,
                url=queue_item.url,
                keyword=keyword,
                details={"products_found": len(product_urls), "total_pages": total_pages},
            )

            # If this is a search (not pagination) and there are more pages, queue pagination
            if queue_item.url_type == CrawlQueueUrlType.SEARCH and total_pages > 1:
                pages_to_queue = min(total_pages, 10)  # Cap at 10 pages
                pagination_queued = 0

                for page in range(2, pages_to_queue + 1):
                    page_url = generate_search_url(keyword, page)
                    await _add_to_queue(
                        job_id=job_id,
                        url=page_url,
                        url_type=CrawlQueueUrlType.PAGINATION,
                        keyword=keyword,
                        db=db,
                        priority=1,  # High priority for pagination
                    )
                    pagination_queued += 1

                if pagination_queued > 0:
                    await _add_job_log(job_id, "info", f"Queued {pagination_queued} additional pages for '{keyword}'", db)

            # Filter out already-existing products
            new_urls, skipped = await _filter_new_product_urls(product_urls, db)
            logger.info(f"Job {job_id}: {len(new_urls)} new URLs ({skipped} skipped - already in DB)")
            if skipped > 0:
                await _add_job_log(job_id, "info", f"Skipped {skipped} existing products", db)

            # Add new product URLs to queue (priority 2 for products)
            products_queued = 0
            for url in new_urls:
                await _add_to_queue(
                    job_id=job_id,
                    url=url,
                    url_type=CrawlQueueUrlType.PRODUCT,
                    keyword=keyword,
                    db=db,
                    priority=2,
                )
                products_queued += 1

            if products_queued > 0:
                await _add_job_log(job_id, "info", f"Queued {products_queued} products for fetching", db)

            await db.commit()

            # Check if we should start submissions (threshold met or search completed)
            pending_count = await _get_pending_count(job_id, db)
            if pending_count > 0:
                # Start or continue the submission chain
                delay = random.uniform(SUBMISSION_DELAY_MIN, SUBMISSION_DELAY_MAX)
                asyncio.create_task(_submit_next_from_queue(job_id, delay=delay))

            # Check if job is complete
            await _check_queue_completion(job_id, db)

        except CJParserError as e:
            logger.error(f"Job {job_id}: Search parse error: {e}")
            async with async_session_maker() as db:
                queue_result = await db.execute(
                    select(CrawlQueue).where(CrawlQueue.id == queue_item_id)
                )
                queue_item = queue_result.scalar_one_or_none()
                if queue_item:
                    await _handle_queue_failure(queue_item, str(e), db)
                await _add_job_log(job_id, "error", f"Search parse error: {str(e)[:50]}", db)
                await db.commit()
                # Schedule next
                asyncio.create_task(_submit_next_from_queue(job_id, delay=random.uniform(SUBMISSION_DELAY_MIN, SUBMISSION_DELAY_MAX)))

        except Exception as e:
            logger.exception(f"Job {job_id}: Unexpected error processing search: {e}")
            async with async_session_maker() as db:
                queue_result = await db.execute(
                    select(CrawlQueue).where(CrawlQueue.id == queue_item_id)
                )
                queue_item = queue_result.scalar_one_or_none()
                if queue_item:
                    await _handle_queue_failure(queue_item, str(e), db)
                await db.commit()
                asyncio.create_task(_submit_next_from_queue(job_id, delay=random.uniform(SUBMISSION_DELAY_MIN, SUBMISSION_DELAY_MAX)))


async def _process_product_result_queued(
    job_id: str,
    queue_item_id: str,
    html_url: str,
    original_url: str,
) -> None:
    """Process product page HTML with queue-based workflow.

    Parses product data, applies filters, scores, and stores in database.
    Handles bot detection and saves blocked HTML for debugging.
    """
    from ecom_arb.db.base import async_session_maker
    from ecom_arb.scoring.models import Product as ScoringProduct
    from ecom_arb.scoring.models import ProductCategory
    from ecom_arb.scoring.scorer import score_product

    async with async_session_maker() as db:
        try:
            # Get the queue item
            result = await db.execute(
                select(CrawlQueue).where(CrawlQueue.id == queue_item_id)
            )
            queue_item = result.scalar_one_or_none()

            if not queue_item:
                logger.warning(f"Queue item {queue_item_id} not found")
                return

            # Parse product data
            product_data = await fetch_and_parse_cj_product(html_url)
            logger.info(f"Job {job_id}: Parsed product {product_data.id}: {product_data.name}")

            # Get job config
            job_result = await db.execute(select(CrawlJob).where(CrawlJob.id == job_id))
            job = job_result.scalar_one_or_none()

            if not job or job.status == CrawlJobStatus.CANCELLED:
                queue_item.status = CrawlQueueStatus.FAILED
                queue_item.error_message = "Job cancelled or not found"
                await db.commit()
                return

            config = job.config or {}

            # Safety dedup check
            existing = await db.execute(
                select(ScoredProduct).where(
                    ScoredProduct.source_product_id == product_data.id
                )
            )
            if existing.scalar_one_or_none():
                logger.info(f"Job {job_id}: Product {product_data.id} already exists, skipping")
                queue_item.status = CrawlQueueStatus.COMPLETED
                queue_item.completed_at = datetime.utcnow()
                await db.commit()
                asyncio.create_task(_submit_next_from_queue(job_id, delay=random.uniform(SUBMISSION_DELAY_MIN, SUBMISSION_DELAY_MAX)))
                await _check_queue_completion(job_id, db)
                return

            # Apply filters
            filtered_reason = _apply_crawl_filters(product_data, config)
            if filtered_reason:
                logger.debug(f"Job {job_id}: Product {product_data.id} filtered: {filtered_reason}")
                queue_item.status = CrawlQueueStatus.COMPLETED
                queue_item.completed_at = datetime.utcnow()
                await db.commit()
                asyncio.create_task(_submit_next_from_queue(job_id, delay=random.uniform(SUBMISSION_DELAY_MIN, SUBMISSION_DELAY_MAX)))
                await _check_queue_completion(job_id, db)
                return

            # Create scoring input (same as before)
            sell_price = float(product_data.sell_price_min)
            selling_price = round(sell_price / 0.30, 2)
            selling_price = max(selling_price, 50.0)

            category = _map_category(product_data.categories)

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
                estimated_cpc=0.50,
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
                crawl_job_id=job_id,
                source="cj_crawl",
                source_url=original_url,
                product_cost=Decimal(str(sell_price)),
                shipping_cost=Decimal(str(shipping_cost)),
                selling_price=Decimal(str(selling_price)),
                category=category.value,
                estimated_cpc=Decimal("0.50"),
                monthly_search_volume=1000,  # Default until Google Ads lookup
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

            # Mark queue item as completed
            queue_item.status = CrawlQueueStatus.COMPLETED
            queue_item.completed_at = datetime.utcnow()

            await _log_crawl_event(
                job_id, "parse_ok", db,
                queue_item_id=queue_item_id,
                url=original_url,
                keyword=queue_item.keyword,
                details={
                    "product_id": product_data.id,
                    "passed": score.passed_filters,
                    "margin": float(score.gross_margin),
                },
            )

            await db.commit()
            logger.info(f"Job {job_id}: Scored product {product_data.id} - {score.recommendation}")

            # Log based on result
            short_name = product_data.name[:30] + "..." if len(product_data.name) > 30 else product_data.name
            if score.passed_filters:
                await _add_job_log(job_id, "info", f"✓ PASSED: {short_name} (margin: {score.gross_margin:.1f}%)", db)
            else:
                await _add_job_log(job_id, "warn", f"✗ Rejected: {short_name}", db)

            # Schedule next submission
            asyncio.create_task(_submit_next_from_queue(job_id, delay=random.uniform(SUBMISSION_DELAY_MIN, SUBMISSION_DELAY_MAX)))

            # Check if job is complete
            await _check_queue_completion(job_id, db)

        except ProductRemovedError as e:
            logger.debug(f"Job {job_id}: Product removed from CJ: {original_url}")
            async with async_session_maker() as db:
                queue_result = await db.execute(
                    select(CrawlQueue).where(CrawlQueue.id == queue_item_id)
                )
                queue_item = queue_result.scalar_one_or_none()
                if queue_item:
                    queue_item.status = CrawlQueueStatus.COMPLETED  # Not an error
                    queue_item.completed_at = datetime.utcnow()
                    queue_item.error_message = "Product removed"
                await db.commit()
                asyncio.create_task(_submit_next_from_queue(job_id, delay=random.uniform(SUBMISSION_DELAY_MIN, SUBMISSION_DELAY_MAX)))
                await _check_queue_completion(job_id, db)

        except CJParserError as e:
            logger.error(f"Job {job_id}: Product parse error: {e}")
            async with async_session_maker() as db:
                queue_result = await db.execute(
                    select(CrawlQueue).where(CrawlQueue.id == queue_item_id)
                )
                queue_item = queue_result.scalar_one_or_none()
                if queue_item:
                    # Check if this might be a bot block
                    if "bot" in str(e).lower() or "block" in str(e).lower():
                        # Save HTML for debugging
                        try:
                            from ecom_arb.services.cj_parser import fetch_html
                            html = await fetch_html(html_url)
                            _save_blocked_html(job_id, queue_item_id, html, str(e))
                        except Exception:
                            pass
                    await _handle_queue_failure(queue_item, str(e), db)
                await _add_job_log(job_id, "error", f"Parse error: {str(e)[:50]}", db)
                await db.commit()
                asyncio.create_task(_submit_next_from_queue(job_id, delay=random.uniform(SUBMISSION_DELAY_MIN, SUBMISSION_DELAY_MAX)))

        except Exception as e:
            logger.exception(f"Job {job_id}: Unexpected error processing product: {e}")
            async with async_session_maker() as db:
                queue_result = await db.execute(
                    select(CrawlQueue).where(CrawlQueue.id == queue_item_id)
                )
                queue_item = queue_result.scalar_one_or_none()
                if queue_item:
                    await _handle_queue_failure(queue_item, str(e), db)
                await db.commit()
                asyncio.create_task(_submit_next_from_queue(job_id, delay=random.uniform(SUBMISSION_DELAY_MIN, SUBMISSION_DELAY_MAX)))


# --- Debug Endpoints ---


class CrawlEventResponse(BaseModel):
    """Response for a crawl event."""

    id: str
    job_id: str
    queue_item_id: str | None
    event_type: str
    url: str | None
    keyword: str | None
    details: dict[str, Any]
    created_at: datetime


@router.get("/{job_id}/events", response_model=list[CrawlEventResponse])
async def get_crawl_events(
    job_id: str,
    event_type: str | None = Query(None, description="Filter by event type"),
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
) -> list[CrawlEventResponse]:
    """Get crawl events for debugging."""
    query = select(CrawlEvent).where(CrawlEvent.job_id == job_id)
    if event_type:
        query = query.where(CrawlEvent.event_type == event_type)
    query = query.order_by(desc(CrawlEvent.created_at)).limit(limit)

    result = await db.execute(query)
    events = result.scalars().all()

    return [
        CrawlEventResponse(
            id=e.id,
            job_id=e.job_id,
            queue_item_id=e.queue_item_id,
            event_type=e.event_type,
            url=e.url,
            keyword=e.keyword,
            details=e.details,
            created_at=e.created_at,
        )
        for e in events
    ]


class TimelineEntry(BaseModel):
    """Entry in submission timeline."""

    url: str
    keyword: str | None
    timestamp: datetime
    gap_seconds: float | None


class CrawlTimelineResponse(BaseModel):
    """Response for crawl timeline."""

    timeline: list[TimelineEntry]
    total_submissions: int


@router.get("/{job_id}/timeline", response_model=CrawlTimelineResponse)
async def get_crawl_timeline(
    job_id: str,
    db: AsyncSession = Depends(get_db),
) -> CrawlTimelineResponse:
    """Get submission timeline for pattern analysis."""
    result = await db.execute(
        select(CrawlEvent)
        .where(CrawlEvent.job_id == job_id)
        .where(CrawlEvent.event_type == "submit")
        .order_by(CrawlEvent.created_at)
    )
    submissions = result.scalars().all()

    timeline = []
    for i, event in enumerate(submissions):
        gap = None
        if i > 0:
            gap = (event.created_at - submissions[i - 1].created_at).total_seconds()
        timeline.append(
            TimelineEntry(
                url=event.url or "",
                keyword=event.keyword,
                timestamp=event.created_at,
                gap_seconds=gap,
            )
        )

    return CrawlTimelineResponse(
        timeline=timeline,
        total_submissions=len(timeline),
    )
