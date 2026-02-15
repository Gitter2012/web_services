# ==============================================================================
# 模块: report/generator.py
# 功能: 报告数据收集与 Markdown 格式化引擎
# 架构角色: 提供两个核心功能:
#   1. generate_report_data - 从数据库中收集指定时间范围内的各项统计数据
#   2. format_report_markdown - 将统计数据格式化为 Markdown 格式的报告正文
# 设计说明:
#   - 数据收集横跨多个模块: 文章 (Article), 事件 (EventCluster), 行动项 (ActionItem)
#   - 统计维度包括: 文章总量、高重要性文章数、分类分布、热门事件、
#     关键词趋势、行动项完成情况
#   - Markdown 格式化使用中文标题和中文内容, 面向中文用户
#   - 数据收集和格式化分离, 数据部分以 dict 返回, 可同时用于
#     stats (JSON) 和 content (Markdown) 两种消费方式
# ==============================================================================
"""Report generation logic."""
from __future__ import annotations

import logging
import re
from collections import Counter
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.crawler.models.article import Article
from apps.event.models import EventCluster
from apps.action.models import ActionItem

# 初始化模块级日志记录器
logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# generate_report_data - 收集报告数据
# 参数:
#   - db: 异步数据库会话
#   - period_start: 报告起始时间
#   - period_end: 报告结束时间
# 返回: 结构化的统计数据字典, 包含以下键:
#   - total_items: 文章总数
#   - high_importance_items: 高重要性文章数 (重要性分数 >= 7)
#   - items_by_category: 按 AI 分类的文章数量分布
#   - top_events: 热门事件列表 (按关联文章数降序, 最多 10 条)
#   - trending_keywords: 热门关键词列表 (最多 10 个)
#   - action_review: 行动项统计 (总数、已完成、待处理、已忽略、完成率)
#
# 数据收集流程:
#   1. 查询时间范围内已 AI 处理的文章, 统计总量和高重要性数量
#   2. 按 AI 分类统计各类别的文章数量
#   3. 查询该时间段内活跃的事件聚类, 按文章数排序
#   4. 从文章标题和摘要中提取高频关键词 (过滤停用词)
#   5. 查询该时间段内创建的行动项, 统计各状态的数量和完成率
# --------------------------------------------------------------------------
async def generate_report_data(
    db: AsyncSession, period_start: datetime, period_end: datetime
) -> dict:
    """Generate report data for a period."""
    # ====== 第一步: 查询时间范围内已 AI 处理的文章 ======
    # 仅加载报告所需的字段，避免将完整 ORM 对象全部加载到内存
    result = await db.execute(
        select(
            Article.id, Article.title, Article.ai_summary,
            Article.ai_category, Article.importance_score
        ).where(
            and_(
                Article.crawl_time >= period_start,
                Article.crawl_time <= period_end,
                Article.ai_processed_at.isnot(None),  # 仅统计已经过 AI 处理的文章
            )
        )
    )
    articles = result.all()

    # 统计文章总数和高重要性文章数 (重要性分数 >= 7 为高重要性)
    total = len(articles)
    high_importance = len(
        [a for a in articles if (a.importance_score or 0) >= 7]
    )

    # ====== 第二步: 按 AI 分类统计各类别的文章数量 ======
    categories = {}
    for a in articles:
        cat = a.ai_category or "未分类"  # 无分类的文章归入 "未分类"
        categories[cat] = categories.get(cat, 0) + 1

    # ====== 第三步: 查询热门事件 ======
    # Top events
    # 计算报告覆盖的天数 (虽然此变量未被后续使用, 但保留以备扩展)
    period_days = (period_end - period_start).days + 1
    event_result = await db.execute(
        select(EventCluster)
        .where(
            and_(
                EventCluster.is_active.is_(True),  # 仅查询活跃的事件聚类
                EventCluster.last_updated_at >= period_start,
                EventCluster.last_updated_at <= period_end,
            )
        )
        .order_by(EventCluster.article_count.desc())  # 按关联文章数降序
        .limit(10)  # 最多取 10 个热门事件
    )
    top_events = [
        {
            "title": e.title,
            "category": e.category or "",
            "article_count": e.article_count,
        }
        for e in event_result.scalars().all()
    ]

    # ====== 第四步: 提取热门关键词 ======
    # Trending keywords
    word_counts = Counter()
    for a in articles:
        # 从标题和 AI 摘要中提取词语
        text = f"{a.title} {a.ai_summary or ''}"
        # 匹配 2 个及以上连续中文字符, 或 3 个及以上连续英文字母
        words = re.findall(r"[\u4e00-\u9fff]{2,}|[a-zA-Z]{3,}", text)
        word_counts.update(words)

    # 中英文停用词集合, 过滤无意义的高频词
    stopwords = {
        "的",
        "是",
        "在",
        "了",
        "和",
        "与",
        "有",
        "这",
        "一个",
        "可以",
        "the",
        "and",
        "for",
        "with",
    }
    # 取 top 20 高频词, 过滤停用词和出现次数不足 3 次的词, 最终保留前 10 个
    trending = [
        w
        for w, c in word_counts.most_common(20)
        if w.lower() not in stopwords and c >= 3
    ][:10]

    # ====== 第五步: 行动项统计回顾 ======
    # Action review
    action_result = await db.execute(
        select(ActionItem).where(
            and_(
                ActionItem.created_at >= period_start,
                ActionItem.created_at <= period_end,
            )
        )
    )
    actions = list(action_result.scalars().all())
    # 按状态分类统计
    completed = len([a for a in actions if a.status == "completed"])  # 已完成
    pending = len([a for a in actions if a.status == "pending"])  # 待处理
    dismissed = len([a for a in actions if a.status == "dismissed"])  # 已忽略

    # 汇总所有统计数据为字典返回
    return {
        "total_items": total,
        "high_importance_items": high_importance,
        "items_by_category": categories,
        "top_events": top_events,
        "trending_keywords": trending,
        "action_review": {
            "total": len(actions),
            "completed": completed,
            "pending": pending,
            "dismissed": dismissed,
            # 完成率计算: 已完成 / 总数 * 100, 无行动项时为 0
            "completion_rate": round(completed / len(actions) * 100, 1)
            if actions
            else 0,
        },
    }


