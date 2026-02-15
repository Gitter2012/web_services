# API 文档

## 基础信息

- **Base URL**: `http://localhost:8000`
- **Content-Type**: `application/json`
- **认证方式**: Bearer Token (JWT)
- **文档说明**: 具体字段与模型以代码与 Sphinx 自动化文档为准

---

## 文章 API

### 获取文章列表

```
GET /researchpulse/api/articles
```

**Query Parameters:**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| source_type | string | 否 | 来源类型: arxiv, rss, wechat |
| category | string | 否 | 分类代码 |
| keyword | string | 否 | 搜索关键词 |
| from_date | string | 否 | 起始日期 (YYYY-MM-DD) |
| to_date | string | 否 | 结束日期 (YYYY-MM-DD) |
| sort | string | 否 | 排序字段: publish_time, crawl_time |
| page | int | 否 | 页码，默认 1 |
| page_size | int | 否 | 每页数量，默认 20 |

**Response:**

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
      "arxiv_primary_category": "cs.LG"
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

**Response:**

```json
{
  "type": "arxiv",
  "categories": [
    {
      "id": 1,
      "code": "cs.LG",
      "name": "Machine Learning",
      "description": "..."
    }
  ]
}
```

---

### 获取 RSS 源列表

```
GET /researchpulse/api/feeds
```

**Response:**

```json
{
  "feeds": [
    {
      "id": 1,
      "title": "Hacker News",
      "feed_url": "https://news.ycombinator.com/rss",
      "category": "IT/软件开发",
      "is_active": true
    }
  ]
}
```

---

### 获取所有来源

```
GET /researchpulse/api/sources
```

**Response:**

```json
{
  "arxiv_categories": [...],
  "rss_feeds": [...]
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
```

**认证:** 需要 Bearer Token

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

**Response:**

