"""Shared test fixtures for ResearchPulse tests."""

from __future__ import annotations

import os
import sys
import time
from typing import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text, event, BigInteger, Integer
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

# Ensure ResearchPulse package root is on sys.path so bare imports work
_PROJECT_ROOT = os.path.join(os.path.dirname(__file__), os.pardir)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, os.path.abspath(_PROJECT_ROOT))

# Use in-memory SQLite for tests (faster, no external dependencies)
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


# Fix BigInteger autoincrement on SQLite: BigInteger maps to BIGINT which
# doesn't support autoincrement in SQLite.  Only the exact type name INTEGER
# gets the special ROWID alias behaviour.  We register a compilation hook so
# that BigInteger renders as INTEGER on the sqlite dialect.
from sqlalchemy.ext.compiler import compiles as _compiles  # noqa: E402

@_compiles(BigInteger, "sqlite")
def _compile_big_int_sqlite(type_, compiler, **kw):
    return "INTEGER"


# ---------------------------------------------------------------------------
# Module-level variable to share the test engine between the ``client``
# fixture and helper fixtures (admin_headers, superuser_headers).
# With StaticPool, all connections share the same in-memory SQLite database.
# ---------------------------------------------------------------------------
_test_engine = None


@pytest.fixture(scope="session")
def event_loop_policy():
    """Configure the asyncio event loop policy for tests.

    为异步测试配置默认事件循环策略。

    Returns:
        asyncio.AbstractEventLoopPolicy: Event loop policy instance.
    """
    import asyncio
    return asyncio.DefaultEventLoopPolicy()


@pytest.fixture(scope="session")
def test_engine():
    """Create an async test database engine.

    创建用于测试的异步数据库引擎实例。

    Returns:
        sqlalchemy.ext.asyncio.AsyncEngine: Async test engine.
    """
    from core.models.base import Base

    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        future=True,
        # Use StaticPool to ensure all connections share the same in-memory
        # SQLite database, preventing "index already exists" errors when
        # drop_all/create_all are called across different connections.
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    return engine


@pytest_asyncio.fixture(scope="session")
async def setup_test_db(test_engine):
    """Initialize the test database schema.

    创建测试数据库中的所有表，并在会话结束后清理。

    Args:
        test_engine: Async test database engine.

    Returns:
        sqlalchemy.ext.asyncio.AsyncEngine: Engine with initialized schema.
    """
    from core.models.base import Base

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield test_engine

    # Cleanup
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db_session(setup_test_db) -> AsyncGenerator[AsyncSession, None]:
    """Provide an isolated database session per test.

    为每个测试提供独立数据库会话并重建基础数据。

    Args:
        setup_test_db: Initialized async engine fixture.

    Returns:
        AsyncGenerator[AsyncSession, None]: Async session generator.
    """
    from core.models.base import Base
    from core.models.permission import (
        DEFAULT_PERMISSIONS, DEFAULT_ROLES,
        Permission, Role, RolePermission,
    )
    # Import User model to ensure user_roles association table is registered
    # before SQLAlchemy tries to configure mapper relationships.
    from core.models.user import User  # noqa: F401

    # Recreate all tables for each test
    async with setup_test_db.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    # Create session factory
    session_factory = async_sessionmaker(
        setup_test_db,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with session_factory() as session:
        # Seed default roles and permissions using ORM models
        # (raw SQL doesn't work with BigInteger autoincrement on SQLite)
        try:
            # Create permissions
            perm_objs = {}
            for perm_data in DEFAULT_PERMISSIONS:
                perm = Permission(
                    name=perm_data["name"],
                    resource=perm_data["resource"],
                    action=perm_data["action"],
                    description=perm_data["description"],
                )
                session.add(perm)
                perm_objs[perm_data["name"]] = perm
            await session.flush()

            # Create roles and assign permissions
            for role_name, role_data in DEFAULT_ROLES.items():
                role = Role(
                    name=role_name,
                    description=role_data["description"],
                )
                # Attach permission objects to the role relationship
                for perm_name in role_data["permissions"]:
                    if perm_name in perm_objs:
                        role.permissions.append(perm_objs[perm_name])
                session.add(role)

            await session.commit()
        except Exception as e:
            await session.rollback()
            raise

        yield session

        # Rollback any uncommitted changes
        await session.rollback()


@pytest.fixture
def test_user_data() -> dict:
    """Provide a default test user payload.

    提供默认的测试用户数据字典。

    Returns:
        dict: Test user fields for registration/login.
    """
    return {
        "username": "testuser",
        "email": "test@example.com",
        "password": "password123",
    }


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession, test_user_data: dict):
    """Create a test user in the database.

    在数据库中创建并提交测试用户。

    Args:
        db_session: Async database session.
        test_user_data: User payload for registration.

    Returns:
        core.models.user.User: Created user instance.
    """
    from apps.auth.service import AuthService

    user = await AuthService.register(
        session=db_session,
        username=test_user_data["username"],
        email=test_user_data["email"],
        password=test_user_data["password"],
    )
    await db_session.commit()
    return user


