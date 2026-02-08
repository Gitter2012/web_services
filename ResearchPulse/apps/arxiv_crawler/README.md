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

### 配置来源（优先级由高到低）
1. **环境变量**：运行时覆盖
2. **`.env` 文件**：敏感信息（密码、凭证）
3. **`/config/defaults.yaml` apps.arxiv_crawler**：项目级覆盖
4. **`/apps/arxiv_crawler/config/defaults.yaml`**：应用默认值
5. **Python 代码默认值**：兜底

### 配置项
| 配置 | 默认 | 说明 |
|------|------|------|
| `ARXIV_CATEGORIES` | cs.LG,cs.CV | 订阅的 arXiv 分类 |
| `ARXIV_MAX_RESULTS` | 50 | 每分类最大抓取量 |
| `ARXIV_MIN_RESULTS` | 10 | 每分类最小抓取量（触发回溯阈值） |
| `ARXIV_FALLBACK_DAYS` | 7 | 最大回溯天数（含当日共8天窗口） |
| `ARXIV_SCHEDULE_HOUR` | 0 | 定时抓取小时 |
| `ARXIV_SCHEDULE_MINUTE` | 0 | 定时抓取分钟 |
| `ARXIV_SCHEDULE_TIMEZONE` | UTC | 调度时区 |
| `ARXIV_DATE_WINDOW_DAYS` | 2 | 当日窗口天数（含当天与前 N-1 天） |
| `ARXIV_DATE_WINDOW_TIMEZONE` | Asia/Shanghai | 当日窗口时区基准 |
| `ARXIV_EMAIL_ENABLED` | true | 是否发送邮件 |
| `ARXIV_ABSTRACT_MAX_LEN` | 800 | 摘要最大长度 |
| `ARXIV_TRANSLATION_BASE_URL` | https://hjfy.top/arxiv/ | **固定值，不可修改** |
| `EMAIL_FROM` | your-email@example.com | 发件人地址（默认值在 YAML） |
| `EMAIL_TO` | recipient1@example.com | 收件人地址（默认值在 YAML） |
| `SMTP_PROFILES` | 1,2 | SMTP 配置 ID（默认值在 YAML） |

### SMTP 配置（敏感信息在 .env）
| 配置 | 说明 |
|------|------|
| `SMTP_PASSWORD` | SMTP 密码（敏感） |
| `SMTP1_PASSWORD` | Profile 1 密码（敏感） |
| `SMTP2_PASSWORD` | Profile 2 密码（敏感） |

**非敏感 SMTP 配置（host/user/port/tls 等）已移至 YAML：**
- `/config/defaults.yaml` → `apps.arxiv_crawler.smtp`
- `/apps/arxiv_crawler/config/defaults.yaml`

### 修改配置
```bash
# 通过环境变量覆盖
ARXIV_CATEGORIES=cs.AI,cs.NE uvicorn main:app

# 或编辑应用默认值
vi apps/arxiv_crawler/config/defaults.yaml

# 或编辑项目级覆盖
vi /config/defaults.yaml
```

### 默认值文件
应用默认值位于 `apps/arxiv_crawler/config/defaults.yaml`，包含：
- `arxiv.*`：arXiv API 相关设置
- `schedule.*`：定时任务设置
- `email.*`：邮件开关
- `smtp.*`：SMTP 非敏感参数（端口、超时等）
