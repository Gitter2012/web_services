# =============================================================================
# 模块: apps/crawler/models/config.py
# 功能: 系统配置、备份记录、审计日志和邮件配置的数据模型定义
# 架构角色: 数据持久化层的运维支撑模型。提供四个模型：
#   - SystemConfig: 系统配置的数据库存储（替代或补充文件配置）
#   - BackupRecord: 数据备份的执行记录
#   - AuditLog: 用户操作的审计日志
#   - EmailConfig: 邮件推送配置（SMTP/SendGrid/Mailgun/Brevo）
# 设计理念:
#   1. SystemConfig 将配置存储在数据库中，支持运行时动态修改，
#      无需重启服务。同时标记敏感配置以便于安全审计。
#   2. BackupRecord 记录每次备份的执行情况，支持备份状态追踪和故障排查。
#   3. AuditLog 记录所有关键用户操作，满足安全合规和问题追溯需求。
#   4. EmailConfig 集中管理多后端邮件配置，支持灵活切换和测试。
# =============================================================================

"""System configuration and audit models for ResearchPulse v2."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base, TimestampMixin


# =============================================================================
# SystemConfig 模型
# 职责: 以键值对形式存储系统配置项
# 表名: system_config
# 设计决策:
#   1. 使用 config_key 作为主键（而非自增ID），简化配置读写操作
#   2. is_sensitive 标志用于区分敏感配置（如 API 密钥），
#      便于在日志输出和 API 响应中脱敏处理
#   3. updated_by 记录最后修改人，支持配置变更审计
# =============================================================================
class SystemConfig(Base, TimestampMixin):
    """System configuration stored in database.

    系统配置的数据库存储模型。
    """

    __tablename__ = "system_config"

    # 配置键名作为主键（如 "crawl.interval", "ai.model" 等）
    config_key: Mapped[str] = mapped_column(
        String(100),
        primary_key=True,
        comment="Configuration key",
    )
    # 配置值（以文本形式存储，支持 JSON 等复杂格式）
    config_value: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Configuration value",
    )
    # 配置项的描述说明
    description: Mapped[str] = mapped_column(
        String(255),
        default="",
        nullable=False,
    )
    # 是否为敏感配置（如 API 密钥、数据库密码等）
    # 敏感配置在日志和 API 中需要脱敏处理
    is_sensitive: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Whether this config contains sensitive data",
    )
    # 最后修改此配置的用户ID（可空，系统自动修改时为 NULL）
    # 外键关联 users 表，用户被删除时设置为 NULL（不影响配置记录）
    updated_by: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    def __repr__(self) -> str:
        """Return a readable configuration representation.

        返回配置项的字符串表示。
        """
        return f"<SystemConfig(key={self.config_key})>"


# =============================================================================
# BackupRecord 模型
# 职责: 记录数据备份的执行情况和状态
# 表名: backup_records
# 设计决策:
#   1. backup_date 设有唯一约束，防止同一时间点产生重复备份记录
#   2. status 字段追踪备份生命周期：pending -> completed / failed
#   3. 记录备份文件大小和文章数量，便于监控数据增长趋势
# =============================================================================
class BackupRecord(Base, TimestampMixin):
    """Backup record for data retention.

    数据备份执行记录模型。
    """

    __tablename__ = "backup_records"

    # 备份记录主键
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 备份执行的日期时间（唯一约束防止重复）
    backup_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        unique=True,
        nullable=False,
        index=True,
    )
    # 备份文件的存储路径
    backup_file: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )
    # 备份文件大小（字节），用于监控存储空间使用
    backup_size: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Backup file size in bytes",
    )
    # 备份中包含的文章总数
    article_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    # 备份状态：pending（进行中）、completed（已完成）、failed（失败）
    status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
        nullable=False,
        comment="Status: pending, completed, failed",
    )
    # 备份完成时间（仅在 status='completed' 时有值）
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    # 错误信息（仅在 status='failed' 时有值），用于故障排查
    error_message: Mapped[str] = mapped_column(
        Text,
        nullable=True,
    )

    def __repr__(self) -> str:
        """Return a readable backup record representation.

        返回备份记录的字符串表示。
        """
        return f"<BackupRecord(date={self.backup_date}, status={self.status})>"


# =============================================================================
# AuditLog 模型
# 职责: 记录用户的关键操作，用于安全审计和问题追溯
# 表名: audit_logs
# 设计决策:
#   1. 不继承 TimestampMixin，因为审计日志只需要 created_at（创建时间），
#      不需要 updated_at（审计日志一旦创建不应被修改）
#   2. user_id 使用 SET NULL 级联策略，确保用户被删除后审计日志仍然保留
#   3. details 使用 JSON 字段存储操作的详细参数，灵活适配不同类型的操作
#   4. 记录 IP 地址和 User-Agent，辅助安全分析
# =============================================================================
class AuditLog(Base):
    """Audit log for user actions.

    用户操作审计日志模型。
    """

    __tablename__ = "audit_logs"

    # 审计日志主键
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 执行操作的用户ID（可空，用户删除后保留日志但 user_id 置 NULL）
    user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # 操作类型（如 "login", "delete_article", "update_config" 等）
    action: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )
    # 被操作的资源类型（如 "article", "user", "config" 等）
    resource_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    # 被操作的资源ID
    resource_id: Mapped[str] = mapped_column(
        String(100),
        default="",
        nullable=False,
    )
    # 操作的详细参数（JSON 格式，灵活存储各类操作的上下文信息）
    details: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )
    # 操作者的 IP 地址（支持 IPv4 和 IPv6，最长 45 字符）
    ip_address: Mapped[str] = mapped_column(
        String(45),
        default="",
        nullable=False,
    )
    # 操作者的 User-Agent（用于识别客户端类型）
    user_agent: Mapped[str] = mapped_column(
        String(500),
        default="",
        nullable=False,
    )
    # 操作发生的时间（审计日志不使用 TimestampMixin，手动定义 created_at）
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    def __repr__(self) -> str:
        """Return a readable audit log representation.

        返回审计日志的字符串表示。
        """
        return f"<AuditLog(action={self.action}, resource={self.resource_type})>"


# =============================================================================
# EmailConfig 模型
# 职责: 存储邮件推送配置，支持多种邮件后端
# 表名: email_configs
# 设计决策:
#   1. 单行设计：只存储一条配置记录（id=1），简化管理
#   2. 支持多后端：SMTP、SendGrid、Mailgun、Brevo，可灵活切换
#   3. 敏感字段（密码、API Key）在 API 返回时需要脱敏
#   4. 推送设置支持多种频率：daily、weekly、instant
# =============================================================================
class EmailConfig(Base, TimestampMixin):
    """Email configuration for notifications.

    邮件通知配置模型。
    """

    __tablename__ = "email_configs"

    # 主键（单行设计，通常只有 id=1）
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # ---- SMTP 配置 ----
    smtp_host: Mapped[str] = mapped_column(
        String(255),
        default="",
        nullable=False,
        comment="SMTP server host",
    )
    smtp_port: Mapped[int] = mapped_column(
        Integer,
        default=587,
        nullable=False,
        comment="SMTP server port",
    )
    smtp_user: Mapped[str] = mapped_column(
        String(255),
        default="",
        nullable=False,
        comment="SMTP username",
    )
    smtp_password: Mapped[str] = mapped_column(
        String(255),
        default="",
        nullable=False,
        comment="SMTP password (encrypted)",
    )
    smtp_use_tls: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="Use TLS for SMTP",
    )

    # ---- SendGrid 配置 ----
    sendgrid_api_key: Mapped[str] = mapped_column(
        String(255),
        default="",
        nullable=False,
        comment="SendGrid API key",
    )

    # ---- Mailgun 配置 ----
    mailgun_api_key: Mapped[str] = mapped_column(
        String(255),
        default="",
        nullable=False,
        comment="Mailgun API key",
    )
    mailgun_domain: Mapped[str] = mapped_column(
        String(255),
        default="",
        nullable=False,
        comment="Mailgun domain",
    )

    # ---- Brevo 配置 ----
    brevo_api_key: Mapped[str] = mapped_column(
        String(255),
        default="",
        nullable=False,
        comment="Brevo API key",
    )
    brevo_from_name: Mapped[str] = mapped_column(
        String(100),
        default="ResearchPulse",
        nullable=False,
        comment="Brevo sender name",
    )

    # ---- 推送设置 ----
    email_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Enable email notifications",
    )
    active_backend: Mapped[str] = mapped_column(
        String(20),
        default="smtp",
        nullable=False,
        comment="Active backend: smtp, sendgrid, mailgun, brevo",
    )
    sender_email: Mapped[str] = mapped_column(
        String(255),
        default="",
        nullable=False,
        comment="Sender email address",
    )
    push_frequency: Mapped[str] = mapped_column(
        String(20),
        default="daily",
        nullable=False,
        comment="Push frequency: daily, weekly, instant",
    )
    push_time: Mapped[str] = mapped_column(
        String(10),
        default="09:00",
        nullable=False,
        comment="Push time (HH:MM format)",
    )
    max_articles_per_email: Mapped[int] = mapped_column(
        Integer,
        default=20,
        nullable=False,
        comment="Max articles per email",
    )

    def __repr__(self) -> str:
        """Return a readable email config representation.

        返回邮件配置的字符串表示。
        """
        return f"<EmailConfig(enabled={self.email_enabled}, backend={self.active_backend})>"

