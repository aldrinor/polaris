"""R2 (I-deepfix-001, #1344) — per-task facet checklist drives the completeness/expansion loop.

THE GAP: the production completeness/expansion loop (``nodes/completeness_checker.py``) only has a
CLINICAL checklist. On a general task (labor, finance, science) it reads a vacuous "0 of 0 covered"
(``completeness_state == "not_applicable"``) and fires NO gap-closing retrieval, so a tail facet
missed on retrieval pass one stays missed. Coverage never closes on general questions.

THE FIX (retrieval-frontier half): derive a per-task facet checklist from R1's facet tree
(``expert_facet_planner``), measure which facets the ACCUMULATED corpus actually covers, and fire
targeted expansion queries for the UNCOVERED facets — repeating until the source yield stops growing
(a SATURATION stop keyed to new-distinct-source fraction, NOT a fixed count / breadth target). This
turns a vacuous general-task completeness check into a genuine coverage-closing loop keyed to the
task's own facets.

SCOPE NOTE (parallel-safety): the group note pins this GROUP to ``retrieval/`` ONLY, so this half of
R2 lives at the FS-Researcher retrieval frontier (``fs_researcher_query_gen`` wires it in) and
``nodes/completeness_checker.py`` is left UNTOUCHED. The facet checklist is genuinely a
retrieval-frontier mechanism — it drives expansion RETRIEVAL. If the completeness NODE's own
``expand_queries`` path should also consume this checklist, that is a CORE/integration follow-up.

DNA (§-1.3): coverage loop keyed to the task's own facets. It ADDS on-topic expansion queries only;
it DROPS ZERO sources; it touches no faithfulness gate. The saturation stop and the max-rounds bound
are compute-SAFETY bounds keyed to source YIELD — never a breadth number. Default OFF
(``PG_FACET_COMPLETENESS``) => the FS-Researcher path is byte-identical to today.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from src.polaris_graph.retrieval.expert_facet_planner import Facet

# (research_question, **kw) -> LiveRetrievalResult (has ``.evidence_rows``). Injected — same contract
# as ``fs_researcher_query_gen.PerQueryRetrieveFn`` so the loop is unit-testable on a stub.
PerQueryRetrieveFn = Callable[..., Any]

_STOPWORDS = frozenset(
    "the a an of to in on for and or but with without within into over under about across "
    "is are was were be been being as by at from this that these those it its their his her "
    "how what why when where which who whom whose than then also more most less least very "
    "impact effect role between among during recent trends over time change how it works "
    "mechanism drivers who affected stakeholders criticism limitations counter evidence dissent "
    "regional differences countries".split()
)


def facet_completeness_enabled() -> bool:
    """True iff the R2 facet-checklist expansion loop is flag-enabled (default OFF = legacy).

    LAW VI env kill-switch. Default OFF keeps the FS-Researcher path byte-identical; the tests
    exercise the ON path explicitly.
    """
    return os.getenv("PG_FACET_COMPLETENESS", "0").strip() in ("1", "true", "True")


def _min_hits() -> int:
    """Min evidence rows matching a facet's keywords for the facet to count as covered (default 1)."""
    return max(1, int(os.getenv("PG_FACET_COVERAGE_MIN_HITS", "1")))


def _saturation_min_new_fraction() -> float:
    """Stop the expansion loop when a round's NEW distinct sources fall below this fraction of the
    corpus already gathered. A compute-safety SATURATION stop keyed to source YIELD — never a breadth
    count / target (§-1.3). Default 0.10 (a round adding <10% new sources is judged saturated)."""
    try:
        v = float(os.getenv("PG_FACET_SATURATION_MIN_NEW_FRACTION", "0.10"))
    except ValueError:
        v = 0.10
    return max(0.0, v)


def _max_expansion_rounds() -> int:
    """Hard compute-safety bound on expansion rounds (caps cost even if saturation never triggers).
    Not a breadth target — it bounds the loop UP-side. Default 4."""
    return max(1, int(os.getenv("PG_FACET_EXPANSION_MAX_ROUNDS", "4")))


