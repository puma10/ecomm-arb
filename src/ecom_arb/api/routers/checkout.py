"""Checkout API endpoints with Stripe integration."""

import secrets
from datetime import datetime, timezone
from decimal import Decimal

import stripe
from fastapi import APIRouter, Depends, HTTPException, Header, Request, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ecom_arb.config import get_settings
from ecom_arb.db import Order, OrderStatus, Product, get_db

router = APIRouter(prefix="/checkout", tags=["checkout"])
settings = get_settings()

# Configure Stripe
stripe.api_key = settings.stripe_secret_key


class ShippingAddress(BaseModel):
    """Shipping address schema."""

    first_name: str
    last_name: str
    address_line1: str
    address_line2: str = ""
    city: str
    state: str
    postal_code: str
    country: str = "US"


class CheckoutRequest(BaseModel):
    """Checkout session request."""

    product_slug: str
    email: EmailStr
    shipping_address: ShippingAddress
    quantity: int = 1


class CheckoutResponse(BaseModel):
    """Checkout session response."""

    checkout_url: str
    session_id: str


def generate_order_number() -> str:
    """Generate a human-readable order number."""
    # Format: ORD-XXXXXX (6 random alphanumeric chars)
    return f"ORD-{secrets.token_hex(3).upper()}"


@router.post("/session", response_model=CheckoutResponse)
async def create_checkout_session(
    checkout_data: CheckoutRequest,
    db: AsyncSession = Depends(get_db),
) -> CheckoutResponse:
    """Create a Stripe checkout session and order."""
    # Get product
    result = await db.execute(
        select(Product).where(
            Product.slug == checkout_data.product_slug,
            Product.active == True,  # noqa: E712
        )
    )
    product = result.scalar_one_or_none()

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )

    # Calculate totals
    subtotal = product.price * checkout_data.quantity
    shipping_cost = product.shipping_cost if product.shipping_cost else Decimal("0")
    total = subtotal + shipping_cost

    # Create order (pending payment)
    order = Order(
        order_number=generate_order_number(),
        email=checkout_data.email,
        status=OrderStatus.PENDING,
        product_id=product.id,
        quantity=checkout_data.quantity,
        subtotal=subtotal,
        shipping_cost=shipping_cost,
        total=total,
        shipping_address=checkout_data.shipping_address.model_dump(),
    )
    db.add(order)
    await db.flush()
    await db.refresh(order)

    # Create Stripe checkout session
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[
                {
                    "price_data": {
                        "currency": "usd",
                        "product_data": {
                            "name": product.name,
                            "images": product.images[:1] if product.images else [],
                        },
                        "unit_amount": int(product.price * 100),  # Stripe uses cents
                    },
                    "quantity": checkout_data.quantity,
                },
            ],
            # Add shipping as a separate line item if applicable
            **(
                {
                    "shipping_options": [
                        {
                            "shipping_rate_data": {
                                "type": "fixed_amount",
                                "fixed_amount": {
                                    "amount": int(shipping_cost * 100),
                                    "currency": "usd",
                                },
                                "display_name": f"Standard Shipping ({product.shipping_days_min}-{product.shipping_days_max} days)",
                            },
                        },
                    ],
                }
                if shipping_cost > 0
                else {}
            ),
            mode="payment",
            success_url=settings.stripe_success_url.format(order_id=order.id),
            cancel_url=settings.stripe_cancel_url.format(product_slug=product.slug),
            customer_email=checkout_data.email,
            metadata={
                "order_id": str(order.id),
                "order_number": order.order_number,
            },
        )

        # Update order with session ID
        order.stripe_checkout_session_id = session.id
        await db.flush()

        return CheckoutResponse(
            checkout_url=session.url,
            session_id=session.id,
        )

    except stripe.StripeError as e:
        # Rollback order on Stripe error
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Payment error: {e!s}",
        )


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(alias="stripe-signature"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Handle Stripe webhook events."""
    payload = await request.body()

    try:
        event = stripe.Webhook.construct_event(
            payload,
            stripe_signature,
            settings.stripe_webhook_secret,
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    # Handle the event
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        order_id = session.get("metadata", {}).get("order_id")

        if order_id:
            # Update order status
            result = await db.execute(select(Order).where(Order.id == order_id))
            order = result.scalar_one_or_none()

            if order:
                order.status = OrderStatus.PAID
                order.paid_at = datetime.now(timezone.utc)
                order.stripe_payment_intent_id = session.get("payment_intent")
                await db.flush()

    elif event["type"] == "payment_intent.payment_failed":
        session = event["data"]["object"]
        # Log failed payment (could add alerting here)
        pass

    return {"status": "received"}
