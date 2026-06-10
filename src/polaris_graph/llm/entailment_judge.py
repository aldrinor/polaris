"""Entailment judge — LLM-as-judge for strict_verify check (f).

Originally inlined in `polaris_graph.clinical_generator.strict_verify`. Extracted
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

Public surface (re-exported via `polaris_graph.clinical_generator.strict_verify`
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

# I-bug-100: import openrouter_client as a MODULE reference (not by-value)
# so monkeypatch.setattr on its globals (`PG_MAX_COST_PER_RUN`,
# `_COST_LEDGER_PATH`, etc.) propagates to the cost-accounting code paths
# in this module. Direct `from … import _COST_LEDGER_PATH` would bind
# the value at import time and tests could not override it without
# reloading the module.
#
# I-bug-102 NOTE: this top-level import IS evaluated even in off-mode.
# The "skip clinical_generator import" goal in I-bug-102 is interpreted as
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
# I-transport-001 (#1191) Site 4 (LAW VI — no magic numbers): bounded SAME-provider retry count
# for a single judge call. A transient transport/parse/empty-choices fault on the entailment judge
# previously fell straight through to the fail-open ('ENTAILED','judge_error:…') sentinel, which the
# consumers DROP in enforce mode — an OVER-DROP of a salvageable verdict (the drb_72-class coverage
# collapse). Retry the POST+parse this many extra times before emitting the sentinel; default 2
# (=> up to 3 total attempts). 0 disables the retry (single attempt, the pre-#1191 behavior).
_DEFAULT_ENTAILMENT_RETRIES = 2
# Short fixed backoff between judge retries (seconds). Env-overridable per LAW VI.
_DEFAULT_ENTAILMENT_RETRY_BACKOFF_S = 0.5


class _RetryableJudgeError(Exception):
    """I-transport-001 (#1191) Site 4: a transient/recoverable judge fault that should trigger a
    bounded SAME-provider retry. Carries the human-readable `reason` used for the terminal
    ('ENTAILED','judge_error: <reason>') sentinel so a bad-verdict's `bad_verdict=<v>` detail is
    preserved across retries instead of being collapsed into a generic exception type name."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason
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
        # I-sov-001: endpoint is env-configurable so the sovereign deploy
        # can point the entailment judge at the OVH H200 vLLM endpoint
        # (set OPENROUTER_BASE_URL=http://<priv-ip>:8000/v1). Default keeps
        # OpenRouter. Mirrors openrouter_client.py:43-45.
        base_url = os.environ.get(
            "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
        ).rstrip("/")
        self._endpoint = f"{base_url}/chat/completions"
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

        I-transport-001 (#1191) Site 4: a transient transport/parse/empty-choices/bad-verdict
        fault is now RETRIED on the same provider up to `PG_ENTAILMENT_RETRIES` extra times
        (default 2 => 3 total attempts; env-driven per LAW VI) before the method emits the
        ('ENTAILED', 'judge_error: ...') sentinel on exhaustion. This is NOT a fail-OPEN: both
        consumers FAIL CLOSED on that sentinel — `clinical_generator/strict_verify.py:295-301`
        keys on the `judge_error:` PREFIX alone (drops in enforce); `provenance_generator.py:1795`
        sets `judge_error_flag` on `verdict=='ENTAILED' AND reason.startswith('judge_error:')`
        (consumed -> drop). The sentinel stays EXACTLY ('ENTAILED', 'judge_error: ...') so that
        detection is preserved (do NOT flip to NEUTRAL standalone — that bypasses the
        provenance detection at :1795). The retry's only effect is to stop a SINGLE transient
        judge fault from OVER-DROPPING a salvageable verdict (the drb_72-class coverage collapse),
        without loosening the binding faithfulness gate.

        I-bug-100: after each successful httpx call this method records
        the call cost via openrouter_client's module-level helpers
        (`_add_run_cost`, `check_run_budget`, `_COST_LEDGER_PATH`) so
        judge spend is visible to the per-run budget cap and the cost
        ledger. `BudgetExceededError` is explicitly re-raised before
        the broad retry/fail-closed handler so a cap breach aborts the
        sweep cleanly instead of being masked as a transient judge error
        or being retried.
        """
        prompt = _ENTAILMENT_PROMPT.format(span=span, sentence=sentence)
        started = time.monotonic()
        # I-bug-946 (#932): when Path-B gate is active, force singleton provider routing in
        # the request body to match the resolved-at-preflight per-role provider. Without this,
        # this direct httpx path bypasses the gate's routing intent (the OpenRouterClient path
        # also got the override via openrouter_client.py:1400-1410). Codex iter-2 P1#2.
        # Codex iter-1 diff P1#2: this lookup MUST use explicit role="evaluator", NOT the
        # ambient _ROLE contextvar. The entailment judge fires during section generation
        # (where _ROLE=="generator"), but it posts the evaluator-family model — using the
        # ambient role would route Gemma to the generator's provider (Fireworks, no Gemma).
        try:
            from src.polaris_graph.benchmark import pathB_capture as _pathb_for_routing
            _gate_provider = _pathb_for_routing.get_role_provider("evaluator")
        except Exception:
            _gate_provider = None
        json_body: dict = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
            "max_tokens": 100,
            "response_format": {"type": "json_object"},
        }
        if _gate_provider:
            json_body["provider"] = {
                "order": [_gate_provider],
                "allow_fallbacks": False,
                "require_parameters": True,
            }
        def _emit_raw_io(status: str, raw_response, duration_ms=None) -> None:
            # I-obs-001 #1141 AC3 (gate iter-1 P1): single capture point so a judge call emits EXACTLY
            # one raw-IO record tagged by its TRUE outcome — "ok" ONLY after a validated verdict;
            # "judge_error" on bad_verdict / parse-failure / transport fail-open. Default-OFF; never raises.
            try:
                _io_sink = _orc.current_raw_io_sink()
                if _io_sink is None:
                    return
                import uuid as _uuid
                _io_sink.record(
                    call_id=_uuid.uuid4().hex, call_type="entailment_judge", role="evaluator",
                    request={**json_body, "messages": [{"role": "user", "content": prompt}]},
                    raw_response=raw_response, duration_ms=duration_ms, status=status,
                )
            except Exception:  # noqa: BLE001
                pass

        # I-transport-001 (#1191) Site 4: bounded SAME-provider retry around post+parse+budget+
        # verdict (LAW VI — env-driven bounds). A single transient transport/parse/empty-choices/
        # bad-verdict fault now RETRIES instead of immediately fail-closing the verdict (which the
        # consumers DROP -> over-drop of a salvageable verdict, the drb_72-class coverage collapse).
        _retries = max(0, int(os.environ.get("PG_ENTAILMENT_RETRIES", _DEFAULT_ENTAILMENT_RETRIES)))
        _backoff = max(
            0.0,
            float(os.environ.get(
                "PG_ENTAILMENT_RETRY_BACKOFF_S", _DEFAULT_ENTAILMENT_RETRY_BACKOFF_S
            )),
        )
        data = None  # I-obs-001 #1141 AC3: bound before the loop so the terminal judge_error
        # capture can prefer the served response (post ok, parse/verdict failed) over the exc string.
        last_reason = ""
        for attempt in range(_retries + 1):
            data = None  # reset per attempt so a later attempt's terminal capture is not stale.
            try:
                response = self._client.post(
                    self._endpoint,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json=json_body,
                )
                response.raise_for_status()
                data = response.json()

                # I-safety-002b (#925): Path-B gate capture. The entailment judge is the
                # evaluator-family LLM call that bypasses OpenRouterClient (direct httpx),
                # so without capturing here the gate's two-family completeness check would
                # be a silent no-op. Best-effort + gate-flagged; lazy import keeps off-mode
                # import cost zero. `data` is the genuinely-served non-stream JSON.
                try:
                    from src.polaris_graph.benchmark import pathB_capture as _pathb
                    if _pathb.is_active():
                        _pathb.capture_llm_call(
                            role="evaluator",
                            messages=[{"role": "user", "content": prompt}],
                            raw_response=data,
                        )
                except Exception:  # noqa: BLE001 — capture must never break the judge
                    pass

                # I-bug-100: cost recording. Reads + records BEFORE verdict
                # parse so a cap breach aborts the sweep regardless of
                # downstream parse outcome. Each real POST (incl. a retried one) bills its OWN
                # tokens — correct, real money was spent — so this runs inside the loop per attempt.
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
                    # Bad verdict = a recoverable failed verification: raise the RETRYABLE error so a
                    # transient garbled verdict re-issues. The reason (with bad_verdict=<v>) is
                    # preserved for the terminal sentinel on exhaustion.
                    raise _RetryableJudgeError(f"bad_verdict={verdict!r}")
                # Validated verdict → the ONE success raw-IO record, AFTER parse (gate iter-1 P1).
                _emit_raw_io("ok", data, duration_ms=(time.monotonic() - started) * 1000.0)
                return verdict, reason
            except _orc.BudgetExceededError:
                # I-bug-100: do NOT fail-open OR retry on cap breach. Propagate immediately so the
                # sweep aborts with a clear cause (this except MUST stay FIRST/outside the retry).
                raise
            except _RetryableJudgeError as exc:
                last_reason = exc.reason
                if attempt < _retries:
                    logger.warning(
                        "entailment judge bad verdict (attempt %d/%d): %s — retrying.",
                        attempt + 1, _retries + 1, exc.reason,
                    )
                    time.sleep(_backoff)
                    continue
                break
            except Exception as exc:  # noqa: BLE001 — transient transport/parse fault: retry then fail-closed
                last_reason = type(exc).__name__
                if attempt < _retries:
                    logger.warning(
                        "entailment judge error (attempt %d/%d): %s — retrying.",
                        attempt + 1, _retries + 1, exc,
                    )
                    time.sleep(_backoff)
                    continue
                logger.warning("entailment judge error (final): %s", exc)
                break

        # Retries exhausted: emit EXACTLY ONE terminal judge_error record (no per-attempt emits) and
        # return the fail-CLOSED-at-consumer sentinel. Prefer the bound served data (a parse/verdict
        # failure on a real response) over a bare error string. The sentinel stays ENTAILED+prefix so
        # both consumers DROP it (see method docstring + §5 DIVERGENCE in the brief).
        _emit_raw_io("judge_error", data if data is not None else {"error": last_reason})
        return "ENTAILED", f"judge_error: {last_reason}"


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
    # FX-11 (BUG-10): route through the SINGLE canonical cost-ledger writer, which bumps the shared,
    # monotonic per-session accumulator and appends the row atomically (NOT current_run_cost(),
    # which is reset per parallel four-role worker). Best-effort I/O is handled inside the writer.
    _orc.append_cost_ledger_row(
        session_id=_orc._CURRENT_RUN_ID_CTX.get() or "no_run_id",
        call_type="entailment_judge",
        cost_usd=actual_cost,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        duration_ms=duration_ms,
    )


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

# FX-09 (I-ready-017): per-RUN, concurrency-isolated judge counters. The process-
# lifetime _JUDGE_TELEMETRY above is shared across threads, so a per-run
# judge_error_rate computed from its delta is contaminated when two runs share one
# process (the v6 Dramatiq worker runs `asyncio.run(run_one_query(...))` under
# `--threads 2`). A ContextVar is isolated per OS-thread AND per asyncio Task, so each
# run that calls begin_run_judge_telemetry() gets its OWN {calls, judge_error}
# counter. The global counter (health endpoint) is unaffected.
import contextvars  # noqa: E402  (kept next to the counters it scopes)

_RUN_JUDGE_TELEMETRY: contextvars.ContextVar[dict[str, int] | None] = (
    contextvars.ContextVar("_run_judge_telemetry", default=None)
)


def begin_run_judge_telemetry() -> dict[str, int]:
    """Start a per-run, concurrency-isolated judge counter and return it.

    Bind a fresh {calls, judge_error} dict to the contextvar for THIS run. The judge
    ticks both the process-lifetime counter and (if set) this per-run dict. Read the
    returned dict at the end of the run for an isolated denominator — never
    contaminated by a sibling run sharing the process (FX-09 #1114). Sequential calls
    in one context each rebind to a fresh dict, so no reset is required for
    correctness; the previous run's dict is simply replaced.
    """
    tel = {"calls": 0, "judge_error": 0}
    _RUN_JUDGE_TELEMETRY.set(tel)
    return tel


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
    # FX-09: also tick the per-run, concurrency-isolated counter if a run scope is active.
    _run_tel = _RUN_JUDGE_TELEMETRY.get()
    if _run_tel is not None:
        _run_tel["calls"] += 1
    if reason.startswith("judge_error:"):
        _JUDGE_TELEMETRY["judge_error"] += 1
        if _run_tel is not None:
            _run_tel["judge_error"] += 1
        return
    key = verdict.lower()
    if key in _JUDGE_TELEMETRY:
        _JUDGE_TELEMETRY[key] += 1
