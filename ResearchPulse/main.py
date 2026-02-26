# =============================================================================
# 模块: main.py
# 功能: ResearchPulse v2 应用程序的主入口文件
# 架构角色: 作为整个 FastAPI 应用的启动和编排中心，负责：
#   1. 初始化日志系统
#   2. 管理应用生命周期（启动/关闭）
#   3. 注册所有路由（认证、UI、管理、AI、嵌入、事件、话题、行动、报告）
#   4. 配置中间件（CORS 跨域）
#   5. 初始化数据库默认数据（角色、权限、超级用户）
#   6. 启动和停止定时任务调度器
# =============================================================================
"""Main application entry point for ResearchPulse v2."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

# 数据库相关：初始化、关闭、连接检查
from core.database import init_db, close_db, check_db_connection
# ORM 基础模型
from core.models.base import Base
# 用户模型
from core.models.user import User
# 权限模型：角色、权限定义及默认值
from core.models.permission import Role, Permission, DEFAULT_PERMISSIONS, DEFAULT_ROLES
# 认证模块：路由和认证服务
from apps.auth import router as auth_router, AuthService
# 前端 UI 模块路由
from apps.ui import router as ui_router
# UI 模板初始化函数
from apps.ui.api import init_templates
# 管理后台路由
from apps.admin import router as admin_router
# AI 处理模块路由
from apps.ai_processor import router as ai_router
# 向量嵌入模块路由
from apps.embedding import router as embedding_router
# 事件聚类模块路由
from apps.event import router as event_router
# 话题发现模块路由
from apps.topic import router as topic_router
# 行动项模块路由
from apps.action import router as action_router
# 报告生成模块路由
from apps.report import router as report_router
# 每日 arXiv 报告模块路由
from apps.daily_report.api import router as daily_report_router
# 定时任务调度器的启动和停止函数
from apps.scheduler import start_scheduler, stop_scheduler
# Pipeline models — imported to ensure table is registered with Base.metadata
import apps.pipeline.models  # noqa: F401
# 日志系统初始化
from common.logger import setup_logging
# 全局配置单例
from settings import settings

# 初始化日志系统，根据 settings.debug 决定日志级别
# 第二个参数 None 表示不指定日志文件路径，使用 YAML 配置中的默认值
# Setup logging
setup_logging(settings.debug, None)
# 获取当前模块的 logger 实例
logger = logging.getLogger(__name__)


# =============================================================================
# 后台任务恢复函数
# =============================================================================
async def resume_background_tasks():
    """Resume incomplete background tasks after server restart.

    服务重启后恢复未完成的后台任务。
    对于 pending 或 running 状态的任务，重新启动执行。
    """
    import asyncio
    from sqlalchemy import select
    from core.database import get_session_factory
    from apps.task_manager import BackgroundTask
    from apps.task_manager.service import TaskManager

    session_factory = get_session_factory()
    task_manager = TaskManager()

    async with session_factory() as db:
        # 查找所有未完成的任务
        query = select(BackgroundTask).where(
            BackgroundTask.status.in_(["pending", "running"])
        )
        result = await db.execute(query)
        incomplete_tasks = list(result.scalars().all())

        if not incomplete_tasks:
            return

        logger.info(f"Found {len(incomplete_tasks)} incomplete background tasks")

        for task in incomplete_tasks:
            # 根据任务类型恢复执行
            if task.task_type == "daily_report":
                await _resume_daily_report_task(task, task_manager)
            else:
                # 其他类型任务标记为失败
                await task_manager.fail_task(
                    task.task_id,
                    "任务因服务重启而中断，请手动重新执行"
                )


async def _resume_daily_report_task(task: BackgroundTask, task_manager: TaskManager):
    """Resume a daily report generation task."""
    import asyncio
    from datetime import date
    from apps.daily_report.service import DailyReportService

    params = task.params or {}
    report_date_str = params.get("report_date")
    categories = params.get("categories")

    if not report_date_str:
        await task_manager.fail_task(task.task_id, "任务参数丢失")
        return

    report_date = date.fromisoformat(report_date_str)

    # 定义后台执行的协程
    async def run_generate():
        service = DailyReportService()

        async def update_progress(progress: int, message: str):
            await task_manager.update_progress(task.task_id, progress, message)

        reports = await service.generate_daily_reports(
            report_date=report_date,
            categories=categories,
            progress_callback=update_progress,
        )
        return {
            "report_date": report_date.isoformat(),
            "categories": categories,
            "generated_count": len(reports),
            "report_ids": [r.id for r in reports],
        }

    # 重新启动后台任务
    asyncio.create_task(task_manager.run_in_background(task, run_generate))
    logger.info(f"Resumed daily_report task: {task.task_id}")


# 使用 asynccontextmanager 装饰器定义应用的生命周期管理器
# 这是 FastAPI 推荐的方式，替代了旧版的 on_event("startup") 和 on_event("shutdown")
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # ======================== 启动阶段 ========================
    logger.info("Starting ResearchPulse v2...")

    # 第一步：检查数据库连接是否可用
    # 如果数据库不可达，直接抛出 RuntimeError 阻止应用启动
    if not await check_db_connection():
        logger.error("Database connection failed")
        raise RuntimeError("Cannot connect to database")

    # 第二步：初始化数据库表结构（创建尚不存在的表）
    await init_db()
    logger.info("Database initialized")

    # 第三步：初始化默认数据（角色、权限、超级用户）
    await init_default_data()

    # 第四步：将功能开关和配置项的默认值写入数据库
    # 延迟导入避免循环依赖，feature_config 是模块级单例
    from common.feature_config import feature_config
    await feature_config.seed_defaults()
    logger.info("Feature config defaults seeded")

    # 第五步：初始化 Jinja2 模板引擎
    # 模板目录位于 apps/ui/templates/
    import pathlib
    template_dir = pathlib.Path(__file__).parent / "apps" / "ui" / "templates"
    init_templates(str(template_dir))

    # 第六步：启动后台定时任务调度器（APScheduler）
    # 调度器负责定时爬取、数据清理、备份、AI处理等任务
    await start_scheduler()
    logger.info("Scheduler started")

    # 第七步：恢复未完成的后台任务
    await resume_background_tasks()
    logger.info("Background tasks resumed")

    logger.info("ResearchPulse v2 started successfully")

    # yield 之前是启动逻辑，yield 之后是关闭逻辑
    yield

    # ======================== 关闭阶段 ========================
    logger.info("Shutting down ResearchPulse v2...")
    # 停止调度器，确保正在执行的任务能够优雅完成
    await stop_scheduler()
    # 关闭数据库连接池，释放所有连接资源
    await close_db()
    logger.info("ResearchPulse v2 shutdown complete")


# 创建 FastAPI 应用实例
# title: 应用名称，来自配置文件
# lifespan: 指定生命周期管理器，控制启动和关闭行为
app = FastAPI(
    title=settings.app_name,
    description="Research Paper and Article Aggregator",
    version="2.0.0",
    lifespan=lifespan,
)

# 添加 CORS（跨域资源共享）中间件
# 允许的来源通过 CORS_ORIGINS 环境变量配置（逗号分隔，或 "*" 表示全部）
# 生产环境建议将 CORS_ORIGINS 设为具体的前端域名列表
# 注意: allow_origins=["*"] 时不应启用 allow_credentials=True
# （CORS 规范不允许 credentials + wildcard origins 的组合，浏览器会拒绝响应）
_cors_origins = settings.cors_origins.split(",") if settings.cors_origins != "*" else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 全局异常处理器
# 捕获所有未处理的异常，防止敏感错误信息泄露给客户端
# 统一返回 500 状态码和通用错误消息
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


# =============================================================================
# 路由注册
# 将各模块的路由器挂载到不同的 URL 前缀下
# =============================================================================

# 认证路由：登录、注册、Token 刷新等，挂载到 /api/v1 前缀
app.include_router(auth_router, prefix="/api/v1")

# UI 路由：前端页面渲染，挂载到配置的 URL 前缀下（默认 /researchpulse）
app.include_router(ui_router, prefix=settings.url_prefix)

# 管理后台路由：用户管理、系统配置等，挂载到 /api/v1 前缀
app.include_router(admin_router, prefix="/api/v1")

# 扩展功能模块路由
# 每个模块有独立的 URL 前缀和标签（用于 Swagger 文档分组）
app.include_router(ai_router, prefix="/researchpulse/api/ai", tags=["AI Processing"])          # AI 智能处理
app.include_router(embedding_router, prefix="/researchpulse/api/embedding", tags=["Embedding"])  # 向量嵌入与相似度搜索
app.include_router(event_router, prefix="/researchpulse/api/events", tags=["Events"])            # 事件聚类
app.include_router(topic_router, prefix="/researchpulse/api/topics", tags=["Topics"])            # 话题发现与雷达
app.include_router(action_router, prefix="/researchpulse/api/actions", tags=["Actions"])         # 行动项追踪
app.include_router(report_router, prefix="/researchpulse/api/reports", tags=["Reports"])         # 报告自动生成
app.include_router(daily_report_router, prefix="/researchpulse/api", tags=["Daily Reports"])    # 每日 arXiv 报告


# 健康检查端点
# 用于容器编排（如 Kubernetes）和负载均衡器的健康探测
# 返回应用和数据库的健康状态
@app.get("/health")
async def health_check():
    """Health check endpoint with detailed component status.

    检查应用各组件的健康状态，包括数据库、Redis、Milvus、Ollama。

    Returns:
        Dict[str, Any]: Health status of each component.
    """
    # 检查数据库连接是否正常
    db_ok = await check_db_connection()

    # 检查 Redis 连接（如果配置了）
    redis_ok = await _check_redis_connection()

    # 检查 Milvus 连接（如果配置了）
    milvus_ok = await _check_milvus_connection()

    # 检查 Ollama 连接（如果配置了）
    ollama_ok = await _check_ollama_connection()

    # 综合判断：数据库必须正常，其他可选
    all_healthy = db_ok

    return {
        "status": "healthy" if all_healthy else "unhealthy",
        "components": {
            "database": "connected" if db_ok else "disconnected",
            "redis": "connected" if redis_ok else "disconnected",
            "milvus": "connected" if milvus_ok else "disconnected",
            "ollama": "connected" if ollama_ok else "disconnected",
        },
    }


@app.get("/health/live")
async def liveness_check():
    """Liveness probe for Kubernetes.

    Kubernetes 用存活探针，检查应用是否存活。
    如果返回 200，说明应用正在运行。

    Returns:
        Dict[str, str]: Simple alive status.
    """
    return {"status": "alive"}


@app.get("/health/ready")
async def readiness_check():
    """Readiness probe for Kubernetes.

    Kubernetes 用就绪探针，检查应用是否准备好接收流量。
    数据库必须可用才返回 200。

    Returns:
        Dict[str, Any]: Ready status with database check.
    """
    db_ok = await check_db_connection()
    if not db_ok:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="Database not ready")
    return {"status": "ready"}


async def _check_redis_connection() -> bool:
    """Check Redis connection status.

    检查 Redis 连接状态。

    Returns:
        bool: True if Redis is available or not configured.
    """
    try:
        from settings import settings
        if not settings.redis_host:
            return True  # Redis not configured, treat as OK
        import redis.asyncio as redis
        client = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            password=settings.redis_password or None,
            db=settings.redis_db,
        )
        await client.ping()
        await client.close()
        return True
    except Exception:
        return False


async def _check_milvus_connection() -> bool:
    """Check Milvus connection status.

    检查 Milvus 向量数据库连接状态。

    Returns:
        bool: True if Milvus is available or not configured.
    """
    try:
        from settings import settings
        from pymilvus import connections, utility
        connections.connect(
            alias="health_check",
            host=settings.milvus_host,
            port=settings.milvus_port,
            timeout=5,
        )
        utility.list_collections(using="health_check")
        connections.disconnect("health_check")
        return True
    except Exception:
        return False


async def _check_ollama_connection() -> bool:
    """Check Ollama connection status.

    检查 Ollama 服务连接状态。

    Returns:
        bool: True if Ollama is available or not configured.
    """
    try:
        import httpx
        from settings import settings
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{settings.ollama_host}/api/tags")
            return response.status_code == 200
    except Exception:
        return False


# 根路径页面 —— 导航门户
# 返回 HTML 页面，作为所有服务的入口导航
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
    # 初始化默认角色和权限数据
    # 该函数在应用启动时调用，确保数据库中存在必要的基础数据
    # 使用 INSERT ... 方式只插入不存在的数据，不会覆盖已有数据
    from core.database import get_session_factory
    from sqlalchemy import text

    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            # 第一步：创建权限记录
            # 遍历 DEFAULT_PERMISSIONS 列表，逐条检查并插入
            # 每条权限包含 name（唯一标识）、resource（资源类型）、action（操作类型）、description（描述）
            for perm_data in DEFAULT_PERMISSIONS:
                # 先查询该权限是否已存在，避免重复插入
                result = await session.execute(
                    text("SELECT id FROM permissions WHERE name = :name"), {"name": perm_data["name"]}
                )
                if not result.scalar():
                    await session.execute(
                        text("INSERT INTO permissions (name, resource, action, description) VALUES (:name, :resource, :action, :description)"),
                        {"name": perm_data["name"], "resource": perm_data["resource"], "action": perm_data["action"], "description": perm_data["description"]},
                    )

            # flush 将变更推送到数据库但不提交事务，确保后续能引用到新插入的权限
            await session.flush()

            # 第二步：创建角色记录
            # 遍历 DEFAULT_ROLES 字典，逐个检查并插入角色
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

            # 第三步：为角色分配权限（多对多关系）
            # 使用 INSERT IGNORE 避免重复分配导致报错
            # 通过子查询从 roles 和 permissions 表中获取 ID，实现名称到 ID 的映射
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

            # 第四步：创建超级用户（如果配置了密码）
            # 仅在 settings 中配置了 superuser_password 时才创建
            # 这允许通过环境变量或 .env 文件控制是否创建超级用户
            if settings.superuser_password:
                result = await session.execute(
                    text("SELECT id FROM users WHERE username = :username"), {"username": settings.superuser_username}
                )
                if not result.scalar():
                    # 使用 AuthService 创建超级用户，确保密码经过正确的哈希处理
                    await AuthService.create_superuser(
                        session=session,
                        username=settings.superuser_username,
                        email=settings.superuser_email,
                        password=settings.superuser_password,
                    )
                    logger.info(f"Superuser created: {settings.superuser_username}")

            # 提交事务，将所有变更持久化到数据库
            await session.commit()
        except Exception:
            # 出现任何异常时回滚事务，保持数据一致性
            await session.rollback()
            raise


def run() -> None:
    """Entry point for ``researchpulse`` console script (see pyproject.toml)."""
    # 控制台脚本入口函数
    # 通过 pyproject.toml 中的 [project.scripts] 配置调用
    # 使用 uvicorn 作为 ASGI 服务器运行 FastAPI 应用
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser(description="Run ResearchPulse server")
    parser.add_argument("--host", type=str, default=None, help="Host to bind to")
    parser.add_argument("--port", type=int, default=None, help="Port to bind to")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    args = parser.parse_args()

    # 优先使用命令行参数，其次使用 settings 配置
    host = args.host or settings.app_host
    port = args.port or settings.app_port
    reload = args.reload or settings.debug

    uvicorn.run(
        "main:app",       # 指向本模块的 app 实例
        host=host,        # 监听地址
        port=port,        # 端口
        reload=reload,    # 调试模式下启用热重载
    )


# 直接运行本文件时的入口
if __name__ == "__main__":
    run()
