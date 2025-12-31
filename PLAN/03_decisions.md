# Decisions (ADRs)

Architecture Decision Records for the E-commerce Arbitrage System.

---

## ADR-001: Store Platform

**Status:** accepted
**Date:** December 2025

### Context
Need an e-commerce platform to host product pages, process payments, and manage orders. Must be open-source and Python-native for integration with scoring engine and automation services.

### Options

| Option | Summary | Pros | Cons |
|:-------|:--------|:-----|:-----|
| Shopify | Hosted e-commerce platform | Battle-tested, app ecosystem | Closed, fees, can't integrate with Python backend |
| Saleor | Python/Django headless commerce | Open-source, Python-native, GraphQL API, headless | Learning curve, may be overkill |
| Shuup | Python/Django e-commerce | Open-source, Python, customizable | Smaller community |
| Custom (FastAPI + Next.js) | Build storefront from scratch | Full control, exact fit, Python backend | More upfront work, payment integration |

### Decision
**Custom storefront: FastAPI backend + Next.js frontend**

### Rationale
- Full control over product pages, checkout flow, and data
- Python backend integrates directly with scoring engine, fulfillment automation
- Next.js provides modern, fast storefront
- Avoids platform fees and limitations
- Can integrate any payment processor (Stripe)
- Headless architecture scales well

### Consequences
- Must build: product pages, cart, checkout, order management
- Must handle payment integration (Stripe)
- Must implement Google Ads conversion tracking
- More upfront development, but no platform lock-in

### Reversal Triggers
- Build time exceeds 4 weeks for basic storefront
- Payment/compliance complexity becomes overwhelming
- Find an open-source solution that fits better

---

## ADR-002: Fulfillment Integration

**Status:** accepted
**Date:** December 2025

### Context
Need to automatically route orders to multiple fulfillment sources. This is true arbitrage — buy from wherever is cheapest/fastest, sell on our storefront.

### Options

| Option | Summary | Pros | Cons |
|:-------|:--------|:-----|:-----|
| Single source (AliExpress) | Traditional dropshipping | Simple | Limited selection, slow shipping |
| Multi-source custom | Build integrations to multiple platforms | Maximum flexibility, true arbitrage | More complex, multiple APIs |
| Third-party aggregator | AutoDS, Spocket, etc. | Pre-built integrations | Fees, less control, may not cover all sources |

### Decision
**Custom multi-source fulfillment system**

### Fulfillment Sources (Priority Order)
| Source | Use Case | API/Method |
|--------|----------|------------|
| Amazon | Fast US shipping, Prime arbitrage | Amazon Product API + automation |
| CJ Dropshipping | US warehouse, good margins | CJ API |
| AliExpress | Largest catalog, lowest cost | API or scraping |
| Temu | Emerging, competitive pricing | API or scraping |
| eBay | Specific items, competitive | eBay API |

### Rationale
- True arbitrage requires flexibility on fulfillment source
- Same product might be cheaper on Amazon vs AliExpress depending on day
- US-based sources (Amazon) enable faster shipping = higher CVR
- Custom system integrates with our Python backend
- Can optimize per-order: cheapest source that meets shipping requirement

### Consequences
- Must build integrations to each platform
- Must handle different order flows per source
- Must track which source fulfilled which order
- More complexity, but more margin opportunity

### Reversal Triggers
- Integration complexity blocks progress
- Single source proves sufficient
- Find aggregator that covers all sources well

---

## ADR-003: Backend Architecture

**Status:** accepted
**Date:** December 2025

### Context
Need a backend that handles: scoring engine, fulfillment automation, Google Ads integration, order management, and API for Next.js frontend.

### Options

| Option | Summary | Pros | Cons |
|:-------|:--------|:-----|:-----|
| FastAPI | Modern Python async framework | Fast, async, great docs, Python ecosystem | Need to learn FastAPI patterns |
| Django | Full-featured Python framework | Batteries included, ORM, admin | Heavier, more opinionated |
| Flask | Lightweight Python framework | Simple, flexible | Less structure, manual setup |
| Node.js (Express/Fastify) | JavaScript backend | Same language as Next.js | Weaker data/scraping ecosystem |

