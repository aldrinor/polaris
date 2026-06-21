"""Path-B gate lifecycle tests (I-safety-002b / #925 PR-2). Offline, no real LLM."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.polaris_graph.benchmark import pathB_capture as pc
from src.polaris_graph.benchmark.pathB_runner import gate_around_question
from scripts.dr_benchmark.pathB_run_gate import GateError


# I-meta-002 sub-PR-5: the 4 locked architecture role slugs (config/architecture/
# polaris_runtime_lock.yaml). _role_pins() now returns generator/mirror/sentinel/judge, and
# the post-run gate enforces completeness in BOTH directions (every pinned role observed AND
# every observed role pinned), so the captured calls must be exactly these four roles.
# I-beatboth-008 (#1285) all-GLM-5.2: generator AND mirror are both z-ai/glm-5.2 (two-family
# relaxation via the lock's family_policy.allowed_collisions [[generator, mirror]]); Sentinel
# CERTIFIED minimax/minimax-m2 (decomposition) + Judge qwen stay independent D8 arbiters.
_GEN_SLUG = "z-ai/glm-5.2"
_MIRROR_SLUG = "z-ai/glm-5.2"
_SENTINEL_SLUG = "minimax/minimax-m2"
_JUDGE_SLUG = "qwen/qwen3.6-35b-a3b"

_FOUR_ROLE_SLUGS = {
    "generator": _GEN_SLUG,
    "mirror": _MIRROR_SLUG,
    "sentinel": _SENTINEL_SLUG,
    "judge": _JUDGE_SLUG,
}

# I-meta-002 PR-9/M4: the 3 self-hosted vLLM verifier roles (serving_route: vast_self_host*)
# require a configured PG_<ROLE>_BASE_URL at preflight and serve from THAT box. The post-run
# gate compares the served endpoint to the pinned base_url, so the captured-metadata endpoint
# below MUST equal the env value set in _full_power_env (single source of truth, no network).
_SELF_HOST_BASE_URLS = {
    "mirror": "http://10.0.0.5:8000",
    "sentinel": "http://10.0.0.6:8000",
    "judge": "http://10.0.0.7:8000",
}


def _full_power_env(monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_ALLOW_FALLBACKS", "false")
    monkeypatch.setenv("OPENROUTER_PROVIDER_ORDER", "deepinfra")
    monkeypatch.setenv("SERPER_API_KEY", "x")
    monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", "y")
    monkeypatch.setenv("PG_PATHB_GATE_SALT", "pathB-test-salt-VERY-secret")
    # Codex PR-2 diff iter-1 P1 #1: PG_GENERATOR_MODEL is the documented honest_sweep
    # override; the pin must read it first (not OPENROUTER_DEFAULT_MODEL).
    monkeypatch.setenv("PG_GENERATOR_MODEL", _GEN_SLUG)
    # The preflight eff_entail==eff_eval invariant (pathB_run_gate) reads PG_EVALUATOR_MODEL;
    # keep it equal to the default entailment model (gemma) so that gate stays satisfied. It
    # is NOT a role pin anymore (the 4-role set is generator/mirror/sentinel/judge).
    monkeypatch.setenv("PG_EVALUATOR_MODEL", "google/gemma-4-31b-it")
    # I-meta-002 PR-9/M4: each self-host verifier role's endpoint must be configured at
    # preflight (LAW VI fail-closed). Env-only — NO network in these offline tests.
    for role, base_url in _SELF_HOST_BASE_URLS.items():
        monkeypatch.setenv(f"PG_{role.upper()}_BASE_URL", base_url)


def _capture_four_roles(pc) -> None:
    """Capture one served completion per locked role (generator/mirror/sentinel/judge).

    The post-run gate requires every PINNED role to appear in captured calls; the 4-role pin
    set therefore needs a capture for each.

    Role-specific served shape (I-meta-002 PR-9/M4):
    - generator (serving_route: openrouter) keeps the OpenRouter raw shape (provider +
      served model); it still goes through the OpenRouter provider+model post-run checks. The
      provider is the offline-pinned 'deepinfra' (the only entry in OPENROUTER_PROVIDER_ORDER).
    - mirror/sentinel/judge (serving_route: vast_self_host*) carry the M1 self-host raw shape
      raw['_pathb_served'] = {'endpoint': base_url, 'model': served_model} — exactly what
      openai_compatible_transport stashes — which build_response_metadata flattens onto the
      captured metadata as top-level model+endpoint keys for the served==pinned check. The
      endpoint matches the PG_<ROLE>_BASE_URL set in _full_power_env (same source of truth).
    """
    for role, slug in _FOUR_ROLE_SLUGS.items():
        if role in _SELF_HOST_BASE_URLS:
            raw_response = {
                "_pathb_served": {"endpoint": _SELF_HOST_BASE_URLS[role], "model": slug}
            }
        else:
            raw_response = {"provider": "deepinfra", "model": slug}
        pc.capture_llm_call(
            role=role,
            messages=[{"role": "user", "content": role}],
            raw_response=raw_response,
        )


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
        _capture_four_roles(pc)
        pc.record_retrieval_attempt("serper")
        pc.record_retrieval_attempt("semantic_scholar")
    pin = json.loads((tmp_path / "pathB_gate_pin.json").read_text(encoding="utf-8"))
    result = json.loads((tmp_path / "pathB_gate_result.json").read_text(encoding="utf-8"))
    assert "effective_config_hash" in pin
    assert result["verdict"] == "PASS"
    assert set(result["served_identity_by_role"]) == {
        "generator", "mirror", "sentinel", "judge",
    }
    # The pin now records the 4 locked roles, lock-sourced (config/architecture lock).
    pinned_roles = {rp["role"] for rp in pin["role_pins"]}
    assert pinned_roles == {"generator", "mirror", "sentinel", "judge"}


# --- gate enabled, but a required backend was never attempted -> GateError + result FAIL ---
def test_enabled_fails_when_backend_not_attempted(tmp_path: Path, monkeypatch) -> None:
    _full_power_env(monkeypatch)
    _patch_preflight_offline(monkeypatch)
    pc.clear_pathB_capture()
    with pytest.raises(GateError, match="never attempted"):
        with gate_around_question(enabled=True, run_dir=tmp_path):
            _capture_four_roles(pc)
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


# --- I-meta-002 sub-PR-5: _role_pins() returns the FOUR locked roles, lock-sourced slugs ---
def test_role_pins_returns_four_locked_roles(monkeypatch) -> None:
    # No PG_*_MODEL overrides set: defaults are sourced from the architecture lock.
    monkeypatch.delenv("PG_GENERATOR_MODEL", raising=False)
    monkeypatch.delenv("OPENROUTER_DEFAULT_MODEL", raising=False)
    monkeypatch.delenv("PG_MIRROR_MODEL", raising=False)
    monkeypatch.delenv("PG_SENTINEL_MODEL", raising=False)
    monkeypatch.delenv("PG_JUDGE_MODEL", raising=False)
    from src.polaris_graph.benchmark.pathB_runner import _role_pins
    pins = {p.role: p.model_slug for p in _role_pins()}
    assert pins == _FOUR_ROLE_SLUGS  # lock-sourced generator/mirror/sentinel/judge


# --- per-role PG_*_MODEL env override is applied ON TOP of the lock default ---
def test_role_pins_env_overrides_applied(monkeypatch) -> None:
    monkeypatch.delenv("PG_GENERATOR_MODEL", raising=False)
    monkeypatch.delenv("OPENROUTER_DEFAULT_MODEL", raising=False)
    # Override mirror to another distinct-family slug (mistral) so all_distinct still holds.
    monkeypatch.setenv("PG_MIRROR_MODEL", "mistralai/mistral-large")
    from src.polaris_graph.benchmark.pathB_runner import _role_pins
    pins = {p.role: p.model_slug for p in _role_pins()}
    assert pins["mirror"] == "mistralai/mistral-large"
    assert pins["generator"] == _GEN_SLUG  # untouched, lock-sourced


# --- a NON-ALLOWED same-family 4-role map fails LOUD at pin-build via validate_role_families ---
def test_role_pins_rejects_family_collision(monkeypatch) -> None:
    # I-beatboth-008 (#1285): under the all-GLM-5.2 lock the generator defaults to z-ai/glm-5.2
    # (family 'glm'), and (generator, mirror) is the ONLY operator-approved allowed_collision.
    # Force the judge into the 'glm' family -> collides with the generator on a pair that is NOT
    # in allowed_collisions, so _role_pins must still raise LOUD. (The prior judge->deepseek
    # collision premise was stale: the generator is no longer deepseek post all-GLM-5.2 switch.)
    monkeypatch.delenv("PG_GENERATOR_MODEL", raising=False)
    monkeypatch.delenv("OPENROUTER_DEFAULT_MODEL", raising=False)
    monkeypatch.setenv("PG_JUDGE_MODEL", "z-ai/glm-5.1")  # family 'glm' -> non-allowed collision
    from src.polaris_graph.benchmark.pathB_runner import _role_pins
    with pytest.raises(RuntimeError, match="family"):
        _role_pins()


# --- Codex PR-2 iter-1 P1 #2: system_fingerprint must NOT be a required surrogate field;
# a valid response without it must pass the gate. Regression test.
def test_gate_passes_without_system_fingerprint(tmp_path: Path, monkeypatch) -> None:
    _full_power_env(monkeypatch)
    _patch_preflight_offline(monkeypatch)
    pc.clear_pathB_capture()
    with gate_around_question(enabled=True, run_dir=tmp_path):
        # responses deliberately OMIT system_fingerprint — must still pass
        _capture_four_roles(pc)
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
            _capture_four_roles(pc)
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
            _capture_four_roles(pc)
            pc.record_retrieval_attempt("serper")
            # semantic_scholar deliberately omitted -> post-run gate FAIL
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
