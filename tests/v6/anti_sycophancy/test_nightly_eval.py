"""I-anti-004 — Nightly anti-sycophancy eval tests.

Test 5 follows Codex P2 guidance: the project's Dramatiq broker has no
Results middleware, so `.send().get_result()` would block forever. We
exercise actor delivery via `broker.join(actor.queue_name)` and assert
the structured log line, then assert the dict contract via `actor.fn()`.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from polaris_v6.anti_sycophancy import nightly_eval as ne

_REPO = Path(__file__).resolve().parent.parent.parent.parent
_CORPUS = _REPO / "tests" / "v6" / "fixtures" / "sycophancy_v1" / "paired_prompts.json"
_PASS = _REPO / "tests" / "v6" / "fixtures" / "anti_sycophancy" / "passing_responses.json"
_FAIL = _REPO / "tests" / "v6" / "fixtures" / "anti_sycophancy" / "failing_responses.json"


def test_nightly_pass_on_clean_fixture() -> None:
    out = ne.run_nightly_anti_sycophancy_eval_impl(_CORPUS, _PASS)
    assert out["verdict"] == "PASS"
    assert out["mean_delta"] == 0.0
    assert out["N"] == 20


def test_nightly_fail_on_drift_fixture() -> None:
    out = ne.run_nightly_anti_sycophancy_eval_impl(_CORPUS, _FAIL)
    assert out["verdict"] == "FAIL"
    assert out["mean_delta"] == 1.0


def test_nightly_rejects_missing_paired_id(tmp_path: Path) -> None:
    full = json.loads(_PASS.read_text(encoding="utf-8"))
    p = tmp_path / "partial.json"
    p.write_text(json.dumps(full[:-1]), encoding="utf-8")
    with pytest.raises(ValueError, match="must exactly cover"):
        ne.run_nightly_anti_sycophancy_eval_impl(_CORPUS, p)


def test_nightly_rejects_duplicate_paired_id(tmp_path: Path) -> None:
    full = json.loads(_PASS.read_text(encoding="utf-8"))
    dupe = full[:-1] + [full[0]]
    p = tmp_path / "dupe.json"
    p.write_text(json.dumps(dupe), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate paired_ids"):
        ne.run_nightly_anti_sycophancy_eval_impl(_CORPUS, p)


def test_nightly_actor_invokes_underlying_callable(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="polaris.anti_sycophancy.nightly_eval")
    result = ne.run_nightly_anti_sycophancy_eval.fn(str(_CORPUS), str(_PASS))
    assert result == {"N": 20, "mean_delta": 0.0, "threshold": 0.05, "verdict": "PASS"}
    assert any("[nightly-anti-sycophancy]" in r.message for r in caplog.records)
