

# ResearchPulse 项目完整代码生成规范（含最新需求）

## 📌 核心指令
**所有子项目必须采用标准化两端式挂载路径**：  
`/arxiv/crawler/...`（arxiv_crawler）  
`/arxiv/ui/...`（arxiv_ui）  
**严禁**使用单段路径或非标准前缀（如 `/api/v1/arxiv` 或 `/web_ui`）。

---

## 一、项目概述

ResearchPulse 是一个基于 FastAPI 构建的模块化、可扩展的自动化任务平台，旨在定期抓取学术资源（如 arXiv 论文），结构化处理数据，并通过多种渠道（如邮件）主动推送更新。系统设计支持未来灵活接入更多数据源、检测任务或通知方式，所有子功能以独立子项目形式组织，便于维护与扩展。

---

## 二、核心目标（当前阶段）

实现 **每日自动抓取 arXiv 新发布论文** 的完整闭环流程，包括：
- 按指定学科分类（如 `cs.LG`、`astro-ph.HE`）筛选内容；
- **智能回溯抓取**：确保每分类 ≥10 篇（当日不足则向前回溯 ≤7 天）；
- 提取标题、作者、分类、摘要等关键信息；
- 将结果保存为本地 Markdown 文件；
- **生成聚合邮件**：包含全局统计、分类明细（当日/历史篇数）、每篇论文来源日期；
- 抓取完成后自动将内容推送至预设邮箱列表；
- **新增**：生成美化 UI 网页，支持分类筛选、"仅最新"/"显示全部"切换、翻页功能。

---

## 三、系统架构要求

### 1. 模块化设计
- 每个功能单元作为**独立子项目**，存放在 `apps/` 目录下：
  - `arxiv_crawler`：数据抓取、存储、邮件通知
  - `arxiv_ui`：内容可视化、交互界面
- 子项目包含自身所需的 API 路由、任务逻辑、配置和依赖，彼此解耦。

### 2. 统一挂载机制（强制执行）
| 子项目 | 挂载基础路径 | 完整路径示例 |
|--------|--------------|--------------|
| `arxiv_crawler` | `/arxiv/crawler` | `GET /arxiv/crawler/status` |
| `arxiv_ui` | `/arxiv/ui` | `GET /arxiv/ui/`（主页面）`GET /arxiv/ui/api/entries`（API） |

> ✅ **实现要求**：`main.py` 中通过 `APP_MOUNT_PATHS` 映射字典动态挂载，子项目内部路由**不包含** `/arxiv/xxx` 前缀。

### 3. 公共组件抽象
- 可复用功能（邮件发送、日志记录、HTTP 请求封装、文件写入工具等）提取至 `common/` 目录。

### 4. 启动控制灵活性
- 通过 `ENABLED_APPS` 环境变量控制子模块：
  ```bash
  # 启用抓取 + 可视化
  ENABLED_APPS=arxiv_crawler,arxiv_ui uvicorn main:app --host 0.0.0.0 --port 8000
  ```
- 被禁用的子项目**不注册路由、不启动任务**。

---

## 四、arxiv_crawler 子项目详细需求（全量更新）

### 🔄 智能抓取逻辑（关键更新）
| 场景 | 行为 | 说明 |
|------|------|------|
| **当日 ≥10篇** | 全量抓取当日数据 | 保留所有结果，不回溯 |
| **当日 <10篇** | 向前逐日回溯（最多7天） | 按日期倒序抓取，累计至≥10篇即停 |
| **回溯上限** | 最多回溯7天 | 即使不足10篇也停止 |
| **去重机制** | 全局论文ID集合 | 同一论文仅保留首次出现（按日期优先级） |
| **存储粒度** | 按**实际抓取日期**生成文件 | 回溯数据存入对应历史日期目录 |

### 📧 聚合邮件内容规范（重大变更）
#### 邮件主题
`[ResearchPulse] {最新日期} 多分类论文汇总（共{总篇数}篇 | {分类数}类）`

