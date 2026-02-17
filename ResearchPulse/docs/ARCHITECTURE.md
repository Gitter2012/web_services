# 架构设计文档

## 整体架构

ResearchPulse 采用分层架构设计，从上到下分为用户界面层、API 网关层、功能开关层、业务逻辑层和数据访问层。

```
┌─────────────────────────────────────────────────────────────────┐
│                         用户界面层                               │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │   首页      │  │ ResearchPulse│  │  管理后台   │              │
│  │  (导航)     │  │   (文章)     │  │   (管理)    │              │
│  └─────────────┘  └─────────────┘  └─────────────┘              │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                         API 网关层                               │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐  │
│  │文章 API │ │用户 API │ │订阅 API │ │AI API  │ │管理 API │  │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘  │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐  │
│  │嵌入 API │ │事件 API │ │话题 API │ │行动 API │ │报告 API │  │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    功能开关层 (Feature Toggle)                    │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  feature_config.py - 数据库持久化 + 内存缓存 (60s TTL)    │  │
│  │  10 个独立开关: AI/嵌入/事件/话题/行动/报告/爬虫/备份/...  │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                         业务逻辑层                               │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │  认证服务   │  │  订阅服务   │  │  导出服务   │              │
│  └─────────────┘  └─────────────┘  └─────────────┘              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │  爬虫服务   │  │  邮件服务   │  │  调度服务   │              │
│  │ (7种数据源) │  │ (4种后端)  │  │ (8个任务)  │              │
│  └─────────────┘  └─────────────┘  └─────────────┘              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │ AI 分析服务 │  │ 嵌入服务   │  │ 事件聚类   │              │
│  │(3种Provider)│  │(Milvus)    │  │(混合算法)  │              │
│  └─────────────┘  └─────────────┘  └─────────────┘              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │ 话题发现   │  │ 行动项服务 │  │ 报告服务   │              │
│  └─────────────┘  └─────────────┘  └─────────────┘              │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                         数据访问层                               │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │   MySQL     │  │   Milvus    │  │   Redis     │              │
│  │  (主数据)   │  │ (向量数据)  │  │   (缓存)    │              │
│  │ SQLAlchemy  │  │ pymilvus   │  │   可选      │              │
│  └─────────────┘  └─────────────┘  └─────────────┘              │
│  ┌─────────────┐  ┌─────────────┐                               │
│  │   Ollama    │  │   Files     │                               │
│  │  (AI推理)   │  │  (备份)     │                               │
│  └─────────────┘  └─────────────┘                               │
└─────────────────────────────────────────────────────────────────┘
```

## 数据处理流水线

文章从抓取到最终产出报告的完整数据处理流程：

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│  Crawl   │───>│AI Process│───>│ Embed    │───>│ Cluster  │
│ 文章抓取 │    │ AI分析   │    │ 向量化   │    │ 事件聚类 │
│(7种数据源)│    │(3种模型) │    │(384维)   │    │(混合算法)│
└──────────┘    └──────────┘    └──────────┘    └──────────┘
                     │                               │
                     │                               ▼
                     │          ┌──────────┐    ┌──────────┐
                     │          │  Topic   │<───│  Event   │
                     │          │ 话题发现 │    │ 事件追踪 │
                     │          └──────────┘    └──────────┘
                     │               │
                     ▼               ▼
                ┌──────────┐    ┌──────────┐
                │  Action  │    │  Report  │
                │ 行动项   │    │ 报告生成 │
                └──────────┘    └──────────┘
                                     │
                                     ▼
                                ┌──────────┐
                                │  Email   │
                                │ 邮件推送 │
                                └──────────┘
