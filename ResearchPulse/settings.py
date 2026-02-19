# =============================================================================
# 模块: settings.py
# 功能: ResearchPulse v2 的全局应用配置模块
# 架构角色: 作为整个应用的配置中枢，提供统一的配置管理。
#   采用分层配置优先级机制，从高到低依次为：
#   1. 环境变量（运行时覆盖，适用于容器化部署）
#   2. .env 文件（存放敏感信息如密码、API密钥）
#   3. config/defaults.yaml（非敏感默认值）
#   4. Python 代码中的硬编码默认值（兜底方案）
#
# 设计决策:
#   - 使用 pydantic-settings 的 BaseSettings 实现类型安全的配置
#   - YAML 文件在模块加载时一次性读取并缓存到模块级变量中
#   - validation_alias 用于将大写的环境变量名映射到小写的 Python 属性名
#   - 敏感信息（数据库密码、JWT密钥、API密钥等）不在 YAML 中设默认值，
#     而是通过环境变量或 .env 文件注入
# =============================================================================
"""Global application settings for ResearchPulse v2.

Configuration precedence (highest to lowest):
1. Environment variables (runtime override)
2. .env file (secrets)
3. config/defaults.yaml (non-sensitive defaults)
4. Hardcoded Python defaults (fallback)
"""

from __future__ import annotations

import secrets
from pathlib import Path
from typing import List, Optional

import yaml
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# 项目根目录（settings.py 所在目录）
BASE_DIR = Path(__file__).resolve().parent
# 配置文件目录
CONFIG_DIR = BASE_DIR / "config"


def load_yaml_config() -> dict:
    """Load configuration from defaults.yaml.

    从 YAML 配置文件加载默认配置。
    如果文件不存在则返回空字典，不会抛出异常。

    返回值:
        dict: YAML 文件内容解析后的字典，文件不存在或为空时返回 {}
    """
    config_path = CONFIG_DIR / "defaults.yaml"
    if not config_path.exists():
        return {}
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


# 模块加载时一次性读取 YAML 配置并缓存
# 后续各 Field 的 default 值直接从这些缓存字典中读取
_yaml_config = load_yaml_config()
# 从 YAML 中提取各配置段（section），每段对应一个功能模块
_app_config = _yaml_config.get("app", {})                # 应用基本配置
_db_config = _yaml_config.get("database", {})             # 数据库配置
_cache_config = _yaml_config.get("cache", {})             # Redis 缓存配置
_jwt_config = _yaml_config.get("jwt", {})                 # JWT 认证配置
_crawler_config = _yaml_config.get("crawler", {})         # 爬虫配置
_scheduler_config = _yaml_config.get("scheduler", {})     # 定时任务调度配置
_retention_config = _yaml_config.get("data_retention", {})  # 数据保留策略配置
_email_config = _yaml_config.get("email", {})             # 邮件服务配置
_ai_config = _yaml_config.get("ai_processor", {})         # AI 处理器配置
_embedding_config = _yaml_config.get("embedding", {})     # 向量嵌入配置
_event_config = _yaml_config.get("event", {})             # 事件聚类配置
_topic_config = _yaml_config.get("topic", {})             # 话题发现配置
_action_config = _yaml_config.get("action", {})           # 行动项配置
_report_config = _yaml_config.get("report", {})           # 报告生成配置
_weibo_config = _crawler_config.get("weibo", {})         # 微博热搜爬虫配置


def _get_default_data_dir() -> Path:
    """Get default data directory.

    获取默认的数据存储目录。
    如果 YAML 中配置的路径是相对路径，则基于 BASE_DIR 转换为绝对路径。

    返回值:
        Path: 数据目录的绝对路径
    """
    yaml_dir = _app_config.get("data_dir", "./data")
    path = Path(yaml_dir)
    # 相对路径需要基于项目根目录解析为绝对路径
    if not path.is_absolute():
        return BASE_DIR / path
    return path


