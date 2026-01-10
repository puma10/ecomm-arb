# LLM-Based Product Analysis System

## Overview

Replace deterministic regex-based product analysis with LLM-powered semantic understanding for:
1. **Keyword exploration** - Dynamic tree search to find optimal ad keywords
2. **Amazon comparison** - Semantic matching to find truly similar products
3. **Viability scoring** - Holistic product scoring based on margin, keywords, and market

## Problem Statement

### Current Limitations
- Regex-based spec extraction is brittle and misses context
- Fixed keyword lists don't explore the full search space
- Products rejected for "low conversion" on broad keywords might be viable on niche keywords
- Amazon comparison matches by keyword, not by actual product similarity

### Solution
Single LLM call that:
1. Deeply understands what the product IS (type, style, use case, buyer persona)
2. Generates keyword candidates across specificity tiers
3. Scores Amazon products on true similarity
4. Outputs structured data for downstream processing

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         PRODUCT ANALYSIS PIPELINE                        │
└─────────────────────────────────────────────────────────────────────────┘

┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────┐
│   CJ Product │────▶│  LLM Analyze │────▶│   Keyword    │────▶│  Score   │
│   (crawled)  │     │  (Haiku)     │     │   Explorer   │     │  Product │
└──────────────┘     └──────────────┘     └──────────────┘     └──────────┘
                            │                    │
                            ▼                    ▼
                     ┌──────────────┐     ┌──────────────┐
                     │   Amazon     │     │  Google Ads  │
                     │   ScraperAPI │     │     API      │
                     └──────────────┘     └──────────────┘
```

### Phase 1: LLM Product Understanding

**Input:**
```json
{
  "name": "Cement Japanese-style Log Silent Corridor Ceiling Lamp",
  "weight_grams": 1500,
  "cost": 12.50,
  "category": "lighting"
}
```

**LLM Prompt:**
```
Analyze this product for e-commerce advertising:

Product: {name}
Weight: {weight}g
Cost: ${cost}
Category: {category}

Return JSON:
{
  "product_understanding": {
    "product_type": "specific type (e.g., ceiling pendant lamp)",
    "style": ["style descriptors"],
    "materials": ["detected materials"],
    "use_cases": ["where/how it's used"],
    "buyer_persona": "who buys this",
    "quality_tier": "budget|mid-range|premium",
    "price_expectation": "$X-Y range buyers expect"
  },
  "seed_keywords": {
    "exact": ["highly specific keywords, 3-5 words"],
    "specific": ["product type keywords, 2-3 words"],
    "broad": ["category keywords, 1-2 words"]
  }
}
```

**Output:**
```json
{
  "product_understanding": {
    "product_type": "ceiling pendant lamp",
    "style": ["japanese minimalist", "wabi-sabi", "rustic modern"],
    "materials": ["cement", "concrete", "wood accents"],
    "use_cases": ["hallway", "corridor", "entryway", "dining room"],
    "buyer_persona": "homeowner seeking aesthetic decorative lighting",
    "quality_tier": "mid-range",
    "price_expectation": "$60-150"
  },
  "seed_keywords": {
    "exact": ["cement pendant lamp japanese style", "concrete ceiling light minimalist"],
    "specific": ["japanese pendant light", "cement hanging lamp", "corridor ceiling lamp"],
    "broad": ["pendant light", "ceiling lamp", "hallway lighting"]
  }
}
```

---

### Phase 2: Keyword Exploration Algorithm

**Goal:** Find the optimal keywords by exploring the search space dynamically.

```python
async def explore_keywords(product, product_understanding, depth=0, max_depth=4):
    """
    Recursively explore keyword space to find optimal ad keywords.

    Returns tree of keywords with volume, CPC, relevance, and profit potential.
    """

    if depth == 0:
        # Start with LLM-generated seed keywords
        keywords = product_understanding["seed_keywords"]["broad"] + \
                   product_understanding["seed_keywords"]["specific"]

    results = []

    for keyword in keywords:
        # 1. Get data from Google Ads API
        ads_data = await google_ads_api.get_keyword_data(keyword)
        # Returns: volume, cpc, competition, related_keywords

        if ads_data.volume < MIN_VOLUME_THRESHOLD:  # e.g., 50/month
            continue  # Dead end - no volume

        # 2. LLM scores relevance to our specific product
        relevance = await llm_score_relevance(keyword, product, product_understanding)
        # Returns: 0-100 score + reasoning

        # 3. Estimate conversion based on specificity + relevance
        word_count = len(keyword.split())
        base_conversion = {1: 0.01, 2: 0.02, 3: 0.04, 4: 0.08, 5: 0.12}.get(word_count, 0.15)
        est_conversion = base_conversion * (relevance / 100)

        # 4. Calculate profit potential
        margin = product.selling_price - product.cost - ads_data.cpc
        profit_potential = ads_data.volume * est_conversion * margin

        results.append({
            "keyword": keyword,
            "volume": ads_data.volume,
            "cpc": ads_data.cpc,
            "competition": ads_data.competition,
            "relevance": relevance,
            "est_conversion": est_conversion,
            "profit_potential": profit_potential,
            "depth": depth,
        })

        # 5. RECURSE on promising branches
        if ads_data.volume > BRANCH_THRESHOLD and depth < max_depth:
            # LLM filters related keywords to only relevant ones
            relevant_related = await llm_filter_related_keywords(
                ads_data.related_keywords,
                product,
                product_understanding
            )

            if relevant_related:
                deeper_results = await explore_keywords(
                    product,
                    product_understanding,
                    keywords=relevant_related,
                    depth=depth + 1
                )
                results.extend(deeper_results)

    return sorted(results, key=lambda x: x["profit_potential"], reverse=True)
