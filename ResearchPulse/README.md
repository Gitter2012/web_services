# ResearchPulse

> 学术资讯聚合与智能分析平台 - 订阅、跟踪、分析、推送最新研究动态

## 项目简介

ResearchPulse 是一个学术资讯聚合与智能分析平台，支持从多个来源（arXiv、RSS、微信公众号）抓取最新研究文章，并通过 AI 分析、向量嵌入、事件聚类、话题追踪等能力，提供深度内容洞察。同时具备用户订阅管理、邮件推送、Markdown 导出、行动项提取、定期报告生成等功能。

### 主要特性

- 🔍 **多源聚合** - 支持 arXiv、RSS、微信公众号等多种来源
- 🤖 **AI 内容分析** - 基于 Ollama/OpenAI 的文章摘要、分类、重要性评分
- 🧬 **向量嵌入** - 基于 sentence-transformers + Milvus 的语义相似文章检索
- 📊 **事件聚类** - 将相关文章自动聚合为事件，追踪事件时间线
- 🎯 **话题雷达** - 自动发现新兴话题，追踪话题趋势变化
- ✅ **行动项提取** - 从文章中提取可执行的行动项，支持完成/忽略管理
- 📝 **报告生成** - 自动生成周报/月报，汇总分析期间的研究动态
- 📬 **邮件推送** - 自动推送用户订阅的最新文章
- 📥 **Markdown 导出** - 一键导出订阅文章为 Markdown 格式
- 👤 **用户系统** - 完整的用户注册、登录、权限管理
- ⭐ **收藏管理** - 收藏喜欢的文章，随时查看
- 🌐 **中英对照** - arXiv 论文支持一键翻译
- 🔧 **功能开关** - 所有高级功能均可通过 Feature Toggle 独立启停

## 管理后台功能增强

面向运营与运维的管理后台增强方向主要包括：

- **邮件推送配置**：SMTP 与推送策略配置、测试邮件能力
- **系统配置管理**：抓取间隔、并发数、超时等运行参数可视化配置
- **爬取任务管理**：手动触发、队列状态与任务历史查看
- **备份管理**：备份创建、列表、下载与恢复流程
- **审计日志**：操作记录查询与导出
- **事件 / 话题管理**：事件聚类管理、话题创建与趋势维护
- **仪表盘增强**：订阅统计与功能开关概览

详细规划与实施方案请参考：
- `docs/admin_features_plan.md`
- `docs/admin_implementation_plan.md`

## 技术栈

| 类别 | 技术 |
|------|------|
| 后端框架 | FastAPI |
| 数据库 | MySQL 8.0+ |
| 向量数据库 | Milvus 2.3+ |
| ORM | SQLAlchemy 2.0 |
| 异步任务 | APScheduler |
| AI 推理 | Ollama / OpenAI |
| 向量嵌入 | sentence-transformers |
| 模板引擎 | Jinja2 |
| HTTP 客户端 | httpx |
| 邮件服务 | SMTP / SendGrid / Mailgun / Brevo |

## 目录结构

```
ResearchPulse/
├── apps/                        # 应用模块
│   ├── auth/                    # 用户认证
│   ├── admin/                   # 管理后台
│   ├── crawler/                 # 爬虫模块
│   │   ├── arxiv/               # arXiv 爬虫
│   │   ├── rss/                 # RSS 爬虫
│   │   ├── wechat/              # 微信爬虫
│   │   └── models/              # 数据模型
│   ├── ai_processor/            # AI 内容分析
│   ├── embedding/               # 向量嵌入
│   ├── event/                   # 事件聚类
│   ├── topic/                   # 话题雷达
│   ├── action/                  # 行动项管理
│   ├── report/                  # 报告生成
│   ├── scheduler/               # 定时任务
│   │   └── jobs/                # 任务实现
│   └── ui/                      # 前端界面
├── common/                      # 公共模块
│   ├── email.py                 # 邮件发送
│   ├── http.py                  # HTTP 请求
│   ├── cache.py                 # 内存缓存
│   ├── markdown.py              # Markdown 导出
│   ├── feature_config.py        # 功能开关管理
│   └── logger.py                # 日志工具
├── config/                      # 配置文件
│   └── defaults.yaml            # 默认配置
├── core/                        # 核心模块
│   ├── database.py              # 数据库连接
│   ├── models/                  # 基础模型
│   ├── security.py              # 安全工具
│   └── dependencies.py          # 依赖注入
├── docs/                        # 项目文档
├── logs/                        # 日志目录
├── run/                         # 运行时文件
├── sql/                         # SQL 脚本
│   └── init.sql                 # 数据库初始化
├── docker-compose.milvus.yml    # Milvus 部署配置
├── .env                         # 环境配置
├── .env.example                 # 环境配置示例
├── main.py                      # 应用入口
├── settings.py                  # 配置管理
└── README.md                    # 项目说明
```

