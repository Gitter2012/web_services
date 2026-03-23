# ResearchPulse v2 运维脚本

> 脚本说明与主文档保持一致，若脚本行为调整请同步更新 README 与 docs。

## 脚本列表

| 脚本 | 描述 |
|------|------|
| `control.sh` | 统一入口（推荐） |
| `service.sh` | 服务管理 |
| `deploy.sh` | 部署 |
| `init.sh` | 初始化 |
| `crawl.sh` | 手动爬取触发 |
| `email.sh` | 手动邮件发送 |
| `ai-pipeline.sh` | AI 流水线手动运行 |
| `repair-arxiv.sh` | arXiv 数据修复 |
| `test.sh` | 测试 |
| `sync-categories.sh` | arXiv 分类同步 |

## 快速使用

```bash
# 部署
./scripts/control.sh deploy

# 启动（后台）
./scripts/control.sh start -d

# 状态
./scripts/control.sh status -v

# 停止
./scripts/control.sh stop

# 重启
./scripts/control.sh restart

# 日志
./scripts/control.sh logs -f
```

## 服务管理

```bash
./scripts/service.sh start --port 8080 -d
./scripts/service.sh stop --force
./scripts/service.sh restart
./scripts/service.sh status -v
```

## 环境变量

项目根目录创建 `.env`：

```env
DB_HOST=localhost
DB_PORT=3306
DB_NAME=research_pulse
DB_USER=research_user
DB_PASSWORD=your_password
JWT_SECRET_KEY=your_secret
```

## 手动爬取

使用 `crawl.sh` 脚本可手动触发爬取任务：

```bash
# 爬取所有已激活的数据源
./scripts/crawl.sh all

# 仅爬取 arXiv
./scripts/crawl.sh arxiv

# 爬取指定的 arXiv 分类
./scripts/crawl.sh arxiv cs.AI cs.CL cs.LG

# 仅爬取 RSS
./scripts/crawl.sh rss

# 爬取微博热搜
./scripts/crawl.sh weibo

# 爬取中文官媒新闻
./scripts/crawl.sh cn_news

# 模拟运行（不写入数据库）
./scripts/crawl.sh all --dry-run

# 详细输出模式
./scripts/crawl.sh arxiv --verbose
```

**支持的数据源**：`all`, `arxiv`, `rss`, `weibo`, `hackernews`, `reddit`, `twitter`, `cn_news`

**选项**：
- `--dry-run`: 模拟运行，不写入数据库
- `--verbose, -v`: 显示详细输出
- `--help, -h`: 显示帮助信息

## 手动邮件发送

使用 `email.sh` 脚本可手动触发邮件发送操作：

```bash
# 发送测试邮件（验证邮件配置）
./scripts/email.sh test --to admin@example.com

# 指定后端发送测试邮件
./scripts/email.sh test --to admin@example.com --backend smtp

# 触发用户订阅通知（过去 24 小时）
./scripts/email.sh notify

# 触发通知，指定时间范围和用户数
./scripts/email.sh notify --since 2025-01-01 --max-users 10

# 发送自定义邮件
./scripts/email.sh send --to user@example.com --subject "标题" --body "内容"

# 从文件读取正文，发送 HTML 邮件
./scripts/email.sh send --to a@x.com,b@x.com --subject "标题" --body-file msg.html --html
```

**命令**：`test`（测试邮件）、`notify`（用户通知）、`send`（自定义邮件）

**通用选项**：
- `--backend <smtp|sendgrid|mailgun|brevo>`: 指定后端（默认按优先级 fallback）
- `--help, -h`: 显示帮助信息

**notify 选项**：
- `--since <YYYY-MM-DD>`: 文章时间下限（默认过去 24 小时）
- `--max-users <n>`: 最大处理用户数（默认 100）

**send 选项**：
- `--to <email>`: 收件人（多个以逗号分隔）
- `--subject <text>`: 邮件主题
- `--body <text>` / `--body-file <path>`: 邮件正文（二选一）
- `--html`: 将正文视为 HTML 格式

也可通过 `control.sh` 调用：

