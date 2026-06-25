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
# Classifier knobs.
CRAG_MODEL_ENV: str = "PG_ADEQUACY_CRAG_MODEL"
CRAG_MAX_TOKENS_ENV: str = "PG_ADEQUACY_CRAG_MAX_TOKENS"
CRAG_RENDER_CAP_ENV: str = "PG_ADEQUACY_CRAG_RENDER_CAP"

# Conservative defaults: one corrective loop-back, up to four gap queries.
_DEFAULT_MAX_LOOPS: int = 1
_DEFAULT_MAX_GAP_QUERIES: int = 4
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


def derive_gap_queries(
    *,
    research_question: str,
    findings: list[Any],
    gap_dimensions: list[str] | None = None,
    extra_terms: list[str] | None = None,
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

    Returns:
        An ordered, de-duplicated, capped list of gap queries. Empty iff there
        is no gap to target (the caller then falls back to re-issuing the
        research question).
    """
    question = (research_question or "").strip()
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

    def _add(text: str) -> None:
        cleaned = " ".join(text.split())
        key = cleaned.lower()
        if cleaned and key not in seen:
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
        _add(f"{question} {phrase}" if question else phrase)

    # SECONDARY: failing count-floor findings (advisory) for the gap axis.
    for finding in findings or []:
        ok = getattr(finding, "ok", True)
        if ok:
            continue
        name = getattr(finding, "name", "")
        phrase = gap_phrase.get(name)
        if phrase is None:
            continue
        _add(f"{question} {phrase}" if question else phrase)

    for term in extra_terms or []:
        term = (term or "").strip()
        if term:
            _add(f"{question} {term}" if question else term)

    return queries[: max_gap_queries()]
