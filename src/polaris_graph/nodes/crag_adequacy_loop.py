"""CRAG adequacy classifier + loop-back bridge (winner W7, I-wire-001 #1305).

Wires the bake-off winner **adequacy_crag** into the adequacy gate. Two things
are wired here, and the second is the one the Codex P1 demanded:

1. **The CRAG sufficiency CLASSIFIER replaces the count-floor STOP decision.**
   The legacy adequacy gate (`corpus_adequacy_gate.assess_corpus_adequacy`)
   decides `proceed` / `expand` / `abort` from a fixed N-source COUNT-FLOOR
   (`min_total_sources`, `min_t1_count`, ...). The count-floor was exactly the
   bug — a corpus can clear every count threshold and still be INSUFFICIENT
   (the specific required finding missing, an unresolved conflict), or it can
   miss a count threshold while being perfectly sufficient on relevance. The
   bake-off winner `crag` (Corrective-RAG, Yan et al. 2024, arXiv:2401.15884)
   judges sufficiency by **retrieval CONFIDENCE over the gathered evidence**,
   not by source count, and scored bal-acc=1.0 / gap-detection-recall=1.0 vs
   the count-floor's 0.9167 (scorecard
   `scripts/dr_benchmark/upstream_bakeoff/adequacy_design_race/results/adequacy_design_race_results.json`).
   When `PG_ADEQUACY_CRAG` is ON, `classify_sufficiency()` runs the CRAG
   confidence grader (CORRECT / AMBIGUOUS / INCORRECT over the WHOLE corpus)
   and that verdict — NOT the count-floor decision — drives the STOP decision.

2. **A bounded corrective LOOP-BACK on a not-sufficient verdict.** When CRAG
   grades the corpus AMBIGUOUS / INCORRECT (not sufficient), fire one more
   retrieval round targeted at the gap, merge the new sources, and RE-GRADE
   with CRAG — instead of the single-pass `abort_corpus_inadequate`.

SCOPE / FILE-NAME CORRECTION (LAW II honesty — read before the diff-gate):
The task + plan name `retrieval/crag_retriever.py` as the seam to import. That
is the WRONG file: `crag_retriever.py` is an EMBEDDING chunk-retriever
(all-MiniLM cosine scoring of pre-fetched `RawDocument`s) that was never a
candidate in the adequacy design-race. The bal-acc=1.0 winner is
`crag_design()` in
`scripts/dr_benchmark/upstream_bakeoff/adequacy_design_race/candidates.py` — an
LLM-driven confidence grader on the GLM-5.2 backbone. Importing a benchmark
script into `src/` is forbidden, and instantiating `CRAGRetriever` would load a
heavy embedding model (§8.4) for an un-benchmarked mechanism. So this module
PORTS `crag_design`'s proven mechanism (the `_CRAG_RUBRIC`, the JSON parse, the
CORRECT/AMBIGUOUS/INCORRECT -> enough/not_enough rule) into production, calling
through the existing `OpenRouterClient` on the mirror GLM model per §9.1.8 (the
aux classifier is NOT one of the 4 locked roles -> maps to the mirror). The
mechanism, not the file name, is the winner.

DESIGN (CLAUDE.md §-1.3 weight-and-consolidate, §-1.4 fire-in-output):

* **Flag-gated default-OFF.** `PG_ADEQUACY_CRAG` unset => this module is never
  consulted, no LLM call is made, and the legacy count-floor path runs
  byte-identically. The run-script lazy-imports this module only inside the ON
  branch.
* **Bounded.** `PG_ADEQUACY_CRAG_MAX_LOOPS` (default 1) caps the number of
  corrective loop-backs so the corpus state cannot loop forever. The DECISION
  is sequential by nature (gated on the corpus state after each round); the
  per-round retrieval fan-out is parallel and is owned by `run_live_retrieval`
  (this module adds NO second concurrency knob — §-1.3 anti-knob).
* **Faithfulness FROZEN.** CRAG is a retrieval/STOP decision step, not a
  faithfulness change. It only decides WHETHER to widen the corpus; the
  faithfulness engine (strict_verify / NLI / 4-role / provenance) is untouched
  and still gates every merged source downstream. CRAG can never relax a
  faithfulness gate; it can only feed it more candidates.

This module owns the CRAG classifier prompt/parse + the pure decision/
derivation helpers (no retrieval network calls of its own). The run-script owns
the actual `run_live_retrieval` fan-out + merge, so the loop-back reuses the
proven, already-bounded parallel retrieval machinery rather than
re-implementing it.
"""
from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import Iterable
from typing import Any

logger = logging.getLogger("polaris_graph.crag_adequacy_loop")

# Accepted truthy spellings for the gate flag (mirrors the recency wiring
# pattern used elsewhere in the pipeline).
_ON_VALUES: frozenset[str] = frozenset({"1", "true", "on", "yes"})

