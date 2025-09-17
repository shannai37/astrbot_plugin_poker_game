from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger

import asyncio
import json
from typing import Dict, List, Optional, Any, Callable, Tuple, AsyncGenerator
from dataclasses import dataclass, asdict
from enum import Enum
import random
import time
from pathlib import Path
import functools

# 导入自定义模块
from .models.card_system import Card, CardSystem, HandRank
from .models.game_engine import TexasHoldemGame, GamePhase, PlayerAction
from .models.player_manager import PlayerManager, PlayerInfo
from .models.room_manager import RoomManager, GameRoom, RoomStatus
from .utils.data_persistence import DatabaseManager
from .utils.ui_builder import GameUIBuilder


def handle_plugin_exception(operation_name: str):
    """
    异常处理装饰器，用于包装命令处理函数
    
    Args:
        operation_name: 操作名称，用于错误消息
        
    Returns:
        装饰器函数
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(self, event, *args, **kwargs):
            try:
                async for result in func(self, event, *args, **kwargs):
                    yield result
            except Exception as e:
                logger.error(f"{operation_name}失败: {e}")
                yield event.plain_result(f"❌ {operation_name}失败: {str(e)}")
        return wrapper
    return decorator


@register("texas_holdem", "山萘", "德州扑克游戏插件 - 支持多人游戏、积分系统、房间管理", "1.1.0")
class TexasHoldemPlugin(Star):
    """
    德州扑克插件主类
    
    功能包括：
    - 多人德州扑克游戏
    - 玩家积分和统计系统  
    - 房间管理和匹配系统
    - 管理员控制面板
    - 数据持久化
    
    支持的操作：
    - 玩家游戏指令：join/leave/status/stats/rank
    - 房间管理：create/rooms/quickjoin
    - 管理员指令：ban/unban/addchips/reset等
    """
    
    def __init__(self, context: Context):
        super().__init__(context)
        
        # 初始化数据目录
        self.data_dir = Path("data/plugins/texas_holdem_data")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # 初始化核心组件
        self.database_manager = DatabaseManager(self.data_dir / "game_data.db")
        self.player_manager = PlayerManager(self.database_manager)
        self.room_manager = RoomManager(self.database_manager, self.player_manager)
        self.ui_builder = GameUIBuilder()
        
        # 初始化标志
        self.is_initialized = False
        
        # 插件配置（硬编码默认值）
        self.plugin_config = {
            "initial_chips": 3000,  # 与PlayerInfo默认值保持一致
            "daily_bonus": 100, 
            "blind_levels": [1, 2, 5, 10, 25, 50],
            "timeout_seconds": 30,
            "max_rooms": 20,
            "min_players": 2,
            "max_players": 6
        }
        
        # 记录插件启动时间
        self.start_time = time.time()
        
        # 初始化命令处理器（新架构预览）
        self._init_command_handlers()
        
        logger.info("德州扑克插件初始化完成")
    
    def _init_command_handlers(self):
        """
        初始化命令处理器（现在正在使用）
        
        将命令处理逻辑分离到专门的处理器中，实现职责分离。
        """
        try:
            from .handlers.game_handler import GameCommandHandler
            from .handlers.admin_handler import AdminCommandHandler
            
            # 创建处理器实例
            self.game_handler = GameCommandHandler(self)
            self.admin_handler = AdminCommandHandler(self)
            
            logger.info("命令处理器初始化完成")
            
        except ImportError as e:
            logger.warning(f"命令处理器导入失败: {e}")
            self.game_handler = None
            self.admin_handler = None
        except Exception as e:
            logger.error(f"命令处理器初始化失败: {e}")
            self.game_handler = None
            self.admin_handler = None

    async def initialize_plugin(self):
        """
        初始化插件数据库和配置
        
        创建必要的数据表，加载历史数据
        """
        try:
            logger.info("=" * 50)
            logger.info("🚀 开始初始化德州扑克插件...")
            logger.info("=" * 50)
            
            # 确保数据目录存在
            self.data_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"✅ 数据目录已确保存在: {self.data_dir}")
            
            # 检查数据库管理器状态
            logger.info("🔍 检查数据库管理器状态...")
            logger.info(f"数据库管理器类型: {type(self.database_manager)}")
            logger.info(f"数据库文件路径: {self.database_manager.db_file if hasattr(self.database_manager, 'db_file') else '未知'}")
            
            # 初始化数据库管理器
            logger.info("🔧 正在初始化数据库管理器...")
            await self.database_manager.initialize()
            logger.info("✅ 数据库管理器初始化完成")
            
            # 验证数据库连接
            logger.info("🧪 验证数据库连接...")
            if hasattr(self.database_manager, 'db_connection') and self.database_manager.db_connection:
                # 测试连接
                try:
                    await self.database_manager.db_connection.execute("SELECT 1")
                    logger.info("✅ 数据库连接正常")
                except Exception as e:
                    logger.error(f"❌ 数据库连接测试失败: {e}")
                    raise Exception("数据库连接测试失败") from e
            else:
                logger.error("❌ 数据库连接对象不存在")
                raise Exception("数据库连接对象不存在")
            
            # 加载玩家数据
            logger.info("👥 正在加载玩家数据...")
            await self.player_manager.load_players()
            logger.info(f"✅ 玩家数据加载完成，当前玩家数: {len(self.player_manager.players)}")
            
            # 启动自动保存任务
            logger.info("💾 启动玩家数据自动保存任务...")
            self.player_manager.start_auto_save()
            logger.info("✅ 自动保存任务已启动")
            
            # 加载房间数据
            logger.info("🏠 正在加载房间数据...")
            await self.room_manager.load_rooms()
            logger.info(f"✅ 房间数据加载完成，当前房间数: {len(self.room_manager.rooms)}")
            
            self.is_initialized = True
            logger.info("=" * 50)
            logger.info("🎉 德州扑克插件初始化完全成功!")
            logger.info("=" * 50)
            
        except Exception as e:
            logger.error("=" * 50)
            logger.error("💥 插件初始化失败!")
            logger.error(f"错误类型: {type(e).__name__}")
            logger.error(f"错误信息: {str(e)}")
            logger.error("=" * 50)
            
            import traceback
            logger.error("完整错误栈:")
            logger.error(traceback.format_exc())
            
            self.is_initialized = False
            # 尝试清理已初始化的组件
            try:
                if hasattr(self.player_manager, 'stop_auto_save'):
                    self.player_manager.stop_auto_save()
                    logger.info("🧹 自动保存任务已停止")
            except Exception as cleanup_error:
                logger.error(f"清理过程中发生错误: {cleanup_error}")
            raise

    @filter.on_astrbot_loaded()
    async def on_loaded(self):
        """AstrBot启动完成时初始化插件"""
        await self.initialize_plugin()

    async def ensure_initialized(self):
        """确保插件已初始化"""
        if not self.is_initialized:
            await self.initialize_plugin()

    # ==================== 玩家游戏指令 ====================
    
    @filter.command("poker")
    async def poker_main(self, event: AstrMessageEvent) -> AsyncGenerator:
        """
        德州扑克主命令入口
        
        Args:
            event: 消息事件对象
            
        Yields:
            消息结果对象
        """
        help_text = """🎰 德州扑克游戏

