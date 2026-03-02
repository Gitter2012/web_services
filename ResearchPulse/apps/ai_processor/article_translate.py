# =============================================================================
# 模块: apps/ai_processor/article_translate.py
# 功能: arXiv 文章翻译核心逻辑（标题 + 摘要，英文 → 中文）
# 架构角色: AI 处理器子系统的公共翻译函数
# 设计理念:
#   1. 单一职责：仅负责文章批量翻译，不含其他 AI 处理逻辑
#   2. 乐观锁：使用 updated_at 作为版本号，避免多进程并发冲突
#   3. 可复用：供 apps/crawler/translate_hook.py 和 scripts/ 共同调用
# =============================================================================

"""Article translation utilities for ResearchPulse.

Provides a single public function `translate_articles` that translates
arXiv English titles and summaries to Chinese, using optimistic locking
to handle concurrent access safely.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


async def translate_articles(
    article_ids: list[int] | None = None,
    limit: int | None = None,
    concurrency: int = 1,
) -> dict[str, Any]:
    """翻译 arXiv 文章的英文标题和摘要。

    参数：
        article_ids: 要翻译的文章 ID 列表。为 None 时翻译所有待翻译文章。
        limit: 最多处理的文章数量（仅在 article_ids 为 None 时生效）。
        concurrency: 并发翻译任务数。

    返回：
        dict: 翻译结果统计，包含以下字段：
            - translated_titles: 翻译成功的标题数
            - translated_summaries: 翻译成功的摘要数
            - skipped: 跳过的数量（AI 返回空结果）
            - failed: 失败数量
            - conflict: 乐观锁冲突数量
            - total: 实际处理的文章数
    """
    from core.database import get_session_factory
    from sqlalchemy import and_, or_, select, update
    from apps.crawler.models.article import Article
    from apps.ai_processor.service import get_ai_provider, _is_english

    # article_ids 为空列表时直接返回
    if article_ids is not None and not article_ids:
        return {"translated_titles": 0, "translated_summaries": 0, "skipped": 0, "failed": 0, "total": 0}

    session_factory = get_session_factory()
    provider = get_ai_provider()

    # 构造查询：过滤 source_type='arxiv' 且需要翻译的文章
    # 条件：标题或摘要至少有一个需要翻译
    base_where = and_(
        Article.source_type == "arxiv",
        Article.title.isnot(None),
        Article.title != "",
        or_(
            Article.translated_title.is_(None),
            and_(
                Article.summary.isnot(None),
                Article.summary != "",
                Article.content_summary.is_(None),
            ),
        ),
    )

    async with session_factory() as session:
        query = (
            select(Article.id, Article.updated_at)
            .order_by(Article.crawl_time.desc())
        )

        if article_ids is not None:
            # 指定 ID 模式：在给定 ID 中筛选需要翻译的
            query = query.where(and_(Article.id.in_(article_ids), base_where))
        else:
            # 全量模式：翻译所有待翻译文章，可选数量限制
            query = query.where(base_where)
            if limit is not None:
                query = query.limit(limit)

        result = await session.execute(query)
        # (article_id, version_timestamp) 列表，version_timestamp 作乐观锁版本号
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
    progress_counter = [0]  # 使用列表以便在闭包中修改
    total_count = len(article_versions)

    async def translate_article(article_id: int, version_timestamp) -> tuple[int, int, int, int, int]:
        """翻译单篇文章，使用乐观锁。

        返回：
            tuple: (titles, summaries, skipped, failed, conflict) 计数。
        """
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
        """线程安全地更新计数器。"""
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
            logger.info(
                f"[translate] 进度: {current}/{total_count} ({pct:.1f}%) "
                f"- 标题: {translated_titles}, 摘要: {translated_summaries}"
            )

    # 使用信号量控制并发
    semaphore = asyncio.Semaphore(concurrency)

    async def translate_with_semaphore(article_id: int, version_timestamp):
        async with semaphore:
            result = await translate_article(article_id, version_timestamp)
            await update_counter(result)

    try:
        # 并发执行所有翻译任务
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
        logger.error(f"Translation failed: {e}", exc_info=True)
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
