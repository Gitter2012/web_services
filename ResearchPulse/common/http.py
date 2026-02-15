# =============================================================================
# 模块: common/http.py
# 功能: HTTP 客户端工具模块，为爬虫和外部 API 调用提供健壮的 HTTP 请求能力
# 架构角色: 作为通用 HTTP 基础设施层，被爬虫模块（crawler）等上层模块调用。
#   提供以下核心能力：
#   1. User-Agent 轮换：每次请求随机选择浏览器 UA，模拟真实浏览器行为
#   2. 完整的浏览器请求头模拟（Sec-Fetch-*、Referer 等）
#   3. 指数退避重试机制，支持 Retry-After 响应头
#   4. HTTP 客户端自动回收：每 N 次请求或连续错误后重建连接池
#   5. 可选的响应缓存（委托给 cache 模块）
#   6. 请求频率控制（delay + jitter 防止被封禁）
#
# 设计决策:
#   - 使用 httpx.Client（同步），而非 httpx.AsyncClient，因为爬虫任务在线程池中执行
#   - 客户端采用连接池 + 定期回收策略，平衡性能与反指纹检测
#   - HTTP/1.1 模式更接近普通浏览器行为（HTTP/2 可能触发某些反爬机制）
#   - 超时参数细分为 connect/read/write/pool 四个维度，防止连接池耗尽导致的死锁
# =============================================================================
from __future__ import annotations

import logging
import random
import time
import hashlib
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse

import httpx

# 导入缓存模块的读写函数
from common.cache import cache_response, get_cached_response

logger = logging.getLogger(__name__)

# 全局共享的 httpx 客户端实例（惰性创建）
_client: Optional[httpx.Client] = None
# 当前客户端已处理的请求计数
_request_count: int = 0
# 每处理 N 个请求后重建客户端，防止连接指纹被追踪
_SESSION_ROTATE_EVERY: int = 25  # Recreate client after N requests

# 连续网络错误达到此阈值后强制重建客户端
# 陈旧/断开的连接池连接可能导致反复超时，重建可恢复新的 TCP 连接
_CONSECUTIVE_ERRORS_BEFORE_ROTATE: int = 2
# 当前连续网络错误计数
_consecutive_errors: int = 0

# ---------------------------------------------------------------------------
# User-Agent 轮换列表 —— 使用真实、完整的浏览器 UA 字符串
# 覆盖主流浏览器和操作系统组合，使请求看起来像来自不同用户
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
    # Chrome on Android
    "Mozilla/5.0 (Linux; Android 13; SM-G991B) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
    # Safari on iPhone
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1",
]

# Accept 请求头变体，根据请求内容类型选择合适的 Accept 头
_ACCEPT_HTML = "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
_ACCEPT_XML = "application/atom+xml,application/xml,text/xml;q=0.9,*/*;q=0.8"
_ACCEPT_JSON = "application/json, text/javascript, */*; q=0.01"
_ACCEPT_IMAGE = "image/avif,image/webp,image/apng,image/*,*/*;q=0.8"

# Referer 模式映射：根据目标网站域名自动设置合适的 Referer 头
# 使请求看起来像从该网站内部发起的导航
_REFERER_PATTERNS = {
    "arxiv.org": "https://arxiv.org/",
    "github.com": "https://github.com/",
    "twitter.com": "https://twitter.com/",
    "x.com": "https://x.com/",
    "mp.weixin.qq.com": "https://weixin.qq.com/",
}


def _get_user_agent() -> str:
    """Get a random user-agent string.

    随机选择一个 User-Agent 字符串。
    每次请求使用不同的 UA，降低被识别为爬虫的风险。

    Returns:
        str: Randomly chosen User-Agent string.
    """
    return random.choice(_USER_AGENTS)


