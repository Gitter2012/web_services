#!/usr/bin/env python3
"""
快速功能测试
"""
import requests
import json

print("=" * 60)
print("快速功能测试")
print("=" * 60)

# 测试1: 服务器响应
print("\n[1] 测试服务器响应...")
try:
    response = requests.get("http://localhost:8000", timeout=3)
    if response.status_code == 200:
        print("✓ 服务器响应正常")
    else:
        print(f"✗ 服务器响应异常: {response.status_code}")
except Exception as e:
    print(f"✗ 无法连接服务器: {e}")
    exit(1)

# 测试2: HTML内容检查
print("\n[2] 检查页面内容...")
html = response.text
checks = {
    "游戏信息栏": "game-info",
    "扑克桌": "poker-table",
    "控制按钮": "start-btn",
    "排行榜": "leaderboard-panel",
    "历史记录": "history-panel",
    "底池显示": "pot-display",
    "公共牌区域": "community-cards",
}

for name, keyword in checks.items():
    if keyword in html:
        print(f"✓ {name}")
    else:
        print(f"✗ {name} 缺失")

# 测试3: API端点
print("\n[3] 测试API端点...")
try:
    response = requests.get("http://localhost:8000/api/game_history?limit=5", timeout=3)
    if response.status_code == 200:
        data = response.json()
        if 'history' in data:
            print(f"✓ 游戏历史API (记录数: {len(data['history'])})")
        else:
            print("✗ 游戏历史API 数据格式错误")
    else:
        print(f"✗ 游戏历史API 响应异常: {response.status_code}")
except Exception as e:
    print(f"✗ 游戏历史API 错误: {e}")

# 测试4: 检查关键功能
print("\n[4] 检查关键功能代码...")
features = {
    "座位计算函数": "calculateSeatPosition",
    "玩家卡片创建": "createPlayerCard",
    "游戏UI更新": "updateGameUI",
    "排行榜切换": "toggleLeaderboard",
    "历史记录切换": "toggleHistory",
    "音效系统": "soundEffects",
    "最终结果显示": "showFinalResults",
}

for name, keyword in features.items():
    if keyword in html:
        print(f"✓ {name}")
    else:
        print(f"✗ {name} 缺失")

print("\n" + "=" * 60)
print("测试完成!")
print("=" * 60)
print("\n建议：在浏览器中打开 http://localhost:8000 进行手动测试")
print("测试项目：")
print("  1. 加入游戏")
print("  2. 添加AI玩家")
print("  3. 开始游戏并完成一局")
print("  4. 查看排行榜（右侧）")
print("  5. 查看牌局回顾（左侧）")
print("  6. 结束游戏查看最终结果")
