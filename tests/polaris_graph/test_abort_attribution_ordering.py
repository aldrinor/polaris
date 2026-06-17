"""ITEM 3 (I-arch-007 death-forensic, GH #1264): CORRECT abort cause-attribution.

The Q78 death: the binding entailment verifier bricked its shared client → most claims
fail-CLOSED-dropped → the report fell below the verified-section floor. The pipeline labeled
that ``abort_excessive_gap`` (telling the operator to "widen retrieval" — the exactly-wrong
remedy) because the ``abort_excessive_gap`` branch ``return``ed BEFORE the verifier-degraded
guard ran. ITEM 3 HOISTS the judge-error-rate attribution INTO the gap/empty terminal block so a
degraded BINDING verifier aborts with the TRUE cause (``abort_verifier_degraded``).

These tests exercise the PURE attribution pieces (the advisor's guidance: drive the giant
``run_one_query`` is heavy + brittle; test the predicate + selector + ENTRY-GUARD separately):

  * ``judge_error_degraded_from_telemetry`` — the EARLY degraded read off the live per-run
    telemetry counter; mirrors the canonical late read (zero-base delta). Telemetry-None → inert.
  * ``select_gap_abort_status`` — the 3-way priority INSIDE the block (degraded wins over gap wins
    over no-verified).
  * the BLOCK-ENTRY predicate ``not verified_sections or is_excessive_gap(...)`` — the regression
    guard the whole correction hinges on: a degraded verifier with HEALTHY (above-floor) coverage
    must NOT enter the gap block at all (so it reaches the late always-release LABEL-AND-CONTINUE
    path unchanged). This guarantee lives in the ENTRY condition, NOT in the selector — so it is
    tested HERE, separately, exactly as the advisor flagged.

No network, no spend: drives the real entailment-judge telemetry counters via
``_record_judge_outcome`` and the pure sweep helpers.
"""
from __future__ import annotations

import pytest

from dataclasses import dataclass

from scripts.run_honest_sweep_r3 import (
    build_excessive_gap_abort_body,
    build_no_verified_sections_abort_body,
    build_verifier_degraded_abort_body,
    is_excessive_gap,
    judge_error_degraded_from_telemetry,
    max_judge_error_rate,
    select_gap_abort_status,
)
from src.polaris_graph.llm.entailment_judge import (
    _record_judge_outcome,
    begin_run_judge_telemetry,
    reset_judge_telemetry,
)


@pytest.fixture(autouse=True)
def _reset_telemetry():
    reset_judge_telemetry()
    try:
        yield
    finally:
        reset_judge_telemetry()


@pytest.fixture
def _low_cap(monkeypatch):
    """A degraded-trip cap so any non-zero error rate counts as degraded."""
    monkeypatch.setenv("PG_MAX_JUDGE_ERROR_RATE", "0.5")
    assert abs(max_judge_error_rate() - 0.5) < 1e-9


# --------------------------------------------------------------------------------------------
# judge_error_degraded_from_telemetry — the EARLY degraded read (mirrors the canonical late read)
# --------------------------------------------------------------------------------------------


def test_telemetry_degraded_above_cap(_low_cap) -> None:
    """100 judge calls, 90 errored → rate 0.9 > cap 0.5 → degraded True."""
    run_tel = begin_run_judge_telemetry()
    for i in range(100):
        if i < 90:
            _record_judge_outcome("ENTAILED", "judge_error: client has been closed")
        else:
            _record_judge_outcome("ENTAILED", "ok")
    degraded, rate, calls, errors = judge_error_degraded_from_telemetry(run_tel)
    assert calls == 100
    assert errors == 90
    assert abs(rate - 0.9) < 1e-9
    assert degraded is True


def test_telemetry_healthy_below_cap(_low_cap) -> None:
    """100 judge calls, 10 errored → rate 0.1 < cap 0.5 → degraded False."""
    run_tel = begin_run_judge_telemetry()
    for i in range(100):
        if i < 10:
            _record_judge_outcome("ENTAILED", "judge_error: transient")
        else:
            _record_judge_outcome("ENTAILED", "ok")
    degraded, rate, calls, errors = judge_error_degraded_from_telemetry(run_tel)
    assert (calls, errors) == (100, 10)
    assert abs(rate - 0.1) < 1e-9
    assert degraded is False


def test_telemetry_none_is_inert() -> None:
    """Telemetry unavailable (the rare import-failure path) → degraded False, rate 0.0 →
    the EARLY relabel is INERT and today's gap label stands (the late reason-grep fallback
    remains the authority there)."""
    degraded, rate, calls, errors = judge_error_degraded_from_telemetry(None)
    assert degraded is False
    assert rate == 0.0
    assert (calls, errors) == (0, 0)


