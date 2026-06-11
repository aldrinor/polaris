"""I-perm-016 (#1209) — map-reduce evidence distiller unit tests.

Covers the buildspec section 7 deterministic units (offline; no live LLM):

  1. Flag OFF -> _call_section receives the SAME raw evidence blocks as legacy
     (byte-identical legacy path; no distillate import/effect).
  2. MAP validation rejects: fake support_quote, bad offsets, out-of-span
     numbers, and non-entailed claims (the entailment gate keyed off
     PG_STRICT_VERIFY_ENTAILMENT=enforce + a monkeypatched judge).
  3. no_relevant_findings creates a coverage row; no source disappears.
  4. REDUCE formatter contains ledger rows, NOT <<<evidence:...>>> raw blocks.
  5. filter_and_strip_reduce_markers drops uncited reducer prose AND strips the
     [[finding:...]] markers before unchanged strict verification.

The drb_76 replay (buildspec item 8) is a PAID-run acceptance gate (operator-
authorized live run), NOT an offline unit — no live call, no fabricated replay
fixtures (LAW II).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

import src.polaris_graph.clinical_generator.strict_verify as strict_verify_mod
from src.polaris_graph.generator import evidence_distiller as ed
from src.polaris_graph.generator.evidence_distiller import (
    CoverageRow,
    DistilledFinding,
    SectionDistillate,
    distill_section_evidence,
    filter_and_strip_reduce_markers,
    render_reduce_user,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@dataclass
class _Section:
    title: str
    focus: str


_EV_ID = "ev_001"
_DIRECT_QUOTE = (
    "The estimated mean change from baseline in HbA1c at 40 weeks was -1.86 "
    "percentage points with semaglutide. Adverse events occurred in 43% of all "
    "participants."
)
_EV_ROW = {
    "evidence_id": _EV_ID,
    "tier": "T1",
    "statement": "Tirzepatide versus Semaglutide in Type 2 Diabetes",
    "direct_quote": _DIRECT_QUOTE,
    "source_url": "https://example.org/surpass2",
}
_POOL = {_EV_ID: _EV_ROW}
_SECTION = _Section(title="Efficacy", focus="HbA1c efficacy of semaglutide")


class _FakeJudge:
    """Stand-in for the entailment judge. verdict is fixed per instance."""

    def __init__(self, verdict: str = "ENTAILED", reason: str = "ok"):
        self._verdict = verdict
        self._reason = reason

    def judge(self, sentence: str, span: str) -> tuple[str, str]:
        return self._verdict, self._reason


def _enforce_entailment(monkeypatch, verdict: str = "ENTAILED") -> None:
    """Put the entailment gate in enforce mode with a deterministic judge.

    The production verifier path (provenance_generator.verify_sentence_provenance)
    lazy-imports `_get_judge` + `_entailment_mode` from clinical_generator.
    strict_verify, so monkeypatching THAT module's `_get_judge` propagates.
    """
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    # Reset the unknown-mode warn cache (defensive; not load-bearing).
    monkeypatch.setattr(strict_verify_mod, "_get_judge", lambda: _FakeJudge(verdict),
                        raising=True)


def _make_map_client(monkeypatch, payload: dict, *, content_json: str | None = None):
    """Monkeypatch OpenRouterClient so the MAP _call returns a fixed JSON object.

    `payload` is serialized to the response content unless `content_json` is given
    (used to inject malformed/edge-case JSON).
    """
    import json as _json

    import src.polaris_graph.llm.openrouter_client as orc

    body = content_json if content_json is not None else _json.dumps(payload)

    class _FakeResp:
        content = body
        reasoning = None
        input_tokens = 11
        output_tokens = 7

    class _FakeClient:
        def __init__(self, *a, **k):
            pass

        async def _call(self, *a, **k):
            return _FakeResp()

        async def close(self):
            return None

    monkeypatch.setattr(orc, "OpenRouterClient", _FakeClient, raising=True)


# ---------------------------------------------------------------------------
# Test 1: flag OFF -> _call_section gets the SAME raw evidence blocks as legacy
# ---------------------------------------------------------------------------

def test_flag_off_call_section_uses_raw_evidence_blocks(monkeypatch):
    """With distillate=None, _call_section must build the legacy raw
    <<<evidence:...>>> blocks and never touch the distiller."""
    monkeypatch.delenv("PG_SECTION_DISTILL", raising=False)

    import src.polaris_graph.generator.multi_section_generator as msg

    # Confirm the flag reads OFF.
    assert msg._section_distill_enabled() is False

    captured = {}

    class _Resp:
        content = "Semaglutide reduced HbA1c by -1.86 percentage points [ev_001]."
        input_tokens = 5
        output_tokens = 9
        reasoning = None

    class _CaptureClient:
        def __init__(self, *a, **k):
            pass

        async def generate(self, prompt, system, max_tokens, temperature, **k):
            captured["prompt"] = prompt
            captured["system"] = system
            return _Resp()

        async def close(self):
            return None

    import src.polaris_graph.llm.openrouter_client as orc
    monkeypatch.setattr(orc, "OpenRouterClient", _CaptureClient, raising=True)

    from src.polaris_graph.generator.multi_section_generator import (
        SectionPlan, _call_section,
    )
    sec = SectionPlan(title="Efficacy", focus="HbA1c", ev_ids=[_EV_ID])

    raw, _in, _out, atoms = asyncio.run(_call_section(
        sec, [_EV_ROW], "deepseek/deepseek-v4-pro", 0.3, 4096,
        # distillate defaults to None -> legacy path
    ))

    # The legacy raw evidence block delimiter must be in the prompt.
    assert "<<<evidence:ev_001>>>" in captured["prompt"]
    assert _DIRECT_QUOTE in captured["prompt"]
    # And NO REDUCE ledger artifacts.
    assert "VALIDATED_FINDINGS_LEDGER" not in captured["prompt"]
    assert "[[finding:" not in captured["prompt"]


# ---------------------------------------------------------------------------
# Test 2: MAP validation fail-closed (4 rejection modes)
# ---------------------------------------------------------------------------

def test_map_rejects_fake_support_quote(monkeypatch):
    """A support_quote that is NOT a substring of direct_quote is rejected ->
    validation_failed coverage row, zero findings."""
    _enforce_entailment(monkeypatch, "ENTAILED")
    payload = {
        "evidence_id": _EV_ID,
        "no_relevant_findings": False,
        "findings": [{
            "claim": "Semaglutide reduced HbA1c by -1.86 percentage points.",
            "support_quote": "this text is not in the direct quote at all",
            "span_start": 0, "span_end": 10,
            "numbers": ["-1.86"], "entities": ["semaglutide"],
            "caveat": "", "contradiction_key": "", "source_tier": "T1",
        }],
    }
    _make_map_client(monkeypatch, payload)
    monkeypatch.setattr(ed, "_default_cache_dir", lambda: __import__("pathlib").Path(
        __import__("tempfile").mkdtemp()))

    dist = asyncio.run(distill_section_evidence(
        _SECTION, [_EV_ROW], _POOL, model="m",
    ))
    assert dist.findings == []
    assert len(dist.coverage) == 1
    assert dist.coverage[0].status == "validation_failed"
    assert dist.coverage[0].evidence_id == _EV_ID


def test_map_rejects_out_of_span_numbers(monkeypatch):
    """A claim asserting a number that is NOT in the support span is rejected."""
    _enforce_entailment(monkeypatch, "ENTAILED")
    payload = {
        "evidence_id": _EV_ID,
        "no_relevant_findings": False,
        "findings": [{
            # 99.9 is not anywhere in the support span.
            "claim": "Semaglutide reduced HbA1c by 99.9 percentage points.",
            "support_quote": "-1.86 percentage points with semaglutide",
            "span_start": 0, "span_end": 0,
            "numbers": ["99.9"], "entities": ["semaglutide"],
            "caveat": "", "contradiction_key": "", "source_tier": "T1",
        }],
    }
    _make_map_client(monkeypatch, payload)
    monkeypatch.setattr(ed, "_default_cache_dir", lambda: __import__("pathlib").Path(
        __import__("tempfile").mkdtemp()))

    dist = asyncio.run(distill_section_evidence(
        _SECTION, [_EV_ROW], _POOL, model="m",
    ))
    assert dist.findings == []
    assert dist.coverage[0].status == "validation_failed"


def test_map_rejects_non_entailed_claim(monkeypatch):
    """A claim the entailment judge marks NEUTRAL is rejected in enforce mode."""
    _enforce_entailment(monkeypatch, "NEUTRAL")  # judge says NOT entailed
    payload = {
        "evidence_id": _EV_ID,
        "no_relevant_findings": False,
        "findings": [{
            "claim": "Semaglutide reduced HbA1c by -1.86 percentage points.",
            "support_quote": "-1.86 percentage points with semaglutide",
            "span_start": 0, "span_end": 0,
            "numbers": ["-1.86"], "entities": ["semaglutide"],
            "caveat": "", "contradiction_key": "", "source_tier": "T1",
        }],
    }
    _make_map_client(monkeypatch, payload)
    monkeypatch.setattr(ed, "_default_cache_dir", lambda: __import__("pathlib").Path(
        __import__("tempfile").mkdtemp()))

    dist = asyncio.run(distill_section_evidence(
        _SECTION, [_EV_ROW], _POOL, model="m",
    ))
    assert dist.findings == []
    assert dist.coverage[0].status == "validation_failed"


def test_map_rejects_bad_offsets_uncorrectable(monkeypatch):
    """When the quote is NOT a substring at all, offset correction can't rescue
    it -> rejected. (The offset-correction success path is exercised by the
    accept test below.)"""
    _enforce_entailment(monkeypatch, "ENTAILED")
    payload = {
        "evidence_id": _EV_ID,
        "no_relevant_findings": False,
        "findings": [{
            "claim": "Adverse events occurred in 43% of all participants.",
            # support_quote text altered so it is no longer a substring.
            "support_quote": "Adverse events occurred in 43% of NObody",
            "span_start": 999, "span_end": 1099,  # nonsense offsets too
            "numbers": ["43"], "entities": [],
            "caveat": "", "contradiction_key": "", "source_tier": "T1",
        }],
    }
    _make_map_client(monkeypatch, payload)
    monkeypatch.setattr(ed, "_default_cache_dir", lambda: __import__("pathlib").Path(
        __import__("tempfile").mkdtemp()))

    dist = asyncio.run(distill_section_evidence(
        _SECTION, [_EV_ROW], _POOL, model="m",
    ))
    assert dist.findings == []
    assert dist.coverage[0].status == "validation_failed"


def test_map_accepts_valid_finding_with_offset_correction(monkeypatch):
    """A valid finding whose offsets DISAGREE but whose quote is an exact
    substring is accepted with offsets corrected to the first occurrence."""
    _enforce_entailment(monkeypatch, "ENTAILED")
    support = "-1.86 percentage points with semaglutide"
    true_start = _DIRECT_QUOTE.find(support)
    assert true_start > 0  # the LLM's 0/0 offsets are WRONG; correction needed
    payload = {
        "evidence_id": _EV_ID,
        "no_relevant_findings": False,
        "findings": [{
            "claim": "HbA1c fell by -1.86 percentage points with semaglutide.",
            "support_quote": support,
            "span_start": 0, "span_end": 0,  # wrong; quote is mid-string
            "numbers": ["-1.86"], "entities": ["semaglutide"],
            "caveat": "", "contradiction_key": "", "source_tier": "T1",
        }],
    }
    _make_map_client(monkeypatch, payload)
    monkeypatch.setattr(ed, "_default_cache_dir", lambda: __import__("pathlib").Path(
        __import__("tempfile").mkdtemp()))

    dist = asyncio.run(distill_section_evidence(
        _SECTION, [_EV_ROW], _POOL, model="m",
    ))
    assert len(dist.findings) == 1
    f = dist.findings[0]
    # Offsets corrected to the real first occurrence; slice == support_quote.
    assert f.span_start == true_start
    assert _DIRECT_QUOTE[f.span_start:f.span_end] == support
    # Numeric finding mapped to a section-local atom (atom_002, value -1.86).
    assert f.atom_ids, "numeric finding must carry >=1 section atom"
    assert dist.coverage[0].status == "mapped"


# ---------------------------------------------------------------------------
# Test 3: no_relevant_findings -> coverage row, no source disappears
# ---------------------------------------------------------------------------

def test_no_relevant_findings_creates_coverage_row(monkeypatch):
    _enforce_entailment(monkeypatch, "ENTAILED")
    payload = {
        "evidence_id": _EV_ID,
        "no_relevant_findings": True,
        "no_relevant_reason": "source is off-topic for this section",
        "findings": [],
    }
    _make_map_client(monkeypatch, payload)
    monkeypatch.setattr(ed, "_default_cache_dir", lambda: __import__("pathlib").Path(
        __import__("tempfile").mkdtemp()))

    dist = asyncio.run(distill_section_evidence(
        _SECTION, [_EV_ROW], _POOL, model="m",
    ))
    assert dist.findings == []
    # Exactly one coverage row for the one input source — nothing disappears.
    assert len(dist.coverage) == 1
    assert dist.coverage[0].evidence_id == _EV_ID
    assert dist.coverage[0].status == "no_relevant_findings"
    assert "off-topic" in dist.coverage[0].reason


def test_every_input_row_has_a_coverage_row_or_finding(monkeypatch):
    """Two sources, one mapped + one no_relevant -> both accounted for."""
    _enforce_entailment(monkeypatch, "ENTAILED")
    ev2 = dict(_EV_ROW, evidence_id="ev_002")

    import json as _json
    import src.polaris_graph.llm.openrouter_client as orc

    def _payload_for(ev_id):
        if ev_id == _EV_ID:
            return {
                "evidence_id": _EV_ID, "no_relevant_findings": False,
                "findings": [{
                    "claim": "HbA1c fell by -1.86 percentage points with semaglutide.",
                    "support_quote": "-1.86 percentage points with semaglutide",
                    "span_start": 0, "span_end": 0, "numbers": ["-1.86"],
                    "entities": [], "caveat": "", "contradiction_key": "",
                    "source_tier": "T1",
                }],
            }
        return {"evidence_id": ev_id, "no_relevant_findings": True,
                "no_relevant_reason": "off-topic", "findings": []}

    class _Resp:
        def __init__(self, body):
            self.content = body
            self.reasoning = None
            self.input_tokens = 3
            self.output_tokens = 2

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def _call(self, *, messages, **k):
            user = messages[1]["content"]
            ev_id = "ev_002" if "ev_002" in user else _EV_ID
            return _Resp(_json.dumps(_payload_for(ev_id)))

        async def close(self):
            return None

    monkeypatch.setattr(orc, "OpenRouterClient", _Client, raising=True)
    monkeypatch.setattr(ed, "_default_cache_dir", lambda: __import__("pathlib").Path(
        __import__("tempfile").mkdtemp()))

    dist = asyncio.run(distill_section_evidence(
        _SECTION, [_EV_ROW, ev2], {_EV_ID: _EV_ROW, "ev_002": ev2}, model="m",
    ))
    covered = {c.evidence_id for c in dist.coverage} | {f.evidence_id for f in dist.findings}
    assert covered == {_EV_ID, "ev_002"}


# ---------------------------------------------------------------------------
# Test 4: REDUCE formatter contains ledger rows, not raw quote blocks
# ---------------------------------------------------------------------------

def test_reduce_formatter_has_ledger_rows_not_raw_evidence_blocks():
    f = DistilledFinding(
        finding_id="f001_000", evidence_id=_EV_ID,
        claim="HbA1c fell by -1.86 percentage points with semaglutide.",
        span_start=10, span_end=51,
        support_quote="-1.86 percentage points with semaglutide",
        numbers=["-1.86"], entities=["semaglutide"], caveat="",
        contradiction_key="", source_tier="T1", atom_ids=["atom_002"],
    )
    dist = SectionDistillate(
        section_title="Efficacy", section_focus="HbA1c",
        findings=[f], coverage=[], contradiction_clusters=[],
        atom_catalog={},
    )
    rendered = render_reduce_user(dist)
    assert "VALIDATED_FINDINGS_LEDGER" in rendered
    assert "f001_000 | ev_001 | T1 |" in rendered
    assert "atom_ids=atom_002" in rendered
    # NO raw evidence delimiter blocks.
    assert "<<<evidence:" not in rendered
    assert "<<<end_evidence>>>" not in rendered


# ---------------------------------------------------------------------------
# Test 5: filter_and_strip_reduce_markers drops uncited prose + strips markers
# ---------------------------------------------------------------------------

def test_filter_strips_markers_and_drops_uncited_prose():
    f = DistilledFinding(
        finding_id="f001_000", evidence_id=_EV_ID,
        claim="HbA1c fell by -1.86 pp.", span_start=10, span_end=51,
        support_quote="-1.86 percentage points with semaglutide",
        numbers=["-1.86"], entities=[], caveat="",
        contradiction_key="", source_tier="T1", atom_ids=["atom_002"],
    )
    dist = SectionDistillate(
        section_title="Efficacy", section_focus="HbA1c",
        findings=[f], coverage=[], contradiction_clusters=[], atom_catalog={},
    )
    # 3 sentences:
    #  (1) cited finding + matching full token -> KEPT, marker stripped.
    #  (2) uncited reducer prose -> DROPPED.
    #  (3) finding marker for an UNKNOWN finding id -> DROPPED.
    raw = (
        "HbA1c fell by -1.86 percentage points [[finding:f001_000]] "
        "[#ev:ev_001:10-51]. "
        "Overall the drug shows broad metabolic benefit. "
        "Weight also improved markedly [[finding:f999_999]] [#ev:ev_001:0-5]."
    )
    out = filter_and_strip_reduce_markers(raw, dist)

    # Finding markers stripped entirely.
    assert "[[finding:" not in out
    # The cited sentence survived with its full provenance token intact.
    assert "[#ev:ev_001:10-51]" in out
    assert "HbA1c fell by -1.86 percentage points" in out
    # Uncited prose dropped.
    assert "broad metabolic benefit" not in out
    # Unknown-finding sentence dropped.
    assert "Weight also improved" not in out


def test_filter_returns_empty_for_all_uncited():
    dist = SectionDistillate(
        section_title="Efficacy", section_focus="HbA1c",
        findings=[], coverage=[], contradiction_clusters=[], atom_catalog={},
    )
    raw = "This is uncited prose. So is this."
    assert filter_and_strip_reduce_markers(raw, dist) == ""


# ---------------------------------------------------------------------------
# Test 12 (Codex diff-gate iter-1 P1 ruling): a numeric finding with NO
# section-local atom is KEPT with empty atom_ids, not rejected — the entailment
# gate still runs, so faithfulness holds and coverage is not shed on a
# cataloguing artifact (the safety/incidence-heavy drb_76 failure mode).
# ---------------------------------------------------------------------------

def test_validate_finding_keeps_numeric_without_section_atom(monkeypatch):
    _enforce_entailment(monkeypatch, "ENTAILED")
    # "43%" lives in _DIRECT_QUOTE but section_atoms is EMPTY (the atom routes to a
    # different primary_section), so _match_atom_ids returns [] for this number.
    raw = {
        "claim": "Adverse events occurred in 43% of all participants.",
        "support_quote": "Adverse events occurred in 43% of all participants",
        "span_start": 0, "span_end": 0, "numbers": ["43"],
        "entities": [], "caveat": "", "contradiction_key": "", "source_tier": "T1",
    }
    result = ed._validate_finding(
        raw, evidence_id=_EV_ID, direct_quote=_DIRECT_QUOTE, tier="T1",
        evidence_pool=_POOL, section_atoms={}, finding_id="f001_001",
    )
    # KEPT (not None) with empty atom_ids — the old code returned None here.
    assert result is not None
    assert result.atom_ids == []
    assert "43" in result.numbers


# ---------------------------------------------------------------------------
# Test 13 (Codex diff-gate iter-1 P2): the marker-strip filter binds the
# [#ev:...] token to the CITED finding's evidence_id — a real finding marker
# paired with a token from a DIFFERENT source is dropped; the same prose with
# the matching-source token survives.
# ---------------------------------------------------------------------------

def test_filter_drops_marker_with_mismatched_source_token():
    f = DistilledFinding(
        finding_id="f001_000", evidence_id=_EV_ID,
        claim="HbA1c fell by -1.86 pp.", span_start=10, span_end=51,
        support_quote="-1.86 percentage points with semaglutide",
        numbers=["-1.86"], entities=[], caveat="",
        contradiction_key="", source_tier="T1", atom_ids=[],
    )
    dist = SectionDistillate(
        section_title="Efficacy", section_focus="HbA1c",
        findings=[f], coverage=[], contradiction_clusters=[], atom_catalog={},
    )
    raw = (
        "HbA1c fell by -1.86 percentage points [[finding:f001_000]] "
        "[#ev:ev_777:0-5]. "
        "HbA1c fell by -1.86 percentage points [[finding:f001_000]] "
        "[#ev:ev_001:10-51]."
    )
    out = filter_and_strip_reduce_markers(raw, dist)
    # Mismatched-source token sentence dropped; matching-source one kept.
    assert "[#ev:ev_777:0-5]" not in out
    assert "[#ev:ev_001:10-51]" in out


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
