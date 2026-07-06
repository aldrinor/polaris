"""I-deepfix-001 Wave-2d (#1344) — two-sided pro/con debate handling.

ISOLATED + OFFLINE: no paid API, no GPU, no model. Drives (a) the shared plan-time debate detector, (b)
the composition-side asymmetry-disclosure helper, and (c) the retrieval-side ``counter_evidence`` lens
guarantee — all directly, with a DETERMINISTIC stub LLM. The con clause itself is composed by the
UNCHANGED per-basket path (verified against its OWN basket-scoped pool); Wave-2d never composes, so these
tests exercise its actual surface: detection, con-presence inspection over composed [#ev] tokens, and the
never-fabricate-balance disclosure.

Asserts:
  1. ``is_debate_question`` precision: True on explicit opposition-pair / debate framing; False on plain
     mechanism / bare ``A vs B`` comparison.
  2. ``_is_debate_section`` reads the section PLAN framing (title+focus), not composed content.
  3. Flags default OFF => the disclosure pass and the counter_evidence guarantee are no-ops.
  4. ON both sides present (verified pro clause AND verified con clause) => NO disclosure.
  5. ON one-sided (verified pro, con absent / unverifiable) => exactly one honest marker-less asymmetry
     disclosure; con is NEVER fabricated (no [#ev] token, no con prose); inputs never mutated.
  6. A gap section (no verified units) => no disclosure (no noise).
  7. An M6 conflict unit (cites both pro + con) counts as two-sided.
  8. ON counter_evidence guarantee: a debate question keeps the ``counter_evidence`` angle even under a
     reduced ``PG_EXPERT_FACET_ANGLES`` budget; OFF => byte-identical (angle truncated).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Repo root on path.
_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

# Offline: no judge calls, deterministic behavior.
os.environ.setdefault("PG_VERIFICATION_MODE", "off")

from src.polaris_graph.retrieval import expert_facet_planner as efp  # noqa: E402
from src.polaris_graph.generator import multi_section_generator as msg  # noqa: E402
from src.polaris_graph.generator.multi_section_generator import SectionPlan  # noqa: E402
from src.polaris_graph.synthesis.credibility_pass import BasketMember, ClaimBasket  # noqa: E402


# ── tiny builders (real dataclasses, faithful shapes) ─────────────────────────────────────────────
def _member(eid: str) -> BasketMember:
    return BasketMember(
        evidence_id=eid, source_url="", source_tier="",
        origin_cluster_id=f"origin::{eid}", credibility_weight=1.0, authority_score=1.0,
        span=(0, 10), direct_quote="finding xx", span_verdict="SUPPORTS",
    )


def _basket(cluster_id: str, subject: str, eids, *, refuters=()) -> ClaimBasket:
    members = [_member(e) for e in eids]
    return ClaimBasket(
        claim_cluster_id=cluster_id, claim_text=f"{subject} claim", subject=subject,
        predicate="predicate", supporting_members=members, refuter_cluster_ids=tuple(refuters),
        weight_mass=1.0, total_clustered_origin_count=len(members),
        verified_support_origin_count=len(members), basket_verdict="full",
    )


def _unit(eid: str) -> str:
    """A composed verified clause carrying one provenance token for evidence_id ``eid``."""
    return f"A verified clause. [#ev:{eid}:0-10]"


def _stub_llm(_prompt: str) -> str:
    """Deterministic facet-tree reply (two clean, hyphen-free facet names)."""
    return "First facet\nSecond facet"


# ── 1. detector precision ─────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("text", [
    "benefits and risks of AI in medicine",
    "the advantages and disadvantages of remote work",
    "positive and negative views on nuclear power",
    "pros and cons of a four-day week",
    "risks and benefits of the vaccine",
    "advantages vs disadvantages of the merger",
    "positive vs negative effects of the drug",
    "the case for and against rent control",
    "information for and against the proposal",
    "the debate over the minimum wage",
    "a controversial and contested policy",
    "arguments on both sides of the issue",
    "supporters and critics of the reform",
    "strengths and weaknesses of the framework",
])
def test_is_debate_question_positive(text):
    assert efp.is_debate_question(text)


@pytest.mark.parametrize("text", [
    "mechanism of action of statins",
    "how does photosynthesis work",
    "drug A vs drug B efficacy",          # bare comparison, NOT a pro/con debate
    "quantitative comparison of GDP growth across regions",
    "the history of the internet",
    "waiting for and hoping to see results",
])
def test_is_debate_question_negative(text):
    assert not efp.is_debate_question(text)


# ── 2. section detector reads the PLAN framing ───────────────────────────────────────────────────
def test_is_debate_section_uses_plan_framing():
    debate = SectionPlan(title="Benefits and Risks",
                         focus="Weigh the benefits and risks of the policy.", ev_ids=[])
    plain = SectionPlan(title="Mechanism",
                        focus="How the drug works at the receptor.", ev_ids=[])
    assert msg._is_debate_section(debate) is True
    assert msg._is_debate_section(plain) is False


# ── 3. flags default OFF (byte-identical guard) ──────────────────────────────────────────────────
def test_flags_default_off(monkeypatch):
    monkeypatch.delenv("PG_TWO_SIDED_DEBATE", raising=False)
    assert msg._two_sided_debate_enabled() is False
    assert efp.two_sided_debate_enabled() is False


# ── 4. ON both sides present => NO disclosure ────────────────────────────────────────────────────
def test_both_sides_present_no_disclosure():
    pro = _basket("pro1", "Policy", ["evp"], refuters=["con1"])
    con = _basket("con1", "Policy", ["evc"])
    section = SectionPlan(title="Benefits and Risks", focus="benefits and risks of the policy",
                          ev_ids=["evp", "evc"])
    out = msg._maybe_two_sided_debate_disclosure(
        section, [pro, con], [_unit("evp"), _unit("evc")], [],
    )
    assert out == []  # both a verified pro AND a verified con clause => nothing added


# ── 5a. one-sided: con basket present but its clause did NOT compose => disclose ──────────────────
def test_one_sided_con_basket_uncomposed_discloses():
    pro = _basket("pro1", "Policy", ["evp"], refuters=["con1"])
    con = _basket("con1", "Policy", ["evc"])
    section = SectionPlan(title="Benefits and Risks", focus="benefits and risks of the policy",
                          ev_ids=["evp"])
    out = msg._maybe_two_sided_debate_disclosure(section, [pro, con], [_unit("evp")], [])
    assert len(out) == 1
    assert out[0].startswith(msg._TWO_SIDED_DEBATE_DISCLOSURE_PREFIX)
    assert "[#ev:" not in out[0]              # never fabricates a con clause / provenance token
    assert "policy" in out[0].lower()         # names the section subject honestly


# ── 5b. one-sided: no con basket at all => disclose, preserving existing disclosures ──────────────
def test_one_sided_no_con_basket_discloses():
    pro = _basket("pro1", "Policy", ["evp"])  # no refuters => no con side
    section = SectionPlan(title="Pros and Cons", focus="pros and cons of the policy", ev_ids=["evp"])
    out = msg._maybe_two_sided_debate_disclosure(section, [pro], [_unit("evp")], ["existing disclosure"])
    assert "existing disclosure" in out                              # existing held-aside kept
    assert out[-1].startswith(msg._TWO_SIDED_DEBATE_DISCLOSURE_PREFIX)
    assert "[#ev:" not in out[-1]


# ── 5c. inputs are never mutated; never fabricates prose ─────────────────────────────────────────
def test_inputs_not_mutated():
    pro = _basket("pro1", "Policy", ["evp"])
    real = [_unit("evp")]
    disc = ["x"]
    section = SectionPlan(title="Pros and Cons", focus="pros and cons of the policy", ev_ids=["evp"])
    out = msg._maybe_two_sided_debate_disclosure(section, [pro], real, disc)
    assert disc == ["x"]              # input disclosures list not mutated
    assert real == [_unit("evp")]     # composed units untouched (read-only inspection)
    assert out is not disc            # a new list is returned


# ── 6. gap section (no verified units) => no disclosure noise ─────────────────────────────────────
def test_empty_section_no_disclosure():
    pro = _basket("pro1", "Policy", ["evp"])
    section = SectionPlan(title="Pros and Cons", focus="pros and cons of the policy", ev_ids=["evp"])
    out = msg._maybe_two_sided_debate_disclosure(section, [pro], [], [])
    assert out == []


# ── 7. an M6 conflict unit (both pro + con tokens) counts as two-sided ────────────────────────────
def test_conflict_unit_counts_two_sided():
    pro = _basket("pro1", "Policy", ["evp"], refuters=["con1"])
    con = _basket("con1", "Policy", ["evc"])
    conflict_unit = "Pro clause [#ev:evp:0-10]; in contrast, con clause [#ev:evc:0-10]"
    section = SectionPlan(title="Benefits and Risks", focus="benefits and risks of the policy",
                          ev_ids=["evp", "evc"])
    out = msg._maybe_two_sided_debate_disclosure(section, [pro, con], [conflict_unit], [])
    assert out == []


# ── 8. counter_evidence retrieval guarantee (expert_facet_planner) ────────────────────────────────
def test_angle_lenses_for_guarantee():
    base = [label for label, _ in efp._angle_lenses_for(2, False)]
    assert base == ["mechanism", "stakeholder"]                  # OFF => byte-identical slice
    guaranteed = [label for label, _ in efp._angle_lenses_for(2, True)]
    assert "counter_evidence" in guaranteed                       # ON => con angle guaranteed
    full = [label for label, _ in efp._angle_lenses_for(5, True)]
    assert full.count("counter_evidence") == 1                    # no duplicate when already present


def test_counter_evidence_guaranteed_on(monkeypatch):
    monkeypatch.setenv("PG_TWO_SIDED_DEBATE", "1")
    monkeypatch.setenv("PG_EXPERT_FACET_ANGLES", "2")  # would truncate counter_evidence (index 2)
    queries = efp.facet_seed_queries("benefits and risks of AI", _stub_llm)
    assert any("counter-evidence" in q for q in queries)


def test_counter_evidence_not_guaranteed_off(monkeypatch):
    monkeypatch.delenv("PG_TWO_SIDED_DEBATE", raising=False)
    monkeypatch.setenv("PG_EXPERT_FACET_ANGLES", "2")
    queries = efp.facet_seed_queries("benefits and risks of AI", _stub_llm)
    assert not any("counter-evidence" in q for q in queries)  # only mechanism + stakeholder
