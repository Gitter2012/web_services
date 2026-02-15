# =============================================================================
# OpenAI Embedding 提供商模块
# =============================================================================
# 本模块实现了基于 OpenAI API 的云端嵌入提供商。
# 在架构中，这是 BaseEmbeddingProvider 的备选实现，适用于：
#   - 需要更高质量嵌入的场景
#   - 多语言文本处理（OpenAI 的嵌入模型对中文支持更好）
#
# 默认使用 text-embedding-3-small 模型：
#   - 维度：1536
#   - 质量：高
#   - 成本：按 token 计费
# =============================================================================

"""OpenAI embedding provider."""

from __future__ import annotations

import logging

import httpx

from .base import BaseEmbeddingProvider

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# OpenAI Embedding 提供商实现类
# 通过 HTTP 调用 OpenAI Embeddings API 生成文本嵌入向量。
# 设计决策：
#   - 使用 httpx 同步客户端（encode 是同步方法，上层通过 to_thread 异步化）
#   - 维度根据模型名称自动推断：small -> 1536, large -> 3072
# -----------------------------------------------------------------------------
class OpenAIEmbeddingProvider(BaseEmbeddingProvider):
    """OpenAI API embedding provider.

    基于 OpenAI Embeddings API 的云端嵌入实现。
    """

    def __init__(self, api_key: str = "", model_name: str = "text-embedding-3-small"):
        """Initialize OpenAI embedding provider.

        初始化 OpenAI 嵌入提供商。

        Args:
            api_key: OpenAI API key.
            model_name: Embedding model name.
        """
        self._api_key = api_key
        self.model_name = model_name
        # 根据模型名称推断维度
        # text-embedding-3-small: 1536 维
        # text-embedding-3-large: 3072 维
        self._dimension = 1536 if "small" in model_name else 3072

    def encode(self, text: str) -> list[float]:
        """Encode a single text into an embedding vector.

        将单个文本编码为嵌入向量。

        Args:
            text: Input text.

        Returns:
            list[float]: Embedding vector.

        Raises:
            httpx.HTTPError: If the API request fails.
        """
        # 将单个文本编码为嵌入向量
        # 调用 OpenAI Embeddings API，返回向量数据
        import httpx as _httpx
        response = _httpx.post(
            "https://api.openai.com/v1/embeddings",
            headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
            json={"input": text, "model": self.model_name},
            timeout=30,
        )
        response.raise_for_status()
        # API 返回格式：{"data": [{"embedding": [...], "index": 0}]}
        return response.json()["data"][0]["embedding"]

    def encode_batch(self, texts: list[str]) -> list[list[float]]:
        """Encode multiple texts into embedding vectors.

        批量编码多个文本。

        Args:
            texts: List of input texts.

        Returns:
            list[list[float]]: Embedding vectors aligned to input order.

        Raises:
            httpx.HTTPError: If the API request fails.
        """
        # 批量编码多个文本
        # OpenAI API 支持在 input 中传入列表进行批量编码
        import httpx as _httpx
        response = _httpx.post(
            "https://api.openai.com/v1/embeddings",
            headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
            json={"input": texts, "model": self.model_name},
            timeout=60,  # 批量请求使用更长超时
        )
        response.raise_for_status()
        data = response.json()["data"]
        # 按 index 排序以确保返回顺序与输入顺序一致
        # 这是必要的，因为 API 返回结果的顺序不一定与输入顺序相同
        return [d["embedding"] for d in sorted(data, key=lambda x: x["index"])]

    @property
    def dimension(self) -> int:
        """Return embedding vector dimension.

        返回嵌入向量维度。

        Returns:
            int: Embedding dimension.
        """
        # 返回嵌入向量维度
        return self._dimension
