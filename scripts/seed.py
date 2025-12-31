#!/usr/bin/env python3
"""Seed the database with test products."""

import asyncio
from decimal import Decimal

from sqlalchemy import select

from ecom_arb.db.base import async_session_maker
from ecom_arb.db.models import Product, SupplierSource


SAMPLE_PRODUCTS = [
    {
        "slug": "premium-garden-tool-set",
        "name": "Premium Garden Tool Set - 5 Piece Stainless Steel",
        "description": """Professional-grade garden tool set perfect for any gardener.

This 5-piece set includes:
- Trowel for planting and transplanting
- Cultivator for loosening soil
- Weeder for removing weeds
- Transplanter for moving plants
- Pruning shears for trimming

All tools feature ergonomic handles and rust-resistant stainless steel heads.
Perfect for both beginners and experienced gardeners.""",
        "price": Decimal("89.99"),
        "compare_at_price": Decimal("129.99"),
        "cost": Decimal("22.00"),
        "images": [
            "https://images.unsplash.com/photo-1416879595882-3373a0480b5b?w=800",
            "https://images.unsplash.com/photo-1585320806297-9794b3e4eeae?w=800",
        ],
        "supplier_source": SupplierSource.CJ,
        "supplier_sku": "GT-5PC-001",
        "shipping_cost": Decimal("0"),
        "shipping_days_min": 7,
        "shipping_days_max": 14,
    },
    {
        "slug": "smart-pet-feeder-automatic",
        "name": "Smart Automatic Pet Feeder with WiFi & App Control",
        "description": """Never miss a feeding with our smart automatic pet feeder.

Features:
- WiFi connected with smartphone app
- Schedule up to 6 meals per day
- Portion control from 1/8 to 4 cups
- Voice recording to call your pet
- Battery backup for power outages
- Works with dry food up to 0.5" kibble size

Perfect for busy pet parents or those with irregular schedules.
4L capacity holds up to 16 cups of food.""",
        "price": Decimal("79.99"),
        "compare_at_price": Decimal("99.99"),
        "cost": Decimal("18.00"),
        "images": [
            "https://images.unsplash.com/photo-1601758228041-f3b2795255f1?w=800",
        ],
        "supplier_source": SupplierSource.CJ,
        "supplier_sku": "PF-SMART-001",
        "shipping_cost": Decimal("0"),
        "shipping_days_min": 8,
        "shipping_days_max": 15,
    },
    {
        "slug": "portable-camping-hammock",
        "name": "Ultralight Portable Camping Hammock with Tree Straps",
        "description": """Experience ultimate relaxation anywhere with our ultralight hammock.

Specs:
- Weight capacity: 500 lbs
- Hammock size: 9ft x 4.5ft
- Packed size: 5" x 8" (fits in palm)
- Weight: 12 oz including straps
- Material: Parachute nylon, quick-dry

Includes:
- 1x Hammock
- 2x Tree straps (10ft each)
- 2x Carabiners
- 1x Stuff sack

Perfect for hiking, camping, backyard, or beach. Sets up in under 2 minutes.""",
        "price": Decimal("49.99"),
        "compare_at_price": Decimal("69.99"),
        "cost": Decimal("11.00"),
        "images": [
            "https://images.unsplash.com/photo-1504280390367-361c6d9f38f4?w=800",
            "https://images.unsplash.com/photo-1520824071669-9c78fdc6830d?w=800",
        ],
        "supplier_source": SupplierSource.ALIEXPRESS,
        "supplier_sku": "HAM-UL-001",
        "shipping_cost": Decimal("0"),
        "shipping_days_min": 10,
        "shipping_days_max": 18,
    },
]


async def seed_products() -> None:
    """Seed the database with sample products."""
    async with async_session_maker() as session:
        for product_data in SAMPLE_PRODUCTS:
            # Check if product already exists
            result = await session.execute(
                select(Product).where(Product.slug == product_data["slug"])
            )
            existing = result.scalar_one_or_none()

            if existing:
                print(f"Product '{product_data['slug']}' already exists, skipping...")
                continue

            product = Product(**product_data)
            session.add(product)
            print(f"Created product: {product_data['name']}")

        await session.commit()
        print("\nSeeding complete!")


if __name__ == "__main__":
    asyncio.run(seed_products())