# =============================================================================
# Settings 类: 全局配置类
# 职责: 集中管理所有配置项，提供类型安全的访问方式
# 设计决策:
#   - 继承 pydantic_settings.BaseSettings，自动支持环境变量注入
#   - 每个字段使用 validation_alias 映射环境变量名（大写形式）
#   - default 值优先从 YAML 缓存中获取，找不到时使用硬编码默认值
#   - 属性（@property）用于派生计算字段（如数据库URL）
# =============================================================================
class Settings(BaseSettings):
    """Global application settings."""

    # ======================== 应用基本配置 ========================
    app_name: str = Field(
        default=_app_config.get("name", "ResearchPulse"),
        validation_alias="APP_NAME",
    )
    debug: bool = Field(
        default=_app_config.get("debug", False),
        validation_alias="DEBUG",
    )
    # 应用监听主机和端口
    app_host: str = Field(
        default=_app_config.get("host", "0.0.0.0"),
        validation_alias="APP_HOST",
    )
    app_port: int = Field(
        default=_app_config.get("port", 8000),
        validation_alias="APP_PORT",
    )
    data_dir: Path = Field(
        default=_get_default_data_dir(),
        validation_alias="DATA_DIR",
    )
    # URL 前缀，用于 UI 路由挂载点（如 /researchpulse）
    url_prefix: str = Field(
        default=_app_config.get("url_prefix", "/researchpulse"),
        validation_alias="URL_PREFIX",
    )
    # CORS 配置：允许的来源列表，逗号分隔（如 "http://localhost:3000,https://example.com"）
    # 使用 "*" 允许所有来源（仅建议开发环境使用）
    cors_origins: str = Field(
        default=_app_config.get("cors_origins", "*"),
        validation_alias="CORS_ORIGINS",
    )
    # CORS 是否允许携带凭证（cookies）
    cors_allow_credentials: bool = Field(
        default=_app_config.get("cors_allow_credentials", False),
        validation_alias="CORS_ALLOW_CREDENTIALS",
    )

    # ======================== 数据库配置 ========================
    # 使用 MySQL（异步驱动 aiomysql），支持连接池管理
    db_host: str = Field(
        default="localhost",
        validation_alias="DB_HOST",
    )
    db_port: int = Field(
        default=3306,
        validation_alias="DB_PORT",
    )
    db_name: str = Field(
        default="research_pulse",
        validation_alias="DB_NAME",
    )
    db_user: str = Field(
        default="research_user",
        validation_alias="DB_USER",
    )
    # 数据库密码默认为空，必须通过环境变量或 .env 文件提供
    db_password: str = Field(
        default="",
        validation_alias="DB_PASSWORD",
    )
    # 连接池大小：同时保持的数据库连接数
    db_pool_size: int = Field(
        default=_db_config.get("pool_size", 10),
        validation_alias="DB_POOL_SIZE",
    )
    # 连接池溢出上限：超出 pool_size 后允许额外创建的连接数
    db_max_overflow: int = Field(
        default=_db_config.get("max_overflow", 20),
        validation_alias="DB_MAX_OVERFLOW",
    )
    # 连接回收时间（秒）：超过此时间的连接将被回收重建，防止 MySQL 的 wait_timeout 导致连接断开
    db_pool_recycle: int = Field(
        default=_db_config.get("pool_recycle", 3600),
        validation_alias="DB_POOL_RECYCLE",
    )
    # 是否在日志中输出 SQL 语句（调试用）
    db_echo: bool = Field(
        default=_db_config.get("echo", False),
        validation_alias="DB_ECHO",
    )

    # ======================== Redis 缓存配置（可选） ========================
    # Redis 作为可选的缓存层，未配置时系统使用内存缓存
    redis_host: str = Field(
        default="",
        validation_alias="REDIS_HOST",
    )
    redis_port: int = Field(
        default=6379,
        validation_alias="REDIS_PORT",
    )
    redis_password: str = Field(
        default="",
        validation_alias="REDIS_PASSWORD",
    )
    redis_db: int = Field(
        default=0,
        validation_alias="REDIS_DB",
    )
    # 缓存总开关
    cache_enabled: bool = Field(
        default=_cache_config.get("enabled", False),
        validation_alias="CACHE_ENABLED",
    )
    # 缓存默认 TTL（存活时间），单位秒
    cache_default_ttl: int = Field(
        default=_cache_config.get("default_ttl", 300),
        validation_alias="CACHE_DEFAULT_TTL",
    )

    # ======================== JWT 认证配置 ========================
    # JWT 密钥：为空时自动生成随机密钥（见下方 validator）
    jwt_secret_key: str = Field(
        default="",
        validation_alias="JWT_SECRET_KEY",
    )
    # JWT 签名算法
    jwt_algorithm: str = Field(
        default=_jwt_config.get("algorithm", "HS256"),
        validation_alias="JWT_ALGORITHM",
    )
    # 访问令牌过期时间（分钟），默认 1 天
    jwt_access_token_expire_minutes: int = Field(
        default=_jwt_config.get("access_token_expire_minutes", 1440),
        validation_alias="JWT_ACCESS_TOKEN_EXPIRE_MINUTES",
    )
    # 刷新令牌过期时间（天）
    jwt_refresh_token_expire_days: int = Field(
        default=_jwt_config.get("refresh_token_expire_days", 7),
        validation_alias="JWT_REFRESH_TOKEN_EXPIRE_DAYS",
    )

    # ======================== 爬虫配置 ========================
    # arXiv 爬取的论文分类，逗号分隔
    arxiv_categories: str = Field(
        default=_crawler_config.get("arxiv", {}).get("categories", "cs.LG,cs.CV,cs.CL"),
        validation_alias="ARXIV_CATEGORIES",
    )
    # 每次爬取的最大论文数量
    arxiv_max_results: int = Field(
        default=_crawler_config.get("arxiv", {}).get("max_results", 50),
        validation_alias="ARXIV_MAX_RESULTS",
    )
    # 爬取请求间的基础延迟（秒），用于控制请求频率，避免被封禁
    arxiv_delay_base: float = Field(
        default=_crawler_config.get("arxiv", {}).get("delay_base", 3.0),
        validation_alias="ARXIV_DELAY_BASE",
    )
    # arXiv 爬取排序模式列表（逗号分隔）
    # submittedDate: 新发表论文, lastUpdatedDate: 更新论文
    arxiv_sort_modes: str = Field(
        default=",".join(_crawler_config.get("arxiv", {}).get("sort_modes", ["lastUpdatedDate"])),
        validation_alias="ARXIV_SORT_MODES",
    )
    # 是否标记论文类型（new/updated）
    arxiv_mark_paper_type: bool = Field(
        default=_crawler_config.get("arxiv", {}).get("mark_paper_type", False),
        validation_alias="ARXIV_MARK_PAPER_TYPE",
    )
    # RSS 格式: "rss" 或 "atom"
    arxiv_rss_format: str = Field(
        default=_crawler_config.get("arxiv", {}).get("rss_format", "rss"),
        validation_alias="ARXIV_RSS_FORMAT",
    )

    # ======================== 微博热搜爬虫配置 ========================
    # 微博爬取请求超时时间（秒）
    weibo_timeout: int = Field(
        default=_weibo_config.get("timeout", 30),
        validation_alias="WEIBO_TIMEOUT",
    )
    # 微博爬取请求间的基础延迟（秒），微博反爬较严格，需要更长延迟
    weibo_delay_base: float = Field(
        default=_weibo_config.get("delay_base", 5.0),
        validation_alias="WEIBO_DELAY_BASE",
    )
    # 延迟抖动范围（秒），用于随机化请求间隔
    weibo_delay_jitter: float = Field(
        default=_weibo_config.get("delay_jitter", 2.0),
        validation_alias="WEIBO_DELAY_JITTER",
    )
    # 微博请求最大重试次数
    weibo_max_retry: int = Field(
        default=_weibo_config.get("max_retry", 3),
        validation_alias="WEIBO_MAX_RETRY",
    )
    # 微博重试退避时间（秒）
    weibo_retry_backoff: float = Field(
        default=_weibo_config.get("retry_backoff", 10.0),
        validation_alias="WEIBO_RETRY_BACKOFF",
    )
    # 微博登录 Cookie（用于访问需要认证的接口，如其他榜单）
    # 格式: "SUB=xxx; SUBP=xxx; ..." 或完整 Cookie 字符串
    # 获取方式: 登录微博后，在浏览器开发者工具中复制 Cookie
    weibo_cookie: str = Field(
        default="",
        validation_alias="WEIBO_COOKIE",
    )

    # ======================== Twitter 爬虫配置 ========================
    # TwitterAPI.io API 密钥（第三方 API，比官方 API 便宜）
    # 获取方式: 注册 https://twitterapi.io 账号并获取 API Key
    twitterapi_io_key: str = Field(
        default="",
        validation_alias="TWITTERAPI_IO_KEY",
    )

    # ======================== 定时任务调度配置 ========================
    # 爬取任务执行间隔（小时）
    crawl_interval_hours: int = Field(
        default=_scheduler_config.get("crawl_interval_hours", 6),
        validation_alias="CRAWL_INTERVAL_HOURS",
    )
    # 数据清理任务执行时间（0-23点）
    cleanup_hour: int = Field(
        default=_scheduler_config.get("cleanup_hour", 3),
        validation_alias="CLEANUP_HOUR",
    )
    # 数据库备份任务执行时间（0-23点）
    backup_hour: int = Field(
        default=_scheduler_config.get("backup_hour", 4),
        validation_alias="BACKUP_HOUR",
    )
    # 调度器使用的时区
    scheduler_timezone: str = Field(
        default=_scheduler_config.get("timezone", "UTC"),
        validation_alias="SCHEDULER_TIMEZONE",
    )

    # ======================== 数据保留策略配置 ========================
    # 活跃数据保留天数（超过后可被清理或归档）
    data_retention_days: int = Field(
        default=_retention_config.get("active_days", 7),
        validation_alias="DATA_RETENTION_DAYS",
    )
    # 归档数据保留天数（超过后可被删除）
    data_archive_days: int = Field(
        default=_retention_config.get("archive_days", 30),
        validation_alias="DATA_ARCHIVE_DAYS",
    )
    # 备份文件存储目录
    backup_dir: Path = Field(
        default=Path(_retention_config.get("backup_dir", "./backups")),
        validation_alias="BACKUP_DIR",
    )
    # 是否启用自动备份
    backup_enabled: bool = Field(
        default=_retention_config.get("backup_enabled", True),
        validation_alias="BACKUP_ENABLED",
    )

    # ======================== 超级用户配置 ========================
    # 超级用户在应用首次启动时自动创建
    superuser_username: str = Field(
        default="admin",
        validation_alias="SUPERUSER_USERNAME",
    )
    superuser_email: str = Field(
        default="admin@example.com",
        validation_alias="SUPERUSER_EMAIL",
    )
    # 超级用户密码为空时不创建超级用户，需通过环境变量或 .env 设置
    superuser_password: str = Field(
        default="",
        validation_alias="SUPERUSER_PASSWORD",
    )

    # ======================== 邮件服务配置 ========================
    # 邮件功能总开关
    email_enabled: bool = Field(
        default=_email_config.get("enabled", False),
        validation_alias="EMAIL_ENABLED",
    )
    # 发件人地址
    email_from: str = Field(
        default=_email_config.get("from", ""),
        validation_alias="EMAIL_FROM",
    )
    # 邮件发送后端（smtp / sendgrid / mailgun / brevo）
    email_backend: str = Field(
        default=_email_config.get("backends", "smtp"),
        validation_alias="EMAIL_BACKEND",
    )
    # ---- SMTP 相关配置 ----
    smtp_host: str = Field(
        default=_email_config.get("smtp", {}).get("host", ""),
        validation_alias="SMTP_HOST",
    )
    smtp_port: int = Field(
        default=_email_config.get("smtp", {}).get("port", 587),
        validation_alias="SMTP_PORT",
    )
    smtp_user: str = Field(
        default=_email_config.get("smtp", {}).get("user", ""),
        validation_alias="SMTP_USER",
    )
    smtp_password: str = Field(
        default=_email_config.get("smtp", {}).get("password", ""),
        validation_alias="SMTP_PASSWORD",
    )
    # SMTP 备用端口列表（逗号分隔），用于多端口重试策略
    smtp_ports: str = Field(
        default=_email_config.get("smtp", {}).get("ports", "587,465,2525"),
        validation_alias="SMTP_PORTS",
    )
    # 使用 SSL 直连的端口列表
    smtp_ssl_ports: str = Field(
        default=_email_config.get("smtp", {}).get("ssl_ports", "465"),
        validation_alias="SMTP_SSL_PORTS",
    )
    # SMTP 连接超时（秒）
    smtp_timeout: float = Field(
        default=_email_config.get("smtp", {}).get("timeout", 10.0),
        validation_alias="SMTP_TIMEOUT",
    )
    # SMTP 发送失败重试次数
    smtp_retries: int = Field(
        default=_email_config.get("smtp", {}).get("retries", 3),
        validation_alias="SMTP_RETRIES",
    )
    # SMTP 重试间隔退避时间（秒）
    smtp_retry_backoff: float = Field(
        default=_email_config.get("smtp", {}).get("retry_backoff", 10.0),
        validation_alias="SMTP_RETRY_BACKOFF",
    )
    # 是否启用 STARTTLS（先明文连接再升级为加密）
    smtp_tls: bool = Field(
        default=_email_config.get("smtp", {}).get("tls", True),
        validation_alias="SMTP_TLS",
    )
    # 是否使用 SSL 直连（端口 465 通常使用此方式）
    smtp_ssl: bool = Field(
        default=_email_config.get("smtp", {}).get("ssl", False),
        validation_alias="SMTP_SSL",
    )
    # ---- 第三方邮件服务 API 密钥 ----
    # 这些密钥需要通过环境变量或 .env 文件注入，默认为空
    sendgrid_api_key: str = Field(
        default="",
        validation_alias="SENDGRID_API_KEY",
    )
    mailgun_api_key: str = Field(
        default="",
        validation_alias="MAILGUN_API_KEY",
    )
    mailgun_domain: str = Field(
        default="",
        validation_alias="MAILGUN_DOMAIN",
    )
    brevo_api_key: str = Field(
        default="",
        validation_alias="BREVO_API_KEY",
    )
    # ---- 邮件通知设置 ----
    # 通知频率：daily（每日）/ weekly（每周）等
    email_notification_frequency: str = Field(
        default=_email_config.get("notification", {}).get("frequency", "daily"),
        validation_alias="EMAIL_NOTIFICATION_FREQUENCY",
    )
    # 通知发送时间（HH:MM 格式）
    email_notification_time: str = Field(
        default=_email_config.get("notification", {}).get("time", "09:00"),
        validation_alias="EMAIL_NOTIFICATION_TIME",
    )
    # 单次通知邮件中包含的最大文章数
    email_max_articles: int = Field(
        default=_email_config.get("notification", {}).get("max_articles", 20),
        validation_alias="EMAIL_MAX_ARTICLES",
    )
    # 邮件模板引擎：jinja2（新版美化模板）/ legacy（原有 Markdown 转 HTML）
    email_template_engine: str = Field(
        default=_email_config.get("notification", {}).get("template_engine", "jinja2"),
        validation_alias="EMAIL_TEMPLATE_ENGINE",
    )

    # ======================== 功能开关（Feature Toggles） ========================
    # 可通过环境变量或管理后台动态启用
    feature_ai_processor: bool = Field(
        default=_ai_config.get("enabled", False),
        validation_alias="FEATURE_AI_PROCESSOR",
    )
    feature_embedding: bool = Field(
        default=_embedding_config.get("enabled", False),
        validation_alias="FEATURE_EMBEDDING",
    )
    feature_event_clustering: bool = Field(
        default=_event_config.get("enabled", False),
        validation_alias="FEATURE_EVENT_CLUSTERING",
    )
    feature_topic_radar: bool = Field(
        default=_topic_config.get("enabled", False),
        validation_alias="FEATURE_TOPIC_RADAR",
    )
    feature_action_items: bool = Field(
        default=_action_config.get("enabled", False),
        validation_alias="FEATURE_ACTION_ITEMS",
    )
    feature_report_generation: bool = Field(
        default=_report_config.get("enabled", False),
        validation_alias="FEATURE_REPORT_GENERATION",
    )

    # ======================== AI 处理器配置 ========================
    # AI 服务提供商：ollama（本地部署）/ openai / claude
    ai_provider: str = Field(
        default=_ai_config.get("provider", "ollama"),
        validation_alias="AI_PROVIDER",
    )
    # Ollama 本地服务的 API 地址
    ollama_base_url: str = Field(
        default=_ai_config.get("ollama", {}).get("base_url", "http://localhost:11434"),
        validation_alias="OLLAMA_BASE_URL",
    )
    # Ollama 使用的主模型名称
    ollama_model: str = Field(
        default=_ai_config.get("ollama", {}).get("model", "qwen3:32b"),
        validation_alias="OLLAMA_MODEL",
    )
    # Ollama 轻量模型（用于简单任务，降低资源消耗）
    ollama_model_light: str = Field(
        default=_ai_config.get("ollama", {}).get("model_light", ""),
        validation_alias="OLLAMA_MODEL_LIGHT",
    )
    # Ollama API 请求超时时间（秒）
    ollama_timeout: int = Field(
        default=_ai_config.get("ollama", {}).get("timeout", 120),
        validation_alias="OLLAMA_TIMEOUT",
    )
    # AI 结果缓存开关（避免对相同内容重复调用 AI）
    ai_cache_enabled: bool = Field(
        default=_ai_config.get("cache", {}).get("enabled", True),
        validation_alias="AI_CACHE_ENABLED",
    )
    # AI 缓存 TTL（秒），默认 24 小时
    ai_cache_ttl: int = Field(
        default=_ai_config.get("cache", {}).get("ttl", 86400),
        validation_alias="AI_CACHE_TTL",
    )
    # 送入 AI 处理的最大内容长度（字符数），超出部分会被截断
    ai_max_content_length: int = Field(
        default=_ai_config.get("max_content_length", 1500),
        validation_alias="AI_MAX_CONTENT_LENGTH",
    )
    # AI 批处理并发度（同时处理的文章数量上限）
    ai_batch_concurrency: int = Field(
        default=_ai_config.get("batch_concurrency", 5),
        validation_alias="AI_BATCH_CONCURRENCY",
    )
    # AI 调用最大重试次数
    ai_max_retries: int = Field(
        default=_ai_config.get("max_retries", 3),
        validation_alias="AI_MAX_RETRIES",
    )
    # AI 调用重试基础延迟（秒），指数退避的乘数
    ai_retry_base_delay: float = Field(
        default=_ai_config.get("retry_base_delay", 1.0),
        validation_alias="AI_RETRY_BASE_DELAY",
    )
    # AI 降级回退 Provider（主 Provider 失败时使用，为空则不回退）
    ai_fallback_provider: str = Field(
        default=_ai_config.get("fallback_provider", ""),
        validation_alias="AI_FALLBACK_PROVIDER",
    )

    # ======================== 向量嵌入 / Milvus 配置 ========================
    # 嵌入向量提供商
    embedding_provider: str = Field(
        default=_embedding_config.get("provider", "sentence-transformers"),
        validation_alias="EMBEDDING_PROVIDER",
    )
    # 嵌入模型名称
    embedding_model: str = Field(
        default=_embedding_config.get("model", "all-MiniLM-L6-v2"),
        validation_alias="EMBEDDING_MODEL",
    )
    # 嵌入向量维度（需与模型匹配）
    embedding_dimension: int = Field(
        default=_embedding_config.get("dimension", 384),
        validation_alias="EMBEDDING_DIMENSION",
    )
    # 相似度阈值：高于此值的文章对被认为是相似的
    embedding_similarity_threshold: float = Field(
        default=_embedding_config.get("similarity_threshold", 0.85),
        validation_alias="EMBEDDING_SIMILARITY_THRESHOLD",
    )
    # 嵌入功能开关
    embedding_enabled: bool = Field(
        default=_embedding_config.get("enabled", False),
        validation_alias="EMBEDDING_ENABLED",
    )
    # Milvus 向量数据库服务地址
    milvus_host: str = Field(
        default=_embedding_config.get("milvus", {}).get("host", "localhost"),
        validation_alias="MILVUS_HOST",
    )
    # Milvus 服务端口
    milvus_port: int = Field(
        default=_embedding_config.get("milvus", {}).get("port", 19530),
        validation_alias="MILVUS_PORT",
    )
    # Milvus 集合名称（类似关系型数据库中的"表"）
    milvus_collection_name: str = Field(
        default=_embedding_config.get("milvus", {}).get("collection_name", "article_embeddings"),
        validation_alias="MILVUS_COLLECTION_NAME",
    )

    # ======================== 事件聚类配置 ========================
    # 基于规则的聚类权重（与语义权重之和应为 1.0）
    event_rule_weight: float = Field(
        default=_event_config.get("clustering", {}).get("rule_weight", 0.4),
        validation_alias="EVENT_RULE_WEIGHT",
    )
    # 基于语义的聚类权重
    event_semantic_weight: float = Field(
        default=_event_config.get("clustering", {}).get("semantic_weight", 0.6),
        validation_alias="EVENT_SEMANTIC_WEIGHT",
    )
    # 聚类最小相似度阈值
    event_min_similarity: float = Field(
        default=_event_config.get("clustering", {}).get("min_similarity", 0.7),
        validation_alias="EVENT_MIN_SIMILARITY",
    )

    # ======================== 话题发现配置 ========================
    # 话题发现的最小出现频率（低于此值的关键词不被视为话题）
    topic_min_frequency: int = Field(
        default=_topic_config.get("discovery", {}).get("min_frequency", 5),
        validation_alias="TOPIC_MIN_FREQUENCY",
    )
    # 话题发现的回溯天数（分析多少天内的数据）
    topic_lookback_days: int = Field(
        default=_topic_config.get("discovery", {}).get("lookback_days", 14),
        validation_alias="TOPIC_LOOKBACK_DAYS",
    )

    # pydantic-settings 的模型配置
    # env_file: 指定 .env 文件路径
    # case_sensitive: 环境变量名不区分大小写
    # extra: 忽略未定义的配置项，不报错
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("jwt_secret_key", mode="before")
    @classmethod
    def generate_jwt_secret_if_empty(cls, v: str) -> str:
        """Generate a random JWT secret if not provided.

        JWT 密钥验证器：如果未提供有效的密钥，则自动生成一个随机密钥。
        注意：自动生成的密钥在每次应用重启时都会变化，
        这意味着之前签发的所有 Token 将会失效。
        生产环境应通过环境变量设置固定密钥。

        参数:
            v: 输入的 JWT 密钥字符串

        返回值:
            str: 有效的 JWT 密钥
        """
        # 空字符串或占位符均视为未配置
        if not v or v == "your_jwt_secret_key_here":
            return secrets.token_urlsafe(32)
        return v

    @property
    def database_url(self) -> str:
        """Build async MySQL database URL.

        构建异步 MySQL 连接 URL，使用 aiomysql 驱动。
        密码经过 URL 编码以处理特殊字符。

        返回值:
            str: 形如 mysql+aiomysql://user:pass@host:port/dbname 的连接字符串
        """
        from urllib.parse import quote_plus
        encoded_password = quote_plus(self.db_password)
        return (
            f"mysql+aiomysql://{self.db_user}:{encoded_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @property
    def database_url_sync(self) -> str:
        """Build sync MySQL database URL (for Alembic).

        构建同步 MySQL 连接 URL，使用 pymysql 驱动。
        主要用于 Alembic 数据库迁移工具（不支持异步）。

        返回值:
            str: 形如 mysql+pymysql://user:pass@host:port/dbname 的连接字符串
        """
        from urllib.parse import quote_plus
        encoded_password = quote_plus(self.db_password)
        return (
            f"mysql+pymysql://{self.db_user}:{encoded_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @property
    def redis_available(self) -> bool:
        """Check if Redis is configured.

        判断 Redis 是否已配置（通过检查 redis_host 是否非空）。

        返回值:
            bool: True 表示 Redis 已配置可用
        """
        return bool(self.redis_host)

    @property
    def arxiv_categories_list(self) -> List[str]:
        """Return arxiv categories as a list.

        将逗号分隔的 arXiv 分类字符串转换为列表。
        例如 "cs.LG,cs.CV,cs.CL" -> ["cs.LG", "cs.CV", "cs.CL"]

        返回值:
            List[str]: arXiv 分类列表
        """
        return [c.strip() for c in self.arxiv_categories.split(",") if c.strip()]

    @property
    def arxiv_sort_modes_list(self) -> List[str]:
        """Return arxiv sort modes as a list.

        将逗号分隔的排序模式字符串转换为列表。
        例如 "submittedDate,lastUpdatedDate" -> ["submittedDate", "lastUpdatedDate"]

        返回值:
            List[str]: arXiv 排序模式列表
        """
        return [m.strip() for m in self.arxiv_sort_modes.split(",") if m.strip()]

    @property
    def is_configured(self) -> bool:
        """Check if essential configuration is complete.

        检查关键配置是否已完成（数据库相关配置必须非空）。

        返回值:
            bool: True 表示基本配置已就绪
        """
        return bool(self.db_host and self.db_name and self.db_user)


# 创建全局配置单例
# 整个应用通过 from settings import settings 引用此实例
settings = Settings()
