"""I-deepfix-001 U24 — numeric-claim citation hygiene ENFORCE.

The drb autopsy found ~72% of in-prose decimals (92/128) rendered with no adjacent
citation while the PT11 rule was advisory-only. The fix adds a RENDER-ONLY, faithfulness-
neutral screen on the resolved per-section prose: a sentence that states an in-prose
decimal with NO in-sentence citation marker ([N] or [#ev:...]) is dropped; a cited one
passes unchanged. These tests assert that real behavior offline (no GPU/network/LLM).
"""
from __future__ import annotations

import importlib

from src.polaris_graph.generator.multi_section_generator import (
    _numeric_cite_enforce_enabled,
    _screen_uncited_numeric_sentences,
)


# ── the core enforce/pass contract ───────────────────────────────────

def test_uncited_in_prose_decimal_is_dropped():
    """A sentence stating a decimal with no citation marker is removed."""
    text = "Efficacy rose 10.7% versus placebo. Adherence was stable [3]."
    out = _screen_uncited_numeric_sentences(text)
    assert "10.7%" not in out
    assert "Adherence was stable [3]." in out


def test_cited_in_prose_decimal_passes_bracket_number():
    """A decimal adjacent to a [N] marker passes unchanged (byte-identical)."""
    text = "The mean reduction was 2.5 mg/dL [7]."
    assert _screen_uncited_numeric_sentences(text) == text


def test_cited_in_prose_decimal_passes_ev_token():
    """A decimal in a sentence carrying a [#ev:...] provenance token passes."""
    text = "Weight fell 3.4 kg over 12 weeks [#ev:ev_a12:0-40]."
    assert _screen_uncited_numeric_sentences(text) == text


def test_sentence_without_decimal_is_kept():
    """A non-numeric sentence is never touched, cited or not."""
    text = "GLP-1 receptor activation enhances insulin secretion."
    assert _screen_uncited_numeric_sentences(text) == text


def test_integer_only_sentence_is_kept():
    """PT11 scopes to DECIMALS; a bare integer (study marker) is not a claim."""
    text = "The trial enrolled 68 participants over week 12."
    assert _screen_uncited_numeric_sentences(text) == text


def test_mixed_paragraph_keeps_cited_drops_uncited():
    text = (
        "HbA1c dropped 1.8% at 24 weeks [4]. "
        "A separate cohort reported 0.9% with no source. "
        "Discontinuation was uncommon [5]."
    )
    out = _screen_uncited_numeric_sentences(text)
    assert "1.8%" in out           # cited numeric kept
    assert "[4]" in out
    assert "0.9%" not in out       # uncited numeric dropped
    assert "Discontinuation was uncommon [5]." in out


# ── fail-safe + kill-switch behavior ─────────────────────────────────

def test_all_uncited_section_is_withheld_not_shipped():
    """U24 bypass CLOSED (Codex P1): a section where EVERY sentence asserts an
    uncited in-prose decimal must NOT ship. The prior fail-safe returned the text
    UNCHANGED, letting all the uncited numeric claims through — exactly the clinical
    hazard §-1.1 forbids (a wrong dose/percentage that survives to render is lethal).
    The screen now WITHHOLDS the whole all-uncited body (returns empty); the caller
    renders an explicit gap-disclosure stub instead of shipping the uncited numbers."""
    text = "Value was 1.1. Value was 2.2. Value was 3.3."
    out = _screen_uncited_numeric_sentences(text)
    assert out == ""
    assert "1.1" not in out and "2.2" not in out and "3.3" not in out


def test_empty_and_blank_input_returned_unchanged():
    assert _screen_uncited_numeric_sentences("") == ""
    assert _screen_uncited_numeric_sentences("   ") == "   "


