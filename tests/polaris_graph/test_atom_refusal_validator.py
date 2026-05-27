"""Tests for atom_refusal_validator — refusal/gap rendering.

Per Codex APPROVE_DESIGN 2026-05-26:
    - Approach C hybrid (prompt + post-hoc)
    - STRICT layer: missing/invalid atom → REPLACE sentence
    - SOFT layer: value/endpoint mismatch → log only
    - Sentence-level granularity
    - gaps.json sidecar AND inline refusal markers
    - Multi-atom: ALL cited atoms must exist

Coverage:
    1. Quantitative-claim detector (Triggers A + B + qualitative)
    2. Narrative-allowed prose
    3. Admin-number exclusions
    4. Atom citation parsing (atom_NNN extraction)
    5. STRICT layer: missing citation → refused
    6. STRICT layer: invalid atom_id → refused
    7. STRICT layer: ev_XXX for factual claim → refused
    8. STRICT layer: multi-atom ALL-required (one missing → refused)
    9. SOFT layer: value mismatch → logged_only
    10. Section validation end-to-end
    11. gaps.json schema integrity
"""

from __future__ import annotations

import json
from pathlib import Path

from src.polaris_graph.generator.claim_atom_extractor import ClaimAtom
from src.polaris_graph.generator.atom_refusal_validator import (
    GapRecord,
    RefusalAction,
    RefusalReason,
    build_gaps_document,
    extract_atom_citations,
    extract_ev_citations,
    has_ev_citation_for_factual_claim,
    requires_atom_citation,
    split_sentences,
    validate_section,
    validate_sentence,
    write_gaps_sidecar,
)


# ----------------------------------------------------------------------------
# Test fixtures
# ----------------------------------------------------------------------------

def _make_atom(
    aid: str,
    value: str,
    endpoint: str,
    entity: str = "tirzepatide",
    unit: str = "percentage points",
    comparator: str = "",
    primary_section: str = "Efficacy",
) -> ClaimAtom:
    return ClaimAtom(
        atom_id=aid,
        evidence_id="ev_001",
        span_start=0,
        span_end=100,
        literal_text=f"placeholder for {aid}",
        entity=entity,
        endpoint=endpoint,
        comparator=comparator,
        timepoint="40 weeks",
        value=value,
        unit=unit,
        primary_section=primary_section,
        section_tags=(primary_section,),
        tier="T1",
        value_signed=value.startswith("-"),
        confidence="high",
        provenance_class="open_access",
        source_paper_title="placeholder",
    )


_CATALOG = {
    "atom_001": _make_atom("atom_001", "-2.01", "HbA1c"),
    "atom_002": _make_atom("atom_002", "-2.24", "HbA1c"),
    "atom_003": _make_atom("atom_003", "-2.30", "HbA1c"),
    "atom_004": _make_atom("atom_004", "-1.86", "HbA1c", entity="semaglutide"),
    "atom_005": _make_atom("atom_005", "43", "adverse events",
                            unit="%", primary_section="Safety"),
}


# ============================================================================
# Quantitative-claim detector
# ============================================================================


def test_trigger_a_number_plus_endpoint_requires_atom():
    """Codex Trigger A: number + endpoint vocab term."""
    requires, trigger = requires_atom_citation(
        "Tirzepatide reduced HbA1c by -2.30 percentage points at 40 weeks."
    )
    assert requires
    assert trigger == "trigger_A_number_plus_endpoint"


def test_trigger_b_number_alone_requires_atom():
    """Codex Trigger B: number alone (no endpoint vocab term) but not
    admin/design. Note: 'risk ratio' IS in endpoint vocab so it would
    fire Trigger A; here we use a bare number that's still an
    outcome-shaped claim."""
    requires, trigger = requires_atom_citation(
        "The treatment effect was 0.32."
    )
    assert requires
    assert trigger == "trigger_B_number_alone"


def test_admin_phase_number_does_not_require_atom():
    """Codex Trigger B exclusion: phase number is admin, not outcome."""
    requires, _ = requires_atom_citation(
        "SURPASS-2 was a phase 3 trial."
    )
    assert not requires


def test_admin_week_duration_alone_does_not_require_atom():
    """Codex Trigger B exclusion: week duration alone is admin."""
    requires, _ = requires_atom_citation(
        "The study period was 40 weeks."
    )
    assert not requires


def test_dose_alone_does_not_require_atom():
    """Codex Trigger B exclusion: '15 mg' as dose label alone."""
    requires, _ = requires_atom_citation(
        "Patients received tirzepatide 15 mg once weekly."
    )
    assert not requires


def test_qualitative_comparative_without_number_requires_atom():
    """Codex additional trigger: 'greater than [endpoint]' without
    a number still requires an atom (it's making a comparative claim)."""
    requires, trigger = requires_atom_citation(
        "Tirzepatide produced greater HbA1c reduction than semaglutide."
    )
    assert requires
    assert trigger == "trigger_qualitative_comparative"


def test_mechanism_sentence_does_not_require_atom():
    """Codex narrative-allowed: mechanism of action."""
    requires, _ = requires_atom_citation(
        "Tirzepatide acts via dual GIP/GLP-1 receptor agonism."
    )
    assert not requires


def test_trial_design_sentence_does_not_require_atom():
    """Codex narrative-allowed: trial design."""
    requires, _ = requires_atom_citation(
        "SURPASS-2 was an open-label, randomized, phase 3 trial."
    )
    assert not requires


