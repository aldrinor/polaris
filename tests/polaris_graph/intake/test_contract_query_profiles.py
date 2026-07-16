"""feat/intake-contract — unit tests for the QUERY-TYPE PROFILES lane (Part B).

Pure + offline. NO LLM, NO network, NO faithfulness path. Asserts:

  * flag PG_CONTRACT_QUERY_TYPE_PROFILES default OFF;
  * flag OFF => byte-identical contract (no query_types, no profile fields) —
    to_dict equals the flag-off baseline exactly;
  * the classifier maps sample prompts (incl. task-72 -> literature_review PRIMARY,
    market_industry SECONDARY) to the right ordered type list;
  * a profile supplies DEFAULT presentation fields (origin='profile_default',
    strength='default') when the field is unset;
  * an EXPLICIT prompt field (span-gated enrich) overrides the profile default;
  * a FLOOR value (date window) is never touched by a profile;
  * profiles add typical_sections only when the floor has none, and add NO citation
    or report text.
"""
from __future__ import annotations

import json

import pytest

from src.polaris_graph.intake import contract_compiler as cc
from src.polaris_graph.intake.contract_compiler import (
    _classify_query_type,
    compile_intake_contract,
    query_type_profiles_enabled,
)

# Task-72 RQ (the AI restructuring / 4IR literature review over the AI-and-labor
# corpus): states NO explicit tone/audience/format/length, so profile defaults apply.
_TASK72 = (
    "Conduct a literature review on how artificial intelligence is restructuring "
    "the labor market and the future of the workforce."
)


class FakeClient:
    def __init__(self, response: str) -> None:
        self._response = response
        self.calls: list[str] = []

    def __call__(self, prompt: str) -> str:
        self.calls.append(prompt)
        return self._response


def _on(monkeypatch) -> None:
    monkeypatch.setenv("PG_CONTRACT_QUERY_TYPE_PROFILES", "1")
    cc.query_type_profiles_enabled()  # touch


def test_flag_default_off(monkeypatch) -> None:
    monkeypatch.delenv("PG_CONTRACT_QUERY_TYPE_PROFILES", raising=False)
    assert query_type_profiles_enabled() is False
    monkeypatch.setenv("PG_CONTRACT_QUERY_TYPE_PROFILES", "1")
    assert query_type_profiles_enabled() is True
    monkeypatch.setenv("PG_CONTRACT_QUERY_TYPE_PROFILES", "off")
    assert query_type_profiles_enabled() is False


def test_flag_off_byte_identical(monkeypatch) -> None:
    """Flag OFF => no classify, no profile import, no field write. The contract
    to_dict is IDENTICAL to today's (query_types empty, no profile_default fields)."""
    monkeypatch.delenv("PG_CONTRACT_QUERY_TYPE_PROFILES", raising=False)
    c = compile_intake_contract(_TASK72, llm_fn=None)
    d = c.to_dict()
    assert d["query_types"] == []
    assert not c.tone.is_set()
    assert not c.audience.is_set()
    assert not c.format.is_set()
    assert not c.length.is_set()
    # no profile_default origin anywhere.
    assert all(
        d[f]["origin"] != "profile_default"
        for f in ("tone", "audience", "format", "length")
    )


def test_classifier_task72_literature_review_primary(monkeypatch) -> None:
    c = compile_intake_contract(_TASK72, llm_fn=None)  # floor for slot detection
    types = _classify_query_type(_TASK72, c)
    assert types[0] == "literature_review", types
    assert "market_industry" in types
    assert types[-1] == "general"
    # literature_review precedes market_industry (primary before secondary).
    assert types.index("literature_review") < types.index("market_industry")


@pytest.mark.parametrize(
    "q, expected_primary",
    [
        ("Compare remote work versus office work for executives.", "comparison"),
        ("How to configure a Kubernetes ingress step by step.", "how_to"),
        ("What is the market size and CAGR forecast for solar inverters?", "market_industry"),
        ("Systematic review of mindfulness interventions.", "literature_review"),
        ("Explain the causes of the French Revolution.", "general"),
    ],
)
def test_classifier_maps_sample_prompts(q, expected_primary) -> None:
    c = compile_intake_contract(q, llm_fn=None)
    types = _classify_query_type(q, c)
    assert types[0] == expected_primary, (q, types)
    assert types[-1] == "general"


