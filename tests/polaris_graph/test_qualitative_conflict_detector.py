"""Qualitative present-vs-absent clinical-safety conflict detector (I-meta-002-q1d #944).

NO network / NO model / NO spend — pure rule-cue. Every test asserts a Codex brief-gate required
behavior: pseudo-negation/statistical false-positive suppression, antonym/variant false-negative
recall, concept-type+subject+object+condition keying, source-distinctness, permissive-vs-hedge `may`,
fail-safe-to-review (never silent), finite-float encoding, and loader-schema round-trip.

Drugs are drawn from the GLP-1 allowlist (`scope_gate._DRUG_NAME_RE`) the detector reuses for subject
extraction — the actual golden-benchmark domain. (Generalizing the drug lexicon beyond GLP-1 is the
named follow-up #qual-drug-lexicon.)
"""

from __future__ import annotations

import json

import pytest

import src.polaris_graph.retrieval.qualitative_conflict_detector as qcd
from src.polaris_graph.retrieval.qualitative_conflict_detector import (
    ABSENT,
    INDETERMINATE,
    PRESENT,
    STATISTICAL_NULL,
    detect_qualitative_conflicts,
    extract_qualitative_assertions,
)


def _ev(eid: str, quote: str, url: str, tier: str = "T1") -> dict:
    return {"evidence_id": eid, "direct_quote": quote, "source_url": url, "tier": tier}


def _statuses(quote: str) -> list[str]:
    rows = extract_qualitative_assertions([_ev("ev_000", quote, "https://x")])
    return [a.assertion_status for a in rows]


def _severities(records) -> list[str]:
    return sorted(r.severity for r in records)


# ── RECALL (must fire / must NOT be silent) ──────────────────────────────────────────────────────
def test_antonym_present_vs_absent_no_negation_token_hard_conflict():
    """The lethal false-negative: a disagreement carrying NO 'no/not' token and NO number."""
    records = detect_qualitative_conflicts(extract_qualitative_assertions([
        _ev("ev_000", "Semaglutide is contraindicated in pregnancy.", "https://a"),
        _ev("ev_001", "Semaglutide is safe in pregnancy.", "https://b"),
    ]))
    high = [r for r in records if r.severity == "high"]
    assert len(high) == 1
    assert high[0].subject == "semaglutide"
    assert "contraindication" in high[0].predicate


def test_permissive_ddi_vs_avoid_hard_conflict_not_downgraded():
    """`may be co-administered` is deontic permission (ABSENT), must hard-fire vs `avoid` — NOT
    downgraded to review by the generic hedge rule (Codex brief-gate iter-2 P1.a)."""
    records = detect_qualitative_conflicts(extract_qualitative_assertions([
        _ev("ev_000", "Avoid metformin with semaglutide.", "https://a"),
        _ev("ev_001", "Metformin may be co-administered with semaglutide.", "https://b"),
    ]))
    assert any(r.severity == "high" for r in records)


def test_ae_causation_did_not_lead_vs_leading_cause_hard_conflict():
    """The exact 2026-05-26 real-smoke miss (feedback_qualitative_negation_escapes_regex)."""
    records = detect_qualitative_conflicts(extract_qualitative_assertions([
        _ev("ev_000", "With semaglutide, constipation did not lead to discontinuation.", "https://a"),
        _ev("ev_001", "Semaglutide constipation was a leading cause of discontinuation.", "https://b"),
    ]))
    assert any(r.severity == "high" for r in records)


# ── PRECISION (must NOT hard-fire) ───────────────────────────────────────────────────────────────
def test_statistical_null_not_a_hard_conflict_is_review():
    """'not associated with an increased risk' is a STATISTICAL statement, not an ABSENT assertion —
    must NOT manufacture a phantom hard conflict; surfaced as review instead."""
    records = detect_qualitative_conflicts(extract_qualitative_assertions([
        _ev("ev_000", "Tirzepatide was not associated with an increased risk of pancreatitis.", "https://a"),
        _ev("ev_001", "Tirzepatide is associated with pancreatitis.", "https://b"),
    ]))
    assert not any(r.severity == "high" for r in records)
    assert any(r.severity == "review" for r in records)
    assert STATISTICAL_NULL in _statuses(
        "Tirzepatide was not associated with an increased risk of pancreatitis."
    )


