# API 文档

## 基础信息

- **Base URL**: `http://localhost:8000`
- **Content-Type**: `application/json`
- **认证方式**: Bearer Token (JWT)
- **API 前缀**: 认证相关使用 `/api/v1`，业务相关使用 `/researchpulse/api`
- **交互式文档**: 启动服务后访问 `/docs`（Swagger UI）或 `/redoc`（ReDoc）
- **详细模型定义**: 以代码与 Sphinx 自动化文档为准

---

## 目录

- [用户认证 API](#用户认证-api)
- [文章 API](#文章-api)
- [导出 API](#导出-api)
- [订阅 API](#订阅-api)
- [文章状态 API](#文章状态-api)
- [AI 处理 API](#ai-处理-api)
- [向量嵌入 API](#向量嵌入-api)
- [事件聚类 API](#事件聚类-api)
- [话题雷达 API](#话题雷达-api)
- [行动项 API](#行动项-api)
- [报告 API](#报告-api)
- [每日报告 API](#每日报告-api)
- [管理员 API](#管理员-api)
- [健康检查 API](#健康检查-api)
- [错误响应](#错误响应)

---

## 用户认证 API

### 用户注册

```
POST /api/v1/auth/register
```

**Body:**

```json
{
  "username": "testuser",
  "email": "test@example.com",
  "password": "password123"
}
```

**字段约束:**

| 字段 | 约束 |
|------|------|
| username | 3-50 字符，仅允许字母数字 |
| email | 有效邮箱格式 |
| password | 6-100 字符 |

**Response (201):**

```json
{
  "id": 1,
  "username": "testuser",
  "email": "test@example.com",
  "is_active": true,
  "is_superuser": false,
  "roles": ["viewer"],
  "created_at": "2026-01-01T00:00:00",
  "last_login_at": null
}
```

**错误情况:**

| 状态码 | 说明 |
|--------|------|
| 400 | 用户名或邮箱已存在 |
| 422 | 参数验证失败 |

---

### 用户登录

```
POST /api/v1/auth/login
```

**Body:**

```json
{
  "username": "testuser",
  "password": "password123"
}
```

**Response (200):**

```json
{
  "access_token": "eyJ0eXAi...",
  "refresh_token": "eyJ0eXAi...",
  "token_type": "bearer",
  "expires_in": 86400
}
```

**Token 说明:**

| Token 类型 | 有效期 | 用途 |
|-----------|--------|------|
| access_token | 24 小时（可配置） | API 请求认证 |
| refresh_token | 7 天（可配置） | 刷新 access_token |

**JWT Payload 结构:**

```json
{
  "sub": "12345",
  "username": "testuser",
  "email": "test@example.com",
  "type": "access",
  "exp": 1700000000,
  "roles": ["viewer"]
}
```

**错误情况:**

| 状态码 | 说明 |
|--------|------|
| 401 | 用户名或密码错误 |
| 403 | 账号已被禁用 |

---

### 刷新 Token

```
POST /api/v1/auth/refresh
```

**Body:**

```json
{
  "refresh_token": "eyJ0eXAi..."
}
```

**Response (200):**

```json
{
  "access_token": "eyJ0eXAi...",
  "refresh_token": "eyJ0eXAi...",
  "token_type": "bearer",
  "expires_in": 86400
}
```

---

### 获取当前用户

```
GET /api/v1/auth/me
Authorization: Bearer <token>
```

**Response (200):**

```json
{
  "id": 1,
  "username": "testuser",
  "email": "test@example.com",
  "is_active": true,
  "is_superuser": false,
  "roles": ["viewer"],
  "created_at": "2026-01-01T00:00:00",
  "last_login_at": "2026-01-02T10:00:00"
}
```

---

### 修改密码

```
POST /api/v1/auth/change-password
Authorization: Bearer <token>
```

**Body:**

```json
{
  "current_password": "old_password",
  "new_password": "new_password123"
}
```

**字段约束:**

| 字段 | 约束 |
|------|------|
| new_password | 6-100 字符 |

**Response (200):**

```json
{
  "detail": "密码修改成功"
}
```

---

### 登出

```
POST /api/v1/auth/logout
Authorization: Bearer <token>
```

**Response (200):**

```json
{
  "detail": "登出成功"
}
```

> 注意: JWT 为无状态认证，登出操作在客户端清除 Token。

---

## 文章 API

### 获取文章列表

```
GET /researchpulse/api/articles
```

**Query Parameters:**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| source_type | string | 否 | 来源类型: arxiv, rss, wechat, weibo, twitter, hackernews, reddit |
| category | string | 否 | 分类代码（如 cs.LG） |
| keyword | string | 否 | 搜索关键词（匹配标题和摘要） |
| from_date | string | 否 | 起始日期 (YYYY-MM-DD) |
| to_date | string | 否 | 结束日期 (YYYY-MM-DD) |
| sort | string | 否 | 排序字段: publish_time, crawl_time（默认 crawl_time DESC） |
| page | int | 否 | 页码，默认 1 |
| page_size | int | 否 | 每页数量，默认 20，最大 100 |

**Response (200):**

```json
{
  "articles": [
    {
      "id": 1,
      "source_type": "arxiv",
      "title": "论文标题",
      "url": "https://arxiv.org/abs/xxx",
      "author": "作者列表",
      "summary": "摘要内容",
      "category": "cs.LG",
      "tags": ["cs.LG", "cs.AI"],
      "publish_time": "2026-01-01T00:00:00",
      "crawl_time": "2026-01-01T00:00:00",
      "arxiv_id": "2301.00001",
      "arxiv_primary_category": "cs.LG",
      "ai_summary": "AI 生成的摘要（如已处理）",
      "importance_score": 8,
      "is_starred": false
    }
  ],
  "total": 100,
  "page": 1,
  "page_size": 20
}
```

---

### 获取分类列表

```
GET /researchpulse/api/categories
```

**Query Parameters:**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| source_type | string | 否 | 来源类型: arxiv, rss |

**Response (200):**

```json
{
  "type": "arxiv",
  "categories": [
    {
      "id": 1,
      "code": "cs.LG",
      "name": "Machine Learning",
      "description": "机器学习相关研究"
    }
  ]
}
```

---

### 获取 RSS 源列表

```
GET /researchpulse/api/feeds
```

**Response (200):**

```json
{
  "feeds": [
    {
      "id": 1,
      "title": "Hacker News",
      "feed_url": "https://news.ycombinator.com/rss",
      "category": "IT/软件开发",
      "is_active": true,
      "last_fetched_at": "2026-01-01T12:00:00"
    }
  ]
}
```

---

### 获取所有来源

```
GET /researchpulse/api/sources
```

**Response (200):**

```json
{
  "arxiv_categories": [...],
  "rss_feeds": [...],
  "wechat_accounts": [...]
}
```

---

## 导出 API

### 导出 Markdown

```
GET /researchpulse/api/export/markdown
```

**Query Parameters:**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| source_type | string | 否 | 来源类型 |
| category | string | 否 | 分类 |
| from_date | string | 否 | 起始日期 |
| to_date | string | 否 | 结束日期 |
| page_size | int | 否 | 文章数量，默认 100 |

**Response:**

```
Content-Type: text/markdown
Content-Disposition: attachment; filename="researchpulse_2026-01-01.md"

# 学术资讯聚合
...
```

---

### 导出用户订阅

```
GET /researchpulse/api/export/user-markdown
Authorization: Bearer <token>
```

**Query Parameters:**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| from_date | string | 否 | 起始日期 |

---

## 订阅 API

### 获取用户订阅

```
GET /researchpulse/api/subscriptions
Authorization: Bearer <token>
```

**Response (200):**

```json
{
  "subscriptions": [
    {
      "id": 1,
      "source_type": "arxiv_category",
      "source_id": 1,
      "source_name": "cs.LG - Machine Learning",
      "is_active": true,
      "created_at": "2026-01-01T00:00:00"
    }
  ]
}
```

---

### 创建订阅

```
POST /researchpulse/api/subscriptions
Authorization: Bearer <token>
```

**Body:**

```json
{
  "source_type": "arxiv_category",
  "source_id": 1
}
```

**支持的订阅类型:**

| source_type | 说明 |
|------------|------|
| arxiv_category | arXiv 分类 |
| rss_feed | RSS 源 |
| wechat_account | 微信公众号 |

---

### 删除订阅

```
DELETE /researchpulse/api/subscriptions/{source_type}/{source_id}
Authorization: Bearer <token>
```

---

## 文章状态 API

### 切换收藏状态

```
POST /researchpulse/api/articles/{article_id}/star
Authorization: Bearer <token>
```

**Response (200):**

```json
{
  "status": "ok",
  "is_starred": true
}
```

---

## AI 处理 API

> **功能开关:** `feature.ai_processor`（需启用后方可使用）

### 处理单篇文章

```
POST /researchpulse/api/ai/process
Authorization: Bearer <token>
```

**Body:**

```json
{
  "article_id": 1
}
```

**Response (200):**

```json
{
  "article_id": 1,
  "success": true,
  "summary": "AI 生成的文章摘要",
  "category": "人工智能",
  "importance_score": 8,
  "one_liner": "一句话总结",
  "key_points": [
    {
      "type": "技术突破",
      "value": "关键要点内容",
      "impact": "高"
    }
  ],
  "impact_assessment": {
    "short_term": "短期影响描述",
    "long_term": "长期影响描述",
    "certainty": "high"
  },
  "actionable_items": [
    {
      "type": "跟进",
      "description": "建议行动",
      "priority": "高"
    }
  ],
  "provider": "ollama",
  "model": "qwen3:32b",
  "processing_method": "full",
  "error_message": null
}
```

**处理方式 (processing_method):**

| 方式 | 说明 |
|------|------|
| full | 完整 AI 分析 |
| minimal | 精简提示词（短内容优化） |
| rule_based | 基于规则的快速分类（跳过 AI） |
| domain_fast | 基于域名的快速分类 |
| cached | 命中缓存，无需重新处理 |

---

### 批量处理文章

```
POST /researchpulse/api/ai/batch-process
Authorization: Bearer <token>
```

**Body:**

```json
{
  "article_ids": [1, 2, 3],
  "force": false
}
```

**字段约束:**

| 字段 | 约束 |
|------|------|
| article_ids | 最多 100 个 |
| force | 为 true 时忽略缓存重新处理 |

**Response (200):**

```json
{
  "total": 3,
  "processed": 2,
  "cached": 1,
  "failed": 0,
  "results": [...]
}
```

---

### 获取处理状态

```
GET /researchpulse/api/ai/status/{article_id}
Authorization: Bearer <token>
```

**Response (200):**

```json
{
  "article_id": 1,
  "is_processed": true,
  "processed_at": "2026-01-01T12:00:00",
  "provider": "ollama",
  "model": "qwen3:32b",
  "method": "full"
}
```

---

### 获取 Token 用量统计

```
GET /researchpulse/api/ai/token-stats
Authorization: Bearer <token>
```

**Query Parameters:**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| days | int | 否 | 统计天数，默认 7 |

**Response (200):**

```json
[
  {
    "date": "2026-01-01",
    "provider": "ollama",
    "model": "qwen3:32b",
    "total_calls": 150,
    "cached_calls": 30,
    "total_input_chars": 500000,
    "total_output_chars": 100000,
    "avg_duration_ms": 2500.0,
    "failed_calls": 3
  }
]
```

---

## 向量嵌入 API

> **功能开关:** `feature.embedding`（需启用后方可使用）
>
> **前置依赖:** 需要运行 Milvus 向量数据库

### 计算单篇嵌入

```
POST /researchpulse/api/embedding/compute
Authorization: Bearer <token>
```

**Body:**

```json
{
  "article_id": 1
}
```

**Response (200):**

```json
{
  "article_id": 1,
  "success": true,
  "provider": "sentence-transformers",
  "model": "all-MiniLM-L6-v2",
  "dimension": 384,
  "error_message": null
}
```

---

### 批量计算嵌入

```
POST /researchpulse/api/embedding/batch
Authorization: Bearer <token>
```

**Body:**

```json
{
  "article_ids": [1, 2, 3, 4, 5]
}
```

**字段约束:**

| 字段 | 约束 |
|------|------|
| article_ids | 最多 1000 个 |

**Response (200):**

```json
{
  "total": 5,
  "computed": 4,
  "skipped": 1,
  "failed": 0
}
```

---

### 查找相似文章

```
GET /researchpulse/api/embedding/similar/{article_id}
Authorization: Bearer <token>
```

**Query Parameters:**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| top_k | int | 否 | 返回最相似文章数量，默认 10 |
| threshold | float | 否 | 最低相似度阈值，默认 0.85 |

**Response (200):**

```json
{
  "article_id": 1,
  "similar_articles": [
    {
      "article_id": 42,
      "title": "相似文章标题",
      "similarity_score": 0.92
    }
  ]
}
```

---

### 获取嵌入统计

```
GET /researchpulse/api/embedding/stats
Authorization: Bearer <token>
```

**Response (200):**

```json
{
  "total_embeddings": 5000,
  "provider": "sentence-transformers",
  "model": "all-MiniLM-L6-v2",
  "dimension": 384,
  "milvus_connected": true,
  "collection_count": 5000
}
```

---

### 重建索引

```
POST /researchpulse/api/embedding/rebuild
Authorization: Bearer <token>
```

**需要权限:** admin 或 superuser

**Response (200):**

```json
{
  "detail": "索引重建已开始"
}
```

---

## 事件聚类 API

> **功能开关:** `feature.event_clustering`（需启用后方可使用）
>
> **前置依赖:** 建议同时启用 `feature.embedding` 以获得语义聚类能力

### 获取事件列表

```
GET /researchpulse/api/events
Authorization: Bearer <token>
```

**Query Parameters:**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| is_active | bool | 否 | 筛选活跃/关闭事件 |
| category | string | 否 | 分类过滤 |
| page | int | 否 | 页码 |
| page_size | int | 否 | 每页数量 |

**Response (200):**

```json
{
  "total": 15,
  "events": [
    {
      "id": 1,
      "title": "事件标题",
      "description": "事件描述",
      "category": "人工智能",
      "first_seen_at": "2026-01-01T00:00:00",
      "last_updated_at": "2026-01-03T12:00:00",
      "is_active": true,
      "article_count": 5
    }
  ]
}
```

---

### 获取事件详情

```
GET /researchpulse/api/events/{event_id}
Authorization: Bearer <token>
```

**Response (200):**

```json
{
  "id": 1,
  "title": "事件标题",
  "description": "事件描述",
  "category": "人工智能",
  "first_seen_at": "2026-01-01T00:00:00",
  "last_updated_at": "2026-01-03T12:00:00",
  "is_active": true,
  "article_count": 5,
  "members": [
    {
      "id": 1,
      "article_id": 42,
      "title": "文章标题",
      "similarity_score": 0.88,
      "detection_method": "semantic",
      "added_at": "2026-01-01T10:00:00"
    }
  ]
}
```

**detection_method 取值:**

| 值 | 说明 |
|----|------|
| rule | 基于规则匹配 |
| semantic | 基于语义相似度 |
| hybrid | 混合匹配 |

---

### 触发事件聚类

```
POST /researchpulse/api/events/cluster
Authorization: Bearer <token>
```

**Body:**

```json
{
  "limit": 100,
  "min_importance": 5
}
```

**字段约束:**

| 字段 | 约束 |
|------|------|
| limit | 最大 500，默认 100 |
| min_importance | 1-10，默认 5 |

**Response (200):**

```json
{
  "total_processed": 100,
  "clustered": 45,
  "new_clusters": 3
}
```

**聚类算法:**

```
混合相似度 = 规则权重(0.4) x 规则相似度 + 语义权重(0.6) x 语义相似度
聚类阈值 = 0.7（可配置）
```

---

### 获取事件时间线

```
GET /researchpulse/api/events/{event_id}/timeline
Authorization: Bearer <token>
```

**Response (200):**

```json
[
  {
    "date": "2026-01-01",
    "summary": "事件首次出现，3 篇相关报道",
    "article_count": 3
  },
  {
    "date": "2026-01-02",
    "summary": "事件持续发酵，新增 2 篇报道",
    "article_count": 2
  }
]
```

---

## 话题雷达 API

> **功能开关:** `feature.topic_radar`（需启用后方可使用）

### 获取话题列表

```
GET /researchpulse/api/topics
Authorization: Bearer <token>
```

**Query Parameters:**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| is_active | bool | 否 | 筛选活跃话题 |
| is_auto_discovered | bool | 否 | 筛选自动/手动创建 |

**Response (200):**

```json
{
  "total": 10,
  "topics": [
    {
      "id": 1,
      "name": "大语言模型",
      "description": "LLM 相关研究进展",
      "keywords": ["LLM", "GPT", "大模型"],
      "is_auto_discovered": true,
      "is_active": true,
      "article_count": 25,
      "trend_direction": "up",
      "created_at": "2026-01-01T00:00:00"
    }
  ]
}
```

---

### 创建话题

```
POST /researchpulse/api/topics
Authorization: Bearer <token>
```

**Body:**

```json
{
  "name": "大语言模型",
  "description": "LLM 相关研究进展",
  "keywords": ["LLM", "GPT", "大模型"]
}
```

**字段约束:**

| 字段 | 约束 |
|------|------|
| name | 最长 100 字符 |
| keywords | 至少 1 个关键词 |

---

### 获取话题详情

```
GET /researchpulse/api/topics/{topic_id}
Authorization: Bearer <token>
```

---

### 更新话题

```
PUT /researchpulse/api/topics/{topic_id}
Authorization: Bearer <token>
```

**Body:**

```json
{
  "name": "新名称",
  "description": "新描述",
  "keywords": ["关键词1", "关键词2"],
  "is_active": true
}
```

所有字段均为可选。

---

### 删除话题

```
DELETE /researchpulse/api/topics/{topic_id}
Authorization: Bearer <token>
```

---

### 获取话题关联文章

```
GET /researchpulse/api/topics/{topic_id}/articles
Authorization: Bearer <token>
```

**Response (200):**

```json
[
  {
    "article_id": 42,
    "title": "文章标题",
    "match_score": 0.85,
    "matched_keywords": ["LLM", "GPT"]
  }
]
```

---

### 自动发现话题

```
POST /researchpulse/api/topics/discover
Authorization: Bearer <token>
```

**需要权限:** admin 或 superuser

**Response (200):**

```json
{
  "suggestions": [
    {
      "name": "多模态模型",
      "keywords": ["multimodal", "vision-language"],
      "frequency": 15,
      "confidence": 0.87,
      "source": "keyword_frequency",
      "sample_titles": ["论文标题1", "论文标题2"]
    }
  ]
}
```

**发现参数（可通过管理 API 调整）:**

| 参数 | 默认值 | 说明 |
|------|--------|------|
| min_frequency | 5 | 最小关键词出现次数 |
| lookback_days | 14 | 回溯天数 |
| min_confidence | 0.6 | 最小置信度 |

---

### 获取话题趋势

```
GET /researchpulse/api/topics/{topic_id}/trend
Authorization: Bearer <token>
```

**Response (200):**

```json
{
  "direction": "up",
  "change_percent": 25.0,
  "current_count": 15,
  "previous_count": 12
}
```

**趋势方向 (direction):**

| 值 | 说明 |
|----|------|
| up | 上升趋势 |
| down | 下降趋势 |
| stable | 趋势稳定 |

---

## 行动项 API

> **功能开关:** `feature.action_items`（需启用后方可使用）

### 获取行动项列表

```
GET /researchpulse/api/actions
Authorization: Bearer <token>
```

**Query Parameters:**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| status | string | 否 | 状态过滤: pending, completed, dismissed |
| priority | string | 否 | 优先级过滤: 高, 中, 低 |

返回当前用户的行动项。

**Response (200):**

```json
{
  "total": 5,
  "actions": [
    {
      "id": 1,
      "article_id": 42,
      "user_id": 1,
      "type": "跟进",
      "description": "阅读该论文的实验部分",
      "priority": "高",
      "status": "pending",
      "completed_at": null,
      "dismissed_at": null,
      "created_at": "2026-01-01T10:00:00"
    }
  ]
}
```

---

### 创建行动项

```
POST /researchpulse/api/actions
Authorization: Bearer <token>
```

**Body:**

```json
{
  "article_id": 42,
  "type": "跟进",
  "description": "阅读该论文的实验部分",
  "priority": "高"
}
```

**字段约束:**

| 字段 | 说明 | 默认值 |
|------|------|--------|
| type | 行动项类型 | "跟进" |
| priority | 优先级（高/中/低） | "中" |

---

### 获取行动项详情

```
GET /researchpulse/api/actions/{action_id}
Authorization: Bearer <token>
```

---

### 更新行动项

```
PUT /researchpulse/api/actions/{action_id}
Authorization: Bearer <token>
```

**Body:**

```json
{
  "type": "研究",
  "description": "更新后的描述",
  "priority": "低"
}
```

所有字段均为可选。

---

### 完成行动项

```
POST /researchpulse/api/actions/{action_id}/complete
Authorization: Bearer <token>
```

**Response (200):**

```json
{
  "id": 1,
  "status": "completed",
  "completed_at": "2026-01-02T15:00:00"
}
```

---

### 忽略行动项

```
POST /researchpulse/api/actions/{action_id}/dismiss
Authorization: Bearer <token>
```

**Response (200):**

```json
{
  "id": 1,
  "status": "dismissed",
  "dismissed_at": "2026-01-02T15:00:00"
}
```

**状态流转:**

```
pending → completed   (用户标记完成)
pending → dismissed   (用户忽略)
```

---

## 报告 API

> **功能开关:** `feature.report_generation`（需启用后方可使用）

### 获取报告列表

```
GET /researchpulse/api/reports
Authorization: Bearer <token>
```

返回当前用户的报告。

**Response (200):**

```json
{
  "total": 3,
  "reports": [
    {
      "id": 1,
      "user_id": 1,
      "type": "weekly",
      "period_start": "2026-01-06",
      "period_end": "2026-01-12",
      "title": "周报 2026-01-06 ~ 2026-01-12",
      "content": "报告正文内容...",
      "stats": {
        "total_articles": 120,
        "total_events": 5,
        "total_topics": 3,
        "top_categories": ["cs.LG", "cs.CV"]
      },
      "generated_at": "2026-01-13T00:00:00",
      "created_at": "2026-01-13T00:00:00"
    }
  ]
}
```

---

### 生成周报

```
POST /researchpulse/api/reports/weekly
Authorization: Bearer <token>
```

**Body:**

```json
{
  "weeks_ago": 0
}
```

**字段约束:**

| 字段 | 约束 |
|------|------|
| weeks_ago | 0-52，默认 0（当前周） |

---

### 生成月报

```
POST /researchpulse/api/reports/monthly
Authorization: Bearer <token>
```

**Body:**

```json
{
  "months_ago": 0
}
```

---

### 获取报告详情

```
GET /researchpulse/api/reports/{report_id}
Authorization: Bearer <token>
```

---

### 删除报告

```
DELETE /researchpulse/api/reports/{report_id}
Authorization: Bearer <token>
```

---

## 每日报告 API

> **功能开关:** `daily_report.enabled`（默认启用）

每日 arXiv 论文报告，自动按分类生成当天论文信息，支持 AI 翻译和微信公众号格式导出。

### 获取报告列表

```
GET /researchpulse/api/daily-reports
Authorization: Bearer <token>
```

**Query Parameters:**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| report_date | date | 否 | 报告日期（YYYY-MM-DD） |
| category | string | 否 | arXiv 分类代码（如 cs.LG） |
| status | string | 否 | 报告状态（draft/published/archived） |
| page | int | 否 | 页码，默认 1 |
| page_size | int | 否 | 每页数量，默认 20 |

**Response (200):**

```json
{
  "total": 6,
  "page": 1,
  "page_size": 20,
  "reports": [
    {
      "id": 1,
      "report_date": "2026-02-25",
      "category": "cs.LG",
      "category_name": "机器学习",
      "title": "【每日 arXiv】2026年02月25日 机器学习领域新论文",
      "article_count": 15,
      "status": "draft",
      "created_at": "2026-02-26T00:00:00",
      "published_at": null
    }
  ]
}
```

---

### 获取报告详情

```
GET /researchpulse/api/daily-reports/{report_id}
Authorization: Bearer <token>
```

**Response (200):**

```json
{
  "id": 1,
  "report_date": "2026-02-25",
  "category": "cs.LG",
  "category_name": "机器学习",
  "title": "【每日 arXiv】2026年02月25日 机器学习领域新论文",
  "content_markdown": "# 报告内容...",
  "content_wechat": "微信公众号格式内容...",
  "article_count": 15,
  "article_ids": [1, 2, 3],
  "status": "draft",
  "created_at": "2026-02-26T00:00:00",
  "updated_at": "2026-02-26T00:00:00"
}
```

---

### 导出报告

```
GET /researchpulse/api/daily-reports/{report_id}/export?format={format}
Authorization: Bearer <token>
```

**Query Parameters:**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| format | string | 否 | 导出格式：`markdown` 或 `wechat`，默认 `markdown` |

**Response (200):**

```json
{
  "id": 1,
  "report_date": "2026-02-25",
  "category": "cs.LG",
  "category_name": "机器学习",
  "title": "【每日 arXiv】2026年02月25日 机器学习领域新论文",
  "content": "导出的报告内容...",
  "format": "wechat",
  "article_count": 15
}
```

---

### 手动生成报告

```
POST /researchpulse/api/daily-reports/generate
Authorization: Bearer <token>
```

**Body:**

```json
{
  "report_date": "2026-02-25",
  "categories": ["cs.LG", "cs.CV"]
}
```

**字段说明:**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| report_date | date | 否 | 报告日期，默认昨天 |
| categories | array | 否 | 分类列表，默认使用系统配置 |

**Response (200):**

```json
{
  "success": true,
  "message": "成功生成 2 份报告",
  "reports": [...],
  "errors": []
}
```

---

### 导出一天所有报告（合并版）

```
GET /researchpulse/api/daily-reports/export-daily?report_date={date}&format={format}
Authorization: Bearer <token>
```

**Query Parameters:**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| report_date | date | 是 | 报告日期 |
| format | string | 否 | 导出格式：`markdown` 或 `wechat`，默认 `wechat` |

**Response (200):**

```json
{
  "report_date": "2026-02-25",
  "format": "wechat",
  "total_articles": 45,
  "categories": ["机器学习", "计算机视觉", "人工智能"],
  "content": "合并后的报告内容...",
  "reports": [...]
}
```

---

## 管理员 API

> **权限要求:** 以下 API 均需要 admin 或 superuser 权限

### 获取统计数据

```
GET /api/v1/admin/stats
Authorization: Bearer <token>
```

**Response (200):**

```json
{
  "users": 100,
  "articles": 5000,
  "sources": 50,
  "subscriptions": 500
}
```

---

### 用户管理

#### 获取用户列表

```
GET /api/v1/admin/users
Authorization: Bearer <token>
```

#### 更新用户信息

```
PATCH /api/v1/admin/users/{user_id}
Authorization: Bearer <token>
```

#### 更新用户角色

```
PUT /api/v1/admin/users/{user_id}/role
Authorization: Bearer <token>
```

**Body:**

```json
{
  "role_name": "admin"
}
```

**可用角色:**

| 角色 | 说明 |
|------|------|
| viewer | 只读访问 |
| editor | 内容管理 |
| admin | 完全管理 |
| superuser | 超级管理员 |

#### 切换用户激活状态

```
PUT /api/v1/admin/users/{user_id}/toggle-active
Authorization: Bearer <token>
```

---

### 爬虫管理

#### 获取爬虫状态

```
GET /api/v1/admin/crawler/status
Authorization: Bearer <token>
```

**Response (200):**

```json
{
  "sources": {
    "arxiv": {"active": true, "last_crawl": "2026-01-01T12:00:00", "article_count": 1500},
    "rss": {"active": true, "last_crawl": "2026-01-01T12:00:00", "article_count": 800},
    "wechat": {"active": true, "last_crawl": "2026-01-01T12:00:00", "article_count": 200},
    "weibo": {"active": true, "last_crawl": "2026-01-01T12:00:00", "article_count": 100},
    "twitter": {"active": false, "last_crawl": null, "article_count": 0},
    "hackernews": {"active": true, "last_crawl": "2026-01-01T12:00:00", "article_count": 300},
    "reddit": {"active": true, "last_crawl": "2026-01-01T12:00:00", "article_count": 250}
  },
  "recent_articles": 150,
  "next_crawl": "2026-01-01T18:00:00"
}
```

#### 手动触发爬取

```
POST /api/v1/admin/crawler/trigger
Authorization: Bearer <token>
```

---

### 功能开关管理

#### 获取所有功能开关

```
GET /api/v1/admin/features
Authorization: Bearer <token>
```

**Response (200):**

```json
{
  "feature.ai_processor": false,
  "feature.embedding": false,
  "feature.event_clustering": false,
  "feature.topic_radar": false,
  "feature.action_items": false,
  "feature.report_generation": false,
  "feature.crawler": true,
  "feature.backup": true,
  "feature.cleanup": true,
  "feature.email_notification": false
}
```

#### 切换功能开关

```
PUT /api/v1/admin/features/{feature_key}
Authorization: Bearer <token>
```

**Body:**

```json
{
  "enabled": true
}
```

> 注意: 功能开关有 60 秒内存缓存，修改后最多等待 60 秒生效。

---

### 系统配置管理

#### 获取配置列表

```
GET /api/v1/admin/config
Authorization: Bearer <token>
```

#### 获取分组配置

```
GET /api/v1/admin/config/groups
Authorization: Bearer <token>
```

按前缀分组返回所有配置项（如 `ai.*`、`embedding.*`、`scheduler.*`）。

#### 更新单项配置

```
PUT /api/v1/admin/config/{key}
Authorization: Bearer <token>
```

**Body:**

```json
{
  "value": "新值",
  "description": "配置说明"
}
```

#### 批量更新配置

```
PUT /api/v1/admin/config/batch
Authorization: Bearer <token>
```

**Body:**

```json
{
  "configs": {
    "ai.provider": "ollama",
    "ai.ollama_model": "qwen3:32b",
    "scheduler.crawl_interval_hours": "4"
  }
}
```

---

### 调度任务管理

#### 获取任务列表

```
GET /api/v1/admin/scheduler/jobs
Authorization: Bearer <token>
```

**Response (200):**

```json
[
  {
    "id": "crawl_job",
    "name": "Crawl articles from all sources",
    "trigger": "interval",
    "interval_hours": 6,
    "next_run": "2026-01-01T06:00:00",
    "is_active": true
  },
  {
    "id": "cleanup_job",
    "name": "Clean up expired articles",
    "trigger": "cron",
    "cron_hour": 3,
    "next_run": "2026-01-02T03:00:00",
    "is_active": true
  }
]
```

#### 修改任务调度

```
PUT /api/v1/admin/scheduler/jobs/{job_id}
Authorization: Bearer <token>
```

**Body:**

```json
{
  "interval_hours": 4,
  "cron_hour": null,
  "cron_day_of_week": null
}
```

#### 手动触发任务

```
POST /api/v1/admin/scheduler/jobs/{job_id}/trigger
Authorization: Bearer <token>
```

**可触发的任务:**

| job_id | 说明 |
|--------|------|
| crawl_job | 文章爬取 |
| cleanup_job | 数据清理 |
| backup_job | 数据备份 |
| ai_process_job | AI 分析 |
| embedding_job | 向量嵌入 |
| event_cluster_job | 事件聚类 |
| topic_discovery_job | 话题发现 |

---

### 备份管理

#### 获取备份列表

```
GET /api/v1/admin/backups
Authorization: Bearer <token>
```

#### 创建备份

```
POST /api/v1/admin/backups/create
Authorization: Bearer <token>
```

---

## 健康检查 API

### 完整健康检查

```
GET /health
```

无需认证。

**Response (200):**

```json
{
  "status": "healthy",
  "components": {
    "database": "connected",
    "redis": "connected",
    "milvus": "connected",
    "ollama": "connected"
  }
}
```

**status 取值:**

| 值 | 说明 |
|----|------|
| healthy | 所有必须组件正常 |
| unhealthy | 数据库连接异常 |

> 注意: Redis、Milvus、Ollama 未配置时返回 "connected"（视为非必须组件）

---

### 存活探针

```
GET /health/live
```

**Response (200):**

```json
{
  "status": "alive"
}
```

用于 Kubernetes 存活探针，仅检查应用进程是否运行。

---

### 就绪探针

```
GET /health/ready
```

**Response (200):**

```json
{
  "status": "ready"
}
```

**Response (503):**

```json
{
  "detail": "Database not ready"
}
```

用于 Kubernetes 就绪探针，检查数据库是否可连接。

---

## 错误响应

所有错误响应格式：

```json
{
  "detail": "错误描述"
}
```

**HTTP 状态码:**

| 状态码 | 说明 | 常见场景 |
|--------|------|---------|
| 200 | 成功 | 查询、更新操作 |
| 201 | 创建成功 | 注册、创建资源 |
| 400 | 请求参数错误 | 用户名已存在、参数不合法 |
| 401 | 未认证 | Token 缺失或过期 |
| 403 | 无权限 | 非 admin 访问管理 API |
| 404 | 资源不存在 | 文章/用户 ID 不存在 |
| 422 | 参数验证失败 | Pydantic 模型验证错误 |
| 500 | 服务器错误 | 内部异常（不泄露细节） |
| 503 | 服务不可用 | 数据库未就绪（就绪探针） |

---

## 认证说明

### Token 使用方式

在请求头中携带 Bearer Token：

```
Authorization: Bearer eyJ0eXAi...
```

### Token 刷新流程

```
1. access_token 过期 → 客户端收到 401
2. 使用 refresh_token 调用 POST /api/v1/auth/refresh
3. 获取新的 access_token + refresh_token
4. 使用新 token 重新发起请求
```

### 权限层级

```
superuser > admin > editor > viewer
```

| 角色 | 权限范围 |
|------|---------|
| viewer | 只读访问文章、订阅、导出 |
| editor | viewer + 管理内容（文章、订阅） |
| admin | editor + 管理用户、系统配置、功能开关 |
| superuser | 全部权限，首次启动时自动创建 |

---

## 速率限制

- 默认: 无限制
- 建议生产环境配置: 100 req/min per IP（通过 Nginx 或中间件实现）

---

## Webhook (计划中)

```
POST /webhook/article/new
```

当有新文章时触发通知（该功能尚未实现）。
