"""I-deepfix-001 beat-both w1-F funnel fixes — behavioral tests for F1 / F2 / F4 / F5.

These are OFFLINE, fixture-driven, $0 (no model / GPU / network). Each test proves the EFFECT of a
fix in the real composed/assigned output (RED with the fix OFF, GREEN with it ON), NOT a flag-check
or a tautology. The kill-switch-OFF assertions guard byte-identical legacy behaviour.

Fixes under test (spec: .codex/I-deepfix-001/beatboth_comprehensive_plan.md §2, WORKSTREAM F):

  F1 — ``verified_compose.route_orphan_baskets_to_section_plans``: route EVERY consolidated basket to
       a section so no verified basket is stranded (drb_72: ~600 baskets never reached a composer).
       EFFECT proof: after routing, EVERY basket is returned by ``_section_baskets_for_compose`` for
       some section — zero stranded — where before routing the orphans were stranded.

  F2 — ``multi_section_generator._ev_budget_tracks_payload``: the per-section row-cap CEILING
       (PG_MAX_EV_PER_SECTION=30) is REMOVED so a section keeps its full matched payload. EFFECT
       proof: a section matching 40 evidence rows renders 40 ev_ids with the flag ON, 30 with it OFF.

  F4 — ``multi_section_generator._repair_untokened_draft`` (built + committed WS-3; re-proven here at
       the DRAFT level): an untokened sentence backed by a basket span is REPAIRED into a tokened,
       strict_verify-passing clause instead of being dropped no_provenance_token.

  F5 — ``retrieval.section_blueprint.SectionSpec.effective_target_words``: the ``min(target_words,..)``
       CEILING is removed so the per-section WORD budget tracks the full routed basket payload. EFFECT
       proof: a 40-basket facet's word budget is 4800 with the flag ON vs the 800 target ceiling OFF;
       a thin section stays short either way (no filler).

FAITHFULNESS (§-1.3): every fix here is a throttle-REMOVAL or CONSOLIDATE placement — it drops no
source, caps nothing, targets no number, and touches no faithfulness gate. The repaired/routed claims
still re-pass the UNCHANGED strict_verify per clause (F4 asserts this explicitly).
"""

from __future__ import annotations

import re

from src.polaris_graph.generator import multi_section_generator as msg
from src.polaris_graph.generator import verified_compose as vc
from src.polaris_graph.generator.multi_section_generator import SectionPlan
from src.polaris_graph.generator.provenance_generator import (
    strict_verify,
    verify_sentence_provenance,
)
from src.polaris_graph.retrieval.section_blueprint import SectionSpec

_EV_TOKEN_RE = re.compile(r"\[#ev:[^\]]*\]")


# ─────────────────────────────────────────────────────────────────────────────
# Duck-typed offline shims (production reads via getattr — faithful).
# ─────────────────────────────────────────────────────────────────────────────
class _Member:
    def __init__(self, evidence_id, direct_quote, *, span_verdict="SUPPORTS",
                 credibility_weight=0.5, origin_cluster_id=None):
        self.evidence_id = evidence_id
        self.direct_quote = direct_quote
        self.span_verdict = span_verdict
        self.credibility_weight = credibility_weight
        self.origin_cluster_id = origin_cluster_id or evidence_id


class _Basket:
    def __init__(self, claim_text, members, *, subject="", predicate=""):
        self.claim_text = claim_text
        self.subject = subject
        self.predicate = predicate
        self.supporting_members = members


class _Cred:
    def __init__(self, baskets):
        self.baskets = baskets


def _outline_item(title, *, evidence_target=0, archetype=""):
    class _Item:
        pass
    it = _Item()
    it.title = title
    it.evidence_target = evidence_target
    it.archetype = archetype
    return it


# ═════════════════════════════════════════════════════════════════════════════
# F1 — route EVERY consolidated basket to a section (zero stranded)
# ═════════════════════════════════════════════════════════════════════════════
def _reachable_baskets(plans, cred):
    """The set of basket claim_texts reachable via _section_baskets_for_compose across ALL plans."""
    reached = set()
    for p in plans:
        for b in vc._section_baskets_for_compose(p, cred):
            reached.add(b.claim_text)
    return reached


