# =============================================================================
# 数据库连接与会话管理模块
# =============================================================================
# 本模块负责 ResearchPulse 项目的数据库连接管理，是整个后端系统的数据访问基础层。
# 主要职责：
#   1. 创建和管理 SQLAlchemy 异步数据库引擎（AsyncEngine）
#   2. 提供异步会话工厂（async_sessionmaker），用于生成数据库会话
#   3. 提供数据库会话的生命周期管理（含自动提交和回滚机制）
#   4. 提供数据库初始化（建表）和关闭（释放连接池）功能
#   5. 提供数据库健康检查功能
#
# 架构设计说明：
#   - 使用模块级全局变量（_engine、_session_factory）实现单例模式，
#     避免重复创建引擎和会话工厂，确保整个应用共享同一连接池。
#   - 延迟导入 settings 模块，避免循环依赖问题。
#   - get_session() 作为 FastAPI 的 Depends 依赖注入函数使用，
#     通过 async generator 的方式管理会话生命周期。
# =============================================================================

"""Database connection and session management for ResearchPulse v2."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from core.models.base import Base

logger = logging.getLogger(__name__)

# 模块级全局变量：数据库引擎实例（单例模式）
# 初始为 None，首次调用 get_engine() 时惰性创建
_engine: AsyncEngine | None = None

# 模块级全局变量：异步会话工厂实例（单例模式）
# 初始为 None，首次调用 get_session_factory() 时惰性创建
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Get or create the async database engine.

    This function lazily constructs a singleton SQLAlchemy ``AsyncEngine``
    using configuration values from ``settings``. Subsequent calls return the
    same engine instance so the application shares a single connection pool.

    Returns:
        AsyncEngine: A shared asynchronous engine bound to ``settings.database_url``.

    Raises:
        sqlalchemy.exc.SQLAlchemyError: If the engine cannot be created due to
            invalid configuration or driver issues.
    """
    global _engine
    # 如果引擎尚未创建，则根据配置初始化
    if _engine is None:
        # 延迟导入 settings，避免模块加载时的循环依赖
        from settings import settings

        # 创建异步数据库引擎，配置连接池参数
        # pool_size: 连接池中保持的持久连接数
        # max_overflow: 超出 pool_size 后允许额外创建的临时连接数
        # pool_recycle: 连接回收时间（秒），防止数据库服务端超时断开
        # echo: 是否将 SQL 语句输出到日志（调试用）
        _engine = create_async_engine(
            settings.database_url,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_recycle=settings.db_pool_recycle,
            echo=settings.db_echo,
        )
        logger.info("Database engine created")
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get or create the async session factory.

    The returned factory is a singleton ``async_sessionmaker`` configured with
    ``expire_on_commit=False`` to avoid implicit lazy-loading after ``await``
    boundaries in async handlers.

    Returns:
        async_sessionmaker[AsyncSession]: A session factory bound to the shared engine.
    """
    global _session_factory
    # 如果会话工厂尚未创建，则初始化
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(),
            class_=AsyncSession,
            # expire_on_commit=False：提交后不自动过期对象属性，
            # 这样在 commit 之后仍然可以访问对象的属性值，
            # 对于异步场景非常重要，避免在 await 之后意外触发惰性加载
            expire_on_commit=False,
        )
    return _session_factory


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session for FastAPI dependencies.

    This generator is designed for FastAPI ``Depends`` usage. It yields an
    ``AsyncSession`` and automatically commits on success or rolls back on
    exception, ensuring consistent transaction handling per request.

    Yields:
        AsyncSession: An active async SQLAlchemy session.

    Raises:
        Exception: Re-raises any exception raised by downstream handlers after
            rolling back the session.
    """
    # 获取会话工厂，创建新的数据库会话
    factory = get_session_factory()
    async with factory() as session:
        try:
            # 将会话 yield 给调用方（FastAPI 的路由处理函数）
            yield session
            # 如果路由处理函数正常返回（无异常），则自动提交事务
            await session.commit()
        except Exception:
            # 如果路由处理函数抛出异常，则回滚事务，保证数据一致性
            await session.rollback()
            raise


async def init_db() -> None:
    """Initialize database schema.

    Creates all tables registered on ``Base.metadata`` if they do not already
    exist. This is intended for initial setup or local development.

    Raises:
        sqlalchemy.exc.SQLAlchemyError: If schema creation fails.
    """
    # 获取数据库引擎
    engine = get_engine()
    # 使用 engine.begin() 开启一个自动提交/回滚的连接上下文
    async with engine.begin() as conn:
        # run_sync 将同步的 DDL 操作放到线程池中执行
        # Base.metadata.create_all 会根据所有已注册的 ORM 模型创建对应的数据库表
        # 如果表已存在则跳过（不会覆盖或修改已有表结构）
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created/verified")


async def close_db() -> None:
    """Dispose the database engine and clear session factory.

    This releases pooled connections and resets module-level singletons so
    that a new engine/factory can be created on the next call.
    """
    global _engine, _session_factory
    if _engine:
        # 释放连接池中的所有连接资源
        await _engine.dispose()
        # 重置全局变量为 None，允许下次重新初始化
        _engine = None
        _session_factory = None
        logger.info("Database connections closed")


async def check_db_connection() -> bool:
    """Check whether the database connection is healthy.

    Executes a lightweight ``SELECT 1`` query using a fresh connection.

    Returns:
        bool: ``True`` if the query succeeds, otherwise ``False``.
    """
    try:
        from sqlalchemy import text
        engine = get_engine()
        # 通过执行简单的 SELECT 1 查询来验证数据库连接是否正常
        # 这是一种常见的数据库健康检查方式，开销极小
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        # 连接失败时记录错误日志并返回 False，而非抛出异常
        # 这样调用方可以根据返回值决定如何处理（如返回 503 状态码）
        logger.error(f"Database connection check failed: {e}")
        return False
