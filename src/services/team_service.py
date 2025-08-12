"""
Enterprise team management service for multi-user wallet organizations.
"""
import time
import logging
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass
from enum import Enum
import sqlite3
from contextlib import contextmanager

from ..config import config
from .audit_service import audit_service, AuditEventType

logger = logging.getLogger(__name__)

class TeamRole(Enum):
    """Team member roles with different permissions."""
    OWNER = "owner"          # Full control, can manage team
    ADMIN = "admin"          # Can manage wallets and members
    MANAGER = "manager"      # Can manage wallets, view reports
    MEMBER = "member"        # Can generate wallets, view own data
    VIEWER = "viewer"        # Read-only access

class TeamPermission(Enum):
    """Granular permissions for team operations."""
    GENERATE_WALLETS = "generate_wallets"
    BULK_OPERATIONS = "bulk_operations"
    VIEW_TEAM_WALLETS = "view_team_wallets"
    MANAGE_MEMBERS = "manage_members"
    VIEW_REPORTS = "view_reports"
    ADMIN_FUNCTIONS = "admin_functions"

# Role-based permissions mapping
ROLE_PERMISSIONS = {
    TeamRole.OWNER: {
        TeamPermission.GENERATE_WALLETS,
        TeamPermission.BULK_OPERATIONS, 
        TeamPermission.VIEW_TEAM_WALLETS,
        TeamPermission.MANAGE_MEMBERS,
        TeamPermission.VIEW_REPORTS,
        TeamPermission.ADMIN_FUNCTIONS
    },
    TeamRole.ADMIN: {
        TeamPermission.GENERATE_WALLETS,
        TeamPermission.BULK_OPERATIONS,
        TeamPermission.VIEW_TEAM_WALLETS,
        TeamPermission.MANAGE_MEMBERS,
        TeamPermission.VIEW_REPORTS
    },
    TeamRole.MANAGER: {
        TeamPermission.GENERATE_WALLETS,
        TeamPermission.BULK_OPERATIONS,
        TeamPermission.VIEW_TEAM_WALLETS,
        TeamPermission.VIEW_REPORTS
    },
    TeamRole.MEMBER: {
        TeamPermission.GENERATE_WALLETS,
        TeamPermission.VIEW_TEAM_WALLETS
    },
    TeamRole.VIEWER: {
        TeamPermission.VIEW_TEAM_WALLETS
    }
}

@dataclass
class Team:
    """Team data structure."""
    id: int
    name: str
    description: str
    owner_id: int
    created_at: int
    max_members: int
    settings: Dict

@dataclass
class TeamMember:
    """Team member data structure."""
    team_id: int
    user_id: int
    role: TeamRole
    joined_at: int
    invited_by: int
    permissions: Set[TeamPermission]

