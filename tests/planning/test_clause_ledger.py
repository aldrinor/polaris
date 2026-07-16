"""Tests for the lossless clause ledger (Research Planning Gate — Phase B).

Offline + deterministic (no LLM, no network). These assert the generality-gap
closures from the build task:

  1. clause segmentation is deterministic, stable-ID'd, quote-equality-exact;
  2. deontic-driven detection marks a constraint-bearing clause (and never
     downgrades one);
  3. NORM_OPAQUE preservation: an un-normalizable deontic clause becomes a
     first-class opaque ContractTerm (never silence);
  4. the completeness validator fires on an undispositioned deontic clause;
  5. each new deterministic parser (quality / negation-exclusion / coordination /
     date-hardness-inheritance) fires correctly and NEVER fabricates a span.
"""

from __future__ import annotations

from src.polaris_graph.planning.clause_ledger import (
    DISP_EXPLICIT_CONSTRAINT,
    DISP_OBJECTIVE,
    ledger_candidates,
    opaque_terms_for_uncovered,
    parse_coordination,
    parse_date_bound,
    parse_exclusions,
    parse_quality,
    segment_clauses,
    validate_completeness,
)
from src.polaris_graph.planning.clause_ledger import hard_restriction_scopes
from src.polaris_graph.planning.planning_gate_schema import (
    FORCE_HARD,
    FORCE_PREFER,
    NORM_OPAQUE,
    OP_GTE,
    OP_IN,
    OP_NOT_IN,
    ORIGIN_EXPLICIT,
    ContractTerm,
    PromptSpan,
    ResearchContract,
)

PROMPT = (
    "Analyze the market. Only use news and company press releases from 2024 "
    "onward. Do not cite blogs. Use high-quality sources."
)


# ---------------------------------------------------------------------------
# (1) Segmentation — deterministic, stable ids, quote-equality exact
# ---------------------------------------------------------------------------

def test_segmentation_is_quote_equality_exact():
    clauses = segment_clauses(PROMPT)
    assert clauses, "prompt must segment into at least one clause"
    for c in clauses:
        assert PROMPT[c.start:c.end] == c.text, "clause span must be verbatim"
        assert c.clause_id.startswith("clause_")


def test_segmentation_is_deterministic_and_stable():
    a = segment_clauses(PROMPT)
    b = segment_clauses(PROMPT)
    assert [c.clause_id for c in a] == [c.clause_id for c in b]
    assert [(c.start, c.end) for c in a] == [(c.start, c.end) for c in b]


def test_segmentation_keeps_coordinated_phrase_and_date_in_one_clause():
    # "and" must NOT split — the coordinated source list and the trailing date
    # modifier must share the enclosing "Only …" clause so both inherit hardness.
    clauses = segment_clauses(PROMPT)
    only_clause = next(c for c in clauses if c.text.lower().startswith("only use"))
    assert "news and company press releases" in only_clause.text
    assert "from 2024" in only_clause.text


def test_objective_clause_is_tagged_objective():
    clauses = segment_clauses(PROMPT)
    first = clauses[0]
    assert first.text == "Analyze the market"
    assert first.disposition == DISP_OBJECTIVE
    assert first.deontic is None


# ---------------------------------------------------------------------------
# (2) Deontic detection — constraint-bearing clauses
# ---------------------------------------------------------------------------

def test_deontic_cues_mark_constraint_clauses():
    clauses = segment_clauses(PROMPT)
    by_family = {c.deontic.family: c for c in clauses if c.deontic}
    assert "restrict" in by_family, "'Only' must mark a restriction constraint"
    assert "exclude" in by_family, "'Do not cite' must mark an exclusion constraint"
    assert "quality" in by_family, "'high-quality' must mark a quality constraint"
    for c in clauses:
        if c.deontic:
            assert c.disposition == DISP_EXPLICIT_CONSTRAINT
            assert c.is_constraint_bearing()


def test_deontic_cue_carries_a_verbatim_span():
    clauses = segment_clauses(PROMPT)
    for c in clauses:
        if c.deontic:
            # the cue is a real substring of the clause (not a normalized token).
            assert c.deontic.cue.lower() in c.text.lower()


def test_prohibition_and_restriction_are_hard_preference_is_soft():
    clauses = segment_clauses(
        "You should prefer recent studies. Do not cite blogs."
    )
    prefer = next(c for c in clauses if c.deontic and c.deontic.family == "prefer")
    exclude = next(c for c in clauses if c.deontic and c.deontic.family == "exclude")
    assert prefer.deontic.force == FORCE_PREFER
    assert exclude.deontic.force == FORCE_HARD


# ---------------------------------------------------------------------------
# (5a) QUALITY parser
# ---------------------------------------------------------------------------

