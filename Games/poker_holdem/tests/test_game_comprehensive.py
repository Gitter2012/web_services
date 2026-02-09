#!/usr/bin/env python3
"""
德州扑克游戏全面功能测试
"""
import asyncio
import json
import websockets
import time

WS_URL = "ws://localhost:8000/ws"

class TestResult:
    def __init__(self):
        self.passed = []
        self.failed = []
    
    def add_pass(self, test_name):
        self.passed.append(test_name)
        print(f"✓ {test_name}")
    
    def add_fail(self, test_name, error):
        self.failed.append((test_name, error))
        print(f"✗ {test_name}: {error}")
    
    def summary(self):
        print("\n" + "=" * 60)
        print("测试总结")
        print("=" * 60)
        print(f"通过: {len(self.passed)}")
        print(f"失败: {len(self.failed)}")
        if self.failed:
            print("\n失败的测试:")
            for name, error in self.failed:
                print(f"  - {name}: {error}")
        print("=" * 60)

result = TestResult()

async def test_connection():
    """测试1: 玩家连接"""
    try:
        ws = await websockets.connect(f"{WS_URL}/TestPlayer")
        msg = await asyncio.wait_for(ws.recv(), timeout=3)
        data = json.loads(msg)
        
        if data.get('type') == 'player_id':
            player_id = data.get('data', {}).get('player_id')
            if player_id:
                result.add_pass("玩家连接")
                await ws.close()
                return True
        
        result.add_fail("玩家连接", "未收到player_id")
        await ws.close()
        return False
    except Exception as e:
        result.add_fail("玩家连接", str(e))
        return False

async def test_multi_player_game():
    """测试2-5: 多人游戏流程"""
    players = []
    try:
        # 连接3个玩家
        for i, name in enumerate(['Alice', 'Bob', 'Charlie']):
            ws = await websockets.connect(f"{WS_URL}/{name}")
            msg = await asyncio.wait_for(ws.recv(), timeout=2)
            data = json.loads(msg)
            player_id = data.get('data', {}).get('player_id')
            players.append({'ws': ws, 'id': player_id, 'name': name})
            await asyncio.sleep(0.3)
        
        result.add_pass("多人连接")
        
        # 清空初始消息
        for p in players:
            try:
                while True:
                    await asyncio.wait_for(p['ws'].recv(), timeout=0.1)
            except asyncio.TimeoutError:
                pass
        
        # 开始游戏
        await players[0]['ws'].send(json.dumps({"type": "start_game"}))
        await asyncio.sleep(1)
        
        # 检查游戏开始消息
        game_started = False
        for p in players:
            try:
                msg = await asyncio.wait_for(p['ws'].recv(), timeout=2)
                data = json.loads(msg)
                if data.get('type') == 'game_started':
                    game_started = True
            except asyncio.TimeoutError:
                pass
        
        if game_started:
            result.add_pass("游戏开始")
        else:
            result.add_fail("游戏开始", "未收到game_started消息")
        
        # 清空消息
        for p in players:
            try:
                while True:
                    await asyncio.wait_for(p['ws'].recv(), timeout=0.1)
            except asyncio.TimeoutError:
                pass
        
        # 玩一轮游戏
        actions_count = 0
        max_actions = 30
        game_over = False
        
        for _ in range(max_actions):
            if game_over:
                break
            
            for p in players:
                try:
                    msg = await asyncio.wait_for(p['ws'].recv(), timeout=1)
                    data = json.loads(msg)
                    
                    if data.get('type') == 'game_state':
                        state = data['data']
                        if state['game_stage'] == 'waiting':
                            game_over = True
                            break
                        
                        if state['current_player_id'] == p['id']:
                            actions_count += 1
                            min_bet = state.get('min_bet', 0)
                            action = "call" if min_bet > 0 else "check"
                            await p['ws'].send(json.dumps({
                                "type": "action",
                                "action": action
                            }))
                            await asyncio.sleep(0.2)
                except asyncio.TimeoutError:
                    pass
            
            await asyncio.sleep(0.1)
        
        if actions_count > 0:
            result.add_pass("游戏操作")
        else:
            result.add_fail("游戏操作", "没有执行任何操作")
        
        if game_over:
            result.add_pass("游戏完成")
        else:
            result.add_fail("游戏完成", "游戏未正常完成")
        
        # 测试游戏状态获取
        await players[0]['ws'].send(json.dumps({"type": "get_state"}))
        await asyncio.sleep(0.5)
        
        state_received = False
        try:
            msg = await asyncio.wait_for(players[0]['ws'].recv(), timeout=2)
            data = json.loads(msg)
            if data.get('type') == 'game_state':
                state_received = True
                state = data['data']
                
                # 检查统计数据
                has_stats = any(p['games_played'] > 0 for p in state['players'])
                if has_stats:
                    result.add_pass("统计数据更新")
                else:
                    result.add_fail("统计数据更新", "统计数据未更新")
        except asyncio.TimeoutError:
            pass
        
        if not state_received:
            result.add_fail("游戏状态获取", "未收到状态")
        
        # 关闭连接
        for p in players:
            await p['ws'].close()
        
    except Exception as e:
        result.add_fail("多人游戏流程", str(e))
        for p in players:
            if 'ws' in p:
                await p['ws'].close()

