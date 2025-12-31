"""Google Ads API client for keyword research and campaign management.

Implements SPIKE-002 requirements:
- Keyword Planner CPC estimates
- Campaign creation
- Campaign pause/enable
- Rate limit handling

See: PLAN/04_risks_and_spikes.md (SPIKE-002)
See: PLAN/03_decisions.md (ADR-005)
"""

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Optional

from google.ads.googleads.client import GoogleAdsClient as GoogleAdsApiClient
from google.ads.googleads.errors import GoogleAdsException


class CampaignStatus(Enum):
    """Campaign status values."""

    ENABLED = "ENABLED"
    PAUSED = "PAUSED"
    REMOVED = "REMOVED"


class GoogleAdsError(Exception):
    """Wrapper for Google Ads API errors."""

    def __init__(self, message: str, request_id: str = "", is_rate_limit: bool = False):
        super().__init__(message)
        self.request_id = request_id
        self.is_rate_limit_error = is_rate_limit

    def __str__(self) -> str:
        if self.request_id:
            return f"{super().__str__()} (request_id: {self.request_id})"
        return super().__str__()


@dataclass
class CPCEstimate:
    """CPC estimate for a keyword from Keyword Planner."""

    keyword: str
    avg_monthly_searches: int
    competition: str  # LOW, MEDIUM, HIGH
    low_cpc: Decimal  # Low top-of-page bid
    high_cpc: Decimal  # High top-of-page bid

    @property
    def avg_cpc(self) -> Decimal:
        """Average of low and high CPC estimates."""
        return (self.low_cpc + self.high_cpc) / 2

    @classmethod
    def from_micros(
        cls,
        keyword: str,
        avg_monthly_searches: int,
        competition: str,
        low_top_of_page_bid_micros: int,
        high_top_of_page_bid_micros: int,
    ) -> "CPCEstimate":
        """Create from API micros values (1 dollar = 1,000,000 micros)."""
        return cls(
            keyword=keyword,
            avg_monthly_searches=avg_monthly_searches,
            competition=competition,
            low_cpc=Decimal(low_top_of_page_bid_micros) / Decimal(1_000_000),
            high_cpc=Decimal(high_top_of_page_bid_micros) / Decimal(1_000_000),
        )


@dataclass
class Campaign:
    """Google Ads campaign."""

    id: str
    name: str
    status: CampaignStatus
    daily_budget_cents: int = 0  # Budget in cents


@dataclass
class GoogleAdsConfig:
    """Configuration for Google Ads API access."""

    client_id: str
    client_secret: str
    refresh_token: str
    developer_token: str
    customer_id: str  # Format: 123-456-7890

    def __post_init__(self):
        """Validate configuration."""
        if not self.client_id:
            raise ValueError("client_id is required")
        if not self.client_secret:
            raise ValueError("client_secret is required")
        if not self.refresh_token:
            raise ValueError("refresh_token is required")
        if not self.developer_token:
            raise ValueError("developer_token is required")
        if not self.customer_id:
            raise ValueError("customer_id is required")

    @property
    def customer_id_numeric(self) -> str:
        """Customer ID without hyphens for API calls."""
        return self.customer_id.replace("-", "")


