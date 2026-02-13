"""User subscription model for ResearchPulse v2."""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base, TimestampMixin


class UserSubscription(Base, TimestampMixin):
    """User subscription to sources."""

    __tablename__ = "user_subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment="Source type: arxiv_category, rss_feed, wechat_account",
    )
    source_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="ID of the subscribed source",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    __table_args__ = (
        Index("ix_user_subscription_unique", "user_id", "source_type", "source_id", unique=True),
    )

    def __repr__(self) -> str:
        return f"<UserSubscription(user_id={self.user_id}, type={self.source_type})>"
