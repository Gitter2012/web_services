# ResearchPulse

> 学术资讯聚合与智能分析平台 - 订阅、跟踪、分析、推送最新研究动态

## 项目简介

ResearchPulse 是一个面向学术研究与技术资讯领域的聚合分析平台，支持从 **7 种数据源**（arXiv、RSS、微信公众号、微博热搜、Twitter、HackerNews、Reddit）自动抓取最新文章，并通过多模型 AI 分析（Ollama / OpenAI / Claude）、向量嵌入与语义检索（Milvus）、事件聚类、话题追踪等能力，提供深度内容洞察。系统同时具备用户订阅管理、邮件推送、多格式导出、行动项提取、定期报告生成等完整功能。

### 核心特性

**数据采集**
- 多源聚合 - 支持 arXiv、RSS、微信公众号、微博热搜、Twitter、HackerNews、Reddit 共 7 种数据源
- 智能防爬 - UA 轮换、连接池轮换、自动重试、指数退避、请求抖动
- 定时调度 - 基于 APScheduler 的后台自动抓取与任务编排

**AI 智能分析**
- 多模型支持 - Ollama（本地，推荐 qwen3:32b）、OpenAI（GPT-4o）、Claude
- 文章摘要 - AI 自动生成摘要、分类、重要性评分（1-10）
- 关键要点提取 - 结构化关键发现、影响评估、可执行行动项
- 结果缓存 - 24 小时 TTL 避免重复处理

**语义检索**
- 向量嵌入 - 基于 sentence-transformers（all-MiniLM-L6-v2, 384 维）
- Milvus 存储 - 专业向量数据库，支持高效 cosine 相似度检索
- 相似文章推荐 - 可配置相似度阈值（默认 0.85）的语义匹配

**高级分析**
- 事件聚类 - 混合聚类算法（40% 规则 + 60% 语义），自动聚合相关文章
- 话题雷达 - 自动发现新兴话题，追踪趋势变化（上升/下降/稳定）
- 行动项提取 - 从文章中提取可执行任务，支持优先级和状态管理
- 报告生成 - 自动生成周报/月报，汇总研究动态和统计数据

**用户系统**
- 认证授权 - JWT Token + RBAC 角色权限（admin / editor / viewer）
- 订阅管理 - 按来源类型订阅，个性化信息流
- 收藏管理 - 收藏文章，个人笔记
- 邮件推送 - SMTP / SendGrid / Mailgun / Brevo 多后端
- 多格式导出 - Markdown、JSON、CSV 导出

**运维管理**
- 功能开关 - 10 个独立 Feature Toggle，运行时动态启停
- 管理后台 - 用户管理、爬虫控制、系统配置、调度任务管理
- 健康检查 - /health、/health/live、/health/ready 三端点，支持 Kubernetes
- Docker 部署 - 多阶段构建，非 root 用户，自动健康检查

## 技术栈

| 类别 | 技术 | 说明 |
|------|------|------|
| 后端框架 | FastAPI + Uvicorn | 全异步 ASGI 框架 |
| 主数据库 | MySQL 8.0+ | SQLAlchemy 2.0 异步 ORM |
| 向量数据库 | Milvus 2.3+ | 语义检索与相似文章推荐 |
| 缓存 | Redis 6.0+ | 可选，内存缓存兜底 |
| 定时任务 | APScheduler | AsyncIOScheduler 非阻塞调度 |
| AI 推理 | Ollama / OpenAI / Claude | 本地或云端多模型支持 |
| 向量嵌入 | sentence-transformers | all-MiniLM-L6-v2（384 维） |
| 认证 | PyJWT + bcrypt | JWT 访问令牌 + 刷新令牌 |
| HTTP 客户端 | httpx + aiohttp | 异步请求，防爬策略内置 |
| 模板引擎 | Jinja2 | 前端页面渲染 |
| RSS 解析 | feedparser + BeautifulSoup4 | 多格式 Feed 支持 |
| 邮件 | SMTP / SendGrid / Mailgun / Brevo | 多后端自动回退 |
| 配置管理 | Pydantic Settings + YAML | 四层配置优先级 |
| 文档生成 | Sphinx + Napoleon + Myst | Google 风格 docstring |
| 代码质量 | ruff + mypy + pytest | 静态分析与测试 |
| 容器化 | Docker 多阶段构建 | 生产级安全镜像 |

