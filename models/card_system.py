from enum import Enum
from typing import List, Tuple, Dict, Optional
from dataclasses import dataclass
import random
from collections import Counter


class Suit(Enum):
    """扑克牌花色枚举"""
    CLUBS = "♣"      # 梅花
    DIAMONDS = "♦"   # 方片
    HEARTS = "♥"     # 红桃
    SPADES = "♠"     # 黑桃


class Rank(Enum):
    """扑克牌点数枚举"""
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
    
    @property
    def numeric_value(self) -> int:
        """获取数值"""
        return self.value[0]
    
    @property
    def display(self) -> str:
        """获取显示字符"""
        return self.value[1]


class HandRank(Enum):
    """德州扑克牌型等级"""
    HIGH_CARD = (1, "高牌")
    ONE_PAIR = (2, "一对")
    TWO_PAIR = (3, "两对")
    THREE_KIND = (4, "三条")
    STRAIGHT = (5, "顺子")
    FLUSH = (6, "同花")
    FULL_HOUSE = (7, "葫芦")
    FOUR_KIND = (8, "四条")
    STRAIGHT_FLUSH = (9, "同花顺")
    ROYAL_FLUSH = (10, "皇家同花顺")
    
    @property
    def rank_value(self) -> int:
        """获取牌型等级值"""
        return self.value[0]
    
    @property  
    def name_cn(self) -> str:
        """获取中文名称"""
        return self.value[1]


@dataclass
class Card:
    """
    扑克牌类
    
    属性：
    - suit: 花色
    - rank: 点数
    
    方法：
    - __str__: 返回牌的字符串表示
    - __eq__: 比较两张牌是否相等
    - __lt__: 比较牌的大小（按点数）
    """
    suit: Suit
    rank: Rank
    
    def __str__(self) -> str:
        """
        返回扑克牌的字符串表示
        
        Returns:
            str: 如"♠A", "♥K"等格式
        """
        return f"{self.suit.value}{self.rank.display}"
    
    def __eq__(self, other) -> bool:
        """
        比较两张牌是否完全相同
        
        Args:
            other: 另一张牌对象
            
        Returns:
            bool: 是否相同
        """
        if not isinstance(other, Card):
            return False
        return self.suit == other.suit and self.rank == other.rank
    
    def __lt__(self, other) -> bool:
        """
        比较牌的点数大小
        
        Args:
            other: 另一张牌对象
            
        Returns:
            bool: 是否小于另一张牌
        """
        return self.rank.numeric_value < other.rank.numeric_value
    
    def __hash__(self) -> int:
        """
        返回牌的哈希值，用于集合和字典操作
        
        Returns:
            int: 哈希值
        """
        return hash((self.suit, self.rank))


@dataclass
class HandEvaluation:
    """
    手牌评估结果
    
    属性：
    - hand_rank: 牌型等级
    - primary_value: 主要比较值（如对子的点数）
    - secondary_value: 次要比较值（如两对中较小的对子）
    - kickers: 踢脚牌列表（用于平局时比较）
    - best_cards: 组成最佳牌型的5张牌
    """
    hand_rank: HandRank
    primary_value: int
    secondary_value: int = 0
    kickers: List[int] = None
    best_cards: List[Card] = None
    
    def __post_init__(self):
        """初始化后处理"""
        if self.kickers is None:
            self.kickers = []
        if self.best_cards is None:
            self.best_cards = []
    
    def __lt__(self, other) -> bool:
        """
        比较两个手牌评估结果的大小
        
        Args:
            other: 另一个手牌评估结果
            
        Returns:
            bool: 当前牌型是否小于另一个
        """
        if self.hand_rank.rank_value != other.hand_rank.rank_value:
            return self.hand_rank.rank_value < other.hand_rank.rank_value
        
        if self.primary_value != other.primary_value:
            return self.primary_value < other.primary_value
            
        if self.secondary_value != other.secondary_value:
            return self.secondary_value < other.secondary_value
        
        # 比较踢脚牌
        for k1, k2 in zip(self.kickers, other.kickers):
            if k1 != k2:
                return k1 < k2
                
        return False  # 完全相等
    
    def __le__(self, other) -> bool:
        """小于等于比较"""
        return self.__lt__(other) or self.__eq__(other)
    
    def __gt__(self, other) -> bool:
        """大于比较"""
        return not self.__le__(other)
    
    def __ge__(self, other) -> bool:
        """大于等于比较"""
        return not self.__lt__(other)
    
    def __eq__(self, other) -> bool:
        """等于比较"""
        return (self.hand_rank.rank_value == other.hand_rank.rank_value and
                self.primary_value == other.primary_value and
                self.secondary_value == other.secondary_value and
                self.kickers == other.kickers)
    
    def __ne__(self, other) -> bool:
        """不等于比较"""
        return not self.__eq__(other)


