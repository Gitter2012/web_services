# =============================================================================
# 模块: apps/ai_processor/article_translate.py
# 功能: arXiv 文章翻译核心逻辑（标题 + 摘要，英文 → 中文）
# 架构角色: AI 处理器子系统的公共翻译函数
# 设计理念:
#   1. 单一职责：仅负责文章批量翻译，不含其他 AI 处理逻辑
#   2. 批量并发：先收集所有待翻译文本，再通过 translate_batch 分批并发翻译
#   3. 分批保护：batch_size 控制每批文本量，batch_delay 批间延迟，兼容限速 provider
#   4. 乐观锁：使用 updated_at 作为版本号，避免多进程并发冲突
#   5. 可复用：供 apps/crawler/translate_hook.py 和 scripts/ 共同调用
# =============================================================================

"""Article translation utilities for ResearchPulse.

Provides a single public function `translate_articles` that translates
arXiv English titles and summaries to Chinese, using optimistic locking
to handle concurrent access safely.

四阶段流水线：
  阶段1: 查询所有需要翻译的文章（含内容字段）
  阶段2: 收集待翻译文本列表，记录每篇文章的文本索引
  阶段3+4: 按 batch_size 分批翻译，每批完成后立即并发写回该批涉及的文章
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


async def translate_articles(
    article_ids: list[int] | None = None,
    limit: int | None = None,
    concurrency: int | None = None,
    batch_size: int = 20,
    batch_delay: float = 0.1,
) -> dict[str, Any]:
    """翻译 arXiv 文章的英文标题和摘要。

    参数：
        article_ids: 要翻译的文章 ID 列表。为 None 时翻译所有待翻译文章。
        limit: 最多处理的文章数量（仅在 article_ids 为 None 时生效）。
        concurrency: 并发翻译任务数。为 None 时从 feature_config ai.translate_concurrency 读取（默认 5）。
        batch_size: 每批提交给 translate_batch 的文本数量，用于控制单次 API 请求压力（默认 20）。
        batch_delay: 批次之间的间隔时间（秒），兼容有速率限制的 provider（默认 0.1）。

    返回：
        dict: 翻译结果统计，包含以下字段：
            - translated_titles: 翻译成功的标题数
            - translated_summaries: 翻译成功的摘要数
            - skipped: 跳过的数量（AI 返回空结果）
            - failed: 失败数量
            - conflict: 乐观锁冲突数量
            - total: 实际处理的文章数
    """
    from common.feature_config import feature_config
    from core.database import get_session_factory
    from sqlalchemy import and_, or_, select, update
    from apps.crawler.models.article import Article
    from apps.ai_processor.service import get_ai_provider, _is_english

    # article_ids 为空列表时直接返回
    if article_ids is not None and not article_ids:
        return {"translated_titles": 0, "translated_summaries": 0, "skipped": 0, "failed": 0, "conflict": 0, "total": 0}

    # 从配置读取并发度
    if concurrency is None:
        concurrency = feature_config.get_int("ai.translate_concurrency", 5)

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

    # -------------------------------------------------------------------------
    # 阶段1：查询需翻译文章（含内容字段，避免后续额外查询）
    # -------------------------------------------------------------------------
    async with session_factory() as session:
        query = (
            select(
                Article.id,
                Article.title,
                Article.summary,
                Article.translated_title,
                Article.content_summary,
                Article.updated_at,
            )
            .order_by(Article.crawl_time.desc())
        )

        if article_ids is not None:
            query = query.where(and_(Article.id.in_(article_ids), base_where))
        else:
            query = query.where(base_where)
            if limit is not None:
                query = query.limit(limit)

        result = await session.execute(query)
        rows = result.all()

    if not rows:
        await provider.close()
        return {"translated_titles": 0, "translated_summaries": 0, "skipped": 0, "failed": 0, "conflict": 0, "total": 0}

    total_count = len(rows)

    # -------------------------------------------------------------------------
    # 阶段2：收集待翻译文本列表
    # texts: 所有需翻译的原文（标题和摘要混合）
    # meta:  每篇文章对应的 {article_id, version_timestamp, title_idx, summary_idx}
    #        title_idx / summary_idx 是该文本在 texts 中的下标，None 表示无需翻译
    # -------------------------------------------------------------------------
    texts: list[str] = []
    meta: list[dict] = []

    for row in rows:
        article_id, title, summary, existing_translated_title, existing_content_summary, updated_at = row
        title_idx = None
        summary_idx = None

        # 标题：未翻译且为英文
        if not existing_translated_title and title and _is_english(title):
            title_idx = len(texts)
            texts.append(title)

        # 摘要：未翻译、有内容且为英文
        if not existing_content_summary and summary and _is_english(summary):
            summary_idx = len(texts)
            texts.append(summary)

        meta.append({
            "article_id": article_id,
            "version_timestamp": updated_at,
            "title_idx": title_idx,
            "summary_idx": summary_idx,
        })

    if not texts:
        # 所有文章均已翻译，无需处理
        await provider.close()
        return {"translated_titles": 0, "translated_summaries": 0, "skipped": 0, "failed": 0, "conflict": 0, "total": total_count}

    total_batches = (len(texts) + batch_size - 1) // batch_size
    logger.info(
        f"[translate] 待翻译: {len(texts)} 个文本（{total_count} 篇文章），"
        f"并发度: {concurrency}，分批大小: {batch_size}，共 {total_batches} 批"
    )

    # -------------------------------------------------------------------------
    # 阶段3+4：分批翻译 + 每批立即写回
    # - translated_texts 预初始化为 None，按批次填充，write_article 只写非 None 的字段
    # - 每批翻译完成后，筛选出该批涉及的文章（batch_meta）并发写回
    # - 标题和摘要跨批次时，该文章会被写回两次（各写一个字段），乐观锁各自独立检查
    # -------------------------------------------------------------------------
    # 预初始化翻译结果列表，按批次填充（确保跨批次文章写回时未翻译字段为 None）
    translated_texts: list[str | None] = [None] * len(texts)

    translated_titles = 0
    translated_summaries = 0
    skipped = 0
    failed = 0
    conflict = 0
    write_semaphore = asyncio.Semaphore(concurrency)

    async def write_article(item: dict) -> None:
        """写回单篇文章，仅写入 translated_texts 中已填充（非 None）的字段。"""
        nonlocal translated_titles, translated_summaries, skipped, failed, conflict

        article_id = item["article_id"]
        version_timestamp = item["version_timestamp"]
        title_idx = item["title_idx"]
        summary_idx = item["summary_idx"]

        update_values: dict = {}
        local_skipped = 0

        # 回填标题翻译结果（None 表示该批次尚未翻译，跳过）
        if title_idx is not None:
            result_title = translated_texts[title_idx]
            if result_title is not None:
                if result_title:
                    update_values["translated_title"] = result_title
                else:
                    local_skipped += 1

        # 回填摘要翻译结果（None 表示该批次尚未翻译，跳过）
        if summary_idx is not None:
            result_summary = translated_texts[summary_idx]
            if result_summary is not None:
                if result_summary:
                    update_values["content_summary"] = result_summary
                else:
                    local_skipped += 1

        if not update_values:
            skipped += local_skipped
            return

        try:
            async with session_factory() as session:
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

                if update_result.rowcount == 0:
                    logger.debug(f"Article {article_id} optimistic lock conflict")
                    await session.rollback()
                    conflict += 1
                    return

                await session.commit()

                if "translated_title" in update_values:
                    translated_titles += 1
                if "content_summary" in update_values:
                    translated_summaries += 1
                skipped += local_skipped

        except Exception as e:
            logger.warning(f"Failed to write translation for article {article_id}: {e}")
            failed += 1

    async def write_with_semaphore(item: dict) -> None:
        async with write_semaphore:
            await write_article(item)

    try:
        for batch_idx, i in enumerate(range(0, len(texts), batch_size), 1):
            batch = texts[i:i + batch_size]
            batch_end = i + len(batch)

            # 翻译当前批次
            batch_results = await provider.translate_batch(batch, concurrency=concurrency)

            # 填充本批次的翻译结果到全局列表
            translated_texts[i:batch_end] = batch_results

            # 筛选出 title_idx 或 summary_idx 落在本批次范围内的文章
            batch_meta = [
                item for item in meta
                if (item["title_idx"] is not None and i <= item["title_idx"] < batch_end)
                or (item["summary_idx"] is not None and i <= item["summary_idx"] < batch_end)
            ]

            # 立即并发写回本批次涉及的文章
            write_tasks = [write_with_semaphore(item) for item in batch_meta]
            await asyncio.gather(*write_tasks)

            logger.info(
                f"[translate] 批次 {batch_idx}/{total_batches} 完成并写回"
                f"（{len(batch)} 个文本，{len(batch_meta)} 篇文章）"
            )

            # 最后一批不需要延迟
            if batch_end < len(texts):
                await asyncio.sleep(batch_delay)

    except Exception as e:
        logger.error(f"translate_batch failed: {e}", exc_info=True)
        return {
            "error": str(e),
            "translated_titles": translated_titles,
            "translated_summaries": translated_summaries,
            "skipped": skipped,
            "failed": failed + (total_count - translated_titles - translated_summaries - skipped - conflict - failed),
            "conflict": conflict,
            "total": total_count,
        }
    finally:
        await provider.close()

    logger.info(
        f"[translate] 完成: 标题 {translated_titles}, 摘要 {translated_summaries}, "
        f"跳过 {skipped}, 冲突 {conflict}, 失败 {failed} / 共 {total_count} 篇"
    )

    return {
        "translated_titles": translated_titles,
        "translated_summaries": translated_summaries,
        "skipped": skipped,
        "failed": failed,
        "conflict": conflict,
        "total": total_count,
    }