def _f1_fixture():
    # Plan 0 already owns evA (basket A is NOT an orphan).
    plans = [
        SectionPlan(title="Labor market employment effects", focus="employment", ev_ids=["evA"], archetype=""),
        SectionPlan(title="Wage inequality and income distribution", focus="wages", ev_ids=["evX"], archetype=""),
        SectionPlan(title="Productivity growth mechanisms", focus="productivity", ev_ids=["evY"], archetype=""),
    ]
    basket_a = _Basket("employment effects rose", [_Member("evA", "employment rose sharply")],
                       subject="employment", predicate="rose")
    # Orphan B: no member in any plan's ev_ids; claim overlaps plan[1] (wage inequality).
    basket_b = _Basket("wage inequality widened across the income distribution",
                       [_Member("orphanB", "wage inequality widened across income groups")],
                       subject="wage inequality", predicate="widened")
    # Orphan C: no member in any plan; claim overlaps NO plan title -> residual section.
    basket_c = _Basket("coral reef bleaching accelerated in tropical oceans",
                       [_Member("orphanC", "coral reef bleaching accelerated near the equator")],
                       subject="coral reef bleaching", predicate="accelerated")
    cred = _Cred([basket_a, basket_b, basket_c])
    return plans, cred


def test_f1_orphan_baskets_stranded_when_off(monkeypatch):
    monkeypatch.setenv("PG_ROUTE_ALL_BASKETS", "0")
    plans, cred = _f1_fixture()
    out = vc.route_orphan_baskets_to_section_plans(plans, cred, section_plan_cls=SectionPlan)
    # OFF => plans unchanged; only basket A (already owned) is reachable; B & C stranded (the leak).
    assert out is plans, "flag OFF must return the plan list unchanged (byte-identical)"
    reached = _reachable_baskets(out, cred)
    assert reached == {"employment effects rose"}, (
        "with routing OFF, the two orphan baskets are STRANDED (the drb_72 funnel leak)"
    )


def test_f1_routes_every_basket_to_a_section_zero_stranded(monkeypatch):
    monkeypatch.setenv("PG_ROUTE_ALL_BASKETS", "1")
    plans, cred = _f1_fixture()
    out = vc.route_orphan_baskets_to_section_plans(plans, cred, section_plan_cls=SectionPlan)

    reached = _reachable_baskets(out, cred)
    all_claims = {b.claim_text for b in cred.baskets}
    assert reached == all_claims, (
        f"EVERY consolidated basket must reach a section (zero stranded); "
        f"missing={all_claims - reached}"
    )

    # Orphan B routed to its best-matching TOPICAL section (wage inequality = plan index 1), by
    # appending its member ev_id — NOT to the residual section.
    assert "orphanB" in plans[1].ev_ids, "orphan B must route to the topically-matching section"

    # Orphan C matched no section title -> a single keep-all residual section was appended.
    residual = [p for p in out if p.title == "Additional Corroborated Findings"]
    assert len(residual) == 1, "a basket matching no section must get a residual coverage section"
    assert "orphanC" in residual[0].ev_ids


def test_f1_never_reassigns_an_already_homed_basket(monkeypatch):
    """A basket already reachable by a section must not be moved or duplicated (consolidate, not churn)."""
    monkeypatch.setenv("PG_ROUTE_ALL_BASKETS", "1")
    plans, cred = _f1_fixture()
    before = list(plans[0].ev_ids)
    vc.route_orphan_baskets_to_section_plans(plans, cred, section_plan_cls=SectionPlan)
    assert plans[0].ev_ids == before, "an already-homed basket's section must be untouched"


# ═════════════════════════════════════════════════════════════════════════════
# F2 — per-section evidence budget tracks the matched payload (row-cap removal)
# ═════════════════════════════════════════════════════════════════════════════
def _f2_assign(n_rows):
    outline = [_outline_item("All findings")]
    evidence = [{"evidence_id": f"e{i}", "statement": f"finding {i}", "direct_quote": f"q{i}"}
                for i in range(n_rows)]
    return outline, evidence


def test_f2_row_cap_ceiling_applies_when_off(monkeypatch):
    # Legacy row-cap path (escape hatch) so the PG_MAX_EV_PER_SECTION ceiling is the active lever.
    monkeypatch.setenv("PG_GEN_ROW_CAPS", "1")
    monkeypatch.setenv("PG_SWEEP_CREDIBILITY_REDESIGN", "0")
    monkeypatch.setenv("PG_EV_BUDGET_TRACKS_PAYLOAD", "0")
    monkeypatch.delenv("PG_MAX_EV_PER_SECTION", raising=False)
    outline, evidence = _f2_assign(40)
    plans = msg._assign_evidence_to_planned_outline(outline, evidence, sub_queries=None)
    assert len(plans[0].ev_ids) == 30, (
        "with F2 OFF the section is capped at PG_MAX_EV_PER_SECTION=30 regardless of 40 matched rows"
    )