def _content_tokens(text: str) -> set[str]:
    """Lower-cased content tokens (>=3 chars, stopword-filtered) of ``text``.

    Prefers ``query_decomposer._content_tokens`` (in-scope retrieval util) for consistency with the
    rest of the frontier; falls back to a local tokenizer if that import is unavailable.
    """
    try:
        from src.polaris_graph.retrieval.query_decomposer import _content_tokens as _ct
        toks = {t for t in _ct(text or "") if len(t) >= 3 and t not in _STOPWORDS}
        if toks:
            return toks
    except Exception:
        pass
    return {
        t.lower()
        for t in re.findall(r"[A-Za-z0-9][A-Za-z0-9\-]+", text or "")
        if len(t) >= 3 and t.lower() not in _STOPWORDS
    }


def _facet_keywords(facet: Facet) -> set[str]:
    """The facet's own subject keywords (from its NAME, not the generic angle-lens words).

    A facet counts as covered only when the corpus carries its SUBJECT — the angle-lens words
    (mechanism / stakeholder / temporal / ...) are stripped by the stopword set so a generic word
    can never spuriously mark a facet covered.
    """
    return _content_tokens(facet.name)


def _row_text(row: dict) -> str:
    return " ".join(
        str(row.get(k) or "") for k in ("statement", "direct_quote", "title", "snippet")
    )


@dataclass
class FacetCoverage:
    """Coverage of one facet against the accumulated corpus."""

    facet: Facet
    covered: bool
    hits: int
    matched_keywords: list[str] = field(default_factory=list)


def measure_facet_coverage(
    facets: list[Facet],
    evidence_rows: list[dict],
    *,
    min_hits: int | None = None,
) -> list[FacetCoverage]:
    """Measure which facets the ACCUMULATED corpus covers.

    A facet is covered iff at least ``min_hits`` evidence rows each contain at least one of the
    facet's SUBJECT keywords. Pure / no-network / no-LLM. This is the per-task facet checklist the
    plan calls for, replacing the vacuous clinical-only "0 of 0" on general tasks.
    """
    min_hits = min_hits or _min_hits()
    row_tokens = [_content_tokens(_row_text(r)) for r in (evidence_rows or [])]
    out: list[FacetCoverage] = []
    for facet in facets:
        kws = _facet_keywords(facet)
        if not kws:
            # A facet with no distinguishing subject token cannot be measured — treat as covered so
            # it never drives an unbounded expansion on an empty signal.
            out.append(FacetCoverage(facet=facet, covered=True, hits=0))
            continue
        hits = 0
        matched: set[str] = set()
        for toks in row_tokens:
            inter = kws & toks
            if inter:
                hits += 1
                matched |= inter
        out.append(
            FacetCoverage(
                facet=facet,
                covered=hits >= min_hits,
                hits=hits,
                matched_keywords=sorted(matched),
            )
        )
    return out


def uncovered_facets(coverage: list[FacetCoverage]) -> list[Facet]:
    """The facets not yet covered by the corpus (the expansion-loop work list)."""
    return [c.facet for c in coverage if not c.covered]


def _distinct_sources(rows: list[dict]) -> set[str]:
    out: set[str] = set()
    for r in rows or []:
        u = (r.get("source_url") or r.get("url") or "").strip()
        if u:
            out.add(u)
    return out


@dataclass
class FacetExpansionResult:
    """Outcome of the facet-driven expansion loop."""

    expansion_queries: list[str] = field(default_factory=list)
    results: list[Any] = field(default_factory=list)
    rounds_run: int = 0
    stop_reason: str = ""
    coverage_trace: list[int] = field(default_factory=list)  # uncovered-facet count per round


