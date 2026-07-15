"""feat/intake-contract — unit tests for the intake CONTRACT COMPILER (Part 1).

Pure + offline. A plain ``FakeClient``-style llm_fn stub is injected for the enrich
path (per CLAUDE.md §9.4 — no unittest.mock, no live LLM/network). No full compose
pipeline. Asserts:

  * flag default OFF;
  * floor-only == today's extractors (llm_fn=None adds STRUCTURE, not detections);
  * the FLOOR is NON-DROPPABLE (a hostile/empty LLM cannot erase it);
  * the span gate REJECTS a HARD field whose words are not in the question;
  * degraded mode (llm_fn raises) yields a floor-only contract, loudly warned;
  * the source_rules block is SCAFFOLD ONLY (enforcement_disabled always True).
"""
from __future__ import annotations

import json

from src.polaris_graph.intake.contract_compiler import (
    compile_intake_contract,
    compile_intake_contract_enabled,
)
from src.polaris_graph.retrieval.intake_constraint_extractor import (
    extract_constraints_regex,
    extract_instruction_slots_regex,
)

_Q = (
    "Compare remote work versus office work. Only cite peer-reviewed journals "
    "published before 2020. Write for executives in a concise, analytical tone."
)


class FakeClient:
    """Minimal deterministic llm_fn stub: returns a fixed JSON string, records calls."""

    def __init__(self, response: str) -> None:
        self._response = response
        self.calls: list[str] = []

    def __call__(self, prompt: str) -> str:
        self.calls.append(prompt)
        return self._response


def test_flag_default_off(monkeypatch) -> None:
    monkeypatch.delenv("PG_INTAKE_CONTRACT_COMPILE", raising=False)
    assert compile_intake_contract_enabled() is False
    monkeypatch.setenv("PG_INTAKE_CONTRACT_COMPILE", "shadow")
    assert compile_intake_contract_enabled() is True
    monkeypatch.setenv("PG_INTAKE_CONTRACT_COMPILE", "0")
    assert compile_intake_contract_enabled() is False


def test_floor_only_matches_extractor_detections() -> None:
    """llm_fn=None => the compiler adds STRUCTURE, not new detections: the date /
    journal floor equals exactly what the existing regex extractors already find."""
    c = compile_intake_contract(_Q, llm_fn=None)
    uc = extract_constraints_regex(_Q)
    slots = extract_instruction_slots_regex(_Q)

    assert c.source == "floor"
    assert c.date_window.value["end_year"] == uc.date_end_year == 2020
    assert c.user_constraints.get("journal_only_dormant") == uc.journal_only is True
    assert len(c.instruction_slots) == len(slots) >= 1
    # llm_fn=None never fills the champion-missing (enrich-only) fields.
    assert not c.tone.is_set()
    assert not c.audience.is_set()


def test_source_rules_are_scaffold_only() -> None:
    c = compile_intake_contract(_Q, llm_fn=None)
    assert c.source_rules  # journal-only + the peer_reviewed_journal facet detected
    assert c.source_rules_enforcement_disabled is True
    assert all(r.enforcement_disabled is True for r in c.source_rules)


def test_floor_is_non_droppable_under_hostile_llm() -> None:
    """A hostile LLM that returns an empty object must NOT erase the deterministic
    floor: the date / journal / slots detected by regex survive."""
    llm = FakeClient("{}")
    c = compile_intake_contract(_Q, llm_fn=llm, force=True)
    assert llm.calls, "enrich pass should have called the injected llm_fn"
    assert c.date_window.value["end_year"] == 2020      # floor kept
    assert c.user_constraints.get("journal_only_dormant") is True  # floor kept
    assert len(c.instruction_slots) >= 1                # floor kept


_QH = (
    "Compare remote work versus office work. Only cite peer-reviewed journals "
    "published strictly before 2020. Write for executives."
)


