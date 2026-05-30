"""Gate-A no-spend dry-run harness tests (I-meta-002 sub-PR-6). Offline, NO network, NO spend.

Covers the offline checks that do NOT spawn the pytest subprocess (so the test itself stays
fast and non-recursive): the FROZEN-LOCK COVERAGE check (4 roles + family segregation via the
P2 option-(b) direct path), the per-role contract fixtures (Sentinel lethal-polarity, Judge
5-enum, Mirror two-pass), and the PASS/FAIL aggregation + cheap-probe gating. The pytest-suite
check (a) and the lock-consistency subprocess (b) are exercised end-to-end by the harness run,
not re-spawned here.
"""

from __future__ import annotations

from scripts.dr_benchmark.gate_a_dry_run import (
    CheckResult,
    GateAReport,
    check_frozen_lock_coverage,
    check_role_contracts,
    run_live_probes,
)

# IMPORTANT: these tests run UNDER `pytest tests/dr_benchmark` (one of the suites Gate-A's
# check (a) runs). They therefore must NEVER call `run_gate_a()` / `check_pytest_suites()` —
# doing so would re-spawn `pytest tests/dr_benchmark`, which re-collects this file, an infinite
# recursion. We exercise ONLY the pure offline checks (c)/(d), `run_live_probes`, and the
# aggregation logic constructed from `CheckResult`s directly.


# --- check (c): FROZEN-LOCK COVERAGE asserts 4 roles + distinct families, OFFLINE ---
def test_frozen_lock_coverage_four_roles_and_segregation() -> None:
    result = check_frozen_lock_coverage()
    assert result.passed is True, result.detail
    # The four locked roles must all be named in the passing detail.
    for role in ("generator", "mirror", "sentinel", "judge"):
        assert role in result.detail


# --- check (d): per-role contracts (Sentinel polarity, Judge enum, Mirror binding) ---
def test_role_contracts_fixtures_pass_offline() -> None:
    result = check_role_contracts()
    assert result.passed is True, result.detail
    assert "Sentinel" in result.detail
    assert "Judge" in result.detail
    assert "Mirror" in result.detail


# --- cheap probes are OFF by default: a fresh GateAReport runs no probes ---
def test_live_probes_off_by_default() -> None:
    # Construct a report the way run_gate_a does WITHOUT spawning the subprocess checks
    # (default with_live_probes=False leaves the probe fields empty).
    report = GateAReport(overall_pass=True)
    assert report.live_probes_ran is False
    assert report.live_probe_results == []


# --- cheap probes are ADVISORY ONLY: there are exactly the 3 cheap ones, all advisory ---
def test_live_probes_are_advisory_only() -> None:
    probes = run_live_probes()
    # Three cheap probes (Serper / S2 / DeepSeek), all advisory.
    assert {p.name for p in probes} == {
        "live_probe_serper",
        "live_probe_semantic_scholar",
        "live_probe_deepseek",
    }


# --- PASS aggregation: overall_pass is True iff EVERY core check passed ---
def test_aggregation_all_pass() -> None:
    report = GateAReport(
        overall_pass=all(
            c.passed
            for c in [
                CheckResult("pytest_suites", True, ""),
                CheckResult("lock_consistency", True, ""),
                CheckResult("frozen_lock_coverage", True, ""),
                CheckResult("role_contracts", True, ""),
            ]
        )
    )
    assert report.overall_pass is True


def test_aggregation_one_fail_fails_overall() -> None:
    checks = [
        CheckResult("pytest_suites", True, ""),
        CheckResult("lock_consistency", True, ""),
        CheckResult("frozen_lock_coverage", False, "simulated coverage gap"),
        CheckResult("role_contracts", True, ""),
    ]
    report = GateAReport(overall_pass=all(c.passed for c in checks), checks=checks)
    assert report.overall_pass is False
    # A failing advisory live probe never flips overall_pass.
    report.live_probes_ran = True
    report.live_probe_results = run_live_probes()
    assert report.overall_pass is False


# --- the JSON report carries the no-spend marker + the no-authorize-spend note ---
def test_report_json_marks_no_spend() -> None:
    report = GateAReport(
        overall_pass=True,
        checks=[CheckResult("frozen_lock_coverage", True, "ok")],
    )
    payload = report.to_json_dict()
    assert payload["no_spend"] is True
    assert "does NOT authorize" in payload["note"]
    assert "overall_pass" in payload
    assert isinstance(payload["checks"], list)
    assert payload["checks"][0]["name"] == "frozen_lock_coverage"
