"""Fixtures for the Path-B run capture primitives (I-safety-002b / #925). Pure, no live system.

Proves the two seams Codex flagged: (1) the evaluator-family judge call is captured even though
it bypasses OpenRouterClient (role='evaluator' lands in the sink); (2) served-identity provenance
prefers the genuinely-SSE-served fields over the request-derived streaming `data['model']`.
Plus an end-to-end through the REAL gate (capture dicts -> LLMCall -> assert_post_run).
"""

from __future__ import annotations

import pytest

from src.polaris_graph.benchmark import benchmark_run_capture as pc
from scripts.dr_benchmark.pathB_run_gate import (
    GateError,
    LLMCall,
    RolePin,
    assert_post_run,
    preflight,
)

_SALT = b"pathB-capture-test-salt"
_GEN = "deepseek/deepseek-v4-pro"
_EVAL = "google/gemma-4-31b-it"


@pytest.fixture(autouse=True)
def _clean_capture():
    pc.clear_pathB_capture()
    yield
    pc.clear_pathB_capture()


# --- activation lifecycle ---
def test_inactive_by_default() -> None:
    assert pc.is_active() is False
    # capture + retrieval are no-ops when inactive (never raise)
    pc.capture_llm_call(role="generator", messages=[{"role": "user", "content": "x"}], raw_response={})
    pc.record_retrieval_attempt("serper")
    assert pc.collected_calls() == []
    assert pc.attempted_backends() == set()


def test_register_then_clear() -> None:
    pc.register_pathB_capture()
    assert pc.is_active() is True
    pc.clear_pathB_capture()
    assert pc.is_active() is False


# --- PR-2 hook semantics: only EXPLICITLY-tagged calls are captured (Codex Option B) ---
def test_set_role_reset_role_roundtrip() -> None:
    assert pc.current_llm_role() is None
    tok = pc.set_role("generator")
    assert pc.current_llm_role() == "generator"
    pc.reset_role(tok)
    assert pc.current_llm_role() is None


# --- role context manager: scoped, restores (no leak to later calls) ---
def test_llm_role_scoped_restore() -> None:
    assert pc.current_llm_role() is None
    with pc.llm_role("generator"):
        assert pc.current_llm_role() == "generator"
        with pc.llm_role("evaluator"):
            assert pc.current_llm_role() == "evaluator"
        assert pc.current_llm_role() == "generator"
    assert pc.current_llm_role() is None


# --- retrieval-attempt set ---
def test_retrieval_attempts() -> None:
    pc.register_pathB_capture()
    pc.record_retrieval_attempt("serper")
    pc.record_retrieval_attempt("serper")
    pc.record_retrieval_attempt("semantic_scholar")
    assert pc.attempted_backends() == {"serper", "semantic_scholar"}


# --- request_hash stable + discriminating ---
def test_request_hash_stable_and_discriminating() -> None:
    a = [{"role": "user", "content": "hello"}]
    b = [{"role": "user", "content": "world"}]
    assert pc.request_hash(a) == pc.request_hash(list(a))
    assert pc.request_hash(a) != pc.request_hash(b)
    # non-serializable input must not raise
    pc.request_hash(object())


# --- build_response_metadata: non-stream carries all 3; missing dropped ---
def test_metadata_nonstream_all_fields() -> None:
    meta = pc.build_response_metadata(
        {"provider": "deepinfra", "model": _GEN, "system_fingerprint": "fp_x", "usage": {"x": 1}}
    )
    assert meta == {"provider_name": "deepinfra", "model": _GEN, "system_fingerprint": "fp_x"}


def test_metadata_drops_missing_fields() -> None:
    # provider present, system_fingerprint absent -> dropped (provider+model surrogate)
    meta = pc.build_response_metadata({"provider": "deepinfra", "model": _EVAL})
    assert meta == {"provider_name": "deepinfra", "model": _EVAL}
    # nothing served -> empty (gate will fail loud on this, by design)
    assert pc.build_response_metadata({}) == {}
    assert pc.build_response_metadata(None) == {}


def test_metadata_surfaces_endpoint_when_pathb_served_present() -> None:
    # I-meta-002 PR-7/M1: a self-host vLLM verifier carries NO provider; its served identity
    # for the M4 served==pinned check is the ENDPOINT, stashed under _pathb_served.endpoint.
    self_host = {
        "model": _EVAL,
        "choices": [{"message": {"content": "..."}}],
        "_pathb_served": {"endpoint": "http://sentinel.internal:8002", "model": _EVAL},
    }
    meta = pc.build_response_metadata(self_host)
    assert meta == {"model": _EVAL, "endpoint": "http://sentinel.internal:8002"}
    # No fabricated provider_name for vLLM.
    assert "provider_name" not in meta


def test_metadata_drops_endpoint_when_absent() -> None:
    # Backward compatibility: an OpenRouter response (no endpoint) keeps its 3-key shape; the
    # additive endpoint key is DROPPED, not present-as-None.
    meta = pc.build_response_metadata(
        {"provider": "deepinfra", "model": _GEN, "system_fingerprint": "fp_x"}
    )
    assert "endpoint" not in meta
    assert meta == {"provider_name": "deepinfra", "model": _GEN, "system_fingerprint": "fp_x"}
    # And a streaming served block with no endpoint also drops it.
    streaming = {
        "model": _GEN,
        "_pathb_served": {"provider": "deepinfra", "model": _GEN, "system_fingerprint": "fp_sse"},
    }
    assert "endpoint" not in pc.build_response_metadata(streaming)


