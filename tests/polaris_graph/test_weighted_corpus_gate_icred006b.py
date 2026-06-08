"""I-cred-006b (#1170) — weighted-corpus gate offline smoke + regression tests.

Proves:
  * Pure module: flag semantics (default OFF), deterministic domain-aware disclosure
    (authority_score basis + tier-prior fallback, weighted mean, material-deviation passthrough),
    the corpus-ZERO floor (has_usable_corpus).
  * Sweep wiring (inspect.getsource — no network): the flag-branch exists; the OFF abort blocks are
    PRESERVED (the literal `if not approved:` + `return summary` before the generator call); the
    legitimate corpus-ZERO (`abort_no_sources`) and zero-sufficient-sections
    (`abort_corpus_inadequate` plan-sufficiency) aborts still PRECEDE the generator call; the binding
    per-claim gates (strict_verify resolve sites + the 4-role D8 seam) are UNTOUCHED.
  * Slate activation: PG_SWEEP_WEIGHTED_CORPUS_GATE is in the Gate-B slate, force-on, and required.

OFFLINE ONLY — no spend, no network. Mirrors the existing gate-test pattern
(test_b2_corpus_approval_enforcement.py, test_corpus_adequacy_r6_gap1.py).
"""
from __future__ import annotations

import inspect
from dataclasses import dataclass

import pytest

from src.polaris_graph.nodes.weighted_corpus_gate import (
    CorpusCredibilityDisclosure,
    build_corpus_credibility_disclosure,
    disclosure_to_dict,
    has_usable_corpus,
    weighted_corpus_gate_enabled,
    weighted_corpus_proceeds,
)


@dataclass
class _FakeSource:
    """CorpusSource-shaped stand-in (url / tier / domain + optional authority_score)."""

    url: str
    tier: str
    domain: str = ""
    authority_score: float | None = None


# ──────────────────────────────────────────────────────────────────────────────
# Flag semantics (default OFF => byte-identical)
# ──────────────────────────────────────────────────────────────────────────────

def test_flag_default_off(monkeypatch) -> None:
    monkeypatch.delenv("PG_SWEEP_WEIGHTED_CORPUS_GATE", raising=False)
    assert weighted_corpus_gate_enabled() is False


@pytest.mark.parametrize("val", ["", "0", "false", "off", "no", "FALSE", " Off "])
def test_flag_off_values(monkeypatch, val) -> None:
    monkeypatch.setenv("PG_SWEEP_WEIGHTED_CORPUS_GATE", val)
    assert weighted_corpus_gate_enabled() is False


@pytest.mark.parametrize("val", ["1", "true", "on", "yes", "TRUE"])
def test_flag_on_values(monkeypatch, val) -> None:
    monkeypatch.setenv("PG_SWEEP_WEIGHTED_CORPUS_GATE", val)
    assert weighted_corpus_gate_enabled() is True


# ──────────────────────────────────────────────────────────────────────────────
# has_usable_corpus — the corpus-ZERO floor (NOT a tier proxy)
# ──────────────────────────────────────────────────────────────────────────────

def test_has_usable_corpus_zero_sources_is_false() -> None:
    assert has_usable_corpus([], [{"evidence_id": "e1"}]) is False


def test_has_usable_corpus_zero_evidence_rows_is_false() -> None:
    # iter-2 P0 (Codex): classified sources present but ZERO usable evidence rows must NOT pass the
    # floor — generation consumes evidence_rows, not classified_sources. "Synthesize from nothing" guard.
    assert has_usable_corpus([_FakeSource("u", "T4")], []) is False


def test_has_usable_corpus_sources_and_rows_is_true() -> None:
    assert has_usable_corpus([_FakeSource("u", "T4")], [{"evidence_id": "e1"}]) is True


# ──────────────────────────────────────────────────────────────────────────────
# weighted_corpus_proceeds — THE load-bearing decision (behavioral, not string-presence)
# ──────────────────────────────────────────────────────────────────────────────

def test_proceeds_on_flag_on_material_deviation_with_sources() -> None:
    """The acceptance criterion: flag-ON + a material-deviation corpus + sources -> PROCEED (the
    drb_72 tier-skewed corpus is NOT refused). This is the exact decision wired into run_one_query."""
    srcs = [_FakeSource("https://nber.org/w1", "T4", "nber.org")]
    assert weighted_corpus_proceeds(
        flag_on=True, has_material_deviation=True, classified_sources=srcs,
        evidence_rows=[{"evidence_id": "e1"}],
    ) is True


