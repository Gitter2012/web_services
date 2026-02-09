# 行动超时功能文档

## 更新日期: 2026-02-03

---

## 概述

实现了玩家行动超时功能，包括可配置的超时时间、视觉倒计时进度条、自动弃牌机制，以及在设置面板中的配置选项。

---

## 功能特性

### 1. 可配置超时时间
- **默认值**: 30秒
- **范围**: 10-120秒
- **步进**: 5秒
- **持久化**: 自动保存到localStorage

### 2. 视觉倒计时
- **进度条**: 颜色渐变（绿→黄→红）
- **倒计时文本**: 显示剩余秒数
- **警告动画**: 最后5秒闪烁提示
- **位置**: 当前回合玩家卡片下方

### 3. 自动弃牌
- **超时处理**: 时间到自动执行弃牌操作
- **提示消息**: 显示"操作超时，自动弃牌"
- **音效提示**: 播放通知音效

---

## 用户界面

### 设置面板

**位置**: 设置面板 → 行动超时

```
┌─────────────────────────────────┐
│ ⏰ 行动超时                      │
│ 每轮行动的时间限制，超时将自动弃牌 │
├─────────────────────────────────┤
│ 超时时间              30秒      │
├─────────────────────────────────┤
│ [========滑块========]          │
│ 10秒      60秒      120秒       │
└─────────────────────────────────┘
```

**配置项**:
- 滑块控件: 10-120秒可调
- 实时更新: 拖动即时显示
- 自动保存: 修改后立即保存

### 倒计时显示

**玩家卡片下方**:

```
┌──────────────────┐
│  👤 玩家名称      │
│  💰 筹码: 1000   │
│  🎯 下注: 20     │
│  [扑克牌显示]     │
├──────────────────┤
│ [■■■■■░░░] 15s │ ← 倒计时进度条
└──────────────────┘
```

**进度条特性**:
- 宽度: 100%（随时间递减）
- 颜色: 渐变（绿→黄→红）
- 文本: 剩余秒数（如"15s"）
- 警告: <5秒时闪烁

---

## 技术实现

### 前端实现

#### 1. 设置存储

**位置**: `index.html:1409-1420`

```javascript
const gameSettings = {
    soundEnabled: localStorage.getItem('soundEnabled') !== 'false',
    volume: parseInt(localStorage.getItem('volume') || '100'),
    animationEnabled: localStorage.getItem('animationEnabled') !== 'false',
    autoStartEnabled: localStorage.getItem('autoStartEnabled') !== 'false',
    theme: localStorage.getItem('theme') || 'default',
    turnTimeout: parseInt(localStorage.getItem('turnTimeout') || '30') // 行动超时
};
```

#### 2. 全局变量

**位置**: `index.html:1402-1408`

```javascript
let turnTimer = null; // 行动计时器
let turnTimeRemaining = 0; // 剩余时间（秒）
```

#### 3. 倒计时CSS

**位置**: `index.html:220-255`

```css
/* 行动倒计时 */
.turn-timer {
    position: absolute;
    bottom: -25px;
    left: 0;
    right: 0;
    height: 20px;
    background: rgba(0,0,0,0.7);
    border-radius: 10px;
    overflow: hidden;
    border: 1px solid rgba(255,255,255,0.3);
}

.turn-timer-bar {
    height: 100%;
    background: linear-gradient(90deg, #4CAF50, #FFC107, #f44336);
    transition: width 0.3s linear;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 11px;
    font-weight: bold;
    color: white;
    text-shadow: 0 1px 2px rgba(0,0,0,0.8);
}

.turn-timer-bar.warning {
    animation: timerWarning 0.5s ease-in-out infinite;
}

@keyframes timerWarning {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.7; }
}
```

#### 4. 核心函数

**启动倒计时** (`index.html:2748-2775`):

