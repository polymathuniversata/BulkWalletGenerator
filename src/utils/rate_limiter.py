"""
Enhanced rate limiting with different strategies and monitoring.
"""
import time
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from ..config import config

logger = logging.getLogger(__name__)

class RateLimitStrategy(Enum):
    """Rate limiting strategies."""
    SLIDING_WINDOW = "sliding_window"
    TOKEN_BUCKET = "token_bucket"
    FIXED_WINDOW = "fixed_window"

@dataclass
class RateLimitResult:
    """Result of rate limit check."""
    allowed: bool
    remaining: int
    reset_time: float
    retry_after: Optional[float] = None

class SlidingWindowLimiter:
    """Sliding window rate limiter."""
    
    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: Dict[int, List[float]] = {}
    
    def is_allowed(self, user_id: int) -> RateLimitResult:
        """Check if request is allowed."""
        now = time.time()
        window_start = now - self.window_seconds
        
        # Get or create user bucket
        user_requests = self.requests.setdefault(user_id, [])
        
        # Remove old requests
        user_requests[:] = [req_time for req_time in user_requests if req_time > window_start]
        
        # Check limit
        if len(user_requests) >= self.max_requests:
            # Calculate retry after
            oldest_request = min(user_requests) if user_requests else now
            retry_after = oldest_request + self.window_seconds - now
            
            return RateLimitResult(
                allowed=False,
                remaining=0,
                reset_time=oldest_request + self.window_seconds,
                retry_after=max(0, retry_after)
            )
        
        # Allow request
        user_requests.append(now)
        remaining = self.max_requests - len(user_requests)
        
        return RateLimitResult(
            allowed=True,
            remaining=remaining,
            reset_time=now + self.window_seconds
        )

class TokenBucketLimiter:
    """Token bucket rate limiter."""
    
    def __init__(self, max_tokens: int, refill_rate: float):
        self.max_tokens = max_tokens
        self.refill_rate = refill_rate  # tokens per second
        self.buckets: Dict[int, Tuple[float, float]] = {}  # user_id -> (tokens, last_update)
    
    def is_allowed(self, user_id: int) -> RateLimitResult:
        """Check if request is allowed."""
        now = time.time()
        
        # Get or create user bucket
        if user_id not in self.buckets:
            self.buckets[user_id] = (self.max_tokens - 1, now)  # Consume one token immediately
            return RateLimitResult(
                allowed=True,
                remaining=self.max_tokens - 1,
                reset_time=now + (self.max_tokens / self.refill_rate)
            )
        
        tokens, last_update = self.buckets[user_id]
        
        # Refill tokens
        time_passed = now - last_update
        new_tokens = min(self.max_tokens, tokens + (time_passed * self.refill_rate))
        
        if new_tokens >= 1:
            # Allow request
            self.buckets[user_id] = (new_tokens - 1, now)
            return RateLimitResult(
                allowed=True,
                remaining=int(new_tokens - 1),
                reset_time=now + ((self.max_tokens - new_tokens + 1) / self.refill_rate)
            )
        else:
            # Rate limited
            retry_after = (1 - new_tokens) / self.refill_rate
            return RateLimitResult(
                allowed=False,
                remaining=0,
                reset_time=now + retry_after,
                retry_after=retry_after
            )

