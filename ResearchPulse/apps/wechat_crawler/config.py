from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from common.config_loader import get_app_config

_app_config = get_app_config("wechat_crawler")
_schedule_defaults = _app_config.get("schedule", {})
_database_defaults = _app_config.get("database", {})
_crawl_defaults = _app_config.get("crawl", {})


class WechatCrawlerSettings(BaseSettings):

    # Database
    database_url: str = Field(
        default=_database_defaults.get("url", ""),
        validation_alias="WECHAT_DATABASE_URL",
    )
    database_path: str = Field(
        default=_database_defaults.get("path", "articles.db"),
        validation_alias="WECHAT_DATABASE_PATH",
    )

    # Schedule
    schedule_cron: str = Field(
        default=_schedule_defaults.get("cron", "0 */2 * * *"),
        validation_alias="WECHAT_SCHEDULE_CRON",
    )
    schedule_timezone: str = Field(
        default=_schedule_defaults.get("timezone", "Asia/Shanghai"),
        validation_alias="WECHAT_SCHEDULE_TIMEZONE",
    )
    run_on_startup: bool = Field(
        default=_schedule_defaults.get("run_on_startup", True),
        validation_alias="WECHAT_RUN_ON_STARTUP",
    )

    # Crawl behavior
    retention_days: int = Field(
        default=_crawl_defaults.get("retention_days", 90),
        validation_alias="WECHAT_RETENTION_DAYS",
    )
    fetch_content: bool = Field(
        default=_crawl_defaults.get("fetch_content", False),
        validation_alias="WECHAT_FETCH_CONTENT",
    )
    http_delay_base: float = Field(
        default=_crawl_defaults.get("http_delay_base", 2.0),
        validation_alias="WECHAT_HTTP_DELAY_BASE",
    )
    http_delay_jitter: float = Field(
        default=_crawl_defaults.get("http_delay_jitter", 1.0),
        validation_alias="WECHAT_HTTP_DELAY_JITTER",
    )
    http_timeout: float = Field(
        default=_crawl_defaults.get("http_timeout", 15.0),
        validation_alias="WECHAT_HTTP_TIMEOUT",
    )

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")


settings = WechatCrawlerSettings()
