# =============================================================================
# 用户模型模块
# =============================================================================
# 本模块定义了 ResearchPulse 项目的用户模型（User）和用户角色关联模型（UserRole）。
# 主要职责：
#   1. 定义用户表（users）的 ORM 映射，包括认证信息、状态和通知偏好
#   2. 定义用户与角色的多对多关联表（user_roles）
#   3. 提供密码设置、验证、权限检查等用户相关的业务方法
#
# 架构角色：
#   - 作为认证系统的核心模型，被 dependencies.py 中的认证依赖函数查询
#   - 通过 roles 关系与 RBAC（基于角色的访问控制）系统集成
#   - 被 security.py 的密码哈希和验证函数间接调用
#
# 设计决策：
#   - 继承 TimestampMixin 自动管理 created_at 和 updated_at 字段
#   - username 和 email 字段均建立唯一索引，支持两种方式登录
#   - 密码存储为哈希值，原始密码永远不会被存储
#   - 使用延迟导入（lazy import）调用 security 模块，避免循环依赖
#   - roles 关系使用 lazy="selectin" 策略，查询用户时自动加载角色信息
#   - UserRole 使用复合主键（user_id + role_id），避免重复关联
# =============================================================================

"""User model for ResearchPulse v2."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.models.base import Base, TimestampMixin

# TYPE_CHECKING 仅在类型检查工具（如 mypy、pyright）运行时为 True
# 运行时不会导入，避免循环依赖问题
if TYPE_CHECKING:
    from core.models.permission import Role


class User(Base, TimestampMixin):
    """User model for authentication and RBAC.

    Stores credentials, status flags, and notification preferences.
    保存认证信息、状态标记以及通知偏好设置。

    Attributes:
        id: Primary key.
        username: Unique username.
        email: Unique email address.
        password_hash: Hashed password value.
        is_active: Whether the user account is active.
        is_superuser: Whether the user has superuser privileges.
        last_login_at: Last login timestamp in UTC.
        email_notifications_enabled: Whether email notifications are enabled.
        email_digest_frequency: Digest frequency (daily/weekly/none).
        roles: RBAC roles assigned to the user.
    """
    # 用户模型：存储用户认证信息、状态标记和通知配置
    # 继承 Base（ORM 基类）和 TimestampMixin（自动时间戳）

    __tablename__ = "users"  # 数据库中的表名

    # ---- 主键 ----
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # ---- 认证相关字段 ----
    # 用户名：唯一且带索引，最大 50 字符
    username: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
    )
    # 电子邮箱：唯一且带索引，最大 100 字符
    email: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
    )
    # 密码哈希值：存储 bcrypt 哈希后的密码，而非明文密码
    # 最大 255 字符，足够存储 bcrypt 输出的哈希字符串
    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    # ---- 状态标记字段 ----
    # 用户是否处于活跃状态，被禁用的用户无法登录系统
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    # 是否为超级管理员，超管拥有所有权限，不受 RBAC 规则限制
    is_superuser: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    # 最后登录时间，用于审计和用户活跃度分析
    # 允许为空（用户从未登录过时为 None）
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # ---- 邮件通知设置字段 ----
    # Email notification settings
    # 是否启用邮件通知功能
    email_notifications_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="Whether user wants to receive email notifications",
    )
    # 邮件摘要发送频率：daily（每日）、weekly（每周）或 none（不发送）
    email_digest_frequency: Mapped[str] = mapped_column(
        String(20),
        default="daily",
        nullable=False,
        comment="Email digest frequency: daily, weekly, or none",
    )

    # ---- 关联关系 ----
    # Relationships
    # 用户与角色的多对多关系，通过 user_roles 关联表实现
    # lazy="selectin"：查询用户时自动通过子查询加载角色列表
    # 这样在检查权限时不需要额外的数据库查询
    roles: Mapped[list["Role"]] = relationship(
        "Role",
        secondary="user_roles",
        back_populates="users",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        """Return a readable representation for debugging.

        Returns:
            str: User representation containing id and username.
        """
        # 返回用户对象的可读字符串表示，便于调试和日志输出
        return f"<User(id={self.id}, username={self.username})>"

    def set_password(self, password: str) -> None:
        """Set the user's password hash.

        Args:
            password: Plaintext password.
        """
        # 延迟导入 security 模块，避免循环依赖
        from core.security import hash_password

        # 将明文密码哈希后存储，原始密码不会被保留
        self.password_hash = hash_password(password)

    def check_password(self, password: str) -> bool:
        """Check whether a plaintext password matches.

        Args:
            password: Plaintext password to verify.

        Returns:
            bool: ``True`` if the password matches the stored hash.
        """
        # 延迟导入 security 模块，避免循环依赖
        from core.security import verify_password

        # 将输入的明文密码与存储的哈希值进行比对验证
        return verify_password(password, self.password_hash)

    def update_last_login(self) -> None:
        """Update the last login timestamp.

        Side Effects:
            Mutates ``last_login_at`` to current UTC time.
        """
        # 更新最后登录时间为当前 UTC 时间
        # 通常在用户成功登录后调用此方法
        self.last_login_at = datetime.now(timezone.utc)

    def has_permission(self, permission: str) -> bool:
        """Check whether the user has a specific permission.

        Args:
            permission: Permission name to check.

        Returns:
            bool: ``True`` if the user has the permission.

        Note:
            This method expects roles and permissions to be preloaded.
            该方法要求角色权限已被预加载。
        """
        # 检查用户是否拥有指定权限
        # 注意：此方法要求 roles 和 permissions 关系已预加载（lazy="selectin" 已确保）

        # 超级管理员拥有所有权限，直接返回 True
        if self.is_superuser:
            return True
        # 遍历用户的所有角色及其关联的权限，查找匹配的权限名称
        for role in self.roles:
            for perm in role.permissions:
                if perm.name == permission:
                    return True
        return False

    def has_role(self, role_name: str) -> bool:
        """Check whether the user has a specific role.

        Args:
            role_name: Role name to check.

        Returns:
            bool: ``True`` if the user has the role.
        """
        # 检查用户是否拥有指定角色
        # 使用 any() 函数进行高效的短路判断
        return any(role.name == role_name for role in self.roles)


class UserRole(Base):
    """Association table for user and role mapping.

    Records assignments between users and roles.
    记录用户与角色的多对多关联。
    """
    # 用户-角色关联模型：实现用户与角色的多对多关系
    # 使用复合主键（user_id + role_id）确保同一用户不会被重复分配相同角色

    __tablename__ = "user_roles"  # 数据库中的关联表名

    # 用户 ID 外键，指向 users 表的主键
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id"),
        primary_key=True,
        nullable=False,
    )
    # 角色 ID 外键，指向 roles 表的主键
    role_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("roles.id"),
        primary_key=True,
        nullable=False,
    )
    # 关联创建时间，记录用户被分配角色的时间点
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
