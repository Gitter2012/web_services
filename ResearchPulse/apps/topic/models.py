# ==============================================================================
# 模块: topic/models.py
# 功能: 话题模块的数据库模型定义 (ORM 映射层)
# 架构角色: 定义了话题系统的三个核心数据表:
#   1. Topic - 话题主表, 存储话题的基本信息和关键词
#   2. ArticleTopic - 文章与话题的多对多关联表, 记录匹配关系和分数
#   3. TopicSnapshot - 话题快照表, 定期记录话题活跃度用于趋势分析
# 设计说明: 使用 SQLAlchemy 2.0 声明式映射 (Mapped + mapped_column),
#           所有模型继承 Base 和 TimestampMixin 以获得统一的时间戳字段
# ==============================================================================
"""Topic models."""
from __future__ import annotations
from datetime import datetime, timezone
from sqlalchemy import BigInteger, Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from core.models.base import Base, TimestampMixin

# --------------------------------------------------------------------------
# Topic 模型 - 话题主表
# 职责: 存储用户创建或系统自动发现的话题信息
# 关键字段:
#   - name: 话题名称, 唯一且带索引, 便于快速查找和去重
#   - keywords: JSON 格式的关键词数组, 用于文章-话题匹配
#   - is_auto_discovered: 区分手动创建和自动发现的话题
#   - is_active: 话题激活状态, 可用于软删除或暂停跟踪
#   - created_by_user_id: 关联创建者, 外键级联设为 SET NULL,
#     即用户被删除后话题仍保留但创建者信息清空
# --------------------------------------------------------------------------
class Topic(Base, TimestampMixin):
    """A tracked topic."""
    __tablename__ = "topics"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    keywords: Mapped[dict | None] = mapped_column(JSON, nullable=True, comment="JSON array of keywords")
    is_auto_discovered: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_by_user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

# --------------------------------------------------------------------------
# ArticleTopic 模型 - 文章与话题的关联表
# 职责: 记录文章与话题之间的多对多匹配关系
# 设计决策:
#   - match_score: 匹配分数, 反映文章与话题的相关程度, 用于排序
#   - matched_keywords: JSON 格式存储命中的关键词列表, 方便前端展示匹配原因
#   - UniqueConstraint: 确保同一篇文章和同一个话题之间只有一条关联记录
#   - 两个外键均设置 CASCADE 删除, 确保文章或话题删除时关联记录自动清理
# --------------------------------------------------------------------------
class ArticleTopic(Base, TimestampMixin):
    """Association between articles and topics."""
    __tablename__ = "article_topics"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    article_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("articles.id", ondelete="CASCADE"), nullable=False, index=True)
    topic_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("topics.id", ondelete="CASCADE"), nullable=False, index=True)
    match_score: Mapped[float] = mapped_column(Float, default=0.0)
    matched_keywords: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    __table_args__ = (UniqueConstraint("article_id", "topic_id", name="uq_article_topic"),)

# --------------------------------------------------------------------------
# TopicSnapshot 模型 - 话题快照表
# 职责: 按日期定期记录话题的活跃度指标, 用于生成趋势图和分析
# 关键字段:
#   - snapshot_date: 快照日期 (YYYY-MM-DD 字符串格式), 带索引便于时间范围查询
#   - article_count: 该日期下与话题关联的文章数量
#   - trend_score: 趋势分数, 量化话题的热度变化
#   - trend: 趋势方向枚举 (up/down/stable), 便于快速判断
#   - top_keywords: 该时间段内的热门关键词快照
#   - summary: 该时间段的话题摘要描述
# 设计说明: 快照表的引入使得趋势分析不需要每次都重新计算历史数据,
#           提升了查询性能
# --------------------------------------------------------------------------
class TopicSnapshot(Base, TimestampMixin):
    """Periodic snapshot of topic activity."""
    __tablename__ = "topic_snapshots"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    topic_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("topics.id", ondelete="CASCADE"), nullable=False, index=True)
    snapshot_date: Mapped[str] = mapped_column(String(10), nullable=False, index=True, comment="Date YYYY-MM-DD")
    article_count: Mapped[int] = mapped_column(Integer, default=0)
    trend_score: Mapped[float] = mapped_column(Float, default=0.0)
    trend: Mapped[str] = mapped_column(String(10), default="stable", comment="up, down, stable")
    top_keywords: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    summary: Mapped[str] = mapped_column(Text, nullable=True)
