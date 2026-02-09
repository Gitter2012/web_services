# 快捷加注按钮功能文档

## 更新日期: 2026-02-03

---

## 概述

添加了四个快捷加注按钮，方便玩家快速选择常用的加注金额，无需手动计算和输入。

---

## 功能说明

### 快捷按钮

| 按钮 | 功能 | 计算公式 | 说明 |
|------|------|---------|------|
| **最小** | 最小加注 | 跟注金额 + 最小加注增量 | 符合规则的最小加注额 |
| **半池** | 半个底池 | 跟注金额 + 0.5×底池 | 至少为最小加注 |
| **全池** | 全部底池 | 跟注金额 + 1×底池 | 至少为最小加注 |
| **All-In** | 全部筹码 | 玩家所有筹码 | 梭哈 |

### 使用场景

#### 1. 最小加注 (Min Raise)
```
场景: 试探性加注，保留筹码
示例:
- 大盲注: 20
- 底池: 50
- 需要跟注: 20
→ 最小加注 = 20 + 20 = 40

适用情况:
✓ 持有中等牌力
✓ 想赶走小牌
✓ 控制底池大小
```

#### 2. 半池加注 (Half Pot)
```
场景: 标准加注，保护好牌
示例:
- 底池: 100
- 需要跟注: 30
→ 半池加注 = 30 + 50 = 80

适用情况:
✓ 持有强牌，想要价值下注
✓ 半诈唬（Semi-bluff）
✓ 给对手错误的底池赔率
```

#### 3. 全池加注 (Full Pot)
```
场景: 强力加注，施加压力
示例:
- 底池: 200
- 需要跟注: 50
→ 全池加注 = 50 + 200 = 250

适用情况:
✓ 持有非常强的牌
✓ 诈唬（Bluff）
✓ 保护已经很大的底池
```

#### 4. All-In
```
场景: 梭哈，全部压上
示例:
- 我的筹码: 500
→ All-In = 500

适用情况:
✓ 坚果牌（Nuts）
✓ 短筹码策略
✓ 纯诈唬或价值最大化
```

---

## 技术实现

### HTML结构

**位置**: `index.html:1204-1208`

```html
<!-- 快捷加注按钮 -->
<div class="quick-raise-buttons">
    <button class="btn-quick-raise" onclick="quickRaise('min')" title="最小加注">最小</button>
    <button class="btn-quick-raise" onclick="quickRaise('half')" title="半个底池">半池</button>
    <button class="btn-quick-raise" onclick="quickRaise('pot')" title="全部底池">全池</button>
    <button class="btn-quick-raise btn-allin" onclick="quickRaise('allin')" title="All In">All-In</button>
</div>
```

### CSS样式

**位置**: `index.html:422-458`

```css
.quick-raise-buttons {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 5px;
    margin: 5px 0;
}

.btn-quick-raise {
    padding: 8px 5px;
    font-size: 12px;
    border: 2px solid #607D8B;
    border-radius: 6px;
    background: rgba(96, 125, 139, 0.2);
    color: #fff;
    cursor: pointer;
    transition: all 0.2s;
    font-weight: bold;
}

.btn-quick-raise:hover {
    background: #607D8B;
    transform: translateY(-2px);
    box-shadow: 0 4px 10px rgba(0,0,0,0.3);
}

.btn-quick-raise.btn-allin {
    border-color: #f44336;
    color: #f44336;
    background: rgba(244, 67, 54, 0.2);
}

.btn-quick-raise.btn-allin:hover {
    background: #f44336;
    color: white;
}
```

### JavaScript逻辑

**位置**: `index.html:2302-2360`