## 目录结构

```
ResearchPulse/
├── apps/                           # 应用模块（11 个功能模块）
│   ├── auth/                       # 用户认证与授权
│   │   ├── api.py                  # 认证路由（注册/登录/刷新/登出）
│   │   ├── service.py              # 认证业务逻辑
│   │   ├── schemas.py              # 请求/响应数据模型
│   │   └── dependencies.py         # 依赖注入（当前用户获取）
│   ├── admin/                      # 管理后台
│   │   └── api.py                  # 管理路由（用户/爬虫/配置/功能开关）
│   ├── crawler/                    # 爬虫模块（7 种数据源）
│   │   ├── base.py                 # 爬虫基类 BaseCrawler
│   │   ├── arxiv/                  # arXiv 论文爬虫
│   │   ├── rss/                    # RSS/Atom Feed 爬虫
│   │   ├── wechat/                 # 微信公众号爬虫
│   │   ├── weibo/                  # 微博热搜爬虫
│   │   ├── twitter/                # Twitter 爬虫（TwitterAPI.io）
│   │   ├── hackernews/             # HackerNews 爬虫
│   │   ├── reddit/                 # Reddit 爬虫
│   │   └── models/                 # 数据模型（article/source/subscription）
│   ├── ai_processor/               # AI 内容分析
│   │   ├── api.py                  # AI 处理路由
│   │   ├── service.py              # AI 分析服务（多 Provider）
│   │   └── schemas.py              # AI 请求/响应模型
│   ├── embedding/                  # 向量嵌入与语义检索
│   │   ├── api.py                  # 嵌入路由
│   │   ├── service.py              # 嵌入计算服务
│   │   ├── milvus_client.py        # Milvus 客户端封装
│   │   └── schemas.py              # 嵌入请求/响应模型
│   ├── event/                      # 事件聚类
│   │   ├── api.py                  # 事件路由
│   │   ├── service.py              # 聚类算法服务
│   │   └── schemas.py              # 事件请求/响应模型
│   ├── topic/                      # 话题雷达
│   │   ├── api.py                  # 话题路由
│   │   ├── service.py              # 话题发现与追踪服务
│   │   └── schemas.py              # 话题请求/响应模型
│   ├── action/                     # 行动项管理
│   │   ├── api.py                  # 行动项路由
│   │   ├── service.py              # 行动项服务
│   │   └── schemas.py              # 行动项请求/响应模型
│   ├── report/                     # 报告生成
│   │   ├── api.py                  # 报告路由
│   │   ├── service.py              # 报告生成服务
│   │   └── schemas.py              # 报告请求/响应模型
│   ├── scheduler/                  # 定时任务调度
│   │   ├── tasks.py                # 调度器管理（启动/停止/注册）
│   │   └── jobs/                   # 具体任务实现
│   │       ├── crawl_job.py        # 爬取任务
│   │       ├── cleanup_job.py      # 数据清理任务
│   │       ├── backup_job.py       # 数据备份任务
│   │       ├── notification_job.py # 邮件通知任务
│   │       ├── ai_process_job.py   # AI 分析任务
│   │       ├── embedding_job.py    # 向量嵌入任务
│   │       ├── event_cluster_job.py # 事件聚类任务
│   │       ├── action_extract_job.py # 行动项提取任务
│   │       └── topic_discovery_job.py # 话题发现任务
│   ├── pipeline/                   # 流水线任务队列
│   │   ├── models.py               # PipelineTask ORM 模型
│   │   ├── triggers.py             # 下游任务入队触发函数
│   │   └── worker.py               # 任务队列轮询 Worker
│   └── ui/                         # 前端界面
│       ├── api.py                  # UI 路由与模板渲染
│       └── templates/              # Jinja2 模板
├── common/                         # 公共模块
│   ├── email.py                    # 邮件发送（多后端）
│   ├── http.py                     # HTTP 客户端（防爬策略）
│   ├── cache.py                    # 内存缓存
│   ├── markdown.py                 # Markdown 导出
│   ├── feature_config.py           # 功能开关管理
│   └── logger.py                   # 日志工具
├── config/                         # 配置文件
│   ├── defaults.yaml               # 默认配置（非敏感）
│   └── logging.yaml                # 日志配置
├── core/                           # 核心基础设施
│   ├── database.py                 # 数据库连接与会话管理
│   ├── security.py                 # 密码哈希与 JWT 工具
│   ├── dependencies.py             # FastAPI 依赖注入
│   └── models/                     # 基础数据模型
│       ├── base.py                 # ORM 基类（含时间戳 Mixin）
│       ├── user.py                 # 用户模型
│       └── permission.py           # 角色与权限模型
├── docs/                           # 项目文档
│   ├── API.md                      # API 接口文档
│   ├── ARCHITECTURE.md             # 架构设计文档
│   ├── CONFIGURATION.md            # 配置说明文档
│   ├── DEPLOYMENT.md               # 部署指南文档
│   └── CHANGELOG.md                # 更新日志
├── sql/                            # SQL 脚本
│   └── init.sql                    # 数据库初始化
├── alembic/                        # 数据库迁移
│   └── versions/                   # 迁移版本文件
├── scripts/                        # 部署与运维脚本
├── tests/                          # 测试套件
│   ├── conftest.py                 # 测试夹具与数据库配置
│   └── apps/                       # 模块级测试
├── docker-compose.milvus.yml       # Milvus 部署配置
├── Dockerfile                      # 多阶段构建镜像
├── pyproject.toml                  # 项目元数据与依赖管理
├── requirements.txt                # Python 依赖
├── .env.example                    # 环境变量模板
├── main.py                         # 应用入口
├── settings.py                     # 配置管理
└── README.md                       # 项目说明
```

