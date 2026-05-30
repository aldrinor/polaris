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
# I-meta-002-q1d (#945): per-call retrieval trace (mirror of the generator's reasoning_trace.jsonl for the
# search/fetch half). Holds an ordered list of {kind: query|kept|drop, ...} records for the §-1.1 line-by-
# line audit. PURELY OBSERVATIONAL — populated by best-effort recorders that no-op when not started; the
# §9.1 retrieval/strict_verify chokepoint is never altered. Started fresh PER QUERY by start_retrieval_trace().
_RETRIEVAL_TRACE: contextvars.ContextVar[list | None] = contextvars.ContextVar(
    "_PATHB_RETRIEVAL_TRACE", default=None,
)
# I-bug-946 (#932): per-role resolved provider (e.g. {"generator":"Fireworks","evaluator":"Novita"}).
# Populated by gate_around_question() after preflight resolves each role's actual served provider
# via GET /api/v1/models/<id>/endpoints. openrouter_client and entailment_judge read this to force
# singleton provider routing in their request bodies (otherwise OpenRouter's silent fallback would
# defeat the strict-identity guarantee that smoke #15 caught: evaluator routed to Novita while pin
# expected Fireworks). Per Codex iter-2 P2: ContextVar lives in src (NOT scripts/) so the hot path
# never imports scripts. Codex APPROVE iter 2 on I-bug-946 brief.
_ROLE_PROVIDER: contextvars.ContextVar[dict | None] = contextvars.ContextVar(
    "_PATHB_ROLE_PROVIDER", default=None,
)


def register_pathB_capture() -> None:
    """Begin capture for the current run (fresh collectors). Call once at run start."""
    _SINK.set([])
    _RETRIEVAL.set(set())


def clear_pathB_capture() -> None:
    """End capture (gate off again). Call at run end."""
    _SINK.set(None)
    _ROLE.set(None)
    _RETRIEVAL.set(None)
    _RETRIEVAL_TRACE.set(None)
    _ROLE_PROVIDER.set(None)


def set_role_providers(mapping: dict[str, str]):
    """I-bug-946 (#932): set the resolved per-role provider mapping for the gate run.

    Called by gate_around_question() AFTER preflight() resolves each role's served provider
    via OpenRouter's /api/v1/models/<id>/endpoints. Returns a token; pair with
    reset_role_providers() in try/finally so the mapping never leaks beyond the gate scope.
    """
    return _ROLE_PROVIDER.set(mapping)


def reset_role_providers(token) -> None:
    _ROLE_PROVIDER.reset(token)


def current_role_provider() -> str | None:
    """Return the resolved provider for the CURRENT role (read via _ROLE contextvar).

    Returns None if either the gate is off (mapping is None) or the current role has no
    entry in the mapping. openrouter_client calls this; when None it falls back to its
    current env-driven path (gate-off mode).

    NOTE: entailment_judge must NOT use this — see get_role_provider() below.
    """
    mapping = _ROLE_PROVIDER.get()
    if mapping is None:
        return None
    role = _ROLE.get()
    if role is None:
        return None
    return mapping.get(role)


def get_role_provider(role: str) -> str | None:
    """Explicit-role lookup, NOT keyed off the ambient _ROLE contextvar.

    I-bug-946 (#932) Codex iter-1 diff P1#2: the entailment judge posts the evaluator
    model but is INVOKED from within the generator's _ROLE scope (provenance verification
    fires during section generation). Using current_role_provider() would resolve to the
    generator's provider (Fireworks) for a Gemma post — Fireworks doesn't host Gemma →
    silent re-route. The judge must pass role="evaluator" explicitly.
    """
    mapping = _ROLE_PROVIDER.get()
    if mapping is None:
        return None
    return mapping.get(role)


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


def set_role(role: str):
    """Set the role tag and return a token to restore on. Pair with reset_role(token)
    inside a try/finally — equivalent guarantee to llm_role() ctx-mgr, used where
    re-indenting a large multi-line call block under `with` would be invasive."""
    return _ROLE.set(role)


def reset_role(token) -> None:
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


# ── I-meta-002-q1d (#945): per-call retrieval trace (best-effort, no-op when not started) ──────────
def start_retrieval_trace() -> None:
    """Begin a FRESH retrieval trace for the current query (P2 lifecycle hygiene, Codex brief-gate):
    a new list so a prior query's records can never leak into a later run_dir flush. Call once at the
    top of run_one_query, before retrieval."""
    _RETRIEVAL_TRACE.set([])


def record_retrieval_query(backend: str, query: str, urls: list[str]) -> None:
    """Record one search/fetch backend call: backend, query text, return count, returned URLs."""
    trace = _RETRIEVAL_TRACE.get()
    if trace is not None:
        trace.append({
            "kind": "query", "backend": backend, "query": query,
            "return_count": len(urls), "urls": list(urls),
        })


def record_retrieval_kept(url: str, backend: str) -> None:
    """Record that a fetched source was KEPT into the evidence pool, with its originating backend."""
    trace = _RETRIEVAL_TRACE.get()
    if trace is not None:
        trace.append({"kind": "kept", "url": url, "backend": backend})


def record_retrieval_drop(url: str, reason: str) -> None:
    """Record that a candidate/source was DROPPED, with the reason (content_starved | fetch_failed |
    offtopic | rerank_not_selected | ...)."""
    trace = _RETRIEVAL_TRACE.get()
    if trace is not None:
        trace.append({"kind": "drop", "url": url, "reason": reason})


def retrieval_trace_records() -> list[dict]:
    """Return the current query's retrieval-trace records (empty when not started)."""
    trace = _RETRIEVAL_TRACE.get()
    return list(trace) if trace is not None else []


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
    never counted as served).

    Self-host endpoint (I-meta-002 PR-7/M1): a self-hosted vLLM verifier role (Mirror /
    Sentinel / Judge) carries NO OpenRouter ``provider`` field — its served identity for the
    M4 served==pinned check is the ENDPOINT it was served from. The transport stashes that
    endpoint under ``_pathb_served['endpoint']``; this function surfaces it as an OPTIONAL
    ``endpoint`` key. Backward-compatible: the key is DROPPED when ``_pathb_served`` does not
    carry it (existing OpenRouter 3-key behaviour is unchanged when absent)."""
    raw = raw_response or {}
    served = raw.get("_pathb_served")
    src = served if isinstance(served, dict) else raw
    meta = {
        "provider_name": src.get("provider"),
        "model": src.get("model"),
        "system_fingerprint": src.get("system_fingerprint"),
        "endpoint": src.get("endpoint"),
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