def test_eligibility_sentence_requires_atom_safe_default():
    """Iter-4 decision (Codex iter-3 continuing-P1): eligibility override
    REMOVED. Quantitative claims with eligibility framing now require
    atom citation as the SAFE default. V4 Pro will refuse with the
    refusal template if no supporting atom — preferable to masking a
    real outcome claim that happens to mention baseline characteristics.

    Trade-off per CLAUDE.md §-1.1: false negative (over-refuse benign
    eligibility) is recoverable; false positive (mask real outcome) is
    lethal in clinical context."""
    requires, _ = requires_atom_citation(
        "Eligible patients had inclusion criteria of HbA1c between 7.0 and 10.0."
    )
    assert requires, (
        "After iter-4 eligibility-override removal, this sentence requires "
        "atom citation. V4 Pro emits refusal block; slightly awkward but safe."
    )


def test_hedge_sentence_does_not_require_atom():
    """Codex narrative-allowed: hedges/limitations without quantitative claim.
    '40 weeks' is admin-number; 'remain limited' is hedge."""
    requires, _ = requires_atom_citation(
        "Long-term safety data beyond 40 weeks remain limited."
    )
    assert not requires, (
        "Hedge sentence with admin-number should be allowed without atom."
    )


# ============================================================================
# I-gen-005 Step 3j (Codex iter-4 APPROVE_DESIGN): trial-design narrative
# exemption + result-attribution independent trigger.
# ============================================================================


def test_step3j_trial_design_methodology_sentence_allowed():
    """The s009 real-smoke repro: trial-design methodology framing with
    endpoint vocab + numbers but NO outcome verb or result attribution.
    Must be allowed (Codex APPROVE_DESIGN iter-4)."""
    requires, _ = requires_atom_citation(
        "In a phase 3 trial, 1879 adults with type 2 diabetes "
        "(mean baseline HbA1c 8.28%, mean weight 93.7 kg) were randomly "
        "assigned to tirzepatide 5 mg, 10 mg, or 15 mg or semaglutide 1 mg, "
        "with the primary endpoint of change in HbA1c at 40 weeks."
    )
    assert not requires, (
        "Pure trial-design methodology sentence (Codex iter-4 target repro) "
        "must be allowed without atom citation."
    )


def test_step3j_endpoint_attribution_with_methodology_still_refused():
    """Codex iter-2 P1: 'primary endpoint of change in HbA1c was -2.30'
    has methodology marker BUT also result-attribution (copular endpoint
    value). Result-attribution is independent trigger — must REFUSE."""
    requires, reason = requires_atom_citation(
        "The primary endpoint of change in HbA1c was -2.30 percentage points."
    )
    assert requires, (
        "Endpoint-of result attribution with methodology marker must still "
        "refuse via independent result-attribution trigger."
    )
    assert reason == "trigger_endpoint_result_attribution"


def test_step3j_primary_outcome_attribution_refused():
    """Codex iter-3 P1: branch (a) symmetry — 'primary outcome of'
    parallel to 'primary endpoint of'. Must REFUSE."""
    requires, reason = requires_atom_citation(
        "The primary outcome of change from baseline was -2.30."
    )
    assert requires, (
        "'primary outcome of X was NUMBER' must refuse via "
        "result-attribution independent trigger."
    )
    assert reason == "trigger_endpoint_result_attribution"


def test_step3j_value_at_timepoint_with_phase3_marker_refused():
    """Codex iter-2 P1: 'In a phase 3 trial, mean HbA1c at 40 weeks was 6.2%'
    has trial-design marker but endpoint-at-timepoint with copular value.
    Must REFUSE (preserves safety floor)."""
    requires, reason = requires_atom_citation(
        "In a phase 3 trial, mean HbA1c at 40 weeks was 6.2%."
    )
    assert requires
    assert reason == "trigger_endpoint_result_attribution"


def test_step3j_value_at_week_n_form_refused():
    """Codex iter-2 P1 #2: 'week 40' form (alongside '40 weeks'). Must REFUSE."""
    requires, reason = requires_atom_citation(
        "Mean HbA1c at week 40 was 6.2%."
    )
    assert requires
    assert reason == "trigger_endpoint_result_attribution"


def test_step3j_reverse_order_change_was_n_at_timepoint_refused():
    """Codex iter-2 P1 #1: reverse-order attribution. Must REFUSE."""
    requires, reason = requires_atom_citation(
        "In a phase 3 trial, mean change from baseline was -2.30 at 40 weeks."
    )
    assert requires
    assert reason == "trigger_endpoint_result_attribution"


def test_step3j_passive_was_reported_in_refused():
    """Codex iter-2 P1 #4: passive 'X was reported in N%'. Must REFUSE."""
    requires, reason = requires_atom_citation(
        "In a phase 3 open-label trial, nausea was reported in 22%."
    )
    assert requires
    assert reason == "trigger_endpoint_result_attribution"


def test_step3j_passive_occurred_in_refused():
    """Codex iter-2 P1 #4: 'X occurred in N%'. Must REFUSE."""
    requires, reason = requires_atom_citation(
        "Adverse events occurred in 30% of randomized patients."
    )
    assert requires
    assert reason == "trigger_endpoint_result_attribution"


def test_step3j_n_percent_achieved_endpoint_refused():
    """Codex iter-2 P1 #4: 'NUMBER% achieved X'. Must REFUSE."""
    requires, reason = requires_atom_citation(
        "Across the open-label trial, 86% achieved HbA1c reduction."
    )
    assert requires
    assert reason == "trigger_endpoint_result_attribution"


