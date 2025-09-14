from typing import Dict, AsyncGenerator
from astrbot.api.event import AstrMessageEvent
from astrbot.api import logger
from .base_handler import BaseCommandHandler


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
            'poker_call': self.handle_game_call,
            'poker_raise': self.handle_game_raise,
            'poker_fold': self.handle_game_fold,
            'poker_check': self.handle_game_check,
            'poker_allin': self.handle_game_allin,
            'poker_achievements': self.handle_achievements,
            'poker_equip': self.handle_equip_achievement,
        }
    
    async def handle_join_room(self, event: AstrMessageEvent, room_id: str = None) -> AsyncGenerator:
        """
        处理加入房间命令
        
        Args:
            event: 消息事件对象
            room_id: 房间ID（可选，用于快速匹配）
        """
        user_id = event.get_sender_id()
        
        # 确保玩家已注册
        if not await self.require_player_registration(event, user_id):
            yield event.plain_result("❌ 玩家注册失败")
            return
        
        try:
            # 检查玩家是否已在房间中
            current_room = await self.room_manager.get_player_room(user_id)
            if current_room:
                yield event.plain_result(f"❌ 您已在房间 {current_room.room_id} 中")
                return
            
            # 加入房间逻辑
            if room_id:
                # 加入指定房间
                room = await self.room_manager.get_room(room_id)
                if not room:
                    yield event.plain_result(f"❌ 房间 {room_id} 不存在")
                    return
                
                success = await self.room_manager.join_room(user_id, room_id)
                if success:
                    yield event.plain_result(f"✅ 成功加入房间 {room_id}")
                else:
                    yield event.plain_result(f"❌ 加入房间 {room_id} 失败")
            else:
                # 快速匹配
                available_rooms = await self.room_manager.get_available_rooms()
                if available_rooms:
                    room = available_rooms[0]  # 选择第一个可用房间
                    success = await self.room_manager.join_room(user_id, room.room_id)
                    if success:
                        yield event.plain_result(f"✅ 快速匹配成功，加入房间 {room.room_id}")
                    else:
                        yield event.plain_result("❌ 快速匹配失败")
                else:
                    yield event.plain_result("❌ 暂无可用房间，请使用 /poker_create 创建房间")
                    
        except Exception as e:
            async for result in self.handle_error(event, e, "加入房间"):
                yield result
    
    async def handle_leave_room(self, event: AstrMessageEvent) -> AsyncGenerator:
        """
        处理离开房间命令
        
        Args:
            event: 消息事件对象
        """
        user_id = event.get_sender_id()
        
        try:
            current_room = await self.room_manager.get_player_room(user_id)
            if not current_room:
                yield event.plain_result("❌ 您当前不在任何房间中")
                return
            
            success = await self.room_manager.leave_room(current_room.room_id, user_id)
            if success:
                yield event.plain_result(f"✅ 成功离开房间 {current_room.room_id}")
            else:
                yield event.plain_result("❌ 离开房间失败")
                
        except Exception as e:
            async for result in self.handle_error(event, e, "离开房间"):
                yield result
    
    async def handle_player_status(self, event: AstrMessageEvent) -> AsyncGenerator:
        """
        处理玩家状态查询命令
        
        Args:
            event: 消息事件对象
        """
        user_id = event.get_sender_id()
        
        try:
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
            status_lines.append(f"🏆 胜率: {player.win_rate:.1f}%")
            
            if current_room:
                status_lines.append(f"🏠 当前房间: {current_room.room_id}")
                status_lines.append(f"📊 房间状态: {current_room.status.value}")
                if current_room.game:
                    status_lines.append(f"🎲 游戏阶段: {current_room.game.game_phase.value}")
            else:
                status_lines.append("🏠 当前房间: 无")
                
            yield event.plain_result("\n".join(status_lines))
            
        except Exception as e:
            async for result in self.handle_error(event, e, "查询状态"):
                yield result
    
    # 这里可以添加更多游戏命令的处理方法...
    # 为了避免文件过长，其他方法可以根据需要逐步添加