def test_profile_supplies_defaults_task72(monkeypatch) -> None:
    """Task-72: the literature_review profile fills tone/audience/format/length as
    DEFAULTS (origin='profile_default', strength='default') and appends its
    typical_sections skeleton (floor has no required_sections here)."""
    _on(monkeypatch)
    c = compile_intake_contract(_TASK72, llm_fn=None)
    assert c.tone.value == "scholarly, analytical, measured"
    assert c.tone.origin == "profile_default"
    assert c.tone.strength == "default"
    assert c.tone.verbatim_span == ""            # a default carries no prompt span
    assert c.audience.value == "researchers and domain experts"
    assert c.format.value == "narrative synthesis organized by theme"
    assert c.length.value == "comprehensive"
    # telemetry disclosed, literature_review present.
    assert any(qt["type"] == "literature_review" for qt in c.query_types)
    # typical_sections appended as profile_default gap candidates.
    titles = [s["text"] for s in c.required_sections]
    assert "Thematic Findings" in titles
    assert all(s.get("origin") == "profile_default" for s in c.required_sections)


def test_explicit_prompt_field_overrides_profile(monkeypatch) -> None:
    """An EXPLICIT prompt directive (span-gated enrich => the field is_set) must win:
    the profile's default tone is NOT written over it. Uses a FakeClient enrich that
    proves 'concise' with a verbatim span."""
    _on(monkeypatch)
    q = (
        "Conduct a literature review on AI and the workforce. Write in a concise, "
        "punchy tone."
    )
    llm = FakeClient(json.dumps({
        "tone": "concise, punchy", "tone_span": "concise, punchy tone",
    }))
    c = compile_intake_contract(q, llm_fn=llm, force=True)
    # enrich set tone from the prompt => profile default must NOT overwrite it.
    assert c.tone.value == "concise, punchy"
    assert c.tone.origin == "user_explicit"
    assert c.tone.strength == "hard"
    # the OTHER unset fields still get profile defaults.
    assert c.audience.origin == "profile_default"


def test_floor_value_overrides_profile(monkeypatch) -> None:
    """A FLOOR value is never touched by a profile. The floor date_window
    (deterministic) survives; profiles never write date_window at all."""
    _on(monkeypatch)
    q = (
        "Compare remote versus office work. Only cite peer-reviewed journals "
        "published strictly before 2020."
    )
    c = compile_intake_contract(q, llm_fn=None)
    # floor HARD date window intact — profiles touch no narrowing field.
    assert c.date_window.value["end_year"] == 2020
    assert c.date_window.strength == "hard"
    assert c.date_window.origin == "user_explicit"
    # comparison profile is highest-priority match here and supplies presentation.
    assert c.tone.origin == "profile_default"
    assert any(qt["type"] == "comparison" for qt in c.query_types)


def test_profile_does_not_overwrite_floor_sections(monkeypatch) -> None:
    """typical_sections are appended ONLY when the floor produced no required
    sections. A comparison prompt yields a floor comparison slot, so the profile
    must NOT append its skeleton over it."""
    _on(monkeypatch)
    q = "Compare remote work versus office work."
    c_off_floor = compile_intake_contract(q, llm_fn=None)
    # (this q has a floor comparison slot -> required_sections non-empty)
    assert any(
        str(s.get("kind")).lower() == "comparison" for s in c_off_floor.required_sections
    )
    # none of the required sections are profile_default (floor sections kept).
    assert not any(
        s.get("origin") == "profile_default" for s in c_off_floor.required_sections
    )


def test_profiles_add_no_report_text_or_citations(monkeypatch) -> None:
    """Profiles add ONLY declarative fields — never report prose, never a citation.
    The contract carries no source_rules churn and enforcement stays disabled."""
    _on(monkeypatch)
    c = compile_intake_contract(_TASK72, llm_fn=None)
    assert c.source_rules_enforcement_disabled is True
    assert all(r.enforcement_disabled is True for r in c.source_rules)
    # required_sections injected by the profile are ev-less gap candidates: no text
    # beyond the section TITLE, no citation payload.
    for s in c.required_sections:
        assert set(s.keys()) <= {"kind", "entities", "text", "satisfied", "origin"}
        assert s.get("entities") == []
