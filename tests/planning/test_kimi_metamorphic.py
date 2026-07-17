"""Metamorphic tests for the Kimi K3 gate review (F1-F7).

Each test pins a class of prompt Kimi named as currently broken or vacuously
passing, and asserts the FIXED behaviour. All offline + deterministic (the LLM is
the same worst-case ``_EmptyContractClient`` stub the gate tests use — it drops
everything, so ONLY the deterministic clause ledger + merge + projection are under
test). Every test runs behind PG_GATE=1 (the fixes are gated; OFF is byte-identical).

Classes (Kimi §3 + the fix brief):
  * F3  "X is commonly used since 2018"      -> no hard constraint, no invented date
  * F3  "the avoidance of bias"              -> no exclusion ("avoidance" != "avoid")
  * F3  "What must companies disclose ...?"  -> no oblige-block (a question, not an order)
  * F5  "no blogs or forums"                 -> BOTH excluded, negative predicate
  * F1  "Use Reuters and AP."                -> named INCLUDES (not coverage, not exclusion)
  * F1  "do not cite blogs"                  -> scope exclusion -> RetrievalPolicy
        .excluded_source_kinds AND absent from query text AND not a coverage req
  * F4  "U.S. government reports only"        -> abbreviation dot does not fragment
  * F7  "after 2024" vs "since 2024"          -> strict vs inclusive lower bound
  * i18n a French prompt                      -> DOCUMENTED known gap (English-only cues)
"""

from __future__ import annotations

import asyncio
import json

import pytest

from src.polaris_graph.planning import clause_ledger as cl
from src.polaris_graph.planning.candidate_adapter import reconcile_candidates
from src.polaris_graph.planning.planning_gate_schema import (
    FORCE_HARD,
    ResearchExecutionPlan,
)
from src.polaris_graph.planning.research_planning_gate import run_research_planning_gate
from src.polaris_graph.planning.retrieval_projection import from_contract_and_plan


# ---------------------------------------------------------------------------
# worst-case stub: the LLM drops everything -> only deterministic core is tested
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _gate_on(monkeypatch):
    """Every fix is gated behind PG_GATE (OFF is byte-identical); turn it ON so the
    deterministic ledger + merge + projection run under test."""
    monkeypatch.setenv("PG_GATE", "1")


class _Resp:
    def __init__(self, content: str) -> None:
        self.content = content


class _EmptyContractClient:
    async def generate(self, prompt, system="", max_tokens=4096, temperature=0.0, **_):
        if system.startswith("You are the POLARIS Research Contract"):
            return _Resp(json.dumps({"contract": {"objective": [{
                "term_id": "objective.question",
                "dimension": "objective.question",
                "value": "x", "origin": "inferred", "force": "open",
            }]}, "clause_coverage": []}))
        return _Resp(json.dumps({"plan": {"threads": [], "query_intents": [],
                                          "budget": {}}}))


def _run(prompt: str):
    return asyncio.run(run_research_planning_gate(
        prompt, mode="autonomous", client=_EmptyContractClient(),
    ))


# ---------------------------------------------------------------------------
# F3 — word-boundary matching + instruction-vs-world-statement guard
# ---------------------------------------------------------------------------

def test_f3_commonly_is_not_the_restrict_cue_only():
    """'X is commonly used since 2018': 'commonly' must not match the 'only'
    restrict cue, and the world-statement guard must stop the date from inheriting
    a HARD gate. No fabricated hard constraint, no invented hard date."""
    text = "X is commonly used since 2018"
    assert cl._deontic_hit(text) is None, "a world statement is not an instruction"
    # even the date parser must not hard-bind it (no enclosing hard 'only' scope).
    clauses = cl.segment_clauses(text)
    scopes = cl.hard_restriction_scopes(clauses)
    dates = cl.parse_date_bound(text, hard_scopes=scopes)
    assert all(d.force != FORCE_HARD for d in dates), "no invented HARD date bound"


def test_f3_avoidance_is_not_the_exclude_cue_avoid():
    """'the avoidance of bias': the strong exclude cue 'avoid' must not fire on the
    substring inside 'avoidance' — no fabricated exclusion."""
    assert cl.parse_exclusions("the avoidance of bias") == []
    assert cl._deontic_hit("the avoidance of bias") is None


def test_f3_question_about_obligations_does_not_block():
    """'What must companies disclose under CSRD?': a QUESTION mentioning 'must' is a
    research objective, not an obligation instruction. It must NOT fire oblige, must
    NOT become an opaque hard term, and must NOT block the artifact."""
    prompt = "What must companies disclose under CSRD?"
    assert cl._deontic_hit(prompt) is None
    result = _run(prompt)
    # no hard opaque term -> not blocked_unsupported.
    assert result.enforcement_state != "blocked_unsupported"
    assert not any(t.is_opaque() and t.is_hard()
                   for t in result.contract.all_terms())


# ---------------------------------------------------------------------------
# F5 — coordinated exclusions capture ALL members
# ---------------------------------------------------------------------------