# Env names — the knobs this winner introduces. MAX_LOOPS is the bound; there
# is deliberately NO second concurrency knob (the retrieval fan-out is already
# bounded inside run_live_retrieval).
FLAG_ENV: str = "PG_ADEQUACY_CRAG"
MAX_LOOPS_ENV: str = "PG_ADEQUACY_CRAG_MAX_LOOPS"
MAX_GAP_QUERIES_ENV: str = "PG_ADEQUACY_CRAG_MAX_GAP_QUERIES"
# I-deepfix-001 U22 (#1344): bounded reserved retrieval budget (seconds) for the
# GUARANTEED first corrective round when the SHARED per-question wall was already
# consumed by upstream lanes. See :func:`corrective_reserve_seconds`.
CORRECTIVE_RESERVE_ENV: str = "PG_ADEQUACY_CRAG_CORRECTIVE_RESERVE_SECONDS"
# Classifier knobs.
CRAG_MODEL_ENV: str = "PG_ADEQUACY_CRAG_MODEL"
CRAG_MAX_TOKENS_ENV: str = "PG_ADEQUACY_CRAG_MAX_TOKENS"
CRAG_RENDER_CAP_ENV: str = "PG_ADEQUACY_CRAG_RENDER_CAP"
# I-deepfix-001 R3 (#1344): source-yield-SATURATION widening of the corrective loop.
# The legacy loop bound was a FIXED pass count (`PG_ADEQUACY_CRAG_MAX_LOOPS` default 1)
# — a chained/2nd-order recall rubric (A -> find entity -> fact B) frequently needs more
# than one corrective round, but a fixed "1" stops before the chain closes. R3 widens the
# loop bounded by SOURCE-YIELD SATURATION (keep correcting while each round still surfaces
# NEW sources; stop when the yield flattens) instead of a fixed count. The MAX-loops env
# stays as an outer COMPUTE-SAFETY bound (never a breadth target — §-1.3). YIELD_EPS is the
# novel-source fraction below which the loop is judged saturated.
CRAG_YIELD_EPS_ENV: str = "PG_ADEQUACY_CRAG_YIELD_EPS"
CRAG_MAX_SATURATION_LOOPS_ENV: str = "PG_ADEQUACY_CRAG_MAX_SATURATION_LOOPS"

# Conservative defaults: one corrective loop-back, up to four gap queries.
_DEFAULT_MAX_LOOPS: int = 1
_DEFAULT_MAX_GAP_QUERIES: int = 4
# I-deepfix-001 U22 (#1344): bounded reserved retrieval budget (seconds) for the
# ONE guaranteed corrective round. A positive default so an insufficient verdict
# whose SHARED per-question wall was already exhausted upstream still gets one real
# corrective fetch instead of a 0-iter no-op. A CAP, not a target (billed by usage).
_DEFAULT_CORRECTIVE_RESERVE_SECONDS: float = 300.0
# Per §9.1.8: the aux classifier is NOT one of the 4 locked roles -> mirror GLM.
# z-ai/glm-5.2 is the bake-off backbone the winner was scored on.
_DEFAULT_CRAG_MODEL: str = "z-ai/glm-5.2"
# Generous cap (a CAP, not a target — billed by usage) per the never-starve rule.
_DEFAULT_CRAG_MAX_TOKENS: int = 8192
# Cap how many evidence rows are rendered into the grader prompt (the corpus can
# be large; the confidence grade is over the whole corpus but does not need every
# row verbatim). This is a prompt-size bound, not a faithfulness cap.
_DEFAULT_RENDER_CAP: int = 60

# CRAG sufficiency verdicts -> sufficient? (Yan et al. 2024). CORRECT => stop
# (sufficient); AMBIGUOUS / INCORRECT => not sufficient (corrective retrieval).
_SUFFICIENT_VERDICTS: frozenset[str] = frozenset({"correct"})

# The bake-off-proven CRAG rubric, ported VERBATIM from candidates.py
# (`_CRAG_RUBRIC`) so the production mechanism is the one that scored bal-acc=1.0.
_CRAG_RUBRIC: str = (
    "CRAG (Corrective-RAG) rule: act as a retrieval-CONFIDENCE grader. Grade the WHOLE gathered "
    "evidence as CORRECT (confidently sufficient), AMBIGUOUS, or INCORRECT (insufficient / needs "
    "corrective retrieval). Map CORRECT->enough; AMBIGUOUS or INCORRECT->not_enough. When not "
    "CORRECT, name the specific gap dimensions / missing required findings that drove the low "
    "confidence."
)


def crag_flag_on() -> bool:
    """True iff `PG_ADEQUACY_CRAG` is set to a truthy value (default-OFF)."""
    return os.getenv(FLAG_ENV, "").strip().lower() in _ON_VALUES


def max_loops() -> int:
    """Bounded loop-back cap (>= 0). Reads `PG_ADEQUACY_CRAG_MAX_LOOPS`.

    A malformed value falls back to the conservative default rather than
    raising — the loop budget is an operational knob, not a correctness gate.
    """
    raw = os.getenv(MAX_LOOPS_ENV, "").strip()
    if not raw:
        return _DEFAULT_MAX_LOOPS
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_MAX_LOOPS
    return max(0, value)


def max_gap_queries() -> int:
    """Cap on the number of derived gap queries per loop-back round (>= 1)."""
    raw = os.getenv(MAX_GAP_QUERIES_ENV, "").strip()
    if not raw:
        return _DEFAULT_MAX_GAP_QUERIES
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_MAX_GAP_QUERIES
    return max(1, value)


def _render_cap() -> int:
    raw = os.getenv(CRAG_RENDER_CAP_ENV, "").strip()
    if not raw:
        return _DEFAULT_RENDER_CAP
    try:
        return max(1, int(raw))
    except ValueError:
        return _DEFAULT_RENDER_CAP


