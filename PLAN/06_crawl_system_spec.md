# CJ Dropshipping Crawl System Specification

## Overview

Mass product discovery system using SerpWatch Browser API to scrape CJ Dropshipping at scale, bypassing API rate limits while capturing richer data (retail price suggestions, wholesale tiers).

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              ADMIN UI                                    │
│  ┌────────────────────────────────────────────────────────────────┐     │
│  │  NEW CRAWL CONFIG                                              │     │
│  │  ├─ Keywords: [input tags]                                     │     │
│  │  ├─ Price Range: $[min] - $[max]                              │     │
│  │  ├─ Warehouses: [x] US  [x] CN  [ ] EU                        │     │
│  │  ├─ Categories: [multi-select]                                 │     │
│  │  └─ [Start Crawl]                                             │     │
│  └────────────────────────────────────────────────────────────────┘     │
│  ┌────────────────────────────────────────────────────────────────┐     │
│  │  EXCLUSION LISTS (Persistent)                                  │     │
│  │  ├─ Countries: [DE, FR, UK, ...]                              │     │
│  │  ├─ Categories: [Clothing, ...]                                │     │
│  │  └─ [+ Add Rule]                                               │     │
│  └────────────────────────────────────────────────────────────────┘     │
│  ┌────────────────────────────────────────────────────────────────┐     │
│  │  CRAWL PROGRESS                                                │     │
│  │  Job #abc123 | Running | 1,234 found | 456 scored | 89 passed │     │
│  └────────────────────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           BACKEND API                                    │
│                                                                          │
│  POST /api/crawl/start        - Start new crawl with config             │
│  GET  /api/crawl/{id}         - Get crawl status/progress               │
│  GET  /api/crawl/jobs         - List recent crawl jobs                  │
│  POST /api/crawl/webhook      - Receive SerpWatch postback ◄────────┐   │
│  DELETE /api/crawl/{id}       - Cancel crawl                        │   │
│                                                                      │   │
│  GET  /api/exclusions         - List exclusion rules                 │   │
│  POST /api/exclusions         - Add exclusion rule                   │   │
│  DELETE /api/exclusions/{id}  - Remove exclusion rule                │   │
└──────────────────┬──────────────────────────────────────────────────┘   │
                   │                                                       │
                   ▼                                                       │
┌─────────────────────────────────────────────────────────────────────────┐
│                        SERPWATCH BROWSER API                             │
│                                                                          │
│  POST https://engine.v2.serpwatch.io/api/v2/browser                     │
│  ├─ url: target URL to fetch                                            │
│  ├─ postback_url: our webhook URL                                       │
│  └─ post_id: "crawl-{job_id}-{type}-{index}"                           │
│                                                                          │
│  Queues request → Fetches with browser → Posts HTML to webhook ─────────┘
└─────────────────────────────────────────────────────────────────────────┘
```

## Data Flow

### Phase 1: Search Discovery
```
1. User starts crawl with keywords ["garden tools", "kitchen gadgets"]
2. Backend generates search URLs:
   - https://cjdropshipping.com/search/garden+tools.html
   - https://cjdropshipping.com/search/kitchen+gadgets.html
3. Submit URLs to SerpWatch with post_id="crawl-{job_id}-search-0"
4. SerpWatch fetches pages, posts HTML back to webhook
5. Webhook parses search results, extracts product URLs
6. **DEDUP CHECK**: Skip product URLs where CJ product ID already exists in scored_products
7. Submit NEW product URLs only to SerpWatch for Phase 2
```

### Phase 2: Product Detail Scraping
```
1. Webhook receives product page HTML
2. Decompress Brotli, extract window.productDetailData
3. Parse JSON (fix undefined → null)
4. **DEDUP CHECK**: Skip if source_product_id already in scored_products (safety check)
5. Apply filters (price range, warehouse, categories, exclusions)
6. If passes: score product, store in scored_products table
7. Update crawl job progress
```

## URL Deduplication

**Principle**: Never crawl the same product twice. If a product ID exists in the database, skip it.

### Where Deduplication Happens

1. **Search Results Processing** (Phase 1 → Phase 2)
   - Extract product IDs from search result URLs
   - Query `scored_products` for existing `source_product_id`s
   - Only submit URLs for products NOT in database

2. **Product Page Processing** (safety net)
   - After parsing `productDetailData`, check if `id` exists in database
   - Skip if already exists (handles race conditions)

### Implementation
```python
# In search results processing
async def filter_new_product_urls(product_urls: list[str], db: AsyncSession) -> list[str]:
    """Filter out URLs for products already in database"""
    # Extract product IDs from URLs (e.g., "...-p-2501080655431624400.html" → "2501080655431624400")
    url_to_id = {url: extract_product_id(url) for url in product_urls}
    product_ids = list(url_to_id.values())

    # Query existing products
    result = await db.execute(
        select(ScoredProduct.source_product_id)
        .where(ScoredProduct.source_product_id.in_(product_ids))
    )
    existing_ids = set(row[0] for row in result.fetchall())

    # Return only new URLs
    return [url for url, pid in url_to_id.items() if pid not in existing_ids]

