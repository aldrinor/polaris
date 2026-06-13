"""Wave-3 (I-arch-002 [1]+[2]) positive-known discriminator tests.

Covers checklist steps P1.1 (the 6 new ExtractedNumericClaim discriminator
fields; arm stays the legacy "treatment" default for OFF byte-identity per Codex
Slice-B P1 — a defaulted "treatment" is still treated as UNKNOWN by
claim_graph._unknown_arm so the merge key stays fail-closed flag-ON) and P1.2
(the positive-known extractors + mg/kg dose preservation + day/year endpoint
patterns).

These assert the EXTRACTOR layer only — they prove each discriminator yields a
DISTINCT positive-known value for the two §8 no-merge cases, and the UNKNOWN ''
sentinel when no positive token is present. The actual no-merge decision is made
by claim_graph.build_merge_key (checklist step [6], not yet built); these tests
deliberately do NOT import claim_graph. A spec slot whose value_getter targets
one of these fields will then key on the distinct values proven here.

HARD-RULE coverage:
  - flag OFF => _extract_dose byte-identical to the legacy behaviour (mg/kg path
    is gated behind PG_SWEEP_CREDIBILITY_REDESIGN).
  - the 6 new fields are additive '' = UNKNOWN sentinels; arm keeps the legacy
    "treatment" default (OFF byte-identity).
"""
from __future__ import annotations

import dataclasses

import pytest

from src.polaris_graph.retrieval.contradiction_detector import (
    ExtractedNumericClaim,
    _extract_comparator,
    _extract_direction,
    _extract_dose,
    _extract_dose_frequency,
    _extract_effect_measure,
    _extract_endpoint_phrase,
    _extract_population,
    _extract_route_formulation,
    extract_numeric_claims,
)


# ─────────────────────────────────────────────────────────────────────────────
# P1.1 — dataclass shape: 6 new fields, '' = UNKNOWN sentinel, arm = legacy "treatment"
# ─────────────────────────────────────────────────────────────────────────────


def test_p1_1_new_discriminator_fields_default_unknown_sentinel() -> None:
    claim = ExtractedNumericClaim(
        evidence_id="ev",
        subject="drug",
        predicate="weight loss",
        value=10.0,
        unit="%",
        context_snippet="ctx",
    )
    # All 6 new fields default to the '' UNKNOWN sentinel.
    assert claim.dose_frequency == ""
    assert claim.comparator == ""
    assert claim.route_formulation == ""
    assert claim.effect_measure == ""
    assert claim.direction == ""
    assert claim.population == ""


def test_p1_1_arm_default_is_legacy_treatment_not_none() -> None:
    # OFF byte-identity (Codex Slice-B P1): the dataclass default stays the
    # LEGACY "treatment" string, NOT None — the OFF-path cluster key
    # (_normalized_key_numeric:241) and contradictions.json asdict both read
    # this field, so a None default would drift OFF cluster ids + bytes. A
    # DEFAULTED "treatment" is still treated as UNKNOWN by claim_graph._unknown_arm
    # (flag-ON), so consolidation stays fail-closed without the None change.
    claim = ExtractedNumericClaim(
        evidence_id="ev",
        subject="drug",
        predicate="weight loss",
        value=10.0,
        unit="%",
        context_snippet="ctx",
    )
    assert claim.arm == "treatment"


def test_p1_1_field_names_present_on_dataclass() -> None:
    names = {f.name for f in dataclasses.fields(ExtractedNumericClaim)}
    for required in (
        "dose_frequency",
        "comparator",
        "route_formulation",
        "effect_measure",
        "direction",
        "population",
    ):
        assert required in names, f"missing discriminator field {required!r}"


def test_p1_1_arm_legacy_treatment_on_no_placebo_cue_via_extractor() -> None:
    # §8 #8: no placebo/comparator cue -> arm stays the LEGACY "treatment" string
    # on the live path (OFF byte-identity, Codex Slice-B P1). claim_graph._unknown_arm
    # treats "treatment" as UNKNOWN, so the merge key still singletons it flag-ON.
    evidence = [{
        "evidence_id": "ev1",
        "direct_quote": "Semaglutide 2.4 mg achieved 14.9% weight loss at week 68.",
        "tier": "T1",
        "source_url": "https://example.com/",
    }]
    claims = extract_numeric_claims(evidence)
    assert len(claims) == 1
    assert claims[0].arm == "treatment"


