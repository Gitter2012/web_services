"""Article models for ResearchPulse v2."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base, TimestampMixin


class Article(Base, TimestampMixin):
    """Unified article model for all sources (arxiv, rss, wechat)."""

    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
        comment="Source type: arxiv, rss, wechat",
    )
    source_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="ID of the source (category code, feed id, account id)",
    )
    external_id: Mapped[str] = mapped_column(
        String(255),
        default="",
        nullable=False,
        comment="External ID from source (arxiv_id, article GUID, etc)",
    )
    title: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        default="",
    )
    url: Mapped[str] = mapped_column(
        String(2000),
        nullable=False,
        default="",
    )
    author: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        default="",
    )
    summary: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
    )
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
    )
    cover_image_url: Mapped[str] = mapped_column(
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
    tags: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment="JSON array of tags",
    )
    publish_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    crawl_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
    is_archived: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        index=True,
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Additional fields for specific sources
    # arxiv specific
    arxiv_id: Mapped[str] = mapped_column(
        String(50),
        nullable=True,
        comment="arXiv paper ID",
    )
    arxiv_primary_category: Mapped[str] = mapped_column(
        String(200),
        nullable=True,
        comment="arXiv primary category",
    )
    arxiv_comment: Mapped[str] = mapped_column(
        Text,
        nullable=True,
        comment="arXiv comment field",
    )
    arxiv_updated_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="arXiv updated time",
    )

    # wechat specific
    wechat_account_name: Mapped[str] = mapped_column(
        String(200),
        nullable=True,
        comment="WeChat account name",
    )
    wechat_digest: Mapped[str] = mapped_column(
        Text,
        nullable=True,
        comment="WeChat article digest",
    )

    # AI-generated summary or translated abstract
    content_summary: Mapped[str] = mapped_column(
        Text,
        nullable=True,
        comment="AI summary or translated abstract",
    )

    read_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="Read count for WeChat articles",
    )
    like_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="Like count for WeChat articles",
    )

    __table_args__ = (
        Index("ix_articles_source_external", "source_type", "source_id", "external_id", unique=True),
        Index("ix_articles_publish_time", "publish_time"),
        Index("ix_articles_crawl_time", "crawl_time"),
        Index("ix_articles_archived", "is_archived"),
    )

    def __repr__(self) -> str:
        return f"<Article(id={self.id}, title={self.title[:30]}...)>"


class UserArticleState(Base, TimestampMixin):
    """User's reading state for articles."""

    __tablename__ = "user_article_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    article_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("articles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    is_read: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    is_starred: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    starred_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        Index("ix_user_article_unique", "user_id", "article_id", unique=True),
    )

    def mark_read(self) -> None:
        """Mark article as read."""
        self.is_read = True
        self.read_at = datetime.now(timezone.utc)

    def toggle_star(self) -> bool:
        """Toggle star status. Returns new star status."""
        self.is_starred = not self.is_starred
        if self.is_starred:
            self.starred_at = datetime.now(timezone.utc)
        else:
            self.starred_at = None
        return self.is_starred

    def __repr__(self) -> str:
        return f"<UserArticleState(user_id={self.user_id}, article_id={self.article_id})>"
