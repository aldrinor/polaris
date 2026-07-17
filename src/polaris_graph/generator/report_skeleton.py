"""Closed ARCHETYPE registry + pure report-shape helpers (GENERALIZED Fix 4).

This module holds the deterministic, closed archetype table and the three pure
functions that shape a report's block ORDER + framing heading. It is the
generalized replacement for the journal-literal ``litreview`` shaping that landed
at ``d44ee36`` (hardcoded ``## Introduction and Scope`` + a fixed
sections->depth->KF->biblio order).

Design constraints (from GATE_GENERALIZE_FIX45_PLAN.md §2):
  * PURE. No I/O, no LLM, no ``provenance_generator`` import — nothing here can
    reach the frozen faithfulness engine. The functions arrange OPAQUE block
    strings (they never read or re-compose a verified sentence).
  * CLOSED table, not a generative skeleton (3/3 reviewer convergence). A kind
    that matches no synonym is preserved VERBATIM as an opaque term and falls
    back to the least-wrong universal ``review`` shape (disclosed as an
    assumption by the caller) — never dropped, never invented.
  * Only two things vary per archetype: the Key-Findings POSITION and the
    framing HEADING title. The machinery set is archetype-invariant EXCEPT that
    ``methods`` stays in the scored body when a ``contract.sections`` requirement
    matches it (the systematic-review / PRISMA carve-out).
  * ``order_report_blocks`` is a pure PERMUTATION of the render blocks it is
    handed — count-invariant, nothing deleted, interiors byte-identical.

NO ``journal`` / ``review`` / ``Introduction and Scope`` LITERAL appears in
control flow here — those live only as DATA in ``ARCHETYPES`` / ``KIND_SYNONYMS``
(the anti-hardcode grep test enforces this).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


# ---------------------------------------------------------------------------
# The closed archetype table (DATA, not control flow)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Archetype:
    """One report shape. ``framing_title`` is the ``## {title}`` heading emitted
    over the claim-free framing paragraph (empty => no framing section, e.g. a
    BLUF memo). ``kf_position`` is where the Key-Findings recap sits relative to
    the thematic body: ``lead`` (BLUF, before framing), ``after_framing``
    (default review shape), or ``tail`` (after the synthesis). ``kf_title`` is the
    Key-Findings HEADER label (chrome only — bullets are byte-identical across
    archetypes)."""

    key: str
    framing_title: str
    kf_position: str  # "lead" | "after_framing" | "tail"
    kf_title: str = "Key Findings"


# key -> Archetype. ``review`` is the default (== the landed shape for a review
# contract, so an ON-path review run is byte-identical to d44ee36).
ARCHETYPES: dict[str, Archetype] = {
    "review": Archetype("review", "Introduction and Scope", "after_framing", "Key Findings"),
    "systematic_review": Archetype(
        "systematic_review", "Introduction and Scope", "after_framing", "Key Findings"
    ),
    "memo": Archetype("memo", "", "lead", "Bottom Line"),
    "brief": Archetype("brief", "Executive Summary", "lead", "Key Findings"),
    "comparison": Archetype("comparison", "Scope and Criteria", "after_framing", "Key Findings"),
    "explainer": Archetype("explainer", "Overview", "tail", "Key Findings"),
}

# normalized deliverable.kind value -> archetype key. Same synonym-table pattern
# as retrieval_projection._resolve_facet_id (LAW VI: no new vocabulary; longest
# matching synonym wins; an unmapped value stays opaque and falls back to
# DEFAULT_ARCHETYPE). Keys are lower-cased at resolution time.
KIND_SYNONYMS: dict[str, str] = {
    "literature review": "review",
    "lit review": "review",
    "survey": "review",
    "review": "review",
    "systematic review": "systematic_review",
    "systematic literature review": "systematic_review",
    "meta-analysis": "systematic_review",
    "memo": "memo",
    "decision memo": "memo",
    "briefing memo": "memo",
    "brief": "brief",
    "policy brief": "brief",
    "executive brief": "brief",
    "comparison": "comparison",
    "comparative analysis": "comparison",
    "market scan": "comparison",
    "explainer": "explainer",
    "primer": "explainer",
    "overview": "explainer",
}

DEFAULT_ARCHETYPE = "review"  # least-wrong universal shape; disclosed when assumed


# ---------------------------------------------------------------------------
# COMPOSE DIRECTIVES (DATA, not control flow) — the per-archetype doc-type
# framing the section writer's system prompt reads as an ADDITIVE preamble.
# ---------------------------------------------------------------------------
# Keyed by the SAME archetype key as ``ARCHETYPES`` (resolved via
# ``KIND_SYNONYMS``). Each string is DIRECTIVE-ONLY prose: it frames HOW the
# deliverable reads (structure/voice/scope emphasis), states NO fact, cites NO
# source, carries NO digit and NO ``ev_`` id, and asks for NO heading. It is a
# SUFFIX on the frozen section system prompt — never a gate, never a truncation.
# An unmapped kind resolves to ``DEFAULT_ARCHETYPE`` (disclosed by the caller);
# the raw kind is preserved verbatim in the projection. NO per-kind literal
# lives in control flow — only in this table (the anti-hardcode grep enforces it).
COMPOSE_DIRECTIVES: dict[str, str] = {
    "review": (
        "This is a literature review. Organize the verified findings by theme and "
        "synthesize across sources; foreground scope and how the evidence base fits "
        "together, not a chronology of individual studies."
    ),
    "systematic_review": (
        "This is a systematic review. Present the review question, then the evidence "
        "synthesis by theme, then the limitations of the evidence base; be methodical "
        "and explicit about coverage and gaps without asserting any procedure the "
        "evidence does not support."
    ),
    "memo": (
        "This is a decision memo. Lead bottom-line-first: state the upshot for the "
        "decision up front, then the options and their tradeoffs, in a direct, "
        "decision-oriented voice."
    ),
    "brief": (
        "This is a brief. Open with an executive summary and keep the prose concise "
        "and implication-focused for a time-constrained reader."
    ),
    "comparison": (
        "This is a comparison. Set out the scope and comparison criteria, then treat "
        "each option symmetrically across the same dimensions so the contrast is even-"
        "handed."
    ),
    "explainer": (
        "This is an explainer. Give an overview first, then build up the concepts and "
        "mechanisms in an accessible, explanatory voice for a non-expert reader."
    ),
}


def _norm(s: Any) -> str:
    return str(s or "").strip().lower()


def resolve_archetype_key(kind_value: Any) -> "tuple[str, bool, str]":
    """Resolve a raw ``deliverable.kind`` VALUE string onto an archetype KEY.

    Returns ``(key, assumed, opaque_kind)`` mirroring :func:`resolve_archetype`
    but reading a bare kind string instead of a contract (so a projection that
    already carries ``doc_type`` need not reconstruct a contract). ``assumed`` is
    ``True`` when the default key was used (empty or unmapped kind); ``opaque_kind``
    is the verbatim unmapped kind (``""`` otherwise). PURE. Same longest-synonym-
    wins matching as :func:`resolve_archetype` — no new vocabulary, no per-kind
    branch."""
    raw = str(kind_value or "").strip()
    v = _norm(raw)
    if not v:
        return DEFAULT_ARCHETYPE, True, ""
    best_key = ""
    best_len = -1
    for syn, key in KIND_SYNONYMS.items():
        synl = syn.strip().lower()
        if not synl:
            continue
        if synl in v or v in synl:
            if len(synl) > best_len:
                best_key = key
                best_len = len(synl)
    if best_key and best_key in ARCHETYPES:
        return best_key, False, ""
    return DEFAULT_ARCHETYPE, True, raw


def compose_doc_type_directive(kind_value: Any) -> str:
    """The per-archetype doc-type framing directive for a raw ``deliverable.kind``
    VALUE (``""`` when the kind is empty).

    Resolves ``kind_value`` -> archetype key (via :func:`resolve_archetype_key`)
    and returns the matching :data:`COMPOSE_DIRECTIVES` string. An EMPTY kind
    yields ``""`` (inert => byte-identical). An UNMAPPED kind falls back to the
    default archetype's directive (the caller discloses the assumption). DIRECTIVE
    ONLY: no fact, no digit, no ``ev_`` id, no heading. PURE."""
    if not str(kind_value or "").strip():
        return ""
    key, _assumed, _opaque = resolve_archetype_key(kind_value)
    return COMPOSE_DIRECTIVES.get(key, COMPOSE_DIRECTIVES[DEFAULT_ARCHETYPE])


def compose_section_role(kind_value: Any, section_title: Any) -> str:
    """A short per-section ORIENTATION directive: how ``section_title`` serves a
    deliverable of the resolved kind. ``""`` when the kind or title is empty.

    Generic + DATA-driven: it names the archetype (from :data:`ARCHETYPES`, keyed
    by the resolved key) and the section, with NO per-kind literal in control flow
    and NO per-section role table to maintain. It states the section's job in the
    deliverable's shape in one line so the writer orients this section — DIRECTIVE
    ONLY (no fact, no digit, no ``ev_`` id, no heading). PURE. Kept to a single
    line: every extra sentence is prompt-hash + verbosity surface."""
    kind = str(kind_value or "").strip()
    title = str(section_title or "").strip()
    if not kind or not title:
        return ""
    key, _assumed, _opaque = resolve_archetype_key(kind_value)
    arch = ARCHETYPES.get(key, ARCHETYPES[DEFAULT_ARCHETYPE])
    return (
        f'Compose the "{title}" section so it does its job within this {arch.key} '
        "deliverable's overall shape, consistent with the framing above."
    )


def _first_deliverable_kind_value(contract: Any) -> str:
    """Read the ``deliverable.kind`` VALUE from a ResearchContract.

    ``contract.deliverable`` is a ``list[ContractTerm]`` (not a scalar). We take
    the value of the first term whose ``dimension`` ends in ``deliverable.kind``
    (or bare ``kind``). Returns ``""`` when absent — the caller then assumes the
    default archetype and discloses it. Tolerant of a ``None`` contract."""
    if contract is None:
        return ""
    terms = getattr(contract, "deliverable", None) or []
    for term in terms:
        dim = _norm(getattr(term, "dimension", ""))
        if dim.endswith("deliverable.kind") or dim.endswith(".kind") or dim == "kind":
            val = getattr(term, "value", None)
            if val is not None and str(val).strip():
                return str(val)
    return ""


def resolve_archetype(contract: Any) -> "tuple[Archetype, bool, str]":
    """Map ``contract.deliverable[kind]`` onto a closed :class:`Archetype`.

    Returns ``(archetype, assumed, opaque_kind)``:
      * ``archetype`` — the resolved shape (never ``None``).
      * ``assumed`` — ``True`` when the default was used because the contract
        named no kind OR named a kind matching no synonym (the caller records an
        assumption-ledger disclosure).
      * ``opaque_kind`` — the VERBATIM unmapped kind string when a named kind
        resolved to no archetype (``""`` otherwise), so it can be preserved as an
        opaque term in the disclosure rather than silently dropped.

    Uses the SAME synonym-resolution shape as ``_resolve_facet_id`` (longest
    matching synonym wins, substring both ways to tolerate plurals). A value
    matching no synonym is OPAQUE + falls back to the default (fail-open)."""
    raw = _first_deliverable_kind_value(contract)
    v = _norm(raw)
    if not v:
        return ARCHETYPES[DEFAULT_ARCHETYPE], True, ""
    best_key = ""
    best_len = -1
    for syn, key in KIND_SYNONYMS.items():
        synl = syn.strip().lower()
        if not synl:
            continue
        if synl in v or v in synl:
            if len(synl) > best_len:
                best_key = key
                best_len = len(synl)
    if best_key and best_key in ARCHETYPES:
        return ARCHETYPES[best_key], False, ""
    # Named a kind we do not recognize: preserve verbatim as opaque, fall back.
    return ARCHETYPES[DEFAULT_ARCHETYPE], True, raw


def build_framing_md(objective: str, archetype: Archetype) -> str:
    """A short CLAIM-FREE, CITATION-FREE framing paragraph under the archetype's
    ``## {framing_title}`` heading, derived from the contract OBJECTIVE. It
    asserts NO finding and carries NO ``[N]`` citation — pure framing, the same
    faithfulness class as the abort-path H1s — so it can never reach the
    faithfulness gate as an unverified claim.

    Returns ``""`` when the objective is empty (no empty heading) OR when the
    archetype has an empty ``framing_title`` (a BLUF memo emits no framing
    section). PURE (no I/O). Template-only — no per-kind literal in control flow;
    the heading is DATA from the archetype.

    The prose is emitted DIRECTLY UNDER the H1 (its own ``## {framing_title}``
    subheading follows the lead paragraph) so the H1 title is never orphan-dropped
    by ``dedup_identical_paragraphs`` (which drops a header whose next non-blank
    block is another header)."""
    obj = (objective or "").strip().rstrip(".")
    if not obj:
        return ""
    title = (archetype.framing_title or "").strip()
    if not title:
        return ""
    return (
        f"This report reviews the available evidence on {obj}. It synthesizes the findings that "
        "survived span-level verification, organized by theme; each cited claim is carried verbatim "
        "from a source span. Methods, source-hygiene disclosures, and the reliability audit are "
        "collected in the appendix at the end.\n\n"
        f"## {title}\n\n"
        f"Scope: this review is bounded to the question of {obj}. It reports only claims that passed "
        "span-level verification; unverified or off-topic material is excluded from the findings and "
        "disclosed in the appendix.\n\n"
    )


def contract_requires_section(contract: Any, section_key: str) -> bool:
    """True iff a ``SectionRequirement`` in ``contract.sections`` names the given
    section (case-insensitive substring match on its title value). Used for the
    2-line ``methods_is_machinery`` carve-out: a systematic-review PRISMA Methods
    is SCORED content and stays in the body. Tolerant of a ``None`` contract /
    missing sections (=> False). PURE."""
    if contract is None:
        return False
    key = _norm(section_key)
    if not key:
        return False
    for sec in getattr(contract, "sections", None) or []:
        title_term = getattr(sec, "title", None)
        title_val = _norm(getattr(title_term, "value", "") if title_term is not None else "")
        if not title_val:
            # A section id can stand in when the title term carries no value.
            title_val = _norm(getattr(sec, "section_id", ""))
        if title_val and key in title_val:
            return True
    return False


def order_report_blocks(
    archetype: Archetype,
    *,
    key_findings_md: str,
    sections_concat: str,
    depth_layer_md: str,
    methods_md: str,
    biblio_section_md: str,
    cwf_disclosed_md: str,
    drop_disclosure_md: str,
    methods_is_machinery: bool = True,
) -> "tuple[str, str]":
    """Arrange the EXISTING render blocks into the archetype's order and split the
    audit MACHINERY into a trailing appendix. Returns ``(scored_body,
    machinery_appendix)``.

    Position of the Key-Findings recap follows ``archetype.kf_position``:
      * ``lead``          — KF opens the scored body (BLUF: memo / brief).
      * ``after_framing`` — KF after the thematic sections + synthesis (review).
      * ``tail``          — KF after the synthesis, before the bibliography
                            (explainer). (The framing paragraph itself is emitted
                            by the caller into the TITLE block, so ``after_framing``
                            here means "after the thematic body", matching the
                            landed review order.)

    ``machinery_appendix`` = ``cwf_disclosed_md + drop_disclosure_md`` plus
    ``methods_md`` UNLESS ``methods_is_machinery`` is False (a required
    ``contract.sections`` Methods stays in the scored body). The caller folds the
    appendix under the single typed ``## Appendix`` boundary alongside the
    reliability header.

    POSITION ONLY: every input block is placed EXACTLY ONCE across the two
    returned strings; NOTHING is dropped or edited. A render-time multiset
    assertion (in the caller) confirms permutation-only. PURE (no I/O)."""
    methods_in_body = "" if methods_is_machinery else methods_md
    methods_in_appendix = methods_md if methods_is_machinery else ""

    if archetype.kf_position == "lead":
        scored_body = (
            key_findings_md
            + methods_in_body
            + sections_concat
            + depth_layer_md
            + biblio_section_md
        )
    elif archetype.kf_position == "tail":
        scored_body = (
            methods_in_body
            + sections_concat
            + depth_layer_md
            + key_findings_md
            + biblio_section_md
        )
    else:  # "after_framing" (default review shape == landed order)
        scored_body = (
            methods_in_body
            + sections_concat
            + depth_layer_md
            + key_findings_md
            + biblio_section_md
        )

    machinery_appendix = methods_in_appendix + cwf_disclosed_md + drop_disclosure_md
    return scored_body, machinery_appendix
