"""S5 DRY-E2E integration proof — the run_gate_e2e harness threads the FULL fresh-e2e
path to run_one_query's REAL interface, OFFLINE (network mocked), and FAILS LOUD on abort.

This is the guarantee the next LIVE run completes without the two live-probe failures:

  (2) DOMAIN: the harness must hand run_one_query a scope-gate-ACCEPTED domain. The live
      probe aborted because domain='labor' (not in scope_gate.SUPPORTED_DOMAINS) made
      run_scope_gate reject BEFORE retrieval. Task 72's champion domain is 'workforce'
      (SWEEP_QUERIES in run_honest_sweep_r3.py; champion run_id SWEEP_workforce_drb_72_ai_labor).

  (3) FAIL-LOUD: the harness must NOT print "ALL OK" / exit 0 when run_one_query aborts
      (it writes a STUB report.md on scope-reject, so report.md-exists is NOT proof of success)
      or when no report.md is produced.

Everything here is OFFLINE: the gate runs on the deterministic offline compiler stub (no
OPENROUTER), and run_one_query is replaced by a NETWORK-MOCKED stub with the SAME
(q, out_root) -> summary-dict interface. We assert, against that real interface:

  * the q dict carries an ACCEPTED scope-gate domain (workforce for task 72) + the VERBATIM
    task-72 question (byte-match — no prompt drift / no DRB-II rebind);
  * run_one_query is invoked with PG_GATE + PG_USE_RESEARCH_PLANNER threaded into the env, so
    the S2 RetrievalProjection hook (run_honest_sweep_r3.py:10448) would fire;
  * a report.md path is produced and the RACE/FACT scoring stage receives valid inputs
    (a real, co-located report.md);
  * FAIL-LOUD fires (per-draw NOT ok, run non-zero) if the run ABORTS (abort_* status) or if
    NO report.md is produced — even though the abort path writes a stub report.md.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import scripts.run_gate_e2e as h
from src.polaris_graph.nodes.scope_gate import SUPPORTED_DOMAINS


TASK_72 = "72"


def _task72_prompt() -> str:
    return h._load_drb_task(TASK_72)["prompt"]


# ---------------------------------------------------------------------------
# Fix (2): domain mapping — task 72 -> an ACCEPTED scope-gate domain (workforce)
# ---------------------------------------------------------------------------

def test_task72_domain_is_scope_gate_accepted():
    q = h._query_dict_for_task(h._load_drb_task(TASK_72))
    assert q["domain"] == "workforce", (
        "task 72 must map to the champion domain 'workforce' "
        "(SWEEP_workforce_drb_72_ai_labor), NOT the live-probe's 'labor'."
    )
    assert q["domain"] in SUPPORTED_DOMAINS, "domain must be scope-gate-accepted"
    # verbatim DRB-v1 prompt threaded as q['question'] (no rebind)
    assert q["question"] == _task72_prompt()
    assert q["slug"] == "drb_72_ai_labor"


def test_every_mapped_domain_is_accepted():
    # No task in the S5 slate may map to a domain run_scope_gate would reject.
    for tid, dom in h._TASK_DOMAIN.items():
        assert dom in SUPPORTED_DOMAINS, f"task {tid} -> {dom!r} not in SUPPORTED_DOMAINS"
    assert h._DEFAULT_DOMAIN in SUPPORTED_DOMAINS


def test_unsupported_domain_fails_loud_at_assembly(monkeypatch):
    # A regression that reintroduced a bad domain must fail at assembly, not deep in the run.
    monkeypatch.setitem(h._TASK_DOMAIN, TASK_72, "labor")  # the live-probe's bad value
    with pytest.raises(SystemExit) as ei:
        h._query_dict_for_task(h._load_drb_task(TASK_72))
    assert "SUPPORTED_DOMAINS" in str(ei.value)


# ---------------------------------------------------------------------------
# The DRY-E2E full-path wiring proof (offline, network mocked)
# ---------------------------------------------------------------------------

def _drive_dry_e2e(tmp_path: Path, *, status: str, write_report: bool, seen: dict) -> dict:
    """Drive the FULL live harness path for task 72 against a network-mocked run_one_query.

    The mock captures the exact (q, out_root) + env it was called with into ``seen`` so the
    test can assert the wiring the REAL run_one_query depends on. Returns the per-task result.
    """
    prompt = _task72_prompt()

    base_mock = h.make_mock_run_one_query(
        expected_question=prompt, status=status, write_report=write_report,
    )

    async def _capturing_mock(q, out_root):
        import os
        seen["q"] = dict(q)
        seen["PG_GATE"] = os.environ.get("PG_GATE")
        seen["PG_USE_RESEARCH_PLANNER"] = os.environ.get("PG_USE_RESEARCH_PLANNER")
        return await base_mock(q, out_root)

    return h._process_task(
        TASK_72, out_root=tmp_path, mode="autonomous", gate_on=True,
        dry=False, dry_e2e=True, e2e_runner=_capturing_mock,
        draws=1, score_race=False, score_fact=False,
    )


def test_dry_e2e_success_wires_full_path(tmp_path):
    """Success path: accepted domain + verbatim prompt + gate env threaded -> report produced
    -> scoring inputs present -> per-draw OK. Proves the wiring the next LIVE run relies on."""
    seen: dict = {}
    res = _drive_dry_e2e(
        tmp_path, status="released_with_disclosed_gaps", write_report=True, seen=seen)
    draw = res["draws"][0]

    # (a) run_one_query received an ACCEPTED domain + the VERBATIM task-72 question
    assert seen["q"]["domain"] == "workforce"
    assert seen["q"]["domain"] in SUPPORTED_DOMAINS
    assert seen["q"]["question"] == _task72_prompt()
    assert seen["q"]["slug"] == "drb_72_ai_labor"

    # (b) the gate env slate threaded so the S2 projection would fire (PG_GATE +
    #     PG_USE_RESEARCH_PLANNER — run_honest_sweep_r3.py:10448 requires BOTH)
    assert seen["PG_GATE"] == "1"
    assert seen["PG_USE_RESEARCH_PLANNER"] == "1"

    # (c) the fresh-e2e stage saw a real (non-abort) report and did NOT flag abort
    fe = draw["stages"]["fresh_e2e"]
    assert fe["report_exists"] is True
    assert fe["aborted"] is False
    assert fe["sweep_status"] == "released_with_disclosed_gaps"

    # (d) scoring inputs are present: a co-located, non-trivial report.md the RACE/FACT
    #     stages consume, plus the contract-compliance audit ran on the REAL report
    run_dir = Path(draw["run_dir"])
    report_md = run_dir / "report.md"
    assert report_md.exists() and len(report_md.read_text()) > 50
    assert (run_dir / "contract_compliance.json").exists()
    assert "audit" in draw["stages"]

    # (e) the draw is OK and there is NO error
    assert draw.get("live_ok") is True
    assert not draw.get("error")


def test_dry_e2e_abort_status_triggers_fail_loud(tmp_path):
    """FAIL-LOUD: an abort_* status (e.g. scope reject) must make the draw NOT ok and set an
    error — EVEN THOUGH run_one_query wrote a stub report.md. This is the false-OK fix."""
    seen: dict = {}
    res = _drive_dry_e2e(
        tmp_path, status="abort_scope_rejected", write_report=True, seen=seen)
    draw = res["draws"][0]

    fe = draw["stages"]["fresh_e2e"]
    assert fe["report_exists"] is True          # the abort STUB report.md exists ...
    assert fe["aborted"] is True                # ... but the harness detects the abort
    assert draw.get("live_ok") is not True      # NOT scoreable
    assert draw.get("error")                    # fail-loud error set
    assert "abort_scope_rejected" in draw["error"]
    # the abort report was NOT audited/promoted as a scoreable report
    assert "audit" not in draw["stages"]


def test_dry_e2e_missing_report_triggers_fail_loud(tmp_path):
    """FAIL-LOUD: no report.md (with a non-abort status) is still a FAILURE."""
    seen: dict = {}
    res = _drive_dry_e2e(
        tmp_path, status="released_with_disclosed_gaps", write_report=False, seen=seen)
    draw = res["draws"][0]
    assert draw["stages"]["fresh_e2e"]["report_exists"] is False
    assert draw.get("live_ok") is not True
    assert draw.get("error")
    assert "no report.md" in draw["error"]


# ---------------------------------------------------------------------------
# Fix (3): main() must exit NON-ZERO (never "ALL OK") on abort / missing report
# ---------------------------------------------------------------------------

def _run_main(monkeypatch, tmp_path, *, status: str, write_report: bool, extra_argv=()):
    """Invoke the harness main() end-to-end in --dry-e2e with a mocked runner of the given
    terminal status, so we can assert the process-level exit code + ALL OK / FAIL reporting."""
    # main() builds the mock per task from the DRB prompt via make_mock_run_one_query; patch the
    # factory so every task uses OUR status/write_report while keeping its REAL wiring assertions
    # (accepted domain / verbatim question / gate env). The factory still receives the correct
    # expected_question per task, so the byte-exact prompt assertion inside the mock still holds.
    _real_factory = h.make_mock_run_one_query

    def _factory(**kw):
        kw["status"] = status
        kw["write_report"] = write_report
        return _real_factory(**kw)

    monkeypatch.setattr(h, "make_mock_run_one_query", _factory)
    argv = ["run_gate_e2e.py", "--task-id", TASK_72, "--dry-e2e",
            "--out-root", str(tmp_path)] + list(extra_argv)
    monkeypatch.setattr(h.sys, "argv", argv)
    return h.main()


def test_main_exit_zero_and_all_ok_on_success(monkeypatch, tmp_path, capsys):
    rc = _run_main(monkeypatch, tmp_path,
                   status="released_with_disclosed_gaps", write_report=True)
    out = capsys.readouterr().out
    assert rc == 0
    assert "ALL OK" in out
    summary = json.loads((tmp_path / "gate_e2e_summary.json").read_text())
    assert summary["all_ok"] is True


def test_main_exit_nonzero_and_not_all_ok_on_abort(monkeypatch, tmp_path, capsys):
    rc = _run_main(monkeypatch, tmp_path,
                   status="abort_scope_rejected", write_report=True)
    cap = capsys.readouterr()
    assert rc == 1, "an aborted run must exit NON-ZERO"
    # the harness must NOT print the success banner
    assert "ALL OK" not in cap.out
    assert "FAIL" in cap.err
    summary = json.loads((tmp_path / "gate_e2e_summary.json").read_text())
    assert summary["all_ok"] is False


def test_main_exit_nonzero_on_missing_report(monkeypatch, tmp_path, capsys):
    rc = _run_main(monkeypatch, tmp_path,
                   status="released_with_disclosed_gaps", write_report=False)
    cap = capsys.readouterr()
    assert rc == 1
    assert "ALL OK" not in cap.out
    assert "no report.md" in cap.err.lower() or "no scoreable" in cap.err.lower()
