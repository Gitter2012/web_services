# 配置说明文档

> 文档维护说明：配置项以 `settings.py` 与 `config/defaults.yaml` 为准，变更后请同步更新本文档。

## 目录

- [配置文件](#配置文件)
- [环境变量配置](#环境变量配置)
- [AI 处理配置](#ai-处理配置)
- [向量嵌入 / Milvus 配置](#向量嵌入--milvus-配置)
- [事件聚类配置](#事件聚类配置)
- [话题发现配置](#话题发现配置)
- [功能开关配置](#功能开关配置)
- [邮件配置](#邮件配置)
- [完整 YAML 配置示例](#完整-yaml-配置示例)
- [用户配置](#用户配置)
- [安全建议](#安全建议)
- [环境差异配置](#环境差异配置)

---

## 配置文件

### 主配置文件

| 文件 | 说明 | 包含内容 |
|------|------|---------|
| `.env` | 环境变量配置 | 敏感信息（密码、API 密钥） |
| `config/defaults.yaml` | 默认配置 | 非敏感默认值（端口、延迟、阈值等） |
| `settings.py` | 配置加载和验证 | Pydantic Settings 定义，类型安全 |
| `common/feature_config.py` | 功能开关管理 | 功能开关默认值、数据库持久化、缓存 |

### 配置优先级（从高到低）

```
1. 环境变量          ← 运行时覆盖（容器化部署）
2. .env 文件         ← 敏感信息（密码、API 密钥）
3. config/defaults.yaml ← 非敏感默认值
4. Python 代码默认值   ← settings.py 中的 Field(default=) 兜底
```

当同一配置项在多个地方定义时，高优先级覆盖低优先级。例如：
- `.env` 中设置 `DB_PORT=3307` 会覆盖 `defaults.yaml` 中的 `database.port: 3306`
- 环境变量 `OLLAMA_MODEL=qwen3:8b` 会覆盖 `.env` 和 YAML 中的设置

---

## 环境变量配置

### 应用基本配置

```bash
APP_NAME=ResearchPulse        # 应用名称
APP_HOST=0.0.0.0              # 监听地址
APP_PORT=8000                 # 监听端口
DEBUG=false                   # 调试模式（影响日志级别和热重载）
URL_PREFIX=/researchpulse     # UI 路由前缀
DATA_DIR=./data               # 数据存储目录
CORS_ORIGINS=*                # CORS 允许的来源（逗号分隔或 *）
CORS_ALLOW_CREDENTIALS=false  # CORS 是否允许携带凭证
```

### 数据库配置

```bash
# MySQL 连接
DB_HOST=localhost           # 数据库主机
DB_PORT=3306               # 端口
DB_NAME=research_pulse     # 数据库名
DB_USER=research_user      # 用户名
DB_PASSWORD=your_password  # 密码（必填）

# 连接池
DB_POOL_SIZE=10            # 连接池基础大小
DB_MAX_OVERFLOW=20         # 最大溢出连接数（突发请求）
DB_POOL_RECYCLE=3600       # 连接回收时间（秒），防止 MySQL wait_timeout 断连
DB_ECHO=false              # 是否输出 SQL 日志（调试用）
```

**连接池说明：**
- `pool_size` + `max_overflow` = 同时可用的最大连接数
- 生产环境建议：`DB_POOL_SIZE=20, DB_MAX_OVERFLOW=40`
- `pool_recycle` 应小于 MySQL 的 `wait_timeout`（默认 28800 秒）

### Redis 配置（可选）

```bash
REDIS_HOST=                # Redis 主机（空则不启用 Redis）
REDIS_PORT=6379            # 端口
REDIS_PASSWORD=            # 密码
REDIS_DB=0                 # 数据库编号

CACHE_ENABLED=false        # 是否启用缓存
CACHE_DEFAULT_TTL=300      # 默认缓存 TTL（秒）
```

> 未配置 Redis 时，系统使用内存缓存（LRU）作为兜底方案。

### JWT 配置

```bash
JWT_SECRET_KEY=your-secret-key     # JWT 签名密钥（必填，生产环境固定值）
JWT_ALGORITHM=HS256                # 签名算法
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=1440 # 访问 Token 过期时间（分钟，默认 24 小时）
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7    # 刷新 Token 过期天数
```

> 未设置 `JWT_SECRET_KEY` 时自动生成随机密钥，但每次重启后之前的 Token 会全部失效。

### 超级管理员

```bash
SUPERUSER_USERNAME=admin           # 用户名
SUPERUSER_EMAIL=admin@example.com  # 邮箱
SUPERUSER_PASSWORD=                # 密码（非空时首次启动自动创建）
```

### 爬虫配置

```bash
# arXiv
ARXIV_CATEGORIES=cs.LG,cs.CV,cs.IR,cs.CL,cs.DC  # 默认抓取类目（逗号分隔）
ARXIV_MAX_RESULTS=50                            # 每个类目最大结果数
ARXIV_DELAY_BASE=3.0                            # 请求延迟基数（秒）

# 微博热搜
WEIBO_TIMEOUT=30                  # 请求超时（秒）
WEIBO_DELAY_BASE=5.0              # 基础延迟（秒），微博反爬较严格
WEIBO_DELAY_JITTER=2.0            # 延迟抖动范围（秒）
WEIBO_MAX_RETRY=3                 # 最大重试次数
WEIBO_RETRY_BACKOFF=10.0          # 重试退避时间（秒）
WEIBO_COOKIE=                     # 微博登录 Cookie（可选，用于认证接口）

# Twitter
TWITTERAPI_IO_KEY=                # TwitterAPI.io API 密钥
                                  # 获取：注册 https://twitterapi.io 账号

# 调度
CRAWL_INTERVAL_HOURS=6     # 爬取间隔（小时）
CLEANUP_HOUR=3             # 数据清理执行时间（0-23）
BACKUP_HOUR=4              # 数据备份执行时间（0-23）
SCHEDULER_TIMEZONE=UTC     # 调度器时区
```

### 数据保留配置

```bash
DATA_RETENTION_DAYS=7      # 活跃数据保留天数
DATA_ARCHIVE_DAYS=30       # 归档数据保留天数
BACKUP_DIR=./backups       # 备份文件目录
BACKUP_ENABLED=true        # 是否启用自动备份
```

---

## AI 处理配置

### AI 提供方选择

```bash
AI_PROVIDER=ollama                    # AI 提供方: ollama / openai / claude
```

### Ollama 配置（本地推理）

```bash
OLLAMA_BASE_URL=http://localhost:11434  # Ollama 服务地址
OLLAMA_MODEL=qwen3:32b                 # 主模型（推荐 qwen3:32b）
OLLAMA_MODEL_LIGHT=                     # 轻量模型（可选，用于简单任务）
OLLAMA_TIMEOUT=120                      # 请求超时（秒）
```

### OpenAI 配置（云端推理）

```bash
OPENAI_API_KEY=sk-xxx                  # OpenAI API 密钥
OPENAI_MODEL=gpt-4o                    # 主模型
OPENAI_MODEL_LIGHT=gpt-4o-mini        # 轻量模型
OPENAI_TIMEOUT=60                      # 请求超时（秒）
```

### Claude 配置（云端推理）

```bash
CLAUDE_API_KEY=sk-ant-xxx              # Anthropic API 密钥
CLAUDE_MODEL=claude-3-sonnet           # 主模型
CLAUDE_TIMEOUT=60                      # 请求超时（秒）
```

### AI 缓存配置

```bash
AI_CACHE_ENABLED=true      # 是否启用 AI 结果缓存
AI_CACHE_TTL=86400         # 缓存 TTL（秒），默认 24 小时
AI_MAX_CONTENT_LENGTH=1500 # 送入 AI 的最大内容长度（字符）
```

### YAML 中的完整 AI 配置

```yaml
# config/defaults.yaml
ai_processor:
  enabled: false                    # 功能开关初始值
  provider: ollama                  # 默认提供方
  ollama:
    base_url: "http://localhost:11434"
    model: "qwen3:32b"             # 主模型
    model_light: ""                 # 轻量模型
    model_screen: ""                # 筛选模型
    timeout: 120                    # 超时（秒）
    keep_alive: "5m"                # 模型保活时间
    thinking_enabled: true          # 思维链
    concurrent_enabled: false       # 并发处理
    workers_heavy: 2                # 重任务 worker 数
    workers_screen: 3               # 筛选 worker 数
  openai:
    model: "gpt-4o"
    model_light: "gpt-4o-mini"
    timeout: 60
  claude:
    model: "claude-3-sonnet"
    timeout: 60
  cache:
    enabled: true
    ttl: 86400                      # 24 小时
  max_content_length: 1500          # 最大内容长度
  max_title_length: 200             # 最大标题长度
```

---

## 向量嵌入 / Milvus 配置

### 环境变量

```bash
EMBEDDING_PROVIDER=sentence-transformers  # 嵌入提供方
EMBEDDING_MODEL=all-MiniLM-L6-v2         # 嵌入模型（384 维）
EMBEDDING_DIMENSION=384                   # 向量维度（需与模型匹配）
EMBEDDING_SIMILARITY_THRESHOLD=0.85       # 相似度阈值
EMBEDDING_ENABLED=false                   # 是否启用嵌入功能

# Milvus 连接
MILVUS_HOST=localhost                     # Milvus 主机
MILVUS_PORT=19530                         # Milvus 端口
MILVUS_COLLECTION_NAME=article_embeddings # 集合名称
```

### YAML 中的完整嵌入配置

```yaml
# config/defaults.yaml
embedding:
  enabled: false
  provider: sentence-transformers
  model: all-MiniLM-L6-v2
  dimension: 384
  similarity_threshold: 0.85
  milvus:
    host: localhost
    port: 19530
    user: ""                        # Milvus 认证用户（可选）
    password: ""                    # Milvus 认证密码（可选）
    collection_name: article_embeddings
    index_type: IVF_FLAT            # 索引类型
    metric_type: COSINE             # 距离度量
    index_params:
      nlist: 128                    # 索引聚类数
    search_params:
      nprobe: 16                    # 搜索探针数
    batch_size: 100                 # 批量处理大小
    timeout: 30                     # 连接超时（秒）
```

**索引类型说明：**

| 索引类型 | 说明 | 适用场景 |
|---------|------|---------|
| IVF_FLAT | 倒排索引 + 精确距离 | 中等规模，精度要求高 |
| IVF_SQ8 | 倒排索引 + 标量量化 | 大规模，节省内存 |
| HNSW | 分层导航小世界图 | 高召回率，高查询性能 |

---

## 事件聚类配置

### 环境变量

```bash
EVENT_RULE_WEIGHT=0.4          # 规则权重（0-1）
EVENT_SEMANTIC_WEIGHT=0.6      # 语义权重（0-1，与规则权重之和为 1）
EVENT_MIN_SIMILARITY=0.7       # 最小相似度阈值
```

### YAML 配置

```yaml
# config/defaults.yaml
event:
  enabled: false
  clustering:
    rule_weight: 0.4               # 规则匹配权重
    semantic_weight: 0.6           # 语义相似度权重
    min_similarity: 0.7            # 聚类最小相似度
    time_window_days: 7            # 时间窗口（天）
    min_importance_for_new_cluster: 5  # 创建新事件的最小重要性
  cache_ttl: 300                   # 事件缓存 TTL（秒）
```

**聚类算法说明：**

```
混合相似度 = rule_weight × 规则相似度 + semantic_weight × 语义相似度

规则相似度 = f(标题关键词重叠, 分类匹配, 来源匹配)
语义相似度 = cosine_similarity(embedding_a, embedding_b)

if 混合相似度 >= min_similarity:
    将文章加入已有事件
elif importance_score >= min_importance_for_new_cluster:
    创建新事件
```

---

## 话题发现配置

### 环境变量

```bash
TOPIC_MIN_FREQUENCY=5          # 最小关键词出现频率
TOPIC_LOOKBACK_DAYS=14         # 话题发现回溯天数
```

### YAML 配置

```yaml
# config/defaults.yaml
topic:
  enabled: false
  discovery:
    min_frequency: 5               # 最小关键词频率
    lookback_days: 14              # 分析多少天内的文章
    min_confidence: 0.6            # 最小话题置信度
  radar:
    snapshot_interval: 7           # 快照间隔（天）
    min_relevance: 0.5             # 文章关联最小匹配度
```

---

## 功能开关配置

功能开关通过 `common/feature_config.py` 管理，存储在数据库 `system_configs` 表中，有 60 秒内存缓存。

### 功能开关列表

| 开关键名 | 默认值 | 说明 | 关联组件 |
|---------|--------|------|---------|
| `feature.ai_processor` | false | AI 内容分析 | AI API + 定时任务 |
| `feature.embedding` | false | 向量嵌入 | 嵌入 API + 定时任务 + Milvus |
| `feature.event_clustering` | false | 事件聚类 | 事件 API + 定时任务 |
| `feature.topic_radar` | false | 话题雷达 | 话题 API + 定时任务 |
| `feature.action_items` | false | 行动项提取 | 行动项 API |
| `feature.report_generation` | false | 报告生成 | 报告 API |
| `feature.crawler` | true | 爬虫 | 爬取定时任务 |
| `feature.backup` | true | 数据备份 | 备份定时任务 |
| `feature.cleanup` | true | 数据清理 | 清理定时任务 |
| `feature.email_notification` | false | 邮件推送 | 通知定时任务 |

### 调度器配置键

| 配置键名 | 默认值 | 说明 | 触发器类型 |
|---------|--------|------|-----------|
| `scheduler.crawl_interval_hours` | 6 | 爬取间隔（小时） | IntervalTrigger |
| `scheduler.cleanup_hour` | 3 | 清理任务执行小时 | CronTrigger |
| `scheduler.backup_hour` | 4 | 备份任务执行小时 | CronTrigger |
| `scheduler.ai_process_interval_hours` | 1 | AI 处理间隔（小时） | IntervalTrigger |
| `scheduler.embedding_interval_hours` | 2 | 嵌入计算间隔（小时） | IntervalTrigger |
| `scheduler.event_cluster_hour` | 2 | 事件聚类执行小时 | CronTrigger |
| `scheduler.topic_discovery_day` | mon | 话题发现执行星期几 | CronTrigger |
| `scheduler.topic_discovery_hour` | 1 | 话题发现执行小时 | CronTrigger |

### AI 配置键（运行时可调）

| 配置键名 | 默认值 | 说明 |
|---------|--------|------|
| `ai.provider` | ollama | AI 提供方 |
| `ai.ollama_base_url` | http://localhost:11434 | Ollama 地址 |
| `ai.ollama_model` | qwen3:32b | Ollama 模型 |
| `ai.ollama_timeout` | 120 | Ollama 超时（秒） |
| `ai.cache_enabled` | true | AI 缓存开关 |
| `ai.cache_ttl` | 86400 | AI 缓存 TTL（秒） |
| `ai.max_content_length` | 1500 | 最大内容长度 |

### 嵌入配置键（运行时可调）

| 配置键名 | 默认值 | 说明 |
|---------|--------|------|
| `embedding.provider` | sentence-transformers | 嵌入提供方 |
| `embedding.model` | all-MiniLM-L6-v2 | 嵌入模型 |
| `embedding.similarity_threshold` | 0.85 | 相似度阈值 |
| `embedding.milvus_host` | localhost | Milvus 主机 |
| `embedding.milvus_port` | 19530 | Milvus 端口 |
| `embedding.milvus_collection` | article_embeddings | Milvus 集合名 |

### 事件配置键（运行时可调）

| 配置键名 | 默认值 | 说明 |
|---------|--------|------|
| `event.rule_weight` | 0.4 | 规则权重 |
| `event.semantic_weight` | 0.6 | 语义权重 |
| `event.min_similarity` | 0.7 | 最小相似度 |

### 通过 API 修改配置

```bash
# 启用功能
curl -X PUT http://localhost:8000/api/v1/admin/features/feature.ai_processor \
  -H "Authorization: Bearer <admin_token>" \
  -H "Content-Type: application/json" \
  -d '{"enabled": true}'

# 修改单项配置
curl -X PUT http://localhost:8000/api/v1/admin/config/ai.ollama_model \
  -H "Authorization: Bearer <admin_token>" \
  -H "Content-Type: application/json" \
  -d '{"value": "qwen3:8b"}'

# 批量修改配置
curl -X PUT http://localhost:8000/api/v1/admin/config/batch \
  -H "Authorization: Bearer <admin_token>" \
  -H "Content-Type: application/json" \
  -d '{"configs": {"ai.provider": "ollama", "ai.ollama_model": "qwen3:32b", "scheduler.crawl_interval_hours": "4"}}'

# 查看分组配置
curl http://localhost:8000/api/v1/admin/config/groups \
  -H "Authorization: Bearer <admin_token>"
```

> 注意: 功能开关有 60 秒内存缓存，修改后最多等待 60 秒生效。重启应用立即生效。

---

## 邮件配置

### SMTP 配置

```bash
# 基础配置
EMAIL_ENABLED=false        # 邮件功能总开关
EMAIL_FROM=your@email.com  # 发件人地址
EMAIL_BACKEND=smtp         # 后端类型: smtp / sendgrid / mailgun / brevo

# SMTP 服务器
SMTP_HOST=smtp.gmail.com   # SMTP 主机
SMTP_PORT=587              # SMTP 端口
SMTP_USER=your@email.com   # SMTP 用户名
SMTP_PASSWORD=your-app-password  # SMTP 密码（Gmail 需使用应用专用密码）

# 高级配置
SMTP_PORTS=587,465,2525    # 多端口重试列表
SMTP_SSL_PORTS=465         # SSL 直连端口列表
SMTP_TIMEOUT=10.0          # 连接超时（秒）
SMTP_RETRIES=3             # 重试次数
SMTP_RETRY_BACKOFF=10.0    # 重试间隔（秒）
SMTP_TLS=true              # 启用 STARTTLS
SMTP_SSL=false             # 启用 SSL 直连
```

**常见 SMTP 服务器配置：**

| 服务商 | 主机 | 端口 | 加密 | 说明 |
|--------|------|------|------|------|
| Gmail | smtp.gmail.com | 587 | TLS | 需要应用专用密码 |
| 163 邮箱 | smtp.163.com | 465 | SSL | 需要授权码 |
| QQ 邮箱 | smtp.qq.com | 465 | SSL | 需要授权码 |
| Yahoo | smtp.mail.yahoo.com | 587 | TLS | 需要应用密码 |
| Outlook | smtp.office365.com | 587 | TLS | 标准密码 |

### SendGrid 配置

```bash
SENDGRID_API_KEY=SG.xxx                # SendGrid API 密钥
SENDGRID_FROM_EMAIL=your@email.com     # 发件人（需在 SendGrid 验证）
```

### Mailgun 配置

```bash
MAILGUN_API_KEY=key-xxx                # Mailgun API 密钥
MAILGUN_DOMAIN=mg.yourdomain.com       # Mailgun 域名
MAILGUN_FROM_EMAIL=your@email.com      # 发件人地址
```

### Brevo 配置

```bash
BREVO_API_KEY=xkeysib-xxx             # Brevo（原 Sendinblue）API 密钥
BREVO_FROM_EMAIL=your@email.com        # 发件人地址
BREVO_FROM_NAME=ResearchPulse          # 发件人名称
```

### 通知配置

```bash
EMAIL_NOTIFICATION_FREQUENCY=daily  # 推送频率: daily / weekly / instant
EMAIL_NOTIFICATION_TIME=09:00       # 推送时间（HH:MM 格式）
EMAIL_MAX_ARTICLES=20               # 每封邮件最大文章数
```

### 手动邮件操作

配置完成后，可使用脚本验证和手动触发邮件发送：

```bash
# 发送测试邮件验证配置
./scripts/email.sh test --to admin@example.com

# 指定后端测试
./scripts/email.sh test --to admin@example.com --backend smtp

# 手动触发用户订阅通知
./scripts/email.sh notify
./scripts/email.sh notify --since 2025-01-01 --max-users 10

# 发送自定义邮件
./scripts/email.sh send --to user@example.com --subject "标题" --body "内容"
```

详见 `scripts/README.md` 中的完整参数说明。

---

## 完整 YAML 配置示例

### config/defaults.yaml

```yaml
# ========================================
# ResearchPulse 默认配置
# 此文件包含所有非敏感配置的默认值
# 敏感信息（密码、密钥）请配置在 .env 文件中
# ========================================

# 应用配置
app:
  name: ResearchPulse
  host: "0.0.0.0"
  port: 8000
  debug: false
  data_dir: ./data
  url_prefix: /researchpulse
  cors_origins: "*"                    # 生产环境改为具体域名
  cors_allow_credentials: false

# 数据库配置
database:
  pool_size: 10
  max_overflow: 20
  pool_recycle: 3600
  echo: false

# 缓存配置
cache:
  enabled: false
  default_ttl: 300

# JWT 配置
jwt:
  algorithm: HS256
  access_token_expire_minutes: 1440    # 24 小时
  refresh_token_expire_days: 7

# 爬虫配置
crawler:
  arxiv:
    categories: cs.LG,cs.CV,cs.IR,cs.CL,cs.DC
    max_results: 50
    delay_base: 3.0
    delay_jitter: 1.5
    batch_delay: 10.0
  rss:
    timeout: 30
    max_concurrent: 5
    user_agent: "ResearchPulse/2.0"
  wechat:
    timeout: 30
    max_concurrent: 3
  weibo:
    timeout: 30
    delay_base: 5.0
    delay_jitter: 2.0
    max_retry: 3
    retry_backoff: 10.0
  twitter:
    timeout: 30
  hackernews:
    timeout: 30
  reddit:
    timeout: 30

# 调度配置
scheduler:
  crawl_interval_hours: 6
  cleanup_hour: 3
  backup_hour: 4
  timezone: UTC

# 数据保留
data_retention:
  active_days: 7
  archive_days: 30
  backup_enabled: true
  backup_dir: ./backups

# 日志配置
logging:
  level: INFO
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# 邮件配置
email:
  enabled: false
  from: ""
  backends: smtp
  smtp:
    host: ""
    port: 587
    ports: "587,465,2525"
    ssl_ports: "465"
    user: ""
    password: ""
    timeout: 10.0
    retries: 3
    retry_backoff: 10.0
    tls: true
    ssl: false
  sendgrid:
    api_key: ""
    retries: 3
    retry_backoff: 10.0
  mailgun:
    api_key: ""
    domain: ""
    retries: 3
    retry_backoff: 10.0
  brevo:
    api_key: ""
    from_name: "ResearchPulse"
    retries: 3
    retry_backoff: 10.0
  notification:
    frequency: daily
    time: "09:00"
    max_articles: 20

# AI 处理配置
ai_processor:
  enabled: false
  provider: ollama
  ollama:
    base_url: "http://localhost:11434"
    model: "qwen3:32b"
    model_light: ""
    model_screen: ""
    timeout: 120
    keep_alive: "5m"
    thinking_enabled: true
    concurrent_enabled: false
    workers_heavy: 2
    workers_screen: 3
  openai:
    model: "gpt-4o"
    model_light: "gpt-4o-mini"
    timeout: 60
  claude:
    model: "claude-3-sonnet"
    timeout: 60
  cache:
    enabled: true
    ttl: 86400
  max_content_length: 1500
  max_title_length: 200

# 向量嵌入配置
embedding:
  enabled: false
  provider: sentence-transformers
  model: all-MiniLM-L6-v2
  dimension: 384
  similarity_threshold: 0.85
  milvus:
    host: localhost
    port: 19530
    user: ""
    password: ""
    collection_name: article_embeddings
    index_type: IVF_FLAT
    metric_type: COSINE
    index_params:
      nlist: 128
    search_params:
      nprobe: 16
    batch_size: 100
    timeout: 30

# 事件聚类配置
event:
  enabled: false
  clustering:
    rule_weight: 0.4
    semantic_weight: 0.6
    min_similarity: 0.7
    time_window_days: 7
    min_importance_for_new_cluster: 5
  cache_ttl: 300

# 话题发现配置
topic:
  enabled: false
  discovery:
    min_frequency: 5
    lookback_days: 14
    min_confidence: 0.6
  radar:
    snapshot_interval: 7
    min_relevance: 0.5

# 行动项配置
action:
  enabled: false

# 报告配置
report:
  enabled: false
```

---

## 用户配置

用户可在前端或 API 设置以下个人配置：

### 邮件推送设置

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| email_notifications_enabled | boolean | true | 是否接收邮件推送 |
| email_digest_frequency | string | daily | 推送频率 |

### 推送频率选项

| 值 | 说明 |
|----|------|
| daily | 每天推送一次摘要 |
| weekly | 每周一推送一次摘要 |
| none | 不推送 |

> 超级管理员默认不接收邮件推送。

---

## 安全建议

### 必须修改的配置

```bash
# 生产环境必须修改以下配置
JWT_SECRET_KEY=<随机生成的密钥>      # 绝对不能使用默认值
DB_PASSWORD=<强密码>                 # 不少于 16 字符
SUPERUSER_PASSWORD=<强密码>          # 首次启动后建议修改
SMTP_PASSWORD=<应用专用密码>         # 邮箱专用密码，非登录密码
```

### 生成安全密钥

```bash
# Python
python -c "import secrets; print(secrets.token_urlsafe(32))"

# OpenSSL
openssl rand -hex 32

# /dev/urandom
head -c 32 /dev/urandom | base64
```

### 敏感文件处理

```bash
# .gitignore 应包含以下内容
.env
*.key
*.pem
logs/
data/
backups/
volumes/
__pycache__/
*.pyc
```

### CORS 配置建议

```bash
# 开发环境
CORS_ORIGINS=*
CORS_ALLOW_CREDENTIALS=false

# 生产环境
CORS_ORIGINS=https://your-domain.com,https://admin.your-domain.com
CORS_ALLOW_CREDENTIALS=true
```

> CORS 规范不允许 `credentials=true` 与 `origins=*` 组合使用。

---

## 环境差异配置

### 开发环境

```bash
DEBUG=true                 # 启用调试模式、热重载
DB_ECHO=true               # 输出 SQL 日志
LOG_LEVEL=DEBUG             # 详细日志
CORS_ORIGINS=*              # 允许所有来源
```

### 测试环境

```bash
DB_NAME=research_pulse_test  # 使用独立测试数据库
TESTING=true                 # 测试标记
LOG_LEVEL=WARNING            # 减少日志噪音
```

### 生产环境

```bash
DEBUG=false                # 关闭调试
DB_ECHO=false              # 关闭 SQL 日志
LOG_LEVEL=INFO             # 标准日志级别
CACHE_ENABLED=true         # 启用缓存
DB_POOL_SIZE=20            # 增大连接池
DB_MAX_OVERFLOW=40         # 增大溢出连接
CORS_ORIGINS=https://your-domain.com  # 限制 CORS
```

---

## 配置验证

启动时会自动验证关键配置：

```python
# settings.py
@property
def is_configured(self) -> bool:
    """检查必要配置是否完整"""
    return bool(self.db_host and self.db_name and self.db_user)
```

如果数据库连接失败，应用会在启动阶段抛出 `RuntimeError` 并终止，日志中会记录详细错误信息。
