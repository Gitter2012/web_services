# =============================================================================
# 权限与角色模型模块（RBAC 核心）
# =============================================================================
# 本模块定义了 ResearchPulse 项目的 RBAC（基于角色的访问控制）模型，包括：
#   1. Role（角色模型）：定义系统角色（如 superuser、admin、user、guest）
#   2. Permission（权限模型）：定义细粒度的操作权限（如 article:read、user:manage）
#   3. RolePermission（角色-权限关联模型）：建立角色与权限的多对多关系
#   4. DEFAULT_PERMISSIONS：预定义的系统权限列表
#   5. DEFAULT_ROLES：预定义的角色及其默认权限映射
#
# 架构角色：
#   - 与 User 模型和 UserRole 关联表共同构成完整的 RBAC 权限体系
#   - 被 dependencies.py 的 require_permissions() 函数查询，用于 API 级别的权限检查
#   - 被 User.has_permission() 方法通过关系链查询，用于业务逻辑级别的权限检查
#   - DEFAULT_PERMISSIONS 和 DEFAULT_ROLES 用于系统初始化时自动创建预定义数据
#
# RBAC 数据流：
#   User --[user_roles]--> Role --[role_permissions]--> Permission
#   即：用户通过角色间接获得权限，一个用户可拥有多个角色，一个角色可包含多个权限
#
# 权限命名约定：
#   格式为 "资源:操作"，如 "article:read"、"user:manage"
#   resource 字段存储资源名称，action 字段存储操作类型
# =============================================================================