def test_step3j_baseline_parenthetical_preserved_as_narrative():
    """Codex iter-2/iter-4: design-context baseline characteristics in
    parenthetical (no 'was/=' attribution) must stay allowed."""
    requires, _ = requires_atom_citation(
        "In a phase 3 trial, 1879 adults (mean baseline HbA1c 8.28%, mean "
        "weight 93.7 kg) were randomly assigned to tirzepatide or semaglutide."
    )
    assert not requires, (
        "Baseline parenthetical without 'was/=' value attribution must stay "
        "narrative — distinguishes design-context numbers from outcome values."
    )


def test_step3j_step3b_iter3_historical_repro_still_refused():
    """The Step 3b iter-3 failure mode case — outcome verb with number
    must still refuse even though sentence has 'baseline' framing.
    Verifies trial-design exemption did NOT reintroduce eligibility-masks-
    outcome failure mode."""
    requires, reason = requires_atom_citation(
        "Patients with baseline HbA1c of 8.6% had HbA1c reductions of 2.3 "
        "percentage points."
    )
    assert requires, (
        "Outcome-verb-with-number must still refuse (Step 3b iter-3 safety "
        "floor preserved through Step 3j changes)."
    )


def test_step3j_trial_design_with_qual_comparative_still_refused():
    """Trial-design marker plus qualitative comparative — exemption must
    NOT fire (qual comparative guard preserved)."""
    requires, _ = requires_atom_citation(
        "The phase 3 SURPASS-2 trial showed tirzepatide reduced HbA1c "
        "more than semaglutide."
    )
    assert requires, (
        "Trial-design marker plus qual-comparative must still refuse via "
        "qual-comparative trigger (exemption guard preserved)."
    )


def test_step3j_independent_result_attribution_no_trial_marker_refused():
    """Result-attribution trigger fires INDEPENDENT of trial-design marker.
    Sentence with no methodology marker but with endpoint-at-timepoint
    copular value must still refuse (independent trigger guarantees
    safety even without methodology context)."""
    requires, reason = requires_atom_citation(
        "Baseline HbA1c was 8.5% and HbA1c at 40 weeks was 6.2%."
    )
    assert requires
    assert reason == "trigger_endpoint_result_attribution"


# ============================================================================
# I-gen-005 Step 3j diff iter-1 Codex P1 fixes (3 NOVEL failure modes)
# ============================================================================


def test_step3j_diff_iter1_active_verb_produced_with_trial_marker_refused():
    """Codex diff iter-1 P1 #1: active outcome verb 'produced' was not in
    _OUTCOME_VERB_WITH_NUMBER_RE → trial-design exemption masked the
    result. Now must REFUSE via the widened verb list."""
    requires, _ = requires_atom_citation(
        "In a phase 3 trial, tirzepatide produced -2.30 percentage-point "
        "HbA1c reductions at 40 weeks."
    )
    assert requires, (
        "'produced -2.30' is an outcome verb with number — must refuse "
        "even with trial-design marker present."
    )


def test_step3j_diff_iter1_active_verb_showed_refused():
    """Codex diff iter-1 P1 #1 expansion: 'showed' is similar active verb."""
    requires, _ = requires_atom_citation(
        "In a randomized open-label trial, tirzepatide showed -2.30 "
        "HbA1c reduction at 40 weeks."
    )
    assert requires


def test_step3j_diff_iter1_active_verb_resulted_in_refused():
    """Codex diff iter-1 P1 #1: 'resulted in NUMBER'."""
    requires, _ = requires_atom_citation(
        "Treatment in this open-label trial resulted in 22% nausea."
    )
    assert requires


def test_step3j_diff_iter1_pancreatitis_endpoint_refused():
    """Codex diff iter-1 P1 #2: _ENDPOINT_NAMES_ALT missing pancreatitis.
    Now in vocab — must REFUSE via branch (c)."""
    requires, reason = requires_atom_citation(
        "In the open-label trial, pancreatitis was 0.3%."
    )
    assert requires
    assert reason == "trigger_endpoint_result_attribution"


def test_step3j_diff_iter1_hazard_ratio_endpoint_refused():
    """Codex diff iter-1 P1 #2: hazard ratio missing from vocab."""
    requires, reason = requires_atom_citation(
        "In a phase 3 trial, hazard ratio was 0.78."
    )
    assert requires
    assert reason == "trigger_endpoint_result_attribution"


def test_step3j_diff_iter1_injection_site_endpoint_refused():
    """Codex diff iter-1 P1 #2: injection-site reactions missing."""
    requires, reason = requires_atom_citation(
        "In the open-label trial, injection-site reactions were 5.2%."
    )
    assert requires


def test_step3j_diff_iter1_timepoint_after_refused():
    """Codex diff iter-1 P1 #3: 'after 40 weeks' form."""
    requires, _ = requires_atom_citation(
        "In a phase 3 trial, mean HbA1c after 40 weeks was 6.2%."
    )
    assert requires


def test_step3j_diff_iter1_timepoint_by_week_refused():
    """Codex diff iter-1 P1 #3: 'by week 40' form."""
    requires, _ = requires_atom_citation(
        "In an open-label trial, HbA1c by week 40 was 6.2%."
    )
    assert requires


def test_step3j_diff_iter1_timepoint_at_end_of_refused():
    """Codex diff iter-1 P1 #3: 'at the end of 40 weeks' form."""
    requires, _ = requires_atom_citation(
        "In a phase 3 trial, HbA1c at the end of 40 weeks was 6.2%."
    )
    assert requires


def test_step3j_diff_iter1_n_week_hyphen_form_refused():
    """Codex diff iter-1 P1 #3: '40-week' hyphenated form."""
    requires, _ = requires_atom_citation(
        "In a phase 3 trial, mean HbA1c at the 40-week follow-up was 6.2%."
    )
    assert requires


