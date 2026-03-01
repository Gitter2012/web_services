# 更新日志

所有重要的更改都会记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

---

## [2.2.0] - 2026-03-01

### 新增

- **AIGC 内容写入模块** (`apps/aigc/article_writer.py`)
  - 统一的 AI 生成内容写入工具，供事件聚类、话题发现、行动项提取、报告生成模块调用
  - 以 `source_type='aigc'` 将 AI 生成摘要写入 articles 表
  - 利用 `(source_type, source_id, external_id)` 唯一约束保证幂等性，重复运行不创建重复记录
  - 自动标记 `ai_processed_at`，防止 AI 流水线对 AIGC 文章重复处理
  - 支持 4 种内容来源：`event_clustering`（事件聚类日报）、`topic_radar`（话题趋势日报）、`action_items`（行动建议日报）、`report`（报告中心摘要）
  - 前端新增 AIGC 分组入口，渲染 Markdown 格式内容，独立样式展示

- **后台任务管理模块** (`apps/task_manager/`)
  - `TaskManager` 类负责创建、异步执行、更新任务状态和进度查询
  - `BackgroundTask` ORM 模型持久化任务记录，支持进度回调
  - 主要用于每日报告（`daily_report`）等长耗时后台任务的状态追踪
  - 支持任务类型扩展，通过 `task_type` 字段区分不同业务任务

- **每日 arXiv 报告模块** (`apps/daily_report/`)
  - 自动生成每日 arXiv 论文报告，支持按分类分组
  - AI 翻译论文标题和摘要为中文
  - 生成微信公众号兼容的 Markdown 格式
  - 前端页面支持查看、手动生成、导出报告
  - 定时任务每天早上 8 点自动生成昨天报告
  - 数据库表 `daily_reports` 存储报告内容
  - Article 模型新增 `translated_title` 字段
  - arxiv_categories 表新增 `name_zh` 中文名称字段
  - 权限控制：`daily_report:read`、`daily_report:generate`、`daily_report:export`

- **话题匹配** (`apps/scheduler/jobs/topic_match_job.py`)
  - 自动将文章关联到相关话题的定时任务
  - 支持手动触发 API：`POST /admin/topic/match`
  - CLI 入口：`./scripts/ai-pipeline.sh topic-match`
  - 匹配算法基于关键词权重评分（相关度阈值 > 0.3）
  - 功能开关：`feature.topic_match`（默认禁用）
  - 权限控制：仅管理员可触发

- **Pipeline 任务队列** (`apps/pipeline/`)
  - `pipeline_tasks` 数据库表：持久化流水线任务，进程重启不丢失
  - DAG 触发链：AI 完成 → 自动入队 Embedding + Action → Embedding 完成 → 入队 Event
  - Worker 轮询机制：每 10 分钟（可配置）消费 pending 任务，使用 `SELECT FOR UPDATE SKIP LOCKED`
  - 失败重试：默认最多 3 次重试，超过后标记 failed
  - CLI trigger 模式：`--trigger` 参数将阶段任务入队而非直接执行

- **配置化批处理限制** (`pipeline.*` 配置项)
  - `pipeline.ai_batch_limit`: AI 批处理上限，默认 200（原硬编码 20）
  - `pipeline.embedding_batch_limit`: 嵌入批处理上限，默认 500（原硬编码 100）
  - `pipeline.event_batch_limit`: 事件聚类批处理上限，默认 500（原硬编码 200）
  - `pipeline.action_batch_limit`: 行动项提取批处理上限，默认 200（原硬编码 50）
  - `pipeline.worker_interval_minutes`: Worker 轮询间隔，默认 10 分钟
  - 所有配置项可通过管理后台 API 运行时动态调整

- **手动邮件发送脚本** (`scripts/email.sh`, `scripts/_email_runner.py`)
  - `test`: 发送测试邮件，验证邮件后端配置是否正常
  - `notify`: 手动触发用户订阅通知（等同于定时任务 `run_notification_job`）
  - `send`: 向指定地址发送自定义邮件（支持 HTML、文件读取、多收件人）
  - 支持指定后端 (smtp/sendgrid/mailgun/brevo) 或按优先级自动 fallback
  - 已集成到 `control.sh` 统一入口（`./scripts/control.sh email ...`）

- **邮件与通知代码修复** (14 项)
  - 修复 `_send_with_config` kwargs 参数名不匹配问题
  - 替换已废弃的 `get_event_loop().run_in_executor()` 为 `asyncio.to_thread()`
  - 修复 `send_email_with_fallback` 丢失最终错误信息
  - 修复 `update_email_settings` 链式 `.values()` 覆盖问题
  - 统一 `email_enabled` 与 `feature.email_notification` 双开关检查
  - 修复管理员报告收件人地址错误
  - 修复非 SMTP 后端测试邮件未实际发送
  - 修复 ArXiv/WeChat 订阅匹配使用 ID 而非 code/name
  - 统一邮件发送路径（优先使用 `send_email_with_priority`）
  - 添加 `is_active` 过滤条件到订阅查询
  - 移除 SMTP 重试循环中的死代码
  - 替换邮件模板中的硬编码占位 URL
  - 使用 `hmac.compare_digest()` 替代明文比较验证码/令牌
  - 添加 `asyncio.Semaphore(5)` 控制并发通知发送

