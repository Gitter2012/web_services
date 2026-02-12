from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Feed(Base):
    __tablename__ = "feeds"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(500), nullable=False, default="")
    feed_url = Column(String(2000), nullable=False, unique=True)
    site_url = Column(String(2000), nullable=False, default="")
    category = Column(String(100), nullable=False, default="")
    description = Column(Text, nullable=False, default="")
    is_active = Column(Boolean, nullable=False, default=True)
    last_fetched_at = Column(DateTime, nullable=True)
    error_count = Column(Integer, nullable=False, default=0)
    created_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    articles = relationship("Article", back_populates="feed", cascade="all, delete-orphan")


class Article(Base):
    __tablename__ = "articles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    feed_id = Column(Integer, ForeignKey("feeds.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(1000), nullable=False, default="")
    url = Column(String(2000), nullable=False, unique=True)
    author = Column(String(200), nullable=False, default="")
    summary = Column(Text, nullable=False, default="")
    content_html = Column(Text, nullable=False, default="")
    cover_image_url = Column(String(2000), nullable=False, default="")
    publish_time = Column(DateTime, nullable=True)
    crawl_time = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    is_read = Column(Boolean, nullable=False, default=False)
    is_starred = Column(Boolean, nullable=False, default=False)

    feed = relationship("Feed", back_populates="articles")
