# 配置说明文档

## 配置文件

### 主配置文件

| 文件 | 说明 |
|------|------|
| `.env` | 环境变量配置（敏感信息） |
| `config/defaults.yaml` | 默认配置（非敏感信息） |
| `settings.py` | 配置加载和验证 |

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

## YAML 配置文件

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
