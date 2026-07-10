"""Phase 0b (I-meta-005, gap-#18) smoke tests for the verification-mode router.

Covers the three grounded-prose deltas gated on PG_VERIFICATION_MODE
{off, shadow, enforce} in
``src.polaris_graph.generator.provenance_generator.verify_sentence_provenance``:

  Delta 1 — bounded local-window rescue of the content-word floor.
  Delta 2 — non-numeric NEUTRAL local content-window re-judge.
  Delta 3 — fail-closed on the judge-error fail-OPEN sentinel.

Two orthogonal env vars drive the verifier:
  PG_STRICT_VERIFY_ENTAILMENT {off,warn,enforce} — whether the judge runs.
  PG_VERIFICATION_MODE        {off,shadow,enforce} — whether the deltas fire.

The entailment judge is injected by monkeypatching
``src.polaris_graph.clinical_generator.strict_verify._get_judge`` (the verifier
imports it lazily from there). The injected judge is a PLAIN class with a
``.judge(sentence, span) -> (verdict, reason)`` method and a call counter — NOT
unittest.mock (CLAUDE.md §9.4 bans mock in src/-adjacent verifier paths). The
evidence pools are real ``dict`` rows (no mocked evidence DB).

The two non-negotiable gates:
  * S0b-1 OFF byte-identity wall — off mode == pre-0b behavior, exactly.
  * S0b-5 anti-laundering — a fabrication whose words are scattered >400 chars
    apart MUST stay dropped under enforce (clinical-safety lethal gate).
"""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest

# Ensure repo root on sys.path for the S0b-7 reproduction harness import.
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.polaris_graph.generator import provenance_generator as pg
from src.polaris_graph.clinical_generator import strict_verify as sv


# ─────────────────────────────────────────────────────────────────────────────
# Fakes (plain classes, no unittest.mock — §9.4)
# ─────────────────────────────────────────────────────────────────────────────


class AllEntailJudge:
    """Judge that ENTAILS every span. Used where the judge layer must not block
    the delta under test (content-floor / numeric paths)."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def judge(self, sentence: str, span: str) -> tuple[str, str]:
        self.calls.append((sentence, span))
        return "ENTAILED", "ok"


class MarkerJudge:
    """Judge that ENTAILS iff a marker substring appears in the judged span.
    Branches on the span argument so the narrow combined_span can return NEUTRAL
    while a wider local content window returns ENTAILED (Delta 2 probe)."""

    def __init__(self, marker: str) -> None:
        self.marker = marker.lower()
        self.calls: list[tuple[str, str]] = []

    def judge(self, sentence: str, span: str) -> tuple[str, str]:
        self.calls.append((sentence, span))
        if self.marker in span.lower():
            return "ENTAILED", "window grounds the predicate"
        return "NEUTRAL", "narrow span lacks the predicate"


class JudgeErrorSentinel:
    """Judge that fails OPEN with the real sentinel shape
    ((ENTAILED, "judge_error: ...")) — Delta 3 probe."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def judge(self, sentence: str, span: str) -> tuple[str, str]:
        self.calls.append((sentence, span))
        return "ENTAILED", "judge_error: ConnectError"


