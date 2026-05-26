"""Tests for claim_atom_extractor — the atom-first architecture's
core extraction module.

Per Codex APPROVE_DESIGN 2026-05-26:
    - Option D (regex-now, LLM-later): all extraction is pure regex
    - 13-field ClaimAtom schema (9 Codex + 4 my-proposed additions)
    - Numerical atom_id format ("atom_001", ...)
    - Section-relevance filter for prompt injection
    - Narrative sentences WITH_LIMITS (handled at integration site, not here)

Coverage:
    1. Basic atom extraction (HbA1c reduction with full frame)
    2. Range values (7.25-10.36 kg)
    3. Negative values (HbA1c reduction -2.30)
    4. Multiple atoms per evidence row
    5. Atom skipped when no endpoint found
    6. Section filtering routes atoms correctly
    7. Cross-section atoms (HbA1c is Efficacy AND Comparative AND Dose Response)
    8. Refusal template formatting
    9. Prompt-block formatting (truncation, empty catalog)
    10. Confidence scoring
"""

from __future__ import annotations

from src.polaris_graph.generator.claim_atom_extractor import (
    ClaimAtom,
    build_atom_catalog,
    extract_atoms_from_evidence,
    filter_atoms_for_section,
    format_atom_catalog_for_prompt,
    format_refusal_for_missing_atom,
)


# ----------------------------------------------------------------------------
# Test fixtures (real-style evidence rows from clinical_tirzepatide smokes)
# ----------------------------------------------------------------------------

_SURPASS_2_EV = {
    "evidence_id": "ev_001",
    "tier": "T1",
    "provenance_class": "open_access",
    "title": "Tirzepatide versus Semaglutide Once Weekly in Patients with Type 2 Diabetes",
    "statement": (
        "Tirzepatide versus Semaglutide Once Weekly in Patients with Type 2 Diabetes"
    ),
    "direct_quote": (
        "In the open-label phase 3 SURPASS-2 trial, 1879 adults with type 2 "
        "diabetes were randomized to tirzepatide 5, 10, or 15 mg once weekly "
        "or semaglutide 1 mg. The estimated mean change from baseline in "
        "HbA1c at 40 weeks was -2.01 percentage points with tirzepatide 5 mg, "
        "-2.24 with 10 mg, and -2.30 with 15 mg, versus -1.86 percentage "
        "points with semaglutide. Body weight reduction was 7.6 kg with "
        "tirzepatide 5 mg, 9.3 kg with 10 mg, and 11.2 kg with 15 mg, "
        "compared to 5.7 kg with semaglutide. Adverse events occurred in "
        "43% of all participants. Hypoglycemia was infrequent."
    ),
}

_AFIB_EV = {
    "evidence_id": "ev_023",
    "tier": "T2",
    "provenance_class": "abstract_only",
    "title": "Apixaban vs Warfarin for Stroke Prevention in Atrial Fibrillation",
    "statement": "Apixaban reduces stroke vs warfarin",
    "direct_quote": (
        "In the ARISTOTLE trial of 18,201 patients with atrial fibrillation, "
        "apixaban 5 mg twice daily reduced major bleeding versus warfarin "
        "with a relative risk of 0.69 at 1.8 years. Intracranial hemorrhage "
        "occurred in 0.33% of apixaban patients versus 0.80% of warfarin "
        "patients."
    ),
}


# ----------------------------------------------------------------------------
# 1. Basic atom extraction
# ----------------------------------------------------------------------------

def test_extract_atoms_from_surpass_2_basic():
    atoms = extract_atoms_from_evidence(_SURPASS_2_EV)
    assert len(atoms) >= 4, (
        f"Should extract HbA1c (4 doses) + body weight (4 doses) + AE atoms; got {len(atoms)}"
    )


def test_atom_has_all_17_fields():
    """Iter-2: schema is now 17 fields = 13 Codex APPROVE_DESIGN +
    primary_section (Codex iter-1 P2 addition)."""
    atoms = extract_atoms_from_evidence(_SURPASS_2_EV)
    a = atoms[0]
    expected_fields = {
        "atom_id", "evidence_id", "span_start", "span_end", "literal_text",
        "entity", "endpoint", "comparator", "timepoint", "value", "unit",
        "primary_section", "section_tags", "tier",
        "value_signed", "confidence", "provenance_class", "source_paper_title",
    }
    actual_fields = set(a.__dataclass_fields__.keys())
    assert expected_fields == actual_fields, (
        f"Schema drift: missing={expected_fields - actual_fields} "
        f"extra={actual_fields - expected_fields}"
    )


