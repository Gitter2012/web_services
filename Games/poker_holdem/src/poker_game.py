"""
德州扑克游戏逻辑模块
"""
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
import random
from collections import Counter


class Suit(Enum):
    """花色"""
    HEARTS = "♥"
    DIAMONDS = "♦"
    CLUBS = "♣"
    SPADES = "♠"


class Rank(Enum):
    """牌面大小"""
    TWO = (2, "2")
    THREE = (3, "3")
    FOUR = (4, "4")
    FIVE = (5, "5")
    SIX = (6, "6")
    SEVEN = (7, "7")
    EIGHT = (8, "8")
    NINE = (9, "9")
    TEN = (10, "10")
    JACK = (11, "J")
    QUEEN = (12, "Q")
    KING = (13, "K")
    ACE = (14, "A")

    def __init__(self, numeric_value, display):
        self.numeric_value = numeric_value
        self.display = display


class HandRank(Enum):
    """牌型等级"""
    HIGH_CARD = 1
    PAIR = 2
    TWO_PAIR = 3
    THREE_OF_KIND = 4
    STRAIGHT = 5
    FLUSH = 6
    FULL_HOUSE = 7
    FOUR_OF_KIND = 8
    STRAIGHT_FLUSH = 9
    ROYAL_FLUSH = 10


@dataclass
class Card:
    """扑克牌"""
    suit: Suit
    rank: Rank

    def __str__(self):
        return f"{self.suit.value}{self.rank.display}"

    def to_dict(self):
        return {
            "suit": self.suit.value,
            "rank": self.rank.display,
            "value": self.rank.numeric_value
        }


class Deck:
    """牌堆"""
    def __init__(self):
        self.cards: List[Card] = []
        self.reset()

    def reset(self):
        """重置牌堆"""
        self.cards = [Card(suit, rank) for suit in Suit for rank in Rank]
        random.shuffle(self.cards)

    def deal(self, num: int = 1) -> List[Card]:
        """发牌"""
        dealt_cards = []
        for _ in range(num):
            if self.cards:
                dealt_cards.append(self.cards.pop())
        return dealt_cards


@dataclass
class Player:
    """玩家"""
    id: str
    name: str
    chips: int = 1000
    hand: List[Card] = field(default_factory=list)
    bet: int = 0
    folded: bool = False
    all_in: bool = False
    is_dealer: bool = False
    has_acted: bool = False  # 是否在当前下注轮行动过
    
    # 统计信息
    total_win: int = 0  # 累计输赢
    games_played: int = 0  # 参与局数
    games_won: int = 0  # 获胜次数
    rebuys: int = 0  # 补码次数
    initial_chips: int = 1000  # 初始筹码

    def reset_for_new_hand(self):
        """新一轮重置"""
        self.hand = []
        self.bet = 0
        self.folded = False
        self.all_in = False
        self.has_acted = False

    def to_dict(self, show_cards: bool = False):
        """转换为字典"""
        return {
            "id": self.id,
            "name": self.name,
            "chips": self.chips,
            "bet": self.bet,
            "folded": self.folded,
            "all_in": self.all_in,
            "is_dealer": self.is_dealer,
            "hand": [card.to_dict() for card in self.hand] if show_cards else [],
            # 统计信息
            "total_win": self.total_win,
            "games_played": self.games_played,
            "games_won": self.games_won,
            "rebuys": self.rebuys
        }


