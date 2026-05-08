"""I-bench-001 — benchmark proof-package harness tests."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import scripts.benchmark_proof_package as harness

_ALL6 = [
    "factual_accuracy", "citation_health", "frame_coverage",
    "contradiction_handling", "refusal_calibration", "user_traceability",
]


def _suite(score_dims: list[str], **q_extra) -> dict:
    q = {"question_id": "q1", "template": "clinical_summary",
         "text": "Does aspirin reduce migraine?", "difficulty": "routine",
         "expected_anchors": [], "expected_pico_keywords": [],
         "expected_refusals": [], **q_extra}
    return {"suite_version": "v6_phase3_v1", "questions": [q],
            "competing_systems": ["polaris_v6", "chatgpt_5_5_pro_dr"],
            "score_dimensions": score_dims, "layer_3_evaluator_required": True}


def _run(tmp: Path, suite: dict, responses: dict[str, str]) -> dict:
    sd = tmp / "suite.json"
    sd.write_text(json.dumps(suite), encoding="utf-8")
    rd = tmp / "responses"
    rd.mkdir()
    for k, v in responses.items():
        (rd / f"{k}.txt").write_text(v, encoding="utf-8")
    out = tmp / "out"
    rc = harness.main(["--suite-design", str(sd), "--responses-dir", str(rd),
                       "--output", str(out)])
    assert rc == 0
    return json.loads((out / "proof_package.json").read_text(encoding="utf-8"))


def test_harness_runs_end_to_end(tmp_path: Path) -> None:
    pkg = _run(tmp_path, _suite(_ALL6), {
        "q1_polaris_v6": "aspirin migraine http://a",
        "q1_chatgpt_5_5_pro_dr": "answer",
    })
    assert len(pkg["scores"]) == 2
    assert (tmp_path / "out" / "summary.md").exists()


def test_score_uses_coverage_scorer(tmp_path: Path) -> None:
    pkg = _run(tmp_path, _suite(_ALL6, expected_pico_keywords=["aspirin", "migraine"]), {
        "q1_polaris_v6": "Aspirin reduces migraine.",
        "q1_chatgpt_5_5_pro_dr": "unrelated",
    })
    fa = next(d for s in pkg["scores"] if s["system"] == "polaris_v6"
              for d in s["dimensions"] if d["dimension"] == "factual_accuracy")
    assert fa["raw"] == 1.0


def test_missing_response_yields_empty(tmp_path: Path) -> None:
    pkg = _run(tmp_path, _suite(_ALL6[:4]), {})
    for a in pkg["answers"]:
        assert a["response_text"] == "" and a["citations_count"] == 0


@pytest.mark.parametrize("dims", [_ALL6[:4], _ALL6])
def test_dimensions_always_six_with_filter(tmp_path: Path, dims: list[str]) -> None:
    pkg = _run(tmp_path, _suite(dims), {})
    sel = set(dims)
    for s in pkg["scores"]:
        assert len(s["dimensions"]) == 6
        for d in s["dimensions"]:
            if d["dimension"] not in sel:
                assert d["raw"] == 0.0 and "not requested" in d["rationale"]
    assert pkg["suite"]["layer_3_evaluator_required"] is False


def test_subprocess_runs_end_to_end(tmp_path: Path) -> None:
    sd = tmp_path / "suite.json"
    sd.write_text(json.dumps(_suite(_ALL6)), encoding="utf-8")
    rd = tmp_path / "responses"
    rd.mkdir()
    out = tmp_path / "out"
    repo = Path(__file__).resolve().parents[3]
    rc = subprocess.run(
        [sys.executable, str(repo / "scripts" / "benchmark_proof_package.py"),
         "--suite-design", str(sd), "--responses-dir", str(rd), "--output", str(out)],
        cwd=str(repo), check=False,
    )
    assert rc.returncode == 0
    assert (out / "proof_package.json").exists()
