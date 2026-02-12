from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import String, Text, Boolean, Integer, DateTime, Index
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Article(Base):
    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(500), default="")
    author: Mapped[str] = mapped_column(String(200), default="")
    account_name: Mapped[str] = mapped_column(String(200), default="", index=True)
    account_id: Mapped[str] = mapped_column(String(200), default="")
    digest: Mapped[str] = mapped_column(Text, default="")
    content_url: Mapped[str] = mapped_column(String(2000), unique=True, index=True)
    cover_image_url: Mapped[str] = mapped_column(String(2000), default="")
    publish_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    crawl_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    source_type: Mapped[str] = mapped_column(
        String(20), default="rss"  # "rss" | "mitmproxy"
    )
    read_count: Mapped[int] = mapped_column(Integer, default=0)
    like_count: Mapped[int] = mapped_column(Integer, default=0)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    tags: Mapped[str] = mapped_column(String(500), default="")
    raw_content_html: Mapped[str] = mapped_column(Text, default="")

    __table_args__ = (
        Index("ix_articles_account_publish", "account_name", "publish_time"),
    )


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_name: Mapped[str] = mapped_column(String(200), default="")
    account_id: Mapped[str] = mapped_column(String(200), default="")
    rss_url: Mapped[str] = mapped_column(String(2000), unique=True)
    source_type: Mapped[str] = mapped_column(
        String(20), default="rss"  # "rss" | "mitmproxy"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
