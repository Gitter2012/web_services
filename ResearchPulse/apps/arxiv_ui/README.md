# Arxiv UI 子项目

## 功能
将 arxiv_crawler 生成的 Markdown 转为美观网页，支持：
- 每小时自动检测新内容
- 按分类筛选（cs.LG, astro-ph.HE...）
- "仅最新" / "显示全部" 切换（默认仅最新）
- 响应式设计（桌面/手机适配）
- **翻译链接自动显示**（`https://hjfy.top/arxiv/{id}`）

## 配置说明

### 配置来源（优先级由高到低）
1. **环境变量**：运行时覆盖
2. **`/config/defaults.yaml` apps.arxiv_ui**：项目级覆盖
3. **`/apps/arxiv_ui/config/defaults.yaml`**：应用默认值
4. **Python 代码默认值**：兜底

### 应用默认值文件
应用默认值位于 `apps/arxiv_ui/config/defaults.yaml`，可按需调整扫描间隔、分页等参数。

### 配置项
| 配置 | 默认值 | 说明 |
|------|--------|------|
| `ARXIV_UI_ENABLED` | true | 是否启用 UI |
| `ARXIV_UI_SCAN_INTERVAL` | 3600 | 扫描间隔（秒） |
| `ARXIV_UI_SHOW_ALL_CONTENT` | false | 是否默认展示所有历史内容 |
| `ARXIV_UI_DEFAULT_PAGE_SIZE` | 20 | 每页论文数（仅 SHOW_ALL=true 时生效） |
| `ARXIV_UI_MAX_CONTENT_AGE_DAYS` | 30 | 内容保留上限（天） |
| `ARXIV_UI_DATE_WINDOW_DAYS` | 2 | 当日窗口天数（含当天与前 N-1 天） |
| `ARXIV_UI_DATE_WINDOW_TIMEZONE` | Asia/Shanghai | 当日窗口时区基准 |

> “仅最新”模式会展示当日窗口内条目，超出窗口视为历史。

### 修改配置
```bash
# 通过环境变量覆盖
ARXIV_UI_SCAN_INTERVAL=1800 uvicorn main:app

# 或编辑应用默认值
vi apps/arxiv_ui/config/defaults.yaml

# 或编辑项目级覆盖
vi /config/defaults.yaml
```

### 默认值文件
应用默认值位于 `apps/arxiv_ui/config/defaults.yaml`，包含：
- `enabled`：UI 启用开关
- `scan_interval`：内容扫描间隔
- `show_all_content`：默认显示模式
- `default_page_size`：分页大小
- `max_content_age_days`：内容保留天数

## 访问路径
- **主界面**：`/arxiv/ui/`
- **API**：
  - `GET /arxiv/ui/api/entries?category=cs.LG&show_all=true&page=2`
  - `GET /arxiv/ui/api/categories`
  - `GET /arxiv/ui/api/latest-date`
