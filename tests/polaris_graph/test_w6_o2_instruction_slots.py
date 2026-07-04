"""w6-O2 — instruction-to-slot binding. OFFLINE, deterministic, $0.

O2 closes the RACE instruction-following gap: the prompt's EXPLICIT instructions
(a requested comparison, a named list of sub-topics, a requested section, a
requested structure) were dropped at intake, so the blueprint never decomposed
them into dedicated slots and the report could silently skip a requested
comparison. `extract_instruction_slots` now emits each explicit instruction as a
REQUIRED slot the downstream validator can flag THIN.

These tests prove the EFFECT on real prompt text — a realistic multi-instruction
research prompt decomposes into the exact required slots, and a plain prompt with
no explicit instructions binds NONE (no invented slots). Each is RED before O2
(the function does not exist) and GREEN after.

DNA guard (§-1.3): a slot is a binding, not a filter — the test asserts the slots
carry the requested entities, never that any source is dropped or capped.
"""
from __future__ import annotations

import os

import pytest

from src.polaris_graph.retrieval.intake_constraint_extractor import (
    SLOT_COMPARISON,
    SLOT_ENUMERATION,
    SLOT_STRUCTURE,
    SLOT_TOPIC,
    extract_instruction_slots,
    extract_instruction_slots_enabled,
    extract_instruction_slots_regex,
)


def _by_kind(slots, kind):
    return [s for s in slots if s.kind == kind]


# ─────────────────────────────────────────────────────────────────────────────
# a realistic multi-instruction prompt decomposes into the requested slots
# ─────────────────────────────────────────────────────────────────────────────
def test_multi_instruction_prompt_binds_all_slots():
    prompt = (
        "Assess the current landscape of GLP-1 receptor agonists for obesity. "
        "Compare semaglutide and tirzepatide on efficacy and safety. "
        "Cover the following: cardiovascular outcomes, gastrointestinal adverse "
        "events, and cost-effectiveness. "
        "Include a section on regulatory status across jurisdictions. "
        "Organize the analysis by drug class."
    )
    slots = extract_instruction_slots(prompt)

    # comparison slot binds the two named agents.
    cmp = _by_kind(slots, SLOT_COMPARISON)
    assert len(cmp) >= 1
    cmp_ents = [e.lower() for e in cmp[0].entities]
    assert "semaglutide" in cmp_ents and "tirzepatide" in cmp_ents

    # enumeration slot binds the three explicitly requested topics.
    enum = _by_kind(slots, SLOT_ENUMERATION)
    assert len(enum) == 1
    enum_ents = [e.lower() for e in enum[0].entities]
    assert "cardiovascular outcomes" in enum_ents
    assert "gastrointestinal adverse events" in enum_ents
    assert "cost-effectiveness" in enum_ents

    # requested section becomes a topic slot.
    topic = _by_kind(slots, SLOT_TOPIC)
    assert len(topic) == 1
    assert "regulatory status" in topic[0].entities[0].lower()

    # requested structure becomes a structure slot.
    struct = _by_kind(slots, SLOT_STRUCTURE)
    assert len(struct) == 1
    assert "drug class" in struct[0].entities[0].lower()

    # every slot starts UNsatisfied (the downstream validator flips it).
    assert all(s.satisfied is False for s in slots)
    # slot ids are stable + unique.
    assert len({s.slot_id for s in slots}) == len(slots)


# ─────────────────────────────────────────────────────────────────────────────
# infix "X vs Y" comparison
# ─────────────────────────────────────────────────────────────────────────────
def test_infix_versus_comparison():
    slots = extract_instruction_slots_regex(
        "Evaluate remote work vs office work for engineering productivity."
    )
    cmp = _by_kind(slots, SLOT_COMPARISON)
    assert len(cmp) == 1
    ents = [e.lower() for e in cmp[0].entities]
    assert ents == ["remote work", "office work"]


# ─────────────────────────────────────────────────────────────────────────────
# a plain prompt with NO explicit instructions binds NO slots (no invention)
# ─────────────────────────────────────────────────────────────────────────────
def test_plain_prompt_binds_no_slots():
    slots = extract_instruction_slots(
        "What is the mechanism of action of metformin in type 2 diabetes?"
    )
    assert slots == []


