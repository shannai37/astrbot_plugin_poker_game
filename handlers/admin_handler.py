from typing import Dict, AsyncGenerator
import time
import asyncio
from astrbot.api.event import AstrMessageEvent
from astrbot.api import logger
from .base_handler import BaseCommandHandler


class AdminCommandHandler(BaseCommandHandler):
    """
    管理员命令处理器
    
    负责处理：
    - 玩家管理（封禁、解封、重置等）
    - 系统统计和监控
    - 数据备份和配置
    - 房间管理
    """
    
    def get_command_handlers(self) -> Dict[str, callable]:
        """
        获取管理员命令映射
        
        Returns:
            Dict[str, callable]: 命令名到处理方法的映射
        """
        return {
            'poker_admin': self.handle_admin_panel,
            'poker_admin_players': self.handle_admin_players,
            'poker_admin_ban': self.handle_admin_ban,
            'poker_admin_unban': self.handle_admin_unban,
            'poker_admin_addchips': self.handle_admin_add_chips,
            'poker_admin_reset': self.handle_admin_reset_player,
            'poker_admin_rooms': self.handle_admin_rooms,
            'poker_admin_close': self.handle_admin_close_room,
            'poker_admin_kick': self.handle_admin_kick_player,
            'poker_admin_stats': self.handle_admin_detailed_stats,
            'poker_admin_backup': self.handle_admin_backup,
            'poker_admin_config': self.handle_admin_config,
            'poker_admin_banned': self.handle_admin_banned_list,
        }
    
    
    async def handle_admin_panel(self, event: AstrMessageEvent) -> AsyncGenerator:
        """
        处理管理员面板命令
        
        Args:
            event: 消息事件对象
        """
        
        try:
            # 获取系统统计
            system_stats = await self.player_manager.get_system_stats()
            room_stats = await self.room_manager.get_room_stats()
            
            # 构建管理员面板
            panel_text = self.ui_builder.build_admin_panel(system_stats, room_stats)
            yield event.plain_result(panel_text)
            
        except Exception as e:
            async for result in self.handle_error(event, e, "获取管理员面板"):
                yield result
    
    async def handle_admin_ban(self, event: AstrMessageEvent, player_id: str, duration: int = 24, reason: str = "违规行为") -> AsyncGenerator:
        """
        处理封禁玩家命令
        
        Args:
            event: 消息事件对象
            player_id: 玩家ID
            duration: 封禁时长（小时）
            reason: 封禁原因
        """
        
        try:
            # 使用插件中已有的玩家ID解析方法
            resolved_player_id, error_msg = await self._resolve_player_id(player_id)
            if error_msg:
                yield event.plain_result(error_msg)
                return
            
            player = await self.player_manager.get_player(resolved_player_id)
            if not player:
                yield event.plain_result(f"❌ 玩家不存在: {resolved_player_id}")
                return
            
            if player.is_banned:
                yield event.plain_result(f"❌ 玩家 {player.display_name} 已被封禁")
                return
            
            # 执行封禁 - 修复参数顺序：player_id, reason, duration_hours
            success = await self.player_manager.ban_player(resolved_player_id, reason, duration)
            if success:
                yield event.plain_result(f"✅ 已封禁玩家 {player.display_name} {duration}小时\n原因: {reason}")
                
                # 检查玩家是否在房间中，如果是则将其踢出
                current_room = await self.room_manager.get_player_room(resolved_player_id)
                if current_room:
                    leave_success = await self.room_manager.leave_room(current_room.room_id, resolved_player_id)
                    if leave_success:
                        yield event.plain_result(f"🏠 已将被封禁玩家从房间 {current_room.room_id[:8]} 中移除")
                    else:
                        yield event.plain_result(f"⚠️ 封禁成功但从房间移除失败")
            else:
                yield event.plain_result(f"❌ 封禁操作失败")
                
        except Exception as e:
            async for result in self.handle_error(event, e, "封禁玩家"):
                yield result
    
    async def handle_admin_detailed_stats(self, event: AstrMessageEvent) -> AsyncGenerator:
        """
        处理详细统计命令
        
        Args:
            event: 消息事件对象
        """
        
        try:
            # 获取详细统计信息
            system_stats = await self.player_manager.get_system_stats()
            room_stats = await self.room_manager.get_room_stats()
            
            lines = []
            lines.append("📊 德州扑克详细统计")
            lines.append("=" * 40)
            
            # 系统统计
            lines.append("🖥️ 系统信息:")
            lines.append(f"  👥 总注册玩家: {system_stats.get('total_players', 0)}")
            lines.append(f"  🟢 活跃玩家(7天): {system_stats.get('active_players', 0)}")
            lines.append(f"  🎲 总游戏局数: {system_stats.get('total_games', 0)}")
            lines.append(f"  💰 流通筹码总量: {system_stats.get('total_chips', 0):,}")
            runtime_seconds = time.time() - self.plugin.start_time
            lines.append(f"  📅 运行时间: {self.ui_builder.format_duration(runtime_seconds)}")
            lines.append("")
            
            # 房间统计
            lines.append("🏠 房间信息:")
            lines.append(f"  📊 活跃房间数: {room_stats.get('total_rooms', 0)}")
            lines.append(f"  🟢 游戏中: {room_stats.get('active_rooms', 0)}")
            lines.append(f"  ⏳ 等待中: {room_stats.get('waiting_rooms', 0)}")
            lines.append(f"  👥 在线玩家: {room_stats.get('total_players', 0)}")
            
            yield event.plain_result("\n".join(lines))
            
        except Exception as e:
            async for result in self.handle_error(event, e, "获取详细统计"):
                yield result

    # 以下方法委托给主插件处理
    async def handle_admin_players(self, event: AstrMessageEvent, limit: int = 20) -> AsyncGenerator:
        """处理管理员查看玩家列表命令"""
        async for result in self.plugin.admin_players(event, limit):
            yield result

    async def handle_admin_unban(self, event: AstrMessageEvent, player_id: str) -> AsyncGenerator:
        """处理管理员解封玩家命令"""
        async for result in self.plugin.admin_unban_player(event, player_id):
            yield result

    async def handle_admin_add_chips(self, event: AstrMessageEvent, player_id: str, amount: int, reason: str = "管理员补充") -> AsyncGenerator:
        """处理管理员添加筹码命令"""
        async for result in self.plugin.admin_add_chips(event, player_id, amount, reason):
            yield result

    async def handle_admin_reset_player(self, event: AstrMessageEvent, player_id: str, keep_chips: bool = False) -> AsyncGenerator:
        """处理管理员重置玩家数据命令"""
        async for result in self.plugin.admin_reset_player(event, player_id, keep_chips):
            yield result

    async def handle_admin_rooms(self, event: AstrMessageEvent) -> AsyncGenerator:
        """处理管理员查看房间命令"""
        async for result in self.plugin.admin_rooms(event):
            yield result

    async def handle_admin_close_room(self, event: AstrMessageEvent, room_id: str, reason: str = "管理员关闭") -> AsyncGenerator:
        """处理管理员关闭房间命令"""
        async for result in self.plugin.admin_close_room(event, room_id, reason):
            yield result

    async def handle_admin_kick_player(self, event: AstrMessageEvent, player_id: str, reason: str = "管理员操作") -> AsyncGenerator:
        """处理管理员踢出玩家命令"""
        async for result in self.plugin.admin_kick_player(event, player_id, reason):
            yield result

    async def handle_admin_backup(self, event: AstrMessageEvent) -> AsyncGenerator:
        """处理管理员备份数据命令"""
        async for result in self.plugin.admin_backup(event):
            yield result

    async def handle_admin_config(self, event: AstrMessageEvent) -> AsyncGenerator:
        """处理管理员查看配置命令"""
        async for result in self.plugin.admin_config(event):
            yield result
            
    async def handle_admin_banned_list(self, event: AstrMessageEvent, page: int = 1) -> AsyncGenerator:
        """查看封禁玩家列表"""
        try:
            if not await self.ensure_plugin_initialized():
                yield event.plain_result("❌ 插件正在初始化，请稍后重试")
                return
            
            # 获取所有封禁玩家，同时检查并清理过期封禁
            banned_players = []
            expired_players = []
            current_check_time = time.time()
            
            for player_id, player in self.player_manager.players.items():
                # 检查封禁状态，如果过期则自动清理
                if player.ban_status:
                    if player.ban_until > 0 and current_check_time >= player.ban_until:
                        # 过期封禁，自动清理
                        player.ban_status = False
                        player.ban_reason = ""
                        player.ban_until = 0
                        self.player_manager.cache_dirty = True
                        expired_players.append(player)
                    else:
                        # 仍在封禁期
                        banned_players.append(player)
            
            # 如果有过期玩家被清理，记录日志
            if expired_players:
                expired_names = [p.display_name or p.player_id[-8:] for p in expired_players]
                logger.info(f"清理过期封禁玩家: {', '.join(expired_names)}")
                # 异步保存
                asyncio.create_task(self.player_manager.save_all_players())
            
            if not banned_players:
                yield event.plain_result("📋 当前没有被封禁的玩家")
                return
            
            # 分页显示
            items_per_page = 10
            total_pages = (len(banned_players) + items_per_page - 1) // items_per_page
            page = max(1, min(page, total_pages))
            
            start_idx = (page - 1) * items_per_page
            end_idx = start_idx + items_per_page
            page_players = banned_players[start_idx:end_idx]
            
            # 构建显示信息
            ban_lines = []
            ban_lines.append("🚫 封禁玩家列表")
            ban_lines.append("=" * 40)
            ban_lines.append(f"📊 总计: {len(banned_players)} 名被封禁玩家")
            ban_lines.append(f"📄 第 {page}/{total_pages} 页")
            ban_lines.append("-" * 40)
            
            # 获取当前时间用于计算剩余封禁时间
            current_time = time.time()
            for player in page_players:
                status_emoji = "🔴"
                ban_info = f"{status_emoji} {player.display_name or player.player_id[-8:]}"
                
                # 封禁原因
                if hasattr(player, 'ban_reason') and player.ban_reason:
                    ban_info += f"\n    📝 原因: {player.ban_reason}"
                
                # 封禁时间
                if hasattr(player, 'ban_until'):
                    if player.ban_until == 0:
                        ban_info += f"\n    ⏰ 类型: 永久封禁"
                    elif player.ban_until > 0:
                        remaining = player.ban_until - current_time
                        if remaining > 0:
                            days = int(remaining // 86400)
                            hours = int((remaining % 86400) // 3600)
                            minutes = int((remaining % 3600) // 60)
                            if days > 0:
                                ban_info += f"\n    ⏰ 剩余: {days}天{hours}小时"
                            elif hours > 0:
                                ban_info += f"\n    ⏰ 剩余: {hours}小时{minutes}分钟"
                            else:
                                ban_info += f"\n    ⏰ 剩余: {minutes}分钟"
                        else:
                            ban_info += f"\n    ⏰ 状态: 已过期（待系统清理）"
                
                ban_lines.append(ban_info)
                ban_lines.append("")
            
            # 翻页提示
            if total_pages > 1:
                ban_lines.append("📖 翻页命令:")
                if page > 1:
                    ban_lines.append(f"    /poker_admin_banned {page-1} - 上一页")
                if page < total_pages:
                    ban_lines.append(f"    /poker_admin_banned {page+1} - 下一页")
                ban_lines.append("")
            
            ban_lines.append("💡 使用 /poker_admin_unban [玩家ID] 解除封禁")
            
            yield event.plain_result("\n".join(ban_lines))
            
        except Exception as e:
            async for result in self.handle_error(event, e, "查看封禁列表"):
                yield result
    
    # 这里可以添加更多管理员命令的处理方法...