```

**Thresholds:**
- `MIN_VOLUME_THRESHOLD`: 50 searches/month (stop exploring dead ends)
- `BRANCH_THRESHOLD`: 1,000 searches/month (worth exploring deeper)
- `max_depth`: 4 levels (prevent infinite exploration)

---

### Phase 3: Amazon Comparison with LLM

**Input:** Product understanding + Amazon search results (50 products)

**LLM Prompt:**
```
You are comparing products to find similar items on Amazon.

Our Product:
- Type: {product_type}
- Style: {style}
- Materials: {materials}
- Quality tier: {quality_tier}
- Expected price: {price_expectation}

Amazon Products:
1. "{title}" - ${price} - {reviews} reviews
2. "{title}" - ${price} - {reviews} reviews
...

For each Amazon product, rate similarity 0-100:
- 90-100: Nearly identical (same type, style, quality)
- 70-89: Very similar (same category, similar features)
- 50-69: Somewhat similar (related but different)
- <50: Different product

Return JSON:
{
  "similar_products": [
    {"index": 2, "score": 92, "reason": "Same cement pendant lamp style"},
    {"index": 5, "score": 78, "reason": "Similar minimalist aesthetic, different material"}
  ]
}
```

**Market Price Calculation:**
```python
def calculate_market_price(similar_products, amazon_data):
    # Filter to 60%+ similarity
    matches = [p for p in similar_products if p["score"] >= 60]

    prices = []
    weights = []

    for match in matches:
        amazon_product = amazon_data[match["index"]]
        price = amazon_product["price"]

        # Weight by similarity and reviews
        weight = (match["score"] / 100) * log10(amazon_product["reviews"] + 1)

        prices.append(price)
        weights.append(weight)

    weighted_median = calculate_weighted_median(prices, weights)

    return {
        "weighted_median": weighted_median,
        "min": min(prices),
        "max": max(prices),
        "sample_size": len(matches),
        "top_matches": matches[:5]
    }
```

---

## Data Models

### ScoredProduct (updated fields)

```python
class ScoredProduct:
    # ... existing fields ...

    # LLM Product Understanding
    product_understanding: JSON = {
        "product_type": str,
        "style": list[str],
        "materials": list[str],
        "use_cases": list[str],
        "buyer_persona": str,
        "quality_tier": str,
        "price_expectation": str,
    }

    # Keyword Analysis (replaces simple keyword_analysis)
    keyword_tree: JSON = {
        "explored_at": datetime,
        "keywords": [
            {
                "keyword": str,
                "volume": int,
                "cpc": float,
                "competition": str,
                "relevance": int,
                "est_conversion": float,
                "profit_potential": float,
                "depth": int,
            }
        ],
        "recommended": list[str],
        "best_keyword": str,
        "total_addressable_volume": int,
    }

    # Amazon Comparison (replaces simple amazon_ fields)
    amazon_analysis: JSON = {
        "analyzed_at": datetime,
        "market_price": {
            "weighted_median": float,
            "min": float,
            "max": float,
            "sample_size": int,
        },
        "similar_products": [
            {
                "title": str,
                "price": float,
                "reviews": int,
                "similarity": int,
                "reason": str,
                "asin": str,
            }
        ],
    }

    # Final Score (computed from above)
    viability_score: int  # 0-100
    viability_reasons: JSON = {
        "pros": list[str],
        "cons": list[str],
        "recommendation": str,
    }
```

---

## API Endpoints

### Analyze Single Product
```
POST /api/admin/analyze-product/{product_id}

Response:
{
  "product_id": "uuid",
  "product_understanding": {...},
  "keyword_tree": {...},
  "amazon_analysis": {...},
  "viability_score": 85,
  "viability_reasons": {...}
}
```

### Analyze Batch (background)
```
POST /api/admin/analyze-products
Body: { "product_ids": [...], "limit": 10 }