class HandEvaluator:
    """牌型评估器"""
    
    @staticmethod
    def evaluate(cards: List[Card]) -> Tuple[HandRank, List[int]]:
        """
        评估牌型
        返回: (牌型等级, 用于比较的值列表)
        """
        if len(cards) < 5:
            return HandRank.HIGH_CARD, []
        
        # 获取所有可能的5张牌组合
        from itertools import combinations
        best_rank = HandRank.HIGH_CARD
        best_values = []
        
        for combo in combinations(cards, 5):
            rank, values = HandEvaluator._evaluate_five_cards(list(combo))
            if rank.value > best_rank.value or (rank.value == best_rank.value and values > best_values):
                best_rank = rank
                best_values = values
        
        return best_rank, best_values

    @staticmethod
    def _evaluate_five_cards(cards: List[Card]) -> Tuple[HandRank, List[int]]:
        """评估5张牌的牌型"""
        ranks = sorted([card.rank.numeric_value for card in cards], reverse=True)
        suits = [card.suit for card in cards]
        rank_counts = Counter(ranks)
        
        is_flush = len(set(suits)) == 1
        is_straight = HandEvaluator._is_straight(ranks)
        
        # 同花顺
        if is_flush and is_straight:
            if ranks[0] == 14:  # A
                return HandRank.ROYAL_FLUSH, ranks
            return HandRank.STRAIGHT_FLUSH, ranks
        
        # 四条
        if 4 in rank_counts.values():
            four_rank = [r for r, c in rank_counts.items() if c == 4][0]
            kicker = [r for r in ranks if r != four_rank][0]
            return HandRank.FOUR_OF_KIND, [four_rank, kicker]
        
        # 葫芦
        if 3 in rank_counts.values() and 2 in rank_counts.values():
            three_rank = [r for r, c in rank_counts.items() if c == 3][0]
            pair_rank = [r for r, c in rank_counts.items() if c == 2][0]
            return HandRank.FULL_HOUSE, [three_rank, pair_rank]
        
        # 同花
        if is_flush:
            return HandRank.FLUSH, ranks
        
        # 顺子
        if is_straight:
            return HandRank.STRAIGHT, ranks
        
        # 三条
        if 3 in rank_counts.values():
            three_rank = [r for r, c in rank_counts.items() if c == 3][0]
            kickers = sorted([r for r in ranks if r != three_rank], reverse=True)
            return HandRank.THREE_OF_KIND, [three_rank] + kickers
        
        # 两对
        pairs = [r for r, c in rank_counts.items() if c == 2]
        if len(pairs) == 2:
            pairs = sorted(pairs, reverse=True)
            kicker = [r for r in ranks if r not in pairs][0]
            return HandRank.TWO_PAIR, pairs + [kicker]
        
        # 一对
        if len(pairs) == 1:
            pair_rank = pairs[0]
            kickers = sorted([r for r in ranks if r != pair_rank], reverse=True)
            return HandRank.PAIR, [pair_rank] + kickers
        
        # 高牌
        return HandRank.HIGH_CARD, ranks

    @staticmethod
    def _is_straight(ranks: List[int]) -> bool:
        """判断是否是顺子"""
        ranks = sorted(ranks)
        # 普通顺子
        if ranks == list(range(ranks[0], ranks[0] + 5)):
            return True
        # A-2-3-4-5 顺子
        if ranks == [2, 3, 4, 5, 14]:
            return True
        return False