## 快速开始

### 1. 环境要求

- Python 3.10+
- MySQL 8.0+
- Redis (可选，用于缓存)
- Milvus 2.3+ (可选，用于向量嵌入和相似文章检索)
- Ollama (可选，用于本地 AI 推理)

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置环境

```bash
# 复制配置文件
cp .env.example .env

# 编辑配置
vim .env
```

### 4. 初始化数据库

```bash
mysql -u root -p < sql/init.sql
```

### 5. 启动服务

```bash
python main.py
```

服务将在 `http://localhost:8000` 启动。

### 6. 启动 Milvus（可选）

```bash
docker-compose -f docker-compose.milvus.yml up -d
```

### 7. 启动 Ollama（可选）

```bash
ollama serve
ollama pull qwen3:32b
```

### 8. 访问页面

| 页面 | URL |
|------|-----|
| 导航首页 | http://localhost:8000/ |
| ResearchPulse | http://localhost:8000/researchpulse/ |
| 管理后台 | http://localhost:8000/researchpulse/admin |
| API 文档 | http://localhost:8000/docs |

## 配置说明

### 数据库配置

```bash
DB_HOST=localhost
DB_PORT=3306
DB_NAME=research_pulse
DB_USER=research_user
DB_PASSWORD=your_password
```

### 邮件配置

```bash
# 启用邮件
EMAIL_ENABLED=true
EMAIL_FROM=your-email@gmail.com

# SMTP 配置
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password

# 其他可选后端
SENDGRID_API_KEY=          # SendGrid
MAILGUN_API_KEY=           # Mailgun
MAILGUN_DOMAIN=            # Mailgun 域名
BREVO_API_KEY=             # Brevo
```

### 爬虫配置

```yaml
# config/defaults.yaml
crawler:
  arxiv:
    categories: cs.LG,cs.CV,cs.IR,cs.CL,cs.DC
    max_results: 50
```

### AI / Embedding 配置

```bash
# AI 推理
AI_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen3:32b

# 向量嵌入
EMBEDDING_PROVIDER=sentence-transformers
EMBEDDING_MODEL=all-MiniLM-L6-v2
MILVUS_HOST=localhost
MILVUS_PORT=19530
```

详细配置请参考 [docs/CONFIGURATION.md](docs/CONFIGURATION.md)。

## 文档生成（Sphinx）

本项目使用 **Google 风格 docstring + Sphinx(Napoleon/Myst)** 自动生成 Python 文档，统一采用：

- 英文一行摘要 + 中文补充说明
- `Args` / `Returns` / `Raises` 结构化字段
- 类型提示与返回类型保持一致

### 安装文档依赖

```bash
pip install -e ".[docs]"
```

或手动安装：

```bash
pip install sphinx sphinx-rtd-theme myst-parser
```

### 构建 HTML 文档

```bash
sphinx-build -b html docs docs/_build/html
```

构建完成后打开：`docs/_build/html/index.html`。

## API 概览

### 文章 API

```
GET /researchpulse/api/articles
    ?source_type=arxiv      # 来源类型
    &category=cs.LG         # 分类
    &keyword=machine        # 关键词
    &page=1                 # 页码
    &page_size=20           # 每页数量

GET /researchpulse/api/categories?source_type=arxiv

GET /researchpulse/api/export/markdown
    ?source_type=arxiv
    &from_date=2026-01-01
```

### 用户 API

```
POST /api/v1/auth/register
POST /api/v1/auth/login
POST /api/v1/auth/refresh
GET  /api/v1/auth/me
POST /api/v1/auth/change-password
POST /api/v1/auth/logout
```

### 订阅 API

```
GET    /researchpulse/api/subscriptions
POST   /researchpulse/api/subscriptions
DELETE /researchpulse/api/subscriptions/{type}/{id}
```

