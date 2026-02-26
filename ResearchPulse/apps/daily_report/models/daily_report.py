# =============================================================================
# 模块: apps/daily_report/models/daily_report.py
# 功能: 每日报告数据模型定义
# 架构角色: 数据持久化层，定义每日 arXiv 报告的数据结构
# 设计决策:
#   1. 每个分类每天生成一份报告，通过 (report_date, category) 唯一约束
#   2. 同时存储标准 Markdown 和微信公众号专用格式
#   3. 记录收录的文章 ID 列表，便于追溯和更新
# =============================================================================

"""Daily arXiv report model."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, Index, Integer, String, Text
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base, TimestampMixin


class DailyReport(Base, TimestampMixin):
    """Daily arXiv report model.

    每日 arXiv 报告模型，按分类存储当天发布的论文信息。

    Attributes:
        id: 主键
        report_date: 报告日期
        category: arXiv 分类代码（如 cs.LG）
        category_name: 分类中文名称（如 机器学习）
        title: 报告标题
        content_markdown: Markdown 格式的报告内容
        content_wechat: 微信公众号专用格式内容
        article_count: 收录文章数量
        article_ids: 收录的文章 ID 列表（JSON 格式）
        status: 报告状态（draft/published/archived）
        published_at: 发布时间
    """

    __tablename__ = "daily_reports"

    # ---- 主键 ----
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # ---- 报告基本信息 ----
    report_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
        comment="报告日期",
    )
    category: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="arXiv 分类代码，如 cs.LG, cs.CV",
    )
    category_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="分类中文名称，如 机器学习",
    )

    # ---- 报告内容 ----
    title: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        comment="报告标题",
    )
    content_markdown: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Markdown 格式的报告内容",
    )
    content_wechat: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="微信公众号专用格式内容",
    )

    # ---- 统计信息 ----
    article_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="收录文章数量",
    )
    article_ids: Mapped[list | None] = mapped_column(
        JSON,
        nullable=True,
        comment="收录的文章 ID 列表",
    )

    # ---- 状态 ----
    status: Mapped[str] = mapped_column(
        String(20),
        default="draft",
        nullable=False,
        comment="状态: draft/published/archived",
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="发布时间",
    )

    # ---- 数据库索引定义 ----
    __table_args__ = (
        # 联合唯一索引：确保每天每个分类只有一份报告
        Index("ix_daily_reports_date_category", "report_date", "category", unique=True),
        # 状态索引：支持按状态筛选
        Index("ix_daily_reports_status", "status"),
    )

    def __repr__(self) -> str:
        """Return a readable daily report representation."""
        return f"<DailyReport(id={self.id}, date={self.report_date}, category={self.category})>"