# --------------------------------------------------------------------------
# format_report_markdown - 将报告数据格式化为 Markdown 文本
# 参数:
#   - report_type: 报告类型 ("weekly" 或 "monthly")
#   - period_start: 起始日期字符串 (YYYY-MM-DD)
#   - period_end: 结束日期字符串 (YYYY-MM-DD)
#   - data: 由 generate_report_data 返回的统计数据字典
# 返回: Markdown 格式的报告正文字符串
#
# 报告结构:
#   1. 标题和时间范围
#   2. 总览: 文章总数和高重要性文章数
#   3. 分类分布: 各类别的文章数量 (按数量降序)
#   4. 重要事件: 热门事件列表 (带分类标签和文章数)
#   5. 热门关键词: 逗号分隔的关键词列表
#   6. 行动项回顾: 新增/完成/待处理/完成率统计
# 设计说明: 所有文本使用中文, 面向中文用户群体
# --------------------------------------------------------------------------
def format_report_markdown(
    report_type: str, period_start: str, period_end: str, data: dict
) -> str:
    """Format report data as Markdown."""
    # 根据报告类型生成中文标题
    period_name = "周报" if report_type == "weekly" else "月报"
    lines = [
        f"# ResearchPulse {period_name}",
        f"**时间范围**: {period_start} 至 {period_end}",
        "",
    ]

    # ====== 总览部分 ======
    lines.append(f"## 总览")
    lines.append(f"- 共收录 {data['total_items']} 条内容")
    lines.append(f"- 高重要性 (≥7分) {data['high_importance_items']} 条")
    lines.append("")

    # ====== 分类分布部分: 按文章数量降序排列各分类 ======
    lines.append("## 分类分布")
    for cat, count in sorted(
        data.get("items_by_category", {}).items(),
        key=lambda x: x[1],
        reverse=True,
    ):
        lines.append(f"- {cat}: {count} 条")
    lines.append("")

    # ====== 重要事件部分: 列出热门事件 (如果有) ======
    if data.get("top_events"):
        lines.append(f"## 重要事件 (Top {len(data['top_events'])})")
        for i, event in enumerate(data["top_events"], 1):
            # 格式: 序号. [分类标签] 事件标题 (关联文章数)
            lines.append(
                f"{i}. [{event.get('category', '')}] {event['title']} ({event['article_count']}篇)"
            )
        lines.append("")

    # ====== 热门关键词部分: 逗号分隔展示 (如果有) ======
    if data.get("trending_keywords"):
        lines.append("## 热门关键词")
        lines.append(", ".join(data["trending_keywords"]))
        lines.append("")

    # ====== 行动项回顾部分: 统计各状态数量和完成率 (如果有行动项) ======
    ar = data.get("action_review", {})
    if ar.get("total", 0) > 0:
        lines.append("## 行动项回顾")
        lines.append(
            f"- 新增: {ar['total']}, 已完成: {ar['completed']}, 待处理: {ar['pending']}, 完成率: {ar['completion_rate']}%"
        )

    # 将所有行拼接为完整的 Markdown 文本
    return "\n".join(lines)
