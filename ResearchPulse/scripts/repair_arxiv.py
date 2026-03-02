#!/usr/bin/env python3
"""arXiv 文章数据修复脚本。

本脚本用于修复数据库中缺失作者或摘要字段的 arXiv 文章。
通过调用 arXiv Atom API 获取完整的元数据并回填数据库。

这是一个维护/一次性脚本，不属于常规爬虫流程。
当历史爬取数据缺失时，可运行此脚本进行修复。

功能：
    1. 扫描数据库中缺失 author 或 summary 字段的 arXiv 文章
    2. 批量调用 arXiv Atom API 获取完整元数据
    3. 更新数据库中的缺失字段
    4. 验证修复结果

用法示例：
    # 执行修复
    python3 scripts/repair_arxiv.py

    # 仅检查，不修改（查看有多少文章需要修复）
    python3 scripts/repair_arxiv.py --dry-run

    # 详细输出
    python3 scripts/repair_arxiv.py --verbose

    # 自定义批次大小（每批请求的 arXiv ID 数量）
    python3 scripts/repair_arxiv.py --batch-size 50

注意：
    - arXiv API 有速率限制，脚本默认每批请求间隔 3 秒
    - 建议在非高峰时段运行大规模修复

依赖：
    - httpx: 用于异步 HTTP 请求
    - 数据库连接配置（通过环境变量或 .env 文件）
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import re
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List

# 将项目根目录添加到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, or_, func

from apps.crawler.models.article import Article

# ---------------------------------------------------------------------------
# 常量定义
# ---------------------------------------------------------------------------

# arXiv Atom API 地址
# 参考：https://info.arxiv.org/help/api/user-manual.html
ARXIV_API_URL = "https://export.arxiv.org/api/query"

# 默认批次大小
# arXiv API 建议每次请求不超过 50 个 ID
DEFAULT_BATCH_SIZE = 20

# API 请求间隔（秒）
# 避免触发 arXiv API 速率限制
RATE_LIMIT_DELAY = 3.0

# XML 命名空间
ATOM_NS = "{http://www.w3.org/2005/Atom}"
ARXIV_NS = "{http://arxiv.org/schemas/atom}"

# 模块日志器
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# arXiv API 辅助函数
# ---------------------------------------------------------------------------

def _parse_atom_entry(entry: ET.Element) -> Dict[str, str]:
    """解析 arXiv Atom API 响应中的单个 <entry> 元素。

    从 Atom XML 条目中提取文章的元数据信息。

    参数：
        entry: XML Element 对象，代表一个 <entry> 节点。

    返回：
        Dict[str, str]: 包含以下字段的字典：
            - arxiv_id: arXiv 文章 ID（如 "2301.12345"）
            - title: 文章标题
            - summary: 文章摘要
            - content: 文章内容（arXiv 中等于摘要）
            - author: 作者列表（逗号分隔）
            - category: 主分类代码
    """
    # 从 <id> 元素提取 arxiv_id
    # 格式：http://arxiv.org/abs/2301.12345v1
    entry_id = entry.findtext(f"{ATOM_NS}id", "")
    match = re.search(r"arxiv\.org/abs/([\w.]+?)(?:v\d+)?$", entry_id)
    arxiv_id = match.group(1) if match else ""

    # 提取标题和摘要，清理多余空白
    title = re.sub(r"\s+", " ", entry.findtext(f"{ATOM_NS}title", "").strip())
    summary = re.sub(r"\s+", " ", entry.findtext(f"{ATOM_NS}summary", "").strip())

    # 提取作者列表
    authors = []
    for author_el in entry.findall(f"{ATOM_NS}author"):
        name = author_el.findtext(f"{ATOM_NS}name", "").strip()
        if name:
            authors.append(name)
    author_str = ", ".join(authors)

    # 提取主分类
    primary_cat_el = entry.find(f"{ARXIV_NS}primary_category")
    category = primary_cat_el.get("term", "") if primary_cat_el is not None else ""

    return {
        "arxiv_id": arxiv_id,
        "title": title,
        "summary": summary,
        "content": summary,   # arXiv content = abstract
        "author": author_str,
        "category": category,
    }


async def _fetch_batch(arxiv_ids: List[str]) -> List[Dict[str, str]]:
    """批量获取 arXiv 文章元数据。

    通过 arXiv Atom API 一次性获取多篇文章的元数据。

    参数：
        arxiv_ids: arXiv 文章 ID 列表。

    返回：
        List[Dict[str, str]]: 解析后的元数据列表，每个元素是一篇文章的信息。

    异常：
        httpx.HTTPStatusError: HTTP 请求失败时抛出。
    """
    import httpx

    # 构建 API 请求参数
    params = {
        "id_list": ",".join(arxiv_ids),
        "max_results": str(len(arxiv_ids)),
    }

    # 发送异步 HTTP 请求
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(ARXIV_API_URL, params=params)
        resp.raise_for_status()

    # 解析 XML 响应
    root = ET.fromstring(resp.text)
    results = []
    for entry in root.findall(f"{ATOM_NS}entry"):
        parsed = _parse_atom_entry(entry)
        if parsed["arxiv_id"]:
            results.append(parsed)
    return results


# ---------------------------------------------------------------------------
# 核心修复逻辑
# ---------------------------------------------------------------------------

async def find_incomplete_articles() -> List[Article]:
    """查询数据库中缺失作者或摘要的 arXiv 文章。

    返回：
        List[Article]: 需要修复的文章对象列表。
    """
    from core.database import get_session_factory

    factory = get_session_factory()
    async with factory() as session:
        # 查询条件：source_type 为 arxiv 且 author 或 summary 为空
        stmt = select(Article).where(
            Article.source_type == "arxiv",
            or_(
                Article.author == "",
                Article.author.is_(None),
                Article.summary == "",
                Article.summary.is_(None),
            ),
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def repair_articles(
    *,
    dry_run: bool = False,
    batch_size: int = DEFAULT_BATCH_SIZE,
    verbose: bool = False,
) -> Dict[str, int]:
    """执行文章修复流程。

    主要步骤：
        1. 查找需要修复的文章
        2. 按 arxiv_id 分组（一个 ID 可能对应多篇数据库记录）
        3. 批量调用 API 获取元数据
        4. 更新数据库记录
        5. 验证修复结果

    参数：
        dry_run: 仅检查不修改，默认 False。
        batch_size: 每批请求的 arXiv ID 数量，默认 20。
        verbose: 是否显示详细输出，默认 False。

    返回：
        Dict[str, int]: 包含以下统计字段：
            - total: 需要修复的文章总数
            - fetched: 成功获取元数据的文章数
            - updated: 成功更新的记录数
            - remaining: 仍缺失数据的文章数
    """
    from core.database import get_session_factory

    # Step 1: 查找需要修复的文章
    articles = await find_incomplete_articles()
    logger.info(f"Found {len(articles)} articles needing repair")

    if not articles:
        return {"total": 0, "fetched": 0, "updated": 0, "remaining": 0}

    # Step 2: 按 arxiv_id 分组
    # 一个 arxiv_id 可能对应多篇数据库记录（如不同版本）
    id_to_articles: Dict[str, List[Article]] = {}
    for art in articles:
        if art.arxiv_id:
            id_to_articles.setdefault(art.arxiv_id, []).append(art)

    unique_ids = list(id_to_articles.keys())
    logger.info(f"Unique arXiv IDs to fetch: {len(unique_ids)}")

    # dry-run 模式：仅显示统计，不执行修复
    if dry_run:
        logger.info("[dry-run] Skipping API fetch and DB update")
        if verbose:
            for aid in unique_ids[:20]:
                logger.info(f"  Would repair: {aid}")
            if len(unique_ids) > 20:
                logger.info(f"  ... and {len(unique_ids) - 20} more")
        return {"total": len(articles), "fetched": 0, "updated": 0, "remaining": len(articles)}

    # Step 3: 批量获取元数据
    fetched: Dict[str, Dict[str, str]] = {}
    for i in range(0, len(unique_ids), batch_size):
        batch = unique_ids[i : i + batch_size]
        batch_num = i // batch_size + 1
        total_batches = (len(unique_ids) + batch_size - 1) // batch_size
        logger.info(f"  Fetching batch {batch_num}/{total_batches} ({len(batch)} IDs)...")

        try:
            results = await _fetch_batch(batch)
            for r in results:
                fetched[r["arxiv_id"]] = r
        except Exception as e:
            logger.warning(f"  Batch {batch_num} failed: {e}")

        # 速率限制：批次间延迟
        if i + batch_size < len(unique_ids):
            await asyncio.sleep(RATE_LIMIT_DELAY)

    logger.info(f"Fetched metadata for {len(fetched)} papers")

    # Step 4: 更新数据库记录
    updated = 0
    factory = get_session_factory()
    async with factory() as session:
        # 重新查询以获取附加到当前 session 的对象
        stmt = select(Article).where(
            Article.source_type == "arxiv",
            or_(
                Article.author == "",
                Article.author.is_(None),
                Article.summary == "",
                Article.summary.is_(None),
            ),
        )
        result = await session.execute(stmt)
        db_articles = list(result.scalars().all())

        for art in db_articles:
            meta = fetched.get(art.arxiv_id)
            if not meta:
                continue

            # 逐字段更新（仅更新缺失的字段）
            changed = False
            if not art.author and meta["author"]:
                art.author = meta["author"]
                changed = True
            if not art.summary and meta["summary"]:
                art.summary = meta["summary"]
                changed = True
            if not art.content and meta["content"]:
                art.content = meta["content"]
                changed = True
            if not art.category and meta["category"]:
                art.category = meta["category"]
                changed = True

            if changed:
                updated += 1
                if verbose:
                    logger.info(f"  Updated: {art.arxiv_id} - {meta['author'][:40]}...")

        await session.commit()

    logger.info(f"Updated {updated} article records")

    # Step 5: 验证修复结果
    remaining_articles = await find_incomplete_articles()
    remaining = len(remaining_articles)
    logger.info(f"Remaining articles with missing data: {remaining}")

    return {
        "total": len(articles),
        "fetched": len(fetched),
        "updated": updated,
        "remaining": remaining,
    }


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------

def main():
    """命令行入口函数。

    解析命令行参数并执行修复流程。
    """
    parser = argparse.ArgumentParser(
        description="修复 arXiv 文章缺失的作者和摘要数据",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python3 scripts/repair_arxiv.py                  # 执行修复
  python3 scripts/repair_arxiv.py --dry-run        # 仅检查，不修改
  python3 scripts/repair_arxiv.py --batch-size 50  # 自定义批次大小
""",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅检查缺失数据，不执行修复",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"每批请求的 arXiv ID 数量 (默认: {DEFAULT_BATCH_SIZE})",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="显示详细输出",
    )
    args = parser.parse_args()

    # 配置日志级别
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 执行修复
    try:
        stats = asyncio.run(repair_articles(
            dry_run=args.dry_run,
            batch_size=args.batch_size,
            verbose=args.verbose,
        ))
    except Exception as e:
        logger.exception(f"Repair failed: {e}")
        sys.exit(1)

    # 打印统计摘要
    logger.info("")
    logger.info(f"总计缺失: {stats['total']} 篇")
    logger.info(f"API 获取: {stats['fetched']} 篇")
    logger.info(f"已修复:   {stats['updated']} 篇")
    logger.info(f"仍缺失:   {stats['remaining']} 篇")

    # 返回退出码：仍有缺失数据则返回 1
    sys.exit(0 if stats["remaining"] == 0 else 1)


if __name__ == "__main__":
    main()
