"""I-cap-002 feature 4/4 (#1060): NLI entailment as an ADDITIVE, advisory benchmark annotation.

strict_verify is regex/numeric — it can pass a qualitative-negation hallucination ("drug X did NOT
reduce mortality") whose numbers/content-words still match the cited span. NLI is the **second validator
path**: for each delivered sentence it scores whether the CITED evidence span entails the sentence; a low
entailment prob is a hallucination the regex missed. This is ADVISORY only — it annotates the manifest, it
never changes ``release_allowed``/``status`` (the 4-role D8 seam remains the single binding gate).

**No silent degrade (LAW II + operator no-downgrade directive):** ``annotate_nli_entailment`` raises
``NliUnavailableError`` when the model/deps cannot load — it NEVER returns an empty "clean" result that
reads as "NLI verified". The caller records ``nli_status:"unavailable"`` LOUDLY in the manifest. (This is
the deliberate difference from ``nli_verifier.verify_evidence_nli``, which returns ``[]`` on a missing model.)

Heavy deps (``torch`` / ``transformers`` / ``minicheck``) are imported LAZILY inside the async function, so
importing this module pulls nothing heavy; offline tests mock the scorer (no torch). The live model runs on
the VM (CLAUDE.md §8.4).
"""

from __future__ import annotations

import os
import re
from typing import Any

from src.polaris_graph.clinical_generator.provenance import strip_tokens

# Codex diff-gate iter-1 P2.1: the benchmark's provenance offsets index into the row's
# ``direct_quote`` / ``statement`` (the field strict_verify validates against), so those MUST be tried
# FIRST — slicing ``full_text`` for a row that carries both would pick the wrong byte range.
_SPAN_TEXT_FIELDS = ("direct_quote", "statement", "full_text", "snippet", "text", "source_text")

# Codex diff-gate iter-1 P2.3: strip_tokens removes only ``[#ev:...]``; a pre-resolve sentence can still
# carry ``[#calc:model:hash:field]`` calc tokens and ``(atom_NNN)`` markers that are cleaned from the
# final delivered prose elsewhere. Strip those too, or they create advisory false NLI disputes.
_RESIDUAL_ARTIFACT_RE = re.compile(r"\[#calc:[^\]]*\]|\(?\batom_\d+\b\)?")

# I-wire-012 (#1326): bounded-parallel entailment scoring for the POST-RELEASE advisory NLI annotation.
# The entailment judge is a SYNCHRONOUS ~6-40s network call; scoring N delivered sentences SEQUENTIALLY
# blew past the ``PG_NLI_ANNOTATION_WALL_S`` (default 420s) daemon wall in run_honest_sweep_r3, so the
# whole advisory annotation was dropped (``nli_status:"skipped_wall_timeout"``, sentences_checked=0). Run
# the per-pair judge calls CONCURRENTLY (bounded) so the annotation COMPLETES within the wall. EVERY pair
# is still scored — NO sampling (§-1.1 bans sample-based audits) — so faithfulness coverage is intact;
# only the wall-clock shrinks. Default 12 matches the proven ``PG_CREDIBILITY_JUDGE_CONCURRENCY`` pool
# (I-arch-002 #1251). 1 forces the byte-identical sequential in-context path (off-mode / single pair / tests).
_ENV_NLI_JUDGE_CONCURRENCY = "PG_NLI_JUDGE_CONCURRENCY"
_DEFAULT_NLI_JUDGE_CONCURRENCY = 12


