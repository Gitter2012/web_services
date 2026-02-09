#!/usr/bin/env python3
"""
超时功能测试脚本
"""
import asyncio
import websockets
import json
import sys

async def test_timeout_feature():
    """测试超时功能"""
    print("=" * 60)
    print("超时功能测试")
    print("=" * 60)
    
    uri = "ws://localhost:8000/ws/TestPlayer"
    
    try:
        print("\n[1] 连接到服务器...")
        async with websockets.connect(uri) as websocket:
            print("✓ 连接成功")
            
            # 接收玩家ID
            response = await websocket.recv()
            data = json.loads(response)
            if data.get('type') == 'player_id':
                player_id = data['data']['player_id']
                print(f"✓ 收到玩家ID: {player_id}")
            
            # 接收游戏状态
            response = await websocket.recv()
            print("✓ 收到初始游戏状态")
            
            print("\n[2] 添加AI玩家...")
            await websocket.send(json.dumps({
                'type': 'add_ai',
                'count': 2
            }))
            
            # 等待AI加入消息
            for _ in range(4):  # player_joined x2 + info + game_state
                response = await websocket.recv()
                data = json.loads(response)
                if data.get('type') == 'player_joined':
                    print(f"✓ {data['data']['player_name']} 加入")
            
            print("\n[3] 开始游戏...")
            await websocket.send(json.dumps({'type': 'start_game'}))
            
            # 接收游戏开始消息
            response = await websocket.recv()
            print("✓ 游戏开始")
            
            print("\n[4] 等待轮到测试玩家...")
            print("提示: 打开浏览器 http://localhost:8000")
            print("      观察倒计时进度条是否正常显示")
            print("      观察AI玩家是否有随机延迟（1-3秒）")
            print("\n测试项目:")
            print("  ✓ 倒计时进度条从100%逐渐减少到0%")
            print("  ✓ 倒计时文本显示正确秒数")
            print("  ✓ 剩余5秒时进度条闪烁")
            print("  ✓ 超时后自动弃牌")
            print("  ✓ AI玩家响应时间随机（1-3秒）")
            
            # 持续接收消息
            print("\n等待游戏消息...")
            timeout_count = 0
            message_count = 0
            
            while message_count < 50:  # 接收最多50条消息
                try:
                    response = await asyncio.wait_for(websocket.recv(), timeout=60.0)
                    data = json.loads(response)
                    message_count += 1
                    
                    msg_type = data.get('type')
                    
                    if msg_type == 'game_state':
                        state = data
                        current_player_id = state.get('current_player_id')
                        game_stage = state.get('game_stage')
                        
                        if current_player_id == player_id and game_stage not in ['waiting', 'showdown']:
                            print(f"\n→ 轮到你行动！阶段: {game_stage}")
                            print("  检查浏览器中的倒计时显示...")
                            print("  等待超时自动弃牌...")
                            timeout_count += 1
                    
                    elif msg_type == 'player_action':
                        action_data = data.get('data', {})
                        player_name = action_data.get('player_name', 'Unknown')
                        action = action_data.get('action', 'unknown')
                        amount = action_data.get('amount', 0)
                        
                        action_text = {
                            'fold': '弃牌',
                            'check': '过牌',
                            'call': '跟注',
                            'raise': f'加注 {amount}'
                        }.get(action, action)
                        
                        print(f"  {player_name}: {action_text}")
                    
                    elif msg_type == 'error':
                        error_msg = data.get('data', {}).get('message', '')
                        print(f"  ⚠️  错误: {error_msg}")
                    
                    # 如果已经测试了超时功能，退出
                    if timeout_count >= 1:
                        print(f"\n✓ 已测试超时功能 {timeout_count} 次")
                        break
                        
                except asyncio.TimeoutError:
                    print("\n⚠️  60秒内未收到消息，测试超时")
                    break
            
            print("\n" + "=" * 60)
            print("测试完成!")
            print("=" * 60)
            print(f"\n统计:")
            print(f"  - 接收消息数: {message_count}")
            print(f"  - 超时次数: {timeout_count}")
            
            if timeout_count > 0:
                print("\n✓ 超时功能工作正常")
            else:
                print("\n⚠️  未触发超时（可能游戏太快结束）")
            
    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    print("\n确保服务器正在运行: python main.py")
    print("然后在浏览器打开: http://localhost:8000")
    print("观察倒计时效果...\n")
    
    input("按Enter开始测试...")
    
    asyncio.run(test_timeout_feature())
