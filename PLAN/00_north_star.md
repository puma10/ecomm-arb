# North Star Card

## The Goal
Build an automated e-commerce arbitrage system that uses math-driven product selection and Google Ads to generate $25-50k/month profit with one person + technology.

## Who It's For
Solo operator (you) seeking a scalable, largely automated income stream that leverages:
- Data-driven product selection
- Automated fulfillment (dropshipping)
- AI for customer service and operations
- Minimal ongoing human intervention once systems are built

## Context
Startup MVP. The model is unproven at your scale. Speed to validation matters more than perfection. Build only what's needed to test the core hypothesis: **Can math-driven product selection + capped CPC bidding produce profitable unit economics on Google Ads?**

## Build Profile
**Startup MVP** — Tier 2

Why: Real money is at stake (ad spend, COGS), but you're validating before scaling. You need:
- Critical-path tests (the scoring model must work)
- Clear boundaries (what to automate now vs later)
- Pragmatic security (payment handling, no secrets in code)

## Rigor Tier
**Tier 2 — Balanced**

Minimum bar:
- Unit tests on scoring model calculations
- Integration tests on API connections (Google Ads, AliExpress/CJ, Shopify)
- ADRs for major decisions (tech stack, supplier strategy, automation boundaries)

## Success Metrics
Ranked by priority:

1. **Unit economics validate** — At least 3-5 products where actual CAC < Net Margin
2. **Model accuracy** — Predicted max CPC vs actual profitable CPC within 1.5x
3. **First $10k revenue month** — Proof the system can generate sales
4. **Chargeback rate < 0.8%** — Payment processor stays healthy
5. **Refund rate < 10%** — Product quality and expectations aligned
6. **< 15 hrs/week operational time** — Automation is working

## Non-Goals
Explicitly NOT building (yet):

| Non-Goal | Why Not Now |
|----------|-------------|
| Brand/private label | Validate product-market fit first |
| Multi-channel (Meta, TikTok) | Prove Google Ads works first |
| US warehousing/3PL | Only for validated winners at scale |
| Multiple stores/entities | Complexity without validation |
| Elaborate supplier relationships | No volume to negotiate yet |
| Perfect AI automation | "Good enough" beats "perfect" at this stage |
| SEO/content sites | Long-term moat, not MVP |
| Custom Shopify theme | Default theme is fine |

## Constraints

### Budget
- **Ad testing budget**: $3,000-5,000 (50-100 products × $50-75 each)
- **Samples**: $200-500/month
- **Tools**: $200-400/month (Shopify, apps, APIs)
- **Reserve**: 3 months operating costs liquid

### Tech Stack
- **Store**: Shopify (default theme, standard apps)
- **Fulfillment**: DSers or CJ Dropshipping (already automated)
- **Ads**: Google Ads API for campaign management
- **Scoring engine**: Python (product selection model)
- **Payments**: Shopify Payments or Stripe (single processor to start)
- **CS**: Email + canned responses (automate later when volume justifies)

### Compliance
- **FTC**: Shipping times stated as 20-30 days (honest buffer)
- **Sales tax**: TaxJar/Avalara from day one
- **Policies**: Refund, shipping, privacy, terms pages required
- **Restricted categories**: No supplements, cosmetics, electronics with batteries, children's products, food, medical, weapons

### Timeline
- **Week 1-2**: Build scoring model, set up store, create landing page template
- **Week 3-4**: Launch first 20-50 products on Google Ads
- **Month 2-3**: Find first winners, refine model based on real data
- **Month 3-6**: Scale winners, add Microsoft Ads, evaluate Meta

## Stop/Ask Rules
Agents must pause and ask when:

### Financial
- [ ] Ad spend on any single product exceeds $100 without conversion
- [ ] Daily ad spend approaching $500+ total
- [ ] Chargeback rate approaches 0.5%
- [ ] Refund rate exceeds 12%
- [ ] Payment processor sends any warning or request

### Operational
- [ ] Any product needs scaling past 50 orders/day
- [ ] Adding a new traffic channel (Meta, TikTok, etc.)
- [ ] Supplier issues affect more than 5% of orders
- [ ] Considering US warehouse or inventory purchase
- [ ] Any legal/compliance question arises

### Technical
- [ ] Google Ads account receives warning or policy flag
- [ ] Landing pages get disapproved
- [ ] Considering changes to payment processing
- [ ] Adding new automation that touches customer data or payments

### Strategic
- [ ] Model assumptions need revision (CVR, CPC, margins off by >30%)
- [ ] Considering new niche or product category
- [ ] Any decision that increases monthly fixed costs by >$200

## Decisions Made

| Question | Decision | Rationale |
|----------|----------|-----------|
| Starting categories | January niches: fitness, organization, productivity | Timing advantage, expand later |
| CVR assumption | 1.0% (conservative) | Safer math, protects downside |
| Kill threshold | 100 clicks | Faster learning, acceptable risk |
| Scaling trigger | CVR > 1.5% AND CAC < 70% of net margin | Room for error before scaling |
| Account structure | Standard Google Ads account | Simpler, revisit if limits hit |

---

## Key Formulas (Reference)

### Max CPC Calculation
```
COGS = Product Cost + Shipping
Gross Margin = (Selling Price - COGS) / Selling Price
Net Margin = Gross Margin - 3% (payment) - 8% (refunds) - 0.5% (chargebacks)
Max CPC = CVR × Selling Price × Net Margin
CPC Buffer = Max CPC / Estimated CPC (target: > 1.5x)
```

### Minimum Product Viability
| Metric | Minimum | Ideal |
|--------|---------|-------|
| AOV | $75+ | $150+ |
| Gross Margin | 65%+ | 70%+ |
| CVR (modeled) | 1.0% | 1.5%+ |
| CPC Buffer | 1.5x | 2.0x+ |
| Estimated CPC | < $0.75 | < $0.50 |

### Hard Filters (Reject Product)
- Estimated CPC > $0.75
- Gross margin < 65%
- Selling price < $50 or > $200
- Amazon Prime competitor with 500+ reviews
- Restricted category (see Compliance above)
- No fast shipping option (>30 days typical)
- Requires sizing or fragile

---

## Glossary

| Term | Definition |
|------|------------|
| **AOV** | Average Order Value — the average amount a customer spends per order |
| **CAC** | Customer Acquisition Cost — total ad spend divided by number of customers acquired |
| **COGS** | Cost of Goods Sold — product cost + shipping cost to customer |
| **CPC** | Cost Per Click — what you pay each time someone clicks your ad |
| **CPM** | Cost Per Mille — cost per 1,000 ad impressions |
| **CVR** | Conversion Rate — percentage of visitors who purchase (orders ÷ clicks) |
| **GMV** | Gross Merchandise Value — total value of goods sold before costs |
| **LTV** | Lifetime Value — total revenue from a customer over their relationship |
| **MCC** | My Client Center — Google Ads manager account for multiple accounts |
| **ROAS** | Return On Ad Spend — revenue generated per dollar of ad spend |
| **SKU** | Stock Keeping Unit — unique identifier for a product |
| **UGC** | User Generated Content — photos/videos from real customers |
| **3PL** | Third-Party Logistics — external warehouse/fulfillment provider |
| **FTC** | Federal Trade Commission — US agency enforcing consumer protection |
| **QS** | Quality Score — Google's 1-10 rating of ad/landing page relevance |