class AllNeutralJudge:
    """Judge that returns NEUTRAL for every span. Used to prove the bind bites:
    Delta 1 proposes a window, but if the bounded-window re-judge is NEUTRAL the
    sentence stays dropped (no blanket pass)."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def judge(self, sentence: str, span: str) -> tuple[str, str]:
        self.calls.append((sentence, span))
        return "NEUTRAL", "not entailed"


def _install_judge(monkeypatch: pytest.MonkeyPatch, judge: object) -> None:
    """Patch the lazily-imported judge factory the verifier reaches at runtime."""
    monkeypatch.setattr(sv, "_get_judge", lambda: judge)


def _tok(ev_id: str, start: int, end: int) -> str:
    return f"[#ev:{ev_id}:{start}-{end}]"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch):
    """Each test starts from a known env: deltas OFF, entailment OFF, default
    content-overlap floor. Tests opt in to specific modes explicitly."""
    monkeypatch.delenv("PG_VERIFICATION_MODE", raising=False)
    monkeypatch.delenv("PG_STRICT_VERIFY_ENTAILMENT", raising=False)
    monkeypatch.delenv("PG_PROVENANCE_MIN_CONTENT_OVERLAP", raising=False)
    # I-deepfix-001 item G: clear so the judge_error DEFAULT (FAIL CLOSED) is deterministic
    # regardless of ambient env; the one test that needs the advisory soft-keep opts in with "1".
    monkeypatch.delenv("PG_ENTAILMENT_JUDGE_ERROR_ADVISORY", raising=False)
    yield


# ─────────────────────────────────────────────────────────────────────────────
# S0b-1 — OFF byte-identity wall (the regression wall, MUST NOT be relaxed)
# ─────────────────────────────────────────────────────────────────────────────


def test_s0b1_off_byte_identity_grounded_pass(monkeypatch):
    """A fully grounded numeric sentence passes under off — and the new
    judge_error field is its inert default False. The production default
    entailment mode is 'enforce' (strict_verify._DEFAULT_MODE), so the judge
    DOES run on a passing sentence; pin a deterministic entailing judge so the
    regression wall does not depend on ambient state or a live judge call."""
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    _install_judge(monkeypatch, AllEntailJudge())
    span = "Tirzepatide reduced HbA1c by 2.1 percent versus placebo in the trial."
    pool = {"ev1": {"direct_quote": span}}
    s = f"Tirzepatide reduced HbA1c by 2.1 percent [#ev:ev1:0-{len(span)}]."
    res = pg.verify_sentence_provenance(s, pool)
    assert res.is_verified is True
    assert res.failure_reasons == []
    assert res.judge_error is False  # additive field inert in off mode


@pytest.mark.skip(reason=(
    "Writer-side content-word-overlap floor + the Phase-0b Delta-1 full-row rescue were REMOVED per 2026-07-10 UNFREEZE (fix 2, GH I-arch-s5-001): the no_content_word_overlap_any_cited_span gate forced near-verbatim copying and is deleted, so the Delta-1/shadow/enforce rescue machinery it gated no longer exists. The NLI entailment judge is now the semantic bar (live-judge surface, not offline)."
))
def test_s0b1_off_byte_identity_content_floor_miss(monkeypatch):
    """Narrow byte-range missing content words drops with the EXACT pre-0b
    failure reason under off."""
    row = (
        "Background note. The carbon levy drove decarbonization and "
        "structural change in regional industry."
    )
    row_b = (
        "Grid analysis: the provincial supply is dominated by "
        "hydroelectric power generation."
    )
    pool = {"a": {"direct_quote": row}, "b": {"direct_quote": row_b}}
    s = (
        "Decarbonization reflects structural change in the regional industry "
        "[#ev:a:0-16][#ev:b:0-15]."
    )
    res = pg.verify_sentence_provenance(s, pool)
    assert res.is_verified is False
    assert any(
        r.startswith("no_content_word_overlap_any_cited_span:")
        for r in res.failure_reasons
    )


def test_s0b1_off_byte_identity_numeric_miss(monkeypatch):
    """A decimal absent from any cited span drops under off."""
    span = "The cohort enrolled adults with type 2 diabetes over twelve months."
    pool = {"ev1": {"direct_quote": span}}
    s = f"The drug cut events by 37.4 percent in the cohort [#ev:ev1:0-{len(span)}]."
    res = pg.verify_sentence_provenance(s, pool)
    assert res.is_verified is False
    assert any(
        r.startswith("number_not_in_any_cited_span:") for r in res.failure_reasons
    )


def test_s0b1_off_byte_identity_trial_name_miss(monkeypatch):
    """A named-trial mismatch drops under off (M-25a)."""
    span = (
        "Tirzepatide after intensive lifestyle intervention: the SURMOUNT-3 "
        "phase 3 trial reported weight loss outcomes."
    )
    pool = {"ev1": {"direct_quote": span}}
    s = f"SURMOUNT-1 reported sustained weight loss [#ev:ev1:0-{len(span)}]."
    res = pg.verify_sentence_provenance(s, pool)
    assert res.is_verified is False
    assert any(r.startswith("trial_name_mismatch:") for r in res.failure_reasons)


@pytest.mark.skip(reason=(
    "Writer-side content-word-overlap floor + the Phase-0b Delta-1 full-row rescue were REMOVED per 2026-07-10 UNFREEZE (fix 2, GH I-arch-s5-001): the no_content_word_overlap_any_cited_span gate forced near-verbatim copying and is deleted, so the Delta-1/shadow/enforce rescue machinery it gated no longer exists. The NLI entailment judge is now the semantic bar (live-judge surface, not offline)."
))
def test_s0b1_off_strict_wall_exact_reasons(monkeypatch):
    """Strict byte-identity wall (Codex diff-gate P2): off-mode failure_reasons
    pinned EXACTLY for a deterministic content-floor-miss case, so ANY added
    off-mode failure reason (not just the expected one) is caught — prefix
    presence alone would miss an extra reason."""
    res = pg.verify_sentence_provenance(_S0B2_SENTENCE, _S0B2_POOL)
    assert res.is_verified is False
    assert res.failure_reasons == [
        "no_content_word_overlap_any_cited_span:a,b:"
        "sentence_words=['change', 'decarbonization', 'industry', "
        "'reflects', 'regional']"
    ]
    assert res.judge_error is False


# ─────────────────────────────────────────────────────────────────────────────
# S0b-2 — Delta 1: bounded content-window rescue of the content floor
# ─────────────────────────────────────────────────────────────────────────────

# Fixtures shared across the three S0b-2 modes (the gap-#18 wrongful drop).
_S0B2_ROW_A = (
    "Background note. The carbon levy drove decarbonization and "
    "structural change in regional industry."
)
_S0B2_ROW_B = (
    "Grid analysis: the provincial supply is dominated by "
    "hydroelectric power generation."
)
_S0B2_POOL = {"a": {"direct_quote": _S0B2_ROW_A}, "b": {"direct_quote": _S0B2_ROW_B}}
_S0B2_SENTENCE = (
    "Decarbonization reflects structural change in the regional industry "
    "[#ev:a:0-16][#ev:b:0-15]."
)


@pytest.mark.skip(reason=(
    "Writer-side content-word-overlap floor + the Phase-0b Delta-1 full-row rescue were REMOVED per 2026-07-10 UNFREEZE (fix 2, GH I-arch-s5-001): the no_content_word_overlap_any_cited_span gate forced near-verbatim copying and is deleted, so the Delta-1/shadow/enforce rescue machinery it gated no longer exists. The NLI entailment judge is now the semantic bar (live-judge surface, not offline)."
))
def test_s0b2_delta1_off_dropped(monkeypatch):
    res = pg.verify_sentence_provenance(_S0B2_SENTENCE, _S0B2_POOL)
    assert res.is_verified is False
    assert any(
        r.startswith("no_content_word_overlap_any_cited_span:")
        for r in res.failure_reasons
    )


def test_s0b2_delta1_enforce_rescued(monkeypatch):
    """Delta 1 PROPOSES (clears the floor); the downstream Delta-2 window BIND is
    what actually passes it. A DISCRIMINATING judge (NEUTRAL on the narrow
    combined_span, ENTAILED only when the wider window text appears) is required
    so the bind is genuinely exercised — not a narrow-span pass (architect P2)."""
    monkeypatch.setenv("PG_VERIFICATION_MODE", "enforce")
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    judge = MarkerJudge("structural change")  # absent from narrow spans, present in row_a
    _install_judge(monkeypatch, judge)
    res = pg.verify_sentence_provenance(_S0B2_SENTENCE, _S0B2_POOL)
    assert res.is_verified is True
    assert not any(
        r.startswith("no_content_word_overlap_any_cited_span:")
        for r in res.failure_reasons
    )
    # Bind exercised: narrow combined_span judged NEUTRAL, then the bounded
    # window judged ENTAILED -> at least two judge calls.
    assert len(judge.calls) >= 2


@pytest.mark.skip(reason=(
    "Writer-side content-word-overlap floor + the Phase-0b Delta-1 full-row rescue were REMOVED per 2026-07-10 UNFREEZE (fix 2, GH I-arch-s5-001): the no_content_word_overlap_any_cited_span gate forced near-verbatim copying and is deleted, so the Delta-1/shadow/enforce rescue machinery it gated no longer exists. The NLI entailment judge is now the semantic bar (live-judge surface, not offline)."
))
def test_s0b2_delta1_shadow_output_eq_off_and_logs(monkeypatch, caplog):
    """Shadow: entailment active so the propose-branch runs and logs, but output
    == off (still dropped) AND the entailment judge is never reached (the
    content-floor failure short-circuits the judge block) — spend-neutral."""
    monkeypatch.setenv("PG_VERIFICATION_MODE", "shadow")
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    judge = MarkerJudge("structural change")
    _install_judge(monkeypatch, judge)
    import logging

    with caplog.at_level(logging.WARNING):
        res = pg.verify_sentence_provenance(_S0B2_SENTENCE, _S0B2_POOL)
    # Output identical to off: still dropped on the same reason.
    assert res.is_verified is False
    assert any(
        r.startswith("no_content_word_overlap_any_cited_span:")
        for r in res.failure_reasons
    )
    assert any("SHADOW_would_propose" in rec.getMessage() for rec in caplog.records)
    # Spend-neutral: the content-floor failure means the judge block never runs.
    assert len(judge.calls) == 0


@pytest.mark.skip(reason=(
    "Writer-side content-word-overlap floor + the Phase-0b Delta-1 full-row rescue were REMOVED per 2026-07-10 UNFREEZE (fix 2, GH I-arch-s5-001): the no_content_word_overlap_any_cited_span gate forced near-verbatim copying and is deleted, so the Delta-1/shadow/enforce rescue machinery it gated no longer exists. The NLI entailment judge is now the semantic bar (live-judge surface, not offline)."
))
def test_s0b8_delta1_entailment_off_no_launder(monkeypatch):
    """Architect P1 (the proven hole): PG_VERIFICATION_MODE=enforce AND
    PG_STRICT_VERIFY_ENTAILMENT=off must NOT let Delta 1 launder a content-floor
    drop into a pass with zero entailment backstop. The floor-clear is gated on
    the judge being ACTIVE; with entailment off, Delta 1 does not rescue and the
    judge is never consulted. An AllEntailJudge is installed so that ANY
    erroneous consult would PASS the sentence and fail this test loudly."""
    monkeypatch.setenv("PG_VERIFICATION_MODE", "enforce")
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "off")
    judge = AllEntailJudge()
    _install_judge(monkeypatch, judge)
    res = pg.verify_sentence_provenance(_S0B2_SENTENCE, _S0B2_POOL)
    assert res.is_verified is False, (
        "ENTAILMENT-OFF LAUNDER REGRESSION: Delta 1 rescued a content-floor drop "
        "with no entailment backstop (PG_STRICT_VERIFY_ENTAILMENT=off)."
    )
    assert any(
        r.startswith("no_content_word_overlap_any_cited_span:")
        for r in res.failure_reasons
    )
    assert len(judge.calls) == 0  # judge never consulted under entailment off


def test_s0b9_delta1_window_not_entailed_stays_dropped(monkeypatch):
    """Brief companion (no blanket pass): Delta 1 proposes a window but the
    downstream bounded-window BIND returns NEUTRAL -> fail-closed -> drop. Proves
    the floor-clear alone is never a pass; the entailment bind bites."""
    monkeypatch.setenv("PG_VERIFICATION_MODE", "enforce")
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    judge = AllNeutralJudge()
    _install_judge(monkeypatch, judge)
    res = pg.verify_sentence_provenance(_S0B2_SENTENCE, _S0B2_POOL)
    assert res.is_verified is False
    assert any(r.startswith("entailment_failed:") for r in res.failure_reasons)
    # The bind was attempted: narrow span NEUTRAL then the bounded window NEUTRAL.
    assert len(judge.calls) >= 2


@pytest.mark.skip(reason=(
    "Writer-side content-word-overlap floor + the Phase-0b Delta-1 full-row rescue were REMOVED per 2026-07-10 UNFREEZE (fix 2, GH I-arch-s5-001): the no_content_word_overlap_any_cited_span gate forced near-verbatim copying and is deleted, so the Delta-1/shadow/enforce rescue machinery it gated no longer exists. The NLI entailment judge is now the semantic bar (live-judge surface, not offline)."
))
def test_s0b10_delta1_warn_mode_no_launder(monkeypatch):
    """Codex diff-gate P1 (the proven warn hole): PG_VERIFICATION_MODE=enforce +
    PG_STRICT_VERIFY_ENTAILMENT=warn. warn runs the judge but NEVER drops on
    NEUTRAL/CONTRADICTED (log-only), so a content-floor clear under warn would be
    an UNBACKED rescue. Delta 1 must NOT propose under warn — the content-floor
    drop stays and the judge is never consulted. An all-NEUTRAL judge is used:
    if Delta 1 erroneously cleared, the warn bind would not drop and the sentence
    would launder through."""
    monkeypatch.setenv("PG_VERIFICATION_MODE", "enforce")
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "warn")
    judge = AllNeutralJudge()
    _install_judge(monkeypatch, judge)
    res = pg.verify_sentence_provenance(_S0B2_SENTENCE, _S0B2_POOL)
    assert res.is_verified is False, (
        "WARN-MODE LAUNDER REGRESSION: Delta 1 cleared the content-floor under "
        "entailment warn, where the downstream bind never drops."
    )
    assert any(
        r.startswith("no_content_word_overlap_any_cited_span:")
        for r in res.failure_reasons
    )
    assert len(judge.calls) == 0  # content-floor drop short-circuits the judge block


# ─────────────────────────────────────────────────────────────────────────────
# S0b-3 — Delta 2: non-numeric NEUTRAL local content-window re-judge
# ─────────────────────────────────────────────────────────────────────────────

# Full row: narrow leading byte-range passes the content floor (>=2 words) but
# the judge returns NEUTRAL on it; the wider local content window contains the
# predicate marker 'sleep quality' so the re-judge ENTAILS it.
_S0B3_ROW = (
    "Patients receiving semaglutide reported improved sleep quality and "
    "reduced fatigue over the study period in this cohort."
)
_S0B3_NARROW_END = 48
_S0B3_POOL = {"a": {"direct_quote": _S0B3_ROW}}
_S0B3_SENTENCE = (
    f"Semaglutide patients reported improved sleep quality "
    f"[#ev:a:0-{_S0B3_NARROW_END}]."
)


def _run_s0b3(monkeypatch, mode: str | None):
    if mode is not None:
        monkeypatch.setenv("PG_VERIFICATION_MODE", mode)
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    judge = MarkerJudge("sleep quality")
    _install_judge(monkeypatch, judge)
    res = pg.verify_sentence_provenance(_S0B3_SENTENCE, _S0B3_POOL)
    return res, judge


def test_s0b3_delta2_off_dropped(monkeypatch):
    res, judge = _run_s0b3(monkeypatch, None)
    assert res.is_verified is False
    assert any(r.startswith("entailment_failed:") for r in res.failure_reasons)
    assert len(judge.calls) == 1  # only the narrow combined_span is judged


def test_s0b3_delta2_enforce_rescued(monkeypatch):
    res, judge = _run_s0b3(monkeypatch, "enforce")
    assert res.is_verified is True
    assert res.failure_reasons == []
    assert len(judge.calls) == 2  # narrow span NEUTRAL, then local window ENTAILED


def test_s0b3_delta2_shadow_spend_neutral(monkeypatch):
    """Shadow output == off AND makes NO extra judge call (spend-neutral)."""
    res_off, judge_off = _run_s0b3(monkeypatch, None)
    res_shadow, judge_shadow = _run_s0b3(monkeypatch, "shadow")
    assert res_shadow.is_verified is res_off.is_verified is False
    assert any(r.startswith("entailment_failed:") for r in res_shadow.failure_reasons)
    # The lethal spend-neutrality assertion: shadow judge-call count == off.
    assert len(judge_shadow.calls) == len(judge_off.calls) == 1


# ─────────────────────────────────────────────────────────────────────────────
# S0b-4 — Delta 3: judge-error fail-OPEN sentinel
# ─────────────────────────────────────────────────────────────────────────────

_S0B4_SPAN = "Reduced industrial emissions reflect the hydroelectric power supply mix."
_S0B4_POOL = {"a": {"direct_quote": _S0B4_SPAN}}
_S0B4_SENTENCE = (
    f"Reduced industrial emissions reflect the hydroelectric power supply "
    f"[#ev:a:0-{len(_S0B4_SPAN)}]."
)


def test_s0b4_delta3_judge_error_legacy_hard_drop_with_advisory_off(monkeypatch):
    # I-ready-002 (#1071) Codex iter-1 P1: judge_error fail-closed is keyed on the ENTAILMENT mode
    # (PG_STRICT_VERIFY_ENTAILMENT), DECOUPLED from PG_VERIFICATION_MODE (which ALSO enables the Phase 0b
    # rescue WIDENING). With entailment=enforce a judge_error fails closed REGARDLESS of
    # PG_VERIFICATION_MODE — previously off-verification-mode left the fail-open ENTAILED in place.
    # I-deepfix-001 item G: judge_error now FAILS CLOSED by default; this test pins the explicit
    # PG_ENTAILMENT_JUDGE_ERROR_ADVISORY=0 to assert that value also fails closed (identical to the
    # default). The companion test above pins the unset default fail-closed; a third pins the "1" opt-in.
    monkeypatch.delenv("PG_VERIFICATION_MODE", raising=False)  # verification mode OFF (no rescue)
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    monkeypatch.setenv("PG_ENTAILMENT_JUDGE_ERROR_ADVISORY", "0")  # legacy hard-drop
    _install_judge(monkeypatch, JudgeErrorSentinel())
    res = pg.verify_sentence_provenance(_S0B4_SENTENCE, _S0B4_POOL)
    assert res.is_verified is False  # legacy hard-drop under the kill-switch
    assert res.judge_error is True
    assert any(
        r.startswith("entailment_judge_error_fail_closed:")
        for r in res.failure_reasons
    )


def test_s0b4_delta3_judge_error_fails_closed_by_default(monkeypatch):
    # I-deepfix-001 item G (Codex P0): by DEFAULT (PG_ENTAILMENT_JUDGE_ERROR_ADVISORY unset) a
    # TRANSPORT judge_error under entailment=enforce now FAILS CLOSED — the unverified sentence is
    # DROPPED (is_verified=False, entailment_judge_error_fail_closed reason), never kept-as-advisory.
    # This is the item-G FLIP: keeping an unverified claim on a judge fault (429/blank/transport) was a
    # fail-OPEN on the faithfulness engine's only hard gate. Fail-closed aligns the entailment leg with
    # strict_verify, which already fails closed on a judge_error by default. The durable judge_error=True
    # marker still records that the fault occurred. RED before item G (the old default advisory-KEPT the
    # sentence, is_verified=True); GREEN after (dropped).
    monkeypatch.delenv("PG_VERIFICATION_MODE", raising=False)
    monkeypatch.delenv("PG_ENTAILMENT_JUDGE_ERROR_ADVISORY", raising=False)  # DEFAULT = fail closed
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    _install_judge(monkeypatch, JudgeErrorSentinel())
    res = pg.verify_sentence_provenance(_S0B4_SENTENCE, _S0B4_POOL)
    assert res.is_verified is False  # DEFAULT fail-closed: the unverifiable claim is dropped
    assert res.judge_error is True  # the durable machine-readable marker stays set
    assert any(
        r.startswith("entailment_judge_error_fail_closed:")
        for r in res.failure_reasons
    )
    # NOT advisory-kept: the default path emits no soft-warning keep label
    assert not any(
        str(w).startswith("entailment_unverified_judge_error")
        for w in res.soft_warnings
    )


def test_s0b4_delta3_judge_error_advisory_keep_is_opt_in(monkeypatch):
    # I-deepfix-001 item G: the advisory soft-KEEP survives ONLY behind the explicit opt-in
    # PG_ENTAILMENT_JUDGE_ERROR_ADVISORY=1 (never the default). With the opt-in, a TRANSPORT
    # judge_error under entailment=enforce is demoted from a hard DROP to an ADVISORY soft-warning: the
    # sentence is KEPT on the deterministic (a)-(e) checks (is_verified=True), carries the durable
    # judge_error=True marker, and is LABELLED entailment_unverified_judge_error in soft_warnings — so a
    # downstream count/render layer (the credibility-pass tier classifier) can refuse to treat it as
    # genuine entailment-verified support (the no-leak guarantee lives THERE, not here). This is NOT a
    # faithfulness relaxation of a genuine NEUTRAL/CONTRADICTED verdict — only the transport sentinel is
    # demoted; genuine entailment failures still DROP (asserted by the enforce-drop tests below).
    monkeypatch.delenv("PG_VERIFICATION_MODE", raising=False)
    monkeypatch.setenv("PG_ENTAILMENT_JUDGE_ERROR_ADVISORY", "1")  # explicit opt-in to advisory-keep
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    _install_judge(monkeypatch, JudgeErrorSentinel())
    res = pg.verify_sentence_provenance(_S0B4_SENTENCE, _S0B4_POOL)
    assert res.is_verified is True  # opt-in advisory-keep: kept on the deterministic (a)-(e) checks
    assert res.judge_error is True  # the durable machine-readable marker stays set
    # NOT hard-dropped under the opt-in: no fail-closed failure reason
    assert not any(
        r.startswith("entailment_judge_error_fail_closed:")
        for r in res.failure_reasons
    )
    # LABELLED for the downstream count/render layer
    assert any(
        str(w).startswith("entailment_unverified_judge_error")
        for w in res.soft_warnings
    )


class _NeutralThenJudgeErrorJudge:
    """First call (whole-quote) returns a GENUINE NEUTRAL; the second call (the
    local-window rescue) returns the transport judge_error sentinel. Proves a genuine
    entailment failure followed by a rescue-call judge_error must FAIL CLOSED."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def judge(self, sentence: str, span: str) -> tuple[str, str]:
        self.calls.append((sentence, span))
        if len(self.calls) == 1:
            return "NEUTRAL", "genuine non-entailment on the whole quote"
        return "ENTAILED", "judge_error: ConnectError"