"""Permission and Role models for RBAC in ResearchPulse v2."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, Integer, String, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.models.base import Base

# TYPE_CHECKING 仅在类型检查工具运行时为 True
# 运行时不会导入 User 模型，避免循环依赖
if TYPE_CHECKING:
    from core.models.user import User


class Role(Base):
    """Role model for RBAC.

    Represents a set of permissions assigned to users.
    表示一组权限集合，可分配给用户。
    """
    # 角色模型：定义系统中的角色
    # 角色是权限的集合，用户通过被分配角色来获得相应的权限

    __tablename__ = "roles"  # 数据库中的表名

    # ---- 主键 ----
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # 角色名称：唯一且带索引，最大 50 字符
    # 例如：superuser、admin、user、guest
    name: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
    )
    # 角色描述：简要说明该角色的用途和权限范围
    description: Mapped[str] = mapped_column(
        String(255),
        default="",
        nullable=False,
    )
    # 角色创建时间
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # ---- 关联关系 ----
    # Relationships

    # 角色与用户的多对多关系（通过 user_roles 关联表）
    # lazy="selectin"：查询角色时自动加载关联的用户列表
    users: Mapped[list["User"]] = relationship(
        "User",
        secondary="user_roles",
        back_populates="roles",
        lazy="selectin",
    )
    # 角色与权限的多对多关系（通过 role_permissions 关联表）
    # lazy="selectin"：查询角色时自动加载关联的权限列表
    # 这对于 User.has_permission() 方法的权限检查至关重要
    permissions: Mapped[list["Permission"]] = relationship(
        "Permission",
        secondary="role_permissions",
        back_populates="roles",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        """Return a readable representation for debugging.

        Returns:
            str: Role representation containing id and name.
        """
        # 返回角色对象的可读字符串表示，便于调试和日志输出
        return f"<Role(id={self.id}, name={self.name})>"


class Permission(Base):
    """Permission model for RBAC.

    Represents a fine-grained action on a resource.
    表示对某个资源的细粒度操作权限。
    """
    # 权限模型：定义系统中的细粒度操作权限
    # 每个权限代表对特定资源的特定操作（如"查看文章"、"管理用户"）

    __tablename__ = "permissions"  # 数据库中的表名

    # ---- 主键 ----
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # 权限名称：唯一且带索引，格式为 "资源:操作"
    # 例如：article:read、user:manage、crawler:trigger
    name: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
    )
    # 资源名称：权限所针对的资源类型
    # 带索引，便于按资源类型查询所有相关权限
    # 例如：article、user、crawler、config
    resource: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )
    # 操作类型：对资源允许执行的操作
    # 例如：read、list、create、manage、delete、trigger
    action: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    # 权限描述：人类可读的权限说明
    description: Mapped[str] = mapped_column(
        String(255),
        default="",
        nullable=False,
    )

    # ---- 关联关系 ----
    # Relationships
    # 权限与角色的多对多关系（通过 role_permissions 关联表）
    # back_populates="permissions" 与 Role.permissions 形成双向关系
    roles: Mapped[list["Role"]] = relationship(
        "Role",
        secondary="role_permissions",
        back_populates="permissions",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        """Return a readable representation for debugging.

        Returns:
            str: Permission representation containing id and name.
        """
        # 返回权限对象的可读字符串表示，便于调试和日志输出
        return f"<Permission(id={self.id}, name={self.name})>"


class RolePermission(Base):
    """Association table for role-permission mapping.

    Links roles to permissions in a many-to-many relationship.
    角色与权限的多对多关联表。
    """
    # 角色-权限关联模型：实现角色与权限的多对多关系
    # 使用复合主键（role_id + permission_id）确保同一角色不会被重复分配相同权限

    __tablename__ = "role_permissions"  # 数据库中的关联表名

    # 角色 ID 外键，指向 roles 表的主键
    role_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("roles.id"),
        primary_key=True,
        nullable=False,
    )
    # 权限 ID 外键，指向 permissions 表的主键
    permission_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("permissions.id"),
        primary_key=True,
        nullable=False,
    )
    # 关联创建时间，记录权限被分配给角色的时间点
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


# =============================================================================
# 预定义权限列表
# =============================================================================
# 系统初始化时会根据此列表自动创建权限记录
# 每个权限包含：名称（name）、资源（resource）、操作（action）、描述（description）
# 权限按功能模块分组，涵盖系统所有受控操作

# Predefined permissions
DEFAULT_PERMISSIONS = [
    # ---- 文章（Article）相关权限 ----
    # Article permissions
    {"name": "article:read", "resource": "article", "action": "read", "description": "View articles"},
    {"name": "article:list", "resource": "article", "action": "list", "description": "List articles"},
    # ---- 订阅（Subscription）相关权限 ----
    # Subscription permissions
    {"name": "subscription:create", "resource": "subscription", "action": "create", "description": "Create subscriptions"},
    {"name": "subscription:read", "resource": "subscription", "action": "read", "description": "View own subscriptions"},
    {"name": "subscription:delete", "resource": "subscription", "action": "delete", "description": "Delete subscriptions"},
    # ---- 用户管理（User Management）相关权限 ----
    # User management permissions
    {"name": "user:manage", "resource": "user", "action": "manage", "description": "Manage users"},
    {"name": "user:list", "resource": "user", "action": "list", "description": "List users"},
    # ---- 角色管理（Role Management）相关权限 ----
    # Role management permissions
    {"name": "role:manage", "resource": "role", "action": "manage", "description": "Manage roles"},
    {"name": "role:list", "resource": "role", "action": "list", "description": "List roles"},
    # ---- 爬虫管理（Crawler Management）相关权限 ----
    # Crawler management permissions
    {"name": "crawler:manage", "resource": "crawler", "action": "manage", "description": "Manage crawlers"},
    {"name": "crawler:trigger", "resource": "crawler", "action": "trigger", "description": "Trigger crawl tasks"},
    # ---- 系统配置（Config Management）相关权限 ----
    # Config management permissions
    {"name": "config:manage", "resource": "config", "action": "manage", "description": "Manage system config"},
    {"name": "config:read", "resource": "config", "action": "read", "description": "Read system config"},
    # ---- 备份（Backup）相关权限 ----
    # Backup permissions
    {"name": "backup:manage", "resource": "backup", "action": "manage", "description": "Manage backups"},
    {"name": "backup:restore", "resource": "backup", "action": "restore", "description": "Restore from backup"},
    # ---- AI 处理（AI Processing）相关权限 ----
    # AI processing permissions
    {"name": "ai:process", "resource": "ai_processor", "action": "process", "description": "Trigger AI processing"},
    {"name": "ai:view_stats", "resource": "ai_processor", "action": "view_stats", "description": "View AI token statistics"},
    # ---- 向量嵌入（Embedding）相关权限 ----
    # Embedding permissions
    {"name": "embedding:compute", "resource": "embedding", "action": "compute", "description": "Compute article embeddings"},
    {"name": "embedding:rebuild", "resource": "embedding", "action": "rebuild", "description": "Rebuild Milvus index"},
    # ---- 事件聚类（Event Clustering）相关权限 ----
    # Event clustering permissions
    {"name": "event:read", "resource": "event", "action": "read", "description": "View events"},
    {"name": "event:cluster", "resource": "event", "action": "cluster", "description": "Trigger event clustering"},
    # ---- 主题（Topic）相关权限 ----
    # Topic permissions
    {"name": "topic:read", "resource": "topic", "action": "read", "description": "View topics"},
    {"name": "topic:manage", "resource": "topic", "action": "manage", "description": "Create/update/delete topics"},
    {"name": "topic:discover", "resource": "topic", "action": "discover", "description": "Discover new topics"},
    # ---- 行动项（Action）相关权限 ----
    # Action permissions
    {"name": "action:read", "resource": "action", "action": "read", "description": "View own action items"},
    {"name": "action:manage", "resource": "action", "action": "manage", "description": "Create/update action items"},
    # ---- 报告（Report）相关权限 ----
    # Report permissions
    {"name": "report:read", "resource": "report", "action": "read", "description": "View reports"},
    {"name": "report:generate", "resource": "report", "action": "generate", "description": "Generate reports"},
]

# =============================================================================
# 预定义角色及其默认权限映射
# =============================================================================
# 系统初始化时会根据此字典自动创建角色并分配对应的权限
# 角色从高到低分为四个等级：superuser > admin > user > guest
# 每个角色分配了与其职责相匹配的权限集合

# Predefined roles with their default permissions
DEFAULT_ROLES = {
    # 超级管理员：拥有系统中的所有权限
    "superuser": {
        "description": "Superuser with all permissions",
        "permissions": [p["name"] for p in DEFAULT_PERMISSIONS],
    },
    # 管理员：拥有大部分管理权限，但不包括订阅相关的用户操作权限
    "admin": {
        "description": "Administrator with management permissions",
        "permissions": [
            "article:read", "article:list",
            "user:manage", "user:list",
            "role:list",
            "crawler:manage", "crawler:trigger",
            "config:read", "config:manage",
            "backup:manage",
            # 扩展功能权限
            # Extended feature permissions
            "ai:process", "ai:view_stats",
            "embedding:compute", "embedding:rebuild",
            "event:read", "event:cluster",
            "topic:read", "topic:manage", "topic:discover",
            "action:read", "action:manage",
            "report:read", "report:generate",
        ],
    },
    # 普通用户：拥有基本的读取和个人操作权限
    "user": {
        "description": "Regular user with basic permissions",
        "permissions": [
            "article:read", "article:list",
            "subscription:create", "subscription:read", "subscription:delete",
            # 扩展功能权限
            # Extended feature permissions
            "event:read",
            "topic:read",
            "action:read", "action:manage",
            "report:read", "report:generate",
        ],
    },
    # 访客用户：仅拥有只读访问权限
    "guest": {
        "description": "Guest user with read-only access",
        "permissions": [
            "article:read", "article:list",
        ],
    },
}
