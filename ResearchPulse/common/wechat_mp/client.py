# =============================================================================
# 模块: common/wechat_mp/client.py
# 功能: 微信公众号 API 客户端
# 架构角色: 通用基础设施层，封装微信公众号 HTTP API 调用
# 设计决策:
#   1. 使用 httpx.AsyncClient 进行异步 HTTP 请求
#   2. 内建 token 自动管理（通过 TokenManager）
#   3. 统一错误处理：微信 API 返回 errcode != 0 时抛出 WeChatAPIError
#   4. token 过期自动重试：收到 errcode=40001/42001 时刷新 token 并重试一次
#   5. 支持上传图片（永久素材和图文消息内图片）
# =============================================================================

"""WeChat Official Account (微信公众号) API client."""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

import httpx

from common.wechat_mp.token_manager import TokenManager

logger = logging.getLogger(__name__)


class WeChatAPIError(Exception):
    """Exception raised when WeChat API returns an error.

    微信 API 返回错误时抛出的异常。

    Attributes:
        errcode: 微信 API 错误码
        errmsg: 微信 API 错误信息
    """

    def __init__(self, errcode: int, errmsg: str):
        self.errcode = errcode
        self.errmsg = errmsg
        super().__init__(f"WeChat API error {errcode}: {errmsg}")


# Token 过期相关的错误码
_TOKEN_EXPIRED_CODES = {40001, 42001, 40014}


