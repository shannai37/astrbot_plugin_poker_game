from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field
import asyncio
import time
import uuid
from enum import Enum

from astrbot.api import logger
from .game_engine import TexasHoldemGame, GamePhase
from .player_manager import PlayerManager


class RoomStatus(Enum):
    """房间状态枚举"""
    WAITING = "waiting"          # 等待玩家
    STARTING = "starting"        # 准备开始
    IN_GAME = "in_game"         # 游戏中
    PAUSED = "paused"           # 暂停
    FINISHED = "finished"       # 已结束


class RoomType(Enum):
    """房间类型枚举"""
    QUICK_MATCH = "quick_match"  # 快速匹配
    PRIVATE = "private"          # 私人房间
    TOURNAMENT = "tournament"    # 锦标赛


@dataclass
class GameRoom:
    """
    游戏房间数据类
    
    属性：
    - room_id: 房间唯一标识
    - room_name: 房间名称
    - room_type: 房间类型
    - creator_id: 创建者ID
    - password: 房间密码（私人房间）
    - status: 房间状态
    - small_blind: 小盲注金额
    - big_blind: 大盲注金额
    - min_buy_in: 最小买入金额
    - max_buy_in: 最大买入金额
    - max_players: 最大玩家数
    - current_players: 当前玩家数
    - player_ids: 玩家ID列表
    - waiting_list: 等待列表
    - game: 游戏实例
    - created_time: 创建时间
    - last_activity: 最后活跃时间
    - auto_start: 是否自动开始
    - allow_observers: 是否允许旁观
    - observers: 旁观者列表
    """
    room_id: str
    room_name: str = ""
    room_type: RoomType = RoomType.QUICK_MATCH
    creator_id: str = ""
    password: str = ""
    status: RoomStatus = RoomStatus.WAITING
    small_blind: int = 1
    big_blind: int = 2
    min_buy_in: int = 100
    max_buy_in: int = 10000
    max_players: int = 6
    current_players: int = 0
    player_ids: Set[str] = field(default_factory=set)
    waiting_list: List[str] = field(default_factory=list)
    game: Optional[TexasHoldemGame] = None
    created_time: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    auto_start: bool = True
    allow_observers: bool = True
    observers: Set[str] = field(default_factory=set)
    
    def __post_init__(self):
        """初始化后处理"""
        if not self.room_name:
            self.room_name = f"房间_{self.room_id[:8]}"
    
    @property
    def is_private(self) -> bool:
        """
        检查是否为私人房间
        
        Returns:
            bool: 是否为私人房间
        """
        return bool(self.password) or self.room_type == RoomType.PRIVATE
    
    @property
    def is_full(self) -> bool:
        """
        检查房间是否已满
        
        Returns:
            bool: 是否已满
        """
        return self.current_players >= self.max_players
    
    @property
    def can_start_game(self) -> bool:
        """
        检查是否可以开始游戏
        
        Returns:
            bool: 是否可以开始
        """
        return (self.current_players >= 2 and 
                self.status == RoomStatus.WAITING and
                (self.game is None or self.game.can_start_new_hand()))
    
    @property
    def is_active(self) -> bool:
        """
        检查房间是否活跃
        
        Returns:
            bool: 是否活跃（30分钟内有活动）
        """
        return time.time() - self.last_activity < 1800  # 30分钟
    
    def update_activity(self):
        """更新最后活跃时间"""
        self.last_activity = time.time()
    
    def to_dict(self) -> Dict[str, Any]:
        """
        转换为字典格式
        
        Returns:
            Dict: 房间信息字典
        """
        return {
            'room_id': self.room_id,
            'room_name': self.room_name,
            'room_type': self.room_type.value,
            'creator_id': self.creator_id,
            'password': self.password,
            'status': self.status.value,
            'small_blind': self.small_blind,
            'big_blind': self.big_blind,
            'min_buy_in': self.min_buy_in,
            'max_buy_in': self.max_buy_in,
            'max_players': self.max_players,
            'current_players': self.current_players,
            'player_ids': list(self.player_ids),
            'waiting_list': self.waiting_list,
            'created_time': self.created_time,
            'last_activity': self.last_activity,
            'auto_start': self.auto_start,
            'allow_observers': self.allow_observers,
            'observers': list(self.observers),
            'is_private': self.is_private
        }


