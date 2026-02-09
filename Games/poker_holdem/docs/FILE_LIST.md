# 项目文件清单

## 核心代码文件 (4)

### poker_game.py (442行)
**功能**: 游戏核心逻辑模块
- Card类 - 扑克牌
- Deck类 - 牌堆
- Player类 - 玩家
- HandEvaluator类 - 牌型评估器
- PokerGame类 - 游戏主控制器

### ai_player.py (370行)
**功能**: AI玩家模块
- AIPlayer类 - AI玩家（继承Player）
- AIPlayerFactory类 - AI玩家工厂
- 4种AI性格实现
- 起手牌评估算法
- AI决策逻辑

### main.py (240行)
**功能**: FastAPI后端服务
- FastAPI应用初始化
- WebSocket连接管理
- AI自动行动处理
- HTTP API端点
- 游戏状态广播

### index.html (650行)
**功能**: 前端游戏界面
- 登录界面
- 游戏桌面
- 玩家信息卡片
- 操作按钮
- WebSocket客户端
- 游戏状态显示

## 配置文件 (4)

### requirements.txt
Python依赖包列表

### Dockerfile
Docker镜像构建配置

### docker-compose.yml
Docker Compose编排配置

### nginx.conf
Nginx反向代理配置（支持WebSocket）

## 脚本文件 (2)

### start.sh
快速启动脚本（本地开发）

### deploy.sh
云服务器自动部署脚本

## 测试文件 (4)

### test_game.py
游戏逻辑单元测试

### test_ai.py
AI玩家功能测试

### test_websocket.py
WebSocket连接和通信测试

### test_report.py
综合测试报告生成器

## 文档文件 (6)

### README.md
项目说明文档
- 功能特性介绍
- 快速开始指南
- API文档
- 技术栈说明

### DEPLOYMENT.md
云服务器部署指南
- Docker部署方式
- 传统部署方式
- HTTPS配置
- 性能优化
- 常见问题解答

### AI_GUIDE.md
AI玩家功能说明
- AI特性介绍
- 四种性格详解
- 使用方法
- 决策逻辑
- 对抗策略

### TEST_REPORT.md
测试报告
- 测试概览
- Bug修复记录
- 功能完整性检查
- 测试结论

### PROJECT_SUMMARY.md
项目完成总结
- 已完成功能
- 项目统计
- 核心特性
- 性能指标
- 未来扩展

### FILE_LIST.md
本文件 - 项目文件清单

## 统计信息

### 代码统计
- 核心代码: 1,702 行
- 测试代码: 350+ 行
- 前端代码: 650 行
- 总计: 2,700+ 行

### 文件统计
- 代码文件: 4
- 配置文件: 4
- 脚本文件: 2
- 测试文件: 4
- 文档文件: 6
- 总计: 20 个文件

### 文档统计
- README.md: 6.1 KB
- DEPLOYMENT.md: 7.8 KB
- AI_GUIDE.md: 8.5 KB
- TEST_REPORT.md: 4.5 KB
- PROJECT_SUMMARY.md: 11.2 KB
- 总计: 38.1 KB

## 文件依赖关系

```
main.py
├── poker_game.py (游戏逻辑)
├── ai_player.py (AI玩家)
└── index.html (前端界面)

ai_player.py
└── poker_game.py (继承Player类)

test_game.py
└── poker_game.py

test_ai.py
├── poker_game.py
└── ai_player.py

test_websocket.py
└── main.py (需要服务器运行)

test_report.py
├── test_game.py
└── test_websocket.py
```

## 运行环境要求

### Python环境
- Python 3.10+
- pip

### Python包
- fastapi==0.104.1
- uvicorn[standard]==0.24.0
- websockets==12.0
- python-multipart==0.0.6

### 部署环境（可选）
- Docker
- Docker Compose
- Nginx
- Ubuntu 20.04+

## 快速导航

| 需求 | 文件 |
|------|------|
| 快速开始 | README.md, start.sh |
| 游戏逻辑 | poker_game.py |
| AI功能 | ai_player.py, AI_GUIDE.md |
| 后端服务 | main.py |
| 前端界面 | index.html |
| 部署上线 | DEPLOYMENT.md, deploy.sh |
| 测试验证 | test_*.py, TEST_REPORT.md |
| 完整总结 | PROJECT_SUMMARY.md |

## 许可证

MIT License

---

**项目完整，所有文件就绪！** ✅
