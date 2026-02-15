# =============================================================================
# Event 事件聚类数据模型模块
# =============================================================================
# 本模块定义了事件聚类相关的数据库 ORM 模型。
# 事件聚类是将内容相关的文章自动分组为"事件"的机制，
# 例如多篇关于"GPT-5 发布"的文章会被聚合为一个事件。
#
# 模型关系：
#   EventCluster (1) -- (*) EventMember -- (1) Article
#   一个事件聚类包含多个成员，每个成员关联一篇文章
#
# 设计决策：
#   - 使用中间表 EventMember 而非多对多关系，因为需要记录额外信息
#     （如相似度分数、检测方法、加入时间）
#   - article_id 设为 unique，确保每篇文章只属于一个事件聚类
#   - 使用复合索引 (is_active, last_updated_at) 优化常用查询
# =============================================================================

"""Event clustering models."""
from __future__ import annotations
from datetime import datetime, timezone
from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from core.models.base import Base, TimestampMixin

# -----------------------------------------------------------------------------
# 事件聚类模型
# 表示一个事件，由多篇相关文章聚合而成
# 包含事件的标题、描述、分类、时间跨度和活跃状态
# -----------------------------------------------------------------------------
class EventCluster(Base, TimestampMixin):
    """An event cluster grouping related articles."""
    __tablename__ = "event_clusters"
    # 主键，自增 ID
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # 事件标题，通常来自第一篇文章的标题（经过清理）
    title: Mapped[str] = mapped_column(String(255), nullable=False, comment="Event title")
    # 事件描述（可选），可由后续处理生成
    description: Mapped[str] = mapped_column(Text, nullable=True, comment="Event description")
    # 事件分类（AI/技术/金融等），继承自主要文章的分类
    category: Mapped[str] = mapped_column(String(50), nullable=True, index=True, comment="Event category")
    # 事件首次出现的时间
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    # 事件最后更新时间（有新文章加入时更新）
    last_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    # 事件是否活跃（不活跃的事件不再接受新文章）
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    # 聚类中的文章数量（冗余计数，避免每次都 COUNT 查询）
    article_count: Mapped[int] = mapped_column(Integer, default=0, comment="Number of articles in cluster")
    # 关联的成员列表，使用 selectin 加载策略（查询事件时自动加载成员）
    members: Mapped[list["EventMember"]] = relationship("EventMember", back_populates="event", lazy="selectin")
    # 复合索引：优化"获取活跃事件并按更新时间排序"的常用查询
    __table_args__ = (Index("ix_event_clusters_active_updated", "is_active", "last_updated_at"),)

# -----------------------------------------------------------------------------
# 事件成员模型
# 文章与事件聚类之间的关联表，记录匹配的详细信息
# 设计决策：
#   - article_id 设为 unique，一篇文章只能属于一个事件
#   - 记录 similarity_score 和 detection_method，便于后续分析聚类质量
# -----------------------------------------------------------------------------
class EventMember(Base):
    """Association between articles and event clusters."""
    __tablename__ = "event_members"
    # 主键
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # 关联的事件聚类 ID，级联删除
    event_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("event_clusters.id", ondelete="CASCADE"), nullable=False, index=True)
    # 关联的文章 ID，唯一约束确保一篇文章只属于一个事件
    article_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("articles.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    # 文章与事件聚类的匹配相似度分数
    similarity_score: Mapped[float] = mapped_column(Float, default=0.0, comment="Similarity score to cluster")
    # 匹配检测方法：keyword（关键词）、entity（实体）、semantic（语义）、hybrid（混合）、
    # model（模型名匹配）、title（标题匹配）、initial（首篇文章，创建聚类时）
    detection_method: Mapped[str] = mapped_column(String(50), default="keyword", comment="How match was detected: keyword, entity, semantic, hybrid")
    # 文章被加入事件的时间
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    # 反向关联到事件聚类
    event: Mapped["EventCluster"] = relationship("EventCluster", back_populates="members")
