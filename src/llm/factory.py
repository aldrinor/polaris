"""
POLARIS LLM Factory
===================
Factory function to get the configured LLM client.

Usage:
    from src.llm.factory import get_llm

    llm = get_llm()
    response = llm.generate("What is 2+2?")
"""

import os
import logging
from typing import Optional, Any

logger = logging.getLogger(__name__)


class LLMWrapper:
    """
    Wrapper that provides a consistent interface for LLM generation.

    Supports both KIMI K2.5 and Gemini backends with automatic fallback.
    """

    def __init__(self, backend: str = "auto"):
        """
        Initialize LLM wrapper.

        Args:
            backend: Which LLM backend to use ("kimi", "gemini", or "auto")
        """
        self.backend = backend
        self._kimi_client = None
        self._gemini_client = None

    def _get_kimi(self):
        """Lazy initialization of KIMI client."""
        if self._kimi_client is None:
            try:
                from src.llm.kimi_client import get_kimi_client
                self._kimi_client = get_kimi_client()
            except Exception as e:
                logger.warning(f"Failed to initialize KIMI client: {e}")
                return None
        return self._kimi_client

    def _get_gemini(self):
        """Lazy initialization of Gemini client."""
        if self._gemini_client is None:
            try:
                from src.llm.gemini_client import get_gemini_client
                self._gemini_client = get_gemini_client()
            except Exception as e:
                logger.warning(f"Failed to initialize Gemini client: {e}")
                return None
        return self._gemini_client

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        thinking: bool = False,
    ) -> str:
        """
        Generate a response from the LLM.

        Args:
            prompt: The user prompt to send to the LLM
            system_prompt: Optional system prompt for context
            temperature: Temperature for generation (0.0-1.0)
            max_tokens: Maximum tokens to generate
            thinking: Enable thinking mode (KIMI only)

        Returns:
            Generated text response
        """
        import asyncio

        # Try KIMI first (primary)
        if self.backend in ("kimi", "auto"):
            kimi = self._get_kimi()
            if kimi:
                try:
                    # Use synchronous method
                    response = kimi.generate_sync(
                        prompt=prompt,
                        system_prompt=system_prompt or "You are a helpful AI assistant.",
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )
                    if response:
                        return response
                except Exception as e:
                    logger.warning(f"KIMI generation failed: {e}")

        # Fallback to Gemini (async, so we run it)
        if self.backend in ("gemini", "auto"):
            gemini = self._get_gemini()
            if gemini:
                try:
                    # Gemini is async, run in event loop
                    async def _async_generate():
                        return await gemini.generate(
                            prompt=f"{system_prompt or ''}\n\n{prompt}",
                            temperature=temperature,
                            max_tokens=max_tokens,
                        )

                    # Run async function
                    try:
                        loop = asyncio.get_running_loop()
                        # Already in async context - use nest_asyncio or thread
                        import concurrent.futures
                        with concurrent.futures.ThreadPoolExecutor() as pool:
                            future = pool.submit(asyncio.run, _async_generate())
                            response = future.result(timeout=120)
                    except RuntimeError:
                        # No running loop - can use asyncio.run directly
                        response = asyncio.run(_async_generate())

                    if response:
                        return response
                except Exception as e:
                    logger.warning(f"Gemini generation failed: {e}")

        raise RuntimeError("All LLM backends failed. Check API keys and configuration.")

    async def agenerate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        thinking: bool = False,
    ) -> str:
        """Async version of generate. Currently delegates to sync version."""
        return self.generate(prompt, system_prompt, temperature, max_tokens, thinking)

    def invoke(self, prompt: str, **kwargs) -> "LLMResponse":
        """
        LangChain-compatible invoke method.

        Args:
            prompt: The prompt to send to the LLM
            **kwargs: Additional arguments (ignored)

        Returns:
            LLMResponse object with .content attribute
        """
        response_text = self.generate(prompt)
        return LLMResponse(content=response_text)


class LLMResponse:
    """Simple response class mimicking LangChain response format."""

    def __init__(self, content: str):
        self.content = content

    def __str__(self) -> str:
        return self.content


# Global LLM instance (singleton pattern)
_llm_instance: Optional[LLMWrapper] = None


def get_llm(backend: str = "auto", task_tier: str = "normal", **kwargs) -> LLMWrapper:
    """
    Get the configured LLM instance.

    Args:
        backend: Which backend to use ("kimi", "gemini", or "auto")
        task_tier: Task importance tier ("normal", "important", "critical") - for routing
        **kwargs: Additional arguments (ignored for compatibility)

    Returns:
        LLMWrapper instance
    """
    global _llm_instance

    # Check environment for backend preference
    if backend == "auto":
        backend = os.environ.get("POLARIS_LLM_BACKEND", "auto")

    # task_tier can influence backend choice
    # "critical" tasks use KIMI thinking mode for better accuracy
    if task_tier == "critical":
        backend = "kimi"

    if _llm_instance is None or _llm_instance.backend != backend:
        _llm_instance = LLMWrapper(backend=backend)
        logger.info(f"Initialized LLM factory with backend: {backend}, tier: {task_tier}")

    return _llm_instance


def reset_llm():
    """Reset the global LLM instance."""
    global _llm_instance
    _llm_instance = None
