# =============================================================================
# 模块: common/feature_config.py
# 功能: 功能配置服务，提供数据库驱动的集中式配置管理系统
# 架构角色: 作为运行时配置的核心服务层，位于 settings.py（静态配置）之上，
#   提供动态、可热更新的配置能力。主要特点：
#   1. 数据库持久化：配置存储在 system_config 表中
#   2. 内存缓存：60 秒 TTL 的缓存层，减少数据库查询
#   3. 默认值种子：首次启动时从 DEFAULT_CONFIGS 字典写入数据库
#   4. 管理员可通过 API 动态修改配置，无需重启服务
#   5. 功能开关（Feature Toggle）：控制各模块的启用/禁用状态
#
# 设计决策:
#   - YAML defaults.yaml 仅作为首次运行的种子数据源
#   - 运行时所有读取都通过内存缓存 -> 数据库的链路
#   - 管理员通过 API 修改的值会直接更新数据库和缓存
#   - 使用模块级单例模式（feature_config），全局共享同一实例
# =============================================================================
"""Feature configuration service for ResearchPulse v2.

Provides a centralized, database-backed configuration system with in-memory
caching.  The ``SystemConfig`` table acts as the dynamic configuration hub:

- YAML ``defaults.yaml`` serves only as the initial seed (first-run).
- At runtime every read goes through an in-memory cache (TTL 60 s) backed
  by the database.
- Admin APIs can update values; changes take effect within the cache TTL.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

from fastapi import Depends, HTTPException

logger = logging.getLogger(__name__)

# =============================================================================
# 默认配置字典
# 键使用点分隔的命名空间前缀：feature.* / scheduler.* / ai.* / embedding.* / event.*
# 值是元组 (默认值字符串, 配置项描述)
# 这些默认值在应用首次启动时被写入数据库（seed），已存在的键不会被覆盖
# =============================================================================
DEFAULT_CONFIGS: Dict[str, tuple[str, str]] = {
    # ---- 功能开关 ----
    # 控制各功能模块的启用/禁用状态
    "feature.ai_processor": ("false", "AI processing"),
    "feature.embedding": ("false", "Embedding / Milvus"),
    "feature.event_clustering": ("false", "Event clustering"),
    "feature.topic_radar": ("false", "Topic radar"),
    "feature.action_items": ("false", "Action items"),
    "feature.report_generation": ("false", "Report generation"),
    "feature.crawler": ("true", "Article crawler"),
    "feature.backup": ("true", "Database backup"),
    "feature.cleanup": ("true", "Data cleanup"),
    "feature.email_notification": ("false", "Email notifications"),
    # ---- 调度器参数 ----
    # 控制各定时任务的执行频率和时间点
    "scheduler.crawl_interval_hours": ("6", "Crawl interval in hours"),
    "scheduler.cleanup_hour": ("3", "Hour of day to run cleanup (0-23)"),
    "scheduler.backup_hour": ("4", "Hour of day to run backup (0-23)"),
    "scheduler.ai_process_interval_hours": ("1", "AI processing interval in hours"),
    "scheduler.embedding_interval_hours": ("2", "Embedding computation interval in hours"),
    "scheduler.event_cluster_hour": ("2", "Hour of day to run event clustering (0-23)"),
    "scheduler.topic_discovery_day": ("mon", "Day of week for topic discovery"),
    "scheduler.topic_discovery_hour": ("1", "Hour of day for topic discovery (0-23)"),
    # ---- 行动项提取调度参数 ----
    "scheduler.action_extract_interval_hours": ("2", "Action item extraction interval in hours"),
    # ---- 报告生成调度参数 ----
    "scheduler.report_weekly_day": ("mon", "Day of week for weekly report generation"),
    "scheduler.report_weekly_hour": ("6", "Hour of day for weekly report generation (0-23)"),
    "scheduler.report_monthly_hour": ("7", "Hour of day for monthly report generation on 1st (0-23)"),
    # ---- 邮件通知调度参数 ----
    "scheduler.notification_hour": ("9", "Hour of day to send notification emails (0-23)"),
    "scheduler.notification_minute": ("0", "Minute of hour to send notification emails (0-59)"),
    # ---- AI 处理参数 ----
    "ai.provider": ("ollama", "AI provider: ollama, openai, claude"),
    "ai.ollama_base_url": ("http://localhost:11434", "Ollama API base URL"),
    "ai.ollama_model": ("qwen3:32b", "Ollama model name"),
    "ai.ollama_model_light": ("", "Ollama light model name"),
    "ai.ollama_timeout": ("120", "Ollama request timeout in seconds"),
    "ai.openai_model": ("gpt-4o", "OpenAI model name"),
    "ai.openai_model_light": ("gpt-4o-mini", "OpenAI light model name"),
    "ai.openai_base_url": ("", "OpenAI base URL for proxies or compatible APIs"),
    "ai.openai_timeout": ("60", "OpenAI request timeout in seconds"),
    "ai.claude_model": ("claude-sonnet-4-20250514", "Claude model name"),
    "ai.claude_model_light": ("claude-haiku-4-20250514", "Claude light model name"),
    "ai.claude_timeout": ("60", "Claude request timeout in seconds"),
    "ai.cache_enabled": ("true", "Enable AI result caching"),
    "ai.cache_ttl": ("86400", "AI cache TTL in seconds"),
    "ai.max_content_length": ("1500", "Max content length for AI processing"),
    "ai.max_title_length": ("200", "Max title length for AI processing"),
    "ai.thinking_enabled": ("false", "Enable thinking mode"),
    "ai.concurrent_enabled": ("false", "Enable concurrent processing"),
    "ai.workers_heavy": ("2", "Heavy task workers"),
    "ai.workers_screen": ("4", "Screen task workers"),
    "ai.no_think": ("false", "Disable model thinking (qwen3 etc.)"),
    "ai.num_predict": ("512", "Max generation tokens for high-value content"),
    "ai.num_predict_simple": ("256", "Max generation tokens for simple tasks"),
    "ai.max_retries": ("3", "Max retry attempts for AI API calls"),
    "ai.retry_base_delay": ("1.0", "Retry base delay seconds (exponential backoff)"),
    "ai.batch_concurrency": ("1", "Batch concurrency (1=serial)"),
    "ai.translate_max_tokens": ("4096", "Max output tokens for translation"),
    "ai.fallback_provider": ("", "Fallback AI provider"),
    # ---- 向量嵌入参数 ----
    "embedding.provider": ("sentence-transformers", "Embedding provider"),
    "embedding.model": ("all-MiniLM-L6-v2", "Embedding model name"),
    "embedding.dimension": ("384", "Embedding vector dimension"),
    "embedding.similarity_threshold": ("0.85", "Similarity threshold"),
    "embedding.milvus_host": ("localhost", "Milvus server host"),
    "embedding.milvus_port": ("19530", "Milvus server port"),
    "embedding.milvus_collection": ("article_embeddings", "Milvus collection name"),
    # ---- 事件聚类参数 ----
    "event.rule_weight": ("0.4", "Rule-based weight for clustering"),
    "event.semantic_weight": ("0.6", "Semantic weight for clustering"),
    "event.min_similarity": ("0.7", "Minimum similarity threshold"),
    # ---- 流水线批处理参数 ----
    "pipeline.ai_batch_limit": ("200", "AI processing batch limit per run"),
    "pipeline.embedding_batch_limit": ("500", "Embedding computation batch limit per run"),
    "pipeline.event_batch_limit": ("500", "Event clustering batch limit per run"),
    "pipeline.action_batch_limit": ("200", "Action extraction batch limit per run"),
    "pipeline.worker_interval_minutes": ("10", "Pipeline worker polling interval in minutes"),
    # ---- 数据保留参数 ----
    "retention.active_days": ("7", "Article active retention days"),
    "retention.archive_days": ("30", "Archive retention days"),
    "retention.backup_enabled": ("true", "Enable automatic backup"),
    # ---- 缓存参数 ----
    "cache.enabled": ("false", "Enable caching"),
    "cache.default_ttl": ("300", "Default cache TTL in seconds"),
    # ---- JWT 参数 ----
    "jwt.access_token_expire_minutes": ("1440", "Access token expiration in minutes (default: 1 day)"),
    "jwt.refresh_token_expire_days": ("7", "Refresh token expiration in days"),
}

# 缓存存活时间（秒）
# 60 秒的 TTL 意味着管理员修改配置后最多 60 秒内生效
_CACHE_TTL = 60


# =============================================================================
# FeatureConfigService 类
# 职责: 提供数据库驱动的配置读写服务，带有内存缓存层
# 设计决策:
#   - 使用字典作为内存缓存，简单高效
#   - 缓存使用时间戳判断过期，而非每个键单独计时
#   - 同时提供同步和异步接口，适应不同调用场景
#   - 在异步事件循环已运行时，通过线程池执行同步数据库操作
# =============================================================================
class FeatureConfigService:
    """Database-backed configuration service with in-memory cache.

    Provides dynamic runtime configuration layered above static settings.
    提供运行时动态配置能力，位于静态 settings 之上。
    """

    def __init__(self) -> None:
        """Initialize the feature config service."""
        # 内存缓存字典：key -> value（字符串形式）
        self._cache: Dict[str, str] = {}
        # 缓存最后刷新时间戳（monotonic clock）
        self._cache_ts: float = 0.0
        # 冻结标志：为 True 时跳过缓存刷新，适用于长时间批处理场景
        self._frozen: bool = False

    # ------------------------------------------------------------------
    # 公开读取方法
    # ------------------------------------------------------------------

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Return a config value (string).

        获取配置值（字符串形式）。先检查内存缓存（必要时自动刷新），
        缓存中没有则返回默认值。

        Args:
            key: Configuration key, e.g. "feature.ai_processor".
            default: Default value when key is missing.

        Returns:
            Optional[str]: Config value string or default.
        """
        # 检查缓存是否过期，过期则从数据库重新加载
        self._maybe_refresh_cache()
        val = self._cache.get(key)
        if val is not None:
            return val
        return default

    def get_bool(self, key: str, default: bool = False) -> bool:
        """Return a boolean config value.

        将字符串 "true"/"1"/"yes"/"on" 识别为 True，其他为 False。

        Args:
            key: Configuration key.
            default: Default boolean value.

        Returns:
            bool: Parsed boolean value.
        """
        val = self.get(key)
        if val is None:
            return default
        return val.lower() in ("true", "1", "yes", "on")

    def get_int(self, key: str, default: int = 0) -> int:
        """Return an integer config value.

        Args:
            key: Configuration key.
            default: Default integer value.

        Returns:
            int: Parsed integer value or default on failure.
        """
        val = self.get(key)
        if val is None:
            return default
        try:
            return int(val)
        except (ValueError, TypeError):
            return default

    def get_float(self, key: str, default: float = 0.0) -> float:
        """Return a float config value.

        Args:
            key: Configuration key.
            default: Default float value.

        Returns:
            float: Parsed float value or default on failure.
        """
        val = self.get(key)
        if val is None:
            return default
        try:
            return float(val)
        except (ValueError, TypeError):
            return default

    # ------------------------------------------------------------------
    # 公开写入方法
    # ------------------------------------------------------------------

    def set(
        self,
        key: str,
        value: str,
        description: Optional[str] = None,
        updated_by: Optional[int] = None,
    ) -> None:
        """Write a config value to the database and update cache.

        同步写入配置值到数据库并立即更新内存缓存。
        使用同步引擎执行数据库操作，避免创建第二个事件循环。

        Args:
            key: Configuration key.
            value: Configuration value (string).
            description: Optional description.
            updated_by: Optional updater user ID.

        Side Effects:
            - Updates system_config table.
            - Refreshes in-memory cache.
        """
        import asyncio

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None and loop.is_running():
            # 在 async 上下文中，使用同步引擎避免跨事件循环问题
            self._sync_set(key, value, description, updated_by)
        else:
            asyncio.run(self._async_set(key, value, description, updated_by))

        # 写入数据库成功后，立即更新内存缓存以保证一致性
        self._cache[key] = value

    async def async_set(
        self,
        key: str,
        value: str,
        description: Optional[str] = None,
        updated_by: Optional[int] = None,
    ) -> None:
        """Async version of ``set``.

        异步版本的配置写入方法，适用于已在异步上下文中的场景。

        Args:
            key: Configuration key.
            value: Configuration value.
            description: Optional description.
            updated_by: Optional updater user ID.
        """
        await self._async_set(key, value, description, updated_by)
        # 写入成功后立即更新缓存
        self._cache[key] = value

    # ------------------------------------------------------------------
    # 批量操作方法
    # ------------------------------------------------------------------

    def get_all(self, prefix: Optional[str] = None) -> Dict[str, str]:
        """Return all cached configs, optionally filtered by key prefix.

        获取所有配置项，可选按键名前缀过滤。

        Args:
            prefix: Optional key prefix filter.

        Returns:
            Dict[str, str]: Config key-value mapping.
        """
        self._maybe_refresh_cache()
        if prefix is None:
            return dict(self._cache)
        return {k: v for k, v in self._cache.items() if k.startswith(prefix)}

    def reload(self) -> None:
        """Force-refresh the cache from the database.

        强制刷新缓存：将缓存时间戳重置为 0，触发下次读取时从数据库重新加载。
        同步版本。
        """
        self._cache_ts = 0.0
        self._maybe_refresh_cache()

    async def async_reload(self) -> None:
        """Async force-refresh.

        异步版本的强制刷新缓存方法。
        """
        self._cache_ts = 0.0
        await self._async_refresh_cache()

    def freeze(self) -> None:
        """Freeze the cache, preventing automatic refreshes.

        冻结缓存：在长时间批处理场景中调用，避免处理过程中反复查库。
        调用前应确保缓存已是最新状态（如先调用 reload / async_reload）。
        """
        self._frozen = True
        logger.debug("Feature config cache frozen")

    def unfreeze(self) -> None:
        """Unfreeze the cache, allowing automatic refreshes again.

        解冻缓存：批处理完成后调用，恢复正常的 TTL 刷新机制。
        """
        self._frozen = False
        logger.debug("Feature config cache unfrozen")

    # ------------------------------------------------------------------
    # 默认值种子方法
    # ------------------------------------------------------------------

    async def seed_defaults(
        self, defaults: Optional[Dict[str, tuple[str, str]]] = None
    ) -> int:
        """Insert default config rows into the database.

        Only inserts keys that do not yet exist (won't overwrite admin values).

        将默认配置写入数据库（仅插入不存在的键，不覆盖已有值）。
        这样管理员通过 API 修改的值不会在重启时被重置。

        Args:
            defaults: Optional custom defaults dictionary.

        Returns:
            int: Number of rows inserted.

        Side Effects:
            - Inserts rows into system_config.
            - Refreshes in-memory cache.
        """
        from sqlalchemy import text as sa_text

        from core.database import get_session_factory

        if defaults is None:
            defaults = DEFAULT_CONFIGS

        session_factory = get_session_factory()
        inserted = 0

        async with session_factory() as session:
            try:
                for key, (value, description) in defaults.items():
                    # 先检查该键是否已存在于数据库中
                    result = await session.execute(
                        sa_text(
                            "SELECT config_key FROM system_config WHERE config_key = :key"
                        ),
                        {"key": key},
                    )
                    if not result.scalar():
                        # 键不存在，插入默认值
                        await session.execute(
                            sa_text(
                                "INSERT INTO system_config (config_key, config_value, description, is_sensitive) "
                                "VALUES (:key, :value, :description, :sensitive)"
                            ),
                            {
                                "key": key,
                                "value": value,
                                "description": description,
                                "sensitive": False,
                            },
                        )
                        inserted += 1

                await session.commit()
                logger.info(
                    "Seeded %d default config rows (%d already existed)",
                    inserted,
                    len(defaults) - inserted,
                )
            except Exception:
                await session.rollback()
                raise

        # 种子数据写入后立即刷新缓存，确保新值可被立即使用
        await self._async_refresh_cache()
        return inserted

    # ------------------------------------------------------------------
    # 内部辅助方法
    # ------------------------------------------------------------------

    def _maybe_refresh_cache(self) -> None:
        """Refresh cache if stale (sync path).

        检查缓存是否过期，过期则通过同步引擎从数据库重新加载。
        使用独立的同步引擎避免在 async 上下文中创建第二个事件循环。

        Side Effects:
            - Loads latest data when stale.
            - Falls back to defaults if DB is unavailable.
        """
        # 冻结模式下跳过刷新
        if self._frozen and self._cache:
            return

        # 缓存未过期且非空时直接返回
        if time.monotonic() - self._cache_ts < _CACHE_TTL and self._cache:
            return

        try:
            self._sync_refresh_cache()
        except Exception:
            # 数据库尚未就绪（如应用启动早期阶段）
            # 回退到硬编码的默认值，保证服务可用
            if not self._cache:
                logger.debug("DB not ready, using in-memory defaults")
                self._cache = {k: v for k, (v, _) in DEFAULT_CONFIGS.items()}
                self._cache_ts = time.monotonic()

    def _sync_refresh_cache(self) -> None:
        """Load all config rows from DB using the sync engine.

        通过同步引擎直接读取 system_config 表，不涉及 asyncio 事件循环，
        从而避免跨事件循环污染连接池的问题。

        Side Effects:
            - Replaces the cache dictionary.
            - Updates cache timestamp.
        """
        from sqlalchemy import text as sa_text

        from core.database import get_sync_engine

        engine = get_sync_engine()
        with engine.connect() as conn:
            result = conn.execute(
                sa_text("SELECT config_key, config_value FROM system_config")
            )
            rows = result.all()

        self._cache = {row[0]: row[1] for row in rows}
        self._cache_ts = time.monotonic()

    async def _async_refresh_cache(self) -> None:
        """Load all config rows from DB into the in-memory cache.

        从数据库的 system_config 表加载所有配置到内存缓存。
        全量加载策略：每次刷新都加载所有配置行，简单且保证一致性。

        Side Effects:
            - Replaces the cache dictionary.
            - Updates cache timestamp.
        """
        from sqlalchemy import text as sa_text

        from core.database import get_session_factory

        session_factory = get_session_factory()
        async with session_factory() as session:
            result = await session.execute(
                sa_text("SELECT config_key, config_value FROM system_config")
            )
            rows = result.all()

        # 用数据库查询结果完全替换缓存
        self._cache = {row[0]: row[1] for row in rows}
        # 记录刷新时间戳，用于后续 TTL 判断
        self._cache_ts = time.monotonic()

    async def _async_set(
        self,
        key: str,
        value: str,
        description: Optional[str] = None,
        updated_by: Optional[int] = None,
    ) -> None:
        """Upsert a single config row.

        插入或更新单条配置记录（Upsert 语义）。
        先查询键是否存在，存在则 UPDATE，不存在则 INSERT。

        Args:
            key: Configuration key.
            value: Configuration value.
            description: Optional description.
            updated_by: Optional updater user ID.

        Side Effects:
            - Updates or inserts system_config record.
        """
        from sqlalchemy import text as sa_text

        from core.database import get_session_factory

        session_factory = get_session_factory()
        async with session_factory() as session:
            try:
                # 检查键是否已存在
                result = await session.execute(
                    sa_text(
                        "SELECT config_key FROM system_config WHERE config_key = :key"
                    ),
                    {"key": key},
                )
                if result.scalar():
                    # 键已存在，执行 UPDATE
                    # 动态构建 SET 子句，只更新非 None 的字段
                    params: dict[str, Any] = {"key": key, "value": value}
                    set_parts = ["config_value = :value"]
                    if description is not None:
                        set_parts.append("description = :description")
                        params["description"] = description
                    if updated_by is not None:
                        set_parts.append("updated_by = :updated_by")
                        params["updated_by"] = updated_by
                    await session.execute(
                        sa_text(
                            f"UPDATE system_config SET {', '.join(set_parts)} "
                            "WHERE config_key = :key"
                        ),
                        params,
                    )
                else:
                    # 键不存在，执行 INSERT
                    await session.execute(
                        sa_text(
                            "INSERT INTO system_config (config_key, config_value, description, is_sensitive, updated_by) "
                            "VALUES (:key, :value, :description, :sensitive, :updated_by)"
                        ),
                        {
                            "key": key,
                            "value": value,
                            "description": description or "",
                            "sensitive": False,
                            "updated_by": updated_by,
                        },
                    )
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    def _sync_set(
        self,
        key: str,
        value: str,
        description: Optional[str] = None,
        updated_by: Optional[int] = None,
    ) -> None:
        """Upsert a single config row using the sync engine.

        通过同步引擎执行 upsert，避免在 async 上下文中创建第二个事件循环。

        Args:
            key: Configuration key.
            value: Configuration value.
            description: Optional description.
            updated_by: Optional updater user ID.
        """
        from sqlalchemy import text as sa_text

        from core.database import get_sync_engine

        engine = get_sync_engine()
        with engine.begin() as conn:
            result = conn.execute(
                sa_text(
                    "SELECT config_key FROM system_config WHERE config_key = :key"
                ),
                {"key": key},
            )
            if result.scalar():
                params: dict[str, Any] = {"key": key, "value": value}
                set_parts = ["config_value = :value"]
                if description is not None:
                    set_parts.append("description = :description")
                    params["description"] = description
                if updated_by is not None:
                    set_parts.append("updated_by = :updated_by")
                    params["updated_by"] = updated_by
                conn.execute(
                    sa_text(
                        f"UPDATE system_config SET {', '.join(set_parts)} "
                        "WHERE config_key = :key"
                    ),
                    params,
                )
            else:
                conn.execute(
                    sa_text(
                        "INSERT INTO system_config (config_key, config_value, description, is_sensitive, updated_by) "
                        "VALUES (:key, :value, :description, :sensitive, :updated_by)"
                    ),
                    {
                        "key": key,
                        "value": value,
                        "description": description or "",
                        "sensitive": False,
                        "updated_by": updated_by,
                    },
                )


