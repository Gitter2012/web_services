# 游戏设置功能说明

## 更新日期
2026-02-03

## 功能概述

添加了完整的游戏设置面板，允许玩家自定义游戏体验，包括音效控制、动画设置、自动开始等功能。所有设置自动保存到浏览器本地存储（localStorage）。

## 设置面板

### 访问方式
点击底部控制栏的 **⚙️ 设置** 按钮打开设置面板。

### 面板特点
- 🎨 **现代设计**：半透明黑色背景，金色主题
- 📱 **居中弹窗**：屏幕中央显示，最大高度80vh
- ✨ **淡入动画**：优雅的打开/关闭动画
- 💾 **自动保存**：所有设置即时保存到localStorage
- 🔄 **持久化**：刷新页面后设置保持不变

## 设置项详解

### 1. 🔊 音效控制

**功能**：开关游戏音效

**控制方式**：
- 切换开关（绿色=开启，灰色=关闭）
- 点击开关切换状态
- 开启时播放测试音效

**效果**：
- 关闭后所有游戏音效静音
- 不影响音量设置
- 实时生效

**默认值**：开启

**保存位置**：`localStorage.soundEnabled`

### 2. 🔉 音量调节

**功能**：调节游戏音效音量

**控制方式**：
- 滑块控制（0-100%）
- 拖动滑块实时调节
- 显示当前音量百分比
- 调节时播放测试音效

**效果**：
- 控制所有音效的统一音量
- 使用Web Audio API的masterGain节点
- 实时生效，无需重启

**默认值**：100%

**保存位置**：`localStorage.volume`

**技术实现**：
```javascript
const masterGain = audioContext.createGain();
masterGain.connect(audioContext.destination);
masterGain.gain.value = volume / 100;

// 所有音效连接到masterGain
oscillator.connect(gainNode);
gainNode.connect(masterGain); // 而不是直接连接destination
```

### 3. ✨ 动画效果

**功能**：开关游戏动画

**控制方式**：
- 切换开关
- 点击切换状态

**效果**：
- 关闭后禁用所有CSS动画和过渡
- 包括：发牌动画、筹码移动、卡片翻转等
- 适合低性能设备或喜欢简洁界面的玩家

**默认值**：开启

**保存位置**：`localStorage.animationEnabled`

**技术实现**：
```css
body.no-animation * {
    animation: none !important;
    transition: none !important;
}
```

### 4. ⏱️ 自动开始

**功能**：控制每局结束后的自动开始倒计时

**控制方式**：
- 切换开关
- 点击切换状态

**效果**：
- 开启：每局结束后5秒倒计时自动开始下一局
- 关闭：每局结束后需要手动点击"开始游戏"

**默认值**：开启

**保存位置**：`localStorage.autoStartEnabled`

**应用场景**：
- 快节奏游戏：开启（默认）
- 需要思考时间：关闭

### 5. 🎨 游戏主题

**功能**：更改游戏的颜色主题

**可选主题**：
1. **经典蓝**（默认）
   - 深蓝色渐变背景
   - 颜色：#1e3c72 → #2a5298
   
2. **扑克绿**
   - 经典扑克桌绿色
   - 颜色：#0a5f0a
   
3. **暗黑**
   - 纯黑色主题
   - 颜色：#1a1a1a

**控制方式**：
- 点击主题按钮
- 立即应用并刷新页面

**效果**：
- 改变页面背景颜色
- 需要刷新页面生效

**默认值**：经典蓝

**保存位置**：`localStorage.theme`

**注意**：切换主题会刷新页面，当前游戏进度会丢失。

## 技术实现

### 数据结构

```javascript
const gameSettings = {
    soundEnabled: true,          // 音效开关
    volume: 100,                 // 音量 (0-100)
    animationEnabled: true,      // 动画开关
    autoStartEnabled: true,      // 自动开始
    theme: 'default'            // 主题
};
```

### 初始化

页面加载时从localStorage读取设置：
```javascript
const gameSettings = {
    soundEnabled: localStorage.getItem('soundEnabled') !== 'false',
    volume: parseInt(localStorage.getItem('volume') || '100'),
    animationEnabled: localStorage.getItem('animationEnabled') !== 'false',
    autoStartEnabled: localStorage.getItem('autoStartEnabled') !== 'false',
    theme: localStorage.getItem('theme') || 'default'
};
```

### 音效系统重构

**之前**：
```javascript
soundEffects.dealCard(); // 直接播放
```

**现在**：
```javascript
soundEffects.play(() => soundEffects.dealCard()); // 检查开关后播放
```

**play包装函数**：
```javascript
play: (soundFunc) => {
    if (!gameSettings.soundEnabled) return;
    soundFunc();
}
```

### 主音量控制

使用Web Audio API的GainNode：
```javascript
const masterGain = audioContext.createGain();
masterGain.connect(audioContext.destination);
masterGain.gain.value = gameSettings.volume / 100;

// 所有音效通过masterGain
oscillator.connect(gainNode);
gainNode.connect(masterGain); // 统一音量控制
```

### 持久化

每次设置更改时自动保存：
```javascript
function toggleSound() {
    gameSettings.soundEnabled = !gameSettings.soundEnabled;
    localStorage.setItem('soundEnabled', gameSettings.soundEnabled);
    // ...
}
```

### CSS动画控制

```css
/* 禁用所有动画和过渡 */
body.no-animation * {
    animation: none !important;
    transition: none !important;
}
```

```javascript
// 应用或移除class
if (gameSettings.animationEnabled) {
    document.body.classList.remove('no-animation');
} else {
    document.body.classList.add('no-animation');
}
```

## 用户界面

### 设置面板布局

