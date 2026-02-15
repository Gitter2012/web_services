# ==============================================================================
# 模块: action/models.py
# 功能: 行动项模块的数据库模型定义 (ORM 映射层)
# 架构角色: 定义了行动项系统的核心数据表 ActionItem,
#           存储从文章中提取的可执行任务及其生命周期状态。
# 设计说明:
#   - 使用 SQLAlchemy 2.0 声明式映射 (Mapped + mapped_column)
#   - 继承 Base 和 TimestampMixin 获得统一的表结构和时间戳字段
#   - 行动项绑定到用户和文章, 支持按用户+状态的复合索引查询
#   - 生命周期: pending -> completed 或 pending -> dismissed
# ==============================================================================
"""Action item models."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base, TimestampMixin


# --------------------------------------------------------------------------
# ActionItem 模型 - 行动项表
# 职责: 存储从 AI 处理后的文章中提取出的可执行行动项
# 关键字段:
#   - article_id: 关联的文章 ID, CASCADE 级联删除 (文章删除时行动项也删除)
#   - user_id: 所属用户 ID, CASCADE 级联删除 (用户删除时行动项也删除)
#   - type: 行动项类型, 包括 "跟进"、"验证"、"决策"、"触发器" 四种
#     * 跟进: 需要持续关注的事项
#     * 验证: 需要进一步核实的信息
#     * 决策: 需要做出判断的事项
#     * 触发器: 达到特定条件时需要采取行动的事项
#   - description: 行动项的具体描述内容
#   - priority: 优先级 ("高" / "中" / "低"), 默认为 "中"
#   - status: 当前状态 ("pending" / "completed" / "dismissed"), 默认为 "pending"
#   - completed_at: 完成时间, 当状态变更为 completed 时记录
#   - dismissed_at: 忽略时间, 当状态变更为 dismissed 时记录
# 索引设计:
#   - article_id 单列索引: 支持按文章查询关联的行动项
#   - user_id 单列索引: 支持按用户查询行动项
#   - status 单列索引: 支持按状态过滤
#   - (user_id, status) 复合索引: 优化最常见的 "按用户+状态查询" 场景
# --------------------------------------------------------------------------
class ActionItem(Base, TimestampMixin):
    """An actionable item extracted from articles."""

    __tablename__ = "action_items"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    article_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("articles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    type: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="跟进, 验证, 决策, 触发器"
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[str] = mapped_column(
        String(10), default="中", comment="高, 中, 低"
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
        index=True,
        comment="pending, completed, dismissed",
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    dismissed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # 复合索引: 优化 "查询某用户特定状态的行动项" 这一高频查询场景
    __table_args__ = (Index("ix_action_items_user_status", "user_id", "status"),)
