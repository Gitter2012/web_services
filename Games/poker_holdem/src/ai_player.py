"""
AI玩家模块
实现基于规则的德州扑克AI玩家
"""
import random
from typing import List, Tuple
from .poker_game import Player, Card, HandRank, HandEvaluator, Rank


class AIPlayer(Player):
    """AI玩家类"""
    
    # AI性格类型
    PERSONALITY_TIGHT = "tight"  # 紧凶型：只玩好牌，下注激进
    PERSONALITY_LOOSE = "loose"  # 松凶型：玩很多牌，下注激进
    PERSONALITY_PASSIVE = "passive"  # 被动型：跟注为主，少加注
    PERSONALITY_BALANCED = "balanced"  # 平衡型：根据情况调整
    
    def __init__(self, id: str, name: str, chips: int = 1000, personality: str = PERSONALITY_BALANCED):
        super().__init__(id, name, chips)
        self.personality = personality
        self.is_ai = True
        
        # 性格参数
        self.aggression = self._get_aggression()  # 激进度 0-1
        self.tightness = self._get_tightness()  # 紧度 0-1（越高越挑剔）
        self.bluff_frequency = self._get_bluff_frequency()  # 诈唬频率 0-1
    
    def _get_aggression(self) -> float:
        """获取激进度"""
        if self.personality == self.PERSONALITY_TIGHT:
            return 0.8
        elif self.personality == self.PERSONALITY_LOOSE:
            return 0.9
        elif self.personality == self.PERSONALITY_PASSIVE:
            return 0.3
        else:  # balanced
            return 0.6
    
    def _get_tightness(self) -> float:
        """获取紧度"""
        if self.personality == self.PERSONALITY_TIGHT:
            return 0.8
        elif self.personality == self.PERSONALITY_LOOSE:
            return 0.3
        elif self.personality == self.PERSONALITY_PASSIVE:
            return 0.6
        else:  # balanced
            return 0.5
    
    def _get_bluff_frequency(self) -> float:
        """获取诈唬频率"""
        if self.personality == self.PERSONALITY_TIGHT:
            return 0.1
        elif self.personality == self.PERSONALITY_LOOSE:
            return 0.3
        elif self.personality == self.PERSONALITY_PASSIVE:
            return 0.05
        else:  # balanced
            return 0.15
    
    def evaluate_hand_strength(self, community_cards: List[Card]) -> float:
        """
        评估手牌强度
        返回: 0-1之间的值，1表示最强
        """
        if not self.hand:
            return 0.0
        
        # 如果有公共牌，评估最终牌型
        if community_cards:
            all_cards = self.hand + community_cards
            rank, values = HandEvaluator.evaluate(all_cards)
            
            # 根据牌型给分
            rank_scores = {
                HandRank.HIGH_CARD: 0.1,
                HandRank.PAIR: 0.3,
                HandRank.TWO_PAIR: 0.5,
                HandRank.THREE_OF_KIND: 0.6,
                HandRank.STRAIGHT: 0.7,
                HandRank.FLUSH: 0.8,
                HandRank.FULL_HOUSE: 0.85,
                HandRank.FOUR_OF_KIND: 0.95,
                HandRank.STRAIGHT_FLUSH: 0.98,
                HandRank.ROYAL_FLUSH: 1.0
            }
            
            base_score = rank_scores.get(rank, 0.1)
            
            # 根据牌面大小微调
            if values:
                high_card_bonus = values[0] / 14.0 * 0.1  # 最高牌的加成
                return min(1.0, base_score + high_card_bonus)
            
            return base_score
        else:
            # 翻牌前，只评估起手牌
            return self._evaluate_preflop_hand()
    
    def _evaluate_preflop_hand(self) -> float:
        """评估翻牌前起手牌强度"""
        if len(self.hand) != 2:
            return 0.0
        
        card1, card2 = self.hand
        rank1 = card1.rank.numeric_value
        rank2 = card2.rank.numeric_value
        
        # 是否同花
        suited = card1.suit == card2.suit
        
        # 是否对子
        is_pair = rank1 == rank2
        
        # 高牌
        high_card = max(rank1, rank2)
        low_card = min(rank1, rank2)
        
        # 间隔
        gap = high_card - low_card
        
        # 基础分数（基于高牌）
        score = high_card / 14.0 * 0.5
        
        # 对子加成
        if is_pair:
            if high_card >= 10:  # JJ, QQ, KK, AA
                score = 0.9 + (high_card - 10) / 4.0 * 0.1
            elif high_card >= 7:  # 77-TT
                score = 0.7 + (high_card - 7) / 3.0 * 0.2
            else:  # 22-66
                score = 0.5 + (high_card - 2) / 5.0 * 0.2
        
        # 大牌加成
        if not is_pair:
            if high_card == 14:  # A
                if low_card >= 10:  # AK, AQ, AJ, AT
                    score = 0.8 + (low_card - 10) / 4.0 * 0.15
                else:
                    score = 0.5 + (low_card - 2) / 8.0 * 0.3
            elif high_card == 13:  # K
                if low_card >= 10:  # KQ, KJ, KT
                    score = 0.65 + (low_card - 10) / 3.0 * 0.1
                else:
                    score = 0.4 + (low_card - 2) / 8.0 * 0.25
            elif high_card >= 10 and low_card >= 9:  # QJ, QT, JT
                score = 0.6 + (high_card + low_card - 19) / 4.0 * 0.1
        
        # 同花加成
        if suited and not is_pair:
            score += 0.1
        
        # 连牌加成
        if gap == 1 and not is_pair:  # 连牌
            score += 0.05
        elif gap == 2:  # 一个间隔
            score += 0.02
        
        return min(1.0, score)
    
    def decide_action(
        self, 
        current_bet: int, 
        pot: int, 
        community_cards: List[Card],
        game_stage: str
    ) -> Tuple[str, int]:
        """
        AI决策行动
        返回: (行动类型, 金额)
        """
        # 如果已经弃牌或all-in，不能行动
        if self.folded or self.all_in:
            return "check", 0
        
        # 评估手牌强度
        hand_strength = self.evaluate_hand_strength(community_cards)
        
        # 计算需要跟注的金额
        call_amount = current_bet - self.bet
        
        # 如果不需要下注，可以过牌
        if call_amount == 0:
            # 决定是否加注
            if self._should_raise(hand_strength, pot, game_stage):
                raise_amount = self._calculate_raise_amount(pot, hand_strength, game_stage)
                return "raise", min(raise_amount, self.chips)
            else:
                return "check", 0
        
        # 需要跟注的情况
        if call_amount > self.chips:
            # 筹码不够，只能all-in或弃牌
            if hand_strength >= self.tightness * 0.5:
                return "call", self.chips  # all-in
            else:
                return "fold", 0
        
        # 根据手牌强度和赔率决定
        pot_odds = call_amount / (pot + call_amount) if (pot + call_amount) > 0 else 1
        
        # 调整后的手牌强度（考虑性格）
        adjusted_strength = hand_strength
        
        # 诈唬逻辑
        if random.random() < self.bluff_frequency:
            adjusted_strength += 0.2
        
        # 决策逻辑
        if adjusted_strength < self.tightness * 0.4:
            # 手牌太弱，弃牌
            return "fold", 0
        elif adjusted_strength < pot_odds + 0.2:
            # 手牌中等但赔率不好
            if random.random() < 0.3:
                return "call", call_amount
            else:
                return "fold", 0
        elif adjusted_strength >= self.tightness * 0.7:
            # 手牌很好，考虑加注
            if self._should_raise(hand_strength, pot, game_stage):
                raise_amount = self._calculate_raise_amount(pot, hand_strength, game_stage)
                return "raise", min(raise_amount, self.chips)
            else:
                return "call", call_amount
        else:
            # 手牌还可以，跟注
            return "call", call_amount
    
    def _should_raise(self, hand_strength: float, pot: int, game_stage: str) -> bool:
        """判断是否应该加注"""
        # 根据游戏阶段调整
        stage_threshold = {
            "preflop": 0.7,
            "flop": 0.65,
            "turn": 0.7,
            "river": 0.75
        }
        
        threshold = stage_threshold.get(game_stage, 0.7)
        threshold *= (1 - self.aggression * 0.3)  # 激进的AI更容易加注
        
        # 手牌够强且随机因子通过
        return hand_strength >= threshold and random.random() < self.aggression
    
    def _calculate_raise_amount(self, pot: int, hand_strength: float, game_stage: str) -> int:
        """计算加注金额"""
        # 基础加注：0.5-1.5倍底池
        base_raise = pot * (0.5 + hand_strength)
        
        # 根据游戏阶段调整
        if game_stage == "preflop":
            base_raise *= 0.5  # 翻牌前保守
        elif game_stage == "river":
            base_raise *= 1.2  # 河牌激进
        
        # 根据性格调整
        base_raise *= (0.5 + self.aggression)
        
        # 限制在合理范围
        min_raise = pot * 0.3
        max_raise = min(self.chips, pot * 2)
        
        raise_amount = max(min_raise, min(base_raise, max_raise))
        
        return int(raise_amount)


