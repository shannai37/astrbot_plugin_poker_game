from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
import asyncio
import time
import json
from pathlib import Path

from astrbot.api import logger
from .card_system import HandEvaluation


@dataclass
class PlayerInfo:
    """
    玩家信息数据类
    
    属性：
    - player_id: 玩家唯一标识
    - display_name: 显示名称
    - chips: 当前筹码数
    - level: 玩家等级
    - experience: 经验值
    - total_games: 总游戏局数
    - wins: 胜利局数
    - losses: 失败局数
    - total_profit: 总盈亏
    - best_hand: 历史最佳牌型
    - achievements: 成就列表
    - last_active: 最后活跃时间
    - registration_time: 注册时间
    - daily_bonus_claimed: 今日是否已领取奖励
    - last_bonus_time: 上次领取奖励时间
    - ban_status: 封禁状态
    - ban_reason: 封禁原因
    - ban_until: 封禁到期时间
    """
    player_id: str
    display_name: str = ""
    chips: int = 10000
    level: int = 1
    experience: int = 0
    total_games: int = 0
    wins: int = 0
    losses: int = 0
    total_profit: int = 0
    best_hand: Optional[str] = None
    achievements: List[str] = field(default_factory=list)
    last_active: float = field(default_factory=time.time)
    registration_time: float = field(default_factory=time.time)
    daily_bonus_claimed: bool = False
    last_bonus_time: float = 0
    ban_status: bool = False
    ban_reason: str = ""
    ban_until: float = 0
    equipped_achievement: str = ""  # 装备的成就ID
    
    # 统计属性（计算得出）
    @property
    def win_rate(self) -> float:
        """
        计算胜率
        
        Returns:
            float: 胜率百分比
        """
        if self.total_games == 0:
            return 0.0
        return (self.wins / self.total_games) * 100
    
    @property
    def is_banned(self) -> bool:
        """
        检查是否被封禁
        
        Returns:
            bool: 是否在封禁状态
        """
        if not self.ban_status:
            return False
        
        # 检查封禁是否过期
        if self.ban_until > 0 and time.time() > self.ban_until:
            return False
        
        return True
    
    @property
    def can_claim_daily_bonus(self) -> bool:
        """
        检查是否可以领取每日奖励
        
        Returns:
            bool: 是否可以领取
        """
        if self.daily_bonus_claimed:
            # 检查是否过了一天
            current_day = time.time() // 86400  # 以天为单位
            last_bonus_day = self.last_bonus_time // 86400
            return current_day > last_bonus_day
        return True
    
    @property
    def required_exp_for_next_level(self) -> int:
        """
        计算升级所需经验值
        
        Returns:
            int: 升级所需经验值
        """
        return self.level * 100  # 每级需要 level * 100 经验
    
    def to_dict(self) -> Dict[str, Any]:
        """
        转换为字典格式
        
        Returns:
            Dict: 玩家信息字典
        """
        return {
            'player_id': self.player_id,
            'display_name': self.display_name,
            'chips': self.chips,
            'level': self.level,
            'experience': self.experience,
            'total_games': self.total_games,
            'wins': self.wins,
            'losses': self.losses,
            'total_profit': self.total_profit,
            'best_hand': self.best_hand,
            'achievements': self.achievements,
            'last_active': self.last_active,
            'registration_time': self.registration_time,
            'daily_bonus_claimed': self.daily_bonus_claimed,
            'last_bonus_time': self.last_bonus_time,
            'ban_status': self.ban_status,
            'ban_reason': self.ban_reason,
            'ban_until': self.ban_until,
            'equipped_achievement': self.equipped_achievement
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PlayerInfo':
        """
        从字典创建玩家信息对象
        
        Args:
            data: 玩家数据字典
            
        Returns:
            PlayerInfo: 玩家信息对象
        """
        return cls(
            player_id=data['player_id'],
            display_name=data.get('display_name', ''),
            chips=data.get('chips', 10000),
            level=data.get('level', 1),
            experience=data.get('experience', 0),
            total_games=data.get('total_games', 0),
            wins=data.get('wins', 0),
            losses=data.get('losses', 0),
            total_profit=data.get('total_profit', 0),
            best_hand=data.get('best_hand'),
            achievements=data.get('achievements', []),
            last_active=data.get('last_active', time.time()),
            registration_time=data.get('registration_time', time.time()),
            daily_bonus_claimed=data.get('daily_bonus_claimed', False),
            last_bonus_time=data.get('last_bonus_time', 0),
            ban_status=data.get('ban_status', False),
            ban_reason=data.get('ban_reason', ''),
            ban_until=data.get('ban_until', 0),
            equipped_achievement=data.get('equipped_achievement', '')
        )


@dataclass 
class PlayerStats:
    """
    玩家详细统计数据
    
    包含更详细的游戏统计信息
    """
    player_info: PlayerInfo
    hand_type_wins: Dict[str, int] = field(default_factory=dict)  # 各种牌型获胜次数
    position_stats: Dict[str, Dict[str, int]] = field(default_factory=dict)  # 不同位置的统计
    recent_games: List[Dict[str, Any]] = field(default_factory=list)  # 最近游戏记录
    longest_winning_streak: int = 0  # 最长连胜
    longest_losing_streak: int = 0  # 最长连败
    current_streak: int = 0  # 当前连胜/连败（正数为连胜，负数为连败）
    biggest_win: int = 0  # 单局最大盈利
    biggest_loss: int = 0  # 单局最大亏损
    favorite_hand: Optional[str] = None  # 最常获胜的牌型


class PlayerManager:
    """
    玩家管理系统
    
    功能包括：
    - 玩家注册和资料管理
    - 积分和等级系统
    - 游戏统计和成就系统
    - 每日奖励和签到
    - 封禁和权限管理
    - 排行榜和数据分析
    """
    
    def __init__(self, database_manager):
        """
        初始化玩家管理系统
        
        Args:
            database_manager: 数据库管理器实例
        """
        self.database_manager = database_manager
        self.players: Dict[str, PlayerInfo] = {}
        self.achievements_config = self._init_achievements()
        
        # 缓存管理
        self.cache_dirty = False
        self.last_save_time = time.time()
        self.auto_save_interval = 300  # 5分钟自动保存
        
        # 自动保存任务
        self.auto_save_task: Optional[asyncio.Task] = None
        
    def start_auto_save(self):
        """
        启动自动保存任务
        """
        if not self.auto_save_task or self.auto_save_task.done():
            self.auto_save_task = asyncio.create_task(self.auto_save_task_loop())
            logger.info("自动保存任务已启动")
    
    def _init_achievements(self) -> Dict[str, Dict[str, Any]]:
        """
        初始化成就配置
        
        Returns:
            Dict: 成就配置字典
        """
        return {
            # 基础游戏成就
            "first_game": {
                "name": "初出茅庐",
                "description": "完成第一局游戏",
                "condition": lambda stats: stats.player_info.total_games >= 1,
                "progress": lambda stats: min(stats.player_info.total_games, 1),
                "target": 1,
                "reward": 50,
                "category": "基础",
                "icon": "🎮"
            },
            "ten_games": {
                "name": "小试牛刀", 
                "description": "完成10局游戏",
                "condition": lambda stats: stats.player_info.total_games >= 10,
                "progress": lambda stats: min(stats.player_info.total_games, 10),
                "target": 10,
                "reward": 100,
                "category": "基础",
                "icon": "🎯"
            },
            "fifty_games": {
                "name": "老手",
                "description": "完成50局游戏", 
                "condition": lambda stats: stats.player_info.total_games >= 50,
                "progress": lambda stats: min(stats.player_info.total_games, 50),
                "target": 50,
                "reward": 300,
                "category": "基础",
                "icon": "🎲"
            },
            "hundred_games": {
                "name": "经验丰富",
                "description": "完成100局游戏",
                "condition": lambda stats: stats.player_info.total_games >= 100,
                "progress": lambda stats: min(stats.player_info.total_games, 100),
                "target": 100,
                "reward": 500,
                "category": "基础",
                "icon": "⭐"
            },
            
            # 胜利成就
            "first_win": {
                "name": "首胜",
                "description": "赢得第一局游戏",
                "condition": lambda stats: stats.player_info.wins >= 1,
                "progress": lambda stats: min(stats.player_info.wins, 1),
                "target": 1,
                "reward": 80,
                "category": "胜利",
                "icon": "🏆"
            },
            "five_wins": {
                "name": "胜利者",
                "description": "赢得5局游戏",
                "condition": lambda stats: stats.player_info.wins >= 5,
                "progress": lambda stats: min(stats.player_info.wins, 5),
                "target": 5,
                "reward": 150,
                "category": "胜利",
                "icon": "👑"
            },
            "twenty_wins": {
                "name": "常胜将军",
                "description": "赢得20局游戏",
                "condition": lambda stats: stats.player_info.wins >= 20,
                "progress": lambda stats: min(stats.player_info.wins, 20),
                "target": 20,
                "reward": 400,
                "category": "胜利",
                "icon": "🎖️"
            },
            
            # 连胜成就
            "winning_streak_3": {
                "name": "三连胜",
                "description": "获得3连胜",
                "condition": lambda stats: stats.longest_winning_streak >= 3,
                "progress": lambda stats: min(stats.longest_winning_streak, 3),
                "target": 3,
                "reward": 120,
                "category": "连胜",
                "icon": "🔥"
            },
            "winning_streak_5": {
                "name": "连胜高手",
                "description": "获得5连胜",
                "condition": lambda stats: stats.longest_winning_streak >= 5,
                "progress": lambda stats: min(stats.longest_winning_streak, 5),
                "target": 5,
                "reward": 250,
                "category": "连胜", 
                "icon": "⚡"
            },
            "winning_streak_10": {
                "name": "连胜之王",
                "description": "获得10连胜",
                "condition": lambda stats: stats.longest_winning_streak >= 10,
                "progress": lambda stats: min(stats.longest_winning_streak, 10),
                "target": 10,
                "reward": 600,
                "category": "连胜",
                "icon": "💫"
            },
            
            # 筹码成就
            "rich_player": {
                "name": "小富翁",
                "description": "拥有5000+筹码",
                "condition": lambda stats: stats.player_info.chips >= 5000,
                "progress": lambda stats: min(stats.player_info.chips, 5000),
                "target": 5000,
                "reward": 200,
                "category": "财富",
                "icon": "💰"
            },
            "high_roller": {
                "name": "土豪",
                "description": "拥有10000+筹码",
                "condition": lambda stats: stats.player_info.chips >= 10000,
                "progress": lambda stats: min(stats.player_info.chips, 10000),
                "target": 10000,
                "reward": 300,
                "category": "财富",
                "icon": "💎"
            },
            "millionaire": {
                "name": "百万富翁",
                "description": "拥有100000+筹码",
                "condition": lambda stats: stats.player_info.chips >= 100000,
                "progress": lambda stats: min(stats.player_info.chips, 100000),
                "target": 100000,
                "reward": 1000,
                "category": "财富",
                "icon": "👑"
            },
            
            # 盈利成就
            "profitable": {
                "name": "盈利玩家",
                "description": "总盈利超过1000筹码",
                "condition": lambda stats: stats.player_info.total_profit >= 1000,
                "progress": lambda stats: max(0, min(stats.player_info.total_profit, 1000)),
                "target": 1000,
                "reward": 200,
                "category": "盈利",
                "icon": "📈"
            },
            "big_winner": {
                "name": "大赢家",
                "description": "单局赢得500+筹码",
                "condition": lambda stats: stats.biggest_win >= 500,
                "progress": lambda stats: min(stats.biggest_win, 500),
                "target": 500,
                "reward": 150,
                "category": "盈利",
                "icon": "💸"
            },
            
            # 牌型成就
            "flush_master": {
                "name": "同花大师",
                "description": "用同花获胜1次",
                "condition": lambda stats: stats.hand_type_wins.get("同花", 0) >= 1,
                "progress": lambda stats: min(stats.hand_type_wins.get("同花", 0), 1),
                "target": 1,
                "reward": 120,
                "category": "牌技",
                "icon": "🌟"
            },
            "straight_expert": {
                "name": "顺子专家",
                "description": "用顺子获胜3次",
                "condition": lambda stats: stats.hand_type_wins.get("顺子", 0) >= 3,
                "progress": lambda stats: min(stats.hand_type_wins.get("顺子", 0), 3),
                "target": 3,
                "reward": 200,
                "category": "牌技",
                "icon": "🎪"
            },
            "royal_flush": {
                "name": "皇家同花顺",
                "description": "获得皇家同花顺",
                "condition": lambda stats: stats.hand_type_wins.get("皇家同花顺", 0) >= 1,
                "progress": lambda stats: min(stats.hand_type_wins.get("皇家同花顺", 0), 1),
                "target": 1,
                "reward": 1000,
                "category": "牌技",
                "icon": "👑"
            },
            
            # 胜率成就
            "good_player": {
                "name": "好手",
                "description": "胜率超过60%（至少10局）",
                "condition": lambda stats: stats.player_info.total_games >= 10 and stats.player_info.win_rate >= 60,
                "progress": lambda stats: min(stats.player_info.win_rate, 60) if stats.player_info.total_games >= 10 else 0,
                "target": 60,
                "reward": 300,
                "category": "技术",
                "icon": "🎯"
            },
            "master_player": {
                "name": "扑克大师",
                "description": "胜率超过70%（至少30局）",
                "condition": lambda stats: stats.player_info.total_games >= 30 and stats.player_info.win_rate >= 70,
                "progress": lambda stats: min(stats.player_info.win_rate, 70) if stats.player_info.total_games >= 30 else 0,
                "target": 70,
                "reward": 600,
                "category": "技术",
                "icon": "🏅"
            }
        }
    
    async def get_or_create_player(self, player_id: str, display_name: str = "") -> PlayerInfo:
        """
        获取或创建玩家
        
        Args:
            player_id: 玩家ID
            display_name: 显示名称
            
        Returns:
            PlayerInfo: 玩家信息对象
        """
        if player_id in self.players:
            player = self.players[player_id]
            # 更新最后活跃时间
            player.last_active = time.time()
            return player
        
        # 尝试从数据库加载
        player_data = await self.database_manager.get_player_data(player_id)
        if player_data:
            player = PlayerInfo.from_dict(player_data)
            self.players[player_id] = player
            player.last_active = time.time()
            return player
        
        # 创建新玩家
        player = PlayerInfo(
            player_id=player_id,
            display_name=display_name or f"Player_{player_id[:8]}"
        )
        
        self.players[player_id] = player
        self.cache_dirty = True
        
        logger.info(f"创建新玩家: {player_id} ({player.display_name})")
        
        # 异步保存到数据库
        await self._save_player_to_db(player)
        
        return player
    
    async def update_player_chips(self, player_id: str, new_chips: int) -> bool:
        """
        更新玩家筹码
        
        Args:
            player_id: 玩家ID
            new_chips: 新的筹码数
            
        Returns:
            bool: 是否更新成功
        """
        if player_id not in self.players:
            logger.warning(f"尝试更新不存在的玩家筹码: {player_id}")
            return False
        
        player = self.players[player_id]
        old_chips = player.chips
        player.chips = max(0, new_chips)  # 确保不为负数
        
        # 如果筹码变化显著，记录日志
        if abs(player.chips - old_chips) > 100:
            logger.info(f"玩家 {player_id} 筹码变化: {old_chips} -> {player.chips}")
        
        self.cache_dirty = True
        return True
    
    async def update_game_result(self, player_id: str, profit: int, won: bool, 
                               hand_evaluation: Optional[HandEvaluation] = None) -> bool:
        """
        更新玩家游戏结果
        
        Args:
            player_id: 玩家ID
            profit: 盈亏金额（正数为盈利，负数为亏损）
            won: 是否获胜
            hand_evaluation: 手牌评估结果
            
        Returns:
            bool: 是否更新成功
        """
        if player_id not in self.players:
            logger.warning(f"尝试更新不存在的玩家游戏结果: {player_id}")
            return False
        
        player = self.players[player_id]
        
        # 更新基础统计
        player.total_games += 1
        if won:
            player.wins += 1
        else:
            player.losses += 1
        
        player.total_profit += profit
        
        # 更新经验值（获胜+50，失败+10）
        exp_gain = 50 if won else 10
        await self._add_experience(player, exp_gain)
        
        # 获取详细统计
        stats = await self.get_player_stats(player_id)
        if stats:
            # 更新连胜/连败
            if won:
                if stats.current_streak >= 0:
                    stats.current_streak += 1
                else:
                    stats.current_streak = 1
                stats.longest_winning_streak = max(stats.longest_winning_streak, stats.current_streak)
            else:
                if stats.current_streak <= 0:
                    stats.current_streak -= 1
                else:
                    stats.current_streak = -1
                stats.longest_losing_streak = max(stats.longest_losing_streak, abs(stats.current_streak))
            
            # 更新最大盈亏
            if profit > 0:
                stats.biggest_win = max(stats.biggest_win, profit)
            else:
                stats.biggest_loss = max(stats.biggest_loss, abs(profit))
            
            # 更新手牌统计
            if hand_evaluation and won:
                hand_name = hand_evaluation.hand_rank.name_cn
                stats.hand_type_wins[hand_name] = stats.hand_type_wins.get(hand_name, 0) + 1
                
                # 更新最佳牌型
                if not player.best_hand or hand_evaluation.hand_rank.rank_value > self._get_hand_rank_value(player.best_hand):
                    player.best_hand = hand_name
            
            # 检查成就
            await self._check_achievements(stats)
            
            # 保存详细统计
            await self._save_player_stats(stats)
        
        self.cache_dirty = True
        logger.info(f"玩家 {player_id} 游戏结果更新: 盈亏={profit}, 胜利={won}")
        
        return True
    
    async def add_chips(self, player_id: str, amount: int, reason: str = "") -> bool:
        """
        给玩家增加筹码
        
        Args:
            player_id: 玩家ID
            amount: 筹码数量
            reason: 增加原因
            
        Returns:
            bool: 是否成功
        """
        if player_id not in self.players:
            return False
        
        player = self.players[player_id]
        old_chips = player.chips
        player.chips += amount
        
        logger.info(f"玩家 {player_id} 筹码变化: {old_chips} -> {player.chips} (原因: {reason})")
        
        # 记录交易日志
        await self.database_manager.log_transaction(
            player_id, amount, old_chips, player.chips, reason
        )
        
        self.cache_dirty = True
        return True
    
    async def claim_daily_bonus(self, player_id: str, bonus_amount: int) -> Tuple[bool, str]:
        """
        领取每日奖励
        
        Args:
            player_id: 玩家ID
            bonus_amount: 奖励金额
            
        Returns:
            Tuple[bool, str]: (是否成功, 消息)
        """
        if player_id not in self.players:
            return False, "玩家不存在"
        
        player = self.players[player_id]
        
        if not player.can_claim_daily_bonus:
            # 计算剩余时间
            next_bonus_time = (player.last_bonus_time // 86400 + 1) * 86400
            remaining_hours = (next_bonus_time - time.time()) / 3600
            return False, f"每日奖励已领取，{remaining_hours:.1f}小时后可再次领取"
        
        # 发放奖励
        await self.add_chips(player_id, bonus_amount, "每日奖励")
        
        player.daily_bonus_claimed = True
        player.last_bonus_time = time.time()
        
        self.cache_dirty = True
        
        return True, f"成功领取每日奖励 {bonus_amount} 筹码！"
    
    async def ban_player(self, player_id: str, reason: str, duration_hours: int = 0) -> bool:
        """
        封禁玩家
        
        Args:
            player_id: 玩家ID
            reason: 封禁原因
            duration_hours: 封禁时长（小时），0为永久封禁
            
        Returns:
            bool: 是否成功
        """
        if player_id not in self.players:
            return False
        
        player = self.players[player_id]
        player.ban_status = True
        player.ban_reason = reason
        
        if duration_hours > 0:
            player.ban_until = time.time() + (duration_hours * 3600)
        else:
            player.ban_until = 0  # 永久封禁
        
        self.cache_dirty = True
        
        logger.info(f"玩家 {player_id} 被封禁: {reason}, 时长: {'永久' if duration_hours == 0 else f'{duration_hours}小时'}")
        
        return True
    
    async def unban_player(self, player_id: str) -> bool:
        """
        解封玩家
        
        Args:
            player_id: 玩家ID
            
        Returns:
            bool: 是否成功
        """
        if player_id not in self.players:
            return False
        
        player = self.players[player_id]
        player.ban_status = False
        player.ban_reason = ""
        player.ban_until = 0
        
        self.cache_dirty = True
        
        logger.info(f"玩家 {player_id} 已解封")
        
        return True
    
    async def equip_achievement(self, player_id: str, achievement_id: str) -> Tuple[bool, str]:
        """
        装备成就
        
        Args:
            player_id: 玩家ID
            achievement_id: 成就ID
            
        Returns:
            Tuple[bool, str]: (是否成功, 消息)
        """
        if player_id not in self.players:
            return False, "玩家不存在"
        
        player = self.players[player_id]
        
        # 检查是否已解锁该成就
        if achievement_id not in player.achievements:
            return False, "您还未解锁该成就"
        
        # 检查成就是否存在
        if achievement_id not in self.achievements_config:
            return False, "成就不存在"
        
        # 装备成就
        player.equipped_achievement = achievement_id
        self.cache_dirty = True
        
        achievement_name = self.achievements_config[achievement_id]["name"]
        return True, f"成功装备成就：{achievement_name}"
    
    async def get_achievement_progress(self, player_id: str) -> Dict[str, Any]:
        """
        获取玩家成就进度
        
        Args:
            player_id: 玩家ID
            
        Returns:
            Dict: 成就进度信息
        """
        if player_id not in self.players:
            return {}
        
        stats = await self.get_player_stats(player_id)
        if not stats:
            return {}
        
        progress_data = {
            'unlocked': [],
            'locked': []
        }
        
        for achievement_id, config in self.achievements_config.items():
            is_unlocked = achievement_id in stats.player_info.achievements
            current_progress = config["progress"](stats)
            target = config["target"]
            
            achievement_info = {
                'id': achievement_id,
                'name': config["name"],
                'description': config["description"],
                'icon': config["icon"],
                'category': config["category"],
                'reward': config["reward"],
                'progress': current_progress,
                'target': target,
                'progress_percent': min(100, (current_progress / target) * 100)
            }
            
            if is_unlocked:
                progress_data['unlocked'].append(achievement_info)
            else:
                progress_data['locked'].append(achievement_info)
        
        # 按类别排序
        progress_data['unlocked'].sort(key=lambda x: (x['category'], x['name']))
        progress_data['locked'].sort(key=lambda x: (x['category'], -x['progress_percent'], x['name']))
        
        return progress_data
    
    async def get_player_stats(self, player_id: str) -> Optional[PlayerStats]:
        """
        获取玩家详细统计
        
        Args:
            player_id: 玩家ID
            
        Returns:
            Optional[PlayerStats]: 玩家统计对象
        """
        if player_id not in self.players:
            return None
        
        player_info = self.players[player_id]
        
        # 从数据库加载详细统计
        stats_data = await self.database_manager.get_player_stats(player_id)
        
        return PlayerStats(
            player_info=player_info,
            hand_type_wins=stats_data.get('hand_type_wins', {}),
            position_stats=stats_data.get('position_stats', {}),
            recent_games=stats_data.get('recent_games', []),
            longest_winning_streak=stats_data.get('longest_winning_streak', 0),
            longest_losing_streak=stats_data.get('longest_losing_streak', 0),
            current_streak=stats_data.get('current_streak', 0),
            biggest_win=stats_data.get('biggest_win', 0),
            biggest_loss=stats_data.get('biggest_loss', 0),
            favorite_hand=stats_data.get('favorite_hand')
        )
    
    async def get_leaderboard(self, category: str = "chips", limit: int = 10) -> List[Tuple[int, PlayerInfo]]:
        """
        获取排行榜
        
        Args:
            category: 排行类别 (chips/wins/profit/winrate)
            limit: 返回数量限制
            
        Returns:
            List[Tuple[int, PlayerInfo]]: 排行榜列表 (排名, 玩家信息)
        """
        players = list(self.players.values())
        
        # 过滤掉封禁的玩家和游戏数太少的玩家
        active_players = [p for p in players if not p.is_banned and p.total_games >= 5]
        
        # 根据类别排序
        if category == "chips":
            active_players.sort(key=lambda p: p.chips, reverse=True)
        elif category == "wins":
            active_players.sort(key=lambda p: p.wins, reverse=True)
        elif category == "profit":
            active_players.sort(key=lambda p: p.total_profit, reverse=True)
        elif category == "winrate":
            active_players.sort(key=lambda p: p.win_rate, reverse=True)
        elif category == "level":
            active_players.sort(key=lambda p: (p.level, p.experience), reverse=True)
        else:
            active_players.sort(key=lambda p: p.chips, reverse=True)
        
        # 返回前N名
        result = [(i + 1, player) for i, player in enumerate(active_players[:limit])]
        
        return result
    
    async def get_all_players(self) -> List[PlayerInfo]:
        """
        获取所有玩家列表
        
        Returns:
            List[PlayerInfo]: 玩家列表
        """
        return list(self.players.values())
    
    async def reset_player_data(self, player_id: str, keep_chips: bool = False) -> bool:
        """
        重置玩家数据
        
        Args:
            player_id: 玩家ID
            keep_chips: 是否保留筹码
            
        Returns:
            bool: 是否成功
        """
        if player_id not in self.players:
            return False
        
        player = self.players[player_id]
        current_chips = player.chips if keep_chips else 10000
        
        # 重置数据
        reset_player = PlayerInfo(
            player_id=player.player_id,
            display_name=player.display_name,
            chips=current_chips,
            registration_time=player.registration_time
        )
        
        self.players[player_id] = reset_player
        self.cache_dirty = True
        
        # 清理数据库中的详细统计
        await self.database_manager.reset_player_stats(player_id)
        
        logger.info(f"玩家 {player_id} 数据已重置")
        
        return True
    
    async def _add_experience(self, player: PlayerInfo, exp_amount: int):
        """
        增加玩家经验值并处理升级
        
        Args:
            player: 玩家对象
            exp_amount: 经验值增量
        """
        player.experience += exp_amount
        
        # 检查升级
        required_exp = player.required_exp_for_next_level
        if player.experience >= required_exp:
            old_level = player.level
            player.level += 1
            player.experience -= required_exp
            
            # 升级奖励
            level_bonus = player.level * 50
            player.chips += level_bonus
            
            logger.info(f"玩家 {player.player_id} 升级: {old_level} -> {player.level}, 获得 {level_bonus} 筹码奖励")
    
    def _get_hand_rank_value(self, hand_name: str) -> int:
        """
        获取牌型的价值排序
        
        Args:
            hand_name: 牌型名称
            
        Returns:
            int: 牌型价值
        """
        hand_values = {
            "高牌": 1, "一对": 2, "两对": 3, "三条": 4, "顺子": 5,
            "同花": 6, "葫芦": 7, "四条": 8, "同花顺": 9, "皇家同花顺": 10
        }
        return hand_values.get(hand_name, 0)
    
    async def _check_achievements(self, stats: PlayerStats):
        """
        检查并解锁成就
        
        Args:
            stats: 玩家统计对象
        """
        for achievement_id, config in self.achievements_config.items():
            if achievement_id in stats.player_info.achievements:
                continue  # 已获得
            
            if config["condition"](stats):
                # 解锁成就
                stats.player_info.achievements.append(achievement_id)
                
                # 发放奖励
                reward = config["reward"]
                await self.add_chips(stats.player_info.player_id, reward, f"成就奖励: {config['name']}")
                
                logger.info(f"玩家 {stats.player_info.player_id} 解锁成就: {config['name']}")
    
    async def _save_player_to_db(self, player: PlayerInfo):
        """
        保存单个玩家到数据库
        
        Args:
            player: 玩家对象
        """
        try:
            await self.database_manager.save_player_data(player.player_id, player.to_dict())
        except Exception as e:
            logger.error(f"保存玩家数据失败: {e}")
    
    async def _save_player_stats(self, stats: PlayerStats):
        """
        保存玩家统计到数据库
        
        Args:
            stats: 玩家统计对象
        """
        try:
            stats_dict = {
                'hand_type_wins': stats.hand_type_wins,
                'position_stats': stats.position_stats,
                'recent_games': stats.recent_games[-50:],  # 只保留最近50局
                'longest_winning_streak': stats.longest_winning_streak,
                'longest_losing_streak': stats.longest_losing_streak,
                'current_streak': stats.current_streak,
                'biggest_win': stats.biggest_win,
                'biggest_loss': stats.biggest_loss,
                'favorite_hand': stats.favorite_hand
            }
            
            await self.database_manager.save_player_stats(stats.player_info.player_id, stats_dict)
        except Exception as e:
            logger.error(f"保存玩家统计失败: {e}")
    
    async def save_all_players(self):
        """
        保存所有玩家数据到数据库
        """
        if not self.cache_dirty:
            return
        
        try:
            for player in self.players.values():
                await self._save_player_to_db(player)
            
            self.cache_dirty = False
            self.last_save_time = time.time()
            
            logger.info("所有玩家数据已保存")
        except Exception as e:
            logger.error(f"批量保存玩家数据失败: {e}")
    
    async def load_players(self):
        """
        从数据库加载所有玩家数据
        """
        try:
            players_data = await self.database_manager.load_all_players()
            
            for player_data in players_data:
                player = PlayerInfo.from_dict(player_data)
                self.players[player.player_id] = player
            
            logger.info(f"已加载 {len(self.players)} 个玩家数据")
        except Exception as e:
            logger.error(f"加载玩家数据失败: {e}")
    
    async def auto_save_task_loop(self):
        """
        自动保存任务循环
        """
        while True:
            try:
                await asyncio.sleep(self.auto_save_interval)
                
                if self.cache_dirty and time.time() - self.last_save_time > self.auto_save_interval:
                    await self.save_all_players()
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"自动保存任务错误: {e}")
    
    async def cleanup(self):
        """
        清理资源
        """
        if self.auto_save_task and not self.auto_save_task.done():
            self.auto_save_task.cancel()
        await self.save_all_players()
