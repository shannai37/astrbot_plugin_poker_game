"""
德州扑克插件

一个功能完整的德州扑克游戏插件，支持多人游戏、积分系统、房间管理等功能。

适配AstrBot和NapCat平台，提供完整的德州扑克游戏体验。

主要功能：
- 多人德州扑克游戏
- 玩家积分和等级系统
- 房间创建和管理
- 管理员控制面板
- 数据持久化
- 游戏统计和排行榜

Author: 山萘
Version: 1.0.0
"""

__version__ = "1.0.0"
__author__ = "山萘"
__description__ = "德州扑克游戏插件 - 支持多人游戏、积分系统、房间管理"

# 导出主要类
from .main import TexasHoldemPlugin

__all__ = ["TexasHoldemPlugin"]
