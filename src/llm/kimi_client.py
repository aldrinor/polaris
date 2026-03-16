#!/usr/bin/env python3
"""
POLARIS KIMI K2.5 Client
========================
OpenAI-compatible API client for KIMI K2.5 via Fireworks AI.
Supports both Thinking Mode and Instant Mode.

KIMI K2.5 1T Features:
- 256K context window (native)
- Extended reasoning (thinking mode)
- Fast inference via Fireworks
- Cost-effective: $0.60/1M input, $3.00/1M output

Usage:
    from src.llm.kimi_client import KimiClient, get_kimi_client

    # Thinking mode (default) - slower but more accurate
    client = get_kimi_client(thinking=True)
    response = await client.generate("Analyze this complex problem...")

    # Instant mode - faster for simple tasks
    fast_client = get_kimi_client(thinking=False)
    response = await fast_client.generate("What is 2+2?")
"""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Type, TypeVar

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from openai import AsyncOpenAI, OpenAI
from pydantic import BaseModel
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from src.config import get_config
from src.utils.rate_limiter import get_rate_limiter
from src.utils.cost_tracker import get_cost_tracker, BudgetExceededError

# Configure logging
logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


# =============================================================================
# KIMI CLIENT
# =============================================================================

class KimiClient:
    """
    KIMI K2.5 client with thinking mode support via Fireworks AI.

    Modes:
    - thinking=True: Extended reasoning (slower, more accurate)
      Uses temperature 1.0 as recommended by KIMI
    - thinking=False: Instant mode (faster, good for simple tasks)
      Uses temperature 0.6 for more deterministic outputs

    Features:
    - OpenAI-compatible API (works with Fireworks inference endpoint)
    - Async and sync generation
    - Structured JSON output
    - Pydantic model validation
    - Rate limiting and retry logic
    - Token tracking and cost estimation
    """

    FIREWORKS_BASE_URL = "https://api.fireworks.ai/inference/v1"
    MODEL_ID = "accounts/fireworks/models/kimi-k2p5"

    # Pricing (per 1M tokens)
    INPUT_COST_PER_MILLION = 0.60
    OUTPUT_COST_PER_MILLION = 3.00

    def __init__(
        self,
        api_key: Optional[str] = None,
        thinking_mode: bool = True,
        temperature: Optional[float] = None,
        max_tokens: int = 4096,  # Fireworks requires stream=true for >4096
    ):
        """
        Initialize KIMI client.

        Args:
            api_key: Fireworks API key (or from env FIREWORKS_API_KEY)
            thinking_mode: Enable extended reasoning (default True)
            temperature: Override temperature (default: 1.0 thinking, 0.6 instant)
            max_tokens: Maximum output tokens (default 8192)
        """
        # Try to get API key from config or env
        self.api_key = api_key or os.getenv("FIREWORKS_API_KEY")

        # Also check config if env var not set
        if not self.api_key:
            try:
                config = get_config()
                self.api_key = getattr(config.env, 'fireworks_api_key', None)
            except (AttributeError, ImportError) as e:
                logger.debug(f"Config fallback failed (expected if config not available): {e}")

        if not self.api_key:
            raise ValueError(
                "FIREWORKS_API_KEY not configured. "
                "Set in .env file or pass api_key parameter."
            )

        self.thinking_mode = thinking_mode
        self.max_tokens = max_tokens

        # Temperature: 1.0 for thinking mode, 0.6 for instant (KIMI recommended)
        if temperature is not None:
            self.temperature = temperature
        else:
            self.temperature = 1.0 if thinking_mode else 0.6

        # Initialize OpenAI-compatible clients
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.FIREWORKS_BASE_URL,
        )

        self.async_client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.FIREWORKS_BASE_URL,
        )

        # Rate limiter
        self._rate_limiter = get_rate_limiter()

        # Token tracking
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_reasoning_tokens = 0

        mode_str = "thinking" if thinking_mode else "instant"
        logger.info(
            f"KIMI client initialized: {self.MODEL_ID} "
            f"(mode={mode_str}, temp={self.temperature})"
        )

    async def _wait_for_rate_limit(self) -> None:
        """Wait for rate limit clearance."""
        await self._rate_limiter.acquire_async(
            "api.fireworks.ai",
            timeout=60.0
        )

    def _build_messages(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> List[Dict[str, str]]:
        """Build message list for API call."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        return messages

    def _track_tokens(
        self,
        input_tokens: int,
        output_tokens: int,
        reasoning_content: Optional[str] = None,
    ) -> None:
        """Track token usage and costs."""
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens

        # Estimate reasoning tokens from content
        if reasoning_content:
            reasoning_tokens = int(len(reasoning_content.split()) * 1.3)
            self.total_reasoning_tokens += reasoning_tokens

        # Track costs
        try:
            cost_tracker = get_cost_tracker()
            cost_tracker.add_cost(
                model=self.MODEL_ID,
                tokens_in=input_tokens,
                tokens_out=output_tokens,
            )
            cost_tracker.check_budget()
        except BudgetExceededError:
            logger.error("Budget exceeded - stopping generation")
            raise

    def _parse_response(self, response) -> Dict[str, Any]:
        """Parse API response into standard format."""
        choice = response.choices[0]
        usage = response.usage

        # Extract reasoning content if available (thinking mode)
        reasoning = None
        if hasattr(choice.message, 'reasoning_content'):
            reasoning = choice.message.reasoning_content

        return {
            "content": choice.message.content,
            "reasoning": reasoning,
            "usage": {
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "total_tokens": usage.total_tokens,
            }
        }

    # =========================================================================
    # SYNC METHODS
    # =========================================================================

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((Exception,)),
    )
    def generate_sync(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        Synchronous text generation.

        Args:
            prompt: User prompt
            system_prompt: Optional system instruction
            temperature: Override temperature
            max_tokens: Override max tokens

        Returns:
            Generated text (final response, not reasoning)
        """
        messages = self._build_messages(prompt, system_prompt)

        response = self.client.chat.completions.create(
            model=self.MODEL_ID,
            messages=messages,
            temperature=temperature or self.temperature,
            max_tokens=max_tokens or self.max_tokens,
            extra_body={
                "thinking": {
                    "type": "enabled" if self.thinking_mode else "disabled"
                }
            },
        )

        result = self._parse_response(response)

        # Track tokens
        self._track_tokens(
            result["usage"]["prompt_tokens"],
            result["usage"]["completion_tokens"],
            result.get("reasoning"),
        )

        return result["content"]

    def generate_with_reasoning_sync(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Synchronous generation returning both content and reasoning.

        FIX-220A: Added max_tokens parameter for per-call token budget control.
        FIX-220B: Uses streaming when max_tokens > 4096 (Fireworks requirement).

        Args:
            prompt: User prompt
            system_prompt: Optional system instruction
            max_tokens: Per-call token limit (None = use client default)

        Returns:
            {
                "content": str,  # Final response
                "reasoning": str | None,  # Thinking process (if enabled)
                "usage": {...}
            }
        """
        messages = self._build_messages(prompt, system_prompt)
        effective_max_tokens = max_tokens if max_tokens is not None else self.max_tokens

        # FIX-220B: Fireworks requires stream=true for >4096 output tokens
        if effective_max_tokens > 4096:
            return self._stream_with_reasoning(messages, effective_max_tokens)

        # Standard non-streaming path (<=4096 tokens)
        response = self.client.chat.completions.create(
            model=self.MODEL_ID,
            messages=messages,
            temperature=self.temperature,
            max_tokens=effective_max_tokens,
            extra_body={
                "thinking": {
                    "type": "enabled" if self.thinking_mode else "disabled"
                }
            },
        )

        result = self._parse_response(response)

        self._track_tokens(
            result["usage"]["prompt_tokens"],
            result["usage"]["completion_tokens"],
            result.get("reasoning"),
        )

        return result

    def _stream_with_reasoning(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int,
    ) -> Dict[str, Any]:
        """
        FIX-220B: Stream response for >4096 tokens, extracting reasoning + content.

        Fireworks requires stream=true for output exceeding 4096 tokens.
        This method accumulates streamed chunks and separates reasoning_content
        from content, maintaining the same structural separation as non-streaming.

        Args:
            messages: Formatted message list
            max_tokens: Token budget for this call

        Returns:
            Same dict format as non-streaming: {content, reasoning, usage}
        """
        stream = self.client.chat.completions.create(
            model=self.MODEL_ID,
            messages=messages,
            temperature=self.temperature,
            max_tokens=max_tokens,
            stream=True,
            stream_options={"include_usage": True},
            extra_body={
                "thinking": {
                    "type": "enabled" if self.thinking_mode else "disabled"
                }
            },
        )

        content_parts = []
        reasoning_parts = []
        usage_info = None

        for chunk in stream:
            if not chunk.choices:
                # Usage info arrives in the final chunk with empty choices
                if hasattr(chunk, 'usage') and chunk.usage:
                    usage_info = chunk.usage
                continue

            delta = chunk.choices[0].delta

            # Accumulate reasoning (Fireworks/KIMI extension field)
            if hasattr(delta, 'reasoning_content') and delta.reasoning_content:
                reasoning_parts.append(delta.reasoning_content)

            # Accumulate content
            if delta.content:
                content_parts.append(delta.content)

        content = "".join(content_parts)
        reasoning = "".join(reasoning_parts) if reasoning_parts else None

        # Build usage dict from stream metadata
        if usage_info:
            usage = {
                "prompt_tokens": usage_info.prompt_tokens,
                "completion_tokens": usage_info.completion_tokens,
                "total_tokens": usage_info.total_tokens,
            }
        else:
            # Estimate tokens if streaming didn't provide usage metadata
            est_tokens = int(len(content.split()) * 1.3)
            usage = {
                "prompt_tokens": 0,
                "completion_tokens": est_tokens,
                "total_tokens": est_tokens,
            }
            logger.warning(
                f"[FIX-220B] Stream did not provide usage metadata, estimated {est_tokens} tokens"
            )

        self._track_tokens(
            usage["prompt_tokens"],
            usage["completion_tokens"],
            reasoning,
        )

        return {
            "content": content,
            "reasoning": reasoning,
            "usage": usage,
        }

    # =========================================================================
    # ASYNC METHODS
    # =========================================================================

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((Exception,)),
    )
    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        Async text generation.

        Args:
            prompt: User prompt
            system_prompt: Optional system instruction
            temperature: Override temperature
            max_tokens: Override max tokens

        Returns:
            Generated text (final response, not reasoning)
        """
        await self._wait_for_rate_limit()

        messages = self._build_messages(prompt, system_prompt)

        response = await self.async_client.chat.completions.create(
            model=self.MODEL_ID,
            messages=messages,
            temperature=temperature or self.temperature,
            max_tokens=max_tokens or self.max_tokens,
            extra_body={
                "thinking": {
                    "type": "enabled" if self.thinking_mode else "disabled"
                }
            },
        )

        result = self._parse_response(response)

        self._track_tokens(
            result["usage"]["prompt_tokens"],
            result["usage"]["completion_tokens"],
            result.get("reasoning"),
        )

        return result["content"]

    async def generate_with_reasoning(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Async generation returning both content and reasoning.

        Returns:
            {
                "content": str,
                "reasoning": str | None,
                "usage": {...}
            }
        """
        await self._wait_for_rate_limit()

        messages = self._build_messages(prompt, system_prompt)

        response = await self.async_client.chat.completions.create(
            model=self.MODEL_ID,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            extra_body={
                "thinking": {
                    "type": "enabled" if self.thinking_mode else "disabled"
                }
            },
        )

        result = self._parse_response(response)

        self._track_tokens(
            result["usage"]["prompt_tokens"],
            result["usage"]["completion_tokens"],
            result.get("reasoning"),
        )

        return result

    # =========================================================================
    # STRUCTURED OUTPUT
    # =========================================================================

    async def generate_json(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate structured JSON output.

        Args:
            prompt: User prompt (should request JSON)
            system_prompt: Optional system instruction

        Returns:
            Parsed JSON dict
        """
        json_instruction = "\n\nRespond with valid JSON only. No markdown, no explanation."
        full_prompt = prompt + json_instruction

        response = await self.generate(full_prompt, system_prompt)

        # Clean markdown formatting
        cleaned = response.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        if cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            logger.debug(f"Raw response: {response[:500]}")
            raise ValueError(f"Invalid JSON response: {e}")

    async def generate_structured(
        self,
        prompt: str,
        response_model: Type[T],
        system_prompt: Optional[str] = None,
    ) -> T:
        """
        Generate output conforming to a Pydantic model.

        Args:
            prompt: User prompt
            response_model: Pydantic model class
            system_prompt: Optional system instruction

        Returns:
            Validated Pydantic model instance
        """
        schema = response_model.model_json_schema()

        schema_prompt = f"""
You must respond with JSON that matches this exact schema:

{json.dumps(schema, indent=2)}

Important:
- Include ALL required fields
- Use correct data types
- Do not add extra fields
"""

        full_system = (system_prompt or "") + schema_prompt
        result = await self.generate_json(prompt, full_system)

        return response_model(**result)

    def generate_structured_sync(
        self,
        prompt: str,
        response_model: Type[T],
        system_prompt: Optional[str] = None,
    ) -> T:
        """Synchronous structured output generation."""
        schema = response_model.model_json_schema()

        schema_prompt = f"""
You must respond with JSON that matches this exact schema:

{json.dumps(schema, indent=2)}

Respond with JSON only. No markdown, no explanation.
"""

        full_prompt = prompt + schema_prompt
        messages = self._build_messages(full_prompt, system_prompt)

        response = self.client.chat.completions.create(
            model=self.MODEL_ID,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            extra_body={
                "thinking": {
                    "type": "enabled" if self.thinking_mode else "disabled"
                }
            },
        )

        result = self._parse_response(response)

        self._track_tokens(
            result["usage"]["prompt_tokens"],
            result["usage"]["completion_tokens"],
            result.get("reasoning"),
        )

        # Parse JSON
        content = result["content"]
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]

        data = json.loads(content.strip())
        return response_model(**data)

    # =========================================================================
    # UTILITIES
    # =========================================================================

    def get_stats(self) -> Dict[str, Any]:
        """Get usage statistics."""
        input_cost = self.total_input_tokens * self.INPUT_COST_PER_MILLION / 1_000_000
        output_cost = self.total_output_tokens * self.OUTPUT_COST_PER_MILLION / 1_000_000

        return {
            "model": self.MODEL_ID,
            "thinking_mode": self.thinking_mode,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_reasoning_tokens": self.total_reasoning_tokens,
            "estimated_cost_usd": input_cost + output_cost,
        }

    def reset_stats(self) -> None:
        """Reset token counters."""
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_reasoning_tokens = 0


# =============================================================================
# SINGLETON INSTANCES
# =============================================================================

_kimi_thinking_client: Optional[KimiClient] = None
_kimi_instant_client: Optional[KimiClient] = None


def get_kimi_client(thinking: bool = True) -> KimiClient:
    """
    Get singleton KIMI client.

    Args:
        thinking: If True, use thinking mode (slower, more accurate)
                  If False, use instant mode (faster, simpler tasks)

    Returns:
        KimiClient instance
    """
    global _kimi_thinking_client, _kimi_instant_client

    if thinking:
        if _kimi_thinking_client is None:
            _kimi_thinking_client = KimiClient(thinking_mode=True)
        return _kimi_thinking_client
    else:
        if _kimi_instant_client is None:
            _kimi_instant_client = KimiClient(thinking_mode=False)
        return _kimi_instant_client


def reset_kimi_clients() -> None:
    """Reset singleton clients (for testing)."""
    global _kimi_thinking_client, _kimi_instant_client
    _kimi_thinking_client = None
    _kimi_instant_client = None


# =============================================================================
# SELF-TEST
# =============================================================================

if __name__ == "__main__":

    async def run_tests():
        print("=" * 60)
        print("KIMI K2.5 CLIENT SELF-TEST")
        print("=" * 60)

        try:
            # Test 1: Initialize client
            print("\n[TEST 1] Initialize thinking mode client...")
            client = KimiClient(thinking_mode=True)
            print(f"  [PASS] Client initialized: {client.MODEL_ID}")

            # Test 2: Initialize instant mode
            print("\n[TEST 2] Initialize instant mode client...")
            fast_client = KimiClient(thinking_mode=False)
            assert fast_client.temperature == 0.6
            print(f"  [PASS] Instant client initialized")

            # Test 3: Simple generation (instant mode - faster)
            print("\n[TEST 3] Simple generation (instant mode)...")
            response = await fast_client.generate(
                "What is 2+2? Answer with just the number."
            )
            assert "4" in response
            print(f"  [PASS] Response: {response.strip()[:50]}")

            # Test 4: Generation with reasoning (thinking mode)
            print("\n[TEST 4] Generation with reasoning...")
            result = await client.generate_with_reasoning(
                "Explain briefly why water is essential for life."
            )
            assert result["content"]
            has_reasoning = result.get("reasoning") is not None
            print(f"  [PASS] Content: {result['content'][:50]}...")
            print(f"  [INFO] Has reasoning: {has_reasoning}")

            # Test 5: JSON generation
            print("\n[TEST 5] JSON generation...")
            json_response = await fast_client.generate_json(
                "Return a JSON object with keys 'name' (value: 'test') and 'value' (value: 42)."
            )
            assert json_response.get("name") == "test"
            assert json_response.get("value") == 42
            print(f"  [PASS] JSON: {json_response}")

            # Test 6: Stats
            print("\n[TEST 6] Usage stats...")
            stats = client.get_stats()
            print(f"  [PASS] Stats: {stats}")

            # Test 7: Singleton
            print("\n[TEST 7] Singleton pattern...")
            c1 = get_kimi_client(thinking=True)
            c2 = get_kimi_client(thinking=True)
            assert c1 is c2
            print("  [PASS] Singleton working")

            print("\n" + "=" * 60)
            print("ALL TESTS PASSED")
            print("=" * 60)

        except ValueError as e:
            print(f"\n[ERROR] {e}")
            print("Set FIREWORKS_API_KEY in .env to run tests")

    asyncio.run(run_tests())
