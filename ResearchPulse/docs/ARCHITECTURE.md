# 架构设计文档

## 整体架构

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
│  └─────────────┘  └─────────────┘  └─────────────┘              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │ AI 分析服务 │  │ 嵌入服务   │  │ 事件聚类   │              │
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
```

**阶段说明：**

| 阶段 | 定时任务 | 功能开关 | 说明 |
|------|---------|---------|------|
| Crawl | 每 6 小时 | `feature.crawler` | 从 arXiv/RSS/微信抓取文章 |
| AI Process | 每 1 小时 | `feature.ai_processor` | AI 生成摘要、分类、评分 |
| Embed | 每 2 小时 | `feature.embedding` | 计算文章向量嵌入到 Milvus |
| Cluster | 每天凌晨 2 点 | `feature.event_clustering` | 基于相似度聚类文章为事件 |
| Topic | 每周一凌晨 1 点 | `feature.topic_radar` | 发现和追踪话题趋势 |
| Action | 随 AI 处理产出 | `feature.action_items` | 提取可执行行动项 |
| Report | 用户触发 | `feature.report_generation` | 生成周报/月报 |

## 模块设计

### 1. 爬虫模块 (apps/crawler)

```
crawler/
├── base.py              # 爬虫基类
├── arxiv/
│   └── crawler.py       # arXiv 爬虫
├── rss/
│   └── crawler.py       # RSS 爬虫
├── wechat/
│   └── crawler.py       # 微信爬虫
└── models/
    ├── article.py       # 文章模型
    ├── source.py        # 来源模型
    ├── subscription.py  # 订阅模型
    └── config.py        # 配置模型
```

**爬虫基类设计：**

```python
class BaseCrawler:
    source_type: str          # 来源类型
    source_id: str            # 来源标识

    async def fetch()         # 获取原始数据
    async def parse()         # 解析数据
    async def save()          # 保存数据
    async def run()           # 执行爬取
```

### 2. 认证模块 (apps/auth)

```
auth/
├── api.py               # 路由定义
├── service.py           # 业务逻辑
├── schemas.py           # 请求/响应模型
└── dependencies.py      # 依赖注入
```

**认证流程：**

```
1. 用户注册 → 密码哈希 → 存储用户
2. 用户登录 → 验证密码 → 生成 JWT (access + refresh)
3. 请求认证 → 验证 JWT → 获取用户
4. Token 刷新 → 验证 refresh token → 颁发新 token 对
5. 修改密码 → 验证旧密码 → 更新密码哈希
6. 登出 → 使 token 失效
```

### 3. AI 分析模块 (apps/ai_processor)

```
ai_processor/
├── api.py               # 路由定义
├── service.py           # AI 处理服务
├── schemas.py           # 请求/响应模型
└── prompts/             # AI 提示词模板
```

**处理流程：**

```
文章内容 → 截取(max_content_length) → AI 推理(Ollama/OpenAI)
    → 摘要 + 分类 + 重要性评分 + 关键要点 + 影响评估 + 行动项
    → 缓存结果(TTL 24h) → 写入 ai_processing_logs
```

**支持的 AI 提供方：**

| Provider | 模型 | 用途 |
|----------|------|------|
| Ollama | qwen3:32b | 本地推理（默认） |
| Ollama | (model_light) | 轻量推理 |
| OpenAI | gpt-4 等 | 云端推理 |

### 4. 向量嵌入模块 (apps/embedding)

```
embedding/
├── api.py               # 路由定义
├── service.py           # 嵌入计算服务
├── schemas.py           # 请求/响应模型
└── milvus_client.py     # Milvus 客户端
```

**嵌入流程：**

```
文章标题+摘要 → sentence-transformers(all-MiniLM-L6-v2)
    → 384维向量 → 存入 Milvus(article_embeddings collection)
    → 相似文章检索(cosine similarity, threshold 0.85)
```

### 5. 事件聚类模块 (apps/event)

```
event/
├── api.py               # 路由定义
├── service.py           # 聚类服务
└── schemas.py           # 请求/响应模型
```

**聚类算法：**

```
混合相似度 = 规则权重(0.4) × 规则相似度 + 语义权重(0.6) × 语义相似度

规则相似度: 基于标题关键词、分类、来源等
语义相似度: 基于向量嵌入的 cosine similarity