def test_different_subject_no_conflict():
    records = detect_qualitative_conflicts(extract_qualitative_assertions([
        _ev("ev_000", "Metformin is contraindicated in pregnancy.", "https://a"),
        _ev("ev_001", "Empagliflozin is safe in pregnancy.", "https://b"),
    ]))
    assert records == []


def test_different_concept_type_no_conflict():
    records = detect_qualitative_conflicts(extract_qualitative_assertions([
        _ev("ev_000", "Semaglutide causes nausea.", "https://a"),
        _ev("ev_001", "Semaglutide is not contraindicated in renal impairment.", "https://b"),
    ]))
    assert not any(r.severity == "high" for r in records)


def test_condition_stratified_is_review_not_hard_conflict():
    """contraindicated in renal impairment vs not contraindicated in normal renal function are
    COMPLEMENTARY, not contradictory — review, never a hard conflict (red-team textbook case)."""
    records = detect_qualitative_conflicts(extract_qualitative_assertions([
        _ev("ev_000", "Metformin is contraindicated in renal impairment.", "https://a"),
        _ev("ev_001", "Metformin is not contraindicated in normal renal function.", "https://b"),
    ]))
    assert not any(r.severity == "high" for r in records)
    assert any(r.severity == "review" for r in records)


def test_double_negation_agrees_no_conflict():
    records = detect_qualitative_conflicts(extract_qualitative_assertions([
        _ev("ev_000", "Semaglutide is not non-contraindicated in pregnancy.", "https://a"),
        _ev("ev_001", "Semaglutide is contraindicated in pregnancy.", "https://b"),
    ]))
    assert records == []


def test_same_source_both_ways_no_cross_source_conflict():
    records = detect_qualitative_conflicts(extract_qualitative_assertions([
        _ev("ev_000", "Semaglutide is contraindicated in pregnancy.", "https://same"),
        _ev("ev_001", "Semaglutide is safe in pregnancy.", "https://same"),
    ]))
    assert records == []


# ── status resolution (permissive vs hedge; uncertainty) ─────────────────────────────────────────
def test_permissive_may_is_absent_definite():
    assert ABSENT in _statuses("Metformin may be co-administered with semaglutide.")


def test_epistemic_may_is_indeterminate():
    assert _statuses("Semaglutide may be contraindicated in renal impairment.") == [INDETERMINATE]


def test_uncertainty_cannot_be_excluded_is_indeterminate_and_reviewed_not_dropped():
    records = detect_qualitative_conflicts(extract_qualitative_assertions([
        _ev("ev_000", "Tirzepatide-induced pancreatitis cannot be excluded.", "https://a"),
        _ev("ev_001", "Tirzepatide causes pancreatitis.", "https://b"),
    ]))
    assert any(r.severity == "review" for r in records)
    assert not any(r.severity == "high" for r in records)


# ── object_slot fail-safe (Codex iter-2 P1.b) ────────────────────────────────────────────────────
def test_missing_object_slot_routes_to_review_not_dropped():
    records = detect_qualitative_conflicts(extract_qualitative_assertions([
        _ev("ev_000", "Avoid metformin.", "https://a"),  # no co-drug -> object_slot ""
        _ev("ev_001", "Metformin may be co-administered with semaglutide.", "https://b"),
    ]))
    assert any(r.severity == "review" for r in records)


def test_determinable_different_object_slot_no_flag():
    records = detect_qualitative_conflicts(extract_qualitative_assertions([
        _ev("ev_000", "Avoid tirzepatide with semaglutide.", "https://a"),
        _ev("ev_001", "Tirzepatide may be co-administered with metformin.", "https://b"),
    ]))
    assert records == []


def test_coarse_group_with_hard_conflict_still_emits_review_for_extra_evidence():
    """Pass B must not skip a coarse group that already has a hard conflict (Codex iter-2 P2.a)."""
    records = detect_qualitative_conflicts(extract_qualitative_assertions([
        _ev("ev_000", "Semaglutide is contraindicated in pregnancy.", "https://a"),
        _ev("ev_001", "Semaglutide is safe in pregnancy.", "https://b"),
        _ev("ev_002", "Semaglutide contraindication in pregnancy cannot be excluded.", "https://c"),
    ]))
    sev = _severities(records)
    assert "high" in sev
    assert "review" in sev


