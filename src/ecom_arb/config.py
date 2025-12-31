"""Application configuration using pydantic-settings."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Application
    app_name: str = "ecom-arb"
    debug: bool = False
    environment: str = "development"

    # Database (SQLite for local dev, PostgreSQL for prod)
    database_url: str = "sqlite+aiosqlite:///./ecom_arb.db"

    # Stripe
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_success_url: str = "http://localhost:4290/order/{order_id}"
    stripe_cancel_url: str = "http://localhost:4290/checkout/{product_slug}"

    # Frontend
    frontend_url: str = "http://localhost:4290"

    # API
    api_prefix: str = "/api"

    # Google Ads
    google_ads_client_id: str = ""
    google_ads_client_secret: str = ""
    google_ads_refresh_token: str = ""
    google_ads_developer_token: str = ""
    google_ads_customer_id: str = ""  # Format: 123-456-7890


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
