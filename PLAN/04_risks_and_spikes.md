# Risks & Spikes

## Top Risks

| ID | Risk | Why It Matters | Likelihood | Impact | Resolution |
|:---|:-----|:---------------|:-----------|:-------|:-----------|
| R1 | Google Ads account suspension | Lose primary traffic channel, business stops | M | H | Spike + compliance protocols |
| R2 | Payment processor freeze | Can't collect money, business stops | M | H | Conservative metrics, backup processor research |
| R3 | Unit economics don't validate | Entire model fails, wasted build effort | M | H | Spike before full build |
| R4 | Multi-source integration complexity | Build time explodes, delays launch | M | M | Start with one source, add incrementally |
| R5 | CPC estimates wildly inaccurate | Scoring model useless, waste ad spend | M | M | Spike + calibration loop |
| R6 | Custom storefront takes too long | Delays validation, burns runway | M | M | Timebox, have fallback |
| R7 | Supplier quality variance | Refunds spike, chargebacks, angry customers | H | M | Sample orders, supplier scoring |
| R8 | Product listing ≠ actual product | Customer complaints, returns, chargebacks | H | M | Sample verification |
| R9 | Scraping breaks frequently | Can't get product data from AliExpress/Temu | H | L | CJ API primary, scraping fallback |
| R10 | Winners get copied quickly | Short profit window per product | H | L | Accept, build for velocity |
| R11 | FTC shipping compliance | Legal risk, fines | L | H | Clear policies, proactive refunds |
| R12 | Seasonality blindsides us | Q4 CPCs spike, margins disappear | M | M | Research, buffer in model |

---

## Critical Risks (Must Address Before Building)

### R1: Google Ads Account Suspension

**Why it matters:** Single point of failure for traffic. Account ban = business stops.

**Risk factors:**
- AI-generated landing pages flagged as "misrepresentation"
- New account with many campaigns looks suspicious
- Policy changes we don't anticipate
- Dropshipping with long ship times flagged

**Mitigation:**
- [ ] Human review of all landing pages before launch
- [ ] Start slow (10-20 products, not 100)
- [ ] Comply strictly with stated policies
- [ ] Build email list from day one (owned channel)
- [ ] Have organic traffic plan as backup (SEO)

**Monitoring:**
- Check account status daily during first month
- Set up alerts for policy warnings
- Track Quality Score per campaign

---

### R2: Payment Processor Freeze

**Why it matters:** Stripe/PayPal can freeze funds with little warning. No payments = no business.

**Risk factors:**
- Chargeback rate > 1%
- Refund rate > 10%
- Sudden volume spike
- Long shipping times (looks like fraud to processor)
- Dropshipping flagged as high-risk

**Mitigation:**
- [ ] Keep chargeback rate < 0.5% (alert at 0.3%)
- [ ] Keep refund rate < 8% (alert at 6%)
- [ ] Scale gradually (max 30% month-over-month)
- [ ] Proactive refunds before chargebacks
- [ ] Research backup processor before needed

**Backup processors to research:**
- Stripe (primary)
- PayPal
- Square
- Braintree
- High-risk: Durango, PayKickstart

---

### R3: Unit Economics Don't Validate

**Why it matters:** If the math doesn't work, nothing else matters. Building before validation wastes effort.

**Risk factors:**
- CVR assumption (1.0%) too optimistic
- CPC estimates too low
- Hidden costs we didn't model
- Trust gap too large to overcome

**Mitigation:**
- SPIKE-001: Validate with minimal test before full build
- Start with manual process to test assumptions
- Have kill criteria defined before spending

---

## High-Likelihood Risks (Accept and Manage)

### R7/R8: Supplier and Product Quality

**Why it matters:** Bad products = refunds, chargebacks, angry customers.

**Reality:** This WILL happen. The question is how often and how we handle it.

**Mitigation:**
- Order samples for any product before scaling past 20 orders/day
- Build supplier scoring that learns from issues
- Liberal refund policy (cheaper than chargebacks)
- Set customer expectations clearly (shipping times, product photos)

---

### R10: Winners Get Copied

**Why it matters:** Profitable products attract competition fast (days, not months).

**Reality:** Accept this. It's the nature of the game.

**Mitigation:**
- Optimize for velocity (find winners fast, extract profit fast)
- Don't over-invest in any single product
- Build systems, not products
- Eventually: private label winners for defensibility

---

## Spikes

### SPIKE-001: Unit Economics Validation (Pre-Build)

**Goal:** Can we find products where the math actually works before building the full system?

**Timebox:** 1 week

**Steps:**
1. Manually find 20 products in January niches (fitness, organization)
2. Get CPC estimates from Google Keyword Planner (manual)
3. Get product costs from CJ Dropshipping (manual)
4. Calculate scores using spreadsheet version of model
5. Check Amazon competition for each (manual)
6. Identify top 5 candidates that pass all filters

**Output:**
- Spreadsheet with 20 products scored
- 5+ products that pass filters with CPC buffer > 1.5x
- OR evidence that finding viable products is harder than expected

**Decision it unlocks:**
- Go/no-go on building full system
- Refinement of scoring thresholds

---

### SPIKE-002: Google Ads API Access

**Goal:** Confirm we can programmatically create campaigns and get Keyword Planner data.

**Timebox:** 4 hours

**Steps:**
1. Set up Google Ads developer account
2. Create test campaign via API
3. Query Keyword Planner for CPC estimates
4. Verify we can pause/modify campaigns
5. Check rate limits and quotas

**Output:**
- Working API connection
- Sample CPC data for test keywords
- Understanding of rate limits
- OR blockers identified

