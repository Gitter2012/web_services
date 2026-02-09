# 德州扑克网页游戏

一个基于 FastAPI 和 WebSocket 的实时德州扑克网页游戏，支持AI玩家。

## ✨ 功能特性

- 🎮 **完整的德州扑克规则** - 翻牌前、翻牌、转牌、河牌、摊牌
- 👥 **多人实时对战** - 支持2-8名玩家同时游戏
- 🤖 **智能AI玩家** - 4种性格类型的AI对手
- 🎯 **自动牌型判断** - 10种牌型自动识别和比较
- 💰 **筹码管理系统** - 完整的下注、跟注、加注逻辑
- 📱 **响应式设计** - 支持PC和移动端
- 🔄 **WebSocket实时通信** - 低延迟的游戏体验
- 🎨 **精美界面** - 现代化的游戏界面设计

## 🎲 游戏规则

- 每位玩家初始筹码：1000
- 小盲注：10
- 大盲注：20
- 支持的操作：弃牌、过牌、跟注、加注

## 🚀 快速开始

### 方式一：一键启动（推荐）

```bash
./start.sh
```

### 方式二：手动启动

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 启动服务器
python main.py

# 3. 浏览器访问
open http://localhost:8000
```

### 方式三：Docker部署

```bash
# 构建并启动
docker-compose up -d

# 查看日志
docker-compose logs -f
```

## 🤖 AI玩家

### AI性格类型

1. **紧凶型** (Tight-Aggressive)
   - 只玩好牌，但下注激进
   - 激进度: 0.8，紧度: 0.8
   - 适合打法：稳健且有攻击性

2. **松凶型** (Loose-Aggressive)
   - 玩很多牌，下注激进
   - 激进度: 0.9，紧度: 0.3
   - 适合打法：激进的诈唬高手

3. **被动型** (Passive)
   - 跟注为主，少加注
   - 激进度: 0.3，紧度: 0.6
   - 适合打法：保守谨慎

4. **平衡型** (Balanced)
   - 根据情况灵活调整
   - 激进度: 0.6，紧度: 0.5
   - 适合打法：全面平衡

### 使用AI玩家

1. **在游戏中添加**：点击"添加AI玩家"按钮
2. **通过API添加**：
```bash
curl -X POST http://localhost:8000/api/add_ai?count=3
```

## 📁 项目结构

```
poker/
├── main.py              # FastAPI 主程序（支持AI）
├── poker_game.py        # 游戏核心逻辑
├── ai_player.py         # AI玩家模块
├── index.html           # 前端界面
├── requirements.txt     # Python 依赖
├── Dockerfile           # Docker镜像配置
├── docker-compose.yml   # Docker Compose配置
├── nginx.conf           # Nginx配置文件
├── deploy.sh            # 云服务器部署脚本
├── start.sh             # 快速启动脚本
├── README.md            # 项目说明
├── DEPLOYMENT.md        # 部署指南
└── TEST_REPORT.md       # 测试报告
```

## 🛠 技术栈

- **后端**: Python 3.10 + FastAPI + WebSocket
- **前端**: HTML5 + CSS3 + JavaScript (原生)
- **通信**: WebSocket 实时双向通信
- **部署**: Docker + Docker Compose + Nginx

## 🎮 游戏流程

1. 输入昵称加入游戏
2. 可选：添加AI玩家凑人数
3. 等待至少2名玩家后点击"开始游戏"
4. 系统自动发牌并设置盲注
5. 按照顺序进行操作（弃牌/过牌/跟注/加注）
6. 经过翻牌前、翻牌、转牌、河牌四个阶段
7. 最后摊牌比较牌型大小，赢家获得底池

## 🃏 牌型等级（从小到大）

1. **高牌** (High Card) - 单张大牌
2. **一对** (Pair) - 两张相同点数
3. **两对** (Two Pair) - 两个对子
4. **三条** (Three of a Kind) - 三张相同点数
5. **顺子** (Straight) - 五张连续牌
6. **同花** (Flush) - 五张相同花色
7. **葫芦** (Full House) - 三条+一对
8. **四条** (Four of a Kind) - 四张相同点数
9. **同花顺** (Straight Flush) - 同花色顺子
10. **皇家同花顺** (Royal Flush) - 10-J-Q-K-A同花

## 🌐 云服务器部署

详细部署指南请查看 [DEPLOYMENT.md](DEPLOYMENT.md)

### 快速部署

```bash
# 1. 上传文件到服务器
scp -r . root@your-server-ip:/opt/poker-game/

# 2. SSH连接服务器
ssh root@your-server-ip

# 3. 运行部署脚本
cd /opt/poker-game
chmod +x deploy.sh
./deploy.sh
```

### 推荐配置

- **CPU**: 2核
- **内存**: 4GB
- **带宽**: 5Mbps
- **系统**: Ubuntu 20.04

## 📡 API文档

### HTTP API

- `GET /` - 游戏主页
- `GET /api/game_state` - 获取游戏状态
- `POST /api/reset_game` - 重置游戏
- `POST /api/add_ai?count=N` - 添加N个AI玩家

### WebSocket API

连接: `ws://localhost:8000/ws/{player_name}`

客户端消息：
```json
{
    "type": "start_game" | "action" | "add_ai" | "get_state",
    "action": "fold" | "check" | "call" | "raise",
    "amount": 0,
    "count": 1
}
```

服务端消息：
```json
{
    "type": "game_state" | "player_joined" | "player_left" | 
            "player_action" | "game_started" | "round_end" | 
            "error" | "info",
    "data": {...}
}
```

## 🧪 测试

```bash
# 运行游戏逻辑测试
python test_game.py

# 运行AI玩家测试
python test_ai.py

# 运行WebSocket测试（需要先启动服务器）
python main.py &
python test_websocket.py

# 生成综合测试报告
python test_report.py
```

测试结果详见 [TEST_REPORT.md](TEST_REPORT.md)

## 📊 性能指标

- WebSocket连接延迟: < 100ms
- 游戏状态查询: < 50ms
- 玩家行动处理: < 10ms
- AI决策时间: 1-2秒（模拟思考）
- 并发支持: 8个玩家同时在线

## 🔒 安全性

- 输入验证和清理
- WebSocket消息验证
- 防止SQL注入（如添加数据库）
- 推荐使用HTTPS和WSS
- 建议配置防火墙和fail2ban

## 🐛 已知问题

- 游戏状态存储在内存中，重启后丢失
- 目前仅支持单桌游戏
- AI决策相对简单，可进一步优化

## 🔮 未来改进

- [ ] 添加数据库持久化（PostgreSQL/MongoDB）
- [ ] 支持多桌游戏
- [ ] 添加聊天功能
- [ ] 添加游戏历史记录和回放
- [ ] 添加玩家统计和排行榜
- [ ] 优化AI算法（使用强化学习）
- [ ] 添加游戏音效和动画
- [ ] 支持锦标赛模式
- [ ] 添加观战功能
- [ ] 多语言支持

## 🤝 贡献

欢迎提交Issue和Pull Request！

## 📄 许可证

MIT License

## 👨‍💻 作者

CodeBuddy AI

## 🙏 致谢

感谢所有为这个项目提供建议和帮助的人！

---

**开始游戏，享受德州扑克的乐趣！** 🎉🃏♠️♥️♦️♣️
