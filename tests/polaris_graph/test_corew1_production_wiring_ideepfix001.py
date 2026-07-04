"""I-deepfix-001 (#1344) core-w1 — PRODUCTION-WIRING guards for O1 / F1 / F2 / F3 / F4 / F5 / W1.

Why this file exists (Codex diff-gate iter-1 P1#4):
    The behavioral tests in ``test_o1_facet_outline_ideepfix001.py`` /
    ``test_beatboth_w1f_funnel_fixes.py`` / ``test_f3w1_relevance_weight_and_institutional_authority.py``
    prove each fix's HELPER produces the right RED->GREEN effect, but they call the helper
    DIRECTLY. So they would still pass if the production CALL SITE that invokes the helper were
    reverted (e.g. the F1 route call removed from ``generate_multi_section_report`` or the F4 repair
    call removed from ``_run_section``). Codex flagged exactly that: "would still pass if key
    production wiring were reverted".

    These tests close that gap. Each one binds to the SPECIFIC production function that owns the
    call site and asserts the fix is wired INTO it. If the call site is deleted or unwired, the
    guard FAILS LOUD. They are the honest offline maximum: the async, model-driven orchestrators
    (``generate_multi_section_report`` / ``_run_section`` / ``_call_outline``) cannot be driven to
    real output without a paid GPU/LLM run (operator rule: offline tests prove seam + wiring only;
    the live end-to-end effect is confirmed by the fresh paid run). What is provable offline —
    that the fix's helper is invoked by the real production function on the real data variable —
    is proven here; what is not (the rendered numbers) is deferred to the run, per the plan.

    Paired with the behavioral helper tests, the two together satisfy the gate bar: HELPER proves
    the effect, WIRING proves the effect reaches real composed/assigned/weighted output.

FAITHFULNESS (§-1.3): pure read-only source inspection. Touches no faithfulness gate.
OFFLINE, $0: no network, no model, no GPU.
"""
from __future__ import annotations

import inspect
import re

from src.polaris_graph.generator import multi_section_generator as m
from src.polaris_graph.synthesis import credibility_pass as cp
from src.polaris_graph.synthesis import synthesizer_v2 as sv2


def _collapse(fn) -> str:
    """Source of ``fn`` with every run of whitespace collapsed to a single space (formatting-robust)."""
    return re.sub(r"\s+", " ", inspect.getsource(fn))


# ═════════════════════════════════════════════════════════════════════════════
# O1 — the production outline parser is called with facet_titles DERIVED from the
#      env+domain gate, not a hardcoded False. Revert of the derivation => this fails.
# ═════════════════════════════════════════════════════════════════════════════
def test_o1_call_outline_wires_facet_mode_from_env_and_domain():
    src = _collapse(m._call_outline)
    assert "_facet_outline_active_for_domain(domain)" in src, (
        "O1 UNWIRED: _call_outline must derive facet mode from the env+domain gate "
        "(_facet_outline_active_for_domain), not a constant"
    )
    assert "facet_titles=_facet_mode" in src, (
        "O1 UNWIRED: the real _parse_outline call must receive the derived _facet_mode "
        "(reverting to facet_titles=False re-locks the fixed 6-title container)"
    )


def test_o1_facet_gate_defaults_off_byte_identical():
    """The wiring must be behind the default-OFF PG_FACET_OUTLINE flag (legacy path byte-identical)."""
    import os

    prev = os.environ.pop("PG_FACET_OUTLINE", None)
    try:
        assert m._facet_outline_enabled() is False, "PG_FACET_OUTLINE must default OFF"
        assert m._facet_outline_active_for_domain("economics") is False, (
            "with the flag OFF the non-clinical path stays on the legacy container"
        )
    finally:
        if prev is not None:
            os.environ["PG_FACET_OUTLINE"] = prev


# ═════════════════════════════════════════════════════════════════════════════
# F1 — generate_multi_section_report ROUTES orphan baskets before per-section gen.
#      Revert of the call => orphan baskets are stranded again => this fails.
# ═════════════════════════════════════════════════════════════════════════════
def test_f1_route_orphan_baskets_is_wired_into_the_report_builder():
    src = _collapse(m.generate_multi_section_report)
    assert "plans = route_orphan_baskets_to_section_plans(" in src, (
        "F1 UNWIRED: generate_multi_section_report must reassign `plans` from "
        "route_orphan_baskets_to_section_plans (else every orphan basket is stranded — the "
        "drb_72 ~600-basket funnel leak returns)"
    )
    assert "credibility_analysis" in src, (
        "F1 UNWIRED: the routing must consume the consolidated baskets (credibility_analysis)"
    )