#### 邮件正文结构
```markdown
# 📬 ResearchPulse 每日学术简报 | {最新日期}

## 📊 全局统计
- **覆盖分类**: {分类列表}（共{分类数}类）
- **当日新增**: {当日总篇数}篇（{最新日期}）
- **历史回溯**: {历史总篇数}篇（{最早回溯日期} ~ {昨日日期}）
- **总计**: {总篇数}篇

---

## 📚 分类明细

### 🔹 {分类名称}
- **当日篇数**: {当日篇数}篇（{最新日期}）
- **历史篇数**: {历史篇数}篇（{最早回溯日期} ~ {最近回溯日期}）
- **累计**: {累计篇数}篇

#### 论文列表
1. **[{id}] {标题}**  
   *Authors*: {作者}  
   *Date*: {来源日期}{回溯标记}  
   [PDF](https://arxiv.org/pdf/{id}.pdf) | [翻译](https://hjfy.top/arxiv/{id})  
   *Abstract*: {摘要}...

2. **[{id}] {标题}**  
   *Authors*: ...  
   *Date*: {回溯日期} ← 标注回溯日期  
   [PDF]... | [翻译]...  
   ...
```

#### 关键要求
- ✅ **每篇包含翻译链接**：`[翻译](https://hjfy.top/arxiv/{id})`
- ✅ **标注来源日期**：当日数据不标注，回溯数据标注"← 回溯"
- ✅ **分类分组**：清晰区分不同分类，用分隔线分隔
- ✅ **统计前置**：每个分类开头显示当日/历史/累计篇数
- ✅ **排序规则**：分类内按日期倒序 → 同日期内按arXiv ID倒序

### 💾 数据存储
- **路径**：`{DATA_DIR}/arxiv/{year}/{month}/{day}/{date}_{category}.md`
- **Markdown 格式**：
  ```markdown
  ### [{id}] {标题}
  
  **Authors**: {作者}  
  **Categories**: {分类}  
  **Date**: {来源日期}  ← 新增日期字段
  **Abstract**: {摘要}
  
  [PDF](https://arxiv.org/pdf/{id}.pdf) | [翻译](https://hjfy.top/arxiv/{id})
  ```

### ⚙️ 配置项（新增/更新）
| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `ARXIV_MIN_RESULTS` | `10` | **每分类最小抓取量**（当日不足则触发回溯） |
| `ARXIV_FALLBACK_DAYS` | `7` | **最大回溯天数**（含当日共8天窗口） |
| `ARXIV_TRANSLATION_BASE_URL` | `https://hjfy.top/arxiv/` | **固定值，不可修改** |
| `ARXIV_TRANSLATION_ENABLED` | `True` | **固定为True，始终启用** |

---

## 五、arxiv_ui 子项目详细需求（新增）

### 🌐 功能定位
> 基于 `arxiv_crawler` 生成的 Markdown 数据，提供**学术论文可视化浏览平台**。每小时自动检测新内容，生成响应式网页界面。

### 🔑 核心能力
| 功能 | 要求 |
|------|------|
| **内容生成** | 每小时扫描 `DATA_DIR/arxiv/` 目录，将新 Markdown 转为美化 HTML |
| **默认视图** | 仅展示**最新日期**内容（所有分类混合，按论文提交时间倒序） |
| **分类筛选** | 顶部筛选器：下拉选择分类（`cs.LG`, `astro-ph.HE` 等），实时刷新 |
| **内容范围** | 开关控制：- `关闭`（默认）：仅最新日期内容- `开启`：展示所有历史内容（按论文发布时间倒序） |
| **分页** | 仅当 `SHOW_ALL_CONTENT=True` 时生效，每页 20 篇 |
| **UI 优化** | - 翻译链接显示为蓝色下划线- 每篇标注来源日期（当日/回溯） |

### 📡 API 接口（挂载至 `/arxiv/ui`）
| 端点 | 方法 | 说明 |
|------|------|------|
| `/` | GET | **主页面**（渲染 HTML，含筛选控件、开关） |
| `/api/entries` | GET | 获取论文列表（JSON，支持分页/分类） |
| `/api/categories` | GET | 返回所有可用分类列表 |
| `/api/latest-date` | GET | 返回最新有数据的日期（YYYY-MM-DD） |

### ⚙️ 配置项（`apps/arxiv_ui/config.py`）
```python
class ArxivUIConfig(BaseSettings):
    ENABLED: bool = Field(default=True, env="ARXIV_UI_ENABLED")
    SCAN_INTERVAL: int = Field(3600, env="ARXIV_UI_SCAN_INTERVAL")  # 扫描间隔(秒)
    SHOW_ALL_CONTENT: bool = Field(False, env="ARXIV_UI_SHOW_ALL_CONTENT")  # 默认仅最新
    DEFAULT_PAGE_SIZE: int = Field(20, env="ARXIV_UI_DEFAULT_PAGE_SIZE")
    MAX_CONTENT_AGE_DAYS: int = Field(30, env="ARXIV_UI_MAX_CONTENT_AGE_DAYS")
```

---

## 六、配置项说明（全量）

