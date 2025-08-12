"""
Centralized configuration management for the Wallet Bot.
"""
import os
from pathlib import Path
from typing import Dict, List, Set, Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Config:
    """Centralized configuration with validation and defaults."""
    
    # Core bot configuration
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
    DATA_DIR: Path = Path(os.getenv("DATA_DIR", ".")).resolve()
    
    # Rate limiting
    RATE_LIMIT_PER_MIN: int = int(os.getenv("RATE_LIMIT_PER_MIN", "3"))
    
    # Admin users
    ADMIN_USER_IDS: Set[int] = {
        int(x) for x in os.getenv("ADMIN_USER_IDS", "").replace(" ", "").split(",") 
        if x.isdigit()
    }
    
    # Bulk operation limits
    BULK_MAX_COUNT: int = int(os.getenv("BULK_MAX_COUNT", "1000"))
    BULKZIP_CSV_CHUNK: int = int(os.getenv("BULKZIP_CSV_CHUNK", "10000"))
    BULKZIP_ZIP_CSVS: int = int(os.getenv("BULKZIP_ZIP_CSVS", "10"))
    BULKZIP_MAX_NONADMIN: int = int(os.getenv("BULKZIP_MAX_NONADMIN", "100000"))
    BULKZIP_MAX_COUNT: int = int(os.getenv("BULKZIP_MAX_COUNT", "1000000"))
    
    # EVM RPC endpoints
    RPC_ETH: Optional[str] = os.getenv("RPC_ETH", "").strip() or None
    RPC_BASE: Optional[str] = os.getenv("RPC_BASE", "").strip() or None
    RPC_BSC: Optional[str] = os.getenv("RPC_BSC", "").strip() or None
    RPC_POLYGON: Optional[str] = os.getenv("RPC_POLYGON", "").strip() or None
    RPC_AVAXC: Optional[str] = os.getenv("RPC_AVAXC", "").strip() or None
    
    # Non-EVM balance checking
    ENABLE_BTC_BAL: bool = os.getenv("ENABLE_BTC_BAL", "0") == "1"
    BTC_API_BASE: str = os.getenv("BTC_API_BASE", "https://blockstream.info/api").rstrip("/")
    
    ENABLE_SOL_BAL: bool = os.getenv("ENABLE_SOL_BAL", "0") == "1"
    SOL_RPC_URL: Optional[str] = os.getenv("SOL_RPC_URL", "").strip() or None
    
    ENABLE_TON_BAL: bool = os.getenv("ENABLE_TON_BAL", "0") == "1"
    TON_API_BASE: Optional[str] = os.getenv("TON_API_BASE", "").strip() or None
    TON_API_KEY: Optional[str] = os.getenv("TON_API_KEY", "").strip() or None
    
    # Performance settings
    DB_POOL_SIZE: int = int(os.getenv("DB_POOL_SIZE", "5"))
    BALANCE_CACHE_TTL: int = int(os.getenv("BALANCE_CACHE_TTL", "300"))  # 5 minutes
    
    # Enterprise features
    ENABLE_AUDIT_LOGGING: bool = os.getenv("ENABLE_AUDIT_LOGGING", "0") == "1"
    AUDIT_LOG_PATH: Optional[str] = os.getenv("AUDIT_LOG_PATH", "").strip() or None
    
    ENABLE_TEAM_MANAGEMENT: bool = os.getenv("ENABLE_TEAM_MANAGEMENT", "0") == "1"
    MAX_TEAM_SIZE: int = int(os.getenv("MAX_TEAM_SIZE", "10"))
    
    # Monitoring and metrics
    ENABLE_METRICS: bool = os.getenv("ENABLE_METRICS", "0") == "1"
    METRICS_PORT: int = int(os.getenv("METRICS_PORT", "9090"))
    
    @classmethod
    def validate(cls) -> List[str]:
        """Validate configuration and return list of errors."""
        errors = []
        
        # Required settings
        if not cls.TELEGRAM_BOT_TOKEN:
            errors.append("TELEGRAM_BOT_TOKEN is required")
        
        # Data directory
        try:
            cls.DATA_DIR.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            errors.append(f"Cannot create DATA_DIR {cls.DATA_DIR}: {e}")
        
        # Rate limiting
        if cls.RATE_LIMIT_PER_MIN < 1:
            errors.append("RATE_LIMIT_PER_MIN must be at least 1")
        
        # Bulk limits validation
        if cls.BULK_MAX_COUNT < 1:
            errors.append("BULK_MAX_COUNT must be at least 1")
        
        if cls.BULKZIP_MAX_NONADMIN > cls.BULKZIP_MAX_COUNT:
            errors.append("BULKZIP_MAX_NONADMIN cannot exceed BULKZIP_MAX_COUNT")
        
        # Balance checking validation
        if cls.ENABLE_SOL_BAL and not cls.SOL_RPC_URL:
            errors.append("SOL_RPC_URL required when ENABLE_SOL_BAL=1")
        
        if cls.ENABLE_TON_BAL and not cls.TON_API_BASE:
            errors.append("TON_API_BASE required when ENABLE_TON_BAL=1")
        
        return errors
    
    @classmethod
    def get_supported_chains(cls) -> List[str]:
        """Get list of supported blockchain networks."""
        return ["ETH", "BTC", "SOL", "BASE", "BSC", "POLYGON", "AVAXC", "TRON", "XRP", "DOGE", "LTC", "TON"]
    
    @classmethod
    def get_evm_chains(cls) -> List[str]:
        """Get list of EVM-compatible chains."""
        return ["ETH", "BASE", "BSC", "POLYGON", "AVAXC"]
    
    @classmethod
    def is_admin(cls, user_id: int) -> bool:
        """Check if user is admin."""
        return user_id in cls.ADMIN_USER_IDS
    
    @classmethod
    def get_rpc_status(cls) -> Dict[str, bool]:
        """Get RPC configuration status."""
        return {
            "ETH": bool(cls.RPC_ETH),
            "BASE": bool(cls.RPC_BASE),
            "BSC": bool(cls.RPC_BSC),
            "POLYGON": bool(cls.RPC_POLYGON),
            "AVAXC": bool(cls.RPC_AVAXC),
            "BTC": cls.ENABLE_BTC_BAL,
            "SOL": cls.ENABLE_SOL_BAL and bool(cls.SOL_RPC_URL),
            "TON": cls.ENABLE_TON_BAL and bool(cls.TON_API_BASE),
        }

