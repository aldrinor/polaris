"""I-arch-005 B14 (#1257) — shared SIDE-JUDGE empty-content guard + retry + IO trace.

A *side judge* is any non-binding evaluator LLM call that is NOT one of the four locked
faithfulness roles (e.g. the cross-document NLI conflict judge, the credibility judge,
the entailment side-judge). Their shared failure mode (forensically observed mid-run on
drb_72 / drb_75, 2026-06-12..14) is the **empty-content collapse**: a reasoning model
(GLM-5.1) burns its whole token budget on hidden reasoning and returns a 200 with an
EMPTY / None / whitespace ``message.content``. Downstream that becomes ``json.loads(None)``
(a ``TypeError``) → a broad ``except`` → either a silent fail-open ('neutral', 0.0) that
DROPS a possible real finding, or a fail-CLOSED raise that HOLDS the whole report.

This module is the ONE place that:
  (a) detects empty/None/whitespace content (``is_empty_content``);
  (b) RETRIES the call on empty content (inheriting the proven 4-role transport retry
      posture — see ``semantic_conflict_detector`` empty-content note + the existing
      retries; here the retry is a fresh re-invocation of the injected call);
  (c) captures the raw request/response of EVERY attempt to a trace (and, when a
      run-scoped raw-IO sink is active, to ``<run_dir>/llm_io/`` — the empty-content
      upstream cause is currently INFERENCE; this capture exists to CONFIRM it);
  (d) on persistent empty returns a typed ``JudgeUnavailable`` sentinel — it NEVER
      raises. "VERIFY = LABEL, NEVER HOLD" (operator-locked 2026-06-14): a side-judge
      infra failure may only ADD a disclosed label, never prevent artifact emission.

POSTURE (binding):
  * PURE-ADDITIVE. No production caller is changed by importing this module; callers opt
    in. It NEVER widens a span, never flips ``is_verified``, never makes a failing claim
    pass — it only converts an empty-content judge failure into a disclosed *label*.
  * The LLM call is DEPENDENCY-INJECTED (``call_fn``) so the guard is fully offline-
    testable with a deterministic fake (no network, no model, no spend).
  * NEVER raises for an empty/None result. It DOES re-raise a caller-designated
    "propagate" exception class (e.g. ``BudgetExceededError``) unchanged — a budget cap
    breach is a clean stop signal, not an unadjudicated side-judge call.
  * LAW VI: the retry count is an env-overridable named constant (no magic number).
"""
from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)

# LAW VI — env-overridable retry budget. Default 2 retries (3 total attempts): the
# empty-content collapse is intermittent (a single provider hiccup), so a small bounded
# retry recovers the common case without inflating spend. 0 => one attempt, no retry.
_ENV_RETRIES = "PG_SIDE_JUDGE_EMPTY_RETRIES"
_DEFAULT_RETRIES = 2


def side_judge_empty_retries() -> int:
    """Resolve the empty-content retry budget (LAW VI). Non-int / negative => default."""
    try:
        n = int(os.environ.get(_ENV_RETRIES, "") or _DEFAULT_RETRIES)
    except (TypeError, ValueError):
        return _DEFAULT_RETRIES
    return n if n >= 0 else _DEFAULT_RETRIES


def is_empty_content(content: Any) -> bool:
    """True iff ``content`` is None / not a string / empty / whitespace-only.

    This is the exact predicate the downstream ``json.loads(content)`` chokes on:
    ``json.loads(None)`` raises ``TypeError`` and ``json.loads("")`` /
    ``json.loads("   ")`` raise ``json.JSONDecodeError`` — every one is an
    empty-content collapse, not a real verdict. Kept total (never raises) so it is
    safe to call on any raw provider payload.
    """
    if content is None:
        return True
    if not isinstance(content, str):
        return True
    return content.strip() == ""


@dataclass
class JudgeUnavailable:
    """Typed sentinel: the side judge could not produce non-empty content after retries.

    This is a *value*, not an exception — the whole point (operator-locked 2026-06-14):
    a side-judge infra failure must be LABELABLE, never raisable into a report HOLD. The
    caller converts this into a disclosed gap label (e.g. ``conflict_unscored`` /
    ``credibility_unscored``); it asserts NOTHING about the underlying claim — only that
    the judge could not adjudicate.

    ``attempts`` is the number of calls made; ``reason`` is a short human string;
    ``last_response`` is the final raw provider payload (for the forensic trace).
    """

    reason: str
    attempts: int = 0
    last_response: Any = None


@dataclass
class SideJudgeAttempt:
    """One captured request/response attempt (the in-memory forensic trace row)."""

    call_id: str
    attempt: int
    request: Any
    raw_response: Any
    empty: bool


