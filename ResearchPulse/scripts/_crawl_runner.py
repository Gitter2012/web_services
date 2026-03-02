#!/usr/bin/env python3
"""手动爬虫运行工具。

本脚本提供命令行接口，用于手动触发爬虫任务。
支持运行所有数据源或指定类型的爬虫。

支持的数据源：
    - arxiv:     arXiv 论文爬虫，可指定分类代码
    - rss:       RSS 订阅源爬虫
    - weibo:     微博热搜爬虫
    - hackernews: Hacker News 爬虫
    - reddit:    Reddit 热门帖子爬虫
    - twitter:   Twitter/X 爬虫

用法示例：
    # 运行所有激活的爬虫源
    python scripts/_crawl_runner.py all

    # 爬取指定 arXiv 分类
    python scripts/_crawl_runner.py arxiv cs.AI cs.CL

    # 爬取 RSS 源
    python scripts/_crawl_runner.py rss

    # 模拟运行（不写入数据库）
    python scripts/_crawl_runner.py all --dry-run

    # 显示详细输出
    python scripts/_crawl_runner.py arxiv cs.AI --verbose
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

# 将项目根目录添加到 Python 路径，以便导入项目模块
sys.path.insert(0, str(Path(__file__).parent.parent))

from apps.crawler import CrawlerRunner, CrawlerRegistry
from core.database import close_db

# ---------------------------------------------------------------------------
# 日志配置
# ---------------------------------------------------------------------------
# 配置日志格式：时间戳 + 日志级别 + 消息
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def main():
    """CLI 主入口函数。

    解析命令行参数并执行对应的爬虫任务。

    命令行参数：
        source: 要爬取的数据源类型（all/arxiv/rss/weibo/hackernews/reddit/twitter）
        extra: 额外参数，如 arxiv 分类代码
        --dry-run: 模拟运行，不写入数据库
        --verbose, -v: 显示详细输出

    返回：
        int: 退出码，0 表示成功，1 表示有错误
    """
    # 创建参数解析器
    parser = argparse.ArgumentParser(
        description="ResearchPulse v2 手动爬取工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # 获取可用的源类型列表
    available_sources = CrawlerRegistry.list_sources(enabled_only=True)
    if not available_sources:
        # 如果注册表为空（可能导入失败），使用默认列表
        available_sources = ["all", "arxiv", "rss", "weibo", "hackernews", "reddit", "twitter"]

    # 必选参数：数据源类型
    parser.add_argument(
        "source",
        choices=available_sources + ["all"],
        help="要爬取的数据源"
    )
    # 可选参数：额外参数（如 arxiv 分类代码）
    parser.add_argument(
        "extra",
        nargs="*",
        help="额外参数 (如 arxiv 分类代码)"
    )
    # 选项：模拟运行
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="模拟运行，不写入数据库"
    )
    # 选项：详细输出
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="显示详细输出"
    )

    args = parser.parse_args()

    # 创建爬虫运行器实例
    runner = CrawlerRunner(dry_run=args.dry_run, verbose=args.verbose)

    # 记录开始时间
    start_time = datetime.now(timezone.utc)

    async def run():
        """异步执行爬虫任务。

        根据参数运行所有源或指定类型的爬虫。

        返回：
            CrawlerSummary: 爬取结果摘要
        """
        try:
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
        finally:
            # 关闭数据库连接，避免事件循环关闭后连接清理报错
            await close_db()

    try:
        # 运行异步爬虫任务
        summary = asyncio.run(run())
    except Exception as e:
        logger.error(f"爬取失败: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)

    # 计算总耗时
    end_time = datetime.now(timezone.utc)
    duration = (end_time - start_time).total_seconds()

    # 打印摘要
    runner.print_summary(summary)
    logger.info(f"总耗时: {duration:.2f} 秒")

    # 返回退出码：有错误则返回 1，否则返回 0
    sys.exit(0 if not summary.errors else 1)


if __name__ == "__main__":
    main()
