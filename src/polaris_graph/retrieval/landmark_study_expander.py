"""R2b landmark-study qgen (I-deepfix-001, #1344) — IN-WINDOW landmark empirical-study query expansion.

THE GAP (measured, drb_72 idx-56 AI-labor SWEEP; forensic ``COVERAGE_FORENSIC_RECONCILE``): the
FS-Researcher / expert-facet frontier decomposes the question into ABSTRACT facets, and the
sub-entity widener names concrete occupations / sectors — but NOTHING enumerates the LANDMARK
empirical studies / RCTs / seminal datasets central to the question. ``required_entity_retrieval``
derives proper nouns from the QUESTION text, which for "impact of Generative AI on the labor market"
carries no author names, so the empirical CORE (the profession-defining RCTs and their author teams)
is never queried and the corpus stays canonical-only. The primaries a rubric expects go missing.

THE FIX (systematic-review landmark seeding, forensic-corrected): ONE bounded LOCKED-generator call
enumerates the landmark empirical studies / RCTs / datasets most central to the question, RESPECTING
the stated date window. For a "published before June 2023" question it must name the pre-print /
working-paper VERSION that existed by that date, NEVER the later re-publication the hard scope mask
removes by rule (the forensic reconcile's central correction: widen the IN-WINDOW empirical core, do
NOT reach past the window). Every emitted query carries the question's own subject keywords as a scope
anchor (the same ``distill_keywords`` anchor R1/R2 use), so a landmark query can never generalise
off-subject. This AUGMENTS the FS-Researcher / expert-facet frontier — it does not replace it.

WINDOW + NAME DISCIPLINE (§-1.3, LAW VI, forensic reconcile): the date window ``window_end`` is
supplied by the CALLER at runtime (``extract_constraints_regex(question).date_end_iso()``) — NEVER
hardcoded here; the landmark study NAMES come from the LLM at runtime — NEVER hardcoded. So there is
no baked-in author / domain / date value in this module. A hallucinated study name simply returns no
source (the UNCHANGED ``per_query_retrieve`` + frozen faithfulness engine drop it), never a fabricated
citation.

DNA (§-1.3 WEIGHT-AND-CONSOLIDATE): pure query-FRONTIER expansion. It ADDS on-topic, in-window queries
only; it DROPS ZERO sources; every discovered source flows through the UNCHANGED ``per_query_retrieve``
(scope gate -> tier classify -> fetch -> provenance) and the frozen faithfulness engine (strict_verify
/ NLI / 4-role / span-grounding) exactly as today — a landmark source is NEVER auto-trusted, it must
earn its citation. ``PG_LANDMARK_MAX_STUDIES`` / ``PG_LANDMARK_QUERY_RESERVE`` and the FS-Researcher
``_max_queries`` cap are compute-SAFETY bounds (they cap cost — the opposite of the banned pattern,
which forces a breadth number UP); no forced cap / target / thinner / breadth-canary is introduced.
Default ON (``PG_LANDMARK_STUDY_EXPANSION``) — the coverage arm the forensic reconcile asks for; OFF =>
the FS-Researcher path is byte-identical.
"""

from __future__ import annotations

import os
import re
from typing import Callable, Optional

# (prompt) -> text. The already-picked FS-Researcher / intent-frame LOCKED policy model, injected by
# the caller (async client wrapped to sync) so this module never imports a live client at load time.
LlmFn = Callable[[str], str]

_ON_VALUES = frozenset({"1", "true", "on", "yes"})


def landmark_study_expansion_enabled() -> bool:
    """True iff the in-window landmark-study query expansion is flag-enabled (default OFF).

    LAW VI env kill-switch. I-deepfix-001 Wave-3 (#1344): the activation gate is ``PG_LANDMARK_EXPANDER``
    and defaults OFF — flag-OFF the FS-Researcher path is byte-identical; the Gate-B slate quad-pins it
    ON alongside ``PG_QGEN_PARALLEL_QUERIES`` / ``PG_OPENALEX_DATE_FILTER``. The tests exercise both the
    ON and OFF paths explicitly.
    """
    return os.getenv("PG_LANDMARK_EXPANDER", "0").strip().lower() in _ON_VALUES


def _max_landmark_studies() -> int:
    """Max landmark studies kept from the LLM enumeration. A compute-safety CAP on cost
    (studies x fetch), NOT a breadth target — it bounds the frontier UP-side, never forces a number
    up (§-1.3). Default 12."""
    try:
        return max(1, int(os.getenv("PG_LANDMARK_MAX_STUDIES", "12")))
    except ValueError:
        return 12


def _landmark_reserve() -> int:
    """How many landmark-study queries are ADDED ON TOP of the full baseline query budget.

    Mirrors the sub-entity widener's reserve: without this, a wide baseline frontier fills the whole
    ``PG_QGEN_FS_RESEARCHER_MAX_QUERIES`` budget, so making room for a landmark query would have to
    DISPLACE a baseline query — a SWAP, not a widen. Instead this bounded slice is added as EXTRA
    budget: the effective query budget is RAISED by up to this many positions so the landmark queries
    issue ON TOP of — never in place of — the baseline the flag-OFF path would issue. §-1.3
    WEIGHT-AND-CONSOLIDATE widen-only: a compute-safety UP-side bound (LAW VI env cap
    ``PG_LANDMARK_QUERY_RESERVE``, default 10), never a breadth target and never a drop."""
    try:
        return max(0, int(os.getenv("PG_LANDMARK_QUERY_RESERVE", "10")))
    except ValueError:
        return 10


