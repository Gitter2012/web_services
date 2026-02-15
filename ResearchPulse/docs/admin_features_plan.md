# ResearchPulse 管理后台功能完善规划

> 本规划对应 README 中“管理后台功能增强”章节，用于说明后台能力补齐方向与优先级。

## 一、当前状态概览

### 已完成功能 ✅
- 数据源管理（ArXiv/RSS/微信/待审批RSS）
- 用户管理（启用/禁用）
- 订阅管理（用户端RSS提交）

### 需要完善的功能 ⚠️

---

## 二、功能规划详情

### 阶段一：高优先级 - 修复现有占位实现

#### 1. 邮件推送配置（Email Configuration）
**问题**: 前端UI存在，但后端API未实现，所有操作都是占位符

**需要实现**:
| 任务 | 描述 | 文件位置 |
|------|------|----------|
| 创建邮件配置模型 | 存储 SMTP 配置和推送设置 | `apps/admin/models.py` 或新建 |
| 实现 GET/PUT `/admin/email/config` | 加载/保存邮件配置 | `apps/admin/api.py` |
| 实现 POST `/admin/email/test` | 发送测试邮件 | `apps/admin/api.py` |
| 连接前端JavaScript | 调用实际API而非占位符 | `apps/ui/templates/admin.html` |

**数据模型设计**:
```python
class EmailConfig(Base):
    __tablename__ = "email_configs"

    id: Mapped[int] = mapped_column(primary_key=True)
    # SMTP 配置
    smtp_host: Mapped[str] = mapped_column(String(255))
    smtp_port: Mapped[int] = mapped_column(default=587)
    smtp_user: Mapped[str] = mapped_column(String(255))
    smtp_password: Mapped[str] = mapped_column(String(255))  # 加密存储
    smtp_use_tls: Mapped[bool] = mapped_column(default=True)

    # 推送配置
    email_enabled: Mapped[bool] = mapped_column(default=False)
    push_frequency: Mapped[str] = mapped_column(String(20), default="daily")  # daily/weekly/instant
    push_time: Mapped[str] = mapped_column(String(10), default="09:00")
    max_articles_per_email: Mapped[int] = mapped_column(default=20)

    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)
```

---

#### 2. 系统配置（System Configuration）
**问题**: 后端API存在（`/admin/config`），但前端未正确连接

**需要实现**:
| 任务 | 描述 |
|------|------|
| 实现 `loadConfig()` | 调用 GET `/admin/config` 加载现有配置 |
| 实现 `saveConfig()` | 调用 PUT `/admin/config/batch` 保存配置 |
| 添加更多配置项 | 抓取间隔、并发数、超时设置等 |

**建议配置项**:
- `article_retention_days`: 文章保留天数
- `backup_retention_days`: 备份保留天数
- `crawl_interval_minutes`: 抓取间隔
- `max_concurrent_crawls`: 最大并发抓取数
- `crawl_timeout_seconds`: 抓取超时时间

---

#### 3. 爬取任务管理（Crawler Management）
**问题**: API返回占位符，不实际触发任务

**需要实现**:
| 任务 | 描述 |
|------|------|
| 集成 APScheduler | 连接调度器实现实际任务触发 |
| 实现 `saveCrawlConfig()` | 保存抓取配置到数据库 |
| 实现 `triggerCrawl()` | 实际触发爬取任务 |
| 添加任务状态查询 | GET `/admin/crawler/status` |

**新增管理界面**:
```
爬取配置页面:
├── 全局设置
│   ├── 自动抓取开关
│   ├── 抓取间隔设置
│   └── 并发数限制
├── 任务队列
│   ├── 待执行任务列表
│   ├── 正在执行任务
│   └── 任务历史记录
└── 手动触发
    ├── 选择数据源类型
    ├── 选择具体源
    └── 立即执行
```

---

#### 4. 备份管理（Backup Management）
**问题**: API返回占位符，不实际执行备份

**需要实现**:
| 任务 | 描述 |
|------|------|
| 实现备份逻辑 | 数据库导出、文件打包 |
| 实现恢复逻辑 | 从备份恢复数据 |
| 添加备份列表 | 显示历史备份文件 |
| 添加下载/删除功能 | 管理备份文件 |

**新增管理界面**:
```
备份管理页面:
├── 备份设置
│   ├── 自动备份开关
│   ├── 备份频率
│   └── 保留数量
├── 手动备份
│   └── [创建备份] 按钮
├── 备份列表
│   ├── 文件名 | 大小 | 创建时间 | 操作
│   └── 下载 | 恢复 | 删除
└── 恢复功能
    └── 选择备份文件恢复
```