def extract_product_id(url: str) -> str:
    """Extract CJ product ID from URL"""
    # https://cjdropshipping.com/product/name-here-p-2501080655431624400.html
    match = re.search(r'-p-(\d+)\.html', url)
    return match.group(1) if match else None
```

### Progress Tracking
Track skipped products separately:
```json
{
    "products_skipped_existing": 234,  // Already in DB
    "products_skipped_filtered": 56,   // Failed filters
    "products_new_scored": 89          // Actually processed
}
```

### Future: Auto-Update
Later we'll add a separate "refresh" mode that:
- Re-crawls existing products to update prices/inventory
- Uses `updated_at` timestamp to prioritize stale data
- This is NOT part of the initial implementation

## Database Models

### CrawlJob
```sql
CREATE TABLE crawl_jobs (
    id VARCHAR PRIMARY KEY,
    status VARCHAR DEFAULT 'pending',  -- pending, running, completed, failed, cancelled

    -- Configuration (set at start)
    config JSON NOT NULL,
    /* config structure:
    {
        "keywords": ["garden tools", "kitchen"],
        "price_min": 5.0,
        "price_max": 50.0,
        "include_warehouses": ["US", "CN"],
        "exclude_warehouses": [],  -- merged with exclusion_rules
        "include_categories": [],   -- empty = all
        "exclude_categories": []    -- merged with exclusion_rules
    }
    */

    -- Progress tracking
    progress JSON DEFAULT '{}',
    /* progress structure:
    {
        "search_urls_submitted": 5,
        "search_urls_completed": 3,
        "product_urls_found": 1234,
        "product_urls_skipped_existing": 800,   // Already in DB - not submitted
        "product_urls_submitted": 434,          // New products only
        "product_urls_completed": 430,
        "products_parsed": 425,
        "products_skipped_filtered": 56,        // Failed price/warehouse/category filters
        "products_scored": 369,
        "products_passed_scoring": 89,
        "errors": 5
    }
    */

    error_message VARCHAR,

    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW(),
    started_at TIMESTAMP,
    completed_at TIMESTAMP
);
```

### ExclusionRule
```sql
CREATE TABLE exclusion_rules (
    id VARCHAR PRIMARY KEY,
    rule_type VARCHAR NOT NULL,  -- 'country', 'category', 'supplier', 'keyword'
    value VARCHAR NOT NULL,       -- 'DE', 'Clothing', 'BadSupplier123', 'replica'
    reason VARCHAR,               -- optional note
    created_at TIMESTAMP DEFAULT NOW(),

    UNIQUE(rule_type, value)
);
```

### CrawlProduct (optional - for tracking individual URLs)
```sql
CREATE TABLE crawl_products (
    id VARCHAR PRIMARY KEY,
    crawl_job_id VARCHAR REFERENCES crawl_jobs(id),
    url VARCHAR NOT NULL,
    status VARCHAR DEFAULT 'pending',  -- pending, submitted, completed, failed
    cj_product_id VARCHAR,
    error_message VARCHAR,
    created_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP
);
```

## SerpWatch Integration

### Client Configuration
```python
SERPWATCH_API_KEY = "Z55_HNYlHuF08a6YKQPyTJ297jyXAUSdE-Pt0YIfuNr5_1jM"
SERPWATCH_BASE_URL = "https://engine.v2.serpwatch.io/api"
WEBHOOK_BASE_URL = os.getenv("WEBHOOK_BASE_URL", "http://localhost:6025")
```

### Submit URL
```python
async def submit_url(url: str, crawl_job_id: str, url_type: str, index: int):
    """
    Submit URL to SerpWatch Browser API

    Args:
        url: CJ URL to fetch
        crawl_job_id: Our crawl job ID
        url_type: "search" or "product"
        index: URL index for tracking
    """
    post_id = f"crawl-{crawl_job_id}-{url_type}-{index}"

    response = await httpx.post(
        f"{SERPWATCH_BASE_URL}/v2/browser",
        headers={"Authorization": f"Bearer {SERPWATCH_API_KEY}"},
        json={
            "url": url,
            "device": "desktop",
            "postback_url": f"{WEBHOOK_BASE_URL}/api/crawl/webhook",
            "post_id": post_id
        }
    )
    return response.json()
