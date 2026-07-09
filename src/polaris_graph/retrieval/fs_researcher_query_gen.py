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

import logging
import os
import re
import time
from typing import Any, Callable

logger = logging.getLogger("polaris_graph.fs_researcher_query_gen")

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


def _qgen_parallel_workers() -> int:
    """I-deepfix-001 Wave-3 (#1344): bounded-parallel worker count for the seed-frontier fan-out.

    Default 1 = SERIAL, byte-identical to the legacy per-query loop. >1 = a bounded ThreadPool over
    ``per_query_retrieve`` with an ORDER-STABLE merge. A compute-safety UP bound (LAW VI env cap
    ``PG_QGEN_PARALLEL_QUERIES``), never a breadth target — the SAME query set is issued, only
    concurrently. Fixes the measured throughput collapse where a serial per-query retrieval tail hit
    the retrieval wall and only ~3 of ~35 planned queries fired. §-1.3: additive orchestration; the
    frozen faithfulness engine is untouched. A bad value falls back to 1 (serial)."""
    try:
        return max(1, int(os.getenv("PG_QGEN_PARALLEL_QUERIES", "1")))
    except ValueError:
        return 1


def _issue_seed_frontier(
    seed_queries: list[str],
    seen_q: set[str],
    budget: int,
    per_query_retrieve: PerQueryRetrieveFn,
    retrieve_kwargs: dict,
    wall_passed: Callable[[], bool],
) -> tuple[list[str], list[Any], list[Any]]:
    """Issue up to ``budget`` unique, not-yet-seen seed queries (first-seen-wins, in seed order)
    through ``per_query_retrieve`` and return ``(issued_queries, results, corpus_rows)`` in seed order.

    ``seen_q`` is updated IN PLACE with exactly the issued queries. Serial + byte-identical to the
    legacy loop at ``PG_QGEN_PARALLEL_QUERIES=1``; bounded-parallel (order-stable merge) when >1.

    I-deepfix-001 Wave-3 (#1344): the parallel path selects the SAME deduped, budget-capped query set
    the serial scan would issue, dispatches them concurrently in a bounded ThreadPool, and merges the
    results back in seed order — so the issued query set + result order are identical to serial; only
    the wall-timing of a mid-frontier trip differs (the parallel dispatch issues the whole batch under
    one wall instead of dropping the tail to a serial-loop wall). §-1.3 additive: SAME queries, SAME
    ``per_query_retrieve`` chokepoint, SAME per-query result contract; drops zero sources; the frozen
    faithfulness engine is untouched.
    """
    issued: list[str] = []
    results: list[Any] = []
    corpus_rows: list[Any] = []

    workers = _qgen_parallel_workers()
    if workers <= 1:
        # SERIAL — byte-identical to the legacy per-query loop (wall + budget checked per iteration).
        for q in seed_queries:
            if len(issued) >= budget or wall_passed():
                break
            k = q.lower()
            if k in seen_q:
                continue
            seen_q.add(k)
            issued.append(q)
            result = per_query_retrieve(research_question=q, **retrieve_kwargs)
            results.append(result)
            corpus_rows.extend(list(getattr(result, "evidence_rows", None) or []))
        return issued, results, corpus_rows

    # PARALLEL — order-stable. Select the IDENTICAL query set the serial scan would issue (dedup +
    # budget), then issue concurrently and merge in seed order. The anti-dark fire marker is emitted at
    # EVERY return path below carrying the REALIZED ``issued`` count — I-deepfix-001 Wave-3b (#1344,
    # Codex P1.2): the prior single PRE-ISSUE marker logged ``selected=N`` BEFORE ``selected[0]`` was
    # issued, so a wall trip on ``selected[0]`` skipped ``_rest`` yet the log still read "fired N"
    # (INTENT, not realized ISSUE). ``selected`` is declared up-front so the marker is valid on the
    # wall-passed early return too.
    selected: list[str] = []

    def _emit_fanout_marker() -> None:
        # I-deepfix-001 Wave-3b (#1344): anti-dark liveness marker (Fable/Codex P1) — REALIZED-count
        # edition. Emitted ONLY on the >1 (parallel) path so the serial default stays byte-identical AND
        # the official run's log can DISTINGUISH serial from parallel-N — the exact seam where the "only
        # ~3 of ~35 queries fired" collapse was diagnosed. ``selected=`` is the pre-issue dedup count
        # (intent breadcrumb); ``issued=`` is the REALIZED fan-out the canary keys on, so a wall-tripped
        # 1-of-N now logs issued=1 (NOT selected=N). issued=0 (wall tripped before any seed /
        # all-duplicate / budget-0) is the eligible-yet-zero signal — NEVER gated on >0 (§-1.3: a wall
        # truncation is compute-safety, not a source drop). Structural presence + counts; the frozen
        # faithfulness engine is untouched.
        logger.info(
            "[activation] qgen_parallel_fanout: workers=%d selected=%d issued=%d",
            workers, len(selected), len(issued),
        )

    if wall_passed():
        _emit_fanout_marker()
        return issued, results, corpus_rows
    # I-deepfix-001 Wave-3 (#1344) — Codex P0 (no-drop / order-stable): dedup the SELECTION against a
    # LOCAL key set and mutate the shared ``seen_q`` ONLY as each query is actually ISSUED (mirroring
    # the serial loop, which adds to ``seen_q`` immediately before it retrieves). The prior code marked
    # EVERY ``selected`` query seen up-front; when the retrieval wall tripped on ``selected[0]`` the
    # un-issued ``_rest`` were skipped BUT stayed in ``seen_q``, so the downstream facet-completeness
    # expansion loop (which reads ``seen_q`` as ``already_issued``) could never re-issue them — a real
    # dropped-source breadth loss. Marking seen only on issue leaves the un-issued tail eligible for
    # re-issue, exactly as the serial path leaves it (§-1.3 no drop).
    _selected_keys: set[str] = set()
    for q in seed_queries:
        if len(selected) >= budget:
            break
        k = q.lower()
        if k in seen_q or k in _selected_keys:
            continue
        _selected_keys.add(k)
        selected.append(q)
    if not selected:
        _emit_fanout_marker()  # realized issued=0 (all-duplicate / budget-0): eligible-yet-zero (§-1.3)
        return issued, results, corpus_rows
    from concurrent.futures import ThreadPoolExecutor

    def _one(q: str) -> Any:
        return per_query_retrieve(research_question=q, **retrieve_kwargs)

    # RACE-SAFETY at the PRODUCTION call site (Fable P1): the injected ``per_query_retrieve`` closure
    # (``_iter_per_query_retrieve`` in run_honest_sweep_r3) attaches the layer-4 DOI ``seed_urls`` to
    # the FIRST call it sees via a check-then-set on shared state written for SERIAL calls. Under a
    # concurrent first batch several threads would each read ``done=False`` and re-fetch the SAME seed
    # PDFs — never DROPS a source (additive-safe, faithfulness-neutral) but burns paid fetches
    # nondeterministically and which query carries the seed becomes random. Bind the seed
    # DETERMINISTICALLY to the FIRST selected query by issuing it SERIALLY before the fan-out; the
    # remaining queries then dispatch in the bounded pool. The parallel path now attaches the seed to
    # exactly the query a serial run would (order-stable) — a strict throughput win, no shared-state race.
    _first_result = _one(selected[0])
    seen_q.add(selected[0].lower())  # Codex P0: mark seen ONLY on actual issue (like the serial loop)
    issued.append(selected[0])
    results.append(_first_result)
    corpus_rows.extend(list(getattr(_first_result, "evidence_rows", None) or []))
    _rest = selected[1:]
    # I-deepfix-001 Wave-3 (#1344) — retrieval-wall re-check (Codex P1): ``selected[0]`` above is
    # issued SERIALLY and can itself consume the shared retrieval wall. Mirror the serial loop's
    # per-iteration ``wall_passed()`` guard by re-checking BEFORE dispatching the remaining frontier;
    # otherwise a wall tripped by ``selected[0]`` would still launch the whole ``_rest`` batch past the
    # wall — violating the stated retrieval-wall bound (off-path execution/spend). Skipping ``_rest`` on
    # a passed wall is EXACTLY what the serial path does (its next iteration would ``break``), so this
    # never issues MORE than serial and coverage stays additive — the wall is the compute-safety bound,
    # not a source drop (§-1.3). OFF (workers<=1) is untouched: this branch is parallel-only.
    if _rest and not wall_passed():
        with ThreadPoolExecutor(max_workers=min(workers, len(_rest))) as _ex:
            _result_list = list(_ex.map(_one, _rest))
        for q, result in zip(_rest, _result_list):
            seen_q.add(q.lower())  # Codex P0: mark seen ONLY on actual issue (like the serial loop)
            issued.append(q)
            results.append(result)
            corpus_rows.extend(list(getattr(result, "evidence_rows", None) or []))
    _emit_fanout_marker()  # realized issued count (serial-first + parallel-rest, or wall-tripped 1-of-N)
    return issued, results, corpus_rows


