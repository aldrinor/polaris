"""B10 (2026-06-14) — token-limit resolver (fixes the qwen-judge HTTP-400).

The resolver clamps max_tokens DOWN so prompt + completion never overruns the
model's context window (the HTTP-400 that held the A1/A2 report). These tests
INJECT model metadata (never touch the network) and assert:

  - a judge-class call whose generous max_tokens would overrun the window is
    clamped BELOW the window (the core fix), with reasoning effort untouched;
  - the generator's full-cap budget on a large-context model PASSES THROUGH;
  - unknown models / disabled resolver / offline (no metadata) PASS THROUGH
    (byte-identical to pre-resolver behavior);
  - a prompt that alone overruns the window FAILS LOUD (clamps to a positive
    floor, never silently emits a sub-zero/huge budget).
"""

from __future__ import annotations

import pytest

from polaris_graph.llm import token_limit_resolver as tlr


@pytest.fixture(autouse=True)
def _clean_env_and_cache(monkeypatch):
    # Default-ON resolver, deterministic margin, NO live fetch (offline test).
    monkeypatch.setenv("PG_TOKEN_LIMIT_RESOLVER", "1")
    monkeypatch.setenv("PG_TOKEN_LIMIT_SAFETY_MARGIN", "1000")
    monkeypatch.setenv("PG_TOKEN_LIMIT_ALLOW_FETCH", "0")
    tlr.reset_cache()
    yield
    tlr.reset_cache()


def _inject(monkeypatch, table):
    """Inject a fake /api/v1/models data list (the monkeypatch boundary)."""
    monkeypatch.setattr(tlr, "_fetch_models_table", lambda: table)
    # allow_fetch=0 short-circuits the real fetch, so also let the injected one
    # be used by flipping it on (the injected fn ignores network anyway).
    monkeypatch.setenv("PG_TOKEN_LIMIT_ALLOW_FETCH", "1")
    tlr.reset_cache()


def test_judge_overrun_is_clamped_below_window(monkeypatch):
    """qwen judge: context 8000, completion cap 4000. A generous 16384 request
    with a ~1000-token prompt must clamp to the completion cap (4000), well below
    the window — the qwen-400 fix."""
    _inject(monkeypatch, [{
        "id": "qwen/qwen3.6-35b-a3b",
        "context_length": 8000,
        "top_provider": {"max_completion_tokens": 4000},
    }])
    prompt_tokens = 1000
    allowed = tlr.compute_allowed_max_tokens("qwen/qwen3.6-35b-a3b", prompt_tokens, 16384)
    assert allowed == 4000  # min(cap=4000, ctx 8000-1000-1000=6000, req=16384)
    assert prompt_tokens + allowed < 8000  # never overruns the window


def test_context_window_binds_when_no_completion_cap(monkeypatch):
    """No completion cap reported -> the context window (minus prompt+margin) binds."""
    _inject(monkeypatch, [{
        "id": "some/model",
        "context_length": 10000,
        "top_provider": {},
    }])
    allowed = tlr.compute_allowed_max_tokens("some/model", 3000, 16384)
    # ceiling = 10000 - 3000 - 1000(margin) = 6000
    assert allowed == 6000


def test_generator_full_cap_passes_through(monkeypatch):
    """A large-context generator request fits -> no clamp (the #1253 budget is
    preserved byte-for-byte)."""
    _inject(monkeypatch, [{
        "id": "deepseek/deepseek-v4-pro",
        "context_length": 1048576,
        "top_provider": {"max_completion_tokens": 1048576},
    }])
    requested = 384000
    allowed = tlr.compute_allowed_max_tokens("deepseek/deepseek-v4-pro", 5000, requested)
    assert allowed == requested  # fits comfortably -> unchanged


def test_generator_absent_from_static_passes_through_offline(monkeypatch):
    """Codex B10 iter-1 P1-2: OFFLINE (no live table), the generator is DELIBERATELY
    absent from the static fallback, so its 384000 budget PASSES THROUGH unchanged —
    a conservative static context must never clamp the #1253 full-cap budget."""
    monkeypatch.setenv("PG_TOKEN_LIMIT_ALLOW_FETCH", "0")
    tlr.reset_cache()
    assert tlr.resolve_model_limits("deepseek/deepseek-v4-pro") is None
    allowed = tlr.compute_allowed_max_tokens("deepseek/deepseek-v4-pro", 5000, 384000)
    assert allowed == 384000  # unknown offline -> pass-through, NOT clamped


