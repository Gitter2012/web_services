# 配置说明文档

> 文档维护说明：配置项以 `settings.py` 与 `config/defaults.yaml` 为准，变更后请同步更新本文档。

## 配置文件

### 主配置文件

| 文件 | 说明 |
|------|------|
| `.env` | 环境变量配置（敏感信息） |
| `config/defaults.yaml` | 默认配置（非敏感信息） |
| `settings.py` | 配置加载和验证 |
| `common/feature_config.py` | 功能开关默认值和管理 |

### 配置优先级

1. 环境变量（最高）
2. `.env` 文件
3. `config/defaults.yaml`
4. 代码默认值（最低）

---

## 环境变量配置

### 数据库配置

```bash
# MySQL 连接
DB_HOST=localhost           # 数据库主机
DB_PORT=3306               # 端口
DB_NAME=research_pulse     # 数据库名
DB_USER=research_user      # 用户名
DB_PASSWORD=your_password  # 密码

# 连接池
DB_POOL_SIZE=10            # 连接池大小
DB_MAX_OVERFLOW=20         # 最大溢出连接
DB_POOL_RECYCLE=3600       # 连接回收时间（秒）
DB_ECHO=false              # SQL 日志
```

### Redis 配置（可选）

```bash
REDIS_HOST=                # Redis 主机（空则禁用）
REDIS_PORT=6379            # 端口
REDIS_PASSWORD=            # 密码
REDIS_DB=0                 # 数据库编号

CACHE_ENABLED=false        # 是否启用缓存
CACHE_DEFAULT_TTL=300      # 默认缓存时间（秒）
```

### JWT 配置

```bash
JWT_SECRET_KEY=your-secret-key     # JWT 密钥（必填）
JWT_ALGORITHM=HS256                # 加密算法
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30 # Token 过期时间（分钟）
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7    # 刷新 Token 过期天数
```

### 超级管理员

```bash
SUPERUSER_USERNAME=admin           # 用户名
SUPERUSER_EMAIL=admin@example.com  # 邮箱
SUPERUSER_PASSWORD=                # 密码（首次启动时创建）
```

### 爬虫配置

```bash
# ArXiv
ARXIV_CATEGORIES=cs.LG,cs.CV,cs.IR,cs.CL,cs.DC  # 默认抓取类目
ARXIV_MAX_RESULTS=50                            # 每个类目最大结果数
ARXIV_DELAY_BASE=3.0                            # 请求延迟基数

# 调度
CRAWL_INTERVAL_HOURS=6     # 抓取间隔（小时）
CLEANUP_HOUR=3             # 清理时间
BACKUP_HOUR=4              # 备份时间
SCHEDULER_TIMEZONE=UTC     # 时区
```

### 数据保留配置

```bash
DATA_RETENTION_DAYS=7      # 文章保留天数
DATA_ARCHIVE_DAYS=30       # 归档天数
BACKUP_DIR=./backups       # 备份目录
BACKUP_ENABLED=true        # 是否启用备份
```

---

## AI 处理配置

### AI 提供方

```bash
AI_PROVIDER=ollama                    # AI 提供方: ollama, openai
```

### Ollama 配置

```bash
OLLAMA_BASE_URL=http://localhost:11434  # Ollama 服务地址
OLLAMA_MODEL=qwen3:32b                 # 主模型
OLLAMA_MODEL_LIGHT=                     # 轻量模型（可选）
OLLAMA_TIMEOUT=120                      # 请求超时（秒）
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
    model: "gpt-4"
    model_light: "gpt-3.5-turbo"
    timeout: 60
  cache:
    enabled: true
    ttl: 86400
  max_content_length: 1500
  max_title_length: 200
```

---

## 向量嵌入 / Milvus 配置

### 环境变量

```bash
EMBEDDING_PROVIDER=sentence-transformers  # 嵌入提供方
EMBEDDING_MODEL=all-MiniLM-L6-v2         # 嵌入模型
EMBEDDING_DIMENSION=384                   # 向量维度
EMBEDDING_SIMILARITY_THRESHOLD=0.85       # 相似度阈值
EMBEDDING_ENABLED=false                   # 是否启用嵌入

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
```

