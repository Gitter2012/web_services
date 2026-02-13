"""Global application settings for ResearchPulse v2.

Configuration precedence (highest to lowest):
1. Environment variables (runtime override)
2. .env file (secrets)
3. config/defaults.yaml (non-sensitive defaults)
4. Hardcoded Python defaults (fallback)
"""

from __future__ import annotations

import secrets
from pathlib import Path
from typing import List, Optional

import yaml
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent
CONFIG_DIR = BASE_DIR / "config"


def load_yaml_config() -> dict:
    """Load configuration from defaults.yaml."""
    config_path = CONFIG_DIR / "defaults.yaml"
    if not config_path.exists():
        return {}
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


_yaml_config = load_yaml_config()
_app_config = _yaml_config.get("app", {})
_db_config = _yaml_config.get("database", {})
_cache_config = _yaml_config.get("cache", {})
_jwt_config = _yaml_config.get("jwt", {})
_crawler_config = _yaml_config.get("crawler", {})
_scheduler_config = _yaml_config.get("scheduler", {})
_retention_config = _yaml_config.get("data_retention", {})
_email_config = _yaml_config.get("email", {})


def _get_default_data_dir() -> Path:
    """Get default data directory."""
    yaml_dir = _app_config.get("data_dir", "./data")
    path = Path(yaml_dir)
    if not path.is_absolute():
        return BASE_DIR / path
    return path


