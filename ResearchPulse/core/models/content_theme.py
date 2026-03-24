# =============================================================================
# 模块: core/models/content_theme.py
# 功能: 通用内容主题模型
# 架构角色: 数据持久化层，定义跨报告类型、跨格式化器的通用样式主题
# 设计决策:
#   1. 通过 content_types 字段支持多报告类型（日报、周报、月报等）
#   2. 通过 formatter_types 字段支持多格式化器（微信 HTML、邮件 HTML 等）
#   3. 使用 JSON config 字段存储颜色/字体等样式配置，易于扩展
#   4. 颜色统一在 config.colors 子对象中，结构化管理
# =============================================================================

"""Universal content theme model for ResearchPulse."""

from __future__ import annotations

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.models.base import Base, TimestampMixin


class ContentTheme(Base, TimestampMixin):
    """Universal content theme model supporting multiple report types and formatters.

    通用内容主题模型，支持所有报告类型和格式化器的样式配置。

    每个主题定义了一套完整的颜色配置，可应用于：
    - 微信公众号 HTML 格式化器（wechat_html）
    - 邮件 HTML 模板（email_html）
    - 以及未来的其他格式化器

    Attributes:
        id: 主键
        name: 主题唯一标识符（如 classic_blue, elegant_dark）
        display_name: 界面显示名称（如 经典蓝, 深色雅致）
        description: 主题描述
        content_types: 适用的内容类型列表（JSON），如 ["daily_report", "weekly_report"]
        formatter_types: 适用的格式化器类型列表（JSON），如 ["wechat_html", "email_html"]
        config: 主题配置（JSON），包含颜色、字体、特效等子对象
        is_default: 是否为默认主题
        is_active: 是否启用
        priority: 排序优先级（越大越靠前）
        preview_url: 预览图 URL（可选）
        author: 主题作者（可选）
    """

    __tablename__ = "content_themes"

    # ---- 主键 ----
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # ---- 主题标识 ----
    name: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        unique=True,
        comment="主题唯一标识符，如 classic_blue",
    )
    display_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="界面显示名称，如 经典蓝",
    )
    description: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        comment="主题描述",
    )

    # ---- 应用范围 ----
    content_types: Mapped[list] = mapped_column(
        JSON,
        nullable=False,
        comment="适用内容类型列表，如 [\"daily_report\", \"weekly_report\"]",
    )
    formatter_types: Mapped[list] = mapped_column(
        JSON,
        nullable=False,
        comment="适用格式化器类型，如 [\"wechat_html\", \"email_html\"]",
    )

    # ---- 样式配置 ----
    config: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        comment="主题配置 JSON，包含 colors、typography、effects 子对象",
    )

    # ---- 元数据 ----
    is_default: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="是否为默认主题",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="是否启用",
    )
    priority: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="排序优先级，越大越靠前",
    )
    preview_url: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="预览图 URL",
    )
    author: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="主题作者",
    )

    # ---- 关系 ----
    daily_reports: Mapped[list] = relationship(
        "DailyReport",
        back_populates="wechat_theme",
        foreign_keys="DailyReport.wechat_theme_id",
        lazy="noload",
    )
    reports: Mapped[list] = relationship(
        "Report",
        back_populates="theme",
        foreign_keys="Report.theme_id",
        lazy="noload",
    )

    def get_colors(self) -> dict:
        """Get color configuration from theme config.

        从主题配置中获取颜色配置字典。

        Returns:
            颜色配置字典，如果 config 中没有 colors 子对象则返回空字典。
        """
        return self.config.get("colors", {}) if self.config else {}

    def get_typography(self) -> dict:
        """Get typography configuration from theme config.

        从主题配置中获取字体配置字典。
        """
        return self.config.get("typography", {}) if self.config else {}

    def get_effects(self) -> dict:
        """Get effects configuration from theme config.

        从主题配置中获取特效配置字典。
        """
        return self.config.get("effects", {}) if self.config else {}

    def __repr__(self) -> str:
        """Return a readable theme representation."""
        return f"<ContentTheme(id={self.id}, name={self.name!r}, display_name={self.display_name!r})>"