```

**阶段说明：**

| 阶段 | 定时任务 | 功能开关 | 单次处理量 | 说明 |
|------|---------|---------|-----------|------|
| Crawl | 每 6 小时 | `feature.crawler` | 全部活跃源 | 从 7 种数据源抓取文章 |
| AI Process | 每 1 小时 | `feature.ai_processor` | 50 篇 | AI 生成摘要、分类、评分 |
| Embed | 每 2 小时 | `feature.embedding` | 100 篇 | 计算文章向量嵌入到 Milvus |
| Cluster | 每天凌晨 2 点 | `feature.event_clustering` | 200 篇 | 基于相似度聚类文章为事件 |
| Topic | 每周一凌晨 1 点 | `feature.topic_radar` | - | 发现和追踪话题趋势 |
| Action | 随 AI 处理产出 | `feature.action_items` | - | 提取可执行行动项 |
| Report | 用户触发 | `feature.report_generation` | - | 生成周报/月报 |
| Email | 爬取完成后 | `feature.email_notification` | - | 推送用户订阅文章 |

## 模块设计

### 1. 爬虫模块 (apps/crawler)

爬虫模块采用**插件架构**，通过抽象基类 `BaseCrawler` 定义统一接口，各数据源实现独立的爬虫类。

```
crawler/
├── base.py              # 爬虫基类（定义 fetch/parse/save 接口）
├── arxiv/
│   └── crawler.py       # arXiv 爬虫（API 方式）
├── rss/
│   └── crawler.py       # RSS/Atom 爬虫（feedparser）
├── wechat/
│   └── crawler.py       # 微信公众号爬虫（RSS 代理）
├── weibo/
│   └── crawler.py       # 微博热搜爬虫（页面抓取）
├── twitter/
│   └── crawler.py       # Twitter 爬虫（TwitterAPI.io）
├── hackernews/
│   └── crawler.py       # HackerNews 爬虫（HN API）
├── reddit/
│   └── crawler.py       # Reddit 爬虫
└── models/
    ├── article.py       # 文章模型（统一存储所有来源）
    ├── source.py         # 来源模型（ArxivCategory/RssFeed/WechatAccount）
    ├── subscription.py  # 订阅模型
    └── config.py        # 配置模型
```

**爬虫基类设计：**

```python
class BaseCrawler:
    source_type: str          # 来源类型标识
    source_id: str            # 来源唯一标识

    async def fetch()         # 获取原始数据（HTTP 请求）
    async def parse()         # 解析数据为文章对象
    async def save()          # 存入数据库（去重）
    async def run()           # 执行完整爬取流程
```

**各爬虫特点：**

| 爬虫 | 数据获取方式 | 反爬策略 | 特殊处理 |
|------|------------|---------|---------|
| arXiv | arXiv API | 3s 延迟 + 1.5s 抖动 | 分类映射、arXiv ID 提取 |
| RSS | feedparser 解析 | 30s 超时，5 并发 | 多格式兼容（RSS/Atom） |
| 微信 | RSS Feed 代理 | 30s 超时，3 并发 | 图片本地缓存 |
| 微博 | 页面抓取 | 5s 延迟 + 2s 抖动 | Cookie 认证、热搜排名 |
| Twitter | TwitterAPI.io REST | API 速率限制 | 第三方 API 密钥 |
| HackerNews | HN Official API | 标准延迟 | Score/Comments 数据 |
| Reddit | Reddit API | 标准延迟 | Subreddit 过滤 |

**防爬策略架构（common/http.py）：**

```python
# User-Agent 轮换池（10 种浏览器标识）
_USER_AGENTS = [
    "Chrome/Windows", "Chrome/macOS", "Chrome/Linux",
    "Firefox/Windows", "Firefox/macOS", "Firefox/Linux",
    "Safari/macOS", "Edge/Windows",
    "Chrome/Android", "Safari/iOS"
]

# 连接池管理
_SESSION_ROTATE_EVERY = 25            # 每 25 次请求重建连接池
_CONSECUTIVE_ERRORS_BEFORE_ROTATE = 2  # 连续 2 次错误立即轮换