---

### 阶段二：中优先级 - 新增管理功能

#### 5. 审计日志（Audit Log）
**现状**: 模型存在，无管理界面

**需要实现**:
| 任务 | 描述 |
|------|------|
| GET `/admin/audit-logs` | 分页查询审计日志 |
| 添加审计日志页面 | 显示操作历史 |

**管理界面设计**:
```
审计日志页面:
├── 筛选条件
│   ├── 用户选择
│   ├── 操作类型（登录/订阅/爬取/配置变更）
│   └── 时间范围
├── 日志列表
│   ├── 时间 | 用户 | 操作 | 详情 | IP地址
│   └── 分页显示
└── 导出功能
    └── 导出CSV/JSON
```

---

#### 6. 事件聚类管理（Event Cluster）
**现状**: 模型存在，无管理界面

**需要实现**:
| 任务 | 描述 |
|------|------|
| GET `/admin/events` | 列出事件聚类 |
| PUT `/admin/events/{id}` | 编辑事件信息 |
| POST `/admin/events/merge` | 合并事件 |
| DELETE `/admin/events/{id}` | 删除事件 |

**管理界面设计**:
```
事件管理页面:
├── 统计概览
│   ├── 总事件数
│   ├── 今日新增
│   └── 待审核事件
├── 事件列表
│   ├── 事件名称 | 文章数 | 热度 | 创建时间 | 操作
│   └── 查看 | 编辑 | 合并 | 删除
├── 事件详情
│   ├── 关联文章列表
│   └── 关键词调整
└── 合并功能
    └── 选择多个事件合并
```

---

#### 7. 主题管理（Topic Management）
**现状**: 模型存在，无管理界面

**需要实现**:
| 任务 | 描述 |
|------|------|
| GET `/admin/topics` | 列出主题 |
| POST `/admin/topics` | 创建主题 |
| PUT `/admin/topics/{id}` | 编辑主题关键词 |
| DELETE `/admin/topics/{id}` | 删除主题 |
| GET `/admin/topics/{id}/snapshots` | 查看主题趋势 |

**管理界面设计**:
```
主题管理页面:
├── 统计概览
│   ├── 手动创建主题数
│   ├── 自动发现主题数
│   └── 活跃主题数
├── 主题列表
│   ├── 主题名称 | 类型 | 关键词 | 文章数 | 操作
│   └── 查看 | 编辑 | 删除
├── 创建主题
│   ├── 名称输入
│   ├── 关键词输入（逗号分隔）
│   └── 类型选择（手动/自动）
└── 趋势分析
    └── 主题快照图表
```

---

#### 8. 报告管理（Report Management）
**现状**: 模型存在，无管理界面

**需要实现**:
| 任务 | 描述 |
|------|------|
| GET `/admin/reports` | 列出报告 |
| POST `/admin/reports/generate` | 手动生成报告 |
| GET `/admin/reports/{id}` | 查看报告详情 |
| DELETE `/admin/reports/{id}` | 删除报告 |

**管理界面设计**:
```
报告管理页面:
├── 报告设置
│   ├── 自动生成开关
│   ├── 生成频率（周报/月报）
│   └── 发送到邮箱
├── 手动生成
│   ├── 选择时间范围
│   ├── 选择报告类型
│   └── [生成报告] 按钮
├── 报告列表
│   ├── 报告名称 | 类型 | 时间范围 | 创建时间 | 操作
│   └── 查看 | 下载 | 删除
└── 报告预览
    └── 在线查看报告内容
```

---

#### 9. 向量嵌入管理（Embedding Management）
**现状**: 模型存在，无管理界面

**需要实现**:
| 任务 | 描述 |
|------|------|
| GET `/admin/embeddings/stats` | 嵌入统计 |
| POST `/admin/embeddings/recompute` | 重新计算嵌入 |
| GET `/admin/embeddings/missing` | 查看缺少嵌入的文章 |

**管理界面设计**:
```
嵌入管理页面:
├── 统计概览
│   ├── 总文章数
│   ├── 已嵌入数
│   ├── 未嵌入数
│   └── 嵌入模型版本
├── 批量操作
│   ├── [计算缺失嵌入]
│   └── [全部重新计算]
├── 缺失列表
│   └── 未嵌入文章列表
└── 设置
    ├── 嵌入模型选择
    └── 批处理大小
```

---

### 阶段三：低优先级 - 优化完善

#### 10. 仪表盘统计完善
**问题**: `subscriptions` 统计未返回