def test_quality_parser_fires_on_bare_adjective():
    p = "Use high-quality sources."
    cands = parse_quality(p, hard_scopes=[])
    assert len(cands) == 1
    q = cands[0]
    assert q.dimension == "source.quality"
    assert q.value == "high"
    assert q.force == FORCE_PREFER  # no restriction scope → soft
    assert q.spans[0].quote == "high-quality"


def test_quality_inherits_hardness_under_restriction_scope():
    p = "Only cite peer-reviewed work."
    scopes = hard_restriction_scopes(segment_clauses(p))
    cands = parse_quality(p, hard_scopes=scopes)
    assert cands and cands[0].force == FORCE_HARD, (
        "quality under an 'only' scope inherits hardness"
    )


def test_quality_never_fires_without_a_quality_phrase():
    # the recon's false-positive class: a bare "journal" must NOT invent quality.
    assert parse_quality("Only cite journal articles.", hard_scopes=[]) == []


# ---------------------------------------------------------------------------
# (5b) NEGATION / EXCLUSION parser
# ---------------------------------------------------------------------------

def test_exclusion_fires_on_unknown_kind():
    # "blogs" is not an ontology facet — the recon's exact miss. It MUST still be
    # caught, as a NOT_IN exclusion, never a positive query token.
    cands = parse_exclusions("Do not cite blogs.")
    assert len(cands) == 1
    e = cands[0]
    assert e.dimension == "content.exclusion"
    assert e.value == "blogs"
    assert e.force == FORCE_HARD
    assert e.operator == OP_NOT_IN


def test_exclusion_span_is_exact_verbatim():
    p = "Do not cite blogs."
    cands = parse_exclusions(p)
    sp = cands[0].spans[0]
    assert p[sp.start:sp.end] == sp.quote == "Do not cite blogs"


def test_exclusion_handles_no_and_avoid_and_exclude():
    for text in (
        "Avoid press releases in this report.",
        "Exclude wikipedia entirely.",
        "No blogs.",
    ):
        cands = parse_exclusions(text)
        assert cands, f"exclusion must fire on {text!r}"
        assert cands[0].operator == OP_NOT_IN


def test_weak_negation_does_not_fabricate_prose_exclusions():
    # "no"/"without" appear constantly in ordinary prose; they must NOT become
    # source exclusions unless the noun is a plausible source kind. Otherwise a
    # fabricated NOT_IN would poison retrieval (excluding a wanted topic).
    for prose in (
        "There is no clear consensus on this topic.",
        "The market grew without interruption last year.",
        "There were no major disruptions.",
    ):
        assert parse_exclusions(prose) == [], (
            f"weak negation must not fabricate an exclusion from prose: {prose!r}"
        )
    # but a weak negation before a SOURCE noun still fires.
    assert parse_exclusions("Use reputable outlets; no tabloids.")


# ---------------------------------------------------------------------------
# (5c) COORDINATION parser
# ---------------------------------------------------------------------------

def test_coordination_makes_an_allowed_set():
    p = "Only use news and company press releases from 2024 onward."
    scopes = hard_restriction_scopes(segment_clauses(p))
    cands = parse_coordination(p, hard_scopes=scopes)
    values = sorted(c.value for c in cands)
    assert values == ["company press releases", "news"], values
    # both members are IN, hard (under 'only'), and share one boolean_group.
    groups = {c.detail.get("boolean_group") for c in cands}
    assert len(groups) == 1
    for c in cands:
        assert c.operator == OP_IN
        assert c.force == FORCE_HARD
        assert c.spans and p[c.spans[0].start:c.spans[0].end] == c.spans[0].quote


def test_coordination_strips_trailing_date_fragment():
    p = "Only use news and press releases from 2024."
    cands = parse_coordination(p, hard_scopes=[])
    assert all("from" not in c.value for c in cands), (
        "a trailing 'from 2024' must not leak into a member value"
    )


def test_coordination_ignores_non_lists():
    assert parse_coordination("Only use journal articles.", hard_scopes=[]) == []


def test_coordination_handles_oxford_comma():
    p = "Use news, press releases, and analyst reports."
    vals = sorted(c.value for c in parse_coordination(p, hard_scopes=[]))
    assert vals == ["analyst reports", "news", "press releases"], vals
    # no leaked "and" prefix on the last member.
    assert all(not v.startswith("and ") for v in vals)


def test_coordination_ignores_non_source_verbs():
    # "produce"/"analyze"/"compare" are not source-leads → no coordination.
    assert parse_coordination("We produce reports and dashboards.", hard_scopes=[]) == []
    assert parse_coordination("Compare revenue and profit.", hard_scopes=[]) == []


# ---------------------------------------------------------------------------
# (5d) DATE-HARDNESS INHERITANCE parser
# ---------------------------------------------------------------------------

def test_date_bound_gte_with_hardness_inheritance():
    p = "Only use sources from 2024 onward."
    scopes = hard_restriction_scopes(segment_clauses(p))
    cands = parse_date_bound(p, hard_scopes=scopes)
    assert len(cands) == 1
    d = cands[0]
    assert d.dimension == "date.recency"
    assert d.value == "2024-01-01"
    assert d.operator == OP_GTE
    assert d.force == FORCE_HARD, "date under an 'only' scope inherits hardness"


