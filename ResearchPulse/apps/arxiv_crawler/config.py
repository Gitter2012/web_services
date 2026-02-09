"""arXiv Crawler configuration settings.

Configuration precedence (highest to lowest):
1. Environment variables (runtime override)
2. .env file (secrets: SMTP_PASSWORD, etc.)
3. /config/defaults.yaml apps.arxiv_crawler (project overrides)
4. /apps/arxiv_crawler/config/defaults.yaml (app defaults)
5. Hardcoded Python defaults (fallback)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from common.config_loader import get_app_config

# Load YAML defaults for arxiv_crawler
_app_config = get_app_config("arxiv_crawler")
_arxiv_defaults = _app_config.get("arxiv", {})
_urls_defaults = _arxiv_defaults.get("urls", {})
_schedule_defaults = _app_config.get("schedule", {})
_date_window_defaults = _app_config.get("date_window", {})
_email_defaults = _app_config.get("email", {})
_smtp_defaults = _app_config.get("smtp", {})
_smtp_profile_defaults = _smtp_defaults.get("profile_defaults", {})
_html_list_fallback = _urls_defaults.get("html_list", "https://arxiv.org/list/{category}/new")
_html_list_recent_fallback = _urls_defaults.get("html_list_recent")
if not _html_list_recent_fallback:
    if "/new" in _html_list_fallback:
        _html_list_recent_fallback = _html_list_fallback.replace("/new", "/recent")
    else:
        _html_list_recent_fallback = "https://arxiv.org/list/{category}/recent"


class ArxivSettings(BaseSettings):
    """arXiv crawler settings.

    Non-sensitive defaults loaded from /config/defaults.yaml and app defaults.
    Secrets (passwords, credentials) loaded from .env.
    """

    # arXiv API settings
    arxiv_categories: str = Field(
        default=_arxiv_defaults.get("categories", "cs.LG,cs.CV"),
        validation_alias="ARXIV_CATEGORIES",
    )
    arxiv_main_category: str = Field(
        default=_arxiv_defaults.get("main_category", ""),
        validation_alias="ARXIV_MAIN_CATEGORY",
    )
    arxiv_max_results: int = Field(
        default=_arxiv_defaults.get("max_results", 50),
        validation_alias="ARXIV_MAX_RESULTS",
    )
    arxiv_base_url: str = Field(
        default=_urls_defaults.get("base", "https://export.arxiv.org/api/query"),
        validation_alias="ARXIV_BASE_URL",
    )
    arxiv_rss_url: str = Field(
        default=_urls_defaults.get("rss", "https://export.arxiv.org/rss/{category}"),
        validation_alias="ARXIV_RSS_URL",
    )
    arxiv_html_list_new_url: str = Field(
        default=_urls_defaults.get("html_list_new", _html_list_fallback),
        validation_alias="ARXIV_HTML_LIST_NEW_URL",
    )
    arxiv_html_list_recent_url: str = Field(
        default=_html_list_recent_fallback,
        validation_alias="ARXIV_HTML_LIST_RECENT_URL",
    )
    arxiv_html_list_url: str = Field(
        default=_html_list_fallback,
        validation_alias="ARXIV_HTML_LIST_URL",
    )
    arxiv_html_search_url: str = Field(
        default=_urls_defaults.get(
            "html_search",
            "https://arxiv.org/search/?query={category}&searchtype=all&abstracts=show&order=-announced_date_first&size={size}",
        ),
        validation_alias="ARXIV_HTML_SEARCH_URL",
    )

    arxiv_min_results: int = Field(
        default=_arxiv_defaults.get("min_results", 10),
        validation_alias="ARXIV_MIN_RESULTS",
    )
    arxiv_fallback_days: int = Field(
        default=_arxiv_defaults.get("fallback_days", 7),
        validation_alias="ARXIV_FALLBACK_DAYS",
    )

    # Schedule settings
    schedule_hour: int = Field(
        default=_schedule_defaults.get("hour", 0),
        validation_alias="ARXIV_SCHEDULE_HOUR",
    )
    schedule_minute: int = Field(
        default=_schedule_defaults.get("minute", 0),
        validation_alias="ARXIV_SCHEDULE_MINUTE",
    )
    schedule_timezone: str = Field(
        default=_schedule_defaults.get("timezone", "UTC"),
        validation_alias="ARXIV_SCHEDULE_TIMEZONE",
    )

    # Date window settings
    date_window_days: int = Field(
        default=_date_window_defaults.get("days", 2),
        validation_alias="ARXIV_DATE_WINDOW_DAYS",
    )
    date_window_timezone: str = Field(
        default=_date_window_defaults.get("timezone", "UTC"),
        validation_alias="ARXIV_DATE_WINDOW_TIMEZONE",
    )

    # Email settings
    email_enabled: bool = Field(
        default=_email_defaults.get("enabled", True),
        validation_alias="ARXIV_EMAIL_ENABLED",
    )
    email_html_enabled: bool = Field(
        default=_email_defaults.get("html_enabled", True),
        validation_alias="ARXIV_EMAIL_HTML_ENABLED",
    )
    abstract_max_len: int = Field(
        default=_arxiv_defaults.get("abstract_max_len", 0),
        validation_alias="ARXIV_ABSTRACT_MAX_LEN",
    )

    # Email addresses (secrets in .env)
    email_from: str = Field(
        default=_email_defaults.get("from", ""),
        validation_alias="EMAIL_FROM",
    )
    email_to: str = Field(
        default=_email_defaults.get("to", ""),
        validation_alias="EMAIL_TO",
    )

    # SMTP settings (host/user/password are secrets in .env)
    smtp_host: str = Field("", validation_alias="SMTP_HOST")
    smtp_port: int = Field(
        default=_smtp_defaults.get("port", 587),
        validation_alias="SMTP_PORT",
    )
    smtp_ports: str = Field(
        default=_smtp_defaults.get("ports", ""),
        validation_alias="SMTP_PORTS",
    )
    smtp_ssl_ports: str = Field(
        default=_smtp_defaults.get("ssl_ports", "465"),
        validation_alias="SMTP_SSL_PORTS",
    )
    smtp_timeout: float = Field(
        default=_smtp_defaults.get("timeout", 10.0),
        validation_alias="SMTP_TIMEOUT",
    )
    smtp_retries: int = Field(
        default=_smtp_defaults.get("retries", 5),
        validation_alias="SMTP_RETRIES",
    )
    smtp_retry_backoff: float = Field(
        default=_smtp_defaults.get("retry_backoff", 30.0),
        validation_alias="SMTP_RETRY_BACKOFF",
    )
    smtp_user: str = Field("", validation_alias="SMTP_USER")
    smtp_password: str = Field("", validation_alias="SMTP_PASSWORD")
    smtp_tls: bool = Field(
        default=_smtp_defaults.get("tls", True),
        validation_alias="SMTP_TLS",
    )
    smtp_ssl: bool = Field(
        default=_smtp_defaults.get("ssl", False),
        validation_alias="SMTP_SSL",
    )
    smtp_profiles: str = Field(
        default=_smtp_defaults.get("profiles", ""),
        validation_alias="SMTP_PROFILES",
    )

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")

    @property
    def categories_list(self) -> List[str]:
        """Return arXiv categories as a list."""
        return [item.strip() for item in self.arxiv_categories.split(",") if item.strip()]

    @property
    def email_to_list(self) -> List[str]:
        """Return email recipients as a list."""
        return [item.strip() for item in self.email_to.split(",") if item.strip()]

    @property
    def smtp_ports_list(self) -> List[int]:
        """Return SMTP ports as a list of integers."""
        if not self.smtp_ports:
            return []
        ports: List[int] = []
        for value in self.smtp_ports.split(","):
            value = value.strip()
            if not value:
                continue
            try:
                ports.append(int(value))
            except ValueError:
                continue
        return ports

    @property
    def smtp_ssl_ports_list(self) -> List[int]:
        """Return SMTP SSL ports as a list of integers."""
        ports: List[int] = []
        for value in self.smtp_ssl_ports.split(","):
            value = value.strip()
            if not value:
                continue
            try:
                ports.append(int(value))
            except ValueError:
                continue
        return ports

    @property
    def smtp_profile_ids(self) -> List[str]:
        """Return SMTP profile IDs as a list."""
        return [item.strip() for item in self.smtp_profiles.split(",") if item.strip()]

    def _load_env_file(self) -> dict[str, str]:
        """Load environment variables from .env file."""
        env_files = self.model_config.get("env_file")
        if not env_files:
            return {}
        if isinstance(env_files, (list, tuple)):
            candidates = env_files
        else:
            candidates = [env_files]
        values: dict[str, str] = {}
        base_dir = Path(__file__).resolve().parents[2]
        for env_file in candidates:
            try:
                path = Path(env_file)
                if not path.is_absolute():
                    path = base_dir / path
                if not path.exists():
                    continue
                for line in path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    values[key] = value
            except OSError:
                continue
        return values

    def _profile_env(self, profile_id: str, suffix: str, default: str = "") -> str:
        """Get SMTP profile value from env/.env/YAML defaults."""
        key = f"SMTP{profile_id}_{suffix}"
        if key in os.environ:
            return os.environ[key]
        env_values = self._load_env_file()
        if key in env_values:
            return env_values[key]
        yaml_value = self._profile_default_value(profile_id, suffix)
        if yaml_value is not None:
            return str(yaml_value)
        return default

    @staticmethod
    def _profile_default_value(profile_id: str, suffix: str) -> str | None:
        """Get SMTP profile default from YAML (non-secret fields only)."""
        key_map = {
            "HOST": "host",
            "USER": "user",
            "PORT": "port",
            "PORTS": "ports",
            "SSL_PORTS": "ssl_ports",
            "TIMEOUT": "timeout",
            "RETRIES": "retries",
            "RETRY_BACKOFF": "retry_backoff",
            "TLS": "tls",
            "SSL": "ssl",
        }
        yaml_key = key_map.get(suffix)
        if not yaml_key:
            return None
        profile_defaults = _smtp_profile_defaults.get(str(profile_id), {})
        if not isinstance(profile_defaults, dict):
            return None
        return profile_defaults.get(yaml_key)

    @staticmethod
    def _parse_bool(value: str, default: bool) -> bool:
        """Parse boolean from string."""
        if value == "":
            return default
        return value.strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _parse_int(value: str, default: int) -> int:
        """Parse integer from string."""
        if value == "":
            return default
        try:
            return int(value)
        except ValueError:
            return default

    @staticmethod
    def _parse_float(value: str, default: float) -> float:
        """Parse float from string."""
        if value == "":
            return default
        try:
            return float(value)
        except ValueError:
            return default

    @staticmethod
    def _parse_ports(value: str) -> List[int]:
        """Parse comma-separated ports string to list of integers."""
        if not value:
            return []
        ports: List[int] = []
        for item in value.split(","):
            item = item.strip()
            if not item:
                continue
            try:
                ports.append(int(item))
            except ValueError:
                continue
        return ports

    @property
    def smtp_profiles_list(self) -> List[dict[str, object]]:
        """Return list of SMTP profile configurations."""
        profile_ids = self.smtp_profile_ids
        if not profile_ids:
            return [
                {
                    "id": "default",
                    "host": self.smtp_host,
                    "port": self.smtp_port,
                    "ports": self.smtp_ports_list,
                    "ssl_ports": self.smtp_ssl_ports_list,
                    "timeout": self.smtp_timeout,
                    "retries": self.smtp_retries,
                    "retry_backoff": self.smtp_retry_backoff,
                    "user": self.smtp_user,
                    "password": self.smtp_password,
                    "tls": self.smtp_tls,
                    "ssl": self.smtp_ssl,
                }
            ]

        profiles: List[dict[str, object]] = []
        for profile_id in profile_ids:
            host = self._profile_env(profile_id, "HOST", "")
            port = self._parse_int(self._profile_env(profile_id, "PORT", ""), self.smtp_port)
            ports = self._parse_ports(self._profile_env(profile_id, "PORTS", ""))
            ssl_ports = self._parse_ports(self._profile_env(profile_id, "SSL_PORTS", ""))
            timeout = self._parse_float(
                self._profile_env(profile_id, "TIMEOUT", ""),
                self.smtp_timeout,
            )
            retries = self._parse_int(
                self._profile_env(profile_id, "RETRIES", ""),
                self.smtp_retries,
            )
            retry_backoff = self._parse_float(
                self._profile_env(profile_id, "RETRY_BACKOFF", ""),
                self.smtp_retry_backoff,
            )
            user = self._profile_env(profile_id, "USER", self.smtp_user)
            password = self._profile_env(profile_id, "PASSWORD", self.smtp_password)
            tls = self._parse_bool(self._profile_env(profile_id, "TLS", ""), self.smtp_tls)
            ssl = self._parse_bool(self._profile_env(profile_id, "SSL", ""), self.smtp_ssl)
            profiles.append(
                {
                    "id": profile_id,
                    "host": host,
                    "port": port,
                    "ports": ports,
                    "ssl_ports": ssl_ports,
                    "timeout": timeout,
                    "retries": retries,
                    "retry_backoff": retry_backoff,
                    "user": user,
                    "password": password,
                    "tls": tls,
                    "ssl": ssl,
                }
            )
        return profiles


settings = ArxivSettings()
