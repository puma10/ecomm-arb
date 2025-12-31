"""Command-line interface for testing the scoring engine."""

import argparse
import json
import sys

from ecom_arb.scoring.models import Product, ProductCategory, ScoringConfig
from ecom_arb.scoring.scorer import score_product


def create_example_product() -> Product:
    """Create an example product matching the North Star card."""
    return Product(
        id="example-001",
        name="Premium Garden Tool Set",
        product_cost=25.00,
        shipping_cost=10.00,
        selling_price=100.00,
        category=ProductCategory.GARDEN,
        weight_grams=450,
        is_fragile=False,
        requires_sizing=False,
        supplier_rating=4.8,
        supplier_age_months=36,
        supplier_feedback_count=2500,
        shipping_days_min=7,
        shipping_days_max=14,
        has_fast_shipping=True,
        estimated_cpc=0.35,
        monthly_search_volume=3500,
        amazon_prime_exists=True,
        amazon_review_count=45,
    )


def score_command(args: argparse.Namespace) -> None:
    """Score a product from JSON or use example."""
    if args.json:
        data = json.loads(args.json)
        # Convert category string to enum
        if "category" in data and isinstance(data["category"], str):
            data["category"] = ProductCategory(data["category"])
        product = Product(**data)
    else:
        product = create_example_product()
        print("Using example product (use --json to provide your own)\n")

    # Apply custom config if provided
    config = None
    if args.cvr or args.cpc_multiplier:
        config = ScoringConfig(
            cvr=args.cvr or 0.01,
            cpc_multiplier=args.cpc_multiplier or 1.3,
        )

    result = score_product(product, config)

    # Output
    print(f"Product: {result.product_name}")
    print(f"{'=' * 50}")
    print(f"\nFinancials:")
    print(f"  COGS:         ${result.cogs:.2f}")
    print(f"  Gross Margin: {result.gross_margin:.1%}")
    print(f"  Net Margin:   {result.net_margin:.1%}")
    print(f"  Max CPC:      ${result.max_cpc:.2f}")
    print(f"  CPC Buffer:   {result.cpc_buffer:.2f}x")

    print(f"\nFilters: {'PASSED' if result.passed_filters else 'FAILED'}")
    if result.rejection_reasons:
        for reason in result.rejection_reasons:
            print(f"  - {reason}")

    if result.points is not None:
        print(f"\nScoring:")
        print(f"  Points:      {result.points}/100")
        print(f"  Rank Score:  {result.rank_score:.2f}")
        if result.point_breakdown:
            print(f"\n  Breakdown:")
            for factor, points in result.point_breakdown.items():
                print(f"    {factor:12}: {points}")

    print(f"\n{'=' * 50}")
    print(f"Recommendation: {result.recommendation}")


def main() -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="ecom-arb",
        description="E-commerce Arbitrage Scoring Engine",
    )
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Score command
    score_parser = subparsers.add_parser("score", help="Score a product")
    score_parser.add_argument(
        "--json",
        type=str,
        help="Product data as JSON string",
    )
    score_parser.add_argument(
        "--cvr",
        type=float,
        help="Conversion rate (default: 0.01 = 1%%)",
    )
    score_parser.add_argument(
        "--cpc-multiplier",
        type=float,
        help="CPC multiplier for new accounts (default: 1.3)",
    )

    # Example command
    example_parser = subparsers.add_parser(
        "example",
        help="Show example product JSON",
    )
    example_parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty print JSON",
    )

    args = parser.parse_args()

    if args.command == "score":
        score_command(args)
    elif args.command == "example":
        product = create_example_product()
        data = {
            "id": product.id,
            "name": product.name,
            "product_cost": product.product_cost,
            "shipping_cost": product.shipping_cost,
            "selling_price": product.selling_price,
            "category": product.category.value,
            "weight_grams": product.weight_grams,
            "is_fragile": product.is_fragile,
            "requires_sizing": product.requires_sizing,
            "supplier_rating": product.supplier_rating,
            "supplier_age_months": product.supplier_age_months,
            "supplier_feedback_count": product.supplier_feedback_count,
            "shipping_days_min": product.shipping_days_min,
            "shipping_days_max": product.shipping_days_max,
            "has_fast_shipping": product.has_fast_shipping,
            "estimated_cpc": product.estimated_cpc,
            "monthly_search_volume": product.monthly_search_volume,
            "amazon_prime_exists": product.amazon_prime_exists,
            "amazon_review_count": product.amazon_review_count,
        }
        if args.pretty:
            print(json.dumps(data, indent=2))
        else:
            print(json.dumps(data))
    else:
        parser.print_help()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