def test_step3j_diff_iter2_noninferiority_endpoint_refused():
    """Codex diff iter-2 continuing P1 #2: 'noninferiority' missing from
    _ENDPOINT_NAMES_ALT. Now added."""
    requires, _ = requires_atom_citation(
        "In a phase 3 trial, noninferiority was 0.95."
    )
    assert requires


def test_step3j_diff_iter2_superiority_endpoint_refused():
    """Codex diff iter-2 continuing P1 #2: 'superiority' missing from
    _ENDPOINT_NAMES_ALT. Now added."""
    requires, _ = requires_atom_citation(
        "In a phase 3 trial, superiority was 0.4 percentage points."
    )
    assert requires


def test_step3j_diff_iter2_active_verb_with_article_refused():
    """Codex diff iter-2 novel P1: 'achieved a 2.30 percentage-point
    reduction' — article between verb and number was missed by
    _OUTCOME_VERB_WITH_NUMBER_RE. Now permits optional a/an/the."""
    requires, _ = requires_atom_citation(
        "In a phase 3 trial, tirzepatide achieved a 2.30 percentage-point "
        "HbA1c reduction at 40 weeks."
    )
    assert requires


def test_step3j_diff_iter2_active_verb_produced_with_article_refused():
    """Same pattern with 'produced a'."""
    requires, _ = requires_atom_citation(
        "In a phase 3 trial, tirzepatide produced a -2.30 percentage-point "
        "HbA1c reduction at 40 weeks."
    )
    assert requires


def test_step3j_diff_iter2_led_to_with_article_refused():
    """Same pattern with 'led to a'."""
    requires, _ = requires_atom_citation(
        "In a phase 3 trial, treatment led to a 22% nausea rate."
    )
    assert requires


def test_step3j_diff_iter3_verb_endpoint_of_number_refused():
    """Codex diff iter-3 novel P1: 'tirzepatide achieved HbA1c of 6.2%
    at 40 weeks' — verb + endpoint + 'of NUMBER' pattern bypassed both
    _OUTCOME_VERB_WITH_NUMBER_RE (no number directly after verb) and
    _ENDPOINT_RESULT_ATTRIBUTION_RE branches a-e. New branch (f) catches
    this."""
    requires, reason = requires_atom_citation(
        "In a phase 3 trial, tirzepatide achieved HbA1c of 6.2% at 40 weeks."
    )
    assert requires, (
        "Verb-endpoint-of-NUMBER pattern must refuse via new branch (f)."
    )
    assert reason == "trigger_endpoint_result_attribution"


def test_step3j_diff_iter3_verb_endpoint_of_number_variants():
    """Same pattern with different verb forms."""
    for sentence in [
        "In a phase 3 trial, semaglutide produced HbA1c of 7.0% at 40 weeks.",
        "In a phase 3 open-label trial, tirzepatide demonstrated nausea of 22%.",
        "In a phase 3 trial, treatment showed weight loss of 14.9% at 68 weeks.",
        "In a phase 3 trial, dulaglutide attained HbA1c of 6.8%.",
    ]:
        requires, _ = requires_atom_citation(sentence)
        assert requires, f"Verb+endpoint+of+NUMBER must refuse: {sentence!r}"


def test_step3j_diff_iter4_phrasal_verb_led_to_endpoint_of_number_refused():
    """Codex diff iter-4 P1: phrasal verbs 'led to' / 'resulted in' were
    missing from branch (f). Now added."""
    for sentence in [
        "In a phase 3 trial, treatment led to HbA1c of 6.2% at 40 weeks.",
        "In a phase 3 trial, treatment resulted in HbA1c of 6.2% at 40 weeks.",
        "In a phase 3 trial, treatment led to nausea of 22%.",
        "In a phase 3 trial, treatment resulted in weight loss of 14.9% at 68 weeks.",
        "In a phase 3 trial, treatment leading to weight loss of 14.9%.",
    ]:
        requires, _ = requires_atom_citation(sentence)
        assert requires, (
            f"Phrasal verb + endpoint + 'of NUMBER' must refuse: {sentence!r}"
        )


def test_step3j_diff_iter5_phrasal_verb_with_article_modifier_refused():
    """Codex diff iter-5 P1 (cap-hit): articles/modifiers between
    phrasal verb and endpoint masked outcome. Now permitted via
    optional (a/an/the/mean/median/baseline/change in) carve-out."""
    for sentence in [
        "In a phase 3 trial, treatment led to an HbA1c of 6.2% at 40 weeks.",
        "In a phase 3 trial, treatment resulted in mean HbA1c of 6.2% at 40 weeks.",
        "In a phase 3 trial, treatment led to a change in HbA1c of -2.30 at 40 weeks.",
        "In a phase 3 trial, treatment resulted in median weight loss of 14.9%.",
    ]:
        requires, _ = requires_atom_citation(sentence)
        assert requires, (
            f"Phrasal verb + article/modifier + endpoint + 'of NUMBER' must "
            f"refuse: {sentence!r}"
        )


def test_step3j_diff_iter1_isolated_branch_b_test():
    """Codex diff iter-1 P2: isolated branch (b) test with no endpoint
    vocab name, only generic '<prep> <timepoint> was NUMBER'. Branch (b)
    fires alone."""
    # No endpoint vocab name in the sentence — only "at TIMEPOINT was N".
    # If branch (b) is missing, branches (a)(c)(d)(e) wouldn't catch this.
    requires, reason = requires_atom_citation(
        "In a phase 3 trial, primary measure at 40 weeks was -2.30 points."
    )
    assert requires
    assert reason == "trigger_endpoint_result_attribution"


