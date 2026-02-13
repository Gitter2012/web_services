"""Source models for ResearchPulse v2."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base, TimestampMixin


class ArxivCategory(Base, TimestampMixin):
    """arXiv category model."""

    __tablename__ = "arxiv_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
        comment="Category code (e.g., cs.LG)",
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Full category name",
    )
    parent_code: Mapped[str] = mapped_column(
        String(50),
        default="",
        nullable=False,
        comment="Parent category code",
    )
    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<ArxivCategory(code={self.code}, name={self.name})>"


class RssFeed(Base, TimestampMixin):
    """RSS feed subscription model."""

    __tablename__ = "rss_feeds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        default="",
    )
    feed_url: Mapped[str] = mapped_column(
        String(2000),
        unique=True,
        nullable=False,
    )
    site_url: Mapped[str] = mapped_column(
        String(2000),
        nullable=False,
        default="",
    )
    category: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="",
        index=True,
    )
    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    last_fetched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    error_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<RssFeed(id={self.id}, title={self.title[:30]}...)>"


class WechatAccount(Base, TimestampMixin):
    """WeChat official account model."""

    __tablename__ = "wechat_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_name: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
        comment="WeChat account name (biz)",
    )
    display_name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        default="",
        comment="Display name of the account",
    )
    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
    )
    avatar_url: Mapped[str] = mapped_column(
        String(2000),
        nullable=False,
        default="",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    last_fetched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    error_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<WechatAccount(account_name={self.account_name})>"
