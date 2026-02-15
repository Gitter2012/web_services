# =============================================================================
# AI 处理器数据模型模块
# =============================================================================
# 本模块定义了 AI 处理操作相关的数据库 ORM 模型，包括：
#   - AIProcessingLog: 每次 AI 处理调用的详细日志记录
#   - TokenUsageStat: 按日期聚合的 token/字符使用统计
# 这些模型用于追踪 AI 处理的成本、性能和可靠性指标，
# 是系统可观测性的重要组成部分。
# =============================================================================

"""AI processing models."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, Integer, String, Text, Float
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base, TimestampMixin


# -----------------------------------------------------------------------------
# AI 处理日志模型
# 记录每一次 AI 处理操作的详细信息，包括使用的 provider、模型、耗时、
# 字符数、是否成功、是否命中缓存等。
# 设计决策：选择按操作粒度记录（而非聚合），以便后续灵活查询和分析。
# -----------------------------------------------------------------------------
class AIProcessingLog(Base, TimestampMixin):
    """Log of AI processing operations."""

    __tablename__ = "ai_processing_logs"

    # 主键，自增 ID
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # 被处理的文章 ID，建立索引以加速按文章查询
    article_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False, index=True,
        comment="Article that was processed",
    )
    # AI 服务提供商名称（如 "ollama"、"openai"）
    provider: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="AI provider used",
    )
    # 使用的具体模型名称（如 "gpt-4o-mini"、"qwen2.5"）
    model: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="Model name used",
    )
    # 任务类型，决定使用哪种 prompt 模板
    # content_high: 高价值内容完整分析
    # content_low: 低价值内容简要分析
    # paper_full: 学术论文完整分析
    # screen: 筛选性处理
    task_type: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="Task type: content_high, content_low, paper_full, screen",
    )
    # 输入字符数，用于成本估算
    input_chars: Mapped[int] = mapped_column(
        Integer, default=0, comment="Input character count",
    )
    # 输出字符数，用于成本估算
    output_chars: Mapped[int] = mapped_column(
        Integer, default=0, comment="Output character count",
    )
    # 处理耗时（毫秒），用于性能监控
    duration_ms: Mapped[int] = mapped_column(
        Integer, default=0, comment="Processing duration in milliseconds",
    )
    # 处理是否成功
    success: Mapped[bool] = mapped_column(
        default=True, comment="Whether processing succeeded",
    )
    # 失败时的错误信息，成功时为 None
    error_message: Mapped[str] = mapped_column(
        Text, nullable=True, comment="Error message if failed",
    )
    # 是否命中缓存（已处理过的文章再次请求时返回缓存结果）
    cached: Mapped[bool] = mapped_column(
        default=False, comment="Whether result was from cache",
    )


# -----------------------------------------------------------------------------
# Token 使用统计模型
# 按日期、provider、model 维度聚合的使用统计。
# 设计决策：预聚合的统计表可以加速仪表盘查询，避免每次都从日志表实时聚合。
# 注意：当前 API 层的 token-stats 端点直接从日志表聚合，此表可用于定时任务预计算。
# -----------------------------------------------------------------------------
class TokenUsageStat(Base, TimestampMixin):
    """Aggregated token usage statistics."""

    __tablename__ = "token_usage_stats"

    # 主键，自增 ID
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # 统计日期，格式 YYYY-MM-DD
    date: Mapped[str] = mapped_column(
        String(10), nullable=False, index=True, comment="Date YYYY-MM-DD",
    )
    # AI 服务提供商
    provider: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="AI provider",
    )
    # 模型名称
    model: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="Model name",
    )
    # 当日总调用次数
    total_calls: Mapped[int] = mapped_column(Integer, default=0)
    # 当日缓存命中次数
    cached_calls: Mapped[int] = mapped_column(Integer, default=0)
    # 当日总输入字符数
    total_input_chars: Mapped[int] = mapped_column(Integer, default=0)
    # 当日总输出字符数
    total_output_chars: Mapped[int] = mapped_column(Integer, default=0)
    # 当日总处理耗时（毫秒）
    total_duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    # 当日失败调用次数
    failed_calls: Mapped[int] = mapped_column(Integer, default=0)
