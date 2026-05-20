"""
LLM Provider Abstraction Layer (A7.3 + A8.2).

Provides:
- ABC-based LLMProvider interface with OpenRouter, vLLM, and Ollama backends
- Global concurrency semaphore preventing GPU/API OOM crashes (A8.2)
- Exponential backoff with jitter for rate limit / overload recovery
- Sovereign mode toggle: PG_SOVEREIGN_MODE=1 forces local-only providers
- Factory function get_llm_provider() returns the correct provider

All polaris_graph pipeline LLM calls go through OpenRouterClient directly
(battle-tested, 1617 lines). This module provides:
1. Configuration resolution (which provider, which model)
2. Global concurrency control wrapping ALL LLM calls
3. Sovereign mode enforcement
4. Provider validation
"""

import asyncio
import logging
import os
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("polaris.providers.llm")

# ---------------------------------------------------------------------------
# Configuration from environment (LAW VI)
# ---------------------------------------------------------------------------

# Provider selection
LLM_PROVIDER = os.getenv("POLARIS_LLM_PROVIDER", "openrouter")

# Sovereign mode: when enabled, ALL external API calls are blocked
PG_SOVEREIGN_MODE = os.getenv("PG_SOVEREIGN_MODE", "0") == "1"

# OpenRouter (cloud)
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-v4-pro")

# vLLM (local GPU server)
VLLM_BASE_URL = os.getenv("VLLM_BASE_URL", "http://localhost:8200/v1")
VLLM_MODEL = os.getenv("VLLM_MODEL", "ebircak/gemma-4-31B-it-4bit-W4A16-AWQ")
VLLM_API_KEY = os.getenv("VLLM_API_KEY", "EMPTY")

# Ollama (local, lightweight)
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:70b")

# Local embedding model (sovereign mode)
LOCAL_EMBEDDING_MODEL = os.getenv(
    "PG_LOCAL_EMBEDDING_MODEL", "BAAI/bge-large-en-v1.5"
)

# ---------------------------------------------------------------------------
# A8.2: Global Concurrency Semaphore
# ---------------------------------------------------------------------------

# Max concurrent LLM requests across ALL pipeline nodes
# Cloud: 5 (API rate limits), GPU: 3 (VRAM constraints)
_MAX_CONCURRENT_LLM = int(os.getenv("PG_MAX_CONCURRENT_LLM", "5"))

# Retry configuration
_LLM_RETRY_MAX = int(os.getenv("PG_LLM_RETRY_MAX", "3"))
_LLM_RETRY_BASE_DELAY = float(os.getenv("PG_LLM_RETRY_BASE_DELAY", "1.0"))

# GPU memory threshold for auto-throttle (sovereign mode)
_GPU_MEMORY_THRESHOLD = float(os.getenv("PG_GPU_MEMORY_THRESHOLD", "0.90"))

# Singleton semaphore — initialized lazily
_LLM_SEMAPHORE: Optional[asyncio.Semaphore] = None
_SEMAPHORE_LOCK = asyncio.Lock() if hasattr(asyncio, "Lock") else None


def get_semaphore() -> asyncio.Semaphore:
    """Get or create the global LLM concurrency semaphore.

    Thread-safe lazy initialization. The semaphore limits the number of
    concurrent LLM API calls across all pipeline nodes to prevent:
    - 429 rate limit errors on cloud APIs
    - GPU OOM crashes on local vLLM deployments
    """
    global _LLM_SEMAPHORE
    if _LLM_SEMAPHORE is None:
        _LLM_SEMAPHORE = asyncio.Semaphore(_MAX_CONCURRENT_LLM)
        logger.info(
            "[llm_provider] Concurrency semaphore initialized: max=%d",
            _MAX_CONCURRENT_LLM,
        )
    return _LLM_SEMAPHORE


def reset_semaphore() -> None:
    """Reset the global semaphore (for testing or config changes)."""
    global _LLM_SEMAPHORE
    _LLM_SEMAPHORE = None


# ---------------------------------------------------------------------------
# A8.2: Exponential Backoff with Jitter
# ---------------------------------------------------------------------------