def _seed_angles_per_facet() -> int:
    """R2 (I-deepfix-001, #1344): how many PRIMARY angle queries per facet the SEED pass
    issues when the R2 facet-completeness expansion loop is ON.

    The seed pass issues the first ``_seed_angles_per_facet()`` angle(s) of every facet
    (breadth-first across ALL facets) and RESERVES each facet's remaining angle queries for
    the R2 completeness loop to fire ONLY on the facets the seed corpus leaves UNCOVERED.
    This is what makes the expansion loop non-vacuous: the prior code registered EVERY angle
    query as a seed, so :func:`facet_completeness.run_facet_expansion` (which draws from the
    SAME ``facet.queries``) always read "frontier exhausted" and issued zero expansion
    queries (the Codex/Fable P1).

    A compute-safety split (seed breadth first, then deepen only the gaps) — never a breadth
    target (§-1.3). Default 2. When R2 is OFF the full angle frontier is seeded (no reserve
    carve), so the R1-only path is unchanged in query count."""
    try:
        return max(1, int(os.getenv("PG_EXPERT_FACET_SEED_ANGLES", "2")))
    except ValueError:
        return 2


def _breadth_first_seeds(facets: list[Any], angle_limit: "int | None") -> list[str]:
    """Order the facets' angle queries BREADTH-FIRST (angle-major): every facet's angle-0
    before any facet's angle-1, and so on.

    Spreads the seed query budget across ALL facets first — fixing the measured "only 7 of
    35 facets seeded" starvation where a facet-major seed drained the whole budget on the
    first few facets and later facets were never queried. When ``angle_limit`` is set (R2
    on), only the first ``angle_limit`` angle(s) per facet are seeded so each facet's
    remaining angles stay a RESERVE for the R2 expansion loop; ``angle_limit=None`` (R2 off)
    seeds the full angle frontier so the R1-only path is unchanged in count. De-duplicates
    case-insensitively, order-preserving. Drops ZERO facets (§-1.3 — this only orders and
    splits the same query set)."""
    max_a = max((len(getattr(f, "queries", []) or []) for f in facets), default=0)
    if max_a <= 0:
        return []
    # Leave >= 1 reserve angle per facet when R2 is on (clamp so a small angle count can
    # never accidentally seed every angle and re-starve the expansion loop).
    if angle_limit is None:
        limit = max_a
    else:
        limit = min(max(1, angle_limit), max(1, max_a - 1))
    seeds: list[str] = []
    seen: set[str] = set()
    for a in range(min(limit, max_a)):
        for f in facets:
            qs = getattr(f, "queries", []) or []
            if a < len(qs):
                q = qs[a]
                k = q.lower()
                if k not in seen:
                    seen.add(k)
                    seeds.append(q)
    return seeds


# R5 (I-deepfix-001, #1344): display names for the target languages, for the
# production translator prompt. Code -> human name so the LLM translates reliably.
_LANG_DISPLAY: dict[str, str] = {
    "zh": "Chinese", "ja": "Japanese", "ko": "Korean", "ru": "Russian",
    "ar": "Arabic", "fr": "French", "de": "German", "es": "Spanish",
}


