"""
Comprehensive health checking system for the Wallet Bot.
"""
import time
import logging
import asyncio
import aiohttp
import sqlite3
from typing import Dict, List, Optional, Any, Callable, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
from pathlib import Path

from ..config import config

logger = logging.getLogger(__name__)

class HealthStatus(Enum):
    """Health check status levels."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"

@dataclass
class HealthCheckResult:
    """Result of a health check."""
    component: str
    status: HealthStatus
    message: str
    duration_ms: float
    timestamp: float
    metadata: Dict[str, Any] = None
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            **asdict(self),
            'status': self.status.value,
            'metadata': self.metadata or {}
        }

class HealthCheck:
    """Base class for health checks."""
    
    def __init__(self, name: str, timeout_seconds: float = 5.0):
        self.name = name
        self.timeout_seconds = timeout_seconds
    
    async def check(self) -> HealthCheckResult:
        """Perform the health check."""
        start_time = time.perf_counter()
        
        try:
            # Perform the actual check with timeout
            result = await asyncio.wait_for(
                self._perform_check(),
                timeout=self.timeout_seconds
            )
            
            duration_ms = (time.perf_counter() - start_time) * 1000
            
            return HealthCheckResult(
                component=self.name,
                status=result[0],
                message=result[1],
                duration_ms=duration_ms,
                timestamp=time.time(),
                metadata=result[2] if len(result) > 2 else None
            )
        
        except asyncio.TimeoutError:
            duration_ms = (time.perf_counter() - start_time) * 1000
            return HealthCheckResult(
                component=self.name,
                status=HealthStatus.UNHEALTHY,
                message=f"Health check timed out after {self.timeout_seconds}s",
                duration_ms=duration_ms,
                timestamp=time.time()
            )
        
        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            return HealthCheckResult(
                component=self.name,
                status=HealthStatus.UNHEALTHY,
                message=f"Health check failed: {str(e)}",
                duration_ms=duration_ms,
                timestamp=time.time(),
                metadata={'error_type': type(e).__name__}
            )
    
    async def _perform_check(self) -> Tuple[HealthStatus, str, Optional[Dict]]:
        """Override this method to implement the actual health check logic."""
        raise NotImplementedError("Subclasses must implement _perform_check")

class DatabaseHealthCheck(HealthCheck):
    """Health check for database connectivity and performance."""
    
    def __init__(self, db_path: Path, timeout_seconds: float = 3.0):
        super().__init__("database", timeout_seconds)
        self.db_path = db_path
    
    async def _perform_check(self) -> Tuple[HealthStatus, str, Optional[Dict]]:
        """Check database health."""
        
        # Check if database file exists
        if not self.db_path.exists():
            return (
                HealthStatus.UNHEALTHY,
                f"Database file does not exist: {self.db_path}",
                None
            )
        
        # Test database connection and basic query
        try:
            start_query_time = time.perf_counter()
            
            with sqlite3.connect(str(self.db_path), timeout=self.timeout_seconds) as conn:
                cursor = conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
                table_count = cursor.fetchone()[0]
                
                # Test a simple write operation
                cursor = conn.execute("CREATE TEMP TABLE health_test (id INTEGER)")
                cursor = conn.execute("INSERT INTO health_test (id) VALUES (1)")
                cursor = conn.execute("SELECT COUNT(*) FROM health_test")
                test_count = cursor.fetchone()[0]
            
            query_duration_ms = (time.perf_counter() - start_query_time) * 1000
            
            # Check performance thresholds
            if query_duration_ms > 1000:  # 1 second
                status = HealthStatus.DEGRADED
                message = f"Database responding slowly ({query_duration_ms:.1f}ms)"
            else:
                status = HealthStatus.HEALTHY
                message = f"Database operational ({table_count} tables)"
            
            metadata = {
                'table_count': table_count,
                'query_duration_ms': query_duration_ms,
                'file_size_bytes': self.db_path.stat().st_size,
                'test_result': test_count == 1
            }
            
            return (status, message, metadata)
            
        except sqlite3.OperationalError as e:
            return (
                HealthStatus.UNHEALTHY,
                f"Database operational error: {str(e)}",
                {'error_type': 'operational'}
            )
        
        except Exception as e:
            return (
                HealthStatus.UNHEALTHY,
                f"Database check failed: {str(e)}",
                {'error_type': type(e).__name__}
            )

class RpcHealthCheck(HealthCheck):
    """Health check for RPC endpoint connectivity."""
    
    def __init__(self, name: str, rpc_url: str, timeout_seconds: float = 5.0):
        super().__init__(f"rpc_{name.lower()}", timeout_seconds)
        self.chain_name = name
        self.rpc_url = rpc_url
    
    async def _perform_check(self) -> Tuple[HealthStatus, str, Optional[Dict]]:
        """Check RPC endpoint health."""
        
        if not self.rpc_url:
            return (
                HealthStatus.UNKNOWN,
                f"RPC URL not configured for {self.chain_name}",
                None
            )
        
        try:
            # Test HTTP connectivity with a basic JSON-RPC call
            payload = {
                "jsonrpc": "2.0",
                "method": "eth_blockNumber",  # Works for most EVM chains
                "params": [],
                "id": 1
            }
            
            start_time = time.perf_counter()
            
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout_seconds)
            ) as session:
                async with session.post(
                    self.rpc_url,
                    json=payload,
                    headers={"Content-Type": "application/json"}
                ) as response:
                    response_time_ms = (time.perf_counter() - start_time) * 1000
                    
                    if response.status == 200:
                        data = await response.json()
                        
                        if 'result' in data:
                            # Parse block number if available
                            block_number = None
                            try:
                                block_hex = data['result']
                                block_number = int(block_hex, 16) if block_hex.startswith('0x') else int(block_hex)
                            except (ValueError, TypeError):
                                pass
                            
                            # Determine status based on response time
                            if response_time_ms > 3000:  # 3 seconds
                                status = HealthStatus.DEGRADED
                                message = f"{self.chain_name} RPC responding slowly ({response_time_ms:.0f}ms)"
                            else:
                                status = HealthStatus.HEALTHY
                                message = f"{self.chain_name} RPC operational"
                            
                            metadata = {
                                'response_time_ms': response_time_ms,
                                'latest_block': block_number,
                                'rpc_url_host': self.rpc_url.split('/')[2] if '//' in self.rpc_url else self.rpc_url[:30] + '...'
                            }
                            
                            return (status, message, metadata)
                        
                        elif 'error' in data:
                            return (
                                HealthStatus.DEGRADED,
                                f"{self.chain_name} RPC returned error: {data['error'].get('message', 'Unknown error')}",
                                {'rpc_error': data['error']}
                            )
                    
                    return (
                        HealthStatus.UNHEALTHY,
                        f"{self.chain_name} RPC returned HTTP {response.status}",
                        {'http_status': response.status}
                    )
        
        except asyncio.TimeoutError:
            return (
                HealthStatus.UNHEALTHY,
                f"{self.chain_name} RPC timeout after {self.timeout_seconds}s",
                None
            )
        
        except aiohttp.ClientError as e:
            return (
                HealthStatus.UNHEALTHY,
                f"{self.chain_name} RPC connection error: {str(e)}",
                {'error_type': 'connection'}
            )
        
        except Exception as e:
            return (
                HealthStatus.UNHEALTHY,
                f"{self.chain_name} RPC check failed: {str(e)}",
                {'error_type': type(e).__name__}
            )

class MemoryHealthCheck(HealthCheck):
    """Health check for memory usage."""
    
    def __init__(self, timeout_seconds: float = 1.0):
        super().__init__("memory", timeout_seconds)
    
    async def _perform_check(self) -> Tuple[HealthStatus, str, Optional[Dict]]:
        """Check memory usage."""
        try:
            import psutil
            
            # Get current process memory info
            process = psutil.Process()
            memory_info = process.memory_info()
            memory_percent = process.memory_percent()
            
            # Convert to MB
            rss_mb = memory_info.rss / 1024 / 1024
            vms_mb = memory_info.vms / 1024 / 1024
            
            # Determine status based on memory usage
            if memory_percent > 80:
                status = HealthStatus.UNHEALTHY
                message = f"High memory usage: {memory_percent:.1f}%"
            elif memory_percent > 60:
                status = HealthStatus.DEGRADED
                message = f"Moderate memory usage: {memory_percent:.1f}%"
            else:
                status = HealthStatus.HEALTHY
                message = f"Memory usage normal: {memory_percent:.1f}%"
            
            metadata = {
                'rss_mb': round(rss_mb, 1),
                'vms_mb': round(vms_mb, 1),
                'memory_percent': round(memory_percent, 1),
                'num_threads': process.num_threads()
            }
            
            return (status, message, metadata)
            
        except ImportError:
            return (
                HealthStatus.UNKNOWN,
                "psutil not available for memory monitoring",
                None
            )
        except Exception as e:
            return (
                HealthStatus.UNHEALTHY,
                f"Memory check failed: {str(e)}",
                {'error_type': type(e).__name__}
            )

class DiskSpaceHealthCheck(HealthCheck):
    """Health check for disk space."""
    
    def __init__(self, path: Path, timeout_seconds: float = 1.0):
        super().__init__("disk_space", timeout_seconds)
        self.path = path
    
    async def _perform_check(self) -> Tuple[HealthStatus, str, Optional[Dict]]:
        """Check disk space."""
        try:
            import shutil
            
            total, used, free = shutil.disk_usage(self.path)
            
            # Convert to GB
            total_gb = total / 1024 / 1024 / 1024
            used_gb = used / 1024 / 1024 / 1024
            free_gb = free / 1024 / 1024 / 1024
            used_percent = (used / total) * 100
            
            # Determine status based on free space
            if free_gb < 0.1:  # Less than 100MB
                status = HealthStatus.UNHEALTHY
                message = f"Critical: Only {free_gb:.2f}GB free"
            elif free_gb < 1.0:  # Less than 1GB
                status = HealthStatus.DEGRADED
                message = f"Low disk space: {free_gb:.2f}GB free"
            else:
                status = HealthStatus.HEALTHY
                message = f"Disk space OK: {free_gb:.2f}GB free"
            
            metadata = {
                'total_gb': round(total_gb, 2),
                'used_gb': round(used_gb, 2),
                'free_gb': round(free_gb, 2),
                'used_percent': round(used_percent, 1),
                'path': str(self.path)
            }
            
            return (status, message, metadata)
            
        except Exception as e:
            return (
                HealthStatus.UNHEALTHY,
                f"Disk space check failed: {str(e)}",
                {'error_type': type(e).__name__}
            )

class HealthChecker:
    """Comprehensive health checking system."""
    
    def __init__(self):
        self.checks: List[HealthCheck] = []
        self._last_results: Dict[str, HealthCheckResult] = {}
        self._check_history: Dict[str, List[HealthCheckResult]] = {}
        self.max_history = 100  # Keep last 100 results per check
        
        # Initialize default health checks
        self._init_default_checks()
    
    def _init_default_checks(self) -> None:
        """Initialize default health checks."""
        
        # Database health check
        db_path = config.DATA_DIR / "wallets.db"
        self.add_check(DatabaseHealthCheck(db_path))
        
        # RPC endpoint checks
        if config.RPC_ETH:
            self.add_check(RpcHealthCheck("ETH", config.RPC_ETH))
        
        if config.RPC_BASE:
            self.add_check(RpcHealthCheck("BASE", config.RPC_BASE))
        
        if config.RPC_BSC:
            self.add_check(RpcHealthCheck("BSC", config.RPC_BSC))
        
        if config.RPC_POLYGON:
            self.add_check(RpcHealthCheck("POLYGON", config.RPC_POLYGON))
        
        if config.RPC_AVAXC:
            self.add_check(RpcHealthCheck("AVAXC", config.RPC_AVAXC))
        
        # System resource checks
        self.add_check(MemoryHealthCheck())
        self.add_check(DiskSpaceHealthCheck(config.DATA_DIR))
        
        logger.info(f"Initialized {len(self.checks)} health checks")
    
    def add_check(self, health_check: HealthCheck) -> None:
        """Add a health check."""
        self.checks.append(health_check)
        self._check_history[health_check.name] = []
    
    async def run_check(self, check_name: str) -> Optional[HealthCheckResult]:
        """Run a specific health check by name."""
        for check in self.checks:
            if check.name == check_name:
                result = await check.check()
                self._store_result(result)
                return result
        
        return None
    
    async def run_all_checks(self, timeout_seconds: float = 30.0) -> Dict[str, HealthCheckResult]:
        """Run all health checks."""
        results = {}
        
        try:
            # Run all checks concurrently with overall timeout
            check_tasks = [check.check() for check in self.checks]
            completed_results = await asyncio.wait_for(
                asyncio.gather(*check_tasks, return_exceptions=True),
                timeout=timeout_seconds
            )
            
            # Process results
            for i, result in enumerate(completed_results):
                check_name = self.checks[i].name
                
                if isinstance(result, Exception):
                    # Create error result for failed checks
                    error_result = HealthCheckResult(
                        component=check_name,
                        status=HealthStatus.UNHEALTHY,
                        message=f"Health check exception: {str(result)}",
                        duration_ms=0,
                        timestamp=time.time(),
                        metadata={'error_type': type(result).__name__}
                    )
                    results[check_name] = error_result
                    self._store_result(error_result)
                else:
                    results[check_name] = result
                    self._store_result(result)
        
        except asyncio.TimeoutError:
            # Handle overall timeout
            for check in self.checks:
                if check.name not in results:
                    timeout_result = HealthCheckResult(
                        component=check.name,
                        status=HealthStatus.UNHEALTHY,
                        message="Health check timed out",
                        duration_ms=0,
                        timestamp=time.time()
                    )
                    results[check.name] = timeout_result
                    self._store_result(timeout_result)
        
        return results
    
    def _store_result(self, result: HealthCheckResult) -> None:
        """Store health check result."""
        self._last_results[result.component] = result
        
        # Add to history
        if result.component in self._check_history:
            history = self._check_history[result.component]
            history.append(result)
            
            # Trim history if too long
            if len(history) > self.max_history:
                history[:] = history[-self.max_history:]
    
    def get_last_result(self, check_name: str) -> Optional[HealthCheckResult]:
        """Get the last result for a specific check."""
        return self._last_results.get(check_name)
    
    def get_check_history(self, check_name: str, limit: int = 10) -> List[HealthCheckResult]:
        """Get history for a specific check."""
        history = self._check_history.get(check_name, [])
        return history[-limit:] if history else []
    
    def get_overall_status(self) -> Tuple[HealthStatus, Dict[str, Any]]:
        """Get overall system health status."""
        if not self._last_results:
            return HealthStatus.UNKNOWN, {'message': 'No health checks have been run'}
        
        status_counts = {status: 0 for status in HealthStatus}
        for result in self._last_results.values():
            status_counts[result.status] += 1
        
        # Determine overall status
        if status_counts[HealthStatus.UNHEALTHY] > 0:
            overall_status = HealthStatus.UNHEALTHY
        elif status_counts[HealthStatus.DEGRADED] > 0:
            overall_status = HealthStatus.DEGRADED
        elif status_counts[HealthStatus.UNKNOWN] > 0:
            overall_status = HealthStatus.DEGRADED  # Treat unknown as degraded
        else:
            overall_status = HealthStatus.HEALTHY
        
        # Calculate average response time
        total_duration = sum(r.duration_ms for r in self._last_results.values())
        avg_duration = total_duration / len(self._last_results)
        
        summary = {
            'overall_status': overall_status,
            'total_checks': len(self._last_results),
            'status_breakdown': {s.value: c for s, c in status_counts.items()},
            'average_response_time_ms': round(avg_duration, 2),
            'last_check_time': max(r.timestamp for r in self._last_results.values()) if self._last_results else None
        }
        
        return overall_status, summary
    
    def get_health_report(self) -> Dict[str, Any]:
        """Get comprehensive health report."""
        overall_status, summary = self.get_overall_status()
        
        report = {
            'timestamp': time.time(),
            'overall_status': overall_status.value,
            'summary': summary,
            'checks': {
                name: result.to_dict() 
                for name, result in self._last_results.items()
            }
        }
        
        return report

# Global health checker instance
health_checker = HealthChecker()

# Convenience functions
async def check_system_health() -> Dict[str, Any]:
    """Run all health checks and return report."""
    await health_checker.run_all_checks()
    return health_checker.get_health_report()

async def check_component_health(component: str) -> Optional[HealthCheckResult]:
    """Check health of a specific component."""
    return await health_checker.run_check(component)

def get_health_status() -> Tuple[HealthStatus, Dict[str, Any]]:
    """Get current overall health status."""
    return health_checker.get_overall_status()