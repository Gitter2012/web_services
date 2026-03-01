# ==============================================================================
# 模块: topic/schemas.py
# 功能: 话题模块的 Pydantic 数据验证与序列化模型 (Schema 层)
# 架构角色: 定义 API 层的请求体和响应体结构, 负责:
#   1. 请求参数验证 (TopicCreateRequest, TopicUpdateRequest)
#   2. 响应数据序列化 (TopicSchema, TopicListResponse 等)
#   3. 数据传输对象 (DTO) 的格式规范
# 设计说明: 使用 Pydantic v2 的 BaseModel, 通过 Field 设置默认值和约束条件,
#           TopicSchema 启用 from_attributes 以支持从 ORM 模型直接转换
# ==============================================================================
"""Topic Pydantic schemas."""
from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

# --------------------------------------------------------------------------
# TopicCreateRequest - 创建话题的请求模型
# 用途: 用户手动创建新话题时提交的数据
# 字段:
#   - name: 话题名称, 最大长度 100 字符
#   - description: 话题描述, 默认为空字符串
#   - keywords: 关键词列表, 用于后续的文章匹配, 默认为空列表
# --------------------------------------------------------------------------
class TopicCreateRequest(BaseModel):
    name: str = Field(max_length=100)
    description: str = ""
    keywords: list[str] = Field(default_factory=list)

# --------------------------------------------------------------------------
# TopicUpdateRequest - 更新话题的请求模型
# 用途: 修改已有话题时提交的数据
# 设计说明: 所有字段均为 Optional, 配合 model_dump(exclude_unset=True)
#           实现部分更新, 只修改用户明确传递的字段
# --------------------------------------------------------------------------
class TopicUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    keywords: Optional[list[str]] = None
    is_active: Optional[bool] = None

# --------------------------------------------------------------------------
# TopicSchema - 话题的完整响应模型
# 用途: 返回话题详情时使用的序列化格式
# 设计说明: from_attributes=True 允许直接从 SQLAlchemy ORM 对象转换,
#           无需手动构建字典
# --------------------------------------------------------------------------
class TopicSchema(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    keywords: Optional[list[str]] = None
    is_auto_discovered: bool = False  # 是否由系统自动发现
    is_active: bool = True  # 话题是否处于激活状态
    created_at: Optional[datetime] = None  # 创建时间
    model_config = {"from_attributes": True}  # 启用 ORM 模型属性映射

# --------------------------------------------------------------------------
# TopicListResponse - 话题列表的分页响应模型
# 用途: 列表查询接口的响应格式, 包含总数和话题列表
# --------------------------------------------------------------------------
class TopicListResponse(BaseModel):
    total: int = 0  # 话题总数
    topics: list[TopicSchema] = Field(default_factory=list)  # 话题列表

# --------------------------------------------------------------------------
# TopicArticleSchema - 话题关联文章的响应模型
# 用途: 展示某个话题下关联的文章信息
# 字段:
#   - article_id: 文章唯一标识
#   - title: 文章标题
#   - match_score: 文章与话题的匹配分数 (0~1)
#   - matched_keywords: 匹配命中的关键词列表
# --------------------------------------------------------------------------
class TopicArticleSchema(BaseModel):
    article_id: int
    title: str = ""
    url: str = ""  # 文章链接
    match_score: float = 0.0
    matched_keywords: Optional[list[str]] = None

# --------------------------------------------------------------------------
# TopicTrendSchema - 话题趋势响应模型
# 用途: 展示话题在某个时间段内的热度变化
# 字段:
#   - direction: 趋势方向 ("up" / "down" / "stable")
#   - change_percent: 变化百分比 (正数为增长, 负数为下降)
#   - current_count: 当前周期内关联的文章数量
#   - previous_count: 上一周期内关联的文章数量
# --------------------------------------------------------------------------
class TopicTrendSchema(BaseModel):
    direction: str = "stable"
    change_percent: float = 0.0
    current_count: int = 0
    previous_count: int = 0

# --------------------------------------------------------------------------
# TopicSuggestionSchema - 话题发现建议模型
# 用途: 自动话题发现接口返回的单条建议
# 字段:
#   - name: 建议的话题名称
#   - keywords: 相关关键词列表
#   - frequency: 在近期文章中出现的频次
#   - confidence: 置信度 (0~1), 反映该建议的可靠程度
#   - source: 建议来源 ("entity" 实体识别 / "keyword" 关键词提取)
#   - sample_titles: 包含该话题的示例文章标题 (最多3条)
# --------------------------------------------------------------------------
class TopicSuggestionSchema(BaseModel):
    name: str
    keywords: list[str] = Field(default_factory=list)
    frequency: int = 0
    confidence: float = 0.0
    source: str = ""
    sample_titles: list[str] = Field(default_factory=list)

# --------------------------------------------------------------------------
# DiscoverResponse - 话题发现的响应模型
# 用途: 封装自动话题发现接口的完整响应
# --------------------------------------------------------------------------
class DiscoverResponse(BaseModel):
    suggestions: list[TopicSuggestionSchema] = Field(default_factory=list)
