from enum import Enum
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
import asyncio
import time
from collections import defaultdict

from .card_system import CardSystem, Card, HandEvaluation


class GamePhase(Enum):
    """德州扑克游戏阶段"""
    WAITING = "waiting"           # 等待玩家
    PRE_FLOP = "pre_flop"        # 发底牌阶段
    FLOP = "flop"                # 翻牌阶段
    TURN = "turn"                # 转牌阶段
    RIVER = "river"              # 河牌阶段
    SHOWDOWN = "showdown"        # 摊牌阶段
    GAME_OVER = "game_over"      # 游戏结束


class PlayerAction(Enum):
    """玩家操作类型"""
    FOLD = "fold"                # 弃牌
    CHECK = "check"              # 过牌
    CALL = "call"                # 跟注
    RAISE = "raise"              # 加注
    ALL_IN = "all_in"           # 全押


class PlayerStatus(Enum):
    """玩家状态"""
    ACTIVE = "active"            # 活跃状态
    FOLDED = "folded"           # 已弃牌
    ALL_IN = "all_in"           # 已全押
    WAITING = "waiting"          # 等待状态


@dataclass
class GamePlayer:
    """
    游戏中的玩家对象
    
    属性：
    - player_id: 玩家ID
    - chips: 当前筹码数
    - hole_cards: 底牌（2张）
    - current_bet: 当前轮次已下注金额
    - total_bet: 总下注金额
    - status: 玩家状态
    - position: 座位位置
    - is_dealer: 是否为庄家
    - is_small_blind: 是否为小盲
    - is_big_blind: 是否为大盲
    """
    player_id: str
    chips: int
    hole_cards: List[Card] = field(default_factory=list)
    current_bet: int = 0
    total_bet: int = 0
    status: PlayerStatus = PlayerStatus.WAITING
    position: int = 0
    is_dealer: bool = False
    is_small_blind: bool = False
    is_big_blind: bool = False
    last_action: Optional[PlayerAction] = None
    last_action_time: float = field(default_factory=time.time)
    
    def reset_for_new_hand(self):
        """
        为新一局重置玩家状态
        
        清除底牌、下注记录等，保留筹码和位置信息
        """
        self.hole_cards.clear()
        self.current_bet = 0
        self.total_bet = 0
        self.status = PlayerStatus.ACTIVE if self.chips > 0 else PlayerStatus.WAITING
        self.last_action = None
        self.last_action_time = time.time()
    
    def can_act(self) -> bool:
        """
        判断玩家是否可以行动
        
        Returns:
            bool: 是否可以行动
        """
        return self.status in [PlayerStatus.ACTIVE, PlayerStatus.WAITING] and self.chips > 0
    
    def is_in_hand(self) -> bool:
        """
        判断玩家是否还在牌局中
        
        Returns:
            bool: 是否在牌局中
        """
        return self.status in [PlayerStatus.ACTIVE, PlayerStatus.ALL_IN]


@dataclass
class SidePot:
    """
    边池对象
    
    属性：
    - amount: 边池金额
    - eligible_players: 有资格参与分配的玩家列表
    """
    amount: int
    eligible_players: List[str]