class RateLimitError(Exception):
    """Raised when the API returns a rate limit response (429)."""


class ServerOverloadError(Exception):
    """Raised when the API returns a server overload response (503)."""


async def retry_with_backoff(fn, max_retries: int = _LLM_RETRY_MAX,
                             base_delay: float = _LLM_RETRY_BASE_DELAY):
    """Retry an async callable with exponential backoff + random jitter.

    Retries on RateLimitError, ServerOverloadError, and TimeoutError.
    Other exceptions propagate immediately.

    Args:
        fn: Async callable (no arguments) to retry.
        max_retries: Maximum number of retry attempts.
        base_delay: Base delay in seconds (doubles each attempt).

    Returns:
        The result of fn() on success.

    Raises:
        The last exception if all retries are exhausted.
    """
    last_exc = None
    for attempt in range(max_retries + 1):
        try:
            return await fn()
        except (RateLimitError, ServerOverloadError, TimeoutError) as exc:
            last_exc = exc
            if attempt == max_retries:
                raise
            delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
            logger.warning(
                "[llm_provider] Retry %d/%d after %.1fs: %s",
                attempt + 1, max_retries, delay, str(exc)[:100],
            )
            await asyncio.sleep(delay)
    raise last_exc  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Provider Configuration (preserves backward compatibility)
# ---------------------------------------------------------------------------

@dataclass
class ProviderConfig:
    """Resolved LLM provider configuration."""

    base_url: str
    api_key: str
    model: str
    provider_name: str
    stream: bool = True
    supports_reasoning: bool = False
    max_tokens_default: int = 16384
    sovereign_mode: bool = False


def get_llm_config() -> dict:
    """Get LLM configuration based on deployment mode.

    Returns dict with: base_url, api_key, model, provider_name, stream,
    supports_reasoning, max_tokens_default, sovereign_mode.

    All providers use OpenAI-compatible API format.

    When PG_SOVEREIGN_MODE=1, forces vLLM/Ollama regardless of
    POLARIS_LLM_PROVIDER setting.
    """
    # Sovereign mode override: force local provider
    if PG_SOVEREIGN_MODE:
        provider = os.getenv("POLARIS_LLM_PROVIDER", "vllm").lower()
        if provider == "openrouter":
            logger.warning(
                "[llm_provider] Sovereign mode enabled but provider=openrouter. "
                "Overriding to vllm for air-gap compliance."
            )
            provider = "vllm"
    else:
        provider = LLM_PROVIDER.lower()

    if provider == "vllm":
        config = {
            "base_url": VLLM_BASE_URL,
            "api_key": VLLM_API_KEY,
            "model": VLLM_MODEL,
            "provider_name": "vllm",
            "stream": True,
            "supports_reasoning": False,
            "max_tokens_default": 16384,
            "sovereign_mode": PG_SOVEREIGN_MODE,
        }
        logger.info(
            "[llm_provider] Provider: vLLM at %s model=%s sovereign=%s",
            VLLM_BASE_URL, VLLM_MODEL, PG_SOVEREIGN_MODE,
        )

    elif provider == "ollama":
        config = {
            "base_url": OLLAMA_BASE_URL,
            "api_key": "ollama",
            "model": OLLAMA_MODEL,
            "provider_name": "ollama",
            "stream": True,
            "supports_reasoning": False,
            "max_tokens_default": 8192,
            "sovereign_mode": PG_SOVEREIGN_MODE,
        }
        logger.info(
            "[llm_provider] Provider: Ollama at %s model=%s sovereign=%s",
            OLLAMA_BASE_URL, OLLAMA_MODEL, PG_SOVEREIGN_MODE,
        )

    elif provider == "openrouter":
        if not OPENROUTER_API_KEY:
            raise EnvironmentError(
                "OPENROUTER_API_KEY is required when POLARIS_LLM_PROVIDER=openrouter. "
                "Set it in .env or switch to POLARIS_LLM_PROVIDER=vllm for sovereign mode."
            )
        config = {
            "base_url": OPENROUTER_BASE_URL,
            "api_key": OPENROUTER_API_KEY,
            "model": OPENROUTER_MODEL,
            "provider_name": "openrouter",
            "stream": True,
            "supports_reasoning": True,
            "max_tokens_default": 16384,
            "sovereign_mode": False,
        }
        logger.info(
            "[llm_provider] Provider: OpenRouter model=%s", OPENROUTER_MODEL,
        )

    else:
        raise ValueError(
            f"Unknown LLM provider: '{provider}'. "
            f"Must be one of: openrouter, vllm, ollama. "
            f"Set POLARIS_LLM_PROVIDER in .env"
        )

    return config