class TeamService:
    """Enterprise team management service."""
    
    def __init__(self):
        self.enabled = config.ENABLE_TEAM_MANAGEMENT
        self.db_path = config.DATA_DIR / "teams.db" 
        self.max_team_size = config.MAX_TEAM_SIZE
        self._stats = {
            'total_teams': 0,
            'total_members': 0,
            'operations_count': 0
        }
        
        if self.enabled:
            self._init_database()
            self._update_stats()
    
    def _init_database(self) -> None:
        """Initialize team database schema."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        with sqlite3.connect(self.db_path) as conn:
            # Teams table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS teams (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    description TEXT,
                    owner_id INTEGER NOT NULL,
                    created_at INTEGER NOT NULL,
                    max_members INTEGER DEFAULT 10,
                    settings TEXT DEFAULT '{}',
                    is_active BOOLEAN DEFAULT 1
                )
            """)
            
            # Team members table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS team_members (
                    team_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    joined_at INTEGER NOT NULL,
                    invited_by INTEGER NOT NULL,
                    is_active BOOLEAN DEFAULT 1,
                    PRIMARY KEY (team_id, user_id),
                    FOREIGN KEY (team_id) REFERENCES teams (id) ON DELETE CASCADE
                )
            """)
            
            # Team wallets table (shared team wallet storage)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS team_wallets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    team_id INTEGER NOT NULL,
                    chain TEXT NOT NULL,
                    address TEXT NOT NULL,
                    derivation_path TEXT NOT NULL,
                    created_by INTEGER NOT NULL,
                    created_at INTEGER NOT NULL,
                    label TEXT,
                    tags TEXT,
                    FOREIGN KEY (team_id) REFERENCES teams (id) ON DELETE CASCADE
                )
            """)
            
            # Create indexes
            conn.execute("CREATE INDEX IF NOT EXISTS idx_team_members_user ON team_members(user_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_team_wallets_team ON team_wallets(team_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_team_wallets_chain ON team_wallets(chain)")
            
            conn.commit()
        
        logger.info(f"Team database initialized at {self.db_path}")
    
    async def create_team(
        self, 
        owner_id: int, 
        name: str, 
        description: str = "",
        max_members: int = None
    ) -> Optional[int]:
        """Create a new team."""
        if not self.enabled:
            return None
        
        max_members = max_members or self.max_team_size
        if max_members > self.max_team_size:
            max_members = self.max_team_size
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                # Create team
                cursor = conn.execute("""
                    INSERT INTO teams (name, description, owner_id, created_at, max_members)
                    VALUES (?, ?, ?, ?, ?)
                """, (name, description, owner_id, int(time.time()), max_members))
                
                team_id = cursor.lastrowid
                
                # Add owner as team member
                conn.execute("""
                    INSERT INTO team_members (team_id, user_id, role, joined_at, invited_by)
                    VALUES (?, ?, ?, ?, ?)
                """, (team_id, owner_id, TeamRole.OWNER.value, int(time.time()), owner_id))
                
                conn.commit()
            
            # Audit log
            audit_service.log_admin_action(
                owner_id, 
                "team_created", 
                team_id=team_id, 
                team_name=name
            )
            
            self._stats['total_teams'] += 1
            self._stats['total_members'] += 1
            self._stats['operations_count'] += 1
            
            logger.info(f"Team created: {name} (ID: {team_id}) by user {owner_id}")
            return team_id
            
        except sqlite3.IntegrityError:
            logger.warning(f"Team name '{name}' already exists")
            return None
        except Exception as e:
            logger.error(f"Failed to create team: {e}")
            return None
    
    async def add_team_member(
        self,
        team_id: int,
        user_id: int,
        role: TeamRole,
        invited_by: int
    ) -> bool:
        """Add a member to a team."""
        if not self.enabled:
            return False
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                # Check if team exists and has space
                cursor = conn.execute("""
                    SELECT max_members, 
                           (SELECT COUNT(*) FROM team_members WHERE team_id = ? AND is_active = 1) as current_members
                    FROM teams 
                    WHERE id = ? AND is_active = 1
                """, (team_id, team_id))
                
                result = cursor.fetchone()
                if not result:
                    return False
                
                max_members, current_members = result
                if current_members >= max_members:
                    logger.warning(f"Team {team_id} is full ({current_members}/{max_members})")
                    return False
                
                # Check if inviter has permission
                if not await self.check_permission(team_id, invited_by, TeamPermission.MANAGE_MEMBERS):
                    logger.warning(f"User {invited_by} lacks permission to add members to team {team_id}")
                    return False
                
                # Add member
                conn.execute("""
                    INSERT OR REPLACE INTO team_members 
                    (team_id, user_id, role, joined_at, invited_by, is_active)
                    VALUES (?, ?, ?, ?, ?, 1)
                """, (team_id, user_id, role.value, int(time.time()), invited_by))
                
                conn.commit()
            
            # Audit log
            audit_service.log_admin_action(
                invited_by,
                "member_added",
                team_id=team_id,
                new_member_id=user_id,
                role=role.value
            )
            
            self._stats['total_members'] += 1
            self._stats['operations_count'] += 1
            
            logger.info(f"Added user {user_id} to team {team_id} with role {role.value}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to add team member: {e}")
            return False
    
    async def remove_team_member(self, team_id: int, user_id: int, removed_by: int) -> bool:
        """Remove a member from a team."""
        if not self.enabled:
            return False
        
        try:
            # Check permissions
            if not await self.check_permission(team_id, removed_by, TeamPermission.MANAGE_MEMBERS):
                return False
            
            # Don't allow removing the owner
            member_role = await self.get_user_role(team_id, user_id)
            if member_role == TeamRole.OWNER:
                logger.warning("Cannot remove team owner")
                return False
            
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    UPDATE team_members 
                    SET is_active = 0 
                    WHERE team_id = ? AND user_id = ?
                """, (team_id, user_id))
                
                conn.commit()
            
            # Audit log
            audit_service.log_admin_action(
                removed_by,
                "member_removed",
                team_id=team_id,
                removed_member_id=user_id
            )
            
            self._stats['total_members'] -= 1
            self._stats['operations_count'] += 1
            
            logger.info(f"Removed user {user_id} from team {team_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to remove team member: {e}")
            return False
    
    async def get_user_teams(self, user_id: int) -> List[Dict]:
        """Get all teams a user belongs to."""
        if not self.enabled:
            return []
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("""
                    SELECT t.*, tm.role, tm.joined_at
                    FROM teams t
                    JOIN team_members tm ON t.id = tm.team_id
                    WHERE tm.user_id = ? AND tm.is_active = 1 AND t.is_active = 1
                    ORDER BY tm.joined_at DESC
                """, (user_id,))
                
                return [dict(row) for row in cursor.fetchall()]
                
        except Exception as e:
            logger.error(f"Failed to get user teams: {e}")
            return []
    
    async def get_team_members(self, team_id: int) -> List[Dict]:
        """Get all members of a team."""
        if not self.enabled:
            return []
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("""
                    SELECT user_id, role, joined_at, invited_by
                    FROM team_members
                    WHERE team_id = ? AND is_active = 1
                    ORDER BY joined_at ASC
                """, (team_id,))
                
                return [dict(row) for row in cursor.fetchall()]
                
        except Exception as e:
            logger.error(f"Failed to get team members: {e}")
            return []
    
    async def get_user_role(self, team_id: int, user_id: int) -> Optional[TeamRole]:
        """Get user's role in a team."""
        if not self.enabled:
            return None
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("""
                    SELECT role FROM team_members
                    WHERE team_id = ? AND user_id = ? AND is_active = 1
                """, (team_id, user_id))
                
                result = cursor.fetchone()
                if result:
                    return TeamRole(result[0])
                
        except Exception as e:
            logger.error(f"Failed to get user role: {e}")
        
        return None
    
    async def check_permission(
        self, 
        team_id: int, 
        user_id: int, 
        permission: TeamPermission
    ) -> bool:
        """Check if user has specific permission in team."""
        if not self.enabled:
            return False
        
        role = await self.get_user_role(team_id, user_id)
        if not role:
            return False
        
        return permission in ROLE_PERMISSIONS.get(role, set())
    
    async def add_team_wallet(
        self,
        team_id: int,
        chain: str,
        address: str,
        derivation_path: str,
        created_by: int,
        label: str = "",
        tags: str = ""
    ) -> bool:
        """Add a wallet to team storage."""
        if not self.enabled:
            return False
        
        # Check permissions
        if not await self.check_permission(team_id, created_by, TeamPermission.GENERATE_WALLETS):
            return False
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO team_wallets 
                    (team_id, chain, address, derivation_path, created_by, created_at, label, tags)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (team_id, chain, address, derivation_path, created_by, int(time.time()), label, tags))
                
                conn.commit()
            
            # Audit log
            audit_service.log_wallet_generated(
                created_by,
                chain,
                team_id=team_id,
                address=address[:10] + "...",
                label=label
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to add team wallet: {e}")
            return False
    
    async def get_team_wallets(
        self,
        team_id: int,
        user_id: int,
        chain: Optional[str] = None,
        limit: int = 1000
    ) -> List[Dict]:
        """Get team wallets with permission check."""
        if not self.enabled:
            return []
        
        # Check permissions
        if not await self.check_permission(team_id, user_id, TeamPermission.VIEW_TEAM_WALLETS):
            return []
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                
                if chain:
                    cursor = conn.execute("""
                        SELECT * FROM team_wallets
                        WHERE team_id = ? AND chain = ?
                        ORDER BY created_at DESC
                        LIMIT ?
                    """, (team_id, chain, limit))
                else:
                    cursor = conn.execute("""
                        SELECT * FROM team_wallets
                        WHERE team_id = ?
                        ORDER BY created_at DESC
                        LIMIT ?
                    """, (team_id, limit))
                
                return [dict(row) for row in cursor.fetchall()]
                
        except Exception as e:
            logger.error(f"Failed to get team wallets: {e}")
            return []
    
    def _update_stats(self) -> None:
        """Update internal statistics."""
        if not self.enabled:
            return
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                # Total teams
                cursor = conn.execute("SELECT COUNT(*) FROM teams WHERE is_active = 1")
                self._stats['total_teams'] = cursor.fetchone()[0]
                
                # Total members
                cursor = conn.execute("SELECT COUNT(*) FROM team_members WHERE is_active = 1")
                self._stats['total_members'] = cursor.fetchone()[0]
                
        except Exception as e:
            logger.error(f"Failed to update team stats: {e}")
    
    def get_stats(self) -> Dict:
        """Get team service statistics."""
        if not self.enabled:
            return {'enabled': False}
        
        self._update_stats()
        return {
            **self._stats,
            'enabled': True,
            'max_team_size': self.max_team_size
        }
    
    async def generate_team_report(self, team_id: int, requested_by: int) -> Optional[Dict]:
        """Generate comprehensive team report."""
        if not await self.check_permission(team_id, requested_by, TeamPermission.VIEW_REPORTS):
            return None
        
        try:
            report = {
                'team_id': team_id,
                'generated_at': int(time.time()),
                'generated_by': requested_by,
                'members': await self.get_team_members(team_id),
                'wallets': {},
                'activity_summary': {}
            }
            
            # Get wallet counts by chain
            wallets = await self.get_team_wallets(team_id, requested_by, limit=10000)
            wallet_counts = {}
            for wallet in wallets:
                chain = wallet['chain']
                wallet_counts[chain] = wallet_counts.get(chain, 0) + 1
            
            report['wallets'] = {
                'total': len(wallets),
                'by_chain': wallet_counts
            }
            
            return report
            
        except Exception as e:
            logger.error(f"Failed to generate team report: {e}")
            return None

# Global team service instance  
team_service = TeamService()