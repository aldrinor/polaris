"""Tests for the 3 v6 handover scripts referenced by docs/carney_handover/runbook.md.

  - scripts/v6/cost_summary.py — aggregates EvidenceContract cost_usd
  - scripts/v6/replay_pin.py    — diffs two RunPin JSON files
  - scripts/v6/run_pin_replay.py — pairs baseline+candidate pin sets and gates

Each script is exercised end-to-end via subprocess against a tmp dir with
real fixtures, asserting both stdout content and exit code.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts" / "v6"
FIXTURES = REPO_ROOT / "tests" / "v6" / "fixtures" / "evidence_contract_v1"


def _run(script: str, *args: str, env_extra: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    # Inherit the parent env so pip-installed packages (pydantic, etc.) are
    # discoverable; override PYTHONPATH so `polaris_v6.*` resolves.
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(SCRIPTS / script), *args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


# --- cost_summary.py ---------------------------------------------------------


def test_cost_summary_reads_real_bundles_and_reports(tmp_path: Path) -> None:
    # Use the existing golden fixtures directly — they have real cost_usd.
    result = _run("cost_summary.py", "--bundles-dir", str(FIXTURES))
    assert result.returncode == 0, result.stderr
    assert "matched_runs:" in result.stdout
    assert "sum_cost_usd:" in result.stdout
    assert "avg_cost_usd:" in result.stdout
    assert "min_cost_usd:" in result.stdout


def test_cost_summary_empty_dir_exits_1(tmp_path: Path) -> None:
    result = _run("cost_summary.py", "--bundles-dir", str(tmp_path))
    assert result.returncode == 1
    assert "no bundles matched" in result.stdout


def test_cost_summary_since_filter_excludes_old(tmp_path: Path) -> None:
    # All goldens are dated 2026-05-01; --since 2030-01-01 excludes everything.
    result = _run(
        "cost_summary.py",
        "--bundles-dir",
        str(FIXTURES),
        "--since",
        "2030-01-01",
    )
    assert result.returncode == 1
    assert "no bundles matched" in result.stdout


# --- replay_pin.py -----------------------------------------------------------


def _write_pin(path: Path, **overrides) -> None:
    base = {
        "pin_id": "pin_001",
        "workspace_id": "ws_default",
        "run_id": "run_alpha",
        "template": "clinical",
        "question": "Does drug X reduce CV events?",
        "document_ids": [],
        "pinned_at": "2026-05-01T10:00:00Z",
        "generator_model": "deepseek/v4-flash",
        "verifier_model": "google/gemma-4-31b",
        "generator_seed": 42,
        "sealed_evidence_pool_ids": ["ev1", "ev2"],
        "sealed_verified_sentence_count": 10,
        "sealed_pipeline_status": "success",
        "sealed_cost_usd": 0.42,
    }
    base.update(overrides)
    path.write_text(json.dumps(base), encoding="utf-8")


def test_replay_pin_no_change_exits_0_no_regression(tmp_path: Path) -> None:
    orig = tmp_path / "orig.json"
    rep = tmp_path / "rep.json"
    _write_pin(orig, pin_id="pin_a")
    _write_pin(rep, pin_id="pin_b")
    result = _run("replay_pin.py", "--original", str(orig), "--replay", str(rep))
    assert result.returncode == 0, result.stderr
    assert "is_regression:   False" in result.stdout


def test_replay_pin_pipeline_status_regression_exits_1(tmp_path: Path) -> None:
    orig = tmp_path / "orig.json"
    rep = tmp_path / "rep.json"
    _write_pin(orig, pin_id="pin_a", sealed_pipeline_status="success")
    _write_pin(
        rep,
        pin_id="pin_b",
        sealed_pipeline_status="abort_no_verified_sections",
    )
    result = _run("replay_pin.py", "--original", str(orig), "--replay", str(rep))
    assert result.returncode == 1
    assert "is_regression:   True" in result.stdout


def test_replay_pin_json_emit(tmp_path: Path) -> None:
    orig = tmp_path / "orig.json"
    rep = tmp_path / "rep.json"
    _write_pin(orig, pin_id="pin_a")
    _write_pin(rep, pin_id="pin_b")
    result = _run("replay_pin.py", "--original", str(orig), "--replay", str(rep), "--json")
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["original_pin_id"] == "pin_a"
    assert payload["replay_pin_id"] == "pin_b"
    assert payload["is_regression"] is False


# --- run_pin_replay.py -------------------------------------------------------


def test_run_pin_replay_clean_pass(tmp_path: Path) -> None:
    bdir = tmp_path / "baseline"
    cdir = tmp_path / "candidate"
    bdir.mkdir()
    cdir.mkdir()
    _write_pin(bdir / "p1.json", pin_id="b_p1", run_id="run_alpha")
    _write_pin(cdir / "p1.json", pin_id="c_p1", run_id="run_alpha")
    result = _run(
        "run_pin_replay.py",
        "--baseline-dir",
        str(bdir),
        "--candidate-dir",
        str(cdir),
    )
    assert result.returncode == 0, result.stderr
    assert "verdict: PASS" in result.stdout


def test_run_pin_replay_regression_fails(tmp_path: Path) -> None:
    bdir = tmp_path / "baseline"
    cdir = tmp_path / "candidate"
    bdir.mkdir()
    cdir.mkdir()
    _write_pin(
        bdir / "p1.json",
        pin_id="b_p1",
        run_id="run_alpha",
        sealed_pipeline_status="success",
    )
    _write_pin(
        cdir / "p1.json",
        pin_id="c_p1",
        run_id="run_alpha",
        sealed_pipeline_status="abort_no_verified_sections",
    )
    result = _run(
        "run_pin_replay.py",
        "--baseline-dir",
        str(bdir),
        "--candidate-dir",
        str(cdir),
    )
    assert result.returncode == 1
    assert "verdict: FAIL" in result.stdout
    assert "regressions: 1" in result.stdout


def test_run_pin_replay_missing_baseline_dir_exits_2(tmp_path: Path) -> None:
    result = _run(
        "run_pin_replay.py",
        "--baseline-dir",
        str(tmp_path / "nope"),
        "--candidate-dir",
        str(tmp_path),
    )
    assert result.returncode == 2