# ─────────────────────────────────────────────────────────────────────────────
# a "compare" verb with only one object is NOT a comparison slot
# ─────────────────────────────────────────────────────────────────────────────
def test_single_object_is_not_a_comparison():
    slots = extract_instruction_slots_regex(
        "Compare the effectiveness of the new protocol."
    )
    assert _by_kind(slots, SLOT_COMPARISON) == []


# ─────────────────────────────────────────────────────────────────────────────
# duplicate instructions collapse to one slot (order-preserving)
# ─────────────────────────────────────────────────────────────────────────────
def test_duplicate_instruction_collapses():
    slots = extract_instruction_slots_regex(
        "Compare A and B. Later, please compare A and B again."
    )
    cmp = _by_kind(slots, SLOT_COMPARISON)
    # both spans carry the same entity pair -> deduped to one slot.
    assert len(cmp) == 1
    assert [e.lower() for e in cmp[0].entities] == ["a", "b"]


# ─────────────────────────────────────────────────────────────────────────────
# LLM fallback fills the total-miss case only; injected, offline
# ─────────────────────────────────────────────────────────────────────────────
def test_llm_fallback_used_only_on_total_regex_miss():
    calls = {"n": 0}

    def fake_llm(_prompt):
        calls["n"] += 1
        return (
            '[{"kind": "comparison", "text": "east coast against west coast", '
            '"entities": ["east coast", "west coast"]}]'
        )

    # A prose comparison the regex misses ("weigh ... against ...").
    slots = extract_instruction_slots(
        "Weigh the east coast against the west coast for biotech hiring.",
        llm_fn=fake_llm,
    )
    assert calls["n"] == 1
    cmp = _by_kind(slots, SLOT_COMPARISON)
    assert len(cmp) == 1
    assert cmp[0].source == "llm"
    assert [e.lower() for e in cmp[0].entities] == ["east coast", "west coast"]


def test_llm_not_called_when_regex_already_bound():
    calls = {"n": 0}

    def fake_llm(_prompt):
        calls["n"] += 1
        return "[]"

    slots = extract_instruction_slots("Compare A and B.", llm_fn=fake_llm)
    assert calls["n"] == 0                       # regex fired -> no LLM escalation
    assert len(_by_kind(slots, SLOT_COMPARISON)) == 1


def test_llm_fallback_failsoft_on_bad_reply():
    def bad_llm(_prompt):
        raise RuntimeError("model down")

    # No regex slot + LLM raises -> no slot invented, no exception into the run.
    slots = extract_instruction_slots("A vague prompt with no instructions here.",
                                      llm_fn=bad_llm)
    assert slots == []


# ─────────────────────────────────────────────────────────────────────────────
# config-driven flag (LAW VI): default OFF, on-tokens turn it on
# ─────────────────────────────────────────────────────────────────────────────
def test_flag_default_off():
    prev = os.environ.get("PG_EXTRACT_INSTRUCTION_SLOTS")
    try:
        os.environ.pop("PG_EXTRACT_INSTRUCTION_SLOTS", None)
        assert extract_instruction_slots_enabled() is False
        os.environ["PG_EXTRACT_INSTRUCTION_SLOTS"] = "1"
        assert extract_instruction_slots_enabled() is True
        os.environ["PG_EXTRACT_INSTRUCTION_SLOTS"] = "0"
        assert extract_instruction_slots_enabled() is False
    finally:
        if prev is None:
            os.environ.pop("PG_EXTRACT_INSTRUCTION_SLOTS", None)
        else:
            os.environ["PG_EXTRACT_INSTRUCTION_SLOTS"] = prev


# ─────────────────────────────────────────────────────────────────────────────
# to_dict is JSON-shaped for the downstream ledger/validator
# ─────────────────────────────────────────────────────────────────────────────
def test_slot_to_dict_shape():
    slots = extract_instruction_slots_regex("Compare A and B.")
    d = slots[0].to_dict()
    assert set(d) == {"slot_id", "kind", "text", "entities", "satisfied", "source"}
    assert d["kind"] == SLOT_COMPARISON
    assert d["satisfied"] is False
