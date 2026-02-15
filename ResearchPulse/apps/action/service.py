# ==============================================================================
# 模块: action/service.py
# 功能: 行动项模块的业务逻辑服务层 (Service 层)
# 架构角色: 位于 API 层和数据访问层之间, 封装行动项相关的所有业务操作。
#           负责行动项的 CRUD 操作、状态管理 (完成/忽略) 和从文章中自动提取。
# 设计说明:
#   - ActionService 类聚合了行动项的全部业务逻辑
#   - 所有查询和操作都带有 user_id 过滤, 确保数据隔离 (用户只能操作自己的数据)
#   - 状态变更 (complete/dismiss) 通过独立方法实现, 而非通用的 update 方法,
#     以保证状态转换的原子性和业务规则的完整性
#   - 文章行动项提取功能委托给 extractor.py 处理
# ==============================================================================
"""Action items service."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .models import ActionItem
from .extractor import extract_actions_from_article

# 初始化模块级日志记录器
logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# ActionService - 行动项业务服务类
# 职责: 提供行动项 CRUD、状态管理和文章行动项提取等核心业务操作
# 设计决策:
#   - 采用无状态设计, 每次请求创建新实例
#   - 所有操作强制要求 user_id, 实现用户级别的数据隔离
#   - 状态变更操作 (complete/dismiss) 独立实现, 不使用通用 update
# --------------------------------------------------------------------------
class ActionService:
    """Service class for action item operations.

    行动项业务逻辑服务类，提供 CRUD、状态管理与自动提取功能。
    """

    # ----------------------------------------------------------------------
    # list_actions - 查询用户的行动项列表
    # 参数:
    #   - user_id: 用户 ID, 用于数据隔离
    #   - db: 异步数据库会话
    #   - status: 状态过滤条件, 为 None 时不过滤
    #   - limit: 每页返回数量上限, 默认 50
    #   - offset: 分页偏移量, 默认 0
    # 返回: (行动项列表, 总数) 的元组
    # 逻辑: 先统计总数 (用于分页), 再按创建时间倒序获取指定范围的数据
    # ----------------------------------------------------------------------
    async def list_actions(
        self,
        user_id: int,
        db: AsyncSession,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[ActionItem], int]:
        """List action items for a user.

        查询用户的行动项列表，支持状态过滤与分页。

        Args:
            user_id: Owner user ID.
            db: Async database session.
            status: Optional status filter.
            limit: Max items to return.
            offset: Pagination offset.

        Returns:
            tuple[list[ActionItem], int]: (items, total_count).
        """
        # 基础查询: 按用户 ID 过滤
        query = select(ActionItem).where(ActionItem.user_id == user_id)
        count_query = (
            select(func.count())
            .select_from(ActionItem)
            .where(ActionItem.user_id == user_id)
        )
        if status:
            # 如果指定了状态, 同时为数据查询和计数查询添加状态过滤条件
            query = query.where(ActionItem.status == status)
            count_query = count_query.where(ActionItem.status == status)
        # 先执行计数查询获取总数
        count_result = await db.execute(count_query)
        total = count_result.scalar() or 0
        # 按创建时间倒序排列, 应用分页参数
        result = await db.execute(
            query.order_by(ActionItem.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all()), total

    # ----------------------------------------------------------------------
    # get_action - 根据 ID 获取单个行动项
    # 参数:
    #   - action_id: 行动项 ID
    #   - user_id: 用户 ID (用于所有权校验, 确保只能获取自己的行动项)
    #   - db: 异步数据库会话
    # 返回: ActionItem 对象, 若不存在或不属于该用户则返回 None
    # 设计说明: 同时使用 action_id 和 user_id 作为查询条件,
    #           在数据层面保证用户只能访问自己的行动项
    # ----------------------------------------------------------------------
    async def get_action(
        self, action_id: int, user_id: int, db: AsyncSession
    ) -> ActionItem | None:
        """Get a single action item by ID.

        按行动项 ID 获取用户自己的行动项。

        Args:
            action_id: Action item ID.
            user_id: Owner user ID for access control.
            db: Async database session.

        Returns:
            ActionItem | None: Action item or ``None`` if not found.
        """
        result = await db.execute(
            select(ActionItem).where(
                and_(ActionItem.id == action_id, ActionItem.user_id == user_id)
            )
        )
        return result.scalar_one_or_none()

    # ----------------------------------------------------------------------
    # create_action - 创建新行动项
    # 参数:
    #   - user_id: 所属用户 ID
    #   - article_id: 关联的文章 ID
    #   - type_: 行动项类型 (跟进/验证/决策/触发器)
    #   - description: 描述内容
    #   - priority: 优先级 (高/中/低)
    #   - db: 异步数据库会话
    # 返回: 新创建的 ActionItem 对象
    # 副作用: 向数据库插入新记录, 通过 flush() 获取自增 ID
    # ----------------------------------------------------------------------
    async def create_action(
        self,
        user_id: int,
        article_id: int,
        type_: str,
        description: str,
        priority: str,
        db: AsyncSession,
    ) -> ActionItem:
        """Create a new action item.

        创建并持久化新的行动项记录。

        Args:
            user_id: Owner user ID.
            article_id: Related article ID.
            type_: Action item type (e.g. follow-up/verify).
            description: Action item description.
            priority: Priority level.
            db: Async database session.

        Returns:
            ActionItem: Newly created action item.
        """
        action = ActionItem(
            article_id=article_id,
            user_id=user_id,
            type=type_,
            description=description,
            priority=priority,
        )
        db.add(action)
        await db.flush()  # 刷新到数据库以获取自增主键 ID
        await db.refresh(action)  # 刷新对象以获取数据库生成的默认值
        return action

    # ----------------------------------------------------------------------
    # update_action - 更新行动项属性
    # 参数:
    #   - action_id: 行动项 ID
    #   - user_id: 用户 ID (用于所有权校验)
    #   - db: 异步数据库会话
    #   - **kwargs: 需要更新的字段键值对
    # 返回: 更新后的 ActionItem 对象, 若不存在则返回 None
    # 设计说明: 使用动态 setattr 实现灵活的部分更新,
    #           仅更新值不为 None 且模型确实拥有的属性
    # ----------------------------------------------------------------------
    async def update_action(
        self, action_id: int, user_id: int, db: AsyncSession, **kwargs
    ) -> ActionItem | None:
        """Update an action item with provided fields.

        按传入字段对行动项进行部分更新。

        Args:
            action_id: Action item ID.
            user_id: Owner user ID.
            db: Async database session.
            **kwargs: Fields to update.

        Returns:
            ActionItem | None: Updated action item or ``None`` if not found.
        """
        action = await self.get_action(action_id, user_id, db)
        if not action:
            return None
        for key, value in kwargs.items():
            # 跳过值为 None 的字段和模型中不存在的属性
            if value is not None and hasattr(action, key):
                setattr(action, key, value)
        return action

    # ----------------------------------------------------------------------
    # complete_action - 将行动项标记为已完成
    # 参数:
    #   - action_id: 行动项 ID
    #   - user_id: 用户 ID (用于所有权校验)
    #   - db: 异步数据库会话
    # 返回: 更新后的 ActionItem 对象, 若不存在则返回 None
    # 副作用: 将 status 设为 "completed", 记录 completed_at 时间戳 (UTC)
    # 设计说明: 独立的完成方法确保状态变更的业务规则不被绕过
    # ----------------------------------------------------------------------
    async def complete_action(
        self, action_id: int, user_id: int, db: AsyncSession
    ) -> ActionItem | None:
        """Mark an action item as completed.

        将行动项状态更新为已完成并记录完成时间。

        Args:
            action_id: Action item ID.
            user_id: Owner user ID.
            db: Async database session.

        Returns:
            ActionItem | None: Updated action item or ``None`` if not found.
        """
        action = await self.get_action(action_id, user_id, db)
        if not action:
            return None
        action.status = "completed"
        action.completed_at = datetime.now(timezone.utc)  # 记录完成时间 (UTC 时区)
        return action

    # ----------------------------------------------------------------------
    # dismiss_action - 将行动项标记为已忽略
    # 参数:
    #   - action_id: 行动项 ID
    #   - user_id: 用户 ID (用于所有权校验)
    #   - db: 异步数据库会话
    # 返回: 更新后的 ActionItem 对象, 若不存在则返回 None
    # 副作用: 将 status 设为 "dismissed", 记录 dismissed_at 时间戳 (UTC)
    # 设计说明: dismissed 表示用户认为该行动项不需要执行,
    #           与 completed 区分以便后续统计分析
    # ----------------------------------------------------------------------
    async def dismiss_action(
        self, action_id: int, user_id: int, db: AsyncSession
    ) -> ActionItem | None:
        """Dismiss an action item.

        将行动项状态更新为已忽略并记录忽略时间。

        Args:
            action_id: Action item ID.
            user_id: Owner user ID.
            db: Async database session.

        Returns:
            ActionItem | None: Updated action item or ``None`` if not found.
        """
        action = await self.get_action(action_id, user_id, db)
        if not action:
            return None
        action.status = "dismissed"
        action.dismissed_at = datetime.now(timezone.utc)  # 记录忽略时间 (UTC 时区)
        return action

    # ----------------------------------------------------------------------
    # extract_from_article - 从文章中自动提取行动项
    # 参数:
    #   - article_id: 文章 ID
    #   - user_id: 目标用户 ID (提取出的行动项将归属于该用户)
    #   - db: 异步数据库会话
    # 返回: 提取出的 ActionItem 列表
    # 逻辑: 委托给 extractor.extract_actions_from_article() 执行
    #       提取逻辑基于文章的 AI 处理结果 (actionable_items 字段)
    # ----------------------------------------------------------------------
    async def extract_from_article(
        self, article_id: int, user_id: int, db: AsyncSession
    ) -> list[ActionItem]:
        """Extract action items from an article.

        从文章 AI 处理结果中提取行动项并归属给指定用户。

        Args:
            article_id: Article ID.
            user_id: Owner user ID.
            db: Async database session.

        Returns:
            list[ActionItem]: Extracted action items.
        """
        return await extract_actions_from_article(article_id, user_id, db)