async def test_room_owner():
    """测试6: 房主功能"""
    players = []
    try:
        # 连接2个玩家
        ws1 = await websockets.connect(f"{WS_URL}/Owner")
        msg = await asyncio.wait_for(ws1.recv(), timeout=2)
        owner_id = json.loads(msg).get('data', {}).get('player_id')
        players.append(ws1)
        
        ws2 = await websockets.connect(f"{WS_URL}/Player2")
        msg = await asyncio.wait_for(ws2.recv(), timeout=2)
        players.append(ws2)
        
        await asyncio.sleep(0.5)
        
        # 清空消息
        for ws in players:
            try:
                while True:
                    await asyncio.wait_for(ws.recv(), timeout=0.1)
            except asyncio.TimeoutError:
                pass
        
        # 开始游戏
        await ws1.send(json.dumps({"type": "start_game"}))
        await asyncio.sleep(1)
        
        # 清空消息
        for ws in players:
            try:
                while True:
                    await asyncio.wait_for(ws.recv(), timeout=0.1)
            except asyncio.TimeoutError:
                pass
        
        # 非房主尝试结束游戏
        await ws2.send(json.dumps({"type": "end_game"}))
        await asyncio.sleep(1)
        
        ended_by_non_owner = False
        for ws in players:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=0.5)
                if json.loads(msg).get('type') == 'game_ended':
                    ended_by_non_owner = True
            except asyncio.TimeoutError:
                pass
        
        if not ended_by_non_owner:
            result.add_pass("房主权限控制")
        else:
            result.add_fail("房主权限控制", "非房主能结束游戏")
        
        # 房主结束游戏
        await ws1.send(json.dumps({"type": "end_game"}))
        await asyncio.sleep(1)
        
        ended_by_owner = False
        final_results = None
        for ws in players:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=2)
                data = json.loads(msg)
                if data.get('type') == 'game_ended':
                    ended_by_owner = True
                    final_results = data.get('data')
            except asyncio.TimeoutError:
                pass
        
        if ended_by_owner:
            result.add_pass("房主结束游戏")
        else:
            result.add_fail("房主结束游戏", "房主无法结束游戏")
        
        if final_results and 'rankings' in final_results:
            result.add_pass("最终结果显示")
        else:
            result.add_fail("最终结果显示", "最终结果格式错误")
        
        for ws in players:
            await ws.close()
        
    except Exception as e:
        result.add_fail("房主功能", str(e))
        for ws in players:
            await ws.close()

async def test_ui_elements():
    """测试7: UI元素"""
    import requests
    
    try:
        # 测试主页加载
        response = requests.get("http://localhost:8000", timeout=5)
        if response.status_code == 200:
            html = response.text
            
            # 检查关键UI元素
            checks = [
                ("游戏信息栏", "game-info" in html),
                ("排行榜面板", "leaderboard-panel" in html),
                ("历史记录面板", "history-panel" in html),
                ("控制按钮", "start-btn" in html),
                ("扑克桌", "poker-table" in html),
            ]
            
            for name, check in checks:
                if check:
                    result.add_pass(f"UI元素: {name}")
                else:
                    result.add_fail(f"UI元素: {name}", "元素不存在")
        else:
            result.add_fail("页面加载", f"状态码: {response.status_code}")
    except Exception as e:
        result.add_fail("UI元素测试", str(e))

async def run_all_tests():
    """运行所有测试"""
    print("=" * 60)
    print("德州扑克游戏功能测试")
    print("=" * 60)
    print()
    
    # 测试1: 连接
    await test_connection()
    await asyncio.sleep(1)
    
    # 测试2-5: 多人游戏
    await test_multi_player_game()
    await asyncio.sleep(1)
    
    # 测试6: 房主功能
    await test_room_owner()
    await asyncio.sleep(1)
    
    # 测试7: UI元素
    await test_ui_elements()
    
    # 输出总结
    result.summary()

if __name__ == "__main__":
    try:
        asyncio.run(run_all_tests())
    except KeyboardInterrupt:
        print("\n测试被中断")
    except Exception as e:
        print(f"\n测试出错: {e}")
        import traceback
        traceback.print_exc()