def test_metadata_streaming_prefers_served_over_request_model() -> None:
    # streaming `data` has the REQUEST-derived model fallback at top level, and the
    # genuinely-SSE-served identity under _pathb_served. The served one must win.
    streaming_data = {
        "model": _GEN,  # request-derived fallback (self.model) — must NOT be trusted
        "choices": [{"message": {"content": "..."}}],
        "_pathb_served": {"provider": "deepinfra", "model": _GEN, "system_fingerprint": "fp_sse"},
    }
    meta = pc.build_response_metadata(streaming_data)
    assert meta == {"provider_name": "deepinfra", "model": _GEN, "system_fingerprint": "fp_sse"}
    # and if the SSE served a DIFFERENT (fallback/substituted) model, provenance exposes it
    drifted = dict(streaming_data, _pathb_served={"provider": "FALLBACK", "model": "other/model"})
    meta2 = pc.build_response_metadata(drifted)
    assert meta2 == {"provider_name": "FALLBACK", "model": "other/model"}


# --- capture_llm_call lands with correct shape + role ---
def test_capture_records_call_with_role() -> None:
    pc.register_pathB_capture()
    with pc.llm_role("generator"):
        pc.capture_llm_call(
            role=pc.current_llm_role() or "generator",
            messages=[{"role": "user", "content": "q"}],
            raw_response={"provider": "deepinfra", "model": _GEN, "system_fingerprint": "fp"},
        )
    calls = pc.collected_calls()
    assert len(calls) == 1
    c = calls[0]
    assert c["role"] == "generator"
    assert c["prompt_messages_present"] is True
    assert c["request_hash"]
    assert c["response_metadata"] == {"provider_name": "deepinfra", "model": _GEN, "system_fingerprint": "fp"}


def test_capture_evaluator_judge_path_lands() -> None:
    # The entailment judge bypasses OpenRouterClient (direct httpx). Its capture is
    # role='evaluator' with the judge's own response JSON. Prove it lands in the sink.
    pc.register_pathB_capture()
    pc.capture_llm_call(
        role="evaluator",
        messages=[{"role": "user", "content": "ENTAILMENT prompt"}],
        raw_response={"provider": "deepinfra", "model": _EVAL},
    )
    calls = pc.collected_calls()
    assert [c["role"] for c in calls] == ["evaluator"]
    assert calls[0]["response_metadata"] == {"provider_name": "deepinfra", "model": _EVAL}


# --- end-to-end: capture dicts -> gate LLMCall -> assert_post_run ---
def _full_power_env(monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_ALLOW_FALLBACKS", "false")
    monkeypatch.setenv("OPENROUTER_PROVIDER_ORDER", "deepinfra")
    monkeypatch.setenv("SERPER_API_KEY", "x")
    monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", "y")


def _pins() -> list[RolePin]:
    return [
        RolePin("generator", _GEN, "deepinfra", ("provider_name", "model", "system_fingerprint")),
        RolePin("evaluator", _EVAL, "deepinfra", ("provider_name", "model")),
    ]


def _capture_a_run() -> None:
    pc.register_pathB_capture()
    with pc.llm_role("generator"):
        pc.capture_llm_call(
            role=pc.current_llm_role(),
            messages=[{"role": "user", "content": "generate"}],
            raw_response={"provider": "deepinfra", "model": _GEN, "system_fingerprint": "fp_g"},
        )
    # evaluator judge call (bypasses client; role hardcoded by the judge hook)
    pc.capture_llm_call(
        role="evaluator",
        messages=[{"role": "user", "content": "judge"}],
        raw_response={"provider": "deepinfra", "model": _EVAL},
    )
    pc.record_retrieval_attempt("serper")
    pc.record_retrieval_attempt("semantic_scholar")


def test_end_to_end_capture_feeds_gate_pass(monkeypatch) -> None:
    _full_power_env(monkeypatch)
    pin = preflight(["PG_V30_ENABLED"], _pins(), _SALT, offline=True)
    _capture_a_run()
    calls = [LLMCall(**c) for c in pc.collected_calls()]
    res = assert_post_run(pin, ["PG_V30_ENABLED"], _SALT, calls, pc.attempted_backends())
    assert set(res["served_identity_by_role"]) == {"generator", "evaluator"}


def test_end_to_end_wrong_served_model_fails_gate(monkeypatch) -> None:
    _full_power_env(monkeypatch)
    pin = preflight([], _pins(), _SALT, offline=True)
    pc.register_pathB_capture()
    with pc.llm_role("generator"):
        # served model is NOT the pinned generator slug -> gate must reject
        pc.capture_llm_call(
            role="generator",
            messages=[{"role": "user", "content": "q"}],
            raw_response={"provider": "deepinfra", "model": "deepseek/deepseek-v3.2", "system_fingerprint": "fp"},
        )
    pc.capture_llm_call(
        role="evaluator", messages=[{"role": "user", "content": "j"}],
        raw_response={"provider": "deepinfra", "model": _EVAL},
    )
    calls = [LLMCall(**c) for c in pc.collected_calls()]
    with pytest.raises(GateError, match="served model"):
        assert_post_run(pin, [], _SALT, calls, {"serper", "semantic_scholar"})
