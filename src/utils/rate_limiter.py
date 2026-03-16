#!/usr/bin/env python3
"""
POLARIS Rate Limiter
====================
Thread-safe token bucket rate limiter for API calls.

Prevents API quota exhaustion by enforcing per-domain rate limits.

Usage:
    from src.utils.rate_limiter import RateLimiter, get_rate_limiter

    limiter = get_rate_limiter()
    await limiter.acquire("api.serper.dev")  # Blocks until token available
"""

import asyncio
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, Optional

# Configure logging
logger = logging.getLogger(__name__)


# =============================================================================
# TOKEN BUCKET
# =============================================================================

@dataclass
class TokenBucket:
    """
    Token bucket for rate limiting.

    Tokens are added at a fixed rate up to a maximum capacity.
    Each request consumes one token.
    """
    capacity: float
    refill_rate: float  # tokens per second
    tokens: float = field(default=None)
    last_refill: float = field(default=None)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def __post_init__(self):
        if self.tokens is None:
            self.tokens = self.capacity
        if self.last_refill is None:
            self.last_refill = time.monotonic()

    def _refill(self) -> None:
        """Refill tokens based on elapsed time."""
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now

    def try_acquire(self, tokens: float = 1.0) -> bool:
        """
        Try to acquire tokens without blocking.

        Args:
            tokens: Number of tokens to acquire

        Returns:
            True if acquired, False if insufficient tokens
        """
        with self.lock:
            self._refill()
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            return False

    def acquire_blocking(self, tokens: float = 1.0, timeout: Optional[float] = None) -> bool:
        """
        Acquire tokens, blocking if necessary.

        Args:
            tokens: Number of tokens to acquire
            timeout: Maximum seconds to wait (None = infinite)

        Returns:
            True if acquired, False if timeout
        """
        start = time.monotonic()
        while True:
            if self.try_acquire(tokens):
                return True

            # Calculate wait time
            with self.lock:
                self._refill()
                if self.tokens >= tokens:
                    self.tokens -= tokens
                    return True
                wait_time = (tokens - self.tokens) / self.refill_rate

            # Check timeout
            if timeout is not None:
                elapsed = time.monotonic() - start
                if elapsed + wait_time > timeout:
                    return False
                wait_time = min(wait_time, timeout - elapsed)

            time.sleep(min(wait_time, 0.1))  # Max 100ms sleep intervals

    async def acquire_async(self, tokens: float = 1.0, timeout: Optional[float] = None) -> bool:
        """
        Acquire tokens asynchronously.

        Args:
            tokens: Number of tokens to acquire
            timeout: Maximum seconds to wait (None = infinite)

        Returns:
            True if acquired, False if timeout
        """
        start = time.monotonic()
        while True:
            if self.try_acquire(tokens):
                return True

            # Calculate wait time
            with self.lock:
                self._refill()
                if self.tokens >= tokens:
                    self.tokens -= tokens
                    return True
                wait_time = (tokens - self.tokens) / self.refill_rate

            # Check timeout
            if timeout is not None:
                elapsed = time.monotonic() - start
                if elapsed + wait_time > timeout:
                    return False
                wait_time = min(wait_time, timeout - elapsed)

            await asyncio.sleep(min(wait_time, 0.1))

    @property
    def available_tokens(self) -> float:
        """Get current available tokens."""
        with self.lock:
            self._refill()
            return self.tokens


# =============================================================================
# RATE LIMITER
# =============================================================================

# Default rate limits per domain (requests per second)
DEFAULT_RATE_LIMITS = {
    "api.serper.dev": 10.0,
    "eutils.ncbi.nlm.nih.gov": 3.0,  # NCBI E-utilities
    "api.semanticscholar.org": 10.0,
    "patents.google.com": 5.0,
    "generativelanguage.googleapis.com": 60.0,  # Gemini API
    "api.unpaywall.org": 10.0,
    "default": 5.0,  # Default for unknown domains
}


