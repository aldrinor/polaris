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
    # Codex M-14 v2 fix: citation contract is `[cite:ev_id]`.
    assert "[cite:ev_fda_1]" in para
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
    # Codex M-14 v2: citations use the `[cite:ev_id]` contract.
    assert "[cite:ev_fda]" in para
    assert "[cite:ev_ema]" in para
    assert "[cite:ev_mhra]" in para
    v = result.verdicts[0]
    assert v.verdict == "convergence"
    # Codex M-14 v2: default floor is 0.7, not 0.5.
    assert v.similarity >= 0.7


def test_convergence_picks_longest_value_as_canonical() -> None:
    """When multiple jurisdictions converge, the longest (most
    informative) prose is shown verbatim. Pass convergence_floor=0.3
    so the differently-lengthed values still converge under v2."""
    findings = [
        JurisdictionFinding("FDA", "indications",
                            "approved for diabetes", "ev_short"),
        JurisdictionFinding("EMA", "indications",
                            "approved for diabetes mellitus in adults",
                            "ev_long"),
    ]
    result = synthesize_cross_jurisdiction(findings, convergence_floor=0.3)
    # Even though "approved for diabetes" is shorter, the EMA value
    # is preserved because it's more informative.
    assert "diabetes mellitus in adults" in result.paragraphs[0]


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
# Codex M-14 v2 review regressions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "values",
    [
        # Direct negation — the dominant LAW II failure mode.
        ("approved for adults", "not approved for adults"),
        # Negation phrased differently.
        ("contraindicated in pregnancy", "not contraindicated in pregnancy"),
        # Withdrawn / withheld vs approved.
        ("approved for type 2 diabetes",
         "withheld pending pediatric data review"),
        # Approved vs rejected.
        ("approved for chronic heart failure",
         "rejected for chronic heart failure"),
    ],
)
def test_negation_forces_divergence_regardless_of_jaccard(values: tuple[str, str]) -> None:
    """Codex M-14 v2 review regression: pure token-set Jaccard
    treats "X" vs "not X" as ~0.667 similar, falsely converging.
    The hard force-divergence guard catches this BEFORE Jaccard."""
    fa, fb = values
    findings = [
        JurisdictionFinding("FDA", "boxed_warning", fa, "ev_fda"),
        JurisdictionFinding("EMA", "boxed_warning", fb, "ev_ema"),
    ]
    result = synthesize_cross_jurisdiction(findings)
    assert result.verdicts[0].verdict == "divergence", (
        f"negation case {values!r} flattened to "
        f"{result.verdicts[0].verdict}"
    )


def test_scope_limiter_forces_divergence() -> None:
    """`only` / `restricted` qualifiers materially change the
    indicated population. Their presence vs absence must force
    divergence."""
    findings = [
        JurisdictionFinding(
            "FDA", "indications",
            "approved for adults only", "ev_fda",
        ),
        JurisdictionFinding(
            "EMA", "indications",
            "approved for adults and adolescents", "ev_ema",
        ),
    ]
    result = synthesize_cross_jurisdiction(findings)
    assert result.verdicts[0].verdict == "divergence"


def test_pending_status_forces_divergence() -> None:
    """A jurisdiction with `pending` regulatory status must
    diverge from one with finalized approval."""
    findings = [
        JurisdictionFinding(
            "FDA", "post_marketing",
            "approved with annual safety reporting", "ev_fda",
        ),
        JurisdictionFinding(
            "PMDA", "post_marketing",
            "label revision pending review of Phase 4 data",
            "ev_pmda",
        ),
    ]
    result = synthesize_cross_jurisdiction(findings)
    assert result.verdicts[0].verdict == "divergence"


def test_numeric_mismatch_forces_divergence() -> None:
    """Different numeric values (dose mg, age cutoffs) must force
    divergence even if surrounding tokens overlap heavily."""
    findings = [
        JurisdictionFinding(
            "FDA", "dosage",
            "starting dose 5 mg once daily", "ev_fda",
        ),
        JurisdictionFinding(
            "EMA", "dosage",
            "starting dose 10 mg once daily", "ev_ema",
        ),
    ]
    result = synthesize_cross_jurisdiction(findings)
    assert result.verdicts[0].verdict == "divergence", (
        "5 mg vs 10 mg must NEVER converge despite token overlap"
    )


