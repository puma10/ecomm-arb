"""Keyword exploration service for product advertising.

Recursively explores Google Ads Keyword Planner to find optimal keywords:
- Start with LLM-generated seed keywords
- Expand through related keywords
- Score relevance with LLM
- Build prioritized keyword opportunity map
"""

import asyncio
import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from ecom_arb.config import get_settings
from ecom_arb.integrations.google_ads import (
    CPCEstimate,
    GoogleAdsClient,
    GoogleAdsConfig,
    GoogleAdsError,
)
from ecom_arb.services.llm_analyzer import (
    ProductUnderstanding,
    score_keyword_relevance,
)

logger = logging.getLogger(__name__)


@dataclass
class KeywordOpportunity:
    """A keyword with advertising metrics and relevance."""

    keyword: str
    monthly_volume: int
    avg_cpc: float
    competition: str  # LOW, MEDIUM, HIGH
    relevance_score: int  # 0-100 from LLM
    relevance_reason: str
    tier: str  # exact, specific, broad
    source: str  # seed, expanded, related
    depth: int  # 0 = seed, 1+ = expansion depth

    @property
    def opportunity_score(self) -> float:
        """Combined score factoring volume, CPC efficiency, and relevance.

        Higher is better:
        - High volume = good (more potential customers)
        - Low CPC = good (cheaper ads)
        - High relevance = good (better conversion)
        """
        if self.monthly_volume == 0:
            return 0.0

        # Volume factor (log scale to handle wide range)
        import math
        volume_factor = math.log10(max(self.monthly_volume, 10)) / 6  # Normalize ~0-1

        # CPC efficiency (inverse, capped)
        cpc_factor = 1 / (1 + self.avg_cpc)  # Lower CPC = higher factor

        # Relevance (0-100 -> 0-1)
        relevance_factor = self.relevance_score / 100

        # Weighted combination
        return (
            volume_factor * 0.3
            + cpc_factor * 0.2
            + relevance_factor * 0.5
        ) * 100


