# =============================================================================
# Event 事件聚类服务层模块
# =============================================================================
# 本模块是 Event 子系统的核心业务逻辑层，负责：
#   1. 事件聚类的 CRUD 操作（查询、获取详情）
#   2. 事件时间线的构建
#   3. 文章到事件聚类的自动匹配和分配
#   4. 新事件聚类的自动创建
#
# 聚类算法概述：
#   对每篇未聚类的文章，与所有活跃的事件聚类计算匹配分数：
#   - 分数超过阈值 -> 加入该聚类
#   - 分数未超过阈值但文章重要性 >= 6 -> 创建新聚类
#   - 否则 -> 不聚类
#
# 匹配分数由 clustering.compute_cluster_score 计算，综合考虑：
#   模型名称匹配、标题相似度、实体重叠、关键词重叠、分类一致性
# =============================================================================

"""Event clustering service."""
from __future__ import annotations
import logging
import re
from datetime import datetime, timedelta, timezone
from sqlalchemy import and_, select, update, func
from sqlalchemy.ext.asyncio import AsyncSession
from apps.crawler.models.article import Article
from settings import settings
from common.feature_config import feature_config
from .models import EventCluster, EventMember
from .clustering import compute_cluster_score

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# 事件服务类
# 封装事件聚类相关的所有业务逻辑
# -----------------------------------------------------------------------------
class EventService:
    """Service class for event clustering operations.

    事件聚类业务逻辑服务类，提供事件查询、时间线构建与聚类处理能力。
    """

    async def get_events(self, db: AsyncSession, active_only: bool = True, limit: int = 50, offset: int = 0) -> tuple[list[EventCluster], int]:
        """List event clusters.

        查询事件聚类列表，支持按活跃状态过滤并分页返回。

        Args:
            db: Async database session.
            active_only: Whether to return only active clusters.
            limit: Max number of clusters to return.
            offset: Pagination offset.

        Returns:
            tuple[list[EventCluster], int]: (clusters, total_count).
        """
        # 查询事件聚类列表，支持按活跃状态筛选和分页
        # 参数：
        #   active_only: 是否只返回活跃的事件
        #   limit/offset: 分页参数
        # 返回值：(事件列表, 总数)
        query = select(EventCluster)
        count_query = select(func.count()).select_from(EventCluster)
        # 根据参数添加活跃状态过滤
        if active_only:
            query = query.where(EventCluster.is_active.is_(True))
            count_query = count_query.where(EventCluster.is_active.is_(True))
        # 先查询总数
        count_result = await db.execute(count_query)
        total = count_result.scalar() or 0
        # 按最后更新时间倒序排列，最新的事件排在前面
        query = query.order_by(EventCluster.last_updated_at.desc()).offset(offset).limit(limit)
        result = await db.execute(query)
        events = list(result.scalars().all())
        return events, total

    async def get_event(self, event_id: int, db: AsyncSession) -> dict | None:
        """Get an event cluster by ID with member article info.

        根据事件聚类 ID 获取单个事件对象，包含成员文章的标题和原文链接。

        Args:
            event_id: Event cluster ID.
            db: Async database session.

        Returns:
            dict | None: Event data with members including title/url, or ``None`` if not found.
        """
        from sqlalchemy.orm import selectinload

        # 查询事件聚类，同时加载成员和成员关联的文章
        result = await db.execute(
            select(EventCluster)
            .where(EventCluster.id == event_id)
            .options(
                selectinload(EventCluster.members).selectinload(EventMember.article)
            )
        )
        event = result.scalar_one_or_none()
        if not event:
            return None

        # 手动填充 members 的 title 和 url
        members_data = []
        for m in event.members:
            members_data.append({
                'id': m.id,
                'article_id': m.article_id,
                'similarity_score': m.similarity_score,
                'detection_method': m.detection_method,
                'added_at': m.added_at,
                'title': m.article.title if m.article else '',
                'url': m.article.url if m.article else '',
            })

        return {
            'id': event.id,
            'title': event.title,
            'description': event.description,
            'category': event.category,
            'first_seen_at': event.first_seen_at,
            'last_updated_at': event.last_updated_at,
            'is_active': event.is_active,
            'article_count': event.article_count,
            'members': members_data,
        }

    async def get_event_timeline(self, event_id: int, db: AsyncSession) -> list[dict]:
        """Get timeline entries for an event.

        返回事件相关的文章时间线条目，按发布时间倒序排列。

        Args:
            event_id: Event cluster ID.
            db: Async database session.

        Returns:
            list[dict]: Timeline entries including date, title, summary, and scores.
        """
        # 获取事件的时间线：按发布时间倒序返回关联文章的信息
        # 通过 JOIN 将 EventMember 和 Article 关联查询
        result = await db.execute(
            select(EventMember, Article)
            .join(Article, EventMember.article_id == Article.id)
            .where(EventMember.event_id == event_id)
            .order_by(Article.publish_time.desc())
        )
        rows = result.all()
        # 构建时间线条目
        timeline = []
        for member, article in rows:
            dt = article.publish_time or article.crawl_time
            timeline.append({
                "date": dt.strftime("%Y-%m-%d %H:%M") if dt else "Unknown",
                "title": article.title or "",
                "summary": article.ai_summary or article.summary or "",
                "importance": article.importance_score or 5,
                "similarity": member.similarity_score,  # 文章与事件聚类的匹配分数
                "method": member.detection_method,       # 匹配检测方法
            })
        return timeline

    async def cluster_articles(self, db: AsyncSession, limit: int = 100, min_importance: int = 5) -> dict:
        """Cluster unprocessed articles into events.

        对未聚类文章进行匹配与聚类，必要时创建新事件簇。

        Args:
            db: Async database session.
            limit: Max number of articles to process.
            min_importance: Minimum importance threshold for clustering.

        Returns:
            dict: Processing summary with total, clustered, and new cluster counts.
        """
        # 核心聚类方法：将未聚类的文章匹配到已有事件或创建新事件
        # 参数：
        #   limit: 本次处理的文章数量上限
        #   min_importance: 最低重要性阈值（低于此值的文章不参与聚类）
        # 返回值：处理结果统计（总处理数、已聚类数、新聚类数）

        # 第一步：查询尚未聚类的文章
        # 条件：不在 EventMember 中 + 已 AI 处理 + 重要性达标 + 未归档
        result = await db.execute(
            select(Article)
            .outerjoin(EventMember, Article.id == EventMember.article_id)
            .where(
                and_(
                    EventMember.id.is_(None),                          # 不在任何事件中
                    Article.ai_processed_at.isnot(None),               # 已经过 AI 处理
                    Article.importance_score >= min_importance,         # 重要性达标
                    Article.is_archived.is_(False),                    # 未归档
                )
            )
            .order_by(Article.crawl_time.desc())
            .limit(limit)
        )
        articles = list(result.scalars().all())
        if not articles:
            return {"total_processed": 0, "clustered": 0, "new_clusters": 0}

        # 第二步：获取最近的活跃事件聚类
        # 只匹配最近 3 天内更新过的活跃聚类，过旧的事件不再接受新文章
        cutoff = datetime.now(timezone.utc) - timedelta(days=3)
        cluster_result = await db.execute(
            select(EventCluster)
            .where(and_(EventCluster.is_active.is_(True), EventCluster.last_updated_at >= cutoff))
            .order_by(EventCluster.last_updated_at.desc())
            .limit(100)  # 最多匹配 100 个活跃聚类
        )
        clusters = list(cluster_result.scalars().all())

        # 构建按 category 分组的聚类索引，用于快速预过滤
        # 这样对每篇文章只需先在同 category 的聚类子集中匹配，
        # 减少 O(n*m) 的无效比较
        from collections import defaultdict
        category_to_clusters: dict[str, list[EventCluster]] = defaultdict(list)
        for cluster in clusters:
            cat = cluster.category or "其他"
            category_to_clusters[cat].append(cluster)

        clustered = 0
        new_clusters = 0

        # 第三步：逐篇文章进行匹配
        for article in articles:
            best_match = None      # 最佳匹配的事件聚类
            best_score = 0.0       # 最佳匹配分数
            best_method = "keyword"  # 最佳匹配的检测方法

            article_category = article.ai_category or "其他"

            # 预过滤优化：优先在同 category 的聚类中匹配
            # 如果同 category 未找到，再扩展到全量聚类
            candidate_groups = [category_to_clusters.get(article_category, [])]
            if len(candidate_groups[0]) < len(clusters):
                candidate_groups.append(clusters)  # 全量聚类作为 fallback

            for candidates in candidate_groups:
                for cluster in candidates:
                    score, method = compute_cluster_score(
                        article.title or "",
                        article.content or "",
                        cluster.title,
                        article_category,
                        cluster.category or "",
                    )
                    # 保留最高分的匹配
                    if score > best_score:
                        best_score = score
                        best_match = cluster
                        best_method = method

                # 如果在同 category 中已找到高分匹配，无需搜索全量
                min_similarity = feature_config.get_float("event.min_similarity", 0.7)
                threshold_check = min_similarity * 0.5 if best_method in ("model", "entity") else min_similarity * 0.71
                if best_match and best_score >= threshold_check:
                    break

            # 根据匹配方法使用不同的阈值
            # model 和 entity 匹配的置信度更高，使用较低阈值
            # keyword 和 title 匹配使用较高阈值
            min_similarity = feature_config.get_float("event.min_similarity", 0.7)
            threshold = min_similarity * 0.5 if best_method in ("model", "entity") else min_similarity * 0.71
            if best_match and best_score >= threshold:
                # 匹配成功：加入已有聚类
                member = EventMember(
                    event_id=best_match.id,
                    article_id=article.id,
                    similarity_score=best_score,
                    detection_method=best_method,
                )
                db.add(member)
                # 更新聚类的文章计数和最后更新时间
                await db.execute(
                    update(EventCluster)
                    .where(EventCluster.id == best_match.id)
                    .values(
                        article_count=EventCluster.article_count + 1,
                        last_updated_at=datetime.now(timezone.utc),
                    )
                )
                clustered += 1
            elif (article.importance_score or 0) >= 6:
                # 未匹配到已有聚类，但文章重要性 >= 6：创建新聚类
                # 设计决策：只有重要性较高的文章才值得创建新事件
                new_cluster = EventCluster(
                    title=self._generate_title(article),
                    category=article.ai_category or "其他",
                    first_seen_at=article.publish_time or datetime.now(timezone.utc),
                    last_updated_at=datetime.now(timezone.utc),
                    article_count=1,
                )
                db.add(new_cluster)
                await db.flush()  # flush 以获取新聚类的自增 ID
                # 将文章作为首个成员加入新聚类
                member = EventMember(
                    event_id=new_cluster.id,
                    article_id=article.id,
                    similarity_score=1.0,          # 首篇文章与自身的相似度为 1.0
                    detection_method="initial",    # 标记为初始成员
                )
                db.add(member)
                clusters.append(new_cluster)  # 加入当前批次的聚类列表，后续文章可以匹配到它
                # 同时更新 category 索引
                cat = new_cluster.category or "其他"
                category_to_clusters[cat].append(new_cluster)
                clustered += 1
                new_clusters += 1

        return {"total_processed": len(articles), "clustered": clustered, "new_clusters": new_clusters}

    def _generate_title(self, article: Article) -> str:
        """Generate an event title from an article.

        根据文章标题生成事件标题，并进行截断与前缀清理。

        Args:
            article: Article ORM instance.

        Returns:
            str: Normalized event title.
        """
        # 从文章标题生成事件标题
        # 处理逻辑：
        #   1. 如果标题包含 HN 前缀（如 "Ask HN:", "Show HN:"），去除前缀
        #   2. 截断过长的标题（最多 100 字符）
        title = article.title or ""
        # 去除 Hacker News 风格的前缀
        title = re.sub(r"^(Ask|Show|Tell|Launch) HN[:\s]+", "", title, flags=re.IGNORECASE) if "HN" in title else title
        return title[:100].strip() if len(title) > 100 else title.strip()