def get_provider_config() -> ProviderConfig:
    """Get provider configuration as a typed dataclass."""
    raw = get_llm_config()
    return ProviderConfig(**raw)


def validate_llm_provider() -> dict:
    """Validate LLM provider configuration. Returns status dict."""
    try:
        config = get_llm_config()
        return {
            "provider": config["provider_name"],
            "base_url": config["base_url"],
            "model": config["model"],
            "sovereign_mode": config.get("sovereign_mode", False),
            "max_concurrent_llm": _MAX_CONCURRENT_LLM,
            "status": "configured",
            "error": None,
        }
    except (EnvironmentError, ValueError) as e:
        return {
            "provider": LLM_PROVIDER,
            "base_url": None,
            "model": None,
            "sovereign_mode": PG_SOVEREIGN_MODE,
            "max_concurrent_llm": _MAX_CONCURRENT_LLM,
            "status": "error",
            "error": str(e),
        }


# ---------------------------------------------------------------------------
# Sovereign Mode Utilities
# ---------------------------------------------------------------------------


def is_sovereign_mode() -> bool:
    """Check if sovereign mode is active."""
    return PG_SOVEREIGN_MODE


def get_sovereign_status() -> dict:
    """Get sovereign mode status for dashboard display."""
    return {
        "sovereign_mode": PG_SOVEREIGN_MODE,
        "provider": LLM_PROVIDER,
        "local_llm_endpoint": VLLM_BASE_URL if PG_SOVEREIGN_MODE else None,
        "local_llm_model": VLLM_MODEL if PG_SOVEREIGN_MODE else None,
        "local_embedding_model": LOCAL_EMBEDDING_MODEL if PG_SOVEREIGN_MODE else None,
        "web_search_disabled": PG_SOVEREIGN_MODE,
    }


async def check_gpu_memory() -> dict:
    """Check GPU memory usage via nvidia-smi (sovereign mode only).

    Returns dict with gpu_memory_used_pct, gpu_memory_free_mb.
    Returns empty dict if nvidia-smi is not available.
    """
    if not PG_SOVEREIGN_MODE:
        return {}

    try:
        proc = await asyncio.create_subprocess_exec(
            "nvidia-smi",
            "--query-gpu=memory.used,memory.total,memory.free",
            "--format=csv,noheader,nounits",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5.0)
        if proc.returncode != 0:
            return {}

        line = stdout.decode().strip().split("\n")[0]
        parts = [int(x.strip()) for x in line.split(",")]
        used_mb, total_mb, free_mb = parts[0], parts[1], parts[2]
        used_pct = used_mb / total_mb if total_mb > 0 else 0.0

        result = {
            "gpu_memory_used_pct": round(used_pct, 3),
            "gpu_memory_used_mb": used_mb,
            "gpu_memory_total_mb": total_mb,
            "gpu_memory_free_mb": free_mb,
        }

        # Auto-throttle: if GPU memory usage exceeds threshold, reduce concurrency
        if used_pct > _GPU_MEMORY_THRESHOLD:
            logger.warning(
                "[llm_provider] GPU memory %.1f%% > threshold %.1f%%. "
                "Consider reducing PG_MAX_CONCURRENT_LLM.",
                used_pct * 100, _GPU_MEMORY_THRESHOLD * 100,
            )
            result["throttle_recommended"] = True

        return result

    except (FileNotFoundError, asyncio.TimeoutError):
        return {}
    except Exception as exc:
        logger.debug("[llm_provider] GPU memory check failed: %s", exc)
        return {}
