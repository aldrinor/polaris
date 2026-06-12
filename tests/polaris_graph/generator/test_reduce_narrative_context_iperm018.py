"""I-perm-018 (#1210) — advisory_text + cross_trial_block threaded into the distill
REDUCE prompt as FRAMING-ONLY narrative context.

Proves: (1) byte-identical when no advisory/cross-trial supplied; (2) the narrative
block is framing-only — it explicitly forbids citing/writing FROM it and reaffirms
that every sentence still comes from the VALIDATED_FINDINGS_LEDGER; (3) the ledger
itself is unchanged.
"""
from __future__ import annotations

from src.polaris_graph.generator.evidence_distiller import (
    DistilledFinding,
    SectionDistillate,
    _render_reduce_narrative_context,
    render_reduce_user,
)


def _distillate() -> SectionDistillate:
    f = DistilledFinding(
        finding_id="f001_000", evidence_id="ev_001",
        claim="HbA1c fell by -1.86 percentage points with semaglutide.",
        span_start=10, span_end=51,
        support_quote="-1.86 percentage points with semaglutide",
        numbers=["-1.86"], entities=["semaglutide"], caveat="",
        contradiction_key="", source_tier="T1", atom_ids=["atom_002"],
    )
    return SectionDistillate(
        section_title="Efficacy", section_focus="HbA1c",
        findings=[f], coverage=[], contradiction_clusters=[], atom_catalog={},
    )


def test_byte_identical_when_no_narrative():
    dist = _distillate()
    base = render_reduce_user(dist)
    assert render_reduce_user(dist, advisory_text="", cross_trial_summaries=None) == base
    assert render_reduce_user(dist, advisory_text="", cross_trial_summaries=[]) == base
    assert "NARRATIVE FRAMING CONTEXT" not in base


def test_helper_empty_returns_empty_string():
    assert _render_reduce_narrative_context("", []) == ""
    assert _render_reduce_narrative_context("", None) == ""
    assert _render_reduce_narrative_context("   ", ["   "]) == ""


def test_advisory_appended_as_framing_only():
    dist = _distillate()
    out = render_reduce_user(
        dist, advisory_text="Emphasise jurisdiction-specific regulatory labels.")
    assert "NARRATIVE FRAMING CONTEXT" in out
    assert "DOMAIN_ADVISORY" in out
    assert "jurisdiction-specific regulatory labels" in out
    # framing-only guarantee
    assert "NOT findings" in out
    assert "must NOT write or cite any sentence FROM this block" in out
    assert "VALIDATED_FINDINGS_LEDGER" in out


def test_cross_trial_summaries_appended():
    dist = _distillate()
    out = render_reduce_user(
        dist,
        cross_trial_summaries=[
            "TACT and TACT2 together suggest chelation benefit is unproven.",
        ],
    )
    assert "CROSS_TRIAL_CONNECTIONS" in out
    assert "TACT and TACT2 together suggest chelation benefit is unproven." in out
    assert "must NOT write or cite any sentence FROM this block" in out


def test_ledger_unchanged_with_narrative():
    dist = _distillate()
    out = render_reduce_user(dist, advisory_text="Foo.",
                             cross_trial_summaries=["Bar baz."])
    # the ledger row + write instruction survive intact
    assert "f001_000 | ev_001 | T1 |" in out
    assert "cite=[ev_001]" in out
    assert "Write the section now." in out
    assert "[#ev:ev_" not in out


def test_empty_cross_trial_with_advisory_only():
    dist = _distillate()
    out = render_reduce_user(dist, advisory_text="Only advisory here.",
                             cross_trial_summaries=[])
    assert "DOMAIN_ADVISORY" in out
    assert "CROSS_TRIAL_CONNECTIONS" not in out   # no empty cross-trial section
