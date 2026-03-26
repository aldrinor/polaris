"""
OpenRouter LLM Client for polaris graph.

Single gateway to Qwen 3.5 Plus via OpenRouter. Two call modes:
- reason(): reasoning ON, returned separately in reasoning_details
- generate(): reasoning OFF, clean prose output only

No CoT scrubbing. No regex filters. No post-processing hacks.
The API handles separation at the protocol level.
"""

import asyncio
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Type, TypeVar

import httpx
from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError

from src.polaris_graph.tracing import _current_tracer

load_dotenv()

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# FIX-305: Persistent cost ledger
_COST_LEDGER_PATH = Path(os.getenv("PG_COST_LEDGER_PATH", "logs/pg_cost_ledger.jsonl"))

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = os.getenv(
    "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
)
OPENROUTER_MODEL = os.getenv("OPENROUTER_DEFAULT_MODEL", "qwen/qwen3.5-plus-02-15")
OPENROUTER_BUDGET_USD = float(os.getenv("OPENROUTER_BUDGET_USD", "50.0"))

# FIX-GLM5: Models that always route output to reasoning_content.
# These need reasoning_enabled=True for all calls, and generate() must
# use reasoning as content directly (no </think> tag extraction).
_ALWAYS_REASON_MODELS = frozenset({
    "z-ai/glm-5", "z-ai/glm-5-turbo", "z-ai/glm-4.7",
})

# Pricing per million tokens (configurable per LAW VI)
# Qwen 3.5 Plus: $0.26 input, $1.56 output
# Use API-reported cost when available (FIX-C1)
INPUT_COST_PER_M = float(os.getenv("OPENROUTER_INPUT_COST_PER_M", "0.26"))
OUTPUT_COST_PER_M = float(os.getenv("OPENROUTER_OUTPUT_COST_PER_M", "1.56"))

# Timeouts — FIX-SCHEMA-5: reduced from 180/300 to 90/180.
# Qwen 3.5 Plus typically responds in 10-60s. 3+ min means the API is hung.
# asyncio.wait_for adds +30s grace period on top of these.
DEFAULT_TIMEOUT_SECONDS = int(os.getenv("PG_LLM_TIMEOUT_SECONDS", "90"))
LONG_TIMEOUT_SECONDS = int(os.getenv("PG_LLM_LONG_TIMEOUT_SECONDS", "180"))

# Retry
MAX_RETRIES = 2
RETRY_BACKOFF_BASE = 2.0