### AI 处理 API

```
POST /researchpulse/api/ai/process
POST /researchpulse/api/ai/batch-process
GET  /researchpulse/api/ai/status/{article_id}
GET  /researchpulse/api/ai/token-stats
```

### 向量嵌入 API

```
POST /researchpulse/api/embedding/compute
POST /researchpulse/api/embedding/batch
GET  /researchpulse/api/embedding/similar/{article_id}
GET  /researchpulse/api/embedding/stats
POST /researchpulse/api/embedding/rebuild
```

### 事件聚类 API

```
GET  /researchpulse/api/events
GET  /researchpulse/api/events/{event_id}
POST /researchpulse/api/events/cluster
GET  /researchpulse/api/events/{event_id}/timeline
```

### 话题雷达 API

```
GET    /researchpulse/api/topics
POST   /researchpulse/api/topics
GET    /researchpulse/api/topics/{topic_id}
PUT    /researchpulse/api/topics/{topic_id}
DELETE /researchpulse/api/topics/{topic_id}
GET    /researchpulse/api/topics/{topic_id}/articles
POST   /researchpulse/api/topics/discover
GET    /researchpulse/api/topics/{topic_id}/trend
```

### 行动项 API

```
GET  /researchpulse/api/actions
POST /researchpulse/api/actions
GET  /researchpulse/api/actions/{action_id}
PUT  /researchpulse/api/actions/{action_id}
POST /researchpulse/api/actions/{action_id}/complete
POST /researchpulse/api/actions/{action_id}/dismiss
```

### 报告 API

```
GET    /researchpulse/api/reports
POST   /researchpulse/api/reports/weekly
POST   /researchpulse/api/reports/monthly
GET    /researchpulse/api/reports/{report_id}
DELETE /researchpulse/api/reports/{report_id}
```

完整 API 文档请参考 [docs/API.md](docs/API.md)。

## 功能开关

所有高级功能默认关闭，可通过管理后台或 API 独立启停：

| 功能开关 | 说明 | 默认值 |
|---------|------|--------|
| `feature.ai_processor` | AI 内容分析 | false |
| `feature.embedding` | 向量嵌入 | false |
| `feature.event_clustering` | 事件聚类 | false |
| `feature.topic_radar` | 话题雷达 | false |
| `feature.action_items` | 行动项提取 | false |
| `feature.report_generation` | 报告生成 | false |
| `feature.crawler` | 爬虫 | true |
| `feature.backup` | 数据备份 | true |
| `feature.cleanup` | 数据清理 | true |
| `feature.email_notification` | 邮件推送 | false |

通过管理 API 切换：

```
PUT /api/v1/admin/features/{feature_key}
Body: {"enabled": true}
```

## 防爬策略

系统内置多种防反爬策略：

- **UA 轮换** - 10 种 User-Agent 随机切换
- **连接池轮换** - 每 25 次请求重建连接
- **自动重试** - 支持 429/503 自动重试
- **请求延迟** - 支持随机延迟和抖动
- **缓存机制** - 避免重复请求

## 定时任务

| 任务 | 默认时间 | 功能开关 | 说明 |
|------|---------|---------|------|
| 文章抓取 | 每 6 小时 | `feature.crawler` | 抓取所有活跃源 |
| 数据清理 | 每天凌晨 3 点 | `feature.cleanup` | 清理过期文章 |
| 数据备份 | 每天凌晨 4 点 | `feature.backup` | 备份文章数据 |
| 邮件推送 | 抓取完成后 | `feature.email_notification` | 推送用户订阅 |
| AI 分析 | 每 1 小时 | `feature.ai_processor` | AI 处理新文章 |
| 向量嵌入 | 每 2 小时 | `feature.embedding` | 计算文章嵌入向量 |
| 事件聚类 | 每天凌晨 2 点 | `feature.event_clustering` | 聚类文章为事件 |
| 话题发现 | 每周一凌晨 1 点 | `feature.topic_radar` | 发现新兴话题 |

## 贡献指南

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 提交 Pull Request
6. 补充或更新 docstring 时遵循 Sphinx 兼容格式（英文摘要 + 中文说明 + Args/Returns/Raises）

## 许可证

MIT License

## 联系方式

- 项目地址: https://github.com/web_services/ResearchPulse
- 问题反馈: https://github.com/web_services/ResearchPulse/issues