class GoogleAdsClient:
    """Client for Google Ads API operations.

    Provides methods for:
    - Getting keyword CPC estimates from Keyword Planner
    - Creating and managing campaigns
    - Checking campaign status

    Usage:
        config = GoogleAdsConfig(
            client_id="...",
            client_secret="...",
            refresh_token="...",
            developer_token="...",
            customer_id="123-456-7890",
        )
        client = GoogleAdsClient(config)
        estimates = client.get_keyword_cpc_estimates(["fitness tracker"])
    """

    # Status code mapping from API integers
    _STATUS_MAP = {
        0: CampaignStatus.REMOVED,  # UNSPECIFIED
        1: CampaignStatus.REMOVED,  # UNKNOWN
        2: CampaignStatus.ENABLED,
        3: CampaignStatus.PAUSED,
        4: CampaignStatus.REMOVED,
    }

    # Competition level mapping
    _COMPETITION_MAP = {
        0: "UNSPECIFIED",
        1: "UNKNOWN",
        2: "LOW",
        3: "MEDIUM",
        4: "HIGH",
    }

    def __init__(self, config: GoogleAdsConfig):
        """Initialize client with configuration."""
        self.config = config
        self.customer_id = config.customer_id_numeric

        # Build credentials dict for google-ads library
        credentials = {
            "developer_token": config.developer_token,
            "client_id": config.client_id,
            "client_secret": config.client_secret,
            "refresh_token": config.refresh_token,
            "use_proto_plus": True,
        }

        self._client = GoogleAdsApiClient.load_from_dict(credentials)

    def _handle_exception(self, exc: GoogleAdsException) -> GoogleAdsError:
        """Convert GoogleAdsException to GoogleAdsError."""
        is_rate_limit = False

        # Check for rate limit errors
        if exc.failure and exc.failure.errors:
            for error in exc.failure.errors:
                if hasattr(error.error_code, "quota_error") and error.error_code.quota_error:
                    is_rate_limit = True
                    break

        return GoogleAdsError(
            message=str(exc),
            request_id=exc.request_id or "",
            is_rate_limit=is_rate_limit,
        )

    def get_keyword_cpc_estimates(self, keywords: list[str]) -> list[CPCEstimate]:
        """Get CPC estimates for keywords from Keyword Planner.

        Args:
            keywords: List of keywords to get estimates for.

        Returns:
            List of CPCEstimate objects with bid data.

        Raises:
            GoogleAdsError: If API call fails.
        """
        if not keywords:
            return []

        try:
            keyword_plan_idea_service = self._client.get_service(
                "KeywordPlanIdeaService"
            )

            request = self._client.get_type("GenerateKeywordIdeasRequest")
            request.customer_id = self.customer_id
            request.language = "languageConstants/1000"  # English
            request.geo_target_constants.append("geoTargetConstants/2840")  # US
            request.keyword_plan_network = (
                self._client.enums.KeywordPlanNetworkEnum.GOOGLE_SEARCH
            )

            # Add keywords
            request.keyword_seed.keywords.extend(keywords)

            response = keyword_plan_idea_service.generate_keyword_ideas(request=request)

            estimates = []
            for result in response.results:
                metrics = result.keyword_idea_metrics
                competition_value = (
                    int(metrics.competition) if metrics.competition else 0
                )

                estimate = CPCEstimate.from_micros(
                    keyword=result.text,
                    avg_monthly_searches=metrics.avg_monthly_searches or 0,
                    competition=self._COMPETITION_MAP.get(competition_value, "UNKNOWN"),
                    low_top_of_page_bid_micros=metrics.low_top_of_page_bid_micros or 0,
                    high_top_of_page_bid_micros=metrics.high_top_of_page_bid_micros or 0,
                )
                estimates.append(estimate)

            return estimates

        except GoogleAdsException as exc:
            raise self._handle_exception(exc)

    def create_campaign(
        self,
        name: str,
        daily_budget_cents: int,
        max_cpc_cents: int,
    ) -> Campaign:
        """Create a new Google Ads campaign.

        Args:
            name: Campaign name.
            daily_budget_cents: Daily budget in cents (e.g., 5000 = $50.00).
            max_cpc_cents: Maximum CPC bid in cents (e.g., 75 = $0.75).

        Returns:
            Created Campaign object.

        Raises:
            GoogleAdsError: If campaign creation fails.
        """
        try:
            # First create the budget
            campaign_budget_service = self._client.get_service("CampaignBudgetService")
            campaign_service = self._client.get_service("CampaignService")

            # Create budget
            budget_operation = self._client.get_type("CampaignBudgetOperation")
            budget = budget_operation.create
            budget.name = f"{name} Budget"
            budget.amount_micros = daily_budget_cents * 10_000  # cents to micros
            budget.delivery_method = (
                self._client.enums.BudgetDeliveryMethodEnum.STANDARD
            )

            budget_response = campaign_budget_service.mutate_campaign_budgets(
                customer_id=self.customer_id,
                operations=[budget_operation],
            )
            budget_resource_name = budget_response.results[0].resource_name

            # Create campaign
            campaign_operation = self._client.get_type("CampaignOperation")
            campaign = campaign_operation.create
            campaign.name = name
            campaign.campaign_budget = budget_resource_name
            campaign.advertising_channel_type = (
                self._client.enums.AdvertisingChannelTypeEnum.SEARCH
            )
            campaign.status = self._client.enums.CampaignStatusEnum.ENABLED

            # Set manual CPC bidding
            campaign.manual_cpc.enhanced_cpc_enabled = False

            response = campaign_service.mutate_campaigns(
                customer_id=self.customer_id,
                operations=[campaign_operation],
            )

            # Extract campaign ID from resource name
            resource_name = response.results[0].resource_name
            campaign_id = resource_name.split("/")[-1]

            return Campaign(
                id=campaign_id,
                name=name,
                status=CampaignStatus.ENABLED,
                daily_budget_cents=daily_budget_cents,
            )

        except GoogleAdsException as exc:
            raise self._handle_exception(exc)

    def set_campaign_status(self, campaign_id: str, status: CampaignStatus) -> bool:
        """Set campaign status (pause/enable).

        Args:
            campaign_id: Campaign ID to modify.
            status: New status (ENABLED or PAUSED).

        Returns:
            True if successful.

        Raises:
            GoogleAdsError: If status change fails.
        """
        try:
            campaign_service = self._client.get_service("CampaignService")

            campaign_operation = self._client.get_type("CampaignOperation")
            campaign = campaign_operation.update
            campaign.resource_name = (
                f"customers/{self.customer_id}/campaigns/{campaign_id}"
            )

            if status == CampaignStatus.ENABLED:
                campaign.status = self._client.enums.CampaignStatusEnum.ENABLED
            elif status == CampaignStatus.PAUSED:
                campaign.status = self._client.enums.CampaignStatusEnum.PAUSED
            else:
                campaign.status = self._client.enums.CampaignStatusEnum.REMOVED

            # Set field mask
            field_mask = self._client.get_type("FieldMask")
            field_mask.paths.append("status")
            campaign_operation.update_mask.CopyFrom(field_mask)

            campaign_service.mutate_campaigns(
                customer_id=self.customer_id,
                operations=[campaign_operation],
            )

            return True

        except GoogleAdsException as exc:
            raise self._handle_exception(exc)

    def get_campaign(self, campaign_id: str) -> Optional[Campaign]:
        """Get campaign details by ID.

        Args:
            campaign_id: Campaign ID to fetch.

        Returns:
            Campaign object or None if not found.

        Raises:
            GoogleAdsError: If API call fails.
        """
        try:
            ga_service = self._client.get_service("GoogleAdsService")

            query = f"""
                SELECT
                    campaign.id,
                    campaign.name,
                    campaign.status,
                    campaign_budget.amount_micros
                FROM campaign
                WHERE campaign.id = {campaign_id}
            """

            response = ga_service.search_stream(
                customer_id=self.customer_id,
                query=query,
            )

            for batch in response:
                for row in batch.results:
                    status_value = int(row.campaign.status)
                    return Campaign(
                        id=str(row.campaign.id),
                        name=row.campaign.name,
                        status=self._STATUS_MAP.get(status_value, CampaignStatus.REMOVED),
                        daily_budget_cents=int(row.campaign_budget.amount_micros / 10_000),
                    )

            return None

        except GoogleAdsException as exc:
            raise self._handle_exception(exc)

    def list_campaigns(self, include_removed: bool = False) -> list[Campaign]:
        """List all campaigns.

        Args:
            include_removed: Include removed campaigns in results.

        Returns:
            List of Campaign objects.

        Raises:
            GoogleAdsError: If API call fails.
        """
        try:
            ga_service = self._client.get_service("GoogleAdsService")

            query = """
                SELECT
                    campaign.id,
                    campaign.name,
                    campaign.status,
                    campaign_budget.amount_micros
                FROM campaign
            """

            if not include_removed:
                query += " WHERE campaign.status != 'REMOVED'"

            response = ga_service.search_stream(
                customer_id=self.customer_id,
                query=query,
            )

            campaigns = []
            for batch in response:
                for row in batch.results:
                    status_value = int(row.campaign.status)
                    campaigns.append(
                        Campaign(
                            id=str(row.campaign.id),
                            name=row.campaign.name,
                            status=self._STATUS_MAP.get(
                                status_value, CampaignStatus.REMOVED
                            ),
                            daily_budget_cents=int(
                                row.campaign_budget.amount_micros / 10_000
                            ),
                        )
                    )

            return campaigns

        except GoogleAdsException as exc:
            raise self._handle_exception(exc)