```
╔═══════════════════════════════════╗
║ ⚙️ 游戏设置                    ✕ ║
╠═══════════════════════════════════╣
║ 🔊 音效控制                       ║
║ 控制游戏音效的开关和音量           ║
║ 音效开关         [====●====]     ║
║                                   ║
║ 🔉 音量调节                       ║
║ 🔇 ▬▬▬▬▬●▬▬▬▬▬ 100%              ║
║                                   ║
║ ✨ 动画效果                       ║
║ 控制游戏中的动画效果               ║
║ 动画开关         [====●====]     ║
║                                   ║
║ ⏱️ 自动开始                       ║
║ 每局结束后自动开始下一局的倒计时    ║
║ 自动开始         [====●====]     ║
║                                   ║
║ 🎨 游戏主题                       ║
║ 选择游戏的颜色主题                 ║
║ [经典蓝] [扑克绿] [暗黑]          ║
║                                   ║
║ ─────────────────────────────── ║
║ 德州扑克 v1.0                     ║
║ 所有设置将自动保存到本地           ║
╚═══════════════════════════════════╝
```

### 切换开关样式

**关闭状态**：
```
┌──────────┐
│ ●       │  灰色背景
└──────────┘
```

**开启状态**：
```
┌──────────┐
│       ● │  绿色背景
└──────────┘
```

### 音量滑块

```
🔇 ▬▬▬▬▬▬●▬▬▬ 70%
    └─金色滑块─┘
```

## 使用场景

### 场景1：安静环境
**问题**：在办公室或图书馆玩游戏
**解决**：
1. 打开设置面板
2. 关闭音效开关
3. 或将音量调至0%

### 场景2：低性能设备
**问题**：游戏运行卡顿
**解决**：
1. 打开设置面板
2. 关闭动画效果
3. 游戏变得更流畅

### 场景3：快速连续游戏
**问题**：想连续快速玩多局
**解决**：
1. 确保自动开始已开启（默认）
2. 每局结束后自动5秒倒计时

### 场景4：需要思考时间
**问题**：每局结束后想分析统计数据
**解决**：
1. 打开设置面板
2. 关闭自动开始
3. 手动控制下一局开始时机

### 场景5：个性化外观
**问题**：想要不同的视觉体验
**解决**：
1. 打开设置面板
2. 选择喜欢的主题
3. 页面自动刷新并应用

## 兼容性

### 浏览器支持
- ✅ Chrome/Edge（推荐）
- ✅ Firefox
- ✅ Safari
- ✅ 所有现代浏览器

### 存储大小
- localStorage使用：< 1KB
- 不影响浏览器性能

### 跨设备
- ⚠️ 设置存储在本地浏览器
- ⚠️ 不同设备/浏览器需要分别设置
- ⚠️ 清除浏览器数据会重置设置

## 默认设置

| 设置项 | 默认值 | 说明 |
|--------|--------|------|
| 音效开关 | 开启 | 所有玩家都能听到音效 |
| 音量 | 100% | 最大音量 |
| 动画效果 | 开启 | 完整动画体验 |
| 自动开始 | 开启 | 5秒自动开始 |
| 主题 | 经典蓝 | 默认深蓝色背景 |

## 快捷访问

- **打开设置**：点击底部 ⚙️ 设置按钮
- **关闭设置**：
  - 点击右上角 ✕ 按钮
  - 再次点击 ⚙️ 设置按钮
  - 点击设置面板外的区域（待实现）

## 文件变更

### HTML结构
- 新增设置面板HTML
- 添加设置按钮到控制栏

### CSS样式
- 设置面板样式（.settings-*）
- 切换开关样式（.toggle-switch）
- 滑块样式（input[type="range"]）
- 禁用动画样式（body.no-animation）

### JavaScript功能
- `gameSettings` 对象
- `toggleSettings()` 打开/关闭设置
- `updateSettingsUI()` 同步UI状态
- `toggleSound()` 音效开关
- `updateVolume()` 音量调节
- `toggleAnimation()` 动画开关
- `toggleAutoStart()` 自动开始开关
- `setTheme()` 主题切换
- 音效系统重构（play包装）

## 测试建议

### 测试清单

#### 音效控制
- [ ] 打开设置，切换音效开关
- [ ] 关闭音效后，游戏无声音
- [ ] 开启音效后，游戏有声音
- [ ] 音效状态在刷新后保持

#### 音量调节
- [ ] 拖动音量滑块
- [ ] 音量实时变化
- [ ] 音量值正确显示
- [ ] 音量设置在刷新后保持

#### 动画效果
- [ ] 关闭动画后，无发牌动画
- [ ] 关闭动画后，无过渡效果
- [ ] 开启动画后，动画恢复
- [ ] 动画状态在刷新后保持

#### 自动开始
- [ ] 关闭自动开始，游戏结束后不倒计时
- [ ] 开启自动开始，游戏结束后倒计时
- [ ] 设置在刷新后保持

#### 主题切换
- [ ] 点击不同主题按钮
- [ ] 页面自动刷新
- [ ] 主题成功应用
- [ ] 主题在刷新后保持

## 后续优化建议

1. **云端同步**：账号系统+设置云同步
2. **更多主题**：添加更多配色方案
3. **高级设置**：游戏速度、AI难度等
4. **导入/导出**：设置导出为文件
5. **键盘快捷键**：快捷键打开设置
6. **响应式**：移动端优化

## 总结

设置面板提供了完整的自定义体验：
- ✅ 音效完全可控（开关+音量）
- ✅ 动画可以关闭（提升性能）
- ✅ 自动开始可选（适应不同节奏）
- ✅ 主题个性化（3种选择）
- ✅ 所有设置持久化（localStorage）
- ✅ 界面现代美观（金色主题+动画）

玩家现在可以根据自己的喜好和环境，完全自定义游戏体验！
