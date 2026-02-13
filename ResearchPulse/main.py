"""Main application entry point for ResearchPulse v2."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

from core.database import init_db, close_db, check_db_connection
from core.models.base import Base
from core.models.user import User
from core.models.permission import Role, Permission, DEFAULT_PERMISSIONS, DEFAULT_ROLES
from apps.auth import router as auth_router, AuthService
from apps.ui import router as ui_router
from apps.ui.api import init_templates
from apps.admin import router as admin_router
from apps.scheduler import start_scheduler, stop_scheduler
from common.logger import setup_logging
from settings import settings

# Setup logging
setup_logging(settings.debug, None)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    logger.info("Starting ResearchPulse v2...")

    # Check database connection
    if not await check_db_connection():
        logger.error("Database connection failed")
        raise RuntimeError("Cannot connect to database")

    # Initialize database tables
    await init_db()
    logger.info("Database initialized")

    # Initialize default data (roles, permissions)
    await init_default_data()

    # Initialize templates
    import pathlib
    template_dir = pathlib.Path(__file__).parent / "apps" / "ui" / "templates"
    init_templates(str(template_dir))

    # Start scheduler
    await start_scheduler()
    logger.info("Scheduler started")

    logger.info("ResearchPulse v2 started successfully")

    yield

    # Shutdown
    logger.info("Shutting down ResearchPulse v2...")
    await stop_scheduler()
    await close_db()
    logger.info("ResearchPulse v2 shutdown complete")


# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    description="Research Paper and Article Aggregator",
    version="2.0.0",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


# Include routers
# Auth routes (no prefix)
app.include_router(auth_router, prefix="/api/v1")

# UI routes (under researchpulse prefix)
app.include_router(ui_router, prefix=settings.url_prefix)

# Admin routes (under admin prefix)
app.include_router(admin_router, prefix="/api/v1")


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    db_ok = await check_db_connection()
    return {
        "status": "healthy" if db_ok else "unhealthy",
        "database": "connected" if db_ok else "disconnected",
    }


# Root page - Navigation portal
@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """Home page - Navigation portal for all services."""
    from fastapi.responses import HTMLResponse
    from apps.ui.api import _templates
    return _templates.TemplateResponse(
        "home.html",
        {"request": request}
    )


async def init_default_data():
    """Initialize default roles and permissions."""
    from core.database import get_session_factory
    from sqlalchemy import text

    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            # Create permissions
            for perm_data in DEFAULT_PERMISSIONS:
                result = await session.execute(
                    text("SELECT id FROM permissions WHERE name = :name"), {"name": perm_data["name"]}
                )
                if not result.scalar():
                    await session.execute(
                        text("INSERT INTO permissions (name, resource, action, description) VALUES (:name, :resource, :action, :description)"),
                        {"name": perm_data["name"], "resource": perm_data["resource"], "action": perm_data["action"], "description": perm_data["description"]},
                    )

            await session.flush()

            # Create roles
            for role_name, role_data in DEFAULT_ROLES.items():
                result = await session.execute(
                    text("SELECT id FROM roles WHERE name = :name"), {"name": role_name}
                )
                if not result.scalar():
                    await session.execute(
                        text("INSERT INTO roles (name, description) VALUES (:name, :description)"),
                        {"name": role_name, "description": role_data["description"]},
                    )

            await session.flush()

            # Assign permissions to roles
            for role_name, role_data in DEFAULT_ROLES.items():
                for perm_name in role_data["permissions"]:
                    await session.execute(
                        text("""
                            INSERT IGNORE INTO role_permissions (role_id, permission_id)
                            SELECT r.id, p.id FROM roles r, permissions p
                            WHERE r.name = :role_name AND p.name = :perm_name
                            """),
                        {"role_name": role_name, "perm_name": perm_name},
                    )

            # Create superuser if configured
            if settings.superuser_password:
                result = await session.execute(
                    text("SELECT id FROM users WHERE username = :username"), {"username": settings.superuser_username}
                )
                if not result.scalar():
                    await AuthService.create_superuser(
                        session=session,
                        username=settings.superuser_username,
                        email=settings.superuser_email,
                        password=settings.superuser_password,
                    )
                    logger.info(f"Superuser created: {settings.superuser_username}")

            await session.commit()
        except Exception:
            await session.rollback()
            raise


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
    )