# Global configuration instance
config = Config()

# Convenience functions for backward compatibility
def get_data_dir() -> Path:
    """Get configured data directory."""
    return config.DATA_DIR

def get_rpc_config() -> Dict[str, Optional[str]]:
    """Get RPC configuration."""
    return {
        "RPC_ETH": config.RPC_ETH,
        "RPC_BASE": config.RPC_BASE,
        "RPC_BSC": config.RPC_BSC,
        "RPC_POLYGON": config.RPC_POLYGON,
        "RPC_AVAXC": config.RPC_AVAXC,
    }

def get_balance_config() -> Dict:
    """Get balance checking configuration."""
    return {
        "ENABLE_BTC_BAL": config.ENABLE_BTC_BAL,
        "BTC_API_BASE": config.BTC_API_BASE,
        "ENABLE_SOL_BAL": config.ENABLE_SOL_BAL,
        "SOL_RPC_URL": config.SOL_RPC_URL,
        "ENABLE_TON_BAL": config.ENABLE_TON_BAL,
        "TON_API_BASE": config.TON_API_BASE,
        "TON_API_KEY": config.TON_API_KEY,
    }

def validate_configuration() -> None:
    """Validate configuration and raise error if invalid."""
    errors = config.validate()
    if errors:
        error_msg = "Configuration errors found:\n" + "\n".join(f"- {err}" for err in errors)
        raise RuntimeError(error_msg)