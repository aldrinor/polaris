"""IterResearch (Tongyi) adaptive query generation for the production retrieval path.

I-qgen-002 (#1292). IterResearch WON the I-qgen-001 (#1291) query-gen bake-off on DRB-II
info_recall coverage (0.386 vs the template-facet floor's 0.000). This wires its PORTABLE
scaffold — the report-centric workspace-RECONSTRUCTION loop — into the production sweep as the
query generator, FLAG-GATED (PG_QGEN_ITERRESEARCH; default OFF => byte-identical to the legacy
template-facet path).

The method (arXiv 2510.24701 / 2511.07327, primary-source verified): each round the policy sees
ONLY a minimal workspace = (question, an evolving free-text REPORT, the last action+observation) —
history is discarded (strategic forgetting, O(1) context). From that it derives the NEXT search
query, retrieves, folds the result into a rewritten report, and repeats. Queries are therefore
chosen from what is already established vs. still missing, re-derived each round from the report.

FAITHFULNESS: this changes ONLY which queries are issued. Every query still flows through the
UNCHANGED `run_live_retrieval` (scope gate, tier classify, fetch, provenance), and the faithfulness
engine (strict_verify / NLI / 4-role / provenance) is never touched. The per-round retrieval
results are MERGED (dedup by source URL) into one LiveRetrievalResult so downstream
(consolidation -> generation -> verify -> render) sees the same contract as today.
"""

from __future__ import annotations

import os
import re
from typing import Any, Callable
from src.polaris_graph.settings import resolve

# (research_question, **kw) -> LiveRetrievalResult. Injected so this module never imports the
# 1000-line live_retriever at module load (and so it is unit-testable on a stub).
PerQueryRetrieveFn = Callable[..., Any]
# (prompt) -> text. The GLM-5.2 policy. Injected (async client wrapped to sync by the caller).
LlmFn = Callable[[str], str]


def iterresearch_enabled() -> bool:
    """True iff the IterResearch query-gen path is flag-enabled (default OFF = legacy behaviour)."""
    return resolve("PG_QGEN_ITERRESEARCH").strip() in ("1", "true", "True")


def _max_rounds() -> int:
    """Max IterResearch rounds (= max distinct queries issued). Caps cost; default matches the
    bake-off's equal-budget regime."""
    return int(resolve("PG_QGEN_ITERRESEARCH_MAX_ROUNDS"))


def _obs_digest(rows: list[dict], n: int = 8, chars: int = 160) -> str:
    """A short digest of the newest evidence rows, fed back as the round's observation."""
    parts = []
    for r in (rows or [])[:n]:
        txt = " ".join((r.get("statement") or r.get("direct_quote") or r.get("title") or "").split())[:chars]
        if txt:
            parts.append(txt)
    return " | ".join(parts)


def plan_iterresearch_queries(
    question: str,
    llm: LlmFn,
    per_query_retrieve: PerQueryRetrieveFn,
    *,
    max_rounds: int | None = None,
    retrieve_kwargs: dict | None = None,
) -> tuple[list[str], list[Any]]:
    """Run the IterResearch workspace-reconstruction loop; return (queries_issued, per_round_results).

    Each round: the policy sees ONLY (question, evolving report, last action+observation), emits a
    rewritten REPORT (overwritten — strategic forgetting) + the next QUERY (or STOP), then that one
    query is retrieved via the production `per_query_retrieve`. The per-round LiveRetrievalResults
    are returned for the caller to merge. Pure control flow over injected llm/retrieve — no network
    or live_retriever import here.
    """
    max_rounds = max_rounds or _max_rounds()
    retrieve_kwargs = dict(retrieve_kwargs or {})
    report = ""
    last_obs = ""
    queries: list[str] = []
    results: list[Any] = []
    seen_q: set[str] = set()

    for _ in range(max_rounds):
        out = llm(
            "You are IterResearch. Your ONLY memory is the evolving RESEARCH REPORT below (all "
            "earlier history is discarded). Reason over (question, report, last observation): what "
            "is already established, what is still missing. Then output EXACTLY two blocks:\n"
            "REPORT: <a rewritten, compressed report retaining validated findings plus what you "
            "just learned>\n"
            "QUERY: <ONE next web-search query that targets the most important still-missing "
            "sub-topic, or the single word STOP if the report already covers the question>\n\n"
            f"QUESTION:\n{question}\n\nREPORT:\n{report or '(empty)'}\n\n"
            f"LAST OBSERVATION:\n{last_obs or '(none)'}"
        )
        new_report = ""
        query = ""
        m = re.search(r"REPORT:\s*(.*?)\s*QUERY:", out or "", re.S | re.I)
        if m:
            new_report = m.group(1).strip()
        mq = re.search(r"QUERY:\s*(.*)", out or "", re.S | re.I)
        if mq and mq.group(1).strip():
            query = mq.group(1).strip().splitlines()[0].strip().strip('"').strip()
        report = new_report or report  # OVERWRITE: strategic forgetting / O(1) workspace
        if not query or query.upper().startswith("STOP"):
            break
        key = query.lower()
        if key in seen_q:  # do not waste a round re-issuing an identical query
            continue
        seen_q.add(key)
        queries.append(query)
        result = per_query_retrieve(research_question=query, **retrieve_kwargs)
        results.append(result)
        last_obs = _obs_digest(getattr(result, "evidence_rows", None) or [])

    return queries, results