### Decision
**FastAPI**

### Rationale
- Async-native — handles concurrent API calls well (Google Ads, multiple suppliers)
- Modern Python with type hints — cleaner code, better IDE support
- Best-in-class documentation
- Natural fit for data processing, LLM integration, scraping
- Easy to expose REST API for Next.js frontend
- Lighter than Django for our use case

### Architecture
```
┌─────────────────────────────────────────────────────┐
│                   Next.js Frontend                   │
│         (Storefront + Admin Dashboard)               │
└─────────────────────┬───────────────────────────────┘
                      │ REST API
┌─────────────────────▼───────────────────────────────┐
│                   FastAPI Backend                    │
├─────────────────────────────────────────────────────┤
│  Scoring Engine │ Fulfillment │ Ads │ Orders │ CS   │
└─────────────────────┬───────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────┐
│                    PostgreSQL                        │
└─────────────────────────────────────────────────────┘
```

### Consequences
- Two languages (Python + TypeScript) but clean separation
- FastAPI serves API, Next.js handles all UI
- Need to design API contract between frontend and backend

### Reversal Triggers
- FastAPI becomes bottleneck
- Team strongly prefers different framework

---

## ADR-004: Product Data Sources

**Status:** accepted
**Date:** December 2025

### Context
Need to retrieve product data (cost, shipping, supplier info, images) from multiple sources for scoring and arbitrage. Must support price comparison across platforms.

### Options

| Option | Summary | Pros | Cons |
|:-------|:--------|:-----|:-----|
| Single source | Just AliExpress or CJ | Simple | Misses arbitrage opportunities |
| Multi-source APIs | Integrate all platform APIs | Best data, legitimate | Complex, multiple integrations |
| Third-party aggregators | Sell The Trend, etc. | Pre-built | Fees, limited sources |

### Decision
**Multi-source product data with custom integrations**

### Data Sources
| Source | API/Method | Data Available |
|--------|------------|----------------|
| Amazon | Product Advertising API | Price, Prime status, reviews, shipping |
| CJ Dropshipping | CJ API | Price, cost, US warehouse, shipping time |
| AliExpress | Affiliate API + scraping | Price, cost, seller rating, shipping |
| Temu | Scraping (no public API) | Price, shipping |
| eBay | Browse API | Price, seller rating, shipping |

### Rationale
- True arbitrage requires real-time price comparison
- Same product might be $15 on AliExpress, $22 on Amazon with Prime shipping
- System can choose optimal source per order based on margin vs shipping speed
- Build source integrations as needed, not all at once

### Priority Order
1. **CJ Dropshipping** — Clean API, US warehouse, start here
2. **Amazon** — Fast shipping, good for high-CVR products
3. **AliExpress** — Largest catalog, lowest cost
4. **eBay/Temu** — Additional sources as needed

### Consequences
- Multiple API integrations to build and maintain
- Need to normalize product data across sources
- Price monitoring for same product across platforms
- More complexity, but more margin opportunity

### Reversal Triggers
- Single source proves sufficient
- Integration complexity blocks progress
- Find aggregator that covers all sources

---

## ADR-005: Google Ads Integration

**Status:** accepted
**Date:** December 2025

### Context
Need to create campaigns, set bids, monitor performance, and pause/scale automatically.

### Options

| Option | Summary | Pros | Cons |
|:-------|:--------|:-----|:-----|
| Google Ads API | Direct API access | Full control, free, real-time | Complex API, learning curve, quota management |
| Third-party tools | AdEspresso, Optmyzr, etc. | Easier UI, some automation | Monthly fees, less control, may not support our logic |
| Manual + scripts | Manual campaign creation, API for monitoring | Simpler start | Doesn't scale, human bottleneck |

### Decision
**Google Ads API (direct)**

