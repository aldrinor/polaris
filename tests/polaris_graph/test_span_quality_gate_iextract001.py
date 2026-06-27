"""I-extract-001 LAYER B — offline self-tests for the span-quality gate.

No live calls; the LLM is a stub keyed by unit text. Asserts the §-1.3 FLAG-not-drop
contract, the deterministic precision-narrowing invariant (only ever junk -> clean), the
default-OFF zero-call no-op, the fail-honest error -> pass-through, and confidence-escalation.
"""
from __future__ import annotations

import json

import pytest

from src.polaris_graph.generator import span_quality_gate as sg


# ── stub LLM: return a canned verdict JSON keyed by the candidate unit text ───
def _make_stub(verdict_by_unit: dict[str, dict], *, calls: list[str] | None = None,
               raise_on: set[str] | None = None, raw_by_unit: dict[str, str] | None = None):
    raise_on = raise_on or set()
    raw_by_unit = raw_by_unit or {}

    def _call(prompt: str) -> str:
        # The candidate under review is the LAST "CANDIDATE UNIT:\n..." block in the prompt.
        unit = prompt.rsplit("CANDIDATE UNIT:\n", 1)[1].rsplit("\nJSON:", 1)[0]
        if calls is not None:
            calls.append(unit)
        if unit in raise_on:
            raise RuntimeError("simulated transport fault")
        if unit in raw_by_unit:
            return raw_by_unit[unit]
        return json.dumps(verdict_by_unit[unit])
    return _call


def _v(is_real, cls="clean", span="", conf=0.95):
    return {"is_real_finding": is_real, "failure_class": cls,
            "offending_span": span, "confidence": conf}


@pytest.fixture(autouse=True)
def _enable_gate(monkeypatch):
    monkeypatch.setenv("PG_SPAN_QUALITY_GATE", "1")


# ── core classification ──────────────────────────────────────────────────────
def test_clean_and_each_junk_class_classified():
    clean = "A 2020 OECD study estimates that 14% of jobs are at high risk of automation.[11]"
    heading = "Frequently Asked Questions. How does machine learning work"
    masthead = "Received 12 March 2021; accepted 4 August 2021; published online 2021"
    trunc = "the model predicts employ.; ment growth across all sectors.[5]"
    orphan = ".[4][5]"
    units = [clean, heading, masthead, trunc, orphan]
    stub = _make_stub({
        clean: _v(True),
        heading: _v(False, "scraped_heading", heading),
        masthead: _v(False, "masthead", "Received 12 March 2021; accepted 4 August 2021"),
        trunc: _v(False, "truncation", "employ.; ment"),
        orphan: _v(False, "orphan_citation", ".[4][5]"),
    })
    out = sg.screen_finding_units(units, primary_call_llm=stub)
    assert [v.is_junk for v in out] == [False, True, True, True, True]
    assert [v.junk_class for v in out] == [
        "clean", "scraped_heading", "masthead", "truncation", "orphan_citation"]
    assert [v.unit_index for v in out] == [0, 1, 2, 3, 4]  # order preserved, 1:1


def test_flag_not_drop_length_preserved():
    units = ["clean finding one is a complete sentence.", ".[9][10]", "another complete finding."]
    stub = _make_stub({
        units[0]: _v(True), units[1]: _v(False, "orphan_citation", ".[9][10]"),
        units[2]: _v(True),
    })
    out = sg.screen_finding_units(units, primary_call_llm=stub)
    assert len(out) == len(units)  # nothing dropped — FLAG, never drop (§-1.3)


# ── precision narrowing: only ever junk -> clean ─────────────────────────────
def test_orphan_narrowing_demotes_trailing_citation_finding():
    # A real finding the judge over-flagged as orphan_citation (trailing multi-cite cluster).
    unit = "Automation displaces routine cognitive labor across many sectors.[11][12][13]"
    stub = _make_stub({unit: _v(False, "orphan_citation", "[11][12][13]")})
    out = sg.screen_finding_units([unit], primary_call_llm=stub)
    assert out[0].is_junk is False
    assert out[0].source == "narrowed_clean"


def test_orphan_narrowing_keeps_bracket_only_fragment():
    unit = ".[19][20]"
    stub = _make_stub({unit: _v(False, "orphan_citation", ".[19][20]")})
    out = sg.screen_finding_units([unit], primary_call_llm=stub)
    assert out[0].is_junk is True  # bare fragment survives


def test_truncation_narrowing_demotes_complete_sentence():
    # A complete declarative sentence the judge mislabeled truncation -> demote.
    unit = "GDP grew by three percent in 2021 across all member states.[7]"
    stub = _make_stub({unit: _v(False, "truncation", "across all member states")})
    out = sg.screen_finding_units([unit], primary_call_llm=stub)
    assert out[0].is_junk is False
    assert out[0].source == "narrowed_clean"