def test_floor_hard_field_non_droppable_under_hostile_enrich() -> None:
    """The GENUINELY dangerous case (not the empty short-circuit): a NON-EMPTY,
    parsable LLM response that ACTIVELY tries to OVERWRITE an existing HARD floor
    field with a fabricated value, and to inject a fabricated field whose words are
    not in the question.

    ``_QH`` establishes a HARD floor date_window (``end_year=2020``, operator
    ``allow_only`` — 'strictly before 2020'). The hostile LLM returns a contradicting
    ``date_end_year=2015`` plus a fabricated ``source_language='German'`` the prompt
    never names. Asserts: (a) the FLOOR value wins — 2020 kept, 2015 rejected, and the
    HARD strength/operator are preserved; (b) the fabricated language is span-gate
    rejected with a loud warning; (c) ``_enrich`` was genuinely invoked (source ==
    'enriched'), i.e. this is the real additive-merge path, NOT the empty short-circuit.
    """
    llm = FakeClient(json.dumps({
        "date_end_year": 2015,                 # contradicts the HARD floor 2020
        "date_end_year_span": "before 2020",   # even a plausible-looking span
        "source_language": "German",           # fabricated: never named in the prompt
    }))
    c = compile_intake_contract(_QH, llm_fn=llm, force=True)

    # (c) the real merge path ran — NOT the `if d:`-False empty short-circuit.
    assert llm.calls, "enrich pass should have called the injected llm_fn"
    assert c.source == "enriched"

    # (a) the FLOOR value wins — the HARD field is non-droppable.
    assert c.date_window.value["end_year"] == 2020          # 2015 never overwrote it
    assert c.date_window.strength == "hard"                 # HARD strength preserved
    assert c.date_window.operator == "allow_only"           # allow_only preserved
    assert c.date_window.origin == "user_explicit"

    # (b) the fabricated language (words not in the prompt) is span-gate rejected.
    assert not c.language.is_set()
    assert c.language.value != "German"
    assert any("German" in w for w in c.warnings)


def test_enrich_admits_query_named_year() -> None:
    """Span-gate ADMIT branch: the gate is not rejecting unconditionally. When the
    floor detects NO date window but the prompt literally names a year, the enrich
    pass admits it (soft, non-narrowing). '2018' is in the prompt but not in a
    cutoff pattern, so the floor leaves date_window unset — the enrich date branch
    then runs and admits the query-named year."""
    q = "Discuss the 2018 policy on remote work for a general audience."
    # sanity: the floor itself detects no date window here.
    assert not compile_intake_contract(q, llm_fn=None).date_window.is_set()
    llm = FakeClient(json.dumps({"date_end_year": 2018}))
    c = compile_intake_contract(q, llm_fn=llm, force=True)
    assert c.date_window.is_set()
    assert c.date_window.value["end_year"] == 2018   # query-named year admitted
    assert c.date_window.strength == "soft"          # enrich year is non-narrowing
    assert c.source == "enriched"