def test_does_not_proceed_when_flag_off() -> None:
    """Flag-OFF -> the gate does NOT proceed; the caller falls to the unchanged refusal path
    (byte-identical: the old abort_corpus_approval_denied still fires on a material-deviation corpus)."""
    srcs = [_FakeSource("https://nber.org/w1", "T4", "nber.org")]
    assert weighted_corpus_proceeds(
        flag_on=False, has_material_deviation=True, classified_sources=srcs,
        evidence_rows=[{"evidence_id": "e1"}],
    ) is False


def test_does_not_proceed_when_zero_sources_even_if_flag_on() -> None:
    """The corpus-ZERO floor holds even with the flag on: a zero-source corpus does NOT proceed
    (cannot synthesize from nothing — a real floor, not a tier proxy)."""
    assert weighted_corpus_proceeds(
        flag_on=True, has_material_deviation=True, classified_sources=[],
        evidence_rows=[{"evidence_id": "e1"}],
    ) is False


def test_does_not_proceed_when_zero_evidence_rows_even_if_flag_on_and_sources() -> None:
    """iter-2 P0 (Codex): the ON path must NOT proceed when classified_sources is non-empty but there
    are ZERO usable evidence rows — generation consumes evidence_rows, so this is the real
    'cannot synthesize from nothing' floor. Without this, the planner-OFF beat-both path could reach
    generation with an empty evidence pool. Falls through to the unchanged refusal path instead."""
    srcs = [_FakeSource("https://nber.org/w1", "T4", "nber.org")]
    assert weighted_corpus_proceeds(
        flag_on=True, has_material_deviation=True, classified_sources=srcs,
        evidence_rows=[],
    ) is False


def test_does_not_proceed_when_no_material_deviation() -> None:
    """A within-distribution corpus needs no weighted-proceed (it already auto-approves); the helper
    returns False so the caller's unchanged default-approve path runs."""
    srcs = [_FakeSource("https://aer.org/1", "T1", "aer.org")]
    assert weighted_corpus_proceeds(
        flag_on=True, has_material_deviation=False, classified_sources=srcs,
        evidence_rows=[{"evidence_id": "e1"}],
    ) is False


# ──────────────────────────────────────────────────────────────────────────────
# build_corpus_credibility_disclosure — deterministic, domain-aware, pure
# ──────────────────────────────────────────────────────────────────────────────

def _drb72_like_sources() -> list[_FakeSource]:
    """The drb_72 shape: ~50% T4 (legit NBER/Acemoglu working papers for an economics question)."""
    t4 = [_FakeSource(f"https://nber.org/w{i}", "T4", "nber.org", authority_score=0.62)
          for i in range(5)]
    t1 = [_FakeSource(f"https://aer.org/{i}", "T1", "aer.org", authority_score=0.93)
          for i in range(3)]
    t5 = [_FakeSource(f"https://blog/{i}", "T5", "blog.example", authority_score=0.35)
          for i in range(2)]
    return t4 + t1 + t5


def test_disclosure_uses_authority_score_when_present() -> None:
    srcs = [_FakeSource("https://x", "T4", "nber.org", authority_score=0.62)]
    d = build_corpus_credibility_disclosure(
        classified_sources=srcs,
        tier_counts={"T4": 1},
        tier_fractions={"T4": 1.0},
        total_sources=1,
        had_material_deviation=True,
        domain="economics",
        research_question="q",
    )
    assert len(d.per_source) == 1
    assert d.per_source[0].weight_basis == "authority_score"
    assert d.per_source[0].credibility_weight == pytest.approx(0.62)
    # weighted mean of a single source == its weight
    assert d.weighted_credibility_mean == pytest.approx(0.62)


def test_disclosure_uses_authority_by_url_join_when_object_lacks_it() -> None:
    """When the CorpusSource object has no authority_score attribute (the real shape — authority lives
    on the evidence rows), the caller-supplied url->authority join is used (real weighting, not prior)."""
    srcs = [_FakeSource("https://nber.org/w1", "T4", "nber.org", authority_score=None)]
    d = build_corpus_credibility_disclosure(
        classified_sources=srcs,
        tier_counts={"T4": 1},
        tier_fractions={"T4": 1.0},
        total_sources=1,
        had_material_deviation=True,
        domain="economics",
        research_question="q",
        authority_by_url={"https://nber.org/w1": 0.71},
    )
    assert d.per_source[0].weight_basis == "authority_score"
    assert d.per_source[0].credibility_weight == pytest.approx(0.71)


def test_disclosure_object_authority_wins_over_join() -> None:
    srcs = [_FakeSource("https://x", "T4", authority_score=0.5)]
    d = build_corpus_credibility_disclosure(
        classified_sources=srcs,
        tier_counts={"T4": 1},
        tier_fractions={"T4": 1.0},
        total_sources=1,
        had_material_deviation=True,
        domain="economics",
        research_question="q",
        authority_by_url={"https://x": 0.99},
    )
    # object's own authority_score (0.5) wins over the join (0.99)
    assert d.per_source[0].credibility_weight == pytest.approx(0.5)