# ─────────────────────────────────────────────────────────────────────────────
# P1.2 — DRIFT-MGKG: mg/kg dose preservation gated behind the master flag
# ─────────────────────────────────────────────────────────────────────────────


def test_p1_2_dose_mgkg_off_byte_identical(monkeypatch: pytest.MonkeyPatch) -> None:
    # Flag OFF: the legacy regex path runs verbatim; '5 mg/kg' degrades to
    # '5 mg' exactly as it does in the current tree (byte-identity anchor).
    monkeypatch.delenv("PG_SWEEP_CREDIBILITY_REDESIGN", raising=False)
    assert _extract_dose("dosed at 5 mg/kg daily") == "5 mg"
    assert _extract_dose("dosed at 5 mg daily") == "5 mg"


def test_p1_2_dose_mgkg_off_explicit_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    # An explicit =0 is also OFF (mirrors credibility_pass._OFF_VALUES).
    monkeypatch.setenv("PG_SWEEP_CREDIBILITY_REDESIGN", "0")
    assert _extract_dose("dosed at 5 mg/kg daily") == "5 mg"


def test_p1_2_test7_mgkg_vs_mg_distinct_when_flag_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # §8 #7: "5 mg/kg" vs "5 mg" -> distinct dose discriminator values when ON,
    # so build_merge_key (step [6]) keys them separately => no merge.
    monkeypatch.setenv("PG_SWEEP_CREDIBILITY_REDESIGN", "1")
    mgkg = _extract_dose("dosed at 5 mg/kg daily")
    mg = _extract_dose("dosed at 5 mg daily")
    assert mgkg == "5 mg/kg"
    assert mg == "5 mg"
    assert mgkg != mg


def test_p1_2_test6_distinct_doses_distinct_values() -> None:
    # §8 #6: distinct doses (2.4 mg vs 7.2 mg) -> distinct dose values, with
    # dose-unknown both -> '' (UNKNOWN) so build_merge_key keeps them separate.
    assert _extract_dose("semaglutide 2.4 mg") == "2.4 mg"
    assert _extract_dose("semaglutide 7.2 mg") == "7.2 mg"
    assert _extract_dose("semaglutide weight loss reported") == ""
    assert _extract_dose("semaglutide 2.4 mg") != _extract_dose("semaglutide 7.2 mg")


# ─────────────────────────────────────────────────────────────────────────────
# P1.2 — #19 dose_frequency (weekly vs daily — the ISMP methotrexate sentinel)
# ─────────────────────────────────────────────────────────────────────────────


def test_p1_2_test19_dose_frequency_weekly_vs_daily_distinct() -> None:
    weekly = _extract_dose_frequency("methotrexate 15 mg weekly")
    daily = _extract_dose_frequency("methotrexate 15 mg daily")
    assert weekly == "weekly"
    assert daily == "daily"
    assert weekly != daily


def test_p1_2_dose_frequency_abbreviations_normalize() -> None:
    assert _extract_dose_frequency("given b.i.d.") == "bid"
    assert _extract_dose_frequency("given twice daily") == "bid"
    assert _extract_dose_frequency("given once daily") == "qd"
    assert _extract_dose_frequency("administered q8h") == "q8h"


def test_p1_2_dose_frequency_unknown_when_no_cadence_token() -> None:
    assert _extract_dose_frequency("a single 15 mg dose") == ""
    assert _extract_dose_frequency("") == ""


# ─────────────────────────────────────────────────────────────────────────────
# P1.2 — #9 effect_measure (relative vs absolute risk reduction)
# ─────────────────────────────────────────────────────────────────────────────


def test_p1_2_test9_effect_measure_relative_vs_absolute_distinct() -> None:
    rel = _extract_effect_measure("30% relative risk reduction")
    absol = _extract_effect_measure("30% absolute risk reduction")
    assert rel == "relative"
    assert absol == "absolute"
    assert rel != absol


def test_p1_2_effect_measure_hr_or_and_unknown() -> None:
    assert _extract_effect_measure("hazard ratio of 0.70") == "hr"
    assert _extract_effect_measure("odds ratio of 1.2") == "or"
    # No explicit measure word -> UNKNOWN (never inferred).
    assert _extract_effect_measure("30% weight loss at week 68") == ""


