from __future__ import annotations

import time
from typing import Any, Dict, Optional

import httpx

_client: Optional[httpx.Client] = None


def get_client(timeout: float = 10.0) -> httpx.Client:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.Client(
            timeout=timeout,
            headers={"User-Agent": "ResearchPulse/1.0"},
        )
    return _client


def close_client() -> None:
    global _client
    if _client and not _client.is_closed:
        _client.close()
    _client = None


def get_text(
    url: str,
    params: Optional[Dict[str, Any]] = None,
    timeout: float = 10.0,
    retries: int = 2,
    backoff: float = 0.5,
) -> str:
    last_error: Optional[Exception] = None
    client = get_client(timeout=timeout)
    for attempt in range(retries + 1):
        try:
            response = client.get(url, params=params, timeout=timeout)
            response.raise_for_status()
            return response.text
        except Exception as exc:  # pragma: no cover - pass through
            last_error = exc
            if attempt < retries:
                time.sleep(backoff * (2**attempt))
            else:
                break
    raise RuntimeError(f"HTTP request failed: {last_error}")
