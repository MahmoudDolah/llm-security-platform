"""
Rate Limiting Module

Implements token bucket algorithm for rate limiting using Redis.
"""
import time
from typing import Optional, Tuple
import redis
from dataclasses import dataclass


@dataclass
class RateLimitResult:
    """Result of rate limit check"""
    allowed: bool
    remaining: int
    reset_time: int
    retry_after: Optional[int] = None


class RateLimiter:
    """
    Token bucket rate limiter using Redis.
    
    Prevents abuse by limiting requests per user/API key.
    """
    
    def __init__(
        self,
        redis_url: str,
        requests_per_minute: int = 60,
        burst_size: int = 10
    ):
        """
        Initialize rate limiter.

        Args:
            redis_url: Redis connection URL
            requests_per_minute: Maximum requests per minute
            burst_size: Maximum burst size (tokens that can accumulate)

        Raises:
            redis.exceptions.ConnectionError: If Redis connection fails
        """
        self.redis_client = redis.from_url(redis_url, decode_responses=True)
        # Test the connection immediately
        self.redis_client.ping()
        self.rate = requests_per_minute
        self.burst_size = burst_size
        self.refill_rate = requests_per_minute / 60.0  # tokens per second
    
    def _get_key(self, identifier: str) -> str:
        """Generate Redis key for rate limit tracking"""
        return f"rate_limit:{identifier}"
    
    def check_rate_limit(self, identifier: str) -> RateLimitResult:
        """
        Check if request is allowed under rate limit.
        
        Args:
            identifier: Unique identifier (e.g., API key, user ID)
            
        Returns:
            RateLimitResult indicating if request is allowed
        """
        key = self._get_key(identifier)
        current_time = time.time()
        
        # Get or initialize bucket state
        pipe = self.redis_client.pipeline()
        pipe.get(f"{key}:tokens")
        pipe.get(f"{key}:last_refill")
        tokens_str, last_refill_str = pipe.execute()
        
        # Initialize if doesn't exist
        if tokens_str is None:
            tokens = float(self.burst_size)
            last_refill = current_time
        else:
            tokens = float(tokens_str)
            last_refill = float(last_refill_str)
        
        # Calculate tokens to add based on time elapsed
        time_elapsed = current_time - last_refill
        tokens_to_add = time_elapsed * self.refill_rate
        tokens = min(tokens + tokens_to_add, float(self.burst_size))
        
        # Check if request can be allowed
        if tokens >= 1.0:
            # Allow request, consume 1 token
            tokens -= 1.0
            allowed = True
            retry_after = None
        else:
            # Deny request
            allowed = False
            # Calculate time until next token
            time_for_token = (1.0 - tokens) / self.refill_rate
            retry_after = int(time_for_token) + 1
        
        # Save updated state
        pipe = self.redis_client.pipeline()
        pipe.set(f"{key}:tokens", str(tokens), ex=3600)  # 1 hour expiry
        pipe.set(f"{key}:last_refill", str(current_time), ex=3600)
        pipe.execute()
        
        # Calculate reset time (when bucket will be full again)
        tokens_until_full = self.burst_size - tokens
        reset_time = int(current_time + (tokens_until_full / self.refill_rate))
        
        return RateLimitResult(
            allowed=allowed,
            remaining=int(tokens),
            reset_time=reset_time,
            retry_after=retry_after
        )
    
    def reset(self, identifier: str):
        """Reset rate limit for an identifier"""
        key = self._get_key(identifier)
        self.redis_client.delete(f"{key}:tokens", f"{key}:last_refill")
    
    def get_usage(self, identifier: str) -> Tuple[int, int]:
        """
        Get current usage statistics.
        
        Returns:
            Tuple of (used_tokens, available_tokens)
        """
        key = self._get_key(identifier)
        tokens_str = self.redis_client.get(f"{key}:tokens")
        
        if tokens_str is None:
            return (0, self.burst_size)
        
        available = int(float(tokens_str))
        used = self.burst_size - available
        return (used, available)


class InMemoryRateLimiter:
    """
    In-memory rate limiter for testing/development.
    
    Not suitable for production with multiple instances.
    """
    
    def __init__(self, requests_per_minute: int = 60, burst_size: int = 10):
        self.rate = requests_per_minute
        self.burst_size = burst_size
        self.refill_rate = requests_per_minute / 60.0
        self.buckets = {}  # identifier -> (tokens, last_refill)
    
    def check_rate_limit(self, identifier: str) -> RateLimitResult:
        """Check rate limit using in-memory storage"""
        current_time = time.time()
        
        # Get or initialize bucket
        if identifier not in self.buckets:
            self.buckets[identifier] = (float(self.burst_size), current_time)
        
        tokens, last_refill = self.buckets[identifier]
        
        # Refill tokens
        time_elapsed = current_time - last_refill
        tokens_to_add = time_elapsed * self.refill_rate
        tokens = min(tokens + tokens_to_add, float(self.burst_size))
        
        # Check if allowed
        if tokens >= 1.0:
            tokens -= 1.0
            allowed = True
            retry_after = None
        else:
            allowed = False
            time_for_token = (1.0 - tokens) / self.refill_rate
            retry_after = int(time_for_token) + 1
        
        # Update bucket
        self.buckets[identifier] = (tokens, current_time)
        
        # Calculate reset time
        tokens_until_full = self.burst_size - tokens
        reset_time = int(current_time + (tokens_until_full / self.refill_rate))
        
        return RateLimitResult(
            allowed=allowed,
            remaining=int(tokens),
            reset_time=reset_time,
            retry_after=retry_after
        )
    
    def reset(self, identifier: str):
        """Reset rate limit"""
        if identifier in self.buckets:
            del self.buckets[identifier]


# Example usage
if __name__ == "__main__":
    # Test with in-memory limiter
    limiter = InMemoryRateLimiter(requests_per_minute=10, burst_size=5)
    
    # Simulate requests
    for i in range(10):
        result = limiter.check_rate_limit("user123")
        print(f"Request {i+1}: Allowed={result.allowed}, Remaining={result.remaining}")
        if not result.allowed:
            print(f"  Rate limited! Retry after {result.retry_after}s")
        time.sleep(0.1)
