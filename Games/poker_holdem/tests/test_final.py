#!/usr/bin/env python3
"""
排行榜和房主功能测试 - 完整版
"""
import asyncio
import json
import websockets

WS_URL = "ws://localhost:8000/ws"

async def recv_until(ws, target_type, timeout=5):
    """接收消息直到找到指定类型"""
    try:
        msg_str = await asyncio.wait_for(ws.recv(), timeout=timeout)
        msg = json.loads(msg_str)
        return msg
    except asyncio.TimeoutError:
        return None

async def test():
    print("=" * 70)
    print("测试实时排行榜和房主结束游戏功能")
    print("=" * 70)
    
    # 1. 连接3个玩家
    print("\n[1] 连接3个玩家...")
    ws1 = await websockets.connect(f"{WS_URL}/Alice")
    msg = await recv_until(ws1, "player_id")
    alice_id = msg.get('data', {}).get('player_id') if msg else None
    print(f"✓ Alice 已连接 (ID: {alice_id[:8] if alice_id else 'unknown'}..., 应为房主)")
    await asyncio.sleep(0.5)
    
    ws2 = await websockets.connect(f"{WS_URL}/Bob")
    msg = await recv_until(ws2, "player_id")
    bob_id = msg.get('data', {}).get('player_id') if msg else None
    print(f"✓ Bob 已连接 (ID: {bob_id[:8] if bob_id else 'unknown'}...)")
    await asyncio.sleep(0.5)
    
    ws3 = await websockets.connect(f"{WS_URL}/Charlie")
    msg = await recv_until(ws3, "player_id")
    charlie_id = msg.get('data', {}).get('player_id') if msg else None
    print(f"✓ Charlie 已连接 (ID: {charlie_id[:8] if charlie_id else 'unknown'}...)")
    await asyncio.sleep(0.5)
    
    # 清空初始消息
    for ws in [ws1, ws2, ws3]:
        while True:
            try:
                await asyncio.wait_for(ws.recv(), timeout=0.1)
            except asyncio.TimeoutError:
                break
    
    # 2. 开始游戏
    print("\n[2] 开始游戏...")
    await ws1.send(json.dumps({"type": "start_game"}))
    await asyncio.sleep(2)
    print("✓ 游戏已开始")
    
    # 清空start消息
    for ws in [ws1, ws2, ws3]:
        while True:
            try:
                await asyncio.wait_for(ws.recv(), timeout=0.1)
            except asyncio.TimeoutError:
                break
    
    # 3. 玩一局游戏（简单策略）
    print("\n[3] 玩一局游戏...")
    
    async def play_game(ws, player_id, name):
        actions = 0
        while actions < 20:
            try:
                msg_str = await asyncio.wait_for(ws.recv(), timeout=15)
                msg = json.loads(msg_str)
                
                if msg.get('type') == 'game_state':
                    data = msg['data']
                    if data['game_stage'] == 'waiting':
                        return True
                    
                    if data['current_player_id'] == player_id:
                        actions += 1
                        # 简单策略：都选择check或call
                        if data['min_bet'] > 0:
                            await ws.send(json.dumps({"type": "action", "action": "call"}))
                            print(f"  {name}: call")
                        else:
                            await ws.send(json.dumps({"type": "action", "action": "check"}))
                            print(f"  {name}: check")
            except asyncio.TimeoutError:
                return False
        return False
    
    results = await asyncio.gather(
        play_game(ws1, alice_id, "Alice"),
        play_game(ws2, bob_id, "Bob"),
        play_game(ws3, charlie_id, "Charlie"),
        return_exceptions=True
    )
    
    if any(results):
        print("✓ 游戏已完成")
    else:
        print("⚠ 游戏未正常完成")
    
    await asyncio.sleep(1)
    
    # 4. 检查排行榜数据
    print("\n[4] 检查排行榜数据...")
    
    # 清空消息
    for ws in [ws1, ws2, ws3]:
        while True:
            try:
                await asyncio.wait_for(ws.recv(), timeout=0.1)
            except asyncio.TimeoutError:
                break
    
    # 请求游戏状态
    await ws1.send(json.dumps({"type": "get_state"}))
    await asyncio.sleep(0.5)
    
    msg = await recv_until(ws1, "game_state", 2)
    if msg and msg.get('type') == 'game_state':
        players = msg['data']['players']
        print(f"\n  {'玩家':<10} {'筹码':<8} {'总输赢':<8} {'场次':<6} {'获胜':<6} {'胜率'}")
        print("  " + "-" * 60)
        for p in players:
            rate = (p['games_won']/p['games_played']*100) if p['games_played'] > 0 else 0
            print(f"  {p['name']:<10} {p['chips']:<8} {p['total_win']:<8} "
                  f"{p['games_played']:<6} {p['games_won']:<6} {rate:.1f}%")
        
        has_stats = any(p['games_played'] > 0 for p in players)
        if has_stats:
            print("\n✓ 排行榜数据正常更新")
        else:
            print("\n⚠ 排行榜数据未更新（可能游戏未完成）")
    else:
        print("✗ 无法获取排行榜数据")
    
    # 5. 测试非房主结束游戏
    print("\n[5] 测试非房主结束游戏...")
    
    # 清空消息
    for ws in [ws1, ws2, ws3]:
        while True:
            try:
                await asyncio.wait_for(ws.recv(), timeout=0.1)
            except asyncio.TimeoutError:
                break
    
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
                break
        except:
            pass
    
    if not got_ended:
        print("✓ 非房主无法结束游戏（符合预期）")
    else:
        print("✗ 非房主能够结束游戏（不符合预期）")
    
    # 6. 测试房主结束游戏
    print("\n[6] 测试房主结束游戏...")
    
    await ws1.send(json.dumps({"type": "end_game"}))
    await asyncio.sleep(1)
    
    # 接收最终结果
    final_results = None
    for ws, name in [(ws1, "Alice"), (ws2, "Bob"), (ws3, "Charlie")]:
        try:
            msg_str = await asyncio.wait_for(ws.recv(), timeout=2)
            msg = json.loads(msg_str)
            if msg.get('type') == 'game_ended':
                final_results = msg.get('data')
                print(f"✓ {name} 收到游戏结束消息")
        except asyncio.TimeoutError:
            print(f"✗ {name} 未收到游戏结束消息")
    
    # 显示最终结果
    if final_results:
        print("\n✓ 房主成功结束游戏")
        
        if isinstance(final_results, dict) and 'rankings' in final_results:
            print(f"\n  最终排名 (总共 {final_results.get('total_games', 0)} 局游戏):")
            print(f"  {'排名':<6} {'玩家':<12} {'总输赢':<10} {'筹码':<10} {'胜率':<10} {'战绩'}")
            print("  " + "-" * 70)
            
            for r in final_results['rankings']:
                medals = {1: '🥇', 2: '🥈', 3: '🥉'}
                medal = medals.get(r['rank'], f"  {r['rank']}")
                print(f"  {medal:<6} {r['player_name']:<12} {r['total_win']:<10} "
                      f"{r['final_chips']:<10} {r['win_rate']:.1f}%{'':<5} "
                      f"{r['games_won']}/{r['games_played']}")
        else:
            print(f"\n⚠ 结果格式异常: {type(final_results)}")
    else:
        print("\n✗ 未收到最终结果")
    
    # 清理
    await ws1.close()
    await ws2.close()
    await ws3.close()
    
    print("\n" + "=" * 70)
    print("测试完成!")
    print("=" * 70)

if __name__ == "__main__":
    try:
        asyncio.run(test())
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
