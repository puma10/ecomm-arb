# Crawl Queue Architecture Design

**Date:** 2026-01-02
**Status:** Approved
**Purpose:** Redesign CJ crawl system to be more resilient to anti-bot detection

## Problem Statement

Current crawl flow is predictable and easily detectable:
1. Submit search URL
2. Immediately submit all pagination pages (burst)
3. Immediately submit all product URLs (burst)

This pattern triggers anti-bot systems. We need a queue-based architecture with delays, shuffling, and retry logic.

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Queue storage | Database table | Persistent, survives restarts, easy to inspect |
| Processing model | Webhook-driven + delayed background tasks | Self-regulating, no separate worker process |
| Delay between submissions | 5-15 seconds (random) | Stealthy, ~17 min for 100 products |
| Retry strategy | Jittered exponential, 15min base, max 3 | Long cooldown for bot blocks |
| Interleaving | Shuffle all URLs, wait for ≥15 before starting | Mixes sources, less predictable |
| Priority | Pagination > Products | Keeps discovery funnel fed |
| Job completion | All URLs processed or max-retried | Accurate stats |
| Pagination handling | Queued alongside products | Natural browsing pattern |

## Database Schema

```sql
CREATE TABLE crawl_queue (
    id              TEXT PRIMARY KEY,        -- UUID
    job_id          TEXT NOT NULL,           -- FK to crawl_jobs
    url             TEXT NOT NULL,           -- URL to fetch
    url_type        TEXT NOT NULL,           -- 'search', 'pagination', 'product'
    keyword         TEXT,                    -- Source keyword (for tracking)
    priority        INTEGER DEFAULT 2,       -- 1=pagination, 2=product
    status          TEXT DEFAULT 'pending',  -- pending, submitted, completed, failed
    retry_count     INTEGER DEFAULT 0,
    next_attempt_at TIMESTAMP,               -- NULL = ready now
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    submitted_at    TIMESTAMP,               -- When sent to SerpWatch
    completed_at    TIMESTAMP,
    error_message   TEXT,                    -- Last error if failed

    FOREIGN KEY (job_id) REFERENCES crawl_jobs(id)
);

CREATE INDEX idx_queue_ready ON crawl_queue(job_id, status, next_attempt_at);
CREATE INDEX idx_queue_job_status ON crawl_queue(job_id, status);
```

### Status Transitions

```
pending → submitted    (sent to SerpWatch)
submitted → completed  (webhook received, parsed OK)
submitted → pending    (failed, retry scheduled with next_attempt_at)
pending → failed       (max retries exceeded)
```

## Queue Processing Flow

### 1. Job Startup

```python
async def start_crawl(keywords):
    job = create_job()

    # Add search URLs to queue
    for keyword in keywords:
        add_to_queue(
            job_id=job.id,
            url=generate_search_url(keyword, page=1),
            url_type='search',
            keyword=keyword,
            priority=1  # Same as pagination
        )

    # Kickstart: submit first URL immediately
    await _submit_next_from_queue(job.id, delay=0)

    return job
```

### 2. Webhook Processing

```python
async def handle_webhook(result):
    # 1. Find and update queue item
    queue_item = find_queue_item(result.post_id)

    if result.success:
        queue_item.status = 'completed'
        queue_item.completed_at = now()

        # 2. Parse and add discovered URLs
        if queue_item.url_type in ('search', 'pagination'):
            data = parse_search_results(result.html)

            # Add pagination URLs (priority=1)
            for page_url in data.pagination_urls:
                add_to_queue(
                    job_id=queue_item.job_id,
                    url=page_url,
                    url_type='pagination',
                    keyword=queue_item.keyword,
                    priority=1
                )

            # Add product URLs (priority=2)
            for product_url in data.product_urls:
                add_to_queue(
                    job_id=queue_item.job_id,
                    url=product_url,
                    url_type='product',
                    keyword=queue_item.keyword,
                    priority=2
                )

        elif queue_item.url_type == 'product':
            # Parse and score product
            parse_and_score_product(result.html)

    else:
        # Handle failure
        await handle_queue_failure(queue_item, result.error)

    # 3. Check queue threshold and schedule next submission
    pending_count = count_pending(queue_item.job_id)
    if pending_count >= 15 or queue_item.url_type == 'search':
        delay = random.uniform(5, 15)
        schedule_background_task(_submit_next_from_queue, queue_item.job_id, delay)

    # 4. Check job completion
    check_job_completion(queue_item.job_id)
```