### 全局配置（`.env`）
| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `ENABLED_APPS` | `arxiv_crawler` | 启用的子项目列表（逗号分隔） |
| `DATA_DIR` | `./data` | 数据输出根目录 |
| `LOG_LEVEL` | `INFO` | 日志等级 |
| `LOG_FILE` | 空 | 日志文件路径 |

### arxiv_crawler 配置（`ARXIV_*` 前缀）
| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `ARXIV_CATEGORIES` | `cs.LG,cs.CV` | 抓取的子分类列表 |
| `ARXIV_MIN_RESULTS` | `10` | **每分类最小抓取量**（触发回溯阈值） |
| `ARXIV_FALLBACK_DAYS` | `7` | **最大回溯天数**（含当日共8天窗口） |
| `ARXIV_TRANSLATION_BASE_URL` | `https://hjfy.top/arxiv/` | **固定值，不可修改** |
| `ARXIV_TRANSLATION_ENABLED` | `True` | **固定为True，始终启用** |
| `ARXIV_EMAIL_ENABLED` | `True` | 是否发送邮件 |
| `ARXIV_EMAIL_HTML_ENABLED` | `True` | 是否发送 HTML 邮件 |

### arxiv_ui 配置（`ARXIV_UI_*` 前缀）
| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `ARXIV_UI_SCAN_INTERVAL` | `3600` | 扫描间隔（秒） |
| `ARXIV_UI_SHOW_ALL_CONTENT` | `False` | 是否默认展示所有历史内容 |
| `ARXIV_UI_DEFAULT_PAGE_SIZE` | `20` | 每页论文数（仅 SHOW_ALL=true 时生效） |
| `ARXIV_UI_MAX_CONTENT_AGE_DAYS` | `30` | 保留内容的最长期限（天） |

---

## 七、目录结构（最终版）

```
research-pulse/
├── main.py                  # 应用入口（含 APP_MOUNT_PATHS 映射）
├── settings.py              # 全局配置（Pydantic Settings）
├── common/
│   ├── email.py             # 多后端邮件封装（SendGrid优先）
│   ├── logger.py            # 统一日志初始化
│   └── utils.py             # 通用工具（文件扫描、Markdown解析等）
├── apps/
│   ├── arxiv_crawler/
│   │   ├── README.md        # 包含抓取逻辑/邮件格式/翻译链接说明
│   │   ├── __init__.py
│   │   ├── api.py           # 路由：/status, /trigger（挂载至 /arxiv/crawler）
│   │   ├── tasks.py         # 智能抓取与邮件任务
│   │   ├── parser.py        # 抓取逻辑（含智能回溯）
│   │   └── config.py        # ARXIV_* 配置
│   └── arxiv_ui/            # ← 新增！名称必须为 arxiv_ui
│       ├── README.md        # 包含UI功能/配置/翻译链接说明
│       ├── __init__.py
│       ├── api.py           # 路由：/（主页面）, /api/entries（挂载至 /arxiv/ui）
│       ├── tasks.py         # 每小时扫描任务
│       ├── config.py        # ARXIV_UI_* 配置
│       ├── templates/
│       │   └── index.html.j2
│       └── static/
│           ├── css/style.css
│           └── js/app.js
├── data/                    # .gitignore（arxiv_crawler 生成数据目录）
├── .env.example             # 包含所有配置项示例
├── .env                     # 实际环境变量（不提交）
└── pyproject.toml           # 依赖：fastapi, jinja2, markdown, apscheduler
```

---

## 八、项目级 README 要求（必须遵守）

### ✅ 保留内容
```markdown
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

## 配置说明
- **全局配置**：`.env` 中 `DATA_DIR`, `LOG_LEVEL` 等
- **子项目专属配置**：
  - `arxiv_crawler`：`ARXIV_*` 前缀（详见 `apps/arxiv_crawler/README.md`）
  - `arxiv_ui`：`ARXIV_UI_*` 前缀（详见 `apps/arxiv_ui/README.md`）
```

### ❌ 禁止包含
- 子项目实现细节
- 具体 API 参数说明
- 前端代码示例

---

## 九、子项目专属文档要求

