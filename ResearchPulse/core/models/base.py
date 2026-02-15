# =============================================================================
# ORM 基础模型与通用混入类模块
# =============================================================================
# 本模块定义了 ResearchPulse 项目中所有 SQLAlchemy ORM 模型的基类和通用混入（Mixin）。
# 主要职责：
#   1. 提供所有 ORM 模型的声明式基类（Base），统一模型注册与元数据管理
#   2. 提供时间戳混入类（TimestampMixin），自动管理创建时间和更新时间字段
#   3. 提供带时区的日期时间类型别名（DateTimeTZ），简化字段声明
#
# 架构角色：
#   - 作为所有 ORM 模型（User、Role、Permission、Article 等）的根基类
#   - 被 database.py 模块用于数据库表的自动创建（Base.metadata.create_all）
#   - TimestampMixin 被需要自动时间戳功能的模型继承使用
#
# 设计决策：
#   - 使用 SQLAlchemy 2.0 风格的 DeclarativeBase 声明式基类
#   - 时间戳统一使用 UTC 时区（timezone.utc），避免时区转换问题
#   - 使用 lambda 默认值而非 server_default，确保在 Python 层面生成时间戳
# =============================================================================

"""Base models and mixins for ResearchPulse v2."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for all ORM models.

    All SQLAlchemy models in ResearchPulse must inherit from this base so they
    are registered in ``Base.metadata`` for schema creation and migrations.
    """
    # 所有 ORM 模型必须继承此基类
    # DeclarativeBase 提供了声明式映射功能，自动收集所有子类的表结构定义
    # Base.metadata 包含了所有已注册模型的表元数据，用于建表和 DDL 操作

    pass


class TimestampMixin:
    """Mixin providing ``created_at`` and ``updated_at`` timestamps.

    The timestamps are generated in UTC at the Python layer. ``updated_at`` is
    refreshed automatically on update operations.
    """
    # 时间戳混入类，为模型自动添加 created_at 和 updated_at 字段
    # 使用方式：class MyModel(Base, TimestampMixin): ...
    # 注意：这是一个普通的 Python 混入类，不继承 Base，因此不会单独创建表

    # 记录创建时间，插入时自动设置为当前 UTC 时间
    # 使用 lambda 确保每次创建新实例时都生成新的时间戳
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    # 记录最后更新时间，插入时自动设置，每次更新时自动刷新为当前 UTC 时间
    # onupdate 参数使得每次 UPDATE 操作时 SQLAlchemy 会自动更新此字段
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


# 带时区信息的日期时间类型别名
# 可在其他模型中作为字段类型使用，简化 DateTime(timezone=True) 的重复声明
# 示例：some_date: Mapped[DateTimeTZ] = mapped_column(nullable=True)
# Type alias for datetime with timezone
DateTimeTZ = Annotated[datetime, mapped_column(DateTime(timezone=True))]
