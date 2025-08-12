"""
User profile and wallet storage service with performance optimizations.
"""
import sqlite3
import time
import logging
from pathlib import Path
from typing import List, Tuple, Optional, Dict
import threading
from contextlib import contextmanager

from ..config import get_data_dir

logger = logging.getLogger(__name__)

class ConnectionPool:
    """Simple connection pool for SQLite to improve performance."""
    
    def __init__(self, db_path: Path, pool_size: int = 5):
        self.db_path = db_path
        self.pool_size = pool_size
        self.pool: List[sqlite3.Connection] = []
        self.lock = threading.Lock()
        self._init_pool()
    
    def _init_pool(self):
        """Initialize connection pool."""
        for _ in range(self.pool_size):
            conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            conn.execute("PRAGMA journal_mode=WAL")  # Better concurrency
            conn.execute("PRAGMA synchronous=NORMAL")  # Better performance
            conn.execute("PRAGMA cache_size=10000")  # Larger cache
            conn.execute("PRAGMA temp_store=MEMORY")  # Use memory for temp tables
            self.pool.append(conn)
    
    @contextmanager
    def get_connection(self):
        """Get a connection from the pool."""
        with self.lock:
            if self.pool:
                conn = self.pool.pop()
            else:
                # Pool exhausted, create temporary connection
                conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
                conn.execute("PRAGMA journal_mode=WAL")
                logger.warning("Connection pool exhausted, created temporary connection")
        
        try:
            yield conn
        finally:
            with self.lock:
                if len(self.pool) < self.pool_size:
                    self.pool.append(conn)
                else:
                    conn.close()