### 3. Queue Submission

```python
async def _submit_next_from_queue(job_id: str, delay: float):
    # Wait for delay
    await asyncio.sleep(delay)

    # Get next ready URL (pagination priority, then random)
    queue_item = db.query("""
        SELECT * FROM crawl_queue
        WHERE job_id = :job_id
          AND status = 'pending'
          AND (next_attempt_at IS NULL OR next_attempt_at <= :now)
        ORDER BY priority ASC, RANDOM()
        LIMIT 1
    """, job_id=job_id, now=now())

    if not queue_item:
        return  # Queue empty or all items waiting for retry

    # Submit to SerpWatch
    try:
        await submit_url(queue_item.url, job_id, queue_item.url_type, queue_item.id)
        queue_item.status = 'submitted'
        queue_item.submitted_at = now()
    except SerpWatchError as e:
        await handle_queue_failure(queue_item, str(e))

    # Schedule next submission if more pending
    pending_count = count_pending(job_id)
    if pending_count > 0:
        next_delay = random.uniform(5, 15)
        schedule_background_task(_submit_next_from_queue, job_id, next_delay)
```

## Retry Logic

```python
async def handle_queue_failure(queue_item, error_message: str):
    queue_item.retry_count += 1
    queue_item.error_message = error_message

    if queue_item.retry_count > 3:
        # Max retries exceeded - give up
        queue_item.status = 'failed'
        queue_item.completed_at = now()
        logger.warning(f"Queue item {queue_item.id} failed after 3 retries: {error_message}")
    else:
        # Schedule retry with jittered exponential backoff
        base_delay = 15 * 60  # 15 minutes
        jitter = random.uniform(0, 5 * 60)  # 0-5 minutes
        delay_seconds = base_delay * (2 ** (queue_item.retry_count - 1)) + jitter

        queue_item.status = 'pending'
        queue_item.next_attempt_at = now() + timedelta(seconds=delay_seconds)

        logger.info(f"Queue item {queue_item.id} retry {queue_item.retry_count}, "
                   f"next attempt in {delay_seconds/60:.1f} minutes")
```

### Retry Timeline

| Retry | Base Delay | Jitter | Total Wait |
|-------|------------|--------|------------|
| 1 | 15 min | 0-5 min | ~15-20 min |
| 2 | 30 min | 0-5 min | ~30-35 min |
| 3 | 60 min | 0-5 min | ~60-65 min |
| 4 | - | - | Give up |

Maximum total time before giving up: ~2 hours

## Job Completion

```python
async def check_job_completion(job_id: str):
    stats = db.query("""
        SELECT status, COUNT(*) as count
        FROM crawl_queue
        WHERE job_id = :job_id
        GROUP BY status
    """, job_id=job_id)

    pending = stats.get('pending', 0)
    submitted = stats.get('submitted', 0)

    if pending == 0 and submitted == 0:
        # All items completed or failed
        completed = stats.get('completed', 0)
        failed = stats.get('failed', 0)

        job.status = 'completed'
        job.completed_at = now()
        logger.info(f"Job {job_id} complete: {completed} succeeded, {failed} failed")
```

## Files to Modify

1. **`db/models.py`** - Add `CrawlQueue` SQLAlchemy model
2. **`api/routers/crawl.py`** - Major refactor:
   - `start_crawl()` → queue searches instead of immediate submission
   - `crawl_webhook()` → update queue, add discovered URLs
   - New `_submit_next_from_queue()` background task
   - New `handle_queue_failure()` for retry logic
   - Update `_check_job_completion()` to use queue stats

## Migration Path

1. Add `crawl_queue` table (Alembic migration)
2. Refactor `crawl.py` with queue logic
3. Test with single-keyword crawl
4. Test with multi-keyword crawl
5. Monitor for bot detection issues
6. Tune delay/retry parameters based on results

## Success Metrics

- Reduced bot detection rate (fewer "blocked" errors)
- Jobs complete successfully with partial results on failures
- Retry logic recovers from temporary blocks
- Queue drains predictably without bursts