def test_cache_round_trip_preserves_non_droppable_floor(tmp_path, monkeypatch) -> None:
    """On-disk cache round-trip: a forced write, then a second (unforced) call hits
    the cache WITHOUT re-invoking the LLM and reconstructs the SAME non-droppable
    floor. Changing a version key (model or PROMPT_VERSION) busts the stale entry."""
    import src.polaris_graph.intake.contract_compiler as cc

    monkeypatch.setattr(cc, "_CACHE_DIR", tmp_path / "intake_contracts")
    llm = FakeClient(json.dumps({"length": "concise", "length_span": "concise, analytical tone"}))

    # first call forces a cache WRITE
    c1 = cc.compile_intake_contract(_Q, llm_fn=llm, force=True, model="test-model")
    assert c1.source == "enriched"
    assert c1.date_window.value["end_year"] == 2020
    n_calls = len(llm.calls)

    # second call (no force) HITS the cache — the LLM is NOT invoked again ...
    c2 = cc.compile_intake_contract(_Q, llm_fn=llm, force=False, model="test-model")
    assert len(llm.calls) == n_calls, "second call should hit the cache, not re-invoke the LLM"
    # ... and the non-droppable floor is reconstructed identically.
    assert c2.date_window.value["end_year"] == 2020
    assert c2.date_window.strength == "soft"  # 'before 2020' floor is soft (no 'strictly')
    assert c2.user_constraints.get("journal_only_dormant") is True

    # changing the model version key busts the stale entry => recompiles (LLM called).
    c3 = cc.compile_intake_contract(_Q, llm_fn=llm, force=False, model="other-model")
    assert len(llm.calls) == n_calls + 1, "a new model key must bust the cache"
    assert c3.date_window.value["end_year"] == 2020

    # changing PROMPT_VERSION likewise busts even the SAME model key.
    monkeypatch.setattr(cc, "PROMPT_VERSION", "ic-test-bust")
    c4 = cc.compile_intake_contract(_Q, llm_fn=llm, force=False, model="test-model")
    assert len(llm.calls) == n_calls + 2, "a new PROMPT_VERSION must bust the cache"
    assert c4.date_window.value["end_year"] == 2020


def test_span_gate_rejects_fabricated_hard_year() -> None:
    """The rc-2 recency_from:2015 incident: the LLM claims a cutoff year the question
    never names. Because the floor already carries the real (2020) window, and the
    fabricated year would not overwrite it, we assert on a question WITHOUT a date so
    the fabricated year is the only candidate — and it must be DROPPED with a warning."""
    q = "Summarize the evidence on remote work productivity for a general audience."
    llm = FakeClient(json.dumps({"date_end_year": 2015, "tone": "fabricated"}))
    c = compile_intake_contract(q, llm_fn=llm, force=True)
    # No date admitted (2015 is not in the question) ...
    assert not c.date_window.is_set()
    # ... and the fabrication is disclosed LOUDLY, never silent.
    assert any("2015" in w for w in c.warnings)


def test_span_gate_rejects_fabricated_language() -> None:
    q = "Summarize the evidence on remote work productivity."
    llm = FakeClient(json.dumps({"source_language": "French"}))
    c = compile_intake_contract(q, llm_fn=llm, force=True)
    assert not c.language.is_set()
    assert any("French" in w for w in c.warnings)


def test_enrich_admits_span_proven_soft_field() -> None:
    """A presentation field WITH a verbatim span is admitted (non-narrowing)."""
    q = "Write a concise briefing on solar adoption."
    llm = FakeClient(json.dumps({"length": "concise", "length_span": "a concise briefing"}))
    c = compile_intake_contract(q, llm_fn=llm, force=True)
    assert c.length.value == "concise"
    assert c.length.strength == "hard"       # span proven => hard
    assert c.length.verbatim_span


def test_enrich_demotes_unproven_soft_field() -> None:
    q = "Write a briefing on solar adoption."
    llm = FakeClient(json.dumps({"tone": "persuasive"}))  # no span, not in question
    c = compile_intake_contract(q, llm_fn=llm, force=True)
    assert c.tone.value == "persuasive"
    assert c.tone.strength == "soft"         # no proof => soft, never hard
    assert any("tone" in w for w in c.warnings)


def test_degraded_mode_on_llm_exception() -> None:
    def _boom(_prompt: str) -> str:
        raise RuntimeError("network down")

    c = compile_intake_contract(_Q, llm_fn=_boom, force=True)
    assert c.source == "floor"                       # degraded to floor
    assert c.date_window.value["end_year"] == 2020   # floor intact
    assert any("floor-only" in w for w in c.warnings)


def test_empty_prompt_is_inert() -> None:
    c = compile_intake_contract("", llm_fn=None)
    assert c.is_empty() is True
    assert c.to_dict()["schema_version"] == c.schema_version