- **爬虫模块重构** (`apps/crawler/`)
  - `registry.py`: 爬虫注册表，支持装饰器方式注册爬虫类型
  - `factory.py`: 爬虫工厂，封装爬虫实例创建逻辑
  - `runner.py`: 统一运行器，提供单源/多源/全量爬取入口
  - `crawl.sh`: 手动爬取触发脚本

### 变更

- **爬虫模块架构优化**
  - 采用工厂模式 + 注册表模式重构爬虫模块
  - 简化 `crawl_job.py`，移除冗余代码
  - 添加新数据源无需修改调度代码，只需注册装饰器

- **arXiv 爬虫增强**
  - 支持多排序模式（submittedDate + lastUpdatedDate）
  - 添加论文类型标记（new/updated）
  - 新增 RSS 新域名 rss.arxiv.org，保留旧域名作为备用
  - 更新 HTML 解析适配 arXiv 页面结构变化

### 文档

- 全面更新 README.md，新增 7 种数据源说明、完整 API 概览、测试指南
- 全面更新 docs/API.md，新增健康检查、调度任务管理、备份管理等 API 文档
- 全面更新 docs/ARCHITECTURE.md，新增 Provider 模式、混合聚类算法、Kubernetes 部署架构
- 全面更新 docs/DEPLOYMENT.md，新增 Docker 多阶段构建、K8s 探针、Gunicorn 配置
- 全面更新 docs/CONFIGURATION.md，新增微博/Twitter/Claude 配置、完整 YAML 参考
- 全面更新 docs/CHANGELOG.md，补充完整版本历史和功能记录
- 补充 Sphinx 兼容 docstring 规范说明与文档维护提示

---

## [2.1.0] - 2026-02-14

### 新增

- **AI 内容分析** (`apps/ai_processor/`)
  - 基于 Ollama/OpenAI/Claude 的文章摘要生成
  - 自动分类和重要性评分（1-10）
  - 关键要点提取和影响评估
  - 可执行行动项提取
  - Token 用量统计与追踪
  - 支持批量处理（单次最多 100 篇）
  - 结果缓存（默认 TTL 24h）
  - 多种处理优化策略（rule_based/domain_fast/minimal/full）

- **向量嵌入** (`apps/embedding/`)
  - 基于 sentence-transformers（all-MiniLM-L6-v2, 384 维）的文章向量化
  - Milvus 向量数据库存储与检索
  - 语义相似文章推荐（cosine similarity）
  - 支持批量计算（单次最多 1000 篇）
  - 索引重建功能
  - 嵌入统计 API

- **事件聚类** (`apps/event/`)
  - 基于规则权重(0.4) + 语义相似度(0.6)的混合聚类算法
  - 事件时间线追踪
  - 可配置聚类参数（权重、相似度阈值、时间窗口）
  - 事件生命周期管理（active/closed/archived）

- **话题雷达** (`apps/topic/`)
  - 自动发现新兴话题（关键词频率分析）
  - 话题趋势追踪（上升/下降/稳定）
  - 手动创建和管理话题
  - 话题关联文章检索
  - 话题快照与历史趋势
  - 可配置发现参数（最小频率、回溯天数、置信度）

- **行动项管理** (`apps/action/`)
  - 从文章中提取可执行行动项
  - 支持优先级设置（高/中/低）
  - 完成/忽略状态管理
  - 按用户隔离

- **报告生成** (`apps/report/`)
  - 自动生成周报/月报
  - 汇总期间研究动态、文章统计、事件和话题
  - 报告查看与删除

- **功能开关系统** (`common/feature_config.py`)
  - 10 个独立功能开关，覆盖所有高级模块
  - 通过管理 API 动态切换，运行时生效
  - 数据库持久化，内存缓存（60s TTL）

- **新增数据源**
  - 微博热搜爬虫（`apps/crawler/weibo/`）- 热搜排名采集
  - Twitter 爬虫（`apps/crawler/twitter/`）- 通过 TwitterAPI.io 第三方 API
  - HackerNews 爬虫（`apps/crawler/hackernews/`）- 热帖聚合
  - Reddit 爬虫（`apps/crawler/reddit/`）- 热门帖子聚合

- **新增定时任务**
  - AI 分析任务（每 1 小时，处理 50 篇）
  - 向量嵌入任务（每 2 小时，处理 100 篇）
  - 事件聚类任务（每天凌晨 2 点，处理 200 篇）
  - 话题发现任务（每周一凌晨 1 点）

- **管理后台增强**
  - 功能开关管理 API
  - 调度任务管理 API（查看/修改调度参数/手动触发）
  - 系统配置分组查看和批量更新
  - 备份管理 API（列表/创建）
  - 爬虫状态查看与手动触发

