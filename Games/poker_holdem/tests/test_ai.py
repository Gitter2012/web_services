"""
测试AI玩家功能
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from src.ai_player import AIPlayer, AIPlayerFactory
from src.poker_game import Card, Suit, Rank, PokerGame


def test_ai_hand_evaluation():
    """测试AI手牌评估"""
    print("=" * 60)
    print("测试AI手牌评估")
    print("=" * 60)
    
    ai = AIPlayerFactory.create_ai_player("ai_1", 0)
    
    # 测试强起手牌 - AA
    ai.hand = [
        Card(Suit.HEARTS, Rank.ACE),
        Card(Suit.SPADES, Rank.ACE)
    ]
    strength = ai.evaluate_hand_strength([])
    print(f"AA 强度: {strength:.2f}")
    assert strength > 0.9, "AA应该是很强的起手牌"
    
    # 测试中等起手牌 - AK suited
    ai.hand = [
        Card(Suit.HEARTS, Rank.ACE),
        Card(Suit.HEARTS, Rank.KING)
    ]
    strength = ai.evaluate_hand_strength([])
    print(f"AKs 强度: {strength:.2f}")
    assert strength > 0.7, "AK同花应该是强起手牌"
    
    # 测试弱起手牌 - 72
    ai.hand = [
        Card(Suit.HEARTS, Rank.SEVEN),
        Card(Suit.CLUBS, Rank.TWO)
    ]
    strength = ai.evaluate_hand_strength([])
    print(f"72o 强度: {strength:.2f}")
    assert strength < 0.4, "72应该是弱起手牌"
    
    print("✓ AI手牌评估测试通过\n")


def test_ai_decision_making():
    """测试AI决策"""
    print("=" * 60)
    print("测试AI决策")
    print("=" * 60)
    
    # 创建不同性格的AI
    tight_ai = AIPlayer("ai_tight", "紧凶AI", personality=AIPlayer.PERSONALITY_TIGHT)
    loose_ai = AIPlayer("ai_loose", "松凶AI", personality=AIPlayer.PERSONALITY_LOOSE)
    
    # 给他们相同的起手牌
    test_hand = [
        Card(Suit.HEARTS, Rank.KING),
        Card(Suit.DIAMONDS, Rank.QUEEN)
    ]
    
    tight_ai.hand = test_hand.copy()
    loose_ai.hand = test_hand.copy()
    
    print(f"\n测试手牌: KQ")
    
    # 测试决策
    tight_action, tight_amount = tight_ai.decide_action(20, 30, [], "preflop")
    loose_action, loose_amount = loose_ai.decide_action(20, 30, [], "preflop")
    
    print(f"紧凶AI决策: {tight_action} {tight_amount}")
    print(f"松凶AI决策: {loose_action} {loose_amount}")
    
    print("\n✓ AI决策测试通过\n")


def test_ai_in_game():
    """测试AI在游戏中"""
    print("=" * 60)
    print("测试AI在游戏中")
    print("=" * 60)
    
    game = PokerGame()
    
    # 添加1个真人玩家和2个AI
    game.add_player("human_1", "人类玩家")
    
    ai_players = AIPlayerFactory.create_multiple_ai_players(2)
    for ai in ai_players:
        game.players.append(ai)
    
    print(f"玩家数量: {len(game.players)}")
    for p in game.players:
        ai_tag = "🤖" if isinstance(p, AIPlayer) else "👤"
        print(f"  {ai_tag} {p.name}")
    
    # 开始游戏
    game.start_game()
    print(f"\n游戏阶段: {game.game_stage}")
    print(f"底池: {game.pot}")
    
    # 模拟几轮行动
    rounds = 0
    max_rounds = 10
    
    while game.game_stage != "showdown" and rounds < max_rounds:
        current_player = game.players[game.current_player_index]
        
        if isinstance(current_player, AIPlayer):
            action, amount = current_player.decide_action(
                game.current_bet,
                game.pot,
                game.community_cards,
                game.game_stage
            )
            print(f"{current_player.name} 执行: {action} {amount}")
            game.player_action(current_player.id, action, amount)
        else:
            # 人类玩家自动跟注
            if current_player.bet < game.current_bet:
                game.player_action(current_player.id, "call", 0)
                print(f"{current_player.name} 跟注")
            else:
                game.player_action(current_player.id, "check", 0)
                print(f"{current_player.name} 过牌")
        
        rounds += 1
    
    print(f"\n最终游戏阶段: {game.game_stage}")
    print(f"公共牌数量: {len(game.community_cards)}")
    print(f"最终底池: {game.pot}")
    
    print("\n✓ AI游戏测试通过\n")


def test_ai_personalities():
    """测试不同AI性格"""
    print("=" * 60)
    print("测试AI性格差异")
    print("=" * 60)
    
    personalities = [
        (AIPlayer.PERSONALITY_TIGHT, "紧凶型"),
        (AIPlayer.PERSONALITY_LOOSE, "松凶型"),
        (AIPlayer.PERSONALITY_PASSIVE, "被动型"),
        (AIPlayer.PERSONALITY_BALANCED, "平衡型")
    ]
    
    for personality, name in personalities:
        ai = AIPlayer(f"ai_{personality}", f"AI_{name}", personality=personality)
        print(f"\n{name}:")
        print(f"  激进度: {ai.aggression:.2f}")
        print(f"  紧度: {ai.tightness:.2f}")
        print(f"  诈唬频率: {ai.bluff_frequency:.2f}")
    
    print("\n✓ AI性格测试通过\n")


def run_all_tests():
    """运行所有AI测试"""
    print("\n" + "=" * 60)
    print("开始AI玩家测试")
    print("=" * 60 + "\n")
    
    try:
        test_ai_hand_evaluation()
        test_ai_decision_making()
        test_ai_personalities()
        test_ai_in_game()
        
        print("\n" + "=" * 60)
        print("所有AI测试通过! ✓")
        print("=" * 60)
        
        return True
        
    except AssertionError as e:
        print(f"\n✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    except Exception as e:
        print(f"\n✗ 测试出错: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = run_all_tests()
    exit(0 if success else 1)