def _multilingual_native_reserve() -> int:
    """R5 (I-deepfix-001, #1344): the minimum number of native-language queries
    GUARANTEED a slot within the FS-Researcher query budget on a multilingual task.

    Without this, the multilingual additions are appended AFTER every English seed,
    so a wide English R1 frontier (e.g. 12 facets x 5 angles = 60 seeds) fills the
    whole ``PG_QGEN_FS_RESEARCHER_MAX_QUERIES`` budget and NO native-language query
    is ever issued — the corpus stays English-only on a zh task (the Codex/Fable P1).

    This is a language-ROUTING guarantee (ensure the task's OWN language is actually
    queried), NOT a breadth target (§-1.3): it reorders the SAME query set so a
    bounded slice of native queries lands inside the budget; it adds no query and
    drops none. It is clamped so it can never displace more than half the English
    breadth. Env-driven `PG_MULTILINGUAL_QUERY_RESERVE` (default 6)."""
    try:
        return max(0, int(os.getenv("PG_MULTILINGUAL_QUERY_RESERVE", "6")))
    except ValueError:
        return 6


def _make_multilingual_translate_fn(
    llm: LlmFn,
    base_queries: list[str],
    non_english_langs: tuple[str, ...],
) -> "Callable[[str, str], str] | None":
    """Build a bounded, memoized ``(english_query, lang) -> translated_query`` using
    the injected GLM policy, so an EXPLICIT-language task ('Answer in Chinese') with
    an all-ASCII English body actually emits native-language queries on the production
    path (the Codex P1). The question carries no native script there, so a true
    translation is the ONLY source of a native query.

    Cost is bounded to ONE ``llm`` call per target language (the whole seed batch is
    translated in a single call, not one call per query), memoized. Best-effort: any
    exception or empty / echo reply yields no translation for that query, and the
    module simply skips it — the faithfulness engine is never touched (this only
    decides WHICH queries are searched). Returns ``None`` when translation is
    unavailable (no ``llm`` / no seed queries / no target language)."""
    if llm is None or not base_queries or not non_english_langs:
        return None
    _cache: dict[str, dict[str, str]] = {}

    def _batch(lang: str) -> dict[str, str]:
        if lang in _cache:
            return _cache[lang]
        mapping: dict[str, str] = {}
        try:
            numbered = "\n".join(f"{i + 1}. {q}" for i, q in enumerate(base_queries))
            lang_name = _LANG_DISPLAY.get(lang, lang)
            prompt = (
                f"Translate each of these web-search queries into {lang_name}. "
                "Output ONE translation per line, numbered to match the input, "
                "the translation only with no commentary or transliteration.\n\n"
                f"{numbered}"
            )
            reply = llm(prompt) or ""
            lines = _lines(reply, cap=len(base_queries) + 2)
            for eng, translated in zip(base_queries, lines):
                t = " ".join((translated or "").split()).strip()
                if t and t.lower() != (eng or "").strip().lower():
                    mapping[(eng or "").strip().lower()] = t
        except Exception:  # noqa: BLE001 — translation is best-effort, never fatal
            mapping = {}
        _cache[lang] = mapping
        return mapping

    def _translate(query: str, lang: str) -> str:
        return _batch(lang).get((query or "").strip().lower(), "")

    return _translate


