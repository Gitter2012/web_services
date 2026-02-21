# =============================================================================
# Milvus 向量数据库客户端封装模块
# =============================================================================
# 本模块封装了与 Milvus 向量数据库的所有交互操作。
# Milvus 是一个高性能的开源向量数据库，专门用于存储和检索高维向量数据。
# 在架构中的角色：
#   - 向量存储层：存储文章的嵌入向量
#   - 相似度搜索引擎：基于 COSINE 距离的 ANN（近似最近邻）搜索
#
# 主要功能：
#   - 连接管理（connect/disconnect）
#   - 集合创建与管理（get_or_create_collection）
#   - 向量插入（insert_vectors）
#   - 相似度搜索（search_similar）
#   - 向量删除（delete_by_article_ids）
#   - 索引重建（rebuild_index）
#
# 设计决策：
#   - 使用 HNSW 索引：在精度和速度之间取得良好平衡
#   - 使用 COSINE 距离度量：适合文本嵌入的语义相似度比较
#   - 懒加载 pymilvus：只在实际使用时才导入，减少启动时的依赖检查
# =============================================================================

"""Milvus vector database client wrapper."""

from __future__ import annotations

import logging
from typing import Optional

from settings import settings
from common.feature_config import feature_config

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Milvus 客户端类
# 封装 pymilvus SDK 的常用操作，提供更简洁的接口。
# 使用延迟导入策略，pymilvus 仅在方法调用时才被导入。
# -----------------------------------------------------------------------------
class MilvusClient:
    """Milvus vector database client for article embeddings.

    Milvus 向量数据库客户端封装。
    """

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        collection_name: str | None = None,
    ):
        """Initialize Milvus client settings.

        初始化 Milvus 客户端配置。

        Args:
            host: Milvus host.
            port: Milvus port.
            collection_name: Collection name override.
        """
        # 从配置或参数获取 Milvus 连接信息
        self._host = host or feature_config.get("embedding.milvus_host", settings.milvus_host)
        self._port = port or feature_config.get_int("embedding.milvus_port", settings.milvus_port)
        self._collection_name = collection_name or feature_config.get("embedding.milvus_collection", settings.milvus_collection_name)
        self._collection = None       # 缓存的集合对象，避免重复获取
        self._connected = False       # 连接状态标记

    def connect(self) -> bool:
        """Connect to Milvus server.

        建立与 Milvus 的连接。

        Returns:
            bool: ``True`` if connected successfully.
        """
        # 建立与 Milvus 服务器的连接
        # 返回值：连接是否成功
        try:
            from pymilvus import connections
            connections.connect(
                alias="default",       # 使用默认连接别名
                host=self._host,
                port=self._port,
                timeout=30,            # 连接超时 30 秒
            )
            self._connected = True
            logger.info(f"Connected to Milvus at {self._host}:{self._port}")
            return True
        except Exception as e:
            logger.warning(f"Failed to connect to Milvus: {e}")
            self._connected = False
            return False

    def disconnect(self) -> None:
        """Disconnect from Milvus.

        断开与 Milvus 的连接。
        """
        # 断开与 Milvus 的连接
        try:
            from pymilvus import connections
            connections.disconnect("default")
            self._connected = False
        except Exception:
            pass

    @property
    def is_connected(self) -> bool:
        """Return connection status.

        返回当前连接状态。

        Returns:
            bool: Connection state.
        """
        # 返回当前连接状态
        return self._connected

    def get_or_create_collection(self, dimension: int = 384):
        """Get or create the article embeddings collection.

        获取或创建嵌入向量集合。

        Args:
            dimension: Vector dimension.

        Returns:
            Collection: Milvus collection instance.
        """
        # 获取或创建 Milvus 集合
        # 如果集合已存在则加载，否则创建新集合并建立索引
        # 参数：dimension - 向量维度，默认 384（对应 all-MiniLM-L6-v2）
        if self._collection is not None:
            return self._collection  # 使用缓存的集合对象

        from pymilvus import (
            Collection,
            CollectionSchema,
            DataType,
            FieldSchema,
            utility,
        )

        # 检查集合是否已存在
        if utility.has_collection(self._collection_name):
            self._collection = Collection(self._collection_name)
            self._collection.load()  # 将集合数据加载到内存中以支持搜索
            logger.info(f"Loaded existing collection: {self._collection_name}")
            return self._collection

        # 集合不存在，创建新集合
        # 定义集合 Schema：
        #   - id: 自增主键（Milvus 内部 ID）
        #   - article_id: 文章 ID（用于业务关联）
        #   - embedding: 浮点向量（实际的嵌入数据）
        fields = [
            FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
            FieldSchema(name="article_id", dtype=DataType.INT64),
            FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=dimension),
        ]
        schema = CollectionSchema(fields=fields, description="Article embeddings")
        self._collection = Collection(
            name=self._collection_name, schema=schema
        )

        # 创建 HNSW 索引
        # HNSW（Hierarchical Navigable Small World）是一种高效的 ANN 索引算法
        # M=16: 每个节点的最大邻居数，影响精度和内存使用
        # efConstruction=256: 构建时的搜索宽度，越大索引质量越高但构建越慢
        index_params = {
            "metric_type": "COSINE",      # 使用余弦相似度作为距离度量
            "index_type": "HNSW",
            "params": {"M": 16, "efConstruction": 256},
        }
        self._collection.create_index(field_name="embedding", index_params=index_params)
        self._collection.load()  # 加载到内存以支持搜索
        logger.info(f"Created collection: {self._collection_name} (dim={dimension})")
        return self._collection

    def insert_vectors(
        self, article_ids: list[int], embeddings: list[list[float]]
    ) -> list[int]:
        """Insert vectors into Milvus.

        写入向量并返回 Milvus 主键列表。

        Args:
            article_ids: Article ID list.
            embeddings: Embedding vectors.

        Returns:
            list[int]: Milvus primary keys.
        """
        # 将向量插入 Milvus 集合
        # 参数：
        #   article_ids: 文章 ID 列表
        #   embeddings: 对应的嵌入向量列表
        # 返回值：Milvus 自动生成的主键列表
        collection = self.get_or_create_collection(
            dimension=len(embeddings[0]) if embeddings else 384
        )
        # Milvus 按字段顺序接收数据：[article_id 列表, embedding 列表]
        entities = [article_ids, embeddings]
        insert_result = collection.insert(entities)
        collection.flush()  # 确保数据持久化到磁盘
        return insert_result.primary_keys

    def search_similar(
        self,
        query_vector: list[float],
        top_k: int = 10,
        exclude_article_id: int | None = None,
    ) -> list[tuple[int, float]]:
        """Search for similar vectors.

        基于向量相似度进行搜索。

        Args:
            query_vector: Query embedding vector.
            top_k: Number of results to return.
            exclude_article_id: Optional article ID to exclude.

        Returns:
            list[tuple[int, float]]: (article_id, similarity score) list.
        """
        # 在 Milvus 中搜索与查询向量最相似的向量
        # 参数：
        #   query_vector: 查询向量
        #   top_k: 返回最相似的前 K 个结果
        #   exclude_article_id: 排除的文章 ID（通常排除查询文章自身）
        # 返回值：[(文章ID, 相似度分数), ...] 的列表
        collection = self.get_or_create_collection(dimension=len(query_vector))
        # ef=64: 搜索时的搜索宽度，越大精度越高但速度越慢
        search_params = {"metric_type": "COSINE", "params": {"ef": 64}}

        # 构建过滤表达式，排除指定文章
        expr = f"article_id != {exclude_article_id}" if exclude_article_id else None

        results = collection.search(
            data=[query_vector],           # 查询向量（支持批量查询，这里只查一个）
            anns_field="embedding",        # 搜索的向量字段
            param=search_params,
            limit=top_k,
            expr=expr,                     # 过滤表达式
            output_fields=["article_id"],  # 返回的额外字段
        )

        # 提取搜索结果
        matches = []
        for hit in results[0]:  # results[0] 对应第一个查询向量的结果
            article_id = hit.entity.get("article_id")
            score = hit.score  # COSINE 相似度分数
            matches.append((article_id, score))
        return matches

    def delete_by_article_ids(self, article_ids: list[int]) -> None:
        """Delete vectors by article IDs.

        根据文章 ID 删除向量。

        Args:
            article_ids: Article IDs to delete.
        """
        # 根据文章 ID 删除对应的向量数据
        # 用于文章删除或需要重新计算嵌入的场景
        collection = self.get_or_create_collection()
        expr = f"article_id in {article_ids}"
        collection.delete(expr)

    def get_collection_stats(self) -> dict:
        """Get collection statistics.

        获取集合统计信息。

        Returns:
            dict: Collection stats (name, num_entities).
        """
        # 获取集合的统计信息（主要是向量数量）
        try:
            collection = self.get_or_create_collection()
            return {
                "name": self._collection_name,
                "num_entities": collection.num_entities,  # 集合中的实体总数
            }
        except Exception:
            return {"name": self._collection_name, "num_entities": 0}

    def rebuild_index(self, dimension: int = 384) -> bool:
        """Drop and recreate the collection index.

        重建向量索引。

        Args:
            dimension: Vector dimension.

        Returns:
            bool: ``True`` if rebuild succeeds.
        """
        # 重建 Milvus 索引
        # 操作步骤：释放集合 -> 删除旧索引 -> 创建新索引 -> 重新加载
        # 注意：这是一个阻塞操作，期间该集合的搜索将不可用
        try:
            from pymilvus import utility
            if utility.has_collection(self._collection_name):
                collection = self.get_or_create_collection(dimension)
                collection.release()     # 从内存中释放集合
                collection.drop_index()  # 删除旧索引
                # 重新创建 HNSW 索引（参数与初始创建时一致）
                index_params = {
                    "metric_type": "COSINE",
                    "index_type": "HNSW",
                    "params": {"M": 16, "efConstruction": 256},
                }
                collection.create_index(field_name="embedding", index_params=index_params)
                collection.load()        # 重新加载到内存
                logger.info("Milvus index rebuilt successfully")
                return True
            return False  # 集合不存在
        except Exception as e:
            logger.error(f"Failed to rebuild index: {e}")
            return False