def test_atom_id_numerical_format():
    """Codex APPROVE_DESIGN: atom_id_format: numerical."""
    atoms = extract_atoms_from_evidence(_SURPASS_2_EV)
    for a in atoms:
        assert a.atom_id.startswith("atom_"), f"Expected atom_NNN, got {a.atom_id}"
        # Suffix must be all digits
        assert a.atom_id.removeprefix("atom_").isdigit()


def test_atom_evidence_id_matches_source():
    atoms = extract_atoms_from_evidence(_SURPASS_2_EV)
    for a in atoms:
        assert a.evidence_id == "ev_001"


def test_atom_literal_text_is_in_direct_quote():
    """Verifier can resolve atom_id back to a literal span. Therefore the
    literal_text MUST appear verbatim in the direct_quote (this is the
    safety floor — atoms are not paraphrased)."""
    atoms = extract_atoms_from_evidence(_SURPASS_2_EV)
    quote = _SURPASS_2_EV["direct_quote"]
    for a in atoms:
        assert a.literal_text in quote, (
            f"Atom literal '{a.literal_text[:60]}' not in direct_quote"
        )


# ----------------------------------------------------------------------------
# 2. Value extraction (signed, ranges, units)
# ----------------------------------------------------------------------------

def test_negative_hba1c_value_signed_true():
    """V4 Pro previously flipped negatives. Atoms must preserve sign."""
    atoms = extract_atoms_from_evidence(_SURPASS_2_EV)
    # Find an HbA1c atom
    hba1c_atoms = [a for a in atoms if a.endpoint == "HbA1c"]
    assert len(hba1c_atoms) >= 1
    # At least one should be negative (HbA1c REDUCTIONS are reported)
    neg_atoms = [a for a in hba1c_atoms if a.value_signed]
    assert len(neg_atoms) >= 1, "Should find at least one negative HbA1c atom"
    # Stored value should preserve the sign
    assert all(a.value.startswith("-") for a in neg_atoms)


def test_unit_extracted():
    atoms = extract_atoms_from_evidence(_SURPASS_2_EV)
    # HbA1c values should have unit "percentage points"
    hba1c = [a for a in atoms if a.endpoint == "HbA1c"]
    assert any("percentage" in a.unit or a.unit == "%" for a in hba1c), (
        f"Expected percentage unit on HbA1c atom; got units {[a.unit for a in hba1c]}"
    )
    # Body weight values should have unit "kg"
    weight = [a for a in atoms if a.endpoint == "body weight"]
    assert any(a.unit == "kg" for a in weight), (
        f"Expected kg unit on body weight atom; got units {[a.unit for a in weight]}"
    )


# ----------------------------------------------------------------------------
# 3. Endpoint + section tag routing
# ----------------------------------------------------------------------------

def test_hba1c_routed_to_efficacy_comparative_dose_response():
    """HbA1c is core efficacy; the comparator (semaglutide) makes it
    comparative; dosing (5/10/15 mg) makes it dose-response. So the
    section_tags should include all three."""
    atoms = extract_atoms_from_evidence(_SURPASS_2_EV)
    hba1c = [a for a in atoms if a.endpoint == "HbA1c"]
    assert hba1c
    tags = hba1c[0].section_tags
    assert "Efficacy" in tags
    assert "Comparative" in tags
    assert "Dose Response" in tags


def test_adverse_events_routed_to_safety_only():
    atoms = extract_atoms_from_evidence(_SURPASS_2_EV)
    ae = [a for a in atoms if a.endpoint == "adverse events"]
    if ae:
        assert ae[0].section_tags == ("Safety",)


def test_atom_skipped_when_no_endpoint():
    """A bare number in evidence with no clinical endpoint context
    should NOT produce an atom (noise reduction)."""
    ev = {
        "evidence_id": "ev_999",
        "tier": "T4",
        "title": "A paper",
        "statement": "",
        "direct_quote": "The number 42 appeared in the title. Also 17 footnotes.",
    }
    atoms = extract_atoms_from_evidence(ev)
    assert atoms == [], "Bare numbers without clinical context should not become atoms"


# ----------------------------------------------------------------------------
# 4. Comparator extraction
# ----------------------------------------------------------------------------

def test_comparator_semaglutide_extracted():
    atoms = extract_atoms_from_evidence(_SURPASS_2_EV)
    has_sema = any("semaglutide" in a.comparator.lower() for a in atoms)
    assert has_sema, (
        f"Should find semaglutide as comparator. Comparators={[a.comparator for a in atoms]}"
    )


def test_afib_warfarin_comparator():
    atoms = extract_atoms_from_evidence(_AFIB_EV)
    has_warf = any("warfarin" in a.comparator.lower() for a in atoms)
    assert has_warf