- **认证增强**
  - Refresh Token 支持（7 天有效期）
  - 修改密码 API
  - 登出 API

- **健康检查增强**
  - `GET /health` - 完整组件状态（数据库/Redis/Milvus/Ollama）
  - `GET /health/live` - Kubernetes 存活探针
  - `GET /health/ready` - Kubernetes 就绪探针

- **Docker 支持**
  - 多阶段构建 Dockerfile（builder + production）
  - 非 root 用户运行（appuser）
  - 内置健康检查（30s 间隔）
  - docker-compose.milvus.yml Milvus 部署配置

### 技术栈新增

- Milvus 2.3+ 向量数据库
- Ollama 本地 AI 推理
- OpenAI GPT-4o / GPT-4o-mini 云端推理
- Anthropic Claude 云端推理
- sentence-transformers 向量嵌入
- TwitterAPI.io 第三方 Twitter API

### 改进

- 爬虫模块重构为插件架构（BaseCrawler 基类）
- HTTP 客户端增强防爬策略（UA 轮换、连接池轮换、指数退避）
- 配置系统支持运行时动态修改（管理 API）

---

## [2.0.0] - 2026-02-13

### 新增

- **用户系统**
  - 用户注册、登录
  - JWT Token 认证（HS256 签名）
  - RBAC 权限管理（viewer/editor/admin/superuser）
  - 超级管理员自动创建

- **订阅管理**
  - 用户可订阅 arXiv 类目
  - 用户可订阅 RSS 源
  - 用户可订阅微信公众号

- **邮件推送**
  - SMTP / SendGrid / Mailgun / Brevo 四种后端
  - 多端口自动重试（587/465/2525）
  - SSL/TLS 自动适配
  - 用户可配置推送频率（daily/weekly/none）
  - 超级管理员默认不推送

- **Markdown 导出**
  - 一键导出当前筛选文章
  - 支持按来源、分类、时间筛选
  - 用户订阅导出

- **管理后台**
  - 用户管理（列表/角色修改/启停）
  - 爬虫配置
  - 系统设置
  - 邮件推送配置

- **微信爬虫**
  - RSS Feed 解析
  - 图片本地缓存
  - 多账号批量爬取

- **HTTP 增强**
  - User-Agent 轮换（10 种浏览器标识）
  - 连接池自动轮换（每 25 次请求）
  - Rate Limit 自动处理（429/503 重试）
  - 请求缓存

- **前端功能**
  - 导航首页
  - 来源筛选（arXiv/RSS/微信）
  - 分类联动筛选
  - 中英对照翻译链接
  - 谷歌翻译链接
  - 文章收藏功能

- **配置管理**
  - 四层配置优先级（环境变量 > .env > YAML > 代码默认值）
  - Pydantic Settings 类型安全
  - YAML 非敏感配置分离

### 改进

- 数据库使用 MySQL 替代 SQLite，支持连接池管理
- 全异步架构（FastAPI + aiomysql + httpx）
- 统一的日志系统（可配置级别和格式）
- 配置文件分离（敏感/非敏感）
- 全局异常处理器（不泄露内部错误信息）

### 技术栈

- FastAPI 替代 Flask
- SQLAlchemy 2.0 ORM（异步驱动 aiomysql）
- APScheduler 定时任务（AsyncIOScheduler）
- httpx 异步 HTTP 客户端
- Pydantic v2 + pydantic-settings 配置管理
- PyJWT + bcrypt 认证
- Jinja2 模板引擎

---

## [1.0.0] - 2025-xx-xx

### 新增

- arXiv 论文抓取（API 方式）
- RSS 文章抓取（feedparser）
- 微信公众号抓取（RSS 代理）
- 基础前端展示（Jinja2 模板）
- 邮件通知功能（SMTP）
- Markdown 输出

### 技术栈

- Flask 后端框架
- SQLite 数据库
- 同步架构

---

## 版本规划

### [2.3.0] - 计划中

- [ ] 文章推荐算法（基于用户行为 + 向量相似度）
- [ ] 阅读进度追踪
- [ ] 移动端适配（响应式 UI）
- [ ] WebSocket 实时推送
- [ ] 社交功能（评论、分享）
- [ ] 高级搜索（全文检索 + 语义搜索）
- [ ] 数据分析仪表盘
- [ ] Webhook 通知（新文章事件）
- [ ] 多语言支持（i18n）
- [ ] API 速率限制中间件

### [3.0.0] - 远期规划

- [ ] 微服务拆分（爬虫/AI/检索独立部署）
- [ ] 消息队列（RabbitMQ/Kafka）
- [ ] 分布式任务调度（Celery）
- [ ] 全文检索引擎（Elasticsearch/MeiliSearch）
- [ ] 前后端分离（Vue.js/React 前端）
- [ ] GraphQL API

---

## 贡献

欢迎提交 Issue 和 Pull Request！

---

## 版本号说明

- **主版本号**: 不兼容的 API 更改
- **次版本号**: 向下兼容的功能新增
- **修订号**: 向下兼容的问题修复
