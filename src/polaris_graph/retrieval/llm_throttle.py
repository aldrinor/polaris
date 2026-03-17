"""LLM Concurrency Throttle (Fix R5-#3).

When LangGraph fires 15 parallel Section Writer nodes via Send, all 15 will
call the LLM API simultaneously, blasting ~200,000 tokens at OpenRouter in
a single millisecond. This instantly exceeds Tokens-Per-Minute (TPM) limits,
triggering a wall of 429 errors that crashes asyncio.gather.

This module provides a shared semaphore + retry wrapper for ALL LLM calls
in the v2 synthesis and verification pipeline.

Usage:
    from src.polaris_graph.retrieval.llm_throttle import throttled_llm_call

    result = await throttled_llm_call(
        client.generate,
        prompt="Write a section about...",
        system="You are a research writer...",
        max_tokens=4096,
    )
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
from typing import Any, Callable, Coroutine

logger = logging.getLogger("polaris_graph")

# Max concurrent LLM calls — prevents TPM burst
# 3-4 is safe for most OpenRouter model tiers
LLM_CONCURRENCY = int(os.getenv("PG_LLM_CONCURRENCY", "4"))

# Retry config for 429/502 (TPM exceeded, gateway errors)
LLM_MAX_RETRIES = int(os.getenv("PG_LLM_MAX_RETRIES", "5"))
LLM_RETRY_BASE = float(os.getenv("PG_LLM_RETRY_BASE", "3.0"))
LLM_RETRY_MAX = float(os.getenv("PG_LLM_RETRY_MAX", "60.0"))

# Per-call timeout
LLM_CALL_TIMEOUT = int(os.getenv("PG_LLM_CALL_TIMEOUT", "300"))

# Module-level semaphore (lazy-init inside event loop)
_llm_semaphore: asyncio.Semaphore | None = None


def _get_semaphore() -> asyncio.Semaphore:
    """Lazy-init semaphore (must be inside event loop)."""
    global _llm_semaphore
    if _llm_semaphore is None:
        _llm_semaphore = asyncio.Semaphore(LLM_CONCURRENCY)
        logger.info("LLM throttle initialized: max %d concurrent calls", LLM_CONCURRENCY)
    return _llm_semaphore


# HTTP status codes that warrant retry
_RETRYABLE_CODES = {"429", "502", "503", "504", "rate limit", "too many requests"}


async def throttled_llm_call(
    fn: Callable[..., Coroutine[Any, Any, Any]],
    *args: Any,
    **kwargs: Any,
) -> Any:
    """Execute an async LLM call with semaphore throttling and retry.

    Fix R5-#3: Prevents TPM burst by limiting concurrent LLM calls
    to PG_LLM_CONCURRENCY (default 4). Retries on 429/5xx with
    exponential backoff + jitter.

    Args:
        fn: Async LLM function (e.g., client.generate, client.generate_structured).
        *args, **kwargs: Passed through to fn.

    Returns:
        Whatever fn returns.

    Raises:
        Exception: After LLM_MAX_RETRIES exhausted.
    """
    sem = _get_semaphore()

    last_error: Exception | None = None
    for attempt in range(1, LLM_MAX_RETRIES + 1):
        async with sem:
            try:
                result = await asyncio.wait_for(
                    fn(*args, **kwargs),
                    timeout=LLM_CALL_TIMEOUT,
                )
                return result

            except asyncio.CancelledError:
                # Fix R6-#3: HARD STOP from graph timeout or shutdown.
                # NEVER retry — the graph is killing this node. If we
                # catch and retry, we create an unkillable zombie that
                # hangs the entire graph forever.
                logger.warning("LLM call cancelled by graph (attempt %d)", attempt)
                raise

            except asyncio.TimeoutError:
                # This is OUR per-call timeout (LLM_CALL_TIMEOUT).
                # Safe to retry — the individual call timed out, but the
                # graph hasn't cancelled us yet.
                last_error = TimeoutError(
                    f"LLM call timed out after {LLM_CALL_TIMEOUT}s (attempt {attempt})"
                )
                logger.warning(
                    "LLM timeout (%ds), attempt %d/%d",
                    LLM_CALL_TIMEOUT, attempt, LLM_MAX_RETRIES,
                )

            except Exception as e:
                last_error = e
                error_str = str(e).lower()
                is_retryable = any(code in error_str for code in _RETRYABLE_CODES)

                if is_retryable and attempt < LLM_MAX_RETRIES:
                    delay = min(
                        LLM_RETRY_BASE * (2 ** (attempt - 1)),
                        LLM_RETRY_MAX,
                    )
                    jitter = random.uniform(0, delay * 0.5)
                    total_delay = delay + jitter
                    logger.info(
                        "LLM %s, retrying in %.1fs (attempt %d/%d): %s",
                        "429/TPM" if "429" in error_str else "5xx",
                        total_delay, attempt, LLM_MAX_RETRIES,
                        str(e)[:120],
                    )
                    await asyncio.sleep(total_delay)
                elif not is_retryable:
                    # Non-retryable error — fail immediately
                    raise

    # All retries exhausted
    if last_error:
        raise last_error
    return None
