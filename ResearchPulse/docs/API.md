# API 文档

## 基础信息

- **Base URL**: `http://localhost:8000`
- **Content-Type**: `application/json`
- **认证方式**: Bearer Token (JWT)

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

## 用户 API

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

**Response:**

```json
{
  "id": 1,
  "username": "testuser",
  "email": "test@example.com"
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
  "token_type": "bearer"
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
  "is_superuser": false,
  "roles": ["user"]
}
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
DELETE /api/v1/admin/users/{user_id}
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
