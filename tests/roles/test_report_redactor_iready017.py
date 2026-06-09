"""I-beatboth-fix-000 (#1171) — faithfulness leak closure: post-gate report.md
reconciliation against the 4-role D8 verdicts.

These tests use the REAL drb_90 forensic artifacts (report.md +
four_role_claim_audit.json + manifest.four_role_evaluation.final_verdicts) — NOT a
synthetic fixture — because the leak is a mapping problem (the assembled body is NOT
1:1 with strict_verify-kept; provenance tokens render to [N] markers; downstream
dedup/repair mutate the body). Only the real artifacts exercise that mapping.

Proof obligations (per the leak design):
  (a) each material-non-VERIFIED claim that ships as prose is REMOVED / replaced;
  (b) PRECISION — VERIFIED kept claims SURVIVE (no blanket recall cut);
  (c) gaps.json gains one redacted_unsupported entry per removed claim;
  (d) FAIL-CLOSED — a present-but-unlocatable material claim raises (no partial ship);
  (e) I-faith-003 #1174: redaction is SEVERITY-INDEPENDENT — an S3 claim flagged
      non-VERIFIED IS redacted (the observe-only scope guard no longer exempts a leak);
      an S3 VERIFIED claim still ships (no over-redaction);
  (f) runs on the HELD path (release_allowed=False) just like the shipped one.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.polaris_graph.roles.report_redactor import (
    ReportRedactionError,
    reconcile_report_against_verdicts,
)

# Real drb_90 forensic artifacts, committed as a tracked fixture (CLAUDE.md §5 / LAW VI) so the
# real-artifact tests are CI-portable — outputs/* is gitignored, so the source copies are not
# tracked (Codex iter-3 P1). These three files (report.md + four_role_claim_audit.json +
# manifest.json) are the genuine shipped drb_90 run, not synthetic — the leak is a render-mapping
# problem only the real artifacts exercise.
_FORENSIC = Path(__file__).resolve().parents[1] / "fixtures" / "drb90_redaction"


def _load_real():
    report = (_FORENSIC / "report.md").read_text(encoding="utf-8")
    audit = json.loads((_FORENSIC / "four_role_claim_audit.json").read_text(encoding="utf-8"))
    manifest = json.loads((_FORENSIC / "manifest.json").read_text(encoding="utf-8"))
    final_verdicts = manifest["four_role_evaluation"]["final_verdicts"]
    return report, audit, final_verdicts


# The 7 material UNSUPPORTED claim_ids the 4-role seam flagged (manifest.needs_rewrite).
_NEEDS_REWRITE = [
    "01-000-2bfe564b",
    "01-001-3f613b96",
    "02-000-3542bc50",
    "04-002-05b9f68e",
    "05-001-cd82cb44",
    "06-000-1fdcdae9",
    "06-002-6189d1fa",
]

# Distinctive prose fragments that PROVE a flagged claim was shipping in report.md.
_LEAK_FRAGMENTS = {
    "06-002-6189d1fa": "$27,874 per violation",
    "01-000-2bfe564b": "UN Regulation No. 157 - Automated Lane Keeping Systems (ALKS)",
    "06-000-1fdcdae9": "should not be assumed statistically representative",
    "05-001-cd82cb44": "reported data may not be statistically representative",
    "04-002-05b9f68e": "perform the entire dynamic driving task without driver involvement",
}

# VERIFIED kept claims that MUST survive (precision, not blanket recall).
_VERIFIED_SURVIVORS = [
    "OR 0.457",  # 05-000, VERIFIED
    "0.171",
    "six levels, from Level 0 (no automation) to Level 5",  # 04-000, VERIFIED
    "The term “reporting entities” is defined to include only",  # 01-007 VERIFIED
]


def test_real_drb90_leak_fragments_present_before_redaction():
    """Guard: prove the leak EXISTS in the real artifact before we close it."""
    report, _, _ = _load_real()
    for cid, frag in _LEAK_FRAGMENTS.items():
        assert frag in report, f"{cid} fragment {frag!r} expected in pre-redaction report.md"


def test_real_drb90_material_unsupported_redacted():
    """(a) Every material-non-VERIFIED claim that ships as prose is removed/replaced."""
    report, audit, final_verdicts = _load_real()
    res = reconcile_report_against_verdicts(report, final_verdicts, audit)
    # The leak fragments must be GONE from the redacted body.
    for cid, frag in _LEAK_FRAGMENTS.items():
        assert frag not in res.report_text, (
            f"{cid} fragment {frag!r} STILL present after redaction — leak not closed"
        )
    # Each present leak claim is recorded as redacted.
    redacted_ids = {rc.claim_id for rc in res.redacted}
    for cid in _LEAK_FRAGMENTS:
        assert cid in redacted_ids, f"{cid} should be in redacted records"


def test_real_drb90_verified_claims_survive():
    """(b) PRECISION — VERIFIED kept claims survive; no blanket recall cut."""
    report, audit, final_verdicts = _load_real()
    res = reconcile_report_against_verdicts(report, final_verdicts, audit)
    for survivor in _VERIFIED_SURVIVORS:
        assert survivor in res.report_text, (
            f"VERIFIED survivor {survivor!r} was wrongly redacted (over-redaction)"
        )


def test_real_drb90_gaps_json_one_per_redaction():
    """(c) gaps.json gains exactly one redacted_unsupported entry per removed claim."""
    report, audit, final_verdicts = _load_real()
    res = reconcile_report_against_verdicts(report, final_verdicts, audit)
    gaps = res.gaps_json()
    assert len(gaps) == res.redacted_count
    assert all(g["kind"] == "redacted_unsupported" for g in gaps)
    # claim_id appears exactly once.
    refs = [g["ref"] for g in gaps]
    assert len(refs) == len(set(refs))


def test_real_drb90_absent_claim_is_safe_not_error():
    """02-000 ('Tesla, Inc') is material UNSUPPORTED but downstream dedup already removed
    it from report.md. That is the SAFE state (not shipped) — it must be recorded as
    already_absent, NOT raise.
    """
    report, audit, final_verdicts = _load_real()
    res = reconcile_report_against_verdicts(report, final_verdicts, audit)
    assert "02-000-3542bc50" in res.already_absent
    assert "02-000-3542bc50" not in {rc.claim_id for rc in res.redacted}


def test_s3_unsupported_is_redacted_real_artifact():
    """(e) I-faith-003 #1174 — the S3 leak is CLOSED (BB5-F01 regression on REAL artifacts).
    07-004 is UNSUPPORTED + S3 in the real drb_90 audit map and its prose ('95-98% algorithm
    efficiency') shipped before the fix because the S3 scope guard exempted it from redaction.
    Redaction is now severity-independent, so it MUST be removed.
    """
    report, audit, final_verdicts = _load_real()
    assert final_verdicts["07-004-402b2ac8"] == "UNSUPPORTED"
    assert audit["07-004-402b2ac8"]["severity"] == "S3"
    # Guard: prove the S3 leak was shipping before redaction.
    assert "95–98% algorithm efficiency" in report
    res = reconcile_report_against_verdicts(report, final_verdicts, audit)
    # Now redacted (the observe-only exemption is gone); recorded as a redaction.
    assert "07-004-402b2ac8" in {rc.claim_id for rc in res.redacted}
    assert "95–98% algorithm efficiency" not in res.report_text


def test_s3_verified_still_ships_no_overredaction():
    """Precision: S3 + VERIFIED still ships byte-identical — only a non-VERIFIED verdict
    triggers redaction, never the severity itself."""
    report = "An observed background figure of 12 units.[1]\n"
    audit = {"x-s3v": {"sentence": "An observed background figure of 12 units [#ev:e:0-9].", "severity": "S3"}}
    fv = {"x-s3v": "VERIFIED"}
    res = reconcile_report_against_verdicts(report, fv, audit)
    assert res.report_text == report
    assert res.redacted == []


def test_partial_verdict_at_s3_is_redacted():
    """Codex brief P2-1: PARTIAL is non-VERIFIED and must redact at ANY severity (incl S3)."""
    report = "A partially-supported claim about the thing.[1]\n"
    audit = {"x-part": {"sentence": "A partially-supported claim about the thing [#ev:e:0-9].", "severity": "S3"}}
    fv = {"x-part": "PARTIAL"}
    res = reconcile_report_against_verdicts(report, fv, audit)
    assert "A partially-supported claim about the thing" not in res.report_text
    assert "x-part" in {rc.claim_id for rc in res.redacted}


def test_fail_closed_on_present_but_unlocatable():
    """(d) FAIL-CLOSED: a material non-VERIFIED claim whose normalized prose IS present in
    the report but cannot be pinned to a discrete sentence raises ReportRedactionError.

    Simulate by handing a claim whose sentence is a fragment that appears mid-sentence in
    a heading line (which the line-level redactor skips), so the stem is present in the
    normalized report but unredactable -> must raise.
    """
    report = "# Heading mentioning the secret penalty figure inline\n\nBody line unrelated.\n"
    audit = {
        "99-000-deadbeef": {
            "sentence": "the secret penalty figure [#ev:x:0-10].",
            "severity": "S2",
        }
    }
    final_verdicts = {"99-000-deadbeef": "UNSUPPORTED"}
    with pytest.raises(ReportRedactionError):
        reconcile_report_against_verdicts(report, final_verdicts, audit)


def test_missing_audit_row_for_non_verified_fails_closed():
    """A non-VERIFIED verdict with no audit_map row cannot be located -> fail closed."""
    report = "Body line.\n"
    audit: dict = {}
    final_verdicts = {"01-000-x": "UNSUPPORTED"}
    with pytest.raises(ReportRedactionError):
        reconcile_report_against_verdicts(report, final_verdicts, audit)


def test_all_verified_is_noop():
    """A report whose every claim is VERIFIED is returned byte-identical (no redaction)."""
    report, audit, final_verdicts = _load_real()
    all_verified = {cid: "VERIFIED" for cid in final_verdicts}
    res = reconcile_report_against_verdicts(report, all_verified, audit)
    assert res.report_text == report
    assert res.redacted == []


def test_held_path_runs_identically():
    """(f) The helper is a pure function of (report, verdicts, audit_map) — it does not
    read release_allowed, so it runs identically on the HELD path. Assert the real
    drb_90 case (release_allowed=False) still redacts.
    """
    report, audit, final_verdicts = _load_real()
    manifest = json.loads((_FORENSIC / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["four_role_evaluation"]["release_allowed"] is False
    res = reconcile_report_against_verdicts(report, final_verdicts, audit)
    assert res.redacted_count >= 5


# ─────────────────────────────────────────────────────────────────
# CITATION-MARKER PRESERVATION (Codex iter-1 P1): redacting one sentence must NOT strip the
# [N] citation markers off the VERIFIED sentences around it on the same line, and must NOT
# over-redact a longer VERIFIED sentence that merely shares words with a short rejected claim.
# ─────────────────────────────────────────────────────────────────

def test_redaction_preserves_neighbor_citation_markers():
    """Unit P1 guard: a redacted middle sentence consumes only ITS OWN trailing marker; the
    [8]/[7] markers of the verified sentences on either side survive byte-for-byte."""
    report = (
        "Alpha verified one.[8] Bravo bad claim sentence here.[4] Charlie verified two.[7]\n"
    )
    audit = {
        "x-bravo": {
            "sentence": "Bravo bad claim sentence here [#ev:e:0-9].",
            "severity": "S1",
        }
    }
    fv = {"x-bravo": "UNSUPPORTED"}
    res = reconcile_report_against_verdicts(report, fv, audit)
    assert "Alpha verified one.[8]" in res.report_text, "left neighbor lost its [8]"
    assert "Charlie verified two.[7]" in res.report_text, "right neighbor lost its [7]"
    assert "Bravo bad claim sentence here" not in res.report_text  # the claim is gone
    assert "[4]" not in res.report_text  # the redacted claim's OWN marker is removed with it
    assert "x-bravo" in {rc.claim_id for rc in res.redacted}


def test_real_drb90_verified_survivor_citations_preserved():
    """Real-artifact P1 regression (the exact Codex-reproduced defect): the VERIFIED 05-000
    sentence renders '...crashes.[8]' immediately before the UNSUPPORTED 05-001 sentence on
    the same body line. Redacting 05-001 must NOT strip [8] from the verified neighbor, and
    the OR values + SAE-taxonomy verified sentence keep their cited prose."""
    report, audit, final_verdicts = _load_real()
    res = reconcile_report_against_verdicts(report, final_verdicts, audit)
    assert "crashes.[8]" in res.report_text, "verified 05-000 lost its [8] citation on redaction"
    assert "(OR 0.457)" in res.report_text and "(OR 0.171)" in res.report_text
    assert "Level 5 (full automation)" in res.report_text
    # The VERIFIED 04-000 SAE-taxonomy sentence ends '...sustained basis.[4].[7]' and shares a
    # line with the UNSUPPORTED 04-002 sentence; its [4] marker must survive (this is the exact
    # marker Codex saw drop 21->16 under the bug; the fix keeps it, 21->17 = only redacted-claim [4]s).
    assert "basis.[4]" in res.report_text, "verified 04-000 lost its [4] citation on redaction"
    # No [8] is collateral-dropped: every [8] in the source is on the verified 05-000 sentence.
    assert res.report_text.count("[8]") == report.count("[8]")


def test_no_overredaction_of_verified_sentence_sharing_words():
    """P2-2 guard: a SHORT UNSUPPORTED claim redacts only its own sentence, never a LONGER
    sentence on the same line that merely contains the claim's words as a substring (the
    coverage floor). The longer sentence keeps its [2] marker."""
    report = (
        "The model achieves high recall.[1] "
        "It is well established in prior work that the model achieves high recall on every "
        "held-out benchmark we examined.[2]\n"
    )
    audit = {"bad-1": {"sentence": "The model achieves high recall [#ev:e:0-9].", "severity": "S2"}}
    fv = {"bad-1": "UNSUPPORTED"}
    res = reconcile_report_against_verdicts(report, fv, audit)
    assert "The model achieves high recall.[1]" not in res.report_text  # own sentence redacted
    assert "every held-out benchmark we examined.[2]" in res.report_text  # longer one survives
    assert "[2]" in res.report_text


# ─────────────────────────────────────────────────────────────────
# D8 RULING GUARD (Task 3): the D8 coverage gate is a LEGITIMATE fixed-denominator
# semantic-coverage fraction, NOT a forbidden raw-count gate. This pins the ruling
# (NO change to release_policy.py) by behavior: the denominator is fixed, so dropping a
# claim can only LOWER the fraction — it is un-gameable in the forbidden direction.
# ─────────────────────────────────────────────────────────────────

def test_d8_coverage_gate_is_fixed_denominator_fraction():
    from src.polaris_graph.roles.release_policy import CoverageLedger

    # drb_90: 2 of 6 required entities covered by VERIFIED claims -> 0.333 < 0.70 threshold.
    led = CoverageLedger(
        required_element_ids=["e1", "e2", "e3", "e4", "e5", "e6"],
        covered_element_ids={"e1", "e2"},
    )
    assert abs(led.fraction() - 1 / 3) < 1e-9
    # Dropping/refusing a claim REMOVES it from the numerator; the denominator (required
    # set) is fixed, so the fraction can only fall — never rise. This is why the gate is a
    # completeness measure, not a §-1.1-banned count proxy (which would reward more rows).
    led.covered_element_ids.discard("e2")
    assert abs(led.fraction() - 1 / 6) < 1e-9
    # An empty required set is vacuously complete (1.0) — no count can game it.
    assert CoverageLedger(required_element_ids=[]).fraction() == 1.0


# ─────────────────────────────────────────────────────────────────
# v6 PipelineStatus MIRROR (Codex iter-2 P1): the new abort_report_redaction_failed status is
# loaded into manifest.status -> the v6 actor stores it into pipeline_status -> RunStatusResponse
# validates against the PipelineStatus Literal. Omitting it 500s the GET/list endpoint on a
# redaction-failure abort instead of surfacing the fail-closed status. Mirror it, like
# abort_discovery_degraded / abort_safety_refused / abort_four_role_release_held.
# ─────────────────────────────────────────────────────────────────

def test_abort_report_redaction_failed_in_v6_pipeline_status():
    from typing import get_args

    from src.polaris_v6.schemas.run_status import PipelineStatus

    assert "abort_report_redaction_failed" in get_args(PipelineStatus)


def test_run_status_response_accepts_redaction_failed_without_validationerror():
    """Codex iter-2 repro: RunStatusResponse(..., pipeline_status='abort_report_redaction_failed')
    must construct cleanly — not raise pydantic ValidationError on the API surface."""
    from src.polaris_v6.schemas.run_status import RunStatusResponse

    resp = RunStatusResponse(
        run_id="deadbeef",
        lifecycle_status="completed",
        pipeline_status="abort_report_redaction_failed",
        template="workforce",
        question="q",
        queued_at="2026-06-08T00:00:00Z",
    )
    assert resp.pipeline_status == "abort_report_redaction_failed"
