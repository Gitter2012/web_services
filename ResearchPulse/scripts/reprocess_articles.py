#!/usr/bin/env python3
"""Reprocess existing articles through the AI pipeline (debug / backfill tool).

从数据库中选取已有文章，重新运行 AI 分析流程。
支持 --debug 模式：仅处理少量文章并打印完整的输入输出细节。

Usage:
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

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

warnings.filterwarnings(
    "ignore",
    message=".*garbage collector.*non-checked-in connection.*",
)

from settings import settings  # noqa: E402

# ---------------------------------------------------------------------------
# ANSI 颜色
# ---------------------------------------------------------------------------
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[0;31m"
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
CYAN = "\033[0;36m"
MAGENTA = "\033[0;35m"
NC = "\033[0m"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def _c(text: str, color: str) -> str:
    return f"{color}{text}{NC}"


def _print_section(title: str) -> None:
    print(f"\n{CYAN}{'─' * 60}{NC}")
    print(f"{BOLD}{title}{NC}")
    print(f"{CYAN}{'─' * 60}{NC}")


def _print_kv(key: str, value: str, key_width: int = 18) -> None:
    print(f"  {DIM}{key:<{key_width}}{NC} {value}")


def _truncate(text: str, max_len: int = 200) -> str:
    if not text:
        return "(empty)"
    text = text.replace("\n", " ").strip()
    if len(text) > max_len:
        return text[:max_len] + "..."
    return text


# ---------------------------------------------------------------------------
# 核心：单篇文章 debug 处理
# ---------------------------------------------------------------------------

async def debug_process_article(
    article_id: int,
    service,
    session,
    debug: bool = False,
) -> dict:
    """Process a single article with optional debug output.

    与 AIProcessorService.process_article 相同的流程，
    但在 debug 模式下打印每一步的详细信息。
    """
    from sqlalchemy import select
    from apps.crawler.models.article import Article
    from apps.ai_processor.processors.rule_classifier import (
        classify_by_domain,
        estimate_task_type,
        should_skip_processing,
    )
    from apps.ai_processor.service import _is_english

    # ---- 查询文章 ----
    result = await session.execute(select(Article).where(Article.id == article_id))
    article = result.scalar_one_or_none()
    if not article:
        print(_c(f"  Article {article_id} not found, skipping", RED))
        return {"success": False, "article_id": article_id, "error_message": "not found"}

    title = article.title or ""
    content = article.content or article.summary or ""
    url = article.url or ""
    source_type = article.source_type or ""

    domain = None
    if url:
        try:
            domain = urlparse(url).netloc.lower().replace("www.", "")
        except (ValueError, AttributeError):
            pass

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

        print(f"\n  {DIM}── Input Content (first 500 chars) ──{NC}")
        print(indent(_truncate(content, 500), "  │ "))

    # ---- 规则预筛选 ----
    should_skip, skip_reason = should_skip_processing(title, content, source_type)
    if should_skip:
        if debug:
            print(f"\n  {YELLOW}→ Rule: SKIP ({skip_reason}){NC}")
        return {
            "success": True,
            "article_id": article_id,
            "processing_method": "rule",
            "summary": f"[Skipped] {title[:40]}...",
            "category": "其他",
            "importance_score": 1,
        }

    # ---- 任务类型估算 ----
    task_type = estimate_task_type(url, title, content, domain=domain)
    if debug:
        print(f"\n  {CYAN}→ Task type: {task_type}{NC}")

    # ---- 域名快速分类 ----
    domain_result = classify_by_domain(url, domain=domain)
    if domain_result and len(content) < 1000 and task_type == "content_low":
        category, importance = domain_result
        if debug:
            print(f"  {YELLOW}→ Domain rule: category={category} importance={importance}{NC}")
        return {
            "success": True,
            "article_id": article_id,
            "processing_method": "rule",
            "summary": title[:100],
            "category": category,
            "importance_score": min(6, importance),
        }

    # ---- AI 处理 ----
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

        print(f"\n  {DIM}── AI Prompt ({len(prompt)} chars) ──{NC}")
        # 打印完整 prompt，对长内容做合理截断
        if len(prompt) > 2000:
            display_prompt = prompt[:1000] + f"\n  ... ({len(prompt) - 2000} chars omitted) ...\n" + prompt[-1000:]
        else:
            display_prompt = prompt
        print(indent(display_prompt, "  │ "))
        print(f"\n  {CYAN}→ Calling AI provider...{NC}")

    t0 = time.time()
    processing_result = await service.provider.process_content(title, content, task_type)
    elapsed = time.time() - t0

    if debug:
        success = processing_result.get("success", False)
        status = _c("SUCCESS", GREEN) if success else _c("FAILED", RED)
        print(f"  → AI Response: {status} ({elapsed:.1f}s)")
        _print_kv("Provider", processing_result.get("provider", "?"))
        _print_kv("Model", processing_result.get("model", "?"))
        _print_kv("Duration", f"{processing_result.get('duration_ms', 0)}ms")
        _print_kv("Input chars", str(processing_result.get("input_chars", 0)))
        _print_kv("Output chars", str(processing_result.get("output_chars", 0)))

        if success:
            print(f"\n  {DIM}── AI Output ──{NC}")
            _print_kv("Summary", processing_result.get("summary", ""))
            _print_kv("Category", processing_result.get("category", ""))
            _print_kv("Importance", str(processing_result.get("importance_score", "")))
            _print_kv("One-liner", processing_result.get("one_liner", ""))
            kp = processing_result.get("key_points", [])
            if kp:
                _print_kv("Key points", "")
                for i, p in enumerate(kp, 1):
                    print(f"    {i}. [{p.get('type','')}] {p.get('value','')} → {p.get('impact','')}")
            impact = processing_result.get("impact_assessment")
            if impact:
                _print_kv("Impact", f"short={impact.get('short_term','')}  long={impact.get('long_term','')}")
            actions = processing_result.get("actionable_items", [])
            if actions:
                _print_kv("Actions", "")
                for i, a in enumerate(actions, 1):
                    print(f"    {i}. [{a.get('priority','')}] {a.get('type','')}: {a.get('description','')}")
        else:
            print(f"  {RED}Error: {processing_result.get('error_message', 'unknown')}{NC}")

    # ---- 翻译 ----
    translated = None
    if processing_result.get("success") and _is_english(article.summary or ""):
        if debug:
            print(f"\n  {CYAN}→ English detected, translating summary...{NC}")
        try:
            t1 = time.time()
            translated = await service.provider.translate(article.summary)
            t_elapsed = time.time() - t1
            if translated:
                processing_result["_translated_content"] = translated
            if debug:
                if translated:
                    print(f"  → Translation: {_c('OK', GREEN)} ({t_elapsed:.1f}s, {len(translated)} chars)")
                    print(f"  {DIM}── Translated ──{NC}")
                    print(indent(_truncate(translated, 500), "  │ "))
                else:
                    print(f"  → Translation: {_c('empty result', YELLOW)}")
        except Exception as e:
            if debug:
                print(f"  → Translation: {_c(f'FAILED: {e}', RED)}")

    # ---- 保存结果 ----
    processing_result["processing_method"] = "ai" if processing_result.get("success") else "failed"
    await service._save_result(article, processing_result, session)

    if debug:
        print(f"\n  {GREEN}→ Result saved to DB{NC}")

    return {**processing_result, "article_id": article_id}


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

async def run(args: argparse.Namespace) -> None:
    from core.database import get_session_factory, close_db
    from common.feature_config import feature_config
    from apps.ai_processor.service import AIProcessorService
    from sqlalchemy import select
    from apps.crawler.models.article import Article

    debug = args.debug
    limit = args.limit if not debug or args.limit != 50 else 3  # debug 默认 3 篇

    # 预热
    await feature_config.async_reload()
    feature_config.freeze()

    service = AIProcessorService()
    warmup_ok = await service.warmup()
    if not warmup_ok:
        print(_c("Warning: model warmup did not complete", YELLOW))

    session_factory = get_session_factory()

    try:
        # ---- 确定要处理的文章 ID ----
        if args.ids:
            article_ids = args.ids
        else:
            async with session_factory() as session:
                query = select(Article.id)
                if args.unprocessed:
                    query = query.where(Article.ai_processed_at.is_(None))
                else:
                    # 默认：选取已处理过的文章（刷库场景）
                    query = query.where(Article.ai_processed_at.isnot(None))

                query = query.where(Article.is_archived.is_(False))
                query = query.where(Article.source_type != "aigc")

                if args.source_type:
                    query = query.where(Article.source_type == args.source_type)

                query = query.order_by(Article.crawl_time.desc()).limit(limit)
                result = await session.execute(query)
                article_ids = [row[0] for row in result.all()]

        if not article_ids:
            print(_c("No articles found matching criteria.", YELLOW))
            return

        total = len(article_ids)
        print(f"\n{BOLD}Reprocessing {total} article(s){NC}" +
              (f" {DIM}(debug mode){NC}" if debug else ""))
        if not debug:
            print(f"Article IDs: {article_ids[:20]}{'...' if total > 20 else ''}")

        # ---- 逐篇处理 ----
        stats = {"processed": 0, "cached": 0, "rule": 0, "failed": 0}
        t_start = time.time()

        for i, aid in enumerate(article_ids, 1):
            if not debug:
                print(f"  [{i}/{total}] Article {aid} ...", end=" ", flush=True)

            try:
                async with session_factory() as session:
                    result = await debug_process_article(aid, service, session, debug=debug)
                    await session.commit()

                method = result.get("processing_method", "")
                success = result.get("success", False)

                if method == "cached":
                    stats["cached"] += 1
                    tag = _c("cached", DIM)
                elif method == "rule":
                    stats["rule"] += 1
                    tag = _c("rule", YELLOW)
                elif success:
                    stats["processed"] += 1
                    tag = _c("ok", GREEN)
                else:
                    stats["failed"] += 1
                    tag = _c("fail", RED)

                if not debug:
                    score = result.get("importance_score", "?")
                    cat = result.get("category", "?")
                    print(f"[{tag}] score={score} cat={cat}")

            except Exception as e:
                stats["failed"] += 1
                if debug:
                    print(f"\n  {RED}Exception: {e}{NC}")
                    import traceback
                    traceback.print_exc()
                else:
                    print(f"[{_c('error', RED)}] {e}")

        # ---- 汇总 ----
        t_total = time.time() - t_start
        _print_section("Summary")
        _print_kv("Total", str(total))
        _print_kv("AI processed", str(stats["processed"]))
        _print_kv("Rule classified", str(stats["rule"]))
        _print_kv("Failed", str(stats["failed"]))
        _print_kv("Elapsed", f"{t_total:.1f}s")
        if stats["processed"] > 0:
            _print_kv("Avg per article", f"{t_total / stats['processed']:.1f}s")
        print()

    finally:
        feature_config.unfreeze()
        await service.close()
        await close_db()


def main():
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

    args = parser.parse_args()

    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        print(f"\n{YELLOW}Interrupted{NC}")
        sys.exit(130)


if __name__ == "__main__":
    main()