**需要修复**:
```python
# apps/admin/api.py - get_stats() 函数
async def get_stats(...) -> Dict[str, Any]:
    # 添加订阅统计
    subscriptions_count = await session.scalar(
        select(func.count()).select_from(Subscription)
    )
    return {
        "users": users_count,
        "articles": articles_count,
        "sources": sources_count,
        "subscriptions": subscriptions_count,  # 添加此项
        "today_articles": today_count,
    }
```

---

#### 11. 微信公众号字段修复
**问题**: 模型使用 `account_name`，API期望 `account_id`

**需要修复**:
| 文件 | 修改内容 |
|------|----------|
| `apps/admin/api.py` | 统一使用 `account_name` 或在API层做转换 |
| `apps/ui/templates/admin.html` | 表单字段名与后端保持一致 |

---

#### 12. 用户收藏管理
**问题**: 前端有 TODO 占位符

**需要实现**:
- GET `/admin/users/{id}/stars` - 查看用户收藏
- 在用户管理页面添加收藏统计列

---

## 三、实施优先级排序

### 第一批（立即实施）
1. ✅ 邮件推送配置 - 完整功能链路
2. ✅ 系统配置 - 连接现有API
3. ✅ 仪表盘统计修复 - 添加订阅数

### 第二批（近期实施）
4. 爬取任务管理 - 集成调度器
5. 备份管理 - 实际备份逻辑
6. 审计日志 - 安全合规

### 第三批（后续实施）
7. 事件聚类管理
8. 主题管理
9. 报告管理
10. 向量嵌入管理

---

## 四、文件变更预估

| 功能 | 新增文件 | 修改文件 |
|------|----------|----------|
| 邮件配置 | - | `apps/admin/api.py`, `apps/admin/models.py`, `admin.html` |
| 系统配置 | - | `admin.html` |
| 爬取管理 | - | `apps/admin/api.py`, `admin.html` |
| 备份管理 | `apps/admin/backup.py` | `apps/admin/api.py`, `admin.html` |
| 审计日志 | - | `apps/admin/api.py`, `admin.html` |
| 事件管理 | - | `apps/admin/api.py`, `admin.html` |
| 主题管理 | - | `apps/admin/api.py`, `admin.html` |
| 报告管理 | - | `apps/admin/api.py`, `admin.html` |
| 嵌入管理 | - | `apps/admin/api.py`, `admin.html` |

---

## 五、API 路由规划

```
/api/v1/admin/
├── config/                    # 系统配置
│   ├── GET /                  # 获取所有配置
│   └── PUT /batch             # 批量更新配置
├── email/                     # 邮件配置
│   ├── GET /config            # 获取邮件配置
│   ├── PUT /config            # 更新邮件配置
│   └── POST /test             # 发送测试邮件
├── crawler/                   # 爬取管理
│   ├── GET /status            # 获取爬取状态
│   ├── POST /trigger          # 触发爬取任务
│   └── GET /tasks             # 任务列表
├── backups/                   # 备份管理
│   ├── GET /                  # 备份列表
│   ├── POST /create           # 创建备份
│   ├── GET /{id}/download     # 下载备份
│   ├── POST /{id}/restore     # 恢复备份
│   └── DELETE /{id}           # 删除备份
├── audit-logs/                # 审计日志
│   └── GET /                  # 日志列表（分页筛选）
├── events/                    # 事件管理
│   ├── GET /                  # 事件列表
│   ├── PUT /{id}              # 编辑事件
│   ├── POST /merge            # 合并事件
│   └── DELETE /{id}           # 删除事件
├── topics/                    # 主题管理
│   ├── GET /                  # 主题列表
│   ├── POST /                 # 创建主题
│   ├── PUT /{id}              # 编辑主题
│   ├── DELETE /{id}           # 删除主题
│   └── GET /{id}/snapshots    # 主题趋势
├── reports/                   # 报告管理
│   ├── GET /                  # 报告列表
│   ├── POST /generate         # 生成报告
│   ├── GET /{id}              # 报告详情
│   └── DELETE /{id}           # 删除报告
└── embeddings/                # 嵌入管理
    ├── GET /stats             # 嵌入统计
    ├── GET /missing           # 缺失嵌入的文章
    └── POST /recompute        # 重新计算嵌入
```

---

## 六、数据库迁移预估

### 新增表
- `email_configs` - 邮件配置表

### 现有表（无需迁移）
- `audit_logs` - 已存在
- `article_embeddings` - 已存在
- `event_clusters` - 已存在
- `topics` - 已存在
- `reports` - 已存在

---

请确认此规划后，我可以开始按优先级逐步实现各项功能。
