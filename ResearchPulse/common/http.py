from __future__ import annotations

import logging
import random
import time
from typing import Any, Dict, Optional

import httpx

from common.cache import cache_response, get_cached_response

logger = logging.getLogger(__name__)

_client: Optional[httpx.Client] = None
_request_count: int = 0
_SESSION_ROTATE_EVERY: int = 25  # Recreate client after N requests

# ---------------------------------------------------------------------------
# User-Agent rotation – realistic, complete strings
# ---------------------------------------------------------------------------
_USER_AGENTS = [
    # Chrome on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    # Chrome on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    # Chrome on Linux
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    # Firefox on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) "
    "Gecko/20100101 Firefox/121.0",
    # Firefox on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) "
    "Gecko/20100101 Firefox/121.0",
    # Firefox on Linux
    "Mozilla/5.0 (X11; Linux x86_64; rv:121.0) "
    "Gecko/20100101 Firefox/121.0",
    # Safari on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    # Edge on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
]

# Accept header variants matching the UA family
_ACCEPT_HTML = "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
_ACCEPT_XML = "application/atom+xml,application/xml,text/xml;q=0.9,*/*;q=0.8"


def _get_user_agent() -> str:
    """Get a random user-agent string."""
    return random.choice(_USER_AGENTS)


def _build_headers(ua: str, referer: Optional[str] = None) -> Dict[str, str]:
    """Build a realistic set of browser headers for a single request."""
    headers: Dict[str, str] = {
        "User-Agent": ua,
        "Accept": _ACCEPT_HTML,
        "Accept-Encoding": "gzip, deflate, br",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        # Sec-Fetch metadata (modern browsers send these)
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none" if referer is None else "same-origin",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0",
    }
    if referer:
        headers["Referer"] = referer
    return headers


def get_client(timeout: float = 10.0) -> httpx.Client:
    """Return (and lazily create) a shared httpx.Client.

    The client is intentionally created with *minimal* default headers;
    per-request headers are added via ``_build_headers`` inside ``get_text``.
    """
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            http2=False,  # HTTP/1.1 is more "normal browser" for scraping
        )
    return _client


def rotate_client() -> None:
    """Close and discard the current client so the next call gets a fresh one."""
    global _client, _request_count
    if _client and not _client.is_closed:
        _client.close()
    _client = None
    _request_count = 0


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
    delay: float = 0.0,
    jitter: float = 0.0,
    cache_ttl: int = 0,
    referer: Optional[str] = None,
) -> str:
    """
    Fetch text from URL with retry logic, rate limiting, and caching.

    Improvements over the previous version:
    - User-Agent is rotated **per request** (not per client lifetime).
    - Full set of browser-like headers (Sec-Fetch-*, Referer, etc.).
    - HTTP 429 / 503 responses respect the ``Retry-After`` header.
    - The underlying httpx.Client is automatically recycled every
      ``_SESSION_ROTATE_EVERY`` requests to avoid connection fingerprinting.

    Args:
        url: URL to fetch
        params: Query parameters
        timeout: Request timeout in seconds
        retries: Number of retries on failure
        backoff: Base backoff in seconds for exponential retry
        delay: Base delay in seconds before each request attempt
        jitter: Random jitter (±) to add to delay in seconds
        cache_ttl: Cache TTL in seconds (0 = no caching)
        referer: Optional Referer header to include

    Returns:
        Response text

    Raises:
        RuntimeError: If all retries exhausted
    """
    global _request_count

    # Try cache first if TTL > 0
    if cache_ttl > 0:
        cached = get_cached_response(url, params, cache_ttl)
        if cached is not None:
            return cached

    last_error: Optional[Exception] = None
    client = get_client(timeout=timeout)

    for attempt in range(retries + 1):
        try:
            # Apply rate limiting delay before request
            if delay > 0 or jitter > 0:
                actual_delay = delay
                if jitter > 0:
                    actual_delay += random.uniform(-jitter, jitter)
                    actual_delay = max(0.1, actual_delay)  # Floor at 100ms
                if actual_delay > 0:
                    time.sleep(actual_delay)

            # Rotate User-Agent and rebuild headers for every attempt
            ua = _get_user_agent()
            req_headers = _build_headers(ua, referer=referer)

            # Use XML accept header for API/feed endpoints
            if "api/query" in url or "/rss/" in url:
                req_headers["Accept"] = _ACCEPT_XML

            response = client.get(
                url, params=params, timeout=timeout, headers=req_headers
            )

            # ------- Rate-limit / anti-bot specific handling -------
            if response.status_code in (429, 503):
                retry_after = _parse_retry_after(response.headers.get("Retry-After"))
                wait = max(retry_after, backoff * (2 ** attempt))
                logger.warning(
                    "Rate limited (%s) by %s – waiting %.1fs (attempt %d/%d)",
                    response.status_code,
                    url,
                    wait,
                    attempt + 1,
                    retries + 1,
                )
                time.sleep(wait)
                # After a rate-limit hit, rotate the client to get a fresh
                # connection (and potentially a different source port).
                rotate_client()
                client = get_client(timeout=timeout)
                continue

            response.raise_for_status()

            # Cache successful response
            if cache_ttl > 0:
                cache_response(url, response.text, params)

            # Session rotation bookkeeping
            _request_count += 1
            if _request_count >= _SESSION_ROTATE_EVERY:
                rotate_client()

            return response.text

        except httpx.HTTPStatusError as exc:
            last_error = exc
            status = exc.response.status_code
            # For 4xx (except 429 handled above), retrying won't help
            if 400 <= status < 500:
                logger.warning(
                    "HTTP %d from %s – not retrying", status, url
                )
                break
            if attempt < retries:
                wait = backoff * (2 ** attempt)
                logger.debug(
                    "HTTP %d from %s – retry in %.1fs (attempt %d/%d)",
                    status, url, wait, attempt + 1, retries + 1,
                )
                time.sleep(wait)
            else:
                break

        except (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError) as exc:
            last_error = exc
            if attempt < retries:
                wait = backoff * (2 ** attempt)
                logger.debug(
                    "Network error (%s) fetching %s – retry in %.1fs (attempt %d/%d)",
                    type(exc).__name__, url, wait, attempt + 1, retries + 1,
                )
                time.sleep(wait)
            else:
                break

        except Exception as exc:  # pragma: no cover – unexpected
            last_error = exc
            if attempt < retries:
                time.sleep(backoff * (2 ** attempt))
            else:
                break

    error_type = type(last_error).__name__ if last_error else "UnknownError"
    raise RuntimeError(f"HTTP request failed ({error_type}): {last_error}") from last_error


def _parse_retry_after(value: Optional[str]) -> float:
    """Parse a ``Retry-After`` header value to seconds.

    The header may be an integer (delay-seconds) or an HTTP-date. We only
    handle the integer form here; for dates we fall back to a sane default.
    """
    if not value:
        return 5.0  # Conservative default when header is absent
    try:
        return max(1.0, float(value))
    except (ValueError, TypeError):
        return 5.0
