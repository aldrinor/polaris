"""I-perm-021 (#1213) — RequiredEntityLedger (narrow: inclusion + honest disclosure).

Proves the ledger is pure accounting + honest disclosure over the ALREADY-computed
verified-binding set: VERIFIED only when the entity id is in the covered set (no new credit),
GAP_DISCLOSED otherwise; url_pattern-only missing entities get the canonical-mismatch note;
the Coverage gaps section is deterministic public prose (no LLM, no fabricated citation) and
EMPTY when there are no gaps (so the OFF path stays byte-identical).
"""
from __future__ import annotations

from src.polaris_graph.generator.required_entity_ledger import (
    STATE_GAP_DISCLOSED,
    STATE_VERIFIED,
    build_ledger,
    render_coverage_gaps_section,
    verified_covered_ids,
)


def _ent(eid, *, severity="S1", anchor="", rendering_slot="", **canon):
    e = {"id": eid, "severity": severity, "anchor": anchor, "rendering_slot": rendering_slot}
    e.update(canon)
    return e


def test_verified_and_gap_states():
    entities = [
        _ent("e1", doi="10.1/a", anchor="Trial A"),
        _ent("e2", doi="10.1/b", anchor="Trial B"),
        _ent("e3", pmid="123", anchor="Trial C"),
    ]
    led = build_ledger(entities, covered_entity_ids={"e1", "e3"})
    by = {s.entity_id: s for s in led.slots}
    assert by["e1"].state == STATE_VERIFIED
    assert by["e3"].state == STATE_VERIFIED
    assert by["e2"].state == STATE_GAP_DISCLOSED
    assert {s.entity_id for s in led.verified_slots()} == {"e1", "e3"}
    assert {s.entity_id for s in led.gap_slots()} == {"e2"}
    assert round(led.coverage_fraction(), 4) == round(2 / 3, 4)


def test_verified_covered_ids_excludes_downgraded_claims():
    # Codex diff-gate iter-1 P1 (§-1.1): a claim whose pre-D8 audit row covers an entity but
    # whose 4-role FINAL verdict is NOT VERIFIED must NOT credit coverage (else a real gap is
    # falsely suppressed). The entity then remains GAP_DISCLOSED.
    audit = {
        "00-000-aa": {"covered_element_ids": ["e1"]},   # final VERIFIED -> credits e1
        "00-001-bb": {"covered_element_ids": ["e2"]},   # final UNSUPPORTED -> must NOT credit e2
        "00-002-cc": {"covered_element_ids": ["e3"]},   # final PARTIAL -> must NOT credit e3
    }
    final_verdicts = {
        "00-000-aa": "VERIFIED",
        "00-001-bb": "UNSUPPORTED",
        "00-002-cc": "PARTIAL",
    }
    covered = verified_covered_ids(audit, final_verdicts)
    assert covered == {"e1"}
    # the downgraded entities are disclosed as gaps, NOT marked verified
    led = build_ledger(
        [_ent("e1"), _ent("e2"), _ent("e3")], covered_entity_ids=covered)
    by = {s.entity_id: s for s in led.slots}
    assert by["e1"].state == STATE_VERIFIED
    assert by["e2"].state == STATE_GAP_DISCLOSED
    assert by["e3"].state == STATE_GAP_DISCLOSED


def test_verified_covered_ids_empty_verdicts_credits_nothing():
    # fail-safe: no final_verdicts (seam-timeout path) -> NO claim verified -> all disclosed.
    audit = {"00-000-aa": {"covered_element_ids": ["e1", "e2"]}}
    assert verified_covered_ids(audit, {}) == set()
    assert verified_covered_ids(audit, None) == set()


def test_no_new_credit_a_missing_entity_stays_gap():
    # §-1.1: the ledger never flips a slot to VERIFIED unless its id is in the covered set.
    entities = [_ent("e1", doi="10.1/a")]
    assert build_ledger(entities, covered_entity_ids=set()).slots[0].state == STATE_GAP_DISCLOSED
    assert build_ledger(entities, covered_entity_ids={"e1"}).slots[0].state == STATE_VERIFIED


def test_url_pattern_only_gap_gets_mismatch_note_but_doi_gap_does_not():
    entities = [
        _ent("u1", url_pattern="https://fda.gov/label/x", anchor="FDA label X"),
        _ent("d1", doi="10.1/d", url_pattern="https://x", anchor="Trial D"),  # has doi too
    ]
    led = build_ledger(entities, covered_entity_ids=set())
    by = {s.entity_id: s for s in led.slots}
    assert by["u1"].note and "canonical source" in by["u1"].note   # url_pattern-only -> note
    assert by["d1"].note == ""                                      # doi-bearing -> no note


def test_evidence_gaps_records():
    entities = [_ent("e2", severity="S0", s0_category="contraindications", anchor="X")]
    led = build_ledger(entities, covered_entity_ids=set())
    gaps = led.to_evidence_gaps()
    assert len(gaps) == 1
    g = gaps[0]
    assert g["entity_id"] == "e2" and g["severity"] == "S0"
    assert g["s0_category"] == "contraindications" and g["reason"] == "no_verified_citation"


def test_coverage_gaps_section_empty_when_no_gaps():
    entities = [_ent("e1", doi="10.1/a")]
    led = build_ledger(entities, covered_entity_ids={"e1"})
    assert render_coverage_gaps_section(led) == ""   # byte-identical OFF/no-gap path


def test_coverage_gaps_section_is_public_prose_no_internal_wording():
    entities = [
        _ent("e2", anchor="Trial B", doi="10.1/b"),
        _ent("u1", anchor="FDA label X", url_pattern="https://fda.gov/x"),
    ]
    led = build_ledger(entities, covered_entity_ids=set())
    out = render_coverage_gaps_section(led)
    assert out.startswith("## Coverage gaps")
    assert "Trial B" in out and "FDA label X" in out
    assert "not verified in this run" in out
    assert "canonical source" in out                  # the url_pattern note surfaces
    # no raw internal artifact-path wording (Codex design-gate P2)
    for banned in ("FRAME_GAP", "compose_gap_payload", "_GAP_STUB", "kept_sentences",
                   "strict_verify", "evidence_id"):
        assert banned not in out
    # NEVER fills a gap with a claim — it only discloses absence
    assert "verified citation" in out