# A NUMERIC fixture so the local-window rescue judge fires WITHOUT needing
# PG_VERIFICATION_MODE (the numeric window is built whenever the sentence has a decimal).
_S0B4_NUM_SPAN = "The cohort showed a 2.1 percent reduction in industrial emissions."
_S0B4_NUM_POOL = {"a": {"direct_quote": _S0B4_NUM_SPAN}}
_S0B4_NUM_SENTENCE = (
    f"The cohort showed a 2.1 percent reduction in industrial emissions "
    f"[#ev:a:0-{len(_S0B4_NUM_SPAN)}]."
)


def test_s0b4_rescue_judge_error_after_genuine_neutral_fails_closed(monkeypatch):
    # I-arch-010 FIX-1 (Codex re-gate P1): a genuine NEUTRAL/CONTRADICTED first verdict that enters
    # local-window rescue, where the RESCUE judge then ERRORS, must FAIL CLOSED — NOT advisory-keep.
    # Advisory-keeping would LAUNDER a genuine entailment failure into is_verified=True. The advisory
    # default applies ONLY to a PURE transport error (the FIRST judge call, no genuine verdict before),
    # never to a rescue error that failed to overturn a genuine failure.
    monkeypatch.delenv("PG_VERIFICATION_MODE", raising=False)
    monkeypatch.delenv("PG_ENTAILMENT_JUDGE_ERROR_ADVISORY", raising=False)  # default (fail closed)
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    judge = _NeutralThenJudgeErrorJudge()
    _install_judge(monkeypatch, judge)
    res = pg.verify_sentence_provenance(_S0B4_NUM_SENTENCE, _S0B4_NUM_POOL)
    assert len(judge.calls) == 2, "the genuine NEUTRAL must trigger the local-window rescue judge call"
    assert res.is_verified is False, (
        "a genuine NEUTRAL + rescue judge_error MUST fail closed, not advisory-keep "
        f"(failure_reasons={res.failure_reasons})"
    )
    assert any(
        "rescue_judge_error_on_genuine" in r for r in res.failure_reasons
    ), f"expected the rescue-judge-error fail-closed reason; got {res.failure_reasons}"


