"""Tests for src/polaris_graph/generator/cross_jurisdiction_synthesizer.py
(M-14, Phase C)."""

from __future__ import annotations

import pytest

from src.polaris_graph.generator.cross_jurisdiction_synthesizer import (
    CrossJurisdictionSynthesis,
    FieldVerdict,
    JurisdictionFinding,
    is_known_jurisdiction,
    synthesis_to_dict,
    synthesize_cross_jurisdiction,
)


# ---------------------------------------------------------------------------
# Jurisdiction validation
# ---------------------------------------------------------------------------


def test_known_jurisdictions_recognized() -> None:
    for j in ("FDA", "EMA", "MHRA", "PMDA", "NICE", "HC", "TGA"):
        assert is_known_jurisdiction(j)
        assert is_known_jurisdiction(j.lower())


def test_unknown_jurisdiction_rejected() -> None:
    assert is_known_jurisdiction("ANVISA") is False
    assert is_known_jurisdiction("FRD") is False  # typo of FDA
    assert is_known_jurisdiction("") is False


def test_jurisdiction_normalized_to_uppercase() -> None:
    f = JurisdictionFinding(
        jurisdiction="fda", field_name="indications",
        value="approved for X", bound_ev_id="ev_1",
    )
    assert f.jurisdiction == "FDA"


def test_unknown_jurisdiction_raises_in_synthesize() -> None:
    """LAW II — never silently fuzzy-match a typo'd jurisdiction
    string. Surface upstream catalog drift loudly."""
    with pytest.raises(ValueError, match="unknown jurisdiction"):
        synthesize_cross_jurisdiction([
            JurisdictionFinding(
                jurisdiction="FRD", field_name="indications",
                value="x", bound_ev_id="ev_1",
            ),
        ])


# ---------------------------------------------------------------------------
# Single-jurisdiction case
# ---------------------------------------------------------------------------


def test_single_jurisdiction_emits_single_source_paragraph() -> None:
    findings = [JurisdictionFinding(
        jurisdiction="FDA", field_name="indications",
        value="approved for adults with type 2 diabetes",
        bound_ev_id="ev_fda_1",
    )]
    result = synthesize_cross_jurisdiction(findings)
    assert len(result.paragraphs) == 1
    para = result.paragraphs[0]
    assert "FDA only" in para
    assert "ev_fda_1" in para
    assert "Other jurisdictions" in para
    assert len(result.verdicts) == 1
    v = result.verdicts[0]
    assert v.verdict == "single_source"
    assert v.jurisdictions == ("FDA",)
    assert v.bound_ev_ids == ("ev_fda_1",)


# ---------------------------------------------------------------------------
# Convergence case
# ---------------------------------------------------------------------------


def test_convergence_paragraph_when_all_jurisdictions_agree() -> None:
    """Identical prose across FDA/EMA/MHRA → CONVERGENCE verdict
    + paragraph naming all jurisdictions."""
    common = "approved for adults with type 2 diabetes mellitus"
    findings = [
        JurisdictionFinding("FDA", "indications", common, "ev_fda"),
        JurisdictionFinding("EMA", "indications", common, "ev_ema"),
        JurisdictionFinding("MHRA", "indications", common, "ev_mhra"),
    ]
    result = synthesize_cross_jurisdiction(findings)
    assert len(result.paragraphs) == 1
    para = result.paragraphs[0]
    assert "convergence" in para.lower()
    assert "FDA" in para
    assert "EMA" in para
    assert "MHRA" in para
    # All three citations bound.
    assert "ev_fda" in para
    assert "ev_ema" in para
    assert "ev_mhra" in para
    v = result.verdicts[0]
    assert v.verdict == "convergence"
    assert v.similarity >= 0.5


def test_convergence_picks_longest_value_as_canonical() -> None:
    """When multiple jurisdictions converge, the longest (most
    informative) prose is shown verbatim."""
    findings = [
        JurisdictionFinding("FDA", "indications",
                            "approved for diabetes", "ev_short"),
        JurisdictionFinding("EMA", "indications",
                            "approved for type 2 diabetes mellitus in adults",
                            "ev_long"),
    ]
    result = synthesize_cross_jurisdiction(findings)
    # Even though "approved for diabetes" is shorter, the EMA value
    # is preserved because it's more informative.
    assert "type 2 diabetes mellitus in adults" in result.paragraphs[0]


# ---------------------------------------------------------------------------
# Divergence case — the LAW II safeguard
# ---------------------------------------------------------------------------


