"""Tests for Google Ads API client.

Tests cover:
- Client initialization
- Keyword Planner CPC estimates
- Campaign creation
- Campaign management (pause/enable)
- Error handling
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from ecom_arb.integrations.google_ads import (
    GoogleAdsClient,
    GoogleAdsConfig,
    CampaignStatus,
    CPCEstimate,
    Campaign,
    GoogleAdsError,
)


class TestGoogleAdsConfig:
    """Test configuration validation."""

    def test_config_from_settings(self):
        """Config loads from settings object."""
        config = GoogleAdsConfig(
            client_id="test-client-id.apps.googleusercontent.com",
            client_secret="test-secret",
            refresh_token="test-refresh-token",
            developer_token="test-dev-token",
            customer_id="123-456-7890",
        )
        assert config.client_id == "test-client-id.apps.googleusercontent.com"
        assert config.customer_id_numeric == "1234567890"

    def test_customer_id_normalization(self):
        """Customer ID gets hyphens stripped for API calls."""
        config = GoogleAdsConfig(
            client_id="test",
            client_secret="test",
            refresh_token="test",
            developer_token="test",
            customer_id="748-680-7809",
        )
        assert config.customer_id_numeric == "7486807809"

    def test_invalid_config_raises(self):
        """Empty credentials raise validation error."""
        with pytest.raises(ValueError):
            GoogleAdsConfig(
                client_id="",
                client_secret="test",
                refresh_token="test",
                developer_token="test",
                customer_id="123-456-7890",
            )


class TestGoogleAdsClient:
    """Test Google Ads client operations."""

    @pytest.fixture
    def config(self):
        """Valid test config."""
        return GoogleAdsConfig(
            client_id="test-client-id.apps.googleusercontent.com",
            client_secret="test-secret",
            refresh_token="test-refresh-token",
            developer_token="test-dev-token",
            customer_id="123-456-7890",
        )

    @pytest.fixture
    def mock_google_ads_client(self):
        """Mock the google-ads library client."""
        with patch("ecom_arb.integrations.google_ads.GoogleAdsApiClient") as mock:
            # load_from_dict is a class method that returns a client instance
            mock_instance = MagicMock()
            mock.load_from_dict.return_value = mock_instance
            yield mock

    def test_client_initialization(self, config, mock_google_ads_client):
        """Client initializes with valid config."""
        client = GoogleAdsClient(config)
        assert client.customer_id == "1234567890"
        mock_google_ads_client.load_from_dict.assert_called_once()

    def test_get_keyword_cpc_estimates(self, config, mock_google_ads_client):
        """Get CPC estimates for keywords from Keyword Planner."""
        # Setup mock response
        mock_service = MagicMock()
        mock_google_ads_client.load_from_dict.return_value.get_service.return_value = mock_service

        mock_result = MagicMock()
        mock_metric = MagicMock()
        mock_metric.text = "fitness tracker"
        mock_metric.keyword_idea_metrics.avg_monthly_searches = 10000
        mock_metric.keyword_idea_metrics.competition = 2  # MEDIUM
        mock_metric.keyword_idea_metrics.low_top_of_page_bid_micros = 500000  # $0.50
        mock_metric.keyword_idea_metrics.high_top_of_page_bid_micros = 1500000  # $1.50
        mock_result.results = [mock_metric]
        mock_service.generate_keyword_ideas.return_value = mock_result

        client = GoogleAdsClient(config)
        estimates = client.get_keyword_cpc_estimates(["fitness tracker"])

        assert len(estimates) == 1
        assert estimates[0].keyword == "fitness tracker"
        assert estimates[0].avg_monthly_searches == 10000
        assert estimates[0].low_cpc == Decimal("0.50")
        assert estimates[0].high_cpc == Decimal("1.50")

    def test_get_keyword_cpc_estimates_empty_keywords(self, config, mock_google_ads_client):
        """Empty keyword list returns empty results."""
        client = GoogleAdsClient(config)
        estimates = client.get_keyword_cpc_estimates([])
        assert estimates == []

    def test_create_campaign(self, config, mock_google_ads_client):
        """Create a new Google Ads campaign."""
        mock_instance = mock_google_ads_client.load_from_dict.return_value
        mock_service = MagicMock()
        mock_instance.get_service.return_value = mock_service

        # Mock campaign creation response
        mock_response = MagicMock()
        mock_response.results = [MagicMock(resource_name="customers/123/campaigns/456")]
        mock_service.mutate_campaigns.return_value = mock_response

        client = GoogleAdsClient(config)
        campaign = client.create_campaign(
            name="Test Campaign",
            daily_budget_cents=5000,  # $50.00
            max_cpc_cents=75,  # $0.75
        )

        assert campaign.id == "456"
        assert campaign.name == "Test Campaign"
        assert campaign.status == CampaignStatus.ENABLED

    def test_pause_campaign(self, config, mock_google_ads_client):
        """Pause an existing campaign."""
        mock_instance = mock_google_ads_client.load_from_dict.return_value
        mock_service = MagicMock()
        mock_instance.get_service.return_value = mock_service

        client = GoogleAdsClient(config)
        result = client.set_campaign_status("456", CampaignStatus.PAUSED)

        assert result is True
        mock_service.mutate_campaigns.assert_called_once()

    def test_enable_campaign(self, config, mock_google_ads_client):
        """Enable a paused campaign."""
        mock_instance = mock_google_ads_client.load_from_dict.return_value
        mock_service = MagicMock()
        mock_instance.get_service.return_value = mock_service

        client = GoogleAdsClient(config)
        result = client.set_campaign_status("456", CampaignStatus.ENABLED)

        assert result is True

    def test_get_campaign(self, config, mock_google_ads_client):
        """Get campaign details by ID."""
        mock_instance = mock_google_ads_client.load_from_dict.return_value
        mock_service = MagicMock()
        mock_instance.get_service.return_value = mock_service

        # Mock search response - search_stream returns iterator of batches with .results
        mock_row = MagicMock()
        mock_row.campaign.id = 456
        mock_row.campaign.name = "Test Campaign"
        mock_row.campaign.status = 2  # ENABLED
        mock_row.campaign_budget.amount_micros = 50000000  # $50.00
        mock_batch = MagicMock()
        mock_batch.results = [mock_row]
        mock_service.search_stream.return_value = [mock_batch]

        client = GoogleAdsClient(config)
        campaign = client.get_campaign("456")

        assert campaign.id == "456"
        assert campaign.name == "Test Campaign"
        assert campaign.status == CampaignStatus.ENABLED
        assert campaign.daily_budget_cents == 5000

    def test_get_campaign_not_found(self, config, mock_google_ads_client):
        """Get campaign returns None if not found."""
        mock_instance = mock_google_ads_client.load_from_dict.return_value
        mock_service = MagicMock()
        mock_instance.get_service.return_value = mock_service
        mock_batch = MagicMock()
        mock_batch.results = []  # Empty results
        mock_service.search_stream.return_value = [mock_batch]

        client = GoogleAdsClient(config)
        campaign = client.get_campaign("999")

        assert campaign is None

    def test_list_campaigns(self, config, mock_google_ads_client):
        """List all campaigns."""
        mock_instance = mock_google_ads_client.load_from_dict.return_value
        mock_service = MagicMock()
        mock_instance.get_service.return_value = mock_service

        # Mock search response with multiple campaigns
        mock_row1 = MagicMock()
        mock_row1.campaign.id = 456
        mock_row1.campaign.name = "Campaign 1"
        mock_row1.campaign.status = 2  # ENABLED
        mock_row1.campaign_budget.amount_micros = 50000000

        mock_row2 = MagicMock()
        mock_row2.campaign.id = 789
        mock_row2.campaign.name = "Campaign 2"
        mock_row2.campaign.status = 3  # PAUSED
        mock_row2.campaign_budget.amount_micros = 100000000

        mock_batch = MagicMock()
        mock_batch.results = [mock_row1, mock_row2]
        mock_service.search_stream.return_value = [mock_batch]

        client = GoogleAdsClient(config)
        campaigns = client.list_campaigns()

        assert len(campaigns) == 2
        assert campaigns[0].name == "Campaign 1"
        assert campaigns[1].name == "Campaign 2"


class TestErrorHandling:
    """Test error handling scenarios."""

    @pytest.fixture
    def config(self):
        return GoogleAdsConfig(
            client_id="test-client-id.apps.googleusercontent.com",
            client_secret="test-secret",
            refresh_token="test-refresh-token",
            developer_token="test-dev-token",
            customer_id="123-456-7890",
        )

    @pytest.fixture
    def mock_google_ads_client(self):
        with patch("ecom_arb.integrations.google_ads.GoogleAdsApiClient") as mock:
            mock_instance = MagicMock()
            mock.load_from_dict.return_value = mock_instance
            yield mock

    def test_api_error_wrapped(self, config, mock_google_ads_client):
        """API errors are wrapped in GoogleAdsError."""
        from google.ads.googleads.errors import GoogleAdsException

        mock_instance = mock_google_ads_client.load_from_dict.return_value
        mock_service = MagicMock()
        mock_instance.get_service.return_value = mock_service
        mock_service.generate_keyword_ideas.side_effect = GoogleAdsException(
            error=MagicMock(),
            call=MagicMock(),
            failure=MagicMock(),
            request_id="test-request",
        )

        client = GoogleAdsClient(config)
        with pytest.raises(GoogleAdsError) as exc_info:
            client.get_keyword_cpc_estimates(["test keyword"])

        assert "test-request" in str(exc_info.value)

    def test_rate_limit_error(self, config, mock_google_ads_client):
        """Rate limit errors include retry info."""
        from google.ads.googleads.errors import GoogleAdsException

        mock_failure = MagicMock()
        mock_error = MagicMock()
        mock_error.error_code.quota_error = 1  # RESOURCE_EXHAUSTED
        mock_failure.errors = [mock_error]

        mock_instance = mock_google_ads_client.load_from_dict.return_value
        mock_service = MagicMock()
        mock_instance.get_service.return_value = mock_service
        mock_service.generate_keyword_ideas.side_effect = GoogleAdsException(
            error=MagicMock(),
            call=MagicMock(),
            failure=mock_failure,
            request_id="rate-limit-test",
        )

        client = GoogleAdsClient(config)
        with pytest.raises(GoogleAdsError) as exc_info:
            client.get_keyword_cpc_estimates(["test keyword"])

        assert exc_info.value.is_rate_limit_error


class TestCPCEstimate:
    """Test CPC estimate data structure."""

    def test_cpc_estimate_average(self):
        """Average CPC is calculated correctly."""
        estimate = CPCEstimate(
            keyword="test",
            avg_monthly_searches=1000,
            competition="MEDIUM",
            low_cpc=Decimal("0.50"),
            high_cpc=Decimal("1.50"),
        )
        assert estimate.avg_cpc == Decimal("1.00")

    def test_cpc_estimate_from_micros(self):
        """CPC converts from micros correctly."""
        estimate = CPCEstimate.from_micros(
            keyword="test",
            avg_monthly_searches=1000,
            competition="LOW",
            low_top_of_page_bid_micros=500000,
            high_top_of_page_bid_micros=1500000,
        )
        assert estimate.low_cpc == Decimal("0.50")
        assert estimate.high_cpc == Decimal("1.50")