🎮 基础指令：
• /poker_help - 查看完整帮助
• /poker_status - 查看个人状态
• /poker_game_status - 查看当前游戏状态
• /poker_achievements [页数] - 查看成就（支持翻页）
• /poker_equip [成就ID] - 装备成就
• /poker_leaderboard [页数] - 查看排行榜（支持翻页）
• /poker_rooms - 查看房间列表

🏠 房间操作：
• /poker_create [盲注] - 创建房间
• /poker_join [房间号] - 加入房间
• /poker_quickjoin - 快速匹配
• /poker_start - 开始游戏（2人即可）

🎯 游戏操作：
• /poker_call - 跟注
• /poker_raise [金额] - 加注
• /poker_fold - 弃牌
• /poker_check - 过牌

🆘 紧急功能：
• /poker_exit - 退出游戏

输入 /poker_help 查看完整功能列表"""

        yield event.plain_result(help_text)
    
    @filter.command("poker_help")
    async def poker_help(self, event: AstrMessageEvent) -> AsyncGenerator:
        """
        显示德州扑克插件帮助信息
        
        Args:
            event: 消息事件对象
        """
        help_text = """🎰 德州扑克游戏帮助

🎮 基础指令：
• /poker_join [房间号] - 加入指定房间
• /poker_leave - 离开当前游戏
• /poker_status - 查看个人状态
• /poker_achievements [页数] - 查看成就（支持翻页）
• /poker_equip [成就ID] - 装备成就

📊 统计查询：
• /poker_stats - 查看详细统计
• /poker_leaderboard [页数] - 查看排行榜（支持翻页）

🏠 房间管理：
• /poker_rooms - 查看所有房间
• /poker_create [盲注级别] - 创建房间（盲注级别 1-6）
  ┌─ 💡 盲注级别说明 ─┐
  │ 1: 1/2     4: 10/20  │
  │ 2: 2/4     5: 25/50  │
  │ 3: 5/10    6: 50/100 │
  └──────────────────────┘
• /poker_quickjoin - 快速匹配
• /poker_start - 开始游戏（需至少2人）

🎯 游戏中操作：
• /poker_call - 跟注
• /poker_raise [金额] - 加注到指定金额
• /poker_fold - 弃牌
• /poker_check - 过牌
• /poker_allin - 全押
• /poker_exit - 紧急退出

👑 管理员指令：
• /poker_admin - 管理面板
• /poker_admin_players - 查看玩家列表
• /poker_admin_ban - 封禁玩家
• /poker_admin_unban - 解封玩家

💰 初始积分: 3000 筹码
⏰ 操作超时: 120 秒（90秒时警告）

🎯 祝您游戏愉快！"""
        
        yield event.plain_result(help_text)


    @filter.command("poker_exit")
    async def emergency_exit(self, event: AstrMessageEvent) -> AsyncGenerator:
        """退出游戏并返回筹码（委托给handler处理）"""
        if self.game_handler:
            async for result in self.game_handler.handle_emergency_exit(event):
                yield result
        else:
            yield event.plain_result("❌ 游戏处理器未初始化")

    @filter.command("poker_game_status")
    async def game_status(self, event: AstrMessageEvent) -> AsyncGenerator:
        """
        查看当前游戏详细状态
        
        Args:
            event: 消息事件对象
        """
        user_id = event.get_sender_id()
        
        try:
            room = await self.room_manager.get_player_room(user_id)
            if not room or not room.game:
                yield event.plain_result("❌ 您当前不在任何游戏中")
                return
            
            game_state = room.game.get_game_state()
            
            # 构建详细的游戏状态信息
            status_info = f"""🎮 游戏状态详情
            
🏠 房间ID: {room.room_id[:8]}
🎯 游戏阶段: {game_state.get('phase', 'unknown')}
🎲 局数: {game_state.get('hand_number', 0)}
💰 总底池: {game_state.get('main_pot', 0)}
💵 当前最高下注: {game_state.get('current_bet', 0)}
👤 当前行动玩家: {game_state.get('current_player_id', 'None')}

👥 玩家状态:"""
            
            players_info = game_state.get('players', {})
            for pid, player_data in players_info.items():
                player_name = pid[:8]
                chips = player_data.get('chips', 0)
                current_bet = player_data.get('current_bet', 0)
                status = player_data.get('status', 'unknown')
                is_dealer = "🎲" if player_data.get('is_dealer') else ""
                is_sb = "🔵" if player_data.get('is_small_blind') else ""
                is_bb = "🔴" if player_data.get('is_big_blind') else ""
                last_action = player_data.get('last_action', 'none')
                
                status_info += f"""
  {is_dealer}{is_sb}{is_bb} {player_name}: 💳{chips} | 💰{current_bet} | {status} | {last_action}"""
            
            # 显示公共牌
            community_cards = game_state.get('community_cards', [])
            if community_cards:
                status_info += f"\n\n🎴 公共牌: {' '.join(community_cards)}"
            
            # 显示活跃玩家列表
            active_players = [pid for pid in room.game.player_order if room.game.players[pid].can_act()]
            status_info += f"\n\n🟢 当前活跃玩家: {', '.join([pid[:8] for pid in active_players])}"
            
            yield event.plain_result(status_info)
            
        except Exception as e:
            logger.error(f"查看游戏状态失败: {e}")
            yield event.plain_result(f"❌ 查看游戏状态失败: {str(e)}")

    @filter.command("poker_join")
    async def join_room(self, event: AstrMessageEvent, room_id: str = "") -> AsyncGenerator:
        """加入指定房间（委托给handler处理）"""
        if self.game_handler:
            async for result in self.game_handler.handle_join_room(event, room_id):
                yield result
        else:
            yield event.plain_result("❌ 游戏处理器未初始化")

    @filter.command("poker_quickjoin")
    async def quickjoin_room(self, event: AstrMessageEvent) -> AsyncGenerator:
        """快速匹配房间"""
        user_id = event.get_sender_id()
        
        try:
            await self.ensure_initialized()
            
            # 检查玩家是否已在房间中
            existing_room = await self.room_manager.get_player_room(user_id)
            if existing_room:
                yield event.plain_result(f"❌ 您已在房间 {existing_room.room_id[:8]} 中")
                return
            
            # 确保玩家已注册
            player = await self.player_manager.get_or_create_player(user_id, event.get_sender_name() or f"Player_{user_id[-8:]}")
            if not player:
                yield event.plain_result("❌ 玩家注册失败")
                return
            
            # 获取所有可用房间
            all_rooms = await self.room_manager.get_all_rooms()
            available_rooms = [
                room for room in all_rooms.values() 
                if room.status.name in ['WAITING', 'PLAYING'] and len(room.player_ids) < room.max_players
            ]
            
            if not available_rooms:
                # 没有可用房间，自动创建一个
                yield event.plain_result("🔍 未找到可用房间，正在为您创建新房间...")
                
                room = await self.room_manager.create_room(
                    creator_id=user_id,
                    small_blind=1,
                    big_blind=2,
                    max_players=6
                )
                
                if room:
                    yield event.plain_result(f"""✅ 快速匹配成功！自动创建房间
