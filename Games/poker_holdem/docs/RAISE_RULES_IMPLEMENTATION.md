# 无限注德州扑克加注规则实现文档

## 更新日期: 2026-02-03

---

## 概述

实现了符合无限注德州扑克（No-Limit Texas Hold'em）标准规则的加注系统，包括最小加注量验证、All-In处理和用户界面提示。

---

## 德州扑克加注规则说明

### 基本规则

1. **最小加注量（Minimum Raise）**
   - 加注的增量（raise increment）必须至少等于上一次加注的增量
   - 如果本轮还没有人加注，最小加注增量为大盲注（Big Blind）
   - 加注总额 = 跟注金额 + 加注增量

2. **All-In例外**
   - 如果玩家下注所有筹码（All-In），可以是任意金额
   - 即使All-In金额小于最小加注量，也是合法的

3. **计算示例**
   ```
   大盲注 = 20
   当前最大下注 = 40 (某玩家加注到40)
   玩家A已下注 = 10
   
   玩家A需要：
   - 跟注金额 = 40 - 10 = 30
   - 最小加注增量 = 20 (上次加注量20，或大盲注)
   - 最小加注总额 = 30 + 20 = 50
   
   因此：
   - 只能下注 50+ 或 All-In
   - 不能下注 40（只是跟注，应该用Call按钮）
   - 不能下注 45（加注增量只有5，不足20）
   ```

---

## 后端实现

### 1. 新增游戏状态变量

**文件**: `poker_game.py`

```python
class PokerGame:
    def __init__(self, small_blind: int = 10, big_blind: int = 20):
        # ... 其他初始化
        self.min_raise = big_blind  # 最小加注量（初始为大盲注）
        self.last_raise_amount = 0  # 上次加注的增量
```

### 2. 加注验证逻辑

**位置**: `poker_game.py:379-415`

```python
elif action == "raise":
    # 1. 计算需要跟注的金额
    call_amount = self.current_bet - current_player.bet
    
    # 2. 计算实际加注金额（总下注 - 已下注）
    total_bet_amount = min(amount, current_player.chips)
    raise_increment = total_bet_amount - call_amount
    
    # 3. 验证加注规则
    is_all_in = (total_bet_amount == current_player.chips)
    
    if not is_all_in:
        # 不是all-in时，需要检查最小加注量
        min_raise_increment = max(self.min_raise, self.big_blind)
        
        if raise_increment < min_raise_increment:
            # 加注量不足，拒绝操作
            return False
    
    # 4. 执行加注
    current_player.chips -= total_bet_amount
    current_player.bet += total_bet_amount
    self.pot += total_bet_amount
    
    # 5. 更新当前最大下注和最小加注量
    self.current_bet = current_player.bet
    
    # 更新最小加注量为本次加注的增量
    if raise_increment > 0:
        self.last_raise_amount = raise_increment
        self.min_raise = raise_increment
```

### 3. 重置最小加注量

每个新的下注回合开始时，重置最小加注量：

**位置**: `poker_game.py:476-482`

```python
def _next_stage(self):
    # ... 其他代码
    self.current_bet = 0
    self.min_raise = self.big_blind  # 重置最小加注量为大盲注
    self.last_raise_amount = 0  # 重置上次加注量
```

### 4. 游戏状态API增强

**位置**: `poker_game.py:662-696`

新增返回字段：
```python
{
    "min_raise": 20,          # 最小加注增量
    "min_raise_total": 50,    # 最小加注总额（含跟注）
    "call_amount": 30,        # 跟注金额
    "big_blind": 20,          # 大盲注
    # ... 其他字段
}
```

---

## 前端实现

### 1. 加注验证

**位置**: `index.html:2222-2289`

```javascript
function playerAction(action) {
    if (action === 'raise') {
        const inputAmount = parseInt(document.getElementById('raise-amount').value) || 0;
        
        // 获取当前玩家信息
        const currentPlayer = currentGameState.players.find(p => p.id === playerId);
        
        // 计算跟注金额和加注增量
        const callAmount = currentGameState.current_bet - currentPlayer.bet;
        const raiseIncrement = inputAmount - callAmount;
        
        // 检查是否all-in
        const isAllIn = inputAmount >= currentPlayer.chips;
        
        if (!isAllIn) {
            // 不是all-in时，检查最小加注量
            const minRaiseIncrement = Math.max(
                currentGameState.min_raise || currentGameState.big_blind, 
                currentGameState.big_blind
            );
            
            if (raiseIncrement < minRaiseIncrement) {
                addMessage(
                    `加注增量至少需要 ${minRaiseIncrement} 筹码（当前增量：${raiseIncrement}）`, 
                    'error'
                );
                return;
            }
        }
        
        // 检查筹码是否足够
        if (inputAmount > currentPlayer.chips) {
            addMessage(
                `筹码不足，最多可下注 ${currentPlayer.chips}（All-In）`, 
                'error'
            );
            return;
        }
        
        amount = inputAmount;
    }
    // ... 发送操作到服务器
}
```