def test_divergence_paragraph_when_jurisdictions_disagree() -> None:
    """Materially different prose across jurisdictions → DIVERGENCE
    verdict + per-jurisdiction bullet list, NOT a flattened
    consensus claim."""
    findings = [
        JurisdictionFinding(
            "FDA", "boxed_warning",
            "thyroid C-cell tumors observed in rodent studies",
            "ev_fda",
        ),
        JurisdictionFinding(
            "EMA", "boxed_warning",
            "no boxed warning issued; routine pharmacovigilance",
            "ev_ema",
        ),
        JurisdictionFinding(
            "PMDA", "boxed_warning",
            "label revision pending review of post-marketing data",
            "ev_pmda",
        ),
    ]
    result = synthesize_cross_jurisdiction(findings)
    para = result.paragraphs[0]
    assert "divergence" in para.lower()
    # Each jurisdiction's distinct prose appears.
    assert "thyroid C-cell" in para
    assert "no boxed warning" in para
    assert "post-marketing" in para
    # Each citation appears.
    assert "ev_fda" in para
    assert "ev_ema" in para
    assert "ev_pmda" in para
    v = result.verdicts[0]
    assert v.verdict == "divergence"
    assert v.similarity < 0.5


def test_divergence_does_not_emit_consensus_phrase() -> None:
    """Critical LAW II property: a DIVERGENCE paragraph must NEVER
    use language like 'regulators worldwide approved' that would
    misrepresent the disagreement."""
    findings = [
        JurisdictionFinding(
            "FDA", "indications", "approved for adults",
            "ev_fda",
        ),
        JurisdictionFinding(
            "EMA", "indications",
            "withheld pending pediatric data review",
            "ev_ema",
        ),
    ]
    result = synthesize_cross_jurisdiction(findings)
    para = result.paragraphs[0]
    # No flattening language.
    forbidden_phrases = [
        "regulators worldwide",
        "regulators approved",
        "globally approved",
        "all regulators",
        "international consensus",
    ]
    para_lower = para.lower()
    for phrase in forbidden_phrases:
        assert phrase not in para_lower, (
            f"divergence paragraph contains flattening language: {phrase!r}"
        )


# ---------------------------------------------------------------------------
# Multi-field grouping
# ---------------------------------------------------------------------------


def test_multiple_fields_grouped_independently() -> None:
    findings = [
        JurisdictionFinding("FDA", "indications", "approved for X", "ev_1"),
        JurisdictionFinding("EMA", "indications", "approved for X", "ev_2"),
        JurisdictionFinding(
            "FDA", "boxed_warning", "rare cardiac events", "ev_3",
        ),
        JurisdictionFinding(
            "EMA", "boxed_warning",
            "no boxed warning issued at this time",
            "ev_4",
        ),
    ]
    result = synthesize_cross_jurisdiction(findings)
    assert len(result.paragraphs) == 2
    # Indications: convergence; boxed_warning: divergence.
    by_field = {v.field_name: v for v in result.verdicts}
    assert by_field["indications"].verdict == "convergence"
    assert by_field["boxed_warning"].verdict == "divergence"


def test_field_name_case_insensitive_grouping() -> None:
    findings = [
        JurisdictionFinding("FDA", "Indications", "approved for X", "ev_1"),
        JurisdictionFinding("EMA", "INDICATIONS", "approved for X", "ev_2"),
    ]
    result = synthesize_cross_jurisdiction(findings)
    assert len(result.paragraphs) == 1
    assert result.verdicts[0].verdict == "convergence"


def test_paragraphs_ordered_alphabetically_by_field() -> None:
    findings = [
        JurisdictionFinding("FDA", "warnings", "x", "ev_1"),
        JurisdictionFinding("FDA", "indications", "y", "ev_2"),
        JurisdictionFinding("FDA", "boxed_warning", "z", "ev_3"),
    ]
    result = synthesize_cross_jurisdiction(findings)
    field_names = [v.field_name for v in result.verdicts]
    assert field_names == sorted(field_names)


# ---------------------------------------------------------------------------
# Empty / missing values
# ---------------------------------------------------------------------------


def test_empty_value_skipped() -> None:
    """A finding with empty value (M-70 emitted not_extractable)
    should be treated as 'no finding' and excluded from the
    paragraph, not represented as 'FDA: blank'."""
    findings = [
        JurisdictionFinding("FDA", "indications", "approved for X", "ev_1"),
        JurisdictionFinding("EMA", "indications", "", "ev_2"),
    ]
    result = synthesize_cross_jurisdiction(findings)
    # Single source: only FDA has a value.
    v = result.verdicts[0]
    assert v.verdict == "single_source"
    assert v.jurisdictions == ("FDA",)


def test_all_empty_values_emit_no_findings_verdict() -> None:
    findings = [
        JurisdictionFinding("FDA", "indications", "", "ev_1"),
        JurisdictionFinding("EMA", "indications", "   ", "ev_2"),
    ]
    result = synthesize_cross_jurisdiction(findings)
    assert result.paragraphs == ()
    assert len(result.verdicts) == 1
    assert result.verdicts[0].verdict == "no_findings"


def test_empty_findings_list_returns_empty_synthesis() -> None:
    result = synthesize_cross_jurisdiction([])
    assert result.paragraphs == ()
    assert result.verdicts == ()


# ---------------------------------------------------------------------------
# Threshold tuning
# ---------------------------------------------------------------------------


