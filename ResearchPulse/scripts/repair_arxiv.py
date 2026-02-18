#!/usr/bin/env python3
"""ArXiv article repair script for ResearchPulse v2.

Scans the database for arXiv articles with missing author or summary fields,
then fetches full metadata from the arXiv Atom API and backfills the records.

This is a maintenance/one-off script, NOT part of the regular crawl pipeline.
Run it when stale data from past crawls needs to be repaired.

Usage:
    cd /path/to/ResearchPulse
    python3 scripts/repair_arxiv.py
    python3 scripts/repair_arxiv.py --dry-run     # 仅检查，不修改
    python3 scripts/repair_arxiv.py --verbose      # 详细输出
    python3 scripts/repair_arxiv.py --batch-size 50
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

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, or_, func

from apps.crawler.models.article import Article

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ARXIV_API_URL = "https://export.arxiv.org/api/query"
DEFAULT_BATCH_SIZE = 20   # arXiv API recommends <= 50 IDs per request
RATE_LIMIT_DELAY = 3.0    # seconds between API requests

ATOM_NS = "{http://www.w3.org/2005/Atom}"
ARXIV_NS = "{http://arxiv.org/schemas/atom}"

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# arXiv API helpers
# ---------------------------------------------------------------------------

def _parse_atom_entry(entry: ET.Element) -> Dict[str, str]:
    """Parse a single <entry> from the arXiv Atom API response.

    Returns:
        Dict with keys: arxiv_id, title, summary, content, author, category.
    """
    # Extract arxiv_id from <id>: http://arxiv.org/abs/2301.12345v1
    entry_id = entry.findtext(f"{ATOM_NS}id", "")
    match = re.search(r"arxiv\.org/abs/([\w.]+?)(?:v\d+)?$", entry_id)
    arxiv_id = match.group(1) if match else ""

    title = re.sub(r"\s+", " ", entry.findtext(f"{ATOM_NS}title", "").strip())
    summary = re.sub(r"\s+", " ", entry.findtext(f"{ATOM_NS}summary", "").strip())

    # Authors
    authors = []
    for author_el in entry.findall(f"{ATOM_NS}author"):
        name = author_el.findtext(f"{ATOM_NS}name", "").strip()
        if name:
            authors.append(name)
    author_str = ", ".join(authors)

    # Primary category
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
    """Fetch metadata for a batch of arXiv IDs via the Atom API.

    Uses httpx (already a project dependency) for async HTTP.
    """
    import httpx

    params = {
        "id_list": ",".join(arxiv_ids),
        "max_results": str(len(arxiv_ids)),
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(ARXIV_API_URL, params=params)
        resp.raise_for_status()

    root = ET.fromstring(resp.text)
    results = []
    for entry in root.findall(f"{ATOM_NS}entry"):
        parsed = _parse_atom_entry(entry)
        if parsed["arxiv_id"]:
            results.append(parsed)
    return results


# ---------------------------------------------------------------------------
# Core repair logic
# ---------------------------------------------------------------------------

async def find_incomplete_articles() -> List[Article]:
    """Query DB for arXiv articles with empty author or summary."""
    from core.database import get_session_factory

    factory = get_session_factory()
    async with factory() as session:
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
    """Main repair routine.

    Returns:
        Dict with keys: total, fetched, updated, remaining.
    """
    from core.database import get_session_factory

    # Step 1: find articles needing repair
    articles = await find_incomplete_articles()
    logger.info(f"Found {len(articles)} articles needing repair")

    if not articles:
        return {"total": 0, "fetched": 0, "updated": 0, "remaining": 0}

    # Group by arxiv_id (one arxiv_id may map to multiple DB rows)
    id_to_articles: Dict[str, List[Article]] = {}
    for art in articles:
        if art.arxiv_id:
            id_to_articles.setdefault(art.arxiv_id, []).append(art)

    unique_ids = list(id_to_articles.keys())
    logger.info(f"Unique arXiv IDs to fetch: {len(unique_ids)}")

    if dry_run:
        logger.info("[dry-run] Skipping API fetch and DB update")
        if verbose:
            for aid in unique_ids[:20]:
                logger.info(f"  Would repair: {aid}")
            if len(unique_ids) > 20:
                logger.info(f"  ... and {len(unique_ids) - 20} more")
        return {"total": len(articles), "fetched": 0, "updated": 0, "remaining": len(articles)}

    # Step 2: fetch metadata in batches
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

        # Rate limit between batches
        if i + batch_size < len(unique_ids):
            await asyncio.sleep(RATE_LIMIT_DELAY)

    logger.info(f"Fetched metadata for {len(fetched)} papers")

    # Step 3: update DB records
    updated = 0
    factory = get_session_factory()
    async with factory() as session:
        # Re-query inside this session so objects are attached
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

    # Step 4: verify
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
# CLI entry point
# ---------------------------------------------------------------------------

def main():
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

    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Run
    try:
        stats = asyncio.run(repair_articles(
            dry_run=args.dry_run,
            batch_size=args.batch_size,
            verbose=args.verbose,
        ))
    except Exception as e:
        logger.exception(f"Repair failed: {e}")
        sys.exit(1)

    # Summary
    print()
    print(f"总计缺失: {stats['total']} 篇")
    print(f"API 获取: {stats['fetched']} 篇")
    print(f"已修复:   {stats['updated']} 篇")
    print(f"仍缺失:   {stats['remaining']} 篇")

    sys.exit(0 if stats["remaining"] == 0 else 1)


if __name__ == "__main__":
    main()
