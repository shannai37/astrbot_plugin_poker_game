from abc import ABC, abstractmethod
from typing import Optional, AsyncGenerator
from astrbot.api.event import AstrMessageEvent
from astrbot.api import logger


class BaseCommandHandler(ABC):
    """
    命令处理器基类
    
    提供通用的功能和接口定义，所有具体的命令处理器都应继承此类
    """
    
    def __init__(self, plugin_instance):
        """
        初始化处理器
        
        Args:
            plugin_instance: 主插件实例，用于访问管理器和配置
        """
        self.plugin = plugin_instance
        self.player_manager = plugin_instance.player_manager
        self.room_manager = plugin_instance.room_manager
        self.database_manager = plugin_instance.database_manager
        self.ui_builder = plugin_instance.ui_builder
        self.plugin_config = plugin_instance.plugin_config
        
    @abstractmethod
    def get_command_handlers(self):
        """
        获取此处理器负责的命令映射
        
        Returns:
            Dict[str, callable]: 命令名到处理方法的映射
        """
        pass
    
    async def handle_error(self, event: AstrMessageEvent, error: Exception, operation: str = "操作"):
        """
        统一的错误处理
        
        Args:
            event: 消息事件对象
            error: 异常对象
            operation: 操作描述
        """
        logger.error(f"{operation}失败: {error}")
        yield event.plain_result(f"❌ {operation}失败: {str(error)}")
    
    async def require_player_registration(self, event: AstrMessageEvent, user_id: str) -> bool:
        """
        确保玩家已注册，如果未注册则自动注册
        
        Args:
            event: 消息事件对象
            user_id: 用户ID
            
        Returns:
            bool: 是否成功（注册或已存在）
        """
        try:
            player = await self.player_manager.get_player(user_id)
            if not player:
                # 自动注册
                display_name = event.get_sender_display() or user_id[:8]
                player = await self.player_manager.create_player(user_id, display_name)
                if player:
                    logger.info(f"自动注册新玩家: {user_id} ({display_name})")
                    return True
                else:
                    return False
            return True
        except Exception as e:
            logger.error(f"检查玩家注册状态失败: {e}")
            return False