```javascript
function startTurnTimer() {
    stopTurnTimer(); // 先停止之前的计时器
    
    if (!currentGameState || !playerId) return;
    
    turnTimeRemaining = gameSettings.turnTimeout;
    
    const currentPlayer = currentGameState.players.find(
        p => p.id === currentGameState.current_player_id
    );
    if (!currentPlayer) return;
    
    updateTurnTimerDisplay();
    
    turnTimer = setInterval(() => {
        turnTimeRemaining--;
        
        if (turnTimeRemaining <= 0) {
            // 超时，自动弃牌
            stopTurnTimer();
            addMessage('操作超时，自动弃牌', 'error');
            soundEffects.play(() => soundEffects.notify());
            playerAction('fold');
        } else {
            updateTurnTimerDisplay();
        }
    }, 1000);
}
```

**停止倒计时** (`index.html:2777-2783`):

```javascript
function stopTurnTimer() {
    if (turnTimer) {
        clearInterval(turnTimer);
        turnTimer = null;
    }
    turnTimeRemaining = 0;
}
```

**更新倒计时显示** (`index.html:2785-2805`):

```javascript
function updateTurnTimerDisplay() {
    if (!currentGameState || !currentGameState.current_player_id) return;
    
    const timerBar = document.getElementById(
        `turn-timer-bar-${currentGameState.current_player_id}`
    );
    const timerText = document.getElementById(
        `turn-timer-text-${currentGameState.current_player_id}`
    );
    
    if (timerBar && timerText) {
        const percentage = (turnTimeRemaining / gameSettings.turnTimeout) * 100;
        timerBar.style.width = percentage + '%';
        timerText.textContent = turnTimeRemaining + 's';
        
        // 时间不足5秒时添加警告动画
        if (turnTimeRemaining <= 5) {
            timerBar.classList.add('warning');
        } else {
            timerBar.classList.remove('warning');
        }
    }
}
```

#### 5. 玩家卡片集成

**位置**: `index.html:2209-2219`

在当前回合玩家的卡片中添加倒计时HTML：

```javascript
// 如果是当前回合玩家，添加倒计时显示
if (player.id === currentPlayerId) {
    const timerHTML = `
        <div class="turn-timer" id="turn-timer-${player.id}">
            <div class="turn-timer-bar" id="turn-timer-bar-${player.id}">
                <span id="turn-timer-text-${player.id}">30</span>
            </div>
        </div>
    `;
    cardDiv.innerHTML += timerHTML;
}
```

#### 6. 游戏状态更新触发

**位置**: `index.html:2027-2037`

在`updateGameUI`中控制倒计时启动和停止：

```javascript
// 启动或停止倒计时
if (state.game_stage !== 'waiting' && state.game_stage !== 'showdown') {
    if (state.current_player_id === playerId) {
        // 轮到当前玩家，启动倒计时
        startTurnTimer();
    } else {
        // 不是当前玩家，停止倒计时
        stopTurnTimer();
    }
} else {
    stopTurnTimer();
}
```

---

## 使用流程

### 1. 配置超时时间

```
步骤：
1. 点击左上角 "⚙️ 设置" 按钮
2. 滚动到 "⏰ 行动超时" 设置
3. 拖动滑块选择超时时间（10-120秒）
4. 设置自动保存，关闭面板即可

推荐设置：
- 快节奏: 15-20秒
- 标准: 30秒（默认）
- 休闲: 60秒
- 新手: 90-120秒
```

### 2. 游戏中倒计时

```
轮到你行动时：
1. 玩家卡片下方出现进度条
2. 显示剩余秒数（如"30s"）
3. 进度条逐渐缩短，颜色变化
4. 剩余5秒时开始闪烁警告

超时处理：
1. 时间归零
2. 自动执行弃牌操作
3. 显示提示消息
4. 播放音效
5. 游戏继续下一位玩家
```

---

## 视觉设计

### 进度条颜色

进度条使用渐变色，直观显示时间紧迫程度：

```css
background: linear-gradient(90deg, #4CAF50, #FFC107, #f44336);
```