class ProfileService:
    """Enhanced profile service with performance optimizations."""
    
    def __init__(self):
        self.data_dir = get_data_dir()
        self.db_path = self.data_dir / "profiles.db"
        self.connection_pool = None
        self._stats = {
            'total_wallets': 0,
            'total_users': 0,
            'operations_count': 0
        }
        self._init_database()
    
    def _init_database(self):
        """Initialize database with optimized schema."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # Create connection pool
        self.connection_pool = ConnectionPool(self.db_path)
        
        with self.connection_pool.get_connection() as conn:
            # Create wallets table with indexes
            conn.execute("""
                CREATE TABLE IF NOT EXISTS wallets (
                    user_id INTEGER NOT NULL,
                    chain TEXT NOT NULL,
                    address TEXT NOT NULL,
                    derivation_path TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    PRIMARY KEY (user_id, chain, address)
                )
            """)
            
            # Create indexes for better query performance
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_user_chain 
                ON wallets(user_id, chain)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_created_at 
                ON wallets(created_at DESC)
            """)
            
            # Create user statistics table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_stats (
                    user_id INTEGER PRIMARY KEY,
                    total_wallets INTEGER DEFAULT 0,
                    first_wallet_at INTEGER,
                    last_wallet_at INTEGER,
                    favorite_chain TEXT
                )
            """)
            
            conn.commit()
        
        logger.info(f"Database initialized at {self.db_path}")
        self._update_stats()
    
    async def add_wallet(self, user_id: int, chain: str, address: str, derivation_path: str) -> bool:
        """Add wallet to user profile with statistics update."""
        try:
            current_time = int(time.time())
            
            with self.connection_pool.get_connection() as conn:
                # Insert wallet
                conn.execute("""
                    INSERT OR IGNORE INTO wallets 
                    (user_id, chain, address, derivation_path, created_at) 
                    VALUES (?, ?, ?, ?, ?)
                """, (user_id, chain, address, derivation_path, current_time))
                
                # Update user statistics
                conn.execute("""
                    INSERT OR REPLACE INTO user_stats 
                    (user_id, total_wallets, first_wallet_at, last_wallet_at, favorite_chain)
                    VALUES (
                        ?, 
                        (SELECT COUNT(*) FROM wallets WHERE user_id = ?),
                        COALESCE((SELECT first_wallet_at FROM user_stats WHERE user_id = ?), ?),
                        ?,
                        (SELECT chain FROM wallets WHERE user_id = ? GROUP BY chain ORDER BY COUNT(*) DESC LIMIT 1)
                    )
                """, (user_id, user_id, user_id, current_time, current_time, user_id))
                
                conn.commit()
                
            self._stats['operations_count'] += 1
            logger.debug(f"Added wallet for user {user_id}: {chain} {address[:10]}...")
            return True
            
        except Exception as e:
            logger.error(f"Failed to add wallet for user {user_id}: {e}")
            return False
    
    async def add_wallets_bulk(self, user_id: int, wallets: List[Tuple[str, str, str]]) -> int:
        """Add multiple wallets efficiently using bulk operations."""
        if not wallets:
            return 0
        
        try:
            current_time = int(time.time())
            
            with self.connection_pool.get_connection() as conn:
                # Bulk insert wallets
                wallet_data = [
                    (user_id, chain, address, derivation_path, current_time)
                    for chain, address, derivation_path in wallets
                ]
                
                conn.executemany("""
                    INSERT OR IGNORE INTO wallets 
                    (user_id, chain, address, derivation_path, created_at) 
                    VALUES (?, ?, ?, ?, ?)
                """, wallet_data)
                
                # Update user statistics
                conn.execute("""
                    INSERT OR REPLACE INTO user_stats 
                    (user_id, total_wallets, first_wallet_at, last_wallet_at, favorite_chain)
                    VALUES (
                        ?, 
                        (SELECT COUNT(*) FROM wallets WHERE user_id = ?),
                        COALESCE((SELECT first_wallet_at FROM user_stats WHERE user_id = ?), ?),
                        ?,
                        (SELECT chain FROM wallets WHERE user_id = ? GROUP BY chain ORDER BY COUNT(*) DESC LIMIT 1)
                    )
                """, (user_id, user_id, user_id, current_time, current_time, user_id))
                
                conn.commit()
                
            inserted_count = len(wallets)
            self._stats['operations_count'] += 1
            logger.info(f"Bulk added {inserted_count} wallets for user {user_id}")
            return inserted_count
            
        except Exception as e:
            logger.error(f"Failed to bulk add wallets for user {user_id}: {e}")
            return 0
    
    async def get_wallets(self, user_id: int, chain: Optional[str] = None, limit: int = 1000) -> List[Tuple[str, str, str, int]]:
        """Get user wallets with optional chain filter and limit."""
        try:
            with self.connection_pool.get_connection() as conn:
                if chain:
                    cursor = conn.execute("""
                        SELECT chain, address, derivation_path, created_at 
                        FROM wallets 
                        WHERE user_id = ? AND chain = ? 
                        ORDER BY created_at DESC 
                        LIMIT ?
                    """, (user_id, chain, limit))
                else:
                    cursor = conn.execute("""
                        SELECT chain, address, derivation_path, created_at 
                        FROM wallets 
                        WHERE user_id = ? 
                        ORDER BY created_at DESC 
                        LIMIT ?
                    """, (user_id, limit))
                
                return cursor.fetchall()
                
        except Exception as e:
            logger.error(f"Failed to get wallets for user {user_id}: {e}")
            return []
    
    async def get_wallet_counts_by_chain(self, user_id: int) -> Dict[str, int]:
        """Get wallet counts grouped by chain for a user."""
        try:
            with self.connection_pool.get_connection() as conn:
                cursor = conn.execute("""
                    SELECT chain, COUNT(*) as count 
                    FROM wallets 
                    WHERE user_id = ? 
                    GROUP BY chain 
                    ORDER BY count DESC
                """, (user_id,))
                
                return dict(cursor.fetchall())
                
        except Exception as e:
            logger.error(f"Failed to get wallet counts for user {user_id}: {e}")
            return {}
    
    async def clear_user_wallets(self, user_id: int) -> int:
        """Clear all wallets for a user and return count deleted."""
        try:
            with self.connection_pool.get_connection() as conn:
                cursor = conn.execute("DELETE FROM wallets WHERE user_id = ?", (user_id,))
                conn.execute("DELETE FROM user_stats WHERE user_id = ?", (user_id,))
                conn.commit()
                
                deleted_count = cursor.rowcount
                logger.info(f"Cleared {deleted_count} wallets for user {user_id}")
                return deleted_count
                
        except Exception as e:
            logger.error(f"Failed to clear wallets for user {user_id}: {e}")
            return 0
    
    async def get_user_stats(self, user_id: int) -> Dict:
        """Get detailed statistics for a user."""
        try:
            with self.connection_pool.get_connection() as conn:
                # Get user stats
                cursor = conn.execute("""
                    SELECT total_wallets, first_wallet_at, last_wallet_at, favorite_chain 
                    FROM user_stats 
                    WHERE user_id = ?
                """, (user_id,))
                
                stats = cursor.fetchone()
                if not stats:
                    return {'total_wallets': 0}
                
                total_wallets, first_wallet_at, last_wallet_at, favorite_chain = stats
                
                # Get chain breakdown
                cursor = conn.execute("""
                    SELECT chain, COUNT(*) as count 
                    FROM wallets 
                    WHERE user_id = ? 
                    GROUP BY chain 
                    ORDER BY count DESC
                """, (user_id,))
                
                chain_counts = dict(cursor.fetchall())
                
                return {
                    'total_wallets': total_wallets,
                    'first_wallet_at': first_wallet_at,
                    'last_wallet_at': last_wallet_at,
                    'favorite_chain': favorite_chain,
                    'chain_counts': chain_counts
                }
                
        except Exception as e:
            logger.error(f"Failed to get user stats for {user_id}: {e}")
            return {'total_wallets': 0}
    
    def _update_stats(self):
        """Update internal statistics."""
        try:
            with self.connection_pool.get_connection() as conn:
                # Total wallets
                cursor = conn.execute("SELECT COUNT(*) FROM wallets")
                self._stats['total_wallets'] = cursor.fetchone()[0]
                
                # Total users
                cursor = conn.execute("SELECT COUNT(DISTINCT user_id) FROM wallets")
                self._stats['total_users'] = cursor.fetchone()[0]
                
        except Exception as e:
            logger.error(f"Failed to update stats: {e}")
    
    def get_service_stats(self) -> Dict:
        """Get service-wide statistics."""
        self._update_stats()
        return self._stats.copy()
    
    async def search_wallets(self, user_id: int, query: str) -> List[Tuple[str, str, str, int]]:
        """Search user wallets by address or chain."""
        try:
            with self.connection_pool.get_connection() as conn:
                cursor = conn.execute("""
                    SELECT chain, address, derivation_path, created_at 
                    FROM wallets 
                    WHERE user_id = ? AND (
                        address LIKE ? OR 
                        chain LIKE ?
                    )
                    ORDER BY created_at DESC 
                    LIMIT 100
                """, (user_id, f"%{query}%", f"%{query.upper()}%"))
                
                return cursor.fetchall()
                
        except Exception as e:
            logger.error(f"Failed to search wallets for user {user_id}: {e}")
            return []