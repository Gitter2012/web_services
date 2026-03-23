"""HTTP client for pushing data from Pipeline machine (A) to Display machine (B)."""

from __future__ import annotations

import asyncio
import logging

import httpx

from settings import settings

logger = logging.getLogger(__name__)


class SyncClient:
    """Async HTTP client for sync API requests with retry support."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: int | None = None,
        retry_times: int | None = None,
        retry_delay: int | None = None,
    ):
        self.base_url = (base_url or settings.sync_sender_api_url).rstrip("/")
        self.api_key = api_key or settings.sync_sender_api_key
        self.timeout = timeout or settings.sync_sender_timeout
        self.retry_times = retry_times if retry_times is not None else settings.sync_sender_retry_times
        self.retry_delay = retry_delay or settings.sync_sender_retry_delay
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                headers={
                    "X-Sync-API-Key": self.api_key,
                    "Content-Type": "application/json",
                },
            )
        return self._client

    async def _post_with_retry(self, path: str, data: dict) -> dict:
        """POST with exponential backoff retry."""
        client = await self._get_client()
        url = f"{self.base_url}{path}"
        last_error: Exception | None = None

        for attempt in range(self.retry_times + 1):
            try:
                resp = await client.post(url, json=data)
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                last_error = e
                if attempt < self.retry_times:
                    delay = self.retry_delay * (2 ** attempt)
                    logger.warning(
                        "Sync request to %s failed (attempt %d/%d): %s, retry in %ds",
                        url, attempt + 1, self.retry_times + 1, e, delay,
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        "Sync request to %s failed after %d attempts: %s",
                        url, self.retry_times + 1, e,
                    )
        raise RuntimeError(
            f"Sync request to {url} failed after {self.retry_times + 1} attempts: {last_error}"
        )

    async def sync_articles(self, articles: list[dict]) -> dict[str, int]:
        """Push articles to B, return {natural_key: b_article_id}."""
        batch_size = settings.sync_sender_batch_size
        all_id_map: dict[str, int] = {}
        total = len(articles)

        for i in range(0, total, batch_size):
            batch = articles[i:i + batch_size]
            result = await self._post_with_retry(
                "/researchpulse/api/sync/articles",
                {"articles": batch},
            )
            all_id_map.update(result.get("id_map", {}))
            logger.debug(
                "Synced articles batch %d-%d/%d: %d mapped",
                i + 1, min(i + batch_size, total), total, len(result.get("id_map", {})),
            )

        return all_id_map

    async def sync_daily_reports(self, reports: list[dict]) -> dict:
        """Push daily reports to B."""
        return await self._post_with_retry(
            "/researchpulse/api/sync/daily-reports",
            {"reports": reports},
        )

    async def sync_reports(self, reports: list[dict]) -> dict:
        """Push weekly/monthly reports to B."""
        return await self._post_with_retry(
            "/researchpulse/api/sync/reports",
            {"reports": reports},
        )

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()