# ----------------------------------------------------------------------------
# 5. Timepoint extraction
# ----------------------------------------------------------------------------

def test_timepoint_at_40_weeks():
    atoms = extract_atoms_from_evidence(_SURPASS_2_EV)
    has_40w = any("40 week" in a.timepoint for a in atoms)
    assert has_40w, (
        f"Should find 'at 40 weeks' as timepoint. Timepoints={[a.timepoint for a in atoms]}"
    )


# ----------------------------------------------------------------------------
# 6. Entity extraction
# ----------------------------------------------------------------------------

def test_entity_tirzepatide_extracted():
    atoms = extract_atoms_from_evidence(_SURPASS_2_EV)
    has_tirz = any("tirzepatide" in a.entity.lower() for a in atoms)
    assert has_tirz, (
        f"Should find tirzepatide as entity. Entities={[a.entity for a in atoms]}"
    )


# ----------------------------------------------------------------------------
# 7. Catalog + section filter
# ----------------------------------------------------------------------------

def test_build_atom_catalog_two_evidence_rows():
    catalog = build_atom_catalog([_SURPASS_2_EV, _AFIB_EV])
    # All atoms should have unique atom_ids
    assert len(catalog) == len(set(catalog.keys()))
    # Should have atoms from both evidence rows
    ev_ids = {a.evidence_id for a in catalog.values()}
    assert "ev_001" in ev_ids
    assert "ev_023" in ev_ids


def test_filter_atoms_for_efficacy_section():
    catalog = build_atom_catalog([_SURPASS_2_EV])
    efficacy = filter_atoms_for_section(catalog, "Efficacy")
    # All efficacy atoms should have Efficacy in their section_tags
    for a in efficacy.values():
        assert "Efficacy" in a.section_tags


def test_filter_atoms_for_safety_section():
    catalog = build_atom_catalog([_SURPASS_2_EV])
    safety = filter_atoms_for_section(catalog, "Safety")
    # Adverse events / hypoglycemia atoms should be present
    safety_endpoints = {a.endpoint for a in safety.values()}
    assert any(
        ep in ("adverse events", "hypoglycemia", "GI events", "serious adverse events")
        for ep in safety_endpoints
    ), f"Expected safety endpoints; got {safety_endpoints}"


def test_filter_atoms_for_section_case_insensitive():
    catalog = build_atom_catalog([_SURPASS_2_EV])
    lower = filter_atoms_for_section(catalog, "efficacy")
    upper = filter_atoms_for_section(catalog, "EFFICACY")
    title = filter_atoms_for_section(catalog, "Efficacy")
    assert set(lower.keys()) == set(upper.keys()) == set(title.keys())


# ----------------------------------------------------------------------------
# 8. Refusal template (Codex APPROVE_DESIGN exact wording)
# ----------------------------------------------------------------------------

def test_refusal_template_with_full_frame():
    msg = format_refusal_for_missing_atom(
        endpoint="HbA1c",
        entity="tirzepatide 15 mg",
        timepoint="40 weeks",
    )
    assert "Insufficient verified atom-level evidence" in msg
    assert "HbA1c" in msg
    assert "tirzepatide 15 mg" in msg
    assert "40 weeks" in msg


def test_refusal_template_minimal():
    msg = format_refusal_for_missing_atom(endpoint="pancreatitis incidence")
    assert "Insufficient verified atom-level evidence" in msg
    assert "pancreatitis incidence" in msg
    # Falls back to "cited population" when entity is empty
    assert "cited population" in msg


# ----------------------------------------------------------------------------
# 9. Prompt-block formatting
# ----------------------------------------------------------------------------

def test_format_atom_catalog_for_prompt_empty():
    block = format_atom_catalog_for_prompt({})
    assert "empty" in block.lower()


def test_format_atom_catalog_for_prompt_compact():
    catalog = build_atom_catalog([_SURPASS_2_EV])
    block = format_atom_catalog_for_prompt(catalog)
    assert "ATOM CATALOG" in block
    # First atom should appear
    first_aid = sorted(catalog.keys())[0]
    assert first_aid in block
    # And include its literal text
    first_atom = catalog[first_aid]
    assert first_atom.literal_text[:50] in block


def test_format_atom_catalog_truncates_when_too_many():
    # Construct a fake 100-atom catalog by replicating evidence rows
    evidence_rows = [
        {**_SURPASS_2_EV, "evidence_id": f"ev_{i:03d}"} for i in range(20)
    ]
    catalog = build_atom_catalog(evidence_rows)
    block = format_atom_catalog_for_prompt(catalog, max_atoms=10)
    assert "truncated" in block


