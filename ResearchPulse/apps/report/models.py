# ==============================================================================
# 模块: report/models.py
# 功能: 报告模块的数据库模型定义 (ORM 映射层)
# 架构角色: 定义了报告系统的核心数据表 Report,
#           存储自动生成的周报和月报的完整内容及统计数据。
# 设计说明:
#   - 使用 SQLAlchemy 2.0 声明式映射 (Mapped + mapped_column)
#   - 继承 Base 和 TimestampMixin 获得统一的表结构和时间戳字段
#   - 报告内容以 Markdown 格式存储, 便于前端渲染
#   - stats 字段以 JSON 格式存储结构化统计数据, 便于数据可视化
# ==============================================================================
"""Report models."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base, TimestampMixin


# --------------------------------------------------------------------------
# Report 模型 - 报告表
# 职责: 存储系统自动生成的周报和月报
# 关键字段:
#   - user_id: 报告所属用户 ID, CASCADE 级联删除 (用户删除时报告也删除)
#   - type: 报告类型, "weekly" (周报) 或 "monthly" (月报)
#   - period_start: 报告覆盖的起始日期 (YYYY-MM-DD 字符串格式)
#   - period_end: 报告覆盖的结束日期 (YYYY-MM-DD 字符串格式)
#   - title: 报告标题, 自动生成 (例如: "周报 2024-01-01 ~ 2024-01-07")
#   - content: 报告正文, Markdown 格式, 包含文章统计、事件、关键词等内容
#   - stats: JSON 格式的结构化统计数据, 包含各类聚合指标
#   - generated_at: 报告生成时间, 默认为当前 UTC 时间
# 设计说明:
#   - period_start 和 period_end 使用字符串而非 Date 类型,
#     是为了简化跨数据库兼容性和前端展示
#   - content 和 stats 提供了同一数据的两种视图:
#     content 面向人类阅读 (Markdown), stats 面向程序消费 (JSON)
# --------------------------------------------------------------------------
class Report(Base, TimestampMixin):
    """Generated report (weekly/monthly)."""

    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    type: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="weekly, monthly"
    )
    period_start: Mapped[str] = mapped_column(
        String(10), nullable=False, comment="YYYY-MM-DD"
    )
    period_end: Mapped[str] = mapped_column(
        String(10), nullable=False, comment="YYYY-MM-DD"
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(
        Text, nullable=False, comment="Markdown formatted report"
    )
    stats: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="Report statistics"
    )
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),  # 默认值: 当前 UTC 时间
        nullable=False,
    )
