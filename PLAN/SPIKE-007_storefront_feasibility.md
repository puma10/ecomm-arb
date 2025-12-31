# SPIKE-007: Storefront Feasibility

## Goal
Estimate build time for FastAPI + Next.js storefront MVP.

## MVP Scope

### Core User Journey
```
Google Ad → Product Page → Checkout → Stripe → Confirmation → Order Tracking
```

### Pages Required

| Page | Purpose | Complexity |
|------|---------|------------|
| Product Landing | Single product display, "Buy Now" CTA | Low |
| Checkout | Collect shipping, redirect to Stripe | Medium |
| Confirmation | Show order number, expected delivery | Low |
| Order Status | Track order by email + order ID | Low |

**Note:** Skip cart for MVP. Each product is a standalone landing page. Direct "Buy Now" → Checkout flow reduces friction and complexity.

---

## Frontend (Next.js)

### Tech Stack
- Next.js 14+ (App Router)
- TypeScript
- Tailwind CSS
- shadcn/ui components
- Stripe.js

### Page Structure
```
/p/[slug]           → Product landing page
/checkout/[product] → Checkout form (shipping info)
/order/[id]         → Confirmation + tracking
```

### Components Needed
```
components/
├── ProductPage/
│   ├── ProductImage.tsx      # Main image + gallery
│   ├── ProductDetails.tsx    # Title, price, description
│   ├── BuyButton.tsx         # CTA button
│   ├── TrustBadges.tsx       # Shipping, returns, secure
│   └── ProductSchema.tsx     # JSON-LD for SEO
├── Checkout/
│   ├── ShippingForm.tsx      # Name, address, email
│   ├── OrderSummary.tsx      # Product, price, shipping
│   └── CheckoutButton.tsx    # Stripe redirect
├── Order/
│   ├── OrderConfirmation.tsx # Thank you + order details
│   └── OrderTracking.tsx     # Status + tracking link
└── shared/
    ├── Header.tsx            # Minimal branding
    ├── Footer.tsx            # Policies, contact
    └── LoadingSpinner.tsx
```

### Hour Estimates (Frontend)

| Component | Hours | Notes |
|-----------|-------|-------|
| Project setup (Next.js + Tailwind + shadcn) | 2 | Boilerplate |
| Product landing page | 6 | Image, details, trust signals |
| Checkout page + form | 6 | Validation, Stripe redirect |
| Confirmation page | 2 | Simple display |
| Order tracking page | 3 | Status lookup |
| Header/Footer/Layout | 2 | Minimal chrome |
| Mobile responsive polish | 4 | Critical for ads |
| **Frontend Total** | **25** | |

---

## Backend (FastAPI)

### Tech Stack
- FastAPI
- PostgreSQL
- SQLAlchemy (async)
- Pydantic (already using)
- Stripe Python SDK

### API Endpoints

```python
# Products
GET  /api/products/{slug}     # Get product for landing page

# Checkout
POST /api/checkout/session    # Create Stripe checkout session
GET  /api/checkout/success    # Handle successful payment

# Orders
GET  /api/orders/{id}         # Get order by ID (requires email)
POST /api/orders/lookup       # Lookup by email + order number

# Webhooks
POST /api/webhooks/stripe     # Handle Stripe events
```

### Database Models

```python
# products table
Product:
    id: UUID
    slug: str (unique)
    name: str
    description: str
    price: Decimal
    compare_at_price: Decimal (optional, for "was $X")
    images: List[str]
    supplier_sku: str
    supplier_source: str (cj, amazon, aliexpress)
    shipping_days_min: int
    shipping_days_max: int
    active: bool
    created_at: datetime

# orders table
Order:
    id: UUID
    order_number: str (human readable, e.g., "ORD-12345")
    email: str
    status: OrderStatus (pending, paid, processing, shipped, delivered, refunded)
    product_id: UUID (FK)
    quantity: int
    subtotal: Decimal
    shipping_cost: Decimal
    total: Decimal
    shipping_address: JSON
    stripe_payment_intent: str
    tracking_number: str (optional)
    tracking_url: str (optional)
    supplier_order_id: str (optional)
    created_at: datetime
    updated_at: datetime
```

### Hour Estimates (Backend)

| Component | Hours | Notes |
|-----------|-------|-------|
| Project setup (FastAPI + SQLAlchemy + Alembic) | 3 | Boilerplate + migrations |
| Database models + migrations | 3 | Products, Orders |
| Product endpoints | 2 | Simple CRUD |
| Checkout flow + Stripe session | 4 | Core payment logic |
| Stripe webhook handler | 4 | Payment success, failure |
| Order lookup endpoints | 2 | By ID or email |
| Error handling + logging | 2 | Production ready |
| **Backend Total** | **20** | |