# ----------------------------------------------------------------------------
# 10. Confidence scoring
# ----------------------------------------------------------------------------

def test_high_confidence_atom_has_full_frame():
    """An atom with entity + endpoint + comparator + timepoint + unit
    should be high confidence."""
    atoms = extract_atoms_from_evidence(_SURPASS_2_EV)
    high_conf = [a for a in atoms if a.confidence == "high"]
    assert len(high_conf) >= 1, (
        f"At least one atom should be high confidence. "
        f"Confidences={[(a.endpoint, a.confidence) for a in atoms]}"
    )


# ----------------------------------------------------------------------------
# Codex iter-1 P1 EXACT REGRESSION TESTS
# These assertions encode the SPECIFIC bugs Codex caught. Each test
# documents the prior-bug behavior + the fixed behavior.
# ----------------------------------------------------------------------------

def test_p1_2_no_timepoint_as_outcome_value():
    """Codex iter-1 P1 #2: '40 weeks' was emitted as HbA1c value.
    After the NumberRole classifier, timepoint numbers must NOT
    appear as atom values."""
    atoms = extract_atoms_from_evidence(_SURPASS_2_EV)
    values = {a.value for a in atoms}
    assert "40" not in values, (
        f"'40' (timepoint) leaked into atom values: {values}"
    )


def test_p1_2_no_dose_as_outcome_value():
    """Codex iter-1 P1 #2: '5 mg' / '10 mg' / '15 mg' were emitted as
    HbA1c values. Must NOT appear as atom values."""
    atoms = extract_atoms_from_evidence(_SURPASS_2_EV)
    values = {a.value for a in atoms}
    # 5, 10, 15 are doses in SURPASS-2
    assert "5" not in values
    assert "10" not in values
    assert "15" not in values


def test_p1_2_no_sample_size_as_outcome_value():
    """Codex iter-1 P1 #2: sample sizes (1879) were emitted as atoms.
    Must NOT appear as atom values."""
    atoms = extract_atoms_from_evidence(_SURPASS_2_EV)
    values = {a.value for a in atoms}
    assert "1879" not in values


def test_p1_2_no_ci_bound_as_outcome_value():
    """Codex iter-1 probe: '(95% CI, 0.58 to 0.95)' emitted 0.58 and
    0.95 as MACE values. Must NOT happen."""
    ev_ci = {
        "evidence_id": "ev_ci",
        "tier": "T1",
        "title": "EMPA-REG MACE",
        "statement": "EMPA-REG showed CV benefit",
        "direct_quote": (
            "In EMPA-REG OUTCOME, empagliflozin reduced MACE with a "
            "hazard ratio of 0.74 (95% CI, 0.58 to 0.95) after 3 years."
        ),
    }
    atoms = extract_atoms_from_evidence(ev_ci)
    values = {a.value for a in atoms}
    # 0.58 and 0.95 are CI bounds, NOT outcome values
    assert "0.58" not in values, f"CI lower bound leaked as value: {values}"
    assert "0.95" not in values, f"CI upper bound leaked as value: {values}"
    # 3 (years) is a timepoint, NOT a value
    assert "3" not in values, f"Timepoint year leaked as value: {values}"
    # 0.74 (the HR) IS a valid outcome — should be present
    assert "0.74" in values, f"HR=0.74 should be in atom values: {values}"


def test_p1_1_percent_unit_extracted_without_word_boundary():
    """Codex iter-1 P1 #1: '%' was missed because of word-boundary
    requirement. '43%' must produce unit '%', not 'l' or empty."""
    atoms = extract_atoms_from_evidence(_SURPASS_2_EV)
    ae_atoms = [a for a in atoms if a.value == "43"]
    assert len(ae_atoms) == 1
    assert ae_atoms[0].unit == "%", f"Expected unit='%', got '{ae_atoms[0].unit!r}'"


def test_p1_1_no_dose_unit_on_outcome_value():
    """Codex iter-1 P1 #1: HbA1c -2.24 got unit='mg' from nearby dose.
    Must NOT happen — HbA1c unit should be 'percentage points'."""
    atoms = extract_atoms_from_evidence(_SURPASS_2_EV)
    hba1c_atoms = [a for a in atoms if a.endpoint == "HbA1c"]
    for a in hba1c_atoms:
        assert a.unit != "mg", (
            f"HbA1c atom {a.atom_id} got unit='mg' (dose unit leaked): {a}"
        )
        assert "mg" not in a.unit, (
            f"HbA1c atom {a.atom_id} got unit containing 'mg': '{a.unit}'"
        )


