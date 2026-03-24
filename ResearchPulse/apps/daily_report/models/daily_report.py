# =============================================================================
# 模块: apps/daily_report/models/daily_report.py
# 功能: 每日报告数据模型定义
# 架构角色: 数据持久化层，定义每日报告的数据结构
# 设计决策:
#   1. 每个分类每天每个数据源生成一份报告，通过 (report_date, source_type, category) 唯一约束
#   2. 同时存储标准 Markdown 和微信公众号专用格式
#   3. 记录收录的文章 ID 列表，便于追溯和更新
# =============================================================================

"""Daily report model for multiple data sources."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.models.base import Base, TimestampMixin


class DailyReport(Base, TimestampMixin):
    """Daily report model for multiple data sources.

    每日报告模型，按分类和数据源存储当天发布的内容信息。

    Attributes:
        id: 主键
        report_date: 报告日期
        source_type: 数据源类型（arxiv, hackernews, reddit, weibo, rss）
        category: 分类代码（如 cs.LG, technology）
        category_name: 分类中文名称（如 机器学习）
        title: 报告标题
        content_markdown: Markdown 格式的报告内容
        content_wechat: 微信公众号专用格式内容
        article_count: 收录文章数量
        article_ids: 收录的文章 ID 列表（JSON 格式）
        status: 报告状态（draft/published/archived）
        published_at: 发布时间
        wechat_draft_media_id: 微信草稿 media_id
        wechat_push_status: 微信推送状态（pending/success/failed/skipped）
        wechat_push_error: 微信推送错误信息
        wechat_pushed_at: 微信推送时间
        sync_status: 跨服务器同步状态（pending/success/failed/skipped）
        sync_error: 同步失败时的错误信息
        sync_attempted_at: 最后一次同步尝试的时间
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
    source_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="arxiv",
        index=True,
        comment="数据源类型: arxiv, hackernews, reddit, weibo, rss",
    )
    category: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="分类代码，如 cs.LG, cs.CV, technology",
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

    # ---- 微信公众号推送状态 ----
    wechat_draft_media_id: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        comment="微信草稿 media_id",
    )
    wechat_push_status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
        nullable=False,
        comment="微信推送状态: pending/success/failed/skipped",
    )
    wechat_push_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="微信推送错误错误信息",
    )
    wechat_pushed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="微信推送时间",
    )

    # ---- 跨服务器同步状态 ----
    sync_status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
        nullable=False,
        comment="跨服务器同步状态: pending/success/failed/skipped",
    )
    sync_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="同步失败时的错误信息",
    )
    sync_attempted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="最后一次同步尝试的时间",
    )

    # ---- 内容主题 ----
    wechat_theme_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("content_themes.id", ondelete="SET NULL"),
        nullable=True,
        comment="关联的微信 HTML 主题",
    )

    # ---- 定时推送 ----
    wechat_scheduled_push_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="定时推送时间，为 null 表示未设置定时推送",
    )
    wechat_scheduled_push_job_id: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        comment="APScheduler job_id，用于取消定时推送任务",
    )

    # ---- 关系 ----
    wechat_theme: Mapped["ContentTheme | None"] = relationship(
        "ContentTheme",
        foreign_keys=[wechat_theme_id],
        lazy="selectin",
        back_populates="daily_reports",
    )

    # ---- 数据库索引定义 ----
    __table_args__ = (
        # 联合唯一索引：确保每天每个数据源每个分类只有一份报告
        Index("ix_daily_reports_date_source_category", "report_date", "source_type", "category", unique=True),
        # 状态索引：支持按状态筛选
        Index("ix_daily_reports_status", "status"),
        # 同步状态索引：用于查询待同步或同步失败的报告
        Index("ix_daily_reports_sync_status", "sync_status"),
    )

    def __repr__(self) -> str:
        """Return a readable daily report representation."""
        return f"<DailyReport(id={self.id}, date={self.report_date}, source={self.source_type}, category={self.category})>"
