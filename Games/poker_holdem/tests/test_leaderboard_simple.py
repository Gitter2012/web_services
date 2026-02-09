#!/usr/bin/env python3
"""
简化的排行榜和房主功能测试
"""
import asyncio
import json
import websockets
import requests

BASE_URL = "http://localhost:8000"
WS_URL = "ws://localhost:8000/ws"

async def test_simple():
    print("=" * 60)
    print("测试实时排行榜和房主结束游戏功能")
    print("=" * 60)
    
    # 连接3个玩家
    print("\n[1] 连接玩家...")
    ws1 = await websockets.connect(f"{WS_URL}/Alice")
    print("✓ Alice 已连接（房主）")
    
    ws2 = await websockets.connect(f"{WS_URL}/Bob")
    print("✓ Bob 已连接")
    
    ws3 = await websockets.connect(f"{WS_URL}/Charlie")
    print("✓ Charlie 已连接")
    
    await asyncio.sleep(1)
    
    # 清空初始消息
    for ws in [ws1, ws2, ws3]:
        try:
            while True:
                await asyncio.wait_for(ws.recv(), timeout=0.1)
        except asyncio.TimeoutError:
            pass
    
    # 开始游戏
    print("\n[2] 开始游戏...")
    await ws1.send(json.dumps({"type": "start_game"}))
    await asyncio.sleep(1)
    print("✓ 游戏已开始")
    
    # 玩一局简单的游戏
    print("\n[3] 玩一局游戏...")
    game_over = False
    
    async def handle_player(ws, pid):
        nonlocal game_over
        while not game_over:
            try:
                msg_str = await asyncio.wait_for(ws.recv(), timeout=0.5)
                msg = json.loads(msg_str)
                
                if msg.get('type') == 'game_state':
                    data = msg.get('data', {})
                    current = data.get('current_player_id')
                    stage = data.get('game_stage')
                    
                    if stage == 'waiting':
                        game_over = True
                        print("✓ 游戏结束")
                        return
                    
                    if current == pid:
                        # 简单策略：都跟注或过牌
                        min_bet = data.get('min_bet', 0)
                        if min_bet > 0:
                            await ws.send(json.dumps({"type": "action", "action": "call"}))
                        else:
                            await ws.send(json.dumps({"type": "action", "action": "check"}))
                        await asyncio.sleep(0.2)
            except asyncio.TimeoutError:
                pass
            except Exception as e:
                pass
    
    # 获取玩家ID
    player_ids = {}
    for ws, name in [(ws1, "Alice"), (ws2, "Bob"), (ws3, "Charlie")]:
        try:
            msg_str = await asyncio.wait_for(ws.recv(), timeout=2)
            msg = json.loads(msg_str)
            if msg.get('type') == 'game_state':
                players = msg.get('data', {}).get('players', [])
                for p in players:
                    if p['name'] == name:
                        player_ids[name] = p['id']
                        break
        except:
            pass
    
    # 并发处理所有玩家
    await asyncio.gather(
        handle_player(ws1, player_ids.get("Alice")),
        handle_player(ws2, player_ids.get("Bob")),
        handle_player(ws3, player_ids.get("Charlie"))
    )
    
    await asyncio.sleep(2)
    
    # 检查统计数据
    print("\n[4] 检查排行榜数据...")
    await ws1.send(json.dumps({"type": "get_state"}))
    await asyncio.sleep(0.5)
    
    try:
        msg_str = await asyncio.wait_for(ws1.recv(), timeout=2)
        msg = json.loads(msg_str)
        if msg.get('type') == 'game_state':
            players = msg.get('data', {}).get('players', [])
            print(f"\n玩家统计:")
            for p in players:
                print(f"  {p['name']}: 筹码={p['chips']}, 总输赢={p['total_win']}, "
                      f"场次={p['games_played']}, 获胜={p['games_won']}")
            
            has_data = any(p['games_played'] > 0 for p in players)
            if has_data:
                print("\n✓ 排行榜数据正常")
            else:
                print("\n⚠ 排行榜数据为空")
    except Exception as e:
        print(f"✗ 获取统计失败: {e}")
    
    # 测试非房主结束游戏
    print("\n[5] 测试非房主结束游戏...")
    await ws2.send(json.dumps({"type": "end_game"}))
    await asyncio.sleep(1)
    
    # 检查是否收到game_ended
    got_ended = False
    for ws in [ws1, ws2, ws3]:
        try:
            msg_str = await asyncio.wait_for(ws.recv(), timeout=0.5)
            msg = json.loads(msg_str)
            if msg.get('type') == 'game_ended':
                got_ended = True
        except:
            pass
    
    if not got_ended:
        print("✓ 非房主无法结束游戏")
    else:
        print("✗ 非房主能够结束游戏")
    
    # 测试房主结束游戏
    print("\n[6] 测试房主结束游戏...")
    await ws1.send(json.dumps({"type": "end_game"}))
    await asyncio.sleep(1)
    
    # 检查最终结果
    results_received = []
    for ws, name in [(ws1, "Alice"), (ws2, "Bob"), (ws3, "Charlie")]:
        try:
            msg_str = await asyncio.wait_for(ws.recv(), timeout=1)
            msg = json.loads(msg_str)
            if msg.get('type') == 'game_ended':
                results_received.append((name, msg.get('data')))
                print(f"✓ {name} 收到游戏结束消息")
        except:
            print(f"✗ {name} 未收到消息")
    
    if results_received:
        print("\n✓ 房主成功结束游戏")
        data = results_received[0][1]
        
        if isinstance(data, dict) and 'rankings' in data:
            print(f"\n最终结果 (总共 {data.get('total_games', 0)} 局):")
            print(f"{'排名':<6} {'玩家':<10} {'总输赢':<10} {'筹码':<10} {'胜率'}")
            print("-" * 60)
            for r in data['rankings']:
                medal = ['🥇', '🥈', '🥉'][r['rank']-1] if r['rank'] <= 3 else str(r['rank'])
                print(f"{medal:<6} {r['player_name']:<10} {r['total_win']:<10} "
                      f"{r['final_chips']:<10} {r['win_rate']:.1f}%")
        else:
            print("⚠ 结果格式异常")
    else:
        print("✗ 未收到最终结果")
    
    # 关闭连接
    await ws1.close()
    await ws2.close()
    await ws3.close()
    
    print("\n" + "=" * 60)
    print("测试完成!")
    print("=" * 60)

if __name__ == "__main__":
    try:
        requests.get(BASE_URL, timeout=2)
        asyncio.run(test_simple())
    except Exception as e:
        print(f"错误: 无法连接到服务器")
        print("请确保服务器正在运行: python main.py")