def test_p1_3_arm_specific_entity_binding():
    """Codex iter-1 P1 #3: SURPASS-style sentences flipped arms
    (tirzepatide outcome was labeled entity=semaglutide). With the
    arm-local fix, the -2.30 value (tirzepatide 15 mg arm) must have
    entity containing 'tirzepatide', NOT 'semaglutide'."""
    atoms = extract_atoms_from_evidence(_SURPASS_2_EV)
    hba1c_2_30 = [a for a in atoms if a.value == "-2.30"]
    assert len(hba1c_2_30) == 1
    a = hba1c_2_30[0]
    assert "tirzepatide" in a.entity.lower(), (
        f"-2.30 should be tirzepatide arm, got entity='{a.entity}'"
    )
    # Dose should be 15 mg
    assert "15 mg" in a.entity or "15mg" in a.entity, (
        f"-2.30 should be tirzepatide 15 mg, got entity='{a.entity}'"
    )


def test_p1_3_semaglutide_value_correctly_bound():
    """Codex iter-1 P1 #3: '-1.86 percentage points with semaglutide'
    should bind entity=semaglutide, NOT entity=tirzepatide."""
    atoms = extract_atoms_from_evidence(_SURPASS_2_EV)
    sema_atom = [a for a in atoms if a.value == "-1.86"]
    assert len(sema_atom) == 1
    a = sema_atom[0]
    assert "semaglutide" in a.entity.lower(), (
        f"-1.86 with semaglutide should bind entity=semaglutide, got '{a.entity}'"
    )


def test_p1_4_decimal_not_treated_as_sentence_boundary():
    """Codex iter-1 P1 #4: literal_text expansion split decimals like
    '-2.30' mid-decimal. Verify literal_text contains the FULL decimal."""
    atoms = extract_atoms_from_evidence(_SURPASS_2_EV)
    for a in atoms:
        # The exact raw value must be a substring of literal_text
        assert a.value in a.literal_text, (
            f"Atom {a.atom_id} value='{a.value}' not in literal_text "
            f"'{a.literal_text[:100]}...'"
        )
        # literal_text must NOT end mid-decimal
        assert not a.literal_text.rstrip().endswith("-2."), (
            f"literal_text split a decimal: '{a.literal_text}'"
        )


def test_comparator_does_not_leak_across_sentences():
    """Codex iter-1 P1 #3 corollary: 'Adverse events 43%' should have
    NO comparator. Before the iter-2 fix, the comparator search used a
    300-char window which leaked 'semaglutide' from earlier HbA1c
    sentence into the AE atom."""
    atoms = extract_atoms_from_evidence(_SURPASS_2_EV)
    ae_atoms = [a for a in atoms if a.endpoint == "adverse events"]
    assert len(ae_atoms) >= 1
    for a in ae_atoms:
        assert a.comparator == "", (
            f"AE atom comparator should be empty (single-arm sentence), "
            f"got '{a.comparator}'"
        )


def test_section_tags_dynamic_dose_response():
    """Codex iter-1 P2: section_tags should add 'Dose Response' when
    the entity contains a dose-arm (e.g., 'tirzepatide 15 mg')."""
    atoms = extract_atoms_from_evidence(_SURPASS_2_EV)
    # HbA1c -2.30 has entity 'tirzepatide 15 mg' → Dose Response should be in tags
    a_230 = [a for a in atoms if a.value == "-2.30"][0]
    assert "Dose Response" in a_230.section_tags
    # AE 43% has no dose-arm → Dose Response should NOT be in tags
    a_43 = [a for a in atoms if a.value == "43"][0]
    assert "Dose Response" not in a_43.section_tags


def test_section_tags_comparative_only_when_comparator_present():
    """Codex iter-1 P2: 'Comparative' tag should be added dynamically
    based on extracted comparator, not statically per endpoint."""
    atoms = extract_atoms_from_evidence(_SURPASS_2_EV)
    # AE 43% with empty comparator → 'Comparative' should NOT be in tags
    a_43 = [a for a in atoms if a.value == "43"][0]
    assert "Comparative" not in a_43.section_tags, (
        f"AE atom shouldn't have Comparative tag without a comparator, "
        f"got tags={a_43.section_tags}"
    )
    # HbA1c -2.30 with comparator=semaglutide → 'Comparative' MUST be in tags
    a_230 = [a for a in atoms if a.value == "-2.30"][0]
    assert "Comparative" in a_230.section_tags