```javascript
function quickRaise(type) {
    if (!currentGameState || !playerId) {
        addMessage('游戏状态未加载', 'error');
        return;
    }
    
    const currentPlayer = currentGameState.players.find(p => p.id === playerId);
    if (!currentPlayer) {
        addMessage('未找到玩家信息', 'error');
        return;
    }
    
    const callAmount = currentGameState.current_bet - currentPlayer.bet;
    const pot = currentGameState.pot;
    const minRaiseIncrement = Math.max(
        currentGameState.min_raise || currentGameState.big_blind, 
        currentGameState.big_blind
    );
    let raiseAmount = 0;
    
    switch(type) {
        case 'min':
            // 最小加注：跟注 + 最小加注增量
            raiseAmount = callAmount + minRaiseIncrement;
            break;
        case 'half':
            // 半池：跟注 + 0.5倍底池
            raiseAmount = callAmount + Math.floor(pot * 0.5);
            // 确保不低于最小加注
            raiseAmount = Math.max(raiseAmount, callAmount + minRaiseIncrement);
            break;
        case 'pot':
            // 全池：跟注 + 1倍底池
            raiseAmount = callAmount + pot;
            // 确保不低于最小加注
            raiseAmount = Math.max(raiseAmount, callAmount + minRaiseIncrement);
            break;
        case 'allin':
            // All-In：所有筹码
            raiseAmount = currentPlayer.chips;
            break;
    }
    
    // 限制在玩家筹码范围内
    raiseAmount = Math.min(raiseAmount, currentPlayer.chips);
    
    // 设置到输入框
    const raiseInput = document.getElementById('raise-amount');
    raiseInput.value = raiseAmount;
    
    // 视觉反馈
    raiseInput.style.background = 'rgba(76, 175, 80, 0.2)';
    setTimeout(() => {
        raiseInput.style.background = '';
    }, 500);
    
    // 播放音效
    soundEffects.play(() => soundEffects.notify());
}
```

---

## 用户界面

### 按钮布局

```
┌─────────────────────┐
│ 弃牌                │
│ 过牌                │
│ 跟注                │
├─────────────────────┤
│ [最小][半池][全池][All-In] │
├─────────────────────┤
│ [____输入框____] 加注│
└─────────────────────┘
```

### 视觉效果

#### 桌面版
- 4个按钮水平排列
- 灰色边框和半透明背景
- All-In按钮红色主题
- 悬停时上移并显示阴影

#### 移动版
- 按钮缩小，字体11px
- 间距减小到3px
- 保持4列网格布局
- 触摸友好的大小

### 交互反馈

1. **点击按钮**
   - 立即将计算的金额填入输入框
   - 输入框短暂显示绿色背景（0.5秒）
   - 播放提示音效

2. **悬停效果**
   - 按钮背景变实色
   - 向上移动2px
   - 显示阴影效果
   - All-In变为红色背景

---

## 计算示例

### 示例1: 标准情况

```
游戏状态:
- 大盲注: 20
- 底池: 100
- 当前最大下注: 40
- 我已下注: 0
- 我的筹码: 500
- 上次加注增量: 20

快捷按钮计算:
┌─────┬────────────┬─────────────────────────┐
│ 按钮 │ 计算过程    │ 结果                     │
├─────┼────────────┼─────────────────────────┤
│ 最小 │ 40+20      │ 60                      │
│ 半池 │ 40+50      │ 90 (max(90, 60))        │
│ 全池 │ 40+100     │ 140                     │
│All-In│ 我的筹码    │ 500                     │
└─────┴────────────┴─────────────────────────┘
```

### 示例2: 小筹码情况

```
游戏状态:
- 大盲注: 20
- 底池: 200
- 当前最大下注: 80
- 我已下注: 20
- 我的筹码: 50
- 最小加注增量: 60

快捷按钮计算:
┌─────┬────────────┬─────────────────────────┐
│ 按钮 │ 计算过程    │ 结果                     │
├─────┼────────────┼─────────────────────────┤
│ 最小 │ 60+60      │ 50 (限制为筹码上限)      │
│ 半池 │ 60+100     │ 50 (限制为筹码上限)      │
│ 全池 │ 60+200     │ 50 (限制为筹码上限)      │
│All-In│ 我的筹码    │ 50                      │
└─────┴────────────┴─────────────────────────┘

注意: 筹码不足时，所有按钮实际都是All-In
```

