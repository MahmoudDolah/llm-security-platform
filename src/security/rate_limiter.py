"""
Rate Limiting Module

Implements token bucket algorithm for rate limiting using Redis.
"""

import time
from typing import Optional, Tuple, Dict
import redis
from dataclasses import dataclass


@dataclass
class RateLimitResult:
    """Result of rate limit check"""

    allowed: bool
    remaining: int
    reset_time: int
    retry_after: Optional[int] = None


class TokenBucket:
    """
    Token bucket algorithm implementation.

    This is a shared implementation used by both Redis and in-memory rate limiters.
    """

    def __init__(self, requests_per_minute: int, burst_size: int):
        """
        Initialize token bucket parameters.

        Args:
            requests_per_minute: Maximum requests per minute
            burst_size: Maximum burst size (tokens that can accumulate)
        """
        self.rate = requests_per_minute
        self.burst_size = burst_size
        self.refill_rate = requests_per_minute / 60.0  # tokens per second

    def calculate_tokens(
        self, current_tokens: float, last_refill: float, current_time: float
    ) -> float:
        """
        Calculate current token count after refill.

        Args:
            current_tokens: Current number of tokens
            last_refill: Last refill timestamp
            current_time: Current timestamp

        Returns:
            Updated token count (capped at burst_size)
        """
        time_elapsed = current_time - last_refill
        tokens_to_add = time_elapsed * self.refill_rate
        return min(current_tokens + tokens_to_add, float(self.burst_size))

    def check_and_consume(
        self, tokens: float, current_time: float
    ) -> Tuple[bool, float, Optional[int]]:
        """
        Check if request is allowed and consume a token if so.

        Args:
            tokens: Current token count
            current_time: Current timestamp

        Returns:
            Tuple of (allowed, new_token_count, retry_after_seconds)
        """
        if tokens >= 1.0:
            # Allow request, consume 1 token
            new_tokens = tokens - 1.0
            allowed = True
            retry_after = None
        else:
            # Deny request
            new_tokens = tokens
            allowed = False
            # Calculate time until next token
            time_for_token = (1.0 - tokens) / self.refill_rate
            retry_after = int(time_for_token) + 1

        return allowed, new_tokens, retry_after

    def calculate_reset_time(self, tokens: float, current_time: float) -> int:
        """
        Calculate when the bucket will be full again.

        Args:
            tokens: Current token count
            current_time: Current timestamp

        Returns:
            Unix timestamp when bucket will be full
        """
        tokens_until_full = self.burst_size - tokens
        return int(current_time + (tokens_until_full / self.refill_rate))


class RateLimiter:
    """
    Token bucket rate limiter using Redis.

    Prevents abuse by limiting requests per user/API key.
    """

    def __init__(
        self, redis_url: str, requests_per_minute: int = 60, burst_size: int = 10
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
        self.bucket = TokenBucket(requests_per_minute, burst_size)

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
            tokens = float(self.bucket.burst_size)
            last_refill = current_time
        else:
            tokens = float(tokens_str)
            last_refill = float(last_refill_str)

        # Calculate tokens after refill
        tokens = self.bucket.calculate_tokens(tokens, last_refill, current_time)

        # Check if allowed and consume token
        allowed, tokens, retry_after = self.bucket.check_and_consume(
            tokens, current_time
        )

        # Save updated state
        pipe = self.redis_client.pipeline()
        pipe.set(f"{key}:tokens", str(tokens), ex=3600)  # 1 hour expiry
        pipe.set(f"{key}:last_refill", str(current_time), ex=3600)
        pipe.execute()

        # Calculate reset time
        reset_time = self.bucket.calculate_reset_time(tokens, current_time)

        return RateLimitResult(
            allowed=allowed,
            remaining=int(tokens),
            reset_time=reset_time,
            retry_after=retry_after,
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
            return (0, self.bucket.burst_size)

        available = int(float(tokens_str))
        used = self.bucket.burst_size - available
        return (used, available)


class InMemoryRateLimiter:
    """
    In-memory rate limiter for testing/development.

    Not suitable for production with multiple instances.
    """

    def __init__(self, requests_per_minute: int = 60, burst_size: int = 10):
        self.bucket = TokenBucket(requests_per_minute, burst_size)
        self.buckets: Dict[str, Tuple[float, float]] = (
            {}
        )  # identifier -> (tokens, last_refill)

    def check_rate_limit(self, identifier: str) -> RateLimitResult:
        """Check rate limit using in-memory storage"""
        current_time = time.time()

        # Get or initialize bucket
        if identifier not in self.buckets:
            self.buckets[identifier] = (float(self.bucket.burst_size), current_time)

        tokens, last_refill = self.buckets[identifier]

        # Calculate tokens after refill
        tokens = self.bucket.calculate_tokens(tokens, last_refill, current_time)

        # Check if allowed and consume token
        allowed, tokens, retry_after = self.bucket.check_and_consume(
            tokens, current_time
        )

        # Update bucket
        self.buckets[identifier] = (tokens, current_time)

        # Calculate reset time
        reset_time = self.bucket.calculate_reset_time(tokens, current_time)

        return RateLimitResult(
            allowed=allowed,
            remaining=int(tokens),
            reset_time=reset_time,
            retry_after=retry_after,
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