def test_primary_section_field_populated():
    """Codex iter-2 P2 fix: primary_section is DYNAMIC per comparator +
    dose-arm presence, not static vocab default. In SURPASS-2:
      - HbA1c -2.01/-2.24/-2.30 with comparator=semaglutide AND dose-arms
        → primary_section="Dose Response" (most specific placement).
      - HbA1c -1.86 with comparator=tirzepatide but NO dose-arm
        → primary_section="Comparative Effectiveness".
      - AE 43% with no comparator, no dose-arm → primary_section="Safety".
    Prevents same atom landing in 3 different sections.
    """
    atoms = extract_atoms_from_evidence(_SURPASS_2_EV)
    # tirzepatide arms (dose-arm + comparator) → Dose Response
    tirz_hba1c = [
        a for a in atoms
        if a.endpoint == "HbA1c"
        and "tirzepatide" in (a.entity or "").lower()
    ]
    assert len(tirz_hba1c) == 3, f"expected 3 tirz HbA1c atoms, got {len(tirz_hba1c)}"
    for a in tirz_hba1c:
        assert a.primary_section == "Dose Response", (
            f"tirz HbA1c {a.value} should be Dose Response (dose-arm + "
            f"comparator), got {a.primary_section}"
        )
    # AE 43% → Safety (no comparator suppression — Safety is vocab primary)
    ae = [a for a in atoms if a.endpoint == "adverse events"]
    for a in ae:
        assert a.primary_section == "Safety"


# ============================================================================
# ITER-3 REGRESSION TESTS (Codex iter-2 verdict → 3 P1s + 2 P2s)
# ============================================================================


def test_iter3_p1_ci_comma_form_not_emitted_as_outcome():
    """Codex iter-2 continuing-P1.2 (ci_comma_form):
    `HR 0.74 (95% CI 0.58, 0.95)` must NOT emit 0.58 / 0.95 as
    MACE/HR outcome atoms (they are CI bounds)."""
    ev = {
        "evidence_id": "ev_ci_comma",
        "tier": "T1",
        "direct_quote": (
            "In EMPA-REG OUTCOME, empagliflozin reduced MACE with a "
            "hazard ratio of 0.74 (95% CI 0.58, 0.95) after 3 years."
        ),
    }
    atoms = extract_atoms_from_evidence(ev)
    values = {a.value for a in atoms}
    assert "0.58" not in values, f"CI lower-bound leaked: {values}"
    assert "0.95" not in values, f"CI upper-bound leaked: {values}"
    # The HR value 0.74 is OK as an outcome (it's the hazard ratio itself).


def test_iter3_p1_ci_dash_range_not_emitted_as_outcome():
    """Codex iter-2 continuing-P1.2 (ci_compact_dash_range):
    `HR 0.74 (95% CI 0.58-0.95)` must NOT emit "0.58-0.95" range as
    a MACE/HR outcome atom."""
    ev = {
        "evidence_id": "ev_ci_dash",
        "tier": "T1",
        "direct_quote": (
            "In DAPA-HF, dapagliflozin reduced HF hospitalization with a "
            "hazard ratio of 0.74 (95% CI 0.58-0.95) over the follow-up."
        ),
    }
    atoms = extract_atoms_from_evidence(ev)
    values = {a.value for a in atoms}
    # The dash range should not be emitted as a value
    assert not any("0.58" in v and "0.95" in v for v in values), (
        f"CI dash-range leaked as range atom: {values}"
    )
    assert "0.58" not in values, f"CI lower-bound (split) leaked: {values}"
    assert "0.95" not in values, f"CI upper-bound (split) leaked: {values}"


def test_iter3_p1_reverse_comparator_suppressed_on_comparator_arm():
    """Codex iter-2 novel-P1 (same_sentence_comparator_arm):
    In SURPASS-2, semaglutide is the comparator arm. The -1.86 atom
    must have entity=semaglutide AND comparator="" — NOT
    comparator=tirzepatide (a reverse comparative claim)."""
    atoms = extract_atoms_from_evidence(_SURPASS_2_EV)
    sema = [a for a in atoms if a.value == "-1.86"]
    assert len(sema) == 1, f"expected 1 atom for -1.86, got {len(sema)}"
    a = sema[0]
    assert "semaglutide" in (a.entity or "").lower(), (
        f"-1.86 should bind to semaglutide arm, got entity={a.entity}"
    )
    assert a.comparator == "", (
        f"-1.86 is the comparator arm — must NOT emit comparator. "
        f"Got comparator={a.comparator!r}, which makes a reverse "
        f"comparative claim (semaglutide vs tirzepatide)."
    )