class RoomManager:
    """
    房间管理系统
    
    功能包括：
    - 房间创建和删除
    - 玩家加入和离开
    - 房间状态管理
    - 快速匹配系统
    - 私人房间管理
    - 旁观者系统
    - 房间清理和维护
    """
    
    def __init__(self, database_manager, player_manager: PlayerManager):
        """
        初始化房间管理系统
        
        Args:
            database_manager: 数据库管理器
            player_manager: 玩家管理器
        """
        self.database_manager = database_manager
        self.player_manager = player_manager
        self.rooms: Dict[str, GameRoom] = {}
        self.player_room_mapping: Dict[str, str] = {}  # 玩家ID -> 房间ID
        self.next_room_number = 1  # 简单递增的房间号
        
        # 配置参数
        self.max_rooms = 50
        self.room_cleanup_interval = 300  # 5分钟清理一次
        self.inactive_room_timeout = 3600  # 1小时无活动自动关闭
        
        # 异步任务
        self.cleanup_task: Optional[asyncio.Task] = None
        self.start_cleanup_task()
    
    def start_cleanup_task(self):
        """启动房间清理任务"""
        if self.cleanup_task is None or self.cleanup_task.done():
            self.cleanup_task = asyncio.create_task(self._room_cleanup_loop())
    
    async def create_room(self, creator_id: str, room_name: str = "", 
                         room_type: RoomType = RoomType.QUICK_MATCH,
                         small_blind: int = 1, big_blind: int = 2,
                         max_players: int = 6, password: str = "",
                         **kwargs) -> Optional[GameRoom]:
        """
        创建新房间
        
        Args:
            creator_id: 创建者ID
            room_name: 房间名称
            room_type: 房间类型
            small_blind: 小盲注
            big_blind: 大盲注
            max_players: 最大玩家数
            password: 房间密码
            **kwargs: 其他参数
            
        Returns:
            Optional[GameRoom]: 创建的房间对象，失败返回None
        """
        # 检查房间数量限制
        if len(self.rooms) >= self.max_rooms:
            logger.warning(f"房间数量已达上限: {self.max_rooms}")
            return None
        
        # 检查创建者是否已在其他房间
        if creator_id in self.player_room_mapping:
            existing_room_id = self.player_room_mapping[creator_id]
            existing_room = self.rooms.get(existing_room_id)
            if existing_room and existing_room.status != RoomStatus.FINISHED:
                logger.warning(f"玩家 {creator_id} 已在房间 {existing_room_id} 中")
                return None
        
        # 生成房间ID（从1开始的简单数字）
        room_id = str(self.next_room_number)
        self.next_room_number += 1
        
        # 创建房间
        room = GameRoom(
            room_id=room_id,
            room_name=room_name or f"房间_{room_id}",
            room_type=room_type,
            creator_id=creator_id,
            password=password,
            small_blind=small_blind,
            big_blind=big_blind,
            max_players=min(max_players, 9),  # 最多9人
            min_buy_in=kwargs.get('min_buy_in', big_blind * 20),
            max_buy_in=kwargs.get('max_buy_in', big_blind * 200),
            auto_start=kwargs.get('auto_start', True),
            allow_observers=kwargs.get('allow_observers', True)
        )
        
        self.rooms[room_id] = room
        
        # 创建者自动加入房间
        await self.join_room(room_id, creator_id)
        
        logger.info(f"创建房间: {room_id} by {creator_id}, 盲注: {small_blind}/{big_blind}")
        
        return room
    
    async def join_room(self, room_id: str, player_id: str, password: str = "") -> bool:
        """
        玩家加入房间
        
        Args:
            room_id: 房间ID
            player_id: 玩家ID
            password: 房间密码（私人房间需要）
            
        Returns:
            bool: 是否成功加入
        """
        room = self.rooms.get(room_id)
        if not room:
            logger.warning(f"房间不存在: {room_id}")
            return False
        
        # 检查玩家是否已在其他房间
        if player_id in self.player_room_mapping:
            current_room_id = self.player_room_mapping[player_id]
            if current_room_id != room_id:
                logger.warning(f"玩家 {player_id} 已在房间 {current_room_id} 中")
                return False
        
        # 检查密码
        if room.is_private and room.password != password:
            logger.warning(f"房间 {room_id} 密码错误")
            return False
        
        # 检查封禁状态
        player = await self.player_manager.get_or_create_player(player_id)
        if player.is_banned:
            logger.warning(f"玩家 {player_id} 被封禁，无法加入房间")
            return False
        
        # 检查筹码
        required_chips = room.min_buy_in
        if player.chips < required_chips:
            logger.warning(f"玩家 {player_id} 筹码不足，需要 {required_chips}，当前 {player.chips}")
            return False
        
        # 检查房间状态
        if room.status == RoomStatus.FINISHED:
            logger.warning(f"房间 {room_id} 已结束")
            return False
        
        # 如果房间满了，加入等待列表
        if room.is_full:
            if player_id not in room.waiting_list:
                room.waiting_list.append(player_id)
                logger.info(f"玩家 {player_id} 加入房间 {room_id} 等待列表")
            return True
        
        # 加入房间
        room.player_ids.add(player_id)
        room.current_players = len(room.player_ids)
        room.update_activity()
        
        self.player_room_mapping[player_id] = room_id
        
        # 创建游戏实例
        if room.game is None:
            room.game = TexasHoldemGame(
                room_id=room_id,
                small_blind=room.small_blind,
                big_blind=room.big_blind,
                max_players=room.max_players
            )
        
        # 将玩家添加到游戏中
        buy_in = min(player.chips, room.max_buy_in)
        buy_in = max(buy_in, room.min_buy_in)
        
        if room.game.add_player(player_id, buy_in):
            # 更新玩家筹码
            await self.player_manager.update_player_chips(player_id, player.chips - buy_in)
            
            logger.info(f"玩家 {player_id} 加入房间 {room_id}, 买入: {buy_in}")
            
            # 不再自动开始游戏，需要手动开始
            
            return True
        else:
            # 加入游戏失败，从房间移除
            room.player_ids.discard(player_id)
            room.current_players = len(room.player_ids)
            self.player_room_mapping.pop(player_id, None)
            return False
    
    async def leave_room(self, room_id: str, player_id: str) -> bool:
        """
        玩家离开房间 - 优化版本，减少阻塞操作
        
        Args:
            room_id: 房间ID
            player_id: 玩家ID
            
        Returns:
            bool: 是否成功离开
        """
        room = self.rooms.get(room_id)
        if not room:
            return False
        
        # 从等待列表移除（快速操作）
        if player_id in room.waiting_list:
            room.waiting_list.remove(player_id)
            self.player_room_mapping.pop(player_id, None)
            return True
        
        # 从房间移除（快速操作）
        if player_id in room.player_ids:
            room.player_ids.discard(player_id)
            room.current_players = len(room.player_ids)
            room.update_activity()
            
            # 更新映射（快速操作）
            self.player_room_mapping.pop(player_id, None)
            
            logger.info(f"玩家 {player_id} 离开房间 {room_id}")
            
            # 异步处理复杂操作，不阻塞主流程
            asyncio.create_task(self._handle_player_leave_async(room, player_id))
            
            return True
        
        return False
    
    async def _handle_player_leave_async(self, room: GameRoom, player_id: str):
        """
        异步处理玩家离开的复杂逻辑
        
        Args:
            room: 房间对象
            player_id: 玩家ID
        """
        try:
            # 从游戏中移除并返还筹码
            if room.game:
                player_chips = room.game.get_player_chips(player_id)
                if player_chips > 0:
                    # 异步返还筹码
                    await self.player_manager.add_chips(player_id, player_chips, "离开房间返还")
                
                # 从游戏中移除玩家
                room.game.remove_player(player_id)
            
            # 处理等待列表中的玩家
            await self._process_waiting_list(room)
            
            # 如果房间空了，标记为结束
            if room.current_players == 0:
                room.status = RoomStatus.FINISHED
                await self._cleanup_room(room.room_id)
                
        except Exception as e:
            logger.error(f"异步处理玩家离开失败: {e}")
    
    async def add_observer(self, room_id: str, observer_id: str) -> bool:
        """
        添加旁观者
        
        Args:
            room_id: 房间ID
            observer_id: 旁观者ID
            
        Returns:
            bool: 是否成功
        """
        room = self.rooms.get(room_id)
        if not room or not room.allow_observers:
            return False
        
        # 检查是否已经是玩家
        if observer_id in room.player_ids:
            return False
        
        room.observers.add(observer_id)
        room.update_activity()
        
        logger.info(f"旁观者 {observer_id} 加入房间 {room_id}")
        return True
    
    async def remove_observer(self, room_id: str, observer_id: str) -> bool:
        """
        移除旁观者
        
        Args:
            room_id: 房间ID  
            observer_id: 旁观者ID
            
        Returns:
            bool: 是否成功
        """
        room = self.rooms.get(room_id)
        if not room:
            return False
        
        room.observers.discard(observer_id)
        return True
    
    async def get_room(self, room_id: str) -> Optional[GameRoom]:
        """
        获取房间信息
        
        Args:
            room_id: 房间ID
            
        Returns:
            Optional[GameRoom]: 房间对象
        """
        return self.rooms.get(room_id)
    
    async def get_player_room(self, player_id: str) -> Optional[GameRoom]:
        """
        获取玩家所在房间 - 优化版本，增加快速检查和状态一致性验证
        
        Args:
            player_id: 玩家ID
            
        Returns:
            Optional[GameRoom]: 房间对象
        """
        # 快速检查映射
        room_id = self.player_room_mapping.get(player_id)
        if not room_id:
            return None
            
        # 检查房间是否存在
        room = self.rooms.get(room_id)
        if not room:
            # 房间不存在，清理映射
            self.player_room_mapping.pop(player_id, None)
            logger.warning(f"清理无效房间映射: {player_id} -> {room_id}")
            return None
        
        # 双重验证：检查玩家是否真的在房间中
        if player_id not in room.player_ids and player_id not in room.waiting_list:
            # 映射不一致，清理并返回None  
            self.player_room_mapping.pop(player_id, None)
            logger.warning(f"清理不一致的玩家映射: {player_id} -> {room_id}")
            return None
            
        return room
    
    async def get_available_rooms(self) -> List[GameRoom]:
        """
        获取可用房间列表
        
        Returns:
            List[GameRoom]: 可用房间列表
        """
        available_rooms = []
        
        for room in self.rooms.values():
            if (room.status in [RoomStatus.WAITING, RoomStatus.IN_GAME] and
                room.is_active and
                not room.is_private):
                available_rooms.append(room)
        
        # 按创建时间排序
        available_rooms.sort(key=lambda r: r.created_time, reverse=True)
        
        return available_rooms
    
    async def quick_match(self, player_id: str) -> Optional[GameRoom]:
        """
        快速匹配房间
        
        Args:
            player_id: 玩家ID
            
        Returns:
            Optional[GameRoom]: 匹配到的房间
        """
        # 获取玩家信息
        player = await self.player_manager.get_or_create_player(player_id)
        
        # 寻找合适的房间
        suitable_rooms = []
        
        for room in self.rooms.values():
            if (room.room_type == RoomType.QUICK_MATCH and
                room.status == RoomStatus.WAITING and
                not room.is_full and
                not room.is_private and
                room.min_buy_in <= player.chips):
                suitable_rooms.append(room)
        
        # 按玩家数量排序，优先加入人多的房间
        suitable_rooms.sort(key=lambda r: r.current_players, reverse=True)
        
        # 尝试加入最合适的房间
        for room in suitable_rooms:
            if await self.join_room(room.room_id, player_id):
                return room
        
        # 没有合适房间，创建新房间
        new_room = await self.create_room(
            creator_id=player_id,
            room_type=RoomType.QUICK_MATCH,
            small_blind=1,
            big_blind=2,
            max_players=6
        )
        
        return new_room
    
    async def reset_room(self, room_id: str) -> bool:
        """
        重置房间状态（游戏结束后）
        
        Args:
            room_id: 房间ID
            
        Returns:
            bool: 是否成功
        """
        room = self.rooms.get(room_id)
        if not room:
            return False
        
        room.status = RoomStatus.WAITING
        room.update_activity()
        
        # 检查玩家筹码，移除筹码不足的玩家
        if room.game:
            players_to_remove = []
            
            for player_id in list(room.player_ids):
                player_chips = room.game.get_player_chips(player_id)
                if player_chips < room.min_buy_in:
                    players_to_remove.append(player_id)
                    # 返还剩余筹码
                    if player_chips > 0:
                        await self.player_manager.add_chips(player_id, player_chips, "游戏结束返还")
            
            # 移除筹码不足的玩家
            for player_id in players_to_remove:
                await self.leave_room(room_id, player_id)
        
        # 处理等待列表
        await self._process_waiting_list(room)
        
        # 如果仍有足够玩家，考虑开始新游戏
        if room.can_start_game and room.auto_start:
            await asyncio.sleep(3)  # 短暂延迟
            await self._start_game(room)
        
        return True
    
    async def close_room(self, room_id: str, reason: str = "房间关闭") -> bool:
        """
        关闭房间
        
        Args:
            room_id: 房间ID
            reason: 关闭原因
            
        Returns:
            bool: 是否成功
        """
        room = self.rooms.get(room_id)
        if not room:
            return False
        
        # 结束游戏并返还筹码
        if room.game:
            for player_id in room.player_ids:
                player_chips = room.game.get_player_chips(player_id)
                if player_chips > 0:
                    await self.player_manager.add_chips(player_id, player_chips, f"房间关闭返还: {reason}")
        
        # 清除玩家映射
        for player_id in room.player_ids:
            self.player_room_mapping.pop(player_id, None)
        
        # 移除房间
        room.status = RoomStatus.FINISHED
        
        logger.info(f"房间 {room_id} 已关闭: {reason}")
        
        await self._cleanup_room(room_id)
        
        return True
    
    async def close_all_rooms(self):
        """关闭所有房间"""
        room_ids = list(self.rooms.keys())
        
        for room_id in room_ids:
            await self.close_room(room_id, "系统关闭")
        
        logger.info("所有房间已关闭")
    
    async def _start_game(self, room: GameRoom) -> bool:
        """
        开始游戏
        
        Args:
            room: 房间对象
            
        Returns:
            bool: 是否成功开始
        """
        if not room.can_start_game:
            return False
        
        room.status = RoomStatus.STARTING
        room.update_activity()
        
        # 启动游戏
        if room.game and room.game.start_new_hand():
            room.status = RoomStatus.IN_GAME
            logger.info(f"房间 {room.room_id} 游戏开始，玩家数: {room.current_players}")
            return True
        else:
            room.status = RoomStatus.WAITING
            logger.warning(f"房间 {room.room_id} 游戏启动失败")
            return False
    
    async def _process_waiting_list(self, room: GameRoom):
        """
        处理房间等待列表
        
        Args:
            room: 房间对象
        """
        while room.waiting_list and not room.is_full:
            player_id = room.waiting_list.pop(0)
            
            # 检查玩家是否仍然有效
            player = await self.player_manager.get_or_create_player(player_id)
            if player.is_banned or player.chips < room.min_buy_in:
                continue
            
            # 尝试加入房间
            if await self.join_room(room.room_id, player_id):
                logger.info(f"等待列表玩家 {player_id} 成功加入房间 {room.room_id}")
            else:
                break
    
    async def _cleanup_room(self, room_id: str):
        """
        清理房间资源
        
        Args:
            room_id: 房间ID
        """
        room = self.rooms.get(room_id)
        if room and room.status == RoomStatus.FINISHED and room.current_players == 0:
            # 延迟删除，给时间处理最后的数据
            await asyncio.sleep(30)
            
            if room_id in self.rooms:
                del self.rooms[room_id]
                logger.info(f"房间 {room_id} 资源已清理")
    
    async def _room_cleanup_loop(self):
        """房间清理循环任务"""
        while True:
            try:
                await asyncio.sleep(self.room_cleanup_interval)
                await self._cleanup_inactive_rooms()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"房间清理任务错误: {e}")
    
    async def _cleanup_inactive_rooms(self):
        """清理不活跃的房间"""
        current_time = time.time()
        rooms_to_close = []
        
        for room_id, room in self.rooms.items():
            # 检查房间是否长时间无活动
            if (current_time - room.last_activity > self.inactive_room_timeout and
                room.status != RoomStatus.IN_GAME):
                rooms_to_close.append(room_id)
            
            # 检查空房间
            elif room.current_players == 0 and room.status != RoomStatus.FINISHED:
                room.status = RoomStatus.FINISHED
                rooms_to_close.append(room_id)
        
        # 关闭需要清理的房间
        for room_id in rooms_to_close:
            await self.close_room(room_id, "长时间无活动")
    
    async def get_room_stats(self) -> Dict[str, Any]:
        """
        获取房间统计信息
        
        Returns:
            Dict: 统计信息
        """
        # 只统计活跃房间（非FINISHED状态）
        active_room_list = [r for r in self.rooms.values() if r.status != RoomStatus.FINISHED]
        
        total_rooms = len(active_room_list)
        waiting_rooms = len([r for r in active_room_list if r.status == RoomStatus.WAITING])
        in_game_rooms = len([r for r in active_room_list if r.status == RoomStatus.IN_GAME])
        starting_rooms = len([r for r in active_room_list if r.status == RoomStatus.STARTING])
        paused_rooms = len([r for r in active_room_list if r.status == RoomStatus.PAUSED])
        
        # 统计实际在游戏中的玩家
        total_players = sum(r.current_players for r in active_room_list)
        total_observers = sum(len(r.observers) for r in active_room_list)
        
        return {
            'total_rooms': total_rooms,
            'waiting_rooms': waiting_rooms,
            'active_rooms': in_game_rooms,  # IN_GAME状态的房间
            'starting_rooms': starting_rooms,
            'paused_rooms': paused_rooms,
            'finished_rooms': len([r for r in self.rooms.values() if r.status == RoomStatus.FINISHED]),
            'total_players': total_players,
            'total_observers': total_observers,
            'average_players_per_room': total_players / max(1, total_rooms) if total_rooms > 0 else 0
        }
    
    async def load_rooms(self):
        """从数据库加载房间数据"""
        # 房间数据通常不持久化，重启后重新创建
        logger.info("房间管理器初始化完成")
    
    async def cleanup(self):
        """清理资源"""
        if self.cleanup_task:
            self.cleanup_task.cancel()
            
        await self.close_all_rooms()
        logger.info("房间管理器资源已清理")