---

## 事件聚类配置

```bash
EVENT_RULE_WEIGHT=0.4          # 规则权重
EVENT_SEMANTIC_WEIGHT=0.6      # 语义权重
EVENT_MIN_SIMILARITY=0.7       # 最小相似度阈值
```

### YAML 配置

```yaml
# config/defaults.yaml
event:
  enabled: false
  clustering:
    rule_weight: 0.4
    semantic_weight: 0.6
    min_similarity: 0.7
    time_window_days: 7
    min_importance_for_new_cluster: 5
  cache_ttl: 300
```

---

## 话题发现配置

```bash
TOPIC_MIN_FREQUENCY=5          # 最小关键词频率
TOPIC_LOOKBACK_DAYS=14         # 回溯天数
```

### YAML 配置

```yaml
# config/defaults.yaml
topic:
  enabled: false
  discovery:
    min_frequency: 5
    lookback_days: 14
    min_confidence: 0.6
  radar:
    snapshot_interval: 7
    min_relevance: 0.5
```

---

## 功能开关配置

功能开关通过 `common/feature_config.py` 管理，存储在数据库 `system_configs` 表中，有 60 秒内存缓存。

### 功能开关列表

| 开关键名 | 默认值 | 说明 |
|---------|--------|------|
| `feature.ai_processor` | false | AI 内容分析 |
| `feature.embedding` | false | 向量嵌入 |
| `feature.event_clustering` | false | 事件聚类 |
| `feature.topic_radar` | false | 话题雷达 |
| `feature.action_items` | false | 行动项提取 |
| `feature.report_generation` | false | 报告生成 |
| `feature.crawler` | true | 爬虫 |
| `feature.backup` | true | 数据备份 |
| `feature.cleanup` | true | 数据清理 |
| `feature.email_notification` | false | 邮件推送 |

### 调度器配置键

| 配置键名 | 默认值 | 说明 |
|---------|--------|------|
| `scheduler.crawl_interval_hours` | 6 | 爬取间隔（小时） |
| `scheduler.cleanup_hour` | 3 | 清理任务执行小时 |
| `scheduler.backup_hour` | 4 | 备份任务执行小时 |
| `scheduler.ai_process_interval_hours` | 1 | AI 处理间隔（小时） |
| `scheduler.embedding_interval_hours` | 2 | 嵌入计算间隔（小时） |
| `scheduler.event_cluster_hour` | 2 | 事件聚类执行小时 |
| `scheduler.topic_discovery_day` | mon | 话题发现执行星期几 |
| `scheduler.topic_discovery_hour` | 1 | 话题发现执行小时 |

### AI 配置键

| 配置键名 | 默认值 | 说明 |
|---------|--------|------|
| `ai.provider` | ollama | AI 提供方 |
| `ai.ollama_base_url` | http://localhost:11434 | Ollama 地址 |
| `ai.ollama_model` | qwen3:32b | Ollama 模型 |
| `ai.ollama_timeout` | 120 | Ollama 超时（秒） |
| `ai.cache_enabled` | true | AI 缓存开关 |
| `ai.cache_ttl` | 86400 | AI 缓存 TTL（秒） |
| `ai.max_content_length` | 1500 | 最大内容长度 |

### 嵌入配置键

| 配置键名 | 默认值 | 说明 |
|---------|--------|------|
| `embedding.provider` | sentence-transformers | 嵌入提供方 |
| `embedding.model` | all-MiniLM-L6-v2 | 嵌入模型 |
| `embedding.similarity_threshold` | 0.85 | 相似度阈值 |
| `embedding.milvus_host` | localhost | Milvus 主机 |
| `embedding.milvus_port` | 19530 | Milvus 端口 |
| `embedding.milvus_collection` | article_embeddings | Milvus 集合名 |

### 事件配置键