### Rationale
- Full control over bidding strategy (Manual CPC with our calculated max)
- Can implement exact kill/scale logic from requirements
- No monthly fees beyond ad spend
- Automation is core to the business model

### Consequences
- Need to learn Google Ads API
- Need to handle API quotas and rate limits
- More upfront development time

### Reversal Triggers
- API complexity blocks progress for >2 weeks
- Find a tool that implements our exact logic cheaper

---

## ADR-006: CPC Estimation Source

**Status:** accepted
**Date:** December 2025

### Context
Need estimated CPC before launching campaigns to calculate max bid and filter products.

### Options

| Option | Summary | Pros | Cons |
|:-------|:--------|:-----|:-----|
| Google Keyword Planner API | Official Google tool | Direct from source, free with Ads account | Requires active Ads account, estimates can be rough |
| SEMrush/Ahrefs API | Third-party SEO tools | More data (volume, trends, competition) | $100-400/mo, may not match actual Google CPCs |
| Test spend | Actually run small campaigns | Real data | Costs money, slow |
| Skip estimation | Just bid low and see | Simple | No filtering, waste spend on bad products |

### Decision
**Google Keyword Planner API with 1.3x multiplier**

### Rationale
- Free (already need Google Ads account)
- Direct from Google — most aligned with actual auction
- Apply 1.3x multiplier to account for new account penalty
- Good enough for filtering; real CPC calibrates the model

### Consequences
- Estimates will be rough — need to update model with actual CPC data
- Need to handle Keyword Planner API quota limits

### Reversal Triggers
- Keyword Planner estimates consistently wrong by >2x
- Find better data source that's cost-effective

---

## ADR-007: Database

**Status:** accepted
**Date:** December 2025

### Context
Need to store product data, scores, campaign performance, supplier scores, orders, and customer data. Must support FastAPI backend and Next.js frontend accessing same data.

### Options

| Option | Summary | Pros | Cons |
|:-------|:--------|:-----|:-----|
| SQLite | File-based SQL database | Zero setup, portable | No concurrent access, not for web apps |
| PostgreSQL | Production SQL database | Robust, scalable, great ecosystem | Setup overhead |
| Supabase | Hosted Postgres + extras | Easy setup, free tier, auth built-in | Another service to manage |
| PlanetScale | Hosted MySQL | Serverless, branching | MySQL not Postgres |

### Decision
**PostgreSQL (self-hosted on Hetzner)**

### Rationale
- PostgreSQL is the standard for production Python web apps
- FastAPI + SQLAlchemy/asyncpg work great with Postgres
- Self-hosted on Hetzner VPS — no additional cost
- Concurrent access needed (background jobs + web requests)
- JSON columns for flexible product data
- Full control over configuration and backups

### Schema Domains
| Domain | Tables |
|--------|--------|
| Products | products, product_scores, product_sources |
| Suppliers | suppliers, supplier_scores, supplier_issues |
| Campaigns | campaigns, campaign_metrics, keywords |
| Orders | orders, order_items, fulfillments, tracking |
| Customers | customers, inquiries, refunds |

### Consequences
- Must set up Postgres locally for development and on Hetzner for production
- Must manage migrations (Alembic)
- Must handle backups (pg_dump + Hetzner snapshots)
- Full control over database configuration

### Reversal Triggers
- Database management becomes burden
- Need managed database features (auto-scaling, replicas)

---

## ADR-008: LLM Provider

**Status:** accepted
**Date:** December 2025

### Context
Need LLM for: keyword generation, product descriptions, ad copy, customer service classification/responses.

### Options

| Option | Summary | Pros | Cons |
|:-------|:--------|:-----|:-----|
| OpenAI (GPT-4o/4o-mini) | Industry standard | Great quality, fast, good APIs | Cost at scale, rate limits |
| Anthropic (Claude) | Alternative to OpenAI | Strong reasoning, longer context | Similar cost, fewer integrations |
| Local (Ollama/llama.cpp) | Self-hosted models | Free, private, no rate limits | Lower quality, setup complexity, hardware needs |