class PokerGame:
    """德州扑克游戏"""
    
    def __init__(self, small_blind: int = 10, big_blind: int = 20):
        self.players: List[Player] = []
        self.deck = Deck()
        self.community_cards: List[Card] = []
        self.pot = 0
        self.current_bet = 0
        self.min_raise = big_blind  # 最小加注量（初始为大盲注）
        self.last_raise_amount = 0  # 上次加注的增量
        self.small_blind = small_blind
        self.big_blind = big_blind
        self.dealer_index = 0
        self.current_player_index = 0
        self.game_stage = "waiting"  # waiting, preflop, flop, turn, river, showdown
        self.round_complete = False
        self.game_result = None  # 存储游戏结果
        self.game_history = []  # 牌局历史记录
        self.current_game_actions = []  # 当前局的操作记录
        self.game_number = 0  # 游戏局数
        self.chips_before_game = {}  # 游戏开始前的筹码记录
        self.room_owner_id = None  # 房主ID
        self.game_ended = False  # 游戏是否结束
        self.final_results = None  # 最终结果
        self.turn_timeout = 30  # 行动超时时间（秒）
        self.current_turn_start_time = None  # 当前回合开始时间

    def add_player(self, player_id: str, player_name: str) -> bool:
        """添加玩家"""
        if len(self.players) >= 8:
            return False
        if any(p.id == player_id for p in self.players):
            return False
        
        player = Player(id=player_id, name=player_name)
        self.players.append(player)
        
        # 第一个加入的玩家成为房主
        if self.room_owner_id is None:
            self.room_owner_id = player_id
        
        return True

    def remove_player(self, player_id: str) -> bool:
        """移除玩家"""
        self.players = [p for p in self.players if p.id != player_id]
        return True

    def start_game(self) -> bool:
        """开始游戏"""
        if len(self.players) < 2:
            return False
        
        # 记录游戏开始前的筹码（用于计算输赢）
        self.chips_before_game = {p.id: p.chips for p in self.players}
        
        self.game_stage = "preflop"
        self.deck.reset()
        self.community_cards = []
        self.pot = 0
        self.current_bet = 0
        self.game_result = None  # 重置游戏结果
        self.current_game_actions = []  # 重置操作记录
        self.game_number += 1  # 增加局数
        
        # 重置玩家状态
        for player in self.players:
            player.reset_for_new_hand()
        
        # 设置庄家
        self.players[self.dealer_index].is_dealer = True
        
        # 发手牌
        for _ in range(2):
            for player in self.players:
                if not player.folded:
                    cards = self.deck.deal(1)
                    if cards:
                        player.hand.extend(cards)
        
        # 下盲注
        self._post_blinds()
        
        # 设置第一个行动玩家
        self.current_player_index = (self.dealer_index + 3) % len(self.players)
        self._skip_folded_players()

        # 重置超时时间
        self._reset_turn_timeout()

        return True

    def _post_blinds(self):
        """下盲注"""
        if len(self.players) < 2:
            return
        
        # 小盲注
        small_blind_index = (self.dealer_index + 1) % len(self.players)
        small_blind_player = self.players[small_blind_index]
        small_blind_amount = min(self.small_blind, small_blind_player.chips)
        small_blind_player.chips -= small_blind_amount
        small_blind_player.bet = small_blind_amount
        self.pot += small_blind_amount
        
        # 大盲注
        big_blind_index = (self.dealer_index + 2) % len(self.players)
        big_blind_player = self.players[big_blind_index]
        big_blind_amount = min(self.big_blind, big_blind_player.chips)
        big_blind_player.chips -= big_blind_amount
        big_blind_player.bet = big_blind_amount
        self.pot += big_blind_amount
        
        self.current_bet = big_blind_amount

    def _skip_folded_players(self):
        """跳过已弃牌的玩家"""
        attempts = 0
        while self.players[self.current_player_index].folded and attempts < len(self.players):
            self.current_player_index = (self.current_player_index + 1) % len(self.players)
            attempts += 1

    def player_action(self, player_id: str, action: str, amount: int = 0) -> bool:
        """玩家行动"""
        current_player = self.players[self.current_player_index]
        
        if current_player.id != player_id:
            return False
        
        # 记录操作
        action_record = {
            "player_id": player_id,
            "player_name": current_player.name,
            "action": action,
            "amount": amount if action in ["raise", "call"] else 0,
            "stage": self.game_stage,
            "pot_before": self.pot
        }
        
        if action == "fold":
            current_player.folded = True
        elif action == "call":
            call_amount = min(self.current_bet - current_player.bet, current_player.chips)
            current_player.chips -= call_amount
            current_player.bet += call_amount
            self.pot += call_amount
            action_record["amount"] = call_amount
            if current_player.chips == 0:
                current_player.all_in = True
        elif action == "raise":
            # 验证加注金额
            # 1. 计算需要跟注的金额
            call_amount = self.current_bet - current_player.bet
            
            # 2. 计算实际加注金额（总下注 - 已下注）
            total_bet_amount = min(amount, current_player.chips)
            raise_increment = total_bet_amount - call_amount
            
            # 3. 验证加注规则
            # 如果是all-in，允许任何金额
            is_all_in = (total_bet_amount == current_player.chips)
            
            if not is_all_in:
                # 不是all-in时，需要检查最小加注量
                # 最小加注增量是上次加注量或大盲注（取较大值）
                min_raise_increment = max(self.min_raise, self.big_blind)
                
                if raise_increment < min_raise_increment:
                    # 加注量不足，拒绝操作
                    return False
            
            # 4. 执行加注
            current_player.chips -= total_bet_amount
            current_player.bet += total_bet_amount
            self.pot += total_bet_amount
            
            # 5. 更新当前最大下注和最小加注量
            old_bet = self.current_bet
            self.current_bet = current_player.bet
            
            # 更新最小加注量为本次加注的增量
            if raise_increment > 0:
                self.last_raise_amount = raise_increment
                self.min_raise = raise_increment
            
            action_record["amount"] = total_bet_amount
            
            if current_player.chips == 0:
                current_player.all_in = True
            
            # 加注后，其他玩家需要重新行动
            for p in self.players:
                if p.id != player_id and not p.folded and not p.all_in:
                    p.has_acted = False
        elif action == "check":
            if current_player.bet < self.current_bet:
                return False
        else:
            return False
        
        # 保存操作记录
        self.current_game_actions.append(action_record)

        # 标记当前玩家已行动
        current_player.has_acted = True

        # 移动到下一个玩家
        self.current_player_index = (self.current_player_index + 1) % len(self.players)
        self._skip_folded_players()

        # 重置当前回合开始时间
        self._reset_turn_timeout()

        # 检查是否需要进入下一阶段
        if self._is_betting_round_complete():
            self._next_stage()

        return True

    def _reset_turn_timeout(self):
        """重置当前回合超时时间"""
        import time
        self.current_turn_start_time = time.time()

    def check_timeout(self) -> dict:
        """
        检查当前玩家是否超时
        返回: (是否超时, 操作类型)
        """
        import time

        # 只在游戏进行中检查超时
        if self.game_stage in ["waiting", "showdown"]:
            return False, None

        # 如果没有设置开始时间，设置当前时间
        if self.current_turn_start_time is None:
            self._reset_turn_timeout()
            return False, None

        # 计算已用时间
        elapsed = time.time() - self.current_turn_start_time

        # 检查是否超时
        if elapsed >= self.turn_timeout:
            print(f"[超时检查] 玩家超时! 已用时间: {elapsed:.1f}秒")
            # 当前玩家超时
            current_player = self.players[self.current_player_index]

            # 如果是AI玩家，返回需要AI行动
            if hasattr(current_player, 'is_ai') and current_player.is_ai:
                print(f"[超时检查] 玩家 {current_player.name} 是AI，需要自动行动")
                return True, 'ai_action'

            # 如果是普通玩家，超时弃牌
            if not current_player.folded:
                print(f"[超时检查] 玩家 {current_player.name} 超时自动弃牌")
                # 自动弃牌
                current_player.folded = True

                # 记录操作
                action_record = {
                    "player_id": current_player.id,
                    "player_name": current_player.name,
                    "action": "fold",
                    "amount": 0,
                    "stage": self.game_stage,
                    "pot_before": self.pot,
                    "timeout": True
                }
                self.current_game_actions.append(action_record)

                # 移动到下一个玩家
                self.current_player_index = (self.current_player_index + 1) % len(self.players)
                self._skip_folded_players()

                # 重置超时
                self._reset_turn_timeout()

                # 检查是否需要进入下一阶段
                if self._is_betting_round_complete():
                    self._next_stage()

                return True, 'fold'

        return False, None

    def set_turn_timeout(self, timeout: int):
        """设置超时时间"""
        self.turn_timeout = timeout

    def _is_betting_round_complete(self) -> bool:
        """检查下注轮是否完成"""
        active_players = [p for p in self.players if not p.folded and not p.all_in]
        
        # 如果只剩一个或零个活跃玩家，直接结束
        if len(active_players) <= 1:
            return True
        
        # 检查所有活跃玩家是否都已经行动过
        for player in active_players:
            if not player.has_acted:
                return False
        
        # 检查所有活跃玩家的下注是否一致
        for player in active_players:
            if player.bet < self.current_bet:
                return False
        
        return True

    def _next_stage(self):
        """进入下一阶段"""
        # 检查是否只剩一个活跃玩家（其他人都弃牌）
        active_players = [p for p in self.players if not p.folded]
        if len(active_players) == 1:
            # 直接进入showdown，单人获胜
            self.game_stage = "showdown"
            self._determine_winner()
            return
        
        # 重置下注和行动标志
        for player in self.players:
            player.bet = 0
            player.has_acted = False
        self.current_bet = 0
        self.min_raise = self.big_blind  # 重置最小加注量为大盲注
        self.last_raise_amount = 0  # 重置上次加注量
        
        if self.game_stage == "preflop":
            # 翻牌
            self.community_cards.extend(self.deck.deal(3))
            self.game_stage = "flop"
        elif self.game_stage == "flop":
            # 转牌
            self.community_cards.extend(self.deck.deal(1))
            self.game_stage = "turn"
        elif self.game_stage == "turn":
            # 河牌
            self.community_cards.extend(self.deck.deal(1))
            self.game_stage = "river"
        elif self.game_stage == "river":
            # 摊牌
            self.game_stage = "showdown"
            self._determine_winner()
            return
        
        # 从庄家后第一个玩家开始
        self.current_player_index = (self.dealer_index + 1) % len(self.players)
        self._skip_folded_players()

    def _determine_winner(self):
        """决定胜者"""
        active_players = [p for p in self.players if not p.folded]
        
        # 单人获胜（其他人都弃牌）
        if len(active_players) == 1:
            winner = active_players[0]
            winner.chips += self.pot
            
            # 更新统计信息
            for player in self.players:
                player.games_played += 1
                if player.id in self.chips_before_game:
                    chips_change = player.chips - self.chips_before_game[player.id]
                    player.total_win += chips_change
                if player.id == winner.id:
                    player.games_won += 1
            
            self.game_result = {
                "winners": [{"id": winner.id, "name": winner.name, "hand_name": "其他玩家弃牌"}],
                "win_amount": self.pot,
                "player_hands": []
            }
            self.pot = 0
            
            # 检查并处理补码
            self._check_and_rebuy()
            
            # 保存到历史记录
            self._save_game_history()
            return
        
        # 评估每个玩家的牌型
        player_hands = []
        for player in active_players:
            all_cards = player.hand + self.community_cards
            rank, values = HandEvaluator.evaluate(all_cards)
            player_hands.append({
                "player": player,
                "rank": rank,
                "values": values,
                "hand": player.hand
            })
        
        # 找出最佳牌型
        player_hands.sort(key=lambda x: (x["rank"].value, x["values"]), reverse=True)
        
        # 找出所有赢家（可能平局）
        best_rank = player_hands[0]["rank"]
        best_values = player_hands[0]["values"]
        winners = [ph for ph in player_hands if ph["rank"] == best_rank and ph["values"] == best_values]
        
        # 牌型名称映射
        rank_names = {
            HandRank.HIGH_CARD: "高牌",
            HandRank.PAIR: "一对",
            HandRank.TWO_PAIR: "两对",
            HandRank.THREE_OF_KIND: "三条",
            HandRank.STRAIGHT: "顺子",
            HandRank.FLUSH: "同花",
            HandRank.FULL_HOUSE: "葫芦",
            HandRank.FOUR_OF_KIND: "四条",
            HandRank.STRAIGHT_FLUSH: "同花顺",
            HandRank.ROYAL_FLUSH: "皇家同花顺"
        }
        
        # 分配奖池
        win_amount = self.pot // len(winners)
        winner_ids = set()
        for winner_data in winners:
            winner_data["player"].chips += win_amount
            winner_ids.add(winner_data["player"].id)
        
        # 更新所有玩家的统计信息
        for player in self.players:
            player.games_played += 1
            if player.id in self.chips_before_game:
                chips_change = player.chips - self.chips_before_game[player.id]
                player.total_win += chips_change
            if player.id in winner_ids:
                player.games_won += 1
        
        # 保存游戏结果
        self.game_result = {
            "winners": [
                {
                    "id": w["player"].id,
                    "name": w["player"].name,
                    "hand_name": rank_names.get(w["rank"], "未知")
                }
                for w in winners
            ],
            "win_amount": win_amount,
            "player_hands": [
                {
                    "id": ph["player"].id,
                    "name": ph["player"].name,
                    "hand": [{"suit": c.suit.value, "rank": c.rank.display} for c in ph["hand"]],
                    "hand_name": rank_names.get(ph["rank"], "未知"),
                    "is_winner": ph in winners
                }
                for ph in player_hands
            ]
        }
        
        self.pot = 0
        
        # 检查并处理补码
        self._check_and_rebuy()
        
        # 保存到历史记录
        self._save_game_history()
    
    def _save_game_history(self):
        """保存当前局到历史记录"""
        import datetime
        
        history_entry = {
            "game_number": self.game_number,
            "timestamp": datetime.datetime.now().isoformat(),
            "community_cards": [
                {"suit": c.suit.value, "rank": c.rank.display} 
                for c in self.community_cards
            ],
            "players": [
                {
                    "id": p.id,
                    "name": p.name,
                    "hand": [{"suit": c.suit.value, "rank": c.rank.display} for c in p.hand],
                    "chips": p.chips,
                    "folded": p.folded
                }
                for p in self.players
            ],
            "actions": self.current_game_actions,
            "result": self.game_result
        }
        
        self.game_history.append(history_entry)
        
        # 只保留最近20局
        if len(self.game_history) > 20:
            self.game_history = self.game_history[-20:]
    
    def get_game_history(self, limit: int = 10):
        """获取游戏历史记录"""
        return self.game_history[-limit:]
    
    def _check_and_rebuy(self):
        """检查并为筹码不足的玩家补码"""
        for player in self.players:
            # 如果玩家筹码少于大盲注，自动补码
            if player.chips < self.big_blind:
                rebuy_amount = player.initial_chips - player.chips
                player.chips = player.initial_chips
                player.rebuys += 1
                player.total_win -= rebuy_amount  # 补码算作损失

    def get_game_state(self, player_id: Optional[str] = None) -> dict:
        """获取游戏状态"""
        # 如果是摊牌阶段，显示所有玩家的手牌
        show_all_cards = self.game_stage == "showdown"

        # 计算当前玩家需要跟注的金额和最小加注金额
        min_raise_total = 0
        call_amount = 0
        if player_id and self.players:
            current_player = next((p for p in self.players if p.id == player_id), None)
            if current_player:
                call_amount = self.current_bet - current_player.bet
                # 最小加注总额 = 跟注金额 + 最小加注增量
                min_raise_total = call_amount + max(self.min_raise, self.big_blind)

        # 计算剩余时间
        remaining_time = self.turn_timeout
        if self.current_turn_start_time and self.game_stage not in ["waiting", "showdown"]:
            import time
            elapsed = time.time() - self.current_turn_start_time
            remaining_time = max(0, self.turn_timeout - elapsed)

        return {
            "game_stage": self.game_stage,
            "pot": self.pot,
            "current_bet": self.current_bet,
            "min_raise": max(self.min_raise, self.big_blind),  # 最小加注增量
            "min_raise_total": min_raise_total,  # 最小加注总额
            "call_amount": call_amount,  # 跟注金额
            "big_blind": self.big_blind,  # 大盲注
            "turn_timeout": self.turn_timeout,  # 超时设置
            "remaining_time": remaining_time,  # 剩余时间
            "community_cards": [card.to_dict() for card in self.community_cards],
            "players": [
                p.to_dict(show_cards=(p.id == player_id or show_all_cards))
                for p in self.players
            ],
            "current_player_id": self.players[self.current_player_index].id if self.players and self.current_player_index < len(self.players) else None,
            "dealer_index": self.dealer_index if self.players else -1,
            "game_result": self.game_result,
            "room_owner_id": self.room_owner_id,
            "game_ended": self.game_ended,
            "final_results": self.final_results
        }
    
    def end_game(self, player_id: str) -> bool:
        """结束游戏（仅房主可调用）"""
        if player_id != self.room_owner_id:
            return False
        
        self.game_ended = True
        
        # 生成最终结果
        players_sorted = sorted(self.players, key=lambda p: p.total_win, reverse=True)
        
        self.final_results = {
            "total_games": self.game_number,
            "rankings": [
                {
                    "rank": idx + 1,
                    "player_id": p.id,
                    "player_name": p.name,
                    "final_chips": p.chips,
                    "total_win": p.total_win,
                    "games_played": p.games_played,
                    "games_won": p.games_won,
                    "win_rate": (p.games_won / max(p.games_played, 1)) * 100,
                    "rebuys": p.rebuys
                }
                for idx, p in enumerate(players_sorted)
            ]
        }
        
        return True
