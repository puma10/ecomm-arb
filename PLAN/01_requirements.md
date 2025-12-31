# Requirements

## Scope
- **Project**: E-commerce Arbitrage System
- **Date**: December 2025
- **Rigor Tier**: 2 (Balanced)
- **Reference**: [North Star Card](00_north_star.md)

---

# Phase 1: MVP (Validate Unit Economics)

## Component: Product Scoring Engine

### REQ-001 (P0): Product Viability Calculation

**What must be true:**
System calculates whether a product's unit economics are viable before any ad spend occurs.

**Acceptance Criteria:**
- AC-001.1: Given product cost, shipping cost, and selling price, system calculates gross margin
- AC-001.2: Given gross margin, system calculates net margin (gross - 3% payment - 8% refunds - 0.5% chargebacks)
- AC-001.3: Given CVR assumption (1.0%) and selling price, system calculates max CPC
- AC-001.4: Given max CPC and estimated CPC, system calculates CPC buffer ratio
- AC-001.5: All calculations match hand-calculated examples within 0.1%

**Assumptions:**
- Payment fees = 3% (HIGH confidence - Stripe/Shopify standard)
- Refund rate = 8% (MED confidence - category dependent)
- Chargeback rate = 0.5% (MED confidence - depends on execution)
- CVR = 1.0% (LOW confidence - will calibrate with real data)

**Dependencies:**
- None (pure calculation)

---

### REQ-002 (P0): Product Hard Filters

**What must be true:**
System rejects products that cannot be profitable regardless of other factors.

**Acceptance Criteria:**
- AC-002.1: Reject if estimated CPC > $0.75
- AC-002.2: Reject if gross margin < 65%
- AC-002.3: Reject if selling price < $50 or > $200
- AC-002.4: Reject if product is in restricted category list
- AC-002.5: Reject if typical shipping time > 30 days
- AC-002.6: Reject if product requires sizing
- AC-002.7: Reject if product is fragile/breakable
- AC-002.8: Reject if Amazon Prime competitor exists with 500+ reviews

**Assumptions:**
- Restricted categories: supplements, cosmetics, electronics with batteries, children's products, food, medical, weapons (HIGH confidence - regulatory)

**Dependencies:**
- REQ-003 (CPC estimation)
- REQ-004 (Amazon competition check)

---

### REQ-003 (P0): CPC Estimation

**What must be true:**
System retrieves estimated CPC for product keywords before campaign creation.

**Acceptance Criteria:**
- AC-003.1: Given a product name/description, system generates relevant keyword list
- AC-003.2: System retrieves CPC estimates from Google Keyword Planner API
- AC-003.3: System applies 1.3x multiplier for new account penalty
- AC-003.4: CPC estimate available within 30 seconds per product

**Assumptions:**
- Google Keyword Planner estimates are directionally accurate (MED confidence)
- New account CPC penalty ~1.3x (MED confidence - observed, not guaranteed)

**Dependencies:**
- Google Ads API access
- Valid Google Ads account

---

### REQ-004 (P1): Amazon Competition Check

**What must be true:**
System identifies whether a strong Amazon Prime competitor exists for each product.

**Acceptance Criteria:**
- AC-004.1: Given product keywords, system searches Amazon for matching products
- AC-004.2: System identifies Prime-eligible listings
- AC-004.3: System retrieves review count for top listings
- AC-004.4: System flags products where Prime listing has 500+ reviews

**Assumptions:**
- Amazon search approximates what customers would find (HIGH confidence)

**Dependencies:**
- Amazon Product API or scraping capability

---

### REQ-005 (P1): Product Scoring Model

**What must be true:**
System ranks viable products by expected profitability to prioritize testing.

**Acceptance Criteria:**
- AC-005.1: System assigns points based on scoring factors (CPC, margin, AOV, competition, volume, refund risk, shipping, niche passion)
- AC-005.2: System calculates rank score combining point score and CPC buffer
- AC-005.3: Products sorted by rank score, highest first
- AC-005.4: Score breakdown visible for each product

**Scoring Factors:**
| Factor | Max Points |
|--------|------------|
| CPC Score | 20 |
| Margin Score | 20 |
| AOV Score | 15 |
| Competition Score | 15 |
| Search Volume | 10 |
| Refund Risk | 10 |
| Shipping | 5 |
| Niche Passion | 5 |

