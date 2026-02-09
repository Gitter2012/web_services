#!/usr/bin/env python3
"""
完整游戏流程测试 - 测试补码和统计功能
"""
import asyncio
import websockets
import json

class GamePlayer:
    def __init__(self, name):
        self.name = name
        self.ws = None
        self.player_id = None
        self.game_state = None
        
    async def connect(self):
        uri = f"ws://localhost:8000/ws/{self.name}"
        self.ws = await websockets.connect(uri)
        
    async def receive_messages(self):
        """持续接收消息"""
        async for message in self.ws:
            data = json.loads(message)
            
            if data['type'] == 'player_id':
                self.player_id = data['data']['player_id']
                print(f"✅ {self.name} 已连接")
                
            elif data['type'] == 'game_state':
                self.game_state = data['data']
                # 打印当前状态
                print(f"\n📊 游戏状态更新 - 阶段: {self.game_state['game_stage']}")
                print(f"   底池: {self.game_state['pot']}, 当前下注: {self.game_state['current_bet']}")
                
                # 打印玩家信息
                for p in self.game_state['players']:
                    current = "👉" if p['id'] == self.game_state['current_player_id'] else "  "
                    print(f"   {current} {p['name']}: 筹码={p['chips']}, 下注={p['bet']}, "
                          f"输赢={p['total_win']:+d}, 胜率={p['games_won']}/{p['games_played']}, "
                          f"补码={p['rebuys']}")
                
                # 如果是当前玩家且是人类玩家
                if self.game_state['current_player_id'] == self.player_id:
                    await self.make_decision()
                    
            elif data['type'] == 'game_started':
                print(f"\n🎮 第 {data['data'].get('game_number', '?')} 局游戏开始！")
                
            elif data['type'] == 'player_action':
                action = data['data']
                print(f"   📝 {action.get('player_name', '玩家')}: {action.get('action', '未知')}")
                
    async def make_decision(self):
        """AI决策（简单策略）"""
        await asyncio.sleep(0.5)
        
        current_bet = self.game_state['current_bet']
        my_player = None
        
        for p in self.game_state['players']:
            if p['id'] == self.player_id:
                my_player = p
                break
        
        if not my_player:
            return
            
        my_bet = my_player['bet']
        my_chips = my_player['chips']
        
        # 简单策略：随机决策
        import random
        
        if my_bet < current_bet:
            # 需要跟注或加注
            call_amount = current_bet - my_bet
            
            if call_amount >= my_chips:
                # All-in
                await self.action('call')
            elif random.random() < 0.2:
                # 20%概率弃牌
                await self.action('fold')
            elif random.random() < 0.3:
                # 30%概率加注
                raise_amount = min(current_bet * 2, my_chips)
                await self.action('raise', raise_amount)
            else:
                # 跟注
                await self.action('call')
        else:
            # 可以过牌
            if random.random() < 0.3:
                # 30%概率加注
                raise_amount = min(20, my_chips)
                await self.action('raise', raise_amount)
            else:
                # 过牌
                await self.action('check')
    
    async def action(self, action_type, amount=0):
        """发送操作"""
        await self.ws.send(json.dumps({
            'type': 'action',
            'action': action_type,
            'amount': amount
        }))
        
    async def start_game(self):
        """开始游戏"""
        await self.ws.send(json.dumps({'type': 'start_game'}))
        
    async def add_ai(self, count=1):
        """添加AI"""
        await self.ws.send(json.dumps({
            'type': 'add_ai',
            'count': count
        }))


async def test_complete_game():
    """测试完整游戏流程"""
    print("="*80)
    print("🎮 完整游戏流程测试")
    print("="*80)
    print("\n这个测试会：")
    print("1. 创建一个测试玩家")
    print("2. 添加3个AI玩家")
    print("3. 连续玩10局游戏")
    print("4. 观察统计数据更新")
    print("5. 如果有玩家筹码<20，测试补码功能")
    print("\n" + "="*80 + "\n")
    
    # 创建玩家
    player = GamePlayer("测试玩家A")
    await player.connect()
    
    # 启动消息接收任务
    receive_task = asyncio.create_task(player.receive_messages())
    
    await asyncio.sleep(1)
    
    # 添加AI
    print("📌 添加3个AI玩家...")
    await player.add_ai(3)
    await asyncio.sleep(2)
    
    # 玩10局游戏
    for i in range(10):
        print(f"\n{'='*80}")
        print(f"🎲 开始第 {i+1} 局游戏")
        print(f"{'='*80}")
        
        await player.start_game()
        
        # 等待游戏结束（最多60秒）
        timeout = 60
        start_time = asyncio.get_event_loop().time()
        
        while True:
            await asyncio.sleep(1)
            
            if player.game_state and player.game_state['game_stage'] == 'showdown':
                # 游戏结束
                print(f"\n✅ 第 {i+1} 局游戏结束")
                
                # 打印最终状态
                if player.game_state.get('game_result'):
                    result = player.game_state['game_result']
                    winners = result.get('winners', [])
                    print(f"\n🏆 获胜者: {', '.join([w['name'] for w in winners])}")
                    print(f"💰 赢得: {result.get('win_amount', 0)} 筹码")
                
                # 等待一下让统计更新
                await asyncio.sleep(2)
                break
                
            if asyncio.get_event_loop().time() - start_time > timeout:
                print(f"\n⚠️  游戏超时")
                break
        
        # 短暂暂停
        await asyncio.sleep(2)
    
    print("\n" + "="*80)
    print("📊 最终统计")
    print("="*80)
    
    if player.game_state:
        for p in player.game_state['players']:
            print(f"\n{p['name']}:")
            print(f"  💰 当前筹码: {p['chips']}")
            print(f"  📈 累计输赢: {p['total_win']:+d}")
            print(f"  🎯 胜率: {p['games_won']}/{p['games_played']} "
                  f"({p['games_won']/max(p['games_played'],1)*100:.1f}%)")
            print(f"  💳 补码次数: {p['rebuys']}")
    
    # 取消接收任务
    receive_task.cancel()
    
    print("\n✅ 测试完成！")


if __name__ == "__main__":
    asyncio.run(test_complete_game())