@dataclass
class UsageTracker:
    """Track token usage and cost across the session."""

    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_reasoning_tokens: int = 0
    total_calls: int = 0
    total_errors: int = 0
    budget_usd: float = OPENROUTER_BUDGET_USD
    session_id: str = ""  # FIX-F2: Distinguish runs in persistent cost ledger
    _call_log: list = field(default_factory=list)

    # FIX-C2: Track API-reported cost for accurate billing
    total_api_reported_cost: float = 0.0

    @property
    def total_cost_usd(self) -> float:
        # Prefer API-reported cost if available (accurate per-provider pricing)
        if self.total_api_reported_cost > 0:
            return self.total_api_reported_cost
        input_cost = (self.total_input_tokens / 1_000_000) * INPUT_COST_PER_M
        output_cost = (self.total_output_tokens / 1_000_000) * OUTPUT_COST_PER_M
        return input_cost + output_cost

    @property
    def budget_remaining_usd(self) -> float:
        return self.budget_usd - self.total_cost_usd

    @property
    def budget_exhausted(self) -> bool:
        return self.total_cost_usd >= self.budget_usd

    def record(
        self,
        call_type: str,
        input_tokens: int,
        output_tokens: int,
        reasoning_tokens: int = 0,
        duration_ms: float = 0,
        api_cost: float = 0.0,
        prompt_component_tokens: dict | None = None,
    ):
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.total_reasoning_tokens += reasoning_tokens
        self.total_calls += 1
        # FIX-C2: Accumulate API-reported cost for accurate billing
        if api_cost > 0:
            self.total_api_reported_cost += api_cost
        call_cost = api_cost if api_cost > 0 else round(
            (input_tokens / 1_000_000) * INPUT_COST_PER_M
            + (output_tokens / 1_000_000) * OUTPUT_COST_PER_M,
            6,
        )
        entry = {
            "type": call_type,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "reasoning_tokens": reasoning_tokens,
            "duration_ms": duration_ms,
            "cost_usd": round(call_cost, 6),
            "cumulative_cost_usd": round(self.total_cost_usd, 4),
        }
        # TIER-3 Stage 6: Optional prompt component breakdown
        if prompt_component_tokens:
            entry["prompt_components"] = prompt_component_tokens
        self._call_log.append(entry)

        # FIX-305: Persist to JSONL cost ledger
        self._append_ledger({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": self.session_id,  # FIX-F2: Tag entries with run ID
            "call_type": call_type,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "reasoning_tokens": reasoning_tokens,
            "duration_ms": round(duration_ms, 1),
            "cost_usd": round(call_cost, 6),
            "cumulative_cost_usd": round(self.total_cost_usd, 4),
        })

    def _append_ledger(self, entry: dict):
        """Append a cost entry to the persistent JSONL ledger."""
        try:
            _COST_LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(_COST_LEDGER_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as exc:
            # FIX-O1: Elevated from debug to warning for visibility
            logger.warning("FIX-O1: Cost ledger write failed: %s", exc)

    def summary(self) -> dict:
        return {
            "total_calls": self.total_calls,
            "total_errors": self.total_errors,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_reasoning_tokens": self.total_reasoning_tokens,
            "total_cost_usd": round(self.total_cost_usd, 4),
            "budget_remaining_usd": round(self.budget_remaining_usd, 4),
        }


@dataclass
class LLMResponse:
    """Structured response from an LLM call."""

    content: str
    reasoning: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    model: str = ""
    duration_ms: float = 0
    raw_response: Optional[dict] = None


class BudgetExhaustedError(Exception):
    """Raised when the OpenRouter budget is exhausted."""


class BillingExhaustedException(Exception):
    """Raised when OpenRouter returns 402 Payment Required.

    Once triggered, all subsequent calls are short-circuited to prevent
    hundreds of wasted retries against a billing-blocked account.
    """


def _clean_json(raw: str) -> str:
    """Clean LLM JSON output — strip code fences, fix control chars in strings."""
    text = raw.strip()
    # Strip markdown code fences
    if text.startswith("```"):
        # Remove opening fence (with optional language tag)
        text = re.sub(r"^```(?:json)?\s*\n?", "", text)
        # Remove closing fence
        text = re.sub(r"\n?```\s*$", "", text)
    # Remove non-printable control characters (not \n, \r, \t)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    # FIX-SCHEMA-6: Repair spurious quote before array values (legacy Kimi issue, kept for safety).
    # Two patterns observed:
    #   Pattern 1: {"analyses":":[{"source_url"...  (no space, regex works)
    #   Pattern 2: {"analyses": ":[{","source_url"... (valid JSON, leave alone)
    # Strategy: apply regex, verify JSON still parses, revert if broken.
    # Pattern 2 is valid JSON (analyses=string, source_url=sibling key) and
    # FIX-SCHEMA-7 in Pydantic validators recovers from it.
    _before_schema6 = text
    text = re.sub(r'"\s*:\s*":\s*\[', '": [', text)
    if text != _before_schema6:
        try:
            json.loads(text)
        except (ValueError, json.JSONDecodeError):
            # Regex broke valid JSON (Pattern 2) — revert
            text = _before_schema6
    # Escape raw control chars INSIDE JSON strings (newlines, tabs, etc.)
    # Without this, json.loads() rejects "analysis":"\n\nThe user..."
    text = _escape_control_chars_in_strings(text)
    return text.strip()


def _extract_answer_from_reasoning(reasoning: str) -> Optional[str]:
    """COT-4: Extract the actual answer from reasoning that contains both CoT and answer.

    Some providers put BOTH chain-of-thought AND the final answer into the
    reasoning_content field, leaving content empty. The answer typically
    appears after a </think> tag. This function splits on that tag and
    returns the text after it (the actual answer).

    Returns:
        The answer text after </think>, or None if no tag found or
        only CoT present (no substantial text after tag).
    """
    if not reasoning:
        return None

    # Split on </think> tag (case-insensitive)
    parts = re.split(r"</think>", reasoning, maxsplit=1, flags=re.IGNORECASE)
    if len(parts) < 2:
        return None

    answer = parts[1].strip()
    # Only return if there's substantial content after the tag
    # (not just a few trailing chars or whitespace)
    if len(answer) < 20:
        return None

    return answer


def _extract_json_from_text(text: str) -> Optional[str]:
    """Extract JSON object from mixed CoT + JSON text.

    When providers put both chain-of-thought reasoning AND JSON output
    into the reasoning field, this function finds the JSON portion.
    Strategy: try each '{' position from the LAST occurrence backwards,
    since the JSON output typically comes after the CoT reasoning.
    Returns None if no valid JSON object found.
    """
    # Fast path — text starts with { (already JSON)
    stripped = text.strip()
    if stripped.startswith("{"):
        return stripped

    # Collect all { positions, try from last to first
    # (JSON output is typically at the end of CoT text)
    brace_positions = [i for i, c in enumerate(text) if c == "{"]
    if not brace_positions:
        return None

    # Try each { position — collect all valid JSON objects, return largest.
    # The actual structured output is typically the biggest JSON block.
    best = None
    best_len = 0

    for start in brace_positions:
        depth = 0
        in_string = False
        escape_next = False
        end = -1

        for i in range(start, len(text)):
            c = text[i]
            if escape_next:
                escape_next = False
                continue
            if c == "\\":
                escape_next = True
                continue
            if c == '"' and not escape_next:
                in_string = not in_string
                continue
            if in_string:
                continue
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break

        if end == -1:
            continue  # Unclosed brace, skip

        candidate = text[start:end]
        # Must be substantial (> 50 chars) to be a real JSON object
        if len(candidate) <= 50:
            continue

        try:
            json.loads(candidate)
            if len(candidate) > best_len:
                best = candidate
                best_len = len(candidate)
        except (json.JSONDecodeError, ValueError):
            continue

    if best:
        return best

    # No valid JSON found — return from last { to end (may be truncated)
    last_start = brace_positions[-1]
    candidate = text[last_start:]
    if len(candidate) > 50:
        return candidate
    return None


def _repair_truncated_json(text: str) -> Optional[str]:
    """Repair JSON truncated by max_tokens.

    When the LLM hits max_tokens, the JSON gets cut off mid-string or
    mid-object.  This function extracts all complete top-level objects
    from the first array value found (works for ``analyses``,
    ``verifications``, ``sections``, ``clusters``, etc.) and
    reconstructs valid JSON from them.

    Returns repaired JSON string or None if repair is impossible.
    """
    # Fast path — already valid
    try:
        json.loads(text)
        return text
    except (json.JSONDecodeError, ValueError):
        pass

    # Find the first array value in the JSON — works for any schema
    match = re.search(r'"(\w+)"\s*:\s*\[', text)
    if not match:
        return None

    array_key = match.group(1)
    array_start = match.end()

    # Walk through and extract complete {...} objects at depth-0 of the array
    objects: list[str] = []
    depth = 0
    in_string = False
    escape_next = False
    obj_start: Optional[int] = None

    for i in range(array_start, len(text)):
        ch = text[i]
        if escape_next:
            escape_next = False
            continue
        if ch == "\\" and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            if depth == 0:
                obj_start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and obj_start is not None:
                objects.append(text[obj_start : i + 1])
                obj_start = None
        elif ch == "]" and depth == 0:
            # End of analyses array — stop scanning
            break

    if not objects:
        return None

    repaired = '{"' + array_key + '": [' + ", ".join(objects) + "]}"
    try:
        json.loads(repaired)
        return repaired
    except (json.JSONDecodeError, ValueError):
        return None


def _escape_control_chars_in_strings(text: str) -> str:
    """Escape raw control characters inside JSON string values.

    JSON spec forbids unescaped control chars (U+0000-U+001F) inside strings.
    LLMs frequently emit raw newlines/tabs in string values.
    This walks the text character by character, tracking whether we're
    inside a JSON string, and escapes any control chars found there.
    """
    result = []
    in_string = False
    escape_next = False
    for ch in text:
        if escape_next:
            result.append(ch)
            escape_next = False
            continue
        if ch == "\\" and in_string:
            result.append(ch)
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            result.append(ch)
            continue
        if in_string and ord(ch) < 0x20:
            # Escape the control char
            if ch == "\n":
                result.append("\\n")
            elif ch == "\r":
                result.append("\\r")
            elif ch == "\t":
                result.append("\\t")
            else:
                result.append(f"\\u{ord(ch):04x}")
            continue
        result.append(ch)
    return "".join(result)


class OpenRouterClient:
    """
    Single LLM gateway for polaris graph.

    All calls go through Qwen 3.5 Plus via OpenRouter (configurable via OPENROUTER_DEFAULT_MODEL).
    Two modes:
    - reason(): Extended reasoning ON. CoT returned in reasoning field, not content.
    - generate(): Reasoning OFF. Clean output only. For prose generation.
    """

    # FIX-2: Class-level circuit breaker — propagates across all client instances.
    # Once ANY instance gets 402, ALL instances stop calling.
    _billing_exhausted: bool = False

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        budget_usd: Optional[float] = None,
        session_id: Optional[str] = None,
    ):
        self.api_key = api_key or OPENROUTER_API_KEY
        self.model = model or OPENROUTER_MODEL
        self.base_url = (base_url or OPENROUTER_BASE_URL).rstrip("/")
        self.usage = UsageTracker(
            budget_usd=budget_usd or OPENROUTER_BUDGET_USD,
            session_id=session_id or "",
        )
        if not self.api_key:
            raise ValueError(
                "OPENROUTER_API_KEY not set. Add it to .env file."
            )

        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://polaris-research.ai",
                "X-Title": "polaris graph",
            },
            timeout=httpx.Timeout(DEFAULT_TIMEOUT_SECONDS),
        )

        logger.info(
            "OpenRouter client initialized: model=%s, budget=$%.2f",
            self.model,
            self.usage.budget_usd,
        )

    async def close(self):
        """Close the HTTP client."""
        await self._client.aclose()

    # ------------------------------------------------------------------
    # SSE Streaming
    # ------------------------------------------------------------------

    async def _accumulate_sse(
        self, response: httpx.Response,
    ) -> tuple[str, str, dict]:
        """Accumulate SSE chunks from a streaming response.

        Returns (content, reasoning_content, usage_data).

        Handles OpenRouter SSE format:
        - ``data: {JSON}`` — delta chunks with content/reasoning_content
        - ``data: [DONE]`` — stream terminator
        - ``: OPENROUTER PROCESSING`` — keep-alive comments (ignored)
        - Empty lines between events (ignored)

        Phase 3: Added chunk metrics (count, bytes), mid-stream error
        detection, and [DONE] terminator verification.
        """
        content_parts: list[str] = []
        reasoning_parts: list[str] = []
        usage_data: dict = {}

        # Phase 3: SSE chunk metrics
        chunk_count = 0
        content_bytes = 0
        reasoning_bytes = 0
        done_received = False

        async for line in response.aiter_lines():
            # Skip empty lines and SSE comments (keep-alive)
            if not line or line.startswith(":"):
                continue
            # SSE data lines start with "data: "
            if not line.startswith("data: "):
                continue
            payload = line[6:]  # Strip "data: " prefix
            if payload.strip() == "[DONE]":
                done_received = True
                break
            try:
                chunk = json.loads(payload)
            except (json.JSONDecodeError, ValueError):
                logger.debug("[polaris graph] SSE: skipping unparseable chunk")
                continue

            chunk_count += 1

            # Phase 3: Mid-stream error detection (SOTA research finding)
            # FIX-QWEN-1: Also detect top-level errors with empty choices
            # (Alibaba provider returns 502 as {"choices":[], "error":{...}})
            chunk_error = chunk.get("error")
            choices = chunk.get("choices", [])
            if chunk_error and not choices:
                error_msg = chunk_error.get("message", str(chunk_error))[:200]
                error_code = chunk_error.get("code", "?")
                logger.warning(
                    "[polaris graph] FIX-QWEN-1: Provider error in SSE chunk %d "
                    "(code=%s): %s",
                    chunk_count, error_code, error_msg,
                )
                raise RuntimeError(f"SSE provider error (code={error_code}): {error_msg}")
            if choices:
                finish_reason = choices[0].get("finish_reason")
                if finish_reason == "error":
                    error_info = chunk.get("error", {})
                    error_msg = error_info.get("message", "unknown mid-stream error")
                    logger.error(
                        "[polaris graph] SSE mid-stream error at chunk %d: %s",
                        chunk_count,
                        error_msg[:200],
                    )
                    raise RuntimeError(f"SSE mid-stream error: {error_msg[:200]}")

                delta = choices[0].get("delta", {})
                if delta.get("content"):
                    text = delta["content"]
                    content_parts.append(text)
                    content_bytes += len(text.encode("utf-8"))
                # Check both reasoning_content and reasoning (provider-dependent)
                rc = delta.get("reasoning_content") or delta.get("reasoning")
                if rc:
                    reasoning_parts.append(rc)
                    reasoning_bytes += len(rc.encode("utf-8"))

            # Usage data (typically in final chunk with finish_reason)
            if "usage" in chunk and chunk["usage"]:
                usage_data = chunk["usage"]

        # Phase 3: Log SSE metrics
        content_text = "".join(content_parts)
        reasoning_text = "".join(reasoning_parts)

        if chunk_count > 0:
            logger.info(
                "[polaris graph] SSE metrics: %d chunks, "
                "content=%d bytes (%d chars), reasoning=%d bytes (%d chars), "
                "done=%s, has_usage=%s",
                chunk_count,
                content_bytes,
                len(content_text),
                reasoning_bytes,
                len(reasoning_text),
                done_received,
                bool(usage_data),
            )

        if not done_received and chunk_count > 0:
            logger.warning(
                "[polaris graph] SSE stream ended without [DONE] terminator "
                "after %d chunks — possible connection drop",
                chunk_count,
            )

        return content_text, reasoning_text, usage_data

    async def _read_stream(
        self, body: dict, timeout: float,
    ) -> tuple[str, str, dict]:
        """Execute streaming POST and accumulate SSE response.

        Opens an httpx streaming connection, reads SSE events, and returns
        the accumulated (content, reasoning_content, usage) tuple.

        Handles two response formats:
        - ``text/event-stream``: True SSE — accumulate delta chunks
        - ``application/json``: Non-SSE fallback — provider returned a
          standard JSON response despite ``stream: true`` (happens when
          the provider doesn't support streaming for reasoning models)

        The httpx Timeout uses the caller's timeout for read operations
        and a generous 30s for connection establishment.
        """
        async with self._client.stream(
            "POST",
            "/chat/completions",
            json=body,
            timeout=httpx.Timeout(timeout, connect=30.0),
        ) as response:
            response.raise_for_status()

            content_type = response.headers.get("content-type", "")

            if "text/event-stream" in content_type:
                # True SSE stream — accumulate delta chunks
                logger.debug(
                    "[polaris graph] SSE path: Content-Type=%s",
                    content_type,
                )
                content, reasoning, usage = await self._accumulate_sse(response)

                # Defense: if SSE produced nothing, the stream may have
                # been malformed. Log for diagnostics.
                if not content and not reasoning and not usage:
                    logger.warning(
                        "[polaris graph] SSE stream produced no content, "
                        "reasoning, or usage. Content-Type: %s",
                        content_type,
                    )

                return content, reasoning, usage

            # Non-SSE response — provider returned standard JSON
            # despite stream:true. Read full body and parse.
            logger.info(
                "[polaris graph] Non-SSE path: Content-Type=%s",
                content_type,
            )
            raw_body = await response.aread()
            try:
                data = json.loads(raw_body)
            except (json.JSONDecodeError, ValueError) as exc:
                logger.error(
                    "[polaris graph] Non-SSE response body is not JSON "
                    "(%d bytes, Content-Type: %s): %s",
                    len(raw_body),
                    content_type,
                    str(exc)[:200],
                )
                return "", "", {}

            choices = data.get("choices", [])
            if not choices:
                return "", "", data.get("usage", {})

            message = choices[0].get("message", {})
            logger.info(
                "[polaris graph] Non-SSE response detected "
                "(Content-Type: %s). Parsing as standard JSON. "
                "content=%d chars, reasoning=%d chars",
                content_type,
                len(message.get("content", "") or ""),
                len(message.get("reasoning_content", "") or ""),
            )

            return (
                message.get("content", "") or "",
                message.get("reasoning_content", "")
                or message.get("reasoning", "")
                or "",
                data.get("usage", {}),
            )

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()

    # ------------------------------------------------------------------
    # Core API call
    # ------------------------------------------------------------------

    async def _call(
        self,
        messages: list[dict[str, str]],
        call_type: str,
        reasoning_enabled: bool = True,
        reasoning_effort: str = "high",
        temperature: float = 0.7,
        max_tokens: int = 16384,
        response_format: Optional[dict] = None,
        timeout: Optional[float] = None,
    ) -> LLMResponse:
        """Make a single API call to OpenRouter.

        A8.2: Acquires global concurrency semaphore before executing.
        This prevents GPU OOM on sovereign deployments and 429 rate
        limits on cloud APIs by limiting parallel LLM calls.
        """
        # A8.2: Global concurrency control
        from src.providers.llm_provider import get_semaphore
        semaphore = get_semaphore()
        async with semaphore:
            return await self._call_impl(
                messages, call_type, reasoning_enabled, reasoning_effort,
                temperature, max_tokens, response_format, timeout,
            )

    async def _call_impl(
        self,
        messages: list[dict[str, str]],
        call_type: str,
        reasoning_enabled: bool = True,
        reasoning_effort: str = "high",
        temperature: float = 0.7,
        max_tokens: int = 16384,
        response_format: Optional[dict] = None,
        timeout: Optional[float] = None,
    ) -> LLMResponse:
        """Internal implementation — called within semaphore context."""
        # FIX-402: Short-circuit all calls once 402 Payment Required is received.
        if OpenRouterClient._billing_exhausted:
            raise BillingExhaustedException(
                "OpenRouter billing exhausted (402 circuit breaker OPEN). "
                "No API calls will be attempted."
            )

        if self.usage.budget_exhausted:
            raise BudgetExhaustedError(
                f"Budget exhausted: ${self.usage.total_cost_usd:.2f} "
                f">= ${self.usage.budget_usd:.2f}"
            )

        # K2-3: Filter reasoning_content: null from messages to prevent
        # prompt pollution (literal "null" causes model confusion).
        sanitized_messages = []
        for msg in messages:
            clean_msg = {k: v for k, v in msg.items() if v is not None}
            sanitized_messages.append(clean_msg)

        body: dict[str, Any] = {
            "model": self.model,
            "messages": sanitized_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }

        # FIX-GLM5: Models that always route output to reasoning_content
        # need reasoning_enabled=True regardless of caller's request.
        # Without this, generate() gets empty content and fails.
        if self.model in _ALWAYS_REASON_MODELS and not reasoning_enabled:
            reasoning_enabled = True
            reasoning_effort = reasoning_effort or "medium"

        # Reasoning control — only send when explicitly enabled.
        # Sending {"enabled": False} can cause empty SSE streams on some models.
        if reasoning_enabled:
            body["reasoning"] = {"effort": reasoning_effort, "enabled": True}

        if response_format:
            body["response_format"] = response_format
            # FIX-QWEN-2: Use non-streaming for json_object responses.
            # Alibaba provider (Qwen 3.5 Plus) returns 502 on json_object+stream.
            if response_format.get("type") == "json_object" and not reasoning_enabled:
                body["stream"] = False

        # Provider routing from env; empty = let OpenRouter auto-route
        provider_order_str = os.getenv("OPENROUTER_PROVIDER_ORDER", "")
        provider_order = [p.strip() for p in provider_order_str.split(",") if p.strip()]
        allow_fb = os.getenv("OPENROUTER_ALLOW_FALLBACKS", "true").lower() == "true"
        require_params = os.getenv("OPENROUTER_REQUIRE_PARAMETERS", "true").lower() == "true"
        provider_block: dict[str, Any] = {
            "allow_fallbacks": allow_fb,
            "require_parameters": require_params,
        }
        if provider_order:
            provider_block["order"] = provider_order
        body["provider"] = provider_block

        start = time.monotonic()
        last_error = None

        for attempt in range(MAX_RETRIES + 1):
            try:
                actual_timeout = timeout or DEFAULT_TIMEOUT_SECONDS

                if body.get("stream", True):
                    # Streaming path — accumulate SSE chunks
                    content_text, reasoning_text, stream_usage = await asyncio.wait_for(
                        self._read_stream(body, actual_timeout),
                        timeout=actual_timeout + 30,
                    )
                    data = {
                        "choices": [{
                            "message": {
                                "content": content_text,
                                "reasoning_content": reasoning_text,
                            },
                            "finish_reason": "stop",
                        }],
                        "usage": stream_usage,
                        "model": self.model,
                    }
                else:
                    # FIX-QWEN-2: Non-streaming path for json_object
                    resp = await asyncio.wait_for(
                        self._client.post(
                            "/chat/completions",
                            json=body,
                            timeout=httpx.Timeout(actual_timeout, connect=30.0),
                        ),
                        timeout=actual_timeout + 30,
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    # FIX-QWEN-2: Detect provider errors in non-streaming response
                    if data.get("error") and not data.get("choices"):
                        err = data["error"]
                        raise RuntimeError(
                            f"Provider error (code={err.get('code', '?')}): "
                            f"{err.get('message', str(err))[:200]}"
                        )
                break

            except asyncio.TimeoutError:
                logger.warning(
                    "[polaris graph] FIX-SCHEMA-5: asyncio timeout after %ds "
                    "for %s (attempt %d/%d)",
                    actual_timeout + 30, call_type, attempt + 1, MAX_RETRIES + 1,
                )
                last_error = TimeoutError(
                    f"asyncio timeout after {actual_timeout + 30}s"
                )
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(RETRY_BACKOFF_BASE ** attempt)
                    continue
                raise TimeoutError(
                    f"All {MAX_RETRIES + 1} attempts timed out for {call_type}"
                ) from None

            except httpx.HTTPStatusError as exc:
                last_error = exc
                status = exc.response.status_code

                # FIX-402: Payment Required — set circuit breaker and stop immediately.
                # Prevents hundreds of wasted retries against a billing-blocked account.
                if status == 402:
                    OpenRouterClient._billing_exhausted = True
                    self.usage.total_errors += 1
                    logger.critical(
                        "[polaris graph] FIX-402: OpenRouter returned 402 Payment Required. "
                        "Circuit breaker OPEN — all subsequent LLM calls will be rejected. "
                        "Check billing at https://openrouter.ai/settings/credits"
                    )
                    raise BillingExhaustedException(
                        "OpenRouter 402 Payment Required — billing exhausted. "
                        "No further API calls will be attempted."
                    ) from exc

                # Rate limit — back off
                if status == 429:
                    wait = RETRY_BACKOFF_BASE ** (attempt + 1)
                    logger.warning(
                        "[polaris graph] Rate limited, waiting %.1fs (attempt %d/%d)",
                        wait, attempt + 1, MAX_RETRIES + 1,
                    )
                    await asyncio.sleep(wait)
                    continue

                # Server error — retry
                if status >= 500:
                    wait = RETRY_BACKOFF_BASE ** attempt
                    logger.warning(
                        "[polaris graph] Server error %d, retrying in %.1fs",
                        status, wait,
                    )
                    await asyncio.sleep(wait)
                    continue

                # Client error — don't retry
                self.usage.total_errors += 1
                raise

            except RuntimeError as exc:
                # FIX-QWEN-1: SSE mid-stream/provider errors — retry
                last_error = exc
                if attempt < MAX_RETRIES:
                    wait = RETRY_BACKOFF_BASE ** (attempt + 1)
                    logger.warning(
                        "[polaris graph] FIX-QWEN-1: SSE error, retrying in %.1fs "
                        "(attempt %d/%d): %s",
                        wait, attempt + 1, MAX_RETRIES + 1,
                        str(exc)[:100],
                    )
                    await asyncio.sleep(wait)
                    continue
                self.usage.total_errors += 1
                raise

            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                last_error = exc
                # FIX-052B: DNS failures get longer backoff (outages last 10-60s)
                is_dns_failure = "getaddrinfo" in str(exc).lower()
                if attempt < MAX_RETRIES:
                    if is_dns_failure:
                        dns_wait = float(os.getenv("PG_DNS_RETRY_BACKOFF", "30"))
                        logger.warning(
                            "[polaris graph] DNS failure (getaddrinfo), "
                            "waiting %.0fs before retry (attempt %d/%d): %s",
                            dns_wait, attempt + 1, MAX_RETRIES + 1,
                            str(exc)[:100],
                        )
                        await asyncio.sleep(dns_wait)
                    else:
                        wait = RETRY_BACKOFF_BASE ** (attempt + 1)
                        logger.warning(
                            "[polaris graph] Connection error, retrying in %.1fs: %s",
                            wait, str(exc)[:100],
                        )
                        await asyncio.sleep(wait)
                    continue
                self.usage.total_errors += 1
                raise
        else:
            self.usage.total_errors += 1
            raise last_error  # type: ignore[misc]

        duration_ms = (time.monotonic() - start) * 1000

        # SF-16: Check for empty choices before indexing
        choices = data.get("choices", [])
        if not choices:
            self.usage.total_errors += 1
            raise ValueError(
                f"API returned no choices in response for {call_type} "
                f"(model={data.get('model', '?')})"
            )
        choice = choices[0]
        message = choice.get("message", {})
        content = message.get("content", "")

        # Extract reasoning — OpenRouter returns it in reasoning_content
        # or in reasoning_details array depending on provider
        reasoning = None
        reasoning_tokens = 0

        if "reasoning_content" in message and message["reasoning_content"]:
            reasoning = message["reasoning_content"]
        elif "reasoning" in message and message["reasoning"]:
            # Some providers return it as 'reasoning'
            reasoning = message["reasoning"]

        # SF-30: Token usage from response — warn if missing
        usage_data = data.get("usage", {})
        if not usage_data:
            # FIX-O2: Estimate tokens from content length instead of defaulting to 0
            est_input = sum(len(m.get("content", "")) for m in messages) // 4
            est_output = len(content) // 4 if content else 0
            logger.warning(
                "[polaris graph] FIX-O2: API response missing usage data for %s "
                "— estimating %d/%d tokens from content length",
                call_type, est_input, est_output,
            )
            usage_data = {
                "prompt_tokens": est_input,
                "completion_tokens": est_output,
            }
        input_tokens = usage_data.get("prompt_tokens", 0)
        output_tokens = usage_data.get("completion_tokens", 0)
        reasoning_tokens = usage_data.get("reasoning_tokens", 0)
        # FIX-QM11b: OpenRouter nests reasoning_tokens inside
        # completion_tokens_details, not at top level of usage
        if not reasoning_tokens:
            ctd = usage_data.get("completion_tokens_details", {})
            if ctd:
                reasoning_tokens = ctd.get("reasoning_tokens", 0)

        # FIX-C2: Extract API-reported cost for accurate billing
        api_cost = usage_data.get("cost", 0.0)

        # Track usage
        self.usage.record(
            call_type=call_type,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            reasoning_tokens=reasoning_tokens,
            duration_ms=duration_ms,
            api_cost=api_cost,
        )

        # COT-1: Strict separation — NEVER mix reasoning into content.
        # The API separates content and reasoning_content correctly.
        # Callers (generate(), reason(), generate_structured()) handle
        # empty content at their own level with retry + extraction.
        # FIX-H2: Explicit warning and raise when BOTH content and reasoning are empty.
        # This catches degenerate API responses (0-token completions) instead of
        # silently returning empty strings that cascade into downstream failures.
        if not content and not reasoning:
            logger.warning(
                "[polaris graph] FIX-H2: LLM returned empty content AND empty "
                "reasoning_content for %s (model=%s, %d input tokens)",
                call_type,
                data.get("model", self.model),
                input_tokens,
            )
            raise ValueError(
                f"LLM returned no usable content for {call_type} "
                f"(model={data.get('model', '?')}, input_tokens={input_tokens})"
            )

        if not content and reasoning:
            logger.warning(
                "[polaris graph] COT-1: Content empty for %s, reasoning has "
                "%d chars (reasoning_enabled=%s, response_format=%s). "
                "Returning as-is — caller handles recovery.",
                call_type,
                len(reasoning),
                reasoning_enabled,
                bool(response_format),
            )

        result = LLMResponse(
            content=content,
            reasoning=reasoning,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            reasoning_tokens=reasoning_tokens,
            model=data.get("model", self.model),
            duration_ms=duration_ms,
            raw_response=data,
        )

        logger.info(
            "[polaris graph] %s completed: %d in/%d out/%d reasoning tokens, "
            "%.1fs, $%.4f cumulative",
            call_type,
            input_tokens,
            output_tokens,
            reasoning_tokens,
            duration_ms / 1000,
            self.usage.total_cost_usd,
        )

        # OBS-COST: Emit authoritative llm_call trace with real tokens + cost.
        # This is the SINGLE source of truth — agents no longer need to pass
        # tokens to tracer.llm_call() since the client does it here.
        _cost_tracer = _current_tracer.get(None)
        if _cost_tracer is not None:
            _node = call_type.split(":")[0] if ":" in call_type else "llm"
            _cost_tracer.llm_call(
                node=_node,
                call_type=call_type,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                duration_ms=duration_ms,
                reasoning_tokens=reasoning_tokens,
                cost_usd=round(
                    api_cost if api_cost > 0 else
                    (input_tokens / 1_000_000) * INPUT_COST_PER_M
                    + (output_tokens / 1_000_000) * OUTPUT_COST_PER_M,
                    6,
                ),
                cumulative_cost_usd=round(self.usage.total_cost_usd, 4),
                model=self.model[:50],
            )

        # OBS-REASONING: Persist reasoning to trace JSONL
        if reasoning and isinstance(reasoning, str) and len(reasoning) > 10:
            _obs_tracer = _current_tracer.get(None)
            if _obs_tracer is not None:
                _obs_tracer.reasoning_capture(
                    node=call_type.split(":")[0] if ":" in call_type else "llm",
                    call_type=call_type,
                    reasoning_text=reasoning,
                    prompt_excerpt=(messages[-1].get("content") or "")[:1000] if messages else "",
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    reasoning_tokens=reasoning_tokens,
                )

        # WAVE-1.3: Full LLM prompt + response trace (100% visibility)
        # Every _call() emits complete prompt messages, response, reasoning,
        # and all parameters. ~80-120 events per run, ~2-5MB total.
        _detail_tracer = _current_tracer.get(None)
        if _detail_tracer is not None:
            _detail_node = call_type.split(":")[0] if ":" in call_type else "llm"
            _detail_cost = round(
                api_cost if api_cost > 0 else
                (input_tokens / 1_000_000) * INPUT_COST_PER_M
                + (output_tokens / 1_000_000) * OUTPUT_COST_PER_M,
                6,
            )
            _detail_tracer._emit("llm_detail", _detail_node, {
                "call_type": call_type,
                "model": self.model,
                "temperature": body.get("temperature"),
                "max_tokens": body.get("max_tokens"),
                "reasoning_enabled": reasoning_enabled,
                "response_format": str(body.get("response_format", "")),
                "prompt_messages": [
                    {"role": m.get("role", ""), "content": m.get("content", "")}
                    for m in messages
                ],
                "response_content": result.content or "[EMPTY_RESPONSE]",
                "response_reasoning": result.reasoning or "",
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "reasoning_tokens": result.reasoning_tokens,
                "duration_ms": result.duration_ms,
                "cost_usd": _detail_cost,
            })

        return result

    # ------------------------------------------------------------------
    # Public API: Two modes
    # ------------------------------------------------------------------

    async def reason(
        self,
        prompt: str,
        system: str = "",
        schema: Optional[Type[T]] = None,
        effort: str = "high",
        max_tokens: int = 16384,
        timeout: Optional[float] = None,
    ) -> LLMResponse:
        """
        Analysis/planning call — reasoning ON, returned separately.

        Use for: query planning, evidence analysis, claim verification,
        citation checking, gap identification.

        Reasoning appears in response.reasoning, NOT in response.content.
        """
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        response_format = None
        if schema:
            response_format = {
                "type": "json_schema",
                "json_schema": {
                    "name": schema.__name__,
                    "strict": False,
                    "schema": schema.model_json_schema(),
                },
            }

        result = await self._call(
            messages=messages,
            call_type=f"reason:{schema.__name__ if schema else 'free'}",
            reasoning_enabled=True,
            reasoning_effort=effort,
            temperature=0.7,
            max_tokens=max_tokens,
            response_format=response_format,
            timeout=timeout or LONG_TIMEOUT_SECONDS,
        )

        # SF-28: Initialize _parsed to None to prevent AttributeError
        result._parsed = None  # type: ignore[attr-defined]

        # COT-3: Handle empty content from provider misroute in reason() calls.
        # For free-form reason() (no schema), extract answer from reasoning.
        # For schema calls, generate_structured() already handles this via
        # _extract_json_from_text() — but reason() with schema needs recovery too.
        if not result.content.strip() and result.reasoning:
            extracted = _extract_answer_from_reasoning(result.reasoning)
            if extracted:
                logger.info(
                    "[polaris graph] COT-3: reason() recovered %d chars from "
                    "reasoning via </think> split (schema=%s)",
                    len(extracted),
                    schema.__name__ if schema else "none",
                )
                result = LLMResponse(
                    content=extracted,
                    reasoning=result.reasoning,
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                    reasoning_tokens=result.reasoning_tokens,
                    model=result.model,
                    duration_ms=result.duration_ms,
                    raw_response=result.raw_response,
                )
                result._parsed = None  # type: ignore[attr-defined]
            elif not schema:
                # COT-3 fast path: For free-form reason() (no schema),
                # the reasoning IS the answer — use it directly without retry.
                # FIX-071B: Strip CoT prefix for always-reason models.
                _reason_content = result.reasoning
                if self.model in _ALWAYS_REASON_MODELS:
                    import re as _re
                    _cot_end = _re.search(
                        r"\n(?=(?:##\s|[A-Z][a-z].*(?:\[\d+\]|\[CITE:|\(95%|MD\s|SMD\s)))",
                        _reason_content,
                    )
                    if _cot_end and _cot_end.start() > 100:
                        _reason_content = _reason_content[_cot_end.start():].lstrip()
                        logger.info(
                            "[polaris graph] FIX-071B: Stripped %d chars CoT from "
                            "reason() free-form output",
                            _cot_end.start(),
                        )
                logger.info(
                    "[polaris graph] COT-3: Free-form reason() using "
                    "reasoning as content (%d chars, no schema to parse)",
                    len(_reason_content),
                )
                result = LLMResponse(
                    content=_reason_content,
                    reasoning=result.reasoning,
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                    reasoning_tokens=result.reasoning_tokens,
                    model=result.model,
                    duration_ms=result.duration_ms,
                    raw_response=result.raw_response,
                )
                result._parsed = None  # type: ignore[attr-defined]
            else:
                # Schema call — retry once, provider may re-route
                logger.warning(
                    "[polaris graph] COT-3: reason() content empty, no </think> "
                    "in reasoning (%d chars). Retrying once (schema=%s).",
                    len(result.reasoning),
                    schema.__name__,
                )
                result = await self._call(
                    messages=messages,
                    call_type=f"reason_retry:{schema.__name__ if schema else 'free'}",
                    reasoning_enabled=True,
                    reasoning_effort=effort,
                    temperature=0.7,
                    max_tokens=max_tokens,
                    response_format=response_format,
                    timeout=timeout or LONG_TIMEOUT_SECONDS,
                )
                result._parsed = None  # type: ignore[attr-defined]
                # Try extraction on retry
                if not result.content.strip() and result.reasoning:
                    extracted = _extract_answer_from_reasoning(result.reasoning)
                    if extracted:
                        result = LLMResponse(
                            content=extracted,
                            reasoning=result.reasoning,
                            input_tokens=result.input_tokens,
                            output_tokens=result.output_tokens,
                            reasoning_tokens=result.reasoning_tokens,
                            model=result.model,
                            duration_ms=result.duration_ms,
                            raw_response=result.raw_response,
                        )
                        result._parsed = None  # type: ignore[attr-defined]
                    elif not schema:
                        # COT-3 fallback: For free-form reason() (no schema),
                        # the reasoning IS the answer. Use it as content.
                        # This is correct because reason() with no schema is
                        # asking for analysis/planning where the model's
                        # reasoning output is the desired result.
                        logger.info(
                            "[polaris graph] COT-3: Free-form reason() using "
                            "reasoning as content (%d chars, no schema to parse)",
                            len(result.reasoning),
                        )
                        result = LLMResponse(
                            content=result.reasoning,
                            reasoning=result.reasoning,
                            input_tokens=result.input_tokens,
                            output_tokens=result.output_tokens,
                            reasoning_tokens=result.reasoning_tokens,
                            model=result.model,
                            duration_ms=result.duration_ms,
                            raw_response=result.raw_response,
                        )
                        result._parsed = None  # type: ignore[attr-defined]
                    else:
                        # COT-3 schema fallback: reason() with schema, content
                        # still empty after retry. Try extracting JSON from
                        # reasoning (same pattern as generate_structured()).
                        json_extracted = _extract_json_from_text(result.reasoning)
                        if json_extracted:
                            logger.info(
                                "[polaris graph] COT-3: reason() schema fallback — "
                                "extracted %d chars JSON from reasoning for %s",
                                len(json_extracted),
                                schema.__name__,
                            )
                            result = LLMResponse(
                                content=json_extracted,
                                reasoning=result.reasoning,
                                input_tokens=result.input_tokens,
                                output_tokens=result.output_tokens,
                                reasoning_tokens=result.reasoning_tokens,
                                model=result.model,
                                duration_ms=result.duration_ms,
                                raw_response=result.raw_response,
                            )
                            result._parsed = None  # type: ignore[attr-defined]
                        else:
                            logger.warning(
                                "[polaris graph] COT-3: reason() with schema=%s "
                                "has empty content after retry and no JSON in "
                                "reasoning (%d chars). Schema parsing will skip.",
                                schema.__name__,
                                len(result.reasoning),
                            )

        # Parse schema if provided
        if schema and result.content:
            cleaned = _clean_json(result.content)
            try:
                parsed = schema.model_validate_json(cleaned)
                result._parsed = parsed  # type: ignore[attr-defined]
            except (ValidationError, json.JSONDecodeError) as exc:
                logger.warning(
                    "[polaris graph] Schema validation failed for %s: %s",
                    schema.__name__, str(exc)[:500],
                )
                # One retry with error feedback
                retry_prompt = (
                    f"{prompt}\n\n"
                    f"IMPORTANT: Your previous response failed validation:\n"
                    f"{str(exc)[:500]}\n"
                    f"Please fix the JSON and try again."
                )
                messages[-1] = {"role": "user", "content": retry_prompt}
                result = await self._call(
                    messages=messages,
                    call_type=f"reason_retry:{schema.__name__}",
                    reasoning_enabled=True,
                    reasoning_effort=effort,
                    temperature=0.5,
                    max_tokens=max_tokens,
                    response_format=response_format,
                    timeout=timeout or LONG_TIMEOUT_SECONDS,
                )
                if result.content:
                    cleaned = _clean_json(result.content)
                    parsed = schema.model_validate_json(cleaned)
                    result._parsed = parsed  # type: ignore[attr-defined]

        return result

    async def generate(
        self,
        prompt: str,
        system: str = "",
        max_tokens: int = 4096,
        temperature: float = 0.7,
        timeout: Optional[float] = None,
    ) -> LLMResponse:
        """
        Prose/output call — reasoning OFF, clean output only.

        Use for: section writing, report prose, summaries.

        No CoT in the output. No reasoning field. Just clean text.

        COT-2: If content is empty but reasoning has substance, try to
        extract the answer from reasoning (provider misroute). If that
        fails, retry once (OpenRouter may re-route to a different provider).
        """
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        result = await self._call(
            messages=messages,
            call_type="generate",
            reasoning_enabled=False,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout or DEFAULT_TIMEOUT_SECONDS,
        )

        # COT-2: Handle empty content from provider misroute
        if not result.content.strip() and result.reasoning:
            extracted = _extract_answer_from_reasoning(result.reasoning)
            if extracted:
                logger.info(
                    "[polaris graph] COT-2: generate() recovered %d chars from "
                    "reasoning via </think> split",
                    len(extracted),
                )
                result = LLMResponse(
                    content=extracted,
                    reasoning=result.reasoning,
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                    reasoning_tokens=result.reasoning_tokens,
                    model=result.model,
                    duration_ms=result.duration_ms,
                    raw_response=result.raw_response,
                )
            elif self.model in _ALWAYS_REASON_MODELS:
                # FIX-GLM5: Models that always reason don't use </think> tags.
                # Use reasoning directly as content (same as COT-3 free-form).
                # FIX-GLM5-COT: Strip chain-of-thought markers from reasoning
                # before using as content. GLM-5 puts "1. **Analyze the Request:**"
                # and "The user wants..." thinking before the actual output.
                _cleaned_reasoning = result.reasoning
                import re as _re

                # Strategy 1: Find end of numbered thinking steps pattern
                # GLM-5 uses "1. **Analyze...**\n2. **Draft...**\n" then output
                _thinking_block = _re.search(
                    r"\n(?=(?:##\s|[A-Z][a-z]{3,}.*(?:\[|\(95%|MD\s|SMD\s|HR\s|RR\s|OR\s)))",
                    _cleaned_reasoning,
                )

                # Strategy 2: Find after "Now let me" / "Here is" / "Output:" patterns
                if not _thinking_block or _thinking_block.start() < 50:
                    _thinking_block = _re.search(
                        r"\n(?:(?:Now let me|Here is|Here's|Output:?|The revised|The edited|REVISED|EDITED).*\n)",
                        _cleaned_reasoning,
                        _re.IGNORECASE,
                    )
                    if _thinking_block:
                        _thinking_block = type('M', (), {'start': lambda s=_thinking_block: s.end()})()

                # Strategy 3: Original domain-keyword detection
                if not _thinking_block or _thinking_block.start() < 50:
                    _thinking_block = _re.search(
                        r"(?:^|\n)(?=[A-Z][a-z].*(?:\[CITE:|\[\d+\]|fasting|study|meta|trial|evidence|research|protocol|clinical))",
                        _cleaned_reasoning,
                    )

                if _thinking_block and _thinking_block.start() > 100:
                    _cleaned_reasoning = _cleaned_reasoning[_thinking_block.start():].lstrip()
                    logger.info(
                        "[polaris graph] FIX-GLM5-COT: Stripped %d chars CoT prefix "
                        "from generate() reasoning",
                        _thinking_block.start(),
                    )
                logger.info(
                    "[polaris graph] FIX-GLM5: generate() using reasoning as "
                    "content for always-reason model %s (%d chars)",
                    self.model, len(_cleaned_reasoning),
                )
                result = LLMResponse(
                    content=_cleaned_reasoning,
                    reasoning=result.reasoning,
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                    reasoning_tokens=result.reasoning_tokens,
                    model=result.model,
                    duration_ms=result.duration_ms,
                    raw_response=result.raw_response,
                )
            else:
                # No </think> tag — retry once (provider re-route)
                logger.warning(
                    "[polaris graph] COT-2: generate() content empty, no </think> "
                    "in reasoning (%d chars). Retrying once.",
                    len(result.reasoning),
                )
                result = await self._call(
                    messages=messages,
                    call_type="generate_retry",
                    reasoning_enabled=False,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=timeout or DEFAULT_TIMEOUT_SECONDS,
                )
                # Try extraction on retry result too
                if not result.content.strip() and result.reasoning:
                    extracted = _extract_answer_from_reasoning(result.reasoning)
                    if extracted:
                        result = LLMResponse(
                            content=extracted,
                            reasoning=result.reasoning,
                            input_tokens=result.input_tokens,
                            output_tokens=result.output_tokens,
                            reasoning_tokens=result.reasoning_tokens,
                            model=result.model,
                            duration_ms=result.duration_ms,
                            raw_response=result.raw_response,
                        )
                    else:
                        # SF-15: Fail loud after exhausting retries
                        self.usage.total_errors += 1
                        raise RuntimeError(
                            f"generate() content empty after retry. "
                            f"Reasoning has {len(result.reasoning)} chars but "
                            f"no extractable answer. Provider misrouted output."
                        )

        return result

    async def generate_structured(
        self,
        prompt: str,
        schema: Type[T],
        system: str = "",
        max_tokens: int = 8192,
        timeout: Optional[float] = None,
        reasoning_enabled: bool = False,
        reasoning_effort: str = "high",
    ) -> T:
        """
        Structured output call — reasoning OFF by default, returns parsed schema.

        When reasoning is DISABLED and PG_STRICT_JSON_SCHEMA=1 (default),
        sends response_format with json_schema + strict:true to enforce
        schema compliance at the provider level (Qwen 3.5 Plus supports this).

        When reasoning is ENABLED, relies on prompt-based JSON extraction
        because thinking + json_schema response_format are incompatible.

        FIX-QM1: When reasoning IS explicitly enabled, checks both content
        and reasoning_content for JSON (some models put JSON in reasoning).
        """
        # Use strict:true JSON schema when reasoning is disabled and env allows.
        # Qwen3.5-Plus supports strict schema enforcement. Gate behind
        # PG_STRICT_JSON_SCHEMA (default "1") for backwards compatibility.
        # When reasoning is enabled, skip — thinking + json_schema are incompatible.
        response_format = None
        strict_schema_enabled = os.getenv("PG_STRICT_JSON_SCHEMA", "1") == "1"
        if not reasoning_enabled and strict_schema_enabled:
            try:
                json_schema = schema.model_json_schema()
                response_format = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": schema.__name__,
                        "strict": True,
                        "schema": json_schema,
                    },
                }
            except Exception as schema_exc:
                logger.warning(
                    "[polaris graph] Strict JSON schema extraction failed for %s: %s "
                    "— falling back to prompt-based JSON",
                    schema.__name__, str(schema_exc)[:200],
                )
                response_format = None

        # Ensure system message instructs JSON output (defense-in-depth even with strict schema)
        json_hint = (
            "You MUST respond with valid JSON only. No prose, no markdown, "
            "no code fences — just the JSON object."
        )
        messages = []
        if system:
            messages.append({"role": "system", "content": f"{system}\n\n{json_hint}"})
        else:
            messages.append({"role": "system", "content": json_hint})
        messages.append({"role": "user", "content": prompt})

        result = await self._call(
            messages=messages,
            call_type=f"structured:{schema.__name__}",
            reasoning_enabled=reasoning_enabled,
            reasoning_effort=reasoning_effort,
            temperature=0.5,
            max_tokens=max_tokens,
            response_format=response_format,
            timeout=timeout or DEFAULT_TIMEOUT_SECONDS,
        )

        # FIX-QM1 + FIX-QM11c + FIX-V6: Extract JSON from reasoning when content
        # is empty OR contains stub content. Provider may put CoT + JSON into
        # reasoning field. FIX-V6: LLM sometimes returns verifications as
        # a 3-char string ':[{' instead of a JSON array — detect this stub
        # pattern and fall back to reasoning extraction.
        json_source = result.content
        _is_stub = False
        if json_source and json_source.strip():
            # FIX-V6: Detect stub content — valid JSON whose array fields
            # are strings instead of arrays (e.g. {"verifications":":[{"})
            try:
                _probe = json.loads(_clean_json(json_source))
                if isinstance(_probe, dict):
                    for _k, _v in _probe.items():
                        if isinstance(_v, str) and _v.strip().startswith(":["):
                            _is_stub = True
                            logger.warning(
                                "[polaris graph] FIX-V6: Stub content detected for %s "
                                "(key=%s, value=%s) — trying reasoning fallback",
                                schema.__name__, _k, repr(_v[:50]),
                            )
                            break
            except (json.JSONDecodeError, Exception):
                pass  # Not valid JSON at all — will fail later and retry
        if not json_source.strip() or _is_stub:
            if result.reasoning and result.reasoning.strip():
                # Try to extract just the JSON object from mixed text
                extracted = _extract_json_from_text(result.reasoning)
                if extracted:
                    json_source = extracted
                    logger.info(
                        "[polaris graph] FIX-V6: JSON recovered from reasoning "
                        "for %s (%d chars from %d char reasoning, stub=%s)",
                        schema.__name__,
                        len(json_source),
                        len(result.reasoning),
                        _is_stub,
                    )
                elif not _is_stub:
                    # Original FIX-QM1 fallback: use full reasoning as JSON source
                    json_source = result.reasoning
                    logger.info(
                        "[polaris graph] FIX-QM1: Using full reasoning as JSON "
                        "for %s (%d chars)",
                        schema.__name__,
                        len(json_source),
                    )

        # FIX-SCHEMA-4: Handle prose-prefix before JSON even with reasoning OFF.
        # LLM sometimes ignores response_format=json_object and returns
        # prose text before/instead of JSON. Try to extract JSON from content.
        cleaned = _clean_json(json_source)
        if cleaned and not cleaned.lstrip().startswith("{") and not cleaned.lstrip().startswith("["):
            extracted = _extract_json_from_text(cleaned)
            if extracted:
                logger.info(
                    "[polaris graph] FIX-SCHEMA-4: Extracted JSON from prose "
                    "content for %s (%d chars from %d char content)",
                    schema.__name__,
                    len(extracted),
                    len(cleaned),
                )
                cleaned = extracted
            elif not reasoning_enabled and result.reasoning and result.reasoning.strip():
                # Provider misrouted: output in reasoning despite reasoning=OFF
                extracted_r = _extract_json_from_text(result.reasoning)
                if extracted_r:
                    logger.info(
                        "[polaris graph] FIX-SCHEMA-4: Extracted JSON from "
                        "reasoning (misrouted, reasoning=OFF) for %s",
                        schema.__name__,
                    )
                    cleaned = extracted_r
        # FIX-SCHEMA-6: Log if spurious-quote pattern was detected and fixed
        if '": [' in cleaned and schema.__name__ in (
            "SourceAnalysisBatch", "VerificationBatch", "PageSummaryBatch",
        ):
            logger.debug(
                "[polaris graph] %s: cleaned_len=%d, preview=%s",
                schema.__name__, len(cleaned), cleaned[:200],
            )
        try:
            parsed = schema.model_validate_json(cleaned)
            # FIX-CA1: If ClusterAssessment has empty reasoning/claims but
            # reasoning_content is available, extract from there.
            if (
                schema.__name__ == "ClusterAssessment"
                and result.reasoning
                and len(result.reasoning) > 100
            ):
                if not getattr(parsed, "reasoning", "") or not getattr(parsed, "key_claims", []):
                    import re as _re
                    r_text = result.reasoning
                    # Try to extract reasoning summary
                    if not parsed.reasoning:
                        # Take first 2-3 sentences from reasoning
                        _sentences = _re.split(r'(?<=[.!?])\s+', r_text[:800])
                        parsed.reasoning = " ".join(_sentences[:3]).strip()
                    # Try to extract key claims
                    if not parsed.key_claims:
                        # Look for bullet points or numbered items in reasoning
                        _bullets = _re.findall(
                            r'[-*]\s*(.{20,200}?)(?:\n|$)', r_text
                        )
                        if _bullets:
                            parsed.key_claims = [b.strip() for b in _bullets[:5]]
                        else:
                            # Extract sentences mentioning data/numbers
                            _data_sents = [
                                s.strip() for s in _re.split(r'(?<=[.!?])\s+', r_text)
                                if _re.search(r'\d+\.?\d*\s*(%|MPa|mg|mg/L|ppm|°C|kg)', s)
                            ]
                            parsed.key_claims = _data_sents[:5]
                    # Check for structured data mentions
                    if not parsed.has_structured_data and _re.search(
                        r'(compar|table|chart|numer|measurement|time.series|ranking)',
                        r_text, _re.I
                    ):
                        parsed.has_structured_data = True
                        for dtype in ("comparison", "time_series", "measurement", "ranking"):
                            if dtype.replace("_", " ") in r_text.lower() or dtype in r_text.lower():
                                parsed.data_type = dtype
                                break
            return parsed
        except (ValidationError, json.JSONDecodeError) as exc:
            # Try truncated JSON repair before retrying LLM call
            repaired = _repair_truncated_json(cleaned)
            if repaired:
                try:
                    parsed = schema.model_validate_json(repaired)
                    # FIX-O3: Log recovered object count, not just size change
                    try:
                        repaired_data = json.loads(repaired)
                        first_key = next(iter(repaired_data), "")
                        obj_count = len(repaired_data.get(first_key, [])) if isinstance(repaired_data.get(first_key), list) else 1
                    except Exception:
                        obj_count = "?"
                    logger.info(
                        "[polaris graph] FIX-O3: Repaired truncated JSON for %s "
                        "— recovered %s objects (%d chars → %d chars)",
                        schema.__name__,
                        obj_count,
                        len(cleaned),
                        len(repaired),
                    )
                    return parsed
                except (ValidationError, json.JSONDecodeError) as repair_exc:
                    # SF-29: Log repair failure instead of bare pass
                    logger.warning(
                        "[polaris graph] JSON repair also failed for %s: %s",
                        schema.__name__,
                        str(repair_exc)[:200],
                    )

            logger.warning(
                "[polaris graph] Structured parse failed (%d chars), "
                "retrying: %s",
                len(cleaned),
                str(exc)[:200],
            )
            # Retry with error feedback
            retry_prompt = (
                f"{prompt}\n\n"
                f"IMPORTANT: Your previous response failed validation:\n"
                f"{str(exc)[:500]}\n"
                f"Please fix the JSON and try again. "
                f"Return ONLY valid JSON matching the required format."
            )
            messages[-1] = {"role": "user", "content": retry_prompt}
            result = await self._call(
                messages=messages,
                call_type=f"structured_retry:{schema.__name__}",
                reasoning_enabled=reasoning_enabled,
                reasoning_effort=reasoning_effort,
                temperature=0.3,
                max_tokens=max_tokens,
                response_format=response_format,
                timeout=timeout or DEFAULT_TIMEOUT_SECONDS,
            )

            # FIX-QM1 + FIX-QM11c + FIX-V6: Extract JSON from reasoning on retry too
            json_source = result.content
            _is_stub_retry = False
            if json_source and json_source.strip():
                try:
                    _probe_r = json.loads(_clean_json(json_source))
                    if isinstance(_probe_r, dict):
                        for _k_r, _v_r in _probe_r.items():
                            if isinstance(_v_r, str) and _v_r.strip().startswith(":["):
                                _is_stub_retry = True
                                logger.warning(
                                    "[polaris graph] FIX-V6: Stub content on retry for %s "
                                    "(key=%s) — trying reasoning fallback",
                                    schema.__name__, _k_r,
                                )
                                break
                except (json.JSONDecodeError, Exception):
                    pass
            if (not json_source.strip() or _is_stub_retry) and reasoning_enabled:
                if result.reasoning and result.reasoning.strip():
                    extracted = _extract_json_from_text(result.reasoning)
                    if extracted:
                        json_source = extracted
                        logger.info(
                            "[polaris graph] FIX-V6: JSON recovered from reasoning "
                            "on retry for %s (%d chars, stub=%s)",
                            schema.__name__,
                            len(json_source),
                            _is_stub_retry,
                        )
                    elif not _is_stub_retry:
                        json_source = result.reasoning
                        logger.info(
                            "[polaris graph] FIX-QM1: Using full reasoning as JSON "
                            "on retry for %s (%d chars)",
                            schema.__name__,
                            len(json_source),
                        )

            cleaned = _clean_json(json_source)
            # FIX-SCHEMA-4: Same prose-extraction on retry path
            if cleaned and not cleaned.lstrip().startswith("{") and not cleaned.lstrip().startswith("["):
                extracted = _extract_json_from_text(cleaned)
                if extracted:
                    cleaned = extracted
                elif not reasoning_enabled and result.reasoning and result.reasoning.strip():
                    extracted_r = _extract_json_from_text(result.reasoning)
                    if extracted_r:
                        cleaned = extracted_r
            # Try repair on retry too
            try:
                return schema.model_validate_json(cleaned)
            except (ValidationError, json.JSONDecodeError):
                repaired = _repair_truncated_json(cleaned)
                if repaired:
                    return schema.model_validate_json(repaired)
                raise

    async def validate_reasoning(self) -> bool:
        """Quick check that reasoning tokens are produced. Returns True if working."""
        try:
            result = await self._call(
                messages=[{"role": "user", "content": "What is 2+2? Answer in one word."}],
                call_type="validate_reasoning",
                reasoning_enabled=True,
                reasoning_effort="low",
                temperature=0.0,
                max_tokens=50,
                timeout=30,
            )
            # FIX-QM11c: Check both reasoning_tokens AND reasoning content.
            # Some providers (e.g., DeepInfra) produce reasoning output
            # but don't report the token count in usage.
            has_reasoning_tokens = result.reasoning_tokens > 0
            has_reasoning_content = bool(result.reasoning and len(result.reasoning) > 10)

            if has_reasoning_tokens or has_reasoning_content:
                logger.info(
                    "[polaris graph] FIX-QM11: Reasoning validation PASSED "
                    "(tokens=%d, reasoning_content=%d chars)",
                    result.reasoning_tokens,
                    len(result.reasoning or ""),
                )
                return True
            logger.warning(
                "[polaris graph] FIX-QM11: Reasoning validation FAILED "
                "(0 reasoning tokens, no reasoning content). "
                "Provider may not support reasoning.",
            )
            return False
        except Exception as exc:
            logger.warning(
                "[polaris graph] FIX-QM11: Reasoning validation error: %s",
                str(exc)[:200],
            )
            return False
