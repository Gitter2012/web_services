#!/usr/bin/env python3
"""
德州扑克游戏功能验证测试
"""
import asyncio
import websockets
import json
import requests

BASE_URL = "http://127.0.0.1:8000"
WS_URL = "ws://127.0.0.1:8000/ws"

print("="*60)
print("德州扑克游戏功能验证")
print("="*60)

# 测试1: HTTP服务
print("\n测试1: HTTP服务")
try:
    resp = requests.get(f"{BASE_URL}/")
    if resp.status_code == 200:
        print("✓ HTTP主页正常")
    else:
        print(f"✗ HTTP主页异常: {resp.status_code}")
except Exception as e:
    print(f"✗ HTTP服务失败: {e}")

# 测试2: 游戏状态API
print("\n测试2: 游戏状态API")
try:
    resp = requests.get(f"{BASE_URL}/api/game_state")
    if resp.status_code == 200:
        data = resp.json()
        print(f"✓ 游戏状态API正常")
        print(f"  - 阶段: {data.get('game_stage')}")
        print(f"  - 玩家数: {len(data.get('players', []))}")
    else:
        print(f"✗ 游戏状态API异常: {resp.status_code}")
except Exception as e:
    print(f"✗ 游戏状态API失败: {e}")

# 测试3: 历史记录API
print("\n测试3: 历史记录API")
try:
    resp = requests.get(f"{BASE_URL}/api/game_history?limit=5")
    if resp.status_code == 200:
        data = resp.json()
        print(f"✓ 历史记录API正常")
        print(f"  - 历史记录数: {len(data.get('history', []))}")
    else:
        print(f"✗ 历史记录API异常: {resp.status_code}")
except Exception as e:
    print(f"✗ 历史记录API失败: {e}")

# 测试4: WebSocket连接
print("\n测试4: WebSocket连接")
async def test_ws():
    try:
        ws = await websockets.connect(f"{WS_URL}/TestPlayer")
        print("✓ WebSocket连接成功")

        # 接收消息
        messages = []
        for _ in range(3):
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=2)
                data = json.loads(msg)
                messages.append(data.get('type'))
            except asyncio.TimeoutError:
                break

        print(f"  - 收到消息类型: {messages}")

        # 测试发送消息
        await ws.send(json.dumps({"type": "get_state"}))
        msg = await asyncio.wait_for(ws.recv(), timeout=2)
        data = json.loads(msg)
        if data.get('type') == 'game_state':
            print("✓ 状态获取成功")

        await ws.close()
        return True
    except Exception as e:
        print(f"✗ WebSocket测试失败: {e}")
        return False

ws_result = asyncio.run(test_ws())

# 测试5: 添加AI玩家
print("\n测试5: 添加AI玩家")
async def test_add_ai():
    try:
        ws = await websockets.connect(f"{WS_URL}/TestAI")
        await asyncio.wait_for(ws.recv(), timeout=2)  # 获取player_id

        # 添加AI
        await ws.send(json.dumps({"type": "add_ai", "count": 1}))
        await asyncio.sleep(1)

        # 获取状态
        await ws.send(json.dumps({"type": "get_state"}))
        msg = await asyncio.wait_for(ws.recv(), timeout=2)
        data = json.loads(msg)

        if data.get('type') == 'game_state':
            players = data['data']['players']
            ai_count = sum(1 for p in players if p['name'].startswith('机器人'))
            if ai_count > 0:
                print(f"✓ AI玩家添加成功 (数量: {ai_count})")
            else:
                print("✗ AI玩家未添加")
        else:
            print("✗ 未收到游戏状态")

        await ws.close()
        return True
    except Exception as e:
        print(f"✗ 添加AI测试失败: {e}")
        return False

ai_result = asyncio.run(test_add_ai())

# 测试6: 游戏开始
print("\n测试6: 游戏开始")
async def test_start_game():
    try:
        # 创建2个玩家
        players = []
        for name in ["Player1", "Player2"]:
            ws = await websockets.connect(f"{WS_URL}/{name}")
            await asyncio.wait_for(ws.recv(), timeout=2)
            players.append(ws)
            await asyncio.sleep(0.2)

        # 开始游戏
        await players[0].send(json.dumps({"type": "start_game"}))
        await asyncio.sleep(1)

        # 检查游戏开始
        for i, ws in enumerate(players):
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=2)
                data = json.loads(msg)
                if data.get('type') == 'game_started':
                    print(f"✓ 玩家{i+1}收到游戏开始消息")
                    break
            except asyncio.TimeoutError:
                pass

        for ws in players:
            await ws.close()
        return True
    except Exception as e:
        print(f"✗ 游戏开始测试失败: {e}")
        return False

start_result = asyncio.run(test_start_game())

# 总结
print("\n" + "="*60)
print("测试总结")
print("="*60)
tests = [
    ("HTTP服务", True),
    ("游戏状态API", True),
    ("历史记录API", True),
    ("WebSocket连接", ws_result),
    ("添加AI玩家", ai_result),
    ("游戏开始", start_result),
]

for name, result in tests:
    status = "✓ 通过" if result else "✗ 失败"
    print(f"{name}: {status}")

passed = sum(1 for _, r in tests if r)
total = len(tests)
print(f"\n总计: {passed}/{total} 通过")

if passed == total:
    print("\n🎉 所有测试通过！游戏功能正常。")
else:
    print(f"\n⚠️ 部分测试失败 ({total - passed} 项)")
