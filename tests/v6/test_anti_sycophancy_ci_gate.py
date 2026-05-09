"""I-anti-003 — CI gate tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.anti_sycophancy_ci_gate import main

_REPO = Path(__file__).resolve().parent.parent.parent
_CORPUS = _REPO / "tests" / "v6" / "fixtures" / "sycophancy_v1" / "paired_prompts.json"
_PASS = _REPO / "tests" / "v6" / "fixtures" / "anti_sycophancy" / "passing_responses.json"
_FAIL = _REPO / "tests" / "v6" / "fixtures" / "anti_sycophancy" / "failing_responses.json"


def _run(responses: Path) -> int:
    return main(["--corpus", str(_CORPUS), "--responses", str(responses)])


def test_gate_passes_on_clean_responses() -> None:
    assert _run(_PASS) == 0


def test_gate_fails_on_drift_responses() -> None:
    assert _run(_FAIL) == 1


def _write(tmp_path: Path, payload: list[dict]) -> Path:
    p = tmp_path / "responses.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def test_gate_rejects_unknown_paired_id(tmp_path: Path) -> None:
    payload = [{
        "paired_id": "unknown_xyz",
        "responses": [
            {"framing": f, "response_text": "factual", "refused": False}
            for f in ("neutral", "leading_positive", "leading_negative", "opposite_frame")
        ],
    }]
    assert _run(_write(tmp_path, payload)) == 1


def test_gate_rejects_empty_responses(tmp_path: Path) -> None:
    assert _run(_write(tmp_path, [])) == 1


def test_gate_rejects_missing_paired_id(tmp_path: Path) -> None:
    full = json.loads(_PASS.read_text(encoding="utf-8"))
    assert _run(_write(tmp_path, full[:-1])) == 1


def test_gate_rejects_duplicate_paired_id(tmp_path: Path) -> None:
    full = json.loads(_PASS.read_text(encoding="utf-8"))
    dupe = full[:-1] + [full[0]]
    assert _run(_write(tmp_path, dupe)) == 1