### Decision
**OpenAI GPT-4o-mini for most tasks, GPT-4o for complex tasks**

### Rationale
- GPT-4o-mini is cheap (~$0.15/1M input tokens) and good enough for classification, descriptions
- GPT-4o for complex reasoning if needed (keyword strategy, edge cases)
- Best-in-class API reliability and documentation
- Easy to switch providers later — abstraction layer in code

### Consequences
- Ongoing API cost (estimate: $20-100/month depending on volume)
- Dependent on OpenAI availability
- Need to handle rate limits

### Reversal Triggers
- OpenAI costs exceed $500/month
- Quality issues with generated content
- Need features only available elsewhere

---

## ADR-009: Hosting/Infrastructure

**Status:** accepted
**Date:** December 2025

### Context
Need to host: FastAPI backend, Next.js frontend (storefront + admin), PostgreSQL database, and background jobs (campaign monitoring, fulfillment).

### Options

| Option | Summary | Pros | Cons |
|:-------|:--------|:-----|:-----|
| Vercel + Railway | PaaS for each | Easy deploy, managed | Higher cost, less control |
| DigitalOcean | Popular VPS | Good docs, simple | More expensive than alternatives |
| Hetzner | German VPS provider | Excellent price/performance, reliable | EU-based (latency to US), self-managed |
| AWS/GCP | Full cloud stack | Scalable, enterprise | Complex, expensive |

### Decision
**Hetzner VPS**

### Rationale
- Best price/performance ratio in the industry
- Full control over the stack
- Can run everything on one server initially (simpler)
- Docker Compose for local dev parity
- Easy to scale up server size or add more
- No vendor lock-in

### Server Specs (Starting Point)
| Spec | Value | Cost |
|------|-------|------|
| Type | CPX21 (or similar) | ~€8-15/mo |
| vCPU | 3 cores | |
| RAM | 4-8 GB | |
| Storage | 80-160 GB NVMe | |
| Location | US East (Ashburn) or EU | |

### Architecture
```
┌─────────────────────────────────────────────────┐
│                 Hetzner VPS                      │
├─────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐              │
│  │   Nginx     │  │  Postgres   │              │
│  │  (reverse   │  │             │              │
│  │   proxy)    │  └─────────────┘              │
│  └──────┬──────┘                               │
│         │                                       │
│  ┌──────▼──────┐  ┌─────────────┐              │
│  │   Next.js   │  │   FastAPI   │              │
│  │  (frontend) │  │  (backend)  │              │
│  └─────────────┘  └─────────────┘              │
│                                                 │
│  ┌─────────────────────────────────┐           │
│  │     Background Workers          │           │
│  │  (Campaign monitor, Fulfillment)│           │
│  └─────────────────────────────────┘           │
└─────────────────────────────────────────────────┘
```

### Deployment Stack
| Component | Tool |
|-----------|------|
| Containerization | Docker + Docker Compose |
| Reverse proxy | Nginx or Caddy (auto SSL) |
| Process manager | Docker Compose or systemd |
| CI/CD | GitHub Actions → SSH deploy |
| SSL | Let's Encrypt (via Caddy) |
| Backups | Hetzner snapshots + pg_dump |

### Costs (Estimated)
| Item | Cost |
|------|------|
| VPS (CPX21) | ~€10/mo (~$11) |
| Backups | ~€2/mo |
| Domain | ~$12/year |
| **Total** | **~$15/mo** |

### Consequences
- Must manage server (updates, security, monitoring)
- Single point of failure initially (can add redundancy later)
- Need to set up deployment pipeline
- Full control and visibility

### Reversal Triggers
- Server management becomes burden
- Need global CDN for frontend performance
- Scaling requires more than vertical growth

---

## ADR-010: Admin Dashboard

**Status:** accepted
**Date:** December 2025

### Context
Need visibility into unit economics, campaign performance, health metrics, and operational controls. Part of the Next.js frontend.