def test_iter3_p1_multi_endpoint_value_binds_to_closest_endpoint():
    """Codex iter-2 novel-P1 (multi_endpoint_sentence):
    `tirzepatide reduced HbA1c by -2.30 percentage points and body
    weight by -11.2 kg` — the -11.2 atom must bind to body weight,
    NOT HbA1c."""
    ev = {
        "evidence_id": "ev_multi_endpoint",
        "tier": "T1",
        "direct_quote": (
            "In SURPASS-3, tirzepatide reduced HbA1c by -2.30 percentage "
            "points and body weight by -11.2 kg at 52 weeks."
        ),
    }
    atoms = extract_atoms_from_evidence(ev)
    wt = [a for a in atoms if a.value == "-11.2"]
    assert len(wt) == 1, f"expected 1 atom for -11.2, got {len(wt)}"
    assert wt[0].endpoint != "HbA1c", (
        f"-11.2 kg must NOT bind to HbA1c (false atom). "
        f"Got endpoint={wt[0].endpoint!r}"
    )
    assert "weight" in wt[0].endpoint.lower(), (
        f"-11.2 kg should bind to body weight, got {wt[0].endpoint!r}"
    )


def test_iter3_p2_dose_unit_does_not_preempt_lab_unit():
    """Codex iter-2 P2 (dose_classifier_preempts_compound_lab_units):
    `LDL-C dropped to 90 mg/dL` — the 90 must be classified as
    OUTCOME with unit `mg/dL`, NOT DOSE with unit `mg` (which would
    skip the atom entirely as a non-OUTCOME role)."""
    ev = {
        "evidence_id": "ev_ldl",
        "tier": "T1",
        "direct_quote": (
            "In JUPITER, rosuvastatin reduced LDL-C from 130 to 90 mg/dL "
            "at 12 months in the high-risk arm."
        ),
    }
    atoms = extract_atoms_from_evidence(ev)
    values = {a.value: a for a in atoms}
    assert "90" in values, (
        f"90 mg/dL should be extracted as OUTCOME (not skipped as DOSE). "
        f"Got values={list(values.keys())}"
    )
    a90 = values["90"]
    assert "mg/dl" in a90.unit.lower() or "mg/dL" == a90.unit, (
        f"90 should have unit mg/dL, got unit={a90.unit!r}"
    )


def test_iter4_p1_ci_non_parenthesized_comma_form_caught():
    """Codex iter-3 continuing-P1: non-parenthesized CI forms still leak.
    `HR 0.74, 95% CI 0.58, 0.95` must NOT emit 0.58/0.95 as outcomes."""
    ev = {
        "evidence_id": "ev_ci_unparen_comma",
        "tier": "T1",
        "direct_quote": (
            "empagliflozin reduced MACE with HR 0.74, 95% CI 0.58, 0.95 "
            "after 3 years."
        ),
    }
    atoms = extract_atoms_from_evidence(ev)
    values = {a.value for a in atoms}
    assert "0.58" not in values, f"Non-parenthesized CI lower-bound leaked: {values}"
    assert "0.95" not in values, f"Non-parenthesized CI upper-bound leaked: {values}"


def test_iter4_p1_ci_non_parenthesized_dash_range_caught():
    """Codex iter-3 continuing-P1: non-parenthesized compact dash range.
    `HR 0.74, 95% CI 0.58-0.95` must NOT emit `0.58-0.95` or split bounds."""
    ev = {
        "evidence_id": "ev_ci_unparen_dash",
        "tier": "T1",
        "direct_quote": (
            "dapagliflozin reduced HF hospitalization with HR 0.74, 95% CI "
            "0.58-0.95 in the trial."
        ),
    }
    atoms = extract_atoms_from_evidence(ev)
    values = {a.value for a in atoms}
    # Neither the range nor split bounds should be outcome values
    assert not any("0.58" in v for v in values), f"CI bound leaked: {values}"
    assert not any("0.95" in v for v in values), f"CI bound leaked: {values}"


def test_iter4_p1_left_side_comparator_arm_entity_binding():
    """Codex iter-3 continuing-P1: comparator-arm drug LEFT of value.
    `tirzepatide reduced HbA1c by -2.30 ... versus semaglutide, which
    reduced HbA1c by -1.86` — -1.86 must bind to semaglutide (closest
    drug on left), not tirzepatide (first drug in sentence)."""
    ev = {
        "evidence_id": "ev_left_comparator",
        "tier": "T1",
        "direct_quote": (
            "In SURPASS-2, tirzepatide reduced HbA1c by -2.30 percentage "
            "points versus semaglutide, which reduced HbA1c by -1.86 "
            "percentage points."
        ),
    }
    atoms = extract_atoms_from_evidence(ev)
    sema_atom = [a for a in atoms if a.value == "-1.86"]
    assert len(sema_atom) == 1, f"expected 1 atom for -1.86, got {len(sema_atom)}"
    a = sema_atom[0]
    assert "semaglutide" in (a.entity or "").lower(), (
        f"-1.86 must bind to semaglutide (closest left drug), got "
        f"entity={a.entity!r}. This was a P1 false attribution: emitting "
        f"comparator=semaglutide entity=tirzepatide makes a wrong comparative claim."
    )