# 请求延迟策略
base_delay + random.uniform(0, jitter) + exponential_backoff
```

### 2. 认证模块 (apps/auth)

```
auth/
├── api.py               # 路由定义（10 个端点）
├── service.py           # 业务逻辑（注册/登录/密码管理）
├── schemas.py           # Pydantic 请求/响应模型
└── dependencies.py      # FastAPI 依赖注入
```

**认证流程：**

```
1. 用户注册 → Pydantic 验证 → bcrypt 哈希(12 rounds) → 存储用户 + 分配角色
2. 用户登录 → 验证密码 → 生成 JWT (access: 24h + refresh: 7d)
3. 请求认证 → Bearer Token → JWT 解码验证 → 注入 current_user
4. Token 刷新 → 验证 refresh token → 颁发新 token 对
5. 修改密码 → 验证旧密码 → bcrypt 新哈希 → 更新
6. 登出 → 客户端清除 Token（JWT 无状态）
```

**RBAC 权限模型：**

```
superuser → 全部权限
    └── admin → articles:*, users:*, admin:access, subscriptions:*
        └── editor → articles:read/write/delete, subscriptions:manage
            └── viewer → articles:read, subscriptions:manage
```

### 3. AI 分析模块 (apps/ai_processor)

采用 **Provider 模式** 支持多种 AI 服务提供商。

```
ai_processor/
├── api.py               # 路由定义（单篇/批量/状态/统计）
├── service.py           # AI 处理服务（Provider 适配）
├── schemas.py           # 请求/响应模型
└── prompts/             # AI 提示词模板
```

**处理流程：**

```
文章内容 → 预过滤(规则/域名快速分类)
    → 截取(max_content_length=1500)
    → 检查缓存(TTL 24h)
    → AI 推理(Ollama/OpenAI/Claude)
    → 结构化输出:
        ├── 摘要 (summary)
        ├── 分类 (category)
        ├── 重要性评分 (importance_score: 1-10)
        ├── 一句话总结 (one_liner)
        ├── 关键要点 (key_points[])
        ├── 影响评估 (impact_assessment)
        └── 行动项 (actionable_items[])
    → 写入 ai_processing_logs（含 token 用量）
```

**支持的 AI 提供方：**

| Provider | 模型 | 用途 | 配置项 |
|----------|------|------|--------|
| Ollama | qwen3:32b（推荐） | 本地推理 | OLLAMA_BASE_URL, OLLAMA_MODEL |
| Ollama | 轻量模型（可选） | 简单任务 | OLLAMA_MODEL_LIGHT |
| OpenAI | gpt-4o / gpt-4o-mini | 云端推理 | OPENAI_API_KEY |
| Claude | claude-3 系列 | 云端推理 | CLAUDE_API_KEY |

**处理优化策略：**

| 策略 | 说明 | 适用场景 |
|------|------|---------|
| rule_based | 基于规则快速分类，跳过 AI | 低重要性文章 |
| domain_fast | 基于域名快速分类 | 已知来源域名 |
| minimal | 精简提示词 | 短内容文章 |
| full | 完整 AI 分析 | 标准文章 |
| cached | 命中缓存 | 已处理文章 |

### 4. 向量嵌入模块 (apps/embedding)

```
embedding/
├── api.py               # 路由定义（计算/批量/相似/统计/重建）
├── service.py           # 嵌入计算服务
├── milvus_client.py     # Milvus 客户端封装
└── schemas.py           # 请求/响应模型
```

**嵌入流程：**

```
文章标题+摘要
    → sentence-transformers(all-MiniLM-L6-v2)
    → 384 维向量
    → 存入 Milvus(article_embeddings collection)
    → 相似文章检索(cosine similarity, threshold 0.85, top-k)
