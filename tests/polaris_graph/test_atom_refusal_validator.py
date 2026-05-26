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
