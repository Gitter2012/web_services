#!/usr/bin/env python3
"""
简化调试测试
"""
import asyncio
import json
import websockets

async def test():
    print("连接3个玩家...")
    ws1 = await websockets.connect("ws://localhost:8000/ws/Alice")
    ws2 = await websockets.connect("ws://localhost:8000/ws/Bob")
    ws3 = await websockets.connect("ws://localhost:8000/ws/Charlie")
    
    # 获取player_id
    msg1 = json.loads(await ws1.recv())
    alice_id = msg1['data']['player_id']
    msg2 = json.loads(await ws2.recv())
    bob_id = msg2['data']['player_id']
    msg3 = json.loads(await ws3.recv())
    charlie_id = msg3['data']['player_id']
    
    print(f"Alice: {alice_id[:8]}")
    print(f"Bob: {bob_id[:8]}")
    print(f"Charlie: {charlie_id[:8]}")
    
    # 清空消息
    await asyncio.sleep(1)
    for ws in [ws1, ws2, ws3]:
        while True:
            try:
                await asyncio.wait_for(ws.recv(), timeout=0.1)
            except:
                break
    
    print("\n开始游戏...")
    await ws1.send(json.dumps({"type": "start_game"}))
    await asyncio.sleep(2)
    
    # 清空start消息
    for ws in [ws1, ws2, ws3]:
        while True:
            try:
                await asyncio.wait_for(ws.recv(), timeout=0.1)
            except:
                break
    
    print("玩游戏（最多20个动作）...")
    for i in range(20):
        print(f"\n回合 {i+1}:")
        for ws, name, pid in [(ws1, "Alice", alice_id), (ws2, "Bob", bob_id), (ws3, "Charlie", charlie_id)]:
            try:
                msg_str = await asyncio.wait_for(ws.recv(), timeout=2)
                msg = json.loads(msg_str)
                
                if msg['type'] == 'game_state':
                    data = msg['data']
                    stage = data['game_stage']
                    current = data['current_player_id']
                    
                    print(f"  {name}: stage={stage}, current={current[:8] if current else 'none'}")
                    
                    if stage == 'waiting':
                        print("游戏结束!")
                        goto_end = True
                        break
                    
                    if current == pid:
                        min_bet = data['min_bet']
                        action = "call" if min_bet > 0 else "check"
                        await ws.send(json.dumps({"type": "action", "action": action}))
                        print(f"    -> {name} {action}")
                        await asyncio.sleep(0.3)
            except asyncio.TimeoutError:
                pass
        
        if 'goto_end' in locals():
            break
        await asyncio.sleep(0.2)
    
    print("\n检查最终状态...")
    await ws1.send(json.dumps({"type": "get_state"}))
    await asyncio.sleep(0.5)
    
    msg = json.loads(await ws1.recv())
    if msg['type'] == 'game_state':
        for p in msg['data']['players']:
            print(f"{p['name']}: games_played={p['games_played']}, total_win={p['total_win']}")
    
    print("\n房主结束游戏...")
    await ws1.send(json.dumps({"type": "end_game"}))
    await asyncio.sleep(1)
    
    for ws, name in [(ws1, "Alice"), (ws2, "Bob"), (ws3, "Charlie")]:
        try:
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=1))
            if msg['type'] == 'game_ended':
                print(f"✓ {name} 收到game_ended")
                if name == "Alice":
                    rankings = msg['data']['rankings']
                    print(f"\n最终排名:")
                    for r in rankings:
                        print(f"  {r['rank']}. {r['player_name']}: {r['total_win']}")
        except asyncio.TimeoutError:
            print(f"✗ {name} 没收到")
    
    await ws1.close()
    await ws2.close()
    await ws3.close()
    
    print("\n完成!")

if __name__ == "__main__":
    asyncio.run(test())
