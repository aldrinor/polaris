"""Token-limit resolver (B10 governance — fixes the judge HTTP-400 token-starvation).

PROBLEM (operator-locked 2026-06-14, B10 lane):
    A role/judge call sets ``max_tokens`` to a large generous budget (correct per
    §9.1.8 "go max"), but a model's context window is ``prompt_tokens + max_tokens``.
    When ``prompt_tokens + max_tokens`` exceeds the serving provider's context
    window (or its per-request completion cap), OpenRouter returns HTTP-400
    ("max_tokens ... exceeds context length"). That 400 is exactly what HELD the
    A1/A2 qwen-judge report — a generous cap that should have been free insurance
    instead aborted the run.

THE FIX (a CEILING, never a target):
    ``allowed_max_tokens = min(provider_completion_cap,
                               context_length - prompt_tokens - safety_margin)``
    so ``max_tokens`` NEVER consumes the whole context window. This is a
    clamp-DOWN-only ceiling applied as the FINAL mutation of ``body["max_tokens"]``
    in ``openrouter_client._call_impl`` (after the §9.1.8 reasoning-first floor/cap
    chain). Reasoning EFFORT stays MAX (§9.1.8) — this only bounds the *completion
    token allotment* so the request is well-formed.

DESIGN INVARIANTS (so the off/offline/generator paths stay byte-identical):
    1. PASS-THROUGH when metadata is unavailable. If we cannot resolve a model's
       limits (offline, model absent from the /models table, fetch disabled), the
       requested ``max_tokens`` is returned UNCHANGED. The generator's 384000
       budget on a validated full-cap provider therefore never clamps.
    2. CLAMP-DOWN ONLY. ``resolved <= requested`` always; we never RAISE a budget
       (raising could re-introduce a different provider's 404/400).
    3. FAIL-LOUD, never silent-starve (LAW II / §9.1.8). When the prompt genuinely
       does not fit (the prompt alone, plus the safety margin, overruns the context
       window so no positive completion budget is well-formed), we RAISE
       ``PromptTooLargeError`` and LOUD-log — a tiny max_tokens could not make an
       over-window prompt well-formed (the request would still 400), so we surface
       the real cause deterministically rather than fire a doomed request or
       silently starve. We do NOT re-apply the reasoning-first floor after a clamp
       (that would re-create the 400 this module exists to prevent).
    4. OFFLINE-SAFE + CACHED. The /api/v1/models table is fetched once, lazily,
       behind a TTL cache, via a separately-monkeypatchable fetch hook so tests
       INJECT metadata and never touch the network. prompt_tokens is a cheap
       char/4 estimate (no heavy tokenizer — §8.4).
    5. ENV-GOVERNED (LAW VI). A kill-switch (``PG_TOKEN_LIMIT_RESOLVER``, default
       ON) and the safety margin (``PG_TOKEN_LIMIT_SAFETY_MARGIN``) are env knobs.

This module is import-safe: it performs NO network I/O at import time.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.request
from typing import Optional

logger = logging.getLogger("polaris.llm.token_limit_resolver")


class PromptTooLargeError(ValueError):
    """The prompt alone (plus the safety margin) overruns the model's context window.

    Raised by compute_allowed_max_tokens when no positive completion budget can
    make the request well-formed. This is a deterministic, LOUD prompt-too-large
    failure (LAW II / §9.1.8 never-starve) — clamping max_tokens to a tiny value
    would NOT help (the prompt still exceeds context → the request still 400s), so
    we surface the real cause instead of firing a doomed request or silently
    starving. The caller decides how to degrade (e.g. an honest aborted section).
    """

# ---------------------------------------------------------------------------
# Env-governed knobs (LAW VI)
# ---------------------------------------------------------------------------

# Master kill-switch. Default ON. When "0", compute_allowed_max_tokens is a
# byte-identical pass-through (returns the requested value unchanged) — the
# rollback / regression switch the diff-gate can verify.
_ENABLED_ENV = "PG_TOKEN_LIMIT_RESOLVER"

# Safety margin (tokens) reserved below the context window so prompt + completion
# + provider framing overhead never tips into a 400. Generous default; env-tunable.
_SAFETY_MARGIN_ENV = "PG_TOKEN_LIMIT_SAFETY_MARGIN"
_DEFAULT_SAFETY_MARGIN = 2048

# /api/v1/models table cache TTL (seconds). The table is large and changes rarely.
_MODELS_TTL_ENV = "PG_TOKEN_LIMIT_MODELS_TTL_SECONDS"
_DEFAULT_MODELS_TTL = 3600

# Whether the resolver may fetch the live /api/v1/models table at all. Default ON;
# set "0" in fully-offline runs to rely solely on the static fallback table.
_ALLOW_FETCH_ENV = "PG_TOKEN_LIMIT_ALLOW_FETCH"

_MODELS_URL = os.getenv(
    "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
).rstrip("/") + "/models"


def _resolver_enabled() -> bool:
    return os.getenv(_ENABLED_ENV, "1") == "1"


def _safety_margin() -> int:
    try:
        return max(0, int(os.getenv(_SAFETY_MARGIN_ENV, str(_DEFAULT_SAFETY_MARGIN))))
    except ValueError:
        return _DEFAULT_SAFETY_MARGIN


# ---------------------------------------------------------------------------
# Static fallback limits (offline-safe). Conservative, verified figures for the
# locked-stack roles so the resolver still bounds a request when the live table
# is unreachable. A model ABSENT from both the live table AND this map resolves
# to None -> PASS-THROUGH (the requested value is honored unchanged).
#
# These are APPROXIMATE offline-fallback figures (NOT read from /api/v1/models in
# this session — do not treat them as authoritative; the LIVE table is the source
# of truth per CLAUDE.md §9.1.8 "read the API, don't guess"). They are chosen
# LOWER-bound-safe: a real provider with a bigger window only means we under-clamp
# slightly (still well-formed), never over-clamp. When the live table is reachable
# it overrides these entirely.
#
# CAVEAT (advisor B10): the per-model completion cap stored here / read from the
# live table is OpenRouter's ``top_provider.max_completion_tokens`` — a
# popularity-ranked field, NOT necessarily the GENUINELY-SERVED provider's cap.
# The spec's "overlay the serving provider cap" is therefore only partially met:
# the caller compensates for the one case where it matters (the provider-pinned
# reasoning-first generator family) via ``apply_completion_cap=False``. Resolving
# the true served-provider cap per /models/<id>/endpoints is a residual refinement.
# ---------------------------------------------------------------------------

# model_slug -> (context_length, provider_completion_cap_or_None)
#
# Codex B10 iter-1 P1-2: the GENERATOR is DELIBERATELY ABSENT from this static
# table. The generator runs on the validated full-cap fp8 chain at the §9.1.8
# 384000 budget; a conservative static context here would clamp that 384000 DOWN
# offline (a #1253 regression). Absent -> resolve_model_limits returns None ->
# PASS-THROUGH (byte-identical), which is exactly right for the generator. The
# static fallback covers ONLY the verifier/judge roles whose smaller windows are
# the genuine binding constraint (the qwen-judge 400 this module fixes). When the
# live /models table IS reachable it supplies the generator's true (large) limits,
# which also never clamp the 384000 request.
_STATIC_MODEL_LIMITS: dict[str, tuple[int, Optional[int]]] = {
    # Mirror / evaluator / side-judges.
    "z-ai/glm-5.1":               (200000, 131072),
    # Sentinel.
    "minimax/minimax-m2":         (204800, 131072),
    # Judge — the qwen-400 victim. A2/A3 RC2 (iarch007): the prior offline fallback was the
    # MIS-STATED (131072 ctx, 65536 cap), which over-clamped the judge to 65536 offline and did
    # NOT match the REAL serving window. The role-transport judge provider chain (wandb 262144,
    # io-net 262140) serves a 262144 context window with a ~262144 completion cap, so the offline
    # fallback is the REAL window (262144 ctx, 262144 cap). The clamp then reconciles a generous
    # max_tokens DOWN against the true window (ctx - prompt - margin) — the actual qwen-judge
    # HTTP-400 fix — instead of mis-clamping to a stale 65536. The LIVE /models table still
    # overrides this when reachable. (Retained: the canonical-pinned lock's sovereign Judge is
    # still qwen, pending an operator-signed reconciliation — see I-judge-kimi.)
    "qwen/qwen3.6-35b-a3b":       (262144, 262144),
    # Judge (ACTIVE benchmark, I-judge-kimi 2026-06-29): moonshotai/kimi-k2.6. Live /models +
    # /endpoints 2026-06-29: context_length 262144, top_provider.max_completion_tokens 262144. The
    # offline fallback mirrors the live values so an offline clamp reconciles a generous max_tokens
    # DOWN against the true 262144 window (ctx - prompt - margin), never a stale figure. The LIVE
    # /models table overrides this when reachable.
    "moonshotai/kimi-k2.6":       (262144, 262144),
}


# ---------------------------------------------------------------------------
# Live /api/v1/models table — lazily fetched, TTL-cached, monkeypatchable.
# ---------------------------------------------------------------------------

# Cache: model_slug -> (context_length, provider_completion_cap_or_None)
_models_cache: Optional[dict[str, tuple[int, Optional[int]]]] = None
_models_cache_at: float = 0.0


def _fetch_models_table() -> Optional[list[dict]]:
    """Fetch the raw OpenRouter /api/v1/models ``data`` list.

    Returns the list of model dicts, or None on any failure (offline, non-200,
    malformed). Tests monkeypatch THIS function to inject metadata without
    touching the network. NEVER raises — a fetch failure must degrade to
    pass-through, not abort the LLM call.
    """
    if os.getenv(_ALLOW_FETCH_ENV, "1") != "1":
        return None
    try:
        req = urllib.request.Request(
            _MODELS_URL,
            headers={"User-Agent": "polaris-token-limit-resolver"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:  # nosec B310 (https slug)
            if getattr(resp, "status", 200) != 200:
                return None
            payload = json.loads(resp.read().decode("utf-8"))
        data = payload.get("data")
        if isinstance(data, list):
            return data
        return None
    except Exception as exc:  # noqa: BLE001 — fetch must never abort the call
        logger.warning(
            "[token-limit-resolver] /models fetch failed (%s); "
            "falling back to static limits / pass-through",
            type(exc).__name__,
        )
        return None


def _parse_models_table(data: list[dict]) -> dict[str, tuple[int, Optional[int]]]:
    """Reduce the raw /models ``data`` list to {slug: (context_length, completion_cap)}."""
    out: dict[str, tuple[int, Optional[int]]] = {}
    for entry in data:
        try:
            slug = entry.get("id")
            if not slug:
                continue
            ctx = entry.get("context_length")
            top = entry.get("top_provider") or {}
            cap = top.get("max_completion_tokens")
            ctx_int = int(ctx) if ctx is not None else None
            cap_int = int(cap) if cap is not None else None
            if ctx_int is None and cap_int is None:
                continue
            # If context is unknown but cap is known, treat cap as the bound;
            # store a large context so the cap is what binds.
            out[slug] = (ctx_int if ctx_int is not None else 10 ** 9, cap_int)
        except (TypeError, ValueError):
            continue
    return out


def _get_models_cache() -> dict[str, tuple[int, Optional[int]]]:
    """Return the TTL-cached parsed models table (possibly empty)."""
    global _models_cache, _models_cache_at
    ttl = _DEFAULT_MODELS_TTL
    try:
        ttl = int(os.getenv(_MODELS_TTL_ENV, str(_DEFAULT_MODELS_TTL)))
    except ValueError:
        pass
    now = time.monotonic()
    if _models_cache is not None and (now - _models_cache_at) < ttl:
        return _models_cache
    raw = _fetch_models_table()
    parsed = _parse_models_table(raw) if raw else {}
    _models_cache = parsed
    _models_cache_at = now
    return parsed


def reset_cache() -> None:
    """Clear the models cache (test hook)."""
    global _models_cache, _models_cache_at
    _models_cache = None
    _models_cache_at = 0.0


def resolve_model_limits(model: str) -> Optional[tuple[int, Optional[int]]]:
    """Return (context_length, provider_completion_cap_or_None) for ``model``.

    Resolution order: live /models table -> static fallback -> None.
    None means "unknown" -> the caller must PASS THROUGH the requested budget.
    """
    if not model:
        return None
    table = _get_models_cache()
    if model in table:
        return table[model]
    if model in _STATIC_MODEL_LIMITS:
        return _STATIC_MODEL_LIMITS[model]
    return None


def estimate_prompt_tokens(messages: list[dict]) -> int:
    """Cheap char/4 prompt-token estimate (no heavy tokenizer — §8.4).

    Deliberately conservative-high: counts role + content chars so we slightly
    OVER-estimate the prompt, which makes the ceiling slightly SMALLER — the safe
    direction (a 400 is worse than a marginally shorter completion).
    """
    total_chars = 0
    for msg in messages or []:
        content = msg.get("content")
        if isinstance(content, str):
            total_chars += len(content)
        elif content is not None:
            total_chars += len(str(content))
        # small fixed overhead per message for role/framing tokens
        total_chars += 8
    return (total_chars // 4) + 1


def compute_allowed_max_tokens(
    model: str,
    prompt_tokens: int,
    requested_max_tokens: int,
    apply_completion_cap: bool = True,
) -> int:
    """Clamp ``requested_max_tokens`` so prompt + completion fits the context window.

    Returns ``min(requested_max_tokens, provider_completion_cap,
                  context_length - prompt_tokens - safety_margin)``.

    ``apply_completion_cap`` (default True): when False, the ``top_provider``
    completion-cap candidate is IGNORED and only the ``context_length`` bound
    applies. The caller sets this False for the PROVIDER-PINNED generator family
    (``_REASONING_FIRST_MODELS``): #1253 pins that family to full-cap providers
    (Novita/WandB >= 384k) and EXCLUDES DeepInfra, but OpenRouter's
    ``top_provider.max_completion_tokens`` is a popularity-ranked field that may
    report DeepInfra's 16384 — applying it would clamp a 32k-64k section request
    back down to 16384, re-introducing the exact #1253 starvation. The judge/
    verifier roles are NOT reasoning-first, so their completion-cap clamp (the
    actual HTTP-400 fix) stays intact (Codex/advisor B10 online-path finding).

    CLAMP-DOWN-ONLY + PASS-THROUGH semantics:
      - resolver disabled OR model limits unknown  -> return requested unchanged.
      - the computed ceiling >= requested          -> return requested unchanged
        (the generator's full-cap budget never clamps).
      - the computed ceiling <  requested          -> return the ceiling, LOUD-log.
      - the computed ceiling <= 0 (prompt alone overruns the window) -> RAISE
        PromptTooLargeError. A tiny max_tokens could NOT make an over-window prompt
        well-formed (the request would still 400), so we surface the real cause
        loudly and deterministically rather than firing a doomed request or
        silently starving (Codex B10 iter-1 P1-3; LAW II / §9.1.8 never-starve).

    Reasoning EFFORT is untouched (§9.1.8) — this only bounds completion tokens.
    """
    if not _resolver_enabled():
        return requested_max_tokens
    if requested_max_tokens is None or requested_max_tokens <= 0:
        return requested_max_tokens

    limits = resolve_model_limits(model)
    if limits is None:
        # Unknown model -> PASS THROUGH (byte-identical to pre-resolver behavior).
        return requested_max_tokens

    context_length, completion_cap = limits
    margin = _safety_margin()

    ceiling_candidates: list[int] = []
    if context_length is not None:
        ceiling_candidates.append(int(context_length) - int(prompt_tokens) - margin)
    if completion_cap is not None and apply_completion_cap:
        ceiling_candidates.append(int(completion_cap))

    if not ceiling_candidates:
        return requested_max_tokens

    ceiling = min(ceiling_candidates)

    if ceiling >= requested_max_tokens:
        # Request already fits -> no clamp. Generator full-cap path lands here.
        return requested_max_tokens

    if ceiling <= 0:
        # The prompt alone (plus margin) overruns the window. Clamping max_tokens to
        # a tiny value would NOT make the request well-formed — the prompt still
        # exceeds context, so OpenRouter would still 400 (or, if accepted, the model
        # silently starves). RAISE a deterministic, LOUD prompt-too-large failure so
        # the genuine cause surfaces (Codex B10 iter-1 P1-3; LAW II fail-loud).
        msg = (
            f"prompt too large for model={model}: prompt~{prompt_tokens} tokens + "
            f"safety_margin {margin} >= context_length {context_length} "
            f"(completion_cap={completion_cap}); no positive completion budget fits. "
            f"Reduce the prompt or use a larger-context model. "
            f"(requested max_tokens was {requested_max_tokens}.)"
        )
        logger.error("[token-limit-resolver] FAIL-LOUD: %s", msg)
        raise PromptTooLargeError(msg)

    # Genuine clamp-down: the generous request would overrun the window.
    logger.warning(
        "[token-limit-resolver] clamping max_tokens %d -> %d for model=%s "
        "(context_length=%s, completion_cap=%s, prompt~%d tokens, margin=%d). "
        "Reasoning effort unchanged; this prevents the HTTP-400 context overrun "
        "(the qwen-judge 400 that held the report).",
        requested_max_tokens, ceiling, model, context_length, completion_cap,
        prompt_tokens, margin,
    )
    return ceiling


def finalize_body(
    body: dict,
    model: str,
    prompt_tokens: int,
    apply_completion_cap: bool = True,
) -> dict:
    """A2/RC2 SHARED CHOKEPOINT: reconcile ``body['max_tokens']`` against the real provider
    context window as the FINAL mutation before a body is POSTed.

    This is the single, role-agnostic call BOTH ``openrouter_client._call_impl`` AND the
    ``openrouter_role_transport`` verifier body-builder route through, so a generous max_tokens
    (set per §9.1.8 "go max") that — added to a large prompt — would overrun the serving
    context window is clamped DOWN here to ``min(provider_completion_cap, context_length -
    prompt_tokens - safety_margin)``. Without this, OpenRouter returns HTTP-400 ("max_tokens
    exceeds context length") — exactly the qwen-judge 400 that HELD the A1/A2 report.

    Contract:
      * mutates ``body['max_tokens']`` IN PLACE (clamp-DOWN only) and returns the same ``body``;
      * PASS-THROUGH (no mutation) when the resolver is disabled, the model is unknown / offline,
        the budget already fits, or ``body`` carries no positive ``max_tokens`` — so every
        flag-OFF / generator-full-cap path stays byte-identical;
      * RAISES ``PromptTooLargeError`` (LAW II fail-loud) when the prompt alone overruns the
        window — a tiny max_tokens could not make the request well-formed, so the real cause is
        surfaced deterministically rather than firing a doomed request or silently starving.

    Reasoning EFFORT is untouched (§9.1.8 stays MAX) — this only bounds the COMPLETION-token
    allotment so the request is well-formed. ``apply_completion_cap=False`` is set by the caller
    for the provider-pinned reasoning-first generator family (so OpenRouter's popularity-ranked
    ``top_provider.max_completion_tokens`` cannot clamp a section request back down — see
    ``compute_allowed_max_tokens``).
    """
    if not isinstance(body, dict):
        return body
    requested = body.get("max_tokens")
    if not isinstance(requested, int) or requested <= 0:
        return body
    allowed = compute_allowed_max_tokens(
        model, prompt_tokens, requested, apply_completion_cap=apply_completion_cap
    )
    if allowed != requested:
        body["max_tokens"] = allowed
    return body
