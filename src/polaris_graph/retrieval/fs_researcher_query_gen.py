"""FS-Researcher adaptive query generation for the production retrieval path.

I-recency-001 (#1296). FS-Researcher (arXiv 2602.01566) WON the recency-completion query-gen
re-bake-off under a positive-control-validated judge — balanced across axes (general drb_72
finding_coverage 0.561, clinical 3-slug avg 0.351), 2nd on BOTH and never weak. It SUPERSEDES
IterResearch, whose earlier "0.386" win did NOT reproduce on the validated judge (it scored 0.000
general / ~0.232 clinical = near-WORST). This wires FS-Researcher's PORTABLE scaffold into the
production sweep as the query generator, FLAG-GATED (PG_QGEN_FS_RESEARCHER; default OFF =>
byte-identical to the legacy template-facet path).

The method (arXiv 2602.01566, primary-source verified): build an index.md table-of-contents by
deconstructing the question into sub-topics (a todo queue); for each todo derive ONE search query,
retrieve, and fold the result in; then run a FIXED 6-item self-review checklist (exhaustive
coverage: 'a question the KB cannot fully answer?'; information density: 'an aspect with only 1-2
weak sources?') whose output becomes the next round's deficient todos. Repeat until the checklist
reports NONE or the query budget is exhausted.

FAITHFULNESS: this changes ONLY which queries are issued. Every query still flows through the
UNCHANGED `run_live_retrieval` (scope gate, tier classify, fetch, provenance), and the faithfulness
engine (strict_verify / NLI / 4-role / provenance) is never touched. The per-query retrieval
results are MERGED (dedup by source URL, evidence ids renumbered globally) into one
LiveRetrievalResult so downstream (consolidation -> generation -> verify -> render) sees the same
contract as today. Mirrors `iterresearch_query_gen.py` (`merge_retrieval_results` is identical).
"""

from __future__ import annotations

import os
import re
import time
from typing import Any, Callable

# (research_question, **kw) -> LiveRetrievalResult. Injected so this module never imports the
# 1000-line live_retriever at module load (and so it is unit-testable on a stub).
PerQueryRetrieveFn = Callable[..., Any]
# (prompt) -> text. The GLM-5.2 policy. Injected (async client wrapped to sync by the caller).
LlmFn = Callable[[str], str]


def fs_researcher_enabled() -> bool:
    """True iff the FS-Researcher query-gen path is flag-enabled (default OFF = legacy behaviour)."""
    return os.getenv("PG_QGEN_FS_RESEARCHER", "0").strip() in ("1", "true", "True")


def _max_queries() -> int:
    """Max search queries issued (the equal-budget cap the bake-off used). Caps cost."""
    return int(os.getenv("PG_QGEN_FS_RESEARCHER_MAX_QUERIES", "35"))


def _max_rounds() -> int:
    """Max outer todo-queue / checklist re-plan rounds."""
    return int(os.getenv("PG_QGEN_FS_RESEARCHER_MAX_ROUNDS", "6"))


def _lines(text: str, cap: int = 12) -> list[str]:
    """Parse an LLM reply into clean sub-topic / query line items (strip numbering/bullets)."""
    out: list[str] = []
    for raw in (text or "").splitlines():
        s = raw.strip()
        if not s:
            continue
        s = re.sub(r"^\s*(?:[-*]|\d+[.):])\s*", "", s).strip().strip('"').strip()
        if s and len(s) > 2 and not s.lower().startswith(("here", "sure", "the following")):
            out.append(s)
        if len(out) >= cap:
            break
    return out


def _retrieval_deadline_passed(deadline: "float | None") -> bool:
    """I-deepfix-001 WALL-03 (#1344): True iff the SHARED per-question retrieval wall
    (a monotonic instant anchored ONCE by the spine) has passed.

    Mirrors ``run_honest_sweep_r3._question_retrieval_deadline_passed`` byte-for-byte:
    pure ``time.monotonic()`` comparison against the ALREADY-anchored deadline (never
    re-reads the env — that would re-anchor the wall per call). STRICT ``>`` so the
    boundary instant itself is not yet 'passed'. ``deadline is None`` (the DEFAULT — the
    spine passes None when ``PG_RETRIEVAL_QUESTION_WALL_SECONDS`` is unset) => always
    ``False`` => the FS-Researcher loop is unbounded exactly as before (byte-identical).

    When set, the outer round-loop and the inner per-todo loop consult this so, once the
    wall passes, the loop STOPS issuing new GLM rounds (query-derivation + checklist
    critic — the rounds FIX-2's per-query-retrieve short-circuit does NOT cover) and
    returns the queries gathered so far. §-1.3: stops adding query rounds; drops NO
    gathered source; touches no faithfulness gate."""
    return deadline is not None and time.monotonic() > deadline


