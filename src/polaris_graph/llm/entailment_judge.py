"""Entailment judge — LLM-as-judge for strict_verify check (f).

Originally inlined in `polaris_graph.generator2.strict_verify`. Extracted
per I-bug-099 so future call sites (I-bug-100 OpenRouterClient routing,
I-bug-101 FPR audit harness, etc.) can import the judge + telemetry from
a single canonical location.

I-bug-102 — off-mode contract (verified by `test_off_mode_does_not_instantiate_judge`):
when `PG_STRICT_VERIFY_ENTAILMENT=off`, the judge is NEVER instantiated:
- `_get_judge()` is not called from any code path
- `_EntailmentJudge.__init__` does NOT run
- No `httpx.Client` is constructed
- No OpenRouter network call is made
The class definitions are loaded into the module namespace at import
time (Python module evaluation), but no judge object exists. Module-
level imports are kept lightweight: `openrouter_client` is imported
lazily inside the methods that need it (judge construction, ledger
write, budget check), so off-mode pays zero cost beyond reading the
class definitions.

The judge asks an LLM whether a cited SPAN semantically ENTAILS a
SENTENCE's specific claims. It runs AFTER mechanical checks (a)-(e) and
catches residual fabrication patterns the audit on 2026-05-09 surfaced:
  - mechanistic granularity insertion (M2)
  - specificity inflation (C2)
  - numbers nearby but not entailed (C1)

The judge model is the two-family evaluator (Gemma 4 31B by default),
matching the §9.1.1 invariant — different lineage from the generator
(DeepSeek). Calls go through OpenRouter using the existing project
auth substrate. Family segregation is enforced at construction.

Public surface (re-exported via `polaris_graph.generator2.strict_verify`
for backwards compat with monkeypatch test pattern):
  - _EntailmentJudge: synchronous httpx wrapper around an OpenRouter call
  - _get_judge(): lazy singleton accessor
  - _JUDGE_TELEMETRY: process-lifetime gate counters
  - get_judge_telemetry(): read-only snapshot
  - reset_judge_telemetry(): zero in-place
  - _record_judge_outcome(): tick counters from judge result

NOT moved here (still in strict_verify.py because tests rebind via
monkeypatch.setattr on strict_verify):
  - _DEFAULT_MODE
  - _UNKNOWN_MODE_WARNED
  - _entailment_mode()
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone

# I-bug-100: import openrouter_client as a MODULE reference (not by-value)
# so monkeypatch.setattr on its globals (`PG_MAX_COST_PER_RUN`,
# `_COST_LEDGER_PATH`, etc.) propagates to the cost-accounting code paths
# in this module. Direct `from … import _COST_LEDGER_PATH` would bind
# the value at import time and tests could not override it without
# reloading the module.
#
# I-bug-102 NOTE: this top-level import IS evaluated even in off-mode.
# The "skip generator2 import" goal in I-bug-102 is interpreted as
# "no JUDGE INSTANTIATION + no NETWORK CALL in off-mode" (verified by
# `test_off_mode_does_not_instantiate_judge`), NOT as eliminating the
# module-import side effect. Empirically the openrouter_client import
# is ~50ms cold; off-mode users pay this once at strict_verify import
# time. Eliminating it via per-method lazy-import would complicate the
# `except _orc.BudgetExceededError` semantics (exception types must be
# resolved at except-clause evaluation, which is a hot-path call).
# The test asserts the runtime contract; cold-import cost is accepted.
from src.polaris_graph.llm import openrouter_client as _orc

logger = logging.getLogger(__name__)


_DEFAULT_ENTAILMENT_MODEL = "google/gemma-4-31b-it"
_ENTAILMENT_TIMEOUT_S = 30.0
_ENTAILMENT_PROMPT = """You are a strict entailment judge. You will be given a SPAN of source text and a SENTENCE that cites that span. Decide whether the SPAN entails the SENTENCE.

Rules:
- ENTAILED: every factual assertion in the SENTENCE is supported by the SPAN. Conservative paraphrase is allowed.
- NEUTRAL: the SENTENCE introduces a fact, entity, mechanism, or specificity NOT present in the SPAN (e.g. SPAN says "GLP-1 RAs", SENTENCE says "semaglutide"; SPAN says "adipocyte metabolism", SENTENCE adds "lipid metabolism" or "energy storage"; SPAN has numbers but not the specific claim being made).
- CONTRADICTED: the SENTENCE asserts something the SPAN explicitly disagrees with.