# 模块级单例实例
# 整个应用通过 from common.feature_config import feature_config 共享此实例
feature_config = FeatureConfigService()


# ------------------------------------------------------------------
# FastAPI 依赖注入：require_feature
# 用于在路由层面检查功能开关，未启用的功能返回 503 错误
# ------------------------------------------------------------------


def require_feature(feature_key: str):
    """Create a FastAPI dependency that blocks requests when a feature is disabled.

    创建一个 FastAPI 依赖项，当指定功能未启用时阻止请求并返回 503 错误。
    这是一个工厂函数，返回一个可用于 FastAPI 路由装饰器的 Depends 对象。

    Args:
        feature_key: Feature toggle key, e.g. "feature.ai_processor".

    Returns:
        Depends: FastAPI dependency object.

    Example:
        >>> @router.post("/process", dependencies=[require_feature("feature.ai_processor")])
        ... async def process_article(...):
        ...     ...
    """

    async def _checker() -> None:
        # 从配置服务中读取功能开关状态
        if not feature_config.get_bool(feature_key, False):
            raise HTTPException(
                status_code=503,
                detail=f"Feature '{feature_key}' is not enabled. "
                "An administrator can enable it via PUT /api/v1/admin/features/{feature_key}.",
            )

    return Depends(_checker)