def _reserve_native_within_budget(
    english_seeds: list[str],
    native_additions: list[str],
    max_queries: int,
) -> list[str]:
    """Reorder the seed queries so a bounded slice of native-language queries is
    GUARANTEED to fall inside the first ``max_queries`` issued positions.

    The R5 expansion appends native queries after every English seed; the seed issue
    loop stops at ``max_queries``; so a wide English frontier starves the native
    queries out entirely (Codex/Fable P1). This reorders — never drops — the SAME
    query set: it keeps an English-breadth head, then the reserved native queries
    (so they issue within budget), then the English tail and any leftover native
    queries (issued only if budget remains). English-only tasks (empty
    ``native_additions``) are byte-identical (returns ``english_seeds`` unchanged).

    §-1.3: a language-routing reorder, not a cap/target — every query is preserved;
    only issue ORDER changes so the task's own language is actually queried."""
    if not native_additions:
        return list(english_seeds)
    # Never displace more than half the English breadth (both dimensions survive).
    reserve = min(len(native_additions), _multilingual_native_reserve(), max(1, max_queries // 2))
    if reserve <= 0:
        return list(english_seeds) + list(native_additions)
    reserved_native = native_additions[:reserve]
    leftover_native = native_additions[reserve:]
    head_len = max(0, max_queries - reserve)
    english_head = english_seeds[:head_len]
    english_tail = english_seeds[head_len:]
    return english_head + reserved_native + english_tail + leftover_native


def _scope_anchored() -> bool:
    """I-deepfix-001 (#1344): True iff sub-query generation anchors each derived query to the
    ORIGINAL research question's scope. Default ON.

    Fixes the observed drift (drb_72 v2): a bare sub-topic like 'manufacturing and supply chain
    automation' was searched WITHOUT the question's 'AI + labor market' framing, so the search
    generalised into the sub-topic's broad field (industrial-automation engineering) and pulled
    ~500 off-topic + predatory-journal results into the corpus. Carrying the research question
    into both the TOC-deconstruction and the per-todo query-derivation keeps every sub-query
    on-subject.

    Faithfulness-neutral: this changes ONLY which sources are SEARCHED (more on-topic); it does
    not touch tiering, verification, citation, or any faithfulness gate, and drops ZERO fetched
    sources (§-1.3 — this is retrieval SCOPING of the query, not a filter/cap on results).
    OFF (``0``/``false``) => byte-identical legacy prompts."""
    return os.getenv("PG_FS_RESEARCHER_SCOPE_ANCHOR", "1").strip() not in ("0", "false", "False")


def _landmark_expander_enabled() -> bool:
    """I-deepfix-001 Wave-3 (#1344): env gate for the in-window landmark-study expander, read WITHOUT
    importing ``landmark_study_expander`` so a flag-OFF run NEVER imports that module — the expert-facet
    qgen path is byte-identical even if the module were absent/broken (Codex/Fable Wave-3 P0
    defense-in-depth: a commit assembled from the diff alone must not ModuleNotFoundError the OFF path).
    Mirrors ``landmark_study_expander.landmark_study_expansion_enabled`` exactly (default OFF; accepts
    ``1``/``true``/``on``/``yes``)."""
    return os.getenv("PG_LANDMARK_EXPANDER", "0").strip().lower() in ("1", "true", "on", "yes")


# GENERAL stance / view-diversification frames. Each is a short, TOPIC-AGNOSTIC lens phrase appended to
# a planned facet + the question's own scope anchor, so a good report on ANY contested topic is searched
# from multiple viewpoints (supporting / opposing / challenges / opportunities). This is a GENERAL
# deep-research technique — NO benchmark study title, country, or topic is baked in; the lens words are
# generic stance vocabulary only. The tuple is a FIXED small template set (not a tunable cap/target): the
# lane introduces ZERO new cap/threshold — its size is intrinsic to these four generic frames.
_STANCE_FRAMES: tuple[tuple[str, str], ...] = (
    ("support", "benefits positive evidence supporting arguments"),
    ("oppose", "risks criticism negative evidence opposing arguments"),
    ("challenge", "challenges limitations obstacles concerns"),
    ("opportunity", "opportunities mitigations policy responses solutions"),
)


def _stance_diversify_enabled() -> bool:
    """Env gate for the GENERAL stance/view-diversification seed lane, read WITHOUT importing anything so a
    flag-OFF run NEVER perturbs the query-gen path — byte-identical (the lane is simply skipped). Default
    OFF; accepts ``1``/``true``/``on``/``yes``. Read at CALL time (LAW VI). Mirrors
    ``_landmark_expander_enabled`` exactly."""
    return os.getenv("PG_STANCE_DIVERSIFY_SEEDS", "0").strip().lower() in ("1", "true", "on", "yes")


def _stance_diversify_seeds(facets: list[Any], question: str) -> list[str]:
    """Build the GENERAL stance-diversified query frontier for the planned facets.

    For each facet, emit one query per generic STANCE frame (supporting / opposing / challenges /
    opportunities), each = ``{facet} {stance lens} {question anchor}`` — the facet supplies the
    sub-topic, the stance lens supplies the viewpoint, and the anchor (reused from the sibling
    expert-facet planner) keeps the query inside the question's subject so it cannot generalise into the
    facet's broad field (the same scope-anchor discipline R1/landmark use). Deterministic (no LLM), $0.
    Ordered, case-insensitively de-duplicated. Returns ``[]`` when there are no facets.

    GENERAL, no benchmark-gaming: the stance lens words are topic-agnostic templates — no study title /
    country / benchmark topic is baked in. §-1.3: this ADDS on-topic queries only; it DROPS ZERO sources
    and CAPS NOTHING (no target count, no per-facet cap knob — the frontier size emerges from the fixed
    four frames x the facets); every emitted query still routes through the UNCHANGED per_query_retrieve
    + the frozen faithfulness engine — a stance query that finds nothing verifiable contributes nothing.
    """
    from src.polaris_graph.retrieval import expert_facet_planner as _efp
    anchor = _efp._question_anchor(question)
    out: list[str] = []
    seen: set[str] = set()
    for f in facets:
        name = (getattr(f, "name", "") or "").strip()
        if not name:
            continue
        for _label, lens in _STANCE_FRAMES:
            q = re.sub(r"\s+", " ", f"{name} {lens} {anchor}").strip()
            if not q:
                continue
            key = q.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(q)
    return out


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


def _is_status_leak(text: str, question: str) -> bool:
    """I-qgen-001 (#1373): True iff ``text`` is (or embeds) a validator/status message
    ("Temporal constraint violation: ...", "Insufficient pre-June ...", "Lack of
    specific ...") rather than a research sub-topic/query. Uses the SHARED
    ``is_meta_status_clause`` predicate the retrieval-side scope validator runs, so
    both legs share one classifier; the question text is the subject-exemption
    source (a marker the operator themselves wrote is genuine subject, not a leak).
    ``PG_QUERY_META_STATUS_SCREEN=0`` kill-switch => always False (byte-identical)."""
    from src.polaris_graph.retrieval.scope_query_validator import (  # noqa: PLC0415
        is_meta_status_clause,
        meta_status_screen_enabled,
    )
    return meta_status_screen_enabled() and is_meta_status_clause(text, question)


def _screen_status_lines(items: list[str], question: str) -> list[str]:
    """I-qgen-001 (#1373) channel separation: drop validator/status prose from an
    LLM-derived sub-topic (todo) list so a validation RESULT can never occupy the
    SUB-TOPIC {topic} slot of the query-derivation prompt (drb_72 ev_1091: the leak
    was interpolated into '... regarding the impact of Temporal constraint
    violation: The research question requires literature' and searched). A
    validation message is control-flow — the affected round's facet is ABORTED
    (dropped from the todo queue), never pasted into query text. Faithfulness-
    neutral: pre-fetch query channel only; drops ZERO fetched sources (§-1.3)."""
    kept = [s for s in items if not _is_status_leak(s, question)]
    n_dropped = len(items) - len(kept)
    if n_dropped:
        logger.info(
            "[fs_researcher] I-qgen-001 (#1373) status-leak screen dropped %d "
            "validator/status line(s) from the sub-topic queue "
            "(a validation message is never a query topic).",
            n_dropped,
        )
    return kept


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


def _plan_expert_facet_queries(
    question: str,
    llm: LlmFn,
    per_query_retrieve: PerQueryRetrieveFn,
    *,
    max_queries: int | None = None,
    retrieve_kwargs: dict | None = None,
    retrieval_deadline_monotonic: "float | None" = None,
) -> tuple[list[str], list[Any]]:
    """R1+R2 (I-deepfix-001, #1344) facet-driven frontier: seed queries from the expert-facet tree,
    issue them directly, then (when R2 is enabled) run the facet-completeness expansion loop over the
    UNCOVERED facets until the source yield saturates. Returns (queries_issued, per_query_results),
    the SAME contract as ``plan_fs_researcher_queries``.

    R1 widens the frontier (facet x angle, scope-anchored) — the largest single DRB-II recall lever.
    R2 keys the completeness/expansion loop to the TASK's own facets so a general (non-clinical) task
    no longer reads a vacuous "0 of 0" and fires real gap-closing retrieval. Both ADD on-topic queries
    only and DROP ZERO sources; the FS-Researcher ``max_queries`` cap (compute-safety) still bounds
    cost; the R2 saturation stop is yield-keyed, never a breadth count (§-1.3).
    """
    from src.polaris_graph.retrieval import expert_facet_planner as _efp
    from src.polaris_graph.retrieval import facet_completeness as _fc

    max_queries = max_queries or _max_queries()
    retrieve_kwargs = dict(retrieve_kwargs or {})

    queries: list[str] = []
    results: list[Any] = []
    seen_q: set[str] = set()
    corpus_rows: list[dict] = []

    _deadline = retrieval_deadline_monotonic
    # I-deepfix-001 Wave-3 (#1344): seconds of wall-time consumed by the ADDITIVE landmark-study
    # planning lane, credited BACK to the wall so that lane rides OUTSIDE the baseline retrieval budget
    # and never displaces a baseline query (Codex/Fable P1 "or add budget"). A mutable box so the nested
    # ``_wall_passed`` reads the running total; it stays 0.0 (byte-identical) unless the landmark lane fires.
    _extra_lane_credit = [0.0]

    def _wall_passed() -> bool:
        _d = _deadline
        if _d is not None and _extra_lane_credit[0]:
            _d = _d + _extra_lane_credit[0]
        return _retrieval_deadline_passed(_d)

    if _wall_passed():
        return queries, results

    # R1: build the facet tree (one bounded LLM call) and its scope-anchored angle queries.
    facets = _efp.plan_expert_facets(question, llm)
    # I-deepfix-001 Wave-3a (#1344): expert-facet-planner ACTIVATION fire marker. Emitted ONLY when
    # PG_EXPERT_FACET_PLANNER is ON (this whole facet path is reached only under the flag; the guard keeps
    # the marker OFF byte-identical even if a test drives this helper directly). facets=0 with the flag ON
    # is the eligible-yet-zero (degenerate-LLM-reply) signal. Structural presence + count (§-1.3).
    if _efp.expert_facet_enabled():
        logger.info("[activation] expert_facet_planner: facets=%d", len(facets))

    # R1+R2 seed/reserve split (I-deepfix-001, #1344). Seed BREADTH-FIRST (every facet's
    # primary angle before any facet's deeper angle) so the query budget spreads across ALL
    # facets — fixing the measured "only 7 of 35 facets seeded" starvation. When the R2
    # completeness loop is ON, seed only the first `_seed_angles_per_facet()` angle(s) per
    # facet and RESERVE each facet's remaining angles for the R2 expansion loop to fire on
    # the facets the seed corpus leaves UNCOVERED. The prior code registered EVERY angle as a
    # seed, so `run_facet_expansion` (drawing from the SAME `facet.queries`) always read
    # "frontier exhausted" and issued ZERO expansion queries — the Codex/Fable P1. When R2 is
    # OFF the full angle frontier is seeded (the R1-only path is unchanged in count).
    _r2_on = _fc.facet_completeness_enabled()
    _seed_angle_limit = _seed_angles_per_facet() if _r2_on else None
    seed_queries = _breadth_first_seeds(facets, _seed_angle_limit)

    # R5 (I-deepfix-001, #1344): multilingual / cross-lingual frontier. On a
    # non-English (e.g. zh) DRB-II task the English facet queries never reach the
    # native-language primaries; detect the task's language profile and ADD
    # on-language queries (English stays first + unchanged) so a native-language
    # source and its English paraphrase land in the SAME multi-backend retrieval,
    # cross-lingually reranked into one consolidation basket. English-only tasks
    # are byte-identical (the expansion returns the seeds unchanged); default-ON,
    # OFF via PG_MULTILINGUAL_RETRIEVAL. §-1.3: adds on-language queries only,
    # drops ZERO sources, touches no faithfulness gate.
    from src.polaris_graph.retrieval import language_profile as _lp
    if _lp.multilingual_enabled():
        _profile = _lp.detect_language_profile(question)
        if _profile.is_multilingual:
            # Inject a production translator wrapping the GLM policy so an EXPLICIT
            # -language task (all-ASCII English body + "Answer in Chinese") — which has
            # no native script to carry — still emits real native-language queries.
            _translate_fn = _make_multilingual_translate_fn(
                llm, list(seed_queries), _profile.non_english
            )
            _expanded = _lp.expand_queries_for_profile(
                seed_queries, _profile, question, translate_fn=_translate_fn
            )
            # Separate the native additions from the English seeds, then RESERVE a
            # bounded slice of native queries inside the query budget so a wide English
            # R1 frontier cannot starve the task's own language out of the issued set.
            _eng_keys = {(q or "").strip().lower() for q in seed_queries}
            _native_adds = [
                q for q in _expanded if (q or "").strip().lower() not in _eng_keys
            ]
            seed_queries = _reserve_native_within_budget(
                list(seed_queries), _native_adds, max_queries
            )

    # R2 entity-qgen (I-deepfix-001, #1344): STORM-style sub-entity + perspective query expansion.
    # The abstract facet frontier names sub-TOPICS x analytical angles but never the concrete NICHE
    # sub-entities a DRB-II rubric names (specific occupations / sectors / demographic groups), so
    # their profession-specific primaries are never fetched and the corpus stays canonical-only. This
    # AUGMENTS (does not replace) the frontier: ONE bounded LLM call enumerates the named sub-entities
    # + deterministic STORM-style disciplinary perspective lenses, each scope-anchored to the question
    # so it cannot drift off-subject, and the bounded sub-entity slice is ADDED ON TOP of the FULL
    # baseline frontier — the effective query budget is RAISED by the added slice so the sub-entity
    # queries never SWAP OUT a baseline query (the Codex/Fable iter-1 REVISE). Every discovered source
    # flows through the UNCHANGED per_query_retrieve + frozen faithfulness engine — NEVER auto-trusted.
    # Default OFF (PG_SUBENTITY_QUERY_EXPANSION) => byte-identical. §-1.3: adds on-topic queries only,
    # drops ZERO sources, touches no faithfulness gate.
    #
    # Placed AFTER the R5 block (Codex/Fable iter-2 P1 fix). When R2 ran BEFORE R5 it lengthened
    # `seed_queries` first, and `language_profile.expand_queries_for_profile` caps its native-language
    # additions at max(PG_MULTILINGUAL_MAX_QUERIES, len(base)); once the R2 slice pushed `base` over
    # that cap the native-language queries a flag-OFF run WOULD issue were DROPPED — breaking the §-1.3
    # strict-superset on non-English (e.g. zh) tasks. Running R5 first means R5 expands the PRE-R2
    # baseline — the IDENTICAL input the flag-OFF path expands — into `seed_queries` (English + reserved
    # native). `widen_with_sub_entities` then keeps that whole R5-expanded window at the front and only
    # RAISES the budget by the sub-entity slice, so the flag-ON issued set is a strict SUPERSET of the
    # flag-OFF set: every native-language query is STILL issued (zero dropped) AND the sub-entity queries
    # are added. The sub-entity queries are English scope-anchored and route through the unchanged fetch
    # un-translated — option-(b): R5 native widening + R2 sub-entity widening both land on the budget;
    # translating the sub-entity slice is deliberately NOT done (it would complicate the superset for no
    # required gain). Dedup is against the CURRENT (R5-expanded) frontier so no query is issued twice.
    from src.polaris_graph.retrieval import sub_entity_query_expander as _sqe
    if _sqe.sub_entity_expansion_enabled() and not _wall_passed():
        _sub_qs = _sqe.plan_sub_entity_queries(question, llm)
        _new_sub_count = 0
        if _sub_qs:
            _seed_keys = {(q or "").strip().lower() for q in seed_queries}
            _new_sub = [q for q in _sub_qs if (q or "").strip().lower() not in _seed_keys]
            _new_sub_count = len(_new_sub)
            if _new_sub:
                seed_queries, max_queries = _sqe.widen_with_sub_entities(
                    list(seed_queries), _new_sub, max_queries
                )
        # I-deepfix-001 Wave-3a (#1344): sub-entity-expansion ACTIVATION fire marker. Emitted ONLY inside
        # this PG_SUBENTITY_QUERY_EXPANSION-gated block => OFF byte-identical. expanded_queries = the NET
        # NEW sub-entity queries added on top of the current frontier (0 = LLM named none / all duplicates,
        # the eligible-yet-zero signal). Structural presence + count (§-1.3).
        logger.info("[activation] subentity_query_expansion: expanded_queries=%d", _new_sub_count)

    # COV-C landmark-study expander (I-deepfix-001 Wave-3, #1344): the abstract facet + sub-entity
    # frontier never names the LANDMARK empirical studies / RCTs / seminal datasets central to the
    # question (the question carries no author names), so the empirical CORE stays absent. ONE bounded
    # LLM call enumerates the IN-WINDOW landmark studies (constrained to the question's stated
    # publication ceiling `date_end_iso` so a "before June 2023" question seeds the pre-print /
    # working-paper version, NEVER a later re-publication) and each scope-anchored query is ADDED ON
    # TOP of the FULL baseline frontier — the budget is RAISED by the added slice so a landmark query
    # never SWAPS OUT a baseline query (mirrors sub_entity). Every discovered source flows through the
    # UNCHANGED per_query_retrieve + frozen faithfulness engine — NEVER auto-trusted. Default OFF
    # (PG_LANDMARK_EXPANDER) => byte-identical. §-1.3: adds on-topic in-window queries only, drops ZERO
    # sources, touches no faithfulness gate.
    # The env flag is read via ``_landmark_expander_enabled()`` (reads PG_LANDMARK_EXPANDER directly,
    # NO import) so a flag-OFF run never imports ``landmark_study_expander`` — the OFF path is
    # byte-identical even if that module is absent/broken (Codex/Fable Wave-3 P0 defense-in-depth). The
    # module import is DEFERRED inside the guard for the same reason.
    if _landmark_expander_enabled() and not _wall_passed():
        _lm_t0 = time.monotonic()
        _new_lm_count = 0
        _lm_failed_open = False  # Wave-3b (#1344, Codex P1.1): distinguishes RAN-ok from FAIL-OPEN for the marker
        # I-deepfix-001 Wave-3 (#1344) — Codex/Fable P1 (additive-on-failure): the ENTIRE landmark lane
        # (deferred module import + window extraction + plan + widen) is FAIL-OPEN. If
        # ``landmark_study_expander`` is absent or broken, or its bounded LLM planning call raises, the
        # lane adds ZERO queries and qgen proceeds on the unchanged baseline frontier — it must NEVER
        # abort the whole query generation. This IS the additive / faithfulness-neutral contract: an
        # additive coverage lane can only ADD sources, so ANY failure degrades to the flag-OFF
        # (zero-added) behaviour, never a hard stop (§-1.3). Also directly covers the Wave-3 P0 concern
        # that the FORCE-ON path could ModuleNotFoundError at run time: a missing module now no-ops.
        try:
            from src.polaris_graph.retrieval import landmark_study_expander as _lse
            try:
                from src.polaris_graph.retrieval.intake_constraint_extractor import (
                    extract_constraints_regex as _extract_constraints_regex,
                )
                _window_end = _extract_constraints_regex(question).date_end_iso()
            except Exception:
                _window_end = None
            _lm_qs = _lse.plan_landmark_study_queries(question, llm, _window_end)
            if _lm_qs:
                _seed_keys = {(q or "").strip().lower() for q in seed_queries}
                _new_lm = [q for q in _lm_qs if (q or "").strip().lower() not in _seed_keys]
                _new_lm_count = len(_new_lm)
                if _new_lm:
                    seed_queries, max_queries = _lse.widen_with_landmark_studies(
                        list(seed_queries), _new_lm, max_queries
                    )
        except Exception:  # noqa: BLE001 — additive lane: any failure adds ZERO, never aborts qgen
            # I-deepfix-001 Wave-3b (#1344, Codex P1.1): a FAIL-OPEN landmark lane must NOT read as a
            # healthy fire. Set the degrade flag, emit a DISTINCT ``unavailable_failopen`` marker, and
            # SUPPRESS the positive ``expanded_queries=N`` marker on this path (below). The run_gate_b
            # landmark canary registers this degrade literal as an absent_marker, so a crashed/missing/
            # not-recovered expander is REJECTED as dark instead of passing as a healthy added-zero fire.
            # The lane STILL fails open (adds zero, never aborts qgen); only the LIVENESS LOG is made
            # honest — a lane that FAILED to run is no longer indistinguishable from one that RAN and
            # legitimately added zero (§-1.3 anti-dark, faithfulness-neutral).
            _lm_failed_open = True
            logger.warning(
                "[activation] landmark_study_expansion: unavailable_failopen (added 0)", exc_info=True
            )
            _new_lm_count = 0
        # Credit the landmark planning time BACK to the wall so this additive lane rides OUTSIDE the
        # baseline budget — the baseline seed frontier issued below (and the R2 completeness loop) get
        # the same wall time they would with the lane OFF, so no baseline query is displaced by the
        # landmark enumeration's inline LLM call (Codex/Fable P1 "or add budget").
        _extra_lane_credit[0] += max(0.0, time.monotonic() - _lm_t0)
        # I-deepfix-001 Wave-3 (#1344) landmark-expansion ACTIVATION fire marker, Wave-3b (Codex P1.1)
        # honesty split. Emitted ONLY inside this PG_LANDMARK_EXPANDER-gated block => OFF byte-identical,
        # and ONLY when the lane RAN successfully (``not _lm_failed_open``). expanded_queries = the NET
        # NEW in-window landmark queries added on top of the current frontier; 0 here means the expander
        # RAN and legitimately added zero (LLM named none / all duplicates / no in-window study) — the
        # ACCEPTED eligible-yet-zero signal (§-1.3). On the FAIL-OPEN path this positive marker is
        # SUPPRESSED and the ``unavailable_failopen`` degrade marker (above) fires instead, so the canary
        # can tell a lane that RAN-and-added-zero (accept) from one that FAILED-and-added-zero (reject as
        # dark). Structural presence + count.
        if not _lm_failed_open:
            logger.info("[activation] landmark_study_expansion: expanded_queries=%d", _new_lm_count)

    # GENERAL stance / view-diversification seed lane (default OFF, PG_STANCE_DIVERSIFY_SEEDS): a GENERAL
    # deep-research technique — a good report on ANY contested topic must cover multiple viewpoints. For
    # each planned facet ALSO issue a small set of queries framing the facet from distinct STANCES
    # (supporting / opposing / challenges / opportunities), each scope-anchored to the question. Generic
    # topic-agnostic templates only — NO study title / country / benchmark topic is baked in. UNLIKE the
    # sub-entity / landmark widen lanes this lane does NOT raise the budget: the net-new stance queries are
    # simply APPENDED to the seed frontier and compete for the SAME `max_queries` budget in the seed-issue
    # below — if the budget is already full they don't all fit (honest, never a raised cap to fit them).
    # De-duplicated against the CURRENT frontier here + against `seen_q` inside the seed-issue loop. §-1.3:
    # ADDS on-topic queries only, DROPS ZERO sources, CAPS/THINS/TARGETS NOTHING; every stance query routes
    # through the UNCHANGED per_query_retrieve + the FROZEN faithfulness engine — a stance query that finds
    # nothing verifiable simply contributes nothing (honest). FAIL-OPEN (Codex/Fable additive-on-failure):
    # any import/logic error adds ZERO queries and emits the DISTINCT `unavailable_failopen` degrade marker
    # — it NEVER aborts the host query-gen path. The healthy `issued=N` marker reports the REALIZED count of
    # net-new stance queries added to the frontier (0 = a legitimate ran-ok-zero — no facet / all duplicates
    # — and is ACCEPTED; NEVER gated on a count > 0, §-1.3). Default OFF => this block is skipped entirely =>
    # `seed_queries` unchanged => byte-identical.
    # Wave-6c (Codex P1): the healthy liveness marker is emitted AFTER _issue_seed_frontier below, keyed on the
    # REALIZED count of stance queries that ACTUALLY made it through the (deliberately-unraised) budget + dedup +
    # wall — NOT the pre-truncation appended count. Here we only APPEND the net-new stance queries + record their
    # keys so the realized count can be measured against the issued set.
    _stance_lane_active = False
    _stance_keys: set[str] = set()
    if _stance_diversify_enabled() and not _wall_passed():
        _stance_lane_active = True
        try:
            _stance_qs = _stance_diversify_seeds(facets, question)
            if _stance_qs:
                _seed_keys = {(q or "").strip().lower() for q in seed_queries}
                _new_stance = [q for q in _stance_qs if (q or "").strip().lower() not in _seed_keys]
                if _new_stance:
                    _stance_keys = {(q or "").strip().lower() for q in _new_stance}
                    # ADD ONLY — append to the frontier; `max_queries` is UNCHANGED (never raised to fit
                    # them), so the stance queries flow through the SAME budget-bounded seed-issue below
                    # (§-1.3: additive-only, no cap/target — if the budget is full they don't all fit).
                    seed_queries = list(seed_queries) + _new_stance
        except Exception:  # noqa: BLE001 — additive lane: any failure adds ZERO, never aborts qgen
            # A FAIL-OPEN stance lane must NOT read as a healthy fire: clear the active flag (SUPPRESSES the
            # positive issued= marker below) and emit the DISTINCT `unavailable_failopen` marker so the
            # run_gate_b activation canary (which registers the degrade literal as an absent_marker) REJECTS
            # the dark lane instead of passing it as a healthy added-zero. The lane STILL fails open (adds
            # zero, never aborts qgen); only the liveness LOG is made honest (§-1.3 anti-dark).
            _stance_lane_active = False
            _stance_keys = set()
            logger.warning(
                "[activation] stance_diversify_seeds: unavailable_failopen (added 0)", exc_info=True
            )

    # Issue the seed frontier (facet-angle queries are already full queries — no per-todo llm()
    # derivation needed). Record ONLY the queries ACTUALLY issued in the shared seen-set: a
    # budget-truncated seed stays eligible for the R2 loop, and the RESERVE angles (deliberately never
    # placed in `seed_queries`) stay OUT of `seen_q` so the expansion loop below can fire them for
    # still-uncovered facets. Bounded by the compute-safety query budget + the retrieval wall.
    # I-deepfix-001 Wave-3 (#1344): the fan-out is bounded-parallel when PG_QGEN_PARALLEL_QUERIES>1
    # (order-stable merge, SAME query set); serial + byte-identical at the default 1.
    _issued, _issued_results, _issued_rows = _issue_seed_frontier(
        seed_queries, seen_q, max_queries - len(queries),
        per_query_retrieve, retrieve_kwargs, _wall_passed,
    )
    queries.extend(_issued)
    results.extend(_issued_results)
    corpus_rows.extend(_issued_rows)

    # Wave-6c (Codex P1): emit the stance-lane liveness marker with the REALIZED issued count — how many
    # net-new stance queries ACTUALLY passed the (deliberately-unraised) budget + dedup + wall in
    # _issue_seed_frontier, counted from `_issued` (the verbatim issued queries), NOT the pre-truncation
    # appended count. Mirrors the qgen_parallel_fanout issued= contract. Suppressed on the fail-open path
    # (which logs unavailable_failopen instead). issued=0 is an honest ran-ok-zero — NEVER gated on >0 (§-1.3).
    if _stance_lane_active:
        _realized_stance = sum(1 for _q in _issued if (_q or "").strip().lower() in _stance_keys)
        logger.info("[activation] stance_diversify_seeds: issued=%d", _realized_stance)

    # R2: the facet-completeness expansion loop closes gaps on UNCOVERED facets until yield saturates.
    if _fc.facet_completeness_enabled() and facets and len(queries) < max_queries and not _wall_passed():
        expansion = _fc.run_facet_expansion(
            facets,
            corpus_rows,
            per_query_retrieve,
            retrieve_kwargs=retrieve_kwargs,
            max_queries=max_queries - len(queries),
            already_issued=seen_q,
            retrieval_deadline_passed=_wall_passed,
        )
        queries.extend(expansion.expansion_queries)
        results.extend(expansion.results)

    return queries, results


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

    # R1 (I-deepfix-001, #1344): when the LLM expert-facet planner is flag-enabled, seed the frontier
    # from the facet tree (sub-topics x mechanism/stakeholder/counter/temporal/geographic angles,
    # each scope-anchored) instead of the single one-query-per-sub-topic TOC. Default OFF => this
    # branch never runs and the legacy loop below is byte-identical (the tested path). Isolated in a
    # helper so the legacy body is untouched.
    from src.polaris_graph.retrieval import expert_facet_planner as _efp
    if _efp.expert_facet_enabled():
        return _plan_expert_facet_queries(
            question, llm, per_query_retrieve,
            max_queries=max_queries, retrieve_kwargs=retrieve_kwargs,
            retrieval_deadline_monotonic=retrieval_deadline_monotonic,
        )

    # index.md TOC: deconstruct the question into sub-topics (the todo queue).
    # I-deepfix-001 (#1344): keep every sub-topic scoped to the topic so it does not generalise
    # into its broad field (the drb_72 v2 drift). Default-ON; OFF => the legacy bare prompt.
    if _scope_anchored():
        _toc_prompt = (
            "Deconstruct this research topic into sub-topics (the index.md table of contents). "
            "Every sub-topic MUST stay within the scope of the topic — carry its subject, domain "
            "and key entities; do NOT generalise a sub-topic into its broad field. "
            "One sub-topic per line.\n\n" + question
        )
    else:
        _toc_prompt = (
            "Deconstruct this research topic into sub-topics (the index.md table of contents). "
            "One sub-topic per line.\n\n" + question
        )
    # I-qgen-001 (#1373): screen the TOC reply for validator/status prose BEFORE it
    # becomes the todo queue — a status line must never become a sub-topic.
    todos = _screen_status_lines(_lines(llm(_toc_prompt), cap=10), question) or [question]

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
            # I-deepfix-001 (#1344): carry the RESEARCH QUESTION into the query so a bare sub-topic
            # (e.g. 'manufacturing and supply chain automation') keeps the question's subject and
            # does not drift into its generic field. Default-ON; OFF => the legacy bare prompt.
            if _scope_anchored():
                raw = llm(
                    "Write ONE web-search query for the SUB-TOPIC below, kept STRICTLY within the "
                    "scope of the RESEARCH QUESTION (carry its subject, domain and key entities; do "
                    "NOT broaden the query into the sub-topic's generic field). Query only.\n\n"
                    f"RESEARCH QUESTION:\n{question}\n\nSUB-TOPIC:\n{todo}"
                )
            else:
                raw = llm("Write ONE search query for this sub-topic. Query only.\n\n" + todo)
            query = ""
            if raw and raw.strip():
                query = raw.strip().splitlines()[0].strip().strip('"').strip()
            if not query:
                query = todo
            # I-qgen-001 (#1373): if the DERIVED query itself is (or embeds) a
            # validator/status message — the derivation LLM can also emit one —
            # ABORT this facet's query instead of searching it. The todo-queue
            # screen above already keeps status prose out of the SUB-TOPIC slot;
            # this guards the derivation output channel too.
            if _is_status_leak(query, question):
                logger.info(
                    "[fs_researcher] I-qgen-001 (#1373) aborted a status-leak "
                    "query (validator message in the topic slot): %r",
                    query[:120],
                )
                continue
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
        # I-qgen-001 (#1373): the critic is the highest-risk status-leak channel — its
        # deficiency FINDINGS arrive phrased as validation verdicts ("Temporal constraint
        # violation: ...", "Insufficient pre-June ...", "Lack of specific ..."). Screen
        # them out so a verdict never becomes the next round's sub-topic; an all-status
        # reply empties `deficient` and the loop ABORTS the round (no corrupted search).
        deficient = _screen_status_lines(
            _lines(
                llm(
                    "Self-review the knowledge base against: exhaustive coverage (a question the KB "
                    "cannot fully answer?) and information density (any aspect with only 1-2 weak "
                    "sources?). List sub-topics still needing more search. One per line, or NONE.\n\n"
                    f"QUESTION:\n{question}\n\nNOTES:\n" + "\n".join(notes[-20:])
                ),
                cap=6,
            ),
            question,
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
