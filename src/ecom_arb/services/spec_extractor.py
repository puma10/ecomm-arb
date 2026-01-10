"""Product spec extraction and comparison.

Extracts quantitative and qualitative specs from product titles/descriptions
and compares products for similarity scoring.
"""

import re
import logging
from dataclasses import dataclass, field
from decimal import Decimal

logger = logging.getLogger(__name__)


@dataclass
class ProductSpecs:
    """Extracted product specifications."""

    # Quantitative
    weight_grams: int | None = None
    capacity_ml: int | None = None
    power_watts: int | None = None
    lumens: int | None = None
    battery_mah: int | None = None
    length_cm: float | None = None
    width_cm: float | None = None
    height_cm: float | None = None
    quantity: int | None = None  # pieces in set

    # Qualitative
    material: str | None = None
    power_source: str | None = None  # usb, battery, plug-in, solar
    connectivity: str | None = None  # bluetooth, wifi, wired
    features: list[str] = field(default_factory=list)
    color: str | None = None
    style: str | None = None
    product_type: str | None = None  # lamp, speaker, charger, etc.

    # Raw for debugging
    raw_title: str = ""


# Regex patterns for spec extraction
PATTERNS = {
    # Weight: 200g, 1.5kg, 200 grams
    "weight_grams": [
        (r"(\d+(?:\.\d+)?)\s*kg\b", lambda m: int(float(m.group(1)) * 1000)),
        (r"(\d+(?:\.\d+)?)\s*g(?:rams?)?\b", lambda m: int(float(m.group(1)))),
        (r"(\d+(?:\.\d+)?)\s*oz\b", lambda m: int(float(m.group(1)) * 28.35)),
        (r"(\d+(?:\.\d+)?)\s*lbs?\b", lambda m: int(float(m.group(1)) * 453.6)),
    ],

    # Capacity: 150ml, 1.5L, 500 ml
    "capacity_ml": [
        (r"(\d+(?:\.\d+)?)\s*l(?:iter)?s?\b", lambda m: int(float(m.group(1)) * 1000)),
        (r"(\d+(?:\.\d+)?)\s*ml\b", lambda m: int(float(m.group(1)))),
        (r"(\d+(?:\.\d+)?)\s*oz\b", lambda m: int(float(m.group(1)) * 29.57)),  # fluid oz
    ],

    # Power: 10W, 100 watts
    "power_watts": [
        (r"(\d+(?:\.\d+)?)\s*w(?:atts?)?\b", lambda m: int(float(m.group(1)))),
    ],

    # Lumens: 1000lm, 500 lumens
    "lumens": [
        (r"(\d+)\s*(?:lm|lumens?)\b", lambda m: int(m.group(1))),
    ],

    # Battery: 2000mAh, 5000 mah
    "battery_mah": [
        (r"(\d+)\s*mah\b", lambda m: int(m.group(1))),
    ],

    # Dimensions: 10cm, 5.5 inches, 100mm
    "length_cm": [
        (r"(\d+(?:\.\d+)?)\s*cm\b", lambda m: float(m.group(1))),
        (r"(\d+(?:\.\d+)?)\s*mm\b", lambda m: float(m.group(1)) / 10),
        (r"(\d+(?:\.\d+)?)\s*(?:inch(?:es)?|in|\")\b", lambda m: float(m.group(1)) * 2.54),
        (r"(\d+(?:\.\d+)?)\s*m\b", lambda m: float(m.group(1)) * 100),
    ],

    # Quantity: 3pcs, 5 pack, set of 2
    "quantity": [
        (r"(\d+)\s*(?:pcs?|pieces?|pack|count)\b", lambda m: int(m.group(1))),
        (r"set\s*(?:of\s*)?(\d+)\b", lambda m: int(m.group(1))),
        (r"(\d+)\s*(?:in\s*1|in1)\b", lambda m: int(m.group(1))),
    ],
}

# Material keywords
MATERIALS = {
    "plastic": ["plastic", "abs", "pvc", "acrylic", "polycarbonate", "resin"],
    "metal": ["metal", "aluminum", "aluminium", "steel", "stainless", "iron", "brass", "copper", "zinc", "alloy"],
    "wood": ["wood", "wooden", "bamboo", "oak", "pine", "walnut", "log", "timber", "mdf"],
    "fabric": ["fabric", "cotton", "polyester", "nylon", "canvas", "leather", "linen", "velvet", "mesh"],
    "silicone": ["silicone", "rubber", "tpe", "gel"],
    "glass": ["glass", "crystal"],
    "ceramic": ["ceramic", "porcelain", "cement", "concrete", "stone", "marble"],
}