def _norm(text: str) -> str:
    """Collapse internal whitespace and trim."""
    return re.sub(r"\s+", " ", (text or "")).strip()


def _scope_anchor(question: str) -> str:
    """The question's own subject keywords, used verbatim as a scope anchor on EVERY emitted query.

    Reuses ``query_decomposer.distill_keywords`` (the public, in-scope retrieval util the sibling
    sub-entity + facet planners already anchor on) so the anchor is the same distilled keyword phrase
    the keyword backends use. Falls back to the question's own leading content words when distillation
    yields nothing (never returns an empty anchor — an unanchored landmark query is exactly the
    off-topic drift this fix must not create).
    """
    try:
        from src.polaris_graph.retrieval.query_decomposer import distill_keywords
        anchor = (distill_keywords(question, max_terms=8) or "").strip()
    except Exception:
        anchor = ""
    if anchor:
        return anchor
    words = [w for w in re.findall(r"[A-Za-z0-9][A-Za-z0-9\-]+", question or "") if len(w) > 2]
    return " ".join(words[:8]).strip() or (question or "").strip()


def _clean_study_lines(text: str, cap: int) -> list[str]:
    """Parse an LLM landmark-study reply into clean, de-duplicated study identifiers.

    Strips numbering / bullets / a leading dimension label ("STUDY:", "RCT -", ...), drops obvious
    preamble lines, enforces a short length floor, and de-duplicates case-insensitively. Bounded by
    ``cap``. Mirrors the sibling sub-entity parser so study and entity parsing behave the same.
    """
    out: list[str] = []
    seen: set[str] = set()
    for raw in (text or "").splitlines():
        s = raw.strip()
        if not s:
            continue
        s = re.sub(r"^\s*(?:[-*]|\d+[.):])\s*", "", s).strip()
        # strip an optional leading dimension label ("STUDY:", "Dataset -", ...); the label charset
        # excludes digits / parens / '&' so an author-year identifier ("Noy & Zhang (2023)") is
        # never truncated.
        s = re.sub(r"^[A-Za-z][A-Za-z /_-]{2,20}\s*[:\-]\s+", "", s).strip().strip('"').strip()
        if len(s) <= 2:
            continue
        low = s.lower()
        if low.startswith(("here", "sure", "the following", "none", "landmark", "study:", "studies")):
            continue
        if low in seen:
            continue
        seen.add(low)
        out.append(s)
        if len(out) >= cap:
            break
    return out


def _window_clause(window_end: Optional[str]) -> str:
    """The date-window instruction spliced into the enumeration prompt.

    ``window_end`` is the caller-supplied publication ceiling (e.g. ``"2023-06"`` from
    ``extract_constraints_regex(question).date_end_iso()``), or ``None`` when the question states no
    window. NEVER hardcoded — the value flows in from the question at runtime. When a window is set
    the prompt DEMANDS the version (pre-print / working paper / dataset release) that existed by that
    date and forbids naming a later re-publication (the forensic reconcile's correction). When it is
    ``None`` the prompt still tells the model to honour any window the question itself states.
    """
    if window_end:
        return (
            "The question restricts sources to those published ON OR BEFORE "
            f"{window_end}. Every study you list MUST have a version (pre-print, working paper, "
            "technical report, or dataset release) that existed by that date; name THAT in-window "
            "version, NEVER a later journal re-publication of the same work. Do NOT list any study "
            "first released after the cutoff.\n\n"
        )
    return (
        "If the question states a publication date window, every study you list MUST fall within it "
        "(name the in-window pre-print / working-paper version, never a later re-publication).\n\n"
    )


def _enumerate_landmark_studies(
    question: str, llm: LlmFn, window_end: Optional[str], cap: int
) -> list[str]:
    """ONE bounded LOCKED-generator call: enumerate the landmark empirical studies the question implies.

    Elicits the specific empirical studies / RCTs / seminal datasets (with author teams) most central
    to answering the question, constrained to the stated date window.

    Failure semantics (I-deepfix-001 Wave-3b, #1344 — Codex P0 anti-dark false-green fix): a genuine
    ``llm(...)`` / planner EXCEPTION is NOT swallowed here — it PROPAGATES to the caller's fail-open
    handler (``fs_researcher_query_gen._plan_expert_facet_queries``) so the DISTINCT
    ``unavailable_failopen`` degrade marker fires and the run_gate_b activation canary REJECTS the dark
    lane. Swallowing the exception here (the prior ``except: return []``) made a real failure
    INDISTINGUISHABLE from a healthy RAN-ok-added-zero — the caller read ``[]`` and emitted a positive
    ``expanded_queries=0`` marker, the exact anti-dark false-green this wave targets. An empty /
    degenerate reply (the model legitimately naming no in-window study) still yields ``[]`` via
    ``_clean_study_lines`` — a RAN-ok-zero the caller reports as a healthy ``expanded_queries=0``
    (§-1.3: ran-ok-zero passes, NO count-threshold introduced). This only decides WHICH queries are
    searched — the faithfulness engine is never touched.
    """
    reply = llm(
        "You are an expert research librarian. List the LANDMARK empirical studies, randomized "
        "controlled trials, and seminal datasets (with their author teams) most central to "
        "answering the RESEARCH QUESTION below — the primary sources a systematic review of this "
        "question would be built on, which a generic keyword search would MISS because the "
        "question names no authors. Prefer the field-defining primaries over survey / opinion "
        "pieces. Every study MUST stay within the scope of the question.\n\n"
        + _window_clause(window_end)
        + "One study per line as 'author team, year, short title' — no numbering, no commentary.\n\n"
        "RESEARCH QUESTION:\n" + (question or "")
    )
    return _clean_study_lines(reply, cap)