class WeChatMPClient:
    """WeChat Official Account API client.

    微信公众号 API 客户端，提供以下功能：
    1. 获取 access_token
    2. 创建草稿（draft/add）
    3. 上传图文消息内图片（media/uploadimg）
    4. 上传永久素材（material/add_material）

    Token 管理由内置的 TokenManager 处理，调用方无需手动管理 token。

    Usage:
        client = WeChatMPClient(appid="...", secret="...")
        media_id = await client.create_draft(articles=[...])
        await client.close()
    """

    BASE_URL = "https://api.weixin.qq.com"

    def __init__(
        self,
        appid: str,
        secret: str,
        timeout: float = 30.0,
    ):
        """Initialize WeChatMPClient.

        Args:
            appid: 微信公众号 AppID.
            secret: 微信公众号 AppSecret.
            timeout: HTTP request timeout in seconds.
        """
        self.appid = appid
        self.secret = secret
        self._http_client = httpx.AsyncClient(
            timeout=timeout,
        )
        self.token_manager = TokenManager(self)

    async def close(self) -> None:
        """Close the HTTP client.

        关闭 HTTP 客户端，释放连接资源。
        """
        await self._http_client.aclose()

    # ========================================================================
    # Token 获取（由 TokenManager 调用，不应直接使用）
    # ========================================================================

    async def fetch_access_token(self) -> dict[str, Any]:
        """Fetch a new access_token from WeChat API.

        从微信 API 获取新的 access_token。
        此方法由 TokenManager 内部调用，外部代码应使用
        token_manager.get_valid_token() 获取 token。

        Returns:
            dict with keys: access_token, expires_in

        Raises:
            WeChatAPIError: If the API returns an error.
        """
        url = f"{self.BASE_URL}/cgi-bin/token"
        params = {
            "grant_type": "client_credential",
            "appid": self.appid,
            "secret": self.secret,
        }

        resp = await self._http_client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()

        if "errcode" in data and data["errcode"] != 0:
            raise WeChatAPIError(data["errcode"], data.get("errmsg", "unknown"))

        return data

    # ========================================================================
    # 内部 HTTP 方法（带自动 token 注入和过期重试）
    # ========================================================================

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[dict] = None,
        json_data: Optional[dict] = None,
        files: Optional[dict] = None,
        retry_on_token_expired: bool = True,
    ) -> dict[str, Any]:
        """Send an authenticated request to WeChat API.

        发送带 access_token 认证的请求到微信 API。

        自动处理：
        1. 获取/缓存 access_token 并注入到请求参数中
        2. Token 过期时自动刷新并重试一次

        Args:
            method: HTTP method (GET/POST).
            path: API path (e.g., "/cgi-bin/draft/add").
            params: URL query parameters.
            json_data: JSON request body.
            files: Multipart file upload data.
            retry_on_token_expired: Whether to retry on token expiry.

        Returns:
            Parsed JSON response dict.

        Raises:
            WeChatAPIError: If the API returns an error.
        """
        token = await self.token_manager.get_valid_token()

        url = f"{self.BASE_URL}{path}"
        if params is None:
            params = {}
        params["access_token"] = token

        # 文件上传时不设置 Content-Type，让 httpx 自动处理 multipart
        if files:
            resp = await self._http_client.post(
                url,
                params=params,
                files=files,
            )
        elif method.upper() == "POST":
            resp = await self._http_client.post(
                url,
                params=params,
                json=json_data,
            )
        else:
            resp = await self._http_client.get(url, params=params)

        resp.raise_for_status()
        data = resp.json()

        # 检查微信 API 错误
        errcode = data.get("errcode", 0)
        if errcode != 0:
            # Token 过期：刷新后重试一次
            if errcode in _TOKEN_EXPIRED_CODES and retry_on_token_expired:
                logger.warning(
                    "WeChat token expired (errcode=%d), refreshing and retrying...",
                    errcode,
                )
                self.token_manager.invalidate()
                return await self._request(
                    method,
                    path,
                    params={k: v for k, v in params.items() if k != "access_token"},
                    json_data=json_data,
                    files=files,
                    retry_on_token_expired=False,  # 不再重试
                )
            raise WeChatAPIError(errcode, data.get("errmsg", "unknown"))

        return data

    # ========================================================================
    # 草稿箱接口
    # ========================================================================

    async def create_draft(self, articles: list[dict[str, Any]]) -> str:
        """Create a draft with multiple articles.

        创建包含多篇文章的草稿。

        Args:
            articles: List of article dicts, each containing:
                - title (str): 标题，最多 32 字
                - author (str): 作者
                - digest (str): 摘要，最多 128 字
                - content (str): HTML 正文内容
                - thumb_media_id (str): 封面图永久素材 media_id
                - content_source_url (str, optional): 原文链接
                - need_open_comment (int, optional): 是否打开评论 0/1
                - only_fans_can_comment (int, optional): 是否仅粉丝可评论 0/1

        Returns:
            Draft media_id string.

        Raises:
            WeChatAPIError: If draft creation fails.
        """
        if not articles:
            raise ValueError("At least one article is required")

        if len(articles) > 8:
            raise ValueError(
                f"WeChat draft supports at most 8 articles, got {len(articles)}"
            )

        data = await self._request(
            "POST",
            "/cgi-bin/draft/add",
            json_data={"articles": articles},
        )

        media_id = data.get("media_id", "")
        if not media_id:
            raise WeChatAPIError(-1, "Draft creation returned empty media_id")

        logger.info(
            "Created WeChat draft with %d articles, media_id=%s",
            len(articles),
            media_id,
        )
        return media_id

    # ========================================================================
    # 图片上传接口
    # ========================================================================

    async def upload_article_image(
        self, image_data: bytes, filename: str = "image.jpg"
    ) -> str:
        """Upload an image for use in article content.

        上传图文消息内图片，返回微信 CDN URL。
        上传的图片不占用永久素材配额，但图片仅能在公众号文章中使用。

        Args:
            image_data: Image binary data.
            filename: Image filename.

        Returns:
            WeChat CDN URL string for the uploaded image.

        Raises:
            WeChatAPIError: If upload fails.
        """
        data = await self._request(
            "POST",
            "/cgi-bin/media/uploadimg",
            files={"media": (filename, image_data)},
        )

        url = data.get("url", "")
        if not url:
            raise WeChatAPIError(-1, "Image upload returned empty URL")

        logger.info("Uploaded article image: %s -> %s", filename, url)
        return url

    async def upload_permanent_material(
        self,
        image_data: bytes,
        filename: str = "thumb.jpg",
        media_type: str = "thumb",
    ) -> str:
        """Upload a permanent material (e.g., thumb image).

        上传永久素材（如封面图），返回 media_id。

        Args:
            image_data: Image binary data.
            filename: Image filename.
            media_type: Material type (image/thumb/voice/video).

        Returns:
            Permanent media_id string.

        Raises:
            WeChatAPIError: If upload fails.
        """
        data = await self._request(
            "POST",
            "/cgi-bin/material/add_material",
            params={"type": media_type},
            files={"media": (filename, image_data)},
        )

        media_id = data.get("media_id", "")
        if not media_id:
            raise WeChatAPIError(-1, "Material upload returned empty media_id")

        logger.info("Uploaded permanent material: %s -> %s", filename, media_id)
        return media_id