**Decision it unlocks:**
- ADR-005 confirmed (Google Ads API direct)
- ADR-006 confirmed (Keyword Planner for CPC)

---

### SPIKE-003: CJ Dropshipping API

**Goal:** Confirm CJ API provides the data we need for scoring and fulfillment.

**Timebox:** 4 hours

**Steps:**
1. Sign up for CJ Dropshipping account
2. Get API access
3. Query product catalog for test products
4. Verify data available: cost, shipping, images, supplier info
5. Test order creation flow (sandbox if available)

**Output:**
- Working API connection
- Sample product data
- Understanding of catalog size and categories
- OR gaps in data that require workarounds

**Decision it unlocks:**
- ADR-004 confirmed (CJ as primary source)
- REQ-006 feasibility

---

### SPIKE-004: Amazon Product API

**Goal:** Confirm we can get Amazon pricing and Prime status for arbitrage.

**Timebox:** 4 hours

**Steps:**
1. Apply for Amazon Product Advertising API access
2. Query for test products
3. Verify data: price, Prime status, review count, availability
4. Test buy-box winner identification
5. Check rate limits

**Output:**
- Working API connection
- Sample product data
- Understanding of limitations
- OR need for alternative (Keepa, scraping)

**Decision it unlocks:**
- ADR-002 (Amazon as fulfillment source)
- ADR-011 (Amazon competition check)

---

### SPIKE-005: Stripe Integration

**Goal:** Confirm Stripe works for our use case and understand compliance requirements.

**Timebox:** 2 hours

**Steps:**
1. Review Stripe's dropshipping policies
2. Set up test account
3. Create test checkout flow
4. Understand chargeback handling
5. Review reporting/analytics available

**Output:**
- Stripe account ready
- Understanding of compliance requirements
- Chargeback/dispute process documented
- OR concerns that need addressing

**Decision it unlocks:**
- Payment processor choice confirmed
- Compliance requirements for storefront

---

### SPIKE-006: Scoring Model (Python)

**Goal:** Build the scoring engine in Python — this is the core of the system.

**Timebox:** 8 hours

**Steps:**
1. Create Python module for scoring calculations
2. Implement: gross margin, net margin, max CPC, CPC buffer
3. Implement hard filters (reject/pass)
4. Implement point scoring system
5. Write unit tests for all calculations
6. Test with real product data from SPIKE-001

**Output:**
- Working Python scoring module
- Unit tests passing
- CLI to score a product from JSON input
- Validated against hand-calculated examples

**Decision it unlocks:**
- REQ-001 through REQ-005 implemented
- Foundation for rest of system

---

### SPIKE-007: Custom Storefront Feasibility

**Goal:** Estimate build time for FastAPI + Next.js storefront MVP.

**Timebox:** 4 hours

**Steps:**
1. Sketch minimal storefront: product page, cart, checkout
2. List required API endpoints
3. Identify Stripe checkout integration approach
4. Estimate hours for each component
5. Identify libraries/templates that accelerate build

**Output:**
- Component list with hour estimates
- Total estimated build time
- Key libraries identified
- OR recommendation to use Saleor/other if too long

**Decision it unlocks:**
- ADR-001 confirmed or revised
- Timeline for Phase 1

---

## Spike Schedule

| Spike | Priority | Time | Dependency | Do Before |
|-------|----------|------|------------|-----------|
| SPIKE-001 | Critical | 1 week | None | Any building |
| SPIKE-006 | Critical | 8 hrs | SPIKE-001 data | Full system |
| SPIKE-002 | High | 4 hrs | None | Ads integration |
| SPIKE-003 | High | 4 hrs | None | Product data integration |
| SPIKE-004 | Medium | 4 hrs | None | Amazon fulfillment |
| SPIKE-005 | High | 2 hrs | None | Storefront build |
| SPIKE-007 | High | 4 hrs | SPIKE-001 results | Storefront build |

**Recommended order:**
1. SPIKE-001 — Manual product research to validate model assumptions
2. SPIKE-006 — Build scoring engine in Python (uses SPIKE-001 data to test)
3. SPIKE-002 + SPIKE-003 + SPIKE-005 (parallel) — Validate key integrations
4. SPIKE-007 — Confirm storefront build approach
5. SPIKE-004 — Amazon can come later

---

## Risk Register

Track risk status over time:

| Risk | Status | Last Updated | Notes |
|------|--------|--------------|-------|
| R1: Google Ads suspension | Open | - | Monitor after launch |
| R2: Payment processor | Open | - | Research backup |
| R3: Unit economics | **Validated** | Dec 2025 | SPIKE-001 complete — viable products found |
| R4: Integration complexity | Open | - | Start with CJ only |
| R5: CPC accuracy | Open | - | SPIKE-002 will address |
| R6: Build time | Open | - | SPIKE-007 will address |
| R7: Supplier quality | Accepted | - | Manage with scoring |
| R8: Product quality | Accepted | - | Manage with samples |
| R9: Scraping fragility | Accepted | - | CJ primary |
| R10: Competitor copying | Accepted | - | Build for velocity |
| R11: FTC compliance | Open | - | Policies in place |
| R12: Seasonality | Accepted | - | Buffer in model |

---

## Spike Status

| Spike | Status | Notes |
|-------|--------|-------|
| SPIKE-001 | **Complete** | Unit economics validated manually |
| SPIKE-006 | Ready | Next: Build scoring engine |
| SPIKE-002 | Ready | Google Ads API |
| SPIKE-003 | Ready | CJ API |
| SPIKE-004 | Ready | Amazon API |
| SPIKE-005 | Ready | Stripe |
| SPIKE-007 | Ready | Storefront estimate |