def test_f2_budget_tracks_full_payload_when_on(monkeypatch):
    monkeypatch.setenv("PG_GEN_ROW_CAPS", "1")
    monkeypatch.setenv("PG_SWEEP_CREDIBILITY_REDESIGN", "0")
    monkeypatch.setenv("PG_EV_BUDGET_TRACKS_PAYLOAD", "1")
    monkeypatch.delenv("PG_MAX_EV_PER_SECTION", raising=False)
    outline, evidence = _f2_assign(40)
    plans = msg._assign_evidence_to_planned_outline(outline, evidence, sub_queries=None)
    assert len(plans[0].ev_ids) == 40, (
        "with F2 ON the per-section budget tracks the FULL 40-row matched payload (cap removed)"
    )


# ═════════════════════════════════════════════════════════════════════════════
# F4 — draft-level no-provenance-token repair (WS-3, re-proven end-to-end)
# ═════════════════════════════════════════════════════════════════════════════
_SUPPORTED_QUOTE = (
    "Insulin resistance markedly increased fasting glucose in the treatment cohort "
    "during the study period."
)


def test_f4_draft_repairs_untokened_sentence_instead_of_dropping(monkeypatch):
    monkeypatch.setenv("PG_NO_TOKEN_SENTENCE_REPAIR", "1")
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "off")
    member = _Member("evA", _SUPPORTED_QUOTE)
    basket = _Basket("Insulin resistance raises fasting glucose", [member],
                     subject="insulin resistance", predicate="raises fasting glucose")
    pool = {"evA": {"direct_quote": _SUPPORTED_QUOTE}}

    # A draft whose only sentence is UNTOKENED (the leak precondition) — strict_verify would drop it.
    draft = "Insulin resistance raised fasting glucose across the study cohort overall."
    assert not _EV_TOKEN_RE.search(draft)

    out = msg._repair_untokened_draft(
        draft, [basket], pool,
        writer_fn=lambda _b, _p: "",  # empty writer forces the deterministic verbatim K-span
        verify_fn=verify_sentence_provenance,
    )
    assert _EV_TOKEN_RE.search(out), "the untokened draft sentence must be REPAIRED (carry [#ev])"
    # And the repaired draft SURVIVES the UNCHANGED strict_verify (it would have been dropped before).
    report = strict_verify(out, pool)
    assert report.kept_sentences, "repaired draft must survive strict_verify (was dropped before)"


def test_f4_killswitch_off_leaves_draft_untokened(monkeypatch):
    monkeypatch.setenv("PG_NO_TOKEN_SENTENCE_REPAIR", "0")
    member = _Member("evA", _SUPPORTED_QUOTE)
    basket = _Basket("Insulin resistance raises fasting glucose", [member])
    pool = {"evA": {"direct_quote": _SUPPORTED_QUOTE}}
    draft = "Insulin resistance raised fasting glucose across the study cohort overall."
    out = msg._repair_untokened_draft(
        draft, [basket], pool, writer_fn=lambda _b, _p: "", verify_fn=verify_sentence_provenance,
    )
    assert out == draft, "flag OFF => byte-identical (draft returned unchanged, then dropped by verify)"


# ═════════════════════════════════════════════════════════════════════════════
# F5 — per-section word budget tracks the routed basket payload (ceiling removal)
# ═════════════════════════════════════════════════════════════════════════════
def test_f5_word_ceiling_clamps_rich_facet_when_off(monkeypatch):
    monkeypatch.setenv("PG_WORD_BUDGET_TRACKS_PAYLOAD", "0")
    spec = SectionSpec(section_id="s1", title="rich", target_words=800, evidence_count=40)
    # OFF => min(800, 40*120=4800) => 800 (the ceiling THROTTLES the rich facet).
    assert spec.effective_target_words == 800


def test_f5_word_budget_tracks_full_payload_when_on(monkeypatch):
    monkeypatch.setenv("PG_WORD_BUDGET_TRACKS_PAYLOAD", "1")
    spec = SectionSpec(section_id="s1", title="rich", target_words=800, evidence_count=40)
    # ON => the ceiling is dropped => the budget tracks the 40-basket payload (40 * 120).
    assert spec.effective_target_words == 4800


def test_f5_thin_section_stays_short_either_way(monkeypatch):
    # A section with little evidence must NOT balloon — length emerges from payload, never filler.
    for flag in ("0", "1"):
        monkeypatch.setenv("PG_WORD_BUDGET_TRACKS_PAYLOAD", flag)
        thin = SectionSpec(section_id="s2", title="thin", target_words=800, evidence_count=1)
        assert thin.effective_target_words == 150, f"thin section must stay short (flag={flag})"
        empty = SectionSpec(section_id="s3", title="empty", target_words=800, evidence_count=0)
        assert empty.effective_target_words == 0
