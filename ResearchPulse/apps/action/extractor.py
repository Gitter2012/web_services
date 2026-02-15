# ==============================================================================
# 模块: action/extractor.py
# 功能: 从 AI 处理后的文章中自动提取行动项
# 架构角色: 负责将 AI 处理结果转化为结构化的行动项记录。
#           作为 ActionService 的下游依赖, 被 service.extract_from_article() 调用。
# 设计说明:
#   - 依赖文章的 actionable_items 字段 (由 AI 处理器生成的 JSON 数据)
#   - 该字段包含一个字典列表, 每个字典描述一个可执行的行动项
#   - 本模块负责将这些字典解析为 ActionItem ORM 对象并持久化
#   - 对输入数据做了防御性检查, 容忍格式异常的条目
# ==============================================================================
"""Extract action items from AI-processed articles."""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.crawler.models.article import Article
from .models import ActionItem

# 初始化模块级日志记录器
logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# extract_actions_from_article - 从文章的 AI 处理结果中提取行动项
# 参数:
#   - article_id: 文章 ID
#   - user_id: 目标用户 ID (提取出的行动项将归属于该用户)
#   - db: 异步数据库会话
# 返回: 新创建的 ActionItem 对象列表, 若文章不存在或无行动项数据则返回空列表
# 副作用:
#   - 向数据库批量插入行动项记录
#   - 通过 flush() 确保数据写入但不提交事务 (事务由上层管理)
#   - 记录日志: 成功提取的行动项数量和来源文章 ID
#
# 数据格式说明:
#   文章的 actionable_items 字段预期格式为字典列表, 例如:
#   [
#     {"type": "跟进", "description": "关注某技术进展", "priority": "高"},
#     {"type": "验证", "description": "核实某信息来源", "priority": "中"},
#   ]
#   每个字典的 type 默认为 "跟进", priority 默认为 "中", status 固定为 "pending"
# --------------------------------------------------------------------------
async def extract_actions_from_article(
    article_id: int, user_id: int, db: AsyncSession
) -> list[ActionItem]:
    """Extract action items from an article's AI results."""
    # 查询目标文章
    result = await db.execute(select(Article).where(Article.id == article_id))
    article = result.scalar_one_or_none()
    # 如果文章不存在或没有 AI 提取的行动项数据, 直接返回空列表
    if not article or not article.actionable_items:
        return []

    # 确保 actionable_items 是列表格式, 防御性处理异常数据
    items = (
        article.actionable_items
        if isinstance(article.actionable_items, list)
        else []
    )
    created = []  # 已创建的行动项列表
    for item in items:
        # 跳过非字典格式的条目, 保证数据格式的鲁棒性
        if not isinstance(item, dict):
            continue
        # 创建行动项, 使用 get 方法提供默认值以容忍缺失字段
        action = ActionItem(
            article_id=article_id,
            user_id=user_id,
            type=item.get("type", "跟进"),  # 默认类型: 跟进
            description=item.get("description", ""),  # 默认描述: 空字符串
            priority=item.get("priority", "中"),  # 默认优先级: 中
            status="pending",  # 新创建的行动项初始状态均为 pending
        )
        db.add(action)
        created.append(action)

    # 如果成功创建了行动项, 刷新到数据库并记录日志
    if created:
        await db.flush()  # 批量刷新, 使所有新记录获得数据库生成的 ID
        logger.info(
            f"Extracted {len(created)} action items from article {article_id}"
        )
    return created