class CardSystem:
    """
    扑克牌系统管理类
    
    功能包括：
    - 生成完整的52张牌库
    - 洗牌和发牌
    - 手牌评估和牌型判断
    - 最佳牌型计算
    """
    
    def __init__(self):
        """初始化扑克牌系统"""
        self.deck: List[Card] = []
        self._create_deck()
    
    def _create_deck(self) -> None:
        """
        创建完整的52张扑克牌
        
        生成所有花色和点数的组合
        """
        self.deck = []
        for suit in Suit:
            for rank in Rank:
                self.deck.append(Card(suit, rank))
    
    def shuffle_deck(self) -> None:
        """
        洗牌操作
        
        使用随机算法打乱牌的顺序
        """
        random.shuffle(self.deck)
    
    def deal_card(self) -> Optional[Card]:
        """
        发一张牌
        
        Returns:
            Optional[Card]: 发出的牌，如果牌库为空返回None
        """
        if not self.deck:
            return None
        return self.deck.pop()
    
    def deal_cards(self, count: int) -> List[Card]:
        """
        发多张牌
        
        Args:
            count: 要发的牌数
            
        Returns:
            List[Card]: 发出的牌列表
        """
        cards = []
        for _ in range(count):
            card = self.deal_card()
            if card:
                cards.append(card)
        return cards
    
    def reset_deck(self) -> None:
        """
        重置牌库
        
        重新创建完整的52张牌并洗牌
        """
        self._create_deck()
        self.shuffle_deck()
    
    def cards_remaining(self) -> int:
        """
        获取剩余牌数
        
        Returns:
            int: 牌库中剩余的牌数
        """
        return len(self.deck)
    
    def evaluate_hand(self, hole_cards: List[Card], community_cards: List[Card]) -> HandEvaluation:
        """
        评估手牌
        
        从底牌和公共牌中选出最佳的5张牌组合
        
        Args:
            hole_cards: 玩家的底牌（2张）
            community_cards: 公共牌（最多5张）
            
        Returns:
            HandEvaluation: 手牌评估结果
        """
        all_cards = hole_cards + community_cards
        if len(all_cards) < 5:
            # 如果总牌数不足5张，按高牌处理
            sorted_cards = sorted(all_cards, key=lambda c: c.rank.numeric_value, reverse=True)
            return HandEvaluation(
                hand_rank=HandRank.HIGH_CARD,
                primary_value=sorted_cards[0].rank.numeric_value,
                kickers=[c.rank.numeric_value for c in sorted_cards[1:]],
                best_cards=all_cards
            )
        
        # 生成所有可能的5张牌组合
        from itertools import combinations
        best_evaluation = None
        
        for five_cards in combinations(all_cards, 5):
            evaluation = self._evaluate_five_cards(list(five_cards))
            if best_evaluation is None or evaluation > best_evaluation:
                best_evaluation = evaluation
        
        return best_evaluation
    
    def _evaluate_five_cards(self, cards: List[Card]) -> HandEvaluation:
        """
        评估5张牌的牌型
        
        Args:
            cards: 5张牌的列表
            
        Returns:
            HandEvaluation: 评估结果
        """
        # 按点数排序
        sorted_cards = sorted(cards, key=lambda c: c.rank.numeric_value, reverse=True)
        ranks = [c.rank.numeric_value for c in sorted_cards]
        suits = [c.suit for c in sorted_cards]
        
        # 统计点数出现次数
        rank_counts = Counter(ranks)
        count_values = sorted(rank_counts.values(), reverse=True)
        
        # 判断是否同花
        is_flush = len(set(suits)) == 1
        
        # 判断是否顺子
        is_straight = self._is_straight(ranks)
        
        # 特殊处理A-2-3-4-5顺子
        if ranks == [14, 5, 4, 3, 2]:
            is_straight = True
            # A作为1处理
            ranks = [5, 4, 3, 2, 1]
            sorted_cards = sorted_cards[1:] + [sorted_cards[0]]  # A移到末尾
        
        # 判断牌型
        if is_straight and is_flush:
            if ranks[0] == 14:  # A K Q J 10
                return HandEvaluation(
                    hand_rank=HandRank.ROYAL_FLUSH,
                    primary_value=ranks[0],
                    best_cards=sorted_cards
                )
            else:
                return HandEvaluation(
                    hand_rank=HandRank.STRAIGHT_FLUSH,
                    primary_value=ranks[0],
                    best_cards=sorted_cards
                )
        
        if count_values == [4, 1]:  # 四条
            four_kind_rank = [rank for rank, count in rank_counts.items() if count == 4][0]
            kicker = [rank for rank, count in rank_counts.items() if count == 1][0]
            return HandEvaluation(
                hand_rank=HandRank.FOUR_KIND,
                primary_value=four_kind_rank,
                kickers=[kicker],
                best_cards=sorted_cards
            )
        
        if count_values == [3, 2]:  # 葫芦
            three_kind_rank = [rank for rank, count in rank_counts.items() if count == 3][0]
            pair_rank = [rank for rank, count in rank_counts.items() if count == 2][0]
            return HandEvaluation(
                hand_rank=HandRank.FULL_HOUSE,
                primary_value=three_kind_rank,
                secondary_value=pair_rank,
                best_cards=sorted_cards
            )
        
        if is_flush:  # 同花
            return HandEvaluation(
                hand_rank=HandRank.FLUSH,
                primary_value=ranks[0],
                kickers=ranks[1:],
                best_cards=sorted_cards
            )
        
        if is_straight:  # 顺子
            return HandEvaluation(
                hand_rank=HandRank.STRAIGHT,
                primary_value=ranks[0],
                best_cards=sorted_cards
            )
        
        if count_values == [3, 1, 1]:  # 三条
            three_kind_rank = [rank for rank, count in rank_counts.items() if count == 3][0]
            kickers = sorted([rank for rank, count in rank_counts.items() if count == 1], reverse=True)
            return HandEvaluation(
                hand_rank=HandRank.THREE_KIND,
                primary_value=three_kind_rank,
                kickers=kickers,
                best_cards=sorted_cards
            )
        
        if count_values == [2, 2, 1]:  # 两对
            pairs = sorted([rank for rank, count in rank_counts.items() if count == 2], reverse=True)
            kicker = [rank for rank, count in rank_counts.items() if count == 1][0]
            return HandEvaluation(
                hand_rank=HandRank.TWO_PAIR,
                primary_value=pairs[0],
                secondary_value=pairs[1],
                kickers=[kicker],
                best_cards=sorted_cards
            )
        
        if count_values == [2, 1, 1, 1]:  # 一对
            pair_rank = [rank for rank, count in rank_counts.items() if count == 2][0]
            kickers = sorted([rank for rank, count in rank_counts.items() if count == 1], reverse=True)
            return HandEvaluation(
                hand_rank=HandRank.ONE_PAIR,
                primary_value=pair_rank,
                kickers=kickers,
                best_cards=sorted_cards
            )
        
        # 高牌
        return HandEvaluation(
            hand_rank=HandRank.HIGH_CARD,
            primary_value=ranks[0],
            kickers=ranks[1:],
            best_cards=sorted_cards
        )
    
    def _is_straight(self, ranks: List[int]) -> bool:
        """
        判断是否为顺子
        
        Args:
            ranks: 按降序排列的点数列表
            
        Returns:
            bool: 是否为顺子
        """
        # 检查连续性
        for i in range(len(ranks) - 1):
            if ranks[i] - ranks[i + 1] != 1:
                return False
        return True
    
    def format_hand_evaluation(self, evaluation: HandEvaluation) -> str:
        """
        格式化手牌评估结果为可读字符串
        
        Args:
            evaluation: 手牌评估结果
            
        Returns:
            str: 格式化的字符串描述
        """
        rank_names = {
            2: "2", 3: "3", 4: "4", 5: "5", 6: "6", 7: "7", 8: "8",
            9: "9", 10: "10", 11: "J", 12: "Q", 13: "K", 14: "A", 1: "A"
        }
        
        cards_str = " ".join([str(card) for card in evaluation.best_cards])
        
        if evaluation.hand_rank == HandRank.ROYAL_FLUSH:
            return f"皇家同花顺 [{cards_str}]"
        elif evaluation.hand_rank == HandRank.STRAIGHT_FLUSH:
            return f"同花顺 {rank_names[evaluation.primary_value]}高 [{cards_str}]"
        elif evaluation.hand_rank == HandRank.FOUR_KIND:
            return f"四条{rank_names[evaluation.primary_value]} [{cards_str}]"
        elif evaluation.hand_rank == HandRank.FULL_HOUSE:
            return f"葫芦 {rank_names[evaluation.primary_value]}带{rank_names[evaluation.secondary_value]} [{cards_str}]"
        elif evaluation.hand_rank == HandRank.FLUSH:
            return f"同花 {rank_names[evaluation.primary_value]}高 [{cards_str}]"
        elif evaluation.hand_rank == HandRank.STRAIGHT:
            return f"顺子 {rank_names[evaluation.primary_value]}高 [{cards_str}]"
        elif evaluation.hand_rank == HandRank.THREE_KIND:
            return f"三条{rank_names[evaluation.primary_value]} [{cards_str}]"
        elif evaluation.hand_rank == HandRank.TWO_PAIR:
            return f"两对 {rank_names[evaluation.primary_value]}和{rank_names[evaluation.secondary_value]} [{cards_str}]"
        elif evaluation.hand_rank == HandRank.ONE_PAIR:
            return f"一对{rank_names[evaluation.primary_value]} [{cards_str}]"
        else:
            return f"高牌{rank_names[evaluation.primary_value]} [{cards_str}]"
