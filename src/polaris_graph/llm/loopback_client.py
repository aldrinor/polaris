"""Human-in-the-loop LLM client that replaces OpenRouterClient.

The pipeline runs normally. At every LLM call site, instead of an HTTP request
to OpenRouter, the prompt is written to disk under loopback/pending/. The call
blocks until a corresponding response file appears under loopback/responses/.
The operator (or a separate Claude session) reads the prompt files, generates
responses by hand, and writes them to disk. The pipeline picks them up and
continues.

This is the "Claude Code as the LLM" approach: zero OpenRouter cost; the entire
pipeline executes end-to-end with a real LLM in the loop, surfacing every
code-bug, schema mismatch, and state-machine regression at the cost of the
operator's time.

Drop-in replacement: same constructor signature, same generate / generate_structured
async methods, same async-context-manager semantics, same .usage and .model
attributes that the rest of the codebase reads.

Activated by setting `PG_LOOPBACK_MODE=1`. Detection happens in graph.py at
client construction time (no other code paths need to change).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any, Optional, Type, TypeVar

from pydantic import BaseModel

from src.polaris_graph.llm.openrouter_client import (
    LLMResponse,
    UsageTracker,
)

T = TypeVar("T", bound=BaseModel)
logger = logging.getLogger(__name__)

LOOPBACK_DIR = Path(os.getenv("PG_LOOPBACK_DIR", "loopback"))
PENDING_DIR = LOOPBACK_DIR / "pending"
RESPONSES_DIR = LOOPBACK_DIR / "responses"
DONE_DIR = LOOPBACK_DIR / "done"
POLL_INTERVAL_SEC = 0.5
DEFAULT_TIMEOUT_SEC = float(os.getenv("PG_LOOPBACK_TIMEOUT_SEC", "7200"))  # 2h per call


class LoopbackLLMClient:
    """Drop-in OpenRouterClient replacement for human-in-the-loop testing."""

    _billing_exhausted = False  # mirror class-level OpenRouterClient flag

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        budget_usd: Optional[float] = None,
        session_id: str = "",
    ) -> None:
        self.model = model or "loopback/operator"
        self.usage = UsageTracker(
            budget_usd=budget_usd or 0.0,  # no real budget — operator is free
            session_id=session_id,
        )
        for d in (PENDING_DIR, RESPONSES_DIR, DONE_DIR):
            d.mkdir(parents=True, exist_ok=True)
        logger.info(
            "[LOOPBACK] Initialized — pending=%s, responses=%s, done=%s",
            PENDING_DIR, RESPONSES_DIR, DONE_DIR,
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def close(self):
        return None

    async def validate_reasoning(self) -> bool:
        """Loopback always reports reasoning OK; we don't validate here."""
        return True

    async def generate(
        self,
        prompt: str,
        system: str = "",
        max_tokens: int = 4096,
        temperature: float = 0.7,
        timeout: Optional[float] = None,
        reasoning_max_tokens: Optional[int] = None,
        reasoning_exclude: Optional[bool] = None,
    ) -> LLMResponse:
        """Block until operator writes a response file."""
        return await self._loopback_call(
            prompt=prompt,
            system=system,
            call_type="generate",
            schema_name=None,
            schema_json=None,
            max_tokens=max_tokens,
            temperature=temperature,
            timeout=timeout,
            reasoning_exclude=reasoning_exclude,
        )

    async def reason(
        self,
        prompt: str,
        system: str = "",
        schema: Optional[Type[T]] = None,
        effort: str = "high",
        max_tokens: int = 16384,
        timeout: Optional[float] = None,
        reasoning_max_tokens: Optional[int] = None,
        reasoning_exclude: Optional[bool] = None,
    ) -> LLMResponse:
        """Analysis/planning call — loopback version.

        OpenRouterClient separates reasoning from content. For loopback the
        operator writes a single response; we put it in .content and leave
        .reasoning empty unless the operator explicitly supplied one. Callers
        that check response.reasoning get an empty string; callers that read
        response.content get the operator's answer. This matches the
        production behavior when reasoning_exclude=True.
        """
        call_type = "reason"
        if schema is not None:
            call_type = f"reason:{schema.__name__}"
            try:
                schema_json = schema.model_json_schema()
            except Exception:
                schema_json = {"name": schema.__name__}
            response = await self._loopback_call(
                prompt=prompt,
                system=system,
                call_type=call_type,
                schema_name=schema.__name__,
                schema_json=schema_json,
                max_tokens=max_tokens,
                temperature=0.0,
                timeout=timeout,
                reasoning_exclude=reasoning_exclude,
            )
            # The schema branch exists so reason(schema=X) callers can still
            # parse — but reason() historically returned LLMResponse, not a
            # schema instance. Preserve that contract; callers that want a
            # schema instance should use generate_structured().
            return response
        return await self._loopback_call(
            prompt=prompt,
            system=system,
            call_type=call_type,
            schema_name=None,
            schema_json=None,
            max_tokens=max_tokens,
            temperature=0.0,
            timeout=timeout,
            reasoning_exclude=reasoning_exclude,
        )

    async def generate_structured(
        self,
        prompt: str,
        schema: Type[T],
        system: str = "",
        max_tokens: int = 8192,
        timeout: Optional[float] = None,
        reasoning_enabled: bool = False,
        reasoning_effort: str = "high",
        reasoning_max_tokens: Optional[int] = None,
        reasoning_exclude: Optional[bool] = None,
    ) -> T:
        """Block until operator writes a response file. Parse as schema."""
        try:
            schema_json = schema.model_json_schema()
        except Exception:
            schema_json = {"name": schema.__name__}

        response = await self._loopback_call(
            prompt=prompt,
            system=system,
            call_type=f"structured:{schema.__name__}",
            schema_name=schema.__name__,
            schema_json=schema_json,
            max_tokens=max_tokens,
            temperature=0.0,
            timeout=timeout,
            reasoning_exclude=reasoning_exclude,
        )

        content = response.content.strip()
        # Strip optional code fences the operator might leave in
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])
            content = content.strip()

        try:
            return schema.model_validate_json(content)
        except Exception as exc:
            logger.error(
                "[LOOPBACK] Failed to parse response as %s: %s\nRaw: %s",
                schema.__name__, exc, content[:500],
            )
            raise

    async def _loopback_call(
        self,
        prompt: str,
        system: str,
        call_type: str,
        schema_name: Optional[str],
        schema_json: Optional[dict],
        max_tokens: int,
        temperature: float,
        timeout: Optional[float],
        reasoning_exclude: Optional[bool],
    ) -> LLMResponse:
        req_id = uuid.uuid4().hex[:12]
        timeout_sec = timeout or DEFAULT_TIMEOUT_SEC
        req_path = PENDING_DIR / f"req_{req_id}.json"
        resp_path = RESPONSES_DIR / f"resp_{req_id}.json"
        start_ts = time.time()

        request = {
            "request_id": req_id,
            "call_type": call_type,
            "schema_name": schema_name,
            "schema_json": schema_json,
            "system": system,
            "prompt": prompt,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "reasoning_exclude": reasoning_exclude,
            "timestamp": start_ts,
        }
        with open(req_path, "w", encoding="utf-8") as f:
            json.dump(request, f, indent=2)

        # Banner so the operator sees this in the launching shell
        banner = (
            f"[LOOPBACK] PENDING req_{req_id} call_type={call_type} "
            f"prompt={len(prompt)}c system={len(system)}c max_tokens={max_tokens}"
        )
        logger.info(banner)
        print(banner, flush=True)

        deadline = time.monotonic() + timeout_sec
        while time.monotonic() < deadline:
            if resp_path.exists():
                try:
                    with open(resp_path, encoding="utf-8") as f:
                        response = json.load(f)
                except (json.JSONDecodeError, PermissionError, OSError) as exc:
                    # File still being written, or Windows file-lock race
                    # (errno 13 when the writer process still holds the
                    # handle). Keep polling — the writer will release it.
                    logger.debug(
                        "[LOOPBACK] resp_%s read retry: %s",
                        req_id, type(exc).__name__,
                    )
                    await asyncio.sleep(POLL_INTERVAL_SEC)
                    continue

                # Move both files to done/ for audit trail. On Windows the
                # rename can also race with antivirus handles — retry a few
                # times before giving up (archival is best-effort).
                for rename_attempt in range(5):
                    try:
                        if req_path.exists():
                            req_path.rename(DONE_DIR / req_path.name)
                        if resp_path.exists():
                            resp_path.rename(DONE_DIR / resp_path.name)
                        break
                    except (PermissionError, OSError) as exc:
                        if rename_attempt == 4:
                            logger.warning(
                                "[LOOPBACK] Could not archive %s after retries: %s",
                                req_id, exc,
                            )
                        else:
                            await asyncio.sleep(0.2)

                content = response.get("content", "")
                reasoning = response.get("reasoning", "") or ""
                input_tokens = response.get("input_tokens", max(1, len(prompt) // 4))
                output_tokens = response.get("output_tokens", max(1, len(content) // 4))
                duration_ms = (time.time() - start_ts) * 1000

                # Record in usage tracker
                self.usage.record(
                    call_type=call_type,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    duration_ms=duration_ms,
                    api_cost=0.0,  # operator is free
                    # FX-11 (I-ready-017 P2b): free=True ledgers cost 0 instead of a phantom
                    # paid-rate token estimate, and (with no _add_run_cost) keeps ledger==run-total.
                    free=True,
                )

                logger.info(
                    "[LOOPBACK] RESOLVED req_%s in %.1fs (content=%dc, reasoning=%dc)",
                    req_id, duration_ms / 1000, len(content), len(reasoning),
                )

                return LLMResponse(
                    content=content,
                    reasoning=reasoning,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    model=self.model,
                    duration_ms=duration_ms,
                    raw_response={"loopback": True, "request_id": req_id},
                )

            await asyncio.sleep(POLL_INTERVAL_SEC)

        raise TimeoutError(
            f"[LOOPBACK] No resp_{req_id}.json after {timeout_sec:.0f}s "
            f"(call_type={call_type})"
        )
