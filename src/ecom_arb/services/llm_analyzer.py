"""LLM-based product analysis using OpenRouter.

Provides semantic understanding of products for:
- Product type, style, materials, buyer persona
- Keyword generation and relevance scoring
- Amazon product similarity comparison
"""

import json
import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import httpx

from ecom_arb.config import get_settings

logger = logging.getLogger(__name__)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


@dataclass
class ProductUnderstanding:
    """LLM's understanding of a product."""

    product_type: str
    style: list[str]
    materials: list[str]
    use_cases: list[str]
    buyer_persona: str
    quality_tier: str  # budget, mid-range, premium
    price_expectation: str  # e.g., "$60-150"
    seed_keywords: dict[str, list[str]]  # exact, specific, broad


@dataclass
class AmazonMatch:
    """A similar Amazon product."""

    index: int
    title: str
    price: float
    reviews: int
    similarity: int  # 0-100
    reason: str
    asin: str | None = None


@dataclass
class AmazonAnalysis:
    """Results of Amazon comparison."""

    similar_products: list[AmazonMatch]
    market_price: dict[str, float | None]  # weighted_median, min, max
    sample_size: int


@dataclass
class KeywordScore:
    """Relevance score for a keyword."""

    keyword: str
    relevance: int  # 0-100
    reason: str


async def _call_openrouter(
    messages: list[dict],
    temperature: float = 0.3,
    max_tokens: int = 2000,
) -> dict:
    """Make a call to OpenRouter API.

    Args:
        messages: List of message dicts with role and content
        temperature: Sampling temperature (lower = more deterministic)
        max_tokens: Maximum tokens in response

    Returns:
        Parsed JSON response from the model

    Raises:
        Exception: If API call fails or response is invalid
    """
    settings = get_settings()

    if not settings.openrouter_api_key:
        raise ValueError("OPENROUTER_API_KEY not configured")

    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://ecom-arb.local",  # Required by OpenRouter
        "X-Title": "ecom-arb",
    }

    payload = {
        "model": settings.openrouter_model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            f"{OPENROUTER_BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
        )

        if response.status_code != 200:
            logger.error(f"OpenRouter error: {response.status_code} - {response.text}")
            raise Exception(f"OpenRouter API error: {response.status_code}")

        data = response.json()
        content = data["choices"][0]["message"]["content"]

        # Strip markdown code blocks if present
        content = content.strip()
        if content.startswith("```json"):
            content = content[7:]
        elif content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        # Parse JSON from response
        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {content[:500]}")
            raise Exception(f"Invalid JSON response from LLM: {e}")


async def analyze_product(
    name: str,
    weight_grams: int | None = None,
    cost: float | None = None,
    category: str | None = None,
    description: str | None = None,
) -> ProductUnderstanding:
    """Analyze a product to understand what it is.

    Args:
        name: Product name/title
        weight_grams: Weight in grams (optional)
        cost: Product cost in USD (optional)
        category: Product category (optional)
        description: Product description (optional)

    Returns:
        ProductUnderstanding with type, style, materials, keywords, etc.
    """
    product_info = f"Product: {name}"
    if weight_grams:
        product_info += f"\nWeight: {weight_grams}g"
    if cost:
        product_info += f"\nCost: ${cost:.2f}"
    if category:
        product_info += f"\nCategory: {category}"
    if description:
        product_info += f"\nDescription: {description[:500]}"

    messages = [
        {
            "role": "system",
            "content": """You are an e-commerce product analyst. Analyze products to understand what they are, who buys them, and what keywords people would search for.

Always respond with valid JSON matching the requested schema. Be specific and practical.""",
        },
        {
            "role": "user",
            "content": f"""Analyze this product for e-commerce advertising:

{product_info}

Return JSON with this exact structure:
{{
  "product_type": "specific product type (e.g., 'ceiling pendant lamp', 'bluetooth speaker', 'cable organizer bag')",
  "style": ["style descriptor 1", "style descriptor 2"],
  "materials": ["material 1", "material 2"],
  "use_cases": ["where/how used 1", "where/how used 2"],
  "buyer_persona": "description of who buys this",
  "quality_tier": "budget|mid-range|premium",
  "price_expectation": "$X-Y range (what buyers expect to pay)",
  "seed_keywords": {{
    "exact": ["highly specific 3-5 word keywords that exactly describe this product"],
    "specific": ["2-3 word product type keywords"],
    "broad": ["1-2 word category keywords"]
  }}
}}

Generate 3-5 keywords for each tier. Keywords should be what real shoppers would search for on Google.""",
        },
    ]

    result = await _call_openrouter(messages, temperature=0.3)

    return ProductUnderstanding(
        product_type=result.get("product_type", "unknown"),
        style=result.get("style", []),
        materials=result.get("materials", []),
        use_cases=result.get("use_cases", []),
        buyer_persona=result.get("buyer_persona", ""),
        quality_tier=result.get("quality_tier", "mid-range"),
        price_expectation=result.get("price_expectation", ""),
        seed_keywords=result.get("seed_keywords", {"exact": [], "specific": [], "broad": []}),
    )


