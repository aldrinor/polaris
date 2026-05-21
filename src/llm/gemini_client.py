#!/usr/bin/env python3
"""
POLARIS Gemini Client
=====================
Wrapper for Google Gemini API with structured output support.

Uses Gemini 3 Flash (default) for all generation tasks.
Configurable via config/settings/models.yaml.

Usage:
    from src.llm.gemini_client import GeminiClient, get_gemini_client

    client = get_gemini_client()
    response = await client.generate("What is the capital of France?")
"""

import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Type, TypeVar

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    import google.generativeai as genai
except ImportError:
    # I-pip-001: google-generativeai is EOL and forces protobuf<5, which
    # collides with the protobuf 6.x stack (pip resolution-too-deep). It was
    # dropped from requirements.txt. Importing this module stays cheap;
    # constructing GeminiClient fails loud below. Gemini is covered by
    # langchain-google-genai; port this client to google-genai if needed.
    genai = None  # type: ignore[assignment]
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
# GEMINI CLIENT
# =============================================================================

class GeminiClient:
    """
    Async-compatible Gemini API client.

    Features:
    - Structured JSON output
    - Retry with exponential backoff
    - Rate limiting
    - Token tracking
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 65536,
    ):
        """
        Initialize Gemini client.

        Args:
            api_key: Gemini API key (or from config/env)
            model: Model name (default: gemini-3-flash from config)
            temperature: Generation temperature
            max_tokens: Maximum output tokens
        """
        if genai is None:
            raise ImportError(
                "google-generativeai is not installed (dropped in I-pip-001 — "
                "EOL + forces protobuf<5). Gemini is covered by "
                "langchain-google-genai; port this client to google-genai to "
                "restore direct google.generativeai usage."
            )
        # Load from config
        config = get_config()
        self.api_key = api_key or config.env.gemini_api_key
        self.model_name = model or config.models.llm.model
        self.temperature = temperature
        self.max_tokens = max_tokens

        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not configured")

        # Configure API
        genai.configure(api_key=self.api_key)

        # Initialize model
        self.model = genai.GenerativeModel(
            model_name=self.model_name,
            generation_config=genai.GenerationConfig(
                temperature=self.temperature,
                max_output_tokens=self.max_tokens,
            ),
        )

        # Rate limiter
        self._rate_limiter = get_rate_limiter()

        # Token tracking
        self.total_input_tokens = 0
        self.total_output_tokens = 0

        logger.info(f"Gemini client initialized: {self.model_name}")

    async def _wait_for_rate_limit(self) -> None:
        """Wait for rate limit."""
        await self._rate_limiter.acquire_async(
            "generativelanguage.googleapis.com",
            timeout=60.0
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((Exception,)),
    )
    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> str:
        """
        Generate text from a prompt.

        Args:
            prompt: User prompt
            system_prompt: Optional system instruction

        Returns:
            Generated text
        """
        await self._wait_for_rate_limit()

        # Build messages
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n{prompt}"
        else:
            full_prompt = prompt

        # Run in executor for async compatibility
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self.model.generate_content(full_prompt)
        )

        # Track tokens (approximate based on words)
        input_tokens = int(len(full_prompt.split()) * 1.3)
        output_tokens = int(len(response.text.split()) * 1.3)

        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens

        # Track costs with cost tracker
        try:
            cost_tracker = get_cost_tracker()
            cost_tracker.add_cost(
                model=self.model_name,
                tokens_in=input_tokens,
                tokens_out=output_tokens
            )
            # Check budget after each call
            cost_tracker.check_budget()
        except BudgetExceededError:
            logger.error("Budget exceeded - stopping generation")
            raise

        return response.text

    async def generate_json(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate structured JSON output.

        Args:
            prompt: User prompt (should request JSON output)
            system_prompt: Optional system instruction

        Returns:
            Parsed JSON dict
        """
        # Add JSON instruction
        json_instruction = "\n\nRespond with valid JSON only. No markdown, no explanation."
        full_prompt = prompt + json_instruction

        response = await self.generate(full_prompt, system_prompt)

        # Clean response
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
            response_model: Pydantic model class for response
            system_prompt: Optional system instruction

        Returns:
            Validated Pydantic model instance
        """
        # Get model schema
        schema = response_model.model_json_schema()

        # Build schema prompt
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

        # Validate with Pydantic
        return response_model(**result)

    def get_stats(self) -> Dict[str, Any]:
        """Get usage statistics."""
        return {
            "model": self.model_name,
            "total_input_tokens": int(self.total_input_tokens),
            "total_output_tokens": int(self.total_output_tokens),
            "estimated_cost_usd": self._estimate_cost(),
        }

    def _estimate_cost(self) -> float:
        """Estimate cost in USD (approximate)."""
        # Gemini 2.5 Flash pricing (approximate)
        input_cost = self.total_input_tokens * 0.000001  # $1 per 1M tokens
        output_cost = self.total_output_tokens * 0.000004  # $4 per 1M tokens
        return input_cost + output_cost


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

_gemini_client: Optional[GeminiClient] = None


def get_gemini_client() -> GeminiClient:
    """Get the singleton Gemini client."""
    global _gemini_client
    if _gemini_client is None:
        _gemini_client = GeminiClient()
    return _gemini_client


# =============================================================================
# SELF-TEST
# =============================================================================

if __name__ == "__main__":
    import asyncio

    async def run_tests():
        print("=" * 60)
        print("GEMINI CLIENT SELF-TEST")
        print("=" * 60)

        try:
            # Test 1: Initialize client
            print("\n[TEST 1] Initialize client...")
            client = GeminiClient()
            print(f"  [PASS] Client initialized: {client.model_name}")

            # Test 2: Simple generation
            print("\n[TEST 2] Simple generation...")
            response = await client.generate("What is 2+2? Answer with just the number.")
            assert "4" in response
            print(f"  [PASS] Response: {response.strip()[:50]}")

            # Test 3: JSON generation
            print("\n[TEST 3] JSON generation...")
            json_response = await client.generate_json(
                "Return a JSON object with keys 'name' and 'value'. Name should be 'test' and value should be 42."
            )
            assert json_response.get("name") == "test"
            assert json_response.get("value") == 42
            print(f"  [PASS] JSON: {json_response}")

            # Test 4: Stats
            print("\n[TEST 4] Usage stats...")
            stats = client.get_stats()
            assert stats["total_input_tokens"] > 0
            print(f"  [PASS] Stats: {stats}")

            print("\n" + "=" * 60)
            print("ALL TESTS PASSED")
            print("=" * 60)

        except ValueError as e:
            # LOW-098: Use logger instead of print (in self-test section)
            logger.warning(f"API key not configured: {e}")
            logger.warning("Set GEMINI_API_KEY in .env to run tests")

    asyncio.run(run_tests())