```

### Webhook Payload (from SerpWatch)
```json
{
    "status": "ok",
    "results": [{
        "success": true,
        "url": "https://cjdropshipping.com/product/...",
        "html": "https://serpengine.hel1.your-objectstorage.com/...",
        "post_id": "crawl-abc123-product-42",
        "request_id": "fae98168-..."
    }]
}
```

## HTML Parsing

### Product Page Extraction
```python
import brotli
import json
import httpx

async def parse_cj_product_html(html_url: str) -> dict:
    """
    Fetch and parse CJ product page HTML

    Returns:
        {
            "id": "2501080655431624400",
            "name": "Product Name",
            "sku": "CJYD2264720",
            "sell_price_min": 3.62,
            "sell_price_max": 5.99,
            "weight_min": 210,
            "weight_max": 455,
            "list_count": 169,
            "supplier_id": "...",
            "categories": ["Home Improvement", "Tools"],
            "variants": [
                {
                    "sku": "CJYD226472001AZ",
                    "sell_price": 5.75,
                    "retail_price": 21.91,  # MSRP suggestion
                    "weight": 210,
                    "pack_weight": 230
                }
            ]
        }
    """
    # 1. Fetch HTML
    async with httpx.AsyncClient() as client:
        response = await client.get(html_url)
        html_bytes = response.content

    # 2. Decompress Brotli
    html = brotli.decompress(html_bytes).decode('utf-8')

    # 3. Find productDetailData
    pos = html.find('productDetailData=')
    if pos == -1:
        raise ValueError("productDetailData not found")

    json_start = html.find('{', pos)

    # 4. Extract with balanced braces
    depth = 0
    end = json_start
    for i, c in enumerate(html[json_start:], json_start):
        if c == '{': depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    json_str = html[json_start:end]

    # 5. Fix JavaScript → JSON
    json_str = json_str.replace(':undefined', ':null')
    json_str = json_str.replace(': undefined', ': null')

    # 6. Parse
    data = json.loads(json_str)

    # 7. Transform to our format
    return transform_cj_data(data)
```

### Search Page Extraction
```python
async def parse_cj_search_html(html_url: str) -> list[str]:
    """
    Extract product URLs from CJ search results page

    Returns:
        List of product URLs
    """
    # Similar fetch/decompress logic
    # Extract product links from HTML
    # Return list of product page URLs
```

## API Endpoints

### POST /api/crawl/start
```python
class CrawlConfig(BaseModel):
    keywords: list[str]
    price_min: float = 0
    price_max: float = 1000
    include_warehouses: list[str] = []  # empty = all
    exclude_warehouses: list[str] = []
    include_categories: list[str] = []  # empty = all
    exclude_categories: list[str] = []

@router.post("/start")
async def start_crawl(config: CrawlConfig, db: AsyncSession = Depends(get_db)):
    # 1. Create CrawlJob
    # 2. Merge config exclusions with persistent ExclusionRules
    # 3. Generate search URLs from keywords
    # 4. Submit search URLs to SerpWatch
    # 5. Update job status to "running"
    # 6. Return job ID
```

### POST /api/crawl/webhook
```python
@router.post("/webhook")
async def crawl_webhook(payload: dict, db: AsyncSession = Depends(get_db)):
    # 1. Parse post_id to get job_id, type, index
    # 2. Check if job is still running (not cancelled)
    # 3. Fetch and parse HTML based on type:
    #    - "search": extract product URLs, submit to SerpWatch
    #    - "product": parse product data, filter, score, store
    # 4. Update job progress
    # 5. Check if job is complete (all URLs processed)
    # 6. Return 200 OK (fast response for SerpWatch)