def test_generator_online_deepinfra_cap_does_not_clamp(monkeypatch):
    """Advisor B10 ONLINE-PATH regression: with a realistic /models entry that
    reports DeepInfra's top_provider cap (16384), the provider-pinned generator
    must NOT clamp a 64000 section request (apply_completion_cap=False) — only the
    context_length bound applies. Re-clamping to 16384 would re-introduce the #1253
    starvation on the DEFAULT (fetch-on) path."""
    _inject(monkeypatch, [{
        "id": "deepseek/deepseek-v4-pro",
        "context_length": 163840,
        "top_provider": {"max_completion_tokens": 16384},
    }])
    # apply_completion_cap=False -> ignore the 16384 top_provider cap.
    allowed = tlr.compute_allowed_max_tokens(
        "deepseek/deepseek-v4-pro", 30000, 64000, apply_completion_cap=False
    )
    # ceiling = context 163840 - 30000 - 1000(margin) = 132840 >= 64000 -> no clamp
    assert allowed == 64000
    # And the default (apply_completion_cap=True) WOULD clamp — proving the flag is
    # the load-bearing difference, not an accident of the numbers.
    clamped = tlr.compute_allowed_max_tokens(
        "deepseek/deepseek-v4-pro", 30000, 64000, apply_completion_cap=True
    )
    assert clamped == 16384


def test_judge_completion_cap_still_binds_default(monkeypatch):
    """The judge/verifier roles are NOT reasoning-first, so the caller leaves
    apply_completion_cap=True (default) — the completion cap remains the actual
    HTTP-400 fix and is NOT weakened by the generator exemption."""
    _inject(monkeypatch, [{
        "id": "qwen/qwen3.6-35b-a3b",
        "context_length": 32000,
        "top_provider": {"max_completion_tokens": 8000},
    }])
    allowed = tlr.compute_allowed_max_tokens("qwen/qwen3.6-35b-a3b", 2000, 16384)
    assert allowed == 8000  # completion cap binds -> the qwen-400 fix stays intact


def test_unknown_model_passes_through(monkeypatch):
    """No metadata for the model (and static map miss) -> pass through unchanged."""
    _inject(monkeypatch, [{"id": "other/model", "context_length": 4000}])
    allowed = tlr.compute_allowed_max_tokens("totally/unknown-model", 1000, 16384)
    assert allowed == 16384


def test_disabled_resolver_passes_through(monkeypatch):
    """Kill-switch OFF -> byte-identical pass-through even with metadata present."""
    _inject(monkeypatch, [{
        "id": "qwen/qwen3.6-35b-a3b",
        "context_length": 8000,
        "top_provider": {"max_completion_tokens": 4000},
    }])
    monkeypatch.setenv("PG_TOKEN_LIMIT_RESOLVER", "0")
    allowed = tlr.compute_allowed_max_tokens("qwen/qwen3.6-35b-a3b", 1000, 16384)
    assert allowed == 16384


def test_offline_uses_static_fallback_for_locked_role(monkeypatch):
    """Offline (no live table) -> the static fallback bounds a locked-role request.
    qwen static = (131072 ctx, 65536 cap); a 200000 request clamps to 65536."""
    monkeypatch.setenv("PG_TOKEN_LIMIT_ALLOW_FETCH", "0")
    tlr.reset_cache()
    allowed = tlr.compute_allowed_max_tokens("qwen/qwen3.6-35b-a3b", 1000, 200000)
    assert allowed == 65536  # min(cap 65536, ctx 131072-1000-1000, req 200000)


def test_prompt_alone_overruns_raises_fail_loud(monkeypatch, caplog):
    """Codex B10 iter-1 P1-3: a prompt larger than the window RAISES a deterministic
    PromptTooLargeError (a tiny max_tokens could not make it well-formed). LOUD,
    never a silent starve or a doomed request."""
    _inject(monkeypatch, [{
        "id": "tiny/model",
        "context_length": 2000,
        "top_provider": {},
    }])
    import logging
    caplog.set_level(logging.ERROR, logger="polaris.llm.token_limit_resolver")
    with pytest.raises(tlr.PromptTooLargeError):
        tlr.compute_allowed_max_tokens("tiny/model", 5000, 16384)
    assert any("FAIL-LOUD" in r.message for r in caplog.records)


def test_estimate_prompt_tokens_is_char_over_four(monkeypatch):
    msgs = [{"role": "user", "content": "x" * 400}]
    est = tlr.estimate_prompt_tokens(msgs)
    # ~ (400 + 8)/4 + 1 = 103; cheap, monotonic, no heavy tokenizer
    assert 100 <= est <= 110