def _crag_model() -> str:
    return os.getenv(CRAG_MODEL_ENV, "").strip() or _DEFAULT_CRAG_MODEL


def _crag_max_tokens() -> int:
    raw = os.getenv(CRAG_MAX_TOKENS_ENV, "").strip()
    if not raw:
        return _DEFAULT_CRAG_MAX_TOKENS
    try:
        return max(256, int(raw))
    except ValueError:
        return _DEFAULT_CRAG_MAX_TOKENS


def _extract_json(text: str) -> dict:
    """Pull the first {...} JSON object out of an LLM response.

    Ported from candidates.py `_extract_json` — tolerant of prose / code fences.
    """
    if not text:
        return {}
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except Exception:  # noqa: BLE001 — malformed JSON is a known LLM output mode
        return {}


def _render_corpus_for_grader(
    *,
    classified_sources: list[Any],
    evidence_rows: list[Any],
    render_cap: int,
) -> str:
    """Render a compact view of the gathered evidence for the CRAG grader.

    One line per source: index, tier (the WEIGHT, surfaced not dropped — §-1.3),
    title, url, and a short snippet from the first matching evidence row. The
    grader scores CONFIDENCE over this WHOLE corpus view; this is a prompt-size
    bound, never a faithfulness drop.
    """
    # Map url -> first non-empty snippet from the evidence rows.
    snippet_by_url: dict[str, str] = {}
    for row in evidence_rows or []:
        if not isinstance(row, dict):
            continue
        url = (row.get("source_url") or row.get("url") or "").strip()
        if not url or url in snippet_by_url:
            continue
        snippet = (
            row.get("direct_quote")
            or row.get("statement")
            or row.get("snippet")
            or ""
        )
        snippet_by_url[url] = " ".join(str(snippet).split())[:240]

    lines: list[str] = []
    for idx, src in enumerate(classified_sources or []):
        if idx >= render_cap:
            lines.append(
                f"... ({len(classified_sources) - render_cap} more sources omitted "
                f"from this prompt view; grade confidence over the corpus as a whole)"
            )
            break
        url = (getattr(src, "url", "") or "").strip()
        title = (getattr(src, "title", "") or "").strip()
        tier = getattr(src, "tier", None) or getattr(src, "tier_label", "") or "?"
        snippet = snippet_by_url.get(url, "")
        lines.append(
            f"[{idx}] tier={tier} title={title!r} url={url} "
            f"snippet={snippet!r}"
        )
    return "\n".join(lines)


def build_classifier_prompt(
    *,
    research_question: str,
    classified_sources: list[Any],
    evidence_rows: list[Any],
) -> str:
    """Build the CRAG confidence-grader prompt (pure — no network).

    Split out from :func:`parse_classifier_response` so the run-script (which is
    inside an ``async`` coroutine with a running event loop) can ``await`` the
    production `OpenRouterClient.generate` DIRECTLY — never `asyncio.run()` from
    inside a running loop. The prompt is the bake-off `crag_design` shape with
    the `_CRAG_RUBRIC` ported verbatim.
    """
    question = (research_question or "").strip()
    corpus_view = _render_corpus_for_grader(
        classified_sources=classified_sources,
        evidence_rows=evidence_rows,
        render_cap=_render_cap(),
    )
    return (
        "You are the ADEQUACY controller for a deep-research pipeline using the "
        "CRAG method.\n"
        f"RESEARCH QUESTION: {question}\n\n"
        "EVIDENCE GATHERED SO FAR (one row per source, with its index):\n"
        f"{corpus_view}\n\n"
        f"{_CRAG_RUBRIC}\n\n"
        "Respond with ONLY a JSON object:\n"
        '{"verdict": "CORRECT"|"AMBIGUOUS"|"INCORRECT", '
        '"decision": "enough"|"not_enough", "gap_dimensions": [str,...]}\n'
        "decision is 'enough' iff verdict is CORRECT. gap_dimensions name the "
        "specific missing required findings / gap axes when not CORRECT."
    )


def parse_classifier_response(raw: str) -> dict[str, Any]:
    """Parse the CRAG grader's raw text into a sufficiency decision (pure).

    Maps the CRAG verdict (Yan et al. 2024) to a sufficiency boolean:
    CORRECT -> sufficient; AMBIGUOUS|INCORRECT -> not sufficient.

    Args:
        raw: the grader's raw text (the awaited `OpenRouterClient` content).

    Returns:
        A dict with: ``sufficient`` (bool), ``verdict`` (correct/ambiguous/
        incorrect/unparseable), ``gap_dimensions`` (list[str]),
        ``raw`` (truncated grader text), ``invoked`` (True — the classifier
        ran), ``decision_source`` ("crag_classifier"). On an empty/unparseable
        grade we conservatively return ``sufficient=False`` (corrective
        retrieval) and verdict="unparseable" — never a silent enough.
    """
    raw = raw or ""
    obj = _extract_json(raw)
    verdict = str(obj.get("verdict", "")).strip().lower()
    decision = str(obj.get("decision", "")).strip().lower()
    gap_dimensions = [
        str(g).strip() for g in (obj.get("gap_dimensions") or []) if str(g).strip()
    ]

    if verdict in {"correct", "ambiguous", "incorrect"}:
        sufficient = verdict in _SUFFICIENT_VERDICTS
    elif decision in {"enough", "not_enough"}:
        # Verdict missing but decision present — honor the explicit decision.
        sufficient = decision == "enough"
        verdict = "correct" if sufficient else "ambiguous"
    else:
        # Unparseable grade: conservatively NOT sufficient (corrective retrieval),
        # never a silent enough. This is fail-loud-safe, not a relaxation.
        sufficient = False
        verdict = "unparseable"

    return {
        "sufficient": sufficient,
        "verdict": verdict,
        "gap_dimensions": gap_dimensions,
        "raw": raw[:400],
        "invoked": True,
        "decision_source": "crag_classifier",
    }


