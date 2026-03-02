#!/usr/bin/env python3
"""文章 AI 重处理脚本。

本脚本用于重新运行数据库中已有文章的 AI 分析流程。
主要用于调试和批量刷库场景。

功能：
    1. Debug 模式：处理少量文章并打印完整的输入输出细节
    2. 批量刷库：重新运行已有文章的 AI 分析
    3. 支持串行和并行处理

处理流程：
    1. 规则预筛选：根据规则判断是否跳过处理
    2. 任务类型估算：确定处理方式（content_high/content_low）
    3. 域名快速分类：基于 URL 域名的快速分类规则
    4. AI 处理：调用 AI 模型生成摘要、分类、评分等
    5. 翻译：对英文内容进行中文翻译
    6. 保存结果：更新数据库记录

用法示例：
    # Debug 模式：处理 3 篇，打印详细输入输出
    python scripts/reprocess_articles.py --debug

    # Debug 指定数量
    python scripts/reprocess_articles.py --debug --limit 5

    # 指定文章 ID
    python scripts/reprocess_articles.py --ids 12188 12189 12190 --debug

    # 批量刷库：重处理最近 100 篇已处理过的文章
    python scripts/reprocess_articles.py --limit 100

    # 仅处理未处理的文章
    python scripts/reprocess_articles.py --unprocessed --limit 50

    # 按来源类型筛选
    python scripts/reprocess_articles.py --source-type arxiv --limit 20 --debug

    # 并行处理（非 debug 模式）
    python scripts/reprocess_articles.py --limit 100 --concurrency 4

注意：
    - Debug 模式强制串行处理，以便查看每一步的详细信息
    - 并行处理时每个任务创建独立的 AIProcessorService 实例
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path
from textwrap import indent
from urllib.parse import urlparse

# 将项目根目录添加到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

# 抑制垃圾回收器相关的警告
warnings.filterwarnings(
    "ignore",
    message=".*garbage collector.*non-checked-in connection.*",
)

from settings import settings  # noqa: E402

# ---------------------------------------------------------------------------
# ANSI 颜色常量
# ---------------------------------------------------------------------------
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[0;31m"
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
CYAN = "\033[0;36m"
MAGENTA = "\033[0;35m"
NC = "\033[0m"

# ---------------------------------------------------------------------------
# 日志配置
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def _c(text: str, color: str) -> str:
    """为文本添加颜色。

    参数：
        text: 要着色的文本。
        color: ANSI 颜色代码。

    返回：
        str: 着色后的文本。
    """
    return f"{color}{text}{NC}"


def _print_section(title: str) -> None:
    """打印分节标题。

    参数：
        title: 分节标题文本。
    """
    logger.info("")
    logger.info("─" * 60)
    logger.info(title)
    logger.info("─" * 60)


def _print_kv(key: str, value: str, key_width: int = 18) -> None:
    """打印键值对。

    参数：
        key: 键名。
        value: 值。
        key_width: 键名的对齐宽度，默认 18。
    """
    logger.info(f"  {key:<{key_width}} {value}")


def _truncate(text: str, max_len: int = 200) -> str:
    """截断文本。

    将文本截断到指定长度，并用省略号表示截断部分。
    同时移除换行符，使输出更紧凑。

    参数：
        text: 要截断的文本。
        max_len: 最大长度，默认 200。

    返回：
        str: 截断后的文本。如果输入为空，返回 "(empty)"。
    """
    if not text:
        return "(empty)"
    text = text.replace("\n", " ").strip()
    if len(text) > max_len:
        return text[:max_len] + "..."
    return text


# ---------------------------------------------------------------------------
# 核心处理函数
# ---------------------------------------------------------------------------

async def debug_process_article(
    article_id: int,
    service,
    session,
    debug: bool = False,
) -> dict:
    """处理单篇文章。

    与 AIProcessorService.process_article 相同的流程，
    但在 debug 模式下打印每一步的详细信息。

    处理流程：
        1. 查询文章数据
        2. 规则预筛选（判断是否跳过）
        3. 任务类型估算
        4. 域名快速分类
        5. AI 处理（生成摘要、分类、评分）
        6. 翻译（如果是英文）
        7. 保存结果到数据库

    参数：
        article_id: 文章 ID。
        service: AIProcessorService 实例。
        session: 数据库会话。
        debug: 是否打印详细调试信息。

    返回：
        dict: 处理结果，包含：
            - success: 是否成功
            - article_id: 文章 ID
            - processing_method: 处理方式（ai/rule/failed）
            - summary/category/importance_score 等 AI 输出字段
    """
    from sqlalchemy import select
    from apps.crawler.models.article import Article
    from apps.ai_processor.processors.rule_classifier import (
        classify_by_domain,
        estimate_task_type,
        should_skip_processing,
    )
    from apps.ai_processor.service import _is_english

    # ---- Step 1: 查询文章 ----
    result = await session.execute(select(Article).where(Article.id == article_id))
    article = result.scalar_one_or_none()
    if not article:
        logger.warning(f"Article {article_id} not found, skipping")
        return {"success": False, "article_id": article_id, "error_message": "not found"}

    # 提取文章字段
    title = article.title or ""
    content = article.content or article.summary or ""
    url = article.url or ""
    source_type = article.source_type or ""

    # 解析 URL 域名
    domain = None
    if url:
        try:
            domain = urlparse(url).netloc.lower().replace("www.", "")
        except (ValueError, AttributeError):
            pass

    # Debug 模式：打印文章基本信息
    if debug:
        _print_section(f"Article #{article_id}")
        _print_kv("Title", _truncate(title, 80))
        _print_kv("URL", url or "(none)")
        _print_kv("Source", source_type)
        _print_kv("Domain", domain or "(none)")
        _print_kv("Content length", f"{len(content)} chars")
        _print_kv("Has AI result", "Yes" if article.ai_processed_at else "No")
        if article.ai_processed_at:
            _print_kv("  Previous", f"score={article.importance_score} cat={article.ai_category} method={article.processing_method}")

        logger.debug(f"Input Content (first 500 chars):\n{_truncate(content, 500)}")

    # ---- Step 2: 规则预筛选 ----
    # 根据标题和内容判断是否应该跳过处理
    should_skip, skip_reason = should_skip_processing(title, content, source_type)
    if should_skip:
        if debug:
            logger.debug(f"Rule: SKIP ({skip_reason})")
        return {
            "success": True,
            "article_id": article_id,
            "processing_method": "rule",
            "summary": f"[Skipped] {title[:40]}...",
            "category": "其他",
            "importance_score": 1,
        }

    # ---- Step 3: 任务类型估算 ----
    # 根据内容特征确定处理方式
    task_type = estimate_task_type(url, title, content, domain=domain)
    if debug:
        logger.debug(f"Task type: {task_type}")

    # ---- Step 4: 域名快速分类 ----
    # 对短内容使用域名规则快速分类，跳过 AI 处理
    domain_result = classify_by_domain(url, domain=domain)
    if domain_result and len(content) < 1000 and task_type == "content_low":
        category, importance = domain_result
        if debug:
            logger.debug(f"Domain rule: category={category} importance={importance}")
        return {
            "success": True,
            "article_id": article_id,
            "processing_method": "rule",
            "summary": title[:100],
            "category": category,
            "importance_score": min(6, importance),
        }

    # ---- Step 5: AI 处理 ----
    if debug:
        # 打印将要发送给 AI 的完整 prompt
        from common.feature_config import feature_config
        prompt = service.provider.build_prompt(
            title, content, task_type,
            feature_config.get_int("ai.max_content_length", settings.ai_max_content_length),
        )
        no_think = feature_config.get_bool("ai.no_think", settings.ai_no_think)
        if no_think:
            prompt = f"/no_think\n{prompt}"

        logger.debug(f"AI Prompt ({len(prompt)} chars):")
        # 对长 prompt 进行截断显示
        if len(prompt) > 2000:
            display_prompt = prompt[:1000] + f"\n... ({len(prompt) - 2000} chars omitted) ...\n" + prompt[-1000:]
        else:
            display_prompt = prompt
        logger.debug(display_prompt)
        logger.debug("Calling AI provider...")

    t0 = time.time()
    processing_result = await service.provider.process_content(title, content, task_type)
    elapsed = time.time() - t0

    # Debug 模式：打印 AI 响应详情
    if debug:
        success = processing_result.get("success", False)
        status = "SUCCESS" if success else "FAILED"
        logger.debug(f"AI Response: {status} ({elapsed:.1f}s)")
        _print_kv("Provider", processing_result.get("provider", "?"))
        _print_kv("Model", processing_result.get("model", "?"))
        _print_kv("Duration", f"{processing_result.get('duration_ms', 0)}ms")
        _print_kv("Input chars", str(processing_result.get("input_chars", 0)))
        _print_kv("Output chars", str(processing_result.get("output_chars", 0)))

        if success:
            logger.debug("AI Output:")
            _print_kv("Summary", processing_result.get("summary", ""))
            _print_kv("Category", processing_result.get("category", ""))
            _print_kv("Importance", str(processing_result.get("importance_score", "")))
            _print_kv("One-liner", processing_result.get("one_liner", ""))
            # 打印关键点
            kp = processing_result.get("key_points", [])
            if kp:
                _print_kv("Key points", "")
                for i, p in enumerate(kp, 1):
                    logger.debug(f"    {i}. [{p.get('type','')}] {p.get('value','')} → {p.get('impact','')}")
            # 打印影响评估
            impact = processing_result.get("impact_assessment")
            if impact:
                _print_kv("Impact", f"short={impact.get('short_term','')}  long={impact.get('long_term','')}")
            # 打印行动项
            actions = processing_result.get("actionable_items", [])
            if actions:
                _print_kv("Actions", "")
                for i, a in enumerate(actions, 1):
                    logger.debug(f"    {i}. [{a.get('priority','')}] {a.get('type','')}: {a.get('description','')}")
        else:
            logger.error(f"Error: {processing_result.get('error_message', 'unknown')}")

    # ---- Step 6: 翻译 ----
    # 对英文摘要进行中文翻译
    translated = None
    if processing_result.get("success") and _is_english(article.summary or ""):
        if debug:
            logger.debug("English detected, translating summary...")
        try:
            t1 = time.time()
            translated = await service.provider.translate(article.summary)
            t_elapsed = time.time() - t1
            if translated:
                processing_result["_translated_content"] = translated
            if debug:
                if translated:
                    logger.debug(f"Translation: OK ({t_elapsed:.1f}s, {len(translated)} chars)")
                    logger.debug(f"Translated: {_truncate(translated, 500)}")
                else:
                    logger.debug("Translation: empty result")
        except Exception as e:
            if debug:
                logger.error(f"Translation FAILED: {e}")

    # ---- Step 7: 保存结果 ----
    processing_result["processing_method"] = "ai" if processing_result.get("success") else "failed"
    await service._save_result(article, processing_result, session)

    if debug:
        logger.info("Result saved to DB")

    return {**processing_result, "article_id": article_id}


# ---------------------------------------------------------------------------
# 批量处理函数
# ---------------------------------------------------------------------------

async def _batch_process_serial(
    article_ids: list[int], service, debug: bool
) -> list[dict]:
    """串行处理文章列表。

    逐个处理文章，适用于 debug 模式或并发数为 1 的场景。

    参数：
        article_ids: 要处理的文章 ID 列表。
        service: AIProcessorService 实例。
        debug: 是否打印调试信息。

    返回：
        list[dict]: 每篇文章的处理结果列表。
    """
    from core.database import get_session_factory

    session_factory = get_session_factory()
    results = []
    total = len(article_ids)

    for i, aid in enumerate(article_ids, 1):
        logger.info(f"[{i}/{total}] Processing article {aid} ...")

        try:
            async with session_factory() as session:
                result = await debug_process_article(aid, service, session, debug=debug)
                await session.commit()
                results.append(result)

            # 打印处理状态
            method = result.get("processing_method", "")
            success = result.get("success", False)
            score = result.get("importance_score", "?")
            cat = result.get("category", "?")

            if method == "cached":
                status = "cached"
            elif method == "rule":
                status = "rule"
            elif success:
                status = "ok"
            else:
                status = "failed"

            logger.info(f"[{i}/{total}] Article {aid} [{status}] score={score} cat={cat}")

        except Exception as e:
            results.append({
                "success": False,
                "article_id": aid,
                "processing_method": "failed",
                "error_message": str(e),
            })
            logger.error(f"[{i}/{total}] Article {aid} failed: {e}")
            if debug:
                import traceback
                traceback.print_exc()

    return results


async def _batch_process_concurrent(
    article_ids: list[int], concurrency: int
) -> list[dict]:
    """并行处理文章列表。

    使用信号量控制并发数，每个任务创建独立的 AIProcessorService 实例。

    参数：
        article_ids: 要处理的文章 ID 列表。
        concurrency: 并发数。

    返回：
        list[dict]: 每篇文章的处理结果列表（保持原始顺序）。
    """
    import asyncio
    from core.database import get_session_factory
    from apps.ai_processor.service import AIProcessorService

    semaphore = asyncio.Semaphore(concurrency)
    session_factory = get_session_factory()
    total = len(article_ids)
    completed = [0]  # 使用 list 以便在闭包中修改
    results = [None] * total  # 预分配结果数组，保持顺序
    lock = asyncio.Lock()

    async def _process_one(article_id: int, index: int) -> dict:
        """处理单篇文章的内部函数。"""
        async with semaphore:
            # 打印开始处理信息
            async with lock:
                logger.info(f"[{completed[0] + 1}/{total}] Processing article {article_id} ...")

            # 每个任务创建独立的 service 实例，避免共享状态
            task_service = AIProcessorService()
            try:
                async with session_factory() as session:
                    result = await debug_process_article(article_id, task_service, session, debug=False)
                    await session.commit()

                    # 更新进度并打印结果
                    async with lock:
                        completed[0] += 1
                        results[index] = result

                        # 打印结果状态
                        method = result.get("processing_method", "")
                        success = result.get("success", False)
                        score = result.get("importance_score", "?")
                        cat = result.get("category", "?")

                        if method == "cached":
                            status = "cached"
                        elif method == "rule":
                            status = "rule"
                        elif success:
                            status = "ok"
                        else:
                            status = "failed"

                        logger.info(f"[{completed[0]}/{total}] Article {article_id} [{status}] score={score} cat={cat}")

                    return result
            except Exception as e:
                async with lock:
                    completed[0] += 1
                    results[index] = {
                        "success": False,
                        "article_id": article_id,
                        "processing_method": "failed",
                        "error_message": str(e),
                    }
                    logger.error(f"[{completed[0]}/{total}] Article {article_id} failed: {e}")
                return results[index]
            finally:
                await task_service.close()

    # 并发执行所有任务
    tasks = [_process_one(aid, i) for i, aid in enumerate(article_ids)]
    await asyncio.gather(*tasks)
    return results


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

async def run(args: argparse.Namespace) -> None:
    """主流程入口。

    根据命令行参数执行文章重处理。

    参数：
        args: 解析后的命令行参数。
    """
    from core.database import get_session_factory, close_db
    from common.feature_config import feature_config
    from apps.ai_processor.service import AIProcessorService
    from sqlalchemy import select
    from apps.crawler.models.article import Article

    debug = args.debug
    limit = args.limit if not debug or args.limit != 50 else 3  # debug 默认 3 篇
    concurrency = args.concurrency or 1  # 默认串行

    # 预热配置和服务
    await feature_config.async_reload()
    feature_config.freeze()

    service = AIProcessorService()
    warmup_ok = await service.warmup()
    if not warmup_ok:
        logger.warning("Model warmup did not complete")

    session_factory = get_session_factory()

    try:
        # ---- 确定要处理的文章 ID ----
        if args.ids:
            # 使用指定的文章 ID
            article_ids = args.ids
        else:
            # 从数据库查询文章
            async with session_factory() as session:
                query = select(Article.id)
                if args.unprocessed:
                    # 仅查询未处理的文章
                    query = query.where(Article.ai_processed_at.is_(None))
                else:
                    # 默认：选取已处理过的文章（刷库场景）
                    query = query.where(Article.ai_processed_at.isnot(None))

                # 排除已归档和 AIGC 文章
                query = query.where(Article.is_archived.is_(False))
                query = query.where(Article.source_type != "aigc")

                # 按来源类型筛选
                if args.source_type:
                    query = query.where(Article.source_type == args.source_type)

                # 按爬取时间倒序，限制数量
                query = query.order_by(Article.crawl_time.desc()).limit(limit)
                result = await session.execute(query)
                article_ids = [row[0] for row in result.all()]

        if not article_ids:
            logger.warning("No articles found matching criteria.")
            return

        total = len(article_ids)
        mode_str = " (debug mode)" if debug else ""
        concurrency_str = f" (concurrency={concurrency})" if concurrency > 1 else ""
        logger.info(f"Reprocessing {total} article(s){mode_str}{concurrency_str}")
        if not debug and total <= 20:
            logger.info(f"Article IDs: {article_ids}")

        # ---- 执行处理 ----
        t_start = time.time()

        if concurrency > 1 and not debug:
            # 并行处理
            results = await _batch_process_concurrent(article_ids, concurrency)
        else:
            # 串行处理（debug 模式强制串行）
            results = await _batch_process_serial(article_ids, service, debug)

        # ---- 统计结果 ----
        stats = {"processed": 0, "cached": 0, "rule": 0, "failed": 0}
        for result in results:
            method = result.get("processing_method", "")
            success = result.get("success", False)

            if method == "cached":
                stats["cached"] += 1
            elif method == "rule":
                stats["rule"] += 1
            elif success:
                stats["processed"] += 1
            else:
                stats["failed"] += 1

        # ---- 打印汇总 ----
        t_total = time.time() - t_start
        _print_section("Summary")
        _print_kv("Total", str(total))
        _print_kv("AI processed", str(stats["processed"]))
        _print_kv("Rule classified", str(stats["rule"]))
        _print_kv("Failed", str(stats["failed"]))
        _print_kv("Elapsed", f"{t_total:.1f}s")
        if stats["processed"] > 0:
            _print_kv("Avg per article", f"{t_total / stats['processed']:.1f}s")
        logger.info("")

    finally:
        feature_config.unfreeze()
        await service.close()
        await close_db()


def main():
    """命令行入口函数。"""
    parser = argparse.ArgumentParser(
        description="Reprocess existing articles through AI pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --debug                      # Debug 3 articles with full I/O
  %(prog)s --debug --limit 5            # Debug 5 articles
  %(prog)s --ids 12188 12189 --debug    # Debug specific articles
  %(prog)s --limit 100                  # Batch reprocess 100 articles
  %(prog)s --unprocessed --limit 50     # Process unprocessed articles
  %(prog)s --source-type arxiv --debug  # Debug arxiv articles only
""",
    )
    parser.add_argument(
        "--debug", "-d",
        action="store_true",
        help="Debug mode: print full prompt, AI response, and translation details",
    )
    parser.add_argument(
        "--limit", "-n",
        type=int,
        default=50,
        help="Max articles to process (default: 50, debug default: 3)",
    )
    parser.add_argument(
        "--ids",
        type=int,
        nargs="+",
        help="Specific article IDs to reprocess",
    )
    parser.add_argument(
        "--unprocessed",
        action="store_true",
        help="Only process articles without existing AI results",
    )
    parser.add_argument(
        "--source-type",
        type=str,
        help="Filter by source type (e.g., arxiv, rss, hackernews, weibo)",
    )
    parser.add_argument(
        "--concurrency", "-c",
        type=int,
        default=1,
        help="Number of concurrent workers (default: 1, serial mode). "
             "Use higher values for parallel processing (e.g., -c 4). "
             "Note: debug mode always uses serial processing.",
    )

    args = parser.parse_args()

    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        logger.warning("Interrupted")
        sys.exit(130)


if __name__ == "__main__":
    main()