# ═════════════════════════════════════════════════════════════════════════════
# F2 — the per-section evidence budget cap-removal lives in the REAL assigner that
#      the report builder calls. (The behavioral test already drives this function;
#      this guard binds the cap-removal flag to that exact production function.)
# ═════════════════════════════════════════════════════════════════════════════
def test_f2_row_cap_removal_is_in_the_real_assigner():
    src = _collapse(m._assign_evidence_to_planned_outline)
    assert "_ev_budget_tracks_payload()" in src, (
        "F2 UNWIRED: the row-cap removal (_ev_budget_tracks_payload, PG_EV_BUDGET_TRACKS_PAYLOAD) must "
        "be honored inside _assign_evidence_to_planned_outline — the function the outline builder "
        "actually calls to assign ev_ids to sections; reverting the branch restores the "
        "min(cap, max_ev_per_section) ceiling that drops matched rows"
    )
    assert "min(cap, max_ev_per_section)" in src, (
        "F2 guard sanity: the legacy row-cap ceiling must still exist for the default-OFF path"
    )


# ═════════════════════════════════════════════════════════════════════════════
# F3 — _run_section computes the WEIGHTED compose ev_ids from the real section and
#      feeds them to the draft builder. Revert => the banned lexical floor / raw
#      ev_ids feed compose again => this fails.
# ═════════════════════════════════════════════════════════════════════════════
def test_f3_relevance_weight_is_wired_into_the_section_composer():
    src = _collapse(m._run_section)
    assert "_compose_ev_ids = _compose_relevance_floored_ev_ids(section.ev_ids, evidence_pool)" in src, (
        "F3 UNWIRED: _run_section must derive _compose_ev_ids via the WEIGHT helper on the real "
        "section.ev_ids (reverting to section.ev_ids directly restores the banned lexical floor-drop)"
    )
    assert "_build_verified_span_draft(_compose_ev_ids" in src.replace(" ", ""), (
        "F3 UNWIRED: the weighted _compose_ev_ids must feed the verified-span draft builder, "
        "not be computed then ignored"
    )


# ═════════════════════════════════════════════════════════════════════════════
# F4 — _run_section REPAIRS the untokened draft (rebinds it to `raw`) instead of
#      dropping it. Revert => untokened sentences are dropped no_provenance_token.
# ═════════════════════════════════════════════════════════════════════════════
def test_f4_untokened_repair_is_wired_into_the_section_composer():
    src = _collapse(m._run_section)
    assert "raw = _repair_untokened_draft(" in src, (
        "F4 UNWIRED: _run_section must rebind `raw` through _repair_untokened_draft so an "
        "untokened-but-supported sentence is repaired (carries a real [#ev] and re-passes the "
        "UNCHANGED strict_verify) instead of being dropped"
    )


# ═════════════════════════════════════════════════════════════════════════════
# F5 — the payload-tracking word budget (SectionSpec.effective_target_words) feeds
#      the real section writer. Revert => the writer uses the raw ceiling again.
# ═════════════════════════════════════════════════════════════════════════════
def test_f5_effective_word_budget_feeds_the_real_section_writer():
    src = _collapse(sv2._write_section_inner)
    assert "spec.effective_target_words" in src, (
        "F5 UNWIRED: the section writer must take its word budget from "
        "SectionSpec.effective_target_words (the payload-tracking budget), not a fixed target"
    )


# ═════════════════════════════════════════════════════════════════════════════
# W1 — the institutional-authority + raised-UNKNOWN join runs inside the real
#      credibility pass chain. Revert => institutions stay at the 0.20 soft-filter band.
# ═════════════════════════════════════════════════════════════════════════════
def test_w1_tier_authority_join_runs_in_the_real_credibility_pass():
    src = _collapse(cp._run_chain)
    assert "rows = _join_tier_authority_prior(rows)" in src, (
        "W1 UNWIRED: the credibility pass chain must run _join_tier_authority_prior on its rows so "
        "the institutional weight + raised-UNKNOWN prior reach the weighted output (else credible "
        "non-journal institutions stay soft-filtered at the old 0.20 UNKNOWN band)"
    )