### 📁 `apps/arxiv_crawler/README.md`（必须包含）
```markdown
# Arxiv Crawler 子项目

## 智能抓取逻辑
- **每分类最小10篇**：当日不足则向前回溯（最多7天）
- **去重机制**：全局论文ID集合，避免重复
- **存储策略**：回溯数据存入对应历史日期目录（不影响"最新日期"判定）

## 聚合邮件格式
邮件包含：
1. 全局统计（总篇数、分类数、当日/历史篇数）
2. 按分类分组明细：
   - 每个分类显示：当日篇数 + 历史篇数 + 累计
   - 每篇论文标注来源日期（当日/回溯）
   - 每篇包含PDF链接 + **翻译链接**
3. 分类间用分隔线清晰区分

## 配置说明
| 配置 | 默认 | 说明 |
|------|------|------|
| `ARXIV_MIN_RESULTS` | 10 | 每分类最小抓取量（触发回溯阈值） |
| `ARXIV_FALLBACK_DAYS` | 7 | 最大回溯天数（含当日共8天窗口） |
| `ARXIV_TRANSLATION_BASE_URL` | https://hjfy.top/arxiv/ | **固定值，不可修改** |
```

### 📁 `apps/arxiv_ui/README.md`（必须包含）
```markdown
# Arxiv UI 子项目

## 功能
将 arxiv_crawler 生成的 Markdown 转为美观网页，支持：
- ✅ 每小时自动检测新内容
- ✅ 按分类筛选（cs.LG, astro-ph.HE...）
- ✅ "仅最新" / "显示全部" 切换（默认仅最新）
- ✅ 响应式设计（桌面/手机适配）
- ✅ **翻译链接自动显示**（`https://hjfy.top/arxiv/{id}`）

## 配置项（.env）
| 配置 | 默认值 | 说明 |
|------|--------|------|
| `ARXIV_UI_SCAN_INTERVAL` | 3600 | 扫描间隔（秒） |
| `ARXIV_UI_SHOW_ALL_CONTENT` | false | 是否默认展示所有历史内容 |
| `ARXIV_UI_DEFAULT_PAGE_SIZE` | 20 | 每页论文数（仅 SHOW_ALL=true 时生效） |

## 访问路径
- **主界面**：`/arxiv/ui/`
- **API**：
  - `GET /arxiv/ui/api/entries?category=cs.LG&show_all=true&page=2`
  - `GET /arxiv/ui/api/categories`
  - `GET /arxiv/ui/api/latest-date`
```

---

## 十、代码生成器强制检查清单

- [ ] **路由路径**：子项目内部路由无 `/arxiv/xxx` 前缀（仅定义 `/status`、`/` 等）
- [ ] **挂载逻辑**：`main.py` 使用 `APP_MOUNT_PATHS` 映射字典（含两个子项目）
- [ ] **配置前缀**：arxiv_crawler 用 `ARXIV_`，arxiv_ui 用 `ARXIV_UI_`（无 WEB_UI_）
- [ ] **目录命名**：`apps/arxiv_ui/`（非 web_ui）
- [ ] **翻译链接**：所有 Markdown/邮件/UI 必须包含 `[翻译](https://hjfy.top/arxiv/{id})`
- [ ] **邮件聚合**：包含全局统计+分类明细+每篇来源日期
- [ ] **智能回溯**：当日<10篇则回溯（≤7天），确保每分类≥10篇
- [ ] **文档分工**：
  - 项目级 README 无子项目实现细节
  - 两个子项目 README 各自包含完整功能/配置/API 说明
- [ ] **数据存储**：回溯数据存入对应历史日期目录
- [ ] **arxiv_ui 兼容**：无需修改，天然支持多日期数据

---

## 十一、禁止事项（红线）

- ❌ **不实现智能回溯**：当日<10篇必须向前追溯（≤7天）
- ❌ **邮件无分类统计**：必须包含当日篇数/历史篇数/累计
- ❌ **论文无来源日期标注**：Markdown和邮件中每篇必须标注来源日期
- ❌ **缺失翻译链接**：任何输出（Markdown/邮件/UI）中每篇论文必须含翻译链接
- ❌ **回溯数据存入当日目录**：必须存入对应历史日期目录
- ❌ **邮件主题仅含单分类**：必须为多分类汇总格式
- ❌ **配置项可关闭翻译**：`ARXIV_TRANSLATION_ENABLED` **必须固定为True**
- ❌ **使用非标准路径**：禁止 `/api/v1/arxiv` 或 `/web_ui`

> 💡 **设计哲学**：  
> **数据完整性 > 时效性**：通过智能回溯确保每分类内容充实，提升用户价值  
> **透明化呈现**：邮件中明确区分当日/历史数据，避免信息混淆  
> **固定业务规则**：翻译链接为强制要求，不提供配置开关，确保用户体验一致性  
> **存储与展示解耦**：回溯数据存入历史目录，不影响arxiv_ui的"最新日期"判定逻辑