### Options

| Option | Summary | Pros | Cons |
|:-------|:--------|:-----|:-----|
| Spreadsheet | Google Sheets pulling from APIs | Quick to start | Manual, doesn't scale, no controls |
| Streamlit | Python dashboard | Fast to build, Python-native | Separate app, limited UI |
| Next.js custom | Build into main frontend | Unified codebase, full control, real-time | More upfront work |
| Retool/Airplane | Low-code admin tools | Fast to build | Monthly fees, less control |

### Decision
**Custom Next.js admin dashboard (part of main frontend)**

### Rationale
- Already building Next.js frontend for storefront
- Admin dashboard is same codebase, shared components
- Full control over UI/UX
- Real-time updates via API
- No additional tools or costs
- Can evolve with the business

### Dashboard Sections
| Section | Purpose |
|---------|---------|
| Overview | Revenue, margin, orders today/week/month |
| Products | Scores, status, performance, actions |
| Campaigns | Google Ads metrics, kill/scale controls |
| Orders | Fulfillment status, issues, tracking |
| Suppliers | Scores, issues, inventory |
| Health | Refund rate, chargebacks, shipping times, alerts |

### Consequences
- Frontend and backend share same data model
- Need to design dashboard UI (can use shadcn/ui, Tremor)
- More initial build time, but better long-term

### Reversal Triggers
- Dashboard build takes >2 weeks
- Find low-code tool that fits perfectly

---

## ADR-011: Amazon Competition Check

**Status:** proposed
**Date:** December 2025

### Context
Need to check if products have strong Amazon Prime competitors (500+ reviews) before testing.

### Options

| Option | Summary | Pros | Cons |
|:-------|:--------|:-----|:-----|
| Amazon Product API | Official API | Legitimate, stable | Requires affiliate account, limited access |
| Scraping | Web scraping Amazon | Full data access | Against ToS, anti-bot measures, fragile |
| Keepa/Jungle Scout API | Third-party Amazon data | Clean API, historical data | $20-50/mo |
| Manual check | Human looks at Amazon | Accurate | Doesn't scale, slow |

### Decision
**Manual check for MVP, Keepa API when volume justifies**

### Rationale
- At 50-100 products/week, manual check is ~1 hour work
- Avoids scraping complexity and ToS issues
- Keepa is the cleanest API option when ready to automate
- Not worth $40/mo until model is validated

### Consequences
- Human in the loop for Amazon check
- Part of the "manual review gate" before ad launch
- Scale-limited initially

### Reversal Triggers
- Processing >200 products/week
- Manual check becomes bottleneck
- Ready to invest $40/mo in tooling

---

# Decision Summary

| ADR | Decision | Status |
|-----|----------|--------|
| 001 | Custom storefront: FastAPI + Next.js | Accepted |
| 002 | Multi-source fulfillment (Amazon, CJ, AliExpress, Temu, eBay) | Accepted |
| 003 | FastAPI backend architecture | Accepted |
| 004 | Multi-source product data | Accepted |
| 005 | Google Ads API direct | Accepted |
| 006 | Google Keyword Planner API + 1.3x multiplier | Accepted |
| 007 | PostgreSQL | Accepted |
| 008 | OpenAI GPT-4o-mini / GPT-4o | Accepted |
| 009 | Hetzner VPS (Docker Compose) | Accepted |
| 010 | Custom Next.js admin dashboard | Accepted |
| 011 | Manual Amazon check for MVP, Keepa later | Proposed |

# Tech Stack Summary

```
Frontend:     Next.js (TypeScript)
Backend:      FastAPI (Python)
Database:     PostgreSQL
Hosting:      Hetzner VPS + Docker Compose
LLM:          OpenAI GPT-4o-mini
Payments:     Stripe
Fulfillment:  Multi-source (Amazon, CJ, AliExpress, Temu, eBay)
Ads:          Google Ads API
Deploy:       GitHub Actions → SSH
```