def _score_pairs_parallel(judge: Any, pairs: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """Score every ``(span ⊨ sentence)`` pair with the entailment judge CONCURRENTLY, order-preserving.

    I-wire-012 (#1326). Mirrors the PROVEN I-arch-002 (#1251) credibility-judge pool
    (``authority/credibility_skill.py``): the judge is a SYNC ~6-40s LLM call, so over N delivered
    sentences run SEQUENTIALLY on one thread it overran the post-release NLI wall and the advisory
    annotation was dropped wholesale. With ``PG_NLI_JUDGE_CONCURRENCY`` > 1 the per-pair calls run on a
    bounded ``ThreadPoolExecutor``; EVERY pair is still scored (no sampling — §-1.1) so coverage is intact,
    only wall-clock shrinks. Returns the per-pair ``(verdict, reason)`` list in INPUT order.

    **Budget (preserves the old SYNC loop's two guarantees: spend counts against PG_MAX_COST_PER_RUN AND
    BudgetExceededError propagates).** Each worker runs in its OWN ``contextvars.copy_context()`` snapshot
    (inherits the parent run_id + Path-B capture sink), ``reset_run_cost()``s that copy, and returns
    ``current_run_cost()`` as its per-pair spend DELTA; the collector threads the delta into the single run
    counter (``_add_run_cost``) and re-checks the cap (``check_run_budget``) as each future completes —
    DURING-compute enforcement, overspend bounded to ~workers in flight. A worker ``BudgetExceededError`` /
    exception PROPAGATES through ``future.result()`` (fail-closed — a dropped future never silently reduces
    the annotation), so Core Invariant §9.1.6 and ``NliUnavailableError`` are unchanged. Because
    ``_add_run_cost`` bumps THIS task's ``_RUN_COST_CTX`` (the one the daemon-wall wrapper's
    ``_annotate_capturing`` reads and reconciles to the parent), the caller needs NO change.

    **Exit-safety — does NOT regress the I-wire-011 daemon wall.** The daemon wall in
    ``run_honest_sweep_r3._nli_annotation_with_wall`` still fires on the main event loop independent of this
    pool, so the primary deadlock fix is untouched. On a wall TIMEOUT the annotation worker is abandoned
    mid-``shutdown(wait=True)`` and this non-daemon pool keeps DRAINING the remaining pairs — BOUNDED by the
    I-wire-008 per-call entailment deadline (``PG_ENTAILMENT_TOTAL_S``); it is one of the "OTHER non-daemon
    lingering pools" the ``PG_TEARDOWN_WALL`` watchdog (now armed on both entrypoints, run_honest_sweep_r3
    module note ~L2504) force-reaps at exit, and the annotation *worker thread* itself stays the unchanged
    daemon. Post-wall drained calls still cost money — bounded and recorded in the process-global cost
    ledger, but NOT abortable (the run already released) — an accepted tradeoff for an advisory last step.
    ``shutdown(wait=False, cancel_futures=True)`` on any exception so a failing batch never blocks.
    """
    try:
        workers = max(1, int(
            os.environ.get(_ENV_NLI_JUDGE_CONCURRENCY, _DEFAULT_NLI_JUDGE_CONCURRENCY)
            or _DEFAULT_NLI_JUDGE_CONCURRENCY
        ))
    except (TypeError, ValueError):
        workers = _DEFAULT_NLI_JUDGE_CONCURRENCY
    n = len(pairs)
    # SEQUENTIAL fast path (1 worker or <=1 pair): byte-identical to the pre-#1326 in-context sync loop,
    # so off-mode / single-pair / cost-stays-in-context semantics are exactly preserved with no thread hop.
    if workers == 1 or n <= 1:
        return [judge.judge(p["sentence"], p["span"]) for p in pairs]

    import concurrent.futures  # noqa: PLC0415 — kept out of the module/off-mode import path
    import contextvars  # noqa: PLC0415
    from src.polaris_graph.llm.openrouter_client import (  # noqa: PLC0415
        _add_run_cost,
        check_run_budget,
        current_run_cost,
        reset_run_cost,
    )

    def _score_one(
        idx: int, pair: dict[str, Any], ctx: "contextvars.Context"
    ) -> tuple[int, tuple[str, str], float]:
        def _run() -> tuple[tuple[str, str], float]:
            reset_run_cost()  # isolate THIS pair's spend in the copied context (parent re-adds the delta)
            out = judge.judge(pair["sentence"], pair["span"])
            return out, current_run_cost()
        out, delta = ctx.run(_run)
        return idx, out, delta

    results: list[tuple[str, str] | None] = [None] * n
    pool = concurrent.futures.ThreadPoolExecutor(
        max_workers=workers, thread_name_prefix="nli_judge",
    )
    try:
        futures = [
            pool.submit(_score_one, i, pair, contextvars.copy_context())
            for i, pair in enumerate(pairs)
        ]
        for future in concurrent.futures.as_completed(futures):
            idx, out, delta = future.result()  # re-raises BudgetExceededError / worker exc (fail closed)
            results[idx] = out
            _add_run_cost(delta)   # thread the per-pair spend into the single run counter
            check_run_budget(0)    # raises BudgetExceededError -> bounded overspend (~workers in flight)
    except BaseException:
        pool.shutdown(wait=False, cancel_futures=True)
        raise
    else:
        pool.shutdown(wait=True)
    for i, out in enumerate(results):
        if out is None:
            raise RuntimeError(
                f"annotate_nli_entailment: pair index {i} produced no verdict from the judge pool "
                f"(fail-closed — a dropped future must never silently reduce the advisory annotation)."
            )
    return results  # type: ignore[return-value]  # all-None replaced above; fail-closed if any remained


class NliUnavailableError(RuntimeError):
    """The NLI model/deps could not be loaded. Raised (never silently swallowed) so the caller can
    surface ``nli_status:"unavailable"`` rather than report a false clean pass."""


def _resolve_span_text(row: dict[str, Any], start: int, end: int) -> str:
    """Slice the cited [start:end] span out of an evidence row's text (get_span_text semantics)."""
    text = ""
    for field in _SPAN_TEXT_FIELDS:
        value = row.get(field)
        if isinstance(value, str) and value:
            text = value
            break
    if not text or start < 0 or end > len(text) or start > end:
        return ""
    return text[start:end]


def build_nli_pairs(
    kept_sentences: list[dict[str, Any]],
    ev_pool: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build ``[{sentence, span, section, evidence_id}]`` NLI pairs from delivered kept sentences.

    Per Codex brief-gate P2: (1) the sentence is CLEANED of ``[#ev:...]`` / atom artifacts via
    ``strip_tokens`` so citation tokens don't create false NLI disputes; (2) ALL cited spans of the
    sentence are concatenated as the premise (not first-token-only), so a sentence grounded by multiple
    spans is not over-disputed. A sentence with no cleanable text or no resolvable span is skipped.

    ``kept_sentences``: ``[{"sentence": str, "tokens": [{"evidence_id","start","end"}], "section": str}]``.
    Pure (no model, no network).
    """
    pairs: list[dict[str, Any]] = []
    for ks in kept_sentences or []:
        raw = ks.get("sentence") or ""
        # P2.1: drop [#ev:...] tokens; P2.3: also drop [#calc:...] + (atom_NNN) residuals; collapse ws.
        claim = _RESIDUAL_ARTIFACT_RE.sub(" ", strip_tokens(raw))
        claim = re.sub(r"\s+", " ", claim).strip()
        if not claim:
            continue
        spans: list[str] = []
        first_ev_id = ""
        for tok in ks.get("tokens", []) or []:
            ev_id = tok.get("evidence_id") or ""
            row = ev_pool.get(ev_id)
            if not isinstance(row, dict):
                continue
            span = _resolve_span_text(row, int(tok.get("start", -1)), int(tok.get("end", -1)))
            if span:
                spans.append(span)
                if not first_ev_id:
                    first_ev_id = ev_id
        premise = " ".join(spans).strip()
        if not premise:
            continue  # no resolvable cited span -> nothing to entail against; skip
        pairs.append({
            "sentence": claim,
            "span": premise,
            "section": ks.get("section", ""),
            "evidence_id": first_ev_id,
        })
    return pairs


async def annotate_nli_entailment(
    pairs: list[dict[str, Any]],
) -> dict[str, Any]:
    """Score each (span ⊨ sentence) pair with the frontier LLM entailment judge; ADVISORY annotation.

    I-cap-003 (#1066): the scoring backend is now the project's LLM entailment judge
    (``src.polaris_graph.llm.entailment_judge``) — a frontier OPEN-weight model (default
    ``google/gemma-4-31b-it``) via OpenRouter, family-segregated from the generator, already used by
    strict_verify. This REPLACES the old flan-t5/minicheck path (an old/weak F1-62.1 encoder that was
    git-only and unavailable on the CPU VM → the previous ``nli_status:unavailable`` bug).

    Each pair yields a verdict ``ENTAILED | NEUTRAL | CONTRADICTED``. ``disputed`` = NEUTRAL ∪
    CONTRADICTED (strict_verify's contract is "no unsupported additions"; the per-sentence ``verdict``
    distinguishes them). Returns ``{nli_status:"ok", judge, model, sentences_checked, entailed_count,
    neutral_count, contradicted_count, disputed_count, disputed:[…], advisory:True}``.

    FAIL-LOUD only on a genuine config error: a missing ``OPENROUTER_API_KEY`` raises
    ``NliUnavailableError`` (surfaced as ``nli_status:"unavailable"``, never a silent pass). I-wire-012
    (#1326): the per-pair judge calls run BOUNDED-PARALLEL via ``_score_pairs_parallel`` (``PG_NLI_JUDGE_
    CONCURRENCY``, default 12) so the post-release annotation finishes inside the daemon wall instead of
    being skipped — every pair is still scored (no sampling). Per-pair cost is reconciled into the run's
    ``_RUN_COST_CTX`` ContextVar (so PG_MAX_COST_PER_RUN stays inclusive) and ``BudgetExceededError`` (raised
    inside ``judge.judge`` / re-checked per completed future) propagates out to abort the run on a cap
    breach. A family-segregation error from ``_get_judge()`` PROPAGATES (not masked as "unavailable").
    """
    if not pairs:                                   # fast path — needs no API key / no judge
        return {
            "nli_status": "ok", "judge": "llm_entailment", "sentences_checked": 0,
            "sentences_scored": 0, "entailed_count": 0, "neutral_count": 0, "contradicted_count": 0,
            "disputed_count": 0, "disputed": [], "judge_error_count": 0, "judge_errors": [],
            "advisory": True,
        }

    # Fail-loud on a genuine config error BEFORE constructing the judge (the judge __init__ raises a
    # RuntimeError for a missing key that is indistinguishable from a family-collision RuntimeError —
    # check the key here so only the real missing-key case maps to NliUnavailableError).
    if not os.environ.get("OPENROUTER_API_KEY", "").strip():
        raise NliUnavailableError(
            "OPENROUTER_API_KEY missing — the NLI entailment judge cannot run"
        )

    from src.polaris_graph.llm.entailment_judge import _get_judge

    judge = _get_judge()   # family-segregation RuntimeError propagates (NOT masked as unavailable)
    # I-wire-012 (#1326): score ALL pairs with BOUNDED-PARALLEL judge calls so this POST-RELEASE annotation
    # COMPLETES within the daemon wall. The old per-pair SYNC loop (one ~6-40s network call at a time)
    # overran PG_NLI_ANNOTATION_WALL_S and the whole advisory annotation was skipped. Every pair is still
    # scored (NO sampling — §-1.1); the run-budget gate + BudgetExceededError propagation are preserved by
    # the per-worker copy_context reconciliation inside _score_pairs_parallel (mirrors the proven I-arch-002
    # #1251 credibility pool). Results are INPUT-ORDER so the aggregation below maps each verdict to its own
    # sentence regardless of completion order.
    scored_pairs = _score_pairs_parallel(judge, pairs)
    entailed = neutral = contradicted = judge_errors = 0
    disputed: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for pair, (verdict, reason) in zip(pairs, scored_pairs):
        # I-cap-005 (#1068): the judge FAILS OPEN to ("ENTAILED", "judge_error: ...") on an API/parse
        # error to keep the run alive. Counting that as a genuine ENTAILED would silently report a
        # DEGRADED judge as "NLI clean" — a silent downgrade (LAW II / operator no-downgrade directive).
        # Detect it, count it as an ERROR (NOT entailed), and surface it loudly in the annotation.
        if isinstance(reason, str) and reason.startswith("judge_error:"):
            judge_errors += 1
            errors.append({
                "section": pair.get("section", ""),
                "evidence_id": pair.get("evidence_id", ""),
                "reason": reason,
                "sentence": pair["sentence"],
            })
            continue
        if verdict == "ENTAILED":
            entailed += 1
            continue
        if verdict == "CONTRADICTED":
            contradicted += 1
        else:
            verdict = "NEUTRAL"   # normalize any unexpected verdict to NEUTRAL (still disputed)
            neutral += 1
        disputed.append({
            "section": pair.get("section", ""),
            "evidence_id": pair.get("evidence_id", ""),
            "verdict": verdict,
            "reason": reason,
            "sentence": pair["sentence"],
        })
    scored = len(pairs) - judge_errors
    # If EVERY call errored, nothing was actually entailment-checked — surface nli_status:"error" LOUDLY
    # (not "ok" with a misleading zero-dispute count). Partial errors keep "ok" but expose the count so
    # an audit sees the degradation. Errored sentences are excluded from entailed/neutral/contradicted.
    nli_status = "error" if (pairs and scored == 0) else "ok"
    return {
        "nli_status": nli_status,
        "judge": "llm_entailment",
        "model": judge._model,
        "sentences_checked": len(pairs),
        "sentences_scored": scored,
        "entailed_count": entailed,
        "neutral_count": neutral,
        "contradicted_count": contradicted,
        "disputed_count": len(disputed),
        "disputed": disputed,
        "judge_error_count": judge_errors,
        "judge_errors": errors,
        "advisory": True,
    }
