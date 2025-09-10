import sqlite3
import aiosqlite
import json
import time
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
import asyncio

from astrbot.api import logger


class DatabaseManager:
    """
    数据库管理器
    
    功能包括：
    - SQLite数据库操作
    - 玩家数据存储和查询
    - 游戏记录和统计
    - 交易日志管理
    - 数据备份和恢复
    
    数据库表结构：
    - players: 玩家基础信息
    - player_stats: 玩家详细统计
    - game_records: 游戏记录
    - transactions: 交易记录
    - achievements: 成就记录
    """
    
    def __init__(self, db_path: Path):
        """
        初始化数据库管理器
        
        Args:
            db_path: 数据库文件路径
        """
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 连接池配置
        self.connection_pool_size = 5
        self.connection_timeout = 30
        
        # 表结构版本
        self.schema_version = 1
        
    async def initialize(self):
        """
        初始化数据库
        
        创建必要的表结构
        """
        async with aiosqlite.connect(self.db_path) as db:
            # 设置数据库配置
            await db.execute("PRAGMA foreign_keys = ON")
            await db.execute("PRAGMA journal_mode = WAL")
            await db.execute("PRAGMA synchronous = NORMAL")
            
            # 创建表
            await self._create_tables(db)
            
            # 检查和更新数据库版本
            await self._check_schema_version(db)
            
            await db.commit()
            
        logger.info(f"数据库初始化完成: {self.db_path}")
    
    async def _create_tables(self, db: aiosqlite.Connection):
        """
        创建数据库表
        
        Args:
            db: 数据库连接
        """
        # 玩家基础信息表
        await db.execute("""
            CREATE TABLE IF NOT EXISTS players (
                player_id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                chips INTEGER DEFAULT 10000,
                level INTEGER DEFAULT 1,
                experience INTEGER DEFAULT 0,
                total_games INTEGER DEFAULT 0,
                wins INTEGER DEFAULT 0,
                losses INTEGER DEFAULT 0,
                total_profit INTEGER DEFAULT 0,
                best_hand TEXT,
                achievements TEXT DEFAULT '[]',
                last_active REAL DEFAULT 0,
                registration_time REAL DEFAULT 0,
                daily_bonus_claimed INTEGER DEFAULT 0,
                last_bonus_time REAL DEFAULT 0,
                ban_status INTEGER DEFAULT 0,
                ban_reason TEXT DEFAULT '',
                ban_until REAL DEFAULT 0,
                equipped_achievement TEXT DEFAULT '',
                created_at REAL DEFAULT CURRENT_TIMESTAMP,
                updated_at REAL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 玩家详细统计表
        await db.execute("""
            CREATE TABLE IF NOT EXISTS player_stats (
                player_id TEXT PRIMARY KEY,
                hand_type_wins TEXT DEFAULT '{}',
                position_stats TEXT DEFAULT '{}',
                recent_games TEXT DEFAULT '[]',
                longest_winning_streak INTEGER DEFAULT 0,
                longest_losing_streak INTEGER DEFAULT 0,
                current_streak INTEGER DEFAULT 0,
                biggest_win INTEGER DEFAULT 0,
                biggest_loss INTEGER DEFAULT 0,
                favorite_hand TEXT,
                created_at REAL DEFAULT CURRENT_TIMESTAMP,
                updated_at REAL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (player_id) REFERENCES players (player_id) ON DELETE CASCADE
            )
        """)
        
        # 游戏记录表
        await db.execute("""
            CREATE TABLE IF NOT EXISTS game_records (
                record_id INTEGER PRIMARY KEY AUTOINCREMENT,
                room_id TEXT NOT NULL,
                game_type TEXT DEFAULT 'texas_holdem',
                players TEXT NOT NULL,
                winner_id TEXT,
                game_duration REAL,
                final_pot INTEGER DEFAULT 0,
                hand_results TEXT DEFAULT '{}',
                created_at REAL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 交易记录表
        await db.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_id TEXT NOT NULL,
                amount INTEGER NOT NULL,
                balance_before INTEGER NOT NULL,
                balance_after INTEGER NOT NULL,
                transaction_type TEXT NOT NULL,
                reason TEXT DEFAULT '',
                created_at REAL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (player_id) REFERENCES players (player_id) ON DELETE CASCADE
            )
        """)
        
        # 成就记录表
        await db.execute("""
            CREATE TABLE IF NOT EXISTS achievements (
                achievement_id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_id TEXT NOT NULL,
                achievement_name TEXT NOT NULL,
                achievement_description TEXT,
                reward_amount INTEGER DEFAULT 0,
                unlocked_at REAL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (player_id) REFERENCES players (player_id) ON DELETE CASCADE
            )
        """)
        
        # 系统配置表
        await db.execute("""
            CREATE TABLE IF NOT EXISTS system_config (
                config_key TEXT PRIMARY KEY,
                config_value TEXT NOT NULL,
                updated_at REAL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 创建索引
        await self._create_indexes(db)
    
    async def _create_indexes(self, db: aiosqlite.Connection):
        """
        创建数据库索引
        
        Args:
            db: 数据库连接
        """
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_players_last_active ON players(last_active)",
            "CREATE INDEX IF NOT EXISTS idx_players_chips ON players(chips)",
            "CREATE INDEX IF NOT EXISTS idx_players_wins ON players(wins)",
            "CREATE INDEX IF NOT EXISTS idx_transactions_player_id ON transactions(player_id)",
            "CREATE INDEX IF NOT EXISTS idx_transactions_created_at ON transactions(created_at)",
            "CREATE INDEX IF NOT EXISTS idx_game_records_created_at ON game_records(created_at)",
            "CREATE INDEX IF NOT EXISTS idx_achievements_player_id ON achievements(player_id)",
        ]
        
        for index_sql in indexes:
            await db.execute(index_sql)
    
    async def _check_schema_version(self, db: aiosqlite.Connection):
        """
        检查数据库版本并升级
        
        Args:
            db: 数据库连接
        """
        try:
            cursor = await db.execute("SELECT config_value FROM system_config WHERE config_key = 'schema_version'")
            result = await cursor.fetchone()
            
            if result:
                current_version = int(result[0])
            else:
                current_version = 0
                await db.execute("INSERT INTO system_config (config_key, config_value) VALUES (?, ?)", 
                               ('schema_version', str(self.schema_version)))
            
            if current_version < self.schema_version:
                await self._upgrade_schema(db, current_version, self.schema_version)
                
        except Exception as e:
            logger.error(f"检查数据库版本失败: {e}")
    
    async def _upgrade_schema(self, db: aiosqlite.Connection, from_version: int, to_version: int):
        """
        升级数据库结构
        
        Args:
            db: 数据库连接
            from_version: 当前版本
            to_version: 目标版本
        """
        logger.info(f"升级数据库结构: {from_version} -> {to_version}")
        
        # 未来的数据库升级逻辑
        
        # 更新版本号
        await db.execute("UPDATE system_config SET config_value = ?, updated_at = ? WHERE config_key = 'schema_version'",
                        (str(to_version), time.time()))
    
    # ==================== 玩家数据操作 ====================
    
    async def save_player_data(self, player_id: str, player_data: Dict[str, Any]) -> bool:
        """
        保存玩家数据
        
        Args:
            player_id: 玩家ID
            player_data: 玩家数据字典
            
        Returns:
            bool: 是否成功
        """
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # 转换JSON字段
                achievements_json = json.dumps(player_data.get('achievements', []))
                
                await db.execute("""
                    INSERT OR REPLACE INTO players (
                        player_id, display_name, chips, level, experience,
                        total_games, wins, losses, total_profit, best_hand,
                        achievements, last_active, registration_time,
                        daily_bonus_claimed, last_bonus_time, ban_status,
                        ban_reason, ban_until, equipped_achievement, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    player_id,
                    player_data.get('display_name', ''),
                    player_data.get('chips', 10000),
                    player_data.get('level', 1),
                    player_data.get('experience', 0),
                    player_data.get('total_games', 0),
                    player_data.get('wins', 0),
                    player_data.get('losses', 0),
                    player_data.get('total_profit', 0),
                    player_data.get('best_hand'),
                    achievements_json,
                    player_data.get('last_active', time.time()),
                    player_data.get('registration_time', time.time()),
                    1 if player_data.get('daily_bonus_claimed', False) else 0,
                    player_data.get('last_bonus_time', 0),
                    1 if player_data.get('ban_status', False) else 0,
                    player_data.get('ban_reason', ''),
                    player_data.get('ban_until', 0),
                    player_data.get('equipped_achievement', ''),
                    time.time()
                ))
                
                await db.commit()
                return True
                
        except Exception as e:
            logger.error(f"保存玩家数据失败 {player_id}: {e}")
            return False
    
    async def get_player_data(self, player_id: str) -> Optional[Dict[str, Any]]:
        """
        获取玩家数据
        
        Args:
            player_id: 玩家ID
            
        Returns:
            Optional[Dict]: 玩家数据字典
        """
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute("""
                    SELECT player_id, display_name, chips, level, experience,
                           total_games, wins, losses, total_profit, best_hand,
                           achievements, last_active, registration_time,
                           daily_bonus_claimed, last_bonus_time, ban_status,
                           ban_reason, ban_until, equipped_achievement
                    FROM players WHERE player_id = ?
                """, (player_id,))
                
                row = await cursor.fetchone()
                
                if row:
                    return {
                        'player_id': row[0],
                        'display_name': row[1],
                        'chips': row[2],
                        'level': row[3],
                        'experience': row[4],
                        'total_games': row[5],
                        'wins': row[6],
                        'losses': row[7],
                        'total_profit': row[8],
                        'best_hand': row[9],
                        'achievements': json.loads(row[10]) if row[10] else [],
                        'last_active': row[11],
                        'registration_time': row[12],
                        'daily_bonus_claimed': bool(row[13]),
                        'last_bonus_time': row[14],
                        'ban_status': bool(row[15]),
                        'ban_reason': row[16],
                        'ban_until': row[17],
                        'equipped_achievement': row[18]
                    }
                
                return None
                
        except Exception as e:
            logger.error(f"获取玩家数据失败 {player_id}: {e}")
            return None
    
    async def load_all_players(self) -> List[Dict[str, Any]]:
        """
        加载所有玩家数据
        
        Returns:
            List[Dict]: 玩家数据列表
        """
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute("""
                    SELECT player_id, display_name, chips, level, experience,
                           total_games, wins, losses, total_profit, best_hand,
                           achievements, last_active, registration_time,
                           daily_bonus_claimed, last_bonus_time, ban_status,
                           ban_reason, ban_until, equipped_achievement
                    FROM players
                """)
                
                rows = await cursor.fetchall()
                players = []
                
                for row in rows:
                    players.append({
                        'player_id': row[0],
                        'display_name': row[1],
                        'chips': row[2],
                        'level': row[3],
                        'experience': row[4],
                        'total_games': row[5],
                        'wins': row[6],
                        'losses': row[7],
                        'total_profit': row[8],
                        'best_hand': row[9],
                        'achievements': json.loads(row[10]) if row[10] else [],
                        'last_active': row[11],
                        'registration_time': row[12],
                        'daily_bonus_claimed': bool(row[13]),
                        'last_bonus_time': row[14],
                        'ban_status': bool(row[15]),
                        'ban_reason': row[16],
                        'ban_until': row[17],
                        'equipped_achievement': row[18]
                    })
                
                return players
                
        except Exception as e:
            logger.error(f"加载所有玩家数据失败: {e}")
            return []
    
    # ==================== 玩家统计操作 ====================
    
    async def save_player_stats(self, player_id: str, stats_data: Dict[str, Any]) -> bool:
        """
        保存玩家统计数据
        
        Args:
            player_id: 玩家ID
            stats_data: 统计数据字典
            
        Returns:
            bool: 是否成功
        """
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # 转换JSON字段
                hand_type_wins_json = json.dumps(stats_data.get('hand_type_wins', {}))
                position_stats_json = json.dumps(stats_data.get('position_stats', {}))
                recent_games_json = json.dumps(stats_data.get('recent_games', []))
                
                await db.execute("""
                    INSERT OR REPLACE INTO player_stats (
                        player_id, hand_type_wins, position_stats, recent_games,
                        longest_winning_streak, longest_losing_streak, current_streak,
                        biggest_win, biggest_loss, favorite_hand, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    player_id,
                    hand_type_wins_json,
                    position_stats_json,
                    recent_games_json,
                    stats_data.get('longest_winning_streak', 0),
                    stats_data.get('longest_losing_streak', 0),
                    stats_data.get('current_streak', 0),
                    stats_data.get('biggest_win', 0),
                    stats_data.get('biggest_loss', 0),
                    stats_data.get('favorite_hand'),
                    time.time()
                ))
                
                await db.commit()
                return True
                
        except Exception as e:
            logger.error(f"保存玩家统计失败 {player_id}: {e}")
            return False
    
    async def get_player_stats(self, player_id: str) -> Dict[str, Any]:
        """
        获取玩家统计数据
        
        Args:
            player_id: 玩家ID
            
        Returns:
            Dict: 统计数据字典
        """
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute("""
                    SELECT hand_type_wins, position_stats, recent_games,
                           longest_winning_streak, longest_losing_streak, current_streak,
                           biggest_win, biggest_loss, favorite_hand
                    FROM player_stats WHERE player_id = ?
                """, (player_id,))
                
                row = await cursor.fetchone()
                
                if row:
                    return {
                        'hand_type_wins': json.loads(row[0]) if row[0] else {},
                        'position_stats': json.loads(row[1]) if row[1] else {},
                        'recent_games': json.loads(row[2]) if row[2] else [],
                        'longest_winning_streak': row[3],
                        'longest_losing_streak': row[4],
                        'current_streak': row[5],
                        'biggest_win': row[6],
                        'biggest_loss': row[7],
                        'favorite_hand': row[8]
                    }
                
                return {}
                
        except Exception as e:
            logger.error(f"获取玩家统计失败 {player_id}: {e}")
            return {}
    
    async def reset_player_stats(self, player_id: str) -> bool:
        """
        重置玩家统计数据
        
        Args:
            player_id: 玩家ID
            
        Returns:
            bool: 是否成功
        """
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("DELETE FROM player_stats WHERE player_id = ?", (player_id,))
                await db.execute("DELETE FROM achievements WHERE player_id = ?", (player_id,))
                await db.commit()
                return True
                
        except Exception as e:
            logger.error(f"重置玩家统计失败 {player_id}: {e}")
            return False
    
    # ==================== 交易记录操作 ====================
    
    async def log_transaction(self, player_id: str, amount: int, balance_before: int, 
                             balance_after: int, reason: str, transaction_type: str = "chips") -> bool:
        """
        记录交易日志
        
        Args:
            player_id: 玩家ID
            amount: 交易金额
            balance_before: 交易前余额
            balance_after: 交易后余额
            reason: 交易原因
            transaction_type: 交易类型
            
        Returns:
            bool: 是否成功
        """
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    INSERT INTO transactions (
                        player_id, amount, balance_before, balance_after,
                        transaction_type, reason, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    player_id, amount, balance_before, balance_after,
                    transaction_type, reason, time.time()
                ))
                
                await db.commit()
                return True
                
        except Exception as e:
            logger.error(f"记录交易日志失败: {e}")
            return False
    
    async def get_player_transactions(self, player_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        获取玩家交易记录
        
        Args:
            player_id: 玩家ID
            limit: 记录数量限制
            
        Returns:
            List[Dict]: 交易记录列表
        """
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute("""
                    SELECT transaction_id, amount, balance_before, balance_after,
                           transaction_type, reason, created_at
                    FROM transactions 
                    WHERE player_id = ? 
                    ORDER BY created_at DESC 
                    LIMIT ?
                """, (player_id, limit))
                
                rows = await cursor.fetchall()
                transactions = []
                
                for row in rows:
                    transactions.append({
                        'transaction_id': row[0],
                        'amount': row[1],
                        'balance_before': row[2],
                        'balance_after': row[3],
                        'transaction_type': row[4],
                        'reason': row[5],
                        'created_at': row[6]
                    })
                
                return transactions
                
        except Exception as e:
            logger.error(f"获取玩家交易记录失败 {player_id}: {e}")
            return []
    
    # ==================== 游戏记录操作 ====================
    
    async def save_game_record(self, room_id: str, game_data: Dict[str, Any]) -> bool:
        """
        保存游戏记录
        
        Args:
            room_id: 房间ID
            game_data: 游戏数据
            
        Returns:
            bool: 是否成功
        """
        try:
            async with aiosqlite.connect(self.db_path) as db:
                players_json = json.dumps(game_data.get('players', []))
                hand_results_json = json.dumps(game_data.get('hand_results', {}))
                
                await db.execute("""
                    INSERT INTO game_records (
                        room_id, game_type, players, winner_id,
                        game_duration, final_pot, hand_results, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    room_id,
                    game_data.get('game_type', 'texas_holdem'),
                    players_json,
                    game_data.get('winner_id'),
                    game_data.get('game_duration', 0),
                    game_data.get('final_pot', 0),
                    hand_results_json,
                    time.time()
                ))
                
                await db.commit()
                return True
                
        except Exception as e:
            logger.error(f"保存游戏记录失败: {e}")
            return False
    
    # ==================== 统计查询 ====================
    
    async def get_system_stats(self) -> Dict[str, Any]:
        """
        获取系统统计信息
        
        Returns:
            Dict: 统计信息
        """
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # 总玩家数
                cursor = await db.execute("SELECT COUNT(*) FROM players")
                total_players = (await cursor.fetchone())[0]
                
                # 活跃玩家数（最近7天）
                week_ago = time.time() - 7 * 24 * 3600
                cursor = await db.execute("SELECT COUNT(*) FROM players WHERE last_active > ?", (week_ago,))
                active_players = (await cursor.fetchone())[0]
                
                # 总游戏局数
                cursor = await db.execute("SELECT COUNT(*) FROM game_records")
                total_games = (await cursor.fetchone())[0]
                
                # 总筹码流通
                cursor = await db.execute("SELECT SUM(chips) FROM players WHERE chips > 0")
                result = await cursor.fetchone()
                total_chips = result[0] if result[0] else 0
                
                # 封禁玩家数（包括临时和永久封禁，但排除已过期的临时封禁）
                current_time = time.time()
                cursor = await db.execute("""
                    SELECT COUNT(*) FROM players 
                    WHERE ban_status = 1 
                    AND (ban_until = 0 OR ban_until > ?)
                """, (current_time,))
                banned_players = (await cursor.fetchone())[0]
                
                # 今日新增玩家数
                today_start = current_time - (current_time % 86400)  # 今天开始的时间戳
                cursor = await db.execute("SELECT COUNT(*) FROM players WHERE registration_time > ?", (today_start,))
                today_new_players = (await cursor.fetchone())[0]
                
                # 总盈亏
                cursor = await db.execute("SELECT SUM(total_profit) FROM players")
                result = await cursor.fetchone()
                total_profit = result[0] if result[0] else 0
                
                return {
                    'total_players': total_players,
                    'active_players': active_players,
                    'today_new_players': today_new_players,
                    'total_games': total_games,
                    'total_chips': total_chips,
                    'total_profit': total_profit,
                    'banned_players': banned_players,
                    'database_path': str(self.db_path)
                }
                
        except Exception as e:
            logger.error(f"获取系统统计失败: {e}")
            return {
                'total_players': 0,
                'active_players': 0,
                'today_new_players': 0,
                'total_games': 0,
                'total_chips': 0,
                'total_profit': 0,
                'banned_players': 0,
                'database_path': str(self.db_path)
            }
    
    async def backup_database(self, backup_path: Path) -> bool:
        """
        备份数据库
        
        Args:
            backup_path: 备份文件路径
            
        Returns:
            bool: 是否成功
        """
        try:
            import shutil
            
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(self.db_path, backup_path)
            
            logger.info(f"数据库备份完成: {backup_path}")
            return True
            
        except Exception as e:
            logger.error(f"数据库备份失败: {e}")
            return False
    
    async def close(self):
        """关闭数据库连接"""
        logger.info("数据库连接已关闭")
