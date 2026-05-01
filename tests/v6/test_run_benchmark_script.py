"""Tests for scripts/v6/run_benchmark.py — Phase 3 Task 3.5 runner."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "v6" / "run_benchmark.py"


def _load_module():
    if str(ROOT / "src") not in sys.path:
        sys.path.insert(0, str(ROOT / "src"))
    spec = importlib.util.spec_from_file_location("run_benchmark", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_build_suite_from_browsecomp_records():
    mod = _load_module()
    records = [
        {
            "id": "bc_001",
            "prompt": "What was the first official ascent of K2?",
            "target": "1954",
        },
        {
            "id": "bc_002",
            "prompt": "Who painted Starry Night?",
            "target": "Vincent van Gogh",
        },
    ]
    suite = mod.build_suite_from_records(suite="browsecomp", records=records)
    assert suite.suite_version == "v6_phase3_browsecomp_v1"
    assert len(suite.questions) == 2
    assert suite.questions[0].question_id.startswith("browsecomp:")
    assert "polaris_v6" in suite.competing_systems


def test_build_suite_from_gaia_records():
    mod = _load_module()
    records = [
        {
            "task_id": "gaia_42",
            "Question": "Sum of Fibonacci numbers below 100",
            "Final answer": "232",
            "Level": "1",
        },
    ]
    suite = mod.build_suite_from_records(suite="gaia", records=records)
    assert suite.questions[0].difficulty == "routine"


def test_difficulty_mapping():
    mod = _load_module()
    records = [
        {
            "question_id": "drb_1",
            "query": "Compare housing-starts policy across G7 nations",
            "difficulty": "novel_synthesis",
        },
    ]
    suite = mod.build_suite_from_records(
        suite="deepresearch_bench", records=records
    )
    assert suite.questions[0].difficulty == "novel_synthesis"


def test_dry_run_writes_suite_design(tmp_path):
    fixture = tmp_path / "bench.json"
    fixture.write_text(
        json.dumps(
            [{"id": "x", "prompt": "What is BPEI?"}]
        ),
        encoding="utf-8",
    )
    output = tmp_path / "suite.json"
    mod = _load_module()
    rc = mod.main.__wrapped__ if hasattr(mod.main, "__wrapped__") else mod.main
    sys.argv = [
        "run_benchmark.py",
        "--suite",
        "browsecomp",
        "--input",
        str(fixture),
        "--output",
        str(output),
        "--dry-run",
    ]
    assert rc() == 0
    payload = json.loads(output.read_text())
    assert payload["suite_version"] == "v6_phase3_browsecomp_v1"
    assert len(payload["questions"]) == 1


def test_main_errors_on_missing_input(tmp_path):
    mod = _load_module()
    sys.argv = [
        "run_benchmark.py",
        "--suite",
        "browsecomp",
        "--input",
        str(tmp_path / "does_not_exist.json"),
        "--dry-run",
    ]
    assert mod.main() == 2


def test_main_errors_when_backend_missing_and_not_dry_run(tmp_path):
    fixture = tmp_path / "bench.jsonl"
    fixture.write_text(
        json.dumps({"id": "x", "prompt": "test prompt at least 4"}) + "\n",
        encoding="utf-8",
    )
    mod = _load_module()
    sys.argv = [
        "run_benchmark.py",
        "--suite",
        "browsecomp",
        "--input",
        str(fixture),
    ]
    assert mod.main() == 3