**Dependencies:**
- REQ-001 through REQ-004

---

## Component: Product Data Collection

### REQ-006 (P0): AliExpress Product Data

**What must be true:**
System retrieves product information from AliExpress for scoring.

**Acceptance Criteria:**
- AC-006.1: Retrieve product cost (USD)
- AC-006.2: Retrieve shipping cost to US (ePacket/AliExpress Standard)
- AC-006.3: Retrieve estimated shipping time
- AC-006.4: Retrieve product weight
- AC-006.5: Retrieve seller rating, age, feedback count
- AC-006.6: Retrieve product images
- AC-006.7: Data retrieval completes within 10 seconds per product

**Assumptions:**
- AliExpress data accessible via API or scraping (MED confidence - may require workarounds)

**Dependencies:**
- AliExpress API or scraping infrastructure

---

### REQ-007 (P1): Supplier Hard Filters

**What must be true:**
System rejects suppliers that are likely to cause fulfillment issues.

**Acceptance Criteria:**
- AC-007.1: Reject if store rating < 4.6
- AC-007.2: Reject if store age < 1 year
- AC-007.3: Reject if feedback count < 500
- AC-007.4: Reject if no ePacket/AliExpress Standard shipping option
- AC-007.5: Reject if average response time > 24 hours

**Dependencies:**
- REQ-006

---

## Component: Landing Page Generation

### REQ-008 (P0): Product Page Creation

**What must be true:**
System creates functional product landing pages for each selected product.

**Acceptance Criteria:**
- AC-008.1: Page includes product title, description, price, images
- AC-008.2: Page includes Add to Cart functionality
- AC-008.3: Page includes shipping time disclosure (20-30 days)
- AC-008.4: Page loads in < 3 seconds
- AC-008.5: Page is mobile responsive
- AC-008.6: Page passes Google Ads landing page policy check

**Assumptions:**
- AI-generated descriptions are accurate to product (MED confidence - requires review)

**Dependencies:**
- Shopify store setup
- REQ-006 (product data)

---

### REQ-009 (P0): Required Policy Pages

**What must be true:**
Store has all legally required and trust-building pages.

**Acceptance Criteria:**
- AC-009.1: Refund policy page exists and is linked in footer
- AC-009.2: Shipping policy page exists with honest 20-30 day timeframe
- AC-009.3: Privacy policy page exists
- AC-009.4: Terms of service page exists
- AC-009.5: Contact page exists with working email
- AC-009.6: Physical business address displayed

**Dependencies:**
- Shopify store setup

---

## Component: Google Ads Campaign Management

### REQ-010 (P0): Campaign Creation

**What must be true:**
System creates Google Ads campaigns for scored products with correct settings.

**Acceptance Criteria:**
- AC-010.1: Campaign created with Manual CPC bidding
- AC-010.2: Max CPC set to calculated max from scoring model
- AC-010.3: Daily budget cap set ($10-20 per product initially)
- AC-010.4: Keywords populated from product research
- AC-010.5: Ad copy generated from product data
- AC-010.6: Landing page URL linked correctly

**Dependencies:**
- Google Ads API access
- REQ-001 (max CPC calculation)
- REQ-008 (landing page)

---

### REQ-011 (P0): Campaign Monitoring

**What must be true:**
System tracks campaign performance metrics in real-time.

**Acceptance Criteria:**
- AC-011.1: Track impressions, clicks, CPC by campaign
- AC-011.2: Track conversions, CVR, CAC by campaign
- AC-011.3: Track spend vs budget by campaign
- AC-011.4: Data refreshes at least every 4 hours
- AC-011.5: Alerts triggered when thresholds exceeded

**Dependencies:**
- Google Ads API access
- Shopify conversion tracking

---

### REQ-012 (P0): Kill Logic

**What must be true:**
System automatically pauses underperforming campaigns to limit losses.

**Acceptance Criteria:**
- AC-012.1: Pause campaign if 100 clicks with 0 conversions
- AC-012.2: Pause campaign if actual CPC > 1.5x calculated max CPC for 3+ days
- AC-012.3: Pause campaign if CVR < 0.5% after 200 clicks
- AC-012.4: Pause executes within 1 hour of threshold breach
- AC-012.5: Notification sent when campaign paused

**Dependencies:**
- REQ-011 (monitoring data)

---