@pytest.fixture
def client(test_user_data: dict) -> Generator[TestClient, None, None]:
    """Provide a FastAPI test client with DB overrides.

    构建测试客户端并覆盖数据库依赖，禁用生命周期事件。

    Args:
        test_user_data: Default user payload for auth setup.

    Returns:
        Generator[TestClient, None, None]: Synchronous test client.
    """
    global _test_engine

    from fastapi import Depends, FastAPI
    from main import app
    from core.database import get_session
    from core.models.base import Base
    from core.models.permission import DEFAULT_PERMISSIONS, DEFAULT_ROLES

    # Create test engine
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    # Create session factory
    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    # Expose engine for helper fixtures
    _test_engine = engine

    # Track whether the DB has been seeded
    _seeded = False

    # Override the database session dependency
    async def override_get_session():
        nonlocal _seeded

        if not _seeded:
            # Create tables and seed default data (first request triggers this)
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            async with session_factory() as seed_session:
                from core.models.permission import Permission, Role
                from core.models.user import User  # noqa: F401 — registers user_roles

                perm_objs = {}
                for perm_data in DEFAULT_PERMISSIONS:
                    perm = Permission(
                        name=perm_data["name"],
                        resource=perm_data["resource"],
                        action=perm_data["action"],
                        description=perm_data["description"],
                    )
                    seed_session.add(perm)
                    perm_objs[perm_data["name"]] = perm
                await seed_session.flush()

                for role_name, role_data in DEFAULT_ROLES.items():
                    role = Role(
                        name=role_name,
                        description=role_data["description"],
                    )
                    for perm_name in role_data["permissions"]:
                        if perm_name in perm_objs:
                            role.permissions.append(perm_objs[perm_name])
                    seed_session.add(role)

                await seed_session.commit()
                _seeded = True

        async with session_factory() as session:
            yield session
            # Auto-commit after each request so that changes (e.g. user
            # registration) are persisted across requests in the same
            # in-memory SQLite database.
            await session.commit()
    test_app = FastAPI(title=app.title)

    # Copy middleware
    for middleware in app.user_middleware:
        test_app.user_middleware.append(middleware)

    # Copy exception handlers
    for exc_class, handler in app.exception_handlers.items():
        test_app.add_exception_handler(exc_class, handler)

    # Copy routes
    for route in app.routes:
        test_app.routes.append(route)

    # ----- Test-only utility endpoint for modifying user roles/flags -----
    # This runs within the same session pipeline as regular endpoints,
    # so it shares the in-memory SQLite connection.
    @test_app.post("/_test/modify-user")
    async def _test_modify_user(
        payload: dict,
        session: AsyncSession = Depends(get_session),
    ):
        username = payload["username"]
        action = payload["action"]

        if action == "add_role":
            role_name = payload["role"]
            await session.execute(
                text(
                    "INSERT INTO user_roles (user_id, role_id, created_at) "
                    "SELECT u.id, r.id, CURRENT_TIMESTAMP FROM users u, roles r "
                    "WHERE u.username = :username AND r.name = :role"
                ),
                {"username": username, "role": role_name},
            )
        elif action == "remove_role":
            role_name = payload["role"]
            await session.execute(
                text(
                    "DELETE FROM user_roles WHERE user_id = "
                    "(SELECT id FROM users WHERE username = :username) "
                    "AND role_id = (SELECT id FROM roles WHERE name = :role)"
                ),
                {"username": username, "role": role_name},
            )
        elif action == "set_superuser":
            await session.execute(
                text("UPDATE users SET is_superuser = 1 WHERE username = :username"),
                {"username": username},
            )

        await session.commit()
        return {"ok": True}

    # Override on BOTH the original app and test_app to ensure the override
    # is found regardless of which dependency resolution path is used.
    app.dependency_overrides[get_session] = override_get_session
    test_app.dependency_overrides[get_session] = override_get_session

    with TestClient(test_app, raise_server_exceptions=False) as test_client:
        # Trigger DB initialization with a dummy request before yielding.
        # This ensures tables and seed data exist when helper fixtures
        # (e.g. _register_and_login) run.
        test_client.get("/api/v1/auth/me")
        yield test_client

    app.dependency_overrides.clear()
    test_app.dependency_overrides.clear()
    _test_engine = None


@pytest.fixture
def auth_headers(client: TestClient, test_user_data: dict) -> dict:
    """Build authorization headers for authenticated requests.

    在测试数据库中直接创建用户并登录，返回带 Bearer 令牌的请求头。
    注册用户默认分配 "user" 角色。

    Args:
        client: TestClient instance.
        test_user_data: User payload for registration.

    Returns:
        dict: Authorization header dictionary.
    """
    token = _register_and_login(
        client,
        test_user_data["username"],
        test_user_data["email"],
        test_user_data["password"],
    )
    return {"Authorization": f"Bearer {token}"}