# ============================================================================
# Citation parsing
# ============================================================================


def test_extract_atom_citations_single():
    cites = extract_atom_citations(
        "Tirzepatide reduced HbA1c by -2.30 atom_003 at 40 weeks."
    )
    assert cites == ["atom_003"]


def test_extract_atom_citations_multiple():
    cites = extract_atom_citations(
        "Doses produced -2.01 atom_001, -2.24 atom_002, -2.30 atom_003."
    )
    assert cites == ["atom_001", "atom_002", "atom_003"]


def test_extract_ev_citations():
    cites = extract_ev_citations(
        "Per the protocol [ev_017], blinding was maintained."
    )
    assert "ev_017" in cites[0]


def test_has_ev_citation_for_factual_claim_detected():
    """Per Codex: [ev_XXX] for factual claim → REFUSE."""
    assert has_ev_citation_for_factual_claim(
        "HbA1c reduced by 2.30 percentage points [ev_017]."
    )


def test_has_ev_citation_for_narrative_allowed():
    """ev_XXX in narrative context (no claim) → not flagged."""
    assert not has_ev_citation_for_factual_claim(
        "Per the protocol [ev_017], blinding was maintained."
    )


# ============================================================================
# STRICT layer: refusal cases
# ============================================================================


def test_strict_missing_atom_citation_refused():
    """Factual claim with no atom → refused."""
    record = validate_sentence(
        "Tirzepatide reduced HbA1c by -2.30 percentage points at 40 weeks.",
        sentence_index=0,
        section_id="efficacy",
        section_title="Efficacy",
        catalog=_CATALOG,
    )
    assert record.action == RefusalAction.REFUSED
    assert record.reason == RefusalReason.MISSING_ATOM_CITATION
    assert "Insufficient verified atom-level evidence" in record.rendered_text


def test_strict_invalid_atom_id_refused():
    """Cited atom_NNN that doesn't exist in catalog → refused."""
    record = validate_sentence(
        "Tirzepatide reduced HbA1c by -2.30 percentage points atom_999.",
        sentence_index=0,
        section_id="efficacy",
        section_title="Efficacy",
        catalog=_CATALOG,
    )
    assert record.action == RefusalAction.REFUSED
    assert record.reason == RefusalReason.INVALID_ATOM_ID
    assert "atom_999" in record.missing_atoms


def test_strict_ev_for_factual_claim_refused():
    """[ev_XXX] cited for a factual claim with no atom → refused."""
    record = validate_sentence(
        "HbA1c reduced by 2.30 percentage points [ev_017].",
        sentence_index=0,
        section_id="efficacy",
        section_title="Efficacy",
        catalog=_CATALOG,
    )
    assert record.action == RefusalAction.REFUSED
    assert record.reason == RefusalReason.EV_CITATION_FOR_CLAIM


def test_strict_multi_atom_all_required_any_missing_refuses():
    """ALL_REQUIRED: one cited atom missing → refuse whole sentence."""
    record = validate_sentence(
        "Three doses produced atom_001, atom_002, and atom_999.",
        sentence_index=0,
        section_id="efficacy",
        section_title="Efficacy",
        catalog=_CATALOG,
    )
    assert record.action == RefusalAction.REFUSED
    assert record.reason == RefusalReason.INVALID_ATOM_ID
    assert "atom_999" in record.missing_atoms
    assert "atom_001" not in record.missing_atoms


def test_strict_all_atoms_valid_allows():
    """All cited atoms exist + value present → allowed."""
    record = validate_sentence(
        "Tirzepatide reduced HbA1c by -2.30 percentage points atom_003.",
        sentence_index=0,
        section_id="efficacy",
        section_title="Efficacy",
        catalog=_CATALOG,
    )
    assert record.action == RefusalAction.ALLOWED
    assert record.reason == RefusalReason.NO_VIOLATION


# ============================================================================
# SOFT layer: mismatch logged, sentence kept
# ============================================================================


def test_soft_layer_value_mismatch_logged_only():
    """Cited atom_001 has value -2.01. Sentence says 2.99 — value not
    in sentence. SOFT mismatch → logged, sentence KEPT."""
    record = validate_sentence(
        "Tirzepatide reduced HbA1c by 2.99 percentage points atom_001.",
        sentence_index=0,
        section_id="efficacy",
        section_title="Efficacy",
        catalog=_CATALOG,
    )
    assert record.action == RefusalAction.LOGGED_ONLY
    assert record.reason == RefusalReason.SOFT_MISMATCH
    assert record.rendered_text == record.original_sentence  # KEPT
    assert "atom_001" in (record.notes or "")


# ============================================================================
# Narrative sentences pass through
# ============================================================================


def test_narrative_mechanism_allowed_no_citation():
    record = validate_sentence(
        "Tirzepatide acts via dual GIP/GLP-1 receptor agonism.",
        sentence_index=0,
        section_id="mechanism",
        section_title="Mechanism",
        catalog=_CATALOG,
    )
    assert record.action == RefusalAction.ALLOWED


def test_narrative_trial_design_allowed_no_citation():
    record = validate_sentence(
        "SURPASS-2 was an open-label, randomized, phase 3 trial.",
        sentence_index=0,
        section_id="design",
        section_title="Trial Design",
        catalog=_CATALOG,
    )
    assert record.action == RefusalAction.ALLOWED


# ============================================================================
# Section-level end-to-end
# ============================================================================


