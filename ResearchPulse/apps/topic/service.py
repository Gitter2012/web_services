# ==============================================================================
# 模块: topic/service.py
# 功能: 话题模块的业务逻辑服务层 (Service 层)
# 架构角色: 位于 API 层和数据访问层之间, 封装话题相关的所有业务操作。
#           协调 ORM 模型操作、话题发现 (discovery) 和话题雷达 (radar) 功能。
# 设计说明:
#   - TopicService 类聚合了话题 CRUD、文章关联查询、自动发现和趋势检测等功能
#   - 复杂的算法逻辑委托给 discovery.py 和 radar.py 模块处理
#   - 所有数据库操作通过传入的 AsyncSession 完成, 由调用方管理事务
# ==============================================================================
"""Topic service layer."""
from __future__ import annotations
import logging
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from .models import ArticleTopic, Topic
from .discovery import discover_topics
from .radar import detect_trend, match_article_to_topics

# 初始化模块级日志记录器
logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# TopicService - 话题业务服务类
# 职责: 提供话题 CRUD、文章关联、话题发现、趋势分析等核心业务操作
# 设计决策: 采用无状态设计, 每次请求创建新实例, 所有状态通过参数传入
# --------------------------------------------------------------------------
class TopicService:
    """Service class for topic operations.

    话题业务逻辑服务类，提供话题 CRUD、自动发现与趋势分析能力。
    """

    # ----------------------------------------------------------------------
    # list_topics - 查询话题列表
    # 参数:
    #   - db: 异步数据库会话
    #   - active_only: 是否仅返回活跃话题, 默认 True
    # 返回: (话题列表, 总数) 的元组
    # 逻辑: 先通过子查询统计总数, 再按创建时间倒序获取列表
    # ----------------------------------------------------------------------
    async def list_topics(self, db: AsyncSession, active_only: bool = True) -> tuple[list[Topic], int]:
        """List topics with optional active filter.

        查询话题列表，可按活跃状态过滤。

        Args:
            db: Async database session.
            active_only: Whether to return only active topics.

        Returns:
            tuple[list[Topic], int]: (topics, total_count).
        """
        query = select(Topic)
        if active_only:
            # 仅查询激活状态的话题
            query = query.where(Topic.is_active.is_(True))
        # 使用子查询统计总数, 确保 count 和列表查询的过滤条件一致
        count_result = await db.execute(select(func.count()).select_from(query.subquery()))
        total = count_result.scalar() or 0
        # 按创建时间倒序排列, 最新创建的话题排在前面
        result = await db.execute(query.order_by(Topic.created_at.desc()))
        return list(result.scalars().all()), total

    # ----------------------------------------------------------------------
    # get_topic - 根据 ID 获取单个话题
    # 参数:
    #   - topic_id: 话题 ID
    #   - db: 异步数据库会话
    # 返回: Topic 对象, 若不存在则返回 None
    # ----------------------------------------------------------------------
    async def get_topic(self, topic_id: int, db: AsyncSession) -> Topic | None:
        """Get a topic by ID.

        根据话题 ID 获取话题对象。

        Args:
            topic_id: Topic ID.
            db: Async database session.

        Returns:
            Topic | None: Topic instance or ``None`` if not found.
        """
        result = await db.execute(select(Topic).where(Topic.id == topic_id))
        return result.scalar_one_or_none()

    # ----------------------------------------------------------------------
    # create_topic - 创建新话题
    # 参数:
    #   - name: 话题名称
    #   - description: 话题描述
    #   - keywords: 关键词列表, 用于后续的文章匹配
    #   - user_id: 创建者的用户 ID, 可为 None (系统自动创建时)
    #   - db: 异步数据库会话
    # 返回: 新创建的 Topic 对象
    # 副作用: 向数据库插入一条新记录, 通过 flush() 获取自增 ID,
    #         通过 refresh() 刷新对象属性
    # 设计说明: is_auto_discovered 设为 False, 表示这是用户手动创建的话题
    # ----------------------------------------------------------------------
    async def create_topic(self, name: str, description: str, keywords: list[str], user_id: int | None, db: AsyncSession) -> Topic:
        """Create a new topic.

        创建新话题并写入数据库。

        Args:
            name: Topic name.
            description: Topic description.
            keywords: Keywords used for matching articles.
            user_id: Creator user ID, or ``None`` for system-created topics.
            db: Async database session.

        Returns:
            Topic: Newly created topic instance.
        """
        topic = Topic(name=name, description=description, keywords=keywords, is_auto_discovered=False, created_by_user_id=user_id)
        db.add(topic)
        await db.flush()  # 刷新到数据库以获取自增主键 ID
        await db.refresh(topic)  # 刷新对象以获取数据库生成的默认值
        return topic

    # ----------------------------------------------------------------------
    # update_topic - 更新话题
    # 参数:
    #   - topic_id: 话题 ID
    #   - db: 异步数据库会话
    #   - **kwargs: 需要更新的字段键值对
    # 返回: 更新后的 Topic 对象, 若不存在则返回 None
    # 设计说明: 使用动态 setattr 实现灵活的部分更新,
    #           仅更新值不为 None 且模型确实拥有的属性
    # ----------------------------------------------------------------------
    async def update_topic(self, topic_id: int, db: AsyncSession, **kwargs) -> Topic | None:
        """Update a topic with provided fields.

        按传入字段对话题进行部分更新，忽略空值与不存在字段。

        Args:
            topic_id: Topic ID.
            db: Async database session.
            **kwargs: Fields to update.

        Returns:
            Topic | None: Updated topic or ``None`` if not found.
        """
        topic = await self.get_topic(topic_id, db)
        if not topic:
            return None
        for key, value in kwargs.items():
            # 跳过值为 None 的字段, 以及模型中不存在的属性, 防止意外赋值
            if value is not None and hasattr(topic, key):
                setattr(topic, key, value)
        return topic

    # ----------------------------------------------------------------------
    # delete_topic - 删除话题
    # 参数:
    #   - topic_id: 话题 ID
    #   - db: 异步数据库会话
    # 返回: 删除成功返回 True, 话题不存在返回 False
    # 副作用: 由于外键设置了 CASCADE, 删除话题时会自动清理关联的
    #         ArticleTopic 和 TopicSnapshot 记录
    # ----------------------------------------------------------------------
    async def delete_topic(self, topic_id: int, db: AsyncSession) -> bool:
        """Delete a topic by ID.

        删除话题并触发关联记录的级联清理。

        Args:
            topic_id: Topic ID.
            db: Async database session.

        Returns:
            bool: ``True`` if deleted, otherwise ``False``.
        """
        topic = await self.get_topic(topic_id, db)
        if not topic:
            return False
        await db.delete(topic)
        return True

    # ----------------------------------------------------------------------
    # get_topic_articles - 获取话题关联的文章列表
    # 参数:
    #   - topic_id: 话题 ID
    #   - db: 异步数据库会话
    #   - limit: 返回数量上限, 默认 50
    # 返回: 字典列表, 每条包含 article_id, title, match_score, matched_keywords
    # 逻辑: 通过 ArticleTopic 关联表 JOIN Article 表,
    #       按匹配分数降序排列, 返回最相关的文章
    # 设计说明: 延迟导入 Article 模型以避免循环依赖
    # ----------------------------------------------------------------------
    async def get_topic_articles(self, topic_id: int, db: AsyncSession, limit: int = 50) -> list[dict]:
        """Get articles associated with a topic.

        查询话题关联的文章列表并按匹配分数排序。

        Args:
            topic_id: Topic ID.
            db: Async database session.
            limit: Max number of articles to return.

        Returns:
            list[dict]: Article summaries with match scores.
        """
        # 延迟导入, 避免 topic 和 crawler 模块之间的循环依赖
        from apps.crawler.models.article import Article
        result = await db.execute(
            select(ArticleTopic, Article).join(Article, ArticleTopic.article_id == Article.id)
            .where(ArticleTopic.topic_id == topic_id).order_by(ArticleTopic.match_score.desc()).limit(limit)
        )
        articles = []
        for assoc, art in result.all():
            articles.append({"article_id": art.id, "title": art.title or "", "match_score": assoc.match_score, "matched_keywords": assoc.matched_keywords})
        return articles

    # ----------------------------------------------------------------------
    # discover - 自动发现新话题
    # 参数:
    #   - db: 异步数据库会话
    #   - days: 分析的时间范围天数, 默认 14 天
    #   - min_frequency: 最低出现频次阈值, 默认 5 次
    # 返回: 话题建议字典列表, 包含名称、关键词、频率、置信度等
    # 逻辑: 委托给 discovery.discover_topics() 执行具体的发现算法
    # ----------------------------------------------------------------------
    async def discover(self, db: AsyncSession, days: int = 14, min_frequency: int = 5) -> list[dict]:
        """Discover new topics from recent articles.

        基于时间窗口分析文章内容，生成话题建议列表。

        Args:
            db: Async database session.
            days: Lookback window in days.
            min_frequency: Minimum frequency threshold.

        Returns:
            list[dict]: Topic suggestions with metadata.
        """
        return await discover_topics(db, days=days, min_frequency=min_frequency)

    # ----------------------------------------------------------------------
    # get_trend - 获取话题趋势
    # 参数:
    #   - topic_id: 话题 ID
    #   - db: 异步数据库会话
    #   - period_days: 统计周期天数, 默认 7 天
    # 返回: 趋势信息字典, 包含方向、变化百分比、当前/前期文章数
    # 逻辑: 委托给 radar.detect_trend() 执行趋势检测算法
    # ----------------------------------------------------------------------
    async def get_trend(self, topic_id: int, db: AsyncSession, period_days: int = 7) -> dict:
        """Get trend metrics for a topic.

        获取话题在指定周期内的趋势变化信息。

        Args:
            topic_id: Topic ID.
            db: Async database session.
            period_days: Number of days to compare.

        Returns:
            dict: Trend summary including direction and change rate.
        """
        return await detect_trend(topic_id, db, period_days=period_days)