---

## Stripe Integration

### Approach: Stripe Checkout (Hosted)

**Why Hosted Checkout:**
- Fastest to implement (hours, not days)
- PCI compliance handled by Stripe
- Mobile-optimized out of box
- Apple Pay / Google Pay automatic
- No card input UI to build

**Flow:**
```
1. User clicks "Buy Now"
2. Frontend calls POST /api/checkout/session
3. Backend creates Stripe Checkout Session
4. Frontend redirects to Stripe hosted page
5. User completes payment on Stripe
6. Stripe redirects to success URL
7. Webhook confirms payment → create Order
```

**Webhook Events to Handle:**
- `checkout.session.completed` → Create order, send confirmation email
- `payment_intent.payment_failed` → Log, alert
- `charge.dispute.created` → Alert, track for metrics

### Hour Estimates (Stripe)

| Component | Hours | Notes |
|-----------|-------|-------|
| Stripe account setup | 1 | Test + live keys |
| Checkout session creation | 2 | Backend logic |
| Webhook handling | 3 | Event processing |
| Success/cancel pages | 1 | Redirects |
| **Stripe Total** | **7** | (included in backend) |

---

## Deployment

### Infrastructure (Hetzner)
- Docker Compose
- Nginx reverse proxy
- PostgreSQL container
- Let's Encrypt SSL

### Hour Estimates (DevOps)

| Component | Hours | Notes |
|-----------|-------|-------|
| Docker setup (frontend + backend) | 3 | Dockerfiles, compose |
| Nginx config + SSL | 2 | Certbot |
| GitHub Actions CI/CD | 3 | Build, test, deploy |
| Environment management | 1 | Secrets, configs |
| **DevOps Total** | **9** | |

---

## Summary: Total Build Estimate

| Area | Hours |
|------|-------|
| Frontend (Next.js) | 25 |
| Backend (FastAPI) | 20 |
| DevOps (Docker, CI/CD) | 9 |
| **Total MVP** | **54 hours** |

### With Buffer (1.5x for unknowns)
**Realistic estimate: 80 hours / ~2 weeks**

---

## Accelerating Libraries & Templates

### Frontend
| Library | Saves | Notes |
|---------|-------|-------|
| [shadcn/ui](https://ui.shadcn.com/) | 8+ hrs | Pre-built components |
| [next-themes](https://github.com/pacocoursey/next-themes) | 1 hr | Dark mode (skip for MVP) |
| [react-hook-form](https://react-hook-form.com/) | 2 hrs | Form validation |
| [zod](https://zod.dev/) | 1 hr | Schema validation |

### Backend
| Library | Saves | Notes |
|---------|-------|-------|
| [FastAPI](https://fastapi.tiangolo.com/) | - | Already chosen |
| [SQLModel](https://sqlmodel.tiangolo.com/) | 2 hrs | Pydantic + SQLAlchemy fusion |
| [Alembic](https://alembic.sqlalchemy.org/) | - | Migrations (required) |
| [stripe-python](https://github.com/stripe/stripe-python) | - | Official SDK |

### Templates to Consider
| Template | Type | Notes |
|----------|------|-------|
| [create-t3-app](https://create.t3.gg/) | Full stack | Overkill, but reference |
| [FastAPI template](https://github.com/tiangolo/full-stack-fastapi-template) | Backend | Good patterns |

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Stripe integration complexity | Low | Medium | Use Checkout (hosted) |
| Mobile responsiveness issues | Medium | High | Test early, use Tailwind |
| SEO/page speed for ads | Medium | Medium | Next.js SSR, optimize images |
| Database migrations in prod | Low | Medium | Alembic, test migrations |

---

## Recommendation

**Go ahead with build.**

54-80 hours is reasonable for a functional MVP. Key decisions:

1. **Use Stripe Checkout (hosted)** - Don't build payment UI
2. **Skip cart** - Direct product → checkout flow
3. **Start with 1 product** - Validate flow before scaling
4. **shadcn/ui** - Don't build component library from scratch

### Suggested Build Order
1. Backend: Database + Product endpoint (5 hrs)
2. Backend: Stripe checkout flow (6 hrs)
3. Frontend: Product page (6 hrs)
4. Frontend: Checkout page (6 hrs)
5. Integration testing (4 hrs)
6. DevOps: Docker + deploy (6 hrs)
7. **First product live: ~33 hours**

Then iterate: confirmation page, order tracking, polish.
