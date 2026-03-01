#!/usr/bin/env python3
"""Manual AI pipeline runner for ResearchPulse v2.

手动触发 AI 处理流水线的 CLI 工具，支持按阶段运行或一键运行全部流程。

流水线阶段（按依赖顺序）:
  1. ai        AI 文章处理（摘要、分类、评分）
  2. embedding 向量嵌入计算
  3. event     事件聚类
  4. topic     主题发现

Usage:
    python scripts/_ai_pipeline_runner.py all
    python scripts/_ai_pipeline_runner.py ai
    python scripts/_ai_pipeline_runner.py ai embedding
    python scripts/_ai_pipeline_runner.py embedding event topic
    python scripts/_ai_pipeline_runner.py all --limit 100 --verbose
    python scripts/_ai_pipeline_runner.py all --trigger --force
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
import warnings
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# ---------------------------------------------------------------------------
# 抑制 aiomysql + SQLAlchemy 异步连接池的 GC 回收警告。
# 当多阶段流水线依次运行时，前一阶段的连接池连接可能在后一阶段的
# 模块导入（如 TensorFlow / sentence-transformers）触发 GC 时被发现。
# 此时连接已不再使用，但 SQLAlchemy 会发出 SAWarning 和 logging.error。
# 这是 aiomysql 与 SQLAlchemy 异步引擎的已知行为，不影响功能正确性。
# ---------------------------------------------------------------------------
warnings.filterwarnings(
    "ignore",
    message=".*garbage collector.*non-checked-in connection.*",
)

# 同时静默 SQLAlchemy pool 模块在 GC 回收时输出的 ERROR 级别日志。
# pool.logger 的名称是 "sqlalchemy.pool.impl.AsyncAdaptedQueuePool"，
# 但 Python logging 的 Filter 不会被子 logger 继承，
# 因此直接将 filter 安装在 root logger 的 handler 上。
_pool_gc_filter = type(
    "_PoolGCFilter",
    (logging.Filter,),
    {
        "_SUPPRESSED": ("non-checked-in connection", "Exception terminating connection"),
        "filter": lambda self, record: not any(
            s in record.getMessage() for s in self._SUPPRESSED
        ),
    },
)()
logging.getLogger("sqlalchemy.pool.impl.AsyncAdaptedQueuePool").addFilter(
    _pool_gc_filter
)

from settings import settings

# ---------------------------------------------------------------------------
# ANSI 颜色
# ---------------------------------------------------------------------------
RED = "\033[0;31m"
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
CYAN = "\033[0;36m"
NC = "\033[0m"


class ColoredFormatter(logging.Formatter):
    """Custom formatter that adds ANSI colors based on log level."""

    LEVEL_COLORS = {
        logging.DEBUG: CYAN,
        logging.INFO: CYAN,
        logging.WARNING: YELLOW,
        logging.ERROR: RED,
        logging.CRITICAL: RED,
    }

    def format(self, record):
        # 保存原始 levelname
        orig_levelname = record.levelname
        # 添加颜色
        color = self.LEVEL_COLORS.get(record.levelno, NC)
        record.levelname = f"{color}{record.levelname}{NC}"
        result = super().format(record)
        # 恢复原始 levelname
        record.levelname = orig_levelname
        return result


# ---------------------------------------------------------------------------
# 日志配置
# ---------------------------------------------------------------------------
# 创建带颜色的 formatter
_colored_formatter = ColoredFormatter(
    fmt="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# 配置 root logger
_handler = logging.StreamHandler()
_handler.setFormatter(_colored_formatter)
_handler.addFilter(_pool_gc_filter)

logging.basicConfig(
    level=logging.INFO,
    handlers=[_handler],
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 流水线阶段定义（按依赖顺序）
# ---------------------------------------------------------------------------
STAGES = ("ai", "translate", "embedding", "event", "topic", "topic-match", "action", "report")

STAGE_DESCRIPTIONS = {
    "ai": "AI 文章处理（摘要/分类/评分）",
    "translate": "arXiv 文章标题翻译",
    "embedding": "向量嵌入计算",
    "event": "事件聚类",
    "topic": "主题发现",
    "topic-match": "话题匹配（文章关联到话题）",
    "action": "行动项提取",
    "report": "报告生成",
}

STAGE_FEATURES = {
    "ai": "feature.ai_processor",
    "translate": "feature.ai_processor",
    "embedding": "feature.embedding",
    "event": "feature.event_clustering",
    "topic": "feature.topic_radar",
    "topic-match": "feature.topic_radar",
    "action": "feature.action_items",
    "report": "feature.report_generation",
}


def _log(msg: str, level: str = "info") -> None:
    """Log colored message using logging module.

    Args:
        msg: Message to log.
        level: Log level - 'info', 'success', 'warn', 'error', 'debug'.
    """
    level_map = {
        "info": logging.INFO,
        "success": logging.INFO,  # success 也用 INFO 级别
        "warn": logging.WARNING,
        "error": logging.ERROR,
        "debug": logging.DEBUG,
    }
    colors = {"info": CYAN, "success": GREEN, "warn": YELLOW, "error": RED, "debug": CYAN}
    color = colors.get(level, NC)
    log_level = level_map.get(level, logging.INFO)

    # 为 success 消息添加绿色前缀
    if level == "success":
        logger.log(log_level, f"{color}{msg}{NC}")
    else:
        logger.log(log_level, msg)


# ---------------------------------------------------------------------------
# 各阶段运行函数
# ---------------------------------------------------------------------------

async def _run_ai(limit: int, verbose: bool) -> dict:
    """Run AI processing stage."""
    from core.database import get_session_factory
    from apps.ai_processor.service import AIProcessorService

    session_factory = get_session_factory()
    service = AIProcessorService()

    def progress_callback(current: int, total: int, message: str) -> None:
        """Progress callback for AI processing."""
        if total > 0:
            pct = (current / total) * 100
            logger.info(f"[ai] 进度: {current}/{total} ({pct:.0f}%) - {message}")

    try:
        # 预热模型，避免首次请求因冷启动超时
        warmup_ok = await service.warmup()
        if not warmup_ok:
            _log("[ai] 模型预热未完成，继续处理", "warn")

        async with session_factory() as session:
            result = await service.process_unprocessed(
                session, limit=limit, progress_callback=progress_callback
            )
            return result
    except Exception as e:
        logger.error(f"AI processing failed: {e}", exc_info=verbose)
        return {"error": str(e), "processed": 0, "cached": 0, "failed": 0, "total": 0}
    finally:
        await service.close()


async def _run_translate(limit: int, verbose: bool, concurrency: int = 1) -> dict:
    """Run arXiv title and summary translation stage.

    翻译 source_type='arxiv' 且标题/摘要为英文、且尚未翻译的文章。
    标题翻译存入 translated_title，摘要翻译存入 content_summary。

    使用乐观锁避免多进程竞争：
    - 查询时记录 updated_at 作为版本号
    - 更新时检查版本号，如果已变化则跳过（已被其他进程处理）

    Args:
        limit: Maximum number of articles to process.
        verbose: Enable verbose output.
        concurrency: Number of concurrent translation tasks.
    """
    from core.database import get_session_factory
    from sqlalchemy import and_, or_, select, update
    from apps.crawler.models.article import Article
    from apps.ai_processor.service import get_ai_provider, _is_english
    import asyncio

    session_factory = get_session_factory()
    provider = get_ai_provider()

    # 先查询待翻译的文章 ID 和版本号（updated_at 作为乐观锁版本）
    async with session_factory() as session:
        result = await session.execute(
            select(Article.id, Article.updated_at)
            .where(
                and_(
                    Article.source_type == "arxiv",
                    Article.title.isnot(None),
                    Article.title != "",
                    # 标题或摘要至少有一个需要翻译
                    or_(
                        Article.translated_title.is_(None),
                        and_(
                            Article.summary.isnot(None),
                            Article.summary != "",
                            Article.content_summary.is_(None),
                        ),
                    ),
                )
            )
            .order_by(Article.crawl_time.desc())
            .limit(limit)
        )
        # (article_id, version_timestamp) 列表
        article_versions = [(row[0], row[1]) for row in result.all()]

    if not article_versions:
        await provider.close()
        return {"translated_titles": 0, "translated_summaries": 0, "skipped": 0, "failed": 0, "total": 0}

    # 统计计数器
    translated_titles = 0
    translated_summaries = 0
    skipped = 0
    failed = 0
    conflict = 0  # 乐观锁冲突计数
    counter_lock = asyncio.Lock()
    progress_counter = [0]  # 使用列表以便在闭包中修改
    total_count = len(article_versions)

    async def translate_article(article_id: int, version_timestamp) -> tuple[int, int, int, int, int]:
        """翻译单篇文章，使用乐观锁。返回 (titles, summaries, skipped, failed, conflict)"""
        local_titles = 0
        local_summaries = 0
        local_skipped = 0
        local_failed = 0
        local_conflict = 0

        try:
            async with session_factory() as session:
                # 查询文章内容
                result = await session.execute(
                    select(
                        Article.title,
                        Article.summary,
                        Article.translated_title,
                        Article.content_summary,
                        Article.updated_at,
                    ).where(Article.id == article_id)
                )
                row = result.first()
                if not row:
                    return (0, 0, 0, 1, 0)

                title, summary, existing_translated_title, existing_content_summary, current_updated_at = row

                # 乐观锁检查：如果 updated_at 已变化，说明已被其他进程处理
                if current_updated_at != version_timestamp:
                    logger.debug(f"Article {article_id} already processed by another process (optimistic lock)")
                    return (0, 0, 0, 0, 1)

                # 再次检查是否已有翻译（其他进程可能已完成）
                if existing_translated_title and existing_content_summary:
                    return (0, 0, 0, 0, 0)  # 已完成，不算冲突

                update_values = {}

                # 翻译标题（如果未翻译且为英文）
                if not existing_translated_title and title and _is_english(title):
                    translated_title = await provider.translate(title)
                    if translated_title:
                        update_values["translated_title"] = translated_title
                        local_titles = 1
                    else:
                        local_skipped = 1

                # 翻译摘要（如果未翻译、有内容且为英文）
                if not existing_content_summary and summary and _is_english(summary):
                    translated_summary = await provider.translate(summary)
                    if translated_summary:
                        update_values["content_summary"] = translated_summary
                        local_summaries = 1
                    else:
                        local_skipped += 1

                # 使用乐观锁更新：WHERE 条件包含版本号检查
                if update_values:
                    update_result = await session.execute(
                        update(Article)
                        .where(
                            and_(
                                Article.id == article_id,
                                Article.updated_at == version_timestamp,  # 乐观锁
                            )
                        )
                        .values(**update_values)
                    )

                    # 检查更新是否成功（受影响行数为 0 表示版本冲突）
                    if update_result.rowcount == 0:
                        logger.debug(f"Article {article_id} optimistic lock conflict")
                        await session.rollback()
                        return (0, 0, 0, 0, 1)

                await session.commit()
                return (local_titles, local_summaries, local_skipped, local_failed, local_conflict)

        except Exception as e:
            logger.warning(f"Failed to translate article {article_id}: {e}")
            return (0, 0, 0, 1, 0)

    async def update_counter(result: tuple[int, int, int, int, int]):
        """线程安全地更新计数器"""
        nonlocal translated_titles, translated_summaries, skipped, failed, conflict
        async with counter_lock:
            translated_titles += result[0]
            translated_summaries += result[1]
            skipped += result[2]
            failed += result[3]
            conflict += result[4]
            # 更新进度
            progress_counter[0] += 1
            current = progress_counter[0]
            pct = (current / total_count) * 100
            logger.info(f"[translate] 进度: {current}/{total_count} ({pct:.1f}%) - 标题: {translated_titles}, 摘要: {translated_summaries}")

    # 使用信号量控制并发
    semaphore = asyncio.Semaphore(concurrency)

    async def translate_with_semaphore(article_id: int, version_timestamp):
        async with semaphore:
            result = await translate_article(article_id, version_timestamp)
            await update_counter(result)

    try:
        # 并发执行翻译任务
        tasks = [translate_with_semaphore(aid, ver) for aid, ver in article_versions]
        await asyncio.gather(*tasks)

        return {
            "translated_titles": translated_titles,
            "translated_summaries": translated_summaries,
            "skipped": skipped,
            "failed": failed,
            "conflict": conflict,
            "total": len(article_versions),
        }
    except Exception as e:
        logger.error(f"Translation stage failed: {e}", exc_info=verbose)
        return {
            "error": str(e),
            "translated_titles": translated_titles,
            "translated_summaries": translated_summaries,
            "skipped": skipped,
            "failed": failed,
            "conflict": conflict,
            "total": len(article_versions),
        }
    finally:
        await provider.close()


async def _run_translate_for_articles(article_ids: list[int], concurrency: int = 1) -> dict:
    """Translate specific articles by ID.

    翻译指定 ID 的文章，仅处理 arXiv 英文标题和摘要。
    标题翻译存入 translated_title，摘要翻译存入 content_summary。

    Args:
        article_ids: List of article IDs to translate.
        concurrency: Number of concurrent translation tasks.

    Returns:
        dict: Translation statistics.
    """
    from core.database import get_session_factory
    from sqlalchemy import and_, or_, select, update
    from apps.crawler.models.article import Article
    from apps.ai_processor.service import get_ai_provider, _is_english
    import asyncio

    if not article_ids:
        return {"translated_titles": 0, "translated_summaries": 0, "skipped": 0, "failed": 0, "total": 0}

    session_factory = get_session_factory()
    provider = get_ai_provider()

    # 查询指定文章 ID 中需要翻译的文章
    async with session_factory() as session:
        result = await session.execute(
            select(Article.id, Article.updated_at)
            .where(
                and_(
                    Article.id.in_(article_ids),
                    Article.source_type == "arxiv",
                    Article.title.isnot(None),
                    Article.title != "",
                    # 标题或摘要至少有一个需要翻译
                    or_(
                        Article.translated_title.is_(None),
                        and_(
                            Article.summary.isnot(None),
                            Article.summary != "",
                            Article.content_summary.is_(None),
                        ),
                    ),
                )
            )
            .order_by(Article.crawl_time.desc())
        )
        # (article_id, version_timestamp) 列表
        article_versions = [(row[0], row[1]) for row in result.all()]

    if not article_versions:
        await provider.close()
        return {"translated_titles": 0, "translated_summaries": 0, "skipped": 0, "failed": 0, "total": 0}

    # 统计计数器
    translated_titles = 0
    translated_summaries = 0
    skipped = 0
    failed = 0
    conflict = 0
    counter_lock = asyncio.Lock()
    progress_counter = [0]
    total_count = len(article_versions)

    async def translate_article(article_id: int, version_timestamp) -> tuple[int, int, int, int, int]:
        """翻译单篇文章，使用乐观锁。返回 (titles, summaries, skipped, failed, conflict)"""
        local_titles = 0
        local_summaries = 0
        local_skipped = 0
        local_failed = 0
        local_conflict = 0

        try:
            async with session_factory() as session:
                # 查询文章内容
                result = await session.execute(
                    select(
                        Article.title,
                        Article.summary,
                        Article.translated_title,
                        Article.content_summary,
                        Article.updated_at,
                    ).where(Article.id == article_id)
                )
                row = result.first()
                if not row:
                    return (0, 0, 0, 1, 0)

                title, summary, existing_translated_title, existing_content_summary, current_updated_at = row

                # 乐观锁检查
                if current_updated_at != version_timestamp:
                    return (0, 0, 0, 0, 1)

                # 再次检查是否已有翻译
                if existing_translated_title and existing_content_summary:
                    return (0, 0, 0, 0, 0)

                update_values = {}

                # 翻译标题
                if not existing_translated_title and title and _is_english(title):
                    translated_title = await provider.translate(title)
                    if translated_title:
                        update_values["translated_title"] = translated_title
                        local_titles = 1
                    else:
                        local_skipped = 1

                # 翻译摘要
                if not existing_content_summary and summary and _is_english(summary):
                    translated_summary = await provider.translate(summary)
                    if translated_summary:
                        update_values["content_summary"] = translated_summary
                        local_summaries = 1
                    else:
                        local_skipped += 1

                # 使用乐观锁更新
                if update_values:
                    update_result = await session.execute(
                        update(Article)
                        .where(
                            and_(
                                Article.id == article_id,
                                Article.updated_at == version_timestamp,
                            )
                        )
                        .values(**update_values)
                    )

                    if update_result.rowcount == 0:
                        await session.rollback()
                        return (0, 0, 0, 0, 1)

                await session.commit()
                return (local_titles, local_summaries, local_skipped, local_failed, local_conflict)

        except Exception as e:
            logger.warning(f"Failed to translate article {article_id}: {e}")
            return (0, 0, 0, 1, 0)

    async def update_counter(result: tuple[int, int, int, int, int]):
        """线程安全地更新计数器"""
        nonlocal translated_titles, translated_summaries, skipped, failed, conflict
        async with counter_lock:
            translated_titles += result[0]
            translated_summaries += result[1]
            skipped += result[2]
            failed += result[3]
            conflict += result[4]
            progress_counter[0] += 1
            current = progress_counter[0]
            pct = (current / total_count) * 100
            logger.info(f"[translate] 进度: {current}/{total_count} ({pct:.1f}%) - 标题: {translated_titles}, 摘要: {translated_summaries}")

    semaphore = asyncio.Semaphore(concurrency)

    async def translate_with_semaphore(article_id: int, version_timestamp):
        async with semaphore:
            result = await translate_article(article_id, version_timestamp)
            await update_counter(result)

    try:
        tasks = [translate_with_semaphore(aid, ver) for aid, ver in article_versions]
        await asyncio.gather(*tasks)

        return {
            "translated_titles": translated_titles,
            "translated_summaries": translated_summaries,
            "skipped": skipped,
            "failed": failed,
            "conflict": conflict,
            "total": len(article_versions),
        }
    except Exception as e:
        logger.error(f"Translation for articles failed: {e}", exc_info=True)
        return {
            "error": str(e),
            "translated_titles": translated_titles,
            "translated_summaries": translated_summaries,
            "skipped": skipped,
            "failed": failed,
            "conflict": conflict,
            "total": len(article_versions),
        }
    finally:
        await provider.close()


async def _run_embedding(limit: int, verbose: bool) -> dict:
    """Run embedding computation stage."""
    from core.database import get_session_factory
    from apps.embedding.service import EmbeddingService

    session_factory = get_session_factory()

    def progress_callback(current: int, total: int, message: str) -> None:
        """Progress callback for embedding computation."""
        if total > 0:
            pct = (current / total) * 100
            logger.info(f"[embedding] 进度: {current}/{total} ({pct:.0f}%) - {message}")

    async with session_factory() as session:
        service = EmbeddingService()
        try:
            result = await service.compute_uncomputed(
                session, limit=limit, progress_callback=progress_callback
            )
            await session.commit()
            return result
        except Exception as e:
            logger.error(f"Embedding computation failed: {e}", exc_info=verbose)
            await session.rollback()
            return {"error": str(e), "computed": 0, "skipped": 0, "failed": 0, "total": 0}


async def _run_event(limit: int, verbose: bool) -> dict:
    """Run event clustering stage."""
    from core.database import get_session_factory
    from apps.event.service import EventService

    session_factory = get_session_factory()
    async with session_factory() as session:
        service = EventService()
        try:
            result = await service.cluster_articles(session, limit=limit)
            # 保存 AIGC 汇总文章
            if result.get("clustered", 0) > 0 or result.get("new_clusters", 0) > 0:
                try:
                    from apps.scheduler.jobs.event_cluster_job import _save_event_aigc_article
                    await _save_event_aigc_article(session, result)
                except Exception as e:
                    logger.warning(f"Failed to save event AIGC article: {e}")
            await session.commit()
            return result
        except Exception as e:
            logger.error(f"Event clustering failed: {e}", exc_info=verbose)
            await session.rollback()
            return {"error": str(e), "clustered": 0, "new_clusters": 0, "total_processed": 0}


async def _run_topic(limit: int, verbose: bool) -> dict:
    """Run topic discovery stage."""
    from core.database import get_session_factory
    from apps.topic.service import TopicService

    session_factory = get_session_factory()
    async with session_factory() as session:
        service = TopicService()
        try:
            suggestions = await service.discover(
                session,
                days=settings.topic_lookback_days,
                min_frequency=settings.topic_min_frequency,
            )
            # 保存 AIGC 汇总文章
            if suggestions:
                try:
                    from apps.scheduler.jobs.topic_discovery_job import _save_topic_aigc_article
                    await _save_topic_aigc_article(session, suggestions)
                    await session.commit()
                except Exception as e:
                    logger.warning(f"Failed to save topic AIGC article: {e}")
            return {"suggestions_count": len(suggestions), "suggestions": suggestions}
        except Exception as e:
            logger.error(f"Topic discovery failed: {e}", exc_info=verbose)
            await session.rollback()
            return {"error": str(e), "suggestions_count": 0}


async def _run_topic_match(limit: int, verbose: bool) -> dict:
    """Run topic match stage - match articles to existing topics.

    将文章匹配到已有话题，建立文章-话题关联关系。
    """
    from apps.scheduler.jobs.topic_match_job import run_topic_match_job

    try:
        # 使用 limit 参数控制处理数量
        result = await run_topic_match_job(days=7, limit=limit)
        return result
    except Exception as e:
        logger.error(f"Topic match failed: {e}", exc_info=verbose)
        return {"error": str(e), "matched_count": 0, "total_processed": 0, "associations_created": 0}


async def _run_action(limit: int, verbose: bool) -> dict:
    """Run action item extraction stage."""
    from core.database import get_session_factory
    from apps.scheduler.jobs.action_extract_job import run_action_extract_job

    # action extract job manages its own session; limit is unused here
    try:
        result = await run_action_extract_job()
        # Strip the "skipped" results when running with --force
        if result.get("skipped"):
            # Force mode: run the extraction directly
            from sqlalchemy import and_, select
            from core.models.user import User
            import core.models.permission  # noqa: F401
            from apps.crawler.models.article import Article
            from apps.action.models import ActionItem
            from apps.action.extractor import extract_actions_from_article

            session_factory = get_session_factory()
            extracted_total = 0
            articles_processed = 0
            async with session_factory() as session:
                user_result = await session.execute(
                    select(User.id).where(User.is_superuser.is_(True)).limit(1)
                )
                system_user_id = user_result.scalar()
                if not system_user_id:
                    return {"articles_processed": 0, "extracted": 0}

                art_result = await session.execute(
                    select(Article.id)
                    .outerjoin(ActionItem, Article.id == ActionItem.article_id)
                    .where(
                        and_(
                            ActionItem.id.is_(None),
                            Article.ai_processed_at.isnot(None),
                            Article.is_archived.is_(False),
                            Article.importance_score >= 6,
                            Article.actionable_items.isnot(None),
                        )
                    )
                    .order_by(Article.crawl_time.desc())
                    .limit(limit)
                )
                article_ids = [row[0] for row in art_result.all()]
                for article_id in article_ids:
                    try:
                        actions = await extract_actions_from_article(article_id, system_user_id, session)
                        extracted_total += len(actions)
                        articles_processed += 1
                    except Exception as e:
                        logger.warning(f"Failed to extract actions from article {article_id}: {e}")
                # 保存 AIGC 汇总文章
                if extracted_total > 0:
                    try:
                        from apps.scheduler.jobs.action_extract_job import _save_action_aigc_article
                        await _save_action_aigc_article(session, articles_processed, extracted_total)
                    except Exception as e:
                        logger.warning(f"Failed to save action AIGC article: {e}")
                await session.commit()
            return {"articles_processed": articles_processed, "extracted": extracted_total}
        return result
    except Exception as e:
        logger.error(f"Action extraction failed: {e}", exc_info=verbose)
        return {"error": str(e), "articles_processed": 0, "extracted": 0}


async def _run_report(limit: int, verbose: bool) -> dict:
    """Run report generation stage (weekly)."""
    from apps.scheduler.jobs.report_generate_job import run_weekly_report_job

    try:
        result = await run_weekly_report_job()
        if result.get("skipped"):
            # Force mode: run directly
            from core.database import get_session_factory
            from sqlalchemy import and_, select
            from core.models.user import User
            import core.models.permission  # noqa: F401
            from apps.report.models import Report
            from apps.report.service import ReportService
            from datetime import datetime, timedelta, timezone

            session_factory = get_session_factory()
            generated = 0
            skipped = 0
            async with session_factory() as session:
                user_result = await session.execute(
                    select(User.id).where(User.is_active.is_(True))
                )
                user_ids = [row[0] for row in user_result.all()]
                if not user_ids:
                    return {"generated": 0, "skipped": 0}

                service = ReportService()
                today = datetime.now(timezone.utc)
                last_week_start = today - timedelta(days=today.weekday() + 7)
                last_week_start = last_week_start.replace(hour=0, minute=0, second=0, microsecond=0)
                period_start_str = last_week_start.strftime("%Y-%m-%d")

                for user_id in user_ids:
                    existing = await session.execute(
                        select(Report.id).where(
                            and_(
                                Report.user_id == user_id,
                                Report.type == "weekly",
                                Report.period_start == period_start_str,
                            )
                        ).limit(1)
                    )
                    if existing.scalar():
                        skipped += 1
                        continue
                    try:
                        await service.generate_weekly(user_id, session, weeks_ago=1)
                        generated += 1
                    except Exception as e:
                        logger.warning(f"Failed to generate report for user {user_id}: {e}")
                # 保存 AIGC 汇总文章
                if generated > 0:
                    try:
                        from apps.scheduler.jobs.report_generate_job import _save_report_aigc_article
                        await _save_report_aigc_article(session, "weekly", period_start_str, generated, skipped)
                    except Exception as e:
                        logger.warning(f"Failed to save report AIGC article: {e}")
                await session.commit()
            return {"generated": generated, "skipped": skipped}
        return result
    except Exception as e:
        logger.error(f"Report generation failed: {e}", exc_info=verbose)
        return {"error": str(e), "generated": 0, "skipped": 0}


STAGE_RUNNERS = {
    "ai": _run_ai,
    "translate": _run_translate,
    "embedding": _run_embedding,
    "event": _run_event,
    "topic": _run_topic,
    "topic-match": _run_topic_match,
    "action": _run_action,
    "report": _run_report,
}


# ---------------------------------------------------------------------------
# 队列触发模式
# ---------------------------------------------------------------------------

async def _trigger_stage(stage: str, limit: int) -> dict:
    """Enqueue a pipeline task instead of executing directly.

    CLI trigger mode uses priority=5 (higher than auto-triggered 0-1).
    """
    from core.database import get_session_factory
    from apps.pipeline.triggers import enqueue_task

    # Only enqueue stages that the pipeline worker can handle
    supported = ("ai", "embedding", "event", "action")
    if stage not in supported:
        return {"skipped": True, "reason": f"stage '{stage}' not supported in trigger mode"}

    session_factory = get_session_factory()
    async with session_factory() as session:
        payload = {"trigger_source": "cli", "limit": limit}
        task = await enqueue_task(session, stage, payload=payload, priority=5)
        await session.commit()
        return {"enqueued": True, "task_id": task.id, "stage": stage}


# ---------------------------------------------------------------------------
# 结果格式化
# ---------------------------------------------------------------------------

def _format_result(stage: str, result: dict) -> str:
    """Format stage result as a human-readable line."""
    if "error" in result:
        return f"  错误: {result['error']}"

    if result.get("enqueued"):
        return f"  已入队: task_id={result.get('task_id')}"

    if stage == "ai":
        return (
            f"  处理: {result.get('processed', 0)} | "
            f"缓存: {result.get('cached', 0)} | "
            f"失败: {result.get('failed', 0)} | "
            f"总计: {result.get('total', 0)}"
        )
    elif stage == "translate":
        conflict_str = f"冲突: {result.get('conflict', 0)} | " if result.get('conflict', 0) > 0 else ""
        return (
            f"  标题: {result.get('translated_titles', 0)} | "
            f"摘要: {result.get('translated_summaries', 0)} | "
            f"{conflict_str}"
            f"跳过: {result.get('skipped', 0)} | "
            f"失败: {result.get('failed', 0)} | "
            f"总计: {result.get('total', 0)}"
        )
    elif stage == "embedding":
        return (
            f"  计算: {result.get('computed', 0)} | "
            f"跳过: {result.get('skipped', 0)} | "
            f"失败: {result.get('failed', 0)} | "
            f"总计: {result.get('total', 0)}"
        )
    elif stage == "event":
        return (
            f"  聚类: {result.get('clustered', 0)} | "
            f"新建: {result.get('new_clusters', 0)} | "
            f"总计: {result.get('total_processed', 0)}"
        )
    elif stage == "topic":
        return f"  发现主题: {result.get('suggestions_count', 0)}"
    elif stage == "topic-match":
        return (
            f"  匹配: {result.get('matched_count', 0)} | "
            f"处理: {result.get('total_processed', 0)} | "
            f"关联: {result.get('associations_created', 0)}"
        )
    elif stage == "action":
        return (
            f"  文章: {result.get('articles_processed', 0)} | "
            f"提取行动项: {result.get('extracted', 0)}"
        )
    elif stage == "report":
        return (
            f"  生成: {result.get('generated', 0)} | "
            f"跳过: {result.get('skipped', 0)}"
        )
    else:
        return f"  {json.dumps(result, ensure_ascii=False)}"


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

async def run_pipeline(
    stages: list[str],
    limit: int,
    skip_disabled: bool,
    verbose: bool,
    trigger_mode: bool = False,
    concurrency: int = 0,
) -> dict[str, dict]:
    """Run the specified pipeline stages sequentially.

    Args:
        stages: List of stage names to run.
        limit: Per-stage batch size limit.
        skip_disabled: Whether to skip feature-disabled stages.
        verbose: Enable verbose output.
        trigger_mode: If True, enqueue tasks instead of executing directly.
        concurrency: Concurrency level for AI/translate stages. 0 means use config default.

    Returns:
        dict mapping stage name to its result dict.
    """
    from core.database import close_db

    # 预热 feature_config 缓存（避免事件循环冲突）
    from common.feature_config import feature_config
    await feature_config.async_reload()
    # 冻结缓存：长批处理期间避免反复查库触发跨事件循环问题
    feature_config.freeze()

    # 如果指定了并发数，覆盖配置中的 ai.batch_concurrency
    if concurrency > 0:
        feature_config._cache["ai.batch_concurrency"] = concurrency
        logger.info(f"并发数设置为: {concurrency}")

    results: dict[str, dict] = {}

    try:
        for stage in stages:
            feature_key = STAGE_FEATURES.get(stage, "")
            enabled = feature_config.get_bool(feature_key, False)

            if not enabled and skip_disabled:
                _log(f"[{stage}] 功能未启用 ({feature_key}=false)，跳过", "warn")
                results[stage] = {"skipped": True, "reason": "feature disabled"}
                continue

            if not enabled and not skip_disabled:
                _log(
                    f"[{stage}] 功能未启用 ({feature_key}=false)，"
                    f"--force 模式下强制运行",
                    "warn",
                )

            desc = STAGE_DESCRIPTIONS.get(stage, stage)
            if trigger_mode:
                _log(f"[{stage}] 入队: {desc}")
            else:
                _log(f"[{stage}] 开始: {desc} (limit={limit})")

            t0 = time.time()
            try:
                if trigger_mode:
                    result = await _trigger_stage(stage, limit)
                elif stage == "translate":
                    # translate 阶段支持独立的并发控制
                    result = await _run_translate(limit, verbose, concurrency=concurrency)
                else:
                    result = await STAGE_RUNNERS[stage](limit, verbose)
            except Exception as e:
                logger.error(f"Stage '{stage}' failed: {e}", exc_info=verbose)
                result = {"error": str(e)}
            elapsed = time.time() - t0

            results[stage] = result

            # 打印阶段结果
            if "error" in result:
                _log(f"[{stage}] 失败 ({elapsed:.1f}s)", "error")
            elif result.get("enqueued"):
                _log(f"[{stage}] 已入队 ({elapsed:.1f}s)", "success")
            else:
                _log(f"[{stage}] 完成 ({elapsed:.1f}s)", "success")
            print(_format_result(stage, result))
            print()
    finally:
        feature_config.unfreeze()
        await close_db()

    return results


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="ResearchPulse v2 AI 流水线手动运行工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s all                   # 运行全部阶段
  %(prog)s ai                    # 仅运行 AI 处理
  %(prog)s ai translate          # 运行 AI 处理 + 标题翻译
  %(prog)s translate             # 仅翻译 arXiv 文章标题
  %(prog)s embedding event topic # 运行嵌入 → 事件 → 主题
  %(prog)s all --limit 200       # 每阶段最多处理 200 条
  %(prog)s all --concurrency 4   # 并发处理 4 篇文章
  %(prog)s all --force           # 忽略功能开关，强制运行所有阶段
  %(prog)s all --trigger --force # 将所有阶段任务入队，由 worker 异步执行

阶段说明:
  ai        AI 文章处理（摘要/分类/评分）   [feature.ai_processor]
  translate arXiv 文章标题翻译               [feature.ai_processor]
  embedding 向量嵌入计算                     [feature.embedding]
  event     事件聚类                         [feature.event_clustering]
  topic     主题发现                         [feature.topic_radar]
  action    行动项提取                       [feature.action_items]
  report    报告生成                         [feature.report_generation]
""",
    )

    parser.add_argument(
        "stages",
        nargs="+",
        choices=list(STAGES) + ["all"],
        help="要运行的流水线阶段 (all = 全部按顺序运行)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="每阶段最多处理的文章数 (默认: 50)",
    )
    parser.add_argument(
        "--concurrency", "-c",
        type=int,
        default=0,
        help="并发数，控制 AI/翻译等阶段的并发处理数 (默认: 0，使用配置文件设置)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="忽略功能开关，强制运行所有指定阶段",
    )
    parser.add_argument(
        "--trigger",
        action="store_true",
        help="队列模式: 将阶段任务入队到 pipeline_tasks 表，由 worker 异步执行",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="显示详细输出 (包含完整错误栈)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="以 JSON 格式输出结果",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # 解析阶段列表
    if "all" in args.stages:
        stages = list(STAGES)
    else:
        # 按流水线依赖顺序排序，去重
        seen = set()
        stages = []
        for s in STAGES:
            if s in args.stages and s not in seen:
                stages.append(s)
                seen.add(s)

    if not stages:
        parser.error("未指定有效的流水线阶段")

    # 打印运行信息
    print()
    _log("=" * 50, "info")
    _log("ResearchPulse v2 AI 流水线", "info")
    _log("=" * 50, "info")
    print(f"阶段: {' → '.join(stages)}")
    print(f"Limit: {args.limit}")
    if args.concurrency > 0:
        print(f"并发数: {args.concurrency}")
    if args.trigger:
        print(f"{CYAN}模式: 队列触发 (入队到 pipeline_tasks){NC}")
    if args.force:
        print(f"{YELLOW}模式: 强制运行 (忽略功能开关){NC}")
    _log("-" * 50, "info")
    print()

    t_start = time.time()

    try:
        results = asyncio.run(
            run_pipeline(
                stages=stages,
                limit=args.limit,
                skip_disabled=not args.force,
                verbose=args.verbose,
                trigger_mode=args.trigger,
                concurrency=args.concurrency,
            )
        )
    except KeyboardInterrupt:
        _log("\n用户中断", "warn")
        sys.exit(130)
    except Exception as e:
        _log(f"流水线执行失败: {e}", "error")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)

    t_total = time.time() - t_start

    # JSON 输出
    if args.json_output:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        sys.exit(0)

    # 汇总
    _log("=" * 50, "info")
    _log("流水线执行完毕", "info")
    _log("=" * 50, "info")

    has_error = False
    for stage in stages:
        r = results.get(stage, {})
        if r.get("skipped"):
            status = f"{YELLOW}跳过{NC}"
        elif "error" in r:
            status = f"{RED}失败{NC}"
            has_error = True
        elif r.get("enqueued"):
            status = f"{CYAN}已入队{NC}"
        else:
            status = f"{GREEN}成功{NC}"
        desc = STAGE_DESCRIPTIONS.get(stage, stage)
        print(f"  {stage:12s} {desc:20s} [{status}]")

    print(f"\n总耗时: {t_total:.2f} 秒")
    sys.exit(1 if has_error else 0)


if __name__ == "__main__":
    main()
