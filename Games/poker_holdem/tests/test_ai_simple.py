#!/usr/bin/env python3
"""
简单的AI自动行动测试
"""
import asyncio
import websockets
import json

async def test_ai_auto_action():
    """测试AI自动行动"""
    print("测试AI自动行动...")

    # 连接第一个玩家
    ws = await websockets.connect("ws://127.0.0.1:8000/ws/TestUser")
    print("✓ 玩家已连接")

    # 获取玩家ID
    msg = await ws.recv()
    data = json.loads(msg)
    player_id = data['data']['player_id']
    print(f"✓ 玩家ID: {player_id[:8]}...")

    # 清空初始消息
    for _ in range(5):
        try:
            await asyncio.wait_for(ws.recv(), timeout=0.5)
        except asyncio.TimeoutError:
            break

    # 添加1个AI玩家
    await ws.send(json.dumps({"type": "add_ai", "count": 1}))
    await asyncio.sleep(1)
    print("✓ 已添加1个AI玩家")

    # 开始游戏
    await ws.send(json.dumps({"type": "start_game"}))
    await asyncio.sleep(1)
    print("✓ 开始游戏")

    # 玩家不做操作，等待AI自动行动
    print("等待AI自动行动...")

    actions = 0
    game_stages = []

    for i in range(40):  # 最多等待40秒
        try:
            msg = await asyncio.wait_for(ws.recv(), timeout=1)
            data = json.loads(msg)

            if data.get('type') == 'game_state':
                state = data['data']
                game_stages.append(state['game_stage'])

                # 打印游戏状态
                if state['game_stage'] != 'waiting':
                    print(f"  [{state['game_stage']}] 底池: {state['pot']}, 当前玩家: {state.get('current_player_id', 'N/A')[:8]}...")

            elif data.get('type') == 'player_action':
                action = data['data']
                actions += 1
                print(f"  {action['player_name']} {action['action']} {action['amount']}")

                # 如果是AI行动，说明功能正常
                if action['player_name'].startswith('机器人'):
                    print("✅ AI自动行动成功！")
                    await ws.close()
                    return True

            # 如果游戏进入showdown，说明游戏完成了
            if 'showdown' in game_stages:
                print("✅ 游戏完成")
                break

        except asyncio.TimeoutError:
            continue

    await ws.close()

    if actions > 0:
        print(f"\n✅ 测试成功！共有 {actions} 次操作")
        return True
    else:
        print("\n⚠️ AI没有自动行动")
        return False

if __name__ == "__main__":
    result = asyncio.run(test_ai_auto_action())
    print(f"\n最终结果: {'成功' if result else '失败'}")
