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
        
        # 表结构版本
        self.schema_version = 1
        
        # 持久数据库连接
        self.db_connection = None
        self.connection_lock = asyncio.Lock()
        
    async def initialize(self):
        """
        初始化数据库
        
        创建必要的表结构并建立持久连接
        """
        try:
            logger.info(f"🔧 开始初始化数据库: {self.db_path}")
            
            async with self.connection_lock:
                # 创建持久连接
                logger.info("📡 正在建立数据库连接...")
                self.db_connection = await aiosqlite.connect(str(self.db_path))
                self.db_connection.row_factory = aiosqlite.Row
                logger.info("✅ 数据库连接已建立")
                
                # 设置数据库配置
                logger.info("⚙️ 配置数据库参数...")
                await self.db_connection.execute("PRAGMA foreign_keys = ON")
                await self.db_connection.execute("PRAGMA journal_mode = WAL")
                await self.db_connection.execute("PRAGMA synchronous = NORMAL")
                await self.db_connection.execute("PRAGMA busy_timeout = 30000")  # 30秒超时
                logger.info("✅ 数据库参数配置完成")
                
                # 创建表
                logger.info("🏗️ 创建数据表...")
                await self._create_tables(self.db_connection)
                logger.info("✅ 数据表创建完成")
                
                # 检查和更新数据库版本
                logger.info("🔍 检查数据库版本...")
                await self._check_schema_version(self.db_connection)
                logger.info("✅ 数据库版本检查完成")
                
                await self.db_connection.commit()
                logger.info("💾 数据库事务提交完成")
                
            # 验证连接状态
            if self.db_connection:
                logger.info("✅ 数据库连接验证成功")
            else:
                raise Exception("数据库连接为空")
                
            logger.info(f"🎉 数据库初始化完成: {self.db_path}")
            
        except Exception as e:
            logger.error(f"💥 数据库初始化失败: {e}")
            logger.error(f"数据库路径: {self.db_path}")
            
            import traceback
            logger.error("完整错误栈:")
            logger.error(traceback.format_exc())
            
            if self.db_connection:
                try:
                    await self.db_connection.close()
                    logger.info("🧹 数据库连接已关闭")
                except:
                    pass
                self.db_connection = None
            raise
    
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
    
    # ==================== 连接管理 ====================
    
    async def _get_connection(self) -> aiosqlite.Connection:
        """
        获取持久数据库连接，如果连接不存在则自动初始化
        
        Returns:
            aiosqlite.Connection: 数据库连接
            
        Raises:
            RuntimeError: 如果连接初始化失败
        """
        if not self.db_connection:
            logger.warning("🔄 数据库连接未找到，尝试重新初始化...")
            try:
                await self.initialize()
                logger.info("✅ 数据库连接重新初始化成功")
                
                # 验证连接是否真正可用
                await self.db_connection.execute("SELECT 1")
                logger.info("✅ 数据库连接验证成功")
            except Exception as e:
                logger.error(f"❌ 数据库连接重新初始化失败: {e}")
                # 尝试强制重新创建连接
                try:
                    self.db_connection = None
                    await self.initialize()
                    logger.info("✅ 强制重新创建数据库连接成功")
                except Exception as retry_e:
                    logger.error(f"❌ 强制重新创建连接也失败: {retry_e}")
                    raise RuntimeError("数据库连接完全失败") from retry_e
        
        # 验证连接是否仍然有效
        try:
            await self.db_connection.execute("SELECT 1")
        except Exception as e:
            logger.warning(f"🔄 数据库连接验证失败，尝试重新连接: {e}")
            try:
                # 安全关闭旧连接
                if self.db_connection:
                    try:
                        await self.db_connection.close()
                        logger.info("✅ 旧数据库连接已关闭")
                    except:
                        logger.warning("⚠️ 关闭旧连接时出现问题，继续创建新连接")
                
                # 重置连接并重新初始化
                self.db_connection = None
                await self.initialize()
                logger.info("✅ 数据库连接重连成功")
                
                # 再次验证新连接
                await self.db_connection.execute("SELECT 1")
                logger.info("✅ 新连接验证成功")
            except Exception as re_e:
                logger.error(f"❌ 数据库重连失败: {re_e}")
                raise RuntimeError("数据库连接重连失败") from re_e
                
        return self.db_connection
    
    async def _execute_with_retry(self, operation, max_retries: int = 3):
        """
        带重试机制的数据库操作
        
        Args:
            operation: 数据库操作函数
            max_retries: 最大重试次数
            
        Returns:
            操作结果
        """
        last_error = None
        
        for attempt in range(max_retries):
            try:
                async with self.connection_lock:
                    db = await self._get_connection()
                    return await operation(db)
                    
            except Exception as e:
                last_error = e
                logger.warning(f"数据库操作失败，尝试 {attempt + 1}/{max_retries}: {e}")
                
                # 如果是连接问题，尝试重新建立连接
                if "database is locked" in str(e) or "no such table" in str(e):
                    await asyncio.sleep(0.1 * (attempt + 1))  # 递增延迟
                    continue
                else:
                    break
        
        # 如果所有重试都失败，抛出最后的错误
        raise last_error
    
    # ==================== 辅助方法 ====================
    
    def _row_to_player_dict(self, row) -> Dict[str, Any]:
        """
        将数据库行转换为玩家信息字典
        
        Args:
            row: 数据库查询结果行
            
        Returns:
            Dict: 玩家信息字典
        """
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
            'achievements': self._safe_json_loads(row[10], []),
            'last_active': row[11],
            'registration_time': row[12],
            'daily_bonus_claimed': bool(row[13]),
            'last_bonus_time': row[14],
            'ban_status': bool(row[15]),
            'ban_reason': row[16],
            'ban_until': row[17],
            'equipped_achievement': row[18]
        }
    
    def _safe_json_loads(self, json_str: str, default_value):
        """
        安全的JSON反序列化
        
        Args:
            json_str: JSON字符串
            default_value: 默认值
            
        Returns:
            反序列化后的对象或默认值
        """
        if not json_str:
            return default_value
        
        try:
            result = json.loads(json_str)
            # 类型检查：确保返回值类型与默认值类型一致
            if type(result) != type(default_value):
                logger.warning(f"JSON反序列化类型不匹配，期望 {type(default_value)}，实际 {type(result)}")
                return default_value
            return result
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning(f"JSON反序列化失败: {e}, 使用默认值: {default_value}")
            return default_value

    # ==================== 玩家数据操作 ====================
    
    async def batch_save_players(self, players_data: List[Dict[str, Any]]) -> bool:
        """
        批量保存玩家数据，解决 N+1 问题
        
        Args:
            players_data: 玩家数据列表
            
        Returns:
            bool: 是否成功
        """
        if not players_data:
            return True
            
        async def _batch_save_operation(db: aiosqlite.Connection) -> bool:
            # 构建批量插入语句
            sql = """
                INSERT OR REPLACE INTO players (
                    player_id, display_name, chips, level, experience,
                    total_games, wins, losses, total_profit, best_hand,
                    achievements, last_active, registration_time,
                    daily_bonus_claimed, last_bonus_time, ban_status,
                    ban_reason, ban_until, equipped_achievement, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            
            # 准备批量数据
            batch_data = []
            current_time = time.time()
            
            for player_data in players_data:
                achievements_json = json.dumps(player_data.get('achievements', []))
                
                batch_data.append((
                    player_data.get('player_id'),
                    player_data.get('display_name', ''),
                    player_data.get('chips', 3000),
                    player_data.get('level', 1),
                    player_data.get('experience', 0),
                    player_data.get('total_games', 0),
                    player_data.get('wins', 0),
                    player_data.get('losses', 0),
                    player_data.get('total_profit', 0),
                    player_data.get('best_hand'),
                    achievements_json,
                    player_data.get('last_active', current_time),
                    player_data.get('registration_time', current_time),
                    1 if player_data.get('daily_bonus_claimed', False) else 0,
                    player_data.get('last_bonus_time', 0),
                    1 if player_data.get('ban_status', False) else 0,
                    player_data.get('ban_reason', ''),
                    player_data.get('ban_until', 0),
                    player_data.get('equipped_achievement', ''),
                    current_time
                ))
            
            # 执行批量插入
            await db.executemany(sql, batch_data)
            await db.commit()
            
            logger.info(f"批量保存 {len(batch_data)} 个玩家数据")
            return True
        
        try:
            result = await self._execute_with_retry(_batch_save_operation)
            logger.info(f"✅ 批量保存 {len(players_data)} 个玩家数据成功")
            return result
        except Exception as e:
            logger.error(f"💥 批量保存玩家数据失败: {e}")
            logger.error(f"数据库连接状态: {self.db_connection}")
            
            # 尝试重新初始化数据库连接
            try:
                logger.info("🔄 尝试重新初始化数据库连接...")
                await self.initialize()
                logger.info("✅ 数据库连接重新初始化成功，重试批量保存...")
                result = await self._execute_with_retry(_batch_save_operation)
                logger.info(f"✅ 重试后批量保存成功")
                return result
            except Exception as retry_e:
                logger.error(f"💥 重试批量保存也失败了: {retry_e}")
                return False
    
    async def save_player_data(self, player_id: str, player_data: Dict[str, Any]) -> bool:
        """
        保存玩家数据
        
        Args:
            player_id: 玩家ID
            player_data: 玩家数据字典
            
        Returns:
            bool: 是否成功
        """
        async def _save_operation(db: aiosqlite.Connection) -> bool:
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
                player_data.get('chips', 3000),
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
        
        try:
            result = await self._execute_with_retry(_save_operation)
            return result
        except Exception as e:
            logger.error(f"💥 保存玩家数据失败 {player_id}: {e}")
            
            # 尝试重新初始化数据库连接
            try:
                logger.info("🔄 尝试重新初始化数据库连接...")
                await self.initialize()
                result = await self._execute_with_retry(_save_operation)
                logger.info(f"✅ 重试后保存玩家数据成功: {player_id}")
                return result
            except Exception as retry_e:
                logger.error(f"💥 重试保存玩家数据也失败了 {player_id}: {retry_e}")
                return False
    
    async def get_player_data(self, player_id: str) -> Optional[Dict[str, Any]]:
        """
        获取玩家数据
        
        Args:
            player_id: 玩家ID
            
        Returns:
            Optional[Dict]: 玩家数据字典
        """
        async def _get_operation(db: aiosqlite.Connection) -> Optional[Dict[str, Any]]:
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
                return self._row_to_player_dict(row)
            
            return None
        
        try:
            return await self._execute_with_retry(_get_operation)
        except Exception as e:
            logger.error(f"获取玩家数据失败 {player_id}: {e}")
            return None
    
    async def load_all_players(self) -> List[Dict[str, Any]]:
        """
        加载所有玩家数据
        
        Returns:
            List[Dict]: 玩家数据列表
        """
        async def _load_operation(db: aiosqlite.Connection) -> List[Dict[str, Any]]:
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
                players.append(self._row_to_player_dict(row))
            
            return players
        
        try:
            return await self._execute_with_retry(_load_operation)
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
        async def _save_stats_operation(db: aiosqlite.Connection) -> bool:
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
        
        try:
            return await self._execute_with_retry(_save_stats_operation)
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
        async def _get_stats_operation(db: aiosqlite.Connection) -> Dict[str, Any]:
            cursor = await db.execute("""
                SELECT hand_type_wins, position_stats, recent_games,
                       longest_winning_streak, longest_losing_streak, current_streak,
                       biggest_win, biggest_loss, favorite_hand
                FROM player_stats WHERE player_id = ?
            """, (player_id,))
            
            row = await cursor.fetchone()
            
            if row:
                # 安全的JSON反序列化
                hand_type_wins = {}
                position_stats = {}
                recent_games = []
                
                hand_type_wins = self._safe_json_loads(row[0], {})
                position_stats = self._safe_json_loads(row[1], {})
                recent_games = self._safe_json_loads(row[2], [])
                
                return {
                    'hand_type_wins': hand_type_wins,
                    'position_stats': position_stats,
                    'recent_games': recent_games,
                    'longest_winning_streak': row[3],
                    'longest_losing_streak': row[4],
                    'current_streak': row[5],
                    'biggest_win': row[6],
                    'biggest_loss': row[7],
                    'favorite_hand': row[8]
                }
            
            return {}
        
        try:
            return await self._execute_with_retry(_get_stats_operation)
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
        async def _reset_stats_operation(db: aiosqlite.Connection) -> bool:
            await db.execute("DELETE FROM player_stats WHERE player_id = ?", (player_id,))
            await db.execute("DELETE FROM achievements WHERE player_id = ?", (player_id,))
            await db.commit()
            return True
        
        try:
            return await self._execute_with_retry(_reset_stats_operation)
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
        async def _log_transaction_operation(db: aiosqlite.Connection) -> bool:
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
        
        try:
            result = await self._execute_with_retry(_log_transaction_operation)
            return result
        except Exception as e:
            logger.error(f"💥 记录交易日志失败: {e}")
            
            # 尝试重新初始化数据库连接
            try:
                logger.info("🔄 尝试重新初始化数据库连接...")
                await self.initialize()
                result = await self._execute_with_retry(_log_transaction_operation)
                logger.info(f"✅ 重试后交易日志记录成功: {player_id}")
                return result
            except Exception as retry_e:
                logger.error(f"💥 重试记录交易日志也失败了: {retry_e}")
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
        async def _get_transactions_operation(db: aiosqlite.Connection) -> List[Dict[str, Any]]:
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
        
        try:
            return await self._execute_with_retry(_get_transactions_operation)
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
        async def _save_game_record_operation(db: aiosqlite.Connection) -> bool:
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
        
        try:
            return await self._execute_with_retry(_save_game_record_operation)
        except Exception as e:
            logger.error(f"保存游戏记录失败: {e}")
            return False
    
    # ==================== 玩家查询操作 ====================
    
    async def search_players_by_prefix(self, prefix: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        通过前缀搜索玩家（数据库层面优化）
        
        Args:
            prefix: 玩家ID前缀
            limit: 返回结果数量限制
            
        Returns:
            List[Dict]: 匹配的玩家数据列表
        """
        async def _search_operation(db: aiosqlite.Connection) -> List[Dict[str, Any]]:
            cursor = await db.execute("""
                SELECT player_id, display_name, chips, level, experience,
                       total_games, wins, losses, total_profit, best_hand,
                       achievements, last_active, registration_time,
                       daily_bonus_claimed, last_bonus_time, ban_status,
                       ban_reason, ban_until, equipped_achievement
                FROM players 
                WHERE player_id LIKE ? 
                ORDER BY last_active DESC
                LIMIT ?
            """, (f"{prefix}%", limit))
            
            rows = await cursor.fetchall()
            players = []
            
            for row in rows:
                players.append(self._row_to_player_dict(row))
            
            return players
        
        try:
            return await self._execute_with_retry(_search_operation)
        except Exception as e:
            logger.error(f"搜索玩家失败 {prefix}: {e}")
            return []
    
    async def get_players_by_ids(self, player_ids: List[str]) -> List[Dict[str, Any]]:
        """
        批量获取多个玩家信息
        
        Args:
            player_ids: 玩家ID列表
            
        Returns:
            List[Dict]: 玩家数据列表
        """
        if not player_ids:
            return []
            
        async def _batch_get_operation(db: aiosqlite.Connection) -> List[Dict[str, Any]]:
            # 构建 IN 查询
            placeholders = ','.join('?' * len(player_ids))
            cursor = await db.execute(f"""
                SELECT player_id, display_name, chips, level, experience,
                       total_games, wins, losses, total_profit, best_hand,
                       achievements, last_active, registration_time,
                       daily_bonus_claimed, last_bonus_time, ban_status,
                       ban_reason, ban_until, equipped_achievement
                FROM players 
                WHERE player_id IN ({placeholders})
            """, player_ids)
            
            rows = await cursor.fetchall()
            players = []
            
            for row in rows:
                players.append(self._row_to_player_dict(row))
            
            return players
        
        try:
            return await self._execute_with_retry(_batch_get_operation)
        except Exception as e:
            logger.error(f"批量获取玩家失败: {e}")
            return []
    
    # ==================== 统计查询 ====================
    
    async def get_system_stats(self) -> Dict[str, Any]:
        """
        获取系统统计信息
        
        Returns:
            Dict: 统计信息
        """
        async def _stats_operation(db: aiosqlite.Connection) -> Dict[str, Any]:
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
        
        try:
            return await self._execute_with_retry(_stats_operation)
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
            
            # 在线程池中执行同步操作，避免阻塞事件循环
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            await asyncio.to_thread(shutil.copy2, self.db_path, backup_path)
            
            logger.info(f"数据库备份完成: {backup_path}")
            return True
            
        except Exception as e:
            logger.error(f"数据库备份失败: {e}")
            return False
    
    async def close(self):
        """
        关闭数据库连接
        
        关闭持久连接并清理资源
        """
        async with self.connection_lock:
            if self.db_connection:
                try:
                    await self.db_connection.close()
                    self.db_connection = None
                    logger.info("数据库连接已关闭")
                except Exception as e:
                    logger.error(f"关闭数据库连接失败: {e}")
            else:
                logger.info("数据库管理器已关闭")
