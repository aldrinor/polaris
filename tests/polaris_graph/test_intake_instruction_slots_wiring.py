"""feat/intake-contract — O2 instruction-slot wiring + scope_gate byte-identity.

Covers:
  (a) FLAG-ON: with PG_EXTRACT_INSTRUCTION_SLOTS=1 a multi-instruction question
      populates ProtocolDocument.instruction_slots with the expected kinds/entities;
  (b) FLAG-OFF no-op: instruction_slots == [] and protocol.json is BYTE-IDENTICAL to
      today (no `instruction_slots` / `intake_contract` key), proving the OFF path;
  (c) the section_blueprint consumer: flips `satisfied` for covered slots, marks the
      best-matching section is_thin for an uncovered entity, and is a byte-identical
      no-op given no slots.

Offline/deterministic (llm_fn=None at intake; no network, no LLM, no compose).
"""
from __future__ import annotations

import json
from pathlib import Path

from src.polaris_graph.nodes.scope_gate import run_scope_gate
from src.polaris_graph.retrieval.section_blueprint import (
    SectionSpec,
    bind_instruction_slots,
)

_Q = ("Compare remote work versus office work and include a section on employee "
      "wellbeing.")


def _run(tmp_path: Path, name: str):
    return run_scope_gate(
        research_question=_Q,
        run_dir=tmp_path / name,
        run_id=f"TEST_{name}",
        domain="custom",
    )


# ── (b) FLAG-OFF: byte-identical protocol.json, no new keys ──────────────────

def test_flag_off_protocol_has_no_new_keys(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("PG_EXTRACT_INSTRUCTION_SLOTS", raising=False)
    monkeypatch.delenv("PG_INTAKE_CONTRACT_COMPILE", raising=False)
    res = _run(tmp_path, "off")
    doc = json.loads(res.protocol_path.read_text(encoding="utf-8"))
    assert "instruction_slots" not in doc
    assert "intake_contract" not in doc
    assert res.protocol.instruction_slots == []
    assert res.protocol.intake_contract is None


def test_flag_off_protocol_json_byte_identical(tmp_path, monkeypatch) -> None:
    """Two OFF-path runs of the SAME question produce identical protocol.json bytes
    modulo the volatile identity fields (run_id / timestamps) — proving the new
    fields add nothing to the serialized OFF-path protocol."""
    monkeypatch.delenv("PG_EXTRACT_INSTRUCTION_SLOTS", raising=False)
    monkeypatch.delenv("PG_INTAKE_CONTRACT_COMPILE", raising=False)
    a = json.loads(_run(tmp_path, "a").protocol_path.read_text())
    b = json.loads(_run(tmp_path, "b").protocol_path.read_text())
    for volatile in ("run_id", "created_at_unix", "created_at_iso"):
        a.pop(volatile, None)
        b.pop(volatile, None)
    assert a == b
    assert "instruction_slots" not in a and "intake_contract" not in a


# ── (a) FLAG-ON: instruction_slots populated ────────────────────────────────

def test_flag_on_populates_instruction_slots(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PG_EXTRACT_INSTRUCTION_SLOTS", "1")
    monkeypatch.delenv("PG_INTAKE_CONTRACT_COMPILE", raising=False)
    res = _run(tmp_path, "on")
    slots = res.protocol.instruction_slots
    assert slots, "expected instruction slots with the flag on"
    kinds = {s["kind"] for s in slots}
    assert "comparison" in kinds
    doc = json.loads(res.protocol_path.read_text(encoding="utf-8"))
    assert "instruction_slots" in doc and doc["instruction_slots"]


def test_intake_contract_flag_on_records_shadow(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PG_INTAKE_CONTRACT_COMPILE", "shadow")
    monkeypatch.delenv("PG_EXTRACT_INSTRUCTION_SLOTS", raising=False)
    res = _run(tmp_path, "ic")
    assert res.protocol.intake_contract is not None
    doc = json.loads(res.protocol_path.read_text(encoding="utf-8"))
    assert doc["intake_contract"]["schema_version"] == "intake-contract-v1"
    # SHADOW: enforcement disabled marker present.
    assert doc["intake_contract"]["source_rules_enforcement_disabled"] is True


# ── (c) section_blueprint consumer ──────────────────────────────────────────

def _specs():
    return [
        SectionSpec(section_id="s1", title="Remote work productivity",
                    description="evidence on remote work", is_thin=False, evidence_count=5),
        SectionSpec(section_id="s2", title="Office work dynamics",
                    description="office collaboration", is_thin=False, evidence_count=5),
    ]


def test_consumer_flips_satisfied_for_covered_slot() -> None:
    specs = _specs()
    slots = [{"kind": "comparison", "entities": ["remote work", "office work"],
              "satisfied": False}]
    out = bind_instruction_slots(specs, slots)
    assert slots[0]["satisfied"] is True
    assert out is specs


def test_consumer_marks_thin_for_uncovered_entity() -> None:
    specs = _specs()
    # 'remote wellbeing' is a substring of no section (uncovered) but shares the token
    # 'remote' with section s1 => s1 is the best token-overlap match and is marked thin
    # for targeted retrieval; the slot stays unsatisfied.
    slots = [{"kind": "topic", "entities": ["remote wellbeing"], "satisfied": False}]
    bind_instruction_slots(specs, slots)
    assert slots[0]["satisfied"] is False
    assert specs[0].is_thin is True


def test_consumer_noop_without_slots_is_byte_identical() -> None:
    specs = _specs()
    before = [(s.section_id, s.is_thin) for s in specs]
    bind_instruction_slots(specs, None)
    bind_instruction_slots(specs, [])
    after = [(s.section_id, s.is_thin) for s in specs]
    assert before == after
    assert all(not s.is_thin for s in specs)


def test_consumer_noop_with_empty_specs() -> None:
    slots = [{"kind": "topic", "entities": ["x"], "satisfied": False}]
    assert bind_instruction_slots([], slots) == []
