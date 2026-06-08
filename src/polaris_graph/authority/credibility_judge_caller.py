"""I-cred-012a — spend-tracked, gate-observed SYNC OpenRouter caller for the credibility judge.

The P2 judge is SYNCHRONOUS and runs inside the already-async generator loop, so the LLM call must be sync
(no async-in-async). This MIRRORS the proven `entailment_judge` control surface exactly so the credibility
judge is NOT an unobserved/unpinned bypass (Codex I-cred-012a iter-2 P1-1):
  * FAMILY SEGREGATION at construction — the credibility model must differ from the generator family.
  * PROVIDER PINNING — when the Gate-B Path-B gate is active, pin to the preflight-resolved evaluator
    provider with allow_fallbacks=False (so it can't silently fail over to a non-sovereign/flaky provider).
  * PATH-B CAPTURE (role="evaluator") + RAW-IO SINK — so the two-family/observability gate sees the call.
  * COST + BUDGET — cost recorded and `check_run_budget` enforced; `BudgetExceededError` PROPAGATES (it is
    NOT caught here and must not be masked downstream) so a cap breach reaches the sweep's budget-abort.

The credibility judge is an EVALUATOR-family advisory call (same role surface as the entailment judge);
open-weight model only (env `PG_CREDIBILITY_JUDGE_MODEL`). Runs ONLY when the runner threads it under the
master slate (operator-gated). Offline tests inject a stub caller and never reach this module.
"""
from __future__ import annotations

import os
import time
import uuid
from typing import Callable

from src.polaris_graph.llm import openrouter_client as _orc

_ENV_MODEL = "PG_CREDIBILITY_JUDGE_MODEL"
_DEFAULT_MODEL = "z-ai/glm-5.1"                       # open-weight (MIT), sovereign; override via env
_ENV_MAX_TOKENS = "PG_CREDIBILITY_JUDGE_MAX_TOKENS"
_DEFAULT_MAX_TOKENS = 512
_ENV_TIMEOUT_S = "PG_CREDIBILITY_JUDGE_TIMEOUT_S"
_DEFAULT_TIMEOUT_S = 60.0
_ENV_DEGRADED_PROMPT_TOKENS = "PG_CREDIBILITY_JUDGE_DEGRADED_PROMPT_TOKENS"
_DEFAULT_DEGRADED_PROMPT_TOKENS = 500
_ENV_DEGRADED_COMPLETION_TOKENS = "PG_CREDIBILITY_JUDGE_DEGRADED_COMPLETION_TOKENS"
_DEFAULT_DEGRADED_COMPLETION_TOKENS = 100


def _int_env(name: str, default: int) -> int:
    try:
        value = int(os.environ.get(name, "") or default)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _float_env(name: str, default: float) -> float:
    try:
        value = float(os.environ.get(name, "") or default)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def credibility_judge_model() -> str:
    return os.environ.get(_ENV_MODEL, "").strip() or _DEFAULT_MODEL


def make_openrouter_credibility_caller(
    *, model: str | None = None, max_tokens: int | None = None, temperature: float = 0.0,
    timeout: float | None = None,
) -> Callable[[str], str]:
    """Return a sync ``call_llm(prompt) -> text`` that calls the open-weight credibility model via the SAME
    control surface as the entailment judge: family-checked, provider-pinned, Path-B-captured, cost +
    budget enforced. ``BudgetExceededError`` propagates (a cap breach must abort the sweep, not be masked)."""
    import httpx  # local import: keep off-mode (master flag off) import cost zero

    # Two-family invariant (§9.1.1): the credibility judge (evaluator-family advisory) must NOT share the
    # generator's family. Raises at construction if misconfigured.
    chosen_model = (model or "").strip() or credibility_judge_model()
    _orc.check_family_segregation(evaluator_model=chosen_model)

    cap_tokens = max_tokens or _int_env(_ENV_MAX_TOKENS, _DEFAULT_MAX_TOKENS)
    call_timeout = timeout or _float_env(_ENV_TIMEOUT_S, _DEFAULT_TIMEOUT_S)
    base = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
    endpoint = base + "/chat/completions"
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("PG_SWEEP_CREDIBILITY_REDESIGN credibility judge requires OPENROUTER_API_KEY")

    def call_llm(prompt: str) -> str:
        started = time.monotonic()
        json_body: dict = {
            "model": chosen_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": cap_tokens,
        }
        # PROVIDER PINNING (mirror entailment_judge): pin to the preflight-resolved evaluator provider,
        # allow_fallbacks=False — never silently fail over to a non-sovereign/untested provider.
        try:
            from src.polaris_graph.benchmark import pathB_capture as _pathb
            gate_provider = _pathb.get_role_provider("evaluator")
        except Exception:  # noqa: BLE001 — routing lookup must never break the call
            _pathb = None
            gate_provider = None
        if gate_provider:
            json_body["provider"] = {
                "order": [gate_provider], "allow_fallbacks": False, "require_parameters": True,
            }

        with httpx.Client(timeout=call_timeout) as client:
            response = client.post(
                endpoint,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=json_body,
            )
            response.raise_for_status()
            data = response.json()

        # PATH-B two-family capture + raw-IO sink (so the gate observes this evaluator-role call).
        try:
            if _pathb is not None and _pathb.is_active():
                _pathb.capture_llm_call(
                    role="evaluator",
                    messages=[{"role": "user", "content": prompt}],
                    raw_response=data,
                )
        except Exception:  # noqa: BLE001 — capture must never break the call
            pass
        try:
            io_sink = _orc.current_raw_io_sink()
            if io_sink is not None:
                io_sink.record(
                    call_id=uuid.uuid4().hex, call_type="credibility_judge", role="evaluator",
                    request=json_body, raw_response=data,
                    duration_ms=(time.monotonic() - started) * 1000.0,
                    # I-cred-012a iter-4 P2: label by the SERVED envelope — a malformed response (no
                    # choices) is the judge_error outcome (the content extract below will fail), not
                    # transport-"ok". Observability fidelity; does not change the abort behavior.
                    status=("ok" if (data.get("choices") or []) else "judge_error"),
                )
        except Exception:  # noqa: BLE001
            pass

        # COST + BUDGET first (so a cap breach aborts regardless of parse) — same order as entailment_judge.
        usage = data.get("usage", {}) or {}
        input_tokens = int(usage.get("prompt_tokens", 0) or 0)
        output_tokens = int(usage.get("completion_tokens", 0) or 0)
        cost = float(usage.get("cost", 0) or 0) or _orc._impute_cost_from_tokens(
            chosen_model, input_tokens, output_tokens, 0,
        )
        if cost == 0 and not usage:  # degraded response, no usage block: conservative estimate
            cost = _orc._impute_cost_from_tokens(
                chosen_model,
                _int_env(_ENV_DEGRADED_PROMPT_TOKENS, _DEFAULT_DEGRADED_PROMPT_TOKENS),
                _int_env(_ENV_DEGRADED_COMPLETION_TOKENS, _DEFAULT_DEGRADED_COMPLETION_TOKENS),
                0,
            )
        _orc._add_run_cost(cost)
        try:
            _orc.append_cost_ledger_row(
                session_id=_orc.current_run_id() or "credibility_judge",
                call_type="credibility_judge",
                cost_usd=cost,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
        except Exception:  # noqa: BLE001 — persistent ledger IO is non-critical
            pass
        _orc.check_run_budget(0)  # raises BudgetExceededError on cap breach (MUST propagate — not masked)
        return data["choices"][0]["message"]["content"]

    return call_llm