def test_kill_switch_off_is_byte_identical(monkeypatch):
    """PG_NUMERIC_CITE_ENFORCE off => the screen is a no-op (byte-identical)."""
    monkeypatch.setenv("PG_NUMERIC_CITE_ENFORCE", "0")
    assert not _numeric_cite_enforce_enabled()
    text = "Efficacy rose 10.7% versus placebo. Adherence was stable [3]."
    assert _screen_uncited_numeric_sentences(text) == text


def test_default_is_enforce_on(monkeypatch):
    """Unset => enforce ON (default). This is the 'enforce not advisory' contract."""
    monkeypatch.delenv("PG_NUMERIC_CITE_ENFORCE", raising=False)
    assert _numeric_cite_enforce_enabled()


def test_version_string_in_marker_not_treated_as_uncited_decimal():
    """A decimal that lives only inside a citation token must not trip the screen
    (the sentence has no OTHER in-prose decimal), and the marker counts as a citation."""
    text = "The protocol was applied to every cohort [#ev:ev_9:0-10]."
    # no in-prose decimal at all -> kept
    assert _screen_uncited_numeric_sentences(text) == text


# ── _run_section-level: the U24-withheld body contributes ZERO to D8 ──────────
#
# Codex grpC iter2 P1: the U24 fix withholds an all-uncited-decimal section from the
# RENDER (returns the gap stub), but the returned SectionResult's verified-accounting
# still leaked the withheld numeric claims into the binding D8 four-role gate
# (sentences_verified=resolved_emitted, kept_sentences_pre_resolve=the withheld SVs;
# native_gate_b_inputs then fed them into D8 as verified claims). These tests drive the
# REAL _run_section — exercising the REAL U24 screen + gap-stub decision + accounting —
# with the upstream LLM / strict_verify / resolve seams stubbed offline (no
# network/GPU/LLM). The frozen faithfulness engine is never invoked; only its INPUTS are
# under test.

import asyncio  # noqa: E402
import types  # noqa: E402

from src.polaris_graph.generator import multi_section_generator as _msg  # noqa: E402
from src.polaris_graph.generator import sentence_repair as _sentence_repair  # noqa: E402


class _FakeSV:
    """Minimal SentenceVerification-like. The stubbed resolve/dedup/m41c ignore its
    content; build_native_gate_b_inputs (in the roles test) reads is_verified/sentence/
    tokens, so those are present and faithful."""

    def __init__(self, sentence: str, evidence_id: str):
        self.sentence = sentence
        self.tokens = [types.SimpleNamespace(evidence_id=evidence_id, start=0, end=10)]
        self.is_verified = True


class _FakeReport:
    """Minimal strict_verify report the accounting reads: kept/dropped lists + totals."""

    def __init__(self, kept, dropped, total_in):
        self.kept_sentences = list(kept)
        self.dropped_sentences = list(dropped)
        self.total_kept = len(kept)
        self.total_dropped = len(dropped)
        self.total_in = total_in


class _FakeRepairTelem:
    attempts = 0
    successes = 0
    recovery_rate = 0.0
    null_drops = 0
    token_set_violations = 0
    re_verify_failures = 0
    api_failures = 0
    input_tokens = 0
    output_tokens = 0


