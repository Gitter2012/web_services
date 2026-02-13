# ResearchPulse

> 学术资讯聚合平台 - 订阅、跟踪、推送最新研究动态

## 项目简介

ResearchPulse 是一个学术资讯聚合平台，支持从多个来源（arXiv、RSS、微信公众号）抓取最新研究文章，提供用户订阅管理、邮件推送、Markdown 导出等功能。

### 主要特性

- 🔍 **多源聚合** - 支持 arXiv、RSS、微信公众号等多种来源
- 📬 **邮件推送** - 自动推送用户订阅的最新文章
- 📥 **Markdown 导出** - 一键导出订阅文章为 Markdown 格式
- 👤 **用户系统** - 完整的用户注册、登录、权限管理
- ⭐ **收藏管理** - 收藏喜欢的文章，随时查看
- 🎯 **智能分类** - 按来源、分类、时间等多维度筛选
- 🌐 **中英对照** - arXiv 论文支持一键翻译

## 技术栈

| 类别 | 技术 |
|------|------|
| 后端框架 | FastAPI |
| 数据库 | MySQL 8.0+ |
| ORM | SQLAlchemy 2.0 |
| 异步任务 | APScheduler |
| 模板引擎 | Jinja2 |
| HTTP 客户端 | httpx |
| 邮件服务 | SMTP / SendGrid / Mailgun / Brevo |

## 目录结构

```
ResearchPulse/
├── apps/                    # 应用模块
│   ├── auth/               # 用户认证
│   ├── admin/              # 管理后台
│   ├── crawler/            # 爬虫模块
│   │   ├── arxiv/          # arXiv 爬虫
│   │   ├── rss/            # RSS 爬虫
│   │   ├── wechat/         # 微信爬虫
│   │   └── models/         # 数据模型
│   ├── scheduler/          # 定时任务
│   └── ui/                 # 前端界面
├── common/                  # 公共模块
│   ├── email.py            # 邮件发送
│   ├── http.py             # HTTP 请求
│   ├── cache.py            # 内存缓存
│   ├── markdown.py         # Markdown 导出
│   └── logger.py           # 日志工具
├── config/                  # 配置文件
│   └── defaults.yaml       # 默认配置
├── core/                    # 核心模块
│   ├── database.py         # 数据库连接
│   ├── models/             # 基础模型
│   ├── security.py         # 安全工具
│   └── dependencies.py     # 依赖注入
├── docs/                    # 项目文档
├── logs/                    # 日志目录
├── run/                     # 运行时文件
├── sql/                     # SQL 脚本
│   └── init.sql            # 数据库初始化
├── .env                     # 环境配置
├── .env.example            # 环境配置示例
├── main.py                 # 应用入口
├── settings.py             # 配置管理
└── README.md               # 项目说明
```

## 快速开始

### 1. 环境要求

- Python 3.10+
- MySQL 8.0+
- Redis (可选，用于缓存)

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

### 6. 访问页面

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

## API 文档

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
GET  /api/v1/auth/me
```

### 订阅 API

```
GET    /researchpulse/api/subscriptions
POST   /researchpulse/api/subscriptions
DELETE /researchpulse/api/subscriptions/{type}/{id}
```

## 防爬策略

系统内置多种防反爬策略：

- **UA 轮换** - 10 种 User-Agent 随机切换
- **连接池轮换** - 每 25 次请求重建连接
- **自动重试** - 支持 429/503 自动重试
- **请求延迟** - 支持随机延迟和抖动
- **缓存机制** - 避免重复请求

## 定时任务

| 任务 | 默认时间 | 说明 |
|------|---------|------|
| 文章抓取 | 每 6 小时 | 抓取所有活跃源 |
| 数据清理 | 每天凌晨 3 点 | 清理过期文章 |
| 数据备份 | 每天凌晨 4 点 | 备份文章数据 |
| 邮件推送 | 抓取完成后 | 推送用户订阅 |

## 贡献指南

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 提交 Pull Request

## 许可证

MIT License

## 联系方式

- 项目地址: https://github.com/web_services/ResearchPulse
- 问题反馈: https://github.com/web_services/ResearchPulse/issues
