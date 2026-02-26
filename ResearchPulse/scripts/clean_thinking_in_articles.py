#!/usr/bin/env python3
"""Clean thinking tags from articles database.

清理文章指定字段中的 thinking 标签内容，保留正式结果。

Usage:
    # 清理所有已处理文章的 content 字段
    python scripts/clean_thinking_in_articles.py

    # 指定字段清理
    python scripts/clean_thinking_in_articles.py --field content

    # 清理多个字段
    python scripts/clean_thinking_in_articles.py --field content --field ai_summary

    # 仅统计不执行
    python scripts/clean_thinking_in_articles.py --stats

    # 指定文章 ID
    python scripts/clean_thinking_in_articles.py --ids 17652 17653
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import warnings
warnings.filterwarnings("ignore", message=".*garbage collector.*")

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# 匹配 thinking 标签 (qwen3 等模型)
THINK_TAG_RE = re.compile(r"<think>[\s\S]*?</think>\s*", re.DOTALL | re.IGNORECASE)

# 可清理的字段列表
CLEANABLE_FIELDS = [
    "content",
    "ai_summary",
    "one_liner",
    "key_points",
    "impact_assessment",
    "actionable_items",
]


def clean_think_tags(text: str) -> str:
    """Remove thinking tags from text."""
    if not text:
        return text
    return THINK_TAG_RE.sub("", text).strip()


def clean_json_field(data) -> str:
    """Clean thinking tags from JSON data."""
    if not data:
        return data
    
    if isinstance(data, str):
        return clean_think_tags(data)
    
    if isinstance(data, list):
        cleaned = []
        for item in data:
            if isinstance(item, dict):
                cleaned_item = {}
                for k, v in item.items():
                    if isinstance(v, str):
                        cleaned_item[k] = clean_think_tags(v)
                    else:
                        cleaned_item[k] = v
                cleaned.append(cleaned_item)
            else:
                cleaned.append(item)
        return cleaned
    
    if isinstance(data, dict):
        cleaned = {}
        for k, v in data.items():
            if isinstance(v, str):
                cleaned[k] = clean_think_tags(v)
            else:
                cleaned[k] = v
        return cleaned
    
    return data


async def run(args: argparse.Namespace) -> None:
    from core.database import get_session_factory, close_db
    from sqlalchemy import select, text
    from apps.crawler.models.article import Article

    session_factory = get_session_factory()
    fields = args.field or ["content"]

    try:
        async with session_factory() as session:
            # 构建查询
            if args.ids:
                # 指定文章 ID
                sql = text(f"""
                    SELECT id, {', '.join(fields)}
                    FROM articles 
                    WHERE id IN :ids
                """)
                result = await session.execute(sql, {"ids": tuple(args.ids)})
            else:
                # 查找包含 thinking 标签的文章
                like_conditions = " OR ".join([f"{f} LIKE '%<think>%'" for f in fields])
                sql = text(f"""
                    SELECT id, {', '.join(fields)}
                    FROM articles 
                    WHERE {like_conditions}
                """)
                result = await session.execute(sql)
            
            rows = result.fetchall()
            
            if not rows:
                logger.info("No articles with thinking tags found.")
                return
            
            logger.info(f"Found {len(rows)} articles with thinking tags.")
            
            if args.stats:
                # 仅统计模式
                for row in rows[:10]:
                    logger.info(f"  Article {row[0]}")
                if len(rows) > 10:
                    logger.info(f"  ... and {len(rows) - 10} more")
                return
            
            # 执行清理
            updated_count = 0
            for row in rows:
                article_id = row[0]
                updates = {}
                
                for i, field in enumerate(fields):
                    value = row[i + 1]
                    if not value:
                        continue
                    
                    if field in ("key_points", "impact_assessment", "actionable_items"):
                        # JSON 字段
                        try:
                            if isinstance(value, str):
                                data = json.loads(value)
                            else:
                                data = value
                            cleaned = clean_json_field(data)
                            if cleaned != data:
                                updates[field] = json.dumps(cleaned, ensure_ascii=False)
                        except (json.JSONDecodeError, TypeError):
                            # 如果不是 JSON，当作字符串处理
                            cleaned = clean_think_tags(str(value))
                            if cleaned != value:
                                updates[field] = cleaned
                    else:
                        # 普通文本字段
                        cleaned = clean_think_tags(str(value))
                        if cleaned != value:
                            updates[field] = cleaned
                
                if updates:
                    # 执行更新
                    set_clause = ", ".join([f"{k} = :{k}" for k in updates.keys()])
                    updates["id"] = article_id
                    update_sql = text(f"UPDATE articles SET {set_clause} WHERE id = :id")
                    await session.execute(update_sql, updates)
                    updated_count += 1
                    logger.info(f"Cleaned article {article_id}: {len(updates)} field(s) updated")
            
            await session.commit()
            logger.info(f"Cleaned {updated_count} articles.")

    finally:
        await close_db()


def main():
    parser = argparse.ArgumentParser(
        description="Clean thinking tags from articles database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                              # Clean content field
  %(prog)s --field content --field ai_summary  # Clean multiple fields
  %(prog)s --stats                      # Show statistics only
  %(prog)s --ids 17652 17653            # Clean specific articles
""",
    )
    parser.add_argument(
        "--field", "-f",
        action="append",
        choices=CLEANABLE_FIELDS,
        help=f"Field(s) to clean (choices: {', '.join(CLEANABLE_FIELDS)}). Can specify multiple times.",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show statistics only, do not execute cleaning",
    )
    parser.add_argument(
        "--ids",
        type=int,
        nargs="+",
        help="Specific article IDs to clean",
    )

    args = parser.parse_args()
    
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        print("\nInterrupted")
        sys.exit(130)


if __name__ == "__main__":
    main()