### 示例3: 新回合开始

```
游戏状态:
- 大盲注: 20
- 底池: 300
- 当前最大下注: 0 (新回合)
- 我已下注: 0
- 我的筹码: 800
- 最小加注增量: 20 (重置为大盲注)

快捷按钮计算:
┌─────┬────────────┬─────────────────────────┐
│ 按钮 │ 计算过程    │ 结果                     │
├─────┼────────────┼─────────────────────────┤
│ 最小 │ 0+20       │ 20                      │
│ 半池 │ 0+150      │ 150                     │
│ 全池 │ 0+300      │ 300                     │
│All-In│ 我的筹码    │ 800                     │
└─────┴────────────┴─────────────────────────┘
```

---

## 策略建议

### 何时使用各个按钮

#### 最小加注 (Min)
✓ **适合场景**:
- 持有中等强度的牌（如顶对弱踢脚）
- 翻牌前小对子，想便宜看翻牌
- 后位偷盲
- 控制底池大小

❌ **不适合场景**:
- 持有坚果牌（浪费价值）
- 对抗激进玩家（容易被反加注）

#### 半池加注 (Half Pot)
✓ **适合场景**:
- 持有强牌，想要建立底池
- 半诈唬（有补牌机会的听牌）
- 标准价值下注
- 保护已有底池

❌ **不适合场景**:
- 纯诈唬（成本太高）
- 已经很大的底池（可能赔率不对）

#### 全池加注 (Full Pot)
✓ **适合场景**:
- 持有非常强的牌（如暗三、顺子）
- 纯诈唬代表强牌
- 面对听牌玩家时保护
- 危险公共牌面

❌ **不适合场景**:
- 底池已经很大且筹码不深
- 对抗短筹码玩家（浪费筹码）

#### All-In
✓ **适合场景**:
- 持有坚果牌最大化价值
- 短筹码策略（<10BB）
- 承诺底池（Pot Committed）
- 强力诈唬

❌ **不适合场景**:
- 边缘牌力的情况
- 深筹码且对手有位置优势

---

## 移动端优化

### 响应式设计

**屏幕宽度 ≤ 768px**:

```css
.quick-raise-buttons {
    gap: 3px;  /* 减小间距 */
}

.btn-quick-raise {
    font-size: 11px;  /* 缩小字体 */
    padding: 6px 3px;  /* 减小内边距 */
}
```

### 触摸优化

- 按钮最小触摸区域: 44x30px
- 间距足够避免误触
- 清晰的视觉反馈

---

## 常见问题

### Q1: 为什么半池/全池加注有时等于最小加注？

A: 当底池很小时（如翻牌前），半池或全池可能小于最小加注量。此时系统会自动调整为最小加注量以符合规则。

### Q2: 筹码不足时会怎样？

A: 所有按钮计算的金额都会自动限制在你的筹码范围内。如果筹码不足，会自动设置为All-In金额。

### Q3: 可以修改快捷按钮填入的金额吗？

A: 可以！点击快捷按钮后，金额会填入输入框，你可以手动修改后再点击"加注"按钮。

### Q4: All-In按钮会立即执行吗？

A: 不会！所有快捷按钮只是填入金额，仍需点击"加注"按钮才会执行操作。

---

## 未来优化

1. **自定义快捷按钮**
   - 允许玩家自定义倍数（如2/3底池、1.5倍底池）
   - 保存个人偏好设置

2. **显示赔率信息**
   - 在按钮上显示底池赔率
   - 显示成功率百分比

3. **快捷键支持**
   - M: 最小加注
   - H: 半池
   - P: 全池
   - A: All-In

4. **动画增强**
   - 按钮点击时的粒子效果
   - 金额填入时的数字滚动动画

---

**更新状态**: ✅ 功能已完成并测试  
**服务器地址**: http://localhost:8000  
**兼容性**: 桌面和移动设备全部支持
