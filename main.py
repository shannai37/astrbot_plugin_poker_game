from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
import astrbot.api.message_components as Comp
from astrbot.core.utils.session_waiter import session_waiter, SessionController

import asyncio
import json
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum
import random
import time
from pathlib import Path

# 导入自定义模块
from .models.card_system import Card, CardSystem, HandRank
from .models.game_engine import TexasHoldemGame, GamePhase, PlayerAction
from .models.player_manager import PlayerManager, PlayerInfo
from .models.room_manager import RoomManager, GameRoom, RoomStatus
from .utils.data_persistence import DatabaseManager
from .utils.ui_builder import GameUIBuilder


@register("texas_holdem", "山萘", "德州扑克游戏插件 - 支持多人游戏、积分系统、房间管理", "1.0.0")
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
        self.data_dir = self.get_data_dir()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # 初始化核心组件
        self.database_manager = DatabaseManager(self.data_dir / "game_data.db")
        self.player_manager = PlayerManager(self.database_manager)
        self.room_manager = RoomManager(self.database_manager, self.player_manager)
        self.ui_builder = GameUIBuilder()
        
        # 插件配置（硬编码默认值）
        self.plugin_config = {
            "initial_chips": 10000,  # 与PlayerInfo默认值保持一致
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
        初始化命令处理器（新架构预览）
        
        注意：这是为了演示新架构而添加的，当前仍使用原有的命令处理方式。
        未来可以逐步迁移命令到这些处理器中，实现职责分离。
        """
        try:
            from .handlers.game_handler import GameCommandHandler
            from .handlers.admin_handler import AdminCommandHandler
            
            # 创建处理器实例
            self.game_handler = GameCommandHandler(self)
            self.admin_handler = AdminCommandHandler(self)
            
            # 获取命令映射（供未来使用）
            self.game_commands = self.game_handler.get_command_handlers()
            self.admin_commands = self.admin_handler.get_command_handlers()
            
            logger.info("命令处理器初始化完成")
            
        except ImportError as e:
            logger.warning(f"命令处理器导入失败: {e}")
        except Exception as e:
            logger.error(f"命令处理器初始化失败: {e}")

    async def initialize_plugin(self):
        """
        初始化插件数据库和配置
        
        创建必要的数据表，加载历史数据
        """
        try:
            await self.database_manager.initialize()
            await self.player_manager.load_players()
            # 启动自动保存任务
            self.player_manager.start_auto_save()
            await self.room_manager.load_rooms()
            logger.info("德州扑克插件数据初始化完成")
        except Exception as e:
            logger.error(f"插件初始化失败: {e}")
            raise

    @filter.on_astrbot_loaded()
    async def on_loaded(self):
        """AstrBot启动完成时初始化插件"""
        await self.initialize_plugin()

    # ==================== 玩家游戏指令 ====================
    
    @filter.command("poker")
    async def poker_main(self, event: AstrMessageEvent):
        """
        德州扑克主命令入口
        
        Args:
            event: 消息事件对象
        """
        help_text = """🎰 德州扑克游戏

🎮 基础指令：
• /poker_help - 查看完整帮助
• /poker_status - 查看个人状态
• /poker_game_status - 查看当前游戏状态
• /poker_achievements - 查看成就
• /poker_equip [成就ID] - 装备成就
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
    async def poker_help(self, event: AstrMessageEvent):
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
• /poker_achievements - 查看成就
• /poker_equip [成就ID] - 装备成就

📊 统计查询：
• /poker_stats - 查看详细统计

🏠 房间管理：
• /poker_rooms - 查看所有房间
• /poker_create [盲注级别] - 创建房间
• /poker_start - 开始游戏（需至少2人）

🎯 游戏中操作：
• /poker_call - 跟注
• /poker_raise [金额] - 加注
• /poker_fold - 弃牌
• /poker_check - 过牌
• /poker_allin - 全押

👑 管理员指令：
• /poker_admin - 管理面板
• /poker_admin_players - 查看玩家列表
• /poker_admin_ban - 封禁玩家
• /poker_admin_unban - 解封玩家

💰 初始积分: {initial_chips} 筹码
⏰ 操作超时: {timeout} 秒""".format(
            initial_chips=self.plugin_config["initial_chips"],
            timeout=self.plugin_config["timeout_seconds"]
        )
        
        yield event.plain_result(help_text)

    @filter.command("poker_debug")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def debug_game_state(self, event: AstrMessageEvent):
        """
        深度调试游戏状态
        
        Args:
            event: 消息事件对象
        """
        user_id = event.get_sender_id()
        
        try:
            room = await self.room_manager.get_player_room(user_id)
            if not room or not room.game:
                yield event.plain_result("❌ 您当前不在任何游戏中")
                return
            
            game = room.game
            
            # 收集详细的调试信息
            debug_info = f"""🐛 游戏调试信息

🎮 基本状态:
• 房间ID: {room.room_id}
• 游戏阶段: {game.game_phase.value}
• 当前轮次: {game.hand_number}
• 当前最高下注: {game.current_bet}
• 总底池: {game.main_pot}

👤 当前玩家:
• 当前行动玩家ID: {game.current_player_id}
• 当前玩家索引: {game.current_player_index}
• 最后加注玩家: {game.last_raise_player_id}

👥 玩家列表:
• 玩家顺序: {game.player_order}
• 活跃玩家: {game.active_players}

📊 详细玩家状态:"""
            
            for i, player_id in enumerate(game.player_order):
                player = game.players[player_id]
                is_current = "👈 当前" if player_id == game.current_player_id else ""
                is_active = "✅" if player_id in game.active_players else "❌"
                
                debug_info += f"""
{i}: {player_id[:8]} {is_current}
   状态: {player.status.value} {is_active}
   筹码: {player.chips} | 当前下注: {player.current_bet} | 总下注: {player.total_bet}
   最后操作: {player.last_action.value if player.last_action else 'None'}
   可行动: {player.can_act()} | 在牌局: {player.is_in_hand()}
   位置: {'庄家' if player.is_dealer else ''}{'小盲' if player.is_small_blind else ''}{'大盲' if player.is_big_blind else ''}"""
            
            debug_info += f"""

🔄 轮转逻辑检查:
• 下注轮次完成: {game._is_betting_round_complete()}
• 在牌局玩家数: {len([p for p in game.players.values() if p.is_in_hand()])}
• 可行动玩家数: {len([p for p in game.players.values() if p.can_act()])}
• 最高下注: {max(p.current_bet for p in game.players.values() if p.is_in_hand()) if game.players else 0}

🎴 公共牌: {' '.join([str(card) for card in game.community_cards]) if game.community_cards else '无'}"""
            
            yield event.plain_result(debug_info)
            
        except Exception as e:
            logger.error(f"调试失败: {e}")
            yield event.plain_result(f"❌ 调试失败: {str(e)}")

    @filter.command("poker_fix_turn")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def fix_turn_order(self, event: AstrMessageEvent):
        """
        强制修复玩家轮转顺序
        
        Args:
            event: 消息事件对象
        """
        user_id = event.get_sender_id()
        
        try:
            room = await self.room_manager.get_player_room(user_id)
            if not room or not room.game:
                yield event.plain_result("❌ 您当前不在任何游戏中")
                return
            
            game = room.game
            
            # 记录修复前状态
            old_current = game.current_player_id
            old_active = game.active_players.copy()
            
            # 强制重新计算活跃玩家和当前玩家
            game.active_players = [
                pid for pid in game.player_order 
                if game.players[pid].is_in_hand() and game.players[pid].can_act()
            ]
            
            if game.active_players:
                # 如果当前玩家仍在活跃列表中，保持不变
                if game.current_player_id in game.active_players:
                    game.current_player_index = game.active_players.index(game.current_player_id)
                else:
                    # 否则设置为第一个活跃玩家
                    game.current_player_index = 0
                    game.current_player_id = game.active_players[0]
                
                result_msg = f"""🔧 轮转修复完成
                
修复前:
• 当前玩家: {old_current}
• 活跃玩家: {', '.join([pid[:8] for pid in old_active])}

修复后:
• 当前玩家: {game.current_player_id}
• 活跃玩家: {', '.join([pid[:8] for pid in game.active_players])}
• 当前索引: {game.current_player_index}/{len(game.active_players)}

💡 请使用 /poker_debug 查看详细状态"""
                
                yield event.plain_result(result_msg)
            else:
                yield event.plain_result("❌ 没有活跃玩家，游戏可能已结束")
                
        except Exception as e:
            logger.error(f"修复轮转失败: {e}")
            yield event.plain_result(f"❌ 修复轮转失败: {str(e)}")

    @filter.command("poker_exit")
    async def emergency_exit(self, event: AstrMessageEvent):
        """
        退出游戏并返回筹码
        
        Args:
            event: 消息事件对象
        """
        user_id = event.get_sender_id()
        
        try:
            room = await self.room_manager.get_player_room(user_id)
            if not room or not room.game:
                yield event.plain_result("❌ 您当前不在任何游戏中")
                return
            
            game = room.game
            
            # 计算每个玩家应该返回的筹码
            total_refunded = 0
            for player_id, player in game.players.items():
                refund_amount = player.total_bet
                if refund_amount > 0:
                    player.chips += refund_amount
                    total_refunded += refund_amount
                    await self.player_manager.update_player_chips(player_id, player.chips)
            
            # 清空底池并结束游戏
            game.main_pot = 0
            game.side_pots.clear()
            from .models.game_engine import GamePhase
            game.game_phase = GamePhase.GAME_OVER
            
            yield event.plain_result(f"✅ 游戏已退出，返回筹码 {total_refunded}")
            
            # 清理房间
            await self._auto_cleanup_room(room)
            
        except Exception as e:
            logger.error(f"退出游戏失败: {e}")
            yield event.plain_result(f"❌ 退出失败: {str(e)}")

    @filter.command("poker_game_status")
    async def game_status(self, event: AstrMessageEvent):
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
            
🏠 房间ID: {room.room_id}
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
    async def join_room(self, event: AstrMessageEvent, room_id: str = ""):
        """
        加入指定房间或快速匹配
        
        Args:
            event: 消息事件对象
            room_id: 房间ID，为空时快速匹配
        """
        user_id = event.get_sender_id()
        
        try:
            # 确保玩家已注册
            player = await self.player_manager.get_or_create_player(user_id)
            
            # 检查玩家是否被封禁
            if player.is_banned:
                if player.ban_until > 0:
                    # 临时封禁，显示剩余时间
                    remaining_time = player.ban_until - time.time()
                    if remaining_time > 0:
                        remaining_hours = remaining_time / 3600
                        yield event.plain_result(f"❌ 您已被封禁，剩余时间: {remaining_hours:.1f}小时\n原因: {player.ban_reason}")
                        return
                else:
                    # 永久封禁
                    yield event.plain_result(f"❌ 您已被永久封禁\n原因: {player.ban_reason}")
                    return
            
            # 检查玩家是否已在游戏中
            current_room = await self.room_manager.get_player_room(user_id)
            if current_room:
                yield event.plain_result(f"❌ 您已在房间 {current_room.room_id} 中，请先离开当前游戏")
                return
            
            # 检查积分是否足够
            if player.chips <= 0:
                yield event.plain_result("❌ 积分不足，无法加入游戏。请联系管理员充值。")
                return
            
            if room_id:
                # 加入指定房间
                room = await self.room_manager.get_room(room_id)
                if not room:
                    yield event.plain_result(f"❌ 房间 {room_id} 不存在")
                    return
                    
                result = await self.room_manager.join_room(room_id, user_id)
                if result:
                    yield event.plain_result(f"✅ 成功加入房间 {room_id}")
                    # 发送房间状态
                    room_status = self.ui_builder.build_room_status(room)
                    yield event.plain_result(room_status)
                else:
                    yield event.plain_result("❌ 加入房间失败，房间可能已满或游戏进行中")
            else:
                # 快速匹配
                room = await self.room_manager.quick_match(user_id)
                if room:
                    yield event.plain_result(f"✅ 已匹配到房间 {room.room_id}")
                    room_status = self.ui_builder.build_room_status(room)
                    yield event.plain_result(room_status)
                else:
                    yield event.plain_result("❌ 暂无可用房间，请稍后重试或创建新房间")
                    
        except Exception as e:
            logger.error(f"加入房间失败: {e}")
            yield event.plain_result(f"❌ 加入房间失败: {str(e)}")

    @filter.command("poker_leave")
    async def leave_room(self, event: AstrMessageEvent):
        """
        离开当前房间 - 优化版本，快速响应
        
        Args:
            event: 消息事件对象
        """
        user_id = event.get_sender_id()
        
        try:
            # 快速检查玩家是否在房间中
            current_room = await self.room_manager.get_player_room(user_id)
            if not current_room:
                yield event.plain_result("❌ 您当前不在任何游戏中")
                return
            
            # 立即清除玩家映射，避免重复请求
            room_id = current_room.room_id
            self.room_manager.player_room_mapping.pop(user_id, None)
            
            # 立即回复用户
            yield event.plain_result("✅ 正在离开游戏...")
            
            # 异步处理复杂的离开逻辑
            try:
                result = await self.room_manager.leave_room(room_id, user_id)
                if result:
                    yield event.plain_result("✅ 已成功离开游戏")
                else:
                    # 如果失败，恢复映射
                    self.room_manager.player_room_mapping[user_id] = room_id
                    yield event.plain_result("❌ 离开游戏失败，请重试")
            except Exception as leave_error:
                # 如果出错，恢复映射
                self.room_manager.player_room_mapping[user_id] = room_id
                logger.error(f"离开房间处理失败: {leave_error}")
                yield event.plain_result("❌ 离开游戏时出现错误，请重试")
                
        except Exception as e:
            logger.error(f"离开房间失败: {e}")
            yield event.plain_result(f"❌ 离开房间失败: {str(e)}")

    @filter.command("poker_achievements")
    async def achievements_view(self, event: AstrMessageEvent):
        """
        查看成就进度
        
        Args:
            event: 消息事件
        """
        user_id = event.get_sender_id()
        
        try:
            # 获取成就进度数据
            progress_data = await self.player_manager.get_achievement_progress(user_id)
            
            if not progress_data:
                yield event.plain_result("❌ 无法获取成就数据")
                return
            
            # 构建成就显示
            player_name = await self._get_player_display_name(user_id)
            result_text = self.ui_builder.build_achievements_list(progress_data, player_name)
            
            yield event.plain_result(result_text)
            
        except Exception as e:
            logger.error(f"查看成就失败: {e}")
            yield event.plain_result(f"❌ 查看成就失败: {str(e)}")
    
    @filter.command("poker_equip")
    async def equip_achievement(self, event: AstrMessageEvent):
        """
        装备成就
        
        Args:
            event: 消息事件
        """
        user_id = event.get_sender_id()
        args = event.get_message_plain_text().split()[1:]
        
        if not args:
            yield event.plain_result("❌ 请指定要装备的成就ID\n💡 使用 /poker_achievements 查看可装备的成就")
            return
        
        achievement_id = args[0]
        
        try:
            success, message = await self.player_manager.equip_achievement(user_id, achievement_id)
            
            if success:
                yield event.plain_result(f"✅ {message}")
            else:
                yield event.plain_result(f"❌ {message}")
                
        except Exception as e:
            logger.error(f"装备成就失败: {e}")
            yield event.plain_result(f"❌ 装备成就失败: {str(e)}")

    @filter.command("poker_status")
    async def player_status(self, event: AstrMessageEvent):
        """
        查看玩家个人状态
        
        Args:
            event: 消息事件对象
        """
        user_id = event.get_sender_id()
        
        try:
            player = await self.player_manager.get_or_create_player(user_id)
            current_room = await self.room_manager.get_player_room(user_id)
            
            status_text = f"""👤 玩家状态

💰 当前积分: {player.chips}
🎯 等级: {player.level}
📊 总局数: {player.total_games}
🏆 胜率: {player.win_rate:.1f}%
💹 总盈亏: {player.total_profit:+d}

🎮 游戏状态: {'游戏中' if current_room else '空闲'}"""

            if current_room:
                status_text += f"\n🏠 当前房间: {current_room.room_id}"
                
            yield event.plain_result(status_text)
            
        except Exception as e:
            logger.error(f"查看状态失败: {e}")
            yield event.plain_result(f"❌ 查看状态失败: {str(e)}")

    @filter.command("poker_stats")
    async def player_stats(self, event: AstrMessageEvent):
        """
        查看玩家详细统计
        
        Args:
            event: 消息事件对象
        """
        user_id = event.get_sender_id()
        
        try:
            stats = await self.player_manager.get_player_stats(user_id)
            if not stats:
                yield event.plain_result("❌ 暂无统计数据")
                return
                
            stats_text = self.ui_builder.build_player_stats(stats)
            yield event.plain_result(stats_text)
            
        except Exception as e:
            logger.error(f"查看统计失败: {e}")
            yield event.plain_result(f"❌ 查看统计失败: {str(e)}")

    @filter.command("poker_rooms")
    async def list_rooms(self, event: AstrMessageEvent):
        """
        查看所有可用房间
        
        Args:
            event: 消息事件对象
        """
        try:
            rooms = await self.room_manager.get_available_rooms()
            if not rooms:
                yield event.plain_result("🏠 当前没有可用房间\n\n使用 /poker create 创建新房间")
                return
                
            rooms_text = self.ui_builder.build_rooms_list(rooms)
            yield event.plain_result(rooms_text)
            
        except Exception as e:
            logger.error(f"查看房间列表失败: {e}")
            yield event.plain_result(f"❌ 查看房间列表失败: {str(e)}")

    @filter.command("poker_create")
    async def create_room(self, event: AstrMessageEvent, blind_level: int = 1):
        """
        创建新房间
        
        Args:
            event: 消息事件对象
            blind_level: 盲注级别索引
        """
        user_id = event.get_sender_id()
        
        try:
            # 检查玩家是否被封禁
            player = await self.player_manager.get_or_create_player(user_id)
            if player.is_banned:
                if player.ban_until > 0:
                    # 临时封禁，显示剩余时间
                    remaining_time = player.ban_until - time.time()
                    if remaining_time > 0:
                        remaining_hours = remaining_time / 3600
                        yield event.plain_result(f"❌ 您已被封禁，剩余时间: {remaining_hours:.1f}小时\n原因: {player.ban_reason}")
                        return
                else:
                    # 永久封禁
                    yield event.plain_result(f"❌ 您已被永久封禁\n原因: {player.ban_reason}")
                    return
            
            # 验证盲注级别
            if blind_level < 1 or blind_level > len(self.plugin_config["blind_levels"]):
                yield event.plain_result(f"❌ 盲注级别错误，请选择 1-{len(self.plugin_config['blind_levels'])}")
                return
            
            # 检查玩家是否已在游戏中
            current_room = await self.room_manager.get_player_room(user_id)
            if current_room:
                yield event.plain_result("❌ 您已在游戏中，请先离开当前游戏")
                return
            
            # 创建房间
            blind_amount = self.plugin_config["blind_levels"][blind_level - 1]
            room = await self.room_manager.create_room(
                creator_id=user_id,
                small_blind=blind_amount,
                big_blind=blind_amount * 2,
                max_players=self.plugin_config["max_players"]
            )
            
            if room:
                yield event.plain_result(f"✅ 房间创建成功！房间号: {room.room_id}")
                # 显示房间状态（创建者已自动加入）
                room_status = self.ui_builder.build_room_status(room)
                yield event.plain_result(room_status)
            else:
                yield event.plain_result("❌ 房间创建失败")
                
        except Exception as e:
            logger.error(f"创建房间失败: {e}")
            yield event.plain_result(f"❌ 创建房间失败: {str(e)}")

    @filter.command("poker_start")
    async def start_game(self, event: AstrMessageEvent):
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
                    room.game.add_player(player_id, buy_in)
            
            # 开始新一局
            if room.game.start_new_hand():
                yield event.plain_result("🎉 游戏开始！")
                
                # 发送游戏状态
                game_status = self.ui_builder.build_game_status(room.game)
                yield event.plain_result(game_status)
                
                # 给每个玩家发送私聊手牌
                for player_id in room.player_ids:
                    if player_id in room.game.players:
                        try:
                            await self._send_private_cards(event, player_id, room.game)
                        except Exception as e:
                            logger.error(f"发送手牌给玩家 {player_id} 失败: {e}")
                            # 私聊失败时，不在公共频道显示手牌，只提示发送失败
                            yield event.plain_result(f"⚠️ 无法向玩家 {player_id[:8]} 发送手牌，请检查好友关系或私聊设置。")
            else:
                yield event.plain_result("❌ 游戏开始失败，请检查游戏状态")
                
        except Exception as e:
            logger.error(f"开始游戏失败: {e}")
            yield event.plain_result(f"❌ 开始游戏失败: {str(e)}")

    # ==================== 游戏中操作 ====================
    
    @filter.command("poker_call")
    async def game_call(self, event: AstrMessageEvent):
        """
        跟注操作
        
        Args:
            event: 消息事件对象
        """
        user_id = event.get_sender_id()
        
        try:
            # 获取玩家所在房间
            room = await self.room_manager.get_player_room(user_id)
            if not room or not room.game:
                yield event.plain_result("❌ 您当前不在任何游戏中")
                return
            
            # 检查是否轮到该玩家
            current_player = room.game.current_player_id
            if current_player != user_id:
                # 获取详细的游戏状态用于诊断
                game_state = room.game.get_game_state()
                active_players = [pid for pid in room.game.player_order if room.game.players[pid].can_act()]
                in_hand_players = [pid for pid in room.game.player_order if room.game.players[pid].is_in_hand()]
                
                debug_info = f"""❌ 还没轮到您行动
👤 当前行动玩家: {current_player}
🎯 您的ID: {user_id}
👥 活跃玩家列表: {', '.join([pid[:8] for pid in active_players])}
🃏 在牌局中: {', '.join([pid[:8] for pid in in_hand_players])}
🎮 游戏阶段: {game_state.get('phase', 'unknown')}
🔄 玩家顺序: {', '.join([pid[:8] for pid in room.game.player_order])}

💡 请等待轮到您时再进行操作

🐛 调试信息:
• 您在活跃列表中: {user_id in active_players}
• 您在牌局中: {user_id in in_hand_players}
• 您的状态: {game_state.get('players', {}).get(user_id, {}).get('status', 'unknown')}"""
                
                yield event.plain_result(debug_info)
                return
            
            # 执行跟注操作
            if await room.game.handle_player_action(user_id, PlayerAction.CALL):
                yield event.plain_result("✅ 跟注成功")
                
                # 发送游戏状态更新（群消息）
                game_status = self.ui_builder.build_game_status(room.game)
                yield event.plain_result(game_status)
                
                # 检查游戏是否结束
                if room.game.is_game_over():
                    await self._handle_game_end(room)
            else:
                # 获取详细的游戏状态用于诊断
                game_state = room.game.get_game_state()
                player_info = game_state['players'].get(user_id, {})
                
                current_bet = game_state.get('current_bet', 0)
                player_current_bet = player_info.get('current_bet', 0)
                player_chips = player_info.get('chips', 0)
                call_amount = current_bet - player_current_bet
                
                debug_info = f"""❌ 无法跟注，游戏状态诊断：
💰 当前最高下注: {current_bet}
🎯 您的当前下注: {player_current_bet}
💳 您的筹码: {player_chips}
💵 需要跟注金额: {call_amount}

💡 跟注条件：需要跟注金额 > 0 且您有足够筹码"""
                
                yield event.plain_result(debug_info)
                
        except Exception as e:
            logger.error(f"跟注操作失败: {e}")
            yield event.plain_result(f"❌ 跟注失败: {str(e)}")

    @filter.command("poker_raise")
    async def game_raise(self, event: AstrMessageEvent, amount: int):
        """
        加注操作
        
        Args:
            event: 消息事件对象
            amount: 加注金额
        """
        user_id = event.get_sender_id()
        
        try:
            room = await self.room_manager.get_player_room(user_id)
            if not room or not room.game:
                yield event.plain_result("❌ 您当前不在任何游戏中")
                return
            
            # 检查是否轮到该玩家
            if room.game.current_player_id != user_id:
                yield event.plain_result(f"❌ 还没轮到您，当前行动玩家: {room.game.current_player_id}")
                return
            
            if await room.game.handle_player_action(user_id, PlayerAction.RAISE, amount):
                yield event.plain_result(f"✅ 加注 {amount} 成功")
                
                game_status = self.ui_builder.build_game_status(room.game)
                yield event.plain_result(game_status)
                
                if room.game.is_game_over():
                    await self._handle_game_end(room)
            else:
                # 获取详细的游戏状态用于诊断
                game_state = room.game.get_game_state()
                player_info = game_state['players'].get(user_id, {})
                
                current_bet = game_state.get('current_bet', 0)
                player_current_bet = player_info.get('current_bet', 0)
                player_chips = player_info.get('chips', 0)
                player_status = player_info.get('status', 'unknown')
                game_phase = game_state.get('phase', 'unknown')
                
                # 计算加注需要的金额
                call_amount = current_bet - player_current_bet
                total_needed = call_amount + amount
                min_raise = room.game.big_blind
                
                debug_info = f"""❌ 无法加注，游戏状态诊断：
🎮 游戏阶段: {game_phase}
💰 当前最高下注: {current_bet}
🎯 您的当前下注: {player_current_bet}
💳 您的筹码: {player_chips}
📊 玩家状态: {player_status}

💵 加注分析:
• 需要跟注金额: {call_amount}
• 您的加注金额: {amount}
• 总计需要金额: {total_needed}
• 最小加注要求: {min_raise}

💡 加注条件检查:
✓ 加注金额 > 0: {amount > 0}
✓ 总需要金额 <= 筹码: {total_needed} <= {player_chips} = {total_needed <= player_chips}
✓ 加注金额 >= 最小要求: {amount} >= {min_raise} = {amount >= min_raise}"""
                
                yield event.plain_result(debug_info)
                
        except Exception as e:
            logger.error(f"加注操作失败: {e}")
            yield event.plain_result(f"❌ 加注失败: {str(e)}")

    @filter.command("poker_fold")
    async def game_fold(self, event: AstrMessageEvent):
        """
        弃牌操作
        
        Args:
            event: 消息事件对象
        """
        user_id = event.get_sender_id()
        
        try:
            room = await self.room_manager.get_player_room(user_id)
            if not room or not room.game:
                yield event.plain_result("❌ 您当前不在任何游戏中")
                return
            
            # 检查是否轮到该玩家
            if room.game.current_player_id != user_id:
                yield event.plain_result(f"❌ 还没轮到您，当前行动玩家: {room.game.current_player_id}")
                return
            
            if await room.game.handle_player_action(user_id, PlayerAction.FOLD):
                yield event.plain_result("✅ 弃牌成功")
                
                game_status = self.ui_builder.build_game_status(room.game)
                yield event.plain_result(game_status)
                
                if room.game.is_game_over():
                    await self._handle_game_end(room)
            else:
                yield event.plain_result("❌ 无法弃牌，请检查游戏状态")
                
        except Exception as e:
            logger.error(f"弃牌操作失败: {e}")
            yield event.plain_result(f"❌ 弃牌失败: {str(e)}")

    @filter.command("poker_check")
    async def game_check(self, event: AstrMessageEvent):
        """
        过牌操作
        
        Args:
            event: 消息事件对象
        """
        user_id = event.get_sender_id()
        
        try:
            room = await self.room_manager.get_player_room(user_id)
            if not room or not room.game:
                yield event.plain_result("❌ 您当前不在任何游戏中")
                return
            
            # 检查是否轮到该玩家
            current_player = room.game.current_player_id
            if current_player != user_id:
                yield event.plain_result(f"❌ 还没轮到您，当前行动玩家: {current_player}")
                return
            
            # 获取详细的游戏状态用于诊断
            game_state = room.game.get_game_state()
            player_info = game_state['players'].get(user_id, {})
            
            # 检查过牌是否有效
            if await room.game.handle_player_action(user_id, PlayerAction.CHECK):
                yield event.plain_result("✅ 过牌成功")
                
                game_status = self.ui_builder.build_game_status(room.game)
                yield event.plain_result(game_status)
                
                if room.game.is_game_over():
                    await self._handle_game_end(room)
            else:
                # 提供详细的诊断信息
                current_bet = game_state.get('current_bet', 0)
                player_current_bet = player_info.get('current_bet', 0)
                player_chips = player_info.get('chips', 0)
                player_status = player_info.get('status', 'unknown')
                game_phase = game_state.get('phase', 'unknown')
                
                debug_info = f"""❌ 无法过牌，游戏状态诊断：
🎮 游戏阶段: {game_phase}
💰 当前最高下注: {current_bet}
🎯 您的当前下注: {player_current_bet}
💳 您的筹码: {player_chips}
📊 玩家状态: {player_status}
👤 当前行动玩家: {current_player}

💡 过牌条件：您的当前下注({player_current_bet}) 需要 >= 当前最高下注({current_bet})"""
                
                yield event.plain_result(debug_info)
                
        except Exception as e:
            logger.error(f"过牌操作失败: {e}")
            yield event.plain_result(f"❌ 过牌失败: {str(e)}")

    @filter.command("poker_allin")
    async def game_allin(self, event: AstrMessageEvent):
        """
        全押操作
        
        Args:
            event: 消息事件对象
        """
        user_id = event.get_sender_id()
        
        try:
            room = await self.room_manager.get_player_room(user_id)
            if not room or not room.game:
                yield event.plain_result("❌ 您当前不在任何游戏中")
                return
            
            # 检查是否轮到该玩家
            if room.game.current_player_id != user_id:
                yield event.plain_result(f"❌ 还没轮到您，当前行动玩家: {room.game.current_player_id}")
                return
            
            if await room.game.handle_player_action(user_id, PlayerAction.ALL_IN):
                yield event.plain_result("✅ 全押成功")
                
                game_status = self.ui_builder.build_game_status(room.game)
                yield event.plain_result(game_status)
                
                if room.game.is_game_over():
                    await self._handle_game_end(room)
            else:
                yield event.plain_result("❌ 无法全押，请检查游戏状态")
                
        except Exception as e:
            logger.error(f"全押操作失败: {e}")
            yield event.plain_result(f"❌ 全押失败: {str(e)}")


    # ==================== 辅助方法 ====================
    
    async def _validate_player_turn(self, event: AstrMessageEvent, user_id: str):
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
        解析玩家ID，支持部分ID匹配
        
        Args:
            partial_id: 部分或完整的玩家ID
            filter_condition: 可选的过滤条件函数
            
        Returns:
            Tuple[Optional[str], Optional[str]]: (解析的玩家ID, 错误信息)
        """
        # 如果是完整ID，直接返回
        if len(partial_id) >= 8:
            return partial_id, None
        
        # 部分ID匹配
        all_players = await self.player_manager.get_all_players()
        
        # 应用过滤条件
        if filter_condition:
            matches = [p for p in all_players if p.player_id.startswith(partial_id) and filter_condition(p)]
        else:
            matches = [p for p in all_players if p.player_id.startswith(partial_id)]
        
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
    async def admin_panel(self, event: AstrMessageEvent):
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
    async def admin_players(self, event: AstrMessageEvent, limit: int = 20):
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
    async def admin_ban_player(self, event: AstrMessageEvent, player_id: str, duration: int = 0, reason: str = "管理员操作"):
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
                    yield event.plain_result(f"🏠 已将玩家从房间 {room.room_id} 中移除")
            else:
                yield event.plain_result(f"❌ 封禁失败，玩家不存在: {player_id}")
                
        except Exception as e:
            logger.error(f"封禁玩家失败: {e}")
            yield event.plain_result(f"❌ 封禁操作失败: {str(e)}")

    @filter.command("poker_admin_unban")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def admin_unban_player(self, event: AstrMessageEvent, player_id: str):
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
    async def admin_add_chips(self, event: AstrMessageEvent, player_id: str, amount: int, reason: str = "管理员补充"):
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
    async def admin_reset_player(self, event: AstrMessageEvent, player_id: str, keep_chips: bool = False):
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
                    yield event.plain_result(f"🏠 已将玩家从房间 {room.room_id} 中移除")
            else:
                yield event.plain_result(f"❌ 重置失败，玩家不存在: {player_id}")
                
        except Exception as e:
            logger.error(f"重置玩家数据失败: {e}")
            yield event.plain_result(f"❌ 重置操作失败: {str(e)}")

    @filter.command("poker_admin_rooms")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def admin_rooms(self, event: AstrMessageEvent):
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
    async def admin_close_room(self, event: AstrMessageEvent, room_id: str, reason: str = "管理员关闭"):
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
    async def admin_kick_player(self, event: AstrMessageEvent, player_id: str, reason: str = "管理员操作"):
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
    async def admin_detailed_stats(self, event: AstrMessageEvent):
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
            lines.append(f"  📅 运行时间: {self.ui_builder.format_time(runtime_seconds)}")
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
    async def admin_backup(self, event: AstrMessageEvent):
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
            backup_dir = self.get_data_dir() / "backups"
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
    async def admin_config(self, event: AstrMessageEvent):
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
            
            if platform_name == "aiocqhttp":
                return await self._send_private_message_aiocqhttp(event, user_id, message)
            else:
                # 其他平台可以在这里添加支持
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
            from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
            
            if isinstance(event, AiocqhttpMessageEvent):
                client = event.bot
                await client.api.call_action('send_private_msg', 
                                            user_id=user_id, 
                                            message=message)
                logger.info(f"成功发送私聊消息给用户 {user_id}")
                return True
            else:
                logger.warning("事件类型不是AiocqhttpMessageEvent")
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
        处理游戏结束
        
        Args:
            room: 房间对象
        """
        try:
            if room.game and room.game.is_game_over():
                # 获取游戏结果
                results = room.game.get_game_results()
                
                # 更新每个玩家的统计数据
                for player_id, result in results.items():
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
                
                # 构建结果显示（包含手牌信息）
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
                
                # 强制保存所有玩家数据到数据库，确保统计准确
                try:
                    await self.player_manager.save_all_players()
                    logger.info("玩家数据已强制保存到数据库")
                except Exception as e:
                    logger.error(f"强制保存玩家数据失败: {e}")
                
                # 保存游戏记录到数据库
                try:
                    winners = [pid for pid, result in results.items() if result.get('won', False)]
                    winner_id = winners[0] if winners else None
                    
                    game_record = {
                        'players': list(results.keys()),
                        'winner_id': winner_id,
                        'game_duration': 0,  # TODO: 可以添加游戏时长统计
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
                
                # 记录到日志并等待群消息功能实现
                logger.info(f"房间 {room.room_id} 游戏结束结果:\n{result_text}")
                
                # 自动清理房间和玩家映射
                await self._auto_cleanup_room(room)
                
        except Exception as e:
            logger.error(f"处理游戏结束失败: {e}")

    async def _auto_cleanup_room(self, room):
        """
        游戏结束后重置房间状态，保留玩家列表以便继续下一局
        
        Args:
            room: 游戏房间对象
        """
        try:
            logger.info(f"开始重置房间 {room.room_id} 状态")
            
            # 检查玩家筹码，移除筹码不足的玩家
            players_to_remove = []
            remaining_players = []
            
            for player_id in list(room.player_ids):
                try:
                    player = await self.player_manager.get_or_create_player(player_id)
                    
                    # 如果玩家筹码不足最小买入要求，则移除
                    if player.chips < room.min_buy_in:
                        players_to_remove.append(player_id)
                        logger.info(f"玩家 {player_id} 筹码不足，移出房间")
                    else:
                        remaining_players.append(player_id)
                        
                except Exception as e:
                    logger.error(f"检查玩家 {player_id} 状态失败: {e}")
                    players_to_remove.append(player_id)
            
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
            await self.room_manager.close_all_rooms()
            await self.database_manager.close()
            logger.info("德州扑克插件已安全卸载")
        except Exception as e:
            logger.error(f"插件卸载失败: {e}")
