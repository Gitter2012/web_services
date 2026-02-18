#!/usr/bin/env python3
"""Manual crawl runner for ResearchPulse v2.

This script provides a CLI interface for manually triggering crawl jobs
for specific data sources or all sources at once.

Usage:
    python scripts/_crawl_runner.py all
    python scripts/_crawl_runner.py arxiv cs.AI cs.CL
    python scripts/_crawl_runner.py rss --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from apps.crawler import CrawlerRunner, CrawlerRegistry

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="ResearchPulse v2 手动爬取工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # 获取可用的源类型
    available_sources = CrawlerRegistry.list_sources(enabled_only=True)
    if not available_sources:
        # 如果注册表为空，使用默认列表
        available_sources = ["all", "arxiv", "rss", "weibo", "hackernews", "reddit", "twitter"]

    parser.add_argument(
        "source",
        choices=available_sources + ["all"],
        help="要爬取的数据源"
    )
    parser.add_argument(
        "extra",
        nargs="*",
        help="额外参数 (如 arxiv 分类代码)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="模拟运行，不写入数据库"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="显示详细输出"
    )

    args = parser.parse_args()

    # 创建运行器
    runner = CrawlerRunner(dry_run=args.dry_run, verbose=args.verbose)

    start_time = datetime.now(timezone.utc)

    async def run():
        """Run the crawl."""
        if args.source == "all":
            # 运行所有激活的源
            summary = await runner.run_all()
        else:
            # 运行指定类型的源
            extra_args = args.extra if args.extra else None
            summary = await runner.run_sources(
                source_type=args.source,
                sources=extra_args,
                dry_run=args.dry_run,
            )
        return summary

    try:
        summary = asyncio.run(run())
    except Exception as e:
        runner._print(f"爬取失败: {e}", "error")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)

    end_time = datetime.now(timezone.utc)
    duration = (end_time - start_time).total_seconds()

    # 打印摘要
    runner.print_summary(summary)
    print(f"\n总耗时: {duration:.2f} 秒")

    # 返回退出码
    sys.exit(0 if not summary.errors else 1)


if __name__ == "__main__":
    main()
