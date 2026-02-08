
---

# 项目名称：ResearchPulse

## 项目概述  
ResearchPulse 是一个基于 FastAPI 构建的模块化、可扩展的自动化任务平台，旨在定期抓取学术资源（如 arXiv 论文），结构化处理数据，并通过多种渠道（如邮件）主动推送更新。系统设计支持未来灵活接入更多数据源、检测任务或通知方式，所有子功能以独立子项目形式组织，便于维护与扩展。

---

## 核心目标（当前阶段）

实现 **每日自动抓取 arXiv 新发布论文** 的完整闭环流程，包括：
- 按指定学科分类（如 `cs.LG`、`astro-ph.HE`）筛选内容；
- 提取标题、作者、分类、摘要等关键信息；
- 将结果保存为本地 Markdown 文件；
- 抓取完成后自动将内容推送至预设邮箱列表。

---

## 系统架构要求

### 1. 模块化设计
- 每个功能单元（如 arXiv 抓取器）作为一个**独立子项目**，存放在 `apps/` 目录下（例如 `apps/arxiv_crawler/`）。
- 子项目包含自身所需的 API 路由、任务逻辑、配置和依赖，彼此解耦。

### 2. 统一挂载机制
- 所有子项目的 Web 接口通过统一前缀挂载到主应用（如 `/api/v1/arxiv`）。
- 前缀命名应清晰反映子项目功能。

### 3. 公共组件抽象
- 可复用的功能（如邮件发送、日志记录、HTTP 请求封装、文件写入工具等）应提取至 `common/` 或 `utils/` 目录，避免重复代码。

### 4. 启动控制灵活性
- 主应用启动时，可通过环境变量（如 `ENABLED_APPS=arxiv_crawler`）或命令行参数**动态启用或禁用特定子项目**。
- 被禁用的子项目不应注册其 API 路由，也不应启动其后台任务。

---

## ArXiv 抓取子项目详细需求

### 数据抓取
- **频率**：每天一次（建议 UTC 00:00 执行）。
- **来源**：https://arxiv.org/
- **可配置项**：
  - 主分类（如 `cs`, `physics`）
  - 子分类列表（如 `["cs.LG", "cs.CV", "astro-ph.HE"]`）
  - 配置通过 `.env` 文件或子项目专属配置模块管理。

### 抓取字段
每篇论文需提取以下信息：
- arXiv ID
- 标题（Title）
- 作者列表（Authors）
- 首选分类（Primary Category）
- 所有分类标签（Categories）
- 摘要（Abstract）
- PDF 链接（可选，用于参考）

### 数据存储
- 每次抓取结果按日期和分类生成 **Markdown 文件**，例如：  
  `data/arxiv/2026-02-07_cs.LG.md`
- Markdown 格式应包含元信息区块（YAML front matter 或注释形式）和清晰排版的论文列表。

### 通知机制
- 抓取完成后，自动将当日抓取结果（Markdown 内容）作为**邮件正文**发送至预设收件人列表。
- 邮件服务通过 SMTP 配置（发件邮箱、密码、服务器地址等）从 `.env` 读取。
- 支持多收件人，且邮件主题应包含日期和分类信息（如 `[ResearchPulse] 2026-02-07 cs.LG 新论文`）。

### 任务调度
- 使用 `APScheduler` 或等效异步定时任务库实现每日执行。
- 定时任务应仅在该子项目被启用时注册。

---

## 非功能性要求

- **语言与版本**：Python 3.9+
- **代码风格**：遵循 PEP8，使用类型注解，模块职责单一。
- **配置管理**：采用 Pydantic 的 `BaseSettings` + `.env` 文件，支持环境覆盖。
- **日志**：统一日志格式，区分级别，输出到控制台及可选文件。
- **依赖管理**：使用 `pyproject.toml` 或 `requirements.txt` 明确声明依赖。
- **可测试性**：核心逻辑（解析、邮件、存储）应易于单元测试。
- **安全性**：敏感信息（如邮箱密码）不得硬编码，必须通过环境变量注入。

---

## 示例目录结构（供参考）

```
research-pulse/
├── main.py                  # 应用入口，动态加载启用的子项目
├── settings.py              # 全局配置（Pydantic Settings）
├── common/
│   ├── email.py             # 邮件发送封装
│   ├── logger.py            # 日志初始化
│   └── utils.py             # 通用工具函数
├── apps/
│   └── arxiv_crawler/
│       ├── __init__.py
│       ├── api.py           # 提供 /status, /trigger 等接口
│       ├── tasks.py         # 定时抓取与通知任务
│       ├── parser.py        # arXiv 页面/Feed 解析逻辑
│       └── config.py        # 子项目专属配置（分类列表等）
├── data/                    # 本地存储目录（.gitignore）
├── .env.example             # 环境变量模板
├── .env                     # 实际环境变量（不提交）
└── pyproject.toml           # 项目元数据与依赖
```

---

## 启动方式示例

```bash
# 仅启用 arXiv 抓取器
ENABLED_APPS=arxiv_crawler uvicorn main:app --host 0.0.0.0 --port 8000

# 启用多个子项目（预留扩展）
ENABLED_APPS=arxiv_crawler,github_tracker python main.py
```

---