def test_unresolved_owner_both_sides_is_review_not_hard():
    """Codex diff-gate iter-1 P1.1: a full-key group whose OWNER slot is unresolved on both sides
    (DDI with no co-drug) must NOT hard-fire — it routes to review."""
    records = detect_qualitative_conflicts(extract_qualitative_assertions([
        _ev("ev_000", "Avoid metformin.", "https://a"),            # DDI present, co-drug unresolved
        _ev("ev_001", "Metformin may be co-administered.", "https://b"),  # DDI absent, co-drug unresolved
    ]))
    assert not any(r.severity == "high" for r in records)
    assert any(r.severity == "review" for r in records)


def test_hard_conflict_one_scope_does_not_suppress_review_another_scope_same_sources():
    """Codex diff-gate iter-1 P1.2: a pregnancy hard conflict between sources A/B must NOT suppress
    a DIFFERENT-scope (renal) review between the same A/B sources."""
    records = detect_qualitative_conflicts(extract_qualitative_assertions([
        _ev("ev_000", "Semaglutide is contraindicated in pregnancy.", "https://a"),
        _ev("ev_001", "Semaglutide is safe in pregnancy.", "https://b"),
        _ev("ev_002", "Semaglutide is contraindicated in renal impairment.", "https://a"),
        _ev("ev_003", "Semaglutide is not contraindicated in normal renal function.", "https://b"),
    ]))
    assert any(r.severity == "high" for r in records)    # pregnancy hard conflict
    assert any(r.severity == "review" for r in records)  # renal scope-stratified review NOT suppressed


def test_cross_clause_cue_does_not_leak():
    """Codex diff-gate iter-1 P1.3: a permissive DDI cue in one clause must NOT flip the
    contraindication assertion in a different clause to ABSENT."""
    rows = extract_qualitative_assertions([
        _ev("ev_000",
            "Semaglutide may be co-administered with metformin, but is contraindicated in pregnancy.",
            "https://a"),
    ])
    contra = [a for a in rows if a.concept_type == "contraindication"]
    assert contra and all(a.assertion_status == PRESENT for a in contra)
    # and end-to-end it still hard-fires vs a "safe in pregnancy" source
    records = detect_qualitative_conflicts(extract_qualitative_assertions([
        _ev("ev_000",
            "Semaglutide may be co-administered with metformin, but is contraindicated in pregnancy.",
            "https://a"),
        _ev("ev_001", "Semaglutide is safe in pregnancy.", "https://b"),
    ]))
    assert any(r.severity == "high" for r in records)


def test_coordinated_and_cue_does_not_leak_across_concept():
    """Codex diff-gate iter-2 P1.a: a permissive DDI cue earlier in an UNSPLIT 'and' clause must NOT
    flip a later contraindication to ABSENT — high-precedence cues are concept-local-windowed."""
    rows = extract_qualitative_assertions([
        _ev("ev_000",
            "Semaglutide may be co-administered with metformin and is contraindicated in pregnancy.",
            "https://a"),
    ])
    contra = [a for a in rows if a.concept_type == "contraindication"]
    assert contra and all(a.assertion_status == PRESENT for a in contra)
    records = detect_qualitative_conflicts(extract_qualitative_assertions([
        _ev("ev_000",
            "Semaglutide may be co-administered with metformin and is contraindicated in pregnancy.",
            "https://a"),
        _ev("ev_001", "Semaglutide is safe in pregnancy.", "https://b"),
    ]))
    assert any(r.severity == "high" for r in records)