class AIPlayerFactory:
    """AI玩家工厂"""
    
    AI_NAMES = [
        "机器人Alice", "机器人Bob", "机器人Charlie", 
        "机器人Diana", "机器人Eve", "机器人Frank",
        "机器人Grace", "机器人Henry"
    ]
    
    @staticmethod
    def create_ai_player(player_id: str, index: int = 0, chips: int = 1000) -> AIPlayer:
        """创建AI玩家"""
        personalities = [
            AIPlayer.PERSONALITY_TIGHT,
            AIPlayer.PERSONALITY_LOOSE,
            AIPlayer.PERSONALITY_PASSIVE,
            AIPlayer.PERSONALITY_BALANCED
        ]
        
        name = AIPlayerFactory.AI_NAMES[index % len(AIPlayerFactory.AI_NAMES)]
        personality = personalities[index % len(personalities)]
        
        return AIPlayer(
            id=player_id,
            name=name,
            chips=chips,
            personality=personality
        )
    
    @staticmethod
    def create_multiple_ai_players(count: int, starting_chips: int = 1000) -> List[AIPlayer]:
        """创建多个AI玩家"""
        players = []
        for i in range(count):
            player_id = f"ai_{i+1}"
            player = AIPlayerFactory.create_ai_player(player_id, i, starting_chips)
            players.append(player)
        return players
