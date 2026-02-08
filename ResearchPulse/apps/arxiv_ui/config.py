"""arXiv UI configuration settings.

Configuration precedence (highest to lowest):
1. Environment variables (runtime override)
2. .env file
3. /config/defaults.yaml apps.arxiv_ui (project overrides)
4. /apps/arxiv_ui/config/defaults.yaml (app defaults)
5. Hardcoded Python defaults (fallback)
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from common.config_loader import get_app_config

# Load YAML defaults for arxiv_ui
_app_config = get_app_config("arxiv_ui")
_date_window_defaults = _app_config.get("date_window", {})


class ArxivUIConfig(BaseSettings):
    """arXiv UI settings.

    Non-sensitive defaults loaded from /config/defaults.yaml and app defaults.
    """

    enabled: bool = Field(
        default=_app_config.get("enabled", True),
        validation_alias="ARXIV_UI_ENABLED",
    )
    scan_interval: int = Field(
        default=_app_config.get("scan_interval", 3600),
        validation_alias="ARXIV_UI_SCAN_INTERVAL",
    )
    show_all_content: bool = Field(
        default=_app_config.get("show_all_content", False),
        validation_alias="ARXIV_UI_SHOW_ALL_CONTENT",
    )
    default_page_size: int = Field(
        default=_app_config.get("default_page_size", 20),
        validation_alias="ARXIV_UI_DEFAULT_PAGE_SIZE",
    )
    max_content_age_days: int = Field(
        default=_app_config.get("max_content_age_days", 30),
        validation_alias="ARXIV_UI_MAX_CONTENT_AGE_DAYS",
    )
    date_window_days: int = Field(
        default=_date_window_defaults.get("days", 2),
        validation_alias="ARXIV_UI_DATE_WINDOW_DAYS",
    )
    date_window_timezone: str = Field(
        default=_date_window_defaults.get("timezone", "UTC"),
        validation_alias="ARXIV_UI_DATE_WINDOW_TIMEZONE",
    )

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")


settings = ArxivUIConfig()