```bash
./scripts/control.sh email test --to admin@example.com
./scripts/control.sh email notify
./scripts/control.sh email send --to user@example.com --subject "标题" --body "内容"
```

## AI 流水线

使用 `ai-pipeline.sh` 可手动运行 AI 处理流水线的各个阶段：

```bash
# 运行完整的 AI 流水线（ai → embedding → event → topic）
./scripts/ai-pipeline.sh all

# 仅运行 AI 处理阶段
./scripts/ai-pipeline.sh ai

# 运行 AI 处理 + 嵌入计算
./scripts/ai-pipeline.sh ai embedding

# 仅运行嵌入到主题发现（跳过 AI 处理）
./scripts/ai-pipeline.sh embedding event topic

# 每阶段最多处理 200 条文章
./scripts/ai-pipeline.sh all --limit 200

# 忽略功能开关，强制运行所有阶段
./scripts/ai-pipeline.sh all --force

# 队列模式：将阶段任务入队到 pipeline_tasks 表，由 Worker 异步执行
./scripts/ai-pipeline.sh all --trigger --force

# 以 JSON 格式输出结果
./scripts/ai-pipeline.sh all --json
```

**流水线阶段**（按依赖顺序）：

| 阶段 | 说明 | 功能开关 |
|------|------|----------|
| `ai` | AI 文章处理（摘要/分类/评分） | `feature.ai_processor` |
| `translate` | 标题/摘要翻译（arXiv 英文→中文） | `feature.ai_processor` |
| `embedding` | 向量嵌入计算 | `feature.embedding` |
| `event` | 事件聚类 | `feature.event_clustering` |
| `topic` | 主题发现 | `feature.topic_radar` |
| `action` | 行动项提取 | `feature.action_items` |
| `report` | 报告生成 | `feature.report_generation` |

**选项**：
- `--limit <n>`: 每阶段最多处理的文章数（默认 50）
- `--force`: 忽略功能开关，强制运行所有指定阶段
- `--trigger`: 队列模式，将任务入队到 `pipeline_tasks` 表由 Worker 异步消费（CLI 优先级 5，高于自动触发）
- `--verbose, -v`: 显示详细输出（包含完整错误栈）
- `--json`: 以 JSON 格式输出结果
- `--help, -h`: 显示帮助信息

**说明**：无论命令行中阶段的输入顺序如何，脚本会自动按流水线依赖顺序（ai → embedding → event → topic）排列执行。功能未启用的阶段默认会被跳过，使用 `--force` 可强制运行。

### 文章重处理（reprocess）

对已有文章重新运行 AI 分析流程，适用于刷库或调试：

```bash
# Debug 模式（打印完整 AI 输入输出，默认处理 3 篇）
./scripts/ai-pipeline.sh reprocess --debug

# 重处理指定文章
./scripts/ai-pipeline.sh reprocess --ids 12188 12189 --debug

# 批量重处理 100 篇（并行 4 个 worker）
./scripts/ai-pipeline.sh reprocess --limit 100 --concurrency 4

# 仅处理未处理的文章
./scripts/ai-pipeline.sh reprocess --unprocessed

# 按来源类型筛选
./scripts/ai-pipeline.sh reprocess --source-type arxiv --limit 50

# 通过 control.sh 调用
./scripts/control.sh reprocess --debug
```

**选项**：
- `--debug, -d`: 打印完整 AI 输入输出（默认处理 3 篇）
- `--limit <n>`: 处理数量上限
- `--ids <id...>`: 指定文章 ID
- `--unprocessed`: 仅处理未处理的文章
- `--source-type <t>`: 按来源类型筛选
- `--concurrency, -c`: 并行数（默认 1，debug 模式强制串行）

### 清理 Thinking 标签（clean-thinking）

清理 AI 生成内容中的 `<thinking>` 标签：

```bash
# 清理所有文章的 content 字段
./scripts/ai-pipeline.sh clean-thinking

# 清理指定字段和文章
./scripts/ai-pipeline.sh clean-thinking --field content --field ai_summary --ids 17652

# 仅统计不执行
./scripts/ai-pipeline.sh clean-thinking --stats
```

