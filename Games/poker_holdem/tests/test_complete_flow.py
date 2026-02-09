"""
测试完整游戏流程（包括所有阶段）
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from src.poker_game import PokerGame, Player
from src.ai_player import AIPlayer, AIPlayerFactory


def test_complete_game_flow():
    """测试完整游戏流程"""
    print("=" * 60)
    print("测试完整游戏流程（preflop -> flop -> turn -> river -> showdown）")
    print("=" * 60)
    
    game = PokerGame()
    
    # 添加2个玩家和1个AI
    game.add_player("p1", "玩家1")
    game.add_player("p2", "玩家2")
    
    ai = AIPlayerFactory.create_ai_player("ai_1", 0)
    game.players.append(ai)
    
    print(f"\n玩家数量: {len(game.players)}")
    for p in game.players:
        print(f"  - {p.name}")
    
    # 开始游戏
    game.start_game()
    print(f"\n游戏阶段: {game.game_stage}")
    print(f"底池: {game.pot}")
    print(f"公共牌: {len(game.community_cards)}")
    
    # 模拟游戏进行
    stage_count = 0
    max_actions = 50
    action_count = 0
    
    while game.game_stage != "showdown" and action_count < max_actions:
        current_player = game.players[game.current_player_index]
        
        if isinstance(current_player, AIPlayer):
            # AI决策
            action, amount = current_player.decide_action(
                game.current_bet,
                game.pot,
                game.community_cards,
                game.game_stage
            )
        else:
            # 真人玩家自动跟注或过牌
            if current_player.bet < game.current_bet:
                action, amount = "call", 0
            else:
                action, amount = "check", 0
        
        old_stage = game.game_stage
        success = game.player_action(current_player.id, action, amount)
        
        if success:
            print(f"[{game.game_stage}] {current_player.name} {action} {amount if amount > 0 else ''}")
            
            # 检查是否进入了新阶段
            if game.game_stage != old_stage:
                print(f"\n>>> 进入新阶段: {game.game_stage}")
                print(f"    公共牌数量: {len(game.community_cards)}")
                print(f"    底池: {game.pot}\n")
                stage_count += 1
        
        action_count += 1
    
    print(f"\n最终阶段: {game.game_stage}")
    print(f"公共牌数量: {len(game.community_cards)}")
    print(f"底池: {game.pot}")
    
    # 检查游戏结果
    if game.game_result:
        print("\n游戏结果:")
        print(f"获胜者: {', '.join([w['name'] for w in game.game_result['winners']])}")
        print(f"牌型: {game.game_result['winners'][0]['hand_name']}")
        print(f"赢得: {game.game_result['win_amount']} 筹码")
        
        if game.game_result['player_hands']:
            print("\n所有玩家手牌:")
            for ph in game.game_result['player_hands']:
                winner_tag = "👑" if ph['is_winner'] else "  "
                print(f"  {winner_tag} {ph['name']}: {ph['hand_name']}")
    
    # 验证
    assert game.game_stage == "showdown", f"应该到达摊牌阶段，当前: {game.game_stage}"
    assert len(game.community_cards) == 5, f"应该有5张公共牌，当前: {len(game.community_cards)}"
    assert stage_count >= 4, f"应该经过至少4个阶段，当前: {stage_count}"
    assert game.game_result is not None, "应该有游戏结果"
    
    print("\n✓ 完整游戏流程测试通过!")


if __name__ == "__main__":
    test_complete_game_flow()