阈值: min_similarity = 0.7
```

### 6. 话题雷达模块 (apps/topic)

```
topic/
├── api.py               # 路由定义
├── service.py           # 话题发现服务
└── schemas.py           # 请求/响应模型
```

**话题发现流程：**

```
最近 N 天文章 → 关键词提取 → 频率统计
    → 过滤(min_frequency) → 置信度评估 → 话题建议
    → 管理员确认 → 创建话题 → 定期快照 → 趋势追踪
```

### 7. 行动项模块 (apps/action)

```
action/
├── api.py               # 路由定义
├── service.py           # 行动项服务
└── schemas.py           # 请求/响应模型
```

**状态流转：**

```
pending → completed   (用户标记完成)
pending → dismissed   (用户忽略)
```

### 8. 报告生成模块 (apps/report)

```
report/
├── api.py               # 路由定义
├── service.py           # 报告生成服务
└── schemas.py           # 请求/响应模型
```

**报告类型：**

| 类型 | 周期 | 内容 |
|------|------|------|
| weekly | 周 | 本周文章统计、热门话题、重要事件 |
| monthly | 月 | 月度趋势分析、话题变化、行动项汇总 |

### 9. 调度模块 (apps/scheduler)

```
scheduler/
├── tasks.py                  # 调度器管理
└── jobs/
    ├── crawl_job.py          # 爬取任务
    ├── cleanup_job.py        # 清理任务
    ├── backup_job.py         # 备份任务
    ├── notification_job.py   # 通知任务
    ├── ai_process_job.py     # AI 分析任务
    ├── embedding_job.py      # 向量嵌入任务
    ├── event_cluster_job.py  # 事件聚类任务
    └── topic_discovery_job.py # 话题发现任务
```

**任务调度：**

| 任务 | 触发器 | 功能开关 | 单次处理量 | 说明 |
|------|--------|---------|-----------|------|
| crawl_job | IntervalTrigger(6h) | feature.crawler | 全部活跃源 | 定时爬取 |
| cleanup_job | CronTrigger(hour=3) | feature.cleanup | - | 数据清理 |
| backup_job | CronTrigger(hour=4) | feature.backup | - | 数据备份 |
| notification_job | 事件触发 | feature.email_notification | - | 邮件推送 |
| ai_process_job | IntervalTrigger(1h) | feature.ai_processor | 50 篇 | AI 分析 |
| embedding_job | IntervalTrigger(2h) | feature.embedding | 100 篇 | 向量嵌入 |
| event_cluster_job | CronTrigger(hour=2) | feature.event_clustering | 200 篇 | 事件聚类 |
| topic_discovery_job | CronTrigger(day=mon, hour=1) | feature.topic_radar | - | 话题发现 |

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

| 后端 | 用途 | 配置项 |
|------|------|--------|
| SMTP | 通用邮件发送 | SMTP_HOST, SMTP_PORT |
| SendGrid | API 发送 | SENDGRID_API_KEY |
| Mailgun | API 发送 | MAILGUN_API_KEY |
| Brevo | API 发送 | BREVO_API_KEY |

**特性：**
- 多端口重试（587, 465, 2525）
- SSL/TLS 支持
- 失败自动回退

### 12. HTTP 模块 (common/http.py)

**防爬策略：**

```python
# User-Agent 轮换
_USER_AGENTS = [
    "Chrome/Windows", "Chrome/macOS", "Chrome/Linux",
    "Firefox/Windows", "Firefox/macOS", "Firefox/Linux",
    "Safari/macOS", "Edge/Windows",
    "Chrome/Android", "Safari/iOS"
]

# 连接池轮换
_SESSION_ROTATE_EVERY = 25  # 每 25 次请求重建连接

# 错误恢复
_CONSECUTIVE_ERRORS_BEFORE_ROTATE = 2  # 连续 2 次错误后轮换
```

## 数据模型

### 核心模型（原有）

```sql
-- 用户表
users (
    id, username, email, password_hash,
    is_active, is_superuser,
    email_notifications_enabled,
    email_digest_frequency,
    created_at, last_login_at
)

-- 文章表
articles (
    id, source_type, source_id, external_id,
    title, url, author, summary, content,
    category, tags, publish_time, crawl_time,
    arxiv_id, wechat_account_name, ...
)

-- 订阅表
user_subscriptions (
    id, user_id, source_type, source_id, is_active
)

-- 用户文章状态
user_article_states (
    id, user_id, article_id, is_read, is_starred
)

-- 系统配置
system_configs (
    id, key, value, description, updated_at
)
```

### 扩展模型

```sql
-- AI 处理日志
ai_processing_logs (
    id, article_id, provider, model, processing_method,
    summary, category, importance_score, one_liner,
    key_points, impact_assessment, actionable_items,
    input_chars, output_chars, duration_ms,
    is_cached, error_message,
    created_at
)

