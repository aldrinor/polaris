"""I-ready-009 (#1081) — generator answer-SHAPE: non-clinical questions get a domain-neutral outline.

The Gate-B generator forced clinical section headers (Efficacy/Safety/Population Subgroups) onto
NON-clinical questions. Fix = a generator-only OFF-mode outline-set switch: clinical/unknown keep the
proven clinical _ALLOWED_SECTIONS byte-identical; any other domain gets a domain-neutral generic set.
The planner / scope template / V30 contracts / section-PROSE prompt are ALL untouched. Offline, no spend.
"""
from __future__ import annotations

import inspect

import pytest

from src.polaris_graph.generator import multi_section_generator as m


# ── domain → allowed section set ─────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("domain", ["clinical", "Clinical", " CLINICAL ", "", None])
def test_clinical_and_unknown_keep_clinical_sections_byte_identical(domain):
    assert m._allowed_sections_for_domain(domain) == m._ALLOWED_SECTIONS


@pytest.mark.parametrize("domain", ["economic", "workforce", "policy", "tech", "due_diligence", "source_critical"])
def test_non_clinical_domains_get_generic_set(domain):
    got = m._allowed_sections_for_domain(domain)
    assert got == m._ALLOWED_SECTIONS_GENERIC
    # the generic set must NOT carry clinical headers (that was the defect).
    for clinical_label in ("Efficacy", "Safety", "Regulatory", "Mechanism", "Dose Response",
                           "Population Subgroups", "Long-term Outcomes"):
        assert clinical_label not in got


# ── domain → outline system prompt ───────────────────────────────────────────────────────────────
@pytest.mark.parametrize("domain", ["clinical", "", None])
def test_clinical_unknown_select_clinical_outline_prompt(domain):
    assert m._select_outline_system_prompt(domain) is m.OUTLINE_SYSTEM_PROMPT


@pytest.mark.parametrize("domain", ["economic", "policy", "workforce"])
def test_non_clinical_select_generic_outline_prompt(domain):
    assert m._select_outline_system_prompt(domain) is m.OUTLINE_SYSTEM_PROMPT_GENERIC


def test_clinical_outline_prompt_is_unchanged():
    # the clinical OFF-mode outline prompt keeps its clinical-specific rules (byte-identical path).
    assert "Efficacy" in m.OUTLINE_SYSTEM_PROMPT
    assert "SURPASS" in m.OUTLINE_SYSTEM_PROMPT
    assert "Mechanism" in m.OUTLINE_SYSTEM_PROMPT


def test_generic_outline_prompt_drops_clinical_rules_keeps_rigor():
    g = m.OUTLINE_SYSTEM_PROMPT_GENERIC
    # clinical-specific section-name rules are gone (else they'd contradict the generic title list).
    assert "Efficacy" not in g and "SURPASS" not in g and "SURMOUNT" not in g
    # general DR rigor preserved: tier hierarchy + primary-source-over-derivative + injection-as-data.
    assert "[T1]" in g and "[T7]" in g
    assert "PRIMARY source" in g
    assert "<<<evidence" in g


# ── _parse_outline validates against the supplied set ────────────────────────────────────────────
def _outline_json(title: str) -> str:
    return (
        '{"sections":['
        f'{{"title":"{title}","focus":"f","ev_ids":["ev_1","ev_2"]}},'
        '{"title":"%s","focus":"f","ev_ids":["ev_3","ev_4"]},'
        '{"title":"%s","focus":"f","ev_ids":["ev_5","ev_6"]}]}'
    )


def test_parse_outline_accepts_generic_title_with_generic_allowed():
    raw = (
        '{"sections":['
        '{"title":"Key Findings","focus":"f","ev_ids":["ev_1","ev_2"]},'
        '{"title":"Evidence and Analysis","focus":"f","ev_ids":["ev_3","ev_4"]},'
        '{"title":"Implications","focus":"f","ev_ids":["ev_5","ev_6"]}]}'
    )
    res = m._parse_outline(raw, allowed_sections=m._ALLOWED_SECTIONS_GENERIC)
    titles = {p.title for p in res.plans}
    assert "Key Findings" in titles and "Implications" in titles


def test_parse_outline_drops_clinical_title_under_generic_allowed():
    raw = (
        '{"sections":['
        '{"title":"Efficacy","focus":"f","ev_ids":["ev_1","ev_2"]},'
        '{"title":"Key Findings","focus":"f","ev_ids":["ev_3","ev_4"]},'
        '{"title":"Implications","focus":"f","ev_ids":["ev_5","ev_6"]}]}'
    )
    res = m._parse_outline(raw, allowed_sections=m._ALLOWED_SECTIONS_GENERIC)
    titles = {p.title for p in res.plans}
    assert "Efficacy" not in titles            # clinical title not in the generic allowed set
    assert "Key Findings" in titles


