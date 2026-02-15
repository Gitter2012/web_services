# =============================================================================
# Embedding Provider 抽象基类模块
# =============================================================================
# 本模块定义了嵌入提供商的抽象接口。
# 在架构中，它是嵌入提供商策略模式的核心，确保不同的嵌入模型
# （本地 sentence-transformers、OpenAI API）遵循统一的接口契约。
#
# 所有嵌入提供商必须实现三个接口：
#   - encode: 单文本编码
#   - encode_batch: 批量文本编码
#   - dimension: 返回向量维度
# =============================================================================

"""Base embedding provider."""

from __future__ import annotations

from abc import ABC, abstractmethod


# -----------------------------------------------------------------------------
# 嵌入提供商抽象基类
# 设计决策：
#   - encode 和 encode_batch 是同步方法（而非异步），
#     因为本地模型推理是 CPU 密集型操作，上层通过 asyncio.to_thread 包装
#   - dimension 作为属性暴露，便于创建 Milvus 集合时获取向量维度
# -----------------------------------------------------------------------------
class BaseEmbeddingProvider(ABC):
    """Abstract base class for embedding providers.

    嵌入提供商抽象基类，定义统一编码接口。
    """

    @abstractmethod
    def encode(self, text: str) -> list[float]:
        """Encode text to an embedding vector.

        将单个文本编码为浮点向量。

        Args:
            text: Input text.

        Returns:
            list[float]: Embedding vector.
        """
        # 将单个文本编码为浮点向量
        # 参数：text - 待编码的文本字符串
        # 返回值：浮点数列表，长度等于 dimension
        ...

    @abstractmethod
    def encode_batch(self, texts: list[str]) -> list[list[float]]:
        """Encode multiple texts.

        批量编码文本列表。

        Args:
            texts: List of input texts.

        Returns:
            list[list[float]]: List of embedding vectors.
        """
        # 批量编码多个文本
        # 参数：texts - 文本字符串列表
        # 返回值：嵌入向量列表，每个元素对应一个输入文本
        ...

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Return embedding dimension.

        返回嵌入向量的维度。

        Returns:
            int: Embedding dimension.
        """
        # 返回嵌入向量的维度
        # 例如：all-MiniLM-L6-v2 -> 384, text-embedding-3-small -> 1536
        ...
