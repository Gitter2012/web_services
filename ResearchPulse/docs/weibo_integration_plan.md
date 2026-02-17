# 微博热点抓取集成实施计划

## 项目概述

在 ResearchPulse 中集成微博热点抓取功能，支持多榜单抓取（热搜榜、要闻榜、文娱榜、体育榜、游戏榜）。

---

## 实施进度

### 已完成

- [x] **Phase 1: 基础设施搭建**
  - [x] 添加 `WeiboHotSearch` 数据模型 (`apps/crawler/models/source.py`)
  - [x] 添加数据库表结构 (`sql/init.sql`)
  - [x] 创建 Alembic 迁移脚本 (`alembic/versions/20260217_1650_weibo001_add_weibo_hot_search_table.py`)
  - [x] 添加 weibo 配置 (`config/defaults.yaml`)
  - [x] 添加 WeiboSettings (`settings.py`)

- [x] **Phase 2: 爬虫核心实现**
  - [x] 创建微博爬虫目录 (`apps/crawler/weibo/`)
  - [x] 实现 `WeiboCrawler` 类
  - [x] 测试接口可用性
  - [x] 数据解析和存储

- [x] **Phase 3: 调度集成**
  - [x] 集成到 `crawl_job.py`
  - [x] 支持多榜单遍历

### 待完成

- [ ] **Phase 4: 测试与优化**
  - [ ] 编写单元测试
  - [ ] 集成测试
  - [ ] 反爬策略优化（根据实际运行情况调整）

---

## Cookie 配置说明

### 为什么需要 Cookie

微博的以下榜单需要登录认证才能访问：
- 要闻榜 (socialevent)
- 文娱榜 (entrank)
- 体育榜 (sport)
- 游戏榜 (game)

### 如何获取微博 Cookie

1. **登录微博**
   - 使用浏览器访问 https://weibo.com
   - 登录你的微博账号

2. **获取 Cookie**
   - 打开浏览器开发者工具（F12 或 右键 -> 检查）
   - 切换到 "网络" (Network) 标签
   - 刷新页面或访问任意微博 API
   - 找到任意请求，查看请求头 (Request Headers)
   - 找到 `Cookie` 字段，复制完整的值

3. **关键 Cookie 字段**
   - 最重要的是 `SUB` 和 `SUBP` 字段
   - 例如: `SUB=_2A25K...; SUBP=003...; ...`

### 配置方式

**方式 1: 环境变量**
```bash
export WEIBO_COOKIE="SUB=xxx; SUBP=xxx; ..."
```

**方式 2: .env 文件**
```
WEIBO_COOKIE="SUB=xxx; SUBP=xxx; ..."
```

**方式 3: config/defaults.yaml**
```yaml
crawler:
  weibo:
    cookie: "SUB=xxx; SUBP=xxx; ..."
```

### 注意事项

1. **Cookie 有效期**: 微博 Cookie 通常有效期为几天到几周，过期后需要重新获取
2. **账号安全**: 不要将 Cookie 提交到代码仓库，使用环境变量或 .env 文件
3. **请求频率**: 配置了 Cookie 后，仍然需要控制请求频率，避免被封禁

---

## 接口调研结果

### 可用接口

| 接口 | 状态 | 说明 |
|-----|------|------|
| `https://weibo.com/ajax/side/hotSearch` | ✅ 可用 | 热搜榜数据，返回 `realtime` 字段 |
| `https://s.weibo.com/top/summary?cate=*` | ❌ 需登录 | 重定向到登录页面 |
| `https://weibo.com/ajax/statuses/hotBand` | ❌ 需登录 | 返回登录重定向 |

### 当前支持榜单

| 榜单类型 | 状态 | 说明 |
|---------|------|------|
| realtimehot (热搜榜) | ✅ 支持 | 公开接口，无需 Cookie，默认启用 |
| socialevent (要闻榜) | ✅ 支持 | 需要 Cookie 认证，默认禁用 |
| entrank (文娱榜) | ✅ 支持 | 需要 Cookie 认证，默认禁用 |
| sport (体育榜) | ✅ 支持 | 需要 Cookie 认证，默认禁用 |
| game (游戏榜) | ✅ 支持 | 需要 Cookie 认证，默认禁用 |