def plan_landmark_study_queries(
    question: str, llm: LlmFn, window_end: Optional[str] = None
) -> list[str]:
    """Build the in-window landmark-study query frontier for ``question``.

    Returns an ordered, de-duplicated list of scope-anchored queries (``{landmark study} {question
    anchor}``) — the empirical primaries a generic search misses — from ONE bounded LOCKED-generator
    call constrained to ``window_end``. Pure control flow over the injected ``llm`` — no network here.
    An empty enumeration returns ``[]`` (unlike the sub-entity widener there is no deterministic
    floor: a landmark query is only ever a real study name from the model, so nothing is emitted when
    the model returns nothing). The FS-Researcher ``_max_queries`` cap (compute-safety) still applies
    downstream, so this may return more than are ultimately issued — intentional headroom, never a
    forced count (§-1.3).

    Failure semantics (I-deepfix-001 Wave-3b, #1344 — Codex P0): a genuine ``llm(...)`` / planner
    EXCEPTION from ``_enumerate_landmark_studies`` is NOT caught here — it PROPAGATES to the caller's
    fail-open handler so the ``unavailable_failopen`` degrade marker fires (a real failure must never
    read as a healthy ran-ok-added-zero). A legitimately empty model reply still returns ``[]`` (the
    accepted ran-ok-zero). ``_scope_anchor`` degrades internally to the question's own keywords and is
    never the source of a propagated failure.
    """
    anchor = _scope_anchor(question)
    out: list[str] = []
    seen: set[str] = set()
    for study in _enumerate_landmark_studies(question, llm, window_end, _max_landmark_studies()):
        q = _norm(f"{study} {anchor}")
        if not q:
            continue
        key = q.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(q)
    return out


def widen_with_landmark_studies(
    base_seeds: list[str],
    landmark_queries: list[str],
    max_queries: int,
) -> tuple[list[str], int]:
    """ADD the landmark-study queries ON TOP of the full baseline frontier and RAISE the effective
    query budget by exactly the added slice, so the flag-ON issued query set is a strict SUPERSET of
    the flag-OFF issued set.

    Returns ``(widened_seed_queries, effective_max_queries)``.

    Identical contract to ``sub_entity_query_expander.widen_with_sub_entities``: the flag-OFF path
    issues ``base_seeds[:max_queries]``; this keeps that exact baseline window at the FRONT in
    unchanged order, inserts a bounded slice of landmark queries immediately AFTER it, and returns a
    RAISED budget ``max_queries + reserve``. The downstream seed-issue loop (capped at the returned
    budget) therefore emits ``base_seeds[:max_queries] + reserved`` — every baseline query the flag-OFF
    path would issue is STILL issued, and the landmark queries are ADDED, never SWAPPED IN. Any
    baseline beyond the original budget and any leftover landmark queries trail after and issue only if
    the raised budget still has room — never displacing a baseline query. An empty ``landmark_queries``
    (or a reserve of 0) returns ``(base_seeds, max_queries)`` unchanged (byte-identical no-op).

    §-1.3 WEIGHT-AND-CONSOLIDATE widen-only: this ADDS retrieval by raising the budget by the bounded
    reserve (a LAW VI env cap, ``PG_LANDMARK_QUERY_RESERVE``); it introduces no cap / target / thinner,
    drops ZERO sources, and every added query still routes through the UNCHANGED ``per_query_retrieve``
    (scope -> tier -> fetch -> provenance) and the frozen faithfulness engine — a landmark source is
    NEVER auto-trusted.
    """
    if not landmark_queries:
        return list(base_seeds), max_queries
    reserve = min(len(landmark_queries), _landmark_reserve())
    if reserve <= 0:
        return list(base_seeds), max_queries
    reserved = landmark_queries[:reserve]
    leftover = landmark_queries[reserve:]
    baseline_window = base_seeds[:max_queries]  # exactly what the flag-OFF path issues
    baseline_tail = base_seeds[max_queries:]    # baseline beyond budget (neither path issues)
    widened = baseline_window + reserved + baseline_tail + leftover
    return widened, max_queries + reserve