def _build_headers(ua: str, referer: Optional[str] = None) -> Dict[str, str]:
    """Build a realistic set of browser headers for a single request.

    构建一套逼真的浏览器请求头。
    包括 Sec-Fetch-* 安全元数据头（现代浏览器会自动发送这些头），
    使请求更难被服务器端的反爬机制识别。

    Args:
        ua: User-Agent string.
        referer: Optional Referer header.

    Returns:
        Dict[str, str]: Headers dictionary.
    """
    headers: Dict[str, str] = {
        "User-Agent": ua,
        "Accept": _ACCEPT_HTML,
        "Accept-Encoding": "gzip, deflate, br",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        # Sec-Fetch 安全元数据头（现代浏览器标准）
        "Sec-Fetch-Dest": "document",           # 请求目标类型
        "Sec-Fetch-Mode": "navigate",           # 导航模式
        "Sec-Fetch-Site": "none" if referer is None else "same-origin",  # 请求来源关系
        "Sec-Fetch-User": "?1",                 # 用户触发的请求
        "Cache-Control": "max-age=0",           # 不使用浏览器缓存
    }
    if referer:
        headers["Referer"] = referer
    return headers


def get_client(timeout: float = 10.0) -> httpx.Client:
    """Return (and lazily create) a shared httpx.Client.

    The client is created with minimal default headers; per-request headers
    are set via ``_build_headers`` inside ``get_text``. Uses explicit timeout
    components to avoid hangs on stale pooled connections.

    获取（并惰性创建）全局共享的 httpx 客户端。
    客户端创建时不设置默认请求头，每次请求通过 _build_headers 动态构建。
    超时参数细分为四个维度，防止连接池耗尽等问题导致的无限等待。

    Args:
        timeout: Request timeout in seconds.

    Returns:
        httpx.Client: Shared HTTP client instance.
    """
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.Client(
            timeout=httpx.Timeout(
                connect=min(timeout, 10.0),   # TCP 连接超时：上限 10 秒
                read=timeout,                 # 读取响应体超时
                write=timeout,                # 写入请求体超时
                pool=min(timeout, 5.0),       # 等待连接池空闲位置超时：上限 5 秒
            ),
            follow_redirects=True,            # 自动跟随重定向
            http2=False,  # 使用 HTTP/1.1，更接近普通浏览器的爬取行为
            limits=httpx.Limits(
                max_connections=10,           # 最大并发连接数
                max_keepalive_connections=5,  # 最大保活连接数
                keepalive_expiry=30.0,        # 空闲连接 30 秒后释放
            ),
        )
    return _client


def rotate_client() -> None:
    """Close and discard the current client.

    关闭并丢弃当前客户端，下次调用 get_client 时会创建新的客户端。
    用于定期轮换或错误恢复。

    Side Effects:
        - Closes existing client connections.
        - Resets request counters.
    """
    global _client, _request_count
    if _client and not _client.is_closed:
        _client.close()
    _client = None
    _request_count = 0