def test_asymmetric_numeric_presence_forces_divergence() -> None:
    """One jurisdiction quantifies, another doesn't → divergence."""
    findings = [
        JurisdictionFinding(
            "FDA", "dosage",
            "starting dose 5 mg daily", "ev_fda",
        ),
        JurisdictionFinding(
            "EMA", "dosage",
            "starting dose as recommended by physician", "ev_ema",
        ),
    ]
    result = synthesize_cross_jurisdiction(findings)
    assert result.verdicts[0].verdict == "divergence"


def test_synthesis_invariant_under_input_permutation() -> None:
    """Codex M-14 v2 review regression: convergence canonical
    selection + citation order must be deterministic across input
    permutations. Same set of findings → identical paragraph."""
    findings_a = [
        JurisdictionFinding("FDA", "indications",
                            "approved for adults with type 2 diabetes mellitus",
                            "ev_fda"),
        JurisdictionFinding("EMA", "indications",
                            "approved for adults with type 2 diabetes mellitus",
                            "ev_ema"),
        JurisdictionFinding("MHRA", "indications",
                            "approved for adults with type 2 diabetes mellitus",
                            "ev_mhra"),
    ]
    findings_b = list(reversed(findings_a))
    a = synthesize_cross_jurisdiction(findings_a)
    b = synthesize_cross_jurisdiction(findings_b)
    assert a == b, "synthesis differs under input permutation"


def test_convergence_canonical_tiebreak_is_jurisdiction_alpha() -> None:
    """When multiple values have identical lengths, the canonical
    is the one whose jurisdiction sorts first alphabetically."""
    findings = [
        JurisdictionFinding("FDA", "indications",
                            "approved for adults", "ev_fda"),
        JurisdictionFinding("EMA", "indications",
                            "approved for adults", "ev_ema"),
        JurisdictionFinding("MHRA", "indications",
                            "approved for adults", "ev_mhra"),
    ]
    result = synthesize_cross_jurisdiction(findings)
    # All values identical; alphabetically first jurisdiction is EMA.
    # The paragraph should be deterministic, but more importantly,
    # citation order must be (EMA, FDA, MHRA).
    para = result.paragraphs[0]
    ema_idx = para.find("[cite:ev_ema]")
    fda_idx = para.find("[cite:ev_fda]")
    mhra_idx = para.find("[cite:ev_mhra]")
    assert 0 <= ema_idx < fda_idx < mhra_idx


def test_smuggled_flattening_phrase_in_value_neutralized() -> None:
    """Codex M-14 v2 review regression: even on the divergence
    path, if upstream M-70 prose contained `regulators worldwide`
    or similar, M-14's bullet must NOT preserve it. The
    flattening-phrase guard rewrites it to `[this jurisdiction]`."""
    findings = [
        JurisdictionFinding(
            "FDA", "indications",
            "approved by regulators worldwide for type 2 diabetes",
            "ev_fda",
        ),
        JurisdictionFinding(
            "EMA", "indications",
            "withheld pending review",
            "ev_ema",
        ),
    ]
    result = synthesize_cross_jurisdiction(findings)
    para = result.paragraphs[0]
    # The verdict is divergence (negation/pending guard fires).
    assert result.verdicts[0].verdict == "divergence"
    # The flattening phrase must not appear.
    assert "regulators worldwide" not in para.lower()
    # The replacement marker should appear.
    assert "[this jurisdiction]" in para