Response:
{
  "job_id": "uuid",
  "status": "queued",
  "products_queued": 10
}
```

### Get Analysis Status
```
GET /api/admin/analysis-status/{job_id}

Response:
{
  "job_id": "uuid",
  "status": "processing",
  "completed": 7,
  "total": 10,
  "results": [...]
}
```

---

## UI Pages

### 1. Product Pipeline List (`/admin/products`)

```
┌─────────────────────────────────────────────────────────────────────────┐
│  PRODUCT PIPELINE                              [Analyze All] [Filters]  │
├─────────────────────────────────────────────────────────────────────────┤
│  Status: 42 analyzed, 18 pending                                        │
│                                                                         │
│  ┌─────┬─────────────────────────┬────────┬──────────┬────────┬───────┐│
│  │     │ PRODUCT                 │ MARGIN │ BEST KW  │ MARKET │ SCORE ││
│  ├─────┼─────────────────────────┼────────┼──────────┼────────┼───────┤│
│  │ 🟢  │ Cement Japanese Pendant │  78%   │ 8.1K vol │ $94    │ 92    ││
│  │ 🟢  │ Bluetooth Speaker RGB   │  65%   │ 22K vol  │ $35    │ 88    ││
│  │ 🟡  │ USB Cable Organizer     │  52%   │ 5.2K vol │ $18    │ 65    ││
│  │ 🔴  │ Generic Phone Stand     │  23%   │ 140K vol │ $12    │ 31    ││
│  │ ⏳  │ LED Strip Lights 5M     │  --    │ pending  │ --     │ --    ││
│  └─────┴─────────────────────────┴────────┴──────────┴────────┴───────┘│
└─────────────────────────────────────────────────────────────────────────┘
```

### 2. Product Detail (`/admin/products/[id]`)

See full mockup in conversation above. Key sections:
- Product header with image, cost, market price, margin
- Keyword opportunities table with tree structure
- Amazon comparison with similar products
- Viability reasons (pros/cons)
- Action buttons (Skip, Save, Launch)

---

## Implementation Phases

### Phase 1: LLM Service (2-3 hours)
- [ ] Create `llm_analyzer.py` service
- [ ] Implement product understanding prompt
- [ ] Implement Amazon comparison prompt
- [ ] Implement keyword relevance scoring prompt
- [ ] Add Anthropic API integration (use Haiku for cost)

### Phase 2: Keyword Explorer (2-3 hours)
- [ ] Implement recursive keyword exploration algorithm
- [ ] Integrate with Google Ads API for volume/CPC
- [ ] Add LLM filtering for related keywords
- [ ] Build keyword tree data structure
- [ ] Calculate profit potential for each keyword

### Phase 3: Analysis Pipeline (1-2 hours)
- [ ] Create analysis endpoint that orchestrates:
  1. LLM product understanding
  2. Amazon search + LLM comparison
  3. Keyword exploration
  4. Final scoring
- [ ] Add background job support for batch analysis
- [ ] Update database models

### Phase 4: Frontend - List View (2-3 hours)
- [ ] Update `/admin/products` page
- [ ] Add score column with color coding
- [ ] Add filtering by score, status
- [ ] Add "Analyze" button for pending products
- [ ] Show analysis progress for batch jobs

### Phase 5: Frontend - Detail View (3-4 hours)
- [ ] Create `/admin/products/[id]` page
- [ ] Product header component
- [ ] Keyword tree table component
- [ ] Amazon comparison component
- [ ] Viability reasons component
- [ ] Action buttons

### Phase 6: Campaign Launch (Future)
- [ ] Google Ads campaign creation
- [ ] Product page generation
- [ ] Tracking and analytics

---

## Cost Estimates

### Per Product Analysis
| Component | API Calls | Cost |
|-----------|-----------|------|
| LLM - Product Understanding | 1 Haiku call | $0.0003 |
| LLM - Amazon Comparison | 1 Haiku call | $0.0005 |
| LLM - Keyword Relevance | 3-5 Haiku calls | $0.0015 |
| ScraperAPI - Amazon | 1 call | $0.001 |
| Google Ads API | 5-15 calls | Free (quota) |
| **Total per product** | | **~$0.003** |

### Batch Analysis
| Products | Cost | Time |
|----------|------|------|
| 100 | $0.30 | ~10 min |
| 1,000 | $3.00 | ~2 hours |
| 10,000 | $30.00 | ~20 hours |

---

## Open Questions

1. **Keyword depth** - How deep should we explore? 4 levels seems reasonable but might need tuning.

2. **Relevance threshold** - What similarity score cutoff for Amazon comparison? Starting with 60%.

3. **Caching** - Should we cache keyword data? Google Ads data changes slowly.

4. **Rate limiting** - Need to respect API limits for ScraperAPI and Google Ads.

5. **Refresh frequency** - How often to re-analyze products? Weekly? On-demand only?