### REQ-013 (P1): Scale Logic

**What must be true:**
System identifies winners and increases their budget.

**Acceptance Criteria:**
- AC-013.1: Flag as winner if CVR > 1.5% AND CAC < 70% of net margin after 2+ conversions
- AC-013.2: Increase daily budget by 25% for winners (max $100/day initially)
- AC-013.3: Continue monitoring after scale for regression
- AC-013.4: Notification sent when campaign scaled

**Dependencies:**
- REQ-011 (monitoring data)
- REQ-012 (kill logic must not conflict)

---

## Component: Order Fulfillment

### REQ-014 (P0): Order Routing

**What must be true:**
Customer orders automatically route to suppliers for fulfillment.

**Acceptance Criteria:**
- AC-014.1: New Shopify order triggers fulfillment workflow within 5 minutes
- AC-014.2: Order placed with correct supplier via DSers/CJ API
- AC-014.3: Customer shipping address passed correctly
- AC-014.4: Payment to supplier processed automatically
- AC-014.5: Order confirmation stored for tracking

**Assumptions:**
- DSers or CJ Dropshipping integration works reliably (HIGH confidence - established tools)

**Dependencies:**
- Shopify store
- DSers or CJ Dropshipping account
- Payment method for supplier payments

---

### REQ-015 (P0): Tracking Updates

**What must be true:**
Customers receive tracking information for their orders.

**Acceptance Criteria:**
- AC-015.1: Tracking number captured from supplier within 7 days
- AC-015.2: Tracking number pushed to Shopify order
- AC-015.3: Customer notified via email with tracking link
- AC-015.4: Tracking status monitored for delivery confirmation

**Dependencies:**
- REQ-014 (order routing)
- 17Track API or similar tracking aggregator

---

### REQ-016 (P1): Delay Detection

**What must be true:**
System identifies orders at risk of FTC shipping violations.

**Acceptance Criteria:**
- AC-016.1: Flag orders with no tracking movement for 14+ days
- AC-016.2: Flag orders approaching 25+ days since order
- AC-016.3: Trigger proactive customer email offering refund option
- AC-016.4: Log all delay incidents for supplier scoring

**Dependencies:**
- REQ-015 (tracking data)

---

## Component: Customer Service

### REQ-017 (P1): Inquiry Classification

**What must be true:**
System classifies incoming customer inquiries by type.

**Acceptance Criteria:**
- AC-017.1: Classify "where's my order" inquiries (40-50% of volume)
- AC-017.2: Classify product questions (20-30%)
- AC-017.3: Classify refund requests (15-20%)
- AC-017.4: Classify complaints requiring escalation (5-10%)
- AC-017.5: Classification accuracy > 90%

**Assumptions:**
- LLM classification is reliable for these categories (MED confidence)

**Dependencies:**
- Email/chat integration
- LLM API access

---

### REQ-018 (P1): Automated Responses

**What must be true:**
System auto-responds to routine inquiries without human intervention.

**Acceptance Criteria:**
- AC-018.1: "Where's my order" → auto-reply with tracking link
- AC-018.2: Product questions → auto-reply using product data
- AC-018.3: Simple refund requests (< $50) → auto-approve and process
- AC-018.4: Response sent within 5 minutes of inquiry
- AC-018.5: Human escalation path for edge cases

**Dependencies:**
- REQ-017 (classification)
- REQ-015 (tracking data)
- Shopify refund API

---

### REQ-019 (P1): Refund Automation

**What must be true:**
System processes refunds automatically when rules are met.

**Acceptance Criteria:**
- AC-019.1: Auto-refund if order value < $50 and customer requests
- AC-019.2: Auto-refund if shipping > 25 days with no delivery
- AC-019.3: Refund processed in Shopify within 1 hour
- AC-019.4: Customer notified of refund
- AC-019.5: Supplier score updated for refund-causing issues

**Dependencies:**
- Shopify API
- REQ-007 (supplier scoring)

---

## Component: Monitoring Dashboard

### REQ-020 (P0): Unit Economics Tracking

**What must be true:**
System provides real-time visibility into profitability.

**Acceptance Criteria:**
- AC-020.1: Display revenue by day/week/month
- AC-020.2: Display ad spend by day/week/month
- AC-020.3: Display COGS by day/week/month
- AC-020.4: Display net margin by product and overall
- AC-020.5: Display CAC vs target by product
- AC-020.6: Data refreshes at least hourly