```

**Milvus 配置：**

| 参数 | 值 | 说明 |
|------|-----|------|
| collection_name | article_embeddings | 集合名称 |
| dimension | 384 | 向量维度 |
| index_type | IVF_FLAT | 索引类型 |
| metric_type | COSINE | 距离度量 |
| nlist | 128 | 索引聚类数 |
| nprobe | 16 | 搜索探针数 |
| batch_size | 100 | 批量处理大小 |

### 5. 事件聚类模块 (apps/event)

```
event/
├── api.py               # 路由定义（列表/详情/聚类/时间线）
├── service.py           # 聚类服务
└── schemas.py           # 请求/响应模型
```

**混合聚类算法：**

```
混合相似度 = 规则权重(0.4) × 规则相似度 + 语义权重(0.6) × 语义相似度

规则相似度: 基于标题关键词重叠、分类匹配、来源匹配
语义相似度: 基于 Milvus 向量的 cosine similarity

聚类阈值: min_similarity = 0.7
时间窗口: time_window_days = 7
新事件阈值: min_importance_for_new_cluster = 5
```

**事件生命周期：**

```
active（活跃）→ closed（关闭，无新文章加入）→ archived（归档）
```

### 6. 话题雷达模块 (apps/topic)

```
topic/
├── api.py               # 路由定义（CRUD/发现/趋势/关联文章）
├── service.py           # 话题发现服务
└── schemas.py           # 请求/响应模型
```

**话题发现流程：**

```
最近 N 天文章(lookback_days=14)
    → 关键词提取（标题+摘要分词）
    → 频率统计
    → 过滤(min_frequency=5)
    → 置信度评估(min_confidence=0.6)
    → 话题建议（含 sample_titles）
    → 管理员确认
    → 创建话题
    → 定期快照(snapshot_interval=7 天)
    → 趋势追踪(up/down/stable)
```

**话题生命周期：**

```
new（新发现）→ trending（上升趋势）→ declining（下降）→ dormant（休眠）
```

### 7. 行动项模块 (apps/action)

```
action/
├── api.py               # 路由定义（CRUD/完成/忽略）
├── service.py           # 行动项服务
└── schemas.py           # 请求/响应模型
```

**状态流转：**

```
pending（待处理）→ completed（已完成）
pending（待处理）→ dismissed（已忽略）
```

### 8. 报告生成模块 (apps/report)

```
report/
├── api.py               # 路由定义（列表/周报/月报/详情/删除）
├── service.py           # 报告生成服务
└── schemas.py           # 请求/响应模型
```

**报告类型：**

| 类型 | 周期 | 内容 |
|------|------|------|
| weekly | 周 | 本周文章统计、热门话题、重要事件、行动项汇总 |
| monthly | 月 | 月度趋势分析、话题变化、事件回顾、分类分布 |

### 9. 调度模块 (apps/scheduler)

```
scheduler/
├── tasks.py                  # 调度器管理（启动/停止/注册）
└── jobs/
    ├── crawl_job.py          # 爬取任务（全部活跃源）
    ├── cleanup_job.py        # 清理任务（过期数据）
    ├── backup_job.py         # 备份任务（MySQL dump）
    ├── notification_job.py   # 通知任务（邮件推送）
    ├── ai_process_job.py     # AI 分析任务（50 篇/次）
    ├── embedding_job.py      # 向量嵌入任务（100 篇/次）
    ├── event_cluster_job.py  # 事件聚类任务（200 篇/次）
    └── topic_discovery_job.py # 话题发现任务