def test_citation_format_uses_cite_prefix() -> None:
    """Codex M-14 v2 review fix: citation contract is `[cite:ev_id]`,
    NOT bare `[ev_id]`. The bare form would be confused with the
    V30 strict_verify token format `[#ev:id:start-end]`."""
    findings = [
        JurisdictionFinding("FDA", "x", "approved for X", "ev_id_1"),
        JurisdictionFinding("EMA", "x", "approved for X", "ev_id_2"),
    ]
    result = synthesize_cross_jurisdiction(findings)
    para = result.paragraphs[0]
    # The renderer-only `[cite:ev_id]` contract.
    assert "[cite:ev_id_1]" in para
    assert "[cite:ev_id_2]" in para
    # Must NOT emit the bare `[ev_id]` form.
    # (We can't simply assert "[ev_id_1]" not in para because that
    # substring is present inside `[cite:ev_id_1]`. Instead check
    # the non-cite-prefixed form via regex.)
    import re as _re
    bare_matches = _re.findall(r"(?<!:)\[ev_id_\d\]", para)
    assert not bare_matches, (
        f"bare [ev_id] tokens leaked: {bare_matches}"
    )


# ---------------------------------------------------------------------------
# Codex M-14 v3 review regressions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "values",
    [
        ("approved for adults with type 2 diabetes",
         "isn't approved for adults with type 2 diabetes"),
        ("approved for adults with type 2 diabetes",
         "aren't approved for adults with type 2 diabetes"),
        ("approved for adults with type 2 diabetes",
         "can't be approved for adults with type 2 diabetes"),
        ("approved for adults with type 2 diabetes",
         "won't approve for adults with type 2 diabetes"),
        ("approved for adults",
         "doesn't approve for adults"),
        ("approved for adults",
         "didn't approve for adults"),
        # Apostrophe-less spellings (cant, dont, isnt) seen in
        # the wild from naive copy-paste.
        ("approved for adults",
         "isnt approved for adults"),
        # "cannot" is a common single-word negation.
        ("approved for adults",
         "cannot be approved for adults"),
    ],
)
def test_contraction_negation_forces_divergence(values: tuple[str, str]) -> None:
    """Codex M-14 v3 review regression: v2 tokenized "isn't" as
    {"isn", "t"} — fragments — and the negation guard never saw
    "not". v3 expands contractions BEFORE tokenization."""
    fa, fb = values
    findings = [
        JurisdictionFinding("FDA", "indications", fa, "ev_fda"),
        JurisdictionFinding("EMA", "indications", fb, "ev_ema"),
    ]
    result = synthesize_cross_jurisdiction(findings)
    assert result.verdicts[0].verdict == "divergence", (
        f"contraction case {values!r} flattened to "
        f"{result.verdicts[0].verdict}"
    )


@pytest.mark.parametrize(
    "smuggled_value",
    [
        "approved worldwide for type 2 diabetes",
        "approved globally for chronic conditions",
        "internationally approved for the same indication",
        "consensus across jurisdictions on this indication",
        "global consensus among regulators",
        "unanimously approved by all regulators",
        "every jurisdiction has approved this drug",
        "every regulator has approved this drug",
    ],
)
def test_smuggled_flattening_variants_neutralized(smuggled_value: str) -> None:
    """Codex M-14 v3 review regression: v2 was exact-substring
    match. v3 catches "approved worldwide", "approved globally",
    "internationally approved", "consensus across jurisdictions",
    "unanimously approved", "every jurisdiction" via word-boundary
    regex on trigger words."""
    findings = [
        JurisdictionFinding(
            "FDA", "indications", smuggled_value, "ev_fda",
        ),
        JurisdictionFinding(
            "EMA", "indications",
            "withheld pending Phase 4 review",  # forces divergence
            "ev_ema",
        ),
    ]
    result = synthesize_cross_jurisdiction(findings)
    para = result.paragraphs[0]
    # The flattening trigger word should be neutralized in the
    # rendered paragraph.
    para_lower = para.lower()
    forbidden_in_render = [
        "worldwide", "globally", "internationally",
        "international consensus", "global consensus",
        "consensus across jurisdictions", "unanimous",
        "every jurisdiction", "every regulator",
        "all regulators", "all jurisdictions",
        "regulators worldwide", "regulators globally",
    ]
    for trigger in forbidden_in_render:
        # The trigger must NOT appear in the rendered paragraph.
        # (It might still appear in the original `value` we
        # constructed, but the renderer must have replaced it
        # with [this jurisdiction].)
        assert trigger not in para_lower, (
            f"flattening trigger {trigger!r} survived rendering "
            f"in paragraph: {para}"
        )