def test_date_bound_soft_without_restriction_scope():
    p = "We are interested in trends since 2020."
    cands = parse_date_bound(p, hard_scopes=[])
    assert cands and cands[0].force == FORCE_PREFER
    assert cands[0].value == "2020-01-01"


def test_date_bound_dedups_overlapping_patterns():
    # "from 2024 onward" matches both patterns; must yield ONE candidate.
    cands = parse_date_bound("from 2024 onward", hard_scopes=[])
    assert len(cands) == 1


# ---------------------------------------------------------------------------
# (3) NORM_OPAQUE preservation
# ---------------------------------------------------------------------------

def test_opaque_term_authored_for_uncovered_deontic_clause():
    p = "You must consult industry white papers issued by network operators."
    clauses = segment_clauses(p)
    # no contract term covers the clause → it must become an opaque term.
    terms = opaque_terms_for_uncovered(p, clauses, _contract_with_terms([]))
    assert len(terms) == 1
    t = terms[0]
    assert t.normalization_status == NORM_OPAQUE
    assert t.is_opaque()
    assert t.origin == ORIGIN_EXPLICIT
    assert t.force == FORCE_HARD, "an obligation cue is hard"
    deontic_clause = next(c for c in clauses if c.deontic)
    assert t.value == deontic_clause.text, "the opaque term preserves the raw clause"
    assert t.spans and p[t.spans[0].start:t.spans[0].end] == t.spans[0].quote


def test_opaque_not_authored_when_a_term_covers_the_clause():
    p = "Do not cite blogs."
    clauses = segment_clauses(p)
    # a TERM whose span overlaps the exclusion clause → no opaque term.
    term = ContractTerm(
        term_id="t.excl", dimension="content.exclusion", value="blogs",
        origin=ORIGIN_EXPLICIT, force=FORCE_HARD,
        spans=[PromptSpan(0, len(p) - 1, p[:-1])],
    )
    terms = opaque_terms_for_uncovered(p, clauses, _contract_with_terms([term]))
    assert terms == [], "a covered clause must NOT also spawn an opaque term"


def test_opaque_preserved_is_never_dropped_and_records_the_clause():
    p = "Ensure at least three regulatory filings are consulted."
    clauses = segment_clauses(p)
    terms = opaque_terms_for_uncovered(p, clauses, _contract_with_terms([]))
    assert terms, "an un-normalizable obligation must be preserved, never silent"
    # the clause records the opaque term id back-reference.
    deontic_clause = next(c for c in clauses if c.deontic)
    assert deontic_clause.term_ids == [terms[0].term_id]


# ---------------------------------------------------------------------------
# (4) COMPLETENESS validator
# ---------------------------------------------------------------------------

def _contract_with_terms(terms: list[ContractTerm]) -> ResearchContract:
    return ResearchContract(scope=list(terms))


def test_completeness_flags_an_undispositioned_deontic_clause():
    p = "Do not cite blogs."
    clauses = segment_clauses(p)
    # a contract with NO term covering the exclusion clause.
    errors = validate_completeness(clauses, _contract_with_terms([]))
    codes = {e.code for e in errors}
    assert "clause_undispositioned" in codes, (
        "a deontic clause with no term must fail completeness (lossless gate)"
    )


def test_completeness_passes_when_a_term_covers_the_clause():
    p = "Do not cite blogs."
    clauses = segment_clauses(p)
    term = ContractTerm(
        term_id="t.excl", dimension="content.exclusion", value="blogs",
        origin=ORIGIN_EXPLICIT, force=FORCE_HARD,
        spans=[PromptSpan(0, len(p) - 1, p[:-1])],
    )
    errors = validate_completeness(clauses, _contract_with_terms([term]))
    assert [e for e in errors if e.code == "clause_undispositioned"] == []


def test_completeness_ignores_non_deontic_clauses():
    p = "The market has grown steadily."  # pure context, no cue
    clauses = segment_clauses(p)
    assert all(not c.is_constraint_bearing() for c in clauses)
    assert validate_completeness(clauses, _contract_with_terms([])) == []


# ---------------------------------------------------------------------------
# ledger_candidates driver — the augmenting set the merge consumes
# ---------------------------------------------------------------------------

def test_ledger_candidates_cover_every_gap_in_one_pass():
    clauses = segment_clauses(PROMPT)
    cands = ledger_candidates(PROMPT, clauses)
    dims = {c.dimension for c in cands}
    assert {"source.quality", "content.exclusion", "source.types", "date.recency"} <= dims
    # everything the ledger emits carries a verbatim span (never fabricated).
    for c in cands:
        for sp in c.spans:
            assert PROMPT[sp.start:sp.end] == sp.quote
