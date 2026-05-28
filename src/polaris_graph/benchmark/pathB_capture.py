"""Path-B benchmark run capture (I-safety-002b #925).

Run-scoped capture of every LLM provider completion (all roles) + retrieval-backend
attempts, for the DR head-to-head gate. This module stores PLAIN DICTS; the runner
converts them to ``scripts.dr_benchmark.pathB_run_gate.LLMCall`` when calling
``assert_post_run`` — so this module has ZERO dependency on the gate / scripts package
and the production hot path never imports ``scripts`` from ``src``.

Best-effort + gate-flagged: nothing is captured unless ``register_pathB_capture()`` has
been called for the current run, so when the benchmark gate is OFF the hot path pays only
one contextvar read. Capture NEVER raises (it must not break generation), mirroring the
I-gen-004 reasoning-sink pattern.

Served-identity provenance: ``build_response_metadata`` reads ONLY genuinely-served fields
from the provider response (OpenRouter ``provider`` / served ``model`` / ``system_fingerprint``)
and DROPS missing fields. Request-derived values are never substituted, so a response that
fails to report its served provider/model makes the gate fail loud (in ``assert_post_run``)
rather than silently pass on request-derived data.
"""

from __future__ import annotations

import contextlib
import contextvars
import hashlib
import json
import logging
from typing import Iterator

logger = logging.getLogger(__name__)

# Run-scoped collectors. The contextvars hold REFERENCES to a shared list/set; capture
# mutates them in place so appends inside asyncio child tasks (which copy the context by
# reference) remain visible at the top level where the runner reads them.
_SINK: contextvars.ContextVar[list | None] = contextvars.ContextVar("_PATHB_SINK", default=None)
_ROLE: contextvars.ContextVar[str | None] = contextvars.ContextVar("_PATHB_ROLE", default=None)
_RETRIEVAL: contextvars.ContextVar[set | None] = contextvars.ContextVar("_PATHB_RETRIEVAL", default=None)


def register_pathB_capture() -> None:
    """Begin capture for the current run (fresh collectors). Call once at run start."""
    _SINK.set([])
    _RETRIEVAL.set(set())


def clear_pathB_capture() -> None:
    """End capture (gate off again). Call at run end."""
    _SINK.set(None)
    _ROLE.set(None)
    _RETRIEVAL.set(None)


def is_active() -> bool:
    return _SINK.get() is not None


@contextlib.contextmanager
def llm_role(role: str) -> Iterator[None]:
    """Scope the role tag for LLM calls made inside the block (token set + restore).

    Use a context manager (not a sticky setter) so a role never leaks to later calls."""
    token = _ROLE.set(role)
    try:
        yield
    finally:
        _ROLE.reset(token)


def current_llm_role() -> str | None:
    return _ROLE.get()


def record_retrieval_attempt(backend: str) -> None:
    """Record that a required retrieval backend ('serper'|'semantic_scholar') was attempted."""
    backends = _RETRIEVAL.get()
    if backends is not None:
        backends.add(backend)


def attempted_backends() -> set:
    backends = _RETRIEVAL.get()
    return set(backends) if backends is not None else set()


def collected_calls() -> list[dict]:
    sink = _SINK.get()
    return list(sink) if sink is not None else []


def request_hash(messages) -> str:
    """Stable hash of the prompt messages (presence/integrity, not content storage)."""
    try:
        payload = json.dumps(messages, sort_keys=True, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        payload = repr(messages)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_response_metadata(raw_response: dict | None) -> dict:
    """Served-identity metadata from the provider response — PROVEN-present fields only.

    provider_name <- raw['provider'] (OpenRouter), model <- served raw['model'],
    system_fingerprint <- raw['system_fingerprint']. None/missing fields are DROPPED
    (never request-filled), so an unreported served provider/model surfaces as a gate
    failure rather than a false pass.

    Streaming responses synthesize ``data`` with a request-derived ``model`` fallback, so
    the client stashes the genuinely-SSE-served identity under ``_pathb_served``; when that
    key is present it is the authoritative source (request-derived ``data['model']`` is
    never counted as served)."""
    raw = raw_response or {}
    served = raw.get("_pathb_served")
    src = served if isinstance(served, dict) else raw
    meta = {
        "provider_name": src.get("provider"),
        "model": src.get("model"),
        "system_fingerprint": src.get("system_fingerprint"),
    }
    return {k: v for k, v in meta.items() if v is not None}


def capture_llm_call(*, role: str, messages, raw_response: dict | None) -> None:
    """Best-effort: append one captured provider completion. Never raises; no-op when off."""
    sink = _SINK.get()
    if sink is None:
        return
    try:
        sink.append(
            {
                "call_id": f"{role}-{len(sink)}",
                "role": role,
                "prompt_messages_present": bool(messages),
                "request_hash": request_hash(messages),
                "response_metadata": build_response_metadata(raw_response),
            }
        )
    except Exception as exc:  # noqa: BLE001 — capture must never break generation
        logger.warning("[pathB] capture_llm_call failed (%s) — call not recorded", exc)
