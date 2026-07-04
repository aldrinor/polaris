"""R2 entity-qgen (I-deepfix-001, #1344) — STORM-style sub-entity + perspective query expansion.

THE GAP (measured, drb_72 AI-labor SWEEP): the FS-Researcher / expert-facet frontier decomposes the
question into ABSTRACT facets (sub-topics x mechanism/stakeholder/counter/temporal/geographic angles).
That surfaces the famous canonical studies (Acemoglu / Autor / Frey-Osborne) but MISSES the long-tail
NICHE sub-entities a DRB-II rubric actually names — the concrete occupations, industry sectors, and
demographic groups whose profession-specific primaries never appear in a generic "AI + labor market"
search. Abstract facets do not name "radiologists", "paralegals", "truck drivers", "warehouse
workers" — so their profession-specific evidence is never fetched, and the corpus stays canonical-only.

THE FIX (STORM-style, arXiv:2402.14207 multi-perspective + per-sub-entity decomposition): ONE bounded
LLM call enumerates the concrete NAMED sub-entities the question implies (occupations / sectors /
demographic groups / named technologies-datasets), and a DETERMINISTIC set of STORM-style disciplinary
PERSPECTIVE lenses (economic / social / policy / industry / technical / public-interest) multiplies the
topic at $0. Every emitted query carries the question's own subject keywords as a scope anchor (the same
``distill_keywords`` anchor R1 uses), so a sub-entity query can never generalise off-subject (the
drb_72-v2 off-topic drift guard). This AUGMENTS the FS-Researcher / expert-facet frontier — it does not
replace it.

DNA (§-1.3 WEIGHT-AND-CONSOLIDATE): pure query-FRONTIER expansion. It ADDS on-topic queries only; it
DROPS ZERO sources; every discovered source flows through the UNCHANGED ``per_query_retrieve`` (scope
gate -> tier classify -> fetch -> provenance) and the frozen faithfulness engine (strict_verify / NLI /
4-role / span-grounding) exactly as today — a niche sub-entity source is NEVER auto-trusted, it must
earn its citation like every other source. ``PG_SUBENTITY_MAX_ENTITIES`` / ``PG_SUBENTITY_MAX_PERSPECTIVES``
and the FS-Researcher ``_max_queries`` cap are compute-SAFETY bounds (they cap cost — the opposite of the
banned pattern, which forces a breadth number UP); no forced cap / target / thinner / breadth-canary is
introduced. Default OFF (``PG_SUBENTITY_QUERY_EXPANSION``) => the FS-Researcher path is byte-identical.
"""

from __future__ import annotations

import os
import re
from typing import Callable

# (prompt) -> text. The already-picked FS-Researcher / intent-frame policy model, injected by the
# caller (async client wrapped to sync) so this module never imports a live client at load time.
LlmFn = Callable[[str], str]

# STORM-style disciplinary PERSPECTIVE lenses (arXiv:2402.14207 personas), TOPIC-AGNOSTIC: each lens is
# a short disciplinary-vantage phrase spliced alongside the question's own subject keywords (the scope
# anchor). Deterministic — one bounded LLM call enumerates the named sub-entities; these lenses multiply
# the topic at $0. Distinct from R1's analytical angle lenses (mechanism/stakeholder/counter/temporal/
# geographic): these are DISCIPLINARY personas, so they widen toward vantage points R1 does not cover.
# The order is stable so the emitted frontier is reproducible.
_PERSPECTIVE_LENSES: tuple[tuple[str, str], ...] = (
    ("economic", "economic analysis costs benefits"),
    ("social", "social workforce community impact"),
    ("policy", "policy regulation governance response"),
    ("industry", "industry practitioner adoption deployment"),
    ("technical", "technical mechanism feasibility limits"),
    ("public_interest", "public interest affected groups equity"),
)


def sub_entity_expansion_enabled() -> bool:
    """True iff the sub-entity + perspective query expansion is flag-enabled (default OFF = legacy).

    LAW VI env kill-switch. Default OFF keeps the FS-Researcher path byte-identical until the fresh
    paid run that validates the widened frontier; the tests exercise the ON path explicitly.
    """
    return os.getenv("PG_SUBENTITY_QUERY_EXPANSION", "0").strip() in ("1", "true", "True")


def _max_sub_entities() -> int:
    """Max concrete sub-entities kept from the LLM enumeration. A compute-safety CAP on cost
    (entities x fetch), NOT a breadth target — it bounds the frontier UP-side, never forces a
    number up (§-1.3). Default 12."""
    try:
        return max(1, int(os.getenv("PG_SUBENTITY_MAX_ENTITIES", "12")))
    except ValueError:
        return 12


