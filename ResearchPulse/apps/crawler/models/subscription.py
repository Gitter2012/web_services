# =============================================================================
# 模块: apps/crawler/models/subscription.py
# 功能: 用户订阅关系模型定义
# 架构角色: 数据持久化层的关联模型，建立用户与数据源之间的多对多订阅关系。
#           用户可以订阅多个不同类型的数据源（arXiv 分类、RSS 订阅源、微信公众号），
#           系统根据用户的订阅关系来决定推送哪些内容。
# 设计决策:
#   1. 使用泛化的 source_type + source_id 组合来关联不同类型的数据源，
#      而非为每种数据源创建独立的订阅表。这样做的优势是：
#      - 新增数据源类型时无需修改表结构
#      - 查询用户所有订阅只需查一张表
#      缺点是无法使用外键约束确保 source_id 的引用完整性。
#   2. (user_id, source_type, source_id) 三元组设有唯一约束，
#      确保用户不会重复订阅同一数据源。
#   3. is_active 字段支持软取消订阅，保留历史订阅记录。
# =============================================================================

"""User subscription model for ResearchPulse v2."""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base, TimestampMixin


# =============================================================================
# UserSubscription 模型
# 职责: 记录用户对数据源的订阅关系
# 表名: user_subscriptions
# 关联关系:
#   - user_id -> users.id (外键，用户删除时级联删除)
#   - source_type: 数据源类型标识 ("arxiv_category", "rss_feed", "wechat_account")
#   - source_id: 对应数据源表的主键ID（无外键约束，依靠应用层保证一致性）
# =============================================================================
class UserSubscription(Base, TimestampMixin):
    """User subscription to sources.

    用户订阅关系模型。
    """

    __tablename__ = "user_subscriptions"

    # 主键
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 订阅用户的ID，外键关联 users 表
    # 用户删除时级联删除其所有订阅记录
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # 数据源类型标识
    # 取值范围: "arxiv_category"（arXiv 分类）、"rss_feed"（RSS 源）、"wechat_account"（微信公众号）
    source_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment="Source type: arxiv_category, rss_feed, wechat_account",
    )
    # 数据源ID，对应 arxiv_categories.id / rss_feeds.id / wechat_accounts.id
    # 注意：此处未使用外键约束，因为 source_id 可能指向不同的表
    # 数据一致性由应用层逻辑保证
    source_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="ID of the subscribed source",
    )
    # 订阅是否活跃：False 表示已取消订阅但保留记录
    # 这样设计便于恢复订阅和分析用户行为
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    # ---- 唯一约束 ----
    # 确保每个用户对每个数据源只能订阅一次
    # (user_id, source_type, source_id) 三元组唯一
    __table_args__ = (
        Index("ix_user_subscription_unique", "user_id", "source_type", "source_id", unique=True),
    )

    def __repr__(self) -> str:
        """Return a readable subscription representation.

        返回订阅记录的字符串表示。
        """
        return f"<UserSubscription(user_id={self.user_id}, type={self.source_type})>"
