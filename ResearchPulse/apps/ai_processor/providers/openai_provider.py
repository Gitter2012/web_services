# =============================================================================
# OpenAI AI Provider 模块
# =============================================================================
# 本模块实现了基于 OpenAI API 的云端 LLM 推理提供商。
# 在架构中，这是 BaseAIProvider 的另一个具体实现，适用于：
#   - 需要更高质量分析结果的生产环境
#   - 本地 Ollama 服务不可用时的备选方案
# 通过 OpenAI 的 Chat Completions API 完成内容分析。
# =============================================================================

"""OpenAI AI provider."""

from __future__ import annotations

import json
import logging
import time

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from settings import settings
from .base import BaseAIProvider, parse_json_response

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# OpenAI Provider 实现类
# 通过 HTTP 调用 OpenAI Chat Completions API 完成内容分析。
# 设计决策：
#   - 使用 httpx 而非 openai 官方 SDK，保持依赖轻量
#   - 默认使用 gpt-4o-mini 模型，平衡质量和成本
#   - temperature=0.3：低温度确保输出稳定性
# -----------------------------------------------------------------------------
class OpenAIProvider(BaseAIProvider):
    """OpenAI API provider.

    基于 OpenAI Chat Completions 的 AI 处理提供商。
    """

    def __init__(self, api_key: str | None = None, model: str | None = None):
        """Initialize OpenAI provider.

        初始化 OpenAI 提供商。

        Args:
            api_key: OpenAI API key.
            model: Model name override.
        """
        # API 密钥和模型名称可通过构造参数或配置文件传入
        self._api_key = api_key or ""
        self._model = model or "gpt-4o-mini"  # 默认使用性价比高的 gpt-4o-mini
        self._base_url = "https://api.openai.com/v1"
        # 持久化 HTTP 客户端，复用 TCP 连接
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        """Get or create the persistent HTTP client.

        获取或创建持久化的 HTTP 客户端实例。

        Returns:
            httpx.AsyncClient: Shared HTTP client.
        """
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=60,
                limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
            )
        return self._client

    async def close(self) -> None:
        """Close the persistent HTTP client.

        关闭持久化的 HTTP 客户端，释放连接池资源。
        """
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def is_available(self) -> bool:
        """Check availability of OpenAI provider.

        OpenAI 的可用性判断依赖 API 密钥是否存在。

        Returns:
            bool: Availability status.
        """
        # OpenAI 的可用性判断简单依赖 API 密钥是否存在
        # 不做实际网络请求，避免不必要的 API 调用消耗
        return bool(self._api_key)

    async def _call_api(self, headers: dict, payload: dict) -> dict:
        """Execute the OpenAI API call with retry logic.

        带重试逻辑的 OpenAI API 调用。

        Args:
            headers: HTTP headers including auth.
            payload: API request body.

        Returns:
            dict: Raw API response JSON.
        """
        client = self._get_client()
        response = await client.post(
            f"{self._base_url}/chat/completions",
            headers=headers,
            json=payload,
        )
        response.raise_for_status()
        return response.json()

    async def process_content(
        self, title: str, content: str, task_type: str = "content_high"
    ) -> dict:
        """Process content using OpenAI Chat Completions.

        调用 OpenAI API 进行内容分析并返回结构化结果。

        Args:
            title: Content title.
            content: Content body.
            task_type: Task type.

        Returns:
            dict: Standardized result payload.
        """
        # 构建 prompt，使用基类方法进行内容截断和模板选择
        prompt = self.build_prompt(title, content, task_type, settings.ai_max_content_length)

        # 根据任务类型调整最大输出 token 数
        # 高价值内容和论文需要更详细的输出（512 tokens）
        # 低价值内容只需简要信息（256 tokens）
        max_tokens = 512 if task_type in ("content_high", "paper_full") else 256

        # 构建 OpenAI Chat Completions API 请求头和请求体
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],  # 使用单轮对话格式
            "temperature": 0.3,    # 低温度确保输出稳定
            "max_tokens": max_tokens,
        }

        # 记录开始时间，计算处理耗时
        start_time = time.time()
        try:
            # 使用 tenacity 重试包装器调用 API，应对网络抖动和临时限流
            retrying_call = retry(
                stop=stop_after_attempt(settings.ai_max_retries),
                wait=wait_exponential(multiplier=settings.ai_retry_base_delay, max=10),
                retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)),
                reraise=True,
            )(self._call_api)
            result = await retrying_call(headers, payload)
            # 从 Chat Completions 响应中提取助手回复内容
            response_text = result["choices"][0]["message"]["content"]

            # 计算处理耗时（毫秒）
            duration_ms = int((time.time() - start_time) * 1000)
            # 解析 JSON 响应并提取标准化结果
            data = parse_json_response(response_text)
            extracted = self.extract_result(data)
            # 补充元信息
            extracted["provider"] = "openai"
            extracted["model"] = self._model
            extracted["duration_ms"] = duration_ms
            extracted["input_chars"] = len(prompt)
            extracted["output_chars"] = len(response_text)
            extracted["success"] = True
            return extracted

        except Exception as e:
            # 统一捕获所有异常，返回标准化错误结果
            # 设计决策：OpenAI 调用可能失败的原因多样（网络、限流、余额不足等），
            # 统一处理简化了错误处理逻辑
            return {
                "summary": "", "category": "其他", "importance_score": 5,
                "one_liner": "", "key_points": [], "impact_assessment": None,
                "actionable_items": [], "provider": "openai", "model": self._model,
                "success": False, "error_message": str(e),
            }