def _max_perspectives() -> int:
    """How many STORM-style perspective lenses to emit (<= the number defined). Another compute-safety
    bound on cost, defaulting to the full lens set."""
    try:
        n = int(os.getenv("PG_SUBENTITY_MAX_PERSPECTIVES", str(len(_PERSPECTIVE_LENSES))))
    except ValueError:
        n = len(_PERSPECTIVE_LENSES)
    return max(1, min(n, len(_PERSPECTIVE_LENSES)))


def _sub_entity_reserve() -> int:
    """How many sub-entity / perspective queries are ADDED ON TOP of the full baseline query budget.

    Without this fix, a wide R1 facet frontier fills the whole ``PG_QGEN_FS_RESEARCHER_MAX_QUERIES``
    budget, so making room for a sub-entity query would have to DISPLACE a baseline facet query — a
    SWAP, not a widen (the Codex/Fable iter-1 REVISE). Instead, this bounded slice is added as EXTRA
    budget: the effective query budget is RAISED by up to this many positions so the sub-entity queries
    issue ON TOP of — never in place of — the baseline the flag-OFF path would issue. §-1.3
    WEIGHT-AND-CONSOLIDATE widen-only: a compute-safety UP-side bound on the added retrieval (LAW VI env
    cap), never a breadth target and never a drop. Env-driven ``PG_SUBENTITY_QUERY_RESERVE`` (default 10)."""
    try:
        return max(0, int(os.getenv("PG_SUBENTITY_QUERY_RESERVE", "10")))
    except ValueError:
        return 10


def _norm(text: str) -> str:
    """Collapse internal whitespace and trim."""
    return re.sub(r"\s+", " ", (text or "")).strip()