### 2. 动态UI提示

**位置**: `index.html:1844-1875`

```javascript
function updateGameUI(state) {
    // ... 其他更新
    
    if (state.current_player_id === playerId) {
        // 更新加注输入框的占位符
        const raiseInput = document.getElementById('raise-amount');
        const currentPlayer = state.players.find(p => p.id === playerId);
        
        const callAmount = state.current_bet - currentPlayer.bet;
        const minRaiseIncrement = Math.max(state.min_raise || state.big_blind, state.big_blind);
        const minRaiseTotal = callAmount + minRaiseIncrement;
        
        raiseInput.placeholder = `最少 ${minRaiseTotal} (含跟注${callAmount})`;
        raiseInput.min = minRaiseTotal;
        
        // 更新跟注按钮文本
        const callBtn = document.querySelector('.btn-call');
        if (callAmount > 0) {
            callBtn.textContent = `跟注 ${callAmount}`;
        } else {
            callBtn.textContent = '跟注';
        }
    }
}
```

---

## 用户体验优化

### 1. 输入框占位符

动态显示最小加注金额和跟注金额：
```
占位符: "最少 50 (含跟注30)"
```

### 2. 按钮文本更新

跟注按钮显示需要跟注的具体筹码数：
```
"跟注" → "跟注 30"
```

### 3. 错误提示

清晰的错误消息：
- ❌ "加注增量至少需要 20 筹码（当前增量：5）"
- ❌ "筹码不足，最多可下注 100（All-In）"
- ❌ "请输入有效的加注金额"

---

## 测试场景

### 场景1: 标准加注

```
设定:
- 大盲注: 20
- 当前最大下注: 20
- 玩家筹码: 1000
- 玩家已下注: 0

操作:
✓ 输入 40 (跟注20 + 加注20) → 成功
✓ 输入 100 → 成功
✗ 输入 30 (加注增量只有10) → 失败
✗ 输入 20 (没有加注，只是跟注) → 失败
```

### 场景2: 重加注（Re-raise）

```
设定:
- 大盲注: 20
- 当前最大下注: 100 (有人加注到100)
- 玩家已下注: 20
- 玩家筹码: 1000
- 上次加注增量: 80

操作:
✓ 输入 180 (跟注80 + 加注80) → 成功
✓ 输入 200 (跟注80 + 加注100) → 成功
✗ 输入 150 (加注增量只有50，不足80) → 失败
✗ 输入 100 (只是跟注) → 失败
```

### 场景3: All-In

```
设定:
- 大盲注: 20
- 当前最大下注: 100
- 玩家已下注: 0
- 玩家筹码: 50

操作:
✓ 输入 50 (All-In) → 成功（即使不足最小加注量）
```

### 场景4: 新回合（Flop/Turn/River）

```
设定:
- 进入新回合（Flop）
- 最小加注量重置为大盲注20
- 当前最大下注: 0

操作:
✓ 输入 20 (加注到20) → 成功
✓ 输入 50 → 成功
✗ 输入 10 (小于大盲注) → 失败
```

---

## 规则总结

| 情况 | 最小加注增量 | 最小加注总额 |
|------|------------|------------|
| 本轮首次加注 | 大盲注 | 跟注金额 + 大盲注 |
| 本轮有人加注 | 上次加注增量 | 跟注金额 + 上次加注增量 |
| All-In | 无限制 | 剩余筹码 |
| 新回合开始 | 大盲注（重置） | 大盲注 |

---

## 相关文件

### 后端
- `poker_game.py`: 第234-252行（初始化）
- `poker_game.py`: 第379-415行（加注验证）
- `poker_game.py`: 第476-482行（重置逻辑）
- `poker_game.py`: 第662-696行（状态API）

### 前端
- `index.html`: 第2222-2289行（加注验证）
- `index.html`: 第1844-1875行（UI更新）

---

## 注意事项

1. **服务器端验证优先**: 即使前端验证通过，后端仍会再次验证，确保规则正确执行

2. **All-In特殊处理**: All-In是唯一可以少于最小加注量的情况

3. **跟注vs加注**: 
   - 跟注使用 `Call` 按钮
   - 加注使用 `Raise` 按钮 + 输入金额
   - 输入的金额是**总下注额**，而非**加注增量**

4. **UI提示**: 占位符中的"含跟注XX"提示用户输入的是总额

---

## 未来优化建议

1. **快捷加注按钮**: 添加 "最小加注"、"半个底池"、"全部底池"、"All-In" 快捷按钮

2. **加注历史**: 显示本轮的加注历史，方便玩家决策

3. **滑块输入**: 添加滑块控件，方便选择加注金额

4. **筹码计算器**: 显示加注后的底池赔率（Pot Odds）

---

**测试状态**: ✅ 后端和前端实现完成  
**服务器地址**: http://localhost:8000  
**规则符合**: WSOP（世界扑克大赛）标准无限注德州扑克规则