async def compare_amazon_products(
    product_understanding: ProductUnderstanding,
    amazon_products: list[dict],
) -> AmazonAnalysis:
    """Compare Amazon products to find similar items.

    Args:
        product_understanding: Our understanding of the source product
        amazon_products: List of Amazon products with title, price, reviews, asin

    Returns:
        AmazonAnalysis with similar products and market price
    """
    # Format Amazon products for the prompt
    amazon_list = []
    for i, p in enumerate(amazon_products[:50]):  # Limit to 50
        price = p.get("price", "N/A")
        reviews = p.get("review_count", p.get("reviews", 0))
        title = p.get("title", "")[:100]
        amazon_list.append(f"{i+1}. \"{title}\" - ${price} - {reviews} reviews")

    amazon_text = "\n".join(amazon_list)

    messages = [
        {
            "role": "system",
            "content": """You are comparing products to find similar items on Amazon.
Rate each product's similarity to the target product on a 0-100 scale.
Be strict - only high scores for truly similar products.""",
        },
        {
            "role": "user",
            "content": f"""Find Amazon products similar to ours.

Our Product:
- Type: {product_understanding.product_type}
- Style: {', '.join(product_understanding.style)}
- Materials: {', '.join(product_understanding.materials)}
- Quality tier: {product_understanding.quality_tier}
- Expected price: {product_understanding.price_expectation}

Amazon Products:
{amazon_text}

Rate each Amazon product's similarity (0-100):
- 90-100: Nearly identical (same type, style, quality tier)
- 70-89: Very similar (same category, similar features)
- 50-69: Somewhat similar (related but noticeably different)
- <50: Different product (don't include these)

Return JSON:
{{
  "similar_products": [
    {{"index": 1, "similarity": 85, "reason": "brief reason"}},
    ...only include products with similarity >= 50
  ]
}}

Be selective - only include genuinely similar products.""",
        },
    ]

    result = await _call_openrouter(messages, temperature=0.2)

    similar = result.get("similar_products", [])

    # Build AmazonMatch objects
    matches = []
    for item in similar:
        idx = item.get("index", 0) - 1  # Convert to 0-indexed
        if 0 <= idx < len(amazon_products):
            ap = amazon_products[idx]
            matches.append(
                AmazonMatch(
                    index=idx,
                    title=ap.get("title", ""),
                    price=float(ap.get("price", 0)) if ap.get("price") else 0,
                    reviews=ap.get("review_count", ap.get("reviews", 0)),
                    similarity=item.get("similarity", 0),
                    reason=item.get("reason", ""),
                    asin=ap.get("asin"),
                )
            )

    # Calculate market price from similar products (60%+ similarity)
    high_similarity = [m for m in matches if m.similarity >= 60]
    if high_similarity:
        prices = [m.price for m in high_similarity if m.price > 0]
        if prices:
            # Weight by similarity and log of reviews
            import math
            weighted_prices = []
            weights = []
            for m in high_similarity:
                if m.price > 0:
                    weight = (m.similarity / 100) * (1 + math.log10(m.reviews + 1))
                    weighted_prices.append(m.price * weight)
                    weights.append(weight)

            weighted_median = sum(weighted_prices) / sum(weights) if weights else None
            market_price = {
                "weighted_median": round(weighted_median, 2) if weighted_median else None,
                "min": round(min(prices), 2),
                "max": round(max(prices), 2),
            }
        else:
            market_price = {"weighted_median": None, "min": None, "max": None}
    else:
        market_price = {"weighted_median": None, "min": None, "max": None}

    return AmazonAnalysis(
        similar_products=matches,
        market_price=market_price,
        sample_size=len(high_similarity),
    )


