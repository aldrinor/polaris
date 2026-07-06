"""R1 (I-deepfix-001, #1344) — LLM expert-facet planner widens the query frontier.

THE GAP (measured, drb_72 SWEEP_...1783055694): FS-Researcher issued only 7 of 35 budgeted
queries. The adaptive checklist critic stops at the first ``NONE``; each sub-topic yields exactly
ONE query; ``query_decomposer.decompose_question`` returns ``[]`` for a concise question. The
frontier is therefore built from the question's own words, not the ~53 expert facets a DRB-II task
actually spans. Recall starves before selection even runs.

THE FIX: expand the question into a hierarchical FACET TREE (sub-topics, actors/stakeholders,
time-slices, geographies, mechanisms, opposing views) with ONE bounded LLM call, then multiply each
facet into several distinct facet-ANGLE queries (mechanism / stakeholder / counter-evidence /
temporal / geographic vantage points) by DETERMINISTIC templating. Every emitted query carries the
question's own subject keywords as a scope anchor, so a facet never generalises into its broad field
(the exact drb_72-v2 drift the sibling ``_scope_anchored`` guard in ``fs_researcher_query_gen`` was
built to stop). The deterministic split of the question stays as a FLOOR so a degenerate LLM reply
never shrinks the frontier below the legacy behaviour.

DNA (§-1.3 WEIGHT-AND-CONSOLIDATE): this is pure query-FRONTIER expansion. It adds on-topic queries
only; it DROPS ZERO sources; it touches no tiering / selection / consolidation / strict_verify / NLI
/ 4-role / provenance gate. ``PG_EXPERT_FACET_MAX_FACETS`` and the FS-Researcher ``_max_queries`` cap
are compute-SAFETY bounds (they cap cost — the opposite of the banned pattern, which forces a breadth
number UP); no forced cap / target / thinner / breadth-canary is introduced. Default OFF
(``PG_EXPERT_FACET_PLANNER``) => the FS-Researcher path is byte-identical to today.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Callable

# (prompt) -> text. The already-picked FS-Researcher / intent-frame policy model, injected by the
# caller (async client wrapped to sync) so this module never imports a live client at load time.
LlmFn = Callable[[str], str]

# The facet-angle vantage points. Each is a short lens phrase spliced into the query alongside the
# facet name and the question's own subject keywords (the scope anchor). Deterministic — one bounded
# LLM call produces the facet tree; the angles multiply it at $0. The order is stable so the emitted
# frontier is reproducible.
_ANGLE_LENSES: tuple[tuple[str, str], ...] = (
    ("mechanism", "how it works mechanism drivers"),
    ("stakeholder", "who is affected stakeholders impact"),
    ("counter_evidence", "criticism limitations counter-evidence dissent"),
    ("temporal", "recent trends over time change"),
    ("geographic", "regional differences across countries"),
)


def expert_facet_enabled() -> bool:
    """True iff the R1 expert-facet planner is flag-enabled (default OFF = legacy FS-Researcher).

    LAW VI env kill-switch. Default OFF keeps the production sweep byte-identical until the fresh
    paid run that validates the widened frontier; the tests exercise the ON path explicitly.
    """
    return os.getenv("PG_EXPERT_FACET_PLANNER", "0").strip() in ("1", "true", "True")


def _max_facets() -> int:
    """Max facets kept from the facet tree. A compute-safety CAP on cost (facets x angles x fetch),
    NOT a breadth target — it bounds the frontier UP-side, it never forces a number up (§-1.3)."""
    return max(1, int(os.getenv("PG_EXPERT_FACET_MAX_FACETS", "12")))


def _angles_per_facet() -> int:
    """How many facet-angle vantage queries to emit per facet (<= the number of defined lenses).
    Another compute-safety bound on cost, defaulting to the full lens set."""
    n = int(os.getenv("PG_EXPERT_FACET_ANGLES", str(len(_ANGLE_LENSES))))
    return max(1, min(n, len(_ANGLE_LENSES)))


# ── I-deepfix-001 Wave-2d (#1344) — TWO-SIDED DEBATE con-side retrieval guarantee ────────────────
#
# DeepTRACE One-Sided (#1) / Overconfident (#2): a DEBATE-framed question ("benefits and risks",
# "pros and cons", "positive vs negative") that renders only the majority side scores one-sided. The
# ``counter_evidence`` lens (``_ANGLE_LENSES[2]``) already sources the con angle for every facet, but a
# reduced ``PG_EXPERT_FACET_ANGLES`` budget (e.g. 2) would truncate it away. When ``PG_TWO_SIDED_DEBATE``
# is ON AND the question is debate-framed, GUARANTEE the ``counter_evidence`` lens is emitted regardless
# of the angle budget so the con side is actually retrieved. Pure ADDITIVE widener (§-1.3 WEIGHT-not-
# FILTER): it adds on-topic con-angle queries, drops zero sources, caps nothing. Default OFF =>
# ``debate_active`` is False => ``_ANGLE_LENSES[:n_angles]`` exactly as today => byte-identical.
_COUNTER_EVIDENCE_LABEL = "counter_evidence"

# Precision-first debate-framing detector. Each pattern is an EXPLICIT opposition pair (pro/con,
# benefits/risks, advantages/disadvantages, positive/negative, for/against, supporters/critics, ...)
# joined by ``and`` / ``or`` / ``vs`` / ``versus``, OR a standalone debate word (debate / controversy /
# contested / both-sides). A BARE ``A vs B`` comparison is DELIBERATELY excluded — a head-to-head
# comparison is not a pro/con debate; over-firing would emit a spurious asymmetry note on a plain
# comparison section (under-relax is safe, but a wrong note is noise), so only KNOWN opposition pairs
# license the ``vs`` form.
_DEBATE_CONNECTIVE = r"(?:and|or|vs\.?|versus)"
_DEBATE_PAIR_TERMS: tuple[tuple[str, str], ...] = (
    (r"pros?", r"cons?"),
    (r"benefits?", r"(?:risks?|drawbacks?|harms?|costs?|dangers?|downsides?)"),
    (r"(?:risks?|drawbacks?|harms?|dangers?|downsides?)", r"benefits?"),
    (r"advantages?", r"disadvantages?"),
    (r"disadvantages?", r"advantages?"),
    (r"strengths?", r"(?:weaknesses|limitations)"),
    (r"positives?", r"negatives?"),
    (r"positive", r"negative"),
    (r"upsides?", r"downsides?"),
    (r"for", r"against"),
    (r"(?:supporters?|proponents?)", r"(?:critics?|opponents?|detractors?|skeptics?|sceptics?)"),
    (r"praise", r"criticism"),
)
_DEBATE_STANDALONE: tuple[str, ...] = (
    r"debate[sd]?",
    r"controvers(?:y|ial|ies)",
    r"contested",
    r"both\s+sides",
    r"two\s+sides",
    r"either\s+side",
    r"divided\s+(?:opinion|views?|evidence)",
    r"case\s+for\s+and\s+(?:the\s+)?case\s+against",
)
_DEBATE_RE = re.compile(
    "|".join(
        [rf"\b{a}\s+{_DEBATE_CONNECTIVE}\s+(?:the\s+)?(?:potential\s+)?{b}\b" for a, b in _DEBATE_PAIR_TERMS]
        + [rf"\b{w}\b" for w in _DEBATE_STANDALONE]
    ),
    re.IGNORECASE,
)


def two_sided_debate_enabled() -> bool:
    """``PG_TWO_SIDED_DEBATE`` kill-switch (default OFF, LAW VI). OFF => the con-side retrieval guarantee
    and the composition-side disclosure are both no-ops => byte-identical."""
    return os.getenv("PG_TWO_SIDED_DEBATE", "0").strip().lower() not in ("", "0", "false", "off", "no")


def is_debate_question(text: str) -> bool:
    """True iff ``text`` (a question or a section title+focus) is DEBATE-framed — it asks for both sides
    of a disagreement. Precision-first: matches an explicit opposition pair joined by and/or/vs/versus,
    or a standalone debate word. Pure; the SHARED detector consumed by the retrieval-side con guarantee
    (here) and the composition-side debate-section detector (``multi_section_generator``)."""
    return bool(_DEBATE_RE.search(str(text or "")))


def _angle_lenses_for(n_angles: int, debate_active: bool) -> tuple[tuple[str, str], ...]:
    """The angle lenses to emit for a facet. Default = ``_ANGLE_LENSES[:n_angles]`` (byte-identical).
    When ``debate_active`` (``PG_TWO_SIDED_DEBATE`` ON + debate-framed question), the ``counter_evidence``
    lens is GUARANTEED present even if the budget would have truncated it — the con side must be
    retrieved for a debate query. Additive only; the base slice order is preserved."""
    lenses = list(_ANGLE_LENSES[:n_angles])
    if debate_active and not any(label == _COUNTER_EVIDENCE_LABEL for label, _ in lenses):
        ce = next((l for l in _ANGLE_LENSES if l[0] == _COUNTER_EVIDENCE_LABEL), None)
        if ce is not None:
            lenses.append(ce)
    return tuple(lenses)


@dataclass
class Facet:
    """One expert facet of the research question plus the angle queries derived from it."""

    name: str
    queries: list[str] = field(default_factory=list)


def _clean_facet_lines(text: str, cap: int) -> list[str]:
    """Parse an LLM facet-tree reply into clean facet names (strip numbering/bullets/labels).

    Mirrors ``fs_researcher_query_gen._lines`` semantics (bullet/number strip, drop preamble lines,
    length floor) so facet parsing and the FS-Researcher TOC parse behave the same. Also strips a
    leading ``FACET:`` / ``ACTOR:`` / ``GEOGRAPHY:`` style dimension label the prompt may emit.
    """
    out: list[str] = []
    seen: set[str] = set()
    for raw in (text or "").splitlines():
        s = raw.strip()
        if not s:
            continue
        s = re.sub(r"^\s*(?:[-*]|\d+[.):])\s*", "", s).strip()
        # strip an optional leading dimension label ("FACET:", "Stakeholders -", ...)
        s = re.sub(r"^[A-Za-z][A-Za-z /_-]{2,20}\s*[:\-]\s+", "", s).strip().strip('"').strip()
        if len(s) <= 2:
            continue
        low = s.lower()
        if low.startswith(("here", "sure", "the following", "none", "facet tree")):
            continue
        if low in seen:
            continue
        seen.add(low)
        out.append(s)
        if len(out) >= cap:
            break
    return out


def _question_anchor(question: str) -> str:
    """The question's own subject keywords, used verbatim as a scope anchor on EVERY angle query.

    Reuses ``query_decomposer.distill_keywords`` (in-scope retrieval util) so the anchor is the same
    distilled keyword phrase the keyword backends already use. Falls back to a whitespace-trimmed
    slice of the raw question when distillation yields nothing (never returns an empty anchor — an
    unanchored angle query is exactly the drb_72-v2 off-topic drift this fix must not re-create).
    """
    try:
        from src.polaris_graph.retrieval.query_decomposer import distill_keywords
        anchor = (distill_keywords(question, max_terms=8) or "").strip()
    except Exception:
        anchor = ""
    if anchor:
        return anchor
    # Fallback: the question's own leading content words (never empty for a real question).
    words = [w for w in re.findall(r"[A-Za-z0-9][A-Za-z0-9\-]+", question or "") if len(w) > 2]
    return " ".join(words[:8]).strip() or (question or "").strip()


def _facet_angle_queries(
    facet_name: str, anchor: str, n_angles: int, debate_active: bool = False,
) -> list[str]:
    """Emit up to ``n_angles`` distinct facet-ANGLE queries for one facet, each scope-anchored.

    Each query = ``{facet} {angle lens} {question anchor}`` — the facet supplies the sub-topic, the
    lens supplies the vantage point (mechanism / stakeholder / counter-evidence / temporal /
    geographic), and the anchor keeps it inside the question's subject so it cannot generalise into
    the facet's broad field. Duplicate collapse is case-insensitive.

    Wave-2d: when ``debate_active`` the ``counter_evidence`` lens is guaranteed emitted (con-side
    retrieval for a debate query); ``debate_active=False`` (default / flag OFF) => byte-identical.
    """
    out: list[str] = []
    seen: set[str] = set()
    for label, lens in _angle_lenses_for(n_angles, debate_active):
        # facet first (primary subject), then the angle lens, then the scope anchor.
        q = f"{facet_name} {lens} {anchor}".strip()
        q = re.sub(r"\s+", " ", q)
        key = q.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(q)
    return out


def _deterministic_floor_facets(question: str) -> list[str]:
    """Facet FLOOR when the LLM returns no usable facet tree: the deterministic question split.

    Uses ``query_decomposer.decompose_question`` (returns [] for a truly single-clause question) and
    falls back to the whole question. Guarantees the facet planner never emits FEWER seed facets than
    the legacy deterministic split — the frontier can only widen, never shrink (§-1.3 floor).
    """
    facets: list[str] = []
    try:
        from src.polaris_graph.retrieval.query_decomposer import decompose_question
        facets = list(decompose_question(question) or [])
    except Exception:
        facets = []
    if not facets and question and question.strip():
        facets = [question.strip()]
    return facets


def plan_expert_facets(question: str, llm: LlmFn) -> list[Facet]:
    """Build the facet tree for ``question`` and expand each facet into angle queries.

    ONE bounded LLM call elicits the facet tree across the taxonomy dimensions (sub-topics, actors /
    stakeholders, time-slices, geographies, mechanisms, opposing views); the angles are then
    multiplied deterministically at $0. When the LLM reply is unusable, the deterministic split of
    the question is used as the facet floor. Returns an ordered list of ``Facet`` (each with >=1
    scope-anchored angle query). Pure control flow over the injected ``llm`` — no network here.
    """
    cap = _max_facets()
    n_angles = _angles_per_facet()
    anchor = _question_anchor(question)
    # Wave-2d (#1344): guarantee the counter_evidence angle for a debate-framed question when
    # PG_TWO_SIDED_DEBATE is ON. Default OFF => debate_active is False => byte-identical.
    debate_active = two_sided_debate_enabled() and is_debate_question(question)

    facet_names: list[str] = []
    try:
        reply = llm(
            "You are an expert research planner. Decompose the RESEARCH QUESTION into its distinct "
            "expert facets so an exhaustive literature review can be planned. Cover these dimensions "
            "where they exist: sub-topics, actors/stakeholders, time-slices, geographies, mechanisms, "
            "and opposing/critical views. Every facet MUST stay within the scope of the question — "
            "carry its subject, domain and key entities; do NOT generalise a facet into its broad "
            "field. One facet per line, no numbering.\n\nRESEARCH QUESTION:\n" + (question or "")
        )
        facet_names = _clean_facet_lines(reply, cap)
    except Exception:
        facet_names = []

    # FLOOR: never fewer than the deterministic split; merge (dedup, keep LLM facets first).
    floor = _deterministic_floor_facets(question)
    seen = {f.lower() for f in facet_names}
    for f in floor:
        if f.lower() not in seen:
            facet_names.append(f)
            seen.add(f.lower())
        if len(facet_names) >= cap:
            break
    facet_names = facet_names[:cap]

    facets: list[Facet] = []
    for name in facet_names:
        queries = _facet_angle_queries(name, anchor, n_angles, debate_active)
        if queries:
            facets.append(Facet(name=name, queries=queries))
    return facets


def facet_seed_queries(question: str, llm: LlmFn) -> list[str]:
    """Flatten the facet tree into the ordered, de-duplicated seed-query frontier.

    This is what the FS-Researcher planner consumes when the R1 flag is ON: a widened list of
    on-topic, angle-differentiated, scope-anchored queries. The FS-Researcher ``_max_queries`` cap
    (a compute-safety bound) still applies downstream, so this may return more than are ultimately
    issued — that is intentional headroom, never a forced count.
    """
    out: list[str] = []
    seen: set[str] = set()
    for facet in plan_expert_facets(question, llm):
        for q in facet.queries:
            key = q.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(q)
    return out