**Dependencies:**
- Shopify API (revenue)
- Google Ads API (spend)
- Product data (COGS)

---

### REQ-021 (P0): Health Metrics

**What must be true:**
System tracks and alerts on metrics that threaten business viability.

**Acceptance Criteria:**
- AC-021.1: Track refund rate (alert if > 10%)
- AC-021.2: Track chargeback rate (alert if > 0.5%)
- AC-021.3: Track average shipping time (alert if > 25 days)
- AC-021.4: Track supplier issue rate (alert if > 5%)
- AC-021.5: Alerts sent via email/SMS within 1 hour of threshold breach

**Dependencies:**
- Shopify data
- Payment processor data
- Tracking data

---

## Component: Compliance

### REQ-022 (P0): Sales Tax Collection

**What must be true:**
System collects and remits sales tax where required.

**Acceptance Criteria:**
- AC-022.1: TaxJar or Avalara integrated with Shopify
- AC-022.2: Tax calculated correctly at checkout by state
- AC-022.3: Tax collected and reported automatically
- AC-022.4: Nexus tracking alerts when approaching $100k in any state

**Dependencies:**
- TaxJar or Avalara account
- Shopify integration

---

### REQ-023 (P0): FTC Shipping Compliance

**What must be true:**
System meets FTC Mail Order Rule requirements.

**Acceptance Criteria:**
- AC-023.1: All product pages state 20-30 day shipping timeframe
- AC-023.2: Order confirmation emails include shipping estimate
- AC-023.3: Delay notifications sent if order exceeds stated timeframe
- AC-023.4: Cancel/refund option provided in delay notifications

**Dependencies:**
- REQ-008 (landing pages)
- REQ-016 (delay detection)

---

# Phase 2: Scale (After Validation)

## REQ-024 (P2): Microsoft Ads Integration

**What must be true:**
Campaigns can be mirrored to Microsoft Ads for incremental volume.

**Acceptance Criteria:**
- AC-024.1: Import winning Google Ads campaigns to Microsoft
- AC-024.2: Adjust bids based on Microsoft CPC estimates
- AC-024.3: Same monitoring and kill logic applies

**Dependencies:**
- Phase 1 complete
- Microsoft Ads API access

---

## REQ-025 (P2): Supplier Failover

**What must be true:**
System automatically switches to backup supplier when primary fails.

**Acceptance Criteria:**
- AC-025.1: Each product has primary and backup supplier
- AC-025.2: Auto-switch if primary out of stock
- AC-025.3: Auto-switch if primary response time > 48 hours
- AC-025.4: Notification sent when failover occurs

**Dependencies:**
- Phase 1 supplier scoring working

---

## REQ-026 (P2): Dynamic Supplier Scoring

**What must be true:**
Supplier scores update based on actual performance, not just initial metrics.

**Acceptance Criteria:**
- AC-026.1: Score decreases on wrong item (-10), quality complaint (-5), slow ship (-3), out of stock (-10), non-responsive (-15)
- AC-026.2: Auto-pause supplier if score < 50
- AC-026.3: Blacklist supplier if score < 30

**Dependencies:**
- REQ-019 (refund tracking)
- REQ-016 (delay tracking)

---

# Decisions Made

| Question | Decision | Notes |
|----------|----------|-------|
| Manual review gate | Yes — human reviews before ad launch | Prevents bad products from burning ad spend |
| Sample ordering | Yes — order samples before scaling | Threshold TBD (likely 20+ orders/day) |

# Open Questions

1. **Product sourcing volume** — How many products to evaluate per week? (Figure out during execution)
2. **Sample ordering threshold** — At what orders/day do we order samples? (Start with 20/day, adjust)
3. **Backup payment processor** — Defer until needed (processor warning or $50k+/month)

---

# Requirement Traceability

| Requirement | Success Metric (from North Star) |
|-------------|----------------------------------|
| REQ-001 to REQ-005 | Unit economics validate |
| REQ-010 to REQ-013 | Model accuracy, first $10k month |
| REQ-017 to REQ-019 | Refund rate < 10%, < 15 hrs/week |
| REQ-021 | Chargeback rate < 0.8% |
| REQ-020 | Unit economics validate |
| REQ-022, REQ-023 | Compliance (table stakes) |