def classify_sufficiency(
    *,
    research_question: str,
    classified_sources: list[Any],
    evidence_rows: list[Any],
    llm_generate: Any,
) -> dict[str, Any]:
    """Run the CRAG confidence classifier via a SYNC ``llm_generate`` callable.

    Convenience wrapper around :func:`build_classifier_prompt` +
    :func:`parse_classifier_response` for SYNCHRONOUS callers (tests, offline
    smoke harnesses). The production run-script does NOT use this — it is inside
    a running event loop and ``await``s the client directly via the two pure
    functions above (an `asyncio.run()` from a running loop would raise). This
    REPLACES the count-floor as the STOP signal when `PG_ADEQUACY_CRAG` is ON.

    Args:
        research_question: the run's research question (the relevance anchor).
        classified_sources: the tier-classified sources in the corpus.
        evidence_rows: the grounded evidence rows (for snippets).
        llm_generate: a callable ``(prompt: str) -> str`` returning the grader's
            raw text. FAIL-LOUD: this module never silently fabricates a verdict.

    Returns:
        The :func:`parse_classifier_response` decision dict. On a raised LLM
        call, returns verdict="error", sufficient=False, invoked=True.
    """
    prompt = build_classifier_prompt(
        research_question=research_question,
        classified_sources=classified_sources,
        evidence_rows=evidence_rows,
    )
    try:
        raw = llm_generate(prompt) or ""
    except Exception as exc:  # noqa: BLE001 — surface, never silently pass
        logger.warning("[crag-adequacy] classifier call failed: %s", exc)
        return {
            "sufficient": False,
            "verdict": "error",
            "gap_dimensions": [],
            "raw": str(exc)[:400],
            "invoked": True,
            "decision_source": "crag_classifier",
            "error": str(exc),
        }
    return parse_classifier_response(raw)


def should_loop_back(*, sufficient: bool, loops_done: int) -> bool:
    """Decide whether to fire one more corrective loop-back.

    Keys off the CRAG CLASSIFIER verdict (``sufficient``), NOT the count-floor
    `adequacy.decision` — that is the whole point of the winner. Loop back iff
    the CRAG grader judged the corpus NOT sufficient AND the bounded loop budget
    is not exhausted.

    Args:
        sufficient: the CRAG classifier's sufficiency verdict (True => stop).
        loops_done: number of corrective loop-backs already fired this query.

    Returns:
        True to fire another bounded loop-back; False to stop (sufficient, or
        budget exhausted).
    """
    if sufficient:
        return False
    return loops_done < max_loops()


# I-deepfix-001 R3 (#1344): source-yield-saturation defaults. YIELD_EPS is the
# novel-source fraction below which a corrective round is judged saturated (the
# same novelty metric the Phase-4 saturation loop uses). MAX_SATURATION_LOOPS is
# the OUTER compute-safety bound so the widened loop can never grind unbounded.
_DEFAULT_YIELD_EPS: float = 0.10
_DEFAULT_MAX_SATURATION_LOOPS: int = 4


def crag_yield_eps() -> float:
    """Novel-source-fraction epsilon for the R3 saturation stop (>= 0.0).

    Reads `PG_ADEQUACY_CRAG_YIELD_EPS`. A corrective round whose fraction of NEW
    (canonical-URL-novel) sources is < this value is treated as saturated — the
    corpus stopped growing, so widening further would spend compute for no new
    evidence. A malformed / negative value falls back to the conservative default.
    """
    raw = os.getenv(CRAG_YIELD_EPS_ENV, "").strip()
    if not raw:
        return _DEFAULT_YIELD_EPS
    try:
        value = float(raw)
    except ValueError:
        return _DEFAULT_YIELD_EPS
    return value if value >= 0.0 else _DEFAULT_YIELD_EPS


def crag_max_saturation_loops() -> int:
    """Outer COMPUTE-SAFETY bound on total corrective rounds for the R3 widened
    loop (>= 1). Reads `PG_ADEQUACY_CRAG_MAX_SATURATION_LOOPS`.

    This is a compute bound, NOT a breadth target (§-1.3): the loop stops EARLIER
    on source-yield saturation (:func:`corrective_yield_saturated`) or on a
    sufficient verdict; this cap only guarantees the widened loop terminates even
    if the grader keeps saying insufficient while sources keep trickling in.
    """
    raw = os.getenv(CRAG_MAX_SATURATION_LOOPS_ENV, "").strip()
    if not raw:
        return _DEFAULT_MAX_SATURATION_LOOPS
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_MAX_SATURATION_LOOPS
    return max(1, value)