```

**任务调度详情：**

| 任务 | 触发器 | 功能开关 | 单次处理量 | 错误处理 |
|------|--------|---------|-----------|---------|
| crawl_job | IntervalTrigger(6h) | feature.crawler | 全部活跃源 | 日志记录，下次继续 |
| cleanup_job | CronTrigger(hour=3) | feature.cleanup | - | 日志记录 |
| backup_job | CronTrigger(hour=4) | feature.backup | - | 日志记录 |
| notification_job | 事件触发 | feature.email_notification | - | 失败重试 |
| ai_process_job | IntervalTrigger(1h) | feature.ai_processor | 50 篇 | 跳过失败，继续处理 |
| embedding_job | IntervalTrigger(2h) | feature.embedding | 100 篇 | 跳过失败，继续处理 |
| event_cluster_job | CronTrigger(hour=2) | feature.event_clustering | 200 篇 | 日志记录 |
| topic_discovery_job | CronTrigger(day=mon, hour=1) | feature.topic_radar | - | 日志记录 |

### 10. 功能开关模块 (common/feature_config.py)

**架构设计：**

```
管理 API → feature_config.py → 数据库(system_configs 表)
                ↕ 内存缓存(60s TTL)
各模块 API → is_feature_enabled(key) → 返回 bool
调度器 → 检查功能开关 → 跳过或执行任务
```

**功能开关列表：**

| 开关 | 默认值 | 控制范围 |
|------|--------|---------|
| feature.ai_processor | false | AI 分析 API + 定时任务 |
| feature.embedding | false | 嵌入 API + 定时任务 |
| feature.event_clustering | false | 事件 API + 定时任务 |
| feature.topic_radar | false | 话题 API + 定时任务 |
| feature.action_items | false | 行动项 API |
| feature.report_generation | false | 报告 API |
| feature.crawler | true | 爬虫定时任务 |
| feature.backup | true | 备份定时任务 |
| feature.cleanup | true | 清理定时任务 |
| feature.email_notification | false | 邮件推送 |

### 11. 邮件模块 (common/email.py)

**支持的后端：**

| 后端 | 协议 | 配置项 | 特性 |
|------|------|--------|------|
| SMTP | SMTP/TLS/SSL | SMTP_HOST, SMTP_PORT, SMTP_PASSWORD | 多端口重试（587/465/2525） |
| SendGrid | REST API | SENDGRID_API_KEY | 高可用 |
| Mailgun | REST API | MAILGUN_API_KEY, MAILGUN_DOMAIN | 自定义域名 |
| Brevo | REST API | BREVO_API_KEY | 原 Sendinblue |

**重试策略：**

- 多端口重试（587 → 465 → 2525）
- SSL/TLS 自动适配
- 失败退避（默认 10 秒间隔）
- 后端自动回退

### 12. HTTP 模块 (common/http.py)

集中管理所有对外 HTTP 请求，内置防爬策略。

**防爬策略：**

```python
# User-Agent 轮换（10 种）
random.choice(_USER_AGENTS)

# 连接池管理
_SESSION_ROTATE_EVERY = 25        # 25 次请求后重建
_CONSECUTIVE_ERRORS_BEFORE_ROTATE = 2  # 连续 2 次错误后轮换

# 请求延迟
delay = base_delay + random.uniform(0, jitter)
# 429/503 时指数退避
delay = min(base_delay * (2 ** retry_count), max_delay)
```

## 数据模型

### 核心模型

```sql
-- 用户表
users (
    id, username, email, password_hash,
    is_active, is_superuser,
    email_notifications_enabled,
    email_digest_frequency,
    created_at, last_login_at
)

-- 角色表
roles (id, name, description)

-- 权限表
permissions (id, name, resource, action, description)

-- 角色-权限关联（多对多）
role_permissions (role_id, permission_id)

-- 用户-角色关联（多对多）
user_roles (user_id, role_id)

-- 文章表（统一存储所有来源）
articles (
    id BIGINT AUTO_INCREMENT,
    source_type VARCHAR,       -- arxiv/rss/wechat/weibo/twitter/hackernews/reddit
    source_id VARCHAR,
    external_id VARCHAR,       -- 去重标识
    title, url, author, summary, content,
    category, tags JSON, keywords JSON,
    publish_time, crawl_time,
    -- arXiv 专用字段
    arxiv_id, arxiv_primary_category,
    -- 微信专用字段
    wechat_account_name,
    -- AI 处理结果
    ai_summary, importance_score,
    UNIQUE KEY (source_type, source_id, external_id)
)