# ─────────────────────────────────────────────────────────────────────────────
# P1.2 — #17 route_formulation (IV vs PO)
# ─────────────────────────────────────────────────────────────────────────────


def test_p1_2_test17_route_iv_vs_po_distinct() -> None:
    iv = _extract_route_formulation("1000 mg IV")
    po = _extract_route_formulation("1000 mg PO")
    assert iv == "iv"
    assert po == "po"
    assert iv != po


def test_p1_2_route_spelled_out_and_unknown() -> None:
    assert _extract_route_formulation("administered orally") == "po"
    assert _extract_route_formulation("given subcutaneously") == "sc"
    assert _extract_route_formulation("extended-release tablet") == "er"
    assert _extract_route_formulation("1000 mg dose") == ""


# ─────────────────────────────────────────────────────────────────────────────
# P1.2 — #5 direction TOKEN-ONLY (rose vs fell)
# ─────────────────────────────────────────────────────────────────────────────


def test_p1_2_test5_direction_token_only_rose_vs_fell() -> None:
    up = _extract_direction("stroke rate rose 5%")
    down = _extract_direction("stroke rate fell 5%")
    assert up == "increase"
    assert down == "decrease"
    assert up != down


def test_p1_2_direction_unknown_when_no_token_or_ambiguous() -> None:
    # No direction token -> UNKNOWN (never predicate-derived, design §4.3).
    assert _extract_direction("stroke rate was 5%") == ""
    # Conflicting tokens -> ambiguous -> UNKNOWN (fail-closed / keep separate).
    assert _extract_direction("rose initially then fell") == ""


# ─────────────────────────────────────────────────────────────────────────────
# P1.2 — comparator + population extractors
# ─────────────────────────────────────────────────────────────────────────────


def test_p1_2_comparator_extracts_vs_phrase() -> None:
    assert _extract_comparator("achieved 25% vs placebo") == "placebo"
    assert _extract_comparator("compared to standard care, 12%") == "standard care"
    assert _extract_comparator("14.9% weight loss at week 68") == ""


def test_p1_2_population_extracts_cohort_phrase() -> None:
    assert (
        _extract_population("in patients with type 2 diabetes achieved 14%")
        == "patients with type 2 diabetes"
    )
    assert _extract_population("among participants with heart failure") == (
        "participants with heart failure"
    )
    assert _extract_population("weight loss of 14.9% was reported") == ""


# ─────────────────────────────────────────────────────────────────────────────
# P1.2 — day/year endpoint patterns (additive to _extract_endpoint_phrase)
# ─────────────────────────────────────────────────────────────────────────────


def test_p1_2_endpoint_day_year_patterns(monkeypatch) -> None:
    # Day/year forms are GATED behind PG_SWEEP_CREDIBILITY_REDESIGN (Claude Slice-B
    # iter-2 P1) — they only fire when the redesign is ON.
    monkeypatch.setenv("PG_SWEEP_CREDIBILITY_REDESIGN", "1")
    assert _extract_endpoint_phrase("response measured at day 28") == "at day 28"
    assert _extract_endpoint_phrase("response at 90 days") == "at 90 days"
    assert _extract_endpoint_phrase("survival at year 1") == "at year 1"
    assert _extract_endpoint_phrase("survival at 2 years") == "at 2 years"


def test_p1_2_endpoint_day_year_gated_off_is_empty(monkeypatch) -> None:
    # OFF byte-identity (Claude Slice-B iter-2 P1): a day/year-only phrase that the
    # legacy tree returned "" for MUST still return "" with the flag OFF (endpoint_phrase
    # feeds the legacy cluster key + contradictions.json, so a non-"" OFF value drifts).
    monkeypatch.delenv("PG_SWEEP_CREDIBILITY_REDESIGN", raising=False)
    assert _extract_endpoint_phrase("response measured at day 28") == ""
    assert _extract_endpoint_phrase("survival at 2 years") == ""