def test_f5_coordinated_exclusion_captures_all_members():
    """'no blogs or forums' must exclude BOTH blogs and forums (the old tail regex
    truncated at 'or' and lost 'forums')."""
    ex = cl.parse_exclusions("no blogs or forums")
    vals = {c.value for c in ex}
    assert "blogs" in vals and "forums" in vals
    # both are hard NOT_IN content.exclusion candidates (never positive).
    for c in ex:
        assert c.force == FORCE_HARD
        assert c.dimension == "content.exclusion"


def test_f5_coordinated_exclusion_spans_are_exact():
    prompt = "no blogs or forums"
    for c in cl.parse_exclusions(prompt):
        sp = c.spans[0]
        assert prompt[sp.start:sp.end] == sp.quote  # quote-equality holds per member


# ---------------------------------------------------------------------------
# F1 — named includes vs named excludes vs exclusions (routing, not inversion)
# ---------------------------------------------------------------------------

def test_f1_use_reuters_and_ap_are_positive_includes_never_exclusions():
    """'Use Reuters and AP.' must produce POSITIVE INCLUDES (allowed source kinds
    or named inclusions — a retrieval boost), NEVER exclusions and NEVER required
    coverage. (Whether the deterministic path classifies them as a named source vs
    a source-kind include is an intake-extractor concern; the F1 invariant is only
    that a stated INCLUDE is never inverted into an exclusion/coverage lane.)"""
    result = _run("Analyze wire coverage. Use Reuters and AP.")
    proj = from_contract_and_plan(
        result.contract, result.plan, original_prompt=result.artifact.original_prompt,
    )
    pol = proj.to_retrieval_policy()
    positive = {n.lower() for n in pol.named_inclusions} | {
        a.lower() for a in pol.allowed_source_kinds
    }
    assert positive & {"reuters", "ap"}, \
        f"Reuters/AP must be a positive include: {pol.to_dict()}"
    # NEVER an exclusion.
    excl_l = {n.lower() for n in pol.named_exclusions} | {
        e.lower() for e in pol.excluded_source_kinds
    }
    assert not (excl_l & {"reuters", "ap"}), "a stated include must never be excluded"
    # NEVER a required coverage requirement.
    assert not any(
        s in str(cr.statement.value or "").lower()
        for cr in result.contract.coverage for s in ("reuters", "ap")
    ), "a stated include must never become a required CoverageRequirement"


def test_f1_named_exclude_is_a_negative_named_predicate():
    """A candidate-level named EXCLUDE must route to scope.excluded_sources ->
    RetrievalPolicy.named_exclusions, never content-coverage."""
    from src.polaris_graph.planning.candidate_adapter import (
        CandidateConstraint, PromptSpan as CSpan, _stamp_ir,
    )
    from src.polaris_graph.planning.planning_gate_schema import (
        ResearchContract, ContractTerm, PromptSpan, ORIGIN_EXPLICIT, OP_NOT_IN,
    )
    from src.polaris_graph.planning.retrieval_projection import from_contract_and_plan
    # a named-exclude authored term (as the fixed adapter routes it).
    c = ResearchContract(scope=[ContractTerm(
        term_id="ne", dimension="scope.excluded_sources", value="Reuters",
        origin=ORIGIN_EXPLICIT, force=FORCE_HARD, operator=OP_NOT_IN,
        spans=[PromptSpan(0, 7, "Reuters")],
    )])
    proj = from_contract_and_plan(c, ResearchExecutionPlan())
    assert "Reuters" in proj.named_exclusions
    assert "Reuters" not in proj.hard_scope_terms  # never query text


# ---------------------------------------------------------------------------
# F1 + F2 — 'do not cite blogs': scope exclusion, absent from query text, not coverage
# ---------------------------------------------------------------------------

def test_f1_f2_do_not_cite_blogs_is_a_negative_scope_predicate():
    prompt = "Analyze the ad market. Do not cite blogs."
    result = _run(prompt)

    # (F1) lands in scope as scope.excluded_source_kinds, never content coverage.
    excl_scope = [t for t in result.contract.scope
                  if t.dimension == "scope.excluded_source_kinds"]
    assert any("blog" in str(t.value).lower() and t.operator == "NOT_IN"
               for t in excl_scope), f"blogs not a scope exclusion: {excl_scope}"
    assert not any("blog" in str(cr.statement.value or "").lower()
                   for cr in result.contract.coverage), \
        "an exclusion must NEVER be a required CoverageRequirement (F1)"

    proj = from_contract_and_plan(
        result.contract, result.plan, original_prompt=prompt,
    )
    pol = proj.to_retrieval_policy()
    # (F1) reaches RetrievalPolicy.excluded_source_kinds.
    assert any("blog" in e.lower() for e in pol.excluded_source_kinds), \
        f"blogs not in policy.excluded_source_kinds: {pol.excluded_source_kinds}"

    # (F2) absent from ALL positive query text — never a suffix steering discovery.
    queries = proj.to_amplified_queries(base_question=prompt)
    assert not any("blog" in q.lower() for q in queries), \
        f"'blog' must never appear in positive query text: {queries}"
    assert not any("blog" in s.lower() for s in proj.hard_scope_terms)

    # (F1) surfaced as an op=exclude facet in the legacy protocol shape.
    sp = pol.to_scope_protocol()
    exclude_facets = [f for f in sp["scope_constraints"]["facets"]
                      if f["op"] == "exclude"]
    assert any("blog" in f["facet_id"].lower() for f in exclude_facets), \
        f"no exclude facet for blogs: {exclude_facets}"