def _scope_anchor(question: str) -> str:
    """The question's own subject keywords, used verbatim as a scope anchor on EVERY emitted query.

    Reuses ``query_decomposer.distill_keywords`` (the public, in-scope retrieval util R1's
    ``_question_anchor`` is built on) so the anchor is the same distilled keyword phrase the keyword
    backends and the sibling facet planner already use. Falls back to the question's own leading content
    words when distillation yields nothing (never returns an empty anchor — an unanchored sub-entity
    query is exactly the off-topic drift this fix must not re-create).
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


def _clean_entity_lines(text: str, cap: int) -> list[str]:
    """Parse an LLM sub-entity reply into clean, de-duplicated entity names.

    Strips numbering / bullets / a leading dimension label ("OCCUPATION:", "Sector -", ...), drops
    obvious preamble lines, enforces a short length floor, and de-duplicates case-insensitively.
    Bounded by ``cap``. Mirrors the sibling facet planner's line parsing so entity and facet parsing
    behave the same.
    """
    out: list[str] = []
    seen: set[str] = set()
    for raw in (text or "").splitlines():
        s = raw.strip()
        if not s:
            continue
        s = re.sub(r"^\s*(?:[-*]|\d+[.):])\s*", "", s).strip()
        # strip an optional leading dimension label ("OCCUPATION:", "Demographic -", ...)
        s = re.sub(r"^[A-Za-z][A-Za-z /_-]{2,20}\s*[:\-]\s+", "", s).strip().strip('"').strip()
        if len(s) <= 2:
            continue
        low = s.lower()
        if low.startswith(("here", "sure", "the following", "none", "sub-entit", "sub entit")):
            continue
        if low in seen:
            continue
        seen.add(low)
        out.append(s)
        if len(out) >= cap:
            break
    return out


def _enumerate_sub_entities(question: str, llm: LlmFn, cap: int) -> list[str]:
    """ONE bounded LLM call: enumerate the concrete NAMED sub-entities the question implies.

    Elicits specific occupations / professions, industry sectors, demographic groups, and named
    technologies / datasets that a generic search would miss but that the review scope names or
    implies. Every entity MUST stay within the question's scope. Best-effort: any exception or empty
    reply yields ``[]`` and the caller simply emits the deterministic perspective queries — the
    faithfulness engine is never touched (this only decides WHICH queries are searched).
    """
    try:
        reply = llm(
            "You are an expert research planner. List the concrete, NAMED sub-entities this RESEARCH "
            "QUESTION implies but a generic search would MISS — specific occupations / professions, "
            "industry sectors, demographic groups, and named technologies or datasets whose "
            "profession-specific or sector-specific evidence is relevant. Prefer the long-tail, niche "
            "entities over the obvious headline ones. Every entity MUST stay within the scope of the "
            "question — do NOT drift into a broad field. One entity per line, no numbering.\n\n"
            "RESEARCH QUESTION:\n" + (question or "")
        )
    except Exception:
        return []
    return _clean_entity_lines(reply, cap)


def plan_sub_entity_queries(question: str, llm: LlmFn) -> list[str]:
    """Build the sub-entity + perspective query frontier for ``question``.

    Returns an ordered, de-duplicated list of scope-anchored queries:
      * per-sub-entity queries (``{named sub-entity} {question anchor}``) — the niche occupation /
        sector / demographic primaries a generic search misses, from ONE bounded LLM call, and
      * STORM-style perspective queries (``{disciplinary lens} {question anchor}``) — deterministic,
        $0, always emitted so the frontier widens even when the LLM enumeration is empty.

    Pure control flow over the injected ``llm`` — no network here. The FS-Researcher ``_max_queries``
    cap (a compute-safety bound) still applies downstream, so this may return more than are ultimately
    issued — intentional headroom, never a forced count (§-1.3).
    """
    anchor = _scope_anchor(question)
    out: list[str] = []
    seen: set[str] = set()

    def _add(q: str) -> None:
        q = _norm(q)
        if not q:
            return
        key = q.lower()
        if key in seen:
            return
        seen.add(key)
        out.append(q)

    # Per-sub-entity queries (named, niche, scope-anchored) — the core recall lever.
    for entity in _enumerate_sub_entities(question, llm, _max_sub_entities()):
        _add(f"{entity} {anchor}")

    # STORM-style disciplinary perspective queries (deterministic floor — always widens).
    for _label, lens in _PERSPECTIVE_LENSES[: _max_perspectives()]:
        _add(f"{lens} {anchor}")

    return out


def widen_with_sub_entities(
    base_seeds: list[str],
    sub_entity_queries: list[str],
    max_queries: int,
) -> tuple[list[str], int]:
    """ADD the sub-entity / perspective queries ON TOP of the full baseline frontier and RAISE the
    effective query budget by exactly the added slice, so the flag-ON issued query set is a strict
    SUPERSET of the flag-OFF issued set.

    Returns ``(widened_seed_queries, effective_max_queries)``.

    The flag-OFF path issues ``base_seeds[:max_queries]``. This keeps that exact baseline window at the
    FRONT in unchanged order, inserts a bounded slice of sub-entity queries immediately AFTER it, and
    returns a RAISED budget ``max_queries + reserve``. The downstream seed-issue loop (capped at the
    returned budget) therefore emits ``base_seeds[:max_queries] + reserved`` — every baseline query the
    flag-OFF path would issue is STILL issued, and the sub-entity / perspective queries are ADDED, never
    SWAPPED IN for a baseline query. This is the iter-1 REVISE fix: the prior helper shrank the baseline
    head to ``max_queries - reserve`` so the reserved slice displaced baseline queries out of the budget
    (a swap). Any baseline beyond the original budget and any leftover sub-entity queries trail after and
    issue only if the raised budget still has room — never displacing a baseline query. An empty
    ``sub_entity_queries`` (or a reserve of 0) returns ``(base_seeds, max_queries)`` unchanged
    (byte-identical no-op).

    §-1.3 WEIGHT-AND-CONSOLIDATE widen-only: this ADDS retrieval by raising the budget by the bounded
    reserve (a LAW VI env cap, ``PG_SUBENTITY_QUERY_RESERVE``); it introduces no cap / target / thinner,
    drops ZERO sources, and every added query still routes through the UNCHANGED ``per_query_retrieve``
    (scope -> tier -> fetch -> provenance) and the frozen faithfulness engine — a sub-entity source is
    NEVER auto-trusted.
    """
    if not sub_entity_queries:
        return list(base_seeds), max_queries
    reserve = min(len(sub_entity_queries), _sub_entity_reserve())
    if reserve <= 0:
        return list(base_seeds), max_queries
    reserved = sub_entity_queries[:reserve]
    leftover = sub_entity_queries[reserve:]
    baseline_window = base_seeds[:max_queries]  # exactly what the flag-OFF path issues
    baseline_tail = base_seeds[max_queries:]    # baseline beyond budget (neither path issues)
    widened = baseline_window + reserved + baseline_tail + leftover
    return widened, max_queries + reserve