def test_default_cap_is_inert(monkeypatch) -> None:
    """Unset PG_MAX_JUDGE_ERROR_RATE → default 1.0 → even a 99% error rate is NOT > 1.0 →
    degraded False (byte-identical to today: the gate is inert by default)."""
    monkeypatch.delenv("PG_MAX_JUDGE_ERROR_RATE", raising=False)
    assert abs(max_judge_error_rate() - 1.0) < 1e-9
    run_tel = begin_run_judge_telemetry()
    for i in range(100):
        _record_judge_outcome("ENTAILED", "judge_error: x" if i < 99 else "ok")
    degraded, rate, _, _ = judge_error_degraded_from_telemetry(run_tel)
    assert abs(rate - 0.99) < 1e-9
    assert degraded is False


# --------------------------------------------------------------------------------------------
# select_gap_abort_status — the 3-way priority INSIDE the block
# --------------------------------------------------------------------------------------------


def test_selector_degraded_wins_over_gap() -> None:
    """ITEM 3 core: judge_error_rate>max AND sections<floor → abort_verifier_degraded
    (NOT abort_excessive_gap)."""
    assert (
        select_gap_abort_status(
            has_verified_sections=True, excessive_gap=True, judge_degraded=True,
        )
        == "abort_verifier_degraded"
    )


def test_selector_healthy_gap_is_excessive_gap() -> None:
    """healthy judge + below-floor (some sections verified) → still abort_excessive_gap."""
    assert (
        select_gap_abort_status(
            has_verified_sections=True, excessive_gap=True, judge_degraded=False,
        )
        == "abort_excessive_gap"
    )


def test_selector_no_verified_healthy_is_no_verified_sections() -> None:
    """healthy judge + ZERO verified sections → abort_no_verified_sections."""
    assert (
        select_gap_abort_status(
            has_verified_sections=False, excessive_gap=False, judge_degraded=False,
        )
        == "abort_no_verified_sections"
    )


def test_selector_degraded_wins_even_with_zero_verified() -> None:
    """degraded judge + ZERO verified sections → abort_verifier_degraded (the verifier
    outage is the TRUE cause even when nothing survived)."""
    assert (
        select_gap_abort_status(
            has_verified_sections=False, excessive_gap=False, judge_degraded=True,
        )
        == "abort_verifier_degraded"
    )


# --------------------------------------------------------------------------------------------
# BLOCK-ENTRY predicate — the regression guard (advisor): degraded judge + HEALTHY coverage must
# NOT enter the gap block at all (so it reaches the late LABEL-AND-CONTINUE path unchanged).
# --------------------------------------------------------------------------------------------


def _enters_gap_block(*, verified_count: int, total_sections: int, min_frac: float) -> bool:
    """Faithful mirror of run_one_query's block-entry condition (run_honest_sweep_r3.py):

        verified_sections = filter_verified_sections(multi.sections)   # len == verified_count
        _excessive_gap = bool(verified_sections) and is_excessive_gap(...)
        if not verified_sections or _excessive_gap:   # <-- this predicate

    The degraded-judge attribution lives INSIDE this block; if the block is not entered, the
    run flows to the late verifier-degraded handling (the always-release LABEL-AND-CONTINUE path)
    unchanged. So the regression guard is: a degraded verifier with above-floor coverage must
    return False here."""
    has_verified = verified_count > 0
    excessive_gap = has_verified and is_excessive_gap(verified_count, total_sections, min_frac)
    return (not has_verified) or excessive_gap


def test_entry_guard_degraded_but_above_floor_does_not_enter_block() -> None:
    """REGRESSION GUARD (advisor): a degraded verifier with HEALTHY (above-floor) coverage —
    e.g. 4/5 sections verified at a 0.5 floor — must NOT enter the gap block. If it did, the
    hoisted degraded relabel would TERMINAL-abort a run that today does LABEL-AND-CONTINUE
    through D8 under always-release — a behavior change ITEM 3 forbids. The judge being degraded
    is IRRELEVANT to block entry; only coverage decides entry."""
    assert _enters_gap_block(verified_count=4, total_sections=5, min_frac=0.5) is False


def test_entry_guard_below_floor_enters_block() -> None:
    """Below-floor coverage (1/5 at a 0.5 floor) → enters the gap block (where the degraded
    relabel can then fire)."""
    assert _enters_gap_block(verified_count=1, total_sections=5, min_frac=0.5) is True


def test_entry_guard_zero_verified_enters_block() -> None:
    """Zero verified sections → enters the block regardless of the floor."""
    assert _enters_gap_block(verified_count=0, total_sections=5, min_frac=0.5) is True