def _install_run_section_stubs(monkeypatch, *, resolve_return, kept_svs):
    """Stub ONLY the upstream heavy seams (LLM generation, strict_verify, resolve) so
    _run_section reaches the REAL U24 screen + gap-stub decision + accounting offline."""
    monkeypatch.delenv("PG_NUMERIC_CITE_ENFORCE", raising=False)  # screen default ON
    monkeypatch.setattr(_msg, "_section_distill_enabled", lambda: False)

    async def _stub_call_section(*_a, **_k):
        return ("draft body", 0, 0, {})

    monkeypatch.setattr(_msg, "_call_section", _stub_call_section)
    monkeypatch.setattr(_msg, "_rewrite_draft_with_spans", lambda raw, _pool: (raw, [], []))
    monkeypatch.setattr(
        _msg, "_repair_llm_draft_untokened", lambda rewritten, *_a, **_k: rewritten
    )
    monkeypatch.setattr(
        _msg, "strict_verify", lambda _rewritten, _pool: _FakeReport(kept_svs, [], len(kept_svs))
    )
    monkeypatch.setattr(_msg, "filter_underframed_trial_sentences", lambda svs: (list(svs), []))
    monkeypatch.setattr(_msg, "dedup_same_span_sentences", lambda svs: (list(svs), []))
    monkeypatch.setattr(
        _msg,
        "resolve_provenance_to_citations_with_count",
        lambda _kept, _pool, **_kw: resolve_return,
    )

    async def _stub_repair(*, kept, dropped, evidence_pool, model, max_tokens, temperature):
        return kept, dropped, _FakeRepairTelem()

    monkeypatch.setattr(_sentence_repair, "repair_dropped_section_sentences", _stub_repair)


def _run_one_section(section, evidence_pool):
    return asyncio.run(
        _msg._run_section(
            section,
            evidence_pool,
            model="test/model",
            temperature=0.0,
            max_tokens_per_section=100,
            min_kept_fraction=0.0,  # >=0.0 is never < 0.0 -> no LLM retry
        )
    )


def test_run_section_all_uncited_withheld_zeroes_verified_and_clears_kept(monkeypatch):
    """An all-uncited-decimal section (a) renders the gap stub, (b) reports
    sentences_verified==0 with an EMPTY kept_sentences_pre_resolve, and accounts the
    withheld sentences as dropped. This is the D8 leak closed at the source."""
    kept_svs = [_FakeSV("Value was 1.1.", "ev1"), _FakeSV("Value was 2.2.", "ev1")]
    # resolve EMITS both sentences (resolved_emitted=2) but the rendered prose is all
    # uncited in-prose decimals -> the U24 screen withholds the whole body.
    _install_run_section_stubs(
        monkeypatch,
        resolve_return=("Value was 1.1. Value was 2.2.", [], 2),
        kept_svs=kept_svs,
    )
    section = _msg.SectionPlan(title="Efficacy", focus="f", ev_ids=["ev1"], archetype="")
    evidence_pool = {"ev1": {"text": "some source text", "url": "https://example.org/a"}}

    sr = _run_one_section(section, evidence_pool)

    # (a) renders the gap stub, not the uncited numbers.
    assert sr.is_gap_stub is True
    assert sr.verified_text == _msg._GAP_STUB_SENTENCE
    assert "1.1" not in sr.verified_text and "2.2" not in sr.verified_text
    # (b) zero verified claims + cleared pre-resolve kept -> nothing to leak into D8.
    assert sr.sentences_verified == 0
    assert sr.kept_sentences_pre_resolve == []
    # drop counter stays honest: the 2 withheld sentences are counted as dropped.
    assert sr.sentences_dropped == 2


def test_run_section_normal_cited_section_is_unaffected(monkeypatch):
    """A normal section whose cited numeric sentence passes the screen keeps its verified
    count and its kept_sentences_pre_resolve (byte-identical to legacy behavior)."""
    kept_svs = [_FakeSV("The mean reduction was 2.5 mg/dL [7].", "ev1")]
    _install_run_section_stubs(
        monkeypatch,
        resolve_return=("The mean reduction was 2.5 mg/dL [7].", [{"n": 7}], 1),
        kept_svs=kept_svs,
    )
    section = _msg.SectionPlan(title="Efficacy", focus="f", ev_ids=["ev1"], archetype="")
    evidence_pool = {"ev1": {"text": "some source text", "url": "https://example.org/a"}}

    sr = _run_one_section(section, evidence_pool)

    assert sr.is_gap_stub is False
    assert sr.sentences_verified == 1
    assert len(sr.kept_sentences_pre_resolve) == 1
    assert "2.5 mg/dL [7]" in sr.verified_text