🏠 房间号: {room.room_id[:8]}
💰 盲注: 1/2
👤 房主: {player.display_name}
📋 状态: 等待更多玩家

🎯 等待其他玩家加入，或使用 /poker_start 开始游戏（至少2人）""")
                else:
                    yield event.plain_result("❌ 创建房间失败")
                return
            
            # 选择最合适的房间（优先选择人数较多但未满的房间）
            available_rooms.sort(key=lambda r: len(r.player_ids), reverse=True)
            target_room = available_rooms[0]
            
            # 加入房间
            success = await self.room_manager.add_player_to_room(target_room.room_id, user_id)
            
            if success:
                updated_room = await self.room_manager.get_room(target_room.room_id)
                yield event.plain_result(f"""🎉 快速匹配成功！
🏠 房间号: {target_room.room_id[:8]}
💰 盲注: {updated_room.small_blind}/{updated_room.big_blind}
👥 当前人数: {len(updated_room.player_ids)}/{updated_room.max_players}
📋 房间状态: {updated_room.status.name}

💡 使用 /poker_start 开始游戏（需要房主操作）""")
                
                # 如果房间已有足够玩家，提示可以开始游戏
                if len(updated_room.player_ids) >= 2:
                    yield event.plain_result("🚀 房间已有足够玩家，房主可以开始游戏了！")
                    
            else:
                yield event.plain_result("❌ 加入房间失败")
                
        except Exception as e:
            logger.error(f"快速匹配失败: {e}")
            yield event.plain_result(f"❌ 快速匹配失败: {str(e)}")

    @filter.command("poker_leave")
    async def leave_room(self, event: AstrMessageEvent) -> AsyncGenerator:
        """离开当前房间（委托给handler处理）"""
        if self.game_handler:
            async for result in self.game_handler.handle_leave_room(event):
                yield result
        else:
            yield event.plain_result("❌ 游戏处理器未初始化")

    @filter.command("poker_achievements")
    async def achievements_view(self, event: AstrMessageEvent, page: int = 1) -> AsyncGenerator:
        """查看成就进度（委托给handler处理）- 支持翻页"""
        if self.game_handler:
            async for result in self.game_handler.handle_achievements(event, page):
                yield result
        else:
            yield event.plain_result("❌ 游戏处理器未初始化")
    
    @filter.command("poker_equip")
    async def equip_achievement(self, event: AstrMessageEvent, achievement_id: str = "") -> AsyncGenerator:
        """装备成就（委托给handler处理）"""
        if self.game_handler:
            async for result in self.game_handler.handle_equip_achievement(event, achievement_id or None):
                yield result
        else:
            yield event.plain_result("❌ 游戏处理器未初始化")

    @filter.command("poker_status")
    async def player_status(self, event: AstrMessageEvent) -> AsyncGenerator:
        """查看玩家个人状态（委托给handler处理）"""
        if self.game_handler:
            async for result in self.game_handler.handle_player_status(event):
                yield result
        else:
            yield event.plain_result("❌ 游戏处理器未初始化")

    @filter.command("poker_stats")
    async def player_stats(self, event: AstrMessageEvent) -> AsyncGenerator:
        """查看玩家详细统计（委托给handler处理）"""
        if self.game_handler:
            async for result in self.game_handler.handle_player_stats(event):
                yield result
        else:
            yield event.plain_result("❌ 游戏处理器未初始化")

    @filter.command("poker_rooms")
    async def list_rooms(self, event: AstrMessageEvent) -> AsyncGenerator:
        """查看所有可用房间（委托给handler处理）"""
        if self.game_handler:
            async for result in self.game_handler.handle_rooms_list(event):
                yield result
        else:
            yield event.plain_result("❌ 游戏处理器未初始化")

    @filter.command("poker_create")
    async def create_room(self, event: AstrMessageEvent, blind_level: int = 1) -> AsyncGenerator:
        """创建新房间（委托给handler处理）"""
        if self.game_handler:
            async for result in self.game_handler.handle_create_room(event, blind_level):
                yield result
        else:
            yield event.plain_result("❌ 游戏处理器未初始化")

    @filter.command("poker_start")
    async def start_game(self, event: AstrMessageEvent) -> AsyncGenerator:
        """
        开始房间内的游戏
        
        Args:
            event: 消息事件对象
        """
        user_id = event.get_sender_id()
        
        try:
            # 获取玩家所在房间
            room = await self.room_manager.get_player_room(user_id)
            if not room:
                yield event.plain_result("❌ 您当前不在任何房间中")
                return
            
            # 检查是否是房间创建者（可选限制）
            # if room.creator_id != user_id:
            #     yield event.plain_result("❌ 只有房主可以开始游戏")
            #     return
            
            # 检查游戏是否已经在进行中
            # 只有在游戏存在且有活跃玩家时才认为游戏在进行中
            if room.game and not room.game.is_game_over() and len([p for p in room.game.players.values() if p.is_in_hand()]) > 1:
                yield event.plain_result("❌ 游戏已经在进行中")
                return
            
            # 检查玩家数量
            if len(room.player_ids) < 2:
                yield event.plain_result("❌ 至少需要2名玩家才能开始游戏")
                return
            
            # 初始化游戏（如果还没有）
            if not room.game:
                from .models.game_engine import TexasHoldemGame
                room.game = TexasHoldemGame(
                    room_id=room.room_id,
                    small_blind=room.small_blind,
                    big_blind=room.big_blind,
                    max_players=room.max_players
                )
            
            # 确保所有房间玩家都在游戏中
            for player_id in room.player_ids:
                if player_id not in room.game.players:
                    player = await self.player_manager.get_or_create_player(player_id)
                    buy_in = min(player.chips, room.max_buy_in)
                    buy_in = max(buy_in, room.min_buy_in)
                    # 调用修复后的add_player方法，传递display_name
                    room.game.add_player(player_id, buy_in, player.display_name)
            
            # 开始新一局
            if room.game.start_new_hand():
                yield event.plain_result("🎉 游戏开始！")
                
                # 显示盲注信息和当前行动玩家
                small_blind_player = None
                big_blind_player = None
                current_player = room.game.players.get(room.game.current_player_id)
                
                # 查找盲注玩家
                for player in room.game.players.values():
                    if hasattr(player, 'position'):
                        if player.position == 'SB':
                            small_blind_player = player
                        elif player.position == 'BB':
                            big_blind_player = player
                
                blind_info = f"""💰 盲注信息：
