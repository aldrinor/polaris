"""feat/intake-contract — STRUCTURE + PRESENTATION enforcement lane.

The champion compose path (compose_agentic_report_s3gear329 ->
generate_multi_section_report) now compiles the intake contract (floor-only,
llm_fn=None) and, behind the NEW default-OFF flag ``PG_CONTRACT_ENFORCE_STRUCTURE``,
ADDITIVELY shapes the section plan + passes presentation hints to the writer.

These tests prove:
  (a) FLAG OFF  -> compile returns None, injection returns `plans` byte-identical,
      presentation guidance is "" -> the section plan + writer prompt are unchanged
      (no compile work, no plan mutation, no prompt append);
  (b) FLAG ON   -> required_sections are compiled on the compose path, appear/ordered
      as APPENDED candidates in the plan (never dropping/reordering existing plans),
      and presentation hints reach the section WRITER's system prompt;
  (c) NO-FABRICATION firewall -> an injected required section with an EMPTY evidence
      set yields the honest no-evidence gap stub (0 verified sentences, no [CITE:]
      token, no LLM call) — never invented text or citations;
  (d) the enforcement helpers import NO strict_verify / provenance / faithfulness path.

Fully offline/deterministic: regex-only floor compile with llm_fn=None, pure
injection, a fake writer client. No generator run, no network, no LLM, no compose.
"""
from __future__ import annotations

import copy
import dataclasses
import inspect

import pytest

import src.polaris_graph.generator.multi_section_generator as msg
from src.polaris_graph.generator.multi_section_generator import (
    SectionPlan,
    _compile_compose_contract,
    _contract_enforce_structure_enabled,
    _contract_presentation_guidance,
    _inject_required_sections,
    _run_section,
)
from src.polaris_graph.intake.contract_schema import ContractField, IntakeContract

_Q_STRUCTURED = "Compare remote work versus office work and enumerate the main tradeoffs."
_Q_PLAIN = "Write a report on climate policy."


def _base_plans() -> list[SectionPlan]:
    return [
        SectionPlan(
            title="Remote work productivity",
            focus="Evidence on remote work output and focus time.",
            ev_ids=["ev1", "ev2"],
            basket_ids=["b1"],
        ),
        SectionPlan(
            title="Introduction",
            focus="Framing of the question.",
            ev_ids=["ev3"],
        ),
    ]


def _snapshot(plans: list[SectionPlan]):
    return [dataclasses.astuple(p) for p in plans]


def _contract_with_required(titles_dicts) -> IntakeContract:
    c = IntakeContract()
    c.required_sections = [dict(d) for d in titles_dicts]
    return c


# ── (a) FLAG DEFAULT OFF -> everything is a no-op / byte-identical ─────────────

def test_flag_defaults_off(monkeypatch) -> None:
    monkeypatch.delenv("PG_CONTRACT_ENFORCE_STRUCTURE", raising=False)
    assert _contract_enforce_structure_enabled() is False


def test_compile_returns_none_when_flag_off(monkeypatch) -> None:
    monkeypatch.delenv("PG_CONTRACT_ENFORCE_STRUCTURE", raising=False)
    assert _compile_compose_contract(_Q_STRUCTURED) is None


def test_inject_is_noop_when_contract_none(monkeypatch) -> None:
    monkeypatch.delenv("PG_CONTRACT_ENFORCE_STRUCTURE", raising=False)
    plans = _base_plans()
    before = _snapshot(plans)
    out = _inject_required_sections(plans, None, partial_mode=False)
    # Same object list content, byte-identical structure, nothing appended.
    assert _snapshot(out) == before
    assert len(out) == len(plans)


def test_presentation_guidance_empty_when_contract_none() -> None:
    assert _contract_presentation_guidance(None) == ""


def test_presentation_guidance_empty_when_no_fields_set() -> None:
    # A floor-only contract (no LLM) never sets presentation fields.
    assert _contract_presentation_guidance(IntakeContract()) == ""


# ── (b) FLAG ON -> compile on compose path, additive plan shaping, writer hints ─

def test_compile_on_compose_path_only_when_flag_on(monkeypatch) -> None:
    monkeypatch.setenv("PG_CONTRACT_ENFORCE_STRUCTURE", "1")
    c = _compile_compose_contract(_Q_STRUCTURED)
    assert c is not None
    # A structural (comparison/enumeration) prompt yields required_sections at floor.
    assert c.required_sections, "expected required_sections from the structured prompt"
    # A plain prompt compiles to an inert (empty) contract.
    c2 = _compile_compose_contract(_Q_PLAIN)
    assert c2 is not None and c2.is_empty()