def test_s0b4_delta3_warn_entailment_logs_does_not_drop(monkeypatch, caplog):
    # I-ready-002 (#1071): the log-only judge_error path is now PG_STRICT_VERIFY_ENTAILMENT=warn
    # (was PG_VERIFICATION_MODE=shadow). warn logs "would_fail_closed" but does NOT drop the sentence.
    monkeypatch.delenv("PG_VERIFICATION_MODE", raising=False)
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "warn")
    _install_judge(monkeypatch, JudgeErrorSentinel())
    import logging

    with caplog.at_level(logging.WARNING):
        res = pg.verify_sentence_provenance(_S0B4_SENTENCE, _S0B4_POOL)
    assert res.is_verified is True
    assert res.judge_error is True
    assert any(
        "would_fail_closed_on_judge_error" in rec.getMessage()
        for rec in caplog.records
    )


def test_s0b4_delta3_enforce_fails_closed(monkeypatch):
    # I-arch-010 FIX-1: pin the kill-switch so this legacy hard-drop assertion (judge_error +
    # verification-mode-enforce) stays byte-identical under the new default-advisory behavior.
    monkeypatch.setenv("PG_VERIFICATION_MODE", "enforce")
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    monkeypatch.setenv("PG_ENTAILMENT_JUDGE_ERROR_ADVISORY", "0")  # legacy hard-drop
    _install_judge(monkeypatch, JudgeErrorSentinel())
    res = pg.verify_sentence_provenance(_S0B4_SENTENCE, _S0B4_POOL)
    assert res.is_verified is False
    assert res.judge_error is True
    assert any(
        r.startswith("entailment_judge_error_fail_closed:")
        for r in res.failure_reasons
    )


