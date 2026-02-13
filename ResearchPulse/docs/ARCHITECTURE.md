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
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │  文章 API   │  │  用户 API   │  │  订阅 API   │              │
│  └─────────────┘  └─────────────┘  └─────────────┘              │
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
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                         数据访问层                               │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │   MySQL     │  │   Redis     │  │   Files     │              │
│  │  (主数据)   │  │   (缓存)    │  │  (备份)     │              │
│  └─────────────┘  └─────────────┘  └─────────────┘              │
└─────────────────────────────────────────────────────────────────┘
```

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
├── router.py            # 路由定义
├── service.py           # 业务逻辑
└── dependencies.py      # 依赖注入
```

**认证流程：**

```
1. 用户注册 → 密码哈希 → 存储用户
2. 用户登录 → 验证密码 → 生成 JWT
3. 请求认证 → 验证 JWT → 获取用户
```

### 3. 调度模块 (apps/scheduler)

```
scheduler/
├── tasks.py             # 调度器管理
└── jobs/
    ├── crawl_job.py     # 爬取任务
    ├── cleanup_job.py   # 清理任务
    ├── backup_job.py    # 备份任务
    └── notification_job.py  # 通知任务
```

**任务调度：**

| 任务 | 触发器 | 说明 |
|------|--------|------|
| crawl_job | IntervalTrigger(6h) | 定时爬取 |
| cleanup_job | CronTrigger(hour=3) | 数据清理 |
| backup_job | CronTrigger(hour=4) | 数据备份 |
| notification_job | 事件触发 | 邮件推送 |

### 4. 邮件模块 (common/email.py)

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

### 5. HTTP 模块 (common/http.py)

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

### 核心模型

```sql
-- 用户表
users (
    id, username, email, password_hash,
    is_active, is_superuser,
    email_notifications_enabled,  -- 邮件推送开关
    email_digest_frequency        -- 推送频率
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
     ┌─────────────────────┼─────────────────────┐
     │                     │                     │
┌────────────┐      ┌──────────┐         ┌───────────┐
│arxiv_cats  │      │rss_feeds │         │wechat_accs│
└────────────┘      └──────────┘         └───────────┘
```

## 安全设计

### 1. 认证授权

- **密码存储**: bcrypt 哈希
- **会话管理**: JWT Token
- **权限控制**: RBAC 角色权限

### 2. API 安全

- **CORS**: 可配置跨域策略
- **输入验证**: Pydantic 模型验证
- **SQL 注入**: SQLAlchemy 参数化查询

### 3. 敏感配置

```bash
# .env 文件（不提交到版本控制）
JWT_SECRET_KEY=xxx
DB_PASSWORD=xxx
SMTP_PASSWORD=xxx
```

## 性能优化

### 1. 数据库

- 连接池 (pool_size=10)
- 索引优化
- 分页查询

### 2. 缓存

- HTTP 响应缓存
- 分类数据缓存

### 3. 异步处理

- 全异步 API
- 后台任务调度

## 扩展性

### 添加新的数据源

1. 创建爬虫类继承 `BaseCrawler`
2. 实现 `fetch()` 和 `parse()` 方法
3. 注册到调度任务

### 添加新的邮件后端

1. 在 `common/email.py` 添加发送函数
2. 更新 `send_email()` 路由逻辑
3. 添加配置项

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
           ┌───────────────┐
           │    MySQL      │
           │   (主从复制)   │
           └───────────────┘
                    │
           ┌───────────────┐
           │    Redis      │
           │   (可选缓存)   │
           └───────────────┘
```