def test_validate_section_mixed_sentences():
    """Section with mix of allowed + refused + soft."""
    section_text = (
        "Tirzepatide acts via dual GIP/GLP-1 receptor agonism. "
        "Tirzepatide reduced HbA1c by -2.30 percentage points atom_003 at 40 weeks. "
        "HbA1c reduced by 2.99 percentage points atom_001. "
        "Tirzepatide reduced HbA1c by -2.30 percentage points."
    )
    result = validate_section(
        section_text,
        section_id="efficacy",
        section_title="Efficacy",
        catalog=_CATALOG,
    )
    assert len(result.gap_records) == 4
    assert result.gap_records[0].action == RefusalAction.ALLOWED  # mechanism
    assert result.gap_records[1].action == RefusalAction.ALLOWED  # valid atom
    assert result.gap_records[2].action == RefusalAction.LOGGED_ONLY  # soft mismatch
    assert result.gap_records[3].action == RefusalAction.REFUSED  # no atom


def test_validate_section_counts():
    section_text = (
        "Tirzepatide reduced HbA1c by -2.30 percentage points. "  # refused
        "HbA1c improved by 2.30 atom_003."  # allowed? Let's check
    )
    result = validate_section(
        section_text,
        section_id="efficacy",
        section_title="Efficacy",
        catalog=_CATALOG,
    )
    assert result.refusal_count >= 1


def test_validate_section_rendered_text_replaces_refused():
    """Refused sentences ARE replaced in rendered_text; others kept."""
    section_text = (
        "Tirzepatide acts via dual GIP/GLP-1 receptor agonism. "
        "Tirzepatide reduced HbA1c by -2.30 percentage points."
    )
    result = validate_section(
        section_text,
        section_id="efficacy",
        section_title="Efficacy",
        catalog=_CATALOG,
    )
    # First sentence kept verbatim
    assert "GIP/GLP-1 receptor agonism" in result.rendered_text
    # Second sentence replaced with refusal
    assert "Insufficient verified atom-level evidence" in result.rendered_text


# ============================================================================
# gaps.json schema
# ============================================================================


def test_build_gaps_document_schema():
    section_text = "Tirzepatide reduced HbA1c by -2.30 percentage points."
    result = validate_section(
        section_text, "efficacy", "Efficacy", _CATALOG,
    )
    doc = build_gaps_document("test-doc-001", [result])
    assert doc["document_id"] == "test-doc-001"
    assert "generated_at" in doc
    assert len(doc["sections"]) == 1
    sec = doc["sections"][0]
    assert sec["section_id"] == "efficacy"
    assert sec["section_title"] == "Efficacy"
    assert "claims" in sec
    assert "summary" in sec
    assert sec["summary"]["total_sentences"] >= 1
    assert "totals" in doc


def test_gaps_document_claim_record_schema():
    section_text = "Tirzepatide reduced HbA1c by -2.30 percentage points."
    result = validate_section(
        section_text, "efficacy", "Efficacy", _CATALOG,
    )
    doc = build_gaps_document("test-doc", [result])
    claim = doc["sections"][0]["claims"][0]
    assert "claim_id" in claim
    assert "sentence_index" in claim
    assert "original_sentence" in claim
    assert "rendered_text" in claim
    assert "action" in claim
    assert "reason" in claim
    assert "cited_atoms" in claim
    assert "missing_atoms" in claim
    assert "detected_endpoint" in claim
    assert "detected_entity" in claim
    assert "detected_timepoint" in claim
    assert "detected_values" in claim


def test_write_gaps_sidecar(tmp_path: Path):
    section_text = "Tirzepatide reduced HbA1c by -2.30 percentage points."
    result = validate_section(
        section_text, "efficacy", "Efficacy", _CATALOG,
    )
    path = write_gaps_sidecar(tmp_path, "test-doc", [result])
    assert path.exists()
    assert path.name == "gaps.json"
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["document_id"] == "test-doc"


# ============================================================================
# Sentence splitter
# ============================================================================


def test_step3b_commit2_biblio_marker_not_triggers_false_claim():
    """Step 3b commit 2 (Codex iter-1 P1.1): [1] bibliography markers
    in resolved verified_text must NOT be parsed as numbers by
    _NUMBER_RE → falsely require atom citation on narrative sentences.
    The citation-strip pre-pass removes them before claim detection."""
    requires, _ = requires_atom_citation(
        "Tirzepatide acts via dual GIP/GLP-1 receptor agonism [1]."
    )
    assert not requires, (
        "Narrative sentence with [1] bibliography marker should NOT "
        "require atom citation — [N] markers are not outcome numbers."
    )


def test_step3b_commit2_atom_id_not_triggers_false_number_in_narrative():
    """Step 3b commit 2: atom_NNN in a narrative sentence must not
    trigger Trigger B (number alone) due to the embedded digits."""
    requires, _ = requires_atom_citation(
        "These outcomes were consistent across the SURPASS program (atom_001)."
    )
    # Narrative phrase ("these outcomes were consistent") matches
    # narrative regex; atom_001 strip prevents the "001" from triggering.
    assert not requires


def test_step3b_commit2_paragraph_preservation_in_validate_section():
    """Step 3b commit 2 (Codex iter-2 P2.4): validate_section must
    preserve paragraph boundaries — \\n\\n separates paragraphs in the
    rendered_text, not all flattened to single line."""
    section_text = (
        "Tirzepatide acts via dual GIP/GLP-1 receptor agonism.\n\n"
        "Tirzepatide reduced HbA1c by -2.30 percentage points atom_003."
    )
    result = validate_section(
        section_text, "efficacy", "Efficacy", _CATALOG,
    )
    assert "\n\n" in result.rendered_text, (
        "Paragraph boundaries must be preserved in rendered_text"
    )