- **绿色区域** (#4CAF50): 时间充裕
- **黄色区域** (#FFC107): 时间减少
- **红色区域** (#f44336): 时间紧迫

### 警告动画

剩余时间 ≤ 5秒时触发：

```css
@keyframes timerWarning {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.7; }
}
```

效果：0.5秒间隔闪烁，吸引注意力

---

## 游戏体验

### 优势

1. **节奏控制**: 避免玩家过度思考，保持游戏节奏
2. **公平性**: 所有玩家时间限制一致
3. **可配置**: 适应不同玩家和场景需求
4. **视觉反馈**: 清晰的倒计时显示
5. **防挂机**: 自动处理超时，避免游戏卡住

### 策略建议

#### 针对不同超时设置

**短超时（10-20秒）**:
```
适合:
- 快节奏游戏
- 经验丰富玩家
- 短筹码比赛

策略:
- 快速决策
- 依靠直觉
- 简化思考
```

**标准超时（30秒）**:
```
适合:
- 常规游戏
- 大多数玩家
- 平衡节奏

策略:
- 充分思考
- 计算赔率
- 观察对手
```

**长超时（60-120秒）**:
```
适合:
- 新手学习
- 深筹码游戏
- 复杂决策

策略:
- 仔细分析
- 计算所有可能性
- 深度思考
```

---

## 测试场景

### 场景1: 正常操作

```
初始状态:
- 超时时间: 30秒
- 轮到玩家行动

预期行为:
✓ 进度条从100%开始
✓ 每秒递减约3.3%
✓ 文本显示 "30s" → "29s" → ...
✓ 玩家在超时前操作，倒计时停止
```

### 场景2: 超时弃牌

```
初始状态:
- 超时时间: 10秒
- 轮到玩家行动
- 玩家未操作

预期行为:
✓ 倒计时正常运行 10秒
✓ 剩余5秒开始闪烁
✓ 归零时自动弃牌
✓ 显示"操作超时，自动弃牌"
✓ 播放通知音效
```

### 场景3: 切换玩家

```
初始状态:
- 玩家A行动中，倒计时15秒
- 玩家A完成操作
- 轮到玩家B

预期行为:
✓ 玩家A的倒计时停止并消失
✓ 玩家B的倒计时出现并启动
✓ 从设置的超时时间开始
```

### 场景4: 修改设置

```
操作:
1. 进入设置，将超时从30秒改为60秒
2. 返回游戏
3. 开始新一轮

预期行为:
✓ 新的倒计时使用60秒
✓ 进度条递减速度变慢
✓ 设置保存到localStorage
```

---

## 已知限制

1. **仅前端实现**: 
   - 当前超时逻辑在前端执行
   - 需要后端同步验证以防作弊
   
2. **网络延迟**:
   - 不考虑网络延迟
   - 弱网环境可能影响公平性

3. **浏览器标签页不活跃**:
   - 某些浏览器在标签页不活跃时降低定时器频率
   - 可能导致计时不准确

---

## 未来优化

1. **后端同步**
   ```python
   # 后端记录行动开始时间
   # 验证操作是否在超时内
   # 服务器端强制超时处理
   ```

2. **时间银行（Time Bank）**
   ```
   每个玩家额外获得60-120秒"时间银行"
   可在关键决策时使用
   用完后恢复正常超时
   ```

3. **自适应超时**
   ```
   根据底池大小和游戏阶段调整超时
   - 大底池: +10秒
   - 河牌圈: +5秒
   - 全押决策: +15秒
   ```

4. **超时惩罚**
   ```
   多次超时的玩家:
   - 逐渐减少超时时间
   - 显示警告标记
   - 影响信誉评分
   ```

---

## 相关文件

### 前端
- `index.html`: 第1361-1377行（设置面板HTML）
- `index.html`: 第220-255行（倒计时CSS）
- `index.html`: 第1402-1408行（全局变量）
- `index.html`: 第1409-1420行（设置初始化）
- `index.html`: 第2748-2805行（倒计时函数）
- `index.html`: 第2209-2219行（玩家卡片集成）
- `index.html`: 第2027-2037行（触发逻辑）

---

## 配置参数

| 参数 | 默认值 | 最小值 | 最大值 | 单位 | 说明 |
|------|--------|--------|--------|------|------|
| turnTimeout | 30 | 10 | 120 | 秒 | 行动超时时间 |
| warningThreshold | 5 | - | - | 秒 | 警告阈值（固定） |
| updateInterval | 1 | - | - | 秒 | 更新频率（固定） |

---

**实现状态**: ✅ 前端完成  
**服务器地址**: http://localhost:8000  
**建议**: 后续添加后端验证以提升安全性
