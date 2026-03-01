# =============================================================================
# Event 事件聚类 Pydantic 数据校验模块
# =============================================================================
# 本模块定义了 Event API 所有端点的请求和响应数据结构。
# 使用 Pydantic BaseModel 实现自动的数据验证、序列化和文档生成。
# 主要包含：
#   - 成员 Schema：EventMemberSchema
#   - 聚类 Schema：EventClusterSchema, EventClusterDetailSchema
#   - 列表响应：EventListResponse
#   - 聚类触发：TriggerClusterRequest, TriggerClusterResponse
#   - 时间线：EventTimelineEntry
# =============================================================================

"""Event Pydantic schemas."""
from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

# -----------------------------------------------------------------------------
# 事件成员 Schema
# 表示事件聚类中的一个成员（一篇关联文章的元信息）
# from_attributes=True: 支持从 ORM 对象直接构建
# -----------------------------------------------------------------------------
class EventMemberSchema(BaseModel):
    id: int                                    # 成员记录 ID
    article_id: int                            # 关联的文章 ID
    similarity_score: float = 0.0              # 与事件聚类的相似度分数
    detection_method: str = ""                 # 匹配检测方法
    added_at: Optional[datetime] = None        # 加入事件的时间
    title: str = ""                            # 文章标题
    url: str = ""                              # 原文链接
    model_config = {"from_attributes": True}   # 允许从 ORM 属性构建

# -----------------------------------------------------------------------------
# 事件聚类基础 Schema
# 包含事件的核心信息，不包括成员列表（列表查询时使用）
# -----------------------------------------------------------------------------
class EventClusterSchema(BaseModel):
    id: int                                        # 事件 ID
    title: str = ""                                # 事件标题
    description: Optional[str] = None              # 事件描述
    category: Optional[str] = None                 # 事件分类
    first_seen_at: Optional[datetime] = None       # 首次出现时间
    last_updated_at: Optional[datetime] = None     # 最后更新时间
    is_active: bool = True                         # 是否活跃
    article_count: int = 0                         # 关联文章数量
    model_config = {"from_attributes": True}

# -----------------------------------------------------------------------------
# 事件聚类详情 Schema
# 继承 EventClusterSchema，额外包含成员列表
# 用于单个事件的详情查询
# -----------------------------------------------------------------------------
class EventClusterDetailSchema(EventClusterSchema):
    members: list[EventMemberSchema] = Field(default_factory=list)  # 成员（关联文章）列表

# -----------------------------------------------------------------------------
# 事件列表响应
# 包含分页所需的总数和事件列表
# -----------------------------------------------------------------------------
class EventListResponse(BaseModel):
    total: int = 0                                                      # 符合条件的事件总数
    events: list[EventClusterSchema] = Field(default_factory=list)      # 当前页的事件列表

# -----------------------------------------------------------------------------
# 触发聚类请求
# 用于手动触发事件聚类任务的参数
# -----------------------------------------------------------------------------
class TriggerClusterRequest(BaseModel):
    limit: int = Field(default=100, le=500)            # 本次处理的文章上限，最多 500
    min_importance: int = Field(default=5, ge=1, le=10)  # 最低重要性阈值

# -----------------------------------------------------------------------------
# 触发聚类响应
# 返回聚类任务的执行结果统计
# -----------------------------------------------------------------------------
class TriggerClusterResponse(BaseModel):
    total_processed: int = 0    # 处理的文章总数
    clustered: int = 0          # 成功聚类的文章数（包括加入已有聚类和创建新聚类）
    new_clusters: int = 0       # 新创建的事件聚类数

# -----------------------------------------------------------------------------
# 事件时间线条目
# 事件时间线中的单条记录，表示某个时间点的事件进展
# -----------------------------------------------------------------------------
class EventTimelineEntry(BaseModel):
    date: str                   # 时间点（格式：YYYY-MM-DD HH:MM）
    summary: str = ""           # 该时间点的摘要信息
    article_count: int = 0      # 关联的文章数量
