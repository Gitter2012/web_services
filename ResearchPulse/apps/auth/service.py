# ==========================================================================
# 认证服务模块
# --------------------------------------------------------------------------
# 本模块是 ResearchPulse 系统认证功能的核心业务逻辑层。
# 封装了所有与用户身份认证相关的操作，包括：
#   1. 用户注册 —— 唯一性校验、密码哈希、默认角色分配
#   2. 用户登录 —— 凭据验证、JWT 令牌生成、最后登录时间更新
#   3. 令牌刷新 —— refresh_token 校验与新令牌对生成
#   4. 密码修改 —— 旧密码验证与新密码设置
#   5. 用户查询 —— 按 ID 或用户名检索用户
#   6. 超级用户创建 —— 初始化系统管理员账户
#
# 设计决策：
#   - 采用静态方法 (staticmethod) 设计，AuthService 作为无状态的服务类
#     不持有实例属性，所有状态通过参数传入（数据库会话、用户对象等）
#   - 业务校验失败统一抛出 ValueError，由上层 API 路由统一转换为 HTTP 错误响应
#   - 密码处理委托给 User 模型的 set_password / check_password 方法
#   - JWT 生成委托给 core.security 模块的工具函数
#
# 架构位置：
#   本模块位于 apps/auth/service.py，属于"认证应用"(auth app) 的服务层。
#   被 api.py 路由层调用，依赖 core.models（ORM 模型）和
#   core.security（安全工具）模块。
# ==========================================================================

