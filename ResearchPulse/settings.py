"""Global application settings for ResearchPulse.

Configuration precedence (highest to lowest):
1. Environment variables (runtime override)
2. .env file (secrets)
3. /config/defaults.yaml (non-sensitive defaults)
4. Hardcoded Python defaults (fallback)
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from common.config_loader import get_project_config

BASE_DIR = Path(__file__).resolve().parent

# Load YAML defaults
_project_config = get_project_config()
_app_defaults = _project_config.get("app", {})
_logging_defaults = _project_config.get("logging", {})
_email_defaults = _project_config.get("email", {})


def _get_default_data_dir() -> Path:
    """Get default data directory from YAML or fallback."""
    yaml_dir = _app_defaults.get("data_dir", "./data")
    path = Path(yaml_dir)
    if not path.is_absolute():
        return BASE_DIR / path
    return path


class Settings(BaseSettings):
    """Global application settings.

    Non-sensitive defaults are loaded from /config/defaults.yaml.
    Secrets (API keys, credentials) are loaded from .env.
    Environment variables override both.
    """

    # Application settings
    enabled_apps: str = Field(
        default=_app_defaults.get("enabled_apps", "arxiv_crawler"),
        validation_alias="ENABLED_APPS",
    )
    data_dir: Path = Field(
        default=_get_default_data_dir(),
        validation_alias="DATA_DIR",
    )

    # Logging settings
    log_level: str = Field(
        default=_logging_defaults.get("level", "INFO"),
        validation_alias="LOG_LEVEL",
    )
    log_file: Optional[Path] = Field(
        default=_logging_defaults.get("file"),
        validation_alias="LOG_FILE",
    )

    # Email settings (from address is a secret, kept in .env)
    email_from: str = Field(
        default=_email_defaults.get("from", ""),
        validation_alias="EMAIL_FROM",
    )
    email_backends: str = Field(
        default=_email_defaults.get("backends", "smtp"),
        validation_alias="EMAIL_BACKENDS",
    )

    # SendGrid settings (API key is secret, kept in .env)
    sendgrid_api_key: str = Field("", validation_alias="SENDGRID_API_KEY")
    sendgrid_retries: int = Field(
        default=_email_defaults.get("sendgrid", {}).get("retries", 3),
        validation_alias="SENDGRID_RETRIES",
    )
    sendgrid_retry_backoff: float = Field(
        default=_email_defaults.get("sendgrid", {}).get("retry_backoff", 10.0),
        validation_alias="SENDGRID_RETRY_BACKOFF",
    )

    # Mailgun settings (API key and domain are secrets, kept in .env)
    mailgun_api_key: str = Field("", validation_alias="MAILGUN_API_KEY")
    mailgun_domain: str = Field(
        default=_email_defaults.get("mailgun", {}).get("domain", ""),
        validation_alias="MAILGUN_DOMAIN",
    )
    mailgun_retries: int = Field(
        default=_email_defaults.get("mailgun", {}).get("retries", 3),
        validation_alias="MAILGUN_RETRIES",
    )
    mailgun_retry_backoff: float = Field(
        default=_email_defaults.get("mailgun", {}).get("retry_backoff", 10.0),
        validation_alias="MAILGUN_RETRY_BACKOFF",
    )

    # Brevo settings (API key is secret, kept in .env)
    brevo_api_key: str = Field("", validation_alias="BREVO_API_KEY")
    brevo_from_name: str = Field(
        default=_email_defaults.get("brevo", {}).get("from_name", "ResearchPulse"),
        validation_alias="BREVO_FROM_NAME",
    )
    brevo_retries: int = Field(
        default=_email_defaults.get("brevo", {}).get("retries", 3),
        validation_alias="BREVO_RETRIES",
    )
    brevo_retry_backoff: float = Field(
        default=_email_defaults.get("brevo", {}).get("retry_backoff", 10.0),
        validation_alias="BREVO_RETRY_BACKOFF",
    )

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def enabled_apps_list(self) -> List[str]:
        """Return enabled apps as a list."""
        return [app.strip() for app in self.enabled_apps.split(",") if app.strip()]

    @property
    def email_backends_list(self) -> List[str]:
        """Return email backends as a list."""
        return [item.strip() for item in self.email_backends.split(",") if item.strip()]


settings = Settings()