def test_step3b_pr906_iter3_split_handles_resolved_citation_boundary():
    """Codex PR #906 iter-3 P1: resolve_provenance_to_citations emits
    'sentence.[1] next_sentence.[2]' with citation marker glued to the
    period. Splitter must boundary on this.

    Codex iter-4 P1 follow-up: the [N] marker MUST be PRESERVED in the
    preceding sentence (not consumed as delimiter), otherwise strict
    mode would silently drop bibliography citations from report.md."""
    parts = split_sentences("A.[1] B.[2]")
    assert parts == ["A.[1]", "B.[2]"], (
        f"split must preserve [N] in preceding sentence, got {parts}"
    )

    parts2 = split_sentences(
        "Tirzepatide reduced HbA1c by -2.30 (atom_003).[1] "
        "Semaglutide reduced HbA1c by -1.86.[2]"
    )
    assert parts2 == [
        "Tirzepatide reduced HbA1c by -2.30 (atom_003).[1]",
        "Semaglutide reduced HbA1c by -1.86.[2]",
    ], f"clinical pattern must preserve atom_NNN + [N], got {parts2}"


def test_step3b_commit2_sentence_index_monotonic_across_paragraphs():
    """Step 3b commit 2 (Codex iter-2 P2.4): sentence_index increments
    across paragraphs to ensure claim_id values stay unique in gaps.json."""
    section_text = (
        "First narrative sentence.\n\n"
        "Second paragraph sentence one. Second paragraph sentence two."
    )
    result = validate_section(
        section_text, "test", "Test", _CATALOG,
    )
    indices = [g.sentence_index for g in result.gap_records]
    assert indices == sorted(indices) and len(indices) == len(set(indices)), (
        f"sentence_index must be monotonic + unique across paragraphs, "
        f"got {indices}"
    )


def test_split_sentences_decimal_aware():
    """Decimal-aware split — '2.30' is one token, not 'sentence 2. 30 ...'."""
    parts = split_sentences(
        "HbA1c was -2.30. AE rate was 43%."
    )
    assert len(parts) == 2
    assert "-2.30" in parts[0]
    assert "43%" in parts[1]


# ============================================================================
# ITER-2 REGRESSION TESTS (Codex iter-1 verdict)
# ============================================================================


def test_iter2_p1_qualitative_comparative_safety_requires_atom():
    """Codex iter-1 P1 repro: 'Adverse events were more common with
    tirzepatide than placebo.' must REQUIRE atom citation. Was returning
    False because 'more common' wasn't in qual regex AND comparator-arm
    signal didn't override missing endpoint."""
    requires, trigger = requires_atom_citation(
        "Adverse events were more common with tirzepatide than placebo."
    )
    assert requires, "Comparative safety claim must require atom citation"
    assert trigger == "trigger_qualitative_comparative"


def test_iter2_p1_qualitative_higher_with_drug_requires_atom():
    """Codex iter-1 P1 repro: 'Nausea was higher with tirzepatide than
    placebo.' must require atom. 'Nausea' wasn't in endpoint vocab + no
    qual regex match."""
    requires, trigger = requires_atom_citation(
        "Nausea was higher with tirzepatide than placebo."
    )
    assert requires
    assert trigger == "trigger_qualitative_comparative"


def test_iter2_p1_qualitative_greater_reduction_than_requires_atom():
    """Codex iter-1 P1 repro: 'Tirzepatide showed greater reduction than
    semaglutide.' must require atom. No endpoint vocab term but clearly
    a comparative claim via 'greater <noun> than <drug>'."""
    requires, trigger = requires_atom_citation(
        "Tirzepatide showed greater reduction than semaglutide."
    )
    assert requires
    assert trigger == "trigger_qualitative_comparative"


def test_iter2_p2_eligibility_range_now_requires_atom_safe_default():
    """Superseded by iter-4 (Codex iter-3 continuing-P1): eligibility
    override removed. Quantitative + endpoint sentences require atom
    citation regardless of eligibility framing — safer default."""
    requires, _ = requires_atom_citation(
        "Eligible patients had inclusion criteria of HbA1c between 7.0 and 10.0."
    )
    assert requires


def test_iter2_p2_soft_value_word_boundary_match():
    """Codex iter-1 P2 repro: atom_003 value=-2.30; sentence value=12.30.
    Old substring check returned ALLOWED (false negative); new numeric-
    token-boundary check correctly returns LOGGED_ONLY (SOFT_MISMATCH)."""
    record = validate_sentence(
        "Tirzepatide reduced HbA1c by 12.30 percentage points atom_003.",
        sentence_index=0,
        section_id="efficacy",
        section_title="Efficacy",
        catalog=_CATALOG,
    )
    assert record.action == RefusalAction.LOGGED_ONLY, (
        f"12.30 in sentence != atom_003.value=-2.30; should be SOFT_MISMATCH "
        f"(numeric-token boundary), not ALLOWED. Got {record.action}"
    )
    assert record.reason == RefusalReason.SOFT_MISMATCH


def test_iter3_p1_eligibility_override_does_not_mask_outcome_claim():
    """Codex iter-2 novel-P1 repro: 'Patients with baseline HbA1c of 8.6%
    had HbA1c reductions of 2.3 percentage points.' was returning False
    (allowed) because 'baseline HbA1c' fired eligibility override. This
    is a REAL outcome claim ('reductions of 2.3 percentage points') and
    must require atom citation."""
    requires, trigger = requires_atom_citation(
        "Patients with baseline HbA1c of 8.6% had HbA1c reductions of "
        "2.3 percentage points."
    )
    assert requires, (
        "Outcome claim with baseline-mention must require atom citation, "
        "not bypass via eligibility override"
    )
    assert trigger == "trigger_A_number_plus_endpoint"


