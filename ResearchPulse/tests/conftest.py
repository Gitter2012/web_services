"""Shared test fixtures for ResearchPulse tests."""

from __future__ import annotations

import os
import sys
from typing import AsyncGenerator, Generator
from contextlib import asynccontextmanager

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

# Ensure ResearchPulse package root is on sys.path so bare imports work
_PROJECT_ROOT = os.path.join(os.path.dirname(__file__), os.pardir)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, os.path.abspath(_PROJECT_ROOT))

# Use in-memory SQLite for tests (faster, no external dependencies)
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


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
    from core.models.permission import DEFAULT_PERMISSIONS, DEFAULT_ROLES

    # Create fresh tables for each test
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
        # Seed default roles and permissions
        try:
            # Create permissions
            for perm_data in DEFAULT_PERMISSIONS:
                await session.execute(
                    text("INSERT INTO permissions (name, resource, action, description) VALUES (:name, :resource, :action, :description)"),
                    perm_data
                )
            await session.flush()

            # Create roles
            for role_name, role_data in DEFAULT_ROLES.items():
                await session.execute(
                    text("INSERT INTO roles (name, description) VALUES (:name, :description)"),
                    {"name": role_name, "description": role_data["description"]}
                )
            await session.flush()

            # Assign permissions to roles
            for role_name, role_data in DEFAULT_ROLES.items():
                for perm_name in role_data["permissions"]:
                    await session.execute(
                        text("""
                            INSERT INTO role_permissions (role_id, permission_id)
                            SELECT r.id, p.id FROM roles r, permissions p
                            WHERE r.name = :role_name AND p.name = :perm_name
                        """),
                        {"role_name": role_name, "perm_name": perm_name}
                    )

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
    from fastapi import FastAPI
    from main import app
    from core.database import get_session
    from core.models.base import Base
    from core.models.permission import DEFAULT_PERMISSIONS, DEFAULT_ROLES

    # Create test engine
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        future=True,
    )

    # Create session factory
    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    # Override the database session dependency
    async def override_get_session():
        # Create tables for this test
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with session_factory() as session:
            # Seed default data
            try:
                for perm_data in DEFAULT_PERMISSIONS:
                    await session.execute(
                        text("INSERT INTO permissions (name, resource, action, description) VALUES (:name, :resource, :action, :description)"),
                        perm_data
                    )
                await session.flush()

                for role_name, role_data in DEFAULT_ROLES.items():
                    await session.execute(
                        text("INSERT INTO roles (name, description) VALUES (:name, :description)"),
                        {"name": role_name, "description": role_data["description"]}
                    )
                await session.flush()

                for role_name, role_data in DEFAULT_ROLES.items():
                    for perm_name in role_data["permissions"]:
                        await session.execute(
                            text("""
                                INSERT INTO role_permissions (role_id, permission_id)
                                SELECT r.id, p.id FROM roles r, permissions p
                                WHERE r.name = :role_name AND p.name = :perm_name
                            """),
                            {"role_name": role_name, "perm_name": perm_name}
                        )

                await session.commit()
            except Exception:
                await session.rollback()

            yield session

    # Create a minimal test app with the same routes but no lifespan
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

    # Override the database session dependency
    test_app.dependency_overrides[get_session] = override_get_session

    with TestClient(test_app, raise_server_exceptions=False) as test_client:
        yield test_client

    test_app.dependency_overrides.clear()


@pytest.fixture
def auth_headers(client: TestClient, test_user_data: dict) -> dict:
    """Build authorization headers for authenticated requests.

    注册并登录测试用户后返回带 Bearer 令牌的请求头。

    Args:
        client: TestClient instance.
        test_user_data: User payload for registration.

    Returns:
        dict: Authorization header dictionary.
    """
    # Register user
    client.post(
        "/api/v1/auth/register",
        json=test_user_data,
    )

    # Login
    response = client.post(
        "/api/v1/auth/login",
        json={
            "username": test_user_data["username"],
            "password": test_user_data["password"],
        },
    )

    access_token = response.json()["access_token"]
    return {"Authorization": f"Bearer {access_token}"}


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
