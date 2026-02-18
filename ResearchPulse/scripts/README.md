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

# 模拟运行（不写入数据库）
./scripts/crawl.sh all --dry-run

# 详细输出模式
./scripts/crawl.sh arxiv --verbose
```

**支持的数据源**：`all`, `arxiv`, `rss`, `weibo`, `hackernews`, `reddit`, `twitter`

**选项**：
- `--dry-run`: 模拟运行，不写入数据库
- `--verbose, -v`: 显示详细输出
- `--help, -h`: 显示帮助信息

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