@dataclass
class ExplorationResult:
    """Results from keyword exploration."""

    keywords: list[KeywordOpportunity]
    total_explored: int
    depth_reached: int
    errors: list[str] = field(default_factory=list)

    @property
    def by_tier(self) -> dict[str, list[KeywordOpportunity]]:
        """Group keywords by tier."""
        result: dict[str, list[KeywordOpportunity]] = {
            "exact": [],
            "specific": [],
            "broad": [],
        }
        for kw in self.keywords:
            if kw.tier in result:
                result[kw.tier].append(kw)
        return result

    @property
    def top_opportunities(self) -> list[KeywordOpportunity]:
        """Top 10 keywords by opportunity score."""
        return sorted(self.keywords, key=lambda k: k.opportunity_score, reverse=True)[:10]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for JSON serialization."""
        return {
            "total_keywords": len(self.keywords),
            "total_explored": self.total_explored,
            "depth_reached": self.depth_reached,
            "errors": self.errors,
            "top_opportunities": [
                {
                    "keyword": k.keyword,
                    "volume": k.monthly_volume,
                    "cpc": k.avg_cpc,
                    "relevance": k.relevance_score,
                    "opportunity_score": round(k.opportunity_score, 1),
                    "tier": k.tier,
                }
                for k in self.top_opportunities
            ],
            "by_tier": {
                tier: [
                    {
                        "keyword": k.keyword,
                        "volume": k.monthly_volume,
                        "cpc": k.avg_cpc,
                        "relevance": k.relevance_score,
                        "reason": k.relevance_reason,
                    }
                    for k in keywords
                ]
                for tier, keywords in self.by_tier.items()
            },
        }


class KeywordExplorer:
    """Explores keyword opportunities for product advertising.

    Uses Google Ads Keyword Planner to discover related keywords,
    then scores them with LLM for relevance to the specific product.

    Algorithm:
    1. Start with LLM seed keywords (exact, specific, broad tiers)
    2. Query Google Ads for each seed to get volume/CPC + related keywords
    3. Score all keywords with LLM for product relevance
    4. Expand into related keywords (up to max_depth)
    5. Return prioritized opportunity map
    """

    def __init__(
        self,
        google_ads_client: GoogleAdsClient | None = None,
        max_depth: int = 2,
        min_relevance: int = 50,
        max_keywords_per_tier: int = 20,
    ):
        """Initialize keyword explorer.

        Args:
            google_ads_client: Pre-configured Google Ads client
            max_depth: Maximum expansion depth (0 = seeds only)
            min_relevance: Minimum LLM relevance score to keep
            max_keywords_per_tier: Max keywords to keep per tier
        """
        self.max_depth = max_depth
        self.min_relevance = min_relevance
        self.max_keywords_per_tier = max_keywords_per_tier

        if google_ads_client:
            self.google_client = google_ads_client
        else:
            # Initialize from settings
            settings = get_settings()
            if settings.google_ads_customer_id:
                config = GoogleAdsConfig(
                    client_id=settings.google_ads_client_id,
                    client_secret=settings.google_ads_client_secret,
                    refresh_token=settings.google_ads_refresh_token,
                    developer_token=settings.google_ads_developer_token,
                    customer_id=settings.google_ads_customer_id,
                )
                self.google_client = GoogleAdsClient(config)
            else:
                self.google_client = None

    async def explore(
        self,
        product_understanding: ProductUnderstanding,
    ) -> ExplorationResult:
        """Explore keyword opportunities for a product.

        Args:
            product_understanding: LLM's understanding of the product

        Returns:
            ExplorationResult with prioritized keywords
        """
        if not self.google_client or self.max_depth < 0:
            logger.warning("Google Ads client not configured - returning seed keywords only")
            return await self._explore_without_google(product_understanding)

        # For max_depth=0, skip Google Ads and just return scored seed keywords
        if self.max_depth == 0:
            logger.info("max_depth=0, skipping Google Ads - returning seed keywords with LLM scoring only")
            return await self._explore_without_google(product_understanding)

        all_keywords: dict[str, KeywordOpportunity] = {}
        explored_count = 0
        max_depth_reached = 0
        errors: list[str] = []

        # Get seed keywords from product understanding
        seed_keywords = product_understanding.seed_keywords

        # Process each tier
        for tier, keywords in seed_keywords.items():
            if not keywords:
                continue

            logger.info(f"Exploring {tier} tier: {len(keywords)} seeds")

            # Depth 0: Query seeds
            try:
                estimates = self._get_keyword_estimates(keywords)
                explored_count += len(keywords)

                # Take only top 10 by volume for quick analysis
                # Deep analysis can be triggered manually for promising products
                sorted_estimates = sorted(estimates, key=lambda e: e.avg_monthly_searches, reverse=True)
                top_estimates = sorted_estimates[:10]

                # Score relevance with LLM (just 10 keywords = 1 LLM call)
                scored = await self._score_keywords(
                    [e.keyword for e in top_estimates],
                    product_understanding,
                )

                estimates = top_estimates

                # Build opportunities
                for estimate in estimates:
                    relevance = scored.get(estimate.keyword, {"relevance": 0, "reason": ""})
                    if relevance["relevance"] >= self.min_relevance:
                        kw_key = estimate.keyword.lower()
                        if kw_key not in all_keywords:
                            all_keywords[kw_key] = KeywordOpportunity(
                                keyword=estimate.keyword,
                                monthly_volume=estimate.avg_monthly_searches,
                                avg_cpc=float(estimate.avg_cpc),
                                competition=estimate.competition,
                                relevance_score=relevance["relevance"],
                                relevance_reason=relevance["reason"],
                                tier=tier,
                                source="seed",
                                depth=0,
                            )

                # Skip recursive expansion for quick analysis
                # Deep analysis endpoint can enable this later
                # if self.max_depth > 1:
                #     expansion_keywords = await self._expand_keywords(...)
                max_depth_reached = 1

            except GoogleAdsError as e:
                error_msg = f"Google Ads error for {tier} tier: {str(e)}"
                logger.warning(error_msg)
                errors.append(error_msg)
            except Exception as e:
                error_msg = f"Error exploring {tier} tier: {str(e)}"
                logger.exception(error_msg)
                errors.append(error_msg)

        # Sort by opportunity score and limit per tier
        result_keywords = self._limit_by_tier(list(all_keywords.values()))

        return ExplorationResult(
            keywords=result_keywords,
            total_explored=explored_count,
            depth_reached=max_depth_reached,
            errors=errors,
        )

    async def _explore_without_google(
        self,
        product_understanding: ProductUnderstanding,
    ) -> ExplorationResult:
        """Return seed keywords without Google Ads enrichment."""
        keywords = []

        for tier, tier_keywords in product_understanding.seed_keywords.items():
            for kw in tier_keywords:
                keywords.append(
                    KeywordOpportunity(
                        keyword=kw,
                        monthly_volume=0,  # Unknown without Google Ads
                        avg_cpc=0.0,
                        competition="UNKNOWN",
                        relevance_score=90 if tier == "exact" else 70 if tier == "specific" else 50,
                        relevance_reason="Seed keyword from LLM (no volume data)",
                        tier=tier,
                        source="seed",
                        depth=0,
                    )
                )

        return ExplorationResult(
            keywords=keywords,
            total_explored=len(keywords),
            depth_reached=0,
            errors=["Google Ads client not configured"],
        )

    def _get_keyword_estimates(self, keywords: list[str]) -> list[CPCEstimate]:
        """Get keyword estimates from Google Ads.

        The Keyword Planner returns related keywords beyond just the input.
        """
        if not keywords:
            return []

        # Limit to avoid quota issues
        keywords = keywords[:10]

        try:
            return self.google_client.get_keyword_cpc_estimates(keywords)
        except GoogleAdsError:
            raise
        except Exception as e:
            logger.warning(f"Failed to get keyword estimates: {e}")
            return []

    async def _score_keywords(
        self,
        keywords: list[str],
        product_understanding: ProductUnderstanding,
    ) -> dict[str, dict]:
        """Score keywords for relevance using LLM.

        Returns dict mapping keyword -> {relevance, reason}
        """
        if not keywords:
            return {}

        # Batch in groups of 15 (keep responses within token limits)
        result = {}
        for i in range(0, len(keywords), 15):
            batch = keywords[i:i + 15]
            try:
                scores = await score_keyword_relevance(batch, product_understanding)
                for score in scores:
                    result[score.keyword] = {
                        "relevance": score.relevance,
                        "reason": score.reason,
                    }
            except Exception as e:
                logger.warning(f"Failed to score keywords: {e}")
                # Return neutral scores on failure
                for kw in batch:
                    result[kw] = {"relevance": 50, "reason": "Scoring failed"}

        return result

    async def _expand_keywords(
        self,
        estimates: list[CPCEstimate],
        product_understanding: ProductUnderstanding,
        tier: str,
        current_depth: int,
        all_keywords: dict[str, KeywordOpportunity],
    ) -> int:
        """Recursively expand into related keywords.

        Returns count of keywords explored.
        """
        if current_depth > self.max_depth:
            return 0

        explored = 0

        # Take top keywords by volume for expansion
        sorted_estimates = sorted(estimates, key=lambda e: e.avg_monthly_searches, reverse=True)
        expansion_seeds = [e.keyword for e in sorted_estimates[:5]]  # Top 5 for expansion

        if not expansion_seeds:
            return 0

        try:
            # Get related keywords
            related_estimates = self._get_keyword_estimates(expansion_seeds)
            explored += len(expansion_seeds)

            # Filter out already-seen keywords
            new_estimates = [
                e for e in related_estimates
                if e.keyword.lower() not in all_keywords
            ]

            if not new_estimates:
                return explored

            # Score relevance
            scored = await self._score_keywords(
                [e.keyword for e in new_estimates],
                product_understanding,
            )

            # Build opportunities
            for estimate in new_estimates:
                relevance = scored.get(estimate.keyword, {"relevance": 0, "reason": ""})
                if relevance["relevance"] >= self.min_relevance:
                    kw_key = estimate.keyword.lower()
                    all_keywords[kw_key] = KeywordOpportunity(
                        keyword=estimate.keyword,
                        monthly_volume=estimate.avg_monthly_searches,
                        avg_cpc=float(estimate.avg_cpc),
                        competition=estimate.competition,
                        relevance_score=relevance["relevance"],
                        relevance_reason=relevance["reason"],
                        tier=tier,
                        source="expanded",
                        depth=current_depth,
                    )

            # Continue expansion if we found good keywords
            if current_depth < self.max_depth:
                high_relevance = [e for e in new_estimates if scored.get(e.keyword, {}).get("relevance", 0) >= 70]
                if high_relevance:
                    deeper = await self._expand_keywords(
                        high_relevance,
                        product_understanding,
                        tier,
                        current_depth + 1,
                        all_keywords,
                    )
                    explored += deeper

        except Exception as e:
            logger.warning(f"Expansion failed at depth {current_depth}: {e}")

        return explored

    def _limit_by_tier(
        self,
        keywords: list[KeywordOpportunity],
    ) -> list[KeywordOpportunity]:
        """Limit keywords per tier, keeping best opportunities."""
        by_tier: dict[str, list[KeywordOpportunity]] = {}

        for kw in keywords:
            if kw.tier not in by_tier:
                by_tier[kw.tier] = []
            by_tier[kw.tier].append(kw)

        result = []
        for tier, tier_keywords in by_tier.items():
            # Sort by opportunity score
            sorted_kw = sorted(tier_keywords, key=lambda k: k.opportunity_score, reverse=True)
            result.extend(sorted_kw[:self.max_keywords_per_tier])

        return result


async def explore_product_keywords(
    product_understanding: ProductUnderstanding,
    max_depth: int = 2,
    min_relevance: int = 50,
) -> ExplorationResult:
    """Convenience function to explore keywords for a product.

    Args:
        product_understanding: LLM's understanding of the product
        max_depth: How deep to explore related keywords
        min_relevance: Minimum relevance score to include

    Returns:
        ExplorationResult with prioritized keywords
    """
    explorer = KeywordExplorer(
        max_depth=max_depth,
        min_relevance=min_relevance,
    )
    return await explorer.explore(product_understanding)