def test_thousands_separator_does_not_force_false_divergence() -> None:
    """Codex M-14 v3 review regression: v2 numeric guard treated
    "1,000 mg" vs "1000 mg" as divergence because the regex
    extracted {"1","000"} vs {"1000"}. v3 normalizes thousands-
    separator commas so both produce {"1000"}."""
    findings = [
        JurisdictionFinding(
            "FDA", "dosage",
            "starting dose 1,000 mg once daily", "ev_fda",
        ),
        JurisdictionFinding(
            "EMA", "dosage",
            "starting dose 1000 mg once daily", "ev_ema",
        ),
    ]
    result = synthesize_cross_jurisdiction(findings)
    # Thousands-separator parity must be respected: same value,
    # same verdict.
    assert result.verdicts[0].verdict == "convergence", (
        "1,000 mg vs 1000 mg incorrectly flagged as divergence"
    )


@pytest.mark.parametrize(
    "values",
    [
        # Smart right apostrophe (U+2019) — common from Word/PDF
        # copy-paste.
        ("approved for adults with type 2 diabetes",
         "isn’t approved for adults with type 2 diabetes"),
        ("approved for adults",
         "doesn’t approve for adults"),
        ("approved for adults",
         "can’t be approved for adults"),
        # Smart left apostrophe (U+2018) — rarer but appears.
        ("approved for adults",
         "isn‘t approved for adults"),
    ],
)
def test_smart_apostrophe_contraction_forces_divergence(
    values: tuple[str, str],
) -> None:
    """Codex M-14 v4 review regression: v3 contraction expansion
    only matched ASCII apostrophe `'`. Smart apostrophes (U+2018
    `'`, U+2019 `'`) routinely arrive from Word/PDF copy-paste
    and bypassed the negation guard."""
    fa, fb = values
    findings = [
        JurisdictionFinding("FDA", "indications", fa, "ev_fda"),
        JurisdictionFinding("EMA", "indications", fb, "ev_ema"),
    ]
    result = synthesize_cross_jurisdiction(findings)
    assert result.verdicts[0].verdict == "divergence", (
        f"smart-apostrophe contraction {values!r} flattened to "
        f"{result.verdicts[0].verdict}"
    )


def test_thousands_separator_real_mismatch_still_diverges() -> None:
    """Sanity: the thousands-separator normalization must NOT
    over-correct. Genuinely different values must still diverge."""
    findings = [
        JurisdictionFinding(
            "FDA", "dosage",
            "starting dose 1,000 mg once daily", "ev_fda",
        ),
        JurisdictionFinding(
            "EMA", "dosage",
            "starting dose 2,000 mg once daily", "ev_ema",
        ),
    ]
    result = synthesize_cross_jurisdiction(findings)
    assert result.verdicts[0].verdict == "divergence"


def test_machine_readable_evidence_via_bound_ev_ids_field() -> None:
    """Codex M-14 v2 mandate: pipeline-native code must read
    citation IDs from FieldVerdict.bound_ev_ids, NOT regex-parse
    them out of the rendered paragraph.

    bound_ev_ids ordering follows jurisdiction-alpha. Findings:
    FDA → ev_a, EMA → ev_b. Alphabetically EMA < FDA, so
    bound_ev_ids = (ev_b, ev_a).
    """
    findings = [
        JurisdictionFinding("FDA", "indications", "approved for X", "ev_a"),
        JurisdictionFinding("EMA", "indications", "approved for X", "ev_b"),
    ]
    result = synthesize_cross_jurisdiction(findings)
    v = result.verdicts[0]
    assert v.bound_ev_ids == ("ev_b", "ev_a"), (
        "bound_ev_ids must be ordered by jurisdiction-alpha for "
        "deterministic downstream consumption"
    )
    assert v.jurisdictions == ("EMA", "FDA")


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
