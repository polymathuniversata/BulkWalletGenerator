"""
Production-grade metrics collection and monitoring for the Wallet Bot.
"""
import time
import threading
import logging
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, asdict, field
from enum import Enum
from collections import defaultdict, deque
import json
import asyncio
from contextlib import asynccontextmanager

from ..config import config

logger = logging.getLogger(__name__)

class MetricType(Enum):
    """Types of metrics that can be collected."""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    TIMER = "timer"

@dataclass
class MetricValue:
    """Individual metric value with metadata."""
    name: str
    value: float
    metric_type: MetricType
    timestamp: float
    labels: Dict[str, str] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            **asdict(self),
            'metric_type': self.metric_type.value
        }

class Counter:
    """Thread-safe counter metric."""
    
    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description
        self._value = 0
        self._lock = threading.RLock()
    
    def increment(self, amount: float = 1.0, labels: Dict[str, str] = None) -> None:
        """Increment counter by specified amount."""
        with self._lock:
            self._value += amount
    
    def get_value(self, labels: Dict[str, str] = None) -> MetricValue:
        """Get current counter value."""
        with self._lock:
            return MetricValue(
                name=self.name,
                value=self._value,
                metric_type=MetricType.COUNTER,
                timestamp=time.time(),
                labels=labels or {}
            )
    
    def reset(self) -> None:
        """Reset counter to zero."""
        with self._lock:
            self._value = 0

class Gauge:
    """Thread-safe gauge metric."""
    
    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description
        self._value = 0.0
        self._lock = threading.RLock()
    
    def set(self, value: float, labels: Dict[str, str] = None) -> None:
        """Set gauge value."""
        with self._lock:
            self._value = value
    
    def increment(self, amount: float = 1.0, labels: Dict[str, str] = None) -> None:
        """Increment gauge by specified amount."""
        with self._lock:
            self._value += amount
    
    def decrement(self, amount: float = 1.0, labels: Dict[str, str] = None) -> None:
        """Decrement gauge by specified amount."""
        with self._lock:
            self._value -= amount
    
    def get_value(self, labels: Dict[str, str] = None) -> MetricValue:
        """Get current gauge value."""
        with self._lock:
            return MetricValue(
                name=self.name,
                value=self._value,
                metric_type=MetricType.GAUGE,
                timestamp=time.time(),
                labels=labels or {}
            )

class Histogram:
    """Thread-safe histogram metric for tracking distributions."""
    
    def __init__(self, name: str, description: str = "", buckets: List[float] = None):
        self.name = name
        self.description = description
        self.buckets = buckets or [0.1, 0.5, 1.0, 2.5, 5.0, 10.0, float('inf')]
        self._bucket_counts = defaultdict(int)
        self._sum = 0.0
        self._count = 0
        self._lock = threading.RLock()
    
    def observe(self, value: float, labels: Dict[str, str] = None) -> None:
        """Record an observation."""
        with self._lock:
            self._sum += value
            self._count += 1
            
            # Update bucket counts
            for bucket in self.buckets:
                if value <= bucket:
                    self._bucket_counts[bucket] += 1
    
    def get_value(self, labels: Dict[str, str] = None) -> Dict[str, MetricValue]:
        """Get histogram metrics (buckets, sum, count)."""
        with self._lock:
            now = time.time()
            base_labels = labels or {}
            
            metrics = {}
            
            # Bucket counts
            for bucket, count in self._bucket_counts.items():
                bucket_labels = {**base_labels, 'le': str(bucket)}
                metrics[f"{self.name}_bucket_{bucket}"] = MetricValue(
                    name=f"{self.name}_bucket",
                    value=count,
                    metric_type=MetricType.COUNTER,
                    timestamp=now,
                    labels=bucket_labels
                )
            
            # Sum and count
            metrics[f"{self.name}_sum"] = MetricValue(
                name=f"{self.name}_sum",
                value=self._sum,
                metric_type=MetricType.COUNTER,
                timestamp=now,
                labels=base_labels
            )
            
            metrics[f"{self.name}_count"] = MetricValue(
                name=f"{self.name}_count",
                value=self._count,
                metric_type=MetricType.COUNTER,
                timestamp=now,
                labels=base_labels
            )
            
            return metrics

class Timer:
    """Context manager for timing operations."""
    
    def __init__(self, histogram: Histogram, labels: Dict[str, str] = None):
        self.histogram = histogram
        self.labels = labels
        self.start_time = None
    
    def __enter__(self):
        self.start_time = time.perf_counter()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.start_time is not None:
            duration = time.perf_counter() - self.start_time
            self.histogram.observe(duration, self.labels)

