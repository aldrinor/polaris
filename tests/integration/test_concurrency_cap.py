"""
Integration tests for LLM provider concurrency semaphore and retry logic.

Tests REAL asyncio primitives, REAL Semaphore instances, and REAL concurrent
coroutines. Zero mocks, zero placeholders. All retry tests use real (short)
delays to exercise genuine backoff behavior.

Modules under test:
    src/providers/llm_provider.py
        - get_semaphore()
        - reset_semaphore()
        - retry_with_backoff()
        - RateLimitError, ServerOverloadError
        - _MAX_CONCURRENT_LLM

LAW II:  All assertions verify real runtime behavior.
LAW VI: Concurrency cap read from env / module attribute, not hard-coded.
"""

import asyncio

import pytest

import src.providers.llm_provider as llm_mod
from src.providers.llm_provider import (
    RateLimitError,
    ServerOverloadError,
    get_semaphore,
    reset_semaphore,
    retry_with_backoff,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clean_semaphore(monkeypatch):
    """Reset the global semaphore singleton before and after every test.

    F16 (A3): get_semaphore() now reads PG_MAX_CONCURRENT_LLM from the live env at
    creation time (so the Gate-B slate can set the cap). These tests exercise the
    MODULE-ATTR fallback (`_MAX_CONCURRENT_LLM`, monkeypatched per test), so the env
    override must be UNSET — otherwise an ambient/leaked PG_MAX_CONCURRENT_LLM (e.g.
    from a sibling test that applies the benchmark slate) would win over the
    monkeypatched module attribute. Clearing it keeps these tests hermetic."""
    monkeypatch.delenv("PG_MAX_CONCURRENT_LLM", raising=False)
    reset_semaphore()
    yield
    reset_semaphore()


# ---------------------------------------------------------------------------
# 1-3: Singleton lifecycle
# ---------------------------------------------------------------------------


class TestSemaphoreSingleton:
    """Verify lazy-singleton creation, identity, and reset."""

    def test_get_semaphore_returns_asyncio_semaphore(self):
        """get_semaphore() must return a real asyncio.Semaphore instance."""
        sem = get_semaphore()
        assert isinstance(sem, asyncio.Semaphore), (
            f"Expected asyncio.Semaphore, got {type(sem).__name__}"
        )

    def test_get_semaphore_is_singleton(self):
        """Two consecutive calls must return the exact same object."""
        first = get_semaphore()
        second = get_semaphore()
        assert first is second, "Semaphore must be a singleton across calls"

    def test_reset_semaphore_yields_new_instance(self):
        """After reset_semaphore(), the next call must return a NEW object."""
        original = get_semaphore()
        reset_semaphore()
        replacement = get_semaphore()
        assert replacement is not original, (
            "reset_semaphore() must invalidate the previous singleton"
        )
        assert isinstance(replacement, asyncio.Semaphore)


# ---------------------------------------------------------------------------
# 4-5: Concurrency enforcement
# ---------------------------------------------------------------------------


class TestConcurrencyEnforcement:
    """Verify the semaphore actually limits peak concurrent coroutines."""

    @pytest.mark.asyncio
    async def test_peak_concurrency_with_cap_2(self, monkeypatch):
        """With cap=2 and 5 workers, peak concurrent tasks must never exceed 2."""
        monkeypatch.setattr(llm_mod, "_MAX_CONCURRENT_LLM", 2)
        reset_semaphore()
        sem = get_semaphore()

        peak = 0
        current = 0
        lock = asyncio.Lock()

        async def worker():
            nonlocal peak, current
            async with sem:
                async with lock:
                    current += 1
                    peak = max(peak, current)
                await asyncio.sleep(0.05)
                async with lock:
                    current -= 1

        await asyncio.gather(*[worker() for _ in range(5)])
        assert peak <= 2, f"Peak concurrency {peak} exceeded cap of 2"
        assert peak >= 1, "At least one worker must have run"

    @pytest.mark.asyncio
    async def test_sequential_execution_with_cap_1(self, monkeypatch):
        """With cap=1, tasks must run strictly sequentially (peak == 1)."""
        monkeypatch.setattr(llm_mod, "_MAX_CONCURRENT_LLM", 1)
        reset_semaphore()
        sem = get_semaphore()

        peak = 0
        current = 0
        lock = asyncio.Lock()

        async def worker():
            nonlocal peak, current
            async with sem:
                async with lock:
                    current += 1
                    peak = max(peak, current)
                await asyncio.sleep(0.03)
                async with lock:
                    current -= 1

        await asyncio.gather(*[worker() for _ in range(4)])
        assert peak == 1, f"Peak concurrency {peak} must be exactly 1 with cap=1"


# ---------------------------------------------------------------------------
# 6-7: Environment variable driven configuration
# ---------------------------------------------------------------------------


class TestEnvironmentConfiguration:
    """Verify the semaphore reads its cap from env / module attributes."""

    def test_semaphore_respects_module_attribute(self, monkeypatch):
        """Monkeypatching _MAX_CONCURRENT_LLM changes the Semaphore capacity."""
        monkeypatch.setattr(llm_mod, "_MAX_CONCURRENT_LLM", 7)
        reset_semaphore()
        sem = get_semaphore()
        # asyncio.Semaphore stores its value in _value
        assert sem._value == 7, (
            f"Semaphore initial value {sem._value} != patched cap 7"
        )

    def test_default_cap_is_5(self):
        """When PG_MAX_CONCURRENT_LLM is not overridden, default is 5."""
        # The module-level default is read at import time.  We verify the
        # constant itself, which was resolved from os.getenv with default "5".
        from src.providers.llm_provider import _MAX_CONCURRENT_LLM
        # The value may have been overridden by .env, so we re-derive:
        import os
        expected = int(os.getenv("PG_MAX_CONCURRENT_LLM", "5"))
        assert _MAX_CONCURRENT_LLM == expected, (
            f"_MAX_CONCURRENT_LLM={_MAX_CONCURRENT_LLM} != expected {expected}"
        )


# ---------------------------------------------------------------------------
# 8: Semaphore release on exception
# ---------------------------------------------------------------------------


class TestSemaphoreExceptionSafety:
    """Ensure the semaphore is released even when a coroutine raises."""

    @pytest.mark.asyncio
    async def test_semaphore_releases_on_exception(self, monkeypatch):
        """After a crash inside ``async with sem``, the slot must be freed."""
        monkeypatch.setattr(llm_mod, "_MAX_CONCURRENT_LLM", 1)
        reset_semaphore()
        sem = get_semaphore()

        # First coroutine: acquire, then raise
        with pytest.raises(RuntimeError, match="deliberate"):
            async with sem:
                raise RuntimeError("deliberate crash")

        # Second coroutine: must be able to acquire without blocking
        acquired = False

        async def probe():
            nonlocal acquired
            async with sem:
                acquired = True

        # If the semaphore leaked, this would hang forever.  We use a timeout.
        await asyncio.wait_for(probe(), timeout=2.0)
        assert acquired, "Semaphore must release its slot after an exception"


# ---------------------------------------------------------------------------
# 9-12: retry_with_backoff
# ---------------------------------------------------------------------------


class TestRetryWithBackoff:
    """Exercise real exponential-backoff retry logic with short delays."""

    @pytest.mark.asyncio
    async def test_succeeds_on_first_attempt(self):
        """When fn() succeeds immediately, result is returned and no retry."""
        call_count = 0

        async def always_ok():
            nonlocal call_count
            call_count += 1
            return "first_try"

        result = await retry_with_backoff(
            always_ok, max_retries=3, base_delay=0.01,
        )
        assert result == "first_try"
        assert call_count == 1, "Should call fn exactly once on success"

    @pytest.mark.asyncio
    async def test_retries_on_rate_limit_error(self):
        """RateLimitError on attempt 1 triggers retry; succeeds on attempt 2."""
        attempts = 0

        async def flaky_rate_limit():
            nonlocal attempts
            attempts += 1
            if attempts < 2:
                raise RateLimitError("429 Too Many Requests")
            return "recovered"

        result = await retry_with_backoff(
            flaky_rate_limit, max_retries=3, base_delay=0.01,
        )
        assert result == "recovered"
        assert attempts == 2, f"Expected 2 attempts, got {attempts}"

    @pytest.mark.asyncio
    async def test_retries_on_server_overload_error(self):
        """ServerOverloadError on attempt 1 triggers retry; succeeds on attempt 2."""
        attempts = 0

        async def flaky_overload():
            nonlocal attempts
            attempts += 1
            if attempts < 2:
                raise ServerOverloadError("503 Service Unavailable")
            return "back_online"

        result = await retry_with_backoff(
            flaky_overload, max_retries=3, base_delay=0.01,
        )
        assert result == "back_online"
        assert attempts == 2, f"Expected 2 attempts, got {attempts}"

    @pytest.mark.asyncio
    async def test_retries_on_timeout_error(self):
        """TimeoutError triggers retry logic identically to rate-limit errors."""
        attempts = 0

        async def flaky_timeout():
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise TimeoutError("request timed out")
            return "finally"

        result = await retry_with_backoff(
            flaky_timeout, max_retries=3, base_delay=0.01,
        )
        assert result == "finally"
        assert attempts == 3, f"Expected 3 attempts, got {attempts}"

    @pytest.mark.asyncio
    async def test_exhausts_retries_raises_last_exception(self):
        """When all retries fail, the LAST exception must propagate."""
        attempts = 0

        async def always_fails():
            nonlocal attempts
            attempts += 1
            raise RateLimitError(f"attempt_{attempts}")

        with pytest.raises(RateLimitError, match="attempt_4"):
            await retry_with_backoff(
                always_fails, max_retries=3, base_delay=0.01,
            )
        # max_retries=3 means initial attempt + 3 retries = 4 total
        assert attempts == 4, (
            f"Expected 4 total attempts (1 initial + 3 retries), got {attempts}"
        )

    @pytest.mark.asyncio
    async def test_non_retryable_exception_propagates_immediately(self):
        """Exceptions NOT in the retry set must propagate without retry."""
        attempts = 0

        async def value_error_fn():
            nonlocal attempts
            attempts += 1
            raise ValueError("bad input")

        with pytest.raises(ValueError, match="bad input"):
            await retry_with_backoff(
                value_error_fn, max_retries=3, base_delay=0.01,
            )
        assert attempts == 1, (
            "Non-retryable exception must propagate on first attempt"
        )

    @pytest.mark.asyncio
    async def test_retry_delay_is_real(self):
        """Verify that retry_with_backoff actually waits (real async sleep).

        The delay formula is: base_delay * 2^attempt + random.uniform(0, 1).
        With base_delay=0.05 and 2 retries:
          - Retry 0: >= 0.05s  (0.05*1 + jitter)
          - Retry 1: >= 0.10s  (0.05*2 + jitter)
        Each delay includes random jitter in [0, 1), so we only assert
        that each delay exceeds the deterministic minimum (base_delay * 2^attempt)
        and that real wall-clock time elapsed (total > sum of minimums).
        """
        import time

        attempts = 0
        timestamps = []

        async def timed_flaky():
            nonlocal attempts
            attempts += 1
            timestamps.append(time.monotonic())
            if attempts < 3:
                raise ServerOverloadError("overloaded")
            return "done"

        result = await retry_with_backoff(
            timed_flaky, max_retries=3, base_delay=0.05,
        )
        assert result == "done"
        assert len(timestamps) == 3

        # Verify each retry involved a real delay (not zero-time)
        delay_1 = timestamps[1] - timestamps[0]
        delay_2 = timestamps[2] - timestamps[1]

        # Minimum delay per retry: base_delay * 2^attempt (jitter adds [0, 1))
        # Attempt 0: 0.05 * 2^0 = 0.05s minimum
        # Attempt 1: 0.05 * 2^1 = 0.10s minimum
        assert delay_1 >= 0.04, (
            f"First retry delay {delay_1:.4f}s too short "
            f"(expected >= base_delay * 2^0 = 0.05s, with tolerance)"
        )
        assert delay_2 >= 0.09, (
            f"Second retry delay {delay_2:.4f}s too short "
            f"(expected >= base_delay * 2^1 = 0.10s, with tolerance)"
        )

        # Total elapsed time must exceed sum of deterministic minimums
        total_elapsed = timestamps[-1] - timestamps[0]
        min_total = 0.05 + 0.10  # 0.15s without jitter
        assert total_elapsed >= min_total * 0.8, (
            f"Total elapsed {total_elapsed:.4f}s too short "
            f"(expected >= {min_total * 0.8:.4f}s)"
        )