def corrective_yield_saturated(
    *,
    prev_corpus_rows: list[Any],
    last_round_rows: list[Any],
    eps: float | None = None,
) -> bool:
    """True iff the LAST corrective round's source yield has SATURATED.

    Uses the SAME novelty metric as the Phase-4 saturation loop
    (:func:`src.polaris_graph.retrieval.saturation.marginal_novelty`): the
    fraction of ``last_round_rows`` whose canonical source URL was NOT already in
    ``prev_corpus_rows``. When that fraction is < ``eps`` the round barely added
    any new source — the corrective retrieval has flattened and the loop should
    stop (a yield saturation stop, never a breadth count — §-1.3).

    An EMPTY ``last_round_rows`` (the round fetched nothing) is saturated by
    definition (novelty of an empty round is 0.0). Returns False when the round
    surfaced enough new sources to be worth another pass.
    """
    threshold = crag_yield_eps() if eps is None else eps
    if not last_round_rows:
        return True
    # Local import keeps the heavy saturation import off this module's import path.
    from src.polaris_graph.retrieval.saturation import marginal_novelty

    novelty = marginal_novelty(prev_corpus_rows or [], last_round_rows or [])
    return novelty < threshold


def should_loop_back_saturating(
    *,
    sufficient: bool,
    loops_done: int,
    prev_corpus_rows: list[Any],
    last_round_rows: list[Any],
    yield_eps: float | None = None,
    max_saturation_loops: int | None = None,
) -> bool:
    """R3 (#1344): decide whether to fire one more corrective round, bounded by
    SOURCE-YIELD SATURATION rather than the legacy fixed pass count.

    This REPLACES the fixed ``loops_done < max_loops()`` bound (default 1) with a
    yield-keyed loop so chained / 2nd-order recall rubrics (A -> find entity ->
    fact B) get as many corrective rounds as keep surfacing NEW sources — while
    still terminating. The decision ladder:

    1. ``sufficient`` -> stop (the CRAG grader is confident; corpus is enough).
    2. First corrective round (``loops_done == 0``) on a NOT-sufficient corpus ->
       ALWAYS loop back once (Corrective-RAG's guarantee — mirrors
       :func:`wall_should_break_corrective_loop`). No yield history yet.
    3. ``loops_done >= max_saturation_loops`` -> stop (outer compute-safety bound).
    4. Last round's source yield SATURATED (:func:`corrective_yield_saturated`) ->
       stop (widening no longer produces new evidence).
    5. Otherwise -> loop back (not sufficient, still within the compute bound, and
       the last round is still surfacing new sources).

    Args:
        sufficient: the CRAG classifier's latest sufficiency verdict.
        loops_done: corrective rounds already fired this query.
        prev_corpus_rows: the corpus BEFORE the last corrective round (novelty
            baseline).
        last_round_rows: the RAW rows the last corrective round retrieved (the
            novelty denominator).
        yield_eps: override for `PG_ADEQUACY_CRAG_YIELD_EPS` (tests).
        max_saturation_loops: override for the outer compute bound (tests).

    Returns:
        True to fire another corrective round; False to stop and hand off the
        corpus gathered so far.
    """
    if sufficient:
        return False
    if loops_done <= 0:
        # Guarantee the first corrective round on an insufficient corpus.
        return True
    cap = (
        crag_max_saturation_loops()
        if max_saturation_loops is None
        else max(1, int(max_saturation_loops))
    )
    if loops_done >= cap:
        return False
    if corrective_yield_saturated(
        prev_corpus_rows=prev_corpus_rows,
        last_round_rows=last_round_rows,
        eps=yield_eps,
    ):
        return False
    return True


# ── I-deepfix-001 #1367: corrective-loop arbitration (accept-with-disclosed-gap) ─
# Outcome labels for :func:`crag_loop_arbitration`. Any ``accept_*`` outcome STOPS the
# corrective loop and hands the gathered corpus off to composition; ``loop_back`` fires
# one more corrective round.
ARBITRATION_ACCEPT_SUFFICIENT: str = "accept_sufficient"
ARBITRATION_ACCEPT_DISCLOSED_GAP: str = "accept_disclosed_gap"
ARBITRATION_ACCEPT_SATURATED_BELOW_FLOOR: str = "accept_saturated_below_floor"
ARBITRATION_LOOP_BACK: str = "loop_back"
# Both disclosed-gap variants proceed to composition DISCLOSING a residual coverage gap
# (never an abort / source drop — §-1.3); the run-script treats them alike.
ARBITRATION_ACCEPT_DISCLOSED_GAP_REASONS: frozenset[str] = frozenset(
    {ARBITRATION_ACCEPT_DISCLOSED_GAP, ARBITRATION_ACCEPT_SATURATED_BELOW_FLOOR}
)


