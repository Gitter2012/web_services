# ResearchPulse 管理后台完整实施规划

> 本规划对应 README 中“管理后台功能增强”章节，用于说明具体实施路径与技术拆解。

## 一、项目概述

本规划基于代码分析，全面实现管理后台的功能完善，包括：
- 修复现有占位符实现
- 连接未生效的前后端功能
- 新增缺失的管理功能
- 对应 `config/defaults.yaml` 中所有功能的管理界面

---

## 二、实施架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           管理后台前端 (admin.html)                          │
├─────────────────────────────────────────────────────────────────────────────┤
│  仪表盘  │  数据源  │  爬取管理  │  AI配置  │  向量配置  │  事件管理  │  主题管理  │
│  用户管理 │  邮件配置 │  备份管理 │  审计日志 │  报告管理 │  功能开关 │  系统配置 │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        管理后台 API (apps/admin/api.py)                      │
├─────────────────────────────────────────────────────────────────────────────┤
│  /stats  │  /users  │  /sources/*  │  /config  │  /features  │  /scheduler  │
│  /email  │  /backups │  /audit-logs │  /events  │  /topics  │  /reports    │
│  /crawler │ /embeddings │ /notifications │ /actions                                     │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                     数据层 & 配置服务 (feature_config.py)                     │
├─────────────────────────────────────────────────────────────────────────────┤
│  SystemConfig  │  BackupRecord  │  AuditLog  │  EventCluster  │  Topic      │
│  Report  │  ArticleEmbedding  │  ActionItem  │  EmailConfig (新建)           │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 三、详细实施计划

### 模块 1: 仪表盘优化 (Dashboard)

**优先级**: P0 - 立即实施
**预估工作量**: 小

#### 1.1 添加订阅统计
| 文件 | 修改内容 |
|------|----------|
| `apps/admin/api.py:61-96` | 在 `get_stats()` 中添加订阅数查询 |
| `apps/ui/templates/admin.html` | 前端已支持，无需修改 |

**代码修改**:
```python
# apps/admin/api.py - get_stats()
from apps.crawler.models import Subscription

# 添加订阅统计
subscriptions_count = await session.execute(select(func.count(Subscription.id)))
subscriptions = subscriptions_count.scalar() or 0

return {
    "users": users,
    "articles": articles,
    "sources": sources,
    "subscriptions": subscriptions,  # 新增
    "today_articles": today_articles,
}
```

#### 1.2 添加功能状态概览
在仪表盘显示各功能模块的启用状态：
- AI 处理
- 向量嵌入
- 事件聚类
- 话题雷达
- 邮件通知

---

### 模块 2: 系统配置连接 (System Configuration)

**优先级**: P0 - 立即实施
**预估工作量**: 中

#### 2.1 前端连接现有 API
| 文件 | 修改内容 |
|------|----------|
| `apps/ui/templates/admin.html` | 实现 `loadConfig()` 和 `saveConfig()` |

**代码修改**:
```javascript
// 加载配置
async function loadConfig() {
    const token = localStorage.getItem('access_token');
    const res = await fetch(`${ADMIN_BASE}/config/groups`, {
        headers: { 'Authorization': `Bearer ${token}` }
    });
    const data = await res.json();
    // 渲染配置表单...
}

// 保存配置
async function saveConfig() {
    const token = localStorage.getItem('access_token');
    const configs = {};  // 从表单收集
    const res = await fetch(`${ADMIN_BASE}/config/batch`, {
        method: 'PUT',
        headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ configs })
    });
    // 处理响应...
}
```

#### 2.2 扩展配置项（对应 defaults.yaml）
新增配置项到 `common/feature_config.py`:
```python
DEFAULT_CONFIGS = {
    # ... 现有配置 ...
    
    # 数据保留配置
    "retention.active_days": ("7", "Article active retention days"),
    "retention.archive_days": ("30", "Archive retention days"),
    "retention.backup_enabled": ("true", "Enable automatic backup"),
    
    # JWT 配置
    "jwt.access_token_expire_minutes": ("30", "Access token expiration"),
    "jwt.refresh_token_expire_days": ("7", "Refresh token expiration"),
    
    # 缓存配置
    "cache.enabled": ("false", "Enable caching"),
    "cache.default_ttl": ("300", "Default cache TTL in seconds"),
    
    # 视频配置
    "video.enabled": ("false", "Enable video generation"),
    "video.tts_provider": ("edge-tts", "TTS provider"),
    "video.tts_voice": ("yunxi", "TTS voice"),
}
```

---

### 模块 3: 邮件配置管理 (Email Configuration)

**优先级**: P0 - 立即实施
**预估工作量**: 中

#### 3.1 新增数据模型
| 文件 | 修改内容 |
|------|----------|
| `apps/admin/models.py` 或新建 | 创建 `EmailConfig` 模型 |

```python
class EmailConfig(Base, TimestampMixin):
    __tablename__ = "email_configs"

    id: Mapped[int] = mapped_column(primary_key=True)

    # SMTP 配置
    smtp_host: Mapped[str] = mapped_column(String(255), default="")
    smtp_port: Mapped[int] = mapped_column(default=587)
    smtp_user: Mapped[str] = mapped_column(String(255), default="")
    smtp_password: Mapped[str] = mapped_column(String(255), default="")  # 加密
    smtp_use_tls: Mapped[bool] = mapped_column(default=True)

    # SendGrid 配置
    sendgrid_api_key: Mapped[str] = mapped_column(String(255), default="")

    # Mailgun 配置
    mailgun_api_key: Mapped[str] = mapped_column(String(255), default="")
    mailgun_domain: Mapped[str] = mapped_column(String(255), default="")

    # Brevo 配置
    brevo_api_key: Mapped[str] = mapped_column(String(255), default="")
    brevo_from_name: Mapped[str] = mapped_column(String(100), default="ResearchPulse")

    # 推送配置
    email_enabled: Mapped[bool] = mapped_column(default=False)
    active_backend: Mapped[str] = mapped_column(String(20), default="smtp")
    push_frequency: Mapped[str] = mapped_column(String(20), default="daily")
    push_time: Mapped[str] = mapped_column(String(10), default="09:00")
    max_articles_per_email: Mapped[int] = mapped_column(default=20)
```

#### 3.2 新增 API 端点
| 端点 | 方法 | 功能 |
|------|------|------|
| `/admin/email/config` | GET | 获取邮件配置 |
| `/admin/email/config` | PUT | 更新邮件配置 |
| `/admin/email/test` | POST | 发送测试邮件 |

#### 3.3 前端实现
在 `admin.html` 的邮件配置部分连接真实 API

---

### 模块 4: 爬取任务管理 (Crawler Management)

**优先级**: P1 - 近期实施
**预估工作量**: 中

#### 4.1 实现爬取触发
| 文件 | 修改内容 |
|------|----------|
| `apps/admin/api.py:264-278` | 实现真实的爬取任务触发 |

```python
@router.post("/crawler/trigger")
async def trigger_crawl(
    source_type: str,
    source_id: str,
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Manually trigger a crawl task (admin only)."""
    from apps.scheduler.tasks import get_scheduler
    from apps.crawler.tasks import crawl_arxiv, crawl_rss, crawl_wechat

    task_map = {
        "arxiv": crawl_arxiv,
        "rss": crawl_rss,
        "wechat": crawl_wechat,
    }

    if source_type not in task_map:
        raise HTTPException(400, f"Unknown source type: {source_type}")

    # 异步执行爬取任务
    scheduler = get_scheduler()
    job = scheduler.add_job(
        task_map[source_type],
        args=[source_id],
        id=f"manual_crawl_{source_type}_{source_id}_{datetime.now().timestamp()}",
    )

    return {
        "status": "ok",
        "job_id": job.id,
        "message": f"Crawl triggered for {source_type}:{source_id}",
    }
```

#### 4.2 新增爬取配置 UI
扩展 "抓取配置" 页面：
- 全局设置（并发数、超时、重试）
- 各源独立设置（ArXiv delay、RSS timeout 等）
- 任务队列状态

---

### 模块 5: 备份管理实现 (Backup Management)

**优先级**: P1 - 近期实施
**预估工作量**: 中

#### 5.1 实现备份逻辑
| 文件 | 修改内容 |
|------|----------|
| `apps/admin/backup.py` (新建) | 备份服务逻辑 |
| `apps/admin/api.py:639-649` | 调用实际备份服务 |

```python
# apps/admin/backup.py
import json
import gzip
import shutil
from datetime import datetime, timezone
from pathlib import Path

async def create_backup(session: AsyncSession, data_dir: str) -> Dict[str, Any]:
    """Create a database backup."""
    backup_date = datetime.now(timezone.utc)
    backup_file = f"backup_{backup_date.strftime('%Y%m%d_%H%M%S')}.json.gz"
    backup_path = Path(data_dir) / "backups" / backup_file

    # 导出数据
    articles = await session.execute(select(Article))
    feeds = await session.execute(select(RssFeed))
    # ...

    backup_data = {
        "articles": [a.to_dict() for a in articles.scalars().all()],
        "feeds": [f.to_dict() for f in feeds.scalars().all()],
        # ...
    }

    # 压缩保存
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(backup_path, 'wt', encoding='utf-8') as f:
        json.dump(backup_data, f)

    return {
        "file": str(backup_path),
        "size": backup_path.stat().st_size,
        "article_count": len(backup_data["articles"]),
    }
```

#### 5.2 新增恢复功能
| 端点 | 方法 | 功能 |
|------|------|------|
| `/admin/backups/{id}/download` | GET | 下载备份文件 |
| `/admin/backups/{id}/restore` | POST | 从备份恢复 |
| `/admin/backups/{id}` | DELETE | 删除备份 |

---

### 模块 6: 审计日志管理 (Audit Log)

**优先级**: P1 - 近期实施
**预估工作量**: 小

#### 6.1 新增 API 端点
| 文件 | 修改内容 |
|------|----------|
| `apps/admin/api.py` | 添加审计日志查询端点 |

```python
@router.get("/audit-logs")
async def list_audit_logs(
    user_id: Optional[int] = None,
    action: Optional[str] = None,
    resource_type: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    page: int = 1,
    page_size: int = 50,
    admin: Superuser = None,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """List audit logs with filtering."""
    from apps.crawler.models import AuditLog

    query = select(AuditLog)

    if user_id:
        query = query.where(AuditLog.user_id == user_id)
    if action:
        query = query.where(AuditLog.action == action)
    if resource_type:
        query = query.where(AuditLog.resource_type == resource_type)
    if start_date:
        query = query.where(AuditLog.created_at >= start_date)
    if end_date:
        query = query.where(AuditLog.created_at <= end_date)

    # 分页...
```

#### 6.2 前端实现
新增审计日志页面，包含：
- 用户筛选
- 操作类型筛选
- 时间范围筛选
- 日志详情查看
- 导出功能

---

### 模块 7: AI 配置管理 (AI Configuration)

**优先级**: P2 - 后续实施
**预估工作量**: 中

#### 7.1 功能对应 defaults.yaml
```yaml
ai_processor:
  enabled: false
  provider: "ollama"
  ollama:
    base_url: "http://localhost:11434"
    model: "qwen3:32b"
    timeout: 120
  openai:
    model: "gpt-4o"
  claude:
    model: "claude-sonnet-4-20250514"
```

#### 7.2 新增 API 端点
| 端点 | 方法 | 功能 |
|------|------|------|
| `/admin/ai/config` | GET | 获取 AI 配置 |
| `/admin/ai/config` | PUT | 更新 AI 配置 |
| `/admin/ai/test` | POST | 测试 AI 连接 |

#### 7.3 新增配置项
```python
# common/feature_config.py 扩展
DEFAULT_CONFIGS = {
    # ... 现有 ...
    "ai.openai_model": ("gpt-4o", "OpenAI model name"),
    "ai.openai_model_light": ("gpt-4o-mini", "OpenAI light model"),
    "ai.claude_model": ("claude-sonnet-4-20250514", "Claude model name"),
    "ai.claude_model_light": ("claude-haiku-4-20250514", "Claude light model"),
    "ai.thinking_enabled": ("false", "Enable thinking mode"),
    "ai.concurrent_enabled": ("false", "Enable concurrent processing"),
    "ai.workers_heavy": ("2", "Heavy task workers"),
    "ai.workers_screen": ("4", "Screen task workers"),
}
```

#### 7.4 前端实现
新增 AI 配置页面：
- Provider 选择（Ollama/OpenAI/Claude）
- 各 Provider 参数配置
- 规则优化选项
- 测试按钮

---

### 模块 8: 向量嵌入管理 (Embedding Management)

**优先级**: P2 - 后续实施
**预估工作量**: 中

#### 8.1 功能对应 defaults.yaml
```yaml
embedding:
  enabled: false
  provider: "sentence-transformers"
  model: "all-MiniLM-L6-v2"
  milvus:
    host: "localhost"
    port: 19530
```

#### 8.2 新增 API 端点
| 端点 | 方法 | 功能 |
|------|------|------|
| `/admin/embeddings/stats` | GET | 嵌入统计 |
| `/admin/embeddings/config` | GET/PUT | 嵌入配置 |
| `/admin/embeddings/missing` | GET | 缺失嵌入的文章 |
| `/admin/embeddings/recompute` | POST | 重新计算嵌入 |

#### 8.3 前端实现
新增嵌入管理页面：
- Milvus 连接配置
- 嵌入模型选择
- 统计概览
- 批量操作按钮

---

### 模块 9: 事件聚类管理 (Event Management)

**优先级**: P2 - 后续实施
**预估工作量**: 中

#### 9.1 功能对应 defaults.yaml
```yaml
event:
  enabled: false
  clustering:
    rule_weight: 0.4
    semantic_weight: 0.6
    min_similarity: 0.7
```

#### 9.2 新增 API 端点
| 端点 | 方法 | 功能 |
|------|------|------|
| `/admin/events` | GET | 事件列表 |
| `/admin/events/{id}` | GET | 事件详情 |
| `/admin/events/{id}` | PUT | 编辑事件 |
| `/admin/events/{id}` | DELETE | 删除事件 |
| `/admin/events/merge` | POST | 合并事件 |
| `/admin/events/config` | GET/PUT | 聚类配置 |

#### 9.3 前端实现
新增事件管理页面：
- 事件列表（名称、文章数、热度）
- 事件详情（关联文章）
- 合并操作
- 聚类参数配置

---

### 模块 10: 主题管理 (Topic Management)

**优先级**: P2 - 后续实施
**预估工作量**: 中

#### 10.1 功能对应 defaults.yaml
```yaml
topic:
  enabled: false
  discovery:
    min_frequency: 5
    lookback_days: 14
  radar:
    snapshot_interval: "daily"
```

#### 10.2 新增 API 端点
| 端点 | 方法 | 功能 |
|------|------|------|
| `/admin/topics` | GET | 主题列表 |
| `/admin/topics` | POST | 创建主题 |
| `/admin/topics/{id}` | PUT | 编辑主题 |
| `/admin/topics/{id}` | DELETE | 删除主题 |
| `/admin/topics/{id}/snapshots` | GET | 主题趋势 |
| `/admin/topics/config` | GET/PUT | 发现配置 |

#### 10.3 前端实现
新增主题管理页面：
- 主题列表（手动/自动发现）
- 关键词编辑
- 趋势图表
- 发现参数配置

---

### 模块 11: 报告管理 (Report Management)

**优先级**: P2 - 后续实施
**预估工作量**: 中

#### 11.1 功能对应 defaults.yaml
```yaml
report:
  enabled: false
```

#### 11.2 新增 API 端点
| 端点 | 方法 | 功能 |
|------|------|------|
| `/admin/reports` | GET | 报告列表 |
| `/admin/reports/generate` | POST | 生成报告 |
| `/admin/reports/{id}` | GET | 报告详情 |
| `/admin/reports/{id}` | DELETE | 删除报告 |
| `/admin/reports/config` | GET/PUT | 报告配置 |

#### 11.3 前端实现
新增报告管理页面：
- 报告列表
- 手动生成表单
- 报告预览/下载
- 自动生成配置

---

### 模块 12: 微信通知管理 (WeChat Notification)

**优先级**: P3 - 低优先级
**预估工作量**: 小

#### 12.1 功能对应 defaults.yaml
```yaml
notification:
  wechat:
    enabled: false
    appid: ""
    appsecret: ""
```

#### 12.2 新增配置项
```python
DEFAULT_CONFIGS = {
    "notification.wechat_enabled": ("false", "Enable WeChat notifications"),
    "notification.wechat_appid": ("", "WeChat AppID"),
    "notification.wechat_appsecret": ("", "WeChat AppSecret"),
}
```

#### 12.3 前端实现
在系统配置或通知配置页面添加微信通知设置

---

### 模块 13: 视频生成管理 (Video Generation)

**优先级**: P3 - 低优先级
**预估工作量**: 小

#### 13.1 功能对应 defaults.yaml
```yaml
video:
  enabled: false
  tts:
    provider: "edge-tts"
    voice: "yunxi"
```

#### 13.2 新增配置项
```python
DEFAULT_CONFIGS = {
    "video.enabled": ("false", "Enable video generation"),
    "video.tts_provider": ("edge-tts", "TTS provider"),
    "video.tts_voice": ("yunxi", "TTS voice"),
    "video.output_dir": ("./videos", "Video output directory"),
}
```

---

## 四、实施时间线

### 第一阶段：核心修复 (Week 1)

| 序号 | 任务 | 优先级 | 预估时间 |
|------|------|--------|----------|
| 1.1 | 仪表盘订阅统计 | P0 | 0.5h |
| 1.2 | 系统配置前端连接 | P0 | 2h |
| 1.3 | 邮件配置模型+API | P0 | 3h |
| 1.4 | 邮件配置前端 | P0 | 2h |
| 1.5 | 功能开关 UI 完善 | P0 | 1h |

### 第二阶段：运维功能 (Week 2)

| 序号 | 任务 | 优先级 | 预估时间 |
|------|------|--------|----------|
| 2.1 | 爬取任务触发实现 | P1 | 2h |
| 2.2 | 备份逻辑实现 | P1 | 3h |
| 2.3 | 备份恢复功能 | P1 | 2h |
| 2.4 | 审计日志 API | P1 | 1.5h |
| 2.5 | 审计日志前端 | P1 | 2h |

### 第三阶段：AI/嵌入功能 (Week 3)

| 序号 | 任务 | 优先级 | 预估时间 |
|------|------|--------|----------|
| 3.1 | AI 配置 API | P2 | 2h |
| 3.2 | AI 配置前端 | P2 | 2h |
| 3.3 | 嵌入统计 API | P2 | 1.5h |
| 3.4 | 嵌入管理前端 | P2 | 2h |

### 第四阶段：高级功能 (Week 4)

| 序号 | 任务 | 优先级 | 预估时间 |
|------|------|--------|----------|
| 4.1 | 事件管理 API | P2 | 2h |
| 4.2 | 事件管理前端 | P2 | 2.5h |
| 4.3 | 主题管理 API | P2 | 2h |
| 4.4 | 主题管理前端 | P2 | 2.5h |
| 4.5 | 报告管理 API | P2 | 2h |
| 4.6 | 报告管理前端 | P2 | 2h |

### 第五阶段：辅助功能 (Week 5)

| 序号 | 任务 | 优先级 | 预估时间 |
|------|------|--------|----------|
| 5.1 | 微信通知配置 | P3 | 1h |
| 5.2 | 视频生成配置 | P3 | 1h |
| 5.3 | 综合测试 | P3 | 3h |
| 5.4 | 文档更新 | P3 | 2h |

---

## 五、数据库迁移

### 新增表

```sql
-- 邮件配置表
CREATE TABLE email_configs (
    id INT PRIMARY KEY AUTO_INCREMENT,
    -- SMTP
    smtp_host VARCHAR(255) DEFAULT '',
    smtp_port INT DEFAULT 587,
    smtp_user VARCHAR(255) DEFAULT '',
    smtp_password VARCHAR(255) DEFAULT '',
    smtp_use_tls BOOLEAN DEFAULT TRUE,
    -- SendGrid
    sendgrid_api_key VARCHAR(255) DEFAULT '',
    -- Mailgun
    mailgun_api_key VARCHAR(255) DEFAULT '',
    mailgun_domain VARCHAR(255) DEFAULT '',
    -- Brevo
    brevo_api_key VARCHAR(255) DEFAULT '',
    brevo_from_name VARCHAR(100) DEFAULT 'ResearchPulse',
    -- 推送设置
    email_enabled BOOLEAN DEFAULT FALSE,
    active_backend VARCHAR(20) DEFAULT 'smtp',
    push_frequency VARCHAR(20) DEFAULT 'daily',
    push_time VARCHAR(10) DEFAULT '09:00',
    max_articles_per_email INT DEFAULT 20,
    -- 时间戳
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- 插入默认配置
INSERT INTO email_configs (id) VALUES (1);
```

### 配置种子数据

新增到 `common/feature_config.py` 的 `DEFAULT_CONFIGS` 字典中。

---

## 六、API 路由汇总

```
/api/v1/admin/
├── stats                          # 仪表盘统计
├── users/                         # 用户管理
├── sources/                       # 数据源管理
│   ├── arxiv/
│   ├── rss/
│   ├── wechat/
│   └── stats
├── config/                        # 系统配置
│   ├── GET /                      # 列表
│   ├── PUT /{key}                 # 更新
│   ├── GET /groups                # 分组
│   └── PUT /batch                 # 批量更新
├── features/                      # 功能开关
│   ├── GET /                      # 列表
│   └── PUT /{key}                 # 切换
├── scheduler/                     # 调度器
│   ├── GET /jobs                  # 任务列表
│   ├── PUT /jobs/{id}             # 修改任务
│   └── POST /jobs/{id}/trigger    # 触发任务
├── crawler/                       # 爬虫管理
│   ├── GET /status                # 状态
│   └── POST /trigger              # 触发爬取
├── email/                         # 邮件配置 [新增]
│   ├── GET /config
│   ├── PUT /config
│   └── POST /test
├── backups/                       # 备份管理
│   ├── GET /                      # 列表
│   ├── POST /create               # 创建
│   ├── GET /{id}/download         # 下载 [新增]
│   ├── POST /{id}/restore         # 恢复 [新增]
│   └── DELETE /{id}               # 删除 [新增]
├── audit-logs/                    # 审计日志 [新增]
│   └── GET /
├── ai/                            # AI 配置 [新增]
│   ├── GET /config
│   ├── PUT /config
│   └── POST /test
├── embeddings/                    # 嵌入管理 [新增]
│   ├── GET /stats
│   ├── GET /missing
│   └── POST /recompute
├── events/                        # 事件管理 [新增]
│   ├── GET /
│   ├── PUT /{id}
│   ├── DELETE /{id}
│   └── POST /merge
├── topics/                        # 主题管理 [新增]
│   ├── GET /
│   ├── POST /
│   ├── PUT /{id}
│   ├── DELETE /{id}
│   └── GET /{id}/snapshots
├── reports/                       # 报告管理 [新增]
│   ├── GET /
│   ├── POST /generate
│   ├── GET /{id}
│   └── DELETE /{id}
└── notifications/                 # 通知配置 [新增]
    └── GET/PUT /config
```

---

## 七、前端页面结构

```
admin.html
├── 仪表盘 (Dashboard)
│   ├── 统计卡片（用户/文章/源/订阅/今日）
│   └── 功能状态概览
├── 数据源管理 (Sources)
│   ├── ArXiv 分类
│   ├── RSS 源
│   ├── 微信公众号
│   └── 待审批 RSS
├── 爬取管理 (Crawler) [增强]
│   ├── 全局设置
│   ├── 任务状态
│   └── 手动触发
├── AI 配置 (AI) [新增]
│   ├── Provider 设置
│   ├── 模型选择
│   └── 规则优化
├── 向量嵌入 (Embedding) [新增]
│   ├── 统计概览
│   ├── Milvus 配置
│   └── 批量操作
├── 事件管理 (Events) [新增]
│   ├── 事件列表
│   └── 聚类配置
├── 主题管理 (Topics) [新增]
│   ├── 主题列表
│   └── 发现配置
├── 用户管理 (Users)
├── 邮件配置 (Email) [完善]
│   ├── SMTP 设置
│   ├── SendGrid/Mailgun/Brevo
│   └── 推送设置
├── 备份管理 (Backups) [完善]
│   ├── 备份列表
│   ├── 创建备份
│   └── 恢复功能
├── 审计日志 (Audit Logs) [新增]
│   ├── 日志列表
│   └── 筛选导出
├── 报告管理 (Reports) [新增]
│   ├── 报告列表
│   └── 生成报告
├── 功能开关 (Features)
│   └── 开关列表
├── 调度器 (Scheduler)
│   └── 任务管理
└── 系统配置 (Config)
    └── 配置分组
```

---

## 八、文件变更清单

### 新建文件
| 文件 | 用途 |
|------|------|
| `apps/admin/backup.py` | 备份服务逻辑 |
| `apps/admin/models.py` | 管理后台专用模型（EmailConfig 等） |
| `migrations/versions/xxx_add_email_config.py` | 数据库迁移脚本 |

### 修改文件
| 文件 | 修改内容 |
|------|----------|
| `apps/admin/api.py` | 新增 API 端点 |
| `apps/ui/templates/admin.html` | 新增管理页面 |
| `common/feature_config.py` | 扩展默认配置 |
| `apps/crawler/models/config.py` | 可选：添加 EmailConfig 模型 |

---

## 九、验收标准

### 功能验收
- [ ] 仪表盘显示订阅统计
- [ ] 系统配置可正常保存和加载
- [ ] 邮件配置可设置并测试
- [ ] 爬取任务可手动触发
- [ ] 备份可创建、下载、恢复
- [ ] 审计日志可查询
- [ ] AI 配置可设置
- [ ] 嵌入状态可查看
- [ ] 事件可管理
- [ ] 主题可管理
- [ ] 报告可生成
- [ ] 所有功能开关可正常切换

### 测试验收
- [ ] 所有 API 端点有单元测试
- [ ] 前端交互有集成测试
- [ ] 敏感数据已脱敏显示

---

请确认此规划后，我将按照优先级顺序开始实施。可以从第一阶段开始吗？