def test_f2_opaque_term_never_reaches_positive_query_text():
    """A hard OPAQUE clause ('you must consult industry white papers') is a
    post-fetch eligibility predicate — never a positive query suffix (the old back
    door that folded the raw clause into hard_scope_terms)."""
    prompt = "Summarize telecom trends. You must consult industry white papers."
    result = _run(prompt)
    proj = from_contract_and_plan(result.contract, result.plan, original_prompt=prompt)
    # if an opaque term was produced, it lives in the eligibility bucket, not text.
    queries = proj.to_amplified_queries(base_question=prompt)
    for op in proj.opaque_eligibility_terms:
        assert not any(op.lower() in q.lower() for q in queries)
    # opaque terms never leak into hard_scope_terms.
    assert not any(op in proj.hard_scope_terms for op in proj.opaque_eligibility_terms)


# ---------------------------------------------------------------------------
# F4 — segmentation does not split on abbreviation dots
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("prompt", [
    "Only use U.S. government reports.",
    "Cite peer-reviewed work, e.g. journal articles only.",
    "Use i.e. authoritative sources only.",
    "Compare v2.1 and v3.5 release notes only.",
])
def test_f4_abbreviation_dots_do_not_fragment_clauses(prompt):
    """A restriction scope must stay attached to the noun it scopes: 'U.S.' /
    'e.g.' / 'i.e.' / version numbers must not become clause boundaries."""
    clauses = cl.segment_clauses(prompt)
    joined = " ".join(c.text for c in clauses)
    # the abbreviation stays whole inside a single clause.
    assert any("U.S." in c.text or "e.g." in c.text or "i.e." in c.text
               or "v2.1" in c.text for c in clauses) or "." not in prompt[:-1]
    # no single-letter fragment clause (the "Only use U" | "S. ..." bug).
    assert not any(c.text.strip() in {"S", "U", "g", "e"} for c in clauses), joined


def test_f4_us_restriction_scope_covers_its_noun():
    """'U.S. government reports only' — the 'only' restriction and the noun it
    scopes must be in ONE clause (else the scope detaches from the kind)."""
    prompt = "Use U.S. government reports only."
    clauses = cl.segment_clauses(prompt)
    # exactly one non-trivial clause holds the whole instruction.
    bearing = [c for c in clauses if "U.S." in c.text and "only" in c.text.lower()]
    assert bearing, [c.text for c in clauses]


# ---------------------------------------------------------------------------
# F7 — 'after YYYY' is strict; 'since/from YYYY' is inclusive
# ---------------------------------------------------------------------------

def test_f7_after_year_is_strict_lower_bound():
    dates = cl.parse_date_bound("cite sources after 2024", hard_scopes=[])
    assert dates and dates[0].value == "2025-01-01", \
        "'after 2024' must be GTE 2025-01-01 (strict), not 2024-01-01"


@pytest.mark.parametrize("prompt", ["since 2024", "from 2024 onward"])
def test_f7_since_from_year_is_inclusive_lower_bound(prompt):
    dates = cl.parse_date_bound(prompt, hard_scopes=[])
    assert dates and dates[0].value == "2024-01-01", \
        f"{prompt!r} must be GTE 2024-01-01 (inclusive)"


# ---------------------------------------------------------------------------
# i18n — French prompt: DOCUMENTED KNOWN GAP (the cue lexicon is English-only)
# ---------------------------------------------------------------------------

def test_french_prompt_is_a_documented_known_gap():
    """KNOWN GAP (Kimi BS4): the deontic/exclusion lexicon is English-only, so a
    French exclusion ('ne citez pas de blogs') is NOT detected by the deterministic
    parsers. This test PINS the gap so a future localization change is caught
    (flip the assertion when French cues land). It documents, it does not endorse.

    Critically, the gate must still FAIL SAFE: an undetected constraint yields NO
    fabricated positive constraint (better a miss than an inversion) — the French
    clause never becomes a positive 'blogs' query steer."""
    prompt = "Analysez le marche. Ne citez pas de blogs."
    # the English exclusion lexicon does not fire on the French cue.
    fr_exclusions = cl.parse_exclusions(prompt)
    assert not any("blog" in c.value.lower() for c in fr_exclusions), \
        "if this fails, French exclusions are now handled — update this test"
    # fail-safe: no positive 'blogs' scope term is fabricated from the miss.
    result = _run(prompt)
    proj = from_contract_and_plan(result.contract, result.plan, original_prompt=prompt)
    assert not any("blog" in s.lower() for s in proj.hard_scope_terms), \
        "an undetected exclusion must never invert into a positive query steer"
