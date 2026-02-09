"""
WebSocket客户端测试脚本
模拟多个玩家进行游戏
"""
import asyncio
import websockets
import json


async def test_websocket_client():
    """测试WebSocket连接和游戏流程"""
    print("=" * 60)
    print("测试WebSocket连接和游戏流程")
    print("=" * 60)
    
    # 创建两个玩家的WebSocket连接
    player1_ws = None
    player2_ws = None
    
    try:
        # 玩家1连接
        print("\n玩家1正在连接...")
        player1_ws = await websockets.connect('ws://localhost:8000/ws/玩家1')
        print("✓ 玩家1连接成功")
        
        # 接收玩家1的ID
        msg = await player1_ws.recv()
        data = json.loads(msg)
        print(f"玩家1收到消息: {data['type']}")
        player1_id = data['data']['player_id'] if data['type'] == 'player_id' else None
        
        # 玩家2连接
        print("\n玩家2正在连接...")
        player2_ws = await websockets.connect('ws://localhost:8000/ws/玩家2')
        print("✓ 玩家2连接成功")
        
        # 接收玩家2的ID和消息
        msg = await player2_ws.recv()
        data = json.loads(msg)
        print(f"玩家2收到消息: {data['type']}")
        player2_id = data['data']['player_id'] if data['type'] == 'player_id' else None
        
        # 清空初始消息
        await asyncio.sleep(0.5)
        while True:
            try:
                msg = await asyncio.wait_for(player1_ws.recv(), timeout=0.1)
                data = json.loads(msg)
                print(f"[玩家1] {data['type']}")
            except asyncio.TimeoutError:
                break
        
        while True:
            try:
                msg = await asyncio.wait_for(player2_ws.recv(), timeout=0.1)
                data = json.loads(msg)
                print(f"[玩家2] {data['type']}")
            except asyncio.TimeoutError:
                break
        
        # 玩家1开始游戏
        print("\n玩家1发起开始游戏请求...")
        await player1_ws.send(json.dumps({"type": "start_game"}))
        
        # 等待游戏开始的消息
        await asyncio.sleep(0.5)
        
        # 接收游戏状态
        print("\n接收游戏开始消息...")
        for i in range(5):
            try:
                msg = await asyncio.wait_for(player1_ws.recv(), timeout=1)
                data = json.loads(msg)
                print(f"[玩家1] 收到: {data['type']}")
                if data['type'] == 'game_state':
                    state = data['data']
                    print(f"  - 游戏阶段: {state['game_stage']}")
                    print(f"  - 底池: {state['pot']}")
                    print(f"  - 当前玩家: {state['current_player_id']}")
                    
                    # 如果是当前玩家，执行操作
                    if state['current_player_id'] == player1_id:
                        print("  - 玩家1轮到操作，选择跟注")
                        await player1_ws.send(json.dumps({
                            "type": "action",
                            "action": "call"
                        }))
                    break
            except asyncio.TimeoutError:
                break
        
        # 玩家2接收消息并操作
        print("\n玩家2接收消息...")
        for i in range(5):
            try:
                msg = await asyncio.wait_for(player2_ws.recv(), timeout=1)
                data = json.loads(msg)
                print(f"[玩家2] 收到: {data['type']}")
                if data['type'] == 'game_state':
                    state = data['data']
                    print(f"  - 游戏阶段: {state['game_stage']}")
                    print(f"  - 底池: {state['pot']}")
                    print(f"  - 当前玩家: {state['current_player_id']}")
                    
                    if state['current_player_id'] == player2_id:
                        # 找到玩家2的信息
                        player2_info = None
                        for p in state['players']:
                            if p['id'] == player2_id:
                                player2_info = p
                                break
                        
                        # 根据情况选择操作
                        if player2_info and player2_info['bet'] < state['current_bet']:
                            print("  - 玩家2轮到操作，需要跟注")
                            await player2_ws.send(json.dumps({
                                "type": "action",
                                "action": "call"
                            }))
                        else:
                            print("  - 玩家2轮到操作，选择过牌")
                            await player2_ws.send(json.dumps({
                                "type": "action",
                                "action": "check"
                            }))
            except asyncio.TimeoutError:
                break
        
        # 等待更多消息
        await asyncio.sleep(1)
        
        print("\n✓ WebSocket测试完成")
        
    except Exception as e:
        print(f"\n✗ 测试出错: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        # 关闭连接
        if player1_ws:
            await player1_ws.close()
            print("\n玩家1断开连接")
        if player2_ws:
            await player2_ws.close()
            print("玩家2断开连接")


async def test_connection_only():
    """测试基本连接"""
    print("\n" + "=" * 60)
    print("测试基本WebSocket连接")
    print("=" * 60)
    
    try:
        print("\n正在连接到服务器...")
        ws = await websockets.connect('ws://localhost:8000/ws/测试玩家')
        print("✓ 连接成功")
        
        # 接收消息
        msg = await asyncio.wait_for(ws.recv(), timeout=2)
        data = json.loads(msg)
        print(f"✓ 收到消息: {data['type']}")
        
        await ws.close()
        print("✓ 断开连接成功")
        
    except asyncio.TimeoutError:
        print("✗ 接收消息超时")
    except Exception as e:
        print(f"✗ 连接失败: {e}")


def main():
    """运行测试"""
    print("\n" + "=" * 60)
    print("开始WebSocket测试")
    print("=" * 60)
    
    # 测试基本连接
    asyncio.run(test_connection_only())
    
    # 测试游戏流程
    asyncio.run(test_websocket_client())
    
    print("\n" + "=" * 60)
    print("测试结束")
    print("=" * 60)


if __name__ == "__main__":
    main()
