# =============================================================================
# Sentence-Transformers 本地嵌入提供商模块
# =============================================================================
# 本模块实现了基于 sentence-transformers 库的本地嵌入提供商。
# 在架构中，这是 BaseEmbeddingProvider 的主要实现，适用于：
#   - 大部分场景的默认选择（免费、无需 API 密钥）
#   - 数据隐私敏感场景（所有计算在本地完成）
#   - 低延迟需求场景（无网络往返）
#
# 默认使用 all-MiniLM-L6-v2 模型：
#   - 维度：384
#   - 速度：快（CPU 即可运行）
#   - 质量：适合英文和多语言文本
# =============================================================================

"""Local embedding provider using sentence-transformers."""

from __future__ import annotations

import logging

from .base import BaseEmbeddingProvider

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Sentence-Transformers 提供商实现类
# 设计决策：
#   - 模型懒加载：首次 encode 调用时才加载模型，避免启动时的长等待
#   - 强制使用 CPU：避免 GPU 资源竞争和显存不足问题
#   - normalize_embeddings=True：输出归一化向量，使余弦相似度等价于点积
#   - TOKENIZERS_PARALLELISM=false：避免 tokenizer 多线程导致的警告
# -----------------------------------------------------------------------------
class SentenceTransformerProvider(BaseEmbeddingProvider):
    """Local embedding using sentence-transformers.

    基于 sentence-transformers 的本地嵌入实现。
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        """Initialize the local embedding provider.

        初始化本地嵌入提供商。

        Args:
            model_name: SentenceTransformer model name.
        """
        self.model_name = model_name
        self._model = None       # 延迟加载的模型实例
        self._dimension = None   # 模型输出维度，加载后确定

    def _get_model(self):
        """Lazily load the SentenceTransformer model.

        懒加载模型，首次调用时加载。
        """
        # 懒加载模型：首次调用时加载 sentence-transformers 模型
        # 设置 TOKENIZERS_PARALLELISM 环境变量避免 HuggingFace tokenizer 的警告
        if self._model is None:
            import os
            os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
            from sentence_transformers import SentenceTransformer
            logger.info(f"Loading embedding model: {self.model_name}")
            self._model = SentenceTransformer(self.model_name, device="cpu")
            # 加载完成后记录维度信息
            self._dimension = self._model.get_sentence_embedding_dimension()
        return self._model

    def encode(self, text: str) -> list[float]:
        """Encode a single text into an embedding vector.

        将单个文本编码为归一化的嵌入向量。

        Args:
            text: Input text.

        Returns:
            list[float]: Embedding vector.
        """
        # 将单个文本编码为归一化的嵌入向量
        # convert_to_numpy=True: 返回 numpy 数组（后续 .tolist() 转为 Python 列表）
        # normalize_embeddings=True: 输出 L2 归一化向量
        # show_progress_bar=False: 关闭进度条（单文本不需要）
        model = self._get_model()
        embedding = model.encode(
            text, convert_to_numpy=True, normalize_embeddings=True, show_progress_bar=False
        )
        return embedding.tolist()

    def encode_batch(self, texts: list[str]) -> list[list[float]]:
        """Encode multiple texts into embedding vectors.

        批量编码多个文本为归一化的嵌入向量。

        Args:
            texts: List of input texts.

        Returns:
            list[list[float]]: Embedding vectors.
        """
        # 批量编码多个文本为归一化的嵌入向量
        # sentence-transformers 内部会自动进行 padding 和批处理优化
        model = self._get_model()
        embeddings = model.encode(
            texts, convert_to_numpy=True, normalize_embeddings=True, show_progress_bar=False
        )
        return embeddings.tolist()

    @property
    def dimension(self) -> int:
        """Return embedding vector dimension.

        返回嵌入向量维度。

        Returns:
            int: Embedding dimension.
        """
        # 返回嵌入向量维度
        # 如果模型尚未加载，会触发模型加载以获取维度信息
        if self._dimension is None:
            self._get_model()
        return self._dimension