def test_entry_guard_floor_disabled_above_zero_does_not_enter() -> None:
    """Floor explicitly disabled (min_frac=0) + at least one verified section → not excessive
    gap → does not enter the block (byte-identical to the floor-off behavior)."""
    assert _enters_gap_block(verified_count=1, total_sections=5, min_frac=0.0) is False


# --------------------------------------------------------------------------------------------
# END-TO-END (predicate composition): degraded + below-floor → enters AND relabels to degraded;
# healthy + below-floor → enters AND stays excessive_gap; degraded + above-floor → never enters.
# --------------------------------------------------------------------------------------------


def test_compose_degraded_below_floor_yields_verifier_degraded(_low_cap) -> None:
    run_tel = begin_run_judge_telemetry()
    for i in range(50):
        _record_judge_outcome("ENTAILED", "judge_error: closed" if i < 45 else "ok")
    degraded, _, _, _ = judge_error_degraded_from_telemetry(run_tel)
    assert _enters_gap_block(verified_count=1, total_sections=5, min_frac=0.5) is True
    assert (
        select_gap_abort_status(
            has_verified_sections=True, excessive_gap=True, judge_degraded=degraded,
        )
        == "abort_verifier_degraded"
    )


def test_compose_healthy_below_floor_yields_excessive_gap(_low_cap) -> None:
    run_tel = begin_run_judge_telemetry()
    for _ in range(50):
        _record_judge_outcome("ENTAILED", "ok")
    degraded, _, _, _ = judge_error_degraded_from_telemetry(run_tel)
    assert degraded is False
    assert _enters_gap_block(verified_count=1, total_sections=5, min_frac=0.5) is True
    assert (
        select_gap_abort_status(
            has_verified_sections=True, excessive_gap=True, judge_degraded=degraded,
        )
        == "abort_excessive_gap"
    )


def test_compose_degraded_above_floor_never_enters(_low_cap) -> None:
    run_tel = begin_run_judge_telemetry()
    for i in range(50):
        _record_judge_outcome("ENTAILED", "judge_error: closed" if i < 45 else "ok")
    degraded, _, _, _ = judge_error_degraded_from_telemetry(run_tel)
    assert degraded is True  # the verifier IS degraded
    # ...but coverage is healthy (4/5 above the 0.5 floor) → the block is never entered, so the
    # hoisted relabel cannot fire; the run reaches the late always-release LABEL path unchanged.
    assert _enters_gap_block(verified_count=4, total_sections=5, min_frac=0.5) is False


# --------------------------------------------------------------------------------------------
# report.md BODY framing — the operator-facing surface (the literal Q78 bug ITEM 3 kills): the
# verifier-degraded body must NOT say "widen retrieval" and must frame a VERIFIER outage.
# --------------------------------------------------------------------------------------------


@dataclass
class _FakeSection:
    title: str
    sentences_verified: int = 0
    sentences_dropped: int = 0
    is_gap_stub: bool = False
    regen_attempted: bool = False
    error: object = None


def test_verifier_degraded_body_does_not_say_widen_retrieval() -> None:
    """The whole point of ITEM 3: a degraded-verifier abort's report.md must NOT tell the operator
    to broaden the evidence base (the exactly-wrong remedy for a verifier outage)."""
    body = build_verifier_degraded_abort_body(
        "does X help Y?",
        [_FakeSection("Efficacy", sentences_verified=1), _FakeSection("Safety")],
        verified_count=1,
        judge_error_rate=0.95,
        judge_errors=190,
        judge_calls=200,
        judge_error_cap=0.5,
    )
    low = body.lower()
    # the affirmative "widen retrieval" remedy must be absent (the gap body's exact wrong advice)
    assert "widen retrieval so" not in low
    assert "broaden the evidence base" not in low
    # it MUST frame the TRUE cause: a degraded binding verifier / verifier outage
    assert "verifier" in low
    assert "do not widen retrieval" in low
    assert "190/200" in body  # the judge-error denominator the operator needs
    # the fail-closed sentinel must NOT be advised to relax
    assert "fail-closed" in low or "fail closed" in low


def test_gap_body_still_says_widen_retrieval_unchanged() -> None:
    """Sanity / no-regression: the genuine coverage-gap body (healthy verifier) is UNCHANGED and
    still advises widening retrieval — proving the verifier-degraded body is a NEW distinct
    artifact, not a global edit to the gap body."""
    gap = build_excessive_gap_abort_body(
        "does X help Y?",
        [_FakeSection("Efficacy", sentences_verified=1), _FakeSection("Safety")],
        1,
        0.5,
    )
    assert "Widen retrieval" in gap
    none_verified = build_no_verified_sections_abort_body(
        "does X help Y?",
        [_FakeSection("Efficacy"), _FakeSection("Safety")],
    )
    assert "Widen retrieval" in none_verified
