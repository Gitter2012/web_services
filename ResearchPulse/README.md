# ResearchPulse

## 项目概述
模块化学术资源自动化平台，支持多数据源抓取与可视化推送。

## 系统架构
- **标准化路由**：所有子项目采用 `/领域/功能` 两端式挂载
  - arXiv 抓取：`/arxiv/crawler/*`
  - arXiv 可视化：`/arxiv/ui/*`
- **动态启用**：通过 `ENABLED_APPS` 环境变量控制子模块
- **数据流**：`arxiv_crawler` 生成数据 → `arxiv_ui` 可视化展示

## 启动方式
```bash
# 启用抓取 + 可视化
ENABLED_APPS=arxiv_crawler,arxiv_ui uvicorn main:app --host 0.0.0.0 --port 8000

# 仅启用可视化（需已有 data/arxiv/ 数据）
ENABLED_APPS=arxiv_ui uvicorn main:app --reload
```

## 配置系统

ResearchPulse 采用分层配置系统，支持灵活的配置覆盖和应用级默认值。

### 配置文件
| 文件 | 用途 |
|------|------|
| `/config/defaults.yaml` | 项目级非敏感默认值（覆盖应用默认值） |
| `/apps/<app>/config/defaults.yaml` | 应用级默认值（各应用独立维护） |
| `/config/logging.yaml` | 日志配置，支持按应用自定义级别 |
| `.env` | 仅存放敏感信息（API密钥、密码、凭证） |

### 配置优先级（由高到低）
1. **环境变量**：运行时覆盖
2. **`.env` 文件**：敏感信息（密码、API密钥）
3. **`/config/defaults.yaml` apps.\<app\>**：项目级覆盖
4. **`/apps/<app>/config/defaults.yaml`**：应用级默认值
5. **Python 代码默认值**：兜底

### 深度合并机制
项目级配置与应用级配置采用**深度合并（deep merge）**：
- 项目级配置覆盖应用级同名键
- 应用级独有键被保留
- 嵌套字典递归合并

示例：
```yaml
# /apps/arxiv_crawler/config/defaults.yaml（应用默认）
arxiv:
  max_results: 50
  urls:
    base: "https://export.arxiv.org/api/query"
    rss: "https://export.arxiv.org/rss/{category}"

# /config/defaults.yaml apps.arxiv_crawler（项目覆盖）
arxiv:
  max_results: 100  # 覆盖
  urls:
    rss: "https://custom.arxiv.org/rss/{category}"  # 覆盖

# 最终合并结果
arxiv:
  max_results: 100       # 来自项目
  urls:
    base: "..."          # 来自应用（保留）
    rss: "https://custom..."  # 来自项目（覆盖）
```

### 应用级默认值
各应用在 `apps/<app>/config/defaults.yaml` 维护独立默认值：
- `apps/arxiv_crawler/config/defaults.yaml`：抓取器设置
- `apps/arxiv_ui/config/defaults.yaml`：UI 设置

### 当日窗口（统计/回溯标识）
默认将“当日”定义为**抓取当天 + 前一天**（可配置为最近 N 天）：
- `apps.arxiv_crawler.date_window.days` / `apps.arxiv_crawler.date_window.timezone`
- `apps.arxiv_ui.date_window.days` / `apps.arxiv_ui.date_window.timezone`

环境变量覆盖：
- `ARXIV_DATE_WINDOW_DAYS` / `ARXIV_DATE_WINDOW_TIMEZONE`
- `ARXIV_UI_DATE_WINDOW_DAYS` / `ARXIV_UI_DATE_WINDOW_TIMEZONE`

项目级覆盖位于 `/config/defaults.yaml` 的 `apps.<app_name>` 下。

### 日志配置
`/config/logging.yaml` 支持按应用自定义日志级别：
```yaml
loggers:
  apps.arxiv_crawler:
    level: INFO
    handlers: [console, file]
  apps.arxiv_ui:
    level: INFO
    handlers: [console]
```

### 自定义配置
- **修改敏感信息**：编辑 `.env`
- **修改项目级默认值**：编辑 `/config/defaults.yaml`
- **修改应用级默认值**：编辑 `/apps/<app>/config/defaults.yaml`
- **运行时覆盖**：设置环境变量

### 示例：覆盖配置
```bash
# 通过环境变量覆盖日志级别
LOG_LEVEL=DEBUG uvicorn main:app

# 通过环境变量覆盖 arXiv 分类
ARXIV_CATEGORIES=cs.AI,cs.NE uvicorn main:app
```

## 子项目专属配置
- `arxiv_crawler`：`ARXIV_*` 前缀（详见 `apps/arxiv_crawler/README.md`）
- `arxiv_ui`：`ARXIV_UI_*` 前缀（详见 `apps/arxiv_ui/README.md`）

## 依赖
确保安装 PyYAML：
```bash
pip install PyYAML>=6.0
```