def test_coordinated_and_cue_does_not_leak_reverse_order():
    """Codex diff-gate iter-3 P1: a permissive DDI cue that FOLLOWS the contraindication across an
    'and' must NOT flip it to ABSENT (the reverse-order coordination leak)."""
    rows = extract_qualitative_assertions([
        _ev("ev_000",
            "Semaglutide is contraindicated in pregnancy and may be co-administered with metformin.",
            "https://a"),
    ])
    contra = [a for a in rows if a.concept_type == "contraindication"]
    assert contra and all(a.assertion_status == PRESENT for a in contra)
    # the DDI permissive in the SAME sentence is still its own ABSENT assertion (not lost)
    ddi = [a for a in rows if a.concept_type == "drug_interaction"]
    assert ddi and all(a.assertion_status == ABSENT for a in ddi)
    records = detect_qualitative_conflicts(extract_qualitative_assertions([
        _ev("ev_000",
            "Semaglutide is contraindicated in pregnancy and may be co-administered with metformin.",
            "https://a"),
        _ev("ev_001", "Semaglutide is safe in pregnancy.", "https://b"),
    ]))
    assert any(r.severity == "high" for r in records)


def test_no_evidence_of_negation_not_double_counted():
    """Codex diff-gate iter-2 P1.b: 'no evidence of contraindication' must resolve ABSENT — the
    overlapping 'no' inside 'no evidence of' must NOT cancel the net negation."""
    assert ABSENT in _statuses("Semaglutide shows no evidence of contraindication in pregnancy.")
    records = detect_qualitative_conflicts(extract_qualitative_assertions([
        _ev("ev_000", "Semaglutide shows no evidence of contraindication in pregnancy.", "https://a"),
        _ev("ev_001", "Semaglutide is contraindicated in pregnancy.", "https://b"),
    ]))
    assert any(r.severity == "high" for r in records)


def test_same_concept_coordinated_assertions_not_collapsed():
    """Codex diff-gate iter-4 P1: 'safe in pregnancy and contraindicated in lactation' must yield TWO
    assertions, so a real pregnancy PRESENT-vs-ABSENT conflict vs another source is NOT missed."""
    rows = extract_qualitative_assertions([
        _ev("ev_000", "Semaglutide is safe in pregnancy and contraindicated in lactation.", "https://a"),
    ])
    scopes = {(a.assertion_status, a.condition_scope) for a in rows if a.concept_type == "contraindication"}
    assert (ABSENT, "pregnancy") in scopes      # safe in pregnancy
    assert any(st == PRESENT and "lactation" in sc for (st, sc) in scopes)  # contraindicated in lactation
    # the pregnancy disagreement vs another source is now caught as a HARD conflict
    records = detect_qualitative_conflicts(extract_qualitative_assertions([
        _ev("ev_000", "Semaglutide is safe in pregnancy and contraindicated in lactation.", "https://a"),
        _ev("ev_001", "Semaglutide is contraindicated in pregnancy.", "https://b"),
    ]))
    assert any(r.severity == "high" for r in records)


def test_definite_vs_soft_disjoint_outcomes_no_review_noise():
    """Codex diff-gate iter-4 P2: a definite PRESENT on one outcome vs a STATISTICAL_NULL on an
    UNRELATED outcome (nausea vs pancreatitis) must NOT emit a review flag."""
    records = detect_qualitative_conflicts(extract_qualitative_assertions([
        _ev("ev_000", "Semaglutide causes nausea.", "https://a"),
        _ev("ev_001", "Semaglutide is not associated with an increased risk of pancreatitis.", "https://b"),
    ]))
    assert records == []


# ── finite-float encoding + loader-schema round-trip ─────────────────────────────────────────────
def test_finite_float_encoding_for_all_statuses():
    assert qcd._VALUE_BY_STATUS[PRESENT] == 1.0
    assert qcd._VALUE_BY_STATUS[ABSENT] == 0.0
    assert qcd._VALUE_BY_STATUS[INDETERMINATE] == 0.5
    assert qcd._VALUE_BY_STATUS[STATISTICAL_NULL] == 0.5
    for v in qcd._VALUE_BY_STATUS.values():
        assert isinstance(v, float)