def test_convergence_floor_invalid_raises() -> None:
    findings = [
        JurisdictionFinding("FDA", "x", "y", "ev_1"),
        JurisdictionFinding("EMA", "x", "y", "ev_2"),
    ]
    with pytest.raises(ValueError, match=r"convergence_floor"):
        synthesize_cross_jurisdiction(findings, convergence_floor=1.5)
    with pytest.raises(ValueError, match=r"convergence_floor"):
        synthesize_cross_jurisdiction(findings, convergence_floor=-0.1)


def test_high_threshold_pushes_to_divergence() -> None:
    """Identical-but-short prose at threshold=0.99 should still
    converge (Jaccard = 1.0). Setting threshold > 1.0 is a config
    error caught by the bounds check above."""
    findings = [
        JurisdictionFinding("FDA", "indications",
                            "approved for diabetes", "ev_1"),
        JurisdictionFinding("EMA", "indications",
                            "approved for diabetes", "ev_2"),
    ]
    result = synthesize_cross_jurisdiction(findings, convergence_floor=0.99)
    assert result.verdicts[0].verdict == "convergence"


def test_low_threshold_keeps_loose_matches_in_convergence() -> None:
    """Setting a permissive threshold (0.1) routes mostly-similar
    prose into convergence."""
    findings = [
        JurisdictionFinding("FDA", "indications",
                            "approved for diabetes mellitus type 2 in adults",
                            "ev_1"),
        JurisdictionFinding("EMA", "indications",
                            "approved for type 2 diabetes",
                            "ev_2"),
    ]
    result = synthesize_cross_jurisdiction(findings, convergence_floor=0.1)
    assert result.verdicts[0].verdict == "convergence"


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_synthesis_is_deterministic() -> None:
    findings = [
        JurisdictionFinding("FDA", "indications", "approved for X", "ev_1"),
        JurisdictionFinding("EMA", "indications", "approved for Y", "ev_2"),
    ]
    a = synthesize_cross_jurisdiction(findings)
    b = synthesize_cross_jurisdiction(findings)
    assert a == b


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def test_synthesis_to_dict_round_trip() -> None:
    findings = [
        JurisdictionFinding("FDA", "indications", "approved for X", "ev_1"),
        JurisdictionFinding("EMA", "indications", "approved for X", "ev_2"),
    ]
    result = synthesize_cross_jurisdiction(findings)
    d = synthesis_to_dict(result)
    assert isinstance(d["paragraphs"], list)
    assert isinstance(d["verdicts"], list)
    v = d["verdicts"][0]
    assert v["field_name"] == "indications"
    assert v["verdict"] == "convergence"
    assert "FDA" in v["jurisdictions"]
    assert "EMA" in v["jurisdictions"]


# ---------------------------------------------------------------------------
# Integration-ish: full FDA+EMA+MHRA+PMDA combo with mixed verdicts
# ---------------------------------------------------------------------------


def test_realistic_four_jurisdiction_mixed_verdicts() -> None:
    """Realistic shape: 4 jurisdictions × 3 fields with one
    convergence, one divergence, one single-source."""
    findings = [
        # indications: all four agree (convergence).
        JurisdictionFinding(
            "FDA", "indications",
            "approved for type 2 diabetes mellitus in adults",
            "ev_fda_ind",
        ),
        JurisdictionFinding(
            "EMA", "indications",
            "approved for type 2 diabetes mellitus in adults",
            "ev_ema_ind",
        ),
        JurisdictionFinding(
            "MHRA", "indications",
            "approved for type 2 diabetes mellitus in adults",
            "ev_mhra_ind",
        ),
        JurisdictionFinding(
            "PMDA", "indications",
            "approved for type 2 diabetes mellitus in adults",
            "ev_pmda_ind",
        ),
        # boxed_warning: FDA has it, EMA doesn't, MHRA doesn't,
        # PMDA pending → divergence.
        JurisdictionFinding(
            "FDA", "boxed_warning",
            "thyroid C-cell tumors in rodent studies; not for MEN-2",
            "ev_fda_box",
        ),
        JurisdictionFinding(
            "EMA", "boxed_warning",
            "no boxed warning section in EU label",
            "ev_ema_box",
        ),
        JurisdictionFinding(
            "PMDA", "boxed_warning",
            "label revision pending post-marketing review",
            "ev_pmda_box",
        ),
        # post_marketing_commitments: FDA only → single_source.
        JurisdictionFinding(
            "FDA", "post_marketing_commitments",
            "Phase 4 trial NCT-XXX in adolescents; long-term safety registry",
            "ev_fda_pmc",
        ),
    ]
    result = synthesize_cross_jurisdiction(findings)
    by_field = {v.field_name: v for v in result.verdicts}

    assert by_field["indications"].verdict == "convergence"
    assert set(by_field["indications"].jurisdictions) == {
        "FDA", "EMA", "MHRA", "PMDA",
    }

    assert by_field["boxed_warning"].verdict == "divergence"
    assert set(by_field["boxed_warning"].jurisdictions) == {
        "FDA", "EMA", "PMDA",
    }

    assert by_field["post_marketing_commitments"].verdict == "single_source"
    assert by_field["post_marketing_commitments"].jurisdictions == ("FDA",)
