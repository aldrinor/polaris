"""I-cred-002 (Phase 2, L1 / §9.1) — adaptive LLM credibility skill (reliability × relevance).

ONE generic, domain-agnostic credibility skill. Per research question it scores EACH candidate
source on RELIABILITY × RELEVANCE with a written, inspectable rationale, consuming POLARIS's
already-computed deterministic authority signals (``authority_score`` / ``source_class`` /
``corroboration_count`` / ``authority_confidence`` / ``signal_scores`` / ``junk_class`` /
``predatory_oa``) as its PRIORS. There are NO fixed domain rubrics: the detected ``domain`` is a
single HINT field the judge reasons over, never a branch that swaps rubrics — so this scales to any
field (operator directive 2026-06-08, plan §9.1).

FAITHFULNESS POSTURE (binding):
  * ADVISORY ONLY. This never becomes a faithfulness gate — ``strict_verify``'s six per-sentence
    checks (``generator/provenance_generator.py``) remain the ONLY binding gate. A credibility
    weight/rationale is a side-output to disclose, never a reason to keep or drop a sentence.
  * DEFAULT-OFF byte-identical: ``PG_SWEEP_CREDIBILITY_SKILL`` (no production caller is added here).
  * The LLM call is DEPENDENCY-INJECTED (``judge``); with no judge → no network, no client, no spend
    (mirrors ``retrieval/semantic_conflict_detector``). The production judge is wired by the caller,
    never constructed in this pure library.
  * NO row mutation, NO faithfulness-file import. Pure functions, snake_case, explicit imports.
  * LAW VI: every threshold is an env-overridable named constant (no magic numbers, no hardcoded
    model/endpoint).

ANTI-FABRICATION (the LOW/thin guardrail): for a LOW-confidence or thin-signal source the judge's
reliability is capped at ``clamp01(authority_score) + PG_CREDIBILITY_MAX_UPLIFT`` — the model cannot
invent authority that the deterministic signals do not support. The judge MAY freely DOWN-rate any
source below its prior (a high-authority but irrelevant/weak source can score low); the prior is NOT
a lower bound. The deterministic priors-only judgment is the fallback ONLY on a judge error / no
judge, never a universal floor.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

# ── flag (default OFF — matches supersession.py / claim_graph.py) ─────────────
_FLAG = "PG_SWEEP_CREDIBILITY_SKILL"
_OFF_VALUES = frozenset({"", "0", "false", "off", "no"})

# ── env knobs (LAW VI: named, env-overridable, no magic numbers) ──────────────
_ENV_MAX_UPLIFT = "PG_CREDIBILITY_MAX_UPLIFT"
_ENV_SNIPPET_CHARS = "PG_CREDIBILITY_SNIPPET_CHARS"
_DEFAULT_MAX_UPLIFT = 0.15
_DEFAULT_SNIPPET_CHARS = 1200
# I-arch-002 (#1251): per-source judging concurrency. The judge is a SYNC LLM call (~24s at full
# reasoning); over hundreds of sources SEQUENTIALLY it froze the run. Default 12 parallel workers. 1
# forces the byte-identical sequential path (off-mode / single source / tests).
_ENV_JUDGE_CONCURRENCY = "PG_CREDIBILITY_JUDGE_CONCURRENCY"
_DEFAULT_JUDGE_CONCURRENCY = 12
# I-deepfix-001 (credibility-pass HANG backstop): a HARD wall on the pool-JOIN so a stalled / provider-
# pinned judge worker can NEVER freeze the run. Each worker already carries a ~300s per-call total-
# deadline, but the ``as_completed()`` join had NO outer bound — under a 429 / empty-provider-window storm
# every worker re-enters retry+backoff and the whole pass grinds past the sweep wall (the live faulthandler
# tonight: credibility_skill as_completed blocked, main asyncio loop parked). On the wall we STOP joining,
# fill every un-scored source with its deterministic priors (judge_error=True), and RETURN. Generous
# default so a HEALTHY pass (completes in minutes) NEVER trips it — it only bounds a true multi-hour stall;
# the run slate may lower it to coordinate with PG_CREDIBILITY_PASS_WALL_S. LAW VI: env-driven.
_ENV_JUDGE_POOL_WALL_S = "PG_CREDIBILITY_JUDGE_POOL_WALL_S"
_DEFAULT_JUDGE_POOL_WALL_S = 3600.0

# The deterministic prior-signal names the judge may cite (anti-hallucination: a
# ``signals_cited`` entry that is not one of these AND present on the row is dropped).
_PRIOR_SIGNAL_KEYS = (
    "authority_score",
    "source_class",
    "corroboration_count",
    "authority_confidence",
    "signal_scores",
    "junk_class",
    "predatory_oa",
    "origin_cluster_id",  # Phase-4 independence signal (present once Phase 6 wires P4 -> P2)
)


def credibility_skill_enabled() -> bool:
    """True unless ``PG_SWEEP_CREDIBILITY_SKILL`` is unset/falsey (default OFF => byte-identical).

    Caller kill-switch: no production caller invokes this library while OFF, so the rendered report
    + manifest are unchanged. The pure functions below do NOT read the flag — they are total +
    offline-testable; the caller gates invocation.
    """
    return os.environ.get(_FLAG, "").strip().lower() not in _OFF_VALUES


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "") or default)
    except (TypeError, ValueError):
        return default


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except (TypeError, ValueError):
        return default


def _clamp01(value: Any) -> float | None:
    """Clamp a numeric to [0, 1]. Returns ``None`` for non-numeric / NaN / inf (the caller treats
    that as a judge error — never a NaN weight, never a crash)."""
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(x) or math.isinf(x):
        return None
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x


@dataclass
class CredibilityJudgment:
    """One source's advisory credibility judgment (a side-output, never a verdict input).

    ``reliability_score`` is AFTER the anti-fabrication cap; ``relevance_score`` is the judged
    directness to the question (unknown => 1.0, multiplicative-neutral); ``credibility_weight`` is
    the FIXED product ``clamp01(reliability * relevance)``. ``signals_cited`` is the subset of the
    deterministic prior signals the judge reasoned from. ``judge_error`` is True iff the injected
    judge raised / returned malformed output for THIS source (isolated; priors-only fallback used).
    """

    evidence_id: str
    reliability_score: float
    relevance_score: float
    credibility_weight: float
    rationale: str
    signals_cited: list[str] = field(default_factory=list)
    query_need: str = ""
    judge_error: bool = False


def _present_signals(row: dict[str, Any]) -> list[str]:
    """The deterministic prior signals actually present (non-empty) on this row."""
    return [k for k in _PRIOR_SIGNAL_KEYS if row.get(k) not in (None, "", {}, [])]


def _row_snippet(row: dict[str, Any], max_chars: int) -> str:
    text = str(row.get("direct_quote") or row.get("statement") or row.get("text") or "")
    return text[:max_chars]


def _build_judge_payload(
    research_question: str, row: dict[str, Any], domain: str | None
) -> dict[str, Any]:
    """Pure: assemble the judge payload for ONE source. Does NOT mutate ``row``.

    Carries source identity + bounded descriptors (title / url / snippet — so RELEVANCE is actually
    judgeable) + the deterministic authority priors + the ``domain_hint`` (a single string field,
    NOT a branch / rubric table). The judge sees ONLY this payload.
    """
    snippet_chars = _int_env(_ENV_SNIPPET_CHARS, _DEFAULT_SNIPPET_CHARS)
    return {
        "research_question": research_question,
        "evidence_id": str(row.get("evidence_id", "")),
        "title": str(row.get("title", "") or ""),
        "url": str(row.get("source_url", "") or row.get("url", "") or ""),
        "snippet": _row_snippet(row, snippet_chars),
        "authority_score": row.get("authority_score"),
        "source_class": row.get("source_class"),
        "corroboration_count": row.get("corroboration_count"),
        "authority_confidence": row.get("authority_confidence"),
        "signal_scores": dict(row.get("signal_scores") or {}),
        "junk_class": row.get("junk_class", ""),
        "predatory_oa": row.get("predatory_oa", False),
        "origin_cluster_id": row.get("origin_cluster_id"),  # Phase-4 independence signal (None pre-wiring)
        "domain_hint": domain or "",
    }


def _is_low_or_thin(row: dict[str, Any]) -> bool:
    """A source is LOW/thin (subject to the anti-fabrication cap) when its authority_confidence is
    LOW, or it has no authority_score, or it has no signal_scores."""
    if str(row.get("authority_confidence") or "").strip().upper() == "LOW":
        return True
    if row.get("authority_score") is None:
        return True
    if not (row.get("signal_scores") or {}):
        return True
    return False


def _priors_only_judgment(row: dict[str, Any]) -> CredibilityJudgment:
    """The deterministic fallback (no judge / judge error): reliability from the prior, relevance
    neutral (1.0). Never fabricates relevance it cannot judge."""
    auth = _clamp01(row.get("authority_score"))
    reliability = auth if auth is not None else 0.0
    return CredibilityJudgment(
        evidence_id=str(row.get("evidence_id", "")),
        reliability_score=reliability,
        relevance_score=1.0,
        credibility_weight=reliability,  # == clamp01(reliability * 1.0)
        rationale="no judge wired — deterministic priors only",
        signals_cited=_present_signals(row),
        query_need="",
        judge_error=False,
    )


def _apply_judge(
    research_question: str,
    row: dict[str, Any],
    domain: str | None,
    judge: Callable[[str, dict], dict],
) -> CredibilityJudgment:
    """Run the injected judge for ONE source; fall back to priors on ANY error / malformed output
    (isolated to this row — recall-first, fail-loud-but-bounded)."""
    from src.polaris_graph.llm.openrouter_client import BudgetExceededError
    payload = _build_judge_payload(research_question, row, domain)
    try:
        raw = judge(research_question, payload)
    except BudgetExceededError:
        # Codex #012a iter-3 P1: a budget-cap breach MUST escape this per-row handler to the sweep's
        # budget-abort path — NOT be masked as a per-row judge_error/priors-only fallback.
        raise
    except Exception:
        fallback = _priors_only_judgment(row)
        fallback.judge_error = True
        return fallback
    if not isinstance(raw, dict):
        fallback = _priors_only_judgment(row)
        fallback.judge_error = True
        return fallback

    reliability = _clamp01(raw.get("reliability_score"))
    if reliability is None:  # missing / NaN / inf reliability => judge error for this row
        fallback = _priors_only_judgment(row)
        fallback.judge_error = True
        return fallback
    relevance = _clamp01(raw.get("relevance_score"))
    if relevance is None:  # unknown / malformed relevance => multiplicative-neutral
        relevance = 1.0

    # Anti-fabrication cap: a LOW/thin source's reliability cannot exceed prior + max_uplift.
    if _is_low_or_thin(row):
        auth = _clamp01(row.get("authority_score")) or 0.0
        cap = _clamp01(auth + _float_env(_ENV_MAX_UPLIFT, _DEFAULT_MAX_UPLIFT))
        if cap is not None:
            reliability = min(reliability, cap)

    present = set(_present_signals(row))
    cited = [s for s in (raw.get("signals_cited") or []) if s in present]
    weight = _clamp01(reliability * relevance)
    return CredibilityJudgment(
        evidence_id=str(row.get("evidence_id", "")),
        reliability_score=reliability,
        relevance_score=relevance,
        credibility_weight=weight if weight is not None else 0.0,
        rationale=str(raw.get("rationale", "")),
        signals_cited=cited,
        query_need=str(raw.get("query_need", "")),
        judge_error=False,
    )


def score_source_credibility(
    research_question: str,
    rows: list[dict[str, Any]],
    *,
    domain: str | None = None,
    judge: Optional[Callable[[str, dict], dict]] = None,
) -> list[CredibilityJudgment]:
    """Score each source on reliability × relevance — ADVISORY ONLY, pure, no row mutation.

    With ``judge=None`` returns one priors-only judgment per row (no network, total + offline). With
    an injected ``judge(research_question, payload) -> dict`` runs it PER SOURCE so a judge error is
    isolated to one row. ``domain`` is forwarded only as the ``domain_hint`` payload field — there is
    no domain-keyed branch or rubric table (operator: no fixed rubrics).

    I-arch-002 (#1251): the judge is a SYNCHRONOUS LLM call; over hundreds of sources run SEQUENTIALLY on
    the asyncio MainThread it FROZE the pipeline (py-spy: ssl.recv). With ``PG_CREDIBILITY_JUDGE_CONCURRENCY``
    > 1 the per-source calls run CONCURRENTLY, mirroring the proven 4-role parallel cost pattern
    (``roles/sweep_integration.py``): each source runs in its OWN ``contextvars.copy_context()`` snapshot
    taken on THIS thread (so it inherits the parent run_id + Path-B capture sink), ``reset_run_cost()``s its
    copy, and returns ``current_run_cost()`` as a per-source delta the parent re-adds to the SINGLE run
    counter and re-checks the cap with DURING-compute enforcement (overspend bounded to ~workers in flight).
    Order is preserved (downstream ``zip(rows, judgments)`` requires it). A worker ``BudgetExceededError`` /
    exception PROPAGATES (fail closed; no silent drop). The caller (``multi_section_generator`` 5383) runs
    this whole pass under ``asyncio.to_thread`` so the blocking pool join never sits on the event loop.
    """
    rows = rows or []
    if judge is None:
        return [_priors_only_judgment(row) for row in rows]
    n = len(rows)
    try:
        workers = max(1, int(
            os.environ.get(_ENV_JUDGE_CONCURRENCY, _DEFAULT_JUDGE_CONCURRENCY) or _DEFAULT_JUDGE_CONCURRENCY
        ))
    except (TypeError, ValueError):
        workers = _DEFAULT_JUDGE_CONCURRENCY
    # SEQUENTIAL fast path (1 worker or <=1 row): byte-identical to the pre-#1251 listcomp.
    if workers == 1 or n <= 1:
        return [_apply_judge(research_question, row, domain, judge) for row in rows]

    import concurrent.futures
    import contextvars
    from src.polaris_graph.llm.openrouter_client import (
        reset_run_cost, current_run_cost, _add_run_cost, check_run_budget,
        BudgetExceededError,
    )

    def _score_one(
        idx: int, row: dict[str, Any], ctx: contextvars.Context
    ) -> tuple[int, CredibilityJudgment, float]:
        def _run() -> tuple[CredibilityJudgment, float]:
            reset_run_cost()  # isolate THIS source's spend in the copied context (parent re-adds a clean delta)
            judgment = _apply_judge(research_question, row, domain, judge)
            return judgment, current_run_cost()
        result, delta = ctx.run(_run)
        return idx, result, delta

    # I-deepfix-001 (HANG backstop): the pool JOIN wall — see the _DEFAULT_JUDGE_POOL_WALL_S note above.
    pool_wall = _float_env(_ENV_JUDGE_POOL_WALL_S, _DEFAULT_JUDGE_POOL_WALL_S)

    results: list[Optional[CredibilityJudgment]] = [None] * n
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=workers)
    timed_out = False
    try:
        futures = [
            pool.submit(_score_one, i, row, contextvars.copy_context())
            for i, row in enumerate(rows)
        ]
        try:
            # HARD wall on the join: a stalled worker can never freeze the run. as_completed raises
            # concurrent.futures.TimeoutError when pool_wall elapses before every worker joins.
            for future in concurrent.futures.as_completed(futures, timeout=pool_wall):
                idx, judgment, delta = future.result()  # re-raises BudgetExceededError / worker exc (fail closed)
                results[idx] = judgment
                _add_run_cost(delta)            # thread the per-source spend into the single run counter
                check_run_budget(0)             # raises BudgetExceededError -> bounded overspend (~workers in flight)
        except concurrent.futures.TimeoutError:
            # The wall fired before every worker joined. Drain any future that DID finish (so a real
            # verdict or a real BudgetExceededError is never lost); the rest are filled with priors below.
            timed_out = True
            for future, idx in ((f, i) for i, f in enumerate(futures)):
                if results[idx] is not None or not future.done():
                    continue
                try:
                    _d_idx, judgment, delta = future.result()
                except BudgetExceededError:
                    raise  # a real cap breach MUST still abort the sweep, even on the wall path
                except Exception:  # noqa: BLE001 — a genuinely-failed worker degrades to priors below
                    continue
                results[idx] = judgment
                _add_run_cost(delta)
                # Codex diff-gate iter1 P0: the wall-drain path MUST enforce the aggregate budget just
                # like the healthy join (which does _add_run_cost THEN check_run_budget(0)). Without this
                # a burst of drained futures could push the run past PG_MAX_COST_PER_RUN without ever
                # raising BudgetExceededError. It is OUTSIDE the per-future try above, so the breach
                # propagates to the outer BaseException handler -> non-blocking shutdown + re-raise
                # (fail-closed cap abort), never swallowed by the drain's `except Exception: continue`.
                check_run_budget(0)
    except BaseException:
        pool.shutdown(wait=False, cancel_futures=True)
        raise
    else:
        # Timed-out: don't block on the still-running stalled workers (wait=False) and cancel the queued
        # ones; the healthy path joins normally (wait=True).
        pool.shutdown(wait=not timed_out, cancel_futures=timed_out)

    if timed_out:
        stalled = [i for i, j in enumerate(results) if j is None]
        import logging as _logging  # noqa: PLC0415
        _logging.getLogger(__name__).warning(
            "[credibility] judge pool wall-deadline (PG_CREDIBILITY_JUDGE_POOL_WALL_S=%.0fs) fired with "
            "%d/%d source(s) still unscored; filling them with DETERMINISTIC priors (judge_error=True -> "
            "credibility_pass LABELS them credibility_unscored) and returning — the run NEVER hangs. The "
            "advisory pass degrades; strict_verify / NLI / 4-role D8 / span-grounding are untouched.",
            pool_wall, len(stalled), n,
        )
        for i in stalled:
            fallback = _priors_only_judgment(rows[i])
            fallback.judge_error = True  # fail-closed: LABEL as credibility_unscored, never a silent drop
            results[i] = fallback

    for i, judgment in enumerate(results):
        if judgment is None:
            raise RuntimeError(
                f"score_source_credibility: source index {i} produced no judgment from the compute pool "
                f"(fail-closed — a dropped future must never reduce silently)."
            )
    return [j for j in results if j is not None]
