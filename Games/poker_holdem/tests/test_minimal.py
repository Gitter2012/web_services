#!/usr/bin/env python3
"""
最小化测试 - 只测试连接和基本交互
"""
import asyncio
import json
import websockets

async def test():
    print("连接到服务器...")
    ws = await websockets.connect("ws://localhost:8000/ws/TestPlayer")
    print("✓ 连接成功")
    
    # 接收初始消息
    print("\n接收消息...")
    for i in range(5):
        try:
            msg = await asyncio.wait_for(ws.recv(), timeout=2)
            data = json.loads(msg)
            print(f"  消息 {i+1}: type={data.get('type')}")
            
            if data.get('type') == 'game_state':
                game_data = data.get('data', {})
                print(f"    - 游戏阶段: {game_data.get('game_stage')}")
                print(f"    - 玩家数: {len(game_data.get('players', []))}")
                break
        except asyncio.TimeoutError:
            print(f"  超时 {i+1}")
            break
        except Exception as e:
            print(f"  错误: {e}")
            break
    
    await ws.close()
    print("\n✓ 测试完成")

if __name__ == "__main__":
    asyncio.run(test())
