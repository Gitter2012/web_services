#!/usr/bin/env python3
"""
测试实时排行榜和房主结束游戏功能
"""
import asyncio
import json
import websockets
import requests
import time
from typing import List, Dict

BASE_URL = "http://localhost:8000"
WS_URL = "ws://localhost:8000/ws"

async def connect_player(player_id: str, name: str):
    """连接一个玩家"""
    uri = f"{WS_URL}/{player_id}?name={name}"
    return await websockets.connect(uri)

async def send_action(ws, action: str, amount: int = 0):
    """发送玩家动作"""
    message = {
        "type": "action",
        "action": action,
        "amount": amount
    }
    await ws.send(json.dumps(message))

async def receive_message(ws):
    """接收消息"""
    msg = await ws.recv()
    return json.loads(msg)

async def test_leaderboard_and_room_owner():
    """测试排行榜和房主功能"""
    print("=" * 60)
    print("开始测试实时排行榜和房主结束游戏功能")
    print("=" * 60)
    
    # 1. 连接3个玩家
    print("\n[测试1] 连接3个玩家...")
    players = []
    try:
        player1 = await connect_player("test_player_1", "Player1")
        players.append(("test_player_1", "Player1", player1))
        print("✓ Player1 已连接（应该是房主）")
        await asyncio.sleep(0.5)
        
        player2 = await connect_player("test_player_2", "Player2")
        players.append(("test_player_2", "Player2", player2))
        print("✓ Player2 已连接")
        await asyncio.sleep(0.5)
        
        player3 = await connect_player("test_player_3", "Player3")
        players.append(("test_player_3", "Player3", player3))
        print("✓ Player3 已连接")
        await asyncio.sleep(0.5)
        
    except Exception as e:
        print(f"✗ 连接玩家失败: {e}")
        return
    
    # 清空所有消息
    for pid, name, ws in players:
        try:
            while True:
                await asyncio.wait_for(ws.recv(), timeout=0.1)
        except asyncio.TimeoutError:
            pass
    
    # 2. 开始第一局游戏
    print("\n[测试2] 开始第一局游戏...")
    try:
        await players[0][2].send(json.dumps({"type": "start_game"}))
        await asyncio.sleep(1)
        print("✓ 游戏已开始")
        
        # 接收游戏状态
        for pid, name, ws in players:
            try:
                msg = await asyncio.wait_for(receive_message(ws), timeout=2)
                print(f"  {name} 收到消息: {msg.get('type')}")
            except asyncio.TimeoutError:
                print(f"  {name} 未收到消息")
        
    except Exception as e:
        print(f"✗ 开始游戏失败: {e}")
    
    # 3. 玩几局游戏以产生统计数据
    print("\n[测试3] 玩3局游戏以产生统计数据...")
    for round_num in range(3):
        print(f"\n  第 {round_num + 1} 局:")
        await asyncio.sleep(1)
        
        # 玩完整局游戏
        game_over = False
        action_count = 0
        max_actions = 30  # 防止无限循环
        
        while not game_over and action_count < max_actions:
            # 轮询所有玩家检查当前轮到谁
            for pid, name, ws in players:
                try:
                    # 尝试接收消息
                    msg = await asyncio.wait_for(receive_message(ws), timeout=0.5)
                    
                    if msg.get('type') == 'game_state':
                        game_state = msg.get('data', {})
                        current_player = game_state.get('current_player_id')
                        game_stage = game_state.get('game_stage')
                        
                        # 检查游戏是否结束
                        if game_stage == 'waiting':
                            game_over = True
                            print(f"    游戏结束")
                            break
                        
                        # 如果轮到这个玩家
                        if current_player == pid:
                            action_count += 1
                            min_bet = game_state.get('min_bet', 10)
                            
                            # 简化策略：Player1总是加注，Player2跟注，Player3弃牌
                            if name == "Player1":
                                await send_action(ws, "raise", min_bet + 10)
                                print(f"    {name}: raise {min_bet + 10}")
                            elif name == "Player2":
                                await send_action(ws, "call")
                                print(f"    {name}: call")
                            else:
                                await send_action(ws, "fold")
                                print(f"    {name}: fold")
                            
                            await asyncio.sleep(0.3)
                            
                except asyncio.TimeoutError:
                    pass
                except Exception as e:
                    print(f"    {name} 操作出错: {e}")
            
            if game_over:
                break
            
            await asyncio.sleep(0.2)
        
        print(f"    完成 {action_count} 个动作")
        
        # 等待自动开始下一局
        if round_num < 2:
            print("    等待自动开始下一局...")
            await asyncio.sleep(6)
    
    print("\n✓ 3局游戏已完成")
    
    # 4. 测试排行榜数据
    print("\n[测试4] 检查排行榜数据...")
    try:
        # 等待一下确保数据更新
        await asyncio.sleep(1)
        
        # 接收最新的游戏状态
        for pid, name, ws in players:
            try:
                # 清空旧消息
                while True:
                    await asyncio.wait_for(ws.recv(), timeout=0.1)
            except asyncio.TimeoutError:
                pass
        
        # 请求游戏状态
        await players[0][2].send(json.dumps({"type": "get_state"}))
        await asyncio.sleep(0.5)
        
        msg = await asyncio.wait_for(receive_message(players[0][2]), timeout=2)
        if msg.get('type') == 'game_state':
            game_state = msg.get('data', {})
            players_data = game_state.get('players', [])
            
            print(f"\n  排行榜数据:")
            print(f"  {'玩家':<10} {'筹码':<10} {'总输赢':<10} {'场次':<8} {'获胜':<8} {'胜率':<10} {'补码次数':<10}")
            print("  " + "-" * 80)
            
            for p in players_data:
                win_rate = (p['games_won'] / p['games_played'] * 100) if p['games_played'] > 0 else 0
                print(f"  {p['name']:<10} {p['chips']:<10} {p['total_win']:<10} {p['games_played']:<8} {p['games_won']:<8} {win_rate:<10.1f}% {p['rebuys']:<10}")
            
            # 检查是否有统计数据
            has_stats = any(p['games_played'] > 0 for p in players_data)
            if has_stats:
                print("\n✓ 排行榜数据正常更新")
            else:
                print("\n✗ 排行榜数据未更新")
        else:
            print(f"✗ 未收到游戏状态: {msg.get('type')}")
            
    except Exception as e:
        print(f"✗ 检查排行榜数据失败: {e}")
    
    # 5. 测试房主结束游戏功能
    print("\n[测试5] 测试房主结束游戏功能...")
    
    # 5.1 非房主尝试结束游戏（应该失败）
    print("\n  5.1 - 非房主尝试结束游戏...")
    try:
        await players[1][2].send(json.dumps({"type": "end_game"}))
        await asyncio.sleep(1)
        
        # 检查是否收到game_ended消息
        game_ended = False
        for pid, name, ws in players:
            try:
                msg = await asyncio.wait_for(receive_message(ws), timeout=1)
                if msg.get('type') == 'game_ended':
                    game_ended = True
            except asyncio.TimeoutError:
                pass
        
        if not game_ended:
            print("  ✓ 非房主无法结束游戏（符合预期）")
        else:
            print("  ✗ 非房主能够结束游戏（不符合预期）")
    except Exception as e:
        print(f"  ✗ 测试非房主结束游戏出错: {e}")
    
    # 5.2 房主结束游戏（应该成功）
    print("\n  5.2 - 房主结束游戏...")
    try:
        await players[0][2].send(json.dumps({"type": "end_game"}))
        await asyncio.sleep(1)
        
        # 检查所有玩家是否收到game_ended消息
        results = []
        for pid, name, ws in players:
            try:
                msg = await asyncio.wait_for(receive_message(ws), timeout=2)
                if msg.get('type') == 'game_ended':
                    results.append(msg.get('data'))
                    print(f"  ✓ {name} 收到游戏结束消息")
            except asyncio.TimeoutError:
                print(f"  ✗ {name} 未收到游戏结束消息")
        
        if results:
            print("\n  ✓ 房主成功结束游戏")
            print("\n  最终排名:")
            final_data = results[0]
            
            # 处理新的数据格式
            if isinstance(final_data, dict) and 'rankings' in final_data:
                rankings = final_data['rankings']
                total_games = final_data.get('total_games', 0)
                print(f"  总共进行了 {total_games} 局游戏\n")
            else:
                rankings = final_data if isinstance(final_data, list) else []
            
            print(f"  {'排名':<6} {'玩家':<10} {'筹码':<10} {'总输赢':<10} {'场次':<8} {'获胜':<8} {'胜率':<10} {'补码':<10}")
            print("  " + "-" * 90)
            
            for result in rankings:
                win_rate = result.get('win_rate', 0)
                medal = ""
                if result['rank'] == 1:
                    medal = "🥇"
                elif result['rank'] == 2:
                    medal = "🥈"
                elif result['rank'] == 3:
                    medal = "🥉"
                
                # 兼容两种字段名
                name = result.get('name', result.get('player_name', 'Unknown'))
                chips = result.get('chips', result.get('final_chips', 0))
                
                print(f"  {medal} {result['rank']:<4} {name:<10} {chips:<10} {result['total_win']:<10} {result['games_played']:<8} {result['games_won']:<8} {win_rate:<10.1f}% {result['rebuys']:<10}")
            
        else:
            print("  ✗ 未收到最终结果")
            
    except Exception as e:
        print(f"  ✗ 房主结束游戏失败: {e}")
    
    # 关闭连接
    print("\n[清理] 关闭所有连接...")
    for pid, name, ws in players:
        await ws.close()
    
    print("\n" + "=" * 60)
    print("测试完成!")
    print("=" * 60)

if __name__ == "__main__":
    # 检查服务器是否运行
    try:
        response = requests.get(BASE_URL)
        print(f"服务器状态: {response.status_code}")
    except Exception as e:
        print(f"错误: 无法连接到服务器 {BASE_URL}")
        print(f"请确保服务器正在运行: python main.py")
        exit(1)
    
    # 运行测试
    asyncio.run(test_leaderboard_and_room_owner())