-- 订阅表
user_subscriptions (
    id, user_id, source_type, source_id, is_active,
    created_at
)

-- 用户文章状态（已读/收藏）
user_article_states (
    id, user_id, article_id, is_read, is_starred,
    notes TEXT, read_at, starred_at
)

-- 系统配置（功能开关 + 运行时配置）
system_configs (
    id, key VARCHAR UNIQUE, value TEXT,
    description, updated_at
)
```

### 扩展模型

```sql
-- AI 处理日志
ai_processing_logs (
    id, article_id, provider, model, processing_method,
    summary, category, importance_score, one_liner,
    key_points JSON, impact_assessment JSON, actionable_items JSON,
    input_chars INT, output_chars INT, duration_ms FLOAT,
    is_cached BOOL, error_message,
    created_at
)

-- 文章嵌入元数据（向量存储在 Milvus）
article_embeddings (
    id, article_id, provider, model, dimension,
    created_at
)

-- 事件聚类
event_clusters (
    id, title, description, category,
    first_seen_at, last_updated_at,
    is_active BOOL, article_count INT
)

-- 事件成员（事件-文章关联）
event_members (
    id, event_id, article_id,
    similarity_score FLOAT, detection_method VARCHAR,
    added_at
)

-- 话题
topics (
    id, name, description, keywords JSON,
    is_auto_discovered BOOL, is_active BOOL,
    created_at
)

-- 文章-话题关联
article_topics (
    id, article_id, topic_id,
    match_score FLOAT, matched_keywords JSON
)

-- 话题快照（趋势追踪）
topic_snapshots (
    id, topic_id, article_count INT,
    snapshot_date DATE
)

-- 行动项
action_items (
    id, article_id, user_id,
    type VARCHAR, description TEXT, priority VARCHAR,
    status VARCHAR,  -- pending/completed/dismissed
    completed_at, dismissed_at,
    created_at
)

-- 报告
reports (
    id, user_id, type VARCHAR,  -- weekly/monthly
    period_start DATE, period_end DATE,
    title, content TEXT, stats JSON,
    generated_at, created_at
)
```

### ER 图

```
┌──────────┐     ┌──────────────┐     ┌──────────┐
│  users   │────<│subscriptions │>────│ sources  │
└──────────┘     └──────────────┘     └──────────┘
     │                                     │
     │     ┌──────────┐                   │
     │     │  roles   │<──(user_roles)    │
     │     └──────────┘                   │
     │          │                         │
     │     (role_permissions)             │
     │          │                         │
     │     ┌──────────────┐              │
     │     │ permissions  │              │
     │     └──────────────┘              │
     │                                    │
     │                ┌──────────┐        │
     └───────────────<│ articles │<───────┘
                      └──────────┘
                           │
     ┌─────────┬───────────┼───────────┬─────────────┐
     │         │           │           │             │
┌────────┐┌────────┐┌──────────┐┌───────────┐┌────────────┐
│ai_logs ││embeddings││article  ││event      ││article    │
│        ││        ││_states   ││_members   ││_topics    │
└────────┘└────────┘└──────────┘└───────────┘└────────────┘
                                     │             │
                                     ▼             ▼
                               ┌───────────┐┌──────────┐
                               │event      ││topics    │
                               │_clusters  │└──────────┘
                               └───────────┘     │
                                                 ▼
     ┌──────────┐                          ┌───────────┐
     │ reports  │<────── users             │topic      │
     └──────────┘                          │_snapshots │
                                           └───────────┘
     ┌──────────────┐
     │ action_items │<──── users + articles
     └──────────────┘

     ┌───────────────┐
     │system_configs  │  (功能开关 + 系统配置)
     └───────────────┘
```

## 配置架构

### 四层配置优先级

```
                    优先级从高到低