def crag_loop_arbitration(
    *,
    sufficient: bool,
    count_floor_proceed: bool,
    loops_done: int,
    prev_corpus_rows: list[Any],
    last_round_rows: list[Any],
    yield_eps: float | None = None,
    max_saturation_loops: int | None = None,
) -> str:
    """Arbitrate the corrective loop: fire another round, or ACCEPT-with-disclosed-gap.

    I-deepfix-001 #1367 — the honest §-1.3 answer to the drb_72 non-convergence. When a
    corrective round stopped surfacing NEW sources (yield saturated) OR the outer
    compute bound is hit, and the corpus is NOT graded sufficient, do NOT keep grading it
    INCORRECT and spin another empty corrective round. Proceed to composition, DISCLOSING
    the residual coverage gap. This NEVER drops a source and never relaxes a faithfulness
    gate — it only decides WHEN to stop widening the corpus. The CRAG/adequacy loop is
    thereby never a hard non-convergence driver (the drb_72 defect: malformed corrective
    queries fetch ~nothing, the grader can never reach CORRECT, and the loop burns its
    whole budget every cycle).

    Decision ladder:
      1. ``sufficient`` -> ``accept_sufficient`` (the CRAG grader is confident).
      2. ``loops_done <= 0`` -> ``loop_back`` (Corrective-RAG guarantees the FIRST
         corrective round on an insufficient corpus; no yield history yet).
      3. the yield-saturation stop (:func:`should_loop_back_saturating`) still says keep
         going (last round surfaced new sources AND under the compute bound) ->
         ``loop_back``.
      4. otherwise the loop must stop WITHOUT sufficiency:
         * ``count_floor_proceed`` True  -> ``accept_disclosed_gap`` (the deterministic
           count-floor already judged the corpus adequate; only the CRAG grader wanted
           more — proceed and disclose the residual gap).
         * ``count_floor_proceed`` False -> ``accept_saturated_below_floor`` (the corpus
           is below the count-floor AND the corrective retrieval cannot surface anything
           new; still proceed + disclose — adequacy is never a hard abort, the
           faithfulness engine is the only hard gate — but flag the stronger gap).

    Args mirror :func:`should_loop_back_saturating`; ``count_floor_proceed`` is the
    deterministic count-floor's proceed decision (``adequacy.decision == "proceed"``).
    """
    if sufficient:
        return ARBITRATION_ACCEPT_SUFFICIENT
    if loops_done <= 0:
        return ARBITRATION_LOOP_BACK
    if should_loop_back_saturating(
        sufficient=sufficient,
        loops_done=loops_done,
        prev_corpus_rows=prev_corpus_rows,
        last_round_rows=last_round_rows,
        yield_eps=yield_eps,
        max_saturation_loops=max_saturation_loops,
    ):
        return ARBITRATION_LOOP_BACK
    if count_floor_proceed:
        return ARBITRATION_ACCEPT_DISCLOSED_GAP
    return ARBITRATION_ACCEPT_SATURATED_BELOW_FLOOR


def corrective_reserve_seconds() -> float:
    """Bounded reserved retrieval budget (seconds) for the GUARANTEED first
    corrective round. Reads `PG_ADEQUACY_CRAG_CORRECTIVE_RESERVE_SECONDS`.

    Why this exists (I-deepfix-001 U22, #1344): the CRAG corrective loop shares the
    per-question retrieval wall (`PG_RETRIEVAL_QUESTION_WALL_SECONDS`) with the
    upstream lanes (initial / STORM / deepener). On a wide question those lanes can
    consume the WHOLE wall before adequacy is even graded, so when CRAG grades the
    corpus NOT sufficient the shared wall has already passed and the corrective
    `run_live_retrieval` short-circuits immediately, fetching nothing — the drb_72
    defect (classifier said insufficient, `loops_fired=0`, `stopped_reason=
    retrieval_wall`, injected 0). Corrective-RAG's whole point is that a
    not-sufficient corpus gets at least ONE real corrective round, so the guaranteed
    first round is granted this small bounded budget when (and only when) the shared
    wall is already exhausted.

    A malformed / negative value falls back to the conservative default. This is an
    ADDITIVE retrieval budget, never a breadth cap/thinner (§-1.3): it can only feed
    the unchanged tier classifier + strict_verify engine MORE candidates.
    """
    raw = os.getenv(CORRECTIVE_RESERVE_ENV, "").strip()
    if not raw:
        return _DEFAULT_CORRECTIVE_RESERVE_SECONDS
    try:
        value = float(raw)
    except ValueError:
        return _DEFAULT_CORRECTIVE_RESERVE_SECONDS
    if value < 0:
        return _DEFAULT_CORRECTIVE_RESERVE_SECONDS
    return value


def wall_should_break_corrective_loop(
    *, sufficient: bool, loops_done: int, wall_passed: bool
) -> bool:
    """Whether the CRAG corrective loop should BREAK on the shared retrieval wall.

    Corrective-RAG guarantees that a NOT-sufficient corpus gets at least one
    corrective retrieval round. The shared per-question retrieval wall is consumed by
    the upstream lanes, so breaking the corrective loop the instant the wall has
    passed makes CRAG a no-op EXACTLY when it is needed — the drb_72 defect: the
    classifier graded the corpus insufficient but 0 corrective iterations ran because
    the wall was already exhausted.

    Rule: NEVER break before the FIRST corrective iteration has run when the corpus is
    insufficient (``not sufficient`` and ``loops_done == 0``). After that one
    guaranteed round, honor the wall exactly as before (stop adding rounds; hand off
    the merged corpus). When the corpus is already sufficient, or a corrective round
    has already fired, the wall is honored unchanged — so this preserves the BUG-A
    bound (the loop still cannot grind unbounded past the wall).

    Args:
        sufficient: the CRAG classifier's latest sufficiency verdict.
        loops_done: number of corrective loop-backs already fired this query.
        wall_passed: whether the SHARED per-question retrieval wall has passed
            (``_question_retrieval_deadline_passed(...)`` in the run-script).

    Returns:
        True to BREAK (hand off the corpus gathered so far); False to keep going.
    """
    if not sufficient and loops_done == 0:
        # Guarantee the first corrective iteration — do NOT break on the wall yet.
        return False
    return wall_passed