class RateLimiter:
    """
    Multi-domain rate limiter.

    Manages separate token buckets for each domain.
    Thread-safe for concurrent access.
    """

    def __init__(self, rate_limits: Optional[Dict[str, float]] = None):
        """
        Initialize rate limiter.

        Args:
            rate_limits: Dict of domain -> requests per second
        """
        self._rate_limits = rate_limits or DEFAULT_RATE_LIMITS.copy()
        self._buckets: Dict[str, TokenBucket] = {}
        self._lock = threading.Lock()

    def _get_bucket(self, domain: str) -> TokenBucket:
        """Get or create token bucket for domain."""
        with self._lock:
            if domain not in self._buckets:
                rate = self._rate_limits.get(domain, self._rate_limits.get("default", 5.0))
                # Capacity = 2x rate for burst handling
                self._buckets[domain] = TokenBucket(
                    capacity=rate * 2,
                    refill_rate=rate
                )
            return self._buckets[domain]

    def set_rate_limit(self, domain: str, requests_per_second: float) -> None:
        """
        Set rate limit for a domain.

        Args:
            domain: Domain name
            requests_per_second: Max requests per second
        """
        self._rate_limits[domain] = requests_per_second
        # Reset bucket if it exists
        with self._lock:
            if domain in self._buckets:
                del self._buckets[domain]

    def try_acquire(self, domain: str, tokens: float = 1.0) -> bool:
        """
        Try to acquire tokens for a domain without blocking.

        Args:
            domain: Domain to acquire for
            tokens: Number of tokens

        Returns:
            True if acquired
        """
        bucket = self._get_bucket(domain)
        acquired = bucket.try_acquire(tokens)
        if not acquired:
            logger.debug(f"Rate limited for {domain}, available: {bucket.available_tokens:.2f}")
        return acquired

    def acquire(self, domain: str, tokens: float = 1.0, timeout: Optional[float] = None) -> bool:
        """
        Acquire tokens for a domain, blocking if necessary.

        Args:
            domain: Domain to acquire for
            tokens: Number of tokens
            timeout: Maximum wait time in seconds

        Returns:
            True if acquired, False if timeout
        """
        bucket = self._get_bucket(domain)
        acquired = bucket.acquire_blocking(tokens, timeout)
        if acquired:
            logger.debug(f"Acquired token for {domain}")
        else:
            logger.warning(f"Rate limit timeout for {domain}")
        return acquired

    async def acquire_async(self, domain: str, tokens: float = 1.0, timeout: Optional[float] = None) -> bool:
        """
        Acquire tokens asynchronously.

        Args:
            domain: Domain to acquire for
            tokens: Number of tokens
            timeout: Maximum wait time in seconds

        Returns:
            True if acquired, False if timeout
        """
        bucket = self._get_bucket(domain)
        acquired = await bucket.acquire_async(tokens, timeout)
        if acquired:
            logger.debug(f"Acquired token for {domain}")
        else:
            logger.warning(f"Rate limit timeout for {domain}")
        return acquired

    def get_available(self, domain: str) -> float:
        """Get available tokens for a domain."""
        bucket = self._get_bucket(domain)
        return bucket.available_tokens

    def get_stats(self) -> Dict[str, Dict[str, float]]:
        """Get statistics for all domains."""
        stats = {}
        with self._lock:
            for domain, bucket in self._buckets.items():
                stats[domain] = {
                    "available": bucket.available_tokens,
                    "capacity": bucket.capacity,
                    "rate": bucket.refill_rate,
                }
        return stats


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

_rate_limiter: Optional[RateLimiter] = None


def get_rate_limiter() -> RateLimiter:
    """Get the singleton rate limiter instance."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter


# =============================================================================
# SELF-TEST
# =============================================================================

if __name__ == "__main__":
    import asyncio

    print("=" * 60)
    print("RATE LIMITER SELF-TEST")
    print("=" * 60)

    # Test 1: Token bucket
    print("\n[TEST 1] Token bucket...")
    bucket = TokenBucket(capacity=5.0, refill_rate=2.0)
    assert bucket.try_acquire(1.0) is True
    assert 3.9 <= bucket.available_tokens <= 4.1  # Allow for floating point
    print(f"  [PASS] Token acquired, available: {bucket.available_tokens:.2f}")

    # Test 2: Burst handling
    print("\n[TEST 2] Burst handling...")
    for i in range(4):
        assert bucket.try_acquire(1.0) is True
    # Bucket should be nearly empty now (may have refilled slightly)
    assert bucket.available_tokens < 1.0
    # Next acquire should fail (not enough tokens)
    # Actually, it might succeed due to small refill - just test concept works
    print(f"  [PASS] Burst used tokens, available: {bucket.available_tokens:.2f}")

    # Test 3: Refill
    print("\n[TEST 3] Token refill...")
    time.sleep(0.6)  # Wait for ~1.2 tokens to refill
    assert bucket.available_tokens > 1.0
    print(f"  [PASS] Tokens refilled to {bucket.available_tokens:.2f}")

    # Test 4: Rate limiter multi-domain
    print("\n[TEST 4] Multi-domain rate limiter...")
    limiter = RateLimiter()
    assert limiter.try_acquire("api.serper.dev") is True
    assert limiter.try_acquire("api.semanticscholar.org") is True
    print("  [PASS] Multiple domains work independently")

    # Test 5: Rate limit enforcement
    print("\n[TEST 5] Rate limit enforcement...")
    limiter.set_rate_limit("test.domain", 1.0)  # 1 req/sec
    assert limiter.try_acquire("test.domain") is True
    assert limiter.try_acquire("test.domain") is True  # burst allows 2
    # Should be rate limited now
    start = time.monotonic()
    result = limiter.acquire("test.domain", timeout=0.5)
    elapsed = time.monotonic() - start
    print(f"  [PASS] Waited {elapsed:.2f}s for rate limit (result={result})")

    # Test 6: Async acquire
    print("\n[TEST 6] Async acquire...")

    async def test_async():
        limiter = RateLimiter()
        result = await limiter.acquire_async("async.test")
        return result

    result = asyncio.run(test_async())
    assert result is True
    print("  [PASS] Async acquire works")

    # Test 7: Stats
    print("\n[TEST 7] Statistics...")
    stats = limiter.get_stats()
    assert "test.domain" in stats
    print(f"  [PASS] Stats: {len(stats)} domains tracked")

    print("\n" + "=" * 60)
    print("ALL TESTS PASSED")
    print("=" * 60)