Return STRICT JSON only, no prose:
{{"verdict": "ENTAILED" | "NEUTRAL" | "CONTRADICTED", "reason": "<one short sentence>"}}

SPAN:
{span}

SENTENCE:
{sentence}

JSON:"""


class _EntailmentJudge:
    """Synchronous httpx wrapper around an OpenRouter entailment call.

    Lazy-initialized via _get_judge() so import-time cost is zero when
    PG_STRICT_VERIFY_ENTAILMENT=off (the default before I-bug-095).
    """

    def __init__(self) -> None:
        import httpx  # local import: avoid forcing the dep when off

        # Lazy-import the family-segregation check so the off-mode path
        # never touches openrouter_client. The judge is acting as a
        # content evaluator (Layer-2), so it MUST differ from the
        # generator family per CLAUDE.md §9.1.1 — fail at construction
        # if PG_ENTAILMENT_MODEL is in the same family as PG_GENERATOR_MODEL.
        from src.polaris_graph.llm.openrouter_client import check_family_segregation

        api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError(
                "PG_STRICT_VERIFY_ENTAILMENT requires OPENROUTER_API_KEY"
            )
        self._api_key = api_key
        self._model = os.environ.get(
            "PG_ENTAILMENT_MODEL", _DEFAULT_ENTAILMENT_MODEL
        )
        # Two-family invariant per §9.1.1: raises RuntimeError if the
        # entailment judge ends up in the same family as the generator
        # (e.g. an operator setting PG_ENTAILMENT_MODEL to a DeepSeek
        # variant when PG_GENERATOR_MODEL is also DeepSeek). The
        # default model (google/gemma-4-31b-it) is in a different
        # family from DeepSeek by construction.
        check_family_segregation(evaluator_model=self._model)
        self._client = httpx.Client(timeout=_ENTAILMENT_TIMEOUT_S)

    def judge(self, sentence: str, span: str) -> tuple[str, str]:
        """Return (verdict, reason).

        verdict is one of "ENTAILED", "NEUTRAL", "CONTRADICTED".
        On API/parse failure returns ("ENTAILED", "judge_error: ...") —
        fail-open so a transient OpenRouter outage does not nuke a run.

        I-bug-100: after each successful httpx call this method records
        the call cost via openrouter_client's module-level helpers
        (`_add_run_cost`, `check_run_budget`, `_COST_LEDGER_PATH`) so
        judge spend is visible to the per-run budget cap and the cost
        ledger. `BudgetExceededError` is explicitly re-raised before
        the broad `except Exception` fail-open handler so a cap breach
        aborts the sweep cleanly instead of being masked as a transient
        judge error.
        """
        prompt = _ENTAILMENT_PROMPT.format(span=span, sentence=sentence)
        started = time.monotonic()
        try:
            response = self._client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self._model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.0,
                    "max_tokens": 100,
                    "response_format": {"type": "json_object"},
                },
            )
            response.raise_for_status()
            data = response.json()

            # I-bug-100: cost recording. Reads + records BEFORE verdict
            # parse so a cap breach aborts the sweep regardless of
            # downstream parse outcome.
            usage = data.get("usage", {}) or {}
            input_tokens = int(usage.get("prompt_tokens", 0) or 0)
            output_tokens = int(usage.get("completion_tokens", 0) or 0)
            api_cost = float(usage.get("cost", 0) or 0)
            actual_cost = api_cost or _orc._impute_cost_from_tokens(
                self._model, input_tokens, output_tokens, 0,
            )
            # I-bug-100 iter-1 diff P2 fix: when the entire usage block
            # is absent, both api_cost and the imputed value are 0, which
            # silently bypasses the budget guard. Fall back to a
            # conservative estimate based on typical judge-call shape
            # (~500 prompt + ~100 completion tokens) priced at Opus-tier
            # so the budget cap is preserved on degraded responses.
            if actual_cost == 0 and not usage:
                actual_cost = _orc._impute_cost_from_tokens(
                    self._model, 500, 100, 0,
                )
            _orc._add_run_cost(actual_cost)
            duration_ms = (time.monotonic() - started) * 1000.0
            try:
                _append_judge_ledger_entry(
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    duration_ms=duration_ms,
                    actual_cost=actual_cost,
                )
            except Exception as exc:  # noqa: BLE001 — ledger IO is non-critical
                logger.warning("entailment ledger write failed: %s", exc)
            _orc.check_run_budget(0)  # raises BudgetExceededError if cap breached

            content = data["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            verdict = str(parsed.get("verdict", "")).upper().strip()
            reason = str(parsed.get("reason", ""))
            if verdict not in ("ENTAILED", "NEUTRAL", "CONTRADICTED"):
                return "ENTAILED", f"judge_error: bad_verdict={verdict!r}"
            return verdict, reason
        except _orc.BudgetExceededError:
            # I-bug-100: do NOT fail-open on cap breach. Propagate so
            # the sweep aborts with a clear cause.
            raise
        except Exception as exc:  # noqa: BLE001 — fail-open by design
            logger.warning("entailment judge error: %s", exc)
            return "ENTAILED", f"judge_error: {type(exc).__name__}"


def _append_judge_ledger_entry(
    *,
    input_tokens: int,
    output_tokens: int,
    duration_ms: float,
    actual_cost: float,
) -> None:
    """Append a single entailment-judge call to the cost ledger.

    Schema mirrors `openrouter_client.OpenRouterClient._append_ledger`
    (line ~481-491) so per-run filters that key on `session_id` /
    `call_type` (e.g., scripts/run_honest_sweep_r3.py) include judge
    calls without code changes downstream.

    All `_orc.<attr>` accesses go through the module reference so
    test monkeypatch.setattr on `openrouter_client._COST_LEDGER_PATH`
    propagates correctly.
    """
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "session_id": _orc._CURRENT_RUN_ID_CTX.get() or "no_run_id",
        "call_type": "entailment_judge",
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "reasoning_tokens": 0,
        "duration_ms": round(duration_ms, 1),
        "cost_usd": round(actual_cost, 6),
        "cumulative_cost_usd": round(_orc.current_run_cost(), 4),
    }
    _orc._COST_LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_orc._COST_LEDGER_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


_JUDGE_SINGLETON: _EntailmentJudge | None = None


def _get_judge() -> _EntailmentJudge:
    """Lazy singleton so off-mode pays zero import/connection cost."""
    global _JUDGE_SINGLETON
    if _JUDGE_SINGLETON is None:
        _JUDGE_SINGLETON = _EntailmentJudge()
    return _JUDGE_SINGLETON


# I-bug-096: process-lifetime telemetry counters for the entailment gate.
# In enforce mode the judge fail-open path returns ("ENTAILED",
# "judge_error: ...") on transient API errors. A persistent OpenRouter
# outage or model-format change could make the 6th check silently inert
# — every sentence falls through as ENTAILED while WARNING lines
# accumulate. These counters give an operator a concise "the gate ran N
# times, M of those errored" signal.
#
# Counters are gate-side (not judge-side) per the original I-bug-092
# brief verdict: gate behavior is what we want to measure, not a
# specific judge implementation. Tests with FakeJudge tick these too,
# and a future swapped judge cannot bypass the judge_error counter.
_JUDGE_TELEMETRY: dict[str, int] = {
    "calls": 0,
    "entailed": 0,
    "neutral": 0,
    "contradicted": 0,
    "judge_error": 0,
}


def get_judge_telemetry() -> dict[str, int]:
    """Snapshot of process-lifetime entailment-judge counters.

    Read once before a job to compute deltas if needed. Operators
    concerned that the gate has gone silently inert can poll this from
    a health endpoint or scripts/observability tooling and alert on
    judge_error rate.
    """
    return dict(_JUDGE_TELEMETRY)


def reset_judge_telemetry() -> None:
    """Zero all judge telemetry counters in-place.

    Public so operators can deliberately reset between jobs / runs.
    Tests use this for isolation; production callers can use it to
    bound the counter arithmetic to a single run window.
    """
    for key in _JUDGE_TELEMETRY:
        _JUDGE_TELEMETRY[key] = 0


def _record_judge_outcome(verdict: str, reason: str) -> None:
    """Tick the appropriate counter based on judge return values.

    Normalizes the existing judge fail-open contract: when reason
    starts with 'judge_error:', the call errored and was returned as
    ENTAILED to keep the run alive. We tick judge_error in that case
    instead of entailed so an operator can distinguish "gate accepted
    the sentence" from "gate failed open."
    """
    _JUDGE_TELEMETRY["calls"] += 1
    if reason.startswith("judge_error:"):
        _JUDGE_TELEMETRY["judge_error"] += 1
        return
    key = verdict.lower()
    if key in _JUDGE_TELEMETRY:
        _JUDGE_TELEMETRY[key] += 1