def corrective_iter_deadline(
    *,
    shared_deadline: float | None,
    now: float,
    loops_done: int,
    sufficient: bool,
) -> float | None:
    """Absolute monotonic deadline for the corrective ``run_live_retrieval`` call.

    Keeps the SHARED per-question wall as the deadline in the normal case, but grants
    the ONE guaranteed first corrective round (see
    :func:`wall_should_break_corrective_loop`) a bounded reserved budget when the
    shared wall has ALREADY passed — otherwise that guaranteed round would run against
    an exhausted deadline and fetch nothing (the drb_72 no-op).

    Cases:
      * ``shared_deadline is None`` (wall OFF — the default) => return ``None`` =>
        the corrective retrieval is unbounded exactly as before (byte-identical).
      * shared deadline still in the future => return it unchanged (spend the
        remaining shared budget; no reserve needed).
      * shared deadline already passed AND this is the guaranteed first corrective
        round (``not sufficient`` and ``loops_done == 0``) => return
        ``now + corrective_reserve_seconds()`` so the round can actually fetch.
      * otherwise (wall passed, not the first round) => return the (passed) shared
        deadline unchanged; the loop-break decision stops the loop anyway.

    Args:
        shared_deadline: the anchored per-question retrieval deadline, or ``None``.
        now: the current ``time.monotonic()`` instant (injected for purity/testing).
        loops_done: corrective loop-backs already fired this query.
        sufficient: the CRAG classifier's latest sufficiency verdict.

    Returns:
        The absolute monotonic deadline to pass as ``retrieval_deadline_monotonic``.
    """
    if shared_deadline is None:
        return None
    if now <= shared_deadline:
        # Shared budget not yet exhausted — use it as-is.
        return shared_deadline
    # Shared wall already passed.
    if not sufficient and loops_done == 0:
        return now + corrective_reserve_seconds()
    return shared_deadline


# ── I-deepfix-001 #1367: corrective-query hygiene ────────────────────────────
# The drb_72 non-convergence: the corrective query generator ran dry and echoed
# near-verbatim question fragments (e.g. "researching impact generative future labor
# market please help"). openalex_search (/works?search=<q>) returns ~nothing on those
# malformed / boilerplate-laden long queries, so the corrective rounds fetched almost
# nothing, the CRAG grader could never reach CORRECT, and the loop burned its whole
# budget. These pure helpers CLEAN each derived query (strip search-noise boilerplate,
# cap length) and provide the normalized dedup key the novelty guard keys on. §-1.3:
# they only clean the QUERY STRING that is searched — no source is ever filtered or
# dropped and the faithfulness engine is untouched.
QUERY_MAX_WORDS_ENV: str = "PG_ADEQUACY_CRAG_QUERY_MAX_WORDS"
_DEFAULT_QUERY_MAX_WORDS: int = 24
# Words reserved for the gap-bias phrase so capping the question STEM never drops it.
_QUERY_PHRASE_RESERVE_WORDS: int = 8
# Conversational / imperative filler that is search NOISE for a keyword backend but
# never a subject term. Multi-word phrases FIRST so a subset ("please") cannot strip a
# fragment of an already-removed phrase ("please help"). Stripped case-insensitively as
# whole tokens only (never inside a word) so subject terms are byte-preserved.
_QUERY_BOILERPLATE_PHRASES: tuple[str, ...] = (
    "please help me", "please help", "help me please", "can you help me",
    "can you help", "could you help me", "could you help",
    "i am researching", "i'm researching", "i am looking for", "i'm looking for",
    "tell me about", "thanks in advance", "thank you",
    "researching", "please", "kindly", "thanks",
)


def _query_max_words() -> int:
    """Word cap for a derived corrective query (>= 1). Reads
    `PG_ADEQUACY_CRAG_QUERY_MAX_WORDS`.

    A CAP so an over-long regurgitated question is not sent verbatim to a keyword
    backend that returns nothing on it — never a breadth target (§-1.3). Malformed /
    non-positive values fall back to the conservative default.
    """
    raw = os.getenv(QUERY_MAX_WORDS_ENV, "").strip()
    if not raw:
        return _DEFAULT_QUERY_MAX_WORDS
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_QUERY_MAX_WORDS
    return max(1, value)


def normalize_query_key(text: str) -> str:
    """Normalized dedup identity for a query: lowercased, whitespace-collapsed,
    surrounding punctuation trimmed. Two queries with the same key are treated as the
    SAME query by the corrective novelty guard, so a round cannot re-emit an
    already-tried query.
    """
    return " ".join((text or "").split()).strip().strip("\"'.,;:?! ").lower()