def test_iter4_p1_coordinated_endpoint_list_skipped_when_ambiguous():
    """Codex iter-3 continuing-P1: `HbA1c and body weight reductions
    were -2.30 percentage points and -11.2 kg` — both endpoints + both
    values in coordinate lists. Binding by closest-left picks WRONG.
    Acceptable behavior: skip atoms rather than emit false bindings."""
    ev = {
        "evidence_id": "ev_coord_endpoints",
        "tier": "T1",
        "direct_quote": (
            "In SURPASS-3, HbA1c and body weight reductions were "
            "-2.30 percentage points and -11.2 kg at 52 weeks."
        ),
    }
    atoms = extract_atoms_from_evidence(ev)
    # -2.30 must NOT be emitted as endpoint=body_weight (would be a FALSE
    # claim). Either skip the atom entirely, OR (less safe) emit it
    # bound to HbA1c. The iter-4 fix prefers skip on ambiguity.
    bad_atoms = [
        a for a in atoms
        if a.value == "-2.30"
        and "weight" in a.endpoint.lower()
    ]
    assert len(bad_atoms) == 0, (
        f"-2.30 percentage points was bound to body weight (false claim). "
        f"On ambiguous coordinated endpoint lists, atoms must be skipped."
    )


def test_iter4_p2_dose_arm_alone_routes_to_dose_response():
    """Codex iter-3 P2: dose-arm WITHOUT comparator should still primary
    to Dose Response. Single-arm dose study atoms must not be excluded
    from the Dose Response section."""
    ev = {
        "evidence_id": "ev_single_arm_dose",
        "tier": "T1",
        "direct_quote": (
            "In the open-label phase 2 study, tirzepatide 15 mg reduced "
            "HbA1c by -2.20 percentage points at 26 weeks."
        ),
    }
    atoms = extract_atoms_from_evidence(ev)
    a = [a for a in atoms if a.value == "-2.20"]
    assert len(a) == 1
    assert a[0].primary_section == "Dose Response", (
        f"dose-arm-only HbA1c atom should primary to Dose Response, "
        f"got {a[0].primary_section!r}"
    )


def test_iter4_p2_comparator_does_not_move_safety_atoms():
    """Codex iter-3 P2: comparator should not automatically move
    safety/mechanism atoms OUT of Safety/Mechanism. Only Efficacy /
    Comparative Effectiveness primary atoms can be re-routed by
    comparator presence."""
    ev = {
        "evidence_id": "ev_safety_comparator",
        "tier": "T1",
        "direct_quote": (
            "Adverse events occurred in 45% of tirzepatide patients "
            "versus 38% of semaglutide patients."
        ),
    }
    atoms = extract_atoms_from_evidence(ev)
    ae = [a for a in atoms if a.endpoint == "adverse events"]
    for a in ae:
        assert a.primary_section == "Safety", (
            f"AE atom with comparator must stay in Safety (vocab primary), "
            f"got {a.primary_section!r}"
        )


def test_iter3_p2_filter_by_primary_section_excludes_secondary_tags():
    """Codex iter-2 P2 (primary_section_not_enforced):
    filter_atoms_for_section now returns atoms whose PRIMARY section
    matches — atoms tagged with the section in section_tags but where
    primary_section != section_title are EXCLUDED. Prevents same atom
    landing in 3 sections."""
    atoms = extract_atoms_from_evidence(_SURPASS_2_EV)
    catalog = {a.atom_id: a for a in atoms}

    # tirz HbA1c atoms have primary=Dose Response. They should:
    #   appear in filter("Dose Response")
    #   NOT appear in filter("Efficacy") even though section_tags
    #     includes "Efficacy" too.
    dose_resp = filter_atoms_for_section(catalog, "Dose Response")
    efficacy = filter_atoms_for_section(catalog, "Efficacy")

    tirz_atoms = [
        a for a in atoms
        if a.endpoint == "HbA1c"
        and "tirzepatide" in (a.entity or "").lower()
    ]
    assert len(tirz_atoms) > 0
    for a in tirz_atoms:
        assert a.atom_id in dose_resp, (
            f"tirz atom {a.atom_id} (primary=Dose Response) missing "
            f"from Dose Response filter"
        )
        assert a.atom_id not in efficacy, (
            f"tirz atom {a.atom_id} (primary=Dose Response) leaked "
            f"into Efficacy filter — should be SINGLE PLACEMENT only"
        )