```json
{
  "subscriptions": [
    {
      "id": 1,
      "source_type": "arxiv_category",
      "source_id": 1,
      "is_active": true
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

**Response:**

```json
{
  "status": "ok",
  "is_starred": true
}
```

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

**Response:**

```json
{
  "id": 1,
  "username": "testuser",
  "email": "test@example.com",
  "is_active": true,
  "is_superuser": false,
  "roles": ["user"],
  "created_at": "2026-01-01T00:00:00",
  "last_login_at": null
}
```

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

**Response:**

```json
{
  "access_token": "eyJ0eXAi...",
  "refresh_token": "eyJ0eXAi...",
  "token_type": "bearer",
  "expires_in": 1800
}
```

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

**Response:**

```json
{
  "access_token": "eyJ0eXAi...",
  "refresh_token": "eyJ0eXAi...",
  "token_type": "bearer",
  "expires_in": 1800
}
```

---

### 获取当前用户

```
GET /api/v1/auth/me
Authorization: Bearer <token>
```

**Response:**

```json
{
  "id": 1,
  "username": "testuser",
  "email": "test@example.com",
  "is_active": true,
  "is_superuser": false,
  "roles": ["user"],
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

**Response:**

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

**Response:**

```json
{
  "detail": "登出成功"
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

**Response:**

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

**Response:**

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

**Response:**

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

**Response:**

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

**Response:**

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

**Response:**

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

**Response:**

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

**Response:**

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

**Response:**

```json
{
  "detail": "索引重建已开始"
}
```

---

## 事件聚类 API

> **功能开关:** `feature.event_clustering`（需启用后方可使用）

### 获取事件列表

```
GET /researchpulse/api/events
Authorization: Bearer <token>
```

**Response:**

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

**Response:**

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
      "similarity_score": 0.88,
      "detection_method": "semantic",
      "added_at": "2026-01-01T10:00:00"
    }
  ]
}
```

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

**Response:**

```json
{
  "total_processed": 100,
  "clustered": 45,
  "new_clusters": 3
}
```

---

### 获取事件时间线

```
GET /researchpulse/api/events/{event_id}/timeline
Authorization: Bearer <token>
```

**Response:**

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

**Response:**

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

**Response:**

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

**Response:**

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

---

### 获取话题趋势

```
GET /researchpulse/api/topics/{topic_id}/trend
Authorization: Bearer <token>
```

**Response:**

```json
{
  "direction": "up",
  "change_percent": 25.0,
  "current_count": 15,
  "previous_count": 12
}
```

---

## 行动项 API

> **功能开关:** `feature.action_items`（需启用后方可使用）

### 获取行动项列表

```
GET /researchpulse/api/actions
Authorization: Bearer <token>
```

返回当前用户的行动项。

**Response:**

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

**Response:**

```json
{
  "id": 1,
  "status": "completed",
  "completed_at": "2026-01-02T15:00:00",
  ...
}
```

---

### 忽略行动项

```
POST /researchpulse/api/actions/{action_id}/dismiss
Authorization: Bearer <token>
```

**Response:**

```json
{
  "id": 1,
  "status": "dismissed",
  "dismissed_at": "2026-01-02T15:00:00",
  ...
}
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

**Response:**

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

## 管理员 API

### 获取统计数据

```
GET /api/v1/admin/stats
Authorization: Bearer <token>
```

**需要权限:** admin 或 superuser

**Response:**

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

```
GET    /api/v1/admin/users
PATCH  /api/v1/admin/users/{user_id}
PUT    /api/v1/admin/users/{user_id}/role
PUT    /api/v1/admin/users/{user_id}/toggle-active
```

#### 更新用户角色

```
PUT /api/v1/admin/users/{user_id}/role
```

**Body:**

```json
{
  "role_name": "admin"
}
```

#### 切换用户激活状态

```
PUT /api/v1/admin/users/{user_id}/toggle-active
```

---

### 爬虫管理

```
GET  /api/v1/admin/crawler/status
POST /api/v1/admin/crawler/trigger
```

#### 获取爬虫状态

**Response:**

```json
{
  "sources": {
    "arxiv": {"active": true, "last_crawl": "..."},
    "rss": {"active": true, "last_crawl": "..."}
  },
  "recent_articles": 150
}
```

---

### 功能开关管理

```
GET /api/v1/admin/features
PUT /api/v1/admin/features/{feature_key}
```

#### 获取所有功能开关

**Response:**

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
```

**Body:**

```json
{
  "enabled": true
}
```

---

### 系统配置管理

```
GET  /api/v1/admin/config
GET  /api/v1/admin/config/groups
PUT  /api/v1/admin/config/{key}
PUT  /api/v1/admin/config/batch
```

#### 获取配置列表

```
GET /api/v1/admin/config
```

#### 获取分组配置

```
GET /api/v1/admin/config/groups
```

按前缀分组返回所有配置项。

#### 更新单项配置

```
PUT /api/v1/admin/config/{key}
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
```

**Body:**

```json
{
  "configs": {
    "ai.provider": "ollama",
    "ai.ollama_model": "qwen3:32b"
  }
}
```

---

### 调度任务管理

```
GET  /api/v1/admin/scheduler/jobs
PUT  /api/v1/admin/scheduler/jobs/{job_id}
POST /api/v1/admin/scheduler/jobs/{job_id}/trigger
```

#### 获取任务列表

**Response:**

```json
[
  {
    "id": "crawl_job",
    "name": "Crawl articles from all sources",
    "trigger": "interval",
    "next_run": "2026-01-01T06:00:00"
  }
]
```

#### 修改任务调度

```
PUT /api/v1/admin/scheduler/jobs/{job_id}
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
```

---

### 备份管理

```
GET  /api/v1/admin/backups
POST /api/v1/admin/backups/create
```

---

## 错误响应

所有错误响应格式：

```json
{
  "detail": "错误描述"
}
```

**HTTP 状态码：**

| 状态码 | 说明 |
|--------|------|
| 200 | 成功 |
| 201 | 创建成功 |
| 400 | 请求参数错误 |
| 401 | 未认证 |
| 403 | 无权限 |
| 404 | 资源不存在 |
| 422 | 参数验证失败 |
| 500 | 服务器错误 |

---

## 速率限制

- 默认: 无限制
- 建议生产环境配置: 100 req/min per IP

---

## Webhook (计划中)

```
POST /webhook/article/new
```

当有新文章时触发通知。