def test_parse_outline_default_is_clinical_byte_identical():
    raw = (
        '{"sections":['
        '{"title":"Efficacy","focus":"f","ev_ids":["ev_1","ev_2"]},'
        '{"title":"Safety","focus":"f","ev_ids":["ev_3","ev_4"]},'
        '{"title":"Comparative","focus":"f","ev_ids":["ev_5","ev_6"]}]}'
    )
    res = m._parse_outline(raw)  # no allowed_sections -> clinical default
    titles = {p.title for p in res.plans}
    assert "Efficacy" in titles and "Safety" in titles


# ── deterministic fallback is domain-aware ───────────────────────────────────────────────────────
def _ev(n: int) -> list[dict]:
    return [{"evidence_id": f"ev_{i}"} for i in range(n)]


def test_deterministic_fallback_clinical_uses_clinical_titles():
    plans = m._build_deterministic_fallback_outline(_ev(12), domain="clinical")
    titles = [p.title for p in plans]
    assert titles == ["Efficacy", "Safety", "Comparative"]


def test_deterministic_fallback_non_clinical_uses_generic_titles():
    plans = m._build_deterministic_fallback_outline(_ev(12), domain="economic")
    titles = [p.title for p in plans]
    assert titles == ["Key Findings", "Evidence and Analysis", "Implications"]
    assert "Efficacy" not in titles and "Safety" not in titles


# ── the planner is NOT touched; the section-PROSE prompt is unchanged for all domains ─────────────
def test_no_research_planner_env_in_new_outline_code():
    for fn in (m._allowed_sections_for_domain, m._select_outline_system_prompt,
               m._build_deterministic_fallback_outline, m._call_outline):
        src = inspect.getsource(fn)
        assert "PG_USE_RESEARCH_PLANNER" not in src
        assert "research_plan" not in src  # outline-set switch never reads the planner


def test_generate_multi_section_report_has_domain_param_default_empty():
    sig = inspect.signature(m.generate_multi_section_report)
    assert sig.parameters["domain"].default == ""


def test_section_prose_prompt_selection_is_unchanged():
    # the prose prompt is still keyed on use_field_agnostic (planner), NOT on our new domain switch —
    # so prose rigor (rules 1-13 incl. primary-source/jurisdiction) is identical for every domain.
    src = inspect.getsource(m._select_section_system_prompt)
    assert "use_field_agnostic" in src
    assert "domain" not in src


# ── Codex diff-gate iter-1 P1: the RETRY prompt must be domain-aware end-to-end ───────────────────
class _FakeResp:
    def __init__(self, content):
        self.content = content
        self.input_tokens = 1
        self.output_tokens = 1


def _make_fake_client(captured: list[str]):
    _VALID_GENERIC = (
        '{"sections":['
        '{"title":"Key Findings","focus":"f","ev_ids":["ev_0","ev_1"]},'
        '{"title":"Evidence and Analysis","focus":"f","ev_ids":["ev_2","ev_3"]},'
        '{"title":"Implications","focus":"f","ev_ids":["ev_4","ev_5"]}]}'
    )

    class _FakeClient:
        def __init__(self, model=None):
            pass

        async def generate(self, prompt, system, max_tokens, temperature):
            captured.append(system)
            # first call -> invalid (forces the retry path); second -> a valid generic outline.
            return _FakeResp('{"sections": []}' if len(captured) == 1 else _VALID_GENERIC)

    return _FakeClient


def test_non_clinical_retry_prompt_has_no_clinical_leak(monkeypatch):
    import asyncio

    from src.polaris_graph.llm import openrouter_client as orc

    captured: list[str] = []
    monkeypatch.setattr(orc, "OpenRouterClient", _make_fake_client(captured))
    monkeypatch.setattr(orc, "set_reasoning_call_context", lambda **k: None)

    evidence = [{"evidence_id": f"ev_{i}", "statement": "s", "tier": "T1"} for i in range(8)]
    asyncio.run(m._call_outline(
        "AI labor market displacement", evidence, "fake-model", 0.2, 2500,
        domain="economic",
    ))
    assert len(captured) == 2, "expected a retry (first outline invalid)"
    retry_system = captured[1]
    # the retry must NOT re-inject clinical section names / clinical rules.
    for clinical in ("Efficacy", "Safety", "Regulatory", "SURPASS", "Mechanism must be ADDITIVE"):
        assert clinical not in retry_system, clinical
    # and it must carry the generic outline guidance.
    assert "Key Findings" in retry_system or "Implications" in retry_system


def test_clinical_retry_prompt_is_unchanged(monkeypatch):
    import asyncio

    from src.polaris_graph.llm import openrouter_client as orc

    captured: list[str] = []
    monkeypatch.setattr(orc, "OpenRouterClient", _make_fake_client(captured))
    monkeypatch.setattr(orc, "set_reasoning_call_context", lambda **k: None)

    evidence = [{"evidence_id": f"ev_{i}", "statement": "s", "tier": "T1"} for i in range(8)]
    asyncio.run(m._call_outline(
        "tirzepatide efficacy and safety", evidence, "fake-model", 0.2, 2500,
        domain="clinical",
    ))
    assert len(captured) == 2
    # clinical retry is byte-identical: it still carries the clinical hard requirements.
    assert "Mechanism must be ADDITIVE" in captured[1]
    assert "Efficacy" in captured[1]