• 小盲注: {room.game.small_blind} 筹码{' ('+small_blind_player.display_name+')' if small_blind_player else ''}
• 大盲注: {room.game.big_blind} 筹码{' ('+big_blind_player.display_name+')' if big_blind_player else ''}"""
                
                if current_player:
                    blind_info += f"\n🎲 首先行动: {current_player.display_name}"
                
                yield event.plain_result(blind_info)
                
                # 发送游戏状态
                game_status = self.ui_builder.build_game_status(room.game)
                yield event.plain_result(game_status)
            
                # 发送开始游戏的详细说明
                start_info = f"""
🎉 德州扑克游戏正式开始！

🎴 发牌完成：
• 每位玩家已获得2张底牌（私聊查看）
• 接下来将进行翻牌前下注

🎯 游戏流程：
1️⃣ Pre-flop（翻牌前）- 基于底牌下注
2️⃣ Flop（翻牌）- 3张公共牌
3️⃣ Turn（转牌）- 第4张公共牌  
4️⃣ River（河牌）- 第5张公共牌
5️⃣ Showdown（摊牌）- 比较牌型

💡 操作说明：
• /poker_call - 跟注
• /poker_raise [金额] - 加注
• /poker_fold - 弃牌
• /poker_check - 过牌（无需下注时）
• /poker_allin - 全押

🔔 注意：轮到您行动时会有提示！"""

                yield event.plain_result(start_info)
                
                # 给每个玩家发送私聊手牌
                private_success_count = 0
                for player_id in room.player_ids:
                    if player_id in room.game.players:
                        try:
                            await self._send_private_cards(event, player_id, room.game)
                            private_success_count += 1
                        except Exception as e:
                            logger.error(f"发送手牌给玩家 {player_id} 失败: {e}")
                            # 私聊失败时，不在公共频道显示手牌，只提示发送失败
                            yield event.plain_result(f"⚠️ 无法向玩家 {player_id[:8]} 发送手牌，请检查好友关系或私聊设置。")
                
                # 汇总私聊发牌结果
                if private_success_count == len(room.player_ids):
                    yield event.plain_result("✅ 所有玩家的底牌已通过私聊发送")
                else:
                    yield event.plain_result(f"⚠️ {private_success_count}/{len(room.player_ids)} 位玩家成功接收私聊手牌")
            else:
                yield event.plain_result("❌ 游戏开始失败，请检查游戏状态")
                
        except Exception as e:
            logger.error(f"开始游戏失败: {e}")
            yield event.plain_result(f"❌ 开始游戏失败: {str(e)}")

    # ==================== 游戏中操作 ====================
    
    @filter.command("poker_call")
    async def game_call(self, event: AstrMessageEvent) -> AsyncGenerator:
        """跟注操作（委托给handler处理）"""
        if self.game_handler:
            async for result in self.game_handler.handle_game_call(event):
                yield result
        else:
            yield event.plain_result("❌ 游戏处理器未初始化")

    @filter.command("poker_raise")
    async def game_raise(self, event: AstrMessageEvent, amount: int = None) -> AsyncGenerator:
        """加注操作（委托给handler处理）"""
        if self.game_handler:
            async for result in self.game_handler.handle_game_raise(event, amount):
                yield result
        else:
            yield event.plain_result("❌ 游戏处理器未初始化")

    @filter.command("poker_fold")
    async def game_fold(self, event: AstrMessageEvent) -> AsyncGenerator:
        """弃牌操作（委托给handler处理）"""
        if self.game_handler:
            async for result in self.game_handler.handle_game_fold(event):
                yield result
        else:
            yield event.plain_result("❌ 游戏处理器未初始化")

    @filter.command("poker_check")
    async def game_check(self, event: AstrMessageEvent) -> AsyncGenerator:
        """过牌操作（委托给handler处理）"""
        if self.game_handler:
            async for result in self.game_handler.handle_game_check(event):
                yield result
        else:
            yield event.plain_result("❌ 游戏处理器未初始化")

    @filter.command("poker_allin")
    async def game_allin(self, event: AstrMessageEvent) -> AsyncGenerator:
        """全押操作（委托给handler处理）"""
        if self.game_handler:
            async for result in self.game_handler.handle_game_allin(event):
                yield result
        else:
            yield event.plain_result("❌ 游戏处理器未初始化")


    # ==================== 辅助方法 ====================
    
    async def _validate_player_turn(self, event: AstrMessageEvent, user_id: str) -> Tuple[Optional[object], Optional[str]]:
        """
        验证玩家是否可以进行游戏操作
        
        Args:
            event: 消息事件对象
            user_id: 玩家ID
            
        Returns:
            Tuple[Optional[GameRoom], Optional[str]]: (房间对象, 错误消息)
            如果验证通过，返回 (room, None)
            如果验证失败，返回 (None, error_message)
        """
        # 获取玩家所在房间
        room = await self.room_manager.get_player_room(user_id)
        if not room or not room.game:
            return None, "❌ 您当前不在任何游戏中"
        
        # 检查是否轮到该玩家
        current_player = room.game.current_player_id
        if current_player != user_id:
            # 获取详细的游戏状态用于诊断
            game_state = room.game.get_game_state()
            active_players = [pid for pid in room.game.player_order if room.game.players[pid].can_act()]
            in_hand_players = [pid for pid in room.game.player_order if room.game.players[pid].is_in_hand()]
            
            error_msg = f"""❌ 还没轮到您行动