class RateLimiter:
    """Advanced rate limiter with multiple strategies and monitoring."""
    
    def __init__(
        self,
        strategy: RateLimitStrategy = RateLimitStrategy.SLIDING_WINDOW,
        max_requests: int = None,
        window_seconds: int = 60,
        admin_multiplier: float = 3.0
    ):
        self.strategy = strategy
        self.max_requests = max_requests or config.RATE_LIMIT_PER_MIN
        self.window_seconds = window_seconds
        self.admin_multiplier = admin_multiplier
        
        # Initialize limiter based on strategy
        if strategy == RateLimitStrategy.SLIDING_WINDOW:
            self.user_limiter = SlidingWindowLimiter(self.max_requests, self.window_seconds)
            self.admin_limiter = SlidingWindowLimiter(
                int(self.max_requests * admin_multiplier), 
                self.window_seconds
            )
        elif strategy == RateLimitStrategy.TOKEN_BUCKET:
            refill_rate = self.max_requests / self.window_seconds
            self.user_limiter = TokenBucketLimiter(self.max_requests, refill_rate)
            self.admin_limiter = TokenBucketLimiter(
                int(self.max_requests * admin_multiplier),
                refill_rate * admin_multiplier
            )
        else:
            raise ValueError(f"Unsupported rate limit strategy: {strategy}")
        
        # Statistics
        self._stats = {
            'total_requests': 0,
            'blocked_requests': 0,
            'admin_requests': 0,
            'user_requests': 0
        }
    
    def is_rate_limited(self, user_id: int) -> bool:
        """Simple boolean check for backward compatibility."""
        result = self.check_rate_limit(user_id)
        return not result.allowed
    
    def check_rate_limit(self, user_id: int) -> RateLimitResult:
        """Comprehensive rate limit check with detailed result."""
        self._stats['total_requests'] += 1
        
        # Choose appropriate limiter
        if config.is_admin(user_id):
            result = self.admin_limiter.is_allowed(user_id)
            self._stats['admin_requests'] += 1
        else:
            result = self.user_limiter.is_allowed(user_id)
            self._stats['user_requests'] += 1
        
        if not result.allowed:
            self._stats['blocked_requests'] += 1
            logger.info(f"Rate limited user {user_id}, retry after {result.retry_after:.1f}s")
        
        return result
    
    def get_user_status(self, user_id: int) -> Dict:
        """Get detailed rate limit status for a user."""
        result = self.check_rate_limit(user_id)
        
        return {
            'user_id': user_id,
            'is_admin': config.is_admin(user_id),
            'allowed': result.allowed,
            'remaining': result.remaining,
            'reset_time': result.reset_time,
            'retry_after': result.retry_after,
            'max_requests': (
                int(self.max_requests * self.admin_multiplier) 
                if config.is_admin(user_id) 
                else self.max_requests
            ),
            'window_seconds': self.window_seconds
        }
    
    def get_stats(self) -> Dict:
        """Get rate limiter statistics."""
        total = self._stats['total_requests']
        blocked_rate = (
            self._stats['blocked_requests'] / total 
            if total > 0 else 0
        )
        
        return {
            **self._stats,
            'blocked_rate': f"{blocked_rate:.2%}",
            'strategy': self.strategy.value,
            'max_requests_user': self.max_requests,
            'max_requests_admin': int(self.max_requests * self.admin_multiplier),
            'window_seconds': self.window_seconds
        }
    
    def cleanup_expired(self) -> int:
        """Clean up expired rate limit data."""
        # This would be implemented based on the specific limiter type
        # For now, return 0 as a placeholder
        return 0
    
    def reset_user_limits(self, user_id: int) -> bool:
        """Reset rate limits for a specific user (admin function)."""
        try:
            if hasattr(self.user_limiter, 'requests'):
                self.user_limiter.requests.pop(user_id, None)
            if hasattr(self.admin_limiter, 'requests'):
                self.admin_limiter.requests.pop(user_id, None)
            if hasattr(self.user_limiter, 'buckets'):
                self.user_limiter.buckets.pop(user_id, None)
            if hasattr(self.admin_limiter, 'buckets'):
                self.admin_limiter.buckets.pop(user_id, None)
            
            logger.info(f"Reset rate limits for user {user_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to reset rate limits for user {user_id}: {e}")
            return False

# Global rate limiter instance
default_rate_limiter = RateLimiter()

# Convenience functions for backward compatibility
def is_rate_limited(user_id: int) -> bool:
    """Check if user is rate limited."""
    return default_rate_limiter.is_rate_limited(user_id)

def get_rate_limit_status(user_id: int) -> Dict:
    """Get rate limit status for user."""
    return default_rate_limiter.get_user_status(user_id)