## 快速开始

### 1. 环境要求

| 软件 | 版本 | 必需 | 说明 |
|------|------|------|------|
| Python | 3.10+ | 是 | 支持 3.10 / 3.11 / 3.12 / 3.13 |
| MySQL | 8.0+ | 是 | 主数据库 |
| Redis | 6.0+ | 否 | 缓存层，未配置时使用内存缓存 |
| Milvus | 2.3+ | 否 | 向量嵌入与相似检索功能需要 |
| Ollama | 最新版 | 否 | 本地 AI 推理功能需要 |

### 2. 克隆项目

```bash
git clone https://github.com/web_services/ResearchPulse.git
cd ResearchPulse
```

### 3. 创建虚拟环境

```bash
python -m venv venv
source venv/bin/activate  # Linux/macOS
# venv\Scripts\activate   # Windows
```

### 4. 安装依赖

```bash
# 基础依赖
pip install -r requirements.txt

# 向量嵌入功能（可选）
pip install -e ".[embedding]"

# 开发依赖（测试、lint、类型检查）
pip install -e ".[dev]"

# 文档生成依赖（可选）
pip install -e ".[docs]"
```

### 5. 配置环境变量

```bash
cp .env.example .env
vim .env
```

必填配置项：

```bash
# 数据库连接
DB_HOST=localhost
DB_PORT=3306
DB_NAME=research_pulse
DB_USER=research_user
DB_PASSWORD=your_password

# JWT 密钥（生产环境必须设置固定值）
JWT_SECRET_KEY=your-secret-key

# 超级管理员（首次启动时自动创建）
SUPERUSER_USERNAME=admin
SUPERUSER_EMAIL=admin@example.com
SUPERUSER_PASSWORD=admin_password
```

### 6. 初始化数据库