**选项**：
- `--field, -f <field>`: 指定清理字段（默认: content，可多次指定）
- `--stats`: 仅统计不执行
- `--ids <id...>`: 指定文章 ID

## 数据同步

使用 `sync-categories.sh` 同步 arXiv 分类到数据库：

```bash
# 交互式同步（需确认）
./scripts/sync-categories.sh

# 强制同步（跳过确认）
./scripts/sync-categories.sh --force

# 详细输出模式
./scripts/sync-categories.sh --verbose

# 通过 control.sh 调用
./scripts/control.sh sync categories --force
```

**功能**：
- 从 arXiv 官方网站抓取分类列表
- 如果网站抓取失败，使用内置分类列表作为备用
- 已存在的分类将被更新，新分类将被添加

**选项**：
- `--force, -f`: 强制同步，跳过确认
- `--verbose, -v`: 显示详细输出
- `--help, -h`: 显示帮助信息

## arXiv 数据修复

使用 `repair-arxiv.sh` 修复数据库中 arXiv 文章缺失的作者和摘要数据：

```bash
# 仅检查缺失数据（不执行修复）
./scripts/repair-arxiv.sh --dry-run

# 执行修复
./scripts/repair-arxiv.sh

# 大批次修复
./scripts/repair-arxiv.sh --batch-size 50

# 通过 control.sh 调用
./scripts/control.sh repair arxiv --dry-run
```

**选项**：
- `--dry-run`: 仅检查缺失数据，不执行修复
- `--batch-size <n>`: 每批请求的 arXiv ID 数量（默认 20）
- `--verbose, -v`: 显示详细输出
- `--help, -h`: 显示帮助信息

## 测试

使用 `test.sh` 运行各种测试：

```bash
# 运行单元测试（默认）
./scripts/test.sh

# 运行所有测试
./scripts/test.sh all

# 生成覆盖率报告
./scripts/test.sh coverage

# 生成 HTML 覆盖率报告
./scripts/test.sh coverage --html

# 运行集成测试（需要数据库）
./scripts/test.sh integration

# 端到端测试（需要服务运行）
./scripts/test.sh e2e

# 按关键字过滤测试
./scripts/test.sh -k auth

# 通过 control.sh 调用
./scripts/control.sh test unit
./scripts/control.sh test coverage --html
```

**命令**：`unit`（单元测试）、`all`（所有测试）、`coverage`（覆盖率）、`integration`（集成测试）、`e2e`（端到端）、`service`（服务功能测试）、`fast`（快速测试）、`watch`（监听模式）

**选项**：
- `-v, --verbose`: 详细输出
- `-k KEYWORD`: 按关键字过滤测试
- `--html`: 生成 HTML 覆盖率报告
- `--url URL`: E2E 测试基础 URL（默认 http://localhost:8000）
- `--help, -h`: 显示帮助信息

## 微信封面图上传

使用 `upload_wechat_thumb.py` 上传图片到微信公众号永久素材，获取 `media_id`：

```bash
# 上传默认封面图（data/imgs/default_cat.png）
python scripts/upload_wechat_thumb.py

# 上传指定图片
python scripts/upload_wechat_thumb.py path/to/image.png

# 上传缩略图类型
python scripts/upload_wechat_thumb.py path/to/thumb.png --type thumb
```

**前置条件**：`.env` 中已配置 `WECHAT_MP_APPID` 和 `WECHAT_MP_SECRET`

**选项**：
- `[图片路径]`: 图片文件路径（默认 data/imgs/default_cat.png）
- `--type image|thumb`: 素材类型（默认 image，最大 10MB；thumb 最大 64KB）

## 新闻数据源播种

使用 `seed_news_sources.py` 初始化新闻数据源（英文 RSS + 中文 RSS + 中文官方媒体 HTML 源）：

```bash
# 播种所有预置新闻数据源（幂等操作）
python scripts/seed_news_sources.py
```

**说明**：基于 unique key 做 `INSERT IGNORE` / upsert，可安全重复执行。