def run_facet_expansion(
    facets: list[Facet],
    seed_evidence_rows: list[dict],
    per_query_retrieve: PerQueryRetrieveFn,
    *,
    retrieve_kwargs: dict | None = None,
    min_hits: int | None = None,
    saturation_min_new_fraction: float | None = None,
    max_rounds: int | None = None,
    max_queries: int | None = None,
    already_issued: set[str] | None = None,
    retrieval_deadline_passed: Callable[[], bool] | None = None,
) -> FacetExpansionResult:
    """Fire expansion queries for UNCOVERED facets until the source yield saturates.

    Each round: (1) measure facet coverage against the accumulated corpus; (2) if every facet is
    covered, STOP (``all_covered``); (3) otherwise issue each uncovered facet's angle queries
    (skipping any already issued upstream) through the SAME production ``per_query_retrieve``,
    accumulate the new rows, and (4) STOP when the round's NEW distinct sources fall below
    ``saturation_min_new_fraction`` of the corpus so far (``yield_saturated``) or the compute-safety
    ``max_rounds`` bound is hit. Every new source flows through the UNCHANGED downstream
    (consolidation -> generation -> verify); this loop only decides WHICH queries to issue.

    ``retrieval_deadline_passed`` (optional) is the shared per-question retrieval wall predicate; when
    it returns True the loop stops issuing new rounds (WALL-03 parity with the FS-Researcher loop).
    ``max_queries`` (optional) is a compute-safety budget cap on the TOTAL expansion queries issued
    here (so the caller's overall FS-Researcher query budget is honoured) — a cost bound, never a
    breadth target. Returns the queries issued, the per-query results, and a coverage trace. Drops
    ZERO sources.
    """
    retrieve_kwargs = dict(retrieve_kwargs or {})
    min_hits = min_hits or _min_hits()
    sat = _saturation_min_new_fraction() if saturation_min_new_fraction is None else saturation_min_new_fraction
    max_rounds = max_rounds or _max_expansion_rounds()

    corpus: list[dict] = list(seed_evidence_rows or [])
    known_sources: set[str] = _distinct_sources(corpus)
    issued: set[str] = set(already_issued or set())

    queries_out: list[str] = []
    results_out: list[Any] = []
    trace: list[int] = []
    stop_reason = "max_rounds"

    for round_idx in range(max_rounds):
        if retrieval_deadline_passed is not None and retrieval_deadline_passed():
            stop_reason = "retrieval_wall"
            break
        coverage = measure_facet_coverage(facets, corpus, min_hits=min_hits)
        pending = uncovered_facets(coverage)
        trace.append(len(pending))
        if not pending:
            stop_reason = "all_covered"
            break

        # Issue the uncovered facets' angle queries (dedup against what upstream already issued).
        round_new_sources: set[str] = set()
        issued_this_round = 0
        for facet in pending:
            if retrieval_deadline_passed is not None and retrieval_deadline_passed():
                stop_reason = "retrieval_wall"
                break
            if max_queries is not None and len(queries_out) >= max_queries:
                stop_reason = "query_budget"
                break
            for q in facet.queries:
                if max_queries is not None and len(queries_out) >= max_queries:
                    stop_reason = "query_budget"
                    break
                key = q.lower()
                if key in issued:
                    continue
                issued.add(key)
                queries_out.append(q)
                issued_this_round += 1
                result = per_query_retrieve(research_question=q, **retrieve_kwargs)
                results_out.append(result)
                new_rows = list(getattr(result, "evidence_rows", None) or [])
                corpus.extend(new_rows)
                for u in _distinct_sources(new_rows):
                    if u not in known_sources:
                        round_new_sources.add(u)
            if stop_reason in ("query_budget", "retrieval_wall"):
                break
        if stop_reason in ("query_budget", "retrieval_wall"):
            break

        # No query left to issue for the uncovered facets -> frontier exhausted for them.
        if issued_this_round == 0:
            stop_reason = "frontier_exhausted"
            break

        # SATURATION stop keyed to source YIELD (never a breadth count): if this round added fewer
        # than `sat` * (corpus-so-far) NEW distinct sources, the frontier is saturated.
        prior = max(1, len(known_sources))
        known_sources |= round_new_sources
        new_fraction = len(round_new_sources) / prior
        if new_fraction < sat:
            stop_reason = "yield_saturated"
            break

    return FacetExpansionResult(
        expansion_queries=queries_out,
        results=results_out,
        rounds_run=len(trace),
        stop_reason=stop_reason,
        coverage_trace=trace,
    )