```bash
# 创建数据库
mysql -u root -p -e "CREATE DATABASE research_pulse CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

# 创建用户并授权
mysql -u root -p -e "CREATE USER 'research_user'@'%' IDENTIFIED BY 'your_password';"
mysql -u root -p -e "GRANT ALL PRIVILEGES ON research_pulse.* TO 'research_user'@'%';"
mysql -u root -p -e "FLUSH PRIVILEGES;"

# 初始化表结构
mysql -u research_user -p research_pulse < sql/init.sql
```

### 7. 启动服务

```bash
# 方式一：直接运行
python main.py

# 方式二：使用 uvicorn（开发模式，支持热重载）
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# 方式三：使用控制台脚本
pip install -e .
researchpulse --host 0.0.0.0 --port 8000
```

服务启动后访问 `http://localhost:8000`。

### 8. 启动可选服务

```bash
# 启动 Milvus（向量嵌入功能需要）
docker compose -f docker-compose.milvus.yml up -d

# 启动 Ollama（本地 AI 推理功能需要）
ollama serve
ollama pull qwen3:32b
```

### 9. 访问页面

| 页面 | URL | 说明 |
|------|-----|------|
| 导航首页 | http://localhost:8000/ | 服务入口门户 |
| ResearchPulse | http://localhost:8000/researchpulse/ | 文章浏览与管理 |
| 管理后台 | http://localhost:8000/researchpulse/admin | 系统管理 |
| API 文档 | http://localhost:8000/docs | Swagger UI |
| ReDoc | http://localhost:8000/redoc | 替代 API 文档 |

## 数据源

| 来源 | 类型 | 说明 | 反爬策略 |
|------|------|------|---------|
| arXiv | 学术论文 | 通过 arXiv API 获取，支持分类筛选 | 3s 基础延迟 + 1.5s 抖动 |
| RSS/Atom | 通用订阅 | 支持任意 RSS/Atom Feed | 30s 超时，5 并发 |
| 微信公众号 | 中文内容 | 通过 RSS Feed 代理获取 | 30s 超时，3 并发 |
| 微博热搜 | 社交热点 | 抓取微博热搜榜单 | 5s 基础延迟 + 2s 抖动，3 次重试 |
| Twitter | 国际社交 | 通过 TwitterAPI.io 第三方 API | API 速率限制 |
| HackerNews | 技术资讯 | Hacker News 热帖聚合 | 标准延迟策略 |
| Reddit | 社区讨论 | Reddit 热门帖子聚合 | 标准延迟策略 |

## API 概览

### 认证 API

```
POST /api/v1/auth/register          # 用户注册
POST /api/v1/auth/login             # 用户登录
POST /api/v1/auth/refresh           # 刷新 Token
GET  /api/v1/auth/me                # 获取当前用户
POST /api/v1/auth/change-password   # 修改密码
POST /api/v1/auth/logout            # 登出
```

### 文章 API

```
GET  /researchpulse/api/articles     # 文章列表（支持筛选、排序、分页）
GET  /researchpulse/api/categories   # 分类列表
GET  /researchpulse/api/feeds        # RSS 源列表
GET  /researchpulse/api/sources      # 所有来源
POST /researchpulse/api/articles/{id}/star  # 收藏/取消收藏
```

### 导出 API

```
GET /researchpulse/api/export/markdown       # 导出 Markdown
GET /researchpulse/api/export/user-markdown   # 导出用户订阅
```

### 订阅 API

```
GET    /researchpulse/api/subscriptions                    # 获取订阅列表
POST   /researchpulse/api/subscriptions                    # 创建订阅
DELETE /researchpulse/api/subscriptions/{type}/{id}        # 删除订阅
```

### AI 处理 API（需启用 `feature.ai_processor`）

```
POST /researchpulse/api/ai/process              # 处理单篇文章
POST /researchpulse/api/ai/batch-process         # 批量处理（最多 100 篇）
GET  /researchpulse/api/ai/status/{article_id}   # 获取处理状态
GET  /researchpulse/api/ai/token-stats           # Token 用量统计
```

