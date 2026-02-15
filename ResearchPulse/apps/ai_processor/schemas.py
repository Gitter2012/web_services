# =============================================================================
# AI 处理器 Pydantic 数据校验模块
# =============================================================================
# 本模块定义了 AI 处理器所有 API 端点的请求和响应数据结构。
# 使用 Pydantic BaseModel 实现自动的数据验证、序列化和文档生成。
# 在架构中，这一层位于 API 路由和服务层之间，确保数据格式一致性。
# 主要包含：
#   - 请求模型：ProcessArticleRequest, BatchProcessRequest
#   - 处理结果子结构：KeyPointSchema, ImpactSchema, ActionItemSchema
#   - 响应模型：ProcessingResultSchema, BatchProcessResponse,
#               ProcessingStatusResponse, TokenStatsResponse
# =============================================================================

"""AI processor Pydantic schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# -----------------------------------------------------------------------------
# 单篇文章处理请求
# 仅包含文章 ID，由服务层负责从数据库获取文章内容
# -----------------------------------------------------------------------------
class ProcessArticleRequest(BaseModel):
    """Request to process an article with AI."""
    article_id: int


# -----------------------------------------------------------------------------
# 批量处理请求
# article_ids: 待处理的文章 ID 列表，最多 100 篇（防止单次请求过大）
# force: 是否强制重新处理已有结果的文章（默认跳过已处理的）
# -----------------------------------------------------------------------------
class BatchProcessRequest(BaseModel):
    """Request for batch AI processing."""
    article_ids: list[int] = Field(default_factory=list, max_length=100)
    force: bool = Field(default=False, description="Reprocess already-processed articles")


# -----------------------------------------------------------------------------
# 关键要点 Schema
# AI 从文章中提取的结构化关键信息点
# type: 要点类型（数字/时间/实体/事实）
# value: 具体的关键值
# impact: 该要点的影响说明
# -----------------------------------------------------------------------------
class KeyPointSchema(BaseModel):
    type: str = ""
    value: str = ""
    impact: str = ""


# -----------------------------------------------------------------------------
# 影响评估 Schema
# AI 对文章内容的短期和长期影响分析
# certainty: 确定性级别（certain/uncertain）
# -----------------------------------------------------------------------------
class ImpactSchema(BaseModel):
    short_term: str = ""   # 短期影响描述
    long_term: str = ""    # 长期影响描述
    certainty: str = "uncertain"  # 影响确定性


# -----------------------------------------------------------------------------
# 行动项 Schema
# 从高重要性文章中提取的可执行行动建议
# type: 行动类型（跟进/验证/决策/触发器）
# priority: 优先级（高/中/低）
# -----------------------------------------------------------------------------
class ActionItemSchema(BaseModel):
    type: str = ""
    description: str = ""
    priority: str = "中"  # 默认中等优先级


# -----------------------------------------------------------------------------
# AI 处理结果完整 Schema
# 包含 AI 分析产出的所有结构化信息，是核心的数据输出格式
# category 默认为 "其他"，importance_score 范围 1-10
# processing_method 标识处理方式：ai / rule / cached
# -----------------------------------------------------------------------------
class ProcessingResultSchema(BaseModel):
    """Result of AI processing."""
    article_id: int
    success: bool = True                                          # 处理是否成功
    summary: str = ""                                             # AI 生成的中文摘要
    category: str = "其他"                                         # 文章分类（10 个预定义分类之一）
    importance_score: int = 5                                     # 重要性评分 1-10
    one_liner: str = ""                                           # 一句话总结
    key_points: list[KeyPointSchema] = Field(default_factory=list)  # 关键要点列表
    impact_assessment: Optional[ImpactSchema] = None              # 影响评估（可能为空）
    actionable_items: list[ActionItemSchema] = Field(default_factory=list)  # 行动项列表
    provider: str = ""                                            # 使用的 AI 提供商
    model: str = ""                                               # 使用的模型名称
    processing_method: str = ""                                   # 处理方式标识
    error_message: Optional[str] = None                           # 错误信息（失败时）


# -----------------------------------------------------------------------------
# 批量处理响应
# 汇总批量处理的整体结果统计
# -----------------------------------------------------------------------------
class BatchProcessResponse(BaseModel):
    """Response for batch processing."""
    total: int = 0       # 请求处理的文章总数
    processed: int = 0   # 实际执行 AI 处理的数量
    cached: int = 0      # 命中缓存的数量（已处理过的文章）
    failed: int = 0      # 处理失败的数量
    results: list[ProcessingResultSchema] = Field(default_factory=list)  # 每篇文章的详细结果


# -----------------------------------------------------------------------------
# 处理状态查询响应
# 用于检查某篇文章是否已被 AI 处理以及处理的元信息
# -----------------------------------------------------------------------------
class ProcessingStatusResponse(BaseModel):
    """Status of article processing."""
    article_id: int
    is_processed: bool = False              # 是否已处理
    processed_at: Optional[datetime] = None  # 处理完成时间
    provider: Optional[str] = None          # 使用的提供商
    model: Optional[str] = None             # 使用的模型
    method: Optional[str] = None            # 处理方式


# -----------------------------------------------------------------------------
# Token 使用统计响应
# 按日期+provider+model 维度的使用量统计
# 用于成本监控和使用量仪表盘
# -----------------------------------------------------------------------------
class TokenStatsResponse(BaseModel):
    """Token usage statistics."""
    date: str                       # 统计日期
    provider: str                   # AI 提供商
    model: str                      # 模型名称
    total_calls: int = 0            # 总调用次数
    cached_calls: int = 0           # 缓存命中次数
    total_input_chars: int = 0      # 总输入字符数
    total_output_chars: int = 0     # 总输出字符数
    avg_duration_ms: float = 0.0    # 平均处理耗时（毫秒）
    failed_calls: int = 0           # 失败次数
