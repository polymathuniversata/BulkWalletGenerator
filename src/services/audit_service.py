"""
Enterprise audit logging service for compliance and security monitoring.
"""
import json
import time
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum
import sqlite3
from contextlib import contextmanager

from ..config import config

logger = logging.getLogger(__name__)

class AuditEventType(Enum):
    """Types of auditable events."""
    WALLET_GENERATED = "wallet_generated"
    SEED_REVEALED = "seed_revealed"
    BULK_OPERATION = "bulk_operation"
    BALANCE_CHECKED = "balance_checked"
    PROFILE_ACCESSED = "profile_accessed"
    ADMIN_ACTION = "admin_action"
    USER_LOGIN = "user_login"
    CONFIGURATION_CHANGED = "configuration_changed"
    ERROR_OCCURRED = "error_occurred"
    SECURITY_INCIDENT = "security_incident"

class AuditLevel(Enum):
    """Audit event severity levels."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"

@dataclass
class AuditEvent:
    """Audit event record."""
    timestamp: float
    event_type: AuditEventType
    level: AuditLevel
    user_id: Optional[int]
    session_id: Optional[str]
    details: Dict[str, Any]
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            **asdict(self),
            'event_type': self.event_type.value,
            'level': self.level.value
        }

class AuditLogger:
    """File-based audit logger with rotation."""
    
    def __init__(self, log_path: Path, max_size_mb: int = 100):
        self.log_path = log_path
        self.max_size_bytes = max_size_mb * 1024 * 1024
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
    
    def log_event(self, event: AuditEvent) -> bool:
        """Log audit event to file."""
        try:
            # Check if rotation is needed
            if self.log_path.exists() and self.log_path.stat().st_size > self.max_size_bytes:
                self._rotate_log()
            
            # Write event
            with self.log_path.open('a', encoding='utf-8') as f:
                event_json = json.dumps(event.to_dict(), separators=(',', ':'))
                f.write(f"{event_json}\n")
            
            return True
        except Exception as e:
            logger.error(f"Failed to write audit log: {e}")
            return False
    
    def _rotate_log(self) -> None:
        """Rotate audit log file."""
        try:
            timestamp = int(time.time())
            rotated_path = self.log_path.with_suffix(f".{timestamp}.log")
            self.log_path.rename(rotated_path)
            logger.info(f"Rotated audit log to {rotated_path}")
        except Exception as e:
            logger.error(f"Failed to rotate audit log: {e}")

class AuditDatabase:
    """Database-based audit storage for querying and reporting."""
    
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_database()
    
    def _init_database(self) -> None:
        """Initialize audit database."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    event_type TEXT NOT NULL,
                    level TEXT NOT NULL,
                    user_id INTEGER,
                    session_id TEXT,
                    ip_address TEXT,
                    user_agent TEXT,
                    details TEXT,
                    indexed_at REAL DEFAULT (julianday('now'))
                )
            """)
            
            # Create indexes for efficient querying
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_timestamp 
                ON audit_events(timestamp DESC)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_user_id 
                ON audit_events(user_id, timestamp DESC)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_event_type 
                ON audit_events(event_type, timestamp DESC)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_level 
                ON audit_events(level, timestamp DESC)
            """)
            
            conn.commit()
    
    def store_event(self, event: AuditEvent) -> bool:
        """Store audit event in database."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO audit_events 
                    (timestamp, event_type, level, user_id, session_id, ip_address, user_agent, details)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    event.timestamp,
                    event.event_type.value,
                    event.level.value,
                    event.user_id,
                    event.session_id,
                    event.ip_address,
                    event.user_agent,
                    json.dumps(event.details)
                ))
                conn.commit()
            
            return True
        except Exception as e:
            logger.error(f"Failed to store audit event in database: {e}")
            return False
    
    def query_events(
        self,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        user_id: Optional[int] = None,
        event_type: Optional[AuditEventType] = None,
        level: Optional[AuditLevel] = None,
        limit: int = 1000
    ) -> List[Dict]:
        """Query audit events with filters."""
        try:
            conditions = []
            params = []
            
            if start_time:
                conditions.append("timestamp >= ?")
                params.append(start_time)
            
            if end_time:
                conditions.append("timestamp <= ?")
                params.append(end_time)
            
            if user_id:
                conditions.append("user_id = ?")
                params.append(user_id)
            
            if event_type:
                conditions.append("event_type = ?")
                params.append(event_type.value)
            
            if level:
                conditions.append("level = ?")
                params.append(level.value)
            
            where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
            params.append(limit)
            
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(f"""
                    SELECT * FROM audit_events 
                    {where_clause}
                    ORDER BY timestamp DESC 
                    LIMIT ?
                """, params)
                
                return [dict(row) for row in cursor.fetchall()]
        
        except Exception as e:
            logger.error(f"Failed to query audit events: {e}")
            return []

class AuditService:
    """Enterprise audit service with multiple storage backends."""
    
    def __init__(self):
        self.enabled = config.ENABLE_AUDIT_LOGGING
        self.file_logger: Optional[AuditLogger] = None
        self.database: Optional[AuditDatabase] = None
        self._stats = {
            'events_logged': 0,
            'events_failed': 0,
            'last_event_time': None
        }
        
        if self.enabled:
            self._init_storage()
    
    def _init_storage(self) -> None:
        """Initialize audit storage backends."""
        try:
            # File-based audit logging
            if config.AUDIT_LOG_PATH:
                audit_log_path = Path(config.AUDIT_LOG_PATH)
                self.file_logger = AuditLogger(audit_log_path)
                logger.info(f"Audit file logging enabled: {audit_log_path}")
            
            # Database-based audit storage
            audit_db_path = config.DATA_DIR / "audit.db"
            self.database = AuditDatabase(audit_db_path)
            logger.info(f"Audit database enabled: {audit_db_path}")
            
        except Exception as e:
            logger.error(f"Failed to initialize audit storage: {e}")
            self.enabled = False
    
    def log_event(
        self,
        event_type: AuditEventType,
        user_id: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None,
        level: AuditLevel = AuditLevel.INFO,
        session_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> bool:
        """Log an audit event."""
        if not self.enabled:
            return True  # Succeed silently when disabled
        
        try:
            event = AuditEvent(
                timestamp=time.time(),
                event_type=event_type,
                level=level,
                user_id=user_id,
                session_id=session_id,
                details=details or {},
                ip_address=ip_address,
                user_agent=user_agent
            )
            
            success = True
            
            # Log to file if configured
            if self.file_logger:
                success &= self.file_logger.log_event(event)
            
            # Store in database
            if self.database:
                success &= self.database.store_event(event)
            
            if success:
                self._stats['events_logged'] += 1
                self._stats['last_event_time'] = event.timestamp
            else:
                self._stats['events_failed'] += 1
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to log audit event: {e}")
            self._stats['events_failed'] += 1
            return False
    
    # Convenience methods for common audit events
    
    def log_wallet_generated(self, user_id: int, chain: str, **kwargs) -> bool:
        """Log wallet generation event."""
        return self.log_event(
            AuditEventType.WALLET_GENERATED,
            user_id=user_id,
            details={'chain': chain, **kwargs}
        )
    
    def log_seed_revealed(self, user_id: int, **kwargs) -> bool:
        """Log seed phrase reveal event."""
        return self.log_event(
            AuditEventType.SEED_REVEALED,
            user_id=user_id,
            level=AuditLevel.WARNING,
            details=kwargs
        )
    
    def log_bulk_operation(self, user_id: int, chain: str, count: int, **kwargs) -> bool:
        """Log bulk operation event."""
        return self.log_event(
            AuditEventType.BULK_OPERATION,
            user_id=user_id,
            details={'chain': chain, 'count': count, **kwargs}
        )
    
    def log_admin_action(self, user_id: int, action: str, **kwargs) -> bool:
        """Log admin action event."""
        return self.log_event(
            AuditEventType.ADMIN_ACTION,
            user_id=user_id,
            level=AuditLevel.WARNING,
            details={'action': action, **kwargs}
        )
    
    def log_security_incident(self, user_id: Optional[int], incident_type: str, **kwargs) -> bool:
        """Log security incident."""
        return self.log_event(
            AuditEventType.SECURITY_INCIDENT,
            user_id=user_id,
            level=AuditLevel.CRITICAL,
            details={'incident_type': incident_type, **kwargs}
        )
    
    def log_error(self, user_id: Optional[int], error: str, **kwargs) -> bool:
        """Log error event."""
        return self.log_event(
            AuditEventType.ERROR_OCCURRED,
            user_id=user_id,
            level=AuditLevel.WARNING,
            details={'error': error, **kwargs}
        )
    
    # Query and reporting methods
    
    def get_user_activity(
        self, 
        user_id: int, 
        hours: int = 24
    ) -> List[Dict]:
        """Get user activity for the last N hours."""
        if not self.database:
            return []
        
        start_time = time.time() - (hours * 3600)
        return self.database.query_events(
            start_time=start_time,
            user_id=user_id,
            limit=1000
        )
    
    def get_security_events(self, hours: int = 24) -> List[Dict]:
        """Get security-related events."""
        if not self.database:
            return []
        
        start_time = time.time() - (hours * 3600)
        return self.database.query_events(
            start_time=start_time,
            level=AuditLevel.CRITICAL,
            limit=1000
        )
    
    def get_stats(self) -> Dict:
        """Get audit service statistics."""
        return {
            **self._stats,
            'enabled': self.enabled,
            'has_file_logger': bool(self.file_logger),
            'has_database': bool(self.database)
        }
    
    def generate_compliance_report(
        self, 
        start_time: float, 
        end_time: float
    ) -> Dict[str, Any]:
        """Generate compliance report for a time period."""
        if not self.database:
            return {'error': 'Audit database not available'}
        
        try:
            # Get all events in time range
            all_events = self.database.query_events(
                start_time=start_time,
                end_time=end_time,
                limit=100000  # Large limit for comprehensive report
            )
            
            # Analyze events
            report = {
                'report_period': {
                    'start': start_time,
                    'end': end_time,
                    'duration_hours': (end_time - start_time) / 3600
                },
                'summary': {
                    'total_events': len(all_events),
                    'unique_users': len(set(e['user_id'] for e in all_events if e['user_id'])),
                    'event_types': {},
                    'security_incidents': 0,
                    'admin_actions': 0
                },
                'top_users': {},
                'critical_events': []
            }
            
            # Count events by type and user
            user_activity = {}
            for event in all_events:
                # Event type counts
                event_type = event['event_type']
                report['summary']['event_types'][event_type] = report['summary']['event_types'].get(event_type, 0) + 1
                
                # Special event counts
                if event_type == 'security_incident':
                    report['summary']['security_incidents'] += 1
                elif event_type == 'admin_action':
                    report['summary']['admin_actions'] += 1
                
                # User activity
                if event['user_id']:
                    user_activity[event['user_id']] = user_activity.get(event['user_id'], 0) + 1
                
                # Critical events
                if event['level'] == 'critical':
                    report['critical_events'].append(event)
            
            # Top users by activity
            report['top_users'] = dict(
                sorted(user_activity.items(), key=lambda x: x[1], reverse=True)[:10]
            )
            
            return report
            
        except Exception as e:
            logger.error(f"Failed to generate compliance report: {e}")
            return {'error': str(e)}

# Global audit service instance
audit_service = AuditService()