def test_inject_appends_missing_required_as_undersupplied_candidate() -> None:
    plans = _base_plans()
    before = _snapshot(plans)
    # A required section NOT covered by the existing plans.
    contract = _contract_with_required([
        {"kind": "structure", "entities": ["Regulatory Landscape"],
         "text": "Regulatory Landscape", "satisfied": False},
    ])
    out = _inject_required_sections(plans, contract, partial_mode=False)
    # ADDITIVE: existing plans are untouched and stay first, in order.
    assert _snapshot(out[: len(plans)]) == before
    # Exactly one candidate appended, AFTER the existing plans.
    assert len(out) == len(plans) + 1
    appended = out[-1]
    assert appended.title == "Regulatory Landscape"
    # FIREWALL shape: empty ev_ids + undersupplied disclosure flag.
    assert appended.ev_ids == []
    assert appended.undersupplied is True
    # satisfied annotation flipped False (uncovered).
    assert contract.required_sections[0]["satisfied"] is False


def test_inject_covered_slot_flips_satisfied_and_appends_nothing() -> None:
    plans = _base_plans()
    before = _snapshot(plans)
    # "Remote work" is already covered by the first plan's title.
    contract = _contract_with_required([
        {"kind": "structure", "entities": ["Remote work"],
         "text": "Remote work", "satisfied": False},
    ])
    out = _inject_required_sections(plans, contract, partial_mode=False)
    # Nothing appended, existing plans byte-identical (never dropped/reordered).
    assert _snapshot(out) == before
    assert contract.required_sections[0]["satisfied"] is True


def test_inject_never_drops_or_reorders_existing_plans() -> None:
    plans = _base_plans()
    before_titles = [p.title for p in plans]
    contract = _contract_with_required([
        {"kind": "structure", "entities": ["Brand New Topic"],
         "text": "Brand New Topic", "satisfied": False},
        {"kind": "structure", "entities": ["Another New One"],
         "text": "Another New One", "satisfied": False},
    ])
    out = _inject_required_sections(plans, contract, partial_mode=False)
    assert [p.title for p in out][: len(plans)] == before_titles
    assert [p.title for p in out][len(plans):] == ["Brand New Topic", "Another New One"]


def test_inject_noop_under_partial_mode() -> None:
    plans = _base_plans()
    before = _snapshot(plans)
    contract = _contract_with_required([
        {"kind": "structure", "entities": ["Regulatory Landscape"],
         "text": "Regulatory Landscape", "satisfied": False},
    ])
    out = _inject_required_sections(plans, contract, partial_mode=True)
    assert _snapshot(out) == before  # partial_mode suppresses injection


def test_inject_noop_when_contract_empty() -> None:
    plans = _base_plans()
    before = _snapshot(plans)
    out = _inject_required_sections(plans, IntakeContract(), partial_mode=False)
    assert _snapshot(out) == before


def test_presentation_guidance_renders_set_fields() -> None:
    c = IntakeContract()
    c.format = ContractField(value="literature review", origin="user_explicit", strength="hard")
    c.length = ContractField(value="concise", origin="user_explicit", strength="hard")
    c.tone = ContractField(value="formal", origin="user_explicit", strength="soft")
    g = _contract_presentation_guidance(c)
    assert "literature review" in g and "concise" in g and "formal" in g
    # NON-BINDING framing that reasserts the faithfulness contract.
    assert "NON-BINDING" in g


@pytest.mark.asyncio
async def test_presentation_guidance_reaches_the_writer(monkeypatch) -> None:
    """The presentation guidance string is appended to the WRITER's system prompt
    (downstream of strict_verify). Fake the client to capture `system`."""
    captured: dict[str, str] = {}

    class _FakeResp:
        content = "A grounded sentence."
        input_tokens = 1
        output_tokens = 1

    class _FakeClient:
        def __init__(self, *a, **k):
            pass

        async def generate(self, *, prompt, system, **k):  # noqa: ANN001
            captured["system"] = system
            return _FakeResp()

        async def close(self):
            pass

    import src.polaris_graph.llm.openrouter_client as orc
    monkeypatch.setattr(orc, "OpenRouterClient", _FakeClient)

    section = SectionPlan(title="Body", focus="A body section.", ev_ids=["ev1"])
    ev_subset = [{
        "evidence_id": "ev1", "statement": "A claim.", "direct_quote": "A claim.",
        "source_url": "http://x", "tier": "T1",
    }]
    _c = IntakeContract()
    _c.length = ContractField(value="concise")
    guidance = _contract_presentation_guidance(_c)
    assert guidance  # sanity
    await msg._call_section(
        section, ev_subset, model="fake/model", temperature=0.2, max_tokens=256,
        presentation_guidance=guidance,
    )
    assert "system" in captured
    assert guidance in captured["system"], "presentation guidance must reach the writer prompt"