def close_client() -> None:
    """Close the global HTTP client.

    通常在应用关闭时调用，释放所有连接资源。

    Side Effects:
        - Closes client connections and clears the global reference.
    """
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
    """Fetch text from a URL with retries, rate limiting, and caching.

    Improvements:
    - User-Agent rotates per request.
    - Browser-like headers (Sec-Fetch-*, Referer).
    - 429/503 honors ``Retry-After``.
    - Client is recycled every ``_SESSION_ROTATE_EVERY`` requests.

    从 URL 获取文本内容，具备完善的重试、频率控制和缓存机制。
    这是爬虫模块的核心 HTTP 请求函数。

    Args:
        url: URL to fetch.
        params: Query parameters.
        timeout: Request timeout in seconds.
        retries: Number of retries on failure.
        backoff: Base backoff in seconds for exponential retry.
        delay: Base delay in seconds before each request attempt.
        jitter: Random jitter (+-) added to delay.
        cache_ttl: Cache TTL in seconds (0 disables caching).
        referer: Optional Referer header to include.

    Returns:
        str: Response text body.

    Raises:
        RuntimeError: If all retries are exhausted.
    """
    global _request_count

    # 如果启用了缓存，先尝试从缓存获取
    if cache_ttl > 0:
        cached = get_cached_response(url, params, cache_ttl)
        if cached is not None:
            return cached

    global _consecutive_errors
    last_error: Optional[Exception] = None
    client = get_client(timeout=timeout)

    # 为每个请求构建独立的超时配置
    # connect 和 pool 超时有上限保护，防止过大的 timeout 导致连接阶段等待过久
    req_timeout = httpx.Timeout(
        connect=min(timeout, 10.0),
        read=timeout,
        write=timeout,
        pool=min(timeout, 5.0),
    )

    # 重试循环：最多尝试 retries + 1 次（1 次原始请求 + retries 次重试）
    for attempt in range(retries + 1):
        try:
            # 请求前的频率控制延迟
            # delay 提供基础延迟，jitter 增加随机性，使请求间隔不那么规律
            if delay > 0 or jitter > 0:
                actual_delay = delay
                if jitter > 0:
                    actual_delay += random.uniform(-jitter, jitter)
                    actual_delay = max(0.1, actual_delay)  # 最低延迟 100 毫秒
                if actual_delay > 0:
                    time.sleep(actual_delay)

            # 每次请求都轮换 User-Agent 并重建请求头
            ua = _get_user_agent()
            req_headers = _build_headers(ua, referer=referer)

            # 对 API/Feed 类端点使用 XML Accept 头
            if "api/query" in url or "/rss/" in url:
                req_headers["Accept"] = _ACCEPT_XML

            response = client.get(
                url, params=params, timeout=req_timeout, headers=req_headers
            )

            # ------- 速率限制 / 反爬虫专用处理 -------
            # 429 (Too Many Requests) 和 503 (Service Unavailable) 通常表示被限流
            if response.status_code in (429, 503):
                # 优先使用服务器返回的 Retry-After 头指示的等待时间
                retry_after = _parse_retry_after(response.headers.get("Retry-After"))
                # 取 Retry-After 和指数退避中的较大值
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
                # 遇到限流后轮换客户端，获取新的 TCP 连接（可能分配新的源端口）
                rotate_client()
                client = get_client(timeout=timeout)
                continue

            # 其他非 2xx 状态码将抛出 HTTPStatusError
            response.raise_for_status()

            # 请求成功，缓存响应
            if cache_ttl > 0:
                cache_response(url, response.text, params)

            # 重置连续错误计数器
            _consecutive_errors = 0

            # 客户端轮换记账：达到阈值时重建客户端
            _request_count += 1
            if _request_count >= _SESSION_ROTATE_EVERY:
                rotate_client()

            return response.text

        except httpx.HTTPStatusError as exc:
            last_error = exc
            status_code = exc.response.status_code
            # 4xx 客户端错误（除 429 已在上面处理）不值得重试
            if 400 <= status_code < 500:
                logger.warning(
                    "HTTP %d from %s – not retrying", status_code, url
                )
                break
            # 5xx 服务端错误可以重试
            if attempt < retries:
                wait = backoff * (2 ** attempt)
                logger.debug(
                    "HTTP %d from %s – retry in %.1fs (attempt %d/%d)",
                    status_code, url, wait, attempt + 1, retries + 1,
                )
                time.sleep(wait)
            else:
                break

        except (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError) as exc:
            # 网络层错误：超时、连接失败、读取错误
            last_error = exc
            _consecutive_errors += 1
            # 连续错误达到阈值时轮换客户端，清除可能损坏的连接池
            if _consecutive_errors >= _CONSECUTIVE_ERRORS_BEFORE_ROTATE:
                logger.debug(
                    "Rotating HTTP client after %d consecutive errors",
                    _consecutive_errors,
                )
                rotate_client()
                client = get_client(timeout=timeout)
                _consecutive_errors = 0
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
            # 未预期的异常，仍然尝试重试
            last_error = exc
            if attempt < retries:
                time.sleep(backoff * (2 ** attempt))
            else:
                break

    # 所有重试用尽，抛出 RuntimeError 并附带最后一次错误信息
    error_type = type(last_error).__name__ if last_error else "UnknownError"
    raise RuntimeError(f"HTTP request failed ({error_type}): {last_error}") from last_error


def _parse_retry_after(value: Optional[str]) -> float:
    """Parse a ``Retry-After`` header value to seconds.

    The header may be an integer (delay-seconds) or an HTTP-date. We only
    handle the integer form here; for dates we fall back to a default.

    解析 HTTP Retry-After 响应头的值为秒数。
    该头可以是整数（延迟秒数）或 HTTP 日期格式。
    这里只处理整数形式，日期形式回退到默认值 5 秒。

    Args:
        value: Raw Retry-After header value.

    Returns:
        float: Wait seconds (minimum 1.0).
    """
    if not value:
        return 5.0  # 头部缺失时使用保守的默认值
    try:
        return max(1.0, float(value))
    except (ValueError, TypeError):
        return 5.0