┌─────────────────────────────────────┐
│ 1. 环境变量（运行时 override）       │  ← 容器化部署
├─────────────────────────────────────┤
│ 2. .env 文件（敏感信息）             │  ← 密码、API 密钥
├─────────────────────────────────────┤
│ 3. config/defaults.yaml（非敏感）    │  ← 默认值
├─────────────────────────────────────┤
│ 4. Python 代码默认值（兜底）         │  ← settings.py Field(default=)
└─────────────────────────────────────┘
```

**实现方式（settings.py）：**

- 基于 `pydantic-settings` 的 `BaseSettings`
- YAML 文件在模块加载时一次性读取并缓存
- `validation_alias` 映射环境变量名（大写形式）
- `field_validator` 实现条件默认值（如 JWT 密钥自动生成）

## 安全设计

### 1. 认证授权

- **密码存储**: bcrypt 哈希（12 rounds，72 字节输入限制）
- **会话管理**: JWT Token（HS256 签名，access + refresh 双 Token）
- **权限控制**: RBAC 角色权限模型（4 级角色）
- **超级用户**: 启动时自动创建，不接收邮件推送

### 2. API 安全

- **CORS**: 可配置跨域策略（开发 `*`，生产指定域名）
- **输入验证**: Pydantic 模型强类型验证
- **SQL 注入**: SQLAlchemy 参数化查询
- **功能隔离**: Feature Toggle 控制模块访问
- **异常处理**: 全局异常处理器，不泄露内部错误信息
- **非 root 运行**: Docker 容器使用 appuser

### 3. 敏感配置

```bash
# 仅通过 .env 文件管理，不提交到版本控制
JWT_SECRET_KEY=xxx
DB_PASSWORD=xxx
SMTP_PASSWORD=xxx
SENDGRID_API_KEY=xxx
TWITTERAPI_IO_KEY=xxx
```

### 4. 爬虫安全

- **User-Agent 轮换**: 模拟真实浏览器请求
- **连接池轮换**: 防止 IP 关联追踪
- **请求限速**: 遵守 robots.txt 和 API 速率限制
- **错误恢复**: 自动重试 + 指数退避

## 性能优化

### 1. 数据库

- 连接池管理（pool_size=10, max_overflow=20）
- 连接自动回收（pool_recycle=3600s）
- 索引优化（source_type, external_id, crawl_time）
- 分页查询，避免全表扫描
- 唯一约束去重（source_type + source_id + external_id）

### 2. 缓存

- HTTP 响应缓存
- 分类数据内存缓存
- AI 处理结果缓存（TTL 24h）
- 功能开关内存缓存（TTL 60s）
- 可选 Redis 缓存层

### 3. 向量检索

- Milvus IVF_FLAT 索引加速
- 批量嵌入计算（最多 1000 篇/次）
- 可配置相似度阈值和 top-k

### 4. 异步处理

- 全异步 API（FastAPI + uvicorn）
- AsyncIOScheduler 非阻塞调度
- 异步数据库驱动（aiomysql）
- 异步 HTTP 客户端（httpx）
- 批量 AI 处理（最多 100 篇/次）

## 扩展性

### 添加新的数据源

1. 在 `apps/crawler/` 下创建新目录
2. 创建爬虫类继承 `BaseCrawler`
3. 实现 `fetch()` 和 `parse()` 方法
4. 在 `apps/scheduler/jobs/crawl_job.py` 中注册
5. 更新 `config/defaults.yaml` 添加配置项

### 添加新的 AI 提供方

1. 在 `apps/ai_processor/service.py` 添加 Provider 适配器
2. 更新 `settings.py` 添加配置字段
3. 更新 `config/defaults.yaml` 添加默认值
4. 在 `AI_PROVIDER` 选择逻辑中注册

### 添加新的邮件后端

1. 在 `common/email.py` 添加发送函数
2. 更新 `send_email()` 路由逻辑
3. 在 `settings.py` 添加 API 密钥配置

### 添加新的功能模块

1. 在 `common/feature_config.py` 的 `DEFAULT_CONFIGS` 中添加功能开关
2. 创建模块目录 `apps/new_module/`（包含 api.py, service.py, schemas.py）
3. 在 `main.py` 注册路由
4. 在 API 层检查功能开关
5. 如需定时任务，在 `apps/scheduler/jobs/` 添加任务文件并在 `tasks.py` 注册

## 部署架构

### 单机部署

```
┌─────────────────────────────────────────┐
│            Nginx (反向代理)              │
│  SSL/TLS + 静态文件 + 负载均衡           │
└─────────────────────────────────────────┘
                    │
                    ▼
           ┌─────────────┐
           │ ResearchPulse│
           │  (uvicorn)   │
           └─────────────┘
                    │
     ┌──────────────┼──────────────┐
     ▼              ▼              ▼
