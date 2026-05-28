"""PR-3 scoring pipeline tests (I-safety-002b #925). Pure, offline.

Covers: ledger_schema validation + duplicate detection, reconcile conservative-MAX +
silent-auditor escalation + identity-mismatch error, score_run polaris gate enforcement +
INVALID sentinel skip + ledger/rubric mismatch error, aggregate_systems final-report
shape + invalid-row reporting.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.dr_benchmark.ledger_schema import (
    Claim, Coverage, Ledger, dump_ledger, load_ledger,
)
from scripts.dr_benchmark.reconcile import reconcile
from scripts.dr_benchmark.score_run import InvalidRunError, score_one
from scripts.dr_benchmark.aggregate_systems import render_final_report

_RUBRIC_SHA = "deadbeef" * 8


# --- ledger_schema validation ----------------------------------------------
def test_claim_unreachable_requires_subtype() -> None:
    with pytest.raises(ValueError, match="UNREACHABLE requires"):
        Claim(claim_id="c1", severity="S1", verdict="UNREACHABLE", citation_id="x")


def test_claim_fabricated_requires_span() -> None:
    with pytest.raises(ValueError, match="FABRICATED requires"):
        Claim(claim_id="c1", severity="S1", verdict="FABRICATED", citation_id="x")
    # ok with span
    Claim(claim_id="c1", severity="S1", verdict="FABRICATED",
          citation_id="x", span_quote="refuting")


def test_claim_unsupported_cited_traceability() -> None:
    with pytest.raises(ValueError, match="traceability"):
        Claim(claim_id="c1", severity="S1", verdict="UNSUPPORTED", citation_id="x")
    # ok with audit_note
    Claim(claim_id="c1", severity="S1", verdict="UNSUPPORTED", citation_id="x",
          audit_note="no supporting span found")


def test_ledger_duplicate_claim_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate claim_id"):
        Ledger(
            system="polaris", question_id="Q75", auditor="claude",
            audit_method="m", audit_timestamp_utc="2026-05-28T00:00:00Z",
            rubric_sha256=_RUBRIC_SHA,
            claims=[
                Claim("c1", "S1", "VERIFIED"),
                Claim("c1", "S1", "VERIFIED"),  # duplicate
            ],
        )


def test_ledger_dump_load_roundtrip(tmp_path: Path) -> None:
    led = Ledger(
        system="polaris", question_id="Q75", auditor="claude",
        audit_method="dual-§-1.1-2026-05-28", audit_timestamp_utc="2026-05-28T00:00:00Z",
        rubric_sha256=_RUBRIC_SHA,
        claims=[Claim("c1", "S1", "VERIFIED", citation_id="src1", span_quote="ok")],
        coverage=[Coverage("Q75-E1", True, True)],
    )
    p = tmp_path / "led.json"
    dump_ledger(led, p)
    led2 = load_ledger(p)
    assert led2.claims[0].claim_id == "c1"
    assert led2.coverage[0].element_id == "Q75-E1"


# --- reconcile (conservative-MAX) -----------------------------------------
def _ledger(auditor: str, claim_verdict: str, *, severity: str = "S1",
            covered: bool = True, cited: bool = True,
            span: str | None = None, note: str | None = None,
            subtype: str | None = None) -> Ledger:
    rows = []
    if claim_verdict == "FABRICATED" or claim_verdict == "PARTIAL":
        span = span or "refuting"
    if claim_verdict == "UNREACHABLE":
        subtype = subtype or "paywall"
    if claim_verdict == "UNSUPPORTED":
        note = note or "no supporting span"
    rows.append(Claim(
        claim_id="c1", severity=severity, verdict=claim_verdict,
        citation_id="src1", span_quote=span, unreachable_subtype=subtype, audit_note=note,
    ))
    return Ledger(
        system="polaris", question_id="Q75", auditor=auditor,
        audit_method=f"dual-{auditor}", audit_timestamp_utc="2026-05-28T00:00:00Z",
        rubric_sha256=_RUBRIC_SHA,
        claims=rows,
        coverage=[Coverage("Q75-E1", covered, cited)],
    )


def test_reconcile_conservative_max_takes_worse_verdict() -> None:
    a = _ledger("claude", "VERIFIED")
    b = _ledger("codex", "FABRICATED")
    r = reconcile(a, b)
    assert r.claims[0].verdict == "FABRICATED"
    assert "conservative-MAX" in (r.claims[0].audit_note or "")


def test_reconcile_conservative_max_escalates_severity() -> None:
    a = _ledger("claude", "VERIFIED", severity="S2")
    b = _ledger("codex", "VERIFIED", severity="S0")
    r = reconcile(a, b)
    # both VERIFIED -> verdict stays VERIFIED, severity escalates to S0 (highest)
    assert r.claims[0].verdict == "VERIFIED"
    assert r.claims[0].severity == "S0"


def test_reconcile_coverage_worse_of_two() -> None:
    a = _ledger("claude", "VERIFIED", covered=True, cited=True)
    b = _ledger("codex", "VERIFIED", covered=False, cited=False)
    r = reconcile(a, b)
    assert r.coverage[0].covered is False
    assert r.coverage[0].citation_supported is False


def test_reconcile_silent_auditor_escalates() -> None:
    # One auditor missed claim "c2" entirely — conservative escalation kicks in.
    a = _ledger("claude", "VERIFIED")
    b = _ledger("codex", "VERIFIED")
    # add a 2nd claim only to claude
    a.claims.append(Claim("c2", "S1", "VERIFIED", citation_id="src2", span_quote="x"))
    r = reconcile(a, b)
    c2 = next(c for c in r.claims if c.claim_id == "c2")
    assert c2.verdict in ("UNSUPPORTED", "FABRICATED")  # escalated above VERIFIED
    assert "silent" in (c2.audit_note or "")


def test_reconcile_rubric_sha_mismatch_raises() -> None:
    a = _ledger("claude", "VERIFIED")
    b = _ledger("codex", "VERIFIED")
    b.rubric_sha256 = "0" * 64
    with pytest.raises(ValueError, match="rubric_sha256 mismatch"):
        reconcile(a, b)


# --- score_run polaris gate enforcement -----------------------------------
def _good_ledger_path(tmp_path: Path, system: str = "polaris", question: str = "Q75") -> Path:
    led = Ledger(
        system=system, question_id=question, auditor="reconciled",
        audit_method="reconciled-test", audit_timestamp_utc="2026-05-28T00:00:00Z",
        rubric_sha256=_RUBRIC_SHA,
        claims=[Claim("c1", "S1", "VERIFIED", citation_id="src1", span_quote="ok")],
        coverage=[Coverage("Q75-E1", True, True), Coverage("Q75-E2", True, True),
                  Coverage("Q75-E3", True, True), Coverage("Q75-E4", True, True),
                  Coverage("Q75-E5", True, True), Coverage("Q75-E6", True, True),
                  Coverage("Q75-E7", True, True)],
    )
    p = tmp_path / "ledger.json"
    dump_ledger(led, p)
    return p


def _good_rubric_path(tmp_path: Path) -> Path:
    rubric = {
        "rubric_sha256": _RUBRIC_SHA,
        "rubric_path": "test/rubric.md",
        "build_timestamp_utc": "2026-05-28T00:00:00Z",
        "questions": [
            {
                "question_id": "Q75", "title": "test",
                "elements": [{"element_id": f"Q75-E{i}", "requirement_text": f"e{i}"}
                             for i in range(1, 8)],
            },
        ],
    }
    p = tmp_path / "rubric.json"
    p.write_text(json.dumps(rubric), encoding="utf-8")
    return p


def test_score_polaris_refuses_when_invalid_sentinel(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "pathB_gate_INVALID").write_text("preflight FAIL: example", encoding="utf-8")
    with pytest.raises(InvalidRunError, match="INVALID"):
        score_one(
            system="polaris", question_id="Q75",
            rubric_path=_good_rubric_path(tmp_path),
            ledger_path=_good_ledger_path(tmp_path),
            run_dir=run_dir,
        )


def test_score_polaris_refuses_when_no_gate_result(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    with pytest.raises(InvalidRunError, match="missing pathB_gate_result"):
        score_one(
            system="polaris", question_id="Q75",
            rubric_path=_good_rubric_path(tmp_path),
            ledger_path=_good_ledger_path(tmp_path),
            run_dir=run_dir,
        )


def test_score_polaris_refuses_when_gate_fail(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "pathB_gate_result.json").write_text(
        json.dumps({"verdict": "FAIL", "reason": "OPENROUTER_ALLOW_FALLBACKS"}),
        encoding="utf-8",
    )
    with pytest.raises(InvalidRunError, match="verdict != PASS"):
        score_one(
            system="polaris", question_id="Q75",
            rubric_path=_good_rubric_path(tmp_path),
            ledger_path=_good_ledger_path(tmp_path),
            run_dir=run_dir,
        )


def test_score_polaris_passes_with_gate_pass(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "pathB_gate_result.json").write_text(
        json.dumps({"verdict": "PASS", "served_identity_by_role": {}}),
        encoding="utf-8",
    )
    scored = score_one(
        system="polaris", question_id="Q75",
        rubric_path=_good_rubric_path(tmp_path),
        ledger_path=_good_ledger_path(tmp_path),
        run_dir=run_dir,
    )
    assert scored["passed"] is True
    assert scored["system"] == "polaris"


def test_score_competitor_no_gate_check_needed(tmp_path: Path) -> None:
    # chatgpt/gemini have no Path-B gate (they aren't our pipeline).
    scored = score_one(
        system="chatgpt", question_id="Q75",
        rubric_path=_good_rubric_path(tmp_path),
        ledger_path=_good_ledger_path(tmp_path, system="chatgpt"),
        run_dir=None,
    )
    assert scored["system"] == "chatgpt"


def test_score_rubric_ledger_sha_mismatch_raises(tmp_path: Path) -> None:
    rubric = json.loads(_good_rubric_path(tmp_path).read_text())
    rubric["rubric_sha256"] = "different" * 8
    p = tmp_path / "rubric_mismatch.json"
    p.write_text(json.dumps(rubric), encoding="utf-8")
    with pytest.raises(ValueError, match="rubric_sha256 mismatch"):
        score_one(
            system="chatgpt", question_id="Q75",
            rubric_path=p, ledger_path=_good_ledger_path(tmp_path, system="chatgpt"),
            run_dir=None,
        )


# --- aggregate_systems final report --------------------------------------
def test_aggregate_renders_clinical_3_and_overall_5(tmp_path: Path) -> None:
    scored_dir = tmp_path / "scored"
    scored_dir.mkdir()
    # 1 pass, 1 fail, 1 invalid
    (scored_dir / "polaris_Q75.json").write_text(json.dumps({
        "system": "polaris", "question_id": "Q75", "passed": True,
        "lane1": {"hard_fail_count": 0}, "lane2": {"coverage_fraction": 0.9},
        "reasons": [],
    }), encoding="utf-8")
    (scored_dir / "polaris_Q76.json").write_text(json.dumps({
        "system": "polaris", "question_id": "Q76", "passed": False,
        "lane1": {"hard_fail_count": 1}, "lane2": {"coverage_fraction": 0.5},
        "reasons": ["1 hard fail", "low coverage"],
    }), encoding="utf-8")
    (scored_dir / "polaris_Q78.json").write_text(json.dumps({
        "system": "polaris", "question_id": "Q78", "passed": False,
        "invalid": True, "reason": "pathB_gate_INVALID present",
    }), encoding="utf-8")
    freeze_pin = tmp_path / "freeze_pin.txt"
    freeze_pin.write_text(
        "abc123  .codex/I-safety-002b/gold_rubrics_pathB.md\n",
        encoding="utf-8",
    )
    out = tmp_path / "final_report.md"
    rc = render_final_report(scored_dir=scored_dir, freeze_pin=freeze_pin, out_path=out)
    assert rc == 0
    text = out.read_text(encoding="utf-8")
    # honest label + sections
    assert "DRB-EN high-stakes citation-faithfulness stress slice" in text
    assert "Clinical-3 (#75/#76/#78)" in text
    assert "Overall-5 (#72/#75/#76/#78/#90)" in text
    # invalid row reported, but omitted from numerator (1 passed / 2 valid)
    assert "INVALID" in text
    assert "1/2" in text  # polaris: 1 passed of 2 valid in clinical-3
    # identity pins block present
    assert "freeze_pin.txt" in text
    assert "abc123" in text