### 向量嵌入 API（需启用 `feature.embedding`）

```
POST /researchpulse/api/embedding/compute            # 计算单篇嵌入
POST /researchpulse/api/embedding/batch              # 批量计算（最多 1000 篇）
GET  /researchpulse/api/embedding/similar/{id}       # 查找相似文章
GET  /researchpulse/api/embedding/stats              # 嵌入统计
POST /researchpulse/api/embedding/rebuild            # 重建索引（需 admin）
```

### 事件聚类 API（需启用 `feature.event_clustering`）

```
GET  /researchpulse/api/events                       # 事件列表
GET  /researchpulse/api/events/{event_id}            # 事件详情
POST /researchpulse/api/events/cluster               # 触发聚类
GET  /researchpulse/api/events/{event_id}/timeline   # 事件时间线
```

### 话题雷达 API（需启用 `feature.topic_radar`）

```
GET    /researchpulse/api/topics                     # 话题列表
POST   /researchpulse/api/topics                     # 创建话题
GET    /researchpulse/api/topics/{topic_id}          # 话题详情
PUT    /researchpulse/api/topics/{topic_id}          # 更新话题
DELETE /researchpulse/api/topics/{topic_id}          # 删除话题
GET    /researchpulse/api/topics/{id}/articles       # 关联文章
POST   /researchpulse/api/topics/discover            # 自动发现（需 admin）
GET    /researchpulse/api/topics/{id}/trend          # 趋势追踪
```

### 行动项 API（需启用 `feature.action_items`）

```
GET  /researchpulse/api/actions                      # 行动项列表
POST /researchpulse/api/actions                      # 创建行动项
GET  /researchpulse/api/actions/{action_id}          # 行动项详情
PUT  /researchpulse/api/actions/{action_id}          # 更新行动项
POST /researchpulse/api/actions/{id}/complete        # 标记完成
POST /researchpulse/api/actions/{id}/dismiss         # 标记忽略
```

### 报告 API（需启用 `feature.report_generation`）

```
GET    /researchpulse/api/reports                    # 报告列表
POST   /researchpulse/api/reports/weekly             # 生成周报
POST   /researchpulse/api/reports/monthly            # 生成月报
GET    /researchpulse/api/reports/{report_id}        # 报告详情
DELETE /researchpulse/api/reports/{report_id}        # 删除报告
```

### 管理员 API（需 admin 或 superuser 权限）

```
GET  /api/v1/admin/stats                             # 系统统计
GET  /api/v1/admin/users                             # 用户列表
PUT  /api/v1/admin/users/{id}/role                   # 修改角色
PUT  /api/v1/admin/users/{id}/toggle-active          # 切换状态
GET  /api/v1/admin/crawler/status                    # 爬虫状态
POST /api/v1/admin/crawler/trigger                   # 手动触发爬取
GET  /api/v1/admin/features                          # 功能开关列表
PUT  /api/v1/admin/features/{key}                    # 切换功能开关
GET  /api/v1/admin/config                            # 配置列表
PUT  /api/v1/admin/config/{key}                      # 更新配置
PUT  /api/v1/admin/config/batch                      # 批量更新配置
GET  /api/v1/admin/scheduler/jobs                    # 任务列表
PUT  /api/v1/admin/scheduler/jobs/{id}               # 修改任务调度
POST /api/v1/admin/scheduler/jobs/{id}/trigger       # 手动触发任务
GET  /api/v1/admin/backups                           # 备份列表
POST /api/v1/admin/backups/create                    # 创建备份
```

### 健康检查

```
GET /health          # 组件状态（数据库/Redis/Milvus/Ollama）
GET /health/live     # Kubernetes 存活探针
GET /health/ready    # Kubernetes 就绪探针
```

完整 API 文档请参考 [docs/API.md](docs/API.md) 或启动服务后访问 `/docs`（Swagger UI）。

## 功能开关

所有高级功能默认关闭，可通过管理后台或 API 独立启停：