def test_p1_2_endpoint_existing_week_month_unchanged(monkeypatch) -> None:
    # Additive: existing week/month extraction is byte-unchanged REGARDLESS of the flag.
    for flag in ("0", "1"):
        monkeypatch.setenv("PG_SWEEP_CREDIBILITY_REDESIGN", flag)
        assert _extract_endpoint_phrase("weight loss at week 68") == "at week 68"
        assert _extract_endpoint_phrase("change at month 6") == "at month 6"
        assert _extract_endpoint_phrase("no endpoint here") == ""


def test_p1_2_endpoint_day_year_do_not_override_existing_patterns() -> None:
    # Byte-identity guard: the day/year patterns are placed LAST, so a phrase
    # that ALSO matches an existing pattern keeps the legacy result. Pre-change
    # these returned "from baseline" / "mean change"; the new patterns must not
    # steal precedence.
    assert _extract_endpoint_phrase("change from baseline at day 28") == "from baseline"
    assert _extract_endpoint_phrase("mean change at day 28") == "mean change"


# ─────────────────────────────────────────────────────────────────────────────
# Live path: extractors wired into the constructor (dormant carriers populated)
# ─────────────────────────────────────────────────────────────────────────────


def test_p1_2_extractors_wired_into_claim_construction() -> None:
    evidence = [{
        "evidence_id": "ev1",
        "direct_quote": (
            "In patients with type 2 diabetes, tirzepatide 15 mg weekly achieved "
            "a 30% relative risk reduction at year 1."
        ),
        "tier": "T1",
        "source_url": "https://example.com/",
    }]
    claims = extract_numeric_claims(evidence)
    assert len(claims) == 1
    c = claims[0]
    # The positive-known discriminators were populated from the text.
    assert c.dose_frequency == "weekly"
    assert c.effect_measure == "relative"
    assert c.population.startswith("patients with type 2 diabetes")
    # No placebo cue -> arm stays the legacy "treatment" (OFF byte-identity);
    # claim_graph._unknown_arm treats it as UNKNOWN so the merge key still singletons.
    assert c.arm == "treatment"


# ─────────────────────────────────────────────────────────────────────────────
# Fix C — serialize_contradiction_record gates the 6 dormant fields OFF (byte-identity)
# ─────────────────────────────────────────────────────────────────────────────


def _one_record():
    from src.polaris_graph.retrieval.contradiction_detector import (
        ContradictionRecord, ExtractedNumericClaim,
    )
    c = ExtractedNumericClaim(
        evidence_id="E1", subject="semaglutide", predicate="weight loss",
        value=15.0, unit="%", context_snippet="ctx",
        dose_frequency="weekly", comparator="placebo", route_formulation="sc",
        effect_measure="relative", direction="decrease",
        population="patients with renal impairment")
    return ContradictionRecord(subject="semaglutide", predicate="weight loss", claims=[c],
                               relative_difference=0.2, absolute_difference=3.0, severity="medium")


def test_fixc_serialize_strips_wave3_fields_when_off(monkeypatch) -> None:
    from src.polaris_graph.retrieval.contradiction_detector import (
        serialize_contradiction_record, _WAVE3_DORMANT_NUMERIC_FIELDS,
    )
    monkeypatch.delenv("PG_SWEEP_CREDIBILITY_REDESIGN", raising=False)
    d = serialize_contradiction_record(_one_record())
    keys = set(d["claims"][0].keys())
    # NONE of the 6 dormant fields may appear on the OFF path (legacy JSON had no such keys).
    assert not (set(_WAVE3_DORMANT_NUMERIC_FIELDS) & keys), keys
    # pre-existing fields are always retained.
    assert "endpoint_phrase" in keys and "arm" in keys and "dose" in keys


def test_fixc_serialize_includes_wave3_fields_when_on(monkeypatch) -> None:
    from src.polaris_graph.retrieval.contradiction_detector import (
        serialize_contradiction_record, _WAVE3_DORMANT_NUMERIC_FIELDS,
    )
    monkeypatch.setenv("PG_SWEEP_CREDIBILITY_REDESIGN", "1")
    d = serialize_contradiction_record(_one_record())
    keys = set(d["claims"][0].keys())
    # ON path carries the full discriminator set (the redesign is the new behavior).
    assert set(_WAVE3_DORMANT_NUMERIC_FIELDS) <= keys, keys
    assert d["claims"][0]["population"] == "patients with renal impairment"
