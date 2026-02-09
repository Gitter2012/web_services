#!/usr/bin/env python3
"""
德州扑克游戏综合测试
"""
import asyncio
import websockets
import json
import requests
import uuid

BASE_URL = "http://127.0.0.1:8000"
WS_URL = "ws://127.0.0.1:8000/ws"

class GameTester:
    def __init__(self, name):
        self.name = name
        self.player_id = None
        self.ws = None
        self.messages = []

    async def connect(self):
        uri = f"{WS_URL}/{self.name}"
        self.ws = await websockets.connect(uri)
        # 获取玩家ID
        msg = await self.ws.recv()
        data = json.loads(msg)
        if data['type'] == 'player_id':
            self.player_id = data['data']['player_id']
            return True
        return False

    async def send(self, data):
        await self.ws.send(json.dumps(data))

    async def recv(self, timeout=2):
        try:
            msg = await asyncio.wait_for(self.ws.recv(), timeout=timeout)
            return json.loads(msg)
        except asyncio.TimeoutError:
            return None

    async def close(self):
        if self.ws:
            await self.ws.close()

async def test_basic_game():
    """测试基本游戏流程"""
    print("\n" + "="*60)
    print("测试: 基本游戏流程")
    print("="*60)

    players = []
    try:
        # 创建3个玩家
        for i in range(3):
            name = f"TestPlayer{i}_{uuid.uuid4().hex[:8]}"
            tester = GameTester(name)
            await tester.connect()
            players.append(tester)
            print(f"✓ 玩家{i+1} 已连接")
            await asyncio.sleep(0.2)

        # 等待初始消息
        await asyncio.sleep(1)

        # 玩家1开始游戏
        await players[0].send({"type": "start_game"})
        await asyncio.sleep(1)

        # 检查游戏开始
        for i, p in enumerate(players):
            while True:
                msg = await p.recv(timeout=0.5)
                if not msg:
                    break
                if msg.get('type') == 'game_started':
                    print(f"✓ 玩家{i+1} 收到游戏开始消息")
                    break

        # 测试HTTP API
        try:
            resp = requests.get(f"{BASE_URL}/api/game_state")
            if resp.status_code == 200:
                print("✓ 游戏状态API正常")
            else:
                print("✗ 游戏状态API异常")
        except Exception as e:
            print(f"✗ API测试失败: {e}")

        # 测试历史记录API
        try:
            resp = requests.get(f"{BASE_URL}/api/game_history?limit=5")
            if resp.status_code == 200:
                print("✓ 历史记录API正常")
            else:
                print("✗ 历史记录API异常")
        except Exception as e:
            print(f"✗ 历史记录API失败: {e}")

        return True

    except Exception as e:
        print(f"✗ 测试失败: {e}")
        return False
    finally:
        for p in players:
            await p.close()

async def test_ai_players():
    """测试AI玩家"""
    print("\n" + "="*60)
    print("测试: AI玩家")
    print("="*60)

    tester = None
    try:
        tester = GameTester("AI测试者")
        await tester.connect()
        print("✓ 测试者已连接")

        await asyncio.sleep(0.5)

        # 添加AI玩家
        await tester.send({"type": "add_ai", "count": 2})
        print("✓ 添加2个AI玩家")
        await asyncio.sleep(1)

        # 获取游戏状态检查AI是否加入
        msg = await tester.recv(timeout=2)
        while msg:
            if msg.get('type') == 'game_state':
                players = msg['data']['players']
                ai_count = sum(1 for p in players if p['name'].startswith('机器人'))
                print(f"✓ AI玩家数量: {ai_count}")
                if ai_count >= 2:
                    return True
            msg = await tester.recv(timeout=0.5)

        return False

    except Exception as e:
        print(f"✗ 测试失败: {e}")
        return False
    finally:
        if tester:
            await tester.close()

async def test_room_owner():
    """测试房主功能"""
    print("\n" + "="*60)
    print("测试: 房主功能")
    print("="*60)

    players = []
    try:
        # 创建玩家
        for i in range(2):
            name = f"RoomTest{i}_{uuid.uuid4().hex[:8]}"
            tester = GameTester(name)
            await tester.connect()
            players.append(tester)
            print(f"✓ 玩家{i+1} 已连接")
            await asyncio.sleep(0.2)

        await asyncio.sleep(0.5)

        # 获取游戏状态检查房主
        # 清空消息队列
        while True:
            try:
                await players[0].recv(timeout=0.1)
            except:
                break

        msg = await players[0].recv(timeout=2)
        if msg and msg.get('type') == 'game_state':
            owner_id = msg['data']['room_owner_id']
            print(f"房主ID: {owner_id}")
            print(f"玩家ID: {players[0].player_id}")
            if owner_id == players[0].player_id:
                print("✓ 第一个玩家是房主")
                return True
            else:
                print(f"✗ 房主ID不匹配: {owner_id} != {players[0].player_id}")

        return False

    except Exception as e:
        print(f"✗ 测试失败: {e}")
        return False
    finally:
        for p in players:
            await p.close()

async def main():
    print("\n" + "="*60)
    print("德州扑克游戏综合测试")
    print("="*60)

    # 检查服务器状态
    try:
        resp = requests.get(f"{BASE_URL}/")
        if resp.status_code == 200:
            print("✓ 服务器运行正常")
        else:
            print("✗ 服务器响应异常")
            return
    except Exception as e:
        print(f"✗ 无法连接到服务器: {e}")
        return

    tests = [
        ("基本游戏流程", test_basic_game),
        ("AI玩家功能", test_ai_players),
        ("房主功能", test_room_owner),
    ]

    results = []
    for name, test_func in tests:
        result = await test_func()
        results.append((name, result))
        await asyncio.sleep(0.5)  # 测试之间休息

    # 总结
    print("\n" + "="*60)
    print("测试总结")
    print("="*60)
    passed = sum(1 for _, r in results if r)
    total = len(results)
    for name, result in results:
        status = "✓ 通过" if result else "✗ 失败"
        print(f"{name}: {status}")

    print(f"\n总计: {passed}/{total} 通过")
    if passed == total:
        print("\n🎉 所有测试通过！")
    else:
        print("\n⚠️ 部分测试失败")

if __name__ == "__main__":
    asyncio.run(main())