```

### GET /api/crawl/{job_id}
```python
@router.get("/{job_id}")
async def get_crawl_job(job_id: str, db: AsyncSession = Depends(get_db)):
    # Return job with status and progress
```

### GET /api/exclusions
```python
@router.get("/exclusions")
async def list_exclusions(
    rule_type: str = None,  # filter by type
    db: AsyncSession = Depends(get_db)
):
    # Return all exclusion rules, optionally filtered
```

### POST /api/exclusions
```python
class ExclusionRuleCreate(BaseModel):
    rule_type: str  # country, category, supplier, keyword
    value: str
    reason: str = None

@router.post("/exclusions")
async def add_exclusion(rule: ExclusionRuleCreate, db: AsyncSession = Depends(get_db)):
    # Add new exclusion rule
```

## Frontend Components

### CrawlConfigForm
```tsx
// /admin/crawl/page.tsx or component

interface CrawlConfig {
  keywords: string[];
  priceMin: number;
  priceMax: number;
  includeWarehouses: string[];
  excludeWarehouses: string[];
  includeCategories: string[];
  excludeCategories: string[];
}

function CrawlConfigForm({ onSubmit }: { onSubmit: (config: CrawlConfig) => void }) {
  // Keywords input (tags)
  // Price range inputs
  // Warehouse checkboxes
  // Category multi-select
  // Submit button
}
```

### CrawlProgress
```tsx
interface CrawlJob {
  id: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
  progress: {
    searchUrlsSubmitted: number;
    searchUrlsCompleted: number;
    productUrlsFound: number;
    productsScored: number;
    productsPassed: number;
  };
  createdAt: string;
}

function CrawlProgress({ job }: { job: CrawlJob }) {
  // Progress bars
  // Status indicator
  // Timestamps
}
```

### ExclusionManager
```tsx
interface ExclusionRule {
  id: string;
  ruleType: 'country' | 'category' | 'supplier' | 'keyword';
  value: string;
  reason?: string;
}

function ExclusionManager() {
  // List of rules grouped by type
  // Add rule form
  // Delete rule buttons
}
```

## File Structure

```
src/ecom_arb/
├── api/
│   ├── app.py                    # Add crawl router
│   └── routers/
│       ├── crawl.py              # NEW: Crawl endpoints + webhook
│       └── exclusions.py         # NEW: Exclusion rules CRUD
├── integrations/
│   └── serpwatch.py              # NEW: SerpWatch API client
├── services/
│   └── cj_parser.py              # NEW: HTML parsing logic
└── models/
    ├── crawl_job.py              # NEW: CrawlJob model
    └── exclusion_rule.py         # NEW: ExclusionRule model

frontend/src/
├── app/admin/
│   ├── page.tsx                  # Existing - add link to crawl
│   └── crawl/
│       └── page.tsx              # NEW: Crawl management page
└── lib/
    └── api.ts                    # Add crawl API functions
```

## Environment Variables

```bash
# Add to .env
WEBHOOK_BASE_URL=http://localhost:6025  # Or ngrok URL for local dev
SERPWATCH_API_KEY=Z55_HNYlHuF08a6YKQPyTJ297jyXAUSdE-Pt0YIfuNr5_1jM
```

## Testing Considerations

### Local Development
- Need public URL for SerpWatch postback (ngrok or similar)
- Or mock SerpWatch responses for unit tests

### Webhook Testing
```bash
# Test webhook locally with sample payload
curl -X POST http://localhost:6025/api/crawl/webhook \
  -H "Content-Type: application/json" \
  -d '{"status":"ok","results":[{"success":true,"html":"...","post_id":"crawl-test-product-0"}]}'
```

## Future Enhancements

1. **Auto-scheduling**: Cron-based crawls for new arrivals
2. **Distributed workers**: Multiple webhook processors
3. **Rate limiting**: Control submission rate to SerpWatch
4. **Resume capability**: Restart failed crawls from checkpoint
5. **Duplicate detection**: Skip already-crawled products
6. **Search pagination**: Crawl multiple pages of search results
