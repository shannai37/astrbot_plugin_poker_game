from typing import Dict, List, Any, Optional
import time
import datetime
import json

from astrbot.api import logger
import astrbot.api.message_components as Comp
from ..models.game_engine import TexasHoldemGame, GamePhase
from ..models.player_manager import PlayerInfo, PlayerStats
from ..models.room_manager import GameRoom, RoomStatus
from ..models.card_system import Card


class GameUIBuilder:
    """
    游戏UI构建器
    
    功能包括：
    - 游戏状态可视化
    - 牌桌界面构建
    - 玩家信息展示
    - 排行榜和统计图表
    - 适配不同平台的消息格式
    
    支持的界面类型：
    - 文字版牌桌
    - 房间列表
    - 玩家统计
    - 排行榜
    - 管理员面板
    """
    
    def __init__(self):
        """初始化UI构建器"""
        self.suit_symbols = {
            "♣": "♣",    # 梅花
            "♦": "♦",    # 方片  
            "♥": "♥",    # 红桃
            "♠": "♠"     # 黑桃
        }
        
        self.card_display_width = 3
        self.table_width = 60
        
    def build_game_status(self, game: TexasHoldemGame) -> str:
        """
        构建游戏状态显示
        
        Args:
            game: 游戏实例
            
        Returns:
            str: 格式化的游戏状态文本
        """
        try:
            if not game:
                return "游戏未开始"
            
            game_state = game.get_game_state()
            
            # 构建状态文本
            status_lines = []
            
            # 游戏头部信息
            status_lines.append("🎰 德州扑克游戏状态")
            status_lines.append("=" * 40)
            status_lines.append(f"🏠 房间: {game_state['room_id']}")
            status_lines.append(f"🎲 第{game_state['hand_number']}局 - {self._get_phase_name(game_state['phase'])}")
            status_lines.append(f"💰 底池: {game_state['main_pot']}")
            
            if game_state['current_bet'] > 0:
                status_lines.append(f"💵 当前下注: {game_state['current_bet']}")
            
            status_lines.append("")
            
            # 公共牌
            if game_state['community_cards']:
                community_str = " ".join(game_state['community_cards'])
                status_lines.append(f"🎴 公共牌: {community_str}")
                status_lines.append("")
            
            # 玩家状态
            status_lines.append("👥 玩家状态:")
            status_lines.append("-" * 40)
            
            for player_id, player_data in game_state['players'].items():
                player_line = self._build_player_status_line(player_id, player_data, game_state['current_player_id'])
                status_lines.append(player_line)
            
            # 当前操作玩家（仅在游戏进行中显示）
            if game_state['current_player_id'] and game_state['phase'] not in ['showdown', 'game_over']:
                status_lines.append("")
                status_lines.append(f"⏰ 等待 {game_state['current_player_id'][:8]}... 操作")
                status_lines.append("可用操作: /poker_call | /poker_raise [金额] | /poker_fold | /poker_check")
            elif game_state['phase'] in ['showdown', 'game_over']:
                status_lines.append("")
                status_lines.append("🎯 游戏已结束！")
            
            return "\n".join(status_lines)
            
        except Exception as e:
            logger.error(f"构建游戏状态失败: {e}")
            return f"游戏状态显示错误: {str(e)}"
    
    def _build_player_status_line(self, player_id: str, player_data: Dict, current_player_id: str) -> str:
        """
        构建单个玩家状态行
        
        Args:
            player_id: 玩家ID
            player_data: 玩家数据
            current_player_id: 当前行动玩家ID
            
        Returns:
            str: 格式化的玩家状态行
        """
        # 玩家标识
        player_name = player_id[:8]
        
        # 位置标识 - 只保留庄家标识
        position_symbols = []
        if player_data.get('is_dealer'):
            position_symbols.append("🎯")
        # 移除SB/BB标识，因为用户不清楚含义
        # if player_data.get('is_small_blind'):
        #     position_symbols.append("SB")
        # if player_data.get('is_big_blind'):
        #     position_symbols.append("BB")
        
        position_str = " ".join(position_symbols)
        
        # 状态符号
        status = player_data.get('status', 'waiting')
        status_symbol = self._get_status_symbol(status)
        
        # 当前玩家标识
        current_marker = "👉 " if player_id == current_player_id else "   "
        
        # 筹码和下注信息
        chips = player_data.get('chips', 0)
        current_bet = player_data.get('current_bet', 0)
        total_bet = player_data.get('total_bet', 0)
        
        # 最后操作
        last_action = player_data.get('last_action', '')
        action_str = f"[{self._get_action_name(last_action)}]" if last_action else ""
        
        # 构建完整行
        bet_info = f"下注:{current_bet}" if current_bet > 0 else ""
        
        line_parts = [
            current_marker,
            status_symbol,
            player_name,
            position_str,
            f"💰{chips}",
            bet_info,
            action_str
        ]
        
        # 过滤空字符串并连接
        line = " ".join([part for part in line_parts if part])
        
        return line
    
    def _get_phase_name(self, phase: str) -> str:
        """获取游戏阶段名称"""
        phase_names = {
            'waiting': '等待开始',
            'pre_flop': '翻牌前',
            'flop': '翻牌',
            'turn': '转牌',
            'river': '河牌',
            'showdown': '摊牌',
            'game_over': '游戏结束'
        }
        return phase_names.get(phase, phase)
    
    def _get_status_symbol(self, status: str) -> str:
        """获取玩家状态符号"""
        status_symbols = {
            'active': '🟢',
            'folded': '❌',
            'all_in': '🔥',
            'waiting': '⏸️'
        }
        return status_symbols.get(status, '❓')
    
    def _get_action_name(self, action: str) -> str:
        """获取操作名称"""
        action_names = {
            'fold': '弃牌',
            'check': '过牌', 
            'call': '跟注',
            'raise': '加注',
            'all_in': '全押'
        }
        return action_names.get(action, action)
    
    def build_room_status(self, room: GameRoom) -> str:
        """
        构建房间状态显示
        
        Args:
            room: 房间对象
            
        Returns:
            str: 格式化的房间状态
        """
        try:
            lines = []
            
            # 房间基本信息
            lines.append(f"🏠 房间信息")
            lines.append("=" * 30)
            lines.append(f"🆔 房间号: {room.room_id[:8]}")
            lines.append(f"📝 房间名: {room.room_name}")
            lines.append(f"📊 状态: {self._get_room_status_name(room.status)}")
            lines.append(f"👥 玩家: {room.current_players}/{room.max_players}")
            lines.append(f"💰 盲注: {room.small_blind}/{room.big_blind}")
            lines.append(f"🎯 买入: {room.min_buy_in}-{room.max_buy_in}")
            
            # 房间设置
            settings = []
            if room.is_private:
                settings.append("🔒私人")
            if room.allow_observers:
                settings.append("👁️可旁观")
            if room.auto_start:
                settings.append("🔄自动开始")
            
            if settings:
                lines.append(f"⚙️ 设置: {' '.join(settings)}")
            
            # 玩家列表
            if room.player_ids:
                lines.append("")
                lines.append("👥 在座玩家:")
                for i, player_id in enumerate(sorted(room.player_ids), 1):
                    creator_mark = "👑" if player_id == room.creator_id else f"{i}."
                    # 显示更完整的玩家名称
                    display_name = player_id[:20] if len(player_id) > 20 else player_id
                    lines.append(f"  {creator_mark} {display_name}")
            
            # 等待列表
            if room.waiting_list:
                lines.append("")
                lines.append("⏳ 等待列表:")
                for i, player_id in enumerate(room.waiting_list, 1):
                    lines.append(f"  {i}. {player_id[:12]}")
            
            # 旁观者
            if room.observers:
                lines.append(f"👁️ 旁观者: {len(room.observers)}人")
            
            return "\n".join(lines)
            
        except Exception as e:
            logger.error(f"构建房间状态失败: {e}")
            return f"房间状态显示错误: {str(e)}"
    
    def _get_room_status_name(self, status: RoomStatus) -> str:
        """获取房间状态名称"""
        status_names = {
            RoomStatus.WAITING: "🟡等待中",
            RoomStatus.STARTING: "🟠准备中", 
            RoomStatus.IN_GAME: "🟢游戏中",
            RoomStatus.PAUSED: "🟣暂停",
            RoomStatus.FINISHED: "⚫已结束"
        }
        return status_names.get(status, str(status))
    
    def build_rooms_list(self, rooms: List[GameRoom]) -> str:
        """
        构建房间列表显示
        
        Args:
            rooms: 房间列表
            
        Returns:
            str: 格式化的房间列表
        """
        try:
            if not rooms:
                return "🏠 当前没有可用房间\n\n💡 使用 /poker create 创建新房间"
            
            lines = []
            lines.append(f"🏠 可用房间 ({len(rooms)}个)")
            lines.append("=" * 40)
            
            for room in rooms[:10]:  # 最多显示10个房间
                status_icon = "🟢" if room.status == RoomStatus.WAITING else "🟡"
                private_icon = "🔒" if room.is_private else ""
                
                room_line = (
                    f"{status_icon} {room.room_id[:8]} "
                    f"[{room.current_players}/{room.max_players}] "
                    f"💰{room.small_blind}/{room.big_blind} "
                    f"{private_icon}"
                )
                lines.append(room_line)
            
            lines.append("")
            lines.append("💡 使用 /poker join [房间号] 加入房间")
            lines.append("💡 使用 /poker quickjoin 快速匹配")
            
            return "\n".join(lines)
            
        except Exception as e:
            logger.error(f"构建房间列表失败: {e}")
            return f"房间列表显示错误: {str(e)}"
    
    def build_player_stats(self, stats: PlayerStats) -> str:
        """
        构建玩家统计显示
        
        Args:
            stats: 玩家统计对象
            
        Returns:
            str: 格式化的统计信息
        """
        try:
            player = stats.player_info
            lines = []
            
            # 玩家基本信息
            lines.append(f"👤 玩家统计 - {player.display_name}")
            lines.append("=" * 40)
            lines.append(f"🆔 ID: {player.player_id[:16]}")
            lines.append(f"⭐ 等级: {player.level} (经验: {player.experience}/{player.required_exp_for_next_level})")
            lines.append(f"💰 当前筹码: {player.chips:,}")
            lines.append("")
            
            # 游戏统计
            lines.append("📊 游戏统计:")
            lines.append(f"  🎲 总局数: {player.total_games}")
            lines.append(f"  🏆 胜利: {player.wins} ({player.win_rate:.1f}%)")
            lines.append(f"  💸 失败: {player.losses}")
            lines.append(f"  💹 总盈亏: {player.total_profit:+,}")
            lines.append("")
            
            # 成就
            lines.append("🏅 成就信息:")
            if player.equipped_achievement:
                lines.append(f"  🌟 装备中: {player.equipped_achievement}")
            else:
                lines.append("  🌟 装备中: 无")
            
            if player.achievements:
                lines.append(f"  📊 解锁数量: {len(player.achievements)}个")
                # 显示最新解锁的3个
                for achievement in player.achievements[-3:]:
                    lines.append(f"  • {achievement}")
                if len(player.achievements) > 3:
                    lines.append(f"  ... 还有{len(player.achievements)-3}个")
            else:
                lines.append("  📊 解锁数量: 0个")
            
            lines.append("  💡 使用 /poker_achievements 查看详情")
            lines.append("")
            
            # 最佳牌型
            if player.best_hand:
                lines.append(f"🎴 最佳牌型: {player.best_hand}")
                lines.append("")
            
            # 详细统计
            if stats.biggest_win > 0:
                lines.append(f"💎 最大单局盈利: {stats.biggest_win:,}")
            
            if stats.longest_winning_streak > 0:
                lines.append(f"🔥 最长连胜: {stats.longest_winning_streak}")
            
            # 当前连胜/连败
            if stats.current_streak > 0:
                lines.append(f"📈 当前连胜: {stats.current_streak}")
            elif stats.current_streak < 0:
                lines.append(f"📉 当前连败: {abs(stats.current_streak)}")
            
            # 牌型胜利统计
            if stats.hand_type_wins:
                lines.append("")
                lines.append("🎴 牌型胜利统计:")
                sorted_hands = sorted(stats.hand_type_wins.items(), key=lambda x: x[1], reverse=True)
                for hand_type, count in sorted_hands[:5]:  # 显示前5个
                    lines.append(f"  {hand_type}: {count}次")
            
            # 注册时间
            reg_time = datetime.datetime.fromtimestamp(player.registration_time)
            lines.append("")
            lines.append(f"📅 注册时间: {reg_time.strftime('%Y-%m-%d')}")
            
            return "\n".join(lines)
            
        except Exception as e:
            logger.error(f"构建玩家统计失败: {e}")
            return f"玩家统计显示错误: {str(e)}"
    
    def build_leaderboard(self, leaderboard: List[tuple], category: str) -> str:
        """
        构建排行榜显示
        
        Args:
            leaderboard: 排行榜数据 [(排名, 玩家信息)]
            category: 排行类别
            
        Returns:
            str: 格式化的排行榜
        """
        try:
            category_names = {
                'chips': '💰 筹码排行榜',
                'wins': '🏆 胜局排行榜',
                'profit': '💹 盈利排行榜',
                'winrate': '📊 胜率排行榜',
                'level': '⭐ 等级排行榜'
            }
            
            title = category_names.get(category, f'{category} 排行榜')
            
            lines = []
            lines.append(title)
            lines.append("=" * 35)
            
            if not leaderboard:
                lines.append("暂无排行数据")
                return "\n".join(lines)
            
            for rank, player in leaderboard:
                # 排名标识
                if rank == 1:
                    rank_icon = "🥇"
                elif rank == 2:
                    rank_icon = "🥈"
                elif rank == 3:
                    rank_icon = "🥉"
                else:
                    rank_icon = f"{rank}."
                
                # 根据类别显示不同数值
                if category == 'chips':
                    value = f"{player.chips:,}"
                elif category == 'wins':
                    value = f"{player.wins}胜"
                elif category == 'profit':
                    value = f"{player.total_profit:+,}"
                elif category == 'winrate':
                    value = f"{player.win_rate:.1f}%"
                elif category == 'level':
                    value = f"Lv.{player.level}"
                else:
                    value = ""
                
                player_name = player.display_name or player.player_id[:8]
                
                line = f"{rank_icon} {player_name[:12]} - {value}"
                lines.append(line)
            
            return "\n".join(lines)
            
        except Exception as e:
            logger.error(f"构建排行榜失败: {e}")
            return f"排行榜显示错误: {str(e)}"
    
    def build_game_results(self, results: Dict[str, Dict[str, Any]]) -> str:
        """
        构建游戏结果显示
        
        Args:
            results: 游戏结果字典
            
        Returns:
            str: 格式化的游戏结果
        """
        try:
            lines = []
            lines.append("🎲 游戏结果")
            lines.append("=" * 30)
            
            # 按盈利排序
            sorted_results = sorted(results.items(), key=lambda x: x[1]['profit'], reverse=True)
            
            for player_id, result in sorted_results:
                profit = result['profit']
                won = result['won']
                
                # 结果图标
                if won:
                    icon = "🏆" if profit > 0 else "🤝"
                else:
                    icon = "💸"
                
                # 盈亏颜色（用文本表示）
                if profit > 0:
                    profit_str = f"+{profit:,} 💰"
                elif profit < 0:
                    profit_str = f"{profit:,} 💸"
                else:
                    profit_str = "0"
                
                player_name = player_id[:8]
                
                # 手牌信息
                hand_eval = result.get('hand_evaluation')
                hand_str = ""
                if hand_eval and won:
                    hand_str = f" ({hand_eval.hand_rank.name_cn})"
                
                line = f"{icon} {player_name} {profit_str}{hand_str}"
                lines.append(line)
            
            return "\n".join(lines)
            
        except Exception as e:
            logger.error(f"构建游戏结果失败: {e}")
            return f"游戏结果显示错误: {str(e)}"
    
    def build_admin_panel(self, system_stats: Dict[str, Any], room_stats: Dict[str, Any]) -> str:
        """
        构建管理员面板
        
        Args:
            system_stats: 系统统计
            room_stats: 房间统计
            
        Returns:
            str: 管理员面板内容
        """
        try:
            lines = []
            lines.append("🛠️ 德州扑克管理面板")
            lines.append("=" * 40)
            
            # 系统统计
            lines.append("📊 系统统计:")
            lines.append(f"  👥 总玩家数: {system_stats.get('total_players', 0)}")
            lines.append(f"  🟢 活跃玩家(7天): {system_stats.get('active_players', 0)}")
            lines.append(f"  🆕 今日新增: {system_stats.get('today_new_players', 0)}")
            lines.append(f"  🎲 总游戏局数: {system_stats.get('total_games', 0)}")
            lines.append(f"  💰 流通筹码: {system_stats.get('total_chips', 0):,}")
            lines.append(f"  💹 总盈亏: {system_stats.get('total_profit', 0):+,}")
            lines.append(f"  🚫 封禁玩家: {system_stats.get('banned_players', 0)}")
            lines.append("")
            
            # 房间统计
            lines.append("🏠 房间统计:")
            lines.append(f"  📈 活跃房间数: {room_stats.get('total_rooms', 0)}")
            lines.append(f"  ⏳ 等待中: {room_stats.get('waiting_rooms', 0)}")
            lines.append(f"  🟢 游戏中: {room_stats.get('active_rooms', 0)}")
            lines.append(f"  🔄 准备中: {room_stats.get('starting_rooms', 0)}")
            lines.append(f"  ⏸️ 暂停: {room_stats.get('paused_rooms', 0)}")
            lines.append(f"  ⚫ 已结束: {room_stats.get('finished_rooms', 0)}")
            lines.append(f"  👥 在线玩家: {room_stats.get('total_players', 0)}")
            lines.append(f"  👁️ 旁观者: {room_stats.get('total_observers', 0)}")
            
            # 平均值
            avg_players = room_stats.get('average_players_per_room', 0)
            if avg_players > 0:
                lines.append(f"  📊 平均每房间: {avg_players:.1f}人")
            lines.append("")
            
            # 管理指令
            lines.append("⚙️ 管理指令:")
            lines.append("  /poker_admin_players - 查看玩家列表")
            lines.append("  /poker_admin_ban [用户] [时长] [原因] - 封禁玩家")
            lines.append("  /poker_admin_unban [用户] - 解封玩家")
            lines.append("  /poker_admin_banned [页数] - 查看封禁玩家列表")
            lines.append("  /poker_admin_addchips [用户] [数量] - 增加筹码")
            lines.append("  /poker_admin_backup - 备份数据")
            lines.append("  /poker_admin_stats - 详细统计")
            lines.append("")
            lines.append("🏅 成就指令:")
            lines.append("  /poker_achievements - 查看自己的成就")
            lines.append("  /poker_equip [成就ID] - 装备成就")
            
            return "\n".join(lines)
            
        except Exception as e:
            logger.error(f"构建管理员面板失败: {e}")
            return f"管理员面板显示错误: {str(e)}"
    
    def build_help_message(self) -> str:
        """
        构建帮助信息
        
        Returns:
            str: 帮助信息内容
        """
        lines = []
        lines.append("🎰 德州扑克插件帮助")
        lines.append("=" * 30)
        lines.append("")
        
        lines.append("🎮 基础指令:")
        lines.append("  /poker - 显示帮助")
        lines.append("  /poker join [房间号] - 加入房间")
        lines.append("  /poker leave - 离开房间")
        lines.append("  /poker quickjoin - 快速匹配")
        lines.append("  /poker status - 个人状态")
        lines.append("")
        
        lines.append("📊 信息查询:")
        lines.append("  /poker stats - 详细统计")
        lines.append("  /poker rank - 排行榜")
        lines.append("  /poker rooms - 房间列表")
        lines.append("")
        
        lines.append("🏠 房间管理:")
        lines.append("  /poker create [盲注级别] - 创建房间")
        lines.append("")
        
        lines.append("🎲 游戏操作:")
        lines.append("  /poker call - 跟注")
        lines.append("  /poker raise [金额] - 加注")
        lines.append("  /poker fold - 弃牌")
        lines.append("  /poker check - 过牌")
        lines.append("  /poker allin - 全押")
        lines.append("")
        
        lines.append("💡 提示:")
        lines.append("  • 初始筹码: 10000")
        lines.append("  • 操作超时: 30秒")
        lines.append("  • 支持私聊查看手牌")
        
        return "\n".join(lines)
    
    def build_achievements_list(self, progress_data: Dict[str, Any], player_name: str = "") -> str:
        """
        构建成就列表显示
        
        Args:
            progress_data: 成就进度数据
            player_name: 玩家名称
            
        Returns:
            str: 格式化的成就列表
        """
        try:
            lines = []
            lines.append(f"🏅 {player_name}的成就")
            lines.append("=" * 40)
            
            unlocked = progress_data.get('unlocked', [])
            locked = progress_data.get('locked', [])
            
            # 已解锁成就
            if unlocked:
                lines.append(f"✅ 已解锁成就 ({len(unlocked)}个):")
                lines.append("")
                
                # 按类别分组
                categories = {}
                for achievement in unlocked:
                    category = achievement['category']
                    if category not in categories:
                        categories[category] = []
                    categories[category].append(achievement)
                
                for category, achievements in categories.items():
                    lines.append(f"📂 {category}:")
                    for ach in achievements:
                        lines.append(f"  {ach['icon']} {ach['name']}")
                        lines.append(f"     {ach['description']}")
                        lines.append(f"     ID: {ach['id']}")
                    lines.append("")
            
            # 未解锁成就 (显示前5个最接近的)
            if locked:
                lines.append(f"🔒 进行中成就 (显示前5个):")
                lines.append("")
                
                # 按进度排序，显示最接近完成的
                locked_sorted = sorted(locked, key=lambda x: x['progress_percent'], reverse=True)
                
                for ach in locked_sorted[:5]:
                    progress_bar = self._build_progress_bar(ach['progress_percent'])
                    lines.append(f"  {ach['icon']} {ach['name']}")
                    lines.append(f"     {ach['description']}")
                    lines.append(f"     进度: {ach['progress']}/{ach['target']} {progress_bar}")
                    lines.append("")
            
            lines.append("💡 提示:")
            lines.append("  • 使用 /poker_equip [成就ID] 装备成就")
            lines.append("  • 装备的成就会在您的个人信息中显示")
            
            return "\n".join(lines)
            
        except Exception as e:
            logger.error(f"构建成就列表失败: {e}")
            return f"成就列表显示错误: {str(e)}"
    
    def _build_progress_bar(self, progress_percent: float, length: int = 10) -> str:
        """
        构建进度条
        
        Args:
            progress_percent: 进度百分比
            length: 进度条长度
            
        Returns:
            str: 进度条字符串
        """
        filled = int(progress_percent / 100 * length)
        empty = length - filled
        bar = "█" * filled + "░" * empty
        return f"[{bar}] {progress_percent:.0f}%"
    
    def build_card_visual(self, cards: List[str]) -> str:
        """
        构建扑克牌可视化
        
        Args:
            cards: 扑克牌字符串列表
            
        Returns:
            str: 可视化的扑克牌
        """
        if not cards:
            return "无牌"
        
        try:
            # 简单的文字版牌面
            card_strs = []
            for card_str in cards:
                if len(card_str) >= 2:
                    suit = card_str[0]
                    rank = card_str[1:]
                    
                    # 花色颜色标识（用符号表示）
                    if suit in ['♥', '♦']:
                        color_mark = "🔴"
                    else:
                        color_mark = "⚫"
                    
                    card_strs.append(f"[{color_mark}{rank}{suit}]")
            
            return " ".join(card_strs)
            
        except Exception as e:
            logger.error(f"构建扑克牌可视化失败: {e}")
            return " ".join(cards)
    
    def format_chips(self, amount: int) -> str:
        """
        格式化筹码显示
        
        Args:
            amount: 筹码数量
            
        Returns:
            str: 格式化的筹码字符串
        """
        if amount >= 1_000_000:
            return f"{amount/1_000_000:.1f}M"
        elif amount >= 1_000:
            return f"{amount/1_000:.1f}K"
        else:
            return str(amount)
    
    def format_time(self, timestamp: float) -> str:
        """
        格式化时间显示（用于时间戳）
        
        Args:
            timestamp: 时间戳
            
        Returns:
            str: 格式化的时间字符串
        """
        try:
            dt = datetime.datetime.fromtimestamp(timestamp)
            now = datetime.datetime.now()
            
            # 计算时间差
            diff = now - dt
            
            if diff.days > 0:
                return f"{diff.days}天前"
            elif diff.seconds > 3600:
                hours = diff.seconds // 3600
                return f"{hours}小时前"
            elif diff.seconds > 60:
                minutes = diff.seconds // 60
                return f"{minutes}分钟前"
            else:
                return "刚刚"
                
        except Exception as e:
            logger.error(f"格式化时间失败: {e}")
            return "未知时间"
    
    def format_duration(self, seconds: float) -> str:
        """
        格式化持续时间显示（用于秒数）
        
        Args:
            seconds: 持续时间（秒数）
            
        Returns:
            str: 格式化的持续时间字符串
        """
        try:
            total_seconds = int(seconds)
            
            days = total_seconds // 86400
            hours = (total_seconds % 86400) // 3600
            minutes = (total_seconds % 3600) // 60
            remaining_seconds = total_seconds % 60
            
            parts = []
            if days > 0:
                parts.append(f"{days}天")
            if hours > 0:
                parts.append(f"{hours}小时")
            if minutes > 0:
                parts.append(f"{minutes}分钟")
            if remaining_seconds > 0 or not parts:
                parts.append(f"{remaining_seconds}秒")
            
            return "".join(parts)
                
        except Exception as e:
            logger.error(f"格式化持续时间失败: {e}")
            return "未知时长"
