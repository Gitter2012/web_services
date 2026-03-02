#!/usr/bin/env python3
"""清理文章字段中的 thinking 标签。

本脚本用于清理数据库中文章指定字段里的 thinking 标签内容。
某些 AI 模型（如 Qwen3）在生成时会输出 thinking 标签，
本脚本可以移除这些标签，只保留正式结果。

什么是 thinking 标签？
    某些推理模型会在输出中包含 <think>...</think> 标签，
    用于展示模型的推理过程。这些标签内容通常不需要存储到数据库。

支持清理的字段：
    - content: 文章内容
    - ai_summary: AI 生成的摘要
    - one_liner: 一句话总结
    - key_points: 关键点（JSON 格式）
    - impact_assessment: 影响评估（JSON 格式）
    - actionable_items: 行动项（JSON 格式）

用法示例：
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

# 将项目根目录添加到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

import warnings
# 抑制垃圾回收器相关的警告
warnings.filterwarnings("ignore", message=".*garbage collector.*")

from dotenv import load_dotenv
load_dotenv()

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
# 常量定义
# ---------------------------------------------------------------------------

# 匹配 thinking 标签的正则表达式
# 支持 <think>...</think> 和 <thinking>...</thinking> 格式
# 使用 DOTALL 标志使 . 匹配换行符，IGNORECASE 使匹配不区分大小写
THINK_TAG_RE = re.compile(r"</think>\s*", re.DOTALL | re.IGNORECASE)

# 可清理的字段列表
# 包含文本字段和 JSON 字段
CLEANABLE_FIELDS = [
    "content",           # 文章内容（文本）
    "ai_summary",        # AI 摘要（文本）
    "one_liner",         # 一句话总结（文本）
    "key_points",        # 关键点（JSON）
    "impact_assessment", # 影响评估（JSON）
    "actionable_items",  # 行动项（JSON）
]


# ---------------------------------------------------------------------------
# 清理函数
# ---------------------------------------------------------------------------

def clean_think_tags(text: str) -> str:
    """移除文本中的 thinking 标签。

    从文本中删除所有 <think>...</think> 或 <thinking>...</thinking> 标签及其内容，
    只保留标签外的正式结果。

    参数：
        text: 要清理的文本。

    返回：
        str: 清理后的文本。如果输入为空，返回原输入。

    示例：
        >>> clean_think_tags("<think>推理过程...</think>最终结论")
        '最终结论'
    """
    if not text:
        return text
    return THINK_TAG_RE.sub("", text).strip()


def clean_json_field(data) -> str:
    """清理 JSON 数据中的 thinking 标签。

    递归遍历 JSON 数据结构（字典、列表），清理所有字符串值中的 thinking 标签。

    参数：
        data: 要清理的 JSON 数据，可以是：
            - str: 直接清理字符串
            - list: 遍历列表，清理每个字典中的字符串值
            - dict: 清理字典中所有字符串值

    返回：
        清理后的数据，类型与输入相同。

    示例：
        >>> clean_json_field({"text": "<think>...</think>结果"})
        {'text': '结果'}
    """
    if not data:
        return data

    # 处理字符串类型
    if isinstance(data, str):
        return clean_think_tags(data)

    # 处理列表类型（通常用于 key_points, actionable_items）
    if isinstance(data, list):
        cleaned = []
        for item in data:
            if isinstance(item, dict):
                # 清理字典中的每个字符串值
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

    # 处理字典类型
    if isinstance(data, dict):
        cleaned = {}
        for k, v in data.items():
            if isinstance(v, str):
                cleaned[k] = clean_think_tags(v)
            else:
                cleaned[k] = v
        return cleaned

    # 其他类型直接返回
    return data


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

async def run(args: argparse.Namespace) -> None:
    """执行清理流程。

    根据命令行参数查询需要清理的文章，并执行清理操作。

    参数：
        args: 解析后的命令行参数，包含：
            - field: 要清理的字段列表
            - stats: 是否仅统计
            - ids: 指定的文章 ID 列表
    """
    from core.database import get_session_factory, close_db
    from sqlalchemy import select, text
    from apps.crawler.models.article import Article

    session_factory = get_session_factory()
    # 默认清理 content 字段
    fields = args.field or ["content"]

    try:
        async with session_factory() as session:
            # 构建查询
            if args.ids:
                # 指定文章 ID：直接查询这些文章
                sql = text(f"""
                    SELECT id, {', '.join(fields)}
                    FROM articles 
                    WHERE id IN :ids
                """)
                result = await session.execute(sql, {"ids": tuple(args.ids)})
            else:
                # 查找包含 thinking 标签的文章
                # 使用 LIKE 查询匹配包含 <think 的记录
                like_conditions = " OR ".join([f"{f} LIKE '%<think%'" for f in fields])
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

            # 仅统计模式：显示统计信息后退出
            if args.stats:
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

                # 遍历每个字段进行清理
                for i, field in enumerate(fields):
                    value = row[i + 1]
                    if not value:
                        continue

                    if field in ("key_points", "impact_assessment", "actionable_items"):
                        # JSON 字段：先解析再清理
                        try:
                            if isinstance(value, str):
                                data = json.loads(value)
                            else:
                                data = value
                            cleaned = clean_json_field(data)
                            # 如果有变化，更新字段
                            if cleaned != data:
                                updates[field] = json.dumps(cleaned, ensure_ascii=False)
                        except (json.JSONDecodeError, TypeError):
                            # 解析失败时当作普通字符串处理
                            cleaned = clean_think_tags(str(value))
                            if cleaned != value:
                                updates[field] = cleaned
                    else:
                        # 普通文本字段：直接清理
                        cleaned = clean_think_tags(str(value))
                        if cleaned != value:
                            updates[field] = cleaned

                # 执行数据库更新
                if updates:
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
    """命令行入口函数。

    解析命令行参数并执行清理流程。
    """
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
        logger.warning("Interrupted")
        sys.exit(130)


if __name__ == "__main__":
    main()
