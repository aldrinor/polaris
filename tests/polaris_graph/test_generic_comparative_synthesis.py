"""Tests for the #957 domain-agnostic comparative synthesis. NO network / NO spend.

Asserts the generic detector is a SOFT, guarded restatement: it fires only for a COMPARABLE field
(not narrative-named, atomic value) shared by >=2 NON-trial entities with DISTINCT bound_ev_id, emits a
neutral "Extracted {field} values — ..." restatement (no fabricated comparison, no "across sources"), runs
only on non-trial frames (trial runs unaffected), and is fully disabled by the kill-switch.
"""

from __future__ import annotations

import pytest

import src.polaris_graph.generator.cross_trial_synthesis as cts
from src.polaris_graph.generator.cross_trial_synthesis import (
    _is_atomic_value,
    _is_comparable_field_name,
    build_cross_trial_synthesis,
)
from src.polaris_graph.generator.slot_fill import SlotFieldFill, SlotFillPayload


def _payload(entity_id, fields):
    """fields: list of (field_name, value, bound_ev_id)."""
    sff = tuple(
        SlotFieldFill(field_name=n, status="extracted", value=v, bound_ev_id=e, source_span=v)
        for n, v, e in fields
    )
    return SlotFillPayload(
        slot_id=f"slot_{entity_id}", entity_id=entity_id, subsection_title="X",
        bound_ev_id=(fields[0][2] if fields else "ev_000"), fields=sff,
        provenance_class="primary",
    )


def _generic_patterns(block):
    out = []
    for pats in block.section_to_patterns.values():
        out.extend(p for p in pats if p.pattern_type == "generic_attribute_comparison")
    return out


def _on(monkeypatch):
    monkeypatch.delenv("PG_SYNTH_GENERIC_COMPARATIVE", raising=False)


# ── helper guards ────────────────────────────────────────────────────────
def test_comparable_field_name_excludes_narrative():
    assert _is_comparable_field_name("effect_size")
    assert not _is_comparable_field_name("interpretation")
    assert not _is_comparable_field_name("study_limitations")
    assert not _is_comparable_field_name("clinical_rationale")


def test_atomic_value_guard():
    assert _is_atomic_value("2.1%")                       # decimal point not a sentence end
    assert _is_atomic_value("HR 0.78 (0.65-0.93)")
    assert not _is_atomic_value("x" * 200)                # too long
    assert not _is_atomic_value("First finding. Second finding.")  # multi-sentence
    assert not _is_atomic_value("line one\nline two")     # multi-line


# ── generic detector ────────────────────────────────────────────────────
def test_generic_comparison_emitted_for_comparable_field(monkeypatch):
    _on(monkeypatch)
    payloads = [
        _payload("microbiota_butyrate", [("effect_size", "OR 1.8", "ev_001")]),
        _payload("microbiota_fusobacterium", [("effect_size", "OR 2.4", "ev_002")]),
    ]
    pats = _generic_patterns(build_cross_trial_synthesis(payloads))
    assert len(pats) == 1
    p = pats[0]
    assert p.section == "Comparative"
    assert "OR 1.8" in p.summary and "OR 2.4" in p.summary
    assert "Extracted effect_size values" in p.summary
    assert "across sources" not in p.summary.lower()   # no unverified provenance framing
    assert set(p.contributing_evidence_ids) == {"ev_001", "ev_002"}


def test_narrative_field_does_not_emit(monkeypatch):
    _on(monkeypatch)
    payloads = [
        _payload("entity_a", [("interpretation", "the mechanism is plausible", "ev_001")]),
        _payload("entity_b", [("interpretation", "the mechanism is uncertain", "ev_002")]),
    ]
    assert _generic_patterns(build_cross_trial_synthesis(payloads)) == []


def test_nonatomic_value_does_not_emit(monkeypatch):
    _on(monkeypatch)
    payloads = [
        _payload("entity_a", [("finding", "First claim. Second claim. Third claim.", "ev_001")]),
        _payload("entity_b", [("finding", "Another. And another. And more.", "ev_002")]),
    ]
    assert _generic_patterns(build_cross_trial_synthesis(payloads)) == []


def test_same_source_pair_does_not_emit(monkeypatch):
    _on(monkeypatch)
    # both values share bound_ev_id ev_001 → not a real cross-source comparison
    payloads = [
        _payload("entity_a", [("effect_size", "OR 1.8", "ev_001")]),
        _payload("entity_b", [("effect_size", "OR 2.4", "ev_001")]),
    ]
    assert _generic_patterns(build_cross_trial_synthesis(payloads)) == []


def test_single_entity_does_not_emit(monkeypatch):
    _on(monkeypatch)
    payloads = [_payload("entity_a", [("effect_size", "OR 1.8", "ev_001")])]
    assert _generic_patterns(build_cross_trial_synthesis(payloads)) == []


def test_trial_entities_excluded_from_generic(monkeypatch):
    _on(monkeypatch)
    # trial entity_ids (match the <anchor>_(primary|secondary|cvot) pattern) are NOT
    # routed to the generic detector — trial runs stay on the trial path.
    payloads = [
        _payload("surpass_2_primary", [("effect_size", "ETD -1.9", "ev_001")]),
        _payload("surpass_3_primary", [("effect_size", "ETD -2.1", "ev_002")]),
    ]
    assert _generic_patterns(build_cross_trial_synthesis(payloads)) == []


def test_same_entity_two_sources_does_not_emit(monkeypatch):
    """Codex diff-gate P1: two payloads for the SAME entity_id (distinct
    bound_ev_id) is one entity compared to itself — NOT a cross-entity
    comparison. Distinct provenance is not enough; distinct entities required."""
    _on(monkeypatch)
    payloads = [
        _payload("microbiota_butyrate", [("effect_size", "OR 1.8", "ev_001")]),
        _payload("microbiota_butyrate", [("effect_size", "OR 2.4", "ev_002")]),
    ]
    assert _generic_patterns(build_cross_trial_synthesis(payloads)) == []


def test_killswitch_off_disables_generic(monkeypatch):
    monkeypatch.setenv("PG_SYNTH_GENERIC_COMPARATIVE", "0")
    payloads = [
        _payload("entity_a", [("effect_size", "OR 1.8", "ev_001")]),
        _payload("entity_b", [("effect_size", "OR 2.4", "ev_002")]),
    ]
    assert _generic_patterns(build_cross_trial_synthesis(payloads)) == []