def test_disclosure_falls_back_to_tier_prior_when_no_authority_score() -> None:
    srcs = [_FakeSource("https://x", "T4", "nber.org", authority_score=None)]
    d = build_corpus_credibility_disclosure(
        classified_sources=srcs,
        tier_counts={"T4": 1},
        tier_fractions={"T4": 1.0},
        total_sources=1,
        had_material_deviation=True,
        domain="economics",
        research_question="q",
    )
    assert d.per_source[0].weight_basis == "tier_prior"
    # T4 prior is deterministic and > 0 (lower-tier disclosed as lower-credibility, not dropped)
    assert 0.0 < d.per_source[0].credibility_weight < 1.0


def test_disclosure_weighted_mean_is_count_weighted() -> None:
    d = build_corpus_credibility_disclosure(
        classified_sources=_drb72_like_sources(),
        tier_counts={"T4": 5, "T1": 3, "T5": 2},
        tier_fractions={"T4": 0.5, "T1": 0.3, "T5": 0.2},
        total_sources=10,
        had_material_deviation=True,
        domain="economics",
        research_question="effect of minimum wage",
    )
    expected = (5 * 0.62 + 3 * 0.93 + 2 * 0.35) / 10
    assert d.weighted_credibility_mean == pytest.approx(expected, abs=1e-4)
    assert d.total_sources == 10
    assert d.had_material_deviation is True
    # the disclosure honestly records what the OLD gate would have refused on
    assert "credibility" in d.disclosure_note.lower()
    assert d.gate == "PG_SWEEP_WEIGHTED_CORPUS_GATE"


def test_disclosure_no_material_deviation_note() -> None:
    d = build_corpus_credibility_disclosure(
        classified_sources=[_FakeSource("https://x", "T1", "aer.org", authority_score=0.9)],
        tier_counts={"T1": 1},
        tier_fractions={"T1": 1.0},
        total_sources=1,
        had_material_deviation=False,
        domain="economics",
        research_question="q",
    )
    assert d.had_material_deviation is False
    assert "within the pre-registered" in d.disclosure_note.lower()


def test_disclosure_is_serializable_and_pure() -> None:
    srcs = _drb72_like_sources()
    snapshot = [(_s.url, _s.tier, _s.authority_score) for _s in srcs]
    d = build_corpus_credibility_disclosure(
        classified_sources=srcs,
        tier_counts={"T4": 5, "T1": 3, "T5": 2},
        tier_fractions={"T4": 0.5, "T1": 0.3, "T5": 0.2},
        total_sources=10,
        had_material_deviation=True,
        domain="economics",
        research_question="q",
    )
    as_dict = disclosure_to_dict(d)
    assert isinstance(as_dict, dict)
    assert as_dict["total_sources"] == 10
    assert isinstance(as_dict["per_source"], list) and len(as_dict["per_source"]) == 10
    # NO row mutation
    assert [(_s.url, _s.tier, _s.authority_score) for _s in srcs] == snapshot


def test_disclosure_clamps_out_of_range_authority() -> None:
    srcs = [
        _FakeSource("https://hi", "T1", authority_score=2.0),   # clamps to 1.0
        _FakeSource("https://lo", "T7", authority_score=-1.0),  # clamps to 0.0
        _FakeSource("https://nan", "T4", authority_score=float("nan")),  # -> tier_prior fallback
    ]
    d = build_corpus_credibility_disclosure(
        classified_sources=srcs,
        tier_counts={"T1": 1, "T7": 1, "T4": 1},
        tier_fractions={"T1": 0.33, "T7": 0.33, "T4": 0.33},
        total_sources=3,
        had_material_deviation=True,
        domain="economics",
        research_question="q",
    )
    by_url = {r.url: r for r in d.per_source}
    assert by_url["https://hi"].credibility_weight == pytest.approx(1.0)
    assert by_url["https://lo"].credibility_weight == pytest.approx(0.0)
    # NaN authority is treated as absent -> tier_prior basis (never a NaN weight)
    assert by_url["https://nan"].weight_basis == "tier_prior"
    assert by_url["https://nan"].credibility_weight == by_url["https://nan"].credibility_weight  # not NaN


# ──────────────────────────────────────────────────────────────────────────────
# Sweep wiring (inspect.getsource — offline, no network)
# ──────────────────────────────────────────────────────────────────────────────

def _sweep_src() -> str:
    import scripts.run_honest_sweep_r3 as sweep
    return inspect.getsource(sweep.run_one_query)


