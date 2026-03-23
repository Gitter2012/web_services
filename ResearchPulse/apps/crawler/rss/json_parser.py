# =============================================================================
# 模块: apps/crawler/rss/json_parser.py
# 功能: JSON API Feed 解析器，将 JSON 响应转换为标准化的文章字典列表
# 适用场景: 不提供 RSS/Atom 但有 JSON API 的数据源（如知乎日报 API）
# =============================================================================

"""JSON feed parser for ResearchPulse v2.

Parses JSON API responses into article dictionaries using configurable
field mappings. Configuration is stored in the ``json_config`` column
of the ``rss_feeds`` table.

Config example::

    {
        "items_paths": ["stories", "top_stories"],
        "fields": {
            "title": "title",
            "url": "url",
            "id": "id",
            "image": "images[0]"
        },
        "id_prefix": "zhihu-daily-"
    }
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class JsonFeedParser:
    """Parse JSON API responses into article dictionaries.

    The parser uses a configuration dict to locate the items array
    and map JSON fields to the standard article dictionary format.
    """

    def __init__(self, config: str | dict):
        """Initialize the parser.

        Args:
            config: JSON config string or pre-parsed dict.
        """
        if isinstance(config, str):
            self._config = json.loads(config)
        else:
            self._config = config

        self._items_paths: List[str] = self._config.get("items_paths", [])
        self._fields: Dict[str, str] = self._config.get("fields", {})
        self._id_prefix: str = self._config.get("id_prefix", "")

    def parse(self, raw_data: str) -> List[Dict[str, Any]]:
        """Parse raw JSON text into article dictionaries.

        Args:
            raw_data: JSON response text.

        Returns:
            List of article dicts (same format as RssCrawler._parse_entry).
        """
        try:
            data = json.loads(raw_data)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON feed: {e}")
            return []

        articles: List[Dict[str, Any]] = []
        seen_ids: set = set()

        for path in self._items_paths:
            items = self._extract_by_path(data, path)
            if not isinstance(items, list):
                logger.warning(f"JSON path '{path}' did not resolve to a list, got {type(items).__name__}")
                continue

            for item in items:
                if not isinstance(item, dict):
                    continue

                article = self._parse_item(item)
                if not article:
                    continue

                # Deduplicate by external_id within the same response
                ext_id = article.get("external_id", "")
                if ext_id and ext_id in seen_ids:
                    continue
                if ext_id:
                    seen_ids.add(ext_id)

                articles.append(article)

        return articles

    def _parse_item(self, item: dict) -> Optional[Dict[str, Any]]:
        """Convert a single JSON item to an article dictionary.

        Args:
            item: Raw JSON object for one article.

        Returns:
            Article dict or None if title is missing.
        """
        title = self._extract_field(item, "title")
        if not title:
            return None

        url = self._extract_field(item, "url") or ""
        item_id = self._extract_field(item, "id") or url
        external_id = f"{self._id_prefix}{item_id}" if item_id else ""

        article: Dict[str, Any] = {
            "external_id": external_id,
            "title": str(title),
            "url": str(url) if url else "",
            "author": self._extract_field(item, "author") or "",
            "summary": self._extract_field(item, "summary") or "",
            "content": self._extract_field(item, "content") or "",
            "cover_image_url": self._extract_field(item, "image") or "",
            "tags": [],
            "publish_time": self._parse_date(self._extract_field(item, "date")),
            "source_crawler_type": "rss",
        }

        return article

    def _extract_field(self, item: dict, field_name: str) -> Any:
        """Extract a field value using the config mapping.

        Falls back to the field_name itself if not in the config mapping.

        Args:
            item: JSON object for one article.
            field_name: Logical field name (e.g. 'title', 'url', 'image').

        Returns:
            Extracted value or empty string.
        """
        json_path = self._fields.get(field_name, field_name)
        value = self._extract_by_path(item, json_path)
        return value if value is not None else ""

    @staticmethod
    def _extract_by_path(data: Any, path: str) -> Any:
        """Extract a value from a nested dict/list by dot-separated path.

        Supports array index notation: ``images[0]``.

        Args:
            data: The JSON data to traverse.
            path: Dot-separated path with optional array indices.

        Returns:
            Extracted value or None if path not found.
        """
        if not path:
            return None

        current = data
        parts = path.split(".")

        for part in parts:
            if current is None:
                return None

            # Handle array index: "images[0]" or "[0]"
            bracket_pos = part.find("[")
            if bracket_pos >= 0:
                key = part[:bracket_pos]
                index_str = part[bracket_pos + 1 : part.find("]")]
                if key:
                    if isinstance(current, dict):
                        current = current.get(key)
                    else:
                        return None
                try:
                    idx = int(index_str)
                    if isinstance(current, (list, tuple)) and 0 <= idx < len(current):
                        current = current[idx]
                    else:
                        return None
                except (ValueError, TypeError):
                    return None
            else:
                if isinstance(current, dict):
                    current = current.get(part)
                else:
                    return None

        return current

    @staticmethod
    def _parse_date(value: Any):
        """Try to parse a date string into a datetime.

        Args:
            value: Date string in various formats.

        Returns:
            datetime or None.
        """
        if not value:
            return None

        from datetime import datetime, timezone

        if isinstance(value, (int, float)):
            # Unix timestamp
            try:
                return datetime.fromtimestamp(value, tz=timezone.utc)
            except (ValueError, OSError):
                return None

        if not isinstance(value, str):
            return None

        # Try common date formats
        formats = [
            "%Y-%m-%d",            # 2024-01-15
            "%Y-%m-%dT%H:%M:%S",   # ISO without timezone
            "%Y-%m-%d %H:%M:%S",   # MySQL datetime
            "%Y%m%d",              # Compact: 20240115
        ]
        for fmt in formats:
            try:
                return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue

        return None
