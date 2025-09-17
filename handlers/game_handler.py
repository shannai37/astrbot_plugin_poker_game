from typing import Dict, AsyncGenerator, Tuple, Optional
from astrbot.api.event import AstrMessageEvent
from astrbot.api import logger
import time
from .base_handler import BaseCommandHandler
from ..models.game_engine import PlayerAction, GamePhase


class GameCommandHandler(BaseCommandHandler):
    """
    游戏相关命令处理器
    
    负责处理：
    - 房间加入/离开
    - 游戏状态查询
    - 玩家操作（跟注、加注、弃牌等）
    - 统计和排行榜
    """
    
    def get_command_handlers(self) -> Dict[str, callable]:
        """
        获取游戏命令映射
        
        Returns:
            Dict[str, callable]: 命令名到处理方法的映射
        """
        return {
            'poker_join': self.handle_join_room,
            'poker_leave': self.handle_leave_room,
            'poker_status': self.handle_player_status,
            'poker_stats': self.handle_player_stats,
            'poker_rooms': self.handle_rooms_list,
            'poker_create': self.handle_create_room,
            'poker_start': self.handle_start_game,
            'poker_call': self.handle_game_call,
            'poker_raise': self.handle_game_raise,
            'poker_fold': self.handle_game_fold,
            'poker_check': self.handle_game_check,
            'poker_allin': self.handle_game_allin,
            'poker_achievements': self.handle_achievements,
            'poker_equip': self.handle_equip_achievement,
            'poker_emergency_exit': self.handle_emergency_exit,
            'poker_leaderboard': self.handle_leaderboard,
        }
    
    async def handle_join_room(self, event: AstrMessageEvent, room_id: str = "") -> AsyncGenerator:
        """
        处理加入房间命令
        
        Args:
            event: 消息事件对象
            room_id: 房间ID（为空时快速匹配）
        """
        user_id = event.get_sender_id()
        
        try:
            # 检查封禁状态
            ban_error = await self._check_player_ban_status(user_id)
            if ban_error:
                yield event.plain_result(ban_error)
                return
            
            # 检查玩家是否已在游戏中
            current_room = await self.room_manager.get_player_room(user_id)
            if current_room:
                yield event.plain_result(f"❌ 您已在房间 {current_room.room_id[:8]} 中，请先离开当前游戏")
                return
            
            # 检查积分是否足够
            player = await self.player_manager.get_or_create_player(user_id)
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
                    room_status = self.ui_builder.build_room_status(room)
                    yield event.plain_result(room_status)
                else:
                    yield event.plain_result("❌ 加入房间失败，房间可能已满或游戏进行中")
            else:
                # 快速匹配
                room = await self.room_manager.quick_match(user_id)
                if room:
                    yield event.plain_result(f"✅ 已匹配到房间 {room.room_id[:8]}")
                    room_status = self.ui_builder.build_room_status(room)
                    yield event.plain_result(room_status)
                else:
                    yield event.plain_result("❌ 暂无可用房间，请稍后重试或创建新房间")
                    
        except Exception as e:
            async for result in self.handle_error(event, e, "加入房间"):
                yield result
    
    async def handle_leave_room(self, event: AstrMessageEvent) -> AsyncGenerator:
        """
        处理离开房间命令（简化版本，避免竞态条件）
        
        Args:
            event: 消息事件对象
        """
        user_id = event.get_sender_id()
        
        try:
            current_room = await self.room_manager.get_player_room(user_id)
            if not current_room:
                yield event.plain_result("❌ 您当前不在任何房间中")
                return
            
            room_id = current_room.room_id
            success = await self.room_manager.leave_room(room_id, user_id)
            
            if success:
                yield event.plain_result("✅ 已成功离开游戏")
            else:
                yield event.plain_result("❌ 离开游戏失败，请重试")
                
        except Exception as e:
            async for result in self.handle_error(event, e, "离开房间"):
                yield result
    
    async def handle_create_room(self, event: AstrMessageEvent, blind_level: int = 1) -> AsyncGenerator:
        """
        处理创建房间命令
        
        Args:
            event: 消息事件对象
            blind_level: 盲注级别
        """
        user_id = event.get_sender_id()
        
        try:
            # 确保插件已初始化
            if not await self.ensure_plugin_initialized():
                yield event.plain_result("❌ 插件正在初始化，请稍后重试")
                return
            # 检查玩家是否已经在房间中
            existing_room = await self.room_manager.get_player_room(user_id)
            if existing_room:
                yield event.plain_result(f"❌ 您已在房间 {existing_room.room_id[:8]} 中")
                return
            
            # 检查盲注级别
            valid_levels = self.plugin_config.get("blind_levels", [1, 2, 5, 10, 25, 50])
            if blind_level not in valid_levels:
                yield event.plain_result(f"❌ 盲注级别必须是: {valid_levels}")
                return
            
            # 创建房间
            room = await self.room_manager.create_room(
                creator_id=user_id,
                small_blind=blind_level,
                big_blind=blind_level * 2,
                max_players=6
            )
            
            if room:
                # 确保创建者已注册
                if not await self.require_player_registration(event, user_id):
                    yield event.plain_result("❌ 玩家注册失败，无法创建房间")
                    return
                
                # 显示房间创建成功信息
                room_info = f"""✅ 房间创建成功！
🏠 房间号: {room.room_id[:8]}
💰 盲注: {blind_level}/{blind_level*2}
👤 房主: {event.get_sender_name() or '匿名玩家'}
📋 状态: 等待玩家加入

🎮 游戏说明:
• 至少需要 2 名玩家才能开始
• 使用 /poker_start 开始游戏
• 分享房间号让其他人加入: /poker_join {room.room_id[:8]}

💡 提示: 其他玩家可以通过 /poker_rooms 查看房间列表"""
                
                yield event.plain_result(room_info)
                
                # 提示玩家接下来的操作
                yield event.plain_result("🎯 等待更多玩家加入，或使用 /poker_start 开始游戏（至少2人）")
            else:
                yield event.plain_result("❌ 房间创建失败")
                
        except Exception as e:
            async for result in self.handle_error(event, e, "创建房间"):
                yield result

    async def handle_player_stats(self, event: AstrMessageEvent) -> AsyncGenerator:
        """
        处理玩家统计查询命令
        
        Args:
            event: 消息事件对象
        """
        user_id = event.get_sender_id()
        
        try:
            # 确保玩家注册
            if not await self.require_player_registration(event, user_id):
                yield event.plain_result("❌ 玩家注册失败")
                return
            
            player = await self.player_manager.get_player(user_id)
            stats = await self.player_manager.get_player_stats(user_id)
            
            if not player or not stats:
                yield event.plain_result("❌ 获取统计数据失败")
                return
            
            # 构建统计信息
            stats_text = f"""📊 {player.display_name} 的详细统计

💰 筹码信息:
• 当前筹码: {player.chips:,}
• 历史总盈亏: {player.total_profit:+,}
• 平均每局盈亏: {(stats.player_info.total_profit / max(stats.player_info.total_games, 1)):+.1f}

🎮 游戏记录:
• 总游戏: {player.total_games} 局
• 胜利: {player.wins} 局 ({(player.wins/max(player.total_games,1)*100):.1f}%)
• 失败: {player.losses} 局
• 最长连胜: {stats.longest_winning_streak} 局
• 最长连败: {stats.longest_losing_streak} 局

🏆 成就进展:
• 已获得: {len(player.achievements)} 个成就
• 最佳牌型: {player.best_hand or '无'}
• 单局最大盈利: {stats.biggest_win:+,}
• 单局最大亏损: {stats.biggest_loss:+,}

📈 等级信息:
• 当前等级: {player.level}
• 经验值: {player.experience}
• 距离升级: {1000 - (player.experience % 1000)} EXP"""

            yield event.plain_result(stats_text)
            
        except Exception as e:
            async for result in self.handle_error(event, e, "获取统计信息"):
                yield result

    async def handle_rooms_list(self, event: AstrMessageEvent) -> AsyncGenerator:
        """
        处理房间列表查询命令
        
        Args:
            event: 消息事件对象
        """
        try:
            rooms = list(self.room_manager.rooms.values())
            
            if not rooms:
                yield event.plain_result("🏠 当前没有活跃房间\n使用 /poker_create 创建新房间")
                return
            
            # 过滤可见房间（非私人房间）
            public_rooms = [room for room in rooms if not room.is_private]
            
            if not public_rooms:
                yield event.plain_result("🏠 当前没有公开房间\n使用 /poker_create 创建新房间")
                return
            
            room_list = "🏠 可用房间列表:\n\n"
            
            for room in public_rooms[:10]:  # 最多显示10个房间
                status_icon = {
                    "WAITING": "⏳",
                    "IN_GAME": "🎮", 
                    "FINISHED": "✅"
                }.get(room.status.name, "❓")
                
                room_list += f"{status_icon} {room.room_id[:8]}\n"
                room_list += f"  👥 {room.current_players}/{room.max_players} 人\n"
                room_list += f"  💰 {room.small_blind}/{room.big_blind}\n"
                room_list += f"  📍 {room.status.name}\n\n"
            
            room_list += "使用 /poker_join [房间号] 加入房间"
            yield event.plain_result(room_list)
            
        except Exception as e:
            async for result in self.handle_error(event, e, "获取房间列表"):
                yield result

    async def handle_player_status(self, event: AstrMessageEvent) -> AsyncGenerator:
        """
        处理玩家状态查询命令
        
        Args:
            event: 消息事件对象
        """
        user_id = event.get_sender_id()
        
        try:
            # 确保插件已初始化
            if not await self.ensure_plugin_initialized():
                yield event.plain_result("❌ 插件正在初始化，请稍后重试")
                return
                
            # 确保玩家已注册
            if not await self.require_player_registration(event, user_id):
                yield event.plain_result("❌ 玩家注册失败")
                return
            
            player = await self.player_manager.get_player(user_id)
            current_room = await self.room_manager.get_player_room(user_id)
            
            # 构建状态信息
            status_lines = []
            status_lines.append(f"👤 玩家状态 - {player.display_name}")
            status_lines.append("=" * 30)
            status_lines.append(f"💰 筹码: {player.chips:,}")
            status_lines.append(f"⭐ 等级: {player.level}")
            status_lines.append(f"🎲 总局数: {player.total_games}")
            win_rate = (player.wins / max(player.total_games, 1)) * 100
            status_lines.append(f"🏆 胜率: {win_rate:.1f}%")
            
            # 装备的成就信息
            if player.equipped_achievement:
                achievement_config = self.player_manager.achievements_config.get(player.equipped_achievement)
                if achievement_config:
                    status_lines.append(f"💎 装备成就: {achievement_config['icon']} {achievement_config['name']}")
                else:
                    status_lines.append(f"💎 装备成就: {player.equipped_achievement}")
            else:
                status_lines.append("💎 装备成就: 无")
            
            if current_room:
                status_lines.append(f"🏠 当前房间: {current_room.room_id[:8]}")
                status_lines.append(f"📊 房间状态: {current_room.status.name}")
                if current_room.game:
                    status_lines.append(f"🎲 游戏阶段: {current_room.game.game_phase.value}")
            else:
                status_lines.append("🏠 当前房间: 无")
                
            yield event.plain_result("\n".join(status_lines))
            
        except Exception as e:
            async for result in self.handle_error(event, e, "查询状态"):
                yield result

    async def handle_start_game(self, event: AstrMessageEvent) -> AsyncGenerator:
        """处理开始游戏命令 - 委托给主插件"""
        # 直接调用主插件的方法
        async for result in self.plugin.start_game(event):
            yield result

    async def handle_game_call(self, event: AstrMessageEvent) -> AsyncGenerator:
        """处理跟注命令"""
        user_id = event.get_sender_id()
        
        try:
            if not await self.ensure_plugin_initialized():
                yield event.plain_result("❌ 插件正在初始化，请稍后重试")
                return
                
            if not await self.require_player_registration(event, user_id):
                yield event.plain_result("❌ 玩家注册失败")
                return
            
            # 检查玩家是否在房间中
            room = await self.room_manager.get_player_room(user_id)
            if not room:
                yield event.plain_result("❌ 您当前不在任何房间中")
                return
            
            # 检查游戏是否在进行
            if not room.game or room.game.is_game_over():
                yield event.plain_result("❌ 当前没有进行中的游戏")
                return
            
            # 检查是否轮到该玩家
            if room.game.current_player_id != user_id:
                current_player = room.game.players.get(room.game.current_player_id)
                if current_player:
                    yield event.plain_result(f"❌ 还没轮到您，当前是 {current_player.display_name} 的回合")
                else:
                    yield event.plain_result("❌ 还没轮到您")
                return
            
            # 执行跟注
            player = room.game.players[user_id]
            call_amount = room.game.current_bet - player.current_bet
            
            if call_amount <= 0:
                yield event.plain_result("❌ 无需跟注，您可以选择过牌或加注")
                return
            
            if player.chips < call_amount:
                yield event.plain_result(f"❌ 筹码不足！需要 {call_amount}，但您只有 {player.chips}")
                return
            
            # 执行跟注动作
            success = await room.game.handle_player_action(user_id, PlayerAction.CALL)
            
            if success:
                yield event.plain_result(f"✅ {player.display_name} 跟注 {call_amount}")
                
                # 检查游戏状态并给出相应提示
                async for result in self._handle_post_action_status(event, room):
                    yield result
            else:
                yield event.plain_result("❌ 跟注操作失败")
                    
        except Exception as e:
            async for result in self.handle_error(event, e, "跟注"):
                yield result

    async def handle_game_raise(self, event: AstrMessageEvent, amount: int = None) -> AsyncGenerator:
        """处理加注命令"""
        user_id = event.get_sender_id()
        
        try:
            if not await self.ensure_plugin_initialized():
                yield event.plain_result("❌ 插件正在初始化，请稍后重试")
                return
                
            if not await self.require_player_registration(event, user_id):
                yield event.plain_result("❌ 玩家注册失败")
                return
            
            # 检查玩家是否在房间中
            room = await self.room_manager.get_player_room(user_id)
            if not room:
                yield event.plain_result("❌ 您当前不在任何房间中")
                return
            
            # 检查游戏是否在进行
            if not room.game or room.game.is_game_over():
                yield event.plain_result("❌ 当前没有进行中的游戏")
                return
            
            # 检查是否轮到该玩家
            if room.game.current_player_id != user_id:
                current_player = room.game.players.get(room.game.current_player_id)
                if current_player:
                    yield event.plain_result(f"❌ 还没轮到您，当前是 {current_player.display_name} 的回合")
                else:
                    yield event.plain_result("❌ 还没轮到您")
                return
            
            # 确定加注金额（"加注到"逻辑）
            player = room.game.players[user_id]
            current_call_amount = room.game.current_bet - player.current_bet
            
            if amount is None:
                # 默认最小加注：当前最高下注 + 大盲注
                min_raise_to = room.game.current_bet + room.game.big_blind
                amount = min_raise_to
            
            # 验证加注金额
            if amount <= room.game.current_bet:
                yield event.plain_result(f"❌ 加注金额必须大于当前最高下注 {room.game.current_bet}")
                yield event.plain_result(f"💡 最小加注到: {room.game.current_bet + room.game.big_blind}")
                return
            
            # 计算玩家需要投入的总筹码（加注金额 - 已下注金额）
            total_needed = amount - player.current_bet
            
            if player.chips < total_needed:
                yield event.plain_result(f"❌ 筹码不足！加注到 {amount} 需要额外投入 {total_needed}，但您只有 {player.chips}")
                return
            
            # 记录操作前的当前下注额（用于计算增量）
            old_current_bet = room.game.current_bet
            
            # 执行加注动作
            success = await room.game.handle_player_action(user_id, PlayerAction.RAISE, amount)
            
            if success:
                # 计算实际加注的增量（新的下注额 - 旧的下注额）
                raise_increase = amount - old_current_bet
                yield event.plain_result(f"🔥 {player.display_name} 加注到 {amount} (增加 {raise_increase})")
                
                # 检查游戏状态并给出相应提示
                async for result in self._handle_post_action_status(event, room):
                    yield result
            else:
                yield event.plain_result("❌ 加注操作失败")
                    
        except Exception as e:
            async for result in self.handle_error(event, e, "加注"):
                yield result

    async def handle_game_fold(self, event: AstrMessageEvent) -> AsyncGenerator:
        """处理弃牌命令"""
        user_id = event.get_sender_id()
        
        try:
            if not await self.ensure_plugin_initialized():
                yield event.plain_result("❌ 插件正在初始化，请稍后重试")
                return
                
            if not await self.require_player_registration(event, user_id):
                yield event.plain_result("❌ 玩家注册失败")
                return
            
            # 检查玩家是否在房间中
            room = await self.room_manager.get_player_room(user_id)
            if not room:
                yield event.plain_result("❌ 您当前不在任何房间中")
                return
            
            # 检查游戏是否在进行
            if not room.game or room.game.is_game_over():
                yield event.plain_result("❌ 当前没有进行中的游戏")
                return
            
            # 检查是否轮到该玩家
            if room.game.current_player_id != user_id:
                current_player = room.game.players.get(room.game.current_player_id)
                if current_player:
                    yield event.plain_result(f"❌ 还没轮到您，当前是 {current_player.display_name} 的回合")
                else:
                    yield event.plain_result("❌ 还没轮到您")
                return
            
            # 执行弃牌动作
            player = room.game.players[user_id]
            success = await room.game.handle_player_action(user_id, PlayerAction.FOLD)
            
            if success:
                yield event.plain_result(f"🚫 {player.display_name} 弃牌")
                
                # 检查游戏状态并给出相应提示
                async for result in self._handle_post_action_status(event, room):
                    yield result
            else:
                yield event.plain_result("❌ 弃牌操作失败")
                    
        except Exception as e:
            async for result in self.handle_error(event, e, "弃牌"):
                yield result

    async def handle_game_check(self, event: AstrMessageEvent) -> AsyncGenerator:
        """处理过牌命令"""
        user_id = event.get_sender_id()
        
        try:
            if not await self.ensure_plugin_initialized():
                yield event.plain_result("❌ 插件正在初始化，请稍后重试")
                return
                
            if not await self.require_player_registration(event, user_id):
                yield event.plain_result("❌ 玩家注册失败")
                return
            
            # 检查玩家是否在房间中
            room = await self.room_manager.get_player_room(user_id)
            if not room:
                yield event.plain_result("❌ 您当前不在任何房间中")
                return
            
            # 检查游戏是否在进行
            if not room.game or room.game.is_game_over():
                yield event.plain_result("❌ 当前没有进行中的游戏")
                return
            
            # 检查是否轮到该玩家
            if room.game.current_player_id != user_id:
                current_player = room.game.players.get(room.game.current_player_id)
                if current_player:
                    yield event.plain_result(f"❌ 还没轮到您，当前是 {current_player.display_name} 的回合")
                else:
                    yield event.plain_result("❌ 还没轮到您")
                return
            
            # 检查是否可以过牌
            player = room.game.players[user_id]
            if room.game.current_bet > player.current_bet:
                call_amount = room.game.current_bet - player.current_bet
                yield event.plain_result(f"❌ 无法过牌，需要跟注 {call_amount} 或弃牌")
                return
            
            # 执行过牌动作
            success = await room.game.handle_player_action(user_id, PlayerAction.CHECK)
            
            if success:
                yield event.plain_result(f"✋ {player.display_name} 过牌")
                
                # 检查游戏状态并给出相应提示
                async for result in self._handle_post_action_status(event, room):
                    yield result
            else:
                yield event.plain_result("❌ 过牌操作失败")
                    
        except Exception as e:
            async for result in self.handle_error(event, e, "过牌"):
                yield result

    async def handle_game_allin(self, event: AstrMessageEvent) -> AsyncGenerator:
        """处理全押命令"""
        user_id = event.get_sender_id()
        
        try:
            if not await self.ensure_plugin_initialized():
                yield event.plain_result("❌ 插件正在初始化，请稍后重试")
                return
                
            if not await self.require_player_registration(event, user_id):
                yield event.plain_result("❌ 玩家注册失败")
                return
            
            # 检查玩家是否在房间中
            room = await self.room_manager.get_player_room(user_id)
            if not room:
                yield event.plain_result("❌ 您当前不在任何房间中")
                return
            
            # 检查游戏是否在进行
            if not room.game or room.game.is_game_over():
                yield event.plain_result("❌ 当前没有进行中的游戏")
                return
            
            # 检查是否轮到该玩家
            if room.game.current_player_id != user_id:
                current_player = room.game.players.get(room.game.current_player_id)
                if current_player:
                    yield event.plain_result(f"❌ 还没轮到您，当前是 {current_player.display_name} 的回合")
                else:
                    yield event.plain_result("❌ 还没轮到您")
                return
            
            # 执行全押动作
            player = room.game.players[user_id]
            if player.chips <= 0:
                yield event.plain_result("❌ 您已经没有筹码了")
                return
            
            all_in_amount = player.current_bet + player.chips
            success = await room.game.handle_player_action(user_id, PlayerAction.ALL_IN)
            
            if success:
                yield event.plain_result(f"🚀 {player.display_name} 全押！总下注: {all_in_amount}")
                
                # 检查游戏状态并给出相应提示
                async for result in self._handle_post_action_status(event, room):
                    yield result
            else:
                yield event.plain_result("❌ 全押操作失败")
                    
        except Exception as e:
            async for result in self.handle_error(event, e, "全押"):
                yield result
    
    async def _handle_post_action_status(self, event: AstrMessageEvent, room) -> AsyncGenerator:
        """处理操作后的游戏状态提示"""
        try:
            if room.game.game_phase == GamePhase.GAME_OVER:
                # 游戏结束，显示结算信息
                async for result in self._handle_game_over(event, room):
                    yield result
            elif room.game.game_phase == GamePhase.SHOWDOWN:
                # 摊牌阶段，显示最终结果
                yield event.plain_result("🎯 进入摊牌阶段，计算结果中...")
                async for result in self._handle_showdown(event, room):
                    yield result
            elif room.game.game_phase != GamePhase.WAITING:
                # 显示完整的游戏状态（包含公共牌、玩家状态等）
                async for result in self._show_complete_game_status(event, room):
                    yield result
        except Exception as e:
            logger.error(f"处理操作后状态时发生错误: {e}")
    
    async def _show_complete_game_status(self, event: AstrMessageEvent, room) -> AsyncGenerator:
        """显示完整的游戏状态"""
        try:
            # 构建游戏状态信息
            status_lines = []
            status_lines.append("🎰 德州扑克游戏状态")
            status_lines.append("=" * 40)
            
            # 房间和局数信息
            status_lines.append(f"🏠 房间: {room.room_id[:8]}")
            
            # 游戏阶段
            phase_names = {
                GamePhase.PRE_FLOP: "翻牌前",
                GamePhase.FLOP: "翻牌后", 
                GamePhase.TURN: "转牌后",
                GamePhase.RIVER: "河牌后"
            }
            phase_name = phase_names.get(room.game.game_phase, "未知阶段")
            status_lines.append(f"🎲 第{room.game.hand_number}局 - {phase_name}")
            
            # 底池和下注信息
            status_lines.append(f"💰 底池: {room.game.main_pot}")
            status_lines.append(f"💵 当前下注: {room.game.current_bet}")
            
            # 公共牌信息（如果有）
            community_cards = room.game.get_community_cards()
            if community_cards:
                cards_str = " ".join(community_cards)
                status_lines.append(f"🎴 公共牌: {cards_str}")
            
            status_lines.append("")
            status_lines.append("👥 玩家状态:")
            status_lines.append("-" * 40)
            
            # 玩家状态
            current_player_id = room.game.current_player_id
            for player_id, player in room.game.players.items():
                if not player.is_in_hand():
                    continue
                    
                # 玩家状态指示符
                if player_id == current_player_id:
                    status_prefix = "👉  🟢"  # 当前行动玩家
                else:
                    status_prefix = "    🟢"  # 其他玩家
                
                # 玩家基本信息
                player_line = f"{status_prefix} {player_id[-8:]} 🎯 💰{player.chips}"
                
                # 添加当前下注信息
                if player.current_bet > 0:
                    player_line += f" 下注:{player.current_bet}"
                
                # 添加最后操作
                if player.last_action:
                    action_names = {
                        PlayerAction.FOLD: "弃牌",
                        PlayerAction.CHECK: "过牌", 
                        PlayerAction.CALL: "跟注",
                        PlayerAction.RAISE: "加注",
                        PlayerAction.ALL_IN: "全押"
                    }
                    action_name = action_names.get(player.last_action, str(player.last_action))
                    player_line += f" [{action_name}]"
                
                status_lines.append(player_line)
            
            status_lines.append("")
            
            # 当前行动玩家提示
            if current_player_id:
                current_player = room.game.players.get(current_player_id)
                if current_player:
                    status_lines.append(f"⏰ 等待 {current_player_id[-8:]}... 操作")
                    
                    # 显示可用操作
                    actions = []
                    
                    # 判断能否跟注
                    call_amount = room.game.current_bet - current_player.current_bet
                    if call_amount > 0:
                        actions.append(f"/poker_call (跟注{call_amount})")
                    else:
                        actions.append("/poker_check (过牌)")
                    
                    # 总是可以加注和弃牌
                    actions.append("/poker_raise [金额] (加注到)")
                    actions.append("/poker_fold (弃牌)")
                    
                    # 全押
                    if current_player.chips > 0:
                        actions.append("/poker_allin (全押)")
                    
                    status_lines.append(f"可用操作: {' | '.join(actions)}")
            
            # 输出所有状态信息
            yield event.plain_result("\n".join(status_lines))
            
        except Exception as e:
            logger.error(f"显示完整游戏状态时发生错误: {e}")
            
    async def _handle_showdown(self, event: AstrMessageEvent, room) -> AsyncGenerator:
        """处理摊牌阶段"""
        try:
            # 显示所有玩家的手牌和最终公共牌
            community_cards = room.game.get_community_cards()
            if community_cards:
                cards_str = " ".join(community_cards)
                yield event.plain_result(f"🎴 最终公共牌: {cards_str}")
            
            # 显示每个玩家的手牌（还在牌局中的）
            for player_id, player in room.game.players.items():
                if player.is_in_hand() and player.hole_cards:
                    hole_cards_str = " ".join([str(card) for card in player.hole_cards])
                    yield event.plain_result(f"👤 {player.display_name}: {hole_cards_str}")
            
            yield event.plain_result("🔍 计算最佳牌型中...")
            
        except Exception as e:
            logger.error(f"处理摊牌阶段时发生错误: {e}")
            yield event.plain_result("❌ 摊牌处理出现错误")
    
    async def _handle_game_over(self, event: AstrMessageEvent, room) -> AsyncGenerator:
        """处理游戏结束"""
        try:
            # 收集所有玩家信息和结算数据
            game_summary_lines = []
            game_summary_lines.append("🎉 游戏结束！")
            game_summary_lines.append("=" * 40)
            
            # 显示最终的牌型和结果
            community_cards = room.game.get_community_cards()
            if community_cards:
                cards_str = " ".join(community_cards)
                game_summary_lines.append(f"🎴 公共牌: {cards_str}")
                game_summary_lines.append("")
            
            game_summary_lines.append("📊 最终结算:")
            game_summary_lines.append("-" * 40)
            
            # 显示所有玩家的最终结果
            winner_id = None
            max_profit = float('-inf')
            
            if hasattr(room.game, 'game_results') and room.game.game_results:
                for player_id, result in room.game.game_results.items():
                    profit = result.get('profit', 0)
                    
                    # 获取玩家显示名称
                    player = room.game.players.get(player_id)
                    display_name = player.display_name if player else player_id[-8:]
                    
                    # 获取手牌信息（优先显示牌型，否则显示手牌）
                    hand_desc = result.get('hand_description', '未知牌型')
                    if hand_desc == '未知牌型':
                        # 尝试显示玩家的手牌
                        hand_cards = result.get('hand_cards', [])
                        if hand_cards and len(hand_cards) == 2:
                            hand_desc = f"手牌: {' '.join(hand_cards)}"
                        else:
                            # 如果都没有，尝试从游戏引擎获取
                            if player and hasattr(player, 'hole_cards') and player.hole_cards:
                                hand_desc = f"手牌: {' '.join([str(card) for card in player.hole_cards])}"
                    
                    # 记录最大盈利者
                    if profit > max_profit:
                        max_profit = profit
                        winner_id = player_id
                    
                    # 构建玩家结算信息
                    if profit > 0:
                        game_summary_lines.append(f"🏆 {display_name}: +{profit} 筹码 | {hand_desc}")
                    elif profit == 0:
                        game_summary_lines.append(f"🤝 {display_name}: ±0 筹码 | {hand_desc}")
                    else:
                        game_summary_lines.append(f"💸 {display_name}: {profit} 筹码 | {hand_desc}")
                
                # 显示获胜信息
                if winner_id and max_profit > 0:
                    winner = room.game.players.get(winner_id)
                    winner_name = winner.display_name if winner else winner_id[-8:]
                    game_summary_lines.append("")
                    game_summary_lines.append(f"🎊 恭喜 {winner_name} 获胜，赢得 {max_profit} 筹码！")
            
            game_summary_lines.append("")
            game_summary_lines.append("🚪 所有玩家已自动离开房间")
            
            # 更新玩家数据和房间清理
            await self._update_players_after_game(room)
            
            # 一次性发送完整的结算信息
            yield event.plain_result("\n".join(game_summary_lines))
            
        except Exception as e:
            logger.error(f"处理游戏结束时发生错误: {e}")
            yield event.plain_result("❌ 游戏结算出现错误")
    
    async def _update_players_after_game(self, room):
        """游戏结束后更新玩家数据并清理房间"""
        try:
            # 更新玩家筹码和统计数据
            if hasattr(room.game, 'game_results') and room.game.game_results:
                for player_id, result in room.game.game_results.items():
                    try:
                        player_info = await self.player_manager.get_player(player_id)
                        if player_info:
                            # 更新筹码
                            old_chips = player_info.chips
                            profit = result.get('profit', 0)
                            player_info.chips = result.get('final_chips', old_chips + profit)
                            
                            # 更新统计数据
                            player_info.total_games += 1
                            if profit > 0:
                                player_info.wins += 1
                                if profit > player_info.largest_win:
                                    player_info.largest_win = profit
                            else:
                                player_info.losses += 1
                            
                            player_info.total_profit += profit
                            
                            # 更新最佳牌型
                            hand_eval = result.get('hand_evaluation')
                            if hand_eval and (not player_info.best_hand or hand_eval > player_info.best_hand):
                                player_info.best_hand = str(hand_eval)
                            
                            # 保存玩家数据
                            await self.player_manager.save_player(player_info)
                            logger.info(f"✅ 玩家 {player_id} 数据更新完成：筹码 {old_chips} -> {player_info.chips} (变动: {profit:+})")
                            
                    except Exception as player_error:
                        logger.error(f"更新玩家 {player_id} 数据时发生错误: {player_error}")
            
            # 清理房间 - 将所有玩家移出房间
            player_ids_to_remove = list(room.player_ids.copy())
            for player_id in player_ids_to_remove:
                try:
                    # 确保玩家真正从房间中移除
                    if player_id in room.player_ids:
                        room.player_ids.remove(player_id)
                        logger.info(f"✅ 玩家 {player_id} 已从房间 {room.room_id[:8]} 的玩家列表移除")
                    
                    # 从等待列表中也移除
                    if player_id in room.waiting_list:
                        room.waiting_list.remove(player_id)
                        logger.info(f"✅ 玩家 {player_id} 已从房间等待列表移除")
                    
                    # 从房间管理器的玩家映射中移除
                    if hasattr(self.room_manager, 'player_room_mapping') and player_id in self.room_manager.player_room_mapping:
                        del self.room_manager.player_room_mapping[player_id]
                        logger.info(f"✅ 玩家 {player_id} 已从房间映射中移除")
                        
                except Exception as remove_error:
                    logger.error(f"从房间移除玩家 {player_id} 时发生错误: {remove_error}")
            
                # 完全销毁房间 - 增强房间清理逻辑
                from ..models.room_manager import RoomStatus
                try:
                    # 设置房间状态为已结束
                    room.status = RoomStatus.FINISHED
                    room.current_players = 0
                    room.game = None
                    
                    # 确保所有玩家状态都被重置
                    room.player_ids.clear()
                    room.waiting_list.clear()
                    
                    # 从房间管理器中移除房间
                    if room.room_id in self.room_manager.rooms:
                        del self.room_manager.rooms[room.room_id]
                        logger.info(f"🗑️ 房间 {room.room_id[:8]} 已完全销毁")
                    else:
                        logger.warning(f"⚠️ 房间 {room.room_id[:8]} 不在房间管理器中")
                    
                    # 额外清理：确保房间映射表也被清理
                    if hasattr(self.room_manager, 'player_room_mapping'):
                        # 清理所有指向这个房间的映射
                        keys_to_remove = []
                        for player_id, mapped_room_id in self.room_manager.player_room_mapping.items():
                            if mapped_room_id == room.room_id:
                                keys_to_remove.append(player_id)
                        
                        for key in keys_to_remove:
                            del self.room_manager.player_room_mapping[key]
                            logger.info(f"🧹 清理玩家 {key} 的房间映射")
                        
                except Exception as destroy_error:
                    logger.error(f"销毁房间时发生错误: {destroy_error}")
                
                logger.info(f"🏠 房间 {room.room_id[:8]} 彻底清理和销毁完成")
            
        except Exception as e:
            logger.error(f"游戏结束后清理时发生错误: {e}")

    async def handle_achievements(self, event: AstrMessageEvent, page: int = 1) -> AsyncGenerator:
        """处理成就查看命令 - 支持翻页和详细进度显示"""
        user_id = event.get_sender_id()
        try:
            if not await self.ensure_plugin_initialized():
                yield event.plain_result("❌ 插件正在初始化，请稍后重试")
                return
                
            if not await self.require_player_registration(event, user_id):
                yield event.plain_result("❌ 玩家注册失败")
                return
            
            # 获取成就进度数据
            progress_data = await self.player_manager.get_achievement_progress(user_id)
            if not progress_data:
                yield event.plain_result("❌ 获取成就数据失败")
                return
                
            # 分页设置
            items_per_page = 8
            unlocked = progress_data['unlocked']
            locked = progress_data['locked']
            all_achievements = unlocked + locked
            
            total_pages = (len(all_achievements) + items_per_page - 1) // items_per_page
            page = max(1, min(page, total_pages))
            
            start_idx = (page - 1) * items_per_page
            end_idx = start_idx + items_per_page
            page_achievements = all_achievements[start_idx:end_idx]
            
            # 构建成就显示
            achievement_lines = []
            achievement_lines.append("🏆 成就系统")
            achievement_lines.append("=" * 40)
            
            # 统计信息
            achievement_lines.append(f"📊 成就统计: {len(unlocked)}/{len(all_achievements)} 已解锁")
            
            # 装备的成就信息
            player = await self.player_manager.get_player(user_id)
            if player and player.equipped_achievement:
                equipped_info = None
                for achievement in all_achievements:
                    if achievement['id'] == player.equipped_achievement:
                        equipped_info = achievement
                        break
                if equipped_info:
                    achievement_lines.append(f"💎 装备中: {equipped_info['icon']} {equipped_info['name']}")
            
            achievement_lines.append("")
            achievement_lines.append(f"📄 第 {page}/{total_pages} 页")
            achievement_lines.append("-" * 40)
            
            # 显示当前页的成就
            for achievement in page_achievements:
                icon = achievement['icon']
                name = achievement['name']
                desc = achievement['description']
                achievement_id = achievement['id']
                
                # 修复成就解锁显示逻辑 - 检查progress_percent是否达到100%或is_unlocked
                is_actually_unlocked = achievement['is_unlocked'] or achievement.get('progress_percent', 0) >= 100
                
                if is_actually_unlocked:
                    # 已解锁的成就
                    status_icon = "✅"
                    progress_info = f"🆔 ID: {achievement_id} | 奖励: {achievement.get('reward', 0)} 筹码"
                else:
                    # 未解锁的成就 - 显示进度
                    status_icon = "🔒"
                    progress = achievement['current_progress']
                    target = achievement['target']
                    progress_percent = achievement['progress_percent']
                    progress_bar = self._create_progress_bar(progress_percent)
                    progress_info = f"进度: {progress}/{target} {progress_bar} {progress_percent:.1f}% | 奖励: {achievement.get('reward', 0)} 筹码"
                
                achievement_lines.append(f"{status_icon} {icon} {name}")
                achievement_lines.append(f"    {desc}")
                achievement_lines.append(f"    {progress_info}")
                achievement_lines.append("")
            
            # 翻页提示
            if total_pages > 1:
                achievement_lines.append("📖 翻页命令:")
                if page > 1:
                    achievement_lines.append(f"    /poker_achievements {page-1} - 上一页")
                if page < total_pages:
                    achievement_lines.append(f"    /poker_achievements {page+1} - 下一页")
                achievement_lines.append("")
            
            achievement_lines.append("💡 使用 /poker_equip [成就ID] 装备已解锁的成就")
            
            yield event.plain_result("\n".join(achievement_lines))
            
        except Exception as e:
            async for result in self.handle_error(event, e, "查看成就"):
                yield result
                
    def _create_progress_bar(self, progress_percent: float, length: int = 10) -> str:
        """创建进度条"""
        filled = int(progress_percent * length / 100)
        bar = "█" * filled + "░" * (length - filled)
        return f"[{bar}]"

    async def handle_equip_achievement(self, event: AstrMessageEvent, achievement_id: str = None) -> AsyncGenerator:
        """处理装备成就命令"""
        try:
            if not await self.ensure_plugin_initialized():
                yield event.plain_result("❌ 插件正在初始化，请稍后重试")
                return
                
            user_id = event.get_sender_id()
            if not await self.require_player_registration(event, user_id):
                yield event.plain_result("❌ 玩家注册失败")
                return
            
            if not achievement_id:
                yield event.plain_result("❌ 请指定要装备的成就ID\n💡 使用 /poker_achievements 查看可装备的成就")
                return
            
            # 装备成就
            success, message = await self.player_manager.equip_achievement(user_id, achievement_id)
            
            if success:
                yield event.plain_result(f"✅ {message}")
            else:
                yield event.plain_result(f"❌ {message}")
                
        except Exception as e:
            async for result in self.handle_error(event, e, "装备成就"):
                yield result

            
    async def handle_leaderboard(self, event: AstrMessageEvent, page: int = 1) -> AsyncGenerator:
        """处理排行榜查看命令"""
        try:
            if not await self.ensure_plugin_initialized():
                yield event.plain_result("❌ 插件正在初始化，请稍后重试")
                return
            
            # 获取排行榜数据 - 按胜率排序
            leaderboard = await self.player_manager.get_leaderboard('winrate', limit=1000)  # 获取所有玩家
            
            if not leaderboard:
                yield event.plain_result("📋 暂无排行榜数据")
                return
            
            # 分页设置
            items_per_page = 10
            total_pages = (len(leaderboard) + items_per_page - 1) // items_per_page
            page = max(1, min(page, total_pages))
            
            start_idx = (page - 1) * items_per_page
            end_idx = start_idx + items_per_page
            page_players = leaderboard[start_idx:end_idx]
            
            # 构建排行榜显示
            leaderboard_lines = []
            leaderboard_lines.append("🏆 德州扑克排行榜")
            leaderboard_lines.append("=" * 40)
            leaderboard_lines.append(f"📊 总玩家数: {len(leaderboard)}")
            leaderboard_lines.append(f"📄 第 {page}/{total_pages} 页")
            leaderboard_lines.append("-" * 40)
            
            for i, (rank, player_info) in enumerate(page_players, start=start_idx + 1):
                # 计算胜率
                winrate = (player_info.wins / max(player_info.total_games, 1)) * 100
                
                # 排名图标
                if rank == 1:
                    rank_icon = "🥇"
                elif rank == 2:
                    rank_icon = "🥈"
                elif rank == 3:
                    rank_icon = "🥉"
                else:
                    rank_icon = f"{rank:2d}."
                
                # 玩家信息
                player_line = f"{rank_icon} {player_info.display_name or player_info.player_id[-8:]}"
                stats_line = f"    💰{player_info.chips:,} | 🎲{player_info.total_games} | 🏆{winrate:.1f}% | ⭐{len(player_info.achievements)}"
                
                # 装备的成就
                if player_info.equipped_achievement:
                    achievement_config = self.player_manager.achievements_config.get(player_info.equipped_achievement)
                    if achievement_config:
                        equipped_line = f"    💎 {achievement_config['icon']} {achievement_config['name']}"
                    else:
                        equipped_line = f"    💎 {player_info.equipped_achievement}"
                else:
                    equipped_line = "    💎 无装备成就"
                
                leaderboard_lines.append(player_line)
                leaderboard_lines.append(stats_line)
                leaderboard_lines.append(equipped_line)
                leaderboard_lines.append("")
            
            # 翻页提示
            if total_pages > 1:
                leaderboard_lines.append("📖 翻页命令:")
                if page > 1:
                    leaderboard_lines.append(f"    /poker_leaderboard {page-1} - 上一页")
                if page < total_pages:
                    leaderboard_lines.append(f"    /poker_leaderboard {page+1} - 下一页")
                leaderboard_lines.append("")
            
            leaderboard_lines.append("📝 说明: 💰筹码 | 🎲总局数 | 🏆胜率 | ⭐成就数")
            
            yield event.plain_result("\n".join(leaderboard_lines))
            
        except Exception as e:
            async for result in self.handle_error(event, e, "查看排行榜"):
                yield result

    async def handle_emergency_exit(self, event: AstrMessageEvent) -> AsyncGenerator:
        """处理紧急退出命令"""
        try:
            # 确保插件已初始化
            if not await self.ensure_plugin_initialized(event):
                return
                
            user_id = event.get_sender_id()
            
            # 检查用户是否在房间中
            if not hasattr(self.plugin.room_manager, 'player_room_mapping'):
                yield event.plain_result("❌ 房间系统未初始化")
                return
                
            room_id = self.plugin.room_manager.player_room_mapping.get(user_id)
            if not room_id:
                yield event.plain_result("❌ 您不在任何房间中")
                return
            
            room = self.plugin.room_manager.rooms.get(room_id)
            if not room:
                yield event.plain_result("❌ 房间不存在")
                return
            
            # 强制退出房间
            try:
                # 如果游戏正在进行，先结束游戏
                if hasattr(room, 'game') and room.game and room.game.game_phase != GamePhase.WAITING:
                    # 强制结束游戏
                    room.game.game_phase = GamePhase.GAME_OVER
                    logger.info(f"紧急退出：强制结束房间 {room_id[:8]} 的游戏")
                
                # 移除玩家
                if user_id in room.player_ids:
                    room.player_ids.remove(user_id)
                if user_id in room.waiting_list:
                    room.waiting_list.remove(user_id)
                
                # 从房间映射中移除
                if user_id in self.plugin.room_manager.player_room_mapping:
                    del self.plugin.room_manager.player_room_mapping[user_id]
                
                # 更新房间状态
                room.current_players = len(room.player_ids)
                
                # 如果房间没有玩家了，销毁房间
                if room.current_players == 0:
                    if room_id in self.plugin.room_manager.rooms:
                        del self.plugin.room_manager.rooms[room_id]
                    logger.info(f"紧急退出：已销毁空房间 {room_id[:8]}")
                
                yield event.plain_result(f"✅ 已强制退出房间 {room_id[:8]}")
                
            except Exception as exit_error:
                logger.error(f"紧急退出处理失败: {exit_error}")
                yield event.plain_result(f"⚠️ 退出过程中出现问题，但已尽力清理: {exit_error}")
                
        except Exception as e:
            logger.error(f"紧急退出失败: {e}")
            yield event.plain_result(f"❌ 紧急退出失败: {e}")
    
    # 这里可以添加更多游戏命令的处理方法...
    # 为了避免文件过长，其他方法可以根据需要逐步添加
