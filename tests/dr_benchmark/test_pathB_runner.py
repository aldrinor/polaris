"""Path-B gate lifecycle tests (I-safety-002b / #925 PR-2). Offline, no real LLM."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.polaris_graph.benchmark import pathB_capture as pc
from src.polaris_graph.benchmark.pathB_runner import gate_around_question
from scripts.dr_benchmark.pathB_run_gate import GateError


def _full_power_env(monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_ALLOW_FALLBACKS", "false")
    monkeypatch.setenv("OPENROUTER_PROVIDER_ORDER", "deepinfra")
    monkeypatch.setenv("SERPER_API_KEY", "x")
    monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", "y")
    monkeypatch.setenv("PG_PATHB_GATE_SALT", "pathB-test-salt")
    monkeypatch.setenv("OPENROUTER_DEFAULT_MODEL", "deepseek/deepseek-v4-pro")
    monkeypatch.setenv("PG_EVALUATOR_MODEL", "google/gemma-4-31b-it")


def _patch_preflight_offline(monkeypatch):
    """Force preflight(offline=True) so the lifecycle helper does not hit the network in tests."""
    from src.polaris_graph.benchmark import pathB_runner
    real_preflight = pathB_runner.preflight

    def _offline_preflight(**kw):
        kw["offline"] = True
        return real_preflight(**kw)

    monkeypatch.setattr(pathB_runner, "preflight", _offline_preflight)


# --- gate disabled: no-op (no pin file, no capture, no exception) ---
def test_disabled_is_noop(tmp_path: Path, monkeypatch) -> None:
    _full_power_env(monkeypatch)
    pc.clear_pathB_capture()
    with gate_around_question(enabled=False, run_dir=tmp_path):
        assert pc.is_active() is False
    assert pc.is_active() is False
    assert not (tmp_path / "pathB_gate_pin.json").exists()
    assert not (tmp_path / "pathB_gate_result.json").exists()


# --- gate enabled: tagged report calls captured + retrieval attempts noted + PASS ---
def test_enabled_pass_writes_pin_and_result(tmp_path: Path, monkeypatch) -> None:
    _full_power_env(monkeypatch)
    _patch_preflight_offline(monkeypatch)
    pc.clear_pathB_capture()
    with gate_around_question(enabled=True, run_dir=tmp_path):
        tok = pc.set_role("generator")
        try:
            pc.capture_llm_call(
                role="generator",
                messages=[{"role": "user", "content": "q"}],
                raw_response={
                    "provider": "deepinfra",
                    "model": "deepseek/deepseek-v4-pro",
                    "system_fingerprint": "fp_g",
                },
            )
        finally:
            pc.reset_role(tok)
        pc.capture_llm_call(
            role="evaluator",
            messages=[{"role": "user", "content": "j"}],
            raw_response={
                "provider": "deepinfra",
                "model": "google/gemma-4-31b-it",
                "system_fingerprint": "fp_e",
            },
        )
        pc.record_retrieval_attempt("serper")
        pc.record_retrieval_attempt("semantic_scholar")
    pin = json.loads((tmp_path / "pathB_gate_pin.json").read_text(encoding="utf-8"))
    result = json.loads((tmp_path / "pathB_gate_result.json").read_text(encoding="utf-8"))
    assert "effective_config_hash" in pin
    assert result["verdict"] == "PASS"
    assert set(result["served_identity_by_role"]) == {"generator", "evaluator"}


# --- gate enabled, but a required backend was never attempted -> GateError + result FAIL ---
def test_enabled_fails_when_backend_not_attempted(tmp_path: Path, monkeypatch) -> None:
    _full_power_env(monkeypatch)
    _patch_preflight_offline(monkeypatch)
    pc.clear_pathB_capture()
    with pytest.raises(GateError, match="never attempted"):
        with gate_around_question(enabled=True, run_dir=tmp_path):
            pc.capture_llm_call(
                role="generator",
                messages=[{"role": "user", "content": "q"}],
                raw_response={
                    "provider": "deepinfra",
                    "model": "deepseek/deepseek-v4-pro",
                    "system_fingerprint": "fp_g",
                },
            )
            pc.capture_llm_call(
                role="evaluator",
                messages=[{"role": "user", "content": "j"}],
                raw_response={
                    "provider": "deepinfra",
                    "model": "google/gemma-4-31b-it",
                    "system_fingerprint": "fp_e",
                },
            )
            pc.record_retrieval_attempt("serper")
            # semantic_scholar deliberately NOT attempted -> gate must FAIL
    result = json.loads((tmp_path / "pathB_gate_result.json").read_text(encoding="utf-8"))
    assert result["verdict"] == "FAIL"
    assert "never attempted" in result["reason"]


# --- exception inside body propagates, no post-run assert (would mask the cause) ---
def test_body_exception_propagates_without_assert(tmp_path: Path, monkeypatch) -> None:
    _full_power_env(monkeypatch)
    _patch_preflight_offline(monkeypatch)
    pc.clear_pathB_capture()
    with pytest.raises(RuntimeError, match="boom"):
        with gate_around_question(enabled=True, run_dir=tmp_path):
            raise RuntimeError("boom")
    assert pc.is_active() is False  # capture cleared on exception
    # pin was written (preflight succeeded) but result was NOT (post-run didn't run)
    assert (tmp_path / "pathB_gate_pin.json").exists()
    assert not (tmp_path / "pathB_gate_result.json").exists()