# ─────────────────────────────────────────────────────────────────────────────
# S0b-5 — ANTI-LAUNDERING (LETHAL): scattered fabrication must stay dropped
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.skip(reason=(
    "Writer-side content-word-overlap floor + the Phase-0b Delta-1 full-row rescue were REMOVED per 2026-07-10 UNFREEZE (fix 2, GH I-arch-s5-001): the no_content_word_overlap_any_cited_span gate forced near-verbatim copying and is deleted, so the Delta-1/shadow/enforce rescue machinery it gated no longer exists. The NLI entailment judge is now the semantic bar (live-judge surface, not offline)."
))
def test_s0b5_anti_laundering_scattered_stays_dropped(monkeypatch):
    """A fabrication whose two content words are placed >400 chars apart in the
    cited row MUST NOT be rescued under enforce. This is the clinical-safety
    gate — a rescue that passes this case is a regression and MUST fail."""
    filler = "x" * 500
    row = "decarbonization " + filler + " hydroelectric"
    pool = {"a": {"direct_quote": row}}
    # Narrow span 0-5 misses both whole content words (no word-boundary match).
    s = "Decarbonization stems from hydroelectric interplay [#ev:a:0-5]."
    monkeypatch.setenv("PG_VERIFICATION_MODE", "enforce")
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    _install_judge(monkeypatch, AllEntailJudge())
    res = pg.verify_sentence_provenance(s, pool)
    assert res.is_verified is False, (
        "ANTI-LAUNDERING REGRESSION: scattered (>400-char) content words were "
        "rescued under enforce — the bounded window must not launder fabrication."
    )
    assert any(
        r.startswith("no_content_word_overlap_any_cited_span:")
        for r in res.failure_reasons
    )


