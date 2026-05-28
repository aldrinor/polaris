"""
OpenRouter LLM Client for polaris graph.

Single gateway via OpenRouter. Default model = OPENROUTER_DEFAULT_MODEL
(default deepseek/deepseek-v4-pro per I-cd-009 / GH#624 Carney demo lock).
Two call modes:
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
# I-safety-002b (#925): Path-B benchmark gate capture (stdlib-only, no circular import;
# all calls are gate-flagged via is_active() so the hot path pays one contextvar read).
from src.polaris_graph.benchmark import pathB_capture as _pathb_capture

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
OPENROUTER_MODEL = os.getenv("OPENROUTER_DEFAULT_MODEL", "deepseek/deepseek-v4-pro")
OPENROUTER_BUDGET_USD = float(os.getenv("OPENROUTER_BUDGET_USD", "50.0"))

# R-2 (readiness gate): hard per-run cost cap — a RUNAWAY-LOOP GUARD,
# not an economic limit. Measured by cumulative cost across ALL
# OpenRouterClient instances within a single run.
#
# I-gen-003 (2026-05-14): raised the default from $0.10 to $10.00.
# The $0.10 default was tuned for the V3.2-Exp generator
# ($0.005-$0.01/run). DeepSeek V4 Pro is reasoning-first — it emits
# ~3x the tokens (huge reasoning traces: ~5000 reasoning tokens/call
# observed) and the I-gen-003 CoT-recovery regen loop adds up to 3
# extra section calls. Under the stale $0.10 cap a normal V4 Pro run
# trips BudgetExceededError before it can finish — i.e. the guard
# false-fires on the new generator's NORMAL cost profile. $10.00
# matches the honest_sweep_job_runner.py default and still catches a genuine
# infinite loop / recursive-outline runaway. Override per-run via the
# PG_MAX_COST_PER_RUN env var if a tighter ceiling is wanted.
PG_MAX_COST_PER_RUN = float(os.getenv("PG_MAX_COST_PER_RUN", "10.00"))

# BUG-B-201 fix (pass 2 remediation): per-task ambient state via
# contextvars so concurrent async run_one_query() calls don't stomp
# each other's run_id + cost accumulator.
#
# Pre-fix (commit f632ee5), `_CURRENT_RUN_ID` and `_RUN_COST_USD` were
# module-level globals. Pass 2 showed that under `asyncio.gather`,
# a later run_one_query overwrote the earlier run's ambient id before
# downstream OpenRouterClient() construction — tagging the first run's
# LLM calls with the second run's id.
#
# Post-fix: ContextVar scopes per asyncio Task. Each task sees its own
# run_id + cost without threading explicit kwargs through the call graph.
# Synchronous / serial callers still work because ContextVar defaults
# to the module-default if no set_* has run in the current task.
import contextvars

_RUN_COST_LOCK = __import__("threading").Lock()
_RUN_COST_CTX: contextvars.ContextVar[float] = contextvars.ContextVar(
    "_RUN_COST_USD", default=0.0,
)
_CURRENT_RUN_ID_CTX: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "_CURRENT_RUN_ID", default=None,
)


def set_current_run_id(run_id: str | None) -> None:
    """Set the ambient run-id for the current async task. Each
    asyncio.Task has its own context, so concurrent runs don't stomp.
    """
    _CURRENT_RUN_ID_CTX.set(run_id)


def current_run_id() -> str | None:
    return _CURRENT_RUN_ID_CTX.get()


# I-gen-004 (#496): run-scoped reasoning-trace capture. The generator wires a
# ReasoningTraceCollector as the sink (set_reasoning_sink); the client records
# each raw completed provider response to it (_capture_reasoning_trace) BEFORE
# any caller-level promotion / </think> extraction / retry / truncation raise.
# Layering: the sink is duck-typed (the client never imports the generator).
# The per-call generator context (section, call_type, attempt_n, ...) is
# supplied separately by the caller via set_reasoning_call_context; capture is
# a no-op unless BOTH a sink and a call-context are present, which scopes it
# to generator calls (evaluator / retrieval LLM calls set no context).
_REASONING_SINK_CTX: contextvars.ContextVar[object | None] = contextvars.ContextVar(
    "_REASONING_SINK", default=None,
)
_REASONING_CALL_CTX: contextvars.ContextVar[dict | None] = contextvars.ContextVar(
    "_REASONING_CALL_CTX", default=None,
)


def set_reasoning_sink(sink: object | None) -> None:
    """Register (or clear, with None) the run-scoped reasoning-trace sink — a
    duck-typed object exposing ``record(**fields) -> call_id``. Set at run
    start, cleared at run end."""
    _REASONING_SINK_CTX.set(sink)


def current_reasoning_sink() -> object | None:
    return _REASONING_SINK_CTX.get()


def set_reasoning_call_context(**ctx: object) -> None:
    """Set the per-call generator context (section, call_type, attempt_n,
    parent_call_id, regen_reason) for the next captured provider response.
    Generator call sites set this immediately before each LLM call; passing
    no kwargs clears it (a non-generator call records nothing)."""
    _REASONING_CALL_CTX.set(dict(ctx) if ctx else None)


def current_reasoning_call_context() -> dict | None:
    return _REASONING_CALL_CTX.get()


def _capture_reasoning_trace(
    result: "LLMResponse",
    content: str,
    reasoning: Optional[str],
    *,
    status: str = "ok",
) -> None:
    """Record one raw completed provider response to the run-scoped
    reasoning-trace sink, if one is registered AND the caller set a generator
    call-context. ``content_source`` is recorded as ``direct`` here;
    generate()/reason() finalize it (promoted_from_reasoning /
    extracted_from_reasoning) via the sink's update() using
    ``result.trace_call_id``. Best-effort observability — a sink failure is
    logged loud but never breaks the LLM call (reasoning trace is process
    transparency, not the generation path)."""
    sink = current_reasoning_sink()
    ctx = current_reasoning_call_context()
    if sink is None or not ctx:
        return
    try:
        result.trace_call_id = sink.record(
            section=str(ctx.get("section", "")),
            call_type=str(ctx.get("call_type", "section")),
            model=result.model or "",
            status=status,
            content_source="direct",
            parent_call_id=ctx.get("parent_call_id"),
            regen_reason=ctx.get("regen_reason"),
            attempt_n=int(ctx.get("attempt_n", 1) or 1),
            reasoning_text=reasoning or "",
            content_text=content or "",
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            reasoning_tokens=result.reasoning_tokens,
        )
    except Exception as exc:  # noqa: BLE001 — observability must not break generation
        logger.warning(
            "[polaris graph] I-gen-004: reasoning-trace capture failed "
            "(%s: %s) — generation continues, this record dropped",
            type(exc).__name__,
            exc,
        )


def _finalize_reasoning_trace(call_id: Optional[str], **patch: object) -> None:
    """I-gen-004 (#496): patch an already-captured reasoning-trace record once
    the caller (generate()/reason()) has resolved promotion / `</think>`
    extraction / retry / truncation — e.g. content_source=promoted_from_reasoning
    or status=retry|truncated|error. No-op if no sink or no call_id.
    Best-effort: a sink failure is logged, never raised."""
    if not call_id:
        return
    sink = current_reasoning_sink()
    if sink is None:
        return
    try:
        sink.update(call_id, **patch)
    except Exception as exc:  # noqa: BLE001 — observability must not break generation
        logger.warning(
            "[polaris graph] I-gen-004: reasoning-trace finalize failed "
            "(%s: %s) — generation continues",
            type(exc).__name__,
            exc,
        )


class BudgetExceededError(RuntimeError):
    """Raised when PG_MAX_COST_PER_RUN is breached mid-run."""


class ReasoningFirstTruncationError(RuntimeError):
    """I-bug-089 / I-gen-003: a reasoning-first model (DeepSeek V4 Pro/
    Flash) ran out of token budget while still planning — content is
    empty and reasoning_content has no provenance markers and ends
    mid-sentence. Typed (not bare RuntimeError) so the multi_section
    generator's _call_section can catch *only* this case and let the
    bounded regen loop retry with a larger budget, while every other
    RuntimeError still propagates as a real fault."""


def reset_run_cost() -> None:
    """Reset the current task's run-cost accumulator to 0. Call at the
    start of a run. Uses ContextVar so concurrent async tasks each get
    their own zero-start."""
    _RUN_COST_CTX.set(0.0)


def current_run_cost() -> float:
    """Return the cumulative cost of the current run (USD), scoped to
    the current asyncio task via ContextVar."""
    return _RUN_COST_CTX.get()


def _add_run_cost(delta: float) -> None:
    # BUG-B-201: ContextVar-scoped cost accumulator. Each async task has
    # its own run-cost; concurrent gather() of run_one_query() no longer
    # stomps each other.
    _RUN_COST_CTX.set(_RUN_COST_CTX.get() + float(delta))


# Codex round 1 B-4: conservative per-model prices used when OpenRouter
# omits usage.cost. Prices are $/M tokens and represent the UPPER END of
# published rates for each provider family (if a cheaper provider is used
# we overcharge the run cost, which is the safe direction for a budget
# guard). When the model is unknown we use OPUS-tier defaults.
_PRICE_TABLE_USD_PER_M: dict[str, tuple[float, float]] = {
    # model prefix  :  (input $/M, output $/M)
    # IMPORTANT: longer/more-specific prefixes first. Dict insertion order
    # = iteration order = first-match-wins per _impute_cost_from_tokens.
    # I-cd-010 / GH#625: qwen/qwen3-8b + z-ai/glm-5.1 entries are
    # INTENTIONAL pricing-table coverage for env-overridden models (set
    # PG_GENERATOR_MODEL / OPENROUTER_DEFAULT_MODEL); not the active
    # Carney demo lock defaults.
    "deepseek/deepseek-v4-pro":   (0.435, 0.87),
    "deepseek/deepseek-v4-flash": (0.14, 0.28),
    "deepseek/":       (0.27, 0.38),
    "qwen/qwen3-8b":   (0.05, 0.40),
    "qwen/qwen3-32b":  (0.10, 0.60),
    "qwen/":           (0.10, 0.60),
    "z-ai/glm-5.1":    (0.60, 2.20),
    "z-ai/":           (0.60, 2.20),
    "meta-llama/":     (0.30, 0.90),
    "google/gemma-4-31b-it": (0.13, 0.38),
    "google/gemma":    (0.05, 0.30),
    "google/gemini":   (1.25, 5.00),
    "mistralai/":      (0.30, 0.90),
    "moonshotai/":     (0.60, 2.50),
    "openai/":         (3.00, 10.00),
    "anthropic/":      (3.00, 15.00),
}

_DEFAULT_PRICE_PER_M = (3.00, 15.00)  # Opus-tier worst-case


def _impute_cost_from_tokens(
    model: str,
    input_tokens: int,
    output_tokens: int,
    reasoning_tokens: int,
) -> float:
    """Estimate $/call from token counts + published prices. Reasoning
    tokens bill at the output rate (matches OpenAI / Anthropic practice).
    Used by the budget guard when OpenRouter omits usage.cost.

    Defensive: token counts are clamped to >=0. A corrupted API response
    returning negative tokens must NOT produce a negative cost that
    would silently shrink the accumulated run budget and let a runaway
    loop keep calling past PG_MAX_COST_PER_RUN.
    """
    # Clamp negative token counts — these can only come from a
    # corrupted API response. A negative cost here would be silently
    # absorbed by _add_run_cost and weaken the budget guard.
    input_tokens = max(0, int(input_tokens))
    output_tokens = max(0, int(output_tokens))
    reasoning_tokens = max(0, int(reasoning_tokens))
    if input_tokens == 0 and output_tokens == 0 and reasoning_tokens == 0:
        return 0.0
    model_lower = (model or "").lower()
    input_rate, output_rate = _DEFAULT_PRICE_PER_M
    for prefix, (in_r, out_r) in _PRICE_TABLE_USD_PER_M.items():
        if model_lower.startswith(prefix):
            input_rate, output_rate = in_r, out_r
            break
    return (
        (input_tokens / 1_000_000.0) * input_rate
        + ((output_tokens + reasoning_tokens) / 1_000_000.0) * output_rate
    )


def check_run_budget(anticipated_additional: float = 0.0) -> None:
    """Raise BudgetExceededError if the next call would exceed the cap.

    anticipated_additional: optional estimate of the upcoming call cost
    (used only for guard-before-call — the actual cost is recorded by
    `_add_run_cost()` after the call returns).
    """
    current = current_run_cost()
    projected = current + max(0.0, float(anticipated_additional))
    if projected > PG_MAX_COST_PER_RUN:
        raise BudgetExceededError(
            f"PG_MAX_COST_PER_RUN={PG_MAX_COST_PER_RUN:.4f} exceeded: "
            f"current=${current:.4f} + anticipated=${anticipated_additional:.4f} "
            f"= ${projected:.4f}. Set PG_MAX_COST_PER_RUN higher or call "
            f"reset_run_cost() between runs."
        )

# HONEST-REBUILD Phase 1c (plan: C:/Users/msn/.claude/plans/lovely-finding-firefly.md)
# ─────────────────────────────────────────────────────────────────────────────
# Two-family architecture: generator and evaluator MUST be from different
# training lineages to avoid self-bias (Play Favorites arXiv:2508.06709 Aug
# 2025; DeepHalluBench arXiv:2601.22984 Jan 2026).
#
# Defaults pin the VERIFIED-ON-GROUNDED-FACTUALITY pair (user decision
# 2026-04-17 after multi-axis reasoning; generator default upgraded to V4
# Pro on 2026-05-08 per I-bug-086 once V4 hit OpenRouter):
#
#   Generator: deepseek/deepseek-v4-pro   (role-fit: long-form grounded
#                                          synthesis)
#       - 1.6T total / 49B active params, hybrid CSA+HCA attention
#       - 1.05M context, MIT license, $0.435 in / $0.87 out per M tokens
#         on OpenRouter
#       - Released 2026-04-24 (current frontier open-weight)
#       - Sovereign V4 hosting on OVH H200 still pending I-phase0-006
#         hardware decision; OpenRouter is the bridge until then
#       - Predecessor V3.2 retained on OpenRouter (`deepseek/deepseek-v3.2-exp`),
#         Vectara HHEM 5.3% — switch back via PG_GENERATOR_MODEL env var
#         if V4 Pro produces regressions on the BEAT-BOTH benchmark
#
#   Evaluator: google/gemma-4-31b-it     (role-fit: per-claim faithfulness
#                                         judgment, runs 100s of times per
#                                         report)
#       - 30.7B dense parameters (not MoE — every parameter active per
#         token; preferred for narrow judgment tasks where consistency
#         matters more than raw capability)
#       - 256K context, Apache 2.0 license
#       - Released 2026-04-02 (current frontier open-weight from Google)
#       - Different family from generator (Google vs DeepSeek) —
#         check_family_segregation() allows this pair
#       - Aligns with documented Phase-4 plan (Gemma 4 31B was always the
#         eventual evaluator target; OpenRouter is the bridge until OVH
#         hardware lands per I-phase0-009)
#       - Predecessor Qwen3-8B retained on OpenRouter (`qwen/qwen3-8b`,
#         Vectara HHEM 4.8%) — switch back via PG_EVALUATOR_MODEL env var
#         if Gemma 4 produces regressions on internal benchmarks
#
# WHY NOT GLM 5.1 + Qwen 3.5 Plus (rejected after multi-axis analysis
# 2026-04-17):
#   - GLM-5.1's strengths (SWE-Bench Pro 58.4, BrowseComp 68.0, AIME 92.7)
#     are for agentic coding tasks, NOT our role. Grounded-generation
#     faithfulness is the core requirement; GLM-5 ancestor ranks 57/77 on
#     Vectara at 10.1%. GLM-5.1 has no Vectara data but inherits the signal.
#   - Qwen 3.5 Plus has zero Vectara data. Sibling Qwen 3.5 397B has 88%
#     fabrication rate on AA-Omniscience. Unverified factuality is exactly
#     the "no honest metric" pattern the rebuild is trying to escape.
#   - Cost: GLM 5.1 at $2.15/M blended is ~5x the combined DeepSeek +
#     Qwen3-8B cost per call.
#
# Research trail:
#   loopback/audit/_open_source_models_2026.md
#   loopback/audit/_open_source_models_2026_april_followup.md
#
# Escape hatch for fine-tunes / licensed redistributions: PG_*_FAMILY_OVERRIDE.
# Family derivation uses OpenRouter publisher-slug prefix.
PG_GENERATOR_MODEL = os.getenv(
    "PG_GENERATOR_MODEL",
    # DeepSeek V4 Pro is THE generator (operator directive 2026-05-14).
    #
    # History: I-bug-091 (2026-05-09) reverted the default to V3.2-Exp
    # because V4 Pro is reasoning-first — it emits CoT-style planning and,
    # critically, exhausted max_tokens mid-planning, tripping the I-bug-089
    # SF-15 fail-loud and crashing the pipeline before any section was
    # written.
    #
    # I-gen-003 (2026-05-14) fixes the crash:
    #   - ReasoningFirstTruncationError (typed) + a 20000-token
    #     PG_REASONING_FIRST_MIN_MAX_TOKENS floor give V4 Pro room to both
    #     finish reasoning AND emit the cited paragraph — smoke #3 ran all
    #     6 sections with zero truncation crash.
    #   - _call_section catches that exception and returns an empty draft
    #     so a truncation degrades to an honest abort_no_verified_sections
    #     rather than a hard error_unexpected.
    # V4 Pro's report-layer citation tightness vs the evaluator gate is
    # tracked separately (I-gen-003 PT11 / normalization work). V3.2-Exp
    # is obsolete — NOT a fallback.
    "deepseek/deepseek-v4-pro",
)
PG_EVALUATOR_MODEL = os.getenv("PG_EVALUATOR_MODEL", "google/gemma-4-31b-it")

# Explicit family overrides for the cases where the model-name prefix is
# not the true family (fine-tunes, licensed redistributions, etc.).
PG_GENERATOR_FAMILY_OVERRIDE = os.getenv("PG_GENERATOR_FAMILY_OVERRIDE", "")
PG_EVALUATOR_FAMILY_OVERRIDE = os.getenv("PG_EVALUATOR_FAMILY_OVERRIDE", "")

# Known family prefixes. The first prefix matched wins. Distinct families
# per the loopback/audit/_open_source_models_2026.md family-distance table.
_FAMILY_PREFIXES: dict[str, tuple[str, ...]] = {
    "deepseek": ("deepseek/", "deepseek-ai/"),
    "qwen":     ("qwen/", "qwen-ai/", "alibaba/"),
    "glm":      ("z-ai/", "zhipuai/", "thudm/"),
    "llama":    ("meta-llama/", "meta/", "llama/"),
    "gemma":    ("google/gemma", "google/gemma-", "gemma/"),
    "mistral":  ("mistralai/", "mistral/"),
    "kimi":     ("moonshotai/", "moonshot/", "kimi/"),
    # Closed frontier families included for completeness (off-MVP, but if
    # ever allowed via a closed-source fallback they get their own family).
    "openai":   ("openai/", "gpt-"),
    "anthropic":("anthropic/", "claude-"),
    "google-closed": ("google/gemini",),
}


def family_from_model(model_name: str, override: str = "") -> str:
    """Derive the training-lineage family from an OpenRouter model name.

    Returns the family label ("deepseek", "qwen", "glm", "llama", "gemma",
    "mistral", "kimi", "openai", "anthropic", "google-closed") or
    "unknown" if no prefix matches.

    A non-empty `override` bypasses prefix matching. Use it when a model
    has been renamed or when a fine-tune needs its base-family tag.
    """
    if override:
        return override.strip().lower()
    if not model_name:
        return "unknown"
    m = model_name.strip().lower()
    for family, prefixes in _FAMILY_PREFIXES.items():
        for prefix in prefixes:
            if m.startswith(prefix.lower()):
                return family
    return "unknown"


def check_family_segregation(
    generator_model: str | None = None,
    evaluator_model: str | None = None,
    generator_override: str | None = None,
    evaluator_override: str | None = None,
) -> tuple[str, str]:
    """Fail fast if generator and evaluator are in the same family.

    Returns (generator_family, evaluator_family) on success.
    Raises RuntimeError if same family or if either is "unknown" without
    an explicit override (so misconfiguration is visible at init time).

    Defaults pull from the module-level env-var settings.
    """
    gen_model = generator_model or PG_GENERATOR_MODEL
    eval_model = evaluator_model or PG_EVALUATOR_MODEL
    gen_override = generator_override if generator_override is not None else PG_GENERATOR_FAMILY_OVERRIDE
    eval_override = evaluator_override if evaluator_override is not None else PG_EVALUATOR_FAMILY_OVERRIDE

    gen_family = family_from_model(gen_model, gen_override)
    eval_family = family_from_model(eval_model, eval_override)

    if gen_family == "unknown" and not gen_override:
        raise RuntimeError(
            f"HONEST-REBUILD Phase 1c: generator model '{gen_model}' does not "
            f"match any known family prefix. Set PG_GENERATOR_FAMILY_OVERRIDE "
            f"to the training-lineage family (e.g. 'deepseek', 'qwen') so "
            f"family segregation can be checked. Family-distance from the "
            f"evaluator is the primary mitigation for evaluator-generator "
            f"self-bias (Play Favorites arXiv:2508.06709, DeepHalluBench "
            f"arXiv:2601.22984)."
        )
    if eval_family == "unknown" and not eval_override:
        raise RuntimeError(
            f"HONEST-REBUILD Phase 1c: evaluator model '{eval_model}' does "
            f"not match any known family prefix. Set PG_EVALUATOR_FAMILY_OVERRIDE."
        )
    if gen_family == eval_family:
        raise RuntimeError(
            f"HONEST-REBUILD Phase 1c: generator and evaluator are in the "
            f"same training-lineage family ('{gen_family}'). This defeats "
            f"the purpose of two-family architecture — same-family judges "
            f"share blind spots and RLHF biases. Pick models from different "
            f"families, or document the choice with explicit PG_*_FAMILY_OVERRIDE "
            f"values to demonstrate you know the trade-off. Recommended pair: "
            f"deepseek/deepseek-v4-pro (generator) + google/gemma-4-31b-it "
            f"(evaluator) per loopback/audit/_open_source_models_2026.md."
        )
    return (gen_family, eval_family)

# FIX-GLM5: Models that always route output to reasoning_content.
# These need reasoning_enabled=True for all calls, and generate() must
# use reasoning as content directly (no </think> tag extraction).
#
# FIX-GLM51: z-ai/glm-5.1 added 2026-04-12. Smoke test confirmed it
# routes generate() and reason() output into reasoning_content (content
# empty). The previous COT-1/COT-2 fallback recovery logic worked but
# wasted tokens via retries. Adding to this set makes the handling
# direct instead of fallback-based.
#
# I-cd-010 / GH#625: this is INTENTIONAL reasoning-first registry for
# response-shape-centric recovery (per memory architectural_response_
# shape_centric_recovery). Do not remove the GLM-5.1 entry on the basis
# of "stale model ref" — it's needed for the reasoning-first branch.
_ALWAYS_REASON_MODELS = frozenset({
    "z-ai/glm-5", "z-ai/glm-5-turbo", "z-ai/glm-4.7", "z-ai/glm-5.1",
})

# I-bug-089 (2026-05-09): models that route to reasoning_content even when
# the caller passes reasoning_enabled=False. Used by _call() to cap
# reasoning.max_tokens at 40% of budget so 60% remains for content,
# preventing token-starvation that leaves content="" + reasoning=full
# planning prelude. Distinct from _ALWAYS_REASON_MODELS (which is the
# legacy recovery-side switch); this is the request-side switch.
_REASONING_FIRST_MODELS = frozenset({
    *_ALWAYS_REASON_MODELS,
    "deepseek/deepseek-v4-pro",
    "deepseek/deepseek-v4-flash",
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
    # I-gen-004 (#496): id of the reasoning-trace record this response was
    # captured into (set by _capture_reasoning_trace when a run-scoped sink
    # is registered). None when no sink / not a traced generator call.
    trace_call_id: Optional[str] = None


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

    All calls go through OPENROUTER_DEFAULT_MODEL via OpenRouter (default
    deepseek/deepseek-v4-pro per I-cd-009 / GH#624 Carney demo lock).
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
        # BUG-N-301 fix (deep-dive R11): fall back to the ambient run_id
        # set by the orchestrator via set_current_run_id(). This threads
        # session_id into cost ledger entries without requiring every
        # call site (multi_section_generator, live_deepseek, judge,
        # external evaluator) to pass it explicitly.
        effective_session_id = session_id or _CURRENT_RUN_ID_CTX.get() or ""
        self.usage = UsageTracker(
            budget_usd=budget_usd or OPENROUTER_BUDGET_USD,
            session_id=effective_session_id,
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
    ) -> tuple[str, str, dict, dict]:
        """Accumulate SSE chunks from a streaming response.

        Returns (content, reasoning_content, usage_data, served_identity), where
        served_identity holds the genuinely-served provider/model/system_fingerprint
        captured from the SSE chunks (I-safety-002b #925).

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
        # I-safety-002b (#925): served-identity from SSE chunks (provider/model/
        # system_fingerprint). OpenRouter reports these per-chunk; keep the last
        # non-null. Used to populate the synthesized streaming `data` with the
        # genuinely-served identity (not the request-derived model) for the gate.
        served: dict = {}

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

            # I-safety-002b (#925): capture genuinely-served identity (last non-null wins).
            # Gate-flagged: skip entirely when the Path-B capture is inactive (off-mode pays
            # one contextvar read, not three dict lookups per chunk).
            if _pathb_capture.is_active():
                for _sk in ("provider", "model", "system_fingerprint"):
                    _sv = chunk.get(_sk)
                    if _sv:
                        served[_sk] = _sv

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

        return content_text, reasoning_text, usage_data, served

    async def _read_stream(
        self, body: dict, timeout: float,
    ) -> tuple[str, str, dict, dict]:
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
                content, reasoning, usage, served = await self._accumulate_sse(response)

                # Defense: if SSE produced nothing, the stream may have
                # been malformed. Log for diagnostics.
                if not content and not reasoning and not usage:
                    logger.warning(
                        "[polaris graph] SSE stream produced no content, "
                        "reasoning, or usage. Content-Type: %s",
                        content_type,
                    )

                return content, reasoning, usage, served

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
                return "", "", {}, {}

            # I-safety-002b (#925): served identity from the real JSON body.
            _served = {
                _k: data.get(_k)
                for _k in ("provider", "model", "system_fingerprint")
                if data.get(_k)
            }
            choices = data.get("choices", [])
            if not choices:
                return "", "", data.get("usage", {}), _served

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
                _served,
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
        reasoning_max_tokens: Optional[int] = None,
        reasoning_exclude: Optional[bool] = None,
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
                reasoning_max_tokens, reasoning_exclude,
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
        reasoning_max_tokens: Optional[int] = None,
        reasoning_exclude: Optional[bool] = None,
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

        # R-2: check the shared per-run budget cap. Each client
        # contributes to _RUN_COST_USD after each call; here we abort
        # early if the cap is already breached rather than fire another
        # call and discover the overage after the fact.
        check_run_budget(anticipated_additional=0.0)

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

        # GLM-5 TWO-POOL ARCHITECTURE:
        # Pool 1 (reasoning field): reasoning tokens → logged for monitoring
        # Pool 2 (content field): actual output → used for report
        # GLM-5 returns BOTH when max_tokens is sufficient (tested:
        #   max_tokens=2000 → 1313 chars content + 5868 chars reasoning).
        # CRITICAL: Never merge reasoning into content. Never disable reasoning.
        # Reasoning drives analytical quality (SO WHAT, contradictions, GRADE).
        if self.model in _ALWAYS_REASON_MODELS:
            # W1.2 merge-not-replace: defaults fill only keys the caller didn't set.
            # Caller-passed reasoning_max_tokens / reasoning_exclude now reach the API.
            reasoning_dict: dict[str, Any] = {"exclude": False}
            if reasoning_exclude is not None:
                reasoning_dict["exclude"] = reasoning_exclude
            if reasoning_max_tokens is not None:
                # OpenRouter constraint: effort and max_tokens are mutually exclusive.
                reasoning_dict["max_tokens"] = reasoning_max_tokens
            else:
                reasoning_dict["effort"] = reasoning_effort or "high"
            body["reasoning"] = reasoning_dict
            body["temperature"] = 1.0  # GLM-5 docs: temp 1.0 for thinking
            # Enforce minimum max_tokens so reasoning doesn't starve content.
            # At max_tokens<2000, GLM-5 spends entire budget on reasoning,
            # leaving content empty. Tested: 2000 → 1313 chars content.
            _min_tokens = int(os.getenv("PG_GLM5_MIN_MAX_TOKENS", "4096"))
            if body.get("max_tokens", 0) < _min_tokens:
                body["max_tokens"] = _min_tokens
        elif reasoning_enabled:
            reasoning_dict = {"effort": reasoning_effort, "enabled": True}
            if reasoning_max_tokens is not None:
                reasoning_dict.pop("effort", None)
                reasoning_dict["max_tokens"] = reasoning_max_tokens
            if reasoning_exclude is not None:
                reasoning_dict["exclude"] = reasoning_exclude
            body["reasoning"] = reasoning_dict
        elif self.model in _REASONING_FIRST_MODELS:
            # I-bug-089: caller wants reasoning_enabled=False but this model
            # (e.g. DeepSeek V4 Pro/Flash) routes to reasoning_content anyway.
            # Cap reasoning at 40% of max_tokens so 60% is reserved for content,
            # preventing token-starvation where the planning eats the budget
            # and the model never gets to write the answer. Caller-passed
            # reasoning_max_tokens / reasoning_exclude still take precedence.
            reasoning_dict = {"exclude": False}
            if reasoning_exclude is not None:
                reasoning_dict["exclude"] = reasoning_exclude
            if reasoning_max_tokens is not None:
                reasoning_dict["max_tokens"] = reasoning_max_tokens
            else:
                reasoning_dict["max_tokens"] = max(int(max_tokens * 0.4), 100)
            body["reasoning"] = reasoning_dict
            # I-bug-090 / I-gen-003: OpenRouter does NOT enforce
            # reasoning.max_tokens for V4 Pro on the provider side — the
            # model reasons until it hits the OVERALL max_tokens ceiling.
            # The I-bug-090 estimate of "~2500 reasoning tokens" was wrong:
            # the I-gen-003 V4 Pro smoke (2026-05-14) showed V4 Pro emit
            # 21284 chars (~5300+ tokens) of reasoning and STILL truncate
            # mid-sentence at the 6000-token ceiling — it never reached the
            # content. Floor must give V4 Pro room to FINISH planning AND
            # write the cited paragraph. 20000 floor → ~5-8k reasoning +
            # ~12-15k content headroom. Env-tunable. Smoke #3 (2026-05-14)
            # confirmed: at 20000, V4 Pro completed all 6 sections with
            # zero ReasoningFirstTruncationError.
            _min_tokens = int(os.getenv("PG_REASONING_FIRST_MIN_MAX_TOKENS", "20000"))
            if body.get("max_tokens", 0) < _min_tokens:
                body["max_tokens"] = _min_tokens

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
                    content_text, reasoning_text, stream_usage, stream_served = await asyncio.wait_for(
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
                    # I-safety-002b (#925): stash the genuinely-SSE-served identity so the
                    # Path-B gate sees the SERVED provider/model, not the request-derived
                    # `self.model` fallback above. Gate-flagged: nothing added when off.
                    if _pathb_capture.is_active():
                        data["_pathb_served"] = stream_served
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

                # I-bug-940: OpenRouter returns 404 transiently when the routed provider
                # is briefly upstream-throttled or the edge routing has a momentary miss.
                # Out-of-band probes confirmed the same call succeeds 8s later. Retry
                # with backoff like 429 — a real "model not found" reproduces across all
                # MAX_RETRIES+1 attempts (so a genuine config error still terminates).
                if status == 404 and attempt < MAX_RETRIES:
                    wait = RETRY_BACKOFF_BASE ** (attempt + 1)
                    logger.warning(
                        "[polaris graph] I-bug-940: 404 (transient provider routing), "
                        "waiting %.1fs (attempt %d/%d)",
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

        # FIX-C2: Extract API-reported cost for accurate billing.
        # Codex round 1 B-4: OpenRouter omits `usage.cost` for some models,
        # which let the run budget record $0.00 even when tokens were
        # consumed. Now: if cost is missing AND tokens were consumed,
        # impute a conservative upper bound from published per-model rates.
        api_cost = usage_data.get("cost", None)
        if api_cost is None or api_cost == 0:
            # Use per-model price table; defaults reflect observed upper-
            # bound ($10/M output for opus-tier models) so the guard is
            # always conservative. Token totals may be 0 if the response
            # carried no usage block at all.
            imputed = _impute_cost_from_tokens(
                self.model, input_tokens, output_tokens, reasoning_tokens,
            )
            if api_cost is None and imputed > 0:
                logger.warning(
                    "[polaris graph] B-4: OpenRouter omitted usage.cost "
                    "for model=%r; imputed cost=$%.6f from tokens "
                    "(in=%d out=%d reasoning=%d). Budget guard uses the "
                    "imputed value so a missing cost field cannot bypass "
                    "PG_MAX_COST_PER_RUN.",
                    self.model, imputed, input_tokens, output_tokens,
                    reasoning_tokens,
                )
            api_cost = max(api_cost or 0.0, imputed)

        # Track usage
        self.usage.record(
            call_type=call_type,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            reasoning_tokens=reasoning_tokens,
            duration_ms=duration_ms,
            api_cost=api_cost,
        )
        # R-2: contribute to the shared run-cost counter AFTER the call.
        # Checking the cap BEFORE is done by callers via check_run_budget().
        _add_run_cost(api_cost)

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

        # I-gen-004 (#496): capture the raw completed provider response to the
        # run-scoped reasoning-trace sink BEFORE any caller-level promotion /
        # </think> extraction / retry / ReasoningFirstTruncationError raise.
        _capture_reasoning_trace(result, content, reasoning)

        # I-safety-002b (#925): Path-B benchmark gate capture — one LLMCall per provider
        # completion (this is the unified completion boundary for stream + non-stream +
        # retries + reason/generate/generate_structured). Best-effort + gate-flagged:
        # is_active() is a cheap contextvar read and is False outside a benchmark run.
        # PR-2: capture ONLY explicitly-tagged calls (Codex APPROVE Option B). Auxiliary
        # calls (scope LLM, inductor) without a role tag are NOT captured / NOT gated —
        # the gate polices the REPORT generator + REPORT evaluators only, which is what
        # the benchmark needs and is robust to auxiliary-model config changes.
        if _pathb_capture.is_active():
            _role = _pathb_capture.current_llm_role()
            if _role is not None:
                _pathb_capture.capture_llm_call(
                    role=_role,
                    messages=sanitized_messages,
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
        reasoning_max_tokens: Optional[int] = None,
        reasoning_exclude: Optional[bool] = None,
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
            reasoning_max_tokens=reasoning_max_tokens,
            reasoning_exclude=reasoning_exclude,
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
                # FIX-071B + FIX-076: Strip CoT prefix for always-reason models.
                # GLM-5 always starts with "1. **Analyze the Request:**" planning
                # that contains research terms, fooling the keyword-based strip.
                # Use explicit CoT openers first, then fall back to keyword search.
                _reason_content = result.reasoning
                if self.model in _ALWAYS_REASON_MODELS:
                    import re as _re

                    # FIX-076: First try explicit CoT opener patterns
                    _explicit_cot = _re.search(
                        r"\n(?=(?:##\s|[A-Z][a-z]{3,}[^*\n]{10,}(?:\[\d+\]|\[CITE:)))",
                        _reason_content,
                    )
                    # Also check: if content starts with numbered planning ("1. **Analyze")
                    # find the actual output after all planning steps
                    if _reason_content.lstrip().startswith(("1.", "1 ")) and "**Analyze" in _reason_content[:200]:
                        # Find end of numbered planning — look for prose paragraph
                        # that doesn't start with a number+period
                        _plan_end = _re.search(
                            r"\n\n(?=[A-Z][a-z]{3,}[^*\n]{20,})",
                            _reason_content[200:],  # skip first 200 chars of planning
                        )
                        if _plan_end:
                            _pos = 200 + _plan_end.start()
                            if _pos > 100:
                                _reason_content = _reason_content[_pos:].lstrip()
                                logger.info(
                                    "[polaris graph] FIX-076: Stripped %d chars CoT "
                                    "planning from reason() output",
                                    _pos,
                                )
                    elif _explicit_cot and _explicit_cot.start() > 100:
                        _reason_content = _reason_content[_explicit_cot.start():].lstrip()
                        logger.info(
                            "[polaris graph] FIX-071B: Stripped %d chars CoT from "
                            "reason() free-form output",
                            _explicit_cot.start(),
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
        reasoning_max_tokens: Optional[int] = None,
        reasoning_exclude: Optional[bool] = None,
    ) -> LLMResponse:
        """Prose/output call — see :meth:`_generate_impl` for the full body.

        I-gen-561 (#561) P2-1: a thin wrapper that clears the per-call
        reasoning-trace generator context in a ``finally``, so each
        ``generate()`` invocation's call-context is scoped to exactly that
        call. Without this, a later non-generator ``generate()`` in the same
        task (e.g. ``live_judge.judge_report()``) would be captured under a
        stale generator context and mislabeled.
        """
        try:
            return await self._generate_impl(
                prompt,
                system=system,
                max_tokens=max_tokens,
                temperature=temperature,
                timeout=timeout,
                reasoning_max_tokens=reasoning_max_tokens,
                reasoning_exclude=reasoning_exclude,
            )
        finally:
            # Clear the per-call generator context (no kwargs -> None). The
            # internal COT-2 retry leg runs inside _generate_impl, so it still
            # sees the context; this clears only after the whole call.
            set_reasoning_call_context()

    async def _generate_impl(
        self,
        prompt: str,
        system: str = "",
        max_tokens: int = 4096,
        temperature: float = 0.7,
        timeout: Optional[float] = None,
        reasoning_max_tokens: Optional[int] = None,
        reasoning_exclude: Optional[bool] = None,
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
            reasoning_max_tokens=reasoning_max_tokens,
            reasoning_exclude=reasoning_exclude,
        )
        # I-gen-004 (#496): trace-record id of the raw provider response, for
        # finalizing content_source / status after promotion / retry below.
        _primary_trace_id = result.trace_call_id

        # TWO-POOL: Content field = output. Reasoning field = logged separately.
        # For GLM-5, both pools are populated when max_tokens is sufficient.
        # Log reasoning for monitoring but NEVER merge into content.
        if result.reasoning and self.model in _ALWAYS_REASON_MODELS:
            logger.info(
                "[polaris graph] POOL-1: Reasoning logged (%d chars) for generate()",
                len(result.reasoning),
            )

        if result.content and result.content.strip():
            return result

        # Fallback: content empty (max_tokens too low or provider issue).
        # Try </think> extraction from reasoning as last resort.
        if result.reasoning:
            extracted = _extract_answer_from_reasoning(result.reasoning)
            if extracted:
                logger.warning(
                    "[polaris graph] POOL-FALLBACK: generate() content empty — "
                    "recovered %d chars from reasoning via </think> split",
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
                _finalize_reasoning_trace(
                    _primary_trace_id,
                    content_source="extracted_from_reasoning",
                    content_text=result.content,
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
                        # Use the end of the "Now let me" line as the start of real content
                        _tb_pos = _thinking_block.end()
                        class _PosHolder:
                            def start(self):
                                return _tb_pos
                        _thinking_block = _PosHolder()

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
                _finalize_reasoning_trace(
                    _primary_trace_id,
                    content_source="promoted_from_reasoning",
                    content_text=result.content,
                )
            elif len(result.reasoning.strip()) >= 100:
                # I-bug-088: response-shape-centric normalization for
                # reasoning-first models (e.g. DeepSeek V4 Pro) that route
                # ALL assistant tokens to reasoning_content, leave content
                # empty, and emit no </think> tag. The prior COT-2 retry
                # cannot recover this — the provider produces the same shape
                # on retry. Use raw reasoning as the answer; raw is preserved
                # in result.reasoning for tracing. Threshold of 100 chars
                # guards against treating a near-empty reasoning blip as a
                # full answer.
                #
                # I-bug-089: detect token-starvation case where the model
                # ran out of budget mid-planning. If reasoning has no
                # provenance markers AND ends mid-sentence, the model
                # never wrote the answer — fail loud so caller can retry
                # with bigger budget instead of promoting planning prelude.
                _reasoning_clean = result.reasoning.rstrip()
                if (
                    "[#ev:" not in result.reasoning
                    and not _reasoning_clean.endswith((".", "!", "?", '"'))
                ):
                    self.usage.total_errors += 1
                    _finalize_reasoning_trace(_primary_trace_id, status="truncated")
                    raise ReasoningFirstTruncationError(
                        f"I-bug-089: reasoning-first model {self.model} "
                        f"truncated mid-planning. content empty, reasoning "
                        f"has {len(result.reasoning)} chars but no [#ev:] "
                        f"markers and ends mid-sentence — increase max_tokens "
                        f"budget. SF-15 fail-loud."
                    )
                logger.warning(
                    "[polaris graph] I-bug-088: generate() content empty, "
                    "reasoning has %d chars and no </think> tag. Model %s is "
                    "reasoning-first — using reasoning as content directly.",
                    len(result.reasoning), self.model,
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
                _finalize_reasoning_trace(
                    _primary_trace_id,
                    content_source="promoted_from_reasoning",
                    content_text=result.content,
                )
            else:
                # Reasoning is too sparse to be a real answer — retry once
                # (provider may re-route on retry).
                logger.warning(
                    "[polaris graph] COT-2: generate() content empty, "
                    "reasoning sparse (%d chars). Retrying once.",
                    len(result.reasoning),
                )
                # I-gen-004: the first attempt is superseded by the retry.
                _finalize_reasoning_trace(_primary_trace_id, status="retry")
                result = await self._call(
                    messages=messages,
                    call_type="generate_retry",
                    reasoning_enabled=False,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=timeout or DEFAULT_TIMEOUT_SECONDS,
                )
                _retry_trace_id = result.trace_call_id
                # I-gen-561 (#561) P2-4: the retry's captured record inherits
                # the caller's attempt-1 call-context — link it to the primary
                # attempt and mark it attempt 2. No-op if no sink/context.
                _finalize_reasoning_trace(
                    _retry_trace_id,
                    parent_call_id=_primary_trace_id,
                    attempt_n=2,
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
                        _finalize_reasoning_trace(
                            _retry_trace_id,
                            content_source="extracted_from_reasoning",
                            content_text=result.content,
                        )
                    elif len(result.reasoning.strip()) >= 100:
                        # I-bug-088: same response-shape-centric recovery on
                        # retry. If retry still produces reasoning-only output
                        # with substance, treat reasoning as the answer.
                        logger.warning(
                            "[polaris graph] I-bug-088: retry still reasoning-"
                            "only (%d chars) — promoting to content.",
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
                        _finalize_reasoning_trace(
                            _retry_trace_id,
                            content_source="promoted_from_reasoning",
                            content_text=result.content,
                        )
                    else:
                        # SF-15: Fail loud after exhausting retries
                        self.usage.total_errors += 1
                        _finalize_reasoning_trace(_retry_trace_id, status="error")
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
        reasoning_max_tokens: Optional[int] = None,
        reasoning_exclude: Optional[bool] = None,
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
        #
        # FIX-GLM5-STRUCTURED (2026-04-12): For models in _ALWAYS_REASON_MODELS,
        # reasoning is forced ON by _call() regardless of this parameter. Without
        # this check, GLM 5.1 receives BOTH response_format=json_schema strict:true
        # AND reasoning=enabled, which causes complex-schema calls (StormOutlinePlan,
        # SourceAnalysisBatch, ReportOutline) to dump 17K+ chars of prose into
        # reasoning_content with content="" (empty). Symptom in PG_TEST_090 trace:
        # "Content empty for structured:StormOutlinePlan, reasoning has 17958 chars".
        # The fix makes generate_structured aware that these models always reason,
        # so it skips response_format and uses prompt-based JSON extraction (which
        # works because the prompt's json_hint instructs JSON-only output).
        response_format = None
        strict_schema_enabled = os.getenv("PG_STRICT_JSON_SCHEMA", "1") == "1"
        _effective_reasoning = reasoning_enabled or (self.model in _ALWAYS_REASON_MODELS)
        if not _effective_reasoning and strict_schema_enabled:
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
        # FIX-GEMMA4: Include expected field names in JSON hint to prevent
        # models from using alternative naming or nested wrappers.
        try:
            _schema_fields = list(schema.model_fields.keys())
            _fields_hint = f" Required top-level keys: {', '.join(_schema_fields)}."
        except Exception:
            _fields_hint = ""
        json_hint = (
            "You MUST respond with valid JSON only. No prose, no markdown, "
            f"no code fences — just the JSON object.{_fields_hint}"
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
            reasoning_max_tokens=reasoning_max_tokens,
            reasoning_exclude=reasoning_exclude,
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
        # FIX-GEMMA4: Flatten nested JSON wrappers. Some models (Gemma 4)
        # wrap the expected schema in an outer object like {"research_plan": {...}}.
        # Unwrap by trying each top-level value as the schema target.
        try:
            _probe = json.loads(cleaned)
            if isinstance(_probe, dict) and len(_probe) == 1:
                _inner = next(iter(_probe.values()))
                if isinstance(_inner, dict):
                    # Try validating the inner dict first
                    try:
                        _inner_json = json.dumps(_inner)
                        schema.model_validate_json(_inner_json)
                        cleaned = _inner_json
                        logger.info(
                            "[polaris graph] FIX-GEMMA4: Unwrapped nested JSON for %s "
                            "(outer key: '%s')",
                            schema.__name__, next(iter(_probe.keys())),
                        )
                    except Exception:
                        pass  # Inner doesn't validate either, keep original
        except (json.JSONDecodeError, Exception):
            pass

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
