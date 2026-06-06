"""Crown Jewel I-cj-005 — Corpus approval rubber-stamp resistance.

Per CLAUDE.md §9.1.5: a corpus with material tier deviation aborts before
any generator token is billed (status = abort_corpus_approval_denied).

FX-05 (I-ready-017) STRENGTHENS this invariant. The old gate accepted any
free-text note >=30 chars not in a small denylist — defeated by the R-3
sweep's own 48-char canned note, which auto-approved a material-deviation
corpus and billed it. The gate now enforces:
  - no material deviation → auto-approve OK (no authorization needed)
  - material deviation + NO structured authorization → rejected
  - material deviation + free-text note (any length) → rejected
  - material deviation + COMPLETE structured AuthorizedSweep → OK

The Crown Jewel pins the user-observable rejection invariant: a free-text
note alone never auto-approves a material-deviation corpus.
"""

from __future__ import annotations

from src.polaris_graph.nodes.corpus_approval_gate import (
    AuthorizedSweep,
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


def _valid_authorization() -> AuthorizedSweep:
    return AuthorizedSweep(
        authorized_by="env:PG_AUTHORIZED_SWEEP_APPROVAL",
        authorized_at="2026-06-06T00:00:00Z",
        flag_source="env",
    )


def test_cj_005_no_material_deviation_auto_approves() -> None:
    ok, msg = check_auto_approve_allowed(_report(False), None)
    assert ok and msg == ""


def test_cj_005_material_deviation_no_authorization_rejected() -> None:
    ok, msg = check_auto_approve_allowed(_report(True), None)
    assert not ok and "authoriz" in msg.lower()


def test_cj_005_material_deviation_free_text_note_rejected() -> None:
    """A free-text note — short, trivial, OR substantive — never auto-approves."""
    notes = [
        "",
        "too short",
        "lgtm",
        "approved",
        "R-3 sweep. Domain=clinical. Auto-approve on sweep.",  # the real defeater
        (
            "T1 sources fell below 30% because Cochrane Review CD012345 was "
            "retracted post-protocol-registration and we replaced it with two "
            "T2 systematic reviews. The methods section flags this deviation."
        ),
    ]
    for note in notes:
        ok, msg = check_auto_approve_allowed(_report(True), note)
        assert not ok, f"free-text note {note!r} must NOT auto-approve (FX-05)"
        assert msg, "rejection must include an explanation"


def test_cj_005_material_deviation_structured_authorization_accepted() -> None:
    ok, msg = check_auto_approve_allowed(_report(True), _valid_authorization())
    assert ok and msg == ""


def test_cj_005_material_deviation_incomplete_authorization_rejected() -> None:
    incomplete = AuthorizedSweep(authorized_by="", authorized_at="", flag_source="")
    ok, msg = check_auto_approve_allowed(_report(True), incomplete)
    assert not ok and msg