┌────────┐   ┌──────────┐   ┌────────┐
│ MySQL  │   │  Milvus  │   │ Ollama │
└────────┘   └──────────┘   └────────┘
```

### 多实例部署

```
┌─────────────────────────────────────────┐
│              负载均衡器                  │
│        (Nginx / HAProxy / ALB)          │
└─────────────────────────────────────────┘
                    │
        ┌───────────┼───────────┐
        ▼           ▼           ▼
   ┌─────────┐ ┌─────────┐ ┌─────────┐
   │ App #1  │ │ App #2  │ │ App #3  │
   │(uvicorn)│ │(uvicorn)│ │(uvicorn)│
   └─────────┘ └─────────┘ └─────────┘
        │           │           │
        └───────────┼───────────┘
                    ▼
     ┌──────────────────────────────┐
     │         数据存储层           │
     │  ┌────────┐  ┌──────────┐   │
     │  │ MySQL  │  │  Milvus  │   │
     │  │(主从)  │  │ (向量库) │   │
     │  └────────┘  └──────────┘   │
     │  ┌────────┐  ┌──────────┐   │
     │  │ Redis  │  │  Ollama  │   │
     │  │ (缓存) │  │ (AI推理) │   │
     │  └────────┘  └──────────┘   │
     └──────────────────────────────┘
```

### Kubernetes 部署

```
┌─────────────────────────────────────────┐
│              Ingress Controller          │
└─────────────────────────────────────────┘
                    │
        ┌───────────┼───────────┐
        ▼           ▼           ▼
   ┌─────────┐ ┌─────────┐ ┌─────────┐
   │  Pod #1 │ │  Pod #2 │ │  Pod #3 │
   │ /health │ │ /health │ │ /health │
   │  /live  │ │  /live  │ │  /live  │
   │ /ready  │ │ /ready  │ │ /ready  │
   └─────────┘ └─────────┘ └─────────┘
        │           │           │
        └───────────┼───────────┘
                    ▼
     ┌────────────────────────────┐
     │   StatefulSets / Services  │
     │  MySQL  Milvus  Redis      │
     └────────────────────────────┘
```

**健康检查端点：**

| 端点 | 用途 | 检查内容 |
|------|------|---------|
| GET /health | 综合状态 | 数据库 + Redis + Milvus + Ollama |
| GET /health/live | 存活探针 | 进程是否运行 |
| GET /health/ready | 就绪探针 | 数据库是否可连接 |

## 文档与注释规范

为便于自动化文档生成与维护一致性，项目统一采用 Sphinx 兼容的 docstring 规范：

- 英文一行摘要 + 中文补充说明
- `Args` / `Returns` / `Raises` 结构化字段
- 函数/方法签名类型提示与 docstring 类型保持一致
- 使用 Google 风格（Sphinx Napoleon 扩展兼容）

对应的文档生成方式参见 README 的"文档生成（Sphinx）"部分。