### 默认配置

- **热搜榜**: 默认启用，无需配置即可使用
- **其他榜单**: 默认禁用，需要配置 Cookie 后手动启用
- **Cookie**: 默认为空，不会自动使用任何认证信息

---

## 一、数据源分析

### 1.1 微博接口

| 榜单类型 | 接口路径 | 说明 |
|---------|---------|------|
| 热搜榜 | `realtimehot` | 实时热搜 |
| 要闻榜 | `socialevent` | 社会要闻 |
| 文娱榜 | `entrank` | 娱乐热点 |
| 体育榜 | `sport` | 体育热点 |
| 游戏榜 | `game` | 游戏热点 |

### 1.2 可用接口

**方案A: 热搜榜接口（推荐优先尝试）**
```
GET https://weibo.com/ajax/side/hotSearch
```

**方案B: 榜单汇总页面**
```
GET https://s.weibo.com/top/summary
```

**方案C: 多榜单接口（需要确定具体URL格式）**
- 可能需要逆向分析微博移动端或其他端点

---

## 二、技术架构设计

### 2.1 数据模型

**WeiboHotSearch Source Model** (`source.py`)
```python
class WeiboHotSearch(Base, TimestampMixin):
    __tablename__ = "weibo_hot_searches"

    id: Mapped[int] = mapped_column(primary_key=True)
    board_type: Mapped[str]  # realtimehot, socialevent, entrank, sport, game
    board_name: Mapped[str]  # 热搜榜, 要闻榜, 文娱榜, 体育榜, 游戏榜
    is_active: Mapped[bool] = mapped_column(default=True)
    last_fetched_at: Mapped[datetime | None]
    error_count: Mapped[int] = mapped_column(default=0)
```

**Article 扩展字段**（可选）
- 利用现有 Article 模型的 `metadata` JSON 字段存储微博特有数据：
  - `hot_rank`: 热度排名
  - `hot_value`: 热度值
  - `label`: 标签（新、热、沸等）
  - `emoji`: 表情描述

### 2.2 爬虫实现

**WeiboCrawler** (`apps/crawler/weibo/crawler.py`)
```python
class WeiboCrawler(BaseCrawler):
    source_type = "weibo"
    source_id: str  # board_type (realtimehot, socialevent, etc.)

    async def fetch(self) -> dict:
        # 调用微博接口，处理反爬
        pass

    async def parse(self, raw_data: dict) -> List[Dict]:
        # 解析热搜数据，转换为 Article 格式
        pass
```

---

## 三、实施步骤

### Phase 1: 基础设施搭建（预计工作量：基础）

#### 任务 1.1: 数据模型定义
- [ ] 在 `source.py` 中添加 `WeiboHotSearch` 模型
- [ ] 在 `sql/init.sql` 中添加表结构
- [ ] 创建 Alembic 迁移脚本

#### 任务 1.2: 配置系统
- [ ] 在 `config/defaults.yaml` 添加 weibo 配置节
  ```yaml
  crawler:
    weibo:
      timeout: 30
      delay_base: 5.0  # 微博反爬严格，增加延迟
      max_retry: 3
      boards:
        - type: realtimehot
          name: 热搜榜
          enabled: true
        - type: socialevent
          name: 要闻榜
          enabled: true
        - type: entrank
          name: 文娱榜
          enabled: true
        - type: sport
          name: 体育榜
          enabled: true
        - type: game
          name: 游戏榜
          enabled: true
  ```
- [ ] 在 `settings.py` 添加 WeiboSettings 类

### Phase 2: 爬虫核心实现（预计工作量：核心）

#### 任务 2.1: HTTP 客户端适配
- [ ] 分析微博接口的请求头要求
- [ ] 可能需要的特殊处理：
  - Cookie 认证（游客Cookie或登录Cookie）
  - 特殊的 Referer
  - X-Requested-With 头

#### 任务 2.2: 爬虫类实现
- [ ] 创建 `apps/crawler/weibo/` 目录
- [ ] 实现 `WeiboCrawler` 类
  - [ ] `fetch()`: 调用接口获取数据
  - [ ] `parse()`: 解析 JSON 响应
  - [ ] 错误处理和重试逻辑