@pytest.mark.asyncio
async def test_writer_prompt_unchanged_when_guidance_empty(monkeypatch) -> None:
    """Flag-off equivalent: presentation_guidance="" appends NOTHING to the system."""
    captured: dict[str, str] = {}

    class _FakeResp:
        content = "x."
        input_tokens = 1
        output_tokens = 1

    class _FakeClient:
        def __init__(self, *a, **k):
            pass

        async def generate(self, *, prompt, system, **k):  # noqa: ANN001
            captured["system"] = system
            return _FakeResp()

        async def close(self):
            pass

    import src.polaris_graph.llm.openrouter_client as orc
    monkeypatch.setattr(orc, "OpenRouterClient", _FakeClient)

    section = SectionPlan(title="Body", focus="A body section.", ev_ids=["ev1"])
    ev_subset = [{
        "evidence_id": "ev1", "statement": "A claim.", "direct_quote": "A claim.",
        "source_url": "http://x", "tier": "T1",
    }]
    await msg._call_section(
        section, ev_subset, model="fake/model", temperature=0.2, max_tokens=256,
        presentation_guidance="",
    )
    assert "PRESENTATION GUIDANCE" not in captured["system"]


# ── (c) NO-FABRICATION firewall: injected empty-evidence section stays honest ──

@pytest.mark.asyncio
async def test_injected_empty_evidence_section_yields_honest_gap_stub(monkeypatch) -> None:
    """An injected required section (ev_ids=[]) with an empty evidence pool renders
    the honest no-evidence gap stub — NEVER fabricated prose or citations, and NO
    LLM call. Proves the faithfulness firewall for a forced-but-unsupported section."""
    # Trip a hard failure if any LLM client is constructed on this path.
    import src.polaris_graph.llm.openrouter_client as orc

    class _NoCall:
        def __init__(self, *a, **k):
            raise AssertionError("no LLM must be called for an empty-evidence section")

    monkeypatch.setattr(orc, "OpenRouterClient", _NoCall)

    injected = SectionPlan(title="Regulatory Landscape", focus="Regulatory Landscape",
                           ev_ids=[], undersupplied=True)
    result = await _run_section(
        injected, {},  # empty evidence pool -> empty ev_subset
        model="fake/model", temperature=0.2, max_tokens_per_section=256,
        min_kept_fraction=0.4,
    )
    # Honest degradation: the gap stub, zero verified sentences, disclosed gap.
    assert result.sentences_verified == 0
    assert getattr(result, "is_gap_stub", False) is True
    assert result.verified_text == msg._NO_EVIDENCE_GAP_STUB_SENTENCE
    # NO fabricated citation token leaked into the section text.
    assert "[CITE:" not in result.verified_text
    assert result.biblio_slice == []


# ── (d) faithfulness firewall: enforcement helpers touch no verify path ───────

def _code_only(src: str) -> str:
    """Return ``src`` with comments and string literals (incl. docstrings) removed,
    so a firewall keyword mentioned in EXPLANATORY prose does not false-positive."""
    import io
    import tokenize

    out: list[str] = []
    toks = tokenize.generate_tokens(io.StringIO(src).readline)
    for tok in toks:
        if tok.type in (tokenize.COMMENT, tokenize.STRING):
            continue
        out.append(tok.string)
    return " ".join(out)


def test_enforcement_helpers_import_no_faithfulness_module() -> None:
    for fn in (_compile_compose_contract, _inject_required_sections,
               _contract_presentation_guidance, _contract_enforce_structure_enabled):
        code = _code_only(inspect.getsource(fn))
        for forbidden in ("strict_verify", "provenance", "_audit_citations",
                          "source_rules"):
            assert forbidden not in code, f"{fn.__name__} must not touch {forbidden}"
