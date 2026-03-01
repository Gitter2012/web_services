# =============================================================================
# 模块: apps/crawler/runner.py
# 功能: 统一爬取运行器，提供单源和多源爬取的统一入口
# 架构角色: 爬虫子系统的门面（Facade），封装爬取执行的复杂性
# 设计理念:
#   1. 门面模式（Facade Pattern）简化爬取操作
#   2. 支持单源爬取、多源爬取、全量爬取
#   3. 统一的结果汇总和错误处理
#   4. 支持模拟运行（dry-run）模式
# =============================================================================

"""Unified crawler runner for ResearchPulse v2.

This module provides a high-level interface for running crawlers,
supporting single source, multiple sources, and full crawl operations.

Usage:
    # Run a single source
    runner = CrawlerRunner()
    result = await runner.run_source("arxiv", category="cs.AI")

    # Run all active sources
    summary = await runner.run_all()

    # Run with dry-run mode
    result = await runner.run_source("arxiv", category="cs.AI", dry_run=True)
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.crawler.factory import CrawlerFactory
from apps.crawler.registry import CrawlerRegistry
from core.database import get_session_factory
from settings import settings

logger = logging.getLogger(__name__)


@dataclass
class CrawlResult:
    """Result of a crawl operation.

    单次爬取操作的结果封装。
    """
    source_type: str
    source_id: str
    fetched_count: int = 0
    saved_count: int = 0
    duration_seconds: float = 0.0
    status: str = "pending"
    error: Optional[str] = None
    timestamp: str = ""
    saved_ids: List[int] = field(default_factory=list)  # 保存的文章 ID 列表

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "source_type": self.source_type,
            "source_id": self.source_id,
            "fetched_count": self.fetched_count,
            "saved_count": self.saved_count,
            "duration_seconds": self.duration_seconds,
            "status": self.status,
            "error": self.error,
            "timestamp": self.timestamp,
        }


@dataclass
class CrawlSummary:
    """Summary of multiple crawl operations.

    多次爬取操作的汇总结果。
    """
    status: str = "pending"
    duration_seconds: float = 0.0
    total_articles: int = 0
    results: Dict[str, List[CrawlResult]] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    timestamp: str = ""
    saved_ids: List[int] = field(default_factory=list)  # 所有保存的文章 ID 列表

    def __post_init__(self):
        # 初始化各源类型的结果列表
        if not self.results:
            self.results = {
                "arxiv": [],
                "rss": [],
                "weibo": [],
                "hackernews": [],
                "reddit": [],
                "twitter": [],
            }

    def add_result(self, result: CrawlResult) -> None:
        """Add a crawl result to the summary."""
        source_type = result.source_type
        if source_type not in self.results:
            self.results[source_type] = []
        self.results[source_type].append(result)
        self.total_articles += result.saved_count
        # 收集保存的文章 ID
        if result.saved_ids:
            self.saved_ids.extend(result.saved_ids)

    def add_error(self, error: str) -> None:
        """Add an error to the summary."""
        self.errors.append(error)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "status": self.status,
            "duration_seconds": self.duration_seconds,
            "total_articles": self.total_articles,
            "counts": {
                source_type: len(results)
                for source_type, results in self.results.items()
                if results
            },
            "error_count": len(self.errors),
            "timestamp": self.timestamp,
        }


class CrawlerRunner:
    """Unified crawler runner.

    统一爬取运行器，提供多种爬取模式的入口。

    Features:
        - 单源爬取：run_source()
        - 批量爬取：run_sources()
        - 全量爬取：run_all()
        - 模拟运行：dry_run 模式
        - 详细输出：verbose 模式
    """

    # 各源类型之间的延迟时间（秒）
    SOURCE_DELAYS = {
        "arxiv": 2.0,
        "rss": 1.0,
        "weibo": 5.0,
        "hackernews": 2.0,
        "reddit": 2.0,
        "twitter": 2.0,
    }

    def __init__(
        self,
        dry_run: bool = False,
        verbose: bool = False,
        delays: Optional[Dict[str, float]] = None,
    ):
        """Initialize the runner.

        Args:
            dry_run: If True, don't write to database
            verbose: If True, show verbose output
            delays: Custom delays between sources
        """
        self.dry_run = dry_run
        self.verbose = verbose
        self.delays = {**self.SOURCE_DELAYS, **(delays or {})}

        if verbose:
            logging.getLogger("apps.crawler").setLevel(logging.DEBUG)

    def _print(self, msg: str, level: str = "info") -> None:
        """Print message with color."""
        colors = {
            "info": "\033[0;36m",
            "success": "\033[0;32m",
            "warning": "\033[1;33m",
            "error": "\033[0;31m",
        }
        reset = "\033[0m"
        color = colors.get(level, "")
        print(f"{color}{msg}{reset}")

    async def run_source(
        self,
        source_type: str,
        dry_run: Optional[bool] = None,
        **kwargs,
    ) -> CrawlResult:
        """Run a single crawler by source type.

        运行单个数据源的爬虫。

        Args:
            source_type: Source type identifier
            dry_run: Override instance dry_run setting
            **kwargs: Arguments passed to the crawler constructor

        Returns:
            CrawlResult with crawl details
        """
        use_dry_run = dry_run if dry_run is not None else self.dry_run

        if self.verbose:
            self._print(f"Creating crawler for {source_type}...", "info")

        start_time = datetime.now(timezone.utc)

        try:
            # 创建爬虫实例
            crawler = CrawlerFactory.create_sync(source_type, **kwargs)

            if use_dry_run:
                # 模拟运行模式：只获取和解析，不保存
                raw_data = await crawler.fetch()
                articles = await crawler.parse(raw_data)
                result = CrawlResult(
                    source_type=source_type,
                    source_id=getattr(crawler, "source_id", "unknown"),
                    fetched_count=len(articles),
                    saved_count=0,
                    status="success",
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
                if self.verbose:
                    self._print(
                        f"  [DRY-RUN] Would fetch {len(articles)} articles",
                        "warning"
                    )
            else:
                # 正常运行模式
                run_result = await crawler.run()
                result = CrawlResult(
                    source_type=source_type,
                    source_id=run_result.get("source_id", "unknown"),
                    fetched_count=run_result.get("fetched_count", 0),
                    saved_count=run_result.get("saved_count", 0),
                    status=run_result.get("status", "error"),
                    error=run_result.get("error"),
                    timestamp=run_result.get("timestamp", ""),
                )

        except Exception as e:
            result = CrawlResult(
                source_type=source_type,
                source_id=kwargs.get("category", kwargs.get("feed_id", "unknown")),
                status="error",
                error=str(e),
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
            logger.exception(f"Crawl failed for {source_type}: {e}")

        result.duration_seconds = (datetime.now(timezone.utc) - start_time).total_seconds()
        return result

    async def run_sources(
        self,
        source_type: str,
        sources: Optional[List[str]] = None,
        dry_run: Optional[bool] = None,
    ) -> CrawlSummary:
        """Run crawlers for multiple sources of the same type.

        运行同一类型的多个数据源爬虫。

        Args:
            source_type: Source type identifier
            sources: Optional list of specific source IDs (e.g., category codes)
            dry_run: Override instance dry_run setting

        Returns:
            CrawlSummary with aggregated results
        """
        summary = CrawlSummary()
        start_time = datetime.now(timezone.utc)

        if self.verbose:
            self._print(f"Starting crawl for {source_type}...", "info")

        # 获取该源类型的模型类
        model_class = CrawlerRegistry.get_model_class(source_type)

        if not model_class:
            # 如果没有模型类，直接使用 kwargs 创建
            if sources:
                for source_id in sources:
                    kwargs = self._build_kwargs(source_type, source_id)
                    result = await self.run_source(source_type, dry_run=dry_run, **kwargs)
                    summary.add_result(result)
            return summary

        # 从数据库查询激活的源
        session_factory = get_session_factory()
        async with session_factory() as session:
            if sources:
                # 查询指定的源
                # 需要根据模型类确定查询字段
                query_field = self._get_query_field(model_class)
                result = await session.execute(
                    select(model_class).where(query_field.in_(sources))
                )
            else:
                # 查询所有激活的源
                result = await session.execute(
                    select(model_class).where(model_class.is_active == True)
                )

            db_sources = result.scalars().all()

            if self.verbose:
                self._print(f"Found {len(db_sources)} active sources", "info")

            for source in db_sources:
                try:
                    crawler = await CrawlerFactory.create_from_source(source_type, source)
                    result = await self._run_crawler(crawler, dry_run=dry_run)
                    summary.add_result(result)

                    if self.verbose:
                        self._print(
                            f"  {getattr(source, 'code', getattr(source, 'id', 'unknown'))}: "
                            f"fetched={result.fetched_count}, saved={result.saved_count}",
                            "success"
                        )

                    # 源之间的延迟
                    delay = self.delays.get(source_type, 2.0)
                    await asyncio.sleep(delay)

                except Exception as e:
                    error_msg = f"{source_type}:{getattr(source, 'id', 'unknown')}: {str(e)}"
                    summary.add_error(error_msg)
                    logger.error(f"Crawl failed: {error_msg}")

            if dry_run is None or not dry_run:
                await session.commit()

        summary.duration_seconds = (datetime.now(timezone.utc) - start_time).total_seconds()
        summary.status = "completed" if not summary.errors else "completed_with_errors"
        summary.timestamp = datetime.now(timezone.utc).isoformat()

        return summary

    async def run_all(
        self,
        source_types: Optional[List[str]] = None,
        dry_run: Optional[bool] = None,
    ) -> CrawlSummary:
        """Run all active crawlers.

        运行所有激活的爬虫。

        Args:
            source_types: Optional list of source types to limit crawling
            dry_run: Override instance dry_run setting

        Returns:
            CrawlSummary with aggregated results
        """
        summary = CrawlSummary()
        start_time = datetime.now(timezone.utc)

        types_to_run = source_types or CrawlerRegistry.list_sources(enabled_only=True)

        if self.verbose:
            self._print(f"Starting full crawl for {len(types_to_run)} source types", "info")

        session_factory = get_session_factory()
        own_session = True
        session = None

        try:
            async with session_factory() as session:
                async for crawler, source in CrawlerFactory.create_for_active_sources(
                    source_types=types_to_run, session=session
                ):
                    source_type = crawler.source_type
                    try:
                        result = await self._run_crawler(crawler, dry_run=dry_run)
                        summary.add_result(result)

                        if self.verbose:
                            self._print(
                                f"  {source_type}:{crawler.source_id}: "
                                f"fetched={result.fetched_count}, saved={result.saved_count}",
                                "success"
                            )

                        # 更新源的 last_fetched_at
                        if hasattr(source, "last_fetched_at") and result.status == "success":
                            source.last_fetched_at = datetime.now(timezone.utc)

                        # 源之间的延迟
                        delay = self.delays.get(source_type, 2.0)
                        await asyncio.sleep(delay)

                    except Exception as e:
                        error_msg = f"{source_type}:{crawler.source_id}: {str(e)}"
                        summary.add_error(error_msg)
                        self._print(f"  Error: {error_msg}", "error")

                if dry_run is None or not dry_run:
                    await session.commit()

        except Exception as e:
            summary.add_error(f"Session error: {str(e)}")
            logger.exception(f"Session error: {e}")

        summary.duration_seconds = (datetime.now(timezone.utc) - start_time).total_seconds()
        summary.status = "completed" if not summary.errors else "completed_with_errors"
        summary.timestamp = datetime.now(timezone.utc).isoformat()

        # 抓取完成后，检查是否需要翻译
        if summary.total_articles > 0 and summary.saved_ids:
            try:
                from apps.crawler.translate_hook import translate_after_crawl
                translate_result = await translate_after_crawl(summary.saved_ids)
                if not translate_result.get("skipped"):
                    logger.info(f"Post-crawl translation: {translate_result}")
            except Exception as e:
                logger.warning(f"Post-crawl translation failed: {e}")

        return summary

    async def _run_crawler(
        self,
        crawler: Any,
        dry_run: Optional[bool] = None,
    ) -> CrawlResult:
        """Run a crawler instance and return result."""
        use_dry_run = dry_run if dry_run is not None else self.dry_run

        start_time = datetime.now(timezone.utc)

        try:
            if use_dry_run:
                raw_data = await crawler.fetch()
                articles = await crawler.parse(raw_data)
                return CrawlResult(
                    source_type=crawler.source_type,
                    source_id=crawler.source_id,
                    fetched_count=len(articles),
                    saved_count=0,
                    status="success",
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
            else:
                run_result = await crawler.run()
                return CrawlResult(
                    source_type=crawler.source_type,
                    source_id=run_result.get("source_id", crawler.source_id),
                    fetched_count=run_result.get("fetched_count", 0),
                    saved_count=run_result.get("saved_count", 0),
                    duration_seconds=run_result.get("duration_seconds", 0),
                    status=run_result.get("status", "error"),
                    error=run_result.get("error"),
                    timestamp=run_result.get("timestamp", ""),
                    saved_ids=run_result.get("saved_ids", []),
                )

        except Exception as e:
            return CrawlResult(
                source_type=crawler.source_type,
                source_id=crawler.source_id,
                status="error",
                error=str(e),
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

    def _build_kwargs(self, source_type: str, source_id: str) -> Dict[str, Any]:
        """Build kwargs for crawler constructor based on source type."""
        # 各源类型需要的参数映射
        kwargs_map = {
            "arxiv": {
                "category": source_id,
                "max_results": settings.arxiv_max_results,
                "delay_base": settings.arxiv_delay_base,
                "sort_modes": settings.arxiv_sort_modes_list,
                "mark_paper_type": settings.arxiv_mark_paper_type,
                "rss_format": settings.arxiv_rss_format,
            },
            "rss": {
                "feed_id": source_id,
            },
            "weibo": {
                "source_id": source_id,
                "timeout": settings.weibo_timeout,
                "cookie": settings.weibo_cookie,
                "delay_base": settings.weibo_delay_base,
                "delay_jitter": settings.weibo_delay_jitter,
            },
            "hackernews": {
                "feed_type": source_id,
                "timeout": 30.0,
                "fetch_external_content": True,
            },
            "reddit": {
                "source_type": "subreddit",
                "source_name": source_id,
                "timeout": 30.0,
                "fetch_external_content": True,
            },
            "twitter": {
                "username": source_id,
                "max_results": 20,
                "timeout": 15.0,
            },
        }
        return kwargs_map.get(source_type, {})

    def _get_query_field(self, model_class: Any) -> Any:
        """Get the field to query for source IDs."""
        # 根据模型类确定查询字段
        if hasattr(model_class, "code"):
            return model_class.code
        elif hasattr(model_class, "feed_type"):
            return model_class.feed_type
        elif hasattr(model_class, "source_name"):
            return model_class.source_name
        elif hasattr(model_class, "username"):
            return model_class.username
        elif hasattr(model_class, "board_type"):
            return model_class.board_type
        return model_class.id

    def print_summary(self, summary: CrawlSummary) -> None:
        """Print a formatted summary of crawl results."""
        print("\n" + "=" * 50)
        self._print("爬取摘要", "info")
        print("=" * 50)

        # 同时构建日志文本
        log_lines = ["爬取摘要"]

        for source_type, results in summary.results.items():
            if results:
                total_fetched = sum(r.fetched_count for r in results)
                total_saved = sum(r.saved_count for r in results)
                line = f"  {source_type:12} {len(results)} 个源, 获取 {total_fetched}, 保存 {total_saved}"
                print(line)
                log_lines.append(line.strip())

        print("-" * 50)

        if summary.errors:
            self._print(f"  错误:        {len(summary.errors)} 个", "warning")
            log_lines.append(f"错误: {len(summary.errors)} 个")
            for err in summary.errors[:5]:
                print(f"    - {err}")
                log_lines.append(f"  - {err}")
            if len(summary.errors) > 5:
                print(f"    ... 还有 {len(summary.errors) - 5} 个错误")
                log_lines.append(f"  ... 还有 {len(summary.errors) - 5} 个错误")

        self._print(f"  总计保存:    {summary.total_articles} 篇文章", "success")
        print(f"  耗时:        {summary.duration_seconds:.2f} 秒")
        log_lines.append(f"总计保存: {summary.total_articles} 篇文章")
        log_lines.append(f"耗时: {summary.duration_seconds:.2f} 秒")

        if self.dry_run:
            self._print("  [模拟运行] 数据未写入数据库", "warning")
            log_lines.append("[模拟运行] 数据未写入数据库")

        print("=" * 50)

        # 输出到日志
        logger.info("爬取摘要 | " + " | ".join(log_lines[1:]))