# Power source keywords
POWER_SOURCES = {
    "usb": ["usb", "usb-c", "type-c", "micro usb", "usb powered"],
    "battery": ["battery", "batteries", "aaa", "aa", "18650", "rechargeable"],
    "plug-in": ["plug", "ac", "110v", "220v", "wall powered", "corded"],
    "solar": ["solar", "solar powered"],
}

# Connectivity keywords
CONNECTIVITY = {
    "bluetooth": ["bluetooth", "bt", "wireless"],
    "wifi": ["wifi", "wi-fi", "smart", "app control"],
    "wired": ["wired", "cable", "aux", "3.5mm"],
    "remote": ["remote", "ir", "rf"],
}

# Feature keywords
FEATURES = [
    "rgb", "led", "touch", "dimmable", "timer", "waterproof", "ip65", "ip67", "ip68",
    "portable", "foldable", "adjustable", "rechargeable", "cordless", "magnetic",
    "360", "rotating", "sensor", "motion", "voice control", "alexa", "google home",
    "night light", "projector", "humidifier", "aromatherapy", "speaker",
    "ceiling", "wall", "table", "desk", "floor", "pendant", "chandelier",
    "outdoor", "indoor", "bathroom", "kitchen", "bedroom", "nursery", "garden",
    "vintage", "modern", "industrial", "minimalist", "japanese", "nordic",
    "charger", "wireless charging", "fast charging",
]

# Product type keywords (for type matching)
PRODUCT_TYPES = {
    "lamp": ["lamp", "light", "lighting", "bulb", "fixture", "lantern", "sconce"],
    "speaker": ["speaker", "soundbar", "subwoofer", "audio"],
    "charger": ["charger", "charging", "power bank", "adapter"],
    "projector": ["projector", "projection"],
    "humidifier": ["humidifier", "diffuser", "mist", "aroma"],
    "organizer": ["organizer", "storage", "rack", "shelf", "holder", "stand"],
    "cable": ["cable", "cord", "wire", "usb"],
}


def extract_specs(title: str, description: str = "", weight_grams: int | None = None) -> ProductSpecs:
    """Extract product specs from title and description.

    Args:
        title: Product title
        description: Product description (optional)
        weight_grams: Known weight in grams (e.g., from CJ data)

    Returns:
        ProductSpecs with extracted values
    """
    text = f"{title} {description}".lower()
    specs = ProductSpecs(raw_title=title)

    # Use provided weight if available
    if weight_grams:
        specs.weight_grams = weight_grams

    # Extract quantitative specs using regex
    for field_name, patterns in PATTERNS.items():
        if field_name == "weight_grams" and specs.weight_grams:
            continue  # Skip if already set

        for pattern, converter in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    setattr(specs, field_name, converter(match))
                    break
                except (ValueError, TypeError):
                    continue

    # Extract material
    for material, keywords in MATERIALS.items():
        if any(kw in text for kw in keywords):
            specs.material = material
            break

    # Extract power source
    for source, keywords in POWER_SOURCES.items():
        if any(kw in text for kw in keywords):
            specs.power_source = source
            break

    # Extract connectivity
    for conn, keywords in CONNECTIVITY.items():
        if any(kw in text for kw in keywords):
            specs.connectivity = conn
            break

    # Extract features
    specs.features = [f for f in FEATURES if f in text]

    # Extract product type
    for ptype, keywords in PRODUCT_TYPES.items():
        if any(kw in text for kw in keywords):
            specs.product_type = ptype
            break

    return specs