@dataclass
class SideJudgeOutcome:
    """The guard result: either a parsed ``value`` or a ``JudgeUnavailable`` sentinel.

    ``value`` is the injected ``call_fn``'s return on the FIRST non-empty attempt (the
    caller parses it). ``unavailable`` is set iff every attempt returned empty content.
    ``trace`` is the list of every attempt's captured request/response (always present
    so a test can assert raw IO was captured even on the success path).
    """

    value: Any = None
    unavailable: JudgeUnavailable | None = None
    trace: list = field(default_factory=list)

    @property
    def is_unavailable(self) -> bool:
        return self.unavailable is not None


def call_side_judge_with_guard(
    call_fn: Callable[[], Any],
    *,
    extract_content: Callable[[Any], Any],
    call_type: str,
    role: str | None = None,
    build_request: Callable[[], Any] | None = None,
    propagate: tuple = (),
    retries: int | None = None,
    io_sink: Any = None,
) -> SideJudgeOutcome:
    """Call a side judge with empty-content retry + raw-IO capture + a no-raise sentinel.

    Parameters
    ----------
    call_fn:
        Zero-arg callable that performs ONE side-judge LLM call and returns its RAW
        provider response (the thing ``extract_content`` reads). Injected so the guard is
        offline-testable. May raise a ``propagate`` exception (re-raised unchanged) — any
        OTHER exception is captured as an empty/failed attempt (NEVER re-raised).
    extract_content:
        ``raw_response -> content`` projector (e.g.
        ``lambda r: r["choices"][0]["message"]["content"]``). Run under a guard so a
        malformed shape counts as empty, not a crash.
    call_type / role:
        Forensic tags for the raw-IO sink record.
    build_request:
        Optional zero-arg callable returning the request body to record (for the trace).
        Kept lazy so the caller can capture the exact final body per attempt.
    propagate:
        Exception classes that MUST escape unchanged (e.g. ``BudgetExceededError``).
    retries:
        Override the env retry budget (tests). ``None`` => ``side_judge_empty_retries()``.
    io_sink:
        Optional run-scoped raw-IO sink (``LlmIoSink``). ``None`` => only the active
        ambient sink (``openrouter_client.current_raw_io_sink()``) is used, if any.

    Returns
    -------
    SideJudgeOutcome with EITHER ``value`` (first non-empty response) OR ``unavailable``
    (a ``JudgeUnavailable`` after all attempts returned empty). Never raises except for a
    ``propagate`` class.
    """
    n_retries = side_judge_empty_retries() if retries is None else max(0, int(retries))
    total_attempts = n_retries + 1
    trace: list = []
    last_response: Any = None

    sink = io_sink
    if sink is None:
        try:
            from src.polaris_graph.llm import openrouter_client as _orc  # noqa: PLC0415
            sink = _orc.current_raw_io_sink()
        except Exception:  # noqa: BLE001 — sink discovery must never break the call
            sink = None

    for attempt in range(1, total_attempts + 1):
        request_body: Any = None
        if build_request is not None:
            try:
                request_body = build_request()
            except Exception:  # noqa: BLE001 — request capture must never break the call
                request_body = None
        call_id = uuid.uuid4().hex
        empty = True
        raw_response: Any = None
        try:
            raw_response = call_fn()
        except propagate:  # type: ignore[misc]  # a designated clean-stop signal — re-raise
            raise
        except Exception as exc:  # noqa: BLE001 — a transport/parse failure is an empty attempt
            logger.warning(
                "[side-judge:%s] attempt %d/%d raised (treated as empty): %s",
                call_type, attempt, total_attempts, exc,
            )
            raw_response = {"error": str(exc)}
            empty = True
        else:
            try:
                content = extract_content(raw_response)
            except Exception:  # noqa: BLE001 — malformed shape == empty content
                content = None
            empty = is_empty_content(content)
        last_response = raw_response

        # Capture EVERY attempt's request/response — empty or not — to the forensic trace
        # (and the run-scoped raw-IO sink when active). The empty-content upstream cause is
        # currently INFERENCE; this capture is how we CONFIRM it. Best-effort, never raises.
        trace.append(SideJudgeAttempt(
            call_id=call_id, attempt=attempt, request=request_body,
            raw_response=raw_response, empty=empty,
        ))
        if sink is not None:
            try:
                sink.record(
                    call_id=call_id,
                    call_type=call_type,
                    role=role,
                    request=request_body,
                    raw_response=raw_response,
                    duration_ms=None,
                    status=("ok" if not empty else "empty_content"),
                )
            except Exception:  # noqa: BLE001 — capture must never perturb the call
                pass

        if not empty:
            return SideJudgeOutcome(value=raw_response, unavailable=None, trace=trace)

    # Every attempt returned empty content → a typed sentinel, NEVER a raise.
    logger.warning(
        "[side-judge:%s] persistent empty content after %d attempt(s) -> JudgeUnavailable "
        "(LABEL, never HOLD)", call_type, total_attempts,
    )
    return SideJudgeOutcome(
        value=None,
        unavailable=JudgeUnavailable(
            reason=f"{call_type}: empty content after {total_attempts} attempt(s)",
            attempts=total_attempts,
            last_response=last_response,
        ),
        trace=trace,
    )