"""Authentication service for ResearchPulse v2."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models.permission import Role
from core.models.user import User
from core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# 认证服务类
# --------------------------------------------------------------------------
# AuthService 是一个纯逻辑的服务类，不持有任何状态。
# 所有方法均为 staticmethod，通过参数注入数据库会话等依赖。
# 这种设计使得服务层易于测试（无需实例化）且线程安全。
class AuthService:
    """Service class for authentication operations.

    认证业务逻辑服务类，提供注册、登录、刷新令牌与密码修改等功能。
    """

    # ------------------------------------------------------------------
    # 用户注册
    # ------------------------------------------------------------------
    @staticmethod
    async def register(
        session: AsyncSession,          # 异步数据库会话
        username: str,                  # 用户名（将被转为小写）
        email: str,                     # 邮箱地址（将被转为小写）
        password: str,                  # 明文密码（将被哈希处理后存储）
        assign_default_role: bool = True,  # 是否自动分配默认角色，默认为 True
    ) -> User:
        """Register a new user.

        注册新用户，进行唯一性校验、密码哈希与默认角色分配。

        Args:
            session: Async database session.
            username: Username (will be lowercased).
            email: Email address (will be lowercased).
            password: Plaintext password.
            assign_default_role: Whether to assign the default "user" role.

        Returns:
            User: Newly created user.

        Raises:
            ValueError: If username or email already exists.
        """
        # 检查用户名或邮箱是否已被注册
        # 使用 OR 查询同时匹配两个字段，减少数据库查询次数
        result = await session.execute(
            select(User).where(
                or_(User.username == username.lower(), User.email == email.lower())
            )
        )
        existing_user = result.scalar_one_or_none()
        if existing_user:
            # 区分错误信息：告知用户是用户名还是邮箱已被占用
            if existing_user.username == username.lower():
                raise ValueError("Username already exists")
            raise ValueError("Email already exists")

        # 创建新用户对象
        # 用户名和邮箱统一转小写，确保全局唯一性检查不受大小写影响
        user = User(
            username=username.lower(),
            email=email.lower(),
            is_active=True,        # 新用户默认激活
            is_superuser=False,    # 普通注册用户不是超级管理员
        )
        # 使用 User 模型的 set_password 方法进行密码哈希（内部使用 bcrypt 等算法）
        user.set_password(password)

        # 为新用户分配默认的 "user" 角色
        # 设计决策：默认角色机制确保所有新用户都有基础权限
        if assign_default_role:
            result = await session.execute(select(Role).where(Role.name == "user"))
            default_role = result.scalar_one_or_none()
            if default_role:
                user.roles.append(default_role)

        # 将用户添加到数据库会话
        session.add(user)
        # flush 而非 commit：将变更刷入数据库但不提交事务
        # 这样调用者可以在更大的事务中控制提交时机
        await session.flush()
        # 刷新用户对象，获取数据库生成的字段（如 id、created_at）
        await session.refresh(user)

        logger.info(f"User registered: {username}")
        return user

    # ------------------------------------------------------------------
    # 用户登录
    # ------------------------------------------------------------------
    @staticmethod
    async def login(
        session: AsyncSession,
        username: str,   # 用户名或邮箱（支持两种方式登录）
        password: str,   # 明文密码
    ) -> tuple[User, str, str]:
        """Authenticate user and return tokens.

        验证用户凭据并生成访问/刷新令牌，同时更新最后登录时间。

        Args:
            session: Async database session.
            username: Username or email.
            password: Plaintext password.

        Returns:
            tuple[User, str, str]: (user, access_token, refresh_token).

        Raises:
            ValueError: If credentials are invalid or account is disabled.
        """
        # 通过用户名或邮箱查找用户
        # 支持两种登录方式提升用户体验：用户可以用用户名或邮箱登录
        result = await session.execute(
            select(User).where(
                or_(
                    User.username == username.lower(),
                    User.email == username.lower(),
                )
            )
        )
        user = result.scalar_one_or_none()

        # 用户不存在时返回通用错误信息，不暴露具体原因（安全考虑）
        if not user:
            raise ValueError("Invalid credentials")

        # 检查账户是否被禁用
        if not user.is_active:
            raise ValueError("Account is disabled")

        # 校验密码是否正确
        if not user.check_password(password):
            raise ValueError("Invalid credentials")

        # 更新最后登录时间
        user.update_last_login()

        # 生成 JWT 令牌对
        # token_data 中的 "sub"（subject）字段存放用户 ID，是 JWT 标准声明
        token_data = {"sub": str(user.id)}
        access_token = create_access_token(token_data)    # 短期有效的访问令牌
        refresh_token = create_refresh_token(token_data)  # 长期有效的刷新令牌

        logger.info(f"User logged in: {user.username}")
        return user, access_token, refresh_token

    # ------------------------------------------------------------------
    # 令牌刷新
    # ------------------------------------------------------------------
    @staticmethod
    async def refresh_tokens(
        session: AsyncSession,
        refresh_token: str,  # 客户端提供的刷新令牌
    ) -> tuple[str, str]:
        """Refresh access token using a refresh token.

        验证刷新令牌并生成新的访问/刷新令牌对。

        Args:
            session: Async database session.
            refresh_token: Refresh token string.

        Returns:
            tuple[str, str]: (new_access_token, new_refresh_token).

        Raises:
            ValueError: If token is invalid or user is inactive/missing.
        """
        # 解码并验证 refresh_token 的有效性（签名、过期时间等）
        payload = decode_token(refresh_token)
        if not payload:
            raise ValueError("Invalid refresh token")

        # 校验令牌类型：必须是 "refresh" 类型，防止用 access_token 冒充
        if payload.get("type") != "refresh":
            raise ValueError("Invalid token type")

        # 从令牌载荷中提取用户 ID
        user_id = payload.get("sub")
        if not user_id:
            raise ValueError("Invalid token payload")

        # 根据用户 ID 查询用户，确认用户仍然存在且处于活跃状态
        # 这一步很重要：即使 refresh_token 有效，被禁用的用户也不应获得新令牌
        result = await session.execute(select(User).where(User.id == int(user_id)))
        user = result.scalar_one_or_none()

        if not user or not user.is_active:
            raise ValueError("User not found or inactive")

        # 生成全新的令牌对（access_token + refresh_token）
        # 每次刷新都生成新的 refresh_token，实现"令牌轮换"策略
        # 这增强了安全性：旧的 refresh_token 虽然不会被主动失效，
        # 但在令牌过期后自然失效
        token_data = {"sub": str(user.id)}
        new_access_token = create_access_token(token_data)
        new_refresh_token = create_refresh_token(token_data)

        return new_access_token, new_refresh_token

    # ------------------------------------------------------------------
    # 密码修改
    # ------------------------------------------------------------------
    @staticmethod
    async def change_password(
        session: AsyncSession,
        user: User,              # 当前已认证的用户对象
        current_password: str,   # 当前密码（用于二次验证身份）
        new_password: str,       # 新密码
    ) -> None:
        """Change user's password.

        验证当前密码并设置新密码。

        Args:
            session: Async database session.
            user: Authenticated user.
            current_password: Current plaintext password.
            new_password: New plaintext password.

        Raises:
            ValueError: If current password is incorrect.
        """
        # 先验证当前密码是否正确，防止令牌被盗后恶意修改密码
        if not user.check_password(current_password):
            raise ValueError("Current password is incorrect")

        # 设置新密码（内部会进行哈希处理）
        user.set_password(new_password)
        logger.info(f"Password changed for user: {user.username}")

    # ------------------------------------------------------------------
    # 按 ID 查询用户
    # ------------------------------------------------------------------
    @staticmethod
    async def get_user_by_id(session: AsyncSession, user_id: int) -> User | None:
        """Get user by ID.

        Args:
            session: Async database session.
            user_id: User ID.

        Returns:
            User | None: User instance or ``None`` if not found.
        """
        # 根据用户主键 ID 查询，返回用户对象或 None
        result = await session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # 按用户名查询用户
    # ------------------------------------------------------------------
    @staticmethod
    async def get_user_by_username(
        session: AsyncSession, username: str
    ) -> User | None:
        """Get user by username.

        Args:
            session: Async database session.
            username: Username to look up.

        Returns:
            User | None: User instance or ``None`` if not found.
        """
        # 根据用户名精确查询，返回用户对象或 None
        result = await session.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # 创建超级管理员
    # ------------------------------------------------------------------
    @staticmethod
    async def create_superuser(
        session: AsyncSession,
        username: str,   # 超级管理员用户名
        email: str,      # 超级管理员邮箱
        password: str,   # 超级管理员密码
    ) -> User:
        """Create a superuser account.

        创建具备最高权限的超级管理员账户，并分配 "superuser" 角色。

        Args:
            session: Async database session.
            username: Superuser username.
            email: Superuser email.
            password: Superuser password.

        Returns:
            User: Newly created superuser.
        """
        # 创建超级管理员用户对象
        # 与普通注册不同：is_superuser=True，拥有系统最高权限
        user = User(
            username=username.lower(),
            email=email.lower(),
            is_active=True,
            is_superuser=True,   # 标记为超级管理员
        )
        user.set_password(password)

        # 分配 "superuser" 角色
        # 设计决策：超级管理员既通过 is_superuser 标志位判断，也通过角色系统判断
        # 双重机制确保权限检查的灵活性和向后兼容性
        result = await session.execute(select(Role).where(Role.name == "superuser"))
        superuser_role = result.scalar_one_or_none()
        if superuser_role:
            user.roles.append(superuser_role)

        session.add(user)
        await session.flush()
        await session.refresh(user)

        logger.info(f"Superuser created: {username}")
        return user