def calculate_similarity(spec1: ProductSpecs, spec2: ProductSpecs) -> float:
    """Calculate similarity score between two products.

    Returns:
        Similarity score from 0.0 to 1.0
    """
    # Product type is critical - different types = very low similarity
    if spec1.product_type and spec2.product_type:
        if spec1.product_type != spec2.product_type:
            return 0.05  # Different product types = near zero similarity
        type_match = True
    else:
        type_match = False

    scores = []
    weights = []

    # Product type match bonus (if both have types and match)
    if type_match:
        scores.append(1.0)
        weights.append(0.30)  # 30% weight for matching type

    # Quantitative comparisons (weighted by importance)
    quant_fields = [
        ("weight_grams", 0.15, 0.5),  # field, weight, tolerance (50% - more lenient)
        ("capacity_ml", 0.10, 0.4),
        ("power_watts", 0.08, 0.4),
        ("lumens", 0.08, 0.4),
        ("battery_mah", 0.08, 0.4),
        ("quantity", 0.06, 0.3),
    ]

    for field_name, weight, tolerance in quant_fields:
        val1 = getattr(spec1, field_name)
        val2 = getattr(spec2, field_name)

        if val1 is not None and val2 is not None:
            # Calculate how close they are within tolerance
            max_val = max(val1, val2)
            if max_val > 0:
                diff_pct = abs(val1 - val2) / max_val
                score = max(0, 1 - (diff_pct / tolerance))
                scores.append(score)
                weights.append(weight)

    # Qualitative comparisons (exact match or not)
    qual_fields = [
        ("material", 0.10),
        ("power_source", 0.08),
        ("connectivity", 0.08),
    ]

    for field_name, weight in qual_fields:
        val1 = getattr(spec1, field_name)
        val2 = getattr(spec2, field_name)

        if val1 is not None and val2 is not None:
            score = 1.0 if val1 == val2 else 0.0
            scores.append(score)
            weights.append(weight)

    # Feature overlap (Jaccard similarity)
    if spec1.features and spec2.features:
        set1 = set(spec1.features)
        set2 = set(spec2.features)
        intersection = len(set1 & set2)
        union = len(set1 | set2)
        if union > 0:
            feature_score = intersection / union
            scores.append(feature_score)
            weights.append(0.15)

    # If no specs could be compared, use a baseline based on having same type
    if not scores:
        return 0.3 if type_match else 0.1

    total_weight = sum(weights)
    if total_weight == 0:
        return 0.3 if type_match else 0.1

    weighted_sum = sum(s * w for s, w in zip(scores, weights))
    return weighted_sum / total_weight


def filter_similar_products(
    source_specs: ProductSpecs,
    amazon_products: list[dict],
    min_similarity: float = 0.3,
) -> list[tuple[dict, ProductSpecs, float]]:
    """Filter Amazon products by similarity to source product.

    Args:
        source_specs: Specs of the source product (CJ)
        amazon_products: List of Amazon product dicts with 'title', 'price', etc.
        min_similarity: Minimum similarity score to include (0.0-1.0)

    Returns:
        List of (product, specs, similarity_score) tuples, sorted by similarity desc
    """
    results = []

    for product in amazon_products:
        title = product.get("title", "")
        amazon_specs = extract_specs(title)
        similarity = calculate_similarity(source_specs, amazon_specs)

        if similarity >= min_similarity:
            results.append((product, amazon_specs, similarity))

    # Sort by similarity descending
    results.sort(key=lambda x: x[2], reverse=True)

    return results


def calculate_market_price(
    similar_products: list[tuple[dict, ProductSpecs, float]],
    weight_by_similarity: bool = True,
    weight_by_reviews: bool = True,
) -> dict:
    """Calculate market price from similar products.

    Args:
        similar_products: Output from filter_similar_products
        weight_by_similarity: Weight prices by similarity score
        weight_by_reviews: Weight prices by review count

    Returns:
        Dict with weighted_median, weighted_avg, min, max, sample_size
    """
    if not similar_products:
        return {
            "weighted_median": None,
            "weighted_avg": None,
            "min": None,
            "max": None,
            "sample_size": 0,
        }

    prices = []
    weights = []

    for product, specs, similarity in similar_products:
        price = product.get("price")
        if price is None:
            continue

        price = float(price)
        weight = 1.0

        if weight_by_similarity:
            weight *= similarity

        if weight_by_reviews:
            reviews = product.get("review_count", 0)
            # Log scale for reviews: 1 review = 1, 100 reviews = 2, 10000 = 3
            review_weight = 1 + (0.5 * (len(str(reviews + 1)) - 1))
            weight *= review_weight

        prices.append(price)
        weights.append(weight)

    if not prices:
        return {
            "weighted_median": None,
            "weighted_avg": None,
            "min": None,
            "max": None,
            "sample_size": 0,
        }

    # Weighted average
    total_weight = sum(weights)
    weighted_avg = sum(p * w for p, w in zip(prices, weights)) / total_weight

    # Weighted median (approximate using sorted weighted values)
    sorted_pairs = sorted(zip(prices, weights))
    cumsum = 0
    weighted_median = sorted_pairs[0][0]
    half_weight = total_weight / 2
    for price, weight in sorted_pairs:
        cumsum += weight
        if cumsum >= half_weight:
            weighted_median = price
            break

    return {
        "weighted_median": round(weighted_median, 2),
        "weighted_avg": round(weighted_avg, 2),
        "min": round(min(prices), 2),
        "max": round(max(prices), 2),
        "sample_size": len(prices),
    }
