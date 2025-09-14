from typing import Dict, AsyncGenerator
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
        }
    
    def _is_admin(self, user_id: str) -> bool:
        """
        检查用户是否为管理员
        
        Args:
            user_id: 用户ID
            
        Returns:
            bool: 是否为管理员
        """
        # 这里应该实现管理员权限检查逻辑
        # 可以通过配置文件、数据库或其他方式管理管理员列表
        admin_list = self.plugin_config.get('admin_users', [])
        return user_id in admin_list
    
    async def require_admin_permission(self, event: AstrMessageEvent) -> bool:
        """
        检查并要求管理员权限
        
        Args:
            event: 消息事件对象
            
        Returns:
            bool: 是否有管理员权限
        """
        user_id = event.get_sender_id()
        if not self._is_admin(user_id):
            yield event.plain_result("❌ 此功能仅限管理员使用")
            return False
        return True
    
    async def handle_admin_panel(self, event: AstrMessageEvent) -> AsyncGenerator:
        """
        处理管理员面板命令
        
        Args:
            event: 消息事件对象
        """
        if not await self.require_admin_permission(event):
            return
        
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
        if not await self.require_admin_permission(event):
            return
        
        try:
            # 使用插件中已有的玩家ID解析方法
            resolved_player_id, error_msg = await self.plugin._resolve_player_id(player_id)
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
            
            # 执行封禁
            success = await self.player_manager.ban_player(resolved_player_id, duration, reason)
            if success:
                yield event.plain_result(f"✅ 已封禁玩家 {player.display_name} {duration}小时\n原因: {reason}")
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
        if not await self.require_admin_permission(event):
            return
        
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
            lines.append(f"  📅 运行时间: {self.ui_builder.format_time(self.plugin.start_time)}")
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
    
    # 这里可以添加更多管理员命令的处理方法...