# Async client for async tests
@pytest_asyncio.fixture
async def async_client(setup_test_db) -> AsyncGenerator[AsyncClient, None]:
    """Provide an async test client.

    创建带依赖覆盖的异步 HTTP 客户端用于测试。

    Args:
        setup_test_db: Initialized async engine fixture.

    Returns:
        AsyncGenerator[AsyncClient, None]: Async HTTP client generator.
    """
    from main import app
    from core.database import get_session

    # Create session factory
    session_factory = async_sessionmaker(
        setup_test_db,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async def override_get_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


# =========================================================================
# Feature toggle and role-based fixtures (RBAC testing support)
# =========================================================================

@pytest.fixture(autouse=True)
def enable_features():
    """Enable all feature toggles for tests.

    在测试期间启用所有功能开关，避免端点因功能未开启返回 503。
    通过直接写入内存缓存绕过数据库查询。
    """
    from common.feature_config import feature_config

    original_cache = feature_config._cache.copy()
    original_ts = feature_config._cache_ts

    feature_config._cache.update({
        "feature.ai_processor": "true",
        "feature.embedding": "true",
        "feature.event_clustering": "true",
        "feature.topic_radar": "true",
        "feature.action_items": "true",
        "feature.report_generation": "true",
        "feature.crawler": "true",
        "feature.backup": "true",
        "feature.cleanup": "true",
        "feature.email_notification": "true",
    })
    feature_config._cache_ts = time.monotonic()

    yield

    feature_config._cache = original_cache
    feature_config._cache_ts = original_ts


@pytest.fixture(autouse=True)
def mock_verification_service():
    """Mock email verification service for all tests.

    在测试期间 mock 邮箱验证服务，使注册端点不需要真实的验证令牌。
    """
    from unittest.mock import patch

    with patch(
        "apps.auth.verification_service.VerificationService.validate_verification_token",
        return_value=True,
    ), patch(
        "apps.auth.verification_service.VerificationService.cleanup_verification_data",
        return_value=None,
    ):
        yield


def _register_and_login(
    client: TestClient, username: str, email: str, password: str
) -> str:
    """Register a user via the API and return an access token.

    通过 API 注册用户（VerificationService 已被 mock），然后登录获取 JWT。

    Args:
        client: TestClient instance.
        username: Username for registration.
        email: Email for registration.
        password: Password for registration.

    Returns:
        str: JWT access token.
    """
    reg_resp = client.post(
        "/api/v1/auth/register",
        json={
            "username": username,
            "email": email,
            "password": password,
            "verification_token": "test-token",
        },
    )
    if reg_resp.status_code not in (200, 201):
        raise RuntimeError(
            f"Registration failed for {username}: "
            f"status={reg_resp.status_code} {reg_resp.text}"
        )

    login_resp = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    data = login_resp.json()
    if "access_token" not in data:
        raise RuntimeError(
            f"Login failed for {username}: "
            f"login={login_resp.status_code} {login_resp.text}"
        )
    return data["access_token"]



@pytest.fixture
def admin_headers(client: TestClient) -> dict:
    """Build authorization headers for an admin user.

    注册用户并在数据库中分配 admin 角色，然后返回 Bearer 令牌请求头。
    admin 角色拥有 22 个权限，包含所有扩展功能权限。

    Args:
        client: TestClient instance.

    Returns:
        dict: Authorization header dictionary.
    """
    token = _register_and_login(
        client, "adminuser", "admin@example.com", "password123"
    )

    # Assign admin role to the user via test utility endpoint
    client.post("/_test/modify-user", json={
        "username": "adminuser", "action": "add_role", "role": "admin"
    })

    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def guest_headers(client: TestClient) -> dict:
    """Build authorization headers for a guest-only user.

    注册用户后将其角色从 user 替换为 guest（仅 article:read/list），
    用于验证“已认证但缺少特定权限”的 403 场景。

    Args:
        client: TestClient instance.

    Returns:
        dict: Authorization header dictionary.
    """
    token = _register_and_login(
        client, "guestuser", "guest@example.com", "password123"
    )

    # Remove default "user" role, assign "guest" only
    client.post("/_test/modify-user", json={
        "username": "guestuser", "action": "remove_role", "role": "user"
    })
    client.post("/_test/modify-user", json={
        "username": "guestuser", "action": "add_role", "role": "guest"
    })

    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def superuser_headers(client: TestClient) -> dict:
    """Build authorization headers for a superuser.

    注册用户并设置 is_superuser=True，返回 Bearer 令牌请求头。
    superuser 拥有所有权限（require_permissions 直接放行）。

    Args:
        client: TestClient instance.

    Returns:
        dict: Authorization header dictionary.
    """
    token = _register_and_login(
        client, "superadmin", "super@example.com", "password123"
    )

    # Set is_superuser flag via test utility endpoint
    client.post("/_test/modify-user", json={
        "username": "superadmin", "action": "set_superuser"
    })

    return {"Authorization": f"Bearer {token}"}