async def score_keyword_relevance(
    keywords: list[str],
    product_understanding: ProductUnderstanding,
) -> list[KeywordScore]:
    """Score how relevant keywords are to our product.

    Args:
        keywords: List of keywords to score
        product_understanding: Our understanding of the product

    Returns:
        List of KeywordScore with relevance 0-100
    """
    keyword_list = "\n".join(f"- {kw}" for kw in keywords[:15])  # Limit to 15

    messages = [
        {
            "role": "system",
            "content": """You score keyword relevance for e-commerce advertising.
A keyword is relevant if someone searching for it would want to buy our specific product.""",
        },
        {
            "role": "user",
            "content": f"""Score these keywords for our product.

Our Product:
- Type: {product_understanding.product_type}
- Style: {', '.join(product_understanding.style)}
- Materials: {', '.join(product_understanding.materials)}
- Use cases: {', '.join(product_understanding.use_cases)}

Keywords to score:
{keyword_list}

Rate each keyword's relevance (0-100):
- 90-100: Perfect match - searcher wants exactly our product
- 70-89: Strong match - high purchase intent for our product
- 50-69: Moderate - might want our product
- 30-49: Weak - low intent for our specific product
- <30: Poor - different product or wrong intent

Return JSON:
{{
  "scores": [
    {{"keyword": "keyword text", "relevance": 85, "reason": "brief reason"}}
  ]
}}""",
        },
    ]

    result = await _call_openrouter(messages, temperature=0.2, max_tokens=4000)

    scores = []
    for item in result.get("scores", []):
        scores.append(
            KeywordScore(
                keyword=item.get("keyword", ""),
                relevance=item.get("relevance", 0),
                reason=item.get("reason", ""),
            )
        )

    return scores


async def filter_related_keywords(
    related_keywords: list[str],
    product_understanding: ProductUnderstanding,
    min_relevance: int = 50,
) -> list[str]:
    """Filter related keywords to only relevant ones.

    Args:
        related_keywords: Keywords from Google Ads API
        product_understanding: Our product understanding
        min_relevance: Minimum relevance score to keep

    Returns:
        List of relevant keywords
    """
    if not related_keywords:
        return []

    scores = await score_keyword_relevance(related_keywords, product_understanding)

    return [s.keyword for s in scores if s.relevance >= min_relevance]


async def generate_viability_assessment(
    product_name: str,
    cost: float,
    market_price: dict,
    best_keyword: dict | None,
    keyword_count: int,
    amazon_match_count: int,
) -> dict:
    """Generate a viability assessment with pros, cons, and recommendation.

    Args:
        product_name: Product name
        cost: Our cost
        market_price: Market price dict with weighted_median, min, max
        best_keyword: Best keyword dict with volume, cpc, relevance
        keyword_count: Total keywords found
        amazon_match_count: Number of similar Amazon products

    Returns:
        Dict with score, pros, cons, recommendation
    """
    median = market_price.get("weighted_median")
    margin_pct = ((median - cost) / median * 100) if median and median > cost else 0

    messages = [
        {
            "role": "system",
            "content": """You assess product viability for e-commerce dropshipping.
Consider margin, competition, keyword availability, and market validation.""",
        },
        {
            "role": "user",
            "content": f"""Assess this product's viability:

Product: {product_name}
Cost: ${cost:.2f}
Market Price: ${median:.2f} (range: ${market_price.get('min', 'N/A')}-${market_price.get('max', 'N/A')})
Margin: {margin_pct:.0f}%

Best Keyword: {best_keyword.get('keyword', 'N/A') if best_keyword else 'None found'}
- Volume: {best_keyword.get('volume', 'N/A') if best_keyword else 'N/A'}/month
- CPC: ${best_keyword.get('cpc', 'N/A') if best_keyword else 'N/A'}
- Relevance: {best_keyword.get('relevance', 'N/A') if best_keyword else 'N/A'}%

Total Keywords Found: {keyword_count}
Similar Amazon Products: {amazon_match_count}

Return JSON:
{{
  "score": 0-100,
  "pros": ["pro 1", "pro 2", ...],
  "cons": ["con 1", "con 2", ...],
  "recommendation": "launch|maybe|skip",
  "summary": "one sentence summary"
}}""",
        },
    ]

    result = await _call_openrouter(messages, temperature=0.3)

    return {
        "score": result.get("score", 50),
        "pros": result.get("pros", []),
        "cons": result.get("cons", []),
        "recommendation": result.get("recommendation", "maybe"),
        "summary": result.get("summary", ""),
    }