👤 当前行动玩家: {current_player}
🎯 您的ID: {user_id}
👥 活跃玩家列表: {', '.join([pid[:8] for pid in active_players])}
🃏 在牌局中: {', '.join([pid[:8] for pid in in_hand_players])}
🎲 游戏阶段: {game_state['phase']}
⏰ 请等待轮到您的回合"""
            
            return None, error_msg
        
        return room, None
    
    async def _resolve_player_id(self, partial_id: str, filter_condition=None) -> Tuple[Optional[str], Optional[str]]:
        """
        解析玩家ID，支持部分ID匹配（优化版本）
        
        Args:
            partial_id: 部分或完整的玩家ID
            filter_condition: 可选的过滤条件函数
            
        Returns:
            Tuple[Optional[str], Optional[str]]: (解析的玩家ID, 错误信息)
        """
        # 如果是完整ID，直接返回
        if len(partial_id) >= 8:
            return partial_id, None
        
        # 使用优化的前缀搜索
        matches = await self.player_manager.search_players_by_prefix(partial_id, filter_condition, limit=10)
        
        if not matches:
            filter_desc = "符合条件的" if filter_condition else ""
            return None, f"❌ 未找到{filter_desc}玩家: {partial_id}"
        elif len(matches) > 1:
            match_list = "\n".join([f"  • {p.player_id} ({p.display_name})" for p in matches[:5]])
            filter_desc = "符合条件的" if filter_condition else ""
            return None, f"❌ 找到多个匹配的{filter_desc}玩家:\n{match_list}"
        else:
            return matches[0].player_id, None

    # ==================== 管理员控制界面 ====================
    
    @filter.command("poker_admin")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def admin_panel(self, event: AstrMessageEvent) -> AsyncGenerator:
        """
        管理员主面板
        
        Args:
            event: 消息事件对象
        """
        try:
            # 获取系统统计
            system_stats = await self.database_manager.get_system_stats()
            room_stats = await self.room_manager.get_room_stats()
            
            panel_text = self.ui_builder.build_admin_panel(system_stats, room_stats)
            yield event.plain_result(panel_text)
            
        except Exception as e:
            logger.error(f"管理员面板显示失败: {e}")
            yield event.plain_result(f"❌ 管理员面板显示失败: {str(e)}")

    @filter.command("poker_admin_players")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def admin_players(self, event: AstrMessageEvent, limit: int = 20) -> AsyncGenerator:
        """
        查看玩家列表
        
        Args:
            event: 消息事件对象
            limit: 显示数量限制
        """
        try:
            all_players = await self.player_manager.get_all_players()
            
            # 按最后活跃时间排序
            all_players.sort(key=lambda p: p.last_active, reverse=True)
            
            if not all_players:
                yield event.plain_result("🚫 暂无玩家数据")
                return
            
            lines = []
            lines.append(f"👥 玩家列表 (共{len(all_players)}人，显示前{min(limit, len(all_players))}人)")
            lines.append("=" * 50)
            
            for i, player in enumerate(all_players[:limit], 1):
                # 状态标识
                status_icons = []
                if player.is_banned:
                    status_icons.append("🚫")
                if player.chips <= 0:
                    status_icons.append("💸")
                
                status_str = "".join(status_icons)
                
                # 在线状态
                online_status = "🟢" if time.time() - player.last_active < 300 else "⚫"
                
                line = (f"{i:2d}. {online_status} {player.display_name[:12]:<12} "
                       f"💰{player.chips:>6,} 🎲{player.total_games:>4} "
                       f"🏆{player.wins:>3} {status_str}")
                lines.append(line)
            
            yield event.plain_result("\n".join(lines))
            
        except Exception as e:
            logger.error(f"查看玩家列表失败: {e}")
            yield event.plain_result(f"❌ 查看玩家列表失败: {str(e)}")

    @filter.command("poker_admin_ban")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def admin_ban_player(self, event: AstrMessageEvent, player_id: str, duration: int = 0, reason: str = "管理员操作") -> AsyncGenerator:
        """
        封禁玩家
        
        Args:
            event: 消息事件对象
            player_id: 玩家ID
            duration: 封禁时长（小时），0为永久
            reason: 封禁原因
        """
        try:
            # 查找玩家
            resolved_player_id, error_msg = await self._resolve_player_id(player_id)
            if error_msg:
                yield event.plain_result(error_msg)
                return
            player_id = resolved_player_id
            
            # 执行封禁
            success = await self.player_manager.ban_player(player_id, reason, duration)
            
            if success:
                duration_str = f"{duration}小时" if duration > 0 else "永久"
                yield event.plain_result(f"✅ 已封禁玩家 {player_id[:12]}\n⏰ 时长: {duration_str}\n📝 原因: {reason}")
                
                # 如果玩家在房间中，强制离开
                room = await self.room_manager.get_player_room(player_id)
                if room:
                    await self.room_manager.leave_room(room.room_id, player_id)
                    yield event.plain_result(f"🏠 已将玩家从房间 {room.room_id[:8]} 中移除")
            else:
                yield event.plain_result(f"❌ 封禁失败，玩家不存在: {player_id}")
                
        except Exception as e:
            logger.error(f"封禁玩家失败: {e}")
            yield event.plain_result(f"❌ 封禁操作失败: {str(e)}")

    @filter.command("poker_admin_unban")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def admin_unban_player(self, event: AstrMessageEvent, player_id: str) -> AsyncGenerator:
        """
        解封玩家
        
        Args:
            event: 消息事件对象
            player_id: 玩家ID
        """
        try:
            # 查找玩家（支持部分ID匹配，只查找被封禁的玩家）
            resolved_player_id, error_msg = await self._resolve_player_id(player_id, lambda p: p.is_banned)
            if error_msg:
                yield event.plain_result(error_msg.replace("符合条件的", "被封禁的"))
                return
            player_id = resolved_player_id
            
            success = await self.player_manager.unban_player(player_id)
            
            if success:
                yield event.plain_result(f"✅ 已解封玩家 {player_id[:12]}")
            else:
                yield event.plain_result(f"❌ 解封失败，玩家不存在或未被封禁: {player_id}")
                
        except Exception as e:
            logger.error(f"解封玩家失败: {e}")
            yield event.plain_result(f"❌ 解封操作失败: {str(e)}")

    @filter.command("poker_admin_addchips")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def admin_add_chips(self, event: AstrMessageEvent, player_id: str, amount: int, reason: str = "管理员补充") -> AsyncGenerator:
        """
        给玩家增加筹码
        
        Args:
            event: 消息事件对象
            player_id: 玩家ID
            amount: 筹码数量
            reason: 增加原因
        """
        try:
            # 查找玩家（支持部分ID匹配）
            resolved_player_id, error_msg = await self._resolve_player_id(player_id)
            if error_msg:
                yield event.plain_result(error_msg)
                return
            player_id = resolved_player_id
            
            # 验证数量
            if amount == 0:
                yield event.plain_result("❌ 筹码数量不能为0")
                return
            
            if abs(amount) > 1000000:
                yield event.plain_result("❌ 单次操作筹码数量不能超过1,000,000")
                return
            
            success = await self.player_manager.add_chips(player_id, amount, reason)
            
            if success:
                player = await self.player_manager.get_or_create_player(player_id)
                action_text = "增加" if amount > 0 else "扣除"
                yield event.plain_result(f"✅ 已{action_text}玩家 {player_id[:12]} 筹码 {abs(amount):,}\n💰 当前筹码: {player.chips:,}\n📝 原因: {reason}")
            else:
                yield event.plain_result(f"❌ 筹码操作失败，玩家不存在: {player_id}")
                
        except Exception as e:
            logger.error(f"筹码操作失败: {e}")
            yield event.plain_result(f"❌ 筹码操作失败: {str(e)}")

    @filter.command("poker_admin_reset")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def admin_reset_player(self, event: AstrMessageEvent, player_id: str, keep_chips: bool = False) -> AsyncGenerator:
        """
        重置玩家数据
        
        Args:
            event: 消息事件对象
            player_id: 玩家ID
            keep_chips: 是否保留筹码
        """
        try:
            # 查找玩家（支持部分ID匹配）
            resolved_player_id, error_msg = await self._resolve_player_id(player_id)
            if error_msg:
                yield event.plain_result(error_msg)
                return
            player_id = resolved_player_id
            
            # 确认操作
            success = await self.player_manager.reset_player_data(player_id, keep_chips)
            
            if success:
                chips_text = "保留筹码" if keep_chips else "重置筹码"
                yield event.plain_result(f"✅ 已重置玩家 {player_id[:12]} 的数据\n📊 {chips_text}")
                
                # 如果玩家在房间中，强制离开
                room = await self.room_manager.get_player_room(player_id)
                if room:
                    await self.room_manager.leave_room(room.room_id, player_id)
                    yield event.plain_result(f"🏠 已将玩家从房间 {room.room_id[:8]} 中移除")
            else:
                yield event.plain_result(f"❌ 重置失败，玩家不存在: {player_id}")
                
        except Exception as e:
            logger.error(f"重置玩家数据失败: {e}")
            yield event.plain_result(f"❌ 重置操作失败: {str(e)}")

    @filter.command("poker_admin_rooms")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def admin_rooms(self, event: AstrMessageEvent) -> AsyncGenerator:
        """
        查看所有房间状态
        
        Args:
            event: 消息事件对象
        """
        try:
            all_rooms = list(self.room_manager.rooms.values())
            
            if not all_rooms:
                yield event.plain_result("🏠 当前没有活跃房间")
                return
            
            lines = []
            lines.append(f"🏠 房间管理 (共{len(all_rooms)}个)")
            lines.append("=" * 50)
            
            for room in all_rooms[:20]:  # 最多显示20个房间
                status_name = self.ui_builder._get_room_status_name(room.status)
                
                # 房间类型
                type_icon = "🔒" if room.is_private else "🌍"
                
                # 游戏进行情况
                game_info = ""
                if room.game and room.status.name == "IN_GAME":
                    game_phase = room.game.game_phase.value
                    game_info = f"[{self.ui_builder._get_phase_name(game_phase)}]"
                
                line = (f"{type_icon} {room.room_id[:8]} {status_name} "
                       f"[{room.current_players}/{room.max_players}] "
                       f"💰{room.small_blind}/{room.big_blind} {game_info}")
                lines.append(line)
                
                # 显示玩家
                if room.player_ids:
                    player_names = [pid[:8] for pid in list(room.player_ids)[:3]]
                    if len(room.player_ids) > 3:
                        player_names.append(f"...等{len(room.player_ids)}人")
                    lines.append(f"    👥 {', '.join(player_names)}")
                
                lines.append("")
            
            yield event.plain_result("\n".join(lines))
            
        except Exception as e:
            logger.error(f"查看房间状态失败: {e}")
            yield event.plain_result(f"❌ 查看房间状态失败: {str(e)}")

    @filter.command("poker_admin_close")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def admin_close_room(self, event: AstrMessageEvent, room_id: str, reason: str = "管理员关闭") -> AsyncGenerator:
        """
        强制关闭房间
        
        Args:
            event: 消息事件对象
            room_id: 房间ID
            reason: 关闭原因
        """
        try:
            # 支持部分房间ID匹配
            if len(room_id) < 8:
                matching_rooms = [r for r in self.room_manager.rooms.values() if r.room_id.startswith(room_id)]
                
                if not matching_rooms:
                    yield event.plain_result(f"❌ 未找到房间: {room_id}")
                    return
                elif len(matching_rooms) > 1:
                    room_list = "\n".join([f"  • {r.room_id} ({r.room_name})" for r in matching_rooms[:5]])
                    yield event.plain_result(f"❌ 找到多个匹配房间:\n{room_list}")
                    return
                else:
                    room_id = matching_rooms[0].room_id
            
            success = await self.room_manager.close_room(room_id, reason)
            
            if success:
                yield event.plain_result(f"✅ 已关闭房间 {room_id[:8]}\n📝 原因: {reason}")
            else:
                yield event.plain_result(f"❌ 关闭失败，房间不存在: {room_id}")
                
        except Exception as e:
            logger.error(f"关闭房间失败: {e}")
            yield event.plain_result(f"❌ 关闭房间失败: {str(e)}")

    @filter.command("poker_admin_kick")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def admin_kick_player(self, event: AstrMessageEvent, player_id: str, reason: str = "管理员操作") -> AsyncGenerator:
        """
        踢出玩家
        
        Args:
            event: 消息事件对象
            player_id: 玩家ID
            reason: 踢出原因
        """
        try:
            # 查找玩家所在房间
            room = await self.room_manager.get_player_room(player_id)
            
            if not room:
                yield event.plain_result(f"❌ 玩家 {player_id[:8]} 不在任何房间中")
                return
            
            success = await self.room_manager.leave_room(room.room_id, player_id)
            
            if success:
                yield event.plain_result(f"✅ 已将玩家 {player_id[:8]} 从房间 {room.room_id[:8]} 中踢出\n📝 原因: {reason}")
            else:
                yield event.plain_result(f"❌ 踢出操作失败")
                
        except Exception as e:
            logger.error(f"踢出玩家失败: {e}")
            yield event.plain_result(f"❌ 踢出操作失败: {str(e)}")

    @filter.command("poker_admin_stats")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def admin_detailed_stats(self, event: AstrMessageEvent) -> AsyncGenerator:
        """
        详细系统统计
        
        Args:
            event: 消息事件对象
        """
        try:
            system_stats = await self.database_manager.get_system_stats()
            room_stats = await self.room_manager.get_room_stats()
            
            lines = []
            lines.append("📊 德州扑克系统统计")
            lines.append("=" * 40)
            
            # 系统统计
            lines.append("🖥️ 系统状态:")
            lines.append(f"  💾 数据库: {system_stats.get('database_path', 'N/A')}")
            runtime_seconds = time.time() - self.start_time
            lines.append(f"  📅 运行时间: {self.ui_builder.format_duration(runtime_seconds)}")
            lines.append("")
            
            # 玩家统计
            lines.append("👥 玩家统计:")
            lines.append(f"  📊 总注册: {system_stats.get('total_players', 0)}人")
            lines.append(f"  🟢 活跃(7天): {system_stats.get('active_players', 0)}人")
            lines.append(f"  🚫 被封禁: {system_stats.get('banned_players', 0)}人")
            lines.append(f"  💰 总筹码: {system_stats.get('total_chips', 0):,}")
            lines.append("")
            
            # 游戏统计
            lines.append("🎲 游戏统计:")
            lines.append(f"  📈 总游戏: {system_stats.get('total_games', 0)}局")
            lines.append(f"  🏠 当前房间: {room_stats.get('total_rooms', 0)}个")
            lines.append(f"  🟢 游戏中: {room_stats.get('active_rooms', 0)}个")
            lines.append(f"  ⏳ 等待中: {room_stats.get('waiting_rooms', 0)}个")
            lines.append(f"  👥 在线: {room_stats.get('total_players', 0)}人")
            lines.append(f"  👁️ 旁观: {room_stats.get('total_observers', 0)}人")
            
            # 平均值
            avg_players = room_stats.get('average_players_per_room', 0)
            if avg_players > 0:
                lines.append(f"  📊 平均每房间: {avg_players:.1f}人")
            
            yield event.plain_result("\n".join(lines))
            
        except Exception as e:
            logger.error(f"获取详细统计失败: {e}")
            yield event.plain_result(f"❌ 获取统计失败: {str(e)}")

    @filter.command("poker_admin_backup")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def admin_backup(self, event: AstrMessageEvent) -> AsyncGenerator:
        """
        备份数据库
        
        Args:
            event: 消息事件对象
        """
        try:
            from pathlib import Path
            import datetime
            
            # 生成备份文件名（使用插件数据目录）
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_dir = self.data_dir / "backups"
            backup_dir.mkdir(parents=True, exist_ok=True)
            backup_path = backup_dir / f"texas_holdem_backup_{timestamp}.db"
            
            # 先保存所有数据
            await self.player_manager.save_all_players()
            
            # 执行备份
            success = await self.database_manager.backup_database(backup_path)
            
            if success:
                yield event.plain_result(f"✅ 数据库备份完成\n📁 文件: {backup_path}")
            else:
                yield event.plain_result("❌ 数据库备份失败")
                
        except Exception as e:
            logger.error(f"数据库备份失败: {e}")
            yield event.plain_result(f"❌ 备份操作失败: {str(e)}")

    @filter.command("poker_admin_config")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def admin_config(self, event: AstrMessageEvent) -> AsyncGenerator:
        """
        查看系统配置
        
        Args:
            event: 消息事件对象
        """
        try:
            lines = []
            lines.append("⚙️ 系统配置")
            lines.append("=" * 30)
            
            lines.append("💰 筹码设置:")
            lines.append(f"  初始筹码: {self.plugin_config['initial_chips']}")
            lines.append(f"  每日奖励: {self.plugin_config['daily_bonus']}")
            lines.append("")
            
            lines.append("🎲 游戏设置:")
            lines.append(f"  盲注级别: {self.plugin_config['blind_levels']}")
            lines.append(f"  操作超时: {self.plugin_config['timeout_seconds']}秒")
            lines.append(f"  最小玩家: {self.plugin_config['min_players']}人")
            lines.append(f"  最大玩家: {self.plugin_config['max_players']}人")
            lines.append("")
            
            lines.append("🏠 房间设置:")
            lines.append(f"  最大房间数: {self.plugin_config['max_rooms']}")
            lines.append(f"  当前房间数: {len(self.room_manager.rooms)}")
            
            yield event.plain_result("\n".join(lines))
            
        except Exception as e:
            logger.error(f"查看配置失败: {e}")
            yield event.plain_result(f"❌ 查看配置失败: {str(e)}")

    @filter.command("poker_admin_banned")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def admin_banned_list(self, event: AstrMessageEvent, page: int = 1) -> AsyncGenerator:
        """查看封禁玩家列表（委托给handler处理）"""
        if self.admin_handler:
            async for result in self.admin_handler.handle_admin_banned_list(event, page):
                yield result
        else:
            yield event.plain_result("❌ 管理员处理器未初始化")

    @filter.command("poker_leaderboard")
    async def leaderboard(self, event: AstrMessageEvent, page: int = 1) -> AsyncGenerator:
        """查看排行榜（委托给handler处理）"""
        if self.game_handler:
            async for result in self.game_handler.handle_leaderboard(event, page):
                yield result
        else:
            yield event.plain_result("❌ 游戏处理器未初始化")

    async def _send_private_message(self, event: AstrMessageEvent, user_id: str, message: str) -> bool:
        """
        发送私聊消息的抽象方法
        
        Args:
            event: 消息事件对象
            user_id: 目标用户ID
            message: 消息内容
            
        Returns:
            bool: 是否发送成功
        """
        try:
            platform_name = event.get_platform_name()
            
            # 使用平台适配器模式来处理不同平台
            platform_handlers = {
                "aiocqhttp": self._send_private_message_aiocqhttp,
                # 这里可以轻松添加其他平台支持
                # "telegram": self._send_private_message_telegram,
                # "discord": self._send_private_message_discord,
            }
            
            handler = platform_handlers.get(platform_name)
            if handler:
                return await handler(event, user_id, message)
            else:
                logger.warning(f"平台 {platform_name} 暂不支持私聊发送")
                return False
                
        except Exception as e:
            logger.error(f"私聊发送失败: {e}")
            return False
    
    async def _send_private_message_aiocqhttp(self, event: AstrMessageEvent, user_id: str, message: str) -> bool:
        """
        在 aiocqhttp 平台发送私聊消息
        
        Args:
            event: 消息事件对象
            user_id: 目标用户ID
            message: 消息内容
            
        Returns:
            bool: 是否发送成功
        """
        try:
            # 使用动态导入来避免硬编码依赖
            try:
                from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
                
                if isinstance(event, AiocqhttpMessageEvent):
                    client = event.bot
                    await client.api.call_action('send_private_msg', 
                                                user_id=user_id, 
                                                message=message)
                    logger.info(f"成功发送私聊消息给用户 {user_id}")
                    return True
                else:
                    logger.warning("事件类型不匹配")
                    return False
                    
            except ImportError as import_error:
                logger.warning(f"aiocqhttp模块导入失败: {import_error}")
                return False
                
        except Exception as e:
            logger.error(f"aiocqhttp私聊发送失败: {e}")
            return False
    
    
    async def _send_private_cards(self, event: AstrMessageEvent, user_id: str, game):
        """
        私聊发送手牌信息给玩家
        
        Args:
            event: 消息事件对象
            user_id: 玩家ID
            game: 游戏实例
        """
        try:
            # 获取玩家手牌
            player_cards = game.get_player_cards(user_id)
            if not player_cards:
                logger.warning(f"玩家 {user_id} 没有手牌")
                return
                
            # 简化手牌显示：只显示房间号和手牌信息
            room_id = game.room_id
            cards_text = f"🏠 房间 {room_id}\n🎴 您的手牌: {' '.join(player_cards)}"
            
            # 使用抽象的私聊发送方法
            success = await self._send_private_message(event, user_id, cards_text)
            if not success:
                # 如果私聊发送失败，记录日志但不抛出异常
                logger.warning(f"向玩家 {user_id} 发送手牌失败，可能是平台不支持或用户设置问题")
                
        except Exception as e:
            logger.error(f"私聊发送手牌失败: {e}")
            # 重新抛出异常，以便上层调用可以处理
            raise

    async def _handle_game_end(self, room):
        """
        处理游戏结束（重构版本：分解为多个小方法）
        
        Args:
            room: 房间对象
        """
        try:
            if not (room.game and room.game.is_game_over()):
                return
            
            # 获取游戏结果
            results = room.game.get_game_results()
            
            # 更新玩家统计数据
            await self._update_player_stats_on_game_end(results)
            
            # 构建并发送结果消息
            result_text = await self._build_game_end_message(room, results)
            
            # 持久化游戏数据
            await self._persist_game_results(room, results)
            
            # 记录到日志
            logger.info(f"房间 {room.room_id} 游戏结束结果:\n{result_text}")
            
            # 重置房间状态
            await self._auto_cleanup_room(room)
                
        except Exception as e:
            logger.error(f"游戏结束处理失败: {e}")
            # 强制重置房间，避免卡死
            await self._auto_cleanup_room(room)
    
    async def _update_player_stats_on_game_end(self, results: dict):
        """
        游戏结束时更新玩家统计数据
        
        Args:
            results: 游戏结果字典
        """
        for player_id, result in results.items():
            try:
                profit = result.get('profit', 0)
                won = result.get('won', False)
                hand_evaluation = result.get('hand_evaluation')
                
                # 只更新玩家统计，不更新筹码（游戏引擎已经正确分配了筹码）
                await self.player_manager.update_game_result(
                    player_id, profit, won, hand_evaluation
                )
                
                # 获取玩家当前筹码（包括成就奖励等）
                player = await self.player_manager.get_or_create_player(player_id)
                
                # 更新结果中的最终筹码为实际筹码（包括成就奖励）
                results[player_id]['final_chips'] = player.chips
                
            except Exception as e:
                logger.error(f"更新玩家 {player_id} 统计数据失败: {e}")
    
    async def _build_game_end_message(self, room, results: dict) -> str:
        """
        构建游戏结束消息
        
        Args:
            room: 房间对象
            results: 游戏结果字典
            
        Returns:
            str: 格式化的游戏结束消息
        """
        try:
            result_text = "🎉 游戏结束！\n\n"
            result_text += "🏆 游戏结果:\n"
            
            # 按盈利排序显示结果
            sorted_results = sorted(results.items(), key=lambda x: x[1].get('profit', 0), reverse=True)
            
            for player_id, result in sorted_results:
                profit = result.get('profit', 0)
                won = result.get('won', False)
                hand_cards = result.get('hand_cards', [])
                hand_evaluation = result.get('hand_evaluation')
                
                # 结果图标
                icon = "🏆" if won else "💸"
                profit_str = f"+{profit}" if profit > 0 else str(profit)
                
                # 显示玩家结果和手牌
                player_name = player_id[:8]
                result_line = f"{icon} {player_name}: {profit_str} 筹码"
                
                # 添加手牌信息
                if hand_cards:
                    cards_str = " ".join(hand_cards)
                    result_line += f"\n   🎴 手牌: {cards_str}"
                    
                    # 如果有手牌评估，显示牌型
                    if hand_evaluation and won:
                        hand_rank = hand_evaluation.hand_rank.name_cn
                        result_line += f" ({hand_rank})"
                
                result_text += result_line + "\n"
            
            # 显示公共牌
            community_cards = room.game.get_community_cards()
            if community_cards:
                result_text += f"\n🎴 公共牌: {' '.join(community_cards)}\n"
            
            return result_text
            
        except Exception as e:
            logger.error(f"构建游戏结束消息失败: {e}")
            return "🎉 游戏结束！（消息构建失败）"
    
    async def _persist_game_results(self, room, results: dict):
        """
        持久化游戏结果数据
        
        Args:
            room: 房间对象
            results: 游戏结果字典
        """
        # 保存玩家数据
        await self._save_player_data_on_game_end()
        
        # 保存游戏记录
        await self._save_game_record(room, results)
    
    async def _save_player_data_on_game_end(self):
        """保存游戏结束时的玩家数据"""
        try:
            await self.player_manager.save_all_players()
            logger.info("玩家数据已强制保存到数据库")
        except Exception as e:
            logger.error(f"强制保存玩家数据失败: {e}")
    
    async def _save_game_record(self, room, results: dict):
        """
        保存游戏记录到数据库
        
        Args:
            room: 房间对象
            results: 游戏结果字典
        """
        try:
            winners = [pid for pid, result in results.items() if result.get('won', False)]
            winner_id = winners[0] if winners else None
            
            game_record = {
                'players': list(results.keys()),
                'winner_id': winner_id,
                'game_duration': 0,
                'final_pot': room.game.get_total_pot(),
                'hand_results': {
                    pid: {
                        'profit': result.get('profit', 0),
                        'won': result.get('won', False),
                        'hand_cards': result.get('hand_cards', []),
                        'hand_rank': result.get('hand_evaluation').hand_rank.name_cn if result.get('hand_evaluation') else None
                    }
                    for pid, result in results.items()
                }
            }
            
            await self.database_manager.save_game_record(room.room_id, game_record)
            logger.info(f"游戏记录已保存到数据库: 房间 {room.room_id}")
            
        except Exception as e:
            logger.error(f"保存游戏记录失败: {e}")

    async def _auto_cleanup_room(self, room):
        """
        游戏结束后重置房间状态，保留玩家列表以便继续下一局
        
        Args:
            room: 游戏房间对象
        """
        try:
            logger.info(f"开始重置房间 {room.room_id} 状态")
            
            # 批量获取所有玩家信息，避免 N+1 查询
            all_players = await self.player_manager.get_players_by_ids(list(room.player_ids))
            
            # 构建玩家ID到玩家对象的映射
            player_map = {p.player_id: p for p in all_players}
            
            # 检查玩家筹码，移除筹码不足的玩家
            players_to_remove = []
            remaining_players = []
            
            for player_id in list(room.player_ids):
                player = player_map.get(player_id)
                if not player:
                    players_to_remove.append(player_id)
                    logger.warning(f"玩家 {player_id} 数据不存在，移出房间")
                    continue
                
                # 如果玩家筹码不足最小买入要求，则移除
                if player.chips < room.min_buy_in:
                    players_to_remove.append(player_id)
                    logger.info(f"玩家 {player_id} 筹码不足，移出房间")
                else:
                    remaining_players.append(player_id)
            
            # 移除筹码不足的玩家
            for player_id in players_to_remove:
                room.player_ids.discard(player_id)
                self.room_manager.player_room_mapping.pop(player_id, None)
            
            # 更新房间状态
            room.current_players = len(remaining_players)
            
            # 如果还有足够玩家，将房间设置为等待状态；否则设置为完成状态
            if room.current_players >= 2:
                room.status = RoomStatus.WAITING
                room.game = None  # 重置游戏实例，准备新游戏
                logger.info(f"房间 {room.room_id} 已重置为等待状态，剩余玩家: {room.current_players}")
            else:
                room.status = RoomStatus.FINISHED
                room.game = None
                
                # 如果房间内玩家不足，清空剩余玩家
                for player_id in remaining_players:
                    room.player_ids.discard(player_id)
                    self.room_manager.player_room_mapping.pop(player_id, None)
                room.current_players = 0
                
                logger.info(f"房间 {room.room_id} 玩家不足，设置为完成状态")
            
        except Exception as e:
            logger.error(f"重置房间状态失败: {e}")

    async def _get_player_display_name(self, player_id: str) -> str:
        """
        获取玩家显示名称
        
        Args:
            player_id: 玩家ID
            
        Returns:
            str: 玩家显示名称
        """
        try:
            player = await self.player_manager.get_or_create_player(player_id)
            return player.display_name or player_id[:12]
        except:
            return player_id[:12]

    async def terminate(self):
        """
        插件卸载时的清理工作
        
        保存所有数据，关闭数据库连接
        """
        try:
            await self.player_manager.cleanup()
            await self.room_manager.close_all_rooms()
            await self.database_manager.close()
            logger.info("德州扑克插件已安全卸载")
        except Exception as e:
            logger.error(f"插件卸载失败: {e}")
