"""Crown Jewel I-cj-005 — Corpus approval rubber-stamp resistance.

Per CLAUDE.md §9.1.5: a corpus with material tier deviation + a
rubber-stamp note aborts before any generator token is billed
(status = abort_corpus_approval_denied). The check_auto_approve_allowed
gate enforces:
  - no material deviation → any note OK
  - material deviation + short / trivial note → rejected
  - material deviation + substantive note → OK

The Crown Jewel pins the user-observable rejection invariant; whether
the rejection fires under the length-check branch or the trivial-note
branch is an implementation detail.
"""

from __future__ import annotations

from src.polaris_graph.nodes.corpus_approval_gate import (
    CorpusDistributionReport,
    check_auto_approve_allowed,
)


def _report(material: bool) -> CorpusDistributionReport:
    return CorpusDistributionReport(
        total_sources=10,
        tier_counts={"T1": 5, "T2": 5},
        tier_fractions={"T1": 0.5, "T2": 0.5},
        deviations=[],
        has_material_deviation=material,
        auto_approve_allowed=not material,
    )


def test_cj_005_no_material_deviation_any_note_ok() -> None:
    ok, msg = check_auto_approve_allowed(_report(False), user_note="")
    assert ok and msg == ""


def test_cj_005_material_deviation_empty_note_rejected() -> None:
    ok, msg = check_auto_approve_allowed(_report(True), user_note="")
    assert not ok and "note" in msg.lower()


def test_cj_005_material_deviation_short_note_rejected() -> None:
    ok, msg = check_auto_approve_allowed(_report(True), user_note="too short")
    assert not ok and "note" in msg.lower()


def test_cj_005_material_deviation_short_or_trivial_rejected() -> None:
    for note in ["lgtm", "approved", "ok", "fine", "go ahead", "x"]:
        ok, msg = check_auto_approve_allowed(_report(True), user_note=note)
        assert not ok, f"short / trivial note {note!r} should be rejected"
        assert msg, "rejection must include explanation"


def test_cj_005_material_deviation_substantive_note_accepted() -> None:
    note = (
        "T1 sources fell below 30% because Cochrane Review CD012345 was "
        "retracted post-protocol-registration and we replaced it with two "
        "T2 systematic reviews. The methods section flags this deviation."
    )
    ok, msg = check_auto_approve_allowed(_report(True), user_note=note)
    assert ok and msg == ""