def test_records_roundtrip_through_audit_ir_loader(tmp_path):
    from dataclasses import asdict
    from src.polaris_graph.audit_ir import loader as audit_loader

    records = detect_qualitative_conflicts(extract_qualitative_assertions([
        _ev("ev_000", "Semaglutide is contraindicated in pregnancy.", "https://a"),
        _ev("ev_001", "Semaglutide is safe in pregnancy.", "https://b"),
    ]))
    assert records
    payload = [asdict(r) for r in records]
    # loader-required invariants: list; each record predicate+claims(len>=2); each claim value is float
    assert isinstance(payload, list)
    for rec in payload:
        assert "predicate" in rec and isinstance(rec["claims"], list) and len(rec["claims"]) >= 2
        for cl in rec["claims"]:
            assert {"evidence_id", "predicate", "value"} <= set(cl)
            assert isinstance(float(cl["value"]), float)
    # actually parse through the audit loader (the real consumer)
    p = tmp_path / "contradictions.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    clusters = audit_loader._parse_contradictions(json.loads(p.read_text(encoding="utf-8")))
    assert len(clusters) == len(payload)


# ── lexicon validation (fail-loud) ───────────────────────────────────────────────────────────────
def test_missing_lexicon_section_fails_loud(tmp_path, monkeypatch):
    bad = tmp_path / "bad_lexicon.yaml"
    bad.write_text("concept_types: {contraindication: {present_cues: [x], absent_cues: [y]}}\n",
                   encoding="utf-8")
    monkeypatch.setenv("PG_QUALITATIVE_CONFLICT_LEXICON", str(bad))
    monkeypatch.setattr(qcd, "_lexicon_cache", None)
    with pytest.raises(RuntimeError, match="missing/empty required sections"):
        extract_qualitative_assertions([_ev("ev_000", "x is contraindicated in y.", "https://a")])
    monkeypatch.setattr(qcd, "_lexicon_cache", None)  # reset for other tests


# ── kill-switch + offline smoke (Codex brief-gate P2) ────────────────────────────────────────────
def test_kill_switch_default_on_and_off(monkeypatch):
    monkeypatch.delenv("PG_SWEEP_QUALITATIVE_CONFLICT", raising=False)
    assert qcd.qualitative_conflict_enabled() is True   # default ON
    monkeypatch.setenv("PG_SWEEP_QUALITATIVE_CONFLICT", "0")
    assert qcd.qualitative_conflict_enabled() is False
    monkeypatch.setenv("PG_SWEEP_QUALITATIVE_CONFLICT", "off")
    assert qcd.qualitative_conflict_enabled() is False


def test_offline_smoke_full_path_no_spend(tmp_path):
    """Drive extract -> detect -> serialize -> audit_ir.loader round-trip -> report render, all
    offline (the brief's mandated no-spend smoke). Mirrors the run_honest_sweep_r3 wiring."""
    from dataclasses import asdict
    from src.polaris_graph.audit_ir import loader as audit_loader

    evidence = [
        _ev("ev_000", "Semaglutide is contraindicated in pregnancy.", "https://a"),
        _ev("ev_001", "Semaglutide is safe in pregnancy.", "https://b"),
        _ev("ev_002", "Tirzepatide was not associated with an increased risk of pancreatitis.", "https://c"),
        _ev("ev_003", "Tirzepatide is associated with pancreatitis.", "https://d"),
    ]
    records = detect_qualitative_conflicts(extract_qualitative_assertions(evidence, domain="clinical"))
    # serialize EXACTLY as the sweep does (homogeneous dataclass list -> asdict, no mixed serializer)
    payload = [asdict(r) for r in records]
    p = tmp_path / "contradictions.json"
    p.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    clusters = audit_loader._parse_contradictions(json.loads(p.read_text(encoding="utf-8")))
    assert len(clusters) == len(payload)
    # the report renders by assertion_status text, never the raw float
    for r in records:
        for cl in r.claims:
            assert cl["assertion_status"] in (PRESENT, ABSENT, INDETERMINATE, STATISTICAL_NULL)
    # at least the pregnancy hard conflict + the pancreatitis statistical-null review flag
    sev = _severities(records)
    assert "high" in sev and "review" in sev


# ── empty inputs ─────────────────────────────────────────────────────────────────────────────────
def test_empty_inputs():
    assert extract_qualitative_assertions([]) == []
    assert detect_qualitative_conflicts([]) == []