class Settings(BaseSettings):
    """Global application settings."""

    # Application
    app_name: str = Field(
        default=_app_config.get("name", "ResearchPulse"),
        validation_alias="APP_NAME",
    )
    debug: bool = Field(
        default=_app_config.get("debug", False),
        validation_alias="DEBUG",
    )
    data_dir: Path = Field(
        default=_get_default_data_dir(),
        validation_alias="DATA_DIR",
    )
    url_prefix: str = Field(
        default=_app_config.get("url_prefix", "/researchpulse"),
        validation_alias="URL_PREFIX",
    )

    # Database
    db_host: str = Field(
        default="localhost",
        validation_alias="DB_HOST",
    )
    db_port: int = Field(
        default=3306,
        validation_alias="DB_PORT",
    )
    db_name: str = Field(
        default="research_pulse",
        validation_alias="DB_NAME",
    )
    db_user: str = Field(
        default="research_user",
        validation_alias="DB_USER",
    )
    db_password: str = Field(
        default="",
        validation_alias="DB_PASSWORD",
    )
    db_pool_size: int = Field(
        default=_db_config.get("pool_size", 10),
        validation_alias="DB_POOL_SIZE",
    )
    db_max_overflow: int = Field(
        default=_db_config.get("max_overflow", 20),
        validation_alias="DB_MAX_OVERFLOW",
    )
    db_pool_recycle: int = Field(
        default=_db_config.get("pool_recycle", 3600),
        validation_alias="DB_POOL_RECYCLE",
    )
    db_echo: bool = Field(
        default=_db_config.get("echo", False),
        validation_alias="DB_ECHO",
    )

    # Redis Cache (Optional)
    redis_host: str = Field(
        default="",
        validation_alias="REDIS_HOST",
    )
    redis_port: int = Field(
        default=6379,
        validation_alias="REDIS_PORT",
    )
    redis_password: str = Field(
        default="",
        validation_alias="REDIS_PASSWORD",
    )
    redis_db: int = Field(
        default=0,
        validation_alias="REDIS_DB",
    )
    cache_enabled: bool = Field(
        default=_cache_config.get("enabled", False),
        validation_alias="CACHE_ENABLED",
    )
    cache_default_ttl: int = Field(
        default=_cache_config.get("default_ttl", 300),
        validation_alias="CACHE_DEFAULT_TTL",
    )

    # JWT
    jwt_secret_key: str = Field(
        default="",
        validation_alias="JWT_SECRET_KEY",
    )
    jwt_algorithm: str = Field(
        default=_jwt_config.get("algorithm", "HS256"),
        validation_alias="JWT_ALGORITHM",
    )
    jwt_access_token_expire_minutes: int = Field(
        default=_jwt_config.get("access_token_expire_minutes", 30),
        validation_alias="JWT_ACCESS_TOKEN_EXPIRE_MINUTES",
    )
    jwt_refresh_token_expire_days: int = Field(
        default=_jwt_config.get("refresh_token_expire_days", 7),
        validation_alias="JWT_REFRESH_TOKEN_EXPIRE_DAYS",
    )

    # Crawler
    arxiv_categories: str = Field(
        default=_crawler_config.get("arxiv", {}).get("categories", "cs.LG,cs.CV,cs.CL"),
        validation_alias="ARXIV_CATEGORIES",
    )
    arxiv_max_results: int = Field(
        default=_crawler_config.get("arxiv", {}).get("max_results", 50),
        validation_alias="ARXIV_MAX_RESULTS",
    )
    arxiv_delay_base: float = Field(
        default=_crawler_config.get("arxiv", {}).get("delay_base", 3.0),
        validation_alias="ARXIV_DELAY_BASE",
    )

    # Scheduler
    crawl_interval_hours: int = Field(
        default=_scheduler_config.get("crawl_interval_hours", 6),
        validation_alias="CRAWL_INTERVAL_HOURS",
    )
    cleanup_hour: int = Field(
        default=_scheduler_config.get("cleanup_hour", 3),
        validation_alias="CLEANUP_HOUR",
    )
    backup_hour: int = Field(
        default=_scheduler_config.get("backup_hour", 4),
        validation_alias="BACKUP_HOUR",
    )
    scheduler_timezone: str = Field(
        default=_scheduler_config.get("timezone", "UTC"),
        validation_alias="SCHEDULER_TIMEZONE",
    )

    # Data Retention
    data_retention_days: int = Field(
        default=_retention_config.get("active_days", 7),
        validation_alias="DATA_RETENTION_DAYS",
    )
    data_archive_days: int = Field(
        default=_retention_config.get("archive_days", 30),
        validation_alias="DATA_ARCHIVE_DAYS",
    )
    backup_dir: Path = Field(
        default=Path(_retention_config.get("backup_dir", "./backups")),
        validation_alias="BACKUP_DIR",
    )
    backup_enabled: bool = Field(
        default=_retention_config.get("backup_enabled", True),
        validation_alias="BACKUP_ENABLED",
    )

    # Superuser
    superuser_username: str = Field(
        default="admin",
        validation_alias="SUPERUSER_USERNAME",
    )
    superuser_email: str = Field(
        default="admin@example.com",
        validation_alias="SUPERUSER_EMAIL",
    )
    superuser_password: str = Field(
        default="",
        validation_alias="SUPERUSER_PASSWORD",
    )

    # Email Configuration
    email_enabled: bool = Field(
        default=_email_config.get("enabled", False),
        validation_alias="EMAIL_ENABLED",
    )
    email_from: str = Field(
        default=_email_config.get("from", ""),
        validation_alias="EMAIL_FROM",
    )
    email_backend: str = Field(
        default=_email_config.get("backends", "smtp"),
        validation_alias="EMAIL_BACKEND",
    )
    # SMTP settings
    smtp_host: str = Field(
        default=_email_config.get("smtp", {}).get("host", ""),
        validation_alias="SMTP_HOST",
    )
    smtp_port: int = Field(
        default=_email_config.get("smtp", {}).get("port", 587),
        validation_alias="SMTP_PORT",
    )
    smtp_user: str = Field(
        default=_email_config.get("smtp", {}).get("user", ""),
        validation_alias="SMTP_USER",
    )
    smtp_password: str = Field(
        default=_email_config.get("smtp", {}).get("password", ""),
        validation_alias="SMTP_PASSWORD",
    )
    smtp_ports: str = Field(
        default=_email_config.get("smtp", {}).get("ports", "587,465,2525"),
        validation_alias="SMTP_PORTS",
    )
    smtp_ssl_ports: str = Field(
        default=_email_config.get("smtp", {}).get("ssl_ports", "465"),
        validation_alias="SMTP_SSL_PORTS",
    )
    smtp_timeout: float = Field(
        default=_email_config.get("smtp", {}).get("timeout", 10.0),
        validation_alias="SMTP_TIMEOUT",
    )
    smtp_retries: int = Field(
        default=_email_config.get("smtp", {}).get("retries", 3),
        validation_alias="SMTP_RETRIES",
    )
    smtp_retry_backoff: float = Field(
        default=_email_config.get("smtp", {}).get("retry_backoff", 10.0),
        validation_alias="SMTP_RETRY_BACKOFF",
    )
    smtp_tls: bool = Field(
        default=_email_config.get("smtp", {}).get("tls", True),
        validation_alias="SMTP_TLS",
    )
    smtp_ssl: bool = Field(
        default=_email_config.get("smtp", {}).get("ssl", False),
        validation_alias="SMTP_SSL",
    )
    # API keys for other backends
    sendgrid_api_key: str = Field(
        default="",
        validation_alias="SENDGRID_API_KEY",
    )
    mailgun_api_key: str = Field(
        default="",
        validation_alias="MAILGUN_API_KEY",
    )
    mailgun_domain: str = Field(
        default="",
        validation_alias="MAILGUN_DOMAIN",
    )
    brevo_api_key: str = Field(
        default="",
        validation_alias="BREVO_API_KEY",
    )
    # Notification settings
    email_notification_frequency: str = Field(
        default=_email_config.get("notification", {}).get("frequency", "daily"),
        validation_alias="EMAIL_NOTIFICATION_FREQUENCY",
    )
    email_notification_time: str = Field(
        default=_email_config.get("notification", {}).get("time", "09:00"),
        validation_alias="EMAIL_NOTIFICATION_TIME",
    )
    email_max_articles: int = Field(
        default=_email_config.get("notification", {}).get("max_articles", 20),
        validation_alias="EMAIL_MAX_ARTICLES",
    )

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("jwt_secret_key", mode="before")
    @classmethod
    def generate_jwt_secret_if_empty(cls, v: str) -> str:
        """Generate a random JWT secret if not provided."""
        if not v or v == "your_jwt_secret_key_here":
            return secrets.token_urlsafe(32)
        return v

    @property
    def database_url(self) -> str:
        """Build async MySQL database URL."""
        from urllib.parse import quote_plus
        encoded_password = quote_plus(self.db_password)
        return (
            f"mysql+aiomysql://{self.db_user}:{encoded_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @property
    def database_url_sync(self) -> str:
        """Build sync MySQL database URL (for Alembic)."""
        from urllib.parse import quote_plus
        encoded_password = quote_plus(self.db_password)
        return (
            f"mysql+pymysql://{self.db_user}:{encoded_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @property
    def redis_available(self) -> bool:
        """Check if Redis is configured."""
        return bool(self.redis_host)

    @property
    def arxiv_categories_list(self) -> List[str]:
        """Return arxiv categories as a list."""
        return [c.strip() for c in self.arxiv_categories.split(",") if c.strip()]

    @property
    def is_configured(self) -> bool:
        """Check if essential configuration is complete."""
        return bool(self.db_host and self.db_name and self.db_user)


settings = Settings()
