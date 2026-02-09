"""
测试游戏核心逻辑
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from src.poker_game import (
    Card, Deck, Player, PokerGame, HandEvaluator, 
    Suit, Rank, HandRank
)


def test_deck():
    """测试牌堆"""
    print("=" * 50)
    print("测试牌堆功能")
    print("=" * 50)
    
    deck = Deck()
    print(f"初始牌堆数量: {len(deck.cards)}")
    assert len(deck.cards) == 52, "牌堆应该有52张牌"
    
    # 测试发牌
    cards = deck.deal(5)
    print(f"发5张牌后剩余: {len(deck.cards)}")
    assert len(cards) == 5, "应该发5张牌"
    assert len(deck.cards) == 47, "剩余47张牌"
    
    print("✓ 牌堆测试通过\n")


def test_hand_evaluator():
    """测试牌型判断"""
    print("=" * 50)
    print("测试牌型判断")
    print("=" * 50)
    
    # 测试皇家同花顺
    royal_flush = [
        Card(Suit.HEARTS, Rank.ACE),
        Card(Suit.HEARTS, Rank.KING),
        Card(Suit.HEARTS, Rank.QUEEN),
        Card(Suit.HEARTS, Rank.JACK),
        Card(Suit.HEARTS, Rank.TEN),
    ]
    rank, values = HandEvaluator.evaluate(royal_flush)
    print(f"皇家同花顺: {rank.name} - {values}")
    assert rank == HandRank.ROYAL_FLUSH, "应该是皇家同花顺"
    
    # 测试四条
    four_kind = [
        Card(Suit.HEARTS, Rank.ACE),
        Card(Suit.DIAMONDS, Rank.ACE),
        Card(Suit.CLUBS, Rank.ACE),
        Card(Suit.SPADES, Rank.ACE),
        Card(Suit.HEARTS, Rank.KING),
    ]
    rank, values = HandEvaluator.evaluate(four_kind)
    print(f"四条: {rank.name} - {values}")
    assert rank == HandRank.FOUR_OF_KIND, "应该是四条"
    
    # 测试葫芦
    full_house = [
        Card(Suit.HEARTS, Rank.KING),
        Card(Suit.DIAMONDS, Rank.KING),
        Card(Suit.CLUBS, Rank.KING),
        Card(Suit.SPADES, Rank.QUEEN),
        Card(Suit.HEARTS, Rank.QUEEN),
    ]
    rank, values = HandEvaluator.evaluate(full_house)
    print(f"葫芦: {rank.name} - {values}")
    assert rank == HandRank.FULL_HOUSE, "应该是葫芦"
    
    # 测试同花
    flush = [
        Card(Suit.HEARTS, Rank.ACE),
        Card(Suit.HEARTS, Rank.JACK),
        Card(Suit.HEARTS, Rank.NINE),
        Card(Suit.HEARTS, Rank.SEVEN),
        Card(Suit.HEARTS, Rank.TWO),
    ]
    rank, values = HandEvaluator.evaluate(flush)
    print(f"同花: {rank.name} - {values}")
    assert rank == HandRank.FLUSH, "应该是同花"
    
    # 测试顺子
    straight = [
        Card(Suit.HEARTS, Rank.FIVE),
        Card(Suit.DIAMONDS, Rank.FOUR),
        Card(Suit.CLUBS, Rank.THREE),
        Card(Suit.SPADES, Rank.TWO),
        Card(Suit.HEARTS, Rank.ACE),
    ]
    rank, values = HandEvaluator.evaluate(straight)
    print(f"顺子(A-2-3-4-5): {rank.name} - {values}")
    assert rank == HandRank.STRAIGHT, "应该是顺子"
    
    # 测试三条
    three_kind = [
        Card(Suit.HEARTS, Rank.KING),
        Card(Suit.DIAMONDS, Rank.KING),
        Card(Suit.CLUBS, Rank.KING),
        Card(Suit.SPADES, Rank.QUEEN),
        Card(Suit.HEARTS, Rank.JACK),
    ]
    rank, values = HandEvaluator.evaluate(three_kind)
    print(f"三条: {rank.name} - {values}")
    assert rank == HandRank.THREE_OF_KIND, "应该是三条"
    
    # 测试两对
    two_pair = [
        Card(Suit.HEARTS, Rank.KING),
        Card(Suit.DIAMONDS, Rank.KING),
        Card(Suit.CLUBS, Rank.QUEEN),
        Card(Suit.SPADES, Rank.QUEEN),
        Card(Suit.HEARTS, Rank.JACK),
    ]
    rank, values = HandEvaluator.evaluate(two_pair)
    print(f"两对: {rank.name} - {values}")
    assert rank == HandRank.TWO_PAIR, "应该是两对"
    
    # 测试一对
    pair = [
        Card(Suit.HEARTS, Rank.KING),
        Card(Suit.DIAMONDS, Rank.KING),
        Card(Suit.CLUBS, Rank.QUEEN),
        Card(Suit.SPADES, Rank.JACK),
        Card(Suit.HEARTS, Rank.TEN),
    ]
    rank, values = HandEvaluator.evaluate(pair)
    print(f"一对: {rank.name} - {values}")
    assert rank == HandRank.PAIR, "应该是一对"
    
    # 测试高牌
    high_card = [
        Card(Suit.HEARTS, Rank.ACE),
        Card(Suit.DIAMONDS, Rank.KING),
        Card(Suit.CLUBS, Rank.QUEEN),
        Card(Suit.SPADES, Rank.JACK),
        Card(Suit.HEARTS, Rank.NINE),
    ]
    rank, values = HandEvaluator.evaluate(high_card)
    print(f"高牌: {rank.name} - {values}")
    assert rank == HandRank.HIGH_CARD, "应该是高牌"
    
    print("✓ 牌型判断测试通过\n")


def test_player():
    """测试玩家"""
    print("=" * 50)
    print("测试玩家功能")
    print("=" * 50)
    
    player = Player(id="p1", name="测试玩家", chips=1000)
    print(f"玩家: {player.name}, 筹码: {player.chips}")
    
    # 测试发牌
    deck = Deck()
    player.hand = deck.deal(2)
    print(f"手牌: {[str(card) for card in player.hand]}")
    assert len(player.hand) == 2, "应该有2张手牌"
    
    # 测试下注
    player.bet = 100
    player.chips -= 100
    print(f"下注后 - 筹码: {player.chips}, 当前下注: {player.bet}")
    assert player.chips == 900, "筹码应该减少"
    
    # 测试重置
    player.reset_for_new_hand()
    print(f"重置后 - 手牌: {len(player.hand)}, 下注: {player.bet}")
    assert len(player.hand) == 0, "手牌应该清空"
    assert player.bet == 0, "下注应该重置"
    
    print("✓ 玩家测试通过\n")


def test_game_flow():
    """测试游戏流程"""
    print("=" * 50)
    print("测试游戏流程")
    print("=" * 50)
    
    game = PokerGame(small_blind=10, big_blind=20)
    
    # 添加玩家
    print("添加玩家...")
    assert game.add_player("p1", "玩家1") == True
    assert game.add_player("p2", "玩家2") == True
    assert game.add_player("p3", "玩家3") == True
    print(f"玩家数量: {len(game.players)}")
    assert len(game.players) == 3, "应该有3个玩家"
    
    # 开始游戏
    print("\n开始游戏...")
    assert game.start_game() == True
    print(f"游戏阶段: {game.game_stage}")
    assert game.game_stage == "preflop", "应该在翻牌前阶段"
    
    # 检查盲注
    print(f"\n底池: {game.pot}")
    print(f"当前下注: {game.current_bet}")
    assert game.pot == 30, "底池应该是30（小盲10 + 大盲20）"
    assert game.current_bet == 20, "当前下注应该是20（大盲）"
    
    # 检查手牌
    for i, player in enumerate(game.players):
        print(f"{player.name}: {len(player.hand)}张手牌, 下注: {player.bet}")
        assert len(player.hand) == 2, "每个玩家应该有2张手牌"
    
    # 模拟玩家行动
    print("\n模拟玩家行动...")
    current_player = game.players[game.current_player_index]
    print(f"当前玩家: {current_player.name}")
    
    # 玩家1跟注
    result = game.player_action(current_player.id, "call")
    print(f"玩家行动结果: {result}")
    assert result == True, "行动应该成功"
    
    # 获取游戏状态
    print("\n获取游戏状态...")
    state = game.get_game_state("p1")
    print(f"游戏阶段: {state['game_stage']}")
    print(f"底池: {state['pot']}")
    print(f"公共牌数量: {len(state['community_cards'])}")
    print(f"玩家数量: {len(state['players'])}")
    
    print("✓ 游戏流程测试通过\n")


def test_game_stages():
    """测试游戏阶段转换"""
    print("=" * 50)
    print("测试游戏阶段转换")
    print("=" * 50)
    
    game = PokerGame(small_blind=10, big_blind=20)
    
    # 添加2个玩家
    game.add_player("p1", "玩家1")
    game.add_player("p2", "玩家2")
    
    # 开始游戏
    game.start_game()
    print(f"初始阶段: {game.game_stage}")
    assert game.game_stage == "preflop"
    
    # 模拟玩家行动直到进入下一阶段
    print("\n模拟第一轮下注...")
    for _ in range(2):
        if game.current_player_index < len(game.players):
            current = game.players[game.current_player_index]
            if not current.folded:
                # 跟注或过牌
                if current.bet < game.current_bet:
                    game.player_action(current.id, "call")
                else:
                    game.player_action(current.id, "check")
    
    print(f"当前阶段: {game.game_stage}")
    print(f"公共牌数量: {len(game.community_cards)}")
    
    print("✓ 游戏阶段测试通过\n")


def test_edge_cases():
    """测试边界情况"""
    print("=" * 50)
    print("测试边界情况")
    print("=" * 50)
    
    game = PokerGame()
    
    # 测试游戏人数不足
    game.add_player("p1", "玩家1")
    result = game.start_game()
    print(f"单人游戏启动结果: {result}")
    assert result == False, "单人无法开始游戏"
    
    # 测试玩家上限
    game2 = PokerGame()
    for i in range(9):
        result = game2.add_player(f"p{i}", f"玩家{i}")
        if i < 8:
            assert result == True, f"第{i+1}个玩家应该成功加入"
        else:
            assert result == False, "第9个玩家应该无法加入"
    
    print(f"最大玩家数: {len(game2.players)}")
    assert len(game2.players) == 8, "最多8个玩家"
    
    # 测试重复玩家
    game3 = PokerGame()
    game3.add_player("p1", "玩家1")
    result = game3.add_player("p1", "玩家1")
    print(f"重复玩家结果: {result}")
    assert result == False, "不能添加重复玩家"
    
    print("✓ 边界情况测试通过\n")


def test_all_in():
    """测试All-in情况"""
    print("=" * 50)
    print("测试All-in情况")
    print("=" * 50)
    
    game = PokerGame()
    game.add_player("p1", "玩家1")
    game.add_player("p2", "玩家2")
    
    # 设置玩家筹码
    game.players[0].chips = 50
    game.players[1].chips = 1000
    
    game.start_game()
    
    # 玩家1筹码不足，应该all-in
    current = game.players[game.current_player_index]
    if current.id == "p1":
        game.player_action(current.id, "call")
        print(f"{current.name} all-in状态: {current.all_in}")
    
    print("✓ All-in测试通过\n")


def run_all_tests():
    """运行所有测试"""
    print("\n" + "=" * 50)
    print("开始德州扑克游戏测试")
    print("=" * 50 + "\n")
    
    try:
        test_deck()
        test_hand_evaluator()
        test_player()
        test_game_flow()
        test_game_stages()
        test_edge_cases()
        test_all_in()
        
        print("\n" + "=" * 50)
        print("所有测试通过! ✓")
        print("=" * 50)
        
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
    
    return True


if __name__ == "__main__":
    success = run_all_tests()
    exit(0 if success else 1)
