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
from src.polaris_graph.generator.live_deepseek_generator import _rewrite_draft_with_spans
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


def test_map_keeps_out_of_span_numbers_nonblocking_1217(monkeypatch):
    """#1217 (RECALL fix, Claude+Codex independent re-forensics AGREE on candidate
    (b)): the MAP numbers-in-span pre-filter is NON-BLOCKING. A finding whose
    declared number is not inside the NARROW model support_quote is now KEPT in the
    ledger (was rejected pre-1217) — exactly mirroring the step-(6) entailment
    treatment. This narrow-span pre-filter was STRICTER than the final gate and pure
    recall loss with zero faithfulness benefit: it collapsed distill recall below
    legacy on the drb_76 Safety replay (legacy kept 6 numeric sentences; distill kept
    only the 1 non-numeric claim). Faithfulness is UNCHANGED — a genuinely fabricated
    number CANNOT reach the published report through this path because the final
    per-sentence strict_verify on the REDUCE prose (require_number_match=True,
    re-fitting an 800-char prose-matched span over the WHOLE direct_quote) is the SOLE
    publication authority and drops any number not present in the source span. The
    real "source slice exists" gate (step 1, _locate_span_in_source) is UNCHANGED and
    still rejects a quote that is not in the source (see
    test_map_rejects_bad_offsets_uncorrectable)."""
    _enforce_entailment(monkeypatch, "ENTAILED")
    payload = {
        "evidence_id": _EV_ID,
        "no_relevant_findings": False,
        "findings": [{
            # 99.9 is not anywhere in the narrow support_quote; KEPT at MAP now,
            # the final strict_verify on the REDUCE prose is the number gate.
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
    # KEPT now (was rejected pre-1217): the extraction filter admits it; the final
    # strict_verify on the REDUCE output is the authority on the published number.
    assert len(dist.findings) == 1
    assert dist.findings[0].numbers == ["99.9"]


def test_map_keeps_non_entailed_finding_h1(monkeypatch):
    """#1217 (H1, Claude+Codex AGREE): a finding the PER-FINDING entailment judge
    marks NEUTRAL is now KEPT in the ledger — the per-finding entailment is
    non-blocking. It still passed the extraction filter (located REAL span +
    numbers-in-span); the FINAL per-sentence strict_verify on the REDUCE prose is
    the SOLE publication authority, so a non-entailed claim cannot reach the
    published report through this path. (Running strict_verify once per finding AND
    again per sentence starved the reducer -> section collapse on two live runs.)"""
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
    # KEPT now (was rejected pre-H1): extraction filter admits it; the final
    # strict_verify on the REDUCE output is the authority.
    assert len(dist.findings) == 1
    assert dist.findings[0].numbers == ["-1.86"]


def test_map_rejects_fabricated_claim_absent_from_source(monkeypatch):
    """#1217: a finding whose content is GENUINELY ABSENT from the source is rejected
    at step 1 — even fuzzy content-overlap recovery returns None (no window meets the
    overlap threshold), so no span is admitted. This preserves the core invariant
    'unsupported content -> reject' after the fuzzy-recovery recall fix. (Faithful
    paraphrases that DO overlap a real passage are exercised by the recover/entail
    tests below.)"""
    _enforce_entailment(monkeypatch, "ENTAILED")
    payload = {
        "evidence_id": _EV_ID,
        "no_relevant_findings": False,
        "findings": [{
            # Nothing about pembrolizumab/melanoma/survival is in _DIRECT_QUOTE.
            "claim": "Pembrolizumab tripled overall survival in metastatic melanoma.",
            "support_quote": "Pembrolizumab tripled overall survival in metastatic melanoma",
            "span_start": 999, "span_end": 1099,  # nonsense offsets too
            "numbers": [], "entities": [],
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
    assert "cite=[ev_001]" in rendered
    assert "atom_ids=atom_002" in rendered
    assert "[#ev:ev_" not in rendered
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
    #  (1) cited finding + evidence marker -> KEPT, marker stripped.
    #  (2) uncited reducer prose -> DROPPED.
    #  (3) finding marker for an UNKNOWN finding id -> DROPPED.
    raw = (
        "HbA1c fell by -1.86 percentage points [[finding:f001_000]] "
        "[ev_001]. "
        "Overall the drug shows broad metabolic benefit. "
        "Weight also improved markedly [[finding:f999_999]] [ev_001]."
    )
    out = filter_and_strip_reduce_markers(raw, dist)

    # Finding markers stripped entirely.
    assert "[[finding:" not in out
    # The cited sentence survived with its legacy evidence marker intact.
    assert "[ev_001]" in out
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
# Test 13: the marker-strip filter is permissive about evidence-marker source;
# strict_verify downstream remains the authority on whether the rebound token is
# valid against the pool.
# ---------------------------------------------------------------------------

def test_filter_keeps_cited_sentence_regardless_of_marker_source():
    # #1217: the marker-strip filter is PERMISSIVE — a sentence with a known
    # finding marker + ANY evidence marker survives; strict_verify downstream is
    # the authority on whether the rebound token is valid against the pool.
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
        "HbA1c fell by -1.86 percentage points [[finding:f001_000]] [ev_777]. "
        "HbA1c fell by -1.86 percentage points [[finding:f001_000]] [ev_001]."
    )
    out = filter_and_strip_reduce_markers(raw, dist)
    # BOTH cited sentences survive the permissive filter; strict_verify is the
    # authority (it would drop a token not valid against the pool downstream).
    assert "[ev_777]" in out
    assert "[ev_001]" in out
    # An UNcited sentence (no finding marker / no token) is still dropped.
    assert filter_and_strip_reduce_markers("Plain prose with no markers.", dist) == ""


def test_filter_reattaches_orphaned_marker_fragment_1217_bug_a():
    """#1217 Bug A (Claude live-repro on the VM + Codex independent confirm): when the
    REDUCE places its [[finding]]/[ev] markers in their OWN sentence AFTER the claim's
    terminal period, split_into_sentences yields a marker-only fragment. The OLD filter
    kept that fragment (it carries the markers) and DROPPED the claim sentence (no
    marker) -> output was a bare '[ev_...]' marker -> strict_verify dropped it -> 0
    verified -> placeholder -> TOTAL section collapse (distill 0 vs legacy 11 on the
    paid VM A/B). The pre-pass now REATTACHES the orphaned fragment to the preceding
    sentence so the claim prose survives WITH its marker. This is the EXACT string from
    the VM PG_DISTILL_DEBUG dump."""
    f = DistilledFinding(
        finding_id="f002_000", evidence_id="ev_colibactin_pks_ecoli_mechanism",
        claim="Colibactin induces double-strand breaks in cultured cells.",
        span_start=0, span_end=10, support_quote="x",
        numbers=[], entities=[], caveat="",
        contradiction_key="", source_tier="T1", atom_ids=[],
    )
    dist = SectionDistillate(
        section_title="Safety and contraindications", section_focus="",
        findings=[f], coverage=[], contradiction_clusters=[], atom_catalog={},
    )
    raw = (
        "Colibactin induces double-strand breaks in cultured cells. "
        "[[finding:f002_000]] [ev_colibactin_pks_ecoli_mechanism]"
    )
    out = filter_and_strip_reduce_markers(raw, dist)
    # The claim PROSE survives, carrying its [ev_XXX] marker; the [[finding]] is stripped.
    assert "Colibactin induces double-strand breaks in cultured cells" in out
    assert "[ev_colibactin_pks_ecoli_mechanism]" in out
    assert "[[finding" not in out
    # Regression guard: the output is NOT a bare marker (the pre-1217 collapse signature).
    assert out.strip() != "[ev_colibactin_pks_ecoli_mechanism]"


def test_filter_does_not_reattach_to_create_false_attribution_1217():
    """The reattach pre-pass must only MOVE an orphaned marker fragment onto the
    immediately preceding sentence; it must NOT invent attribution. A leading
    marker-only fragment with no preceding sentence is dropped (no prose to keep), and
    a normal inline-cited sentence is unaffected. Faithfulness: strict_verify still
    re-binds and re-verifies the reassembled sentence's span downstream."""
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
    # A leading orphaned marker (nothing before it) is dropped, not attached to nothing.
    assert filter_and_strip_reduce_markers(
        "[[finding:f001_000]] [ev_001]", dist
    ) == ""
    # A normal inline-cited sentence is unchanged by the pre-pass.
    out = filter_and_strip_reduce_markers(
        "HbA1c fell by -1.86 percentage points [[finding:f001_000]] [ev_001].", dist
    )
    assert "HbA1c fell by -1.86 percentage points" in out
    assert "[ev_001]" in out


def test_filter_normalizes_stale_full_tokens_before_span_rewrite():
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
        "HbA1c fell by -1.86 percentage points with semaglutide "
        "[[finding:f001_000]] [#ev:ev_001:10-51]."
    )
    filtered = filter_and_strip_reduce_markers(raw, dist)
    assert "[#ev:" not in filtered
    assert "[ev_001]" in filtered

    rewritten, converted, unverifiable = _rewrite_draft_with_spans(filtered, _POOL)
    assert converted == 1
    assert unverifiable == 0
    assert "[#ev:ev_001:10-51]" not in rewritten
    assert f"[#ev:ev_001:0-{len(_DIRECT_QUOTE)}]" in rewritten


# ---------------------------------------------------------------------------
# Test 14 (#1217): MAP span-recovery — a whitespace-reformatted quote is
# recovered to the REAL source slice and KEPT; a paraphrased quote is recovered
# by FUZZY content-overlap but must additionally ENTAIL the claim (the fuzzy
# faithfulness gate) — a meaning-changing paraphrase that is not entailed is
# rejected.
# ---------------------------------------------------------------------------

def test_validate_finding_recovers_whitespace_reformatted_quote(monkeypatch):
    _enforce_entailment(monkeypatch, "ENTAILED")
    # The MAP model reformats whitespace (newline + double space) in the quote;
    # the real source has "occurred in 43% of all participants".
    raw = {
        "claim": "Adverse events occurred in 43% of all participants.",
        "support_quote": "occurred in 43%\nof all  participants",
        "span_start": 0, "span_end": 0, "numbers": ["43"],
        "entities": [], "caveat": "", "contradiction_key": "", "source_tier": "T1",
    }
    result = ed._validate_finding(
        raw, evidence_id=_EV_ID, direct_quote=_DIRECT_QUOTE, tier="T1",
        evidence_pool=_POOL, section_atoms={}, finding_id="f001_002",
    )
    assert result is not None  # recovered, not rejected
    assert result.support_quote == "occurred in 43% of all participants"  # REAL slice
    assert "43" in result.numbers


def test_validate_finding_fuzzy_recovers_entailed_paraphrase(monkeypatch):
    """#1217 Bug B recall fix: a PARAPHRASED support_quote (not a verbatim/whitespace
    substring) is recovered to the REAL source window by content-word overlap and
    KEPT when the recovered span ENTAILS the claim. This is the exact pattern that
    collapsed the CDC safety source on the live probe (the model atomized one source
    sentence and dropped markdown italics, so all 3 contraindication findings were
    rejected at step 1). The adopted support_quote is a GENUINE source slice, never
    the model's paraphrase."""
    _enforce_entailment(monkeypatch, "ENTAILED")
    raw = {
        # Paraphrase: drops words / reorders vs the source "Adverse events occurred
        # in 43% of all participants." — not a substring, recovered by overlap.
        "claim": "Adverse events occurred in 43% of participants.",
        "support_quote": "adverse events in 43% of the participants",
        "span_start": 0, "span_end": 0, "numbers": ["43"],
        "entities": [], "caveat": "", "contradiction_key": "", "source_tier": "T1",
    }
    result = ed._validate_finding(
        raw, evidence_id=_EV_ID, direct_quote=_DIRECT_QUOTE, tier="T1",
        evidence_pool=_POOL, section_atoms={}, finding_id="f001_002b",
    )
    assert result is not None  # fuzzy-recovered + entailed -> KEPT
    # The adopted support_quote is a REAL source slice, not the model's paraphrase.
    assert result.support_quote in _DIRECT_QUOTE
    assert "Adverse events occurred in 43%" in result.support_quote


def test_validate_finding_fuzzy_block_rejects_non_entailed_paraphrase(monkeypatch):
    """#1217 Bug B faithfulness gate: a paraphrase that FUZZY-recovers a real span but
    changes meaning via function words ("all" -> "some") must be rejected when the
    recovered span does NOT entail the claim. Fuzzy recovery matches on content-word
    overlap (blind to "some" vs "all"); the BLOCKING entailment check on fuzzy spans
    is the safety net that catches the meaning change. (Exact/whitespace matches stay
    non-blocking — verbatim text cannot drift in meaning.)"""
    _enforce_entailment(monkeypatch, "NEUTRAL")  # span does NOT entail "some"
    raw = {
        "claim": "Adverse events occurred in 43% of some participants.",
        "support_quote": "adverse events occurred in 43% of some participants",
        "span_start": 0, "span_end": 0, "numbers": ["43"],
        "entities": [], "caveat": "", "contradiction_key": "", "source_tier": "T1",
    }
    result = ed._validate_finding(
        raw, evidence_id=_EV_ID, direct_quote=_DIRECT_QUOTE, tier="T1",
        evidence_pool=_POOL, section_atoms={}, finding_id="f001_003",
    )
    assert result is None  # fuzzy-recovered but NOT entailed -> rejected (faithful)


def test_fuzzy_locate_preserves_leading_negation_1217():
    """#1217 Codex diff-gate P2 (clinical faithfulness): fuzzy recovery must EXPAND to
    the enclosing clause/sentence, NEVER shrink past a leading negation. A tight
    content-word shrink would turn a source clause 'is not recommended for
    immunocompromised patients' into 'recommended for immunocompromised patients',
    flipping the meaning BEFORE the per-finding entailment check. The recovered span
    must RETAIN 'not' so the entailment gate judges the true (negative) meaning."""
    src = ("Background text here. The agent is not recommended for immunocompromised "
           "patients in this setting. More unrelated text follows.")
    quote = "agent not recommended for immunocompromised patients"  # paraphrase
    span = ed._fuzzy_locate_span(quote, src)
    assert span is not None
    s, e = span
    recovered = src[s:e]
    assert "not recommended" in recovered  # negation NOT dropped
    assert recovered in src  # a genuine source slice


def test_locate_span_in_source_unit():
    src = "The estimated mean change was -1.86 points with semaglutide."
    # exact
    assert ed._locate_span_in_source("-1.86 points", src) == (src.find("-1.86 points"), src.find("-1.86 points") + len("-1.86 points"))
    # whitespace-flexible
    loc = ed._locate_span_in_source("mean   change\nwas", src)
    assert loc is not None and src[loc[0]:loc[1]] == "mean change was"
    # reworded -> None
    assert ed._locate_span_in_source("median change was", src) is None


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