| 配置键名 | 默认值 | 说明 |
|---------|--------|------|
| `event.rule_weight` | 0.4 | 规则权重 |
| `event.semantic_weight` | 0.6 | 语义权重 |
| `event.min_similarity` | 0.7 | 最小相似度 |

### 通过 API 修改

```bash
# 启用功能
PUT /api/v1/admin/features/feature.ai_processor
Body: {"enabled": true}

# 修改配置
PUT /api/v1/admin/config/ai.ollama_model
Body: {"value": "qwen3:32b"}

# 批量修改
PUT /api/v1/admin/config/batch
Body: {"configs": {"ai.provider": "ollama", "ai.ollama_model": "qwen3:32b"}}
```

---

## 邮件配置

### SMTP 配置

```bash
# 基础配置
EMAIL_ENABLED=false        # 是否启用
EMAIL_FROM=your@email.com  # 发件人地址
EMAIL_BACKEND=smtp         # 后端类型

# SMTP 服务器
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your@email.com
SMTP_PASSWORD=your-app-password

# 高级配置
SMTP_PORTS=587,465,2525    # 多端口重试
SMTP_SSL_PORTS=465         # SSL 端口
SMTP_TIMEOUT=10.0          # 超时时间
SMTP_RETRIES=3             # 重试次数
SMTP_RETRY_BACKOFF=10.0    # 重试间隔
SMTP_TLS=true              # 启用 TLS
SMTP_SSL=false             # 启用 SSL
```

### SendGrid 配置

```bash
SENDGRID_API_KEY=SG.xxx
SENDGRID_FROM_EMAIL=your@email.com
```

### Mailgun 配置

```bash
MAILGUN_API_KEY=key-xxx
MAILGUN_DOMAIN=mg.yourdomain.com
MAILGUN_FROM_EMAIL=your@email.com
```

### Brevo 配置

```bash
BREVO_API_KEY=xkeysib-xxx
BREVO_FROM_EMAIL=your@email.com
BREVO_FROM_NAME=ResearchPulse
```

### 通知配置

```bash
EMAIL_NOTIFICATION_FREQUENCY=daily  # 推送频率: daily, weekly, instant
EMAIL_NOTIFICATION_TIME=09:00       # 推送时间
EMAIL_MAX_ARTICLES=20               # 每封邮件最大文章数
```

---

## 完整 YAML 配置示例

### config/defaults.yaml

```yaml
# 应用配置
app:
  name: ResearchPulse
  debug: false
  data_dir: ./data
  url_prefix: /researchpulse

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
  access_token_expire_minutes: 30
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
    model: "gpt-4"
    model_light: "gpt-3.5-turbo"
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

用户可在前端或 API 设置以下配置：

### 邮件推送设置

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| email_notifications_enabled | boolean | true | 是否接收邮件 |
| email_digest_frequency | string | daily | 推送频率 |

### 推送频率选项

| 值 | 说明 |
|----|------|
| daily | 每天推送 |
| weekly | 每周一推送 |
| none | 不推送 |

---

## 安全建议

### 必须修改的配置

```bash
# 生产环境必须修改
JWT_SECRET_KEY=<随机生成的密钥>
DB_PASSWORD=<强密码>
SMTP_PASSWORD=<应用专用密码>
```

### 生成安全密钥

```bash
# Python
python -c "import secrets; print(secrets.token_urlsafe(32))"

# OpenSSL
openssl rand -hex 32
```

### 敏感文件处理

```bash
# .gitignore 添加
.env
*.key
*.pem
logs/
data/
backups/
volumes/
```

---

## 配置验证

启动时会自动验证配置：

```python
# settings.py
@property
def is_configured(self) -> bool:
    """检查必要配置是否完整"""
    return bool(self.db_host and self.db_name and self.db_user)
```

---

## 环境差异配置

### 开发环境

```bash
DEBUG=true
DB_ECHO=true
LOG_LEVEL=DEBUG
```

### 生产环境

```bash
DEBUG=false
DB_ECHO=false
LOG_LEVEL=INFO
CACHE_ENABLED=true
```

### 测试环境

```bash
DB_NAME=research_pulse_test
TESTING=true
```