def merge_retrieval_results(results: list[Any], result_factory: Callable[..., Any]) -> Any:
    """Merge per-round LiveRetrievalResults into one, preserving the downstream contract.

    CRITICAL (Codex #1292 P1): every per-query run_live_retrieval restarts evidence rows at
    ``ev_000``, so the rows MUST be RENUMBERED to globally-unique ``ev_NNN`` on merge — otherwise the
    downstream ``{evidence_id: row}`` map collides and provenance/verification break. Also carries the
    full contract fields the benchmark gates read: ``journal_metadata_sidecar`` (journal-only mode
    filters on it — dropping it could empty the corpus) and ``corpus_truncated`` (fail-loud telemetry
    that must not be hidden), plus candidates_total/processed.
    """
    if not results:
        return result_factory(
            classified_sources=[], evidence_rows=[], total_candidates_pre_filter=0,
            candidates_kept_by_scope=0, candidates_kept_by_offtopic=0, candidates_fetched=0,
            candidates_failed_fetch=0, api_calls={}, notes=["iterresearch: no rounds"],
        )
    ev_rows: list[dict] = []
    seen_src_for_ev: set[str] = set()
    sources: list = []
    seen_src: set[str] = set()
    api_calls: dict[str, int] = {}
    notes: list[str] = []
    sidecar: dict = {}
    corpus_truncated = False
    # I-deepfix-001 P1-2 / P1-4 (#1344): carry the retrieval-wall + B4 semantic
    # fallback disclosure across the IterResearch merge so the winner-firing gate
    # and the manifest/report see them (OR-combine the booleans like corpus_truncated;
    # SUM the per-round counts like the other candidate counts).
    retrieval_wall_hit = False
    semantic_relevance_fell_back = False
    retrieval_queries_skipped = 0
    retrieval_candidates_unclassified = 0
    pre = kept_scope = kept_off = fetched = failed = 0
    cand_total = cand_processed = 0
    for r in results:
        for row in getattr(r, "evidence_rows", None) or []:
            url = (row.get("source_url") or "").strip()
            if url and url in seen_src_for_ev:  # dedup the same source across rounds
                continue
            if url:
                seen_src_for_ev.add(url)
            new_row = dict(row)
            new_row["evidence_id"] = f"ev_{len(ev_rows):03d}"  # RENUMBER globally-unique
            ev_rows.append(new_row)
        for src in getattr(r, "classified_sources", None) or []:
            url = (getattr(src, "url", "") or "").strip()
            if url and url in seen_src:
                continue
            if url:
                seen_src.add(url)
            sources.append(src)
        for k, v in (getattr(r, "api_calls", None) or {}).items():
            api_calls[k] = api_calls.get(k, 0) + int(v)
        notes.extend(getattr(r, "notes", None) or [])
        _sc = getattr(r, "journal_metadata_sidecar", None)
        if isinstance(_sc, dict):
            sidecar.update(_sc)  # keyed by canonical URL -> merge keeps all rounds' entries
        if getattr(r, "corpus_truncated", False):
            corpus_truncated = True
        if getattr(r, "retrieval_wall_hit", False):
            retrieval_wall_hit = True
        if getattr(r, "semantic_relevance_fell_back", False):
            semantic_relevance_fell_back = True
        retrieval_queries_skipped += int(getattr(r, "retrieval_queries_skipped", 0) or 0)
        retrieval_candidates_unclassified += int(
            getattr(r, "retrieval_candidates_unclassified", 0) or 0
        )
        pre += int(getattr(r, "total_candidates_pre_filter", 0) or 0)
        kept_scope += int(getattr(r, "candidates_kept_by_scope", 0) or 0)
        kept_off += int(getattr(r, "candidates_kept_by_offtopic", 0) or 0)
        fetched += int(getattr(r, "candidates_fetched", 0) or 0)
        failed += int(getattr(r, "candidates_failed_fetch", 0) or 0)
        cand_total += int(getattr(r, "candidates_total", 0) or 0)
        cand_processed += int(getattr(r, "candidates_processed", 0) or 0)
    notes.append(f"iterresearch: merged {len(results)} rounds -> {len(ev_rows)} evidence rows (renumbered)")
    # I-deepfix-001 (#1344, winner-gate false-negative): carry the W5 content-relevance
    # telemetry through the merge (twin of fs_researcher_query_gen). Dropping it made
    # winner_firing_gate read retrieval.content_relevance=None and false-abort "the judge
    # never ran" even though the reranker FIRED every round. Prefer a report whose reranker
    # LOADED (device != 'unavailable'), largest n_scored; if all failed, carry 'unavailable'
    # so the gate marks W5 dark; None iff no round produced one. Telemetry-only, faithfulness-NEUTRAL.
    _cr_reports = [
        c for c in (getattr(r, "content_relevance", None) for r in results)
        if isinstance(c, dict)
    ]
    _cr_loaded = [
        c for c in _cr_reports
        if str(c.get("reranker_device", "") or "").strip().lower() != "unavailable"
    ]
    merged_content_relevance = (
        max(_cr_loaded, key=lambda c: int(c.get("n_scored", 0) or 0)) if _cr_loaded
        else (_cr_reports[0] if _cr_reports else None)
    )
    return result_factory(
        classified_sources=sources, evidence_rows=ev_rows, total_candidates_pre_filter=pre,
        candidates_kept_by_scope=kept_scope, candidates_kept_by_offtopic=kept_off,
        candidates_fetched=fetched, candidates_failed_fetch=failed, api_calls=api_calls, notes=notes,
        corpus_truncated=corpus_truncated, candidates_total=cand_total,
        candidates_processed=cand_processed,
        journal_metadata_sidecar=(sidecar or None),
        # I-deepfix-001 P1-2 / P1-4 (#1344): merged retrieval-wall + B4 fallback disclosure.
        retrieval_wall_hit=retrieval_wall_hit,
        retrieval_queries_skipped=retrieval_queries_skipped,
        retrieval_candidates_unclassified=retrieval_candidates_unclassified,
        semantic_relevance_fell_back=semantic_relevance_fell_back,
        # I-deepfix-001 (#1344): carry the merged W5 content-relevance telemetry.
        content_relevance=merged_content_relevance,
    )


def run_iterresearch_retrieval(
    question: str,
    llm: LlmFn,
    per_query_retrieve: PerQueryRetrieveFn,
    result_factory: Callable[..., Any],
    *,
    max_rounds: int | None = None,
    retrieve_kwargs: dict | None = None,
) -> tuple[Any, list[str]]:
    """The production entry point: run the IterResearch loop over `per_query_retrieve` and return
    (merged LiveRetrievalResult, queries_issued). Faithful to the bake-off winner — each query goes
    through the SAME production retrieval; only query SELECTION is IterResearch."""
    queries, results = plan_iterresearch_queries(
        question, llm, per_query_retrieve, max_rounds=max_rounds, retrieve_kwargs=retrieve_kwargs
    )
    return merge_retrieval_results(results, result_factory), queries
