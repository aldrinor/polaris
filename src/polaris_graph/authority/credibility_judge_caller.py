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
# I-arch-002 (#1251): the judge model (GLM-5.1) is a REASONING model. At max_tokens=512 it burned the
# whole budget on its internal reasoning and got TRUNCATED mid-thought (finish=length) -> the content was
# a truncation-error string, not JSON -> per-row judge_error -> fail-loud (or, vs a slow provider, the SYNC
# call stalled in ssl.recv and FROZE the asyncio loop). Operator directive 2026-06-13: reasoning effort
# stays MAX, NEVER disabled. The fix is to UN-STARVE the budget so high-effort reasoning COMPLETES and then
# emits the JSON (measured: effort=high + 8000 tokens -> finish=stop, 4070 reasoning chars + valid JSON,
# ~24s). Env-overridable per LAW VI.
_DEFAULT_MAX_TOKENS = 8000
_ENV_TIMEOUT_S = "PG_CREDIBILITY_JUDGE_TIMEOUT_S"
# Read-gap timeout (httpx). A completing high-reasoning call is ~24s; 120s leaves headroom for a slow
# provider while still bounding a no-bytes stall. The freeze itself is now prevented structurally by the
# concurrency + asyncio.to_thread offload (the call no longer runs on the event-loop thread).
_DEFAULT_TIMEOUT_S = 120.0
# Reasoning effort for the judge call (OpenRouter `reasoning.effort`). Operator 2026-06-13: MAX, never
# disabled — a credibility judgment with starved reasoning is "pure craps". Default HIGH (OpenRouter's top
# effort tier). Env may pick another VALID effort but the caller never sends an off/disabled reasoning.
_ENV_REASONING_EFFORT = "PG_CREDIBILITY_JUDGE_REASONING_EFFORT"
_DEFAULT_REASONING_EFFORT = "high"
# Bounded SAME-call retry on a transient transport fault / empty-or-truncated content, BEFORE the row
# becomes a judge_error (mirror entailment_judge I-transport-001). 0 disables. Each attempt is a real
# billed call (cost accounted per attempt).
_ENV_RETRIES = "PG_CREDIBILITY_JUDGE_RETRIES"
_DEFAULT_RETRIES = 2
_ENV_RETRY_BACKOFF_S = "PG_CREDIBILITY_JUDGE_RETRY_BACKOFF_S"
_DEFAULT_RETRY_BACKOFF_S = 0.5
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
    # Reasoning effort (operator: MAX, never disabled). An off/disabled value is coerced UP to the default
    # so a stray env can never strip the judge's reasoning.
    # Operator 2026-06-13: reasoning effort stays MAX, never starved. ANY sub-max / off / disabled value
    # (low, medium, off, none, garbage, ...) is coerced UP to the default (high). Only high or a HIGHER
    # tier (xhigh) passes through — the credibility judge can never run with lowered or disabled reasoning.
    reasoning_effort = (os.environ.get(_ENV_REASONING_EFFORT, "").strip().lower() or _DEFAULT_REASONING_EFFORT)
    if reasoning_effort not in ("high", "xhigh"):
        reasoning_effort = _DEFAULT_REASONING_EFFORT
    try:  # retries=0 must be honored (disable), so not _int_env (which clamps <=0 to the default)
        retries = max(0, int(os.environ.get(_ENV_RETRIES, _DEFAULT_RETRIES) or _DEFAULT_RETRIES))
    except (TypeError, ValueError):
        retries = _DEFAULT_RETRIES
    retry_backoff = _float_env(_ENV_RETRY_BACKOFF_S, _DEFAULT_RETRY_BACKOFF_S)
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
            # Operator 2026-06-13: reasoning effort stays MAX. With an un-starved max_tokens the
            # high-effort reasoning completes AND emits the JSON (measured: finish=stop, valid output).
            "reasoning": {"effort": reasoning_effort},
        }
        # PROVIDER PINNING (mirror entailment_judge): pin to the preflight-resolved MIRROR provider,
        # allow_fallbacks=False — never silently fail over to a non-sovereign/untested provider.
        # I-arch-004 F09: route via "mirror" (the LOCKED 4-role key), NOT the RETIRED "evaluator" key.
        # The preflight-resolved role_provider_map only carries generator/mirror/sentinel/judge
        # (pathB_runner._LOCKED_ROLES); the legacy "evaluator" key is absent, so get_role_provider(
        # "evaluator") returned None -> NO provider pin -> this credibility judge FREE-ROUTED to an
        # unpinned provider instead of the locked mirror chain. Per polaris_runtime_lock.yaml:
        # legacy_compat the retired evaluator role maps_to_role: mirror (GLM-5.1), so the side-judge
        # pins to the SAME provider chain as the main mirror role.
        try:
            from src.polaris_graph.benchmark import pathB_capture as _pathb
            gate_provider = _pathb.get_role_provider("mirror")
        except Exception:  # noqa: BLE001 — routing lookup must never break the call
            _pathb = None
            gate_provider = None
        # I-arch-002 (#1250): operator-directed (2026-06-13) — the open-weight judge MODEL is the
        # sovereign unit; the HOSTING provider may be US/China if more stable. A slow/trickling
        # pinned provider (allow_fallbacks=False) FROZE the whole run: this is a synchronous httpx
        # call on the asyncio MainThread, so a stalled SSL read blocks the entire event loop
        # (py-spy root cause). When PG_ROLE_ALLOW_FALLBACKS is set, SKIP the single-provider pin so
        # OpenRouter free-routes the model to its fastest available provider (sidesteps a slow pin
        # entirely — better than allow_fallbacks=True, which only fails over on ERROR, not slowness).
        _free_route = os.environ.get("PG_ROLE_ALLOW_FALLBACKS", "").strip().lower() in (
            "1", "true", "yes", "on",
        )
        if gate_provider and not _free_route:
            json_body["provider"] = {
                "order": [gate_provider], "allow_fallbacks": False, "require_parameters": True,
            }

        # Bounded retry over the SYNC post: a transient transport fault OR an empty/truncated body is
        # retried (each attempt is a real billed call, cost-accounted per attempt) before the row becomes a
        # judge_error. httpx.Timeout bounds the read gap; the event-loop freeze is prevented STRUCTURALLY by
        # the caller's concurrency + asyncio.to_thread offload (this no longer runs on the loop thread).
        client_timeout = httpx.Timeout(call_timeout, connect=15.0)
        last_content = ""
        for _attempt in range(retries + 1):
            try:
                with httpx.Client(timeout=client_timeout) as client:
                    response = client.post(
                        endpoint,
                        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                        json=json_body,
                    )
                    response.raise_for_status()
                    data = response.json()
            except Exception:  # noqa: BLE001 — transport/parse fault: retry, else propagate to the judge
                if _attempt < retries:
                    time.sleep(retry_backoff)
                    continue
                raise  # judge wrapper catches -> {} -> bounded per-row judge_error (fail-loud upstream)

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

            # COST + BUDGET per billed attempt (so a cap breach aborts regardless of parse) — entailment order.
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

            try:
                choice0 = data["choices"][0]
                last_content = choice0["message"]["content"] or ""
                finish_reason = choice0.get("finish_reason")
            except (KeyError, IndexError, TypeError):
                last_content = ""
                finish_reason = None
            # Accept only a COMPLETE, non-empty body. Empty content OR a length-truncation (high-effort
            # reasoning consumed the whole budget -> the JSON never lands) is retried on a fresh call before
            # the row becomes a judge_error. With max_tokens=8000 a truncation is rare; the retry is bounded.
            if last_content.strip() and finish_reason != "length":
                return last_content
            if _attempt < retries:
                time.sleep(retry_backoff)
                continue
        # Retries exhausted with no usable content: return it (judge wrapper -> {} -> bounded judge_error).
        return last_content

    return call_llm
