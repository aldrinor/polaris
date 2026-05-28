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
    monkeypatch.setenv("PG_PATHB_GATE_SALT", "pathB-test-salt-VERY-secret")
    # Codex PR-2 diff iter-1 P1 #1: PG_GENERATOR_MODEL is the documented honest_sweep
    # override; the pin must read it first (not OPENROUTER_DEFAULT_MODEL).
    monkeypatch.setenv("PG_GENERATOR_MODEL", "deepseek/deepseek-v4-pro")
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


# --- Codex PR-2 iter-1 P1 #1: PG_GENERATOR_MODEL is the documented honest_sweep override;
# the pin MUST read it (not OPENROUTER_DEFAULT_MODEL alone). Regression test.
def test_pin_reads_pg_generator_model_first(monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_DEFAULT_MODEL", "wrong/wrong-slug")
    monkeypatch.setenv("PG_GENERATOR_MODEL", "deepseek/deepseek-v4-pro")
    monkeypatch.setenv("PG_EVALUATOR_MODEL", "google/gemma-4-31b-it")
    monkeypatch.setenv("OPENROUTER_PROVIDER_ORDER", "deepinfra")
    from src.polaris_graph.benchmark.pathB_runner import _role_pins
    pins = {p.role: p for p in _role_pins()}
    assert pins["generator"].model_slug == "deepseek/deepseek-v4-pro"  # NOT "wrong/wrong-slug"


# --- Codex PR-2 iter-1 P1 #2: system_fingerprint must NOT be a required surrogate field;
# a valid response without it must pass the gate. Regression test.
def test_gate_passes_without_system_fingerprint(tmp_path: Path, monkeypatch) -> None:
    _full_power_env(monkeypatch)
    _patch_preflight_offline(monkeypatch)
    pc.clear_pathB_capture()
    with gate_around_question(enabled=True, run_dir=tmp_path):
        # responses deliberately OMIT system_fingerprint — must still pass
        pc.capture_llm_call(
            role="generator",
            messages=[{"role": "user", "content": "q"}],
            raw_response={"provider": "deepinfra", "model": "deepseek/deepseek-v4-pro"},
        )
        pc.capture_llm_call(
            role="evaluator",
            messages=[{"role": "user", "content": "j"}],
            raw_response={"provider": "deepinfra", "model": "google/gemma-4-31b-it"},
        )
        pc.record_retrieval_attempt("serper")
        pc.record_retrieval_attempt("semantic_scholar")
    result = json.loads((tmp_path / "pathB_gate_result.json").read_text(encoding="utf-8"))
    assert result["verdict"] == "PASS"


# --- Codex PR-2 iter-1 P2: PG_PATHB_GATE_SALT must be redacted in the pin (HMAC key).
def test_salt_is_redacted_in_pin(tmp_path: Path, monkeypatch) -> None:
    _full_power_env(monkeypatch)
    _patch_preflight_offline(monkeypatch)
    pc.clear_pathB_capture()
    try:
        with gate_around_question(enabled=True, run_dir=tmp_path):
            pc.capture_llm_call(
                role="generator", messages=[{"role": "user", "content": "q"}],
                raw_response={"provider": "deepinfra", "model": "deepseek/deepseek-v4-pro"},
            )
            pc.capture_llm_call(
                role="evaluator", messages=[{"role": "user", "content": "j"}],
                raw_response={"provider": "deepinfra", "model": "google/gemma-4-31b-it"},
            )
            pc.record_retrieval_attempt("serper")
            pc.record_retrieval_attempt("semantic_scholar")
    except Exception:
        pass
    pin_text = (tmp_path / "pathB_gate_pin.json").read_text(encoding="utf-8")
    assert "pathB-test-salt-VERY-secret" not in pin_text  # plaintext absent
    # but the salt env var IS recorded as a secret presence/length entry
    assert "PG_PATHB_GATE_SALT" in pin_text


# --- Codex PR-2 iter-1 P3: preflight FAIL writes a per-run FAIL result + INVALID sentinel.
def test_preflight_fail_writes_result_and_sentinel(tmp_path: Path, monkeypatch) -> None:
    _full_power_env(monkeypatch)
    # break full-power: remove OPENROUTER_ALLOW_FALLBACKS=false invariant
    monkeypatch.setenv("OPENROUTER_ALLOW_FALLBACKS", "true")
    _patch_preflight_offline(monkeypatch)
    pc.clear_pathB_capture()
    with pytest.raises(GateError):
        with gate_around_question(enabled=True, run_dir=tmp_path):
            pass  # never reached
    result = json.loads((tmp_path / "pathB_gate_result.json").read_text(encoding="utf-8"))
    assert result["verdict"] == "FAIL"
    assert result["stage"] == "preflight"
    assert (tmp_path / "pathB_gate_INVALID").exists()


# --- gate FAIL on post-run assert writes INVALID sentinel too (P2 #2: downstream skip) ---
def test_post_run_fail_writes_invalid_sentinel(tmp_path: Path, monkeypatch) -> None:
    _full_power_env(monkeypatch)
    _patch_preflight_offline(monkeypatch)
    pc.clear_pathB_capture()
    with pytest.raises(GateError):
        with gate_around_question(enabled=True, run_dir=tmp_path):
            pc.capture_llm_call(
                role="generator", messages=[{"role": "user", "content": "q"}],
                raw_response={"provider": "deepinfra", "model": "deepseek/deepseek-v4-pro"},
            )
            pc.capture_llm_call(
                role="evaluator", messages=[{"role": "user", "content": "j"}],
                raw_response={"provider": "deepinfra", "model": "google/gemma-4-31b-it"},
            )
            pc.record_retrieval_attempt("serper")
            # semantic_scholar deliberately omitted
    assert (tmp_path / "pathB_gate_INVALID").exists()


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