def test_truncation_narrowing_keeps_midword_glue_and_endcut():
    glue = "standard labor data focus on aggregate statis.; bstitution between groups.[15]"
    endcut = "the majority of experts argued that multimodal systems generate outputs from m"
    stub = _make_stub({
        glue: _v(False, "truncation", "statis.; bstitution"),
        endcut: _v(False, "truncation", "from m"),
    })
    out = sg.screen_finding_units([glue, endcut], primary_call_llm=stub)
    assert [v.is_junk for v in out] == [True, True]  # mid-word evidence -> survive


def test_section_word_prefix_exemption_demotes():
    unit = ("**Foundational Theory.** The model predicts that automation will displace "
            "many routine cognitive tasks across multiple sectors over the coming decade.")
    stub = _make_stub({unit: _v(False, "scraped_heading", "Foundational Theory.")})
    out = sg.screen_finding_units([unit], primary_call_llm=stub)
    assert out[0].is_junk is False
    assert out[0].source == "narrowed_clean"


def test_short_heading_not_exempted():
    # A genuine scraped heading with too-short trailing content is NOT demoted.
    unit = "Frequently Asked Questions. How does it work"
    stub = _make_stub({unit: _v(False, "scraped_heading", unit)})
    out = sg.screen_finding_units([unit], primary_call_llm=stub)
    assert out[0].is_junk is True


# ── fail-honest: error / malformed -> pass-through (never flag on uncertainty) ─
def test_judge_error_is_passthrough_not_flag():
    unit = "some unit that triggers a transport fault"
    stub = _make_stub({}, raise_on={unit})
    out = sg.screen_finding_units([unit], primary_call_llm=stub)
    assert out[0].is_junk is False
    assert out[0].source == "error"


def test_malformed_output_is_passthrough():
    unit = "a unit whose judge returns garbage"
    stub = _make_stub({}, raw_by_unit={unit: "I cannot answer that as JSON."})
    out = sg.screen_finding_units([unit], primary_call_llm=stub)
    assert out[0].is_junk is False
    assert out[0].source == "error"


def test_reasoning_model_json_plus_trailing_prose_parsed():
    # GLM-5.2 reasoning-model norm: a valid verdict object followed by trailing reasoning.
    unit = ".[4][5]"
    raw = ('{"is_real_finding": false, "failure_class": "orphan_citation", '
           '"offending_span": ".[4][5]", "confidence": 0.97}\nThe unit is a bare citation.')
    stub = _make_stub({}, raw_by_unit={unit: raw})
    out = sg.screen_finding_units([unit], primary_call_llm=stub)
    assert out[0].is_junk is True
    assert out[0].junk_class == "orphan_citation"


# ── confidence-escalation ────────────────────────────────────────────────────
def test_low_confidence_escalates_when_escalation_provided():
    unit = "an ambiguous unit the primary is unsure about and ends mid-w"
    primary_calls: list[str] = []
    esc_calls: list[str] = []
    primary = _make_stub({unit: _v(False, "truncation", "mid-w", conf=0.4)}, calls=primary_calls)
    escalation = _make_stub({unit: _v(True, conf=0.9)}, calls=esc_calls)
    out = sg.screen_finding_units(
        [unit], primary_call_llm=primary, escalation_call_llm=escalation)
    assert esc_calls == [unit]          # escalation fired (primary conf 0.4 < 0.7)
    assert out[0].is_junk is False      # escalation overrode to clean
    assert out[0].source == "escalation"


def test_high_confidence_does_not_escalate():
    unit = "a confident clean finding sentence that is complete."
    esc_calls: list[str] = []
    primary = _make_stub({unit: _v(True, conf=0.95)})
    escalation = _make_stub({unit: _v(False, "scraped_heading", unit)}, calls=esc_calls)
    out = sg.screen_finding_units(
        [unit], primary_call_llm=primary, escalation_call_llm=escalation)
    assert esc_calls == []              # no escalation at conf 0.95 >= 0.7
    assert out[0].is_junk is False


# ── default-OFF: zero LLM calls, disabled verdicts ───────────────────────────
def test_disabled_flag_zero_calls_passthrough(monkeypatch):
    monkeypatch.delenv("PG_SPAN_QUALITY_GATE", raising=False)
    calls: list[str] = []
    units = ["unit one.", ".[9][10]"]
    stub = _make_stub({}, calls=calls)
    out = sg.screen_finding_units(units, primary_call_llm=stub)
    assert calls == []                                   # ZERO LLM calls when OFF
    assert all(v.source == "disabled" for v in out)
    assert all(v.is_junk is False for v in out)
    assert len(out) == len(units)


def test_empty_input_returns_empty():
    assert sg.screen_finding_units([]) == []