-- 文章嵌入
article_embeddings (
    id, article_id, provider, model, dimension,
    embedding_vector,
    created_at
)

-- 事件聚类
event_clusters (
    id, title, description, category,
    first_seen_at, last_updated_at,
    is_active, article_count
)

-- 事件成员
event_members (
    id, event_id, article_id,
    similarity_score, detection_method,
    added_at
)

-- 话题
topics (
    id, name, description, keywords,
    is_auto_discovered, is_active,
    created_at
)

-- 文章话题关联
article_topics (
    id, article_id, topic_id,
    match_score, matched_keywords
)

-- 话题快照
topic_snapshots (
    id, topic_id, article_count,
    snapshot_date
)

-- 行动项
action_items (
    id, article_id, user_id,
    type, description, priority,
    status, completed_at, dismissed_at,
    created_at
)

-- 报告
reports (
    id, user_id, type,
    period_start, period_end,
    title, content, stats,
    generated_at, created_at
)
```

### ER 图

```
┌──────────┐     ┌──────────────┐     ┌──────────┐
│  users   │────<│subscriptions │>────│ sources  │
└──────────┘     └──────────────┘     └──────────┘
     │                                     │
     │                ┌──────────┐         │
     └───────────────<│ articles │<────────┘
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
     │ reports  │<────── users ──────>     │topic      │
     └──────────┘                          │_snapshots │
                                           └───────────┘
     ┌──────────────┐
     │ action_items │<──── users + articles
     └──────────────┘

     ┌───────────────┐
     │system_configs  │  (功能开关 + 系统配置)
     └───────────────┘
```

## 安全设计

### 1. 认证授权

- **密码存储**: bcrypt 哈希
- **会话管理**: JWT Token (access + refresh)
- **权限控制**: RBAC 角色权限

### 2. API 安全

- **CORS**: 可配置跨域策略
- **输入验证**: Pydantic 模型验证
- **SQL 注入**: SQLAlchemy 参数化查询
- **功能隔离**: Feature Toggle 控制模块访问

### 3. 敏感配置

```bash
# .env 文件（不提交到版本控制）
JWT_SECRET_KEY=xxx
DB_PASSWORD=xxx
SMTP_PASSWORD=xxx
OLLAMA_BASE_URL=xxx
```

## 性能优化

### 1. 数据库

- 连接池 (pool_size=10)
- 索引优化
- 分页查询

### 2. 缓存

- HTTP 响应缓存
- 分类数据缓存
- AI 处理结果缓存（TTL 24h）
- 功能开关缓存（TTL 60s）

### 3. 向量检索

- Milvus 向量数据库索引
- 批量嵌入计算（最多 1000 篇/次）
- 可配置相似度阈值

### 4. 异步处理

- 全异步 API
- 后台任务调度
- 批量 AI 处理（最多 100 篇/次）

## 扩展性

### 添加新的数据源

1. 创建爬虫类继承 `BaseCrawler`
2. 实现 `fetch()` 和 `parse()` 方法
3. 注册到调度任务

### 添加新的 AI 提供方

1. 在 `ai_processor/service.py` 添加提供方适配器
2. 更新 `settings.py` 添加配置项
3. 更新 `config/defaults.yaml`

### 添加新的邮件后端

1. 在 `common/email.py` 添加发送函数
2. 更新 `send_email()` 路由逻辑
3. 添加配置项

### 添加新的功能模块

1. 在 `common/feature_config.py` 的 `DEFAULT_CONFIGS` 中添加功能开关
2. 创建模块目录 `apps/new_module/`
3. 在 API 层检查功能开关
4. 如需定时任务，在 `scheduler/tasks.py` 注册

## 文档与注释规范

为便于自动化文档生成与维护一致性，项目统一采用 Sphinx 兼容的 docstring 规范：

- 英文一行摘要 + 中文补充说明
- `Args` / `Returns` / `Raises` 结构化字段
- 函数/方法签名类型提示与 docstring 类型保持一致

对应的文档生成方式参见 README 的“文档生成（Sphinx）”部分。

## 部署架构

```
┌─────────────────────────────────────────┐
│              负载均衡器                  │
└─────────────────────────────────────────┘
                    │
        ┌───────────┼───────────┐
        ▼           ▼           ▼
   ┌─────────┐ ┌─────────┐ ┌─────────┐
   │ App #1  │ │ App #2  │ │ App #3  │
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