- [ ] 实现多榜单支持

#### 任务 2.3: 数据解析
- [ ] 解析热搜数据结构
- [ ] 提取字段：
  - 标题、链接、热度值、排名、标签
- [ ] 数据标准化为 Article 格式

### Phase 3: 调度集成（预计工作量：集成）

#### 任务 3.1: 调度任务集成
- [ ] 在 `crawl_job.py` 中添加微博爬虫调用
- [ ] 添加榜单遍历逻辑
- [ ] 错误隔离（单个榜单失败不影响其他）

#### 任务 3.2: 定时任务配置
- [ ] 配置热搜抓取频率（建议 5-10 分钟）
- [ ] 考虑微博热搜变化频率

### Phase 4: 测试与优化（预计工作量：保障）

#### 任务 4.1: 单元测试
- [ ] 编写爬虫测试用例
- [ ] Mock 微博接口响应
- [ ] 测试异常处理

#### 任务 4.2: 集成测试
- [ ] 测试完整抓取流程
- [ ] 测试数据存储
- [ ] 测试去重逻辑

#### 任务 4.3: 反爬策略优化
- [ ] 监控请求成功率
- [ ] 根据实际情况调整：
  - 延迟时间
  - User-Agent 轮换
  - IP 轮换（如需要）
  - Cookie 池（如需要）

---

## 四、关键技术要点

### 4.1 反爬应对策略

| 策略 | 实现方式 | 优先级 |
|-----|---------|-------|
| User-Agent 轮换 | 已有实现，复用 `common/http.py` | 高 |
| 请求延迟 | 已有实现，调整 delay_base 为 5-10秒 | 高 |
| Referer 伪装 | 添加 `https://weibo.com` | 高 |
| Cookie 处理 | 实现游客 Cookie 获取或配置注入 | 中 |
| IP 轮换 | 如频繁被封，考虑代理池 | 低 |

### 4.2 数据存储策略

```
Article 表复用：
├── source_type = "weibo"
├── source_id = "realtimehot" / "socialevent" / ...
├── external_id = 微博话题ID 或 URL hash
├── title = 热搜标题
├── url = 微博搜索链接
├── summary = 热度描述（如有）
├── metadata = {
│       "hot_rank": 1,
│       "hot_value": 1234567,
│       "label": "沸",
│       "emoji": "🔥"
│   }
└── publish_time = 抓取时间
```

### 4.3 去重策略

- 使用 `external_id`：话题ID 或 URL 的 MD5
- 同一话题在多个榜单出现时，分别存储（不同 source_id）

---

## 五、文件变更清单

| 文件 | 操作 | 说明 |
|-----|------|------|
| `apps/crawler/models/source.py` | 修改 | 添加 WeiboHotSearch 模型 |
| `apps/crawler/weibo/__init__.py` | 新建 | 模块初始化 |
| `apps/crawler/weibo/crawler.py` | 新建 | 微博爬虫实现 |
| `config/defaults.yaml` | 修改 | 添加 weibo 配置 |
| `settings.py` | 修改 | 添加 WeiboSettings |
| `apps/scheduler/jobs/crawl_job.py` | 修改 | 集成微博爬虫 |
| `sql/init.sql` | 修改 | 添加 weibo_hot_searches 表 |
| `alembic/versions/xxx_add_weibo.py` | 新建 | 数据库迁移 |

---

## 六、风险与应对

| 风险 | 影响 | 应对措施 |
|-----|------|---------|
| 接口变更 | 中 | 监控解析异常，及时更新 |
| 反爬加强 | 高 | 增加延迟，实现 Cookie 池 |
| 无游客接口 | 高 | 需要配置登录 Cookie |
| 数据量过大 | 低 | 热榜数据量小，无影响 |

---

## 七、后续扩展

1. **热搜趋势分析**: 利用 TopicSnapshot 追踪热搜变化趋势
2. **热度历史**: 记录热度值变化曲线
3. **关键词提取**: 对热搜标题进行 NLP 分析
4. **多平台对比**: 对比微博、知乎、抖音等平台热搜
