# =============================================================================
# Ollama AI Provider 模块
# =============================================================================
# 本模块实现了基于 Ollama 的本地 LLM 推理提供商。
# Ollama 是一个本地运行大语言模型的工具，通过 HTTP API 对外提供服务。
# 在架构中，这是 BaseAIProvider 的一个具体实现，适用于：
#   - 本地开发和测试环境（无需外部 API 密钥）
#   - 对数据隐私有要求的场景（数据不离开本机）
#   - 降低 API 调用成本的场景
# =============================================================================

"""Ollama AI provider using HTTP API."""

from __future__ import annotations

import logging
import time

import httpx

from settings import settings
from .base import BaseAIProvider, parse_json_response

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Ollama Provider 实现类
# 通过 HTTP 调用本地 Ollama 服务的 /api/generate 端点完成内容分析。
# 设计决策：
#   - 使用 httpx 异步客户端，与 FastAPI 的异步架构保持一致
#   - stream=False：关闭流式输出，一次性获取完整响应，简化解析逻辑
#   - keep_alive="300s"：保持模型在内存中 5 分钟，避免频繁加载卸载
# -----------------------------------------------------------------------------
class OllamaProvider(BaseAIProvider):
    """Ollama HTTP API provider for local LLM processing.

    本地 Ollama LLM 处理提供商。
    """

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout: int | None = None,
    ):
        """Initialize Ollama provider.

        初始化 Ollama 提供商。

        Args:
            base_url: Ollama base URL.
            model: Model name.
            timeout: Request timeout in seconds.
        """
        # 从配置或参数获取 Ollama 服务地址、模型名称和超时时间
        self._base_url = base_url or settings.ollama_base_url
        self._model = model or settings.ollama_model
        self._timeout = timeout or settings.ollama_timeout

    async def is_available(self) -> bool:
        """Check if Ollama service is running.

        检查 Ollama 服务是否可用。

        Returns:
            bool: Availability status.
        """
        # 通过调用 /api/tags 端点检测 Ollama 服务是否可用
        # 使用短超时（5秒）快速判断，避免阻塞
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{self._base_url}/api/tags")
                return response.status_code == 200
        except (httpx.RequestError, OSError):
            return False

    async def process_content(
        self, title: str, content: str, task_type: str = "content_high"
    ) -> dict:
        """Process content using Ollama API.

        调用 Ollama API 处理内容并返回结构化结果。

        Args:
            title: Content title.
            content: Content body.
            task_type: Task type.

        Returns:
            dict: Standardized result payload.
        """
        # 构建 prompt，内容长度受 ai_max_content_length 配置限制
        prompt = self.build_prompt(title, content, task_type, settings.ai_max_content_length)

        # 根据任务类型调整最大生成 token 数
        # 高价值内容和论文需要更详细的输出（512 tokens）
        # 低价值内容只需简要信息（256 tokens）
        num_predict = 512 if task_type in ("content_high", "paper_full") else 256

        # 构建 Ollama API 请求体
        payload = {
            "model": self._model,
            "prompt": prompt,
            "stream": False,           # 非流式，一次性返回完整结果
            "keep_alive": "300s",      # 模型保持加载 5 分钟
            "options": {
                "temperature": 0.3,    # 低温度以获得更确定性的输出
                "num_predict": num_predict,
            },
        }

        # 记录开始时间，用于计算处理耗时
        start_time = time.time()
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self._base_url}/api/generate",
                    json=payload,
                )
                response.raise_for_status()
                result = response.json()
                response_text = result.get("response", "")

            # 计算处理耗时（毫秒）
            duration_ms = int((time.time() - start_time) * 1000)
            # 解析 AI 返回的 JSON 文本
            data = parse_json_response(response_text)
            # 从解析后的数据中提取标准化结果
            extracted = self.extract_result(data)
            # 补充元信息
            extracted["provider"] = "ollama"
            extracted["model"] = self._model
            extracted["duration_ms"] = duration_ms
            extracted["input_chars"] = len(prompt)
            extracted["output_chars"] = len(response_text)
            extracted["success"] = True
            return extracted

        except httpx.HTTPStatusError as e:
            # HTTP 状态码错误（如 4xx、5xx）
            return self._error_result(f"HTTP {e.response.status_code}: {e.response.text[:200]}")
        except httpx.RequestError as e:
            # 网络连接错误（如连接超时、拒绝连接）
            return self._error_result(f"Request error: {e}")
        except Exception as e:
            # 其他未预期的错误
            return self._error_result(f"Unexpected error: {e}")

    def _error_result(self, error: str) -> dict:
        """Build a standardized error result payload.

        构造标准化的错误结果字典。

        Args:
            error: Error message.

        Returns:
            dict: Error result payload.
        """
        # 构造标准化的错误结果字典
        # 包含所有必要字段的默认值，确保上层代码不会因缺少字段而崩溃
        return {
            "summary": "", "category": "其他", "importance_score": 5,
            "one_liner": "", "key_points": [], "impact_assessment": None,
            "actionable_items": [], "provider": "ollama", "model": self._model,
            "success": False, "error_message": error,
        }