class TexasHoldemGame:
    """
    德州扑克游戏引擎
    
    功能包括：
    - 游戏流程控制（发牌、下注轮次、摊牌等）
    - 玩家操作处理和验证
    - 下注逻辑和边池计算
    - 游戏结果计算和分配
    - 超时处理和断线重连
    """
    
    def __init__(self, room_id: str, small_blind: int, big_blind: int, max_players: int = 6):
        """
        初始化德州扑克游戏
        
        Args:
            room_id: 房间ID
            small_blind: 小盲注金额
            big_blind: 大盲注金额
            max_players: 最大玩家数
        """
        self.room_id = room_id
        self.small_blind = small_blind
        self.big_blind = big_blind
        self.max_players = max_players
        
        # 游戏状态
        self.game_phase = GamePhase.WAITING
        self.hand_number = 0
        self.dealer_position = 0
        
        # 玩家和座位管理
        self.players: Dict[str, GamePlayer] = {}
        self.player_order: List[str] = []  # 按座位顺序的玩家ID列表
        self.active_players: List[str] = []  # 当前活跃玩家列表
        
        # 游戏进行状态
        self.current_player_index = 0
        self.current_player_id: Optional[str] = None
        self.last_raise_player_id: Optional[str] = None
        self.current_bet = 0  # 当前轮次的最高下注
        
        # 牌和底池
        self.card_system = CardSystem()
        self.community_cards: List[Card] = []
        self.main_pot = 0
        self.side_pots: List[SidePot] = []
        
        # 游戏历史和结果
        self.action_history: List[Dict[str, Any]] = []
        self.game_results: Dict[str, Dict[str, Any]] = {}
        
        # 超时设置
        self.action_timeout = 30  # 30秒操作超时
        self.timeout_task: Optional[asyncio.Task] = None
    
    def add_player(self, player_id: str, chips: int) -> bool:
        """
        添加玩家到游戏中
        
        Args:
            player_id: 玩家ID
            chips: 玩家筹码数
            
        Returns:
            bool: 是否成功添加
        """
        if len(self.players) >= self.max_players:
            return False
        
        if player_id in self.players:
            return False
        
        # 找到空座位
        position = len(self.players)
        
        player = GamePlayer(
            player_id=player_id,
            chips=chips,
            position=position
        )
        
        self.players[player_id] = player
        self.player_order.append(player_id)
        
        # 不自动开始游戏，等待手动开始
        # if len(self.players) >= 2 and self.game_phase == GamePhase.WAITING:
        #     self.start_new_hand()
        
        return True
    
    def remove_player(self, player_id: str) -> bool:
        """
        移除玩家
        
        Args:
            player_id: 玩家ID
            
        Returns:
            bool: 是否成功移除
        """
        if player_id not in self.players:
            return False
        
        player = self.players[player_id]
        
        # 如果游戏进行中且玩家还在牌局中，自动弃牌
        if self.game_phase not in [GamePhase.WAITING, GamePhase.GAME_OVER] and player.is_in_hand():
            self._handle_fold_action(player_id)
        
        # 移除玩家
        del self.players[player_id]
        if player_id in self.player_order:
            self.player_order.remove(player_id)
        if player_id in self.active_players:
            self.active_players.remove(player_id)
        
        # 检查游戏是否可以继续
        if len(self.players) < 2:
            self._end_game()
        
        return True
    
    def start_new_hand(self) -> bool:
        """
        开始新一局游戏
        
        Returns:
            bool: 是否成功开始
        """
        if len(self.players) < 2:
            return False
        
        # 重置游戏状态
        self.hand_number += 1
        self.game_phase = GamePhase.PRE_FLOP
        self.community_cards.clear()
        self.main_pot = 0
        self.side_pots.clear()
        self.current_bet = 0
        self.action_history.clear()
        self.game_results.clear()
        
        # 重置玩家状态
        for player in self.players.values():
            player.reset_for_new_hand()
            # 确保玩家状态正确初始化
            if player.chips > 0:
                player.status = PlayerStatus.ACTIVE
            # 清除盲注标记（将在_set_dealer_and_blinds中重新设置）
            player.is_dealer = False
            player.is_small_blind = False
            player.is_big_blind = False
        
        # 设置庄家和盲注位置
        self._set_dealer_and_blinds()
        
        # 发底牌
        self._deal_hole_cards()
        
        # 收取盲注
        self._collect_blinds()
        
        
        # 设置行动顺序
        self._set_action_order()
        
        # 开始第一轮下注
        self._start_betting_round()
        
        return True
    
    def _set_dealer_and_blinds(self):
        """
        设置庄家和盲注位置
        
        庄家按钮顺时针轮转，小盲注在庄家左边，大盲注在小盲注左边
        """
        # 盲注标记已在start_new_hand中清除
        
        active_player_ids = [pid for pid in self.player_order if self.players[pid].chips > 0]
        if len(active_player_ids) < 2:
            return
        
        # 设置庄家
        dealer_id = active_player_ids[self.dealer_position % len(active_player_ids)]
        self.players[dealer_id].is_dealer = True
        
        # 设置盲注
        if len(active_player_ids) == 2:
            # 两人局：庄家是小盲，另一个是大盲
            sb_id = dealer_id
            bb_id = active_player_ids[(self.dealer_position + 1) % len(active_player_ids)]
        else:
            # 多人局：庄家后第一个是小盲，第二个是大盲
            sb_id = active_player_ids[(self.dealer_position + 1) % len(active_player_ids)]
            bb_id = active_player_ids[(self.dealer_position + 2) % len(active_player_ids)]
        
        self.players[sb_id].is_small_blind = True
        self.players[bb_id].is_big_blind = True
        
        
        # 移动庄家位置
        self.dealer_position = (self.dealer_position + 1) % len(active_player_ids)
    
    def _deal_hole_cards(self):
        """
        发底牌
        
        每个玩家发2张底牌
        """
        self.card_system.reset_deck()
        
        # 每轮给每个玩家发一张牌，发两轮
        for _ in range(2):
            for player_id in self.player_order:
                player = self.players[player_id]
                if player.chips > 0:  # 只给有筹码的玩家发牌
                    card = self.card_system.deal_card()
                    if card:
                        player.hole_cards.append(card)
    
    def _collect_blinds(self):
        """
        收取盲注
        
        强制小盲和大盲玩家下注
        """
        for player in self.players.values():
            if player.is_small_blind and player.chips > 0:
                blind_amount = min(self.small_blind, player.chips)
                player.current_bet = blind_amount
                player.total_bet = blind_amount
                player.chips -= blind_amount
                self.main_pot += blind_amount
                if player.chips == 0:
                    player.status = PlayerStatus.ALL_IN
            
            elif player.is_big_blind and player.chips > 0:
                blind_amount = min(self.big_blind, player.chips)
                player.current_bet = blind_amount
                player.total_bet = blind_amount
                player.chips -= blind_amount
                self.main_pot += blind_amount
                self.current_bet = blind_amount
                if player.chips == 0:
                    player.status = PlayerStatus.ALL_IN
    
    def _set_action_order(self):
        """
        设置行动顺序
        
        Pre-flop: 大盲注后第一个玩家开始
        其他阶段: 小盲注开始（如果已弃牌则下一个活跃玩家）
        """
        
        # 重新计算活跃玩家列表
        self.active_players = [
            pid for pid in self.player_order 
            if self.players[pid].can_act()
        ]
        
        for pid in self.player_order:
            player = self.players[pid]
        
        if not self.active_players:
            return
        
        if self.game_phase == GamePhase.PRE_FLOP:
            # Pre-flop阶段：在2人游戏中，小盲注（庄家）先行动
            sb_player_id = next((pid for pid in self.player_order if self.players[pid].is_small_blind), None)
            if sb_player_id and sb_player_id in self.active_players:
                start_index = self.active_players.index(sb_player_id)
            else:
                start_index = 0
        else:
            # 其他阶段从小盲注开始
            sb_player_id = next((pid for pid in self.player_order if self.players[pid].is_small_blind), None)
            if sb_player_id and sb_player_id in self.active_players:
                start_index = self.active_players.index(sb_player_id)
            else:
                start_index = 0
        
        self.current_player_index = start_index
        self.current_player_id = self.active_players[self.current_player_index]
        self.last_raise_player_id = None
        
    
    def _start_betting_round(self):
        """
        开始下注轮次
        
        设置当前玩家并启动超时计时器
        """
        if not self.active_players:
            self._advance_to_next_phase()
            return
        
        # 只有在非Pre-flop阶段才重置当前轮次下注（Pre-flop阶段需要保留盲注）
        if self.game_phase != GamePhase.PRE_FLOP:
            for player in self.players.values():
                player.current_bet = 0
            self.current_bet = 0
        
        # 启动超时计时器
        self._start_action_timeout()
    
    def player_action(self, player_id: str, action: PlayerAction, amount: int = 0) -> bool:
        """
        处理玩家操作（同步版本）
        
        Args:
            player_id: 玩家ID
            action: 操作类型
            amount: 操作金额（加注时使用）
            
        Returns:
            bool: 操作是否成功
        """
        # 验证操作合法性
        if not self._is_valid_action(player_id, action, amount):
            return False
        
        player = self.players[player_id]
        
        # 执行操作
        if action == PlayerAction.FOLD:
            self._handle_fold_action(player_id)
        elif action == PlayerAction.CHECK:
            self._handle_check_action(player_id)
        elif action == PlayerAction.CALL:
            self._handle_call_action(player_id)
        elif action == PlayerAction.RAISE:
            self._handle_raise_action(player_id, amount)
        elif action == PlayerAction.ALL_IN:
            self._handle_all_in_action(player_id)
        
        # 记录操作
        self._record_action(player_id, action, amount)
        
        # 检查下注轮次是否结束
        round_complete = self._is_betting_round_complete()
        
        if round_complete:
            self._advance_to_next_phase()
        else:
            # 轮到下一个玩家
            old_player = self.current_player_id
            self._move_to_next_player()
        
        return True
    
    async def handle_player_action(self, player_id: str, action: PlayerAction, amount: int = 0) -> bool:
        """
        处理玩家操作
        
        Args:
            player_id: 玩家ID
            action: 操作类型
            amount: 操作金额（加注时使用）
            
        Returns:
            bool: 操作是否成功
        """
        # 验证操作合法性
        if not self._is_valid_action(player_id, action, amount):
            return False
        
        player = self.players[player_id]
        
        # 取消超时计时器
        if self.timeout_task:
            self.timeout_task.cancel()
        
        # 执行操作
        if action == PlayerAction.FOLD:
            self._handle_fold_action(player_id)
        elif action == PlayerAction.CHECK:
            self._handle_check_action(player_id)
        elif action == PlayerAction.CALL:
            self._handle_call_action(player_id)
        elif action == PlayerAction.RAISE:
            self._handle_raise_action(player_id, amount)
        elif action == PlayerAction.ALL_IN:
            self._handle_all_in_action(player_id)
        
        # 记录操作
        self._record_action(player_id, action, amount)
        
        # 检查下注轮次是否结束
        if self._is_betting_round_complete():
            self._advance_to_next_phase()
        else:
            self._move_to_next_player()
        
        return True
    
    def _is_valid_action(self, player_id: str, action: PlayerAction, amount: int = 0) -> bool:
        """
        验证玩家操作是否合法
        
        Args:
            player_id: 玩家ID
            action: 操作类型
            amount: 操作金额
            
        Returns:
            bool: 是否合法
        """
        if player_id != self.current_player_id:
            return False
        
        if player_id not in self.players:
            return False
        
        player = self.players[player_id]
        if not player.can_act():
            return False
        
        call_amount = self.current_bet - player.current_bet
        
        if action == PlayerAction.CHECK:
            # 只有在无需跟注时才能过牌
            return call_amount == 0
        
        elif action == PlayerAction.CALL:
            # 需要有足够筹码跟注，且确实需要跟注
            return call_amount > 0 and player.chips >= call_amount
        
        elif action == PlayerAction.RAISE:
            # 加注金额必须至少是最小加注额
            min_raise = self.big_blind if self.current_bet == 0 else self.current_bet * 2 - player.current_bet
            total_needed = call_amount + amount
            return amount > 0 and total_needed >= min_raise and player.chips >= total_needed
        
        elif action == PlayerAction.ALL_IN:
            # 全押必须把所有筹码都押上
            return player.chips > 0
        
        # FOLD总是合法的
        return True
    
    def _handle_fold_action(self, player_id: str):
        """处理弃牌操作"""
        player = self.players[player_id]
        player.status = PlayerStatus.FOLDED
        player.last_action = PlayerAction.FOLD
        
        if player_id in self.active_players:
            self.active_players.remove(player_id)
        
        # 检查是否只剩一个玩家在牌局中，如果是则立即结束游戏
        players_in_hand = [p for p in self.players.values() if p.is_in_hand()]
        
        if len(players_in_hand) == 1:
            # 只剩一个玩家，立即结束游戏并分配奖励
            winner = players_in_hand[0]
            self._handle_immediate_win(winner.player_id)
        elif len(players_in_hand) == 0:
            # 所有人都弃牌了，平分底池（不太可能但需要处理）
            self._end_game()
    
    def _handle_immediate_win(self, winner_id: str):
        """
        处理立即获胜（如对手弃牌）
        
        Args:
            winner_id: 获胜玩家ID
        """
        
        # 给获胜者分配底池
        winner = self.players[winner_id]
        total_pot = self.main_pot + sum(pot.amount for pot in self.side_pots)
        winner.chips += total_pot
        
        # 初始化游戏结果
        self.game_results.clear()
        
        # 计算每个玩家的盈亏
        for player_id, player in self.players.items():
            profit = -player.total_bet  # 默认亏损为总下注
            won = False
            
            if player_id == winner_id:
                profit = total_pot - player.total_bet  # 获胜者的利润
                won = True
            
            self.game_results[player_id] = {
                'profit': profit,
                'won': won,
                'hand_evaluation': None,  # 弃牌获胜没有手牌评估
                'final_chips': player.chips,
                'hand_cards': [str(card) for card in player.hole_cards]  # 保存手牌信息
            }
            
        
        # 设置游戏状态为结束
        self.game_phase = GamePhase.GAME_OVER
    
    def _handle_check_action(self, player_id: str):
        """处理过牌操作"""
        player = self.players[player_id]
        player.last_action = PlayerAction.CHECK
    
    def _handle_call_action(self, player_id: str):
        """处理跟注操作"""
        player = self.players[player_id]
        call_amount = self.current_bet - player.current_bet
        
        
        if call_amount >= player.chips:
            # 全押跟注
            bet_amount = player.chips
            player.chips = 0
            player.status = PlayerStatus.ALL_IN
        else:
            bet_amount = call_amount
            player.chips -= bet_amount
        
        player.current_bet += bet_amount
        player.total_bet += bet_amount
        player.last_action = PlayerAction.CALL
        self.main_pot += bet_amount
        
    
    def _handle_raise_action(self, player_id: str, raise_amount: int):
        """处理加注操作"""
        player = self.players[player_id]
        call_amount = self.current_bet - player.current_bet
        total_bet = call_amount + raise_amount
        
        if total_bet >= player.chips:
            # 全押加注
            bet_amount = player.chips
            player.chips = 0
            player.status = PlayerStatus.ALL_IN
        else:
            bet_amount = total_bet
            player.chips -= bet_amount
        
        player.current_bet += bet_amount
        player.total_bet += bet_amount
        player.last_action = PlayerAction.RAISE
        self.current_bet = player.current_bet
        self.last_raise_player_id = player_id
        self.main_pot += bet_amount
    
    def _handle_all_in_action(self, player_id: str):
        """处理全押操作"""
        player = self.players[player_id]
        bet_amount = player.chips
        
        player.current_bet += bet_amount
        player.total_bet += bet_amount
        player.chips = 0
        player.status = PlayerStatus.ALL_IN
        player.last_action = PlayerAction.ALL_IN
        
        # 如果全押金额超过当前最高下注，视为加注
        if player.current_bet > self.current_bet:
            self.current_bet = player.current_bet
            self.last_raise_player_id = player_id
        
        self.main_pot += bet_amount
    
    def _record_action(self, player_id: str, action: PlayerAction, amount: int = 0):
        """
        记录玩家操作到历史中
        
        Args:
            player_id: 玩家ID
            action: 操作类型
            amount: 操作金额
        """
        self.action_history.append({
            'player_id': player_id,
            'action': action.value,
            'amount': amount,
            'phase': self.game_phase.value,
            'timestamp': time.time()
        })
    
    def _is_betting_round_complete(self) -> bool:
        """
        检查当前下注轮次是否完成
        
        Returns:
            bool: 是否完成
        """
        
        # 如果只有一个或没有活跃玩家，下注轮次结束
        in_hand_players = [p for p in self.players.values() if p.is_in_hand()]
        
        if len(in_hand_players) <= 1:
            return True
        
        # 如果所有在牌局中的玩家都已全押，下注轮次结束
        can_act_players = [p for p in in_hand_players if p.can_act()]
        
        if not can_act_players:
            return True
        
        # 获取最高下注金额
        max_bet = max(p.current_bet for p in in_hand_players)
        
        # 检查所有未弃牌且能行动的玩家是否都已匹配最高下注
        for player in in_hand_players:
            if player.status == PlayerStatus.ALL_IN:
                continue  # 全押玩家无需匹配
            if player.can_act() and player.current_bet < max_bet:
                return False
        
        # 确保每个玩家都有机会主动行动（所有阶段都需要）
        for player in in_hand_players:
            if player.can_act() and player.last_action is None:
                return False
        
        
        return True
    
    def _move_to_next_player(self):
        """移动到下一个玩家"""
        if not self.active_players:
            return
        
        # 获取当前玩家在活跃列表中的索引
        try:
            current_index = self.active_players.index(self.current_player_id)
        except ValueError:
            # 当前玩家不在活跃列表中，从第一个开始
            current_index = 0
        
        # 移动到下一个玩家
        next_index = (current_index + 1) % len(self.active_players)
        
        # 更新当前玩家
        self.current_player_index = next_index
        self.current_player_id = self.active_players[next_index]
        
        # 重新验证新的当前玩家是否还能行动
        current_player = self.players[self.current_player_id]
        if not current_player.can_act() or not current_player.is_in_hand():
            # 如果新的当前玩家无法行动，重新更新活跃玩家列表
            self.active_players = [
                pid for pid in self.player_order 
                if self.players[pid].is_in_hand() and self.players[pid].can_act()
            ]
            if self.active_players:
                self.current_player_index = 0
                self.current_player_id = self.active_players[0]
        
        # 启动新的超时计时器
        self._start_action_timeout()
    
    def _advance_to_next_phase(self):
        """进入下一个游戏阶段"""
        if self.game_phase == GamePhase.PRE_FLOP:
            self._deal_flop()
            self.game_phase = GamePhase.FLOP
        elif self.game_phase == GamePhase.FLOP:
            self._deal_turn()
            self.game_phase = GamePhase.TURN
        elif self.game_phase == GamePhase.TURN:
            self._deal_river()
            self.game_phase = GamePhase.RIVER
        elif self.game_phase == GamePhase.RIVER:
            self.game_phase = GamePhase.SHOWDOWN
            self._handle_showdown()
            return
        
        # 重置下注状态为新轮次
        for player in self.players.values():
            player.current_bet = 0
            player.last_action = None  # 重置行动状态，每个阶段都需要重新行动
        self.current_bet = 0
        
        # 开始新的下注轮次
        self._set_action_order()
        self._start_betting_round()
    
    def _deal_flop(self):
        """发翻牌（3张公共牌）"""
        self.card_system.deal_card()  # 弃一张牌
        for _ in range(3):
            card = self.card_system.deal_card()
            if card:
                self.community_cards.append(card)
    
    def _deal_turn(self):
        """发转牌（第4张公共牌）"""
        self.card_system.deal_card()  # 弃一张牌
        card = self.card_system.deal_card()
        if card:
            self.community_cards.append(card)
    
    def _deal_river(self):
        """发河牌（第5张公共牌）"""
        self.card_system.deal_card()  # 弃一张牌
        card = self.card_system.deal_card()
        if card:
            self.community_cards.append(card)
    
    def _handle_showdown(self):
        """处理摊牌阶段"""
        # 计算边池
        self._calculate_side_pots()
        
        # 评估所有玩家的手牌
        player_evaluations = {}
        for player_id, player in self.players.items():
            if player.is_in_hand():
                evaluation = self.card_system.evaluate_hand(player.hole_cards, self.community_cards)
                player_evaluations[player_id] = evaluation
        
        # 分配奖金
        self._distribute_winnings(player_evaluations)
        
        # 结束游戏
        self.game_phase = GamePhase.GAME_OVER
    
    def _calculate_side_pots(self):
        """
        计算边池
        
        当有玩家全押时，需要创建边池来正确分配奖金
        """
        # 收集所有玩家的总下注
        bets = []
        for player in self.players.values():
            if player.total_bet > 0:
                bets.append((player.player_id, player.total_bet))
        
        if not bets:
            return
        
        # 按下注金额排序
        bets.sort(key=lambda x: x[1])
        
        self.side_pots.clear()
        prev_bet = 0
        
        for i, (player_id, bet_amount) in enumerate(bets):
            if bet_amount > prev_bet:
                # 创建新的边池
                pot_amount = (bet_amount - prev_bet) * (len(bets) - i)
                eligible_players = [pid for pid, _ in bets[i:]]
                
                side_pot = SidePot(amount=pot_amount, eligible_players=eligible_players)
                self.side_pots.append(side_pot)
                
                prev_bet = bet_amount
    
    def _distribute_winnings(self, player_evaluations: Dict[str, HandEvaluation]):
        """
        分配奖金
        
        Args:
            player_evaluations: 玩家手牌评估结果
        """
        self.game_results.clear()
        
        # 初始化结果
        for player_id in self.players.keys():
            player = self.players[player_id]
            self.game_results[player_id] = {
                'profit': -player.total_bet,
                'won': False,
                'hand_evaluation': player_evaluations.get(player_id),
                'final_chips': player.chips,
                'hand_cards': [str(card) for card in player.hole_cards]  # 保存手牌信息
            }
        
        # 如果没有边池，处理主池
        if not self.side_pots:
            self.side_pots = [SidePot(
                amount=self.main_pot,
                eligible_players=list(player_evaluations.keys())
            )]
        
        # 分配每个边池
        for side_pot in self.side_pots:
            eligible_evaluations = {
                pid: evaluation for pid, evaluation in player_evaluations.items()
                if pid in side_pot.eligible_players
            }
            
            if not eligible_evaluations:
                continue
            
            # 找出最佳手牌
            best_evaluation = max(eligible_evaluations.values())
            winners = [
                pid for pid, evaluation in eligible_evaluations.items()
                if evaluation >= best_evaluation and not evaluation < best_evaluation
            ]
            
            # 平分奖金
            if winners:
                winnings_per_player = side_pot.amount // len(winners)
                remainder = side_pot.amount % len(winners)
                
                for i, winner_id in enumerate(winners):
                    winnings = winnings_per_player + (1 if i < remainder else 0)
                    self.game_results[winner_id]['profit'] += winnings
                    self.game_results[winner_id]['won'] = True
                    self.players[winner_id].chips += winnings
        
        # 更新最终筹码数
        for player_id in self.players.keys():
            self.game_results[player_id]['final_chips'] = self.players[player_id].chips
    
    def _start_action_timeout(self):
        """启动操作超时计时器"""
        if self.timeout_task:
            self.timeout_task.cancel()
        
        async def timeout_handler():
            try:
                await asyncio.sleep(self.action_timeout)
                # 超时自动弃牌
                if self.current_player_id:
                    await self.handle_player_action(self.current_player_id, PlayerAction.FOLD)
            except asyncio.CancelledError:
                pass
        
        self.timeout_task = asyncio.create_task(timeout_handler())
    
    def _end_game(self):
        """结束游戏"""
        self.game_phase = GamePhase.GAME_OVER
        if self.timeout_task:
            self.timeout_task.cancel()
    
    # ==================== 查询方法 ====================
    
    def get_game_state(self) -> Dict[str, Any]:
        """
        获取游戏状态信息
        
        Returns:
            Dict: 包含游戏状态的字典
        """
        return {
            'room_id': self.room_id,
            'phase': self.game_phase.value,
            'hand_number': self.hand_number,
            'community_cards': [str(card) for card in self.community_cards],
            'main_pot': self.main_pot,
            'current_bet': self.current_bet,
            'current_player_id': self.current_player_id,
            'players': {
                pid: {
                    'chips': player.chips,
                    'current_bet': player.current_bet,
                    'total_bet': player.total_bet,
                    'status': player.status.value,
                    'position': player.position,
                    'is_dealer': player.is_dealer,
                    'is_small_blind': player.is_small_blind,
                    'is_big_blind': player.is_big_blind,
                    'last_action': player.last_action.value if player.last_action else None
                }
                for pid, player in self.players.items()
            }
        }
    
    def get_community_cards(self) -> List[str]:
        """
        获取公共牌
        
        Returns:
            List[str]: 公共牌字符串列表
        """
        return [str(card) for card in self.community_cards]
    
    def get_player_chips(self, player_id: str) -> Optional[int]:
        """
        获取玩家筹码数量
        
        Args:
            player_id: 玩家ID
            
        Returns:
            Optional[int]: 玩家筹码数量，如果玩家不存在返回None
        """
        if player_id in self.players:
            return self.players[player_id].chips
        return None
    
    def is_game_over(self) -> bool:
        """
        检查游戏是否结束
        
        Returns:
            bool: 游戏是否结束
        """
        return self.game_phase == GamePhase.GAME_OVER or len([p for p in self.players.values() if p.is_in_hand()]) <= 1
    
    def get_player_cards(self, player_id: str) -> List[str]:
        """
        获取玩家的底牌
        
        Args:
            player_id: 玩家ID
            
        Returns:
            List[str]: 底牌字符串列表
        """
        if player_id in self.players:
            return [str(card) for card in self.players[player_id].hole_cards]
        return []
    
    def get_total_pot(self) -> int:
        """
        获取总底池金额
        
        Returns:
            int: 总底池金额
        """
        return self.main_pot + sum(pot.amount for pot in self.side_pots)
    
    def _is_valid_action(self, player_id: str, action: PlayerAction, amount: int = 0) -> bool:
        """
        验证玩家操作是否合法
        
        Args:
            player_id: 玩家ID
            action: 操作类型
            amount: 操作金额
            
        Returns:
            bool: 操作是否合法
        """
        # 检查玩家是否存在
        if player_id not in self.players:
            return False
        
        player = self.players[player_id]
        
        # 检查是否是当前行动玩家
        if self.current_player_id != player_id:
            return False
        
        # 检查玩家状态
        if not player.can_act():
            return False
        
        # 检查游戏阶段
        if self.game_phase in [GamePhase.WAITING, GamePhase.GAME_OVER]:
            return False
        
        # 检查具体操作
        if action == PlayerAction.FOLD:
            return True
        elif action == PlayerAction.CHECK:
            can_check = player.current_bet >= self.current_bet
            return can_check
        elif action == PlayerAction.CALL:
            # 跟注：当前下注小于需要跟注的金额，且有足够筹码
            call_amount = self.current_bet - player.current_bet
            return call_amount > 0 and player.chips >= call_amount
        elif action == PlayerAction.RAISE:
            return (player.chips > 0 and 
                   amount > self.current_bet and 
                   amount <= player.chips + player.current_bet)
        elif action == PlayerAction.ALL_IN:
            return player.chips > 0
        
        return False
    
    def get_game_results(self) -> Dict[str, Dict[str, Any]]:
        """
        获取游戏结果
        
        Returns:
            Dict: 游戏结果字典
        """
        return self.game_results.copy()
    
    def is_game_over(self) -> bool:
        """
        判断游戏是否结束
        
        Returns:
            bool: 是否结束
        """
        return self.game_phase == GamePhase.GAME_OVER
    
    def can_start_new_hand(self) -> bool:
        """
        判断是否可以开始新一局
        
        Returns:
            bool: 是否可以开始
        """
        active_players = [p for p in self.players.values() if p.chips > 0]
        return len(active_players) >= 2