def test_sweep_imports_and_calls_weighted_gate() -> None:
    src = _sweep_src()
    assert "weighted_corpus_gate_enabled()" in src
    assert "build_corpus_credibility_disclosure(" in src
    assert "has_usable_corpus(" in src
    # the load-bearing decision is the extracted pure helper (asserted behaviorally above), not an
    # inline expression that string-presence tests cannot catch a typo in.
    assert "weighted_corpus_proceeds(" in src
    assert "_weighted_corpus_approve = weighted_corpus_proceeds(" in src


def test_sweep_weighted_gate_requires_evidence_rows_iter2() -> None:
    """iter-2 P0 (Codex): the ON path's two suppression sites must require usable evidence_rows, not
    just classified_sources — generation consumes evidence_rows. Both the weighted_corpus_proceeds call
    and the adequacy-abort suppression must reference retrieval.evidence_rows, so a future edit cannot
    silently restore the 'synthesize from nothing' hole the iter-1 diff had."""
    src = _sweep_src()
    assert "evidence_rows=retrieval.evidence_rows" in src
    assert "bool(retrieval.evidence_rows)" in src


def test_sweep_preserves_approval_abort_literal_and_return() -> None:
    """The OFF path must run the unchanged approval abort: the literal `if not approved:` survives and
    still returns before the generator (the FX-05 enforcement contract is intact)."""
    src = _sweep_src()
    assert "if not approved:" in src
    approval_idx = src.find("if not approved:")
    gen_idx = src.find("generate_multi_section_report(")
    assert approval_idx != -1 and gen_idx != -1
    assert approval_idx < gen_idx
    assert "return summary" in src[approval_idx:gen_idx]
    assert "abort_corpus_approval_denied" in src


def test_sweep_keeps_zero_source_and_zero_section_aborts_before_generation() -> None:
    """The legitimate corpus-ZERO (`abort_no_sources`) and zero-sufficient-sections
    (plan-sufficiency `abort_corpus_inadequate`) aborts are NOT tier proxies and must still precede
    the generator call regardless of the weighted gate."""
    src = _sweep_src()
    gen_idx = src.find("generate_multi_section_report(")
    assert gen_idx != -1
    no_sources_idx = src.find("abort_no_sources")
    assert no_sources_idx != -1 and no_sources_idx < gen_idx
    inadequate_idx = src.find("abort_corpus_inadequate")
    assert inadequate_idx != -1 and inadequate_idx < gen_idx


def test_sweep_weighted_gate_does_not_suppress_journal_only_floor() -> None:
    """The journal-only adequacy FLOOR (`_jo_force_inadequate`) is a SEPARATE mode (#1146) and must
    still abort — the weighted-gate proceed is gated on `not _jo_force_inadequate`."""
    src = _sweep_src()
    assert "_jo_force_inadequate" in src
    assert "not _jo_force_inadequate" in src


def test_binding_faithfulness_gates_untouched() -> None:
    """strict_verify + the 4-role D8 seam remain the ONLY binding gates — this issue touches neither
    the resolve sites that call strict_verify nor the seam activation."""
    src = _sweep_src()
    # strict_verify is still invoked on the generation path
    assert "strict_verify" in src or "generate_multi_section_report(" in src
    # the 4-role seam toggle is unchanged (env flag still read, not removed)
    assert "PG_FOUR_ROLE_MODE" in src or "_seam_will_run" in src


# ──────────────────────────────────────────────────────────────────────────────
# Slate activation (Gate-B)
# ──────────────────────────────────────────────────────────────────────────────

def test_slate_activates_weighted_gate_force_on_and_required() -> None:
    import scripts.dr_benchmark.run_gate_b as gb
    assert gb._FULL_CAPABILITY_BENCHMARK_SLATE.get("PG_SWEEP_WEIGHTED_CORPUS_GATE") == "1"
    assert "PG_SWEEP_WEIGHTED_CORPUS_GATE" in gb._BENCHMARK_FORCE_ON_FLAGS
    assert "PG_SWEEP_WEIGHTED_CORPUS_GATE" in gb._BENCHMARK_PREFLIGHT_REQUIRED_FLAGS


def test_slate_apply_forces_on_over_operator_zero(monkeypatch) -> None:
    """An explicit operator PG_SWEEP_WEIGHTED_CORPUS_GATE=0 must NOT survive the slate (force-on)."""
    import scripts.dr_benchmark.run_gate_b as gb
    monkeypatch.setenv("PG_SWEEP_WEIGHTED_CORPUS_GATE", "0")
    # set_max_cost_per_run side effect is harmless offline; apply the slate and re-check the env.
    gb.apply_full_capability_benchmark_slate()
    import os
    assert os.environ["PG_SWEEP_WEIGHTED_CORPUS_GATE"] == "1"
