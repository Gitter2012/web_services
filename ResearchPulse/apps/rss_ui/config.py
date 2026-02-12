from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from common.config_loader import get_app_config

_app_config = get_app_config("rss_ui")


class RssUISettings(BaseSettings):

    enabled: bool = Field(
        default=_app_config.get("enabled", True),
        validation_alias="RSS_UI_ENABLED",
    )
    default_page_size: int = Field(
        default=_app_config.get("default_page_size", 20),
        validation_alias="RSS_UI_DEFAULT_PAGE_SIZE",
    )

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")


settings = RssUISettings()
