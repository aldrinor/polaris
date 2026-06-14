"""Tests for I-bug-100 — entailment-judge cost recording.

After every successful entailment judge call, the cost is recorded:
1. `_add_run_cost(cost_usd)` increments the per-run accumulator.
2. An entry is appended to `pg_cost_ledger.jsonl` matching the
   OpenRouterClient schema (`session_id` / `call_type` /
   `input_tokens` / `output_tokens` / `reasoning_tokens` /
   `duration_ms` / `cost_usd` / `cumulative_cost_usd`).
3. `check_run_budget(0)` raises `BudgetExceededError` if the call
   pushed cumulative cost past `PG_MAX_COST_PER_RUN`.

`BudgetExceededError` MUST escape the fail-open broad-except handler
so a cap breach aborts the sweep instead of being masked as a
transient judge error.

Test isolation pattern:
- Patch `openrouter_client._COST_LEDGER_PATH` to a tmp file via
  `monkeypatch.setattr` (NOT setenv: the path is bound at import).
- Patch `openrouter_client.PG_MAX_COST_PER_RUN` similarly for the
  cap-breach test.
- Reset `_RUN_COST_CTX` per test via `reset_run_cost()`.
- entailment_judge accesses these via `_orc.<attr>` so monkeypatch
  propagates without module reload.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import pytest

from src.polaris_graph.llm import entailment_judge, openrouter_client


@pytest.fixture(autouse=True)
def _reset_run_cost():
    openrouter_client.reset_run_cost()
    yield
    openrouter_client.reset_run_cost()


@pytest.fixture(autouse=True)
def _reset_judge_singleton():
    # Force a fresh judge per test so the httpx.Client mock applies.
    entailment_judge._JUDGE_SINGLETON = None
    yield
    entailment_judge._JUDGE_SINGLETON = None


def _make_judge_with_mock_response(monkeypatch, response_payload: dict) -> entailment_judge._EntailmentJudge:
    """Build a real `_EntailmentJudge` instance with a mocked httpx.Client.

    The judge's `__init__` sets up family-segregation against
    `PG_GENERATOR_MODEL`; we set both env vars so segregation passes.
    """
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("PG_GENERATOR_MODEL", "deepseek/deepseek-v4-pro")
    monkeypatch.setenv("PG_ENTAILMENT_MODEL", "google/gemma-4-31b-it")

    judge = entailment_judge._EntailmentJudge()

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(return_value=response_payload)
    judge._client = MagicMock()
    judge._client.post = MagicMock(return_value=mock_response)
    return judge


def test_judge_records_api_cost_when_present(monkeypatch, tmp_path):
    """When OpenRouter response includes `usage.cost`, that value is
    recorded verbatim (not imputed) in both the run-cost accumulator
    and the cost ledger.
    """
    ledger_path = tmp_path / "ledger.jsonl"
    monkeypatch.setattr(openrouter_client, "_COST_LEDGER_PATH", ledger_path)
    monkeypatch.setattr(openrouter_client, "PG_MAX_COST_PER_RUN", 1.0)

    payload: dict[str, Any] = {
        "choices": [{"message": {"content": json.dumps({
            "verdict": "ENTAILED", "reason": "supported",
        })}}],
        "usage": {
            "prompt_tokens": 500,
            "completion_tokens": 50,
            "cost": 0.001234,
        },
    }
    judge = _make_judge_with_mock_response(monkeypatch, payload)

    verdict, reason = judge.judge("sentence", "span")
    assert verdict == "ENTAILED"

    # Run-cost accumulator picked up the API-reported cost
    assert openrouter_client.current_run_cost() == pytest.approx(0.001234)

    # Ledger entry has correct schema
    lines = ledger_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["call_type"] == "entailment_judge"
    assert entry["input_tokens"] == 500
    assert entry["output_tokens"] == 50
    assert entry["reasoning_tokens"] == 0
    assert entry["cost_usd"] == pytest.approx(0.001234)
    assert "session_id" in entry
    assert "timestamp" in entry
    assert "duration_ms" in entry


def test_judge_imputes_cost_when_api_cost_absent(monkeypatch, tmp_path):
    """When `usage.cost` is missing, cost is imputed via
    `_impute_cost_from_tokens(model, input, output, 0)` from the
    published price table.
    """
    ledger_path = tmp_path / "ledger.jsonl"
    monkeypatch.setattr(openrouter_client, "_COST_LEDGER_PATH", ledger_path)
    monkeypatch.setattr(openrouter_client, "PG_MAX_COST_PER_RUN", 1.0)

    payload = {
        "choices": [{"message": {"content": json.dumps({
            "verdict": "NEUTRAL", "reason": "specificity inflation",
        })}}],
        "usage": {
            "prompt_tokens": 1_000_000,  # 1M for easy-to-verify rate
            "completion_tokens": 1_000_000,
            # no "cost" key
        },
    }
    judge = _make_judge_with_mock_response(monkeypatch, payload)

    verdict, _ = judge.judge("sentence", "span")
    assert verdict == "NEUTRAL"

    # Per _PRICE_TABLE_USD_PER_M[google/gemma-4-31b-it] = (0.13, 0.38)
    # 1M input @ $0.13/M = $0.13; 1M output @ $0.38/M = $0.38.
    # Total = $0.51.
    expected = (1_000_000 / 1_000_000) * 0.13 + (1_000_000 / 1_000_000) * 0.38
    assert openrouter_client.current_run_cost() == pytest.approx(expected, rel=1e-6)

    entry = json.loads(ledger_path.read_text(encoding="utf-8").strip())
    assert entry["cost_usd"] == pytest.approx(expected, rel=1e-6)


def test_judge_shares_state_with_canonical_src_module(monkeypatch, tmp_path):
    """I-bug-100 Codex iter-1 diff P1 fix: entailment_judge must use the
    SAME module instance as the production sweep (which imports
    `src.polaris_graph.llm.openrouter_client`). Two import spellings —
    `polaris_graph.llm.X` and `src.polaris_graph.llm.X` — load as
    SEPARATE module objects with separate ContextVar state. This test
    asserts the judge's cost-recording uses the canonical `src.*`
    spelling so per-run cost is visible to the sweep.
    """
    # Import via the SRC namespace (matches scripts/run_honest_sweep_r3.py)
    from src.polaris_graph.llm import openrouter_client as src_orc

    ledger_path = tmp_path / "ledger.jsonl"
    monkeypatch.setattr(src_orc, "_COST_LEDGER_PATH", ledger_path)
    monkeypatch.setattr(src_orc, "PG_MAX_COST_PER_RUN", 1.0)
    src_orc.reset_run_cost()

    payload = {
        "choices": [{"message": {"content": json.dumps({
            "verdict": "ENTAILED", "reason": "ok",
        })}}],
        "usage": {
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "cost": 0.000567,
        },
    }
    judge = _make_judge_with_mock_response(monkeypatch, payload)
    judge.judge("sentence", "span")

    # Critical assertion: cost shows up via the SRC namespace
    assert src_orc.current_run_cost() == pytest.approx(0.000567)

    # Ledger entry written via src module attribute (proves shared state)
    entry = json.loads(ledger_path.read_text(encoding="utf-8").strip())
    assert entry["call_type"] == "entailment_judge"
    assert entry["cost_usd"] == pytest.approx(0.000567)


def test_judge_falls_back_to_estimate_when_usage_block_absent(monkeypatch, tmp_path):
    """I-bug-100 Codex iter-1 diff P2 fix: when OpenRouter response has
    no `usage` block at all, both api_cost and the imputed value would
    be 0 (because impute on (0,0,0) returns 0), silently bypassing the
    budget guard. The fallback estimate uses (500, 100) tokens at the
    judge's model rate to keep the cap honest.
    """
    ledger_path = tmp_path / "ledger.jsonl"
    monkeypatch.setattr(openrouter_client, "_COST_LEDGER_PATH", ledger_path)
    monkeypatch.setattr(openrouter_client, "PG_MAX_COST_PER_RUN", 1.0)

    payload = {
        "choices": [{"message": {"content": json.dumps({
            "verdict": "ENTAILED", "reason": "ok",
        })}}],
        # NO usage block at all
    }
    judge = _make_judge_with_mock_response(monkeypatch, payload)
    judge.judge("sentence", "span")

    # Should NOT be 0 — fallback estimate kicks in
    cost = openrouter_client.current_run_cost()
    assert cost > 0, "fallback estimate must produce non-zero cost when usage absent"

    # Per (500, 100) at gemma-4-31b-it rate (0.13, 0.38)
    expected = (500 / 1_000_000) * 0.13 + (100 / 1_000_000) * 0.38
    assert cost == pytest.approx(expected, rel=1e-6)


# ---------- I-sov-001: env-configurable endpoint ----------

def test_judge_endpoint_defaults_to_openrouter(monkeypatch):
    """Default endpoint is OpenRouter when OPENROUTER_BASE_URL is unset."""
    monkeypatch.delenv("OPENROUTER_BASE_URL", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("PG_GENERATOR_MODEL", "deepseek/deepseek-v4-pro")
    monkeypatch.setenv("PG_ENTAILMENT_MODEL", "google/gemma-4-31b-it")
    judge = entailment_judge._EntailmentJudge()
    assert judge._endpoint == "https://openrouter.ai/api/v1/chat/completions"


def test_judge_endpoint_respects_vllm_base_url(monkeypatch):
    """I-sov-001: OPENROUTER_BASE_URL pointed at the OVH H200 vLLM endpoint
    flips the entailment judge to the sovereign backend. Trailing slash
    tolerated (mirrors openrouter_client + real_completion)."""
    monkeypatch.setenv("OPENROUTER_BASE_URL", "http://10.0.0.42:8000/v1/")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("PG_GENERATOR_MODEL", "deepseek/deepseek-v4-pro")
    monkeypatch.setenv("PG_ENTAILMENT_MODEL", "google/gemma-4-31b-it")
    judge = entailment_judge._EntailmentJudge()
    assert judge._endpoint == "http://10.0.0.42:8000/v1/chat/completions"


def test_judge_posts_to_configured_endpoint(monkeypatch):
    """The judge's httpx POST targets self._endpoint, not a hardcoded URL."""
    monkeypatch.setenv("OPENROUTER_BASE_URL", "http://10.0.0.42:8000/v1")
    payload = {
        "choices": [{"message": {"content": json.dumps({
            "verdict": "ENTAILED", "reason": "ok",
        })}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "cost": 0.0001},
    }
    judge = _make_judge_with_mock_response(monkeypatch, payload)
    judge.judge("sentence", "span")
    # First positional arg to post() is the endpoint URL.
    call_args = judge._client.post.call_args
    posted_url = call_args[0][0] if call_args[0] else call_args[1].get("url")
    assert posted_url == "http://10.0.0.42:8000/v1/chat/completions"


def test_judge_raises_budget_exceeded_when_cap_breached(monkeypatch, tmp_path):
    """When the judge call would push cumulative run cost past
    `PG_MAX_COST_PER_RUN`, `BudgetExceededError` is raised — NOT
    silently fail-opened as a `judge_error`.
    """
    ledger_path = tmp_path / "ledger.jsonl"
    monkeypatch.setattr(openrouter_client, "_COST_LEDGER_PATH", ledger_path)
    # Cap of $0.0001 means even a tiny call breaches.
    monkeypatch.setattr(openrouter_client, "PG_MAX_COST_PER_RUN", 0.0001)

    payload = {
        "choices": [{"message": {"content": json.dumps({
            "verdict": "ENTAILED", "reason": "ok",
        })}}],
        "usage": {
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "cost": 0.001,  # 10x the cap
        },
    }
    judge = _make_judge_with_mock_response(monkeypatch, payload)

    with pytest.raises(openrouter_client.BudgetExceededError):
        judge.judge("sentence", "span")


# ───────────────────── I-arch-004 F09: entailment judge pins the MIRROR chain ─────────────────────


def _posted_body(judge):
    """Extract the json body posted by the mocked httpx client."""
    call_args = judge._client.post.call_args
    return call_args.kwargs.get("json") if call_args else None


def test_entailment_judge_pins_mirror_chain_when_gate_active(monkeypatch):
    # I-arch-004 F09: the entailment side-judge must pin to the MIRROR role's resolved provider
    # (the locked GLM-5.1 chain), NOT the RETIRED "evaluator" role. The preflight role_provider_map
    # only carries generator/mirror/sentinel/judge; "evaluator" is absent -> get_role_provider(
    # "evaluator") == None -> NO pin -> free-route. Assert the judge looks up "mirror" and pins it
    # singleton-no-fallback (allow_fallbacks=False, require_parameters=True).
    payload = {
        "choices": [{"message": {"content": json.dumps({"verdict": "ENTAILED", "reason": "ok"})}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "cost": 0.0001},
    }
    judge = _make_judge_with_mock_response(monkeypatch, payload)
    from src.polaris_graph.benchmark import pathB_capture as _pathb
    looked_up = []

    def _fake_get_role_provider(role):
        looked_up.append(role)
        return "novita" if role == "mirror" else None

    monkeypatch.setattr(_pathb, "get_role_provider", _fake_get_role_provider)
    judge.judge("sentence", "span")
    body = _posted_body(judge)
    assert body["provider"] == {
        "order": ["novita"], "allow_fallbacks": False, "require_parameters": True}
    assert "mirror" in looked_up
    assert "evaluator" not in looked_up


def test_entailment_judge_retired_evaluator_key_does_not_free_route(monkeypatch):
    # I-arch-004 F09 regression guard: BEFORE the fix the judge looked up "evaluator", which the
    # locked 4-role role_provider_map never carries -> None -> NO provider pin -> free-route. Mimic
    # the real map shape (only the 4 locked roles populated) and prove the judge now PINS the mirror
    # chain (not None, not the generator's provider, not unpinned/free-route).
    payload = {
        "choices": [{"message": {"content": json.dumps({"verdict": "ENTAILED", "reason": "ok"})}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "cost": 0.0001},
    }
    judge = _make_judge_with_mock_response(monkeypatch, payload)
    from src.polaris_graph.benchmark import pathB_capture as _pathb
    role_map = {"generator": "fireworks", "mirror": "novita",
                "sentinel": "deepinfra", "judge": "together"}
    monkeypatch.setattr(_pathb, "get_role_provider", lambda role: role_map.get(role))
    judge.judge("sentence", "span")
    body = _posted_body(judge)
    assert body["provider"]["order"] == ["novita"]
    assert body["provider"]["allow_fallbacks"] is False
    assert body["provider"]["require_parameters"] is True


# ───────────────── I-arch-004 F19 (§9.1.8): token cap == the GLM-5.1 mirror-chain model max ────────


def test_entailment_judge_max_tokens_defaults_to_mirror_chain_model_max(monkeypatch):
    # F19: the posted body MUST carry the model REAL max (the pinned mirror-chain MIN
    # max_completion_tokens = 131072, live OpenRouter read 2026-06-14), NOT the old small 2000 hardcode.
    monkeypatch.delenv("PG_ENTAILMENT_MAX_TOKENS", raising=False)
    payload = {
        "choices": [{"message": {"content": json.dumps({"verdict": "ENTAILED", "reason": "ok"})}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "cost": 0.0001},
    }
    judge = _make_judge_with_mock_response(monkeypatch, payload)
    judge.judge("sentence", "span")
    body = _posted_body(judge)
    assert body["max_tokens"] == entailment_judge._ENTAILMENT_MAX_TOKENS_CHAIN_MIN == 131072
    # Reasoning effort stays "high" (NOT xhigh — the GLM bake-off proved xhigh blanks). Never starved.
    assert body["reasoning"] == {"effort": "high"}


def test_entailment_judge_max_tokens_env_override_clamped_to_chain_ceiling(monkeypatch):
    # F19: an env override ABOVE the chain MIN is CLAMPED DOWN (would otherwise hard-400 under
    # allow_fallbacks=False); a value BELOW is honored verbatim (cost/testing lever).
    payload = {
        "choices": [{"message": {"content": json.dumps({"verdict": "ENTAILED", "reason": "ok"})}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "cost": 0.0001},
    }
    monkeypatch.setenv("PG_ENTAILMENT_MAX_TOKENS", "999999")
    judge = _make_judge_with_mock_response(monkeypatch, payload)
    judge.judge("sentence", "span")
    assert _posted_body(judge)["max_tokens"] == 131072  # clamped to the chain ceiling

    monkeypatch.setenv("PG_ENTAILMENT_MAX_TOKENS", "4096")
    judge2 = _make_judge_with_mock_response(monkeypatch, payload)
    judge2.judge("sentence", "span")
    assert _posted_body(judge2)["max_tokens"] == 4096  # below ceiling -> honored