def _obs_digest(rows: list[dict], n: int = 3, chars: int = 160) -> str:
    """A short digest of the newest evidence rows (steers the checklist's gap analysis)."""
    parts = []
    for r in (rows or [])[:n]:
        txt = " ".join((r.get("statement") or r.get("direct_quote") or r.get("title") or "").split())[:chars]
        if txt:
            parts.append(txt)
    return " | ".join(parts)


def plan_fs_researcher_queries(
    question: str,
    llm: LlmFn,
    per_query_retrieve: PerQueryRetrieveFn,
    *,
    max_queries: int | None = None,
    max_rounds: int | None = None,
    retrieve_kwargs: dict | None = None,
    retrieval_deadline_monotonic: "float | None" = None,
) -> tuple[list[str], list[Any]]:
    """Run the FS-Researcher TOC/todo-queue + 6-item-checklist loop; return
    (queries_issued, per_query_results).

    index.md TOC: deconstruct the question into sub-topics (a todo queue). Each round: for every
    todo, derive ONE query and retrieve via the production `per_query_retrieve`; then a fixed 6-item
    self-review checklist (exhaustive coverage + information density) yields the deficient sub-topics
    that become the next round's todos. Stops on NONE or the query budget. Pure control flow over the
    injected llm/retrieve — no network or live_retriever import here.

    I-deepfix-001 WALL-03 (#1344): ``retrieval_deadline_monotonic`` is the SHARED per-question
    retrieval wall (anchored ONCE by the spine, ``None`` when the wall knob is unset). FIX-2 already
    short-circuits the per-query ``per_query_retrieve`` once the wall passes; but the adaptive GLM
    rounds — the TOC deconstruction, the per-todo query-derivation ``llm()``, and the 6-item checklist
    critic ``llm()`` — kept firing past the wall (the Codex iter-1 P1). When the deadline is set and
    has passed, the outer round-loop and the inner per-todo loop break, returning the queries gathered
    so far. ``None`` (default) => never trips => byte-identical. §-1.3: drops ZERO gathered queries /
    sources; the engine is untouched.
    """
    max_queries = max_queries or _max_queries()
    max_rounds = max_rounds or _max_rounds()
    retrieve_kwargs = dict(retrieve_kwargs or {})

    queries: list[str] = []
    results: list[Any] = []
    seen_q: set[str] = set()
    notes: list[str] = []

    # WALL-03: if the wall has ALREADY passed before the first GLM round, skip the loop
    # entirely (no TOC-deconstruction llm() either) and hand off the empty query set so the
    # spine merges the corpus gathered upstream rather than grinding the GLM TOC call.
    if _retrieval_deadline_passed(retrieval_deadline_monotonic):
        return queries, results

    # index.md TOC: deconstruct the question into sub-topics (the todo queue).
    todos = _lines(
        llm(
            "Deconstruct this research topic into sub-topics (the index.md table of contents). "
            "One sub-topic per line.\n\n" + question
        ),
        cap=10,
    ) or [question]

    for _ in range(max_rounds):
        if len(queries) >= max_queries or not todos:
            break
        # WALL-03: stop issuing NEW GLM rounds once the shared retrieval wall passes.
        if _retrieval_deadline_passed(retrieval_deadline_monotonic):
            break
        for todo in list(todos):
            if len(queries) >= max_queries:
                break
            # WALL-03: gate each per-todo query-derivation llm() too, so a wall that passes
            # mid-round (between todos) stops the very next GLM call rather than draining the
            # whole todo list.
            if _retrieval_deadline_passed(retrieval_deadline_monotonic):
                break
            raw = llm("Write ONE search query for this sub-topic. Query only.\n\n" + todo)
            query = ""
            if raw and raw.strip():
                query = raw.strip().splitlines()[0].strip().strip('"').strip()
            if not query:
                query = todo
            key = query.lower()
            if key in seen_q:  # do not waste budget re-issuing an identical query
                continue
            seen_q.add(key)
            queries.append(query)
            result = per_query_retrieve(research_question=query, **retrieve_kwargs)
            results.append(result)
            notes.append(f"[{todo[:50]}] {_obs_digest(getattr(result, 'evidence_rows', None) or [])}")
        if len(queries) >= max_queries:
            break
        # WALL-03: gate the 6-item checklist critic llm() — it is one of the two GLM rounds
        # the Codex iter-1 P1 flagged as still firing past the wall.
        if _retrieval_deadline_passed(retrieval_deadline_monotonic):
            break
        # 6-item self-review checklist critic -> deficient sub-topics become the next todos.
        deficient = _lines(
            llm(
                "Self-review the knowledge base against: exhaustive coverage (a question the KB "
                "cannot fully answer?) and information density (any aspect with only 1-2 weak "
                "sources?). List sub-topics still needing more search. One per line, or NONE.\n\n"
                f"QUESTION:\n{question}\n\nNOTES:\n" + "\n".join(notes[-20:])
            ),
            cap=6,
        )
        if not deficient or any("NONE" in d.upper() for d in deficient[:1]):
            break
        todos = deficient

    return queries, results