class MetricsCollector:
    """Production-grade metrics collection system."""
    
    def __init__(self):
        self.enabled = config.ENABLE_METRICS
        self._metrics: Dict[str, Any] = {}
        self._lock = threading.RLock()
        
        # System metrics collection
        self._system_stats = {
            'start_time': time.time(),
            'last_collection': None
        }
        
        if self.enabled:
            self._init_default_metrics()
            logger.info("Metrics collection enabled")
    
    def _init_default_metrics(self) -> None:
        """Initialize default bot metrics."""
        
        # Request metrics
        self.register_counter(
            "bot_requests_total",
            "Total number of bot requests"
        )
        
        self.register_counter(
            "bot_errors_total", 
            "Total number of bot errors"
        )
        
        self.register_histogram(
            "bot_request_duration_seconds",
            "Duration of bot requests in seconds",
            buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, float('inf')]
        )
        
        # Wallet generation metrics
        self.register_counter(
            "wallets_generated_total",
            "Total number of wallets generated"
        )
        
        self.register_histogram(
            "wallet_generation_duration_seconds",
            "Duration of wallet generation in seconds"
        )
        
        # Balance check metrics
        self.register_counter(
            "balance_checks_total",
            "Total number of balance checks"
        )
        
        self.register_histogram(
            "balance_check_duration_seconds",
            "Duration of balance checks in seconds"
        )
        
        # Database metrics
        self.register_gauge(
            "database_connections_active",
            "Number of active database connections"
        )
        
        self.register_histogram(
            "database_query_duration_seconds",
            "Duration of database queries in seconds"
        )
        
        # Rate limiting metrics
        self.register_counter(
            "rate_limit_hits_total",
            "Total number of rate limit hits"
        )
        
        # System metrics
        self.register_gauge(
            "bot_uptime_seconds",
            "Bot uptime in seconds"
        )
        
        self.register_gauge(
            "active_users",
            "Number of active users"
        )
    
    def register_counter(self, name: str, description: str = "") -> Counter:
        """Register a new counter metric."""
        if not self.enabled:
            return Counter(name, description)  # Return dummy counter
        
        with self._lock:
            if name in self._metrics:
                raise ValueError(f"Metric '{name}' already registered")
            
            counter = Counter(name, description)
            self._metrics[name] = counter
            return counter
    
    def register_gauge(self, name: str, description: str = "") -> Gauge:
        """Register a new gauge metric."""
        if not self.enabled:
            return Gauge(name, description)  # Return dummy gauge
        
        with self._lock:
            if name in self._metrics:
                raise ValueError(f"Metric '{name}' already registered")
            
            gauge = Gauge(name, description)
            self._metrics[name] = gauge
            return gauge
    
    def register_histogram(self, name: str, description: str = "", buckets: List[float] = None) -> Histogram:
        """Register a new histogram metric."""
        if not self.enabled:
            return Histogram(name, description, buckets)  # Return dummy histogram
        
        with self._lock:
            if name in self._metrics:
                raise ValueError(f"Metric '{name}' already registered")
            
            histogram = Histogram(name, description, buckets)
            self._metrics[name] = histogram
            return histogram
    
    def get_metric(self, name: str) -> Optional[Any]:
        """Get a registered metric by name."""
        with self._lock:
            return self._metrics.get(name)
    
    def timer(self, metric_name: str, labels: Dict[str, str] = None) -> Timer:
        """Create a timer context manager for a histogram metric."""
        histogram = self.get_metric(metric_name)
        if not isinstance(histogram, Histogram):
            # Return a no-op timer if metric doesn't exist or is wrong type
            return Timer(Histogram("dummy"), labels)
        
        return Timer(histogram, labels)
    
    @asynccontextmanager
    async def async_timer(self, metric_name: str, labels: Dict[str, str] = None):
        """Async context manager for timing operations."""
        start_time = time.perf_counter()
        try:
            yield
        finally:
            duration = time.perf_counter() - start_time
            histogram = self.get_metric(metric_name)
            if isinstance(histogram, Histogram):
                histogram.observe(duration, labels)
    
    def increment(self, metric_name: str, amount: float = 1.0, labels: Dict[str, str] = None) -> None:
        """Increment a counter metric."""
        metric = self.get_metric(metric_name)
        if isinstance(metric, Counter):
            metric.increment(amount, labels)
    
    def set_gauge(self, metric_name: str, value: float, labels: Dict[str, str] = None) -> None:
        """Set a gauge metric value."""
        metric = self.get_metric(metric_name)
        if isinstance(metric, Gauge):
            metric.set(value, labels)
    
    def observe_histogram(self, metric_name: str, value: float, labels: Dict[str, str] = None) -> None:
        """Add an observation to a histogram metric."""
        metric = self.get_metric(metric_name)
        if isinstance(metric, Histogram):
            metric.observe(value, labels)
    
    def collect_all_metrics(self) -> List[MetricValue]:
        """Collect all current metric values."""
        if not self.enabled:
            return []
        
        all_metrics = []
        
        with self._lock:
            # Update system metrics
            self._update_system_metrics()
            
            for metric in self._metrics.values():
                if isinstance(metric, (Counter, Gauge)):
                    all_metrics.append(metric.get_value())
                elif isinstance(metric, Histogram):
                    histogram_metrics = metric.get_value()
                    all_metrics.extend(histogram_metrics.values())
        
        return all_metrics
    
    def _update_system_metrics(self) -> None:
        """Update system-level metrics."""
        now = time.time()
        
        # Update uptime
        uptime_gauge = self.get_metric("bot_uptime_seconds")
        if isinstance(uptime_gauge, Gauge):
            uptime = now - self._system_stats['start_time']
            uptime_gauge.set(uptime)
        
        self._system_stats['last_collection'] = now
    
    def get_metrics_summary(self) -> Dict[str, Any]:
        """Get a summary of all metrics in dictionary format."""
        if not self.enabled:
            return {'enabled': False}
        
        metrics = self.collect_all_metrics()
        summary = {
            'enabled': True,
            'total_metrics': len(metrics),
            'collection_time': time.time(),
            'metrics': {}
        }
        
        for metric in metrics:
            summary['metrics'][metric.name] = {
                'value': metric.value,
                'type': metric.metric_type.value,
                'timestamp': metric.timestamp,
                'labels': metric.labels
            }
        
        return summary
    
    def export_prometheus_format(self) -> str:
        """Export metrics in Prometheus text format."""
        if not self.enabled:
            return "# Metrics collection disabled\n"
        
        metrics = self.collect_all_metrics()
        lines = []
        
        # Group metrics by name for help text
        metric_names = set(m.name.split('_bucket')[0].split('_sum')[0].split('_count')[0] for m in metrics)
        
        for metric_name in sorted(metric_names):
            lines.append(f"# HELP {metric_name} Metric collected by Wallet Bot")
            lines.append(f"# TYPE {metric_name} gauge")  # Simplified type
        
        for metric in sorted(metrics, key=lambda x: x.name):
            labels_str = ""
            if metric.labels:
                label_pairs = [f'{k}="{v}"' for k, v in metric.labels.items()]
                labels_str = "{" + ",".join(label_pairs) + "}"
            
            lines.append(f"{metric.name}{labels_str} {metric.value} {int(metric.timestamp * 1000)}")
        
        return "\n".join(lines) + "\n"
    
    def get_stats(self) -> Dict:
        """Get collector statistics."""
        with self._lock:
            return {
                'enabled': self.enabled,
                'registered_metrics': len(self._metrics),
                'metric_types': {
                    'counters': sum(1 for m in self._metrics.values() if isinstance(m, Counter)),
                    'gauges': sum(1 for m in self._metrics.values() if isinstance(m, Gauge)),
                    'histograms': sum(1 for m in self._metrics.values() if isinstance(m, Histogram))
                },
                'system_stats': self._system_stats.copy()
            }

# Global metrics collector instance
metrics_collector = MetricsCollector()

# Convenience functions for common operations
def increment_counter(name: str, amount: float = 1.0, labels: Dict[str, str] = None) -> None:
    """Increment a counter metric."""
    metrics_collector.increment(name, amount, labels)

def set_gauge(name: str, value: float, labels: Dict[str, str] = None) -> None:
    """Set a gauge metric."""
    metrics_collector.set_gauge(name, value, labels)

def observe_histogram(name: str, value: float, labels: Dict[str, str] = None) -> None:
    """Add observation to histogram."""
    metrics_collector.observe_histogram(name, value, labels)

def time_operation(metric_name: str, labels: Dict[str, str] = None):
    """Timer decorator for functions."""
    return metrics_collector.timer(metric_name, labels)

async def async_time_operation(metric_name: str, labels: Dict[str, str] = None):
    """Async timer context manager."""
    return metrics_collector.async_timer(metric_name, labels)