| 功能开关 | 说明 | 默认值 | 关联定时任务 |
|---------|------|--------|------------|
| `feature.crawler` | 爬虫 | true | 每 6 小时 |
| `feature.ai_processor` | AI 内容分析 | false | 每 1 小时 |
| `feature.embedding` | 向量嵌入 | false | 每 2 小时 |
| `feature.event_clustering` | 事件聚类 | false | 每天凌晨 2 点 |
| `feature.topic_radar` | 话题雷达 | false | 每周一凌晨 1 点 |
| `feature.action_items` | 行动项提取 | false | - |
| `feature.report_generation` | 报告生成 | false | - |
| `feature.email_notification` | 邮件推送 | false | 抓取完成后 |
| `feature.backup` | 数据备份 | true | 每天凌晨 4 点 |
| `feature.cleanup` | 数据清理 | true | 每天凌晨 3 点 |

通过管理 API 切换：

```bash
# 启用 AI 分析
curl -X PUT http://localhost:8000/api/v1/admin/features/feature.ai_processor \
  -H "Authorization: Bearer <admin_token>" \
  -H "Content-Type: application/json" \
  -d '{"enabled": true}'
```

## 定时任务

| 任务 | 触发器 | 功能开关 | 单次处理量 | 说明 |
|------|--------|---------|-----------|------|
| crawl_job | 每 6 小时 | `feature.crawler` | 全部活跃源 | 爬取所有数据源 |
| ai_process_job | 每 1 小时 | `feature.ai_processor` | 200 篇（可配置） | AI 分析新文章 |
| embedding_job | 每 2 小时 | `feature.embedding` | 500 篇（可配置） | 计算文章向量嵌入 |
| event_cluster_job | 每天 02:00 | `feature.event_clustering` | 500 篇（可配置） | 聚类文章为事件 |
| action_extract_job | 每 2 小时 | `feature.action_items` | 200 篇（可配置） | 提取行动项 |
| topic_discovery_job | 每周一 01:00 | `feature.topic_radar` | - | 发现新兴话题 |
| cleanup_job | 每天 03:00 | `feature.cleanup` | - | 清理过期数据 |
| backup_job | 每天 04:00 | `feature.backup` | - | 备份文章数据 |
| notification_job | 爬取完成后 | `feature.email_notification` | - | 推送用户订阅 |
| pipeline_worker | 每 10 分钟 | 无（继承各 job） | 按需 | 消费流水线任务队列 |

所有调度参数可通过管理 API 动态调整。

## 配置说明

### 配置优先级（从高到低）

1. **环境变量** - 运行时覆盖
2. **`.env` 文件** - 存放敏感信息（密码、API 密钥）
3. **`config/defaults.yaml`** - 非敏感默认值
4. **代码默认值** - 兜底方案

### 数据库配置

```bash
DB_HOST=localhost        DB_PORT=3306
DB_NAME=research_pulse   DB_USER=research_user
DB_PASSWORD=your_password
DB_POOL_SIZE=10          DB_MAX_OVERFLOW=20
```

### 邮件配置

```bash
EMAIL_ENABLED=true
EMAIL_FROM=your-email@gmail.com
EMAIL_BACKEND=smtp          # smtp / sendgrid / mailgun / brevo
SMTP_HOST=smtp.gmail.com    SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password
```

验证邮件配置：

```bash
# 发送测试邮件
./scripts/email.sh test --to your@email.com

# 手动触发用户通知
./scripts/email.sh notify

# 发送自定义邮件
./scripts/email.sh send --to user@example.com --subject "标题" --body "内容"
```

### AI / Embedding 配置

```bash
# AI 推理
AI_PROVIDER=ollama                          # ollama / openai / claude
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen3:32b
OLLAMA_API_KEY=                             # 可选，用于有认证要求的远程部署

# OpenAI（支持自定义 API 地址）
OPENAI_API_KEY=sk-xxx
OPENAI_BASE_URL=https://api.openai.com/v1  # 支持代理或兼容 API 服务

# 向量嵌入
EMBEDDING_PROVIDER=sentence-transformers
EMBEDDING_MODEL=all-MiniLM-L6-v2
MILVUS_HOST=localhost    MILVUS_PORT=19530
```

### 爬虫配置

```bash
CRAWL_INTERVAL_HOURS=6                      # 爬取间隔
ARXIV_CATEGORIES=cs.LG,cs.CV,cs.CL         # arXiv 分类
TWITTERAPI_IO_KEY=your-api-key              # Twitter API 密钥
WEIBO_COOKIE=your-cookie-string             # 微博 Cookie（可选）
```

详细配置请参考 [docs/CONFIGURATION.md](docs/CONFIGURATION.md)。

## 防爬策略

系统内置多种防反爬策略，确保稳定持续采集：

- **UA 轮换** - 10 种 User-Agent 随机切换（Chrome/Firefox/Safari/Edge，覆盖 Windows/macOS/Linux/Mobile）
- **连接池轮换** - 每 25 次请求重建连接，连续 2 次错误立即轮换
- **自动重试** - 支持 429/503 自动重试，遵守 Retry-After 头
- **请求延迟** - 基础延迟 + 随机抖动 + 指数退避
- **缓存机制** - 避免重复请求相同资源

## 测试

```bash
# 安装测试依赖
pip install -e ".[dev]"

# 运行全部测试
pytest

# 运行特定模块测试
pytest tests/apps/auth/
pytest tests/apps/crawler/

# 带覆盖率报告
pytest --cov=apps --cov=core --cov=common --cov-report=html

# 类型检查
mypy apps/ core/ common/

# 代码风格检查
ruff check .
```

## 文档生成（Sphinx）

本项目使用 **Google 风格 docstring + Sphinx（Napoleon/Myst）** 自动生成 Python 文档：

- 英文一行摘要 + 中文补充说明
- `Args` / `Returns` / `Raises` 结构化字段
- 类型提示与返回类型保持一致

```bash
# 安装文档依赖
pip install -e ".[docs]"

# 构建 HTML 文档
sphinx-build -b html docs docs/_build/html

# 打开文档
open docs/_build/html/index.html
```

## Docker 部署

```bash
# 构建镜像
docker build -t researchpulse:latest .

# 运行容器
docker run -d \
  --name researchpulse \
  -p 8000:8000 \
  -e DB_HOST=host.docker.internal \
  -e DB_PASSWORD=your_password \
  -e JWT_SECRET_KEY=your-secret-key \
  researchpulse:latest

# 使用 docker-compose 启动完整环境
docker compose up -d
```

详细部署指南请参考 [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)。

## 管理后台功能增强

面向运营与运维的管理后台增强方向主要包括：

- **邮件推送配置** - SMTP 与推送策略配置、测试邮件能力
- **系统配置管理** - 抓取间隔、并发数、超时等运行参数可视化配置
- **爬取任务管理** - 手动触发、队列状态与任务历史查看
- **备份管理** - 备份创建、列表、下载与恢复流程
- **审计日志** - 操作记录查询与导出
- **事件 / 话题管理** - 事件聚类管理、话题创建与趋势维护
- **仪表盘增强** - 订阅统计与功能开关概览

详细规划与实施方案请参考：
- `docs/admin_features_plan.md`
- `docs/admin_implementation_plan.md`

## 贡献指南

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 编写代码并补充测试
4. 确保测试通过 (`pytest`) 和代码规范 (`ruff check .`)
5. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
6. 推送到分支 (`git push origin feature/AmazingFeature`)
7. 提交 Pull Request

**代码规范：**
- Docstring 遵循 Google 风格（英文摘要 + 中文说明 + Args/Returns/Raises）
- 所有函数和方法需要类型提示
- 使用 ruff 进行代码风格检查，mypy 进行类型检查

## 许可证

MIT License

## 联系方式

- 项目地址: https://github.com/web_services/ResearchPulse
- 问题反馈: https://github.com/web_services/ResearchPulse/issues