# ─────────────────────────────────────────────────────────────────────────────
# S0b-6 — bounded-window unit tests for _find_local_content_window
# ─────────────────────────────────────────────────────────────────────────────


def test_s0b6_finder_none_below_min_words():
    # Only one of the needed content words present -> below min_content_overlap.
    assert (
        pg._find_local_content_window(
            {"decarbonization"}, "decarbonization power generation", 400, 2
        )
        is None
    )


def test_s0b6_finder_returns_bounded_window():
    win = pg._find_local_content_window({"alpha", "beta"}, "alpha beta gamma", 400, 2)
    assert win is not None
    start, end = win
    assert end - start <= 400


def test_s0b6_finder_none_when_words_beyond_window():
    # Two needed words separated by >400 chars -> no single <=400 window holds both.
    row = "alpha " + ("z" * 500) + " beta"
    assert pg._find_local_content_window({"alpha", "beta"}, row, 400, 2) is None


# ─────────────────────────────────────────────────────────────────────────────
# S0b-7 — reproduction against the gap-#18 harness
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.skip(reason=(
    "Writer-side content-word-overlap floor + the Phase-0b Delta-1 full-row rescue were REMOVED per 2026-07-10 UNFREEZE (fix 2, GH I-arch-s5-001): the no_content_word_overlap_any_cited_span gate forced near-verbatim copying and is deleted, so the Delta-1/shadow/enforce rescue machinery it gated no longer exists. The NLI entailment judge is now the semantic bar (live-judge surface, not offline)."
))
def test_s0b7_reproduction_gap18_fixture(monkeypatch):
    """The gap-#18 wrongful content-floor drop (rediagnose_gap18.py CASE 3b):
    a narrow byte-range whose FULL cited rows share the synthesis vocabulary.
    Under off it drops; under enforce the bounded-window rescue passes it.
    A genuinely unsupported sentence still drops under enforce.
    """
    # I-ready-018 (#1088): the CASE-3b fixtures are inline below. The previous
    # `importlib.import_module("scripts.rediagnose_gap18")` referenced a local
    # diagnostic script that was NEVER committed to git (ModuleNotFoundError in
    # any clean checkout / CI). Removed the dead dependency; the inline rows are
    # the same ones the diagnosis recorded, and the rescue logic under test is
    # exercised directly via pg below (STALE_ASSERTION, no feature removed).
    row_a = (
        "Background note. The carbon levy drove decarbonization and "
        "structural change in regional industry."
    )
    row_b = (
        "Grid analysis: the provincial supply is dominated by "
        "hydroelectric power generation."
    )
    pool = {"a": {"direct_quote": row_a}, "b": {"direct_quote": row_b}}
    grounded = (
        "Decarbonization reflects structural change in the regional industry "
        "[#ev:a:0-16][#ev:b:0-15]."
    )

    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    _install_judge(monkeypatch, AllEntailJudge())

    # OFF: the gap-#18 sentence drops.
    monkeypatch.delenv("PG_VERIFICATION_MODE", raising=False)
    res_off = pg.verify_sentence_provenance(grounded, pool)
    assert res_off.is_verified is False

    # ENFORCE: the same grounded sentence now passes.
    monkeypatch.setenv("PG_VERIFICATION_MODE", "enforce")
    res_on = pg.verify_sentence_provenance(grounded, pool)
    assert res_on.is_verified is True

    # A genuinely unsupported sentence (content words NOT in either full row)
    # still drops under enforce — the rescue does not launder fabrication.
    unsupported = (
        "Nuclear reactors supplied the desalination plants downtown "
        "[#ev:a:0-16][#ev:b:0-15]."
    )
    res_unsupported = pg.verify_sentence_provenance(unsupported, pool)
    assert res_unsupported.is_verified is False
