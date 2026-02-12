from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from common.config_loader import get_app_config

_app_config = get_app_config("wechat_ui")


class WechatUISettings(BaseSettings):

    enabled: bool = Field(
        default=_app_config.get("enabled", True),
        validation_alias="WECHAT_UI_ENABLED",
    )
    default_page_size: int = Field(
        default=_app_config.get("default_page_size", 20),
        validation_alias="WECHAT_UI_DEFAULT_PAGE_SIZE",
    )
    articles_per_page: int = Field(
        default=_app_config.get("articles_per_page", 20),
        validation_alias="WECHAT_UI_ARTICLES_PER_PAGE",
    )

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")


settings = WechatUISettings()