def sanitize_query(text: str, *, max_words: int | None = None) -> str:
    """Clean a derived query so a keyword backend (openalex /works?search) accepts it.

    Removes conversational / imperative filler (``please help``, ``researching`` …) and
    caps the word count. §-1.3: this cleans ONLY the query STRING that is searched — it
    filters / drops NO source and touches no faithfulness gate. Returns ``""`` when the
    query is empty after cleaning (the caller then skips it).
    """
    s = " ".join((text or "").split())
    if not s:
        return ""
    for phrase in _QUERY_BOILERPLATE_PHRASES:
        s = re.sub(
            rf"(?<![\w-]){re.escape(phrase)}(?![\w-])", " ", s, flags=re.IGNORECASE
        )
    s = " ".join(s.split())
    cap = _query_max_words() if max_words is None else max(1, int(max_words))
    words = s.split()
    if len(words) > cap:
        s = " ".join(words[:cap])
    return s.strip()


def derive_gap_queries(
    *,
    research_question: str,
    findings: list[Any],
    gap_dimensions: list[str] | None = None,
    extra_terms: list[str] | None = None,
    already_tried: "Iterable[str] | None" = None,
) -> list[str]:
    """Derive corrective re-search queries targeted at the adequacy gap.

    CRAG's corrective action re-retrieves toward the SPECIFIC shortfall, not a
    blind re-search. Gap dimensions named by the CRAG classifier take priority;
    failing count-floor findings (advisory now, but still informative for the
    gap axis) are folded in as a secondary signal. This widens the corpus on the
    exact axis the grader flagged.

    The queries are de-duplicated, order-preserving, and capped by
    `PG_ADEQUACY_CRAG_MAX_GAP_QUERIES`. No network calls; pure derivation.

    Args:
        research_question: the run's research question (the retrieval anchor).
        findings: the adequacy report findings (objects exposing `.name`,
            `.ok`). Failing findings drive secondary gap queries.
        gap_dimensions: gap axes named by the CRAG classifier (primary signal).
        extra_terms: optional additional gap terms.
        already_tried: I-deepfix-001 #1367 novelty/dedup guard — queries already
            issued (prior corrective rounds + the raw question). A derived query
            whose normalized key matches one of these is DROPPED, so a corrective
            round never re-emits a near-duplicate / already-tried query (the drb_72
            regurgitation). When every derived query is already tried the result is
            EMPTY — the caller then correctly trips yield-saturation instead of
            re-issuing the raw question.

    Returns:
        An ordered, de-duplicated, boilerplate-stripped, length-capped list of NEW
        gap queries. Empty iff there is no NEW gap to target.
    """
    question = (research_question or "").strip()
    # I-deepfix-001 #1367: build queries from a CLEANED, length-capped question STEM so
    # a long / boilerplate-laden question is not echoed verbatim into a query the keyword
    # backend rejects. Reserve room for the gap-bias phrase so capping the stem never
    # drops it.
    _stem = sanitize_query(
        question, max_words=max(1, _query_max_words() - _QUERY_PHRASE_RESERVE_WORDS)
    )
    # Map each adequacy dimension to a corrective retrieval bias phrase.
    gap_phrase: dict[str, str] = {
        "total_sources": "additional independent sources",
        "t1_count": "peer-reviewed primary research randomized controlled trial",
        "t1_plus_t2": "peer-reviewed and systematic review evidence",
        "t1_plus_t2_plus_t3": "peer-reviewed systematic review and guideline evidence",
        "t3_plus_t4_plus_t6": "government regulatory and institutional reports",
        "evidence_rows": "detailed full-text findings and data",
        "low_quality_fraction": "high-quality peer-reviewed primary sources",
        "t7_fraction": "authoritative full-text sources",
    }

    queries: list[str] = []
    seen: set[str] = set()
    # I-deepfix-001 #1367: seed the seen-set with every query already tried (prior
    # corrective rounds + the raw question) so a round cannot re-emit an already-issued
    # query. Normalized identity match.
    for _prev in already_tried or []:
        _k = normalize_query_key(_prev)
        if _k:
            seen.add(_k)

    def _add(text: str) -> None:
        # I-deepfix-001 #1367: strip search-noise boilerplate + cap length so the query
        # is one a keyword backend accepts, then dedup on the normalized key.
        cleaned = sanitize_query(text)
        if not cleaned:
            return
        key = normalize_query_key(cleaned)
        if key in seen:
            return
        seen.add(key)
        queries.append(cleaned)

    # PRIMARY: gap dimensions named by the CRAG classifier (free-text axes).
    for dim in gap_dimensions or []:
        dim = (dim or "").strip()
        if not dim:
            continue
        # If the dimension matches a known count-floor finding name, use its
        # curated bias phrase; otherwise use the free-text gap axis directly.
        phrase = gap_phrase.get(dim.lower().replace(" ", "_"), dim)
        _add(f"{_stem} {phrase}" if _stem else phrase)

    # SECONDARY: failing count-floor findings (advisory) for the gap axis.
    for finding in findings or []:
        ok = getattr(finding, "ok", True)
        if ok:
            continue
        name = getattr(finding, "name", "")
        phrase = gap_phrase.get(name)
        if phrase is None:
            continue
        _add(f"{_stem} {phrase}" if _stem else phrase)

    for term in extra_terms or []:
        term = (term or "").strip()
        if term:
            _add(f"{_stem} {term}" if _stem else term)

    return queries[: max_gap_queries()]