def test_iter3_p2_comparator_arm_does_not_match_generic_words():
    """Codex iter-2 P2 repro: 'This was more than enough evidence' and
    'More patients than expected completed follow-up' must NOT trigger
    qualitative comparator because 'enough' and 'expected' aren't
    treatment arms."""
    requires1, _ = requires_atom_citation(
        "This was more than enough evidence to proceed."
    )
    assert not requires1, (
        "'more than enough' is benign prose, not a comparative claim"
    )

    requires2, _ = requires_atom_citation(
        "More patients than expected completed follow-up."
    )
    assert not requires2, (
        "'more than expected' is benign prose, not a comparative claim"
    )


def test_iter3_eligibility_now_requires_atom_post_override_removal():
    """Iter-4 update: eligibility override removed entirely (Codex
    iter-3 continuing-P1). Pure eligibility sentences with endpoint+
    number now also require atom (safe default)."""
    requires, _ = requires_atom_citation(
        "Inclusion criteria required HbA1c between 7.0 and 10.0."
    )
    assert requires


def test_iter3_qualitative_drug_arm_still_requires_atom():
    """Regression check: drug comparator arms still trigger atom requirement
    (tightening the `\\w{3,}` didn't break the legitimate cases)."""
    requires, _ = requires_atom_citation(
        "Tirzepatide showed greater reduction than semaglutide."
    )
    assert requires


def test_iter4_codex_repro_outcome_with_criteria_still_required():
    """Codex iter-3 continuing-P1 repro: 'Patients meeting inclusion
    criteria had HbA1c of 6.8% at 40 weeks.' must require atom."""
    requires, _ = requires_atom_citation(
        "Patients meeting inclusion criteria had HbA1c of 6.8% at 40 weeks."
    )
    assert requires, (
        "Outcome claim with criteria-frame must require atom citation"
    )


def test_iter4_comparator_arm_uses_full_drug_regex():
    """Codex iter-3 novel-P1: 'Tirzepatide showed greater reduction
    than exenatide.' was failing because exenatide wasn't in iter-3's
    hardcoded comparator list. iter-4 imports _DRUG_RE from
    atom_extractor so any drug it knows about is auto-included."""
    requires, trigger = requires_atom_citation(
        "Tirzepatide showed greater reduction than exenatide."
    )
    assert requires
    assert trigger == "trigger_qualitative_comparative"


def test_iter2_p2_refused_record_includes_detected_values():
    """Codex iter-1 P2: refused records must populate detected_values
    for downstream audit."""
    record = validate_sentence(
        "Tirzepatide reduced HbA1c by -2.30 percentage points at 40 weeks.",
        sentence_index=0,
        section_id="efficacy",
        section_title="Efficacy",
        catalog=_CATALOG,
    )
    assert record.action == RefusalAction.REFUSED
    assert "-2.30" in record.detected_values, (
        f"Refused record must preserve detected_values. Got: {record.detected_values}"
    )


def test_step3h_splitter_does_not_break_on_semicolon_inside_parens():
    """Step 3h fix (real-V4-Pro smoke PR #911 data): V4 Pro emits
    long sentences with `;` INSIDE parentheses (CI bounds, p-values).
    Pre-fix splitter broke into 3+ fragments → false refusals."""
    text = (
        "The treatment differences were -0.15 percentage points "
        "(95% CI, -0.28 to -0.03; P=0.02) for the 5 mg dose, "
        "-0.39 percentage points (95% CI, -0.51 to -0.26; P<0.001) "
        "for the 10 mg dose. Next sentence."
    )
    parts = split_sentences(text)
    assert len(parts) == 2, (
        f"Should split into 2 sentences (clinical claim + 'Next sentence.'), "
        f"got {len(parts)}: {parts}"
    )


def test_step3h_splitter_keeps_balanced_brackets_outside_parens():
    """Regression: [N] biblio markers (balanced) STILL boundary correctly
    when sentence ends with .[N] (not inside parens)."""
    parts = split_sentences("A.[1] B.[2]")
    assert parts == ["A.[1]", "B.[2]"]


def test_step3h_soft_layer_handles_unicode_minus():
    """Step 3h fix (real-V4-Pro smoke PR #911 data): V4 Pro emits
    U+2212 (MINUS SIGN, "−") for negative clinical values; atom values
    use U+002D (HYPHEN-MINUS, "-"). Without normalization on BOTH sides,
    every clinical negative was a false SOFT_MISMATCH. Real smoke
    showed 4/4 soft_mismatches were this artifact."""
    catalog = {
        "atom_001": ClaimAtom(
            atom_id="atom_001",
            evidence_id="ev_001",
            span_start=0,
            span_end=10,
            literal_text="placeholder",
            entity="tirzepatide",
            endpoint="HbA1c",
            comparator="",
            timepoint="",
            value="-2.30",  # stored with ASCII hyphen-minus
            unit="percentage points",
            primary_section="Efficacy",
            section_tags=("Efficacy",),
            tier="T1",
            value_signed=True,
            confidence="high",
            provenance_class="open_access",
            source_paper_title="t",
        ),
    }
    # Sentence with U+2212 minus (real V4 Pro output)
    record = validate_sentence(
        "Tirzepatide reduced HbA1c by −2.30 percentage points (atom_001).",
        sentence_index=0,
        section_id="efficacy",
        section_title="Efficacy",
        catalog=catalog,
    )
    assert record.action == RefusalAction.ALLOWED, (
        f"U+2212 minus should normalize to ASCII for comparison; "
        f"got action={record.action} reason={record.reason} notes={record.notes}"
    )