def merge_retrieval_results(results: list[Any], result_factory: Callable[..., Any]) -> Any:
    """Merge per-query LiveRetrievalResults into one, preserving the downstream contract.

    Identical to `iterresearch_query_gen.merge_retrieval_results` (Codex #1292 P1): every per-query
    run_live_retrieval restarts evidence rows at ``ev_000``, so rows MUST be RENUMBERED to globally
    unique ``ev_NNN`` on merge — otherwise the downstream ``{evidence_id: row}`` map collides and
    provenance/verification break. Also carries the full contract fields the benchmark gates read:
    ``journal_metadata_sidecar`` and ``corpus_truncated``, plus candidates_total/processed.
    """
    if not results:
        return result_factory(
            classified_sources=[], evidence_rows=[], total_candidates_pre_filter=0,
            candidates_kept_by_scope=0, candidates_kept_by_offtopic=0, candidates_fetched=0,
            candidates_failed_fetch=0, api_calls={}, notes=["fs_researcher: no rounds"],
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
    # fallback disclosure across the FS-Researcher merge so the winner-firing gate
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
    notes.append(f"fs_researcher: merged {len(results)} queries -> {len(ev_rows)} evidence rows (renumbered)")
    # I-deepfix-001 (#1344, winner-gate false-negative): carry the W5 content-relevance
    # telemetry through the merge. The per-query reports were DROPPED here (the I-deepfix-001
    # P1-2/P1-4 carry-through wired retrieval_wall_hit + semantic_relevance_fell_back but MISSED
    # this one) -> winner_firing_gate read retrieval.content_relevance=None and false-aborted
    # "the judge never ran" even though the reranker FIRED every round (scored/demoted real
    # passages). Carry a report whose reranker actually LOADED (reranker_device != 'unavailable'),
    # preferring the most comprehensive round (largest n_scored); if EVERY round's reranker failed
    # to load, carry an 'unavailable' report so the gate correctly marks W5 dark; None iff no round
    # produced a report. Telemetry/disclosure only — faithfulness-NEUTRAL (content_relevance is a
    # WEIGHT, never the faithfulness engine; §-1.3 no drop).
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
        # I-deepfix-001 (#1344): carry the merged W5 content-relevance telemetry so the
        # winner-firing gate sees the reranker fired (was dropped -> false-abort).
        content_relevance=merged_content_relevance,
    )


def run_fs_researcher_retrieval(
    question: str,
    llm: LlmFn,
    per_query_retrieve: PerQueryRetrieveFn,
    result_factory: Callable[..., Any],
    *,
    max_queries: int | None = None,
    max_rounds: int | None = None,
    retrieve_kwargs: dict | None = None,
    retrieval_deadline_monotonic: "float | None" = None,
) -> tuple[Any, list[str]]:
    """The production entry point: run the FS-Researcher loop over `per_query_retrieve` and return
    (merged LiveRetrievalResult, queries_issued). Faithful to the bake-off winner — each query goes
    through the SAME production retrieval; only query SELECTION is FS-Researcher.

    I-deepfix-001 WALL-03 (#1344): ``retrieval_deadline_monotonic`` is the SHARED per-question
    retrieval wall threaded from the spine; the adaptive GLM rounds stop firing once it passes
    (``None`` = default = byte-identical)."""
    queries, results = plan_fs_researcher_queries(
        question, llm, per_query_retrieve,
        max_queries=max_queries, max_rounds=max_rounds, retrieve_kwargs=retrieve_kwargs,
        retrieval_deadline_monotonic=retrieval_deadline_monotonic,
    )
    return merge_retrieval_results(results, result_factory), queries
