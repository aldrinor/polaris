"""I-deepfix-001 V3 (#1344) — DIRECT evidence-span grounding: no-provenance-token repair FINISH.

RED->GREEN, OFFLINE (no GPU / no network / no paid LLM). Proves the ~15 drb_72 GROUNDABLE quantitative
findings that the basket repair path could NOT bind are now recovered by attaching the REAL evidence
span the finding was written from and re-running the UNCHANGED strict_verify per clause — while a
genuinely ungroundable / coincidental sentence STAYS dropped (faithfulness never relaxed).

The entailment judge is stubbed with a deterministic fake (same convention as
``test_provenance_reanchor.py``): ENTAILED only when the judged span actually contains the finding's
anchor phrase, NEUTRAL otherwise. This exercises the enforce-mode acceptance gate exactly as a real
judge would — the correct span passes, a coincidental non-entailing span is rejected. The FROZEN
faithfulness engine (strict_verify / NLI / provenance / span-grounding) is neither imported for edit
nor modified.

iter-2 (Codex P1 laundering-leak fix): ``ground_untokened_sentence_to_span`` now calls ``verify_fn``
with ``allow_local_window_fallback=False`` so the BOUND ``[#ev:id:start-end]`` span must ITSELF entail.
Without it, ``verify_sentence_provenance`` defaults that flag ``True`` and a candidate whose bound span
is NEUTRAL could still PASS via a DIFFERENT in-row local window — laundering an unverified binding
through with its token pointing at a non-entailing span. The two added tests below prove the leak is
CLOSED: (A) at the ``ground_untokened_sentence_to_span`` boundary a candidate whose bound span does not
entail (only a different in-row window would) STAYS DROPPED, and every ``verify_fn`` call forces the
flag False; (B) at the REAL ``verify_sentence_provenance`` engine, the exact distractor candidate the
function builds leaks with the fallback ON and fails closed with it OFF (mirrors the accepted
``test_provenance_reanchor.test_reanchor_red_baseline_leak_requires_fallback``).

The primary GREEN fixture is the ACTUAL drb_72 dropped finding
("One more robot per thousand workers reduces the employment-to-population ratio by 0.2 percentage
points and wages by 0.42%.") grounded to its real source span
(``acemoglu_restrepo_robots_jobs.direct_quote``).
"""
from __future__ import annotations

import re
from types import SimpleNamespace

import pytest

from src.polaris_graph.clinical_generator import strict_verify as _gen2
from src.polaris_graph.generator import verified_compose as vc
from src.polaris_graph.generator.provenance_generator import (
    strict_verify,
    verify_sentence_provenance,
)

_EV_TOKEN_RE = re.compile(r"\[#ev:[^\]]*\]")


# ─────────────────────────────────────────────────────────────────────────────
# Deterministic fake entailment judge (mirrors test_provenance_reanchor._FakeJudge)
# ─────────────────────────────────────────────────────────────────────────────
class _FakeJudge:
    """ENTAILED iff the judged span contains the anchor phrase; NEUTRAL otherwise — so the
    span-grounding search behaves realistically (the correct window passes, a coincidental
    non-entailing window is rejected exactly as the real NLI would)."""

    def __init__(self, anchor: str) -> None:
        self.anchor = anchor.lower()
        self.calls: list[tuple[str, str]] = []

    def judge(self, sentence: str, span: str) -> tuple[str, str]:
        self.calls.append((sentence, span))
        if self.anchor in (span or "").lower():
            return "ENTAILED", "fake-entailed"
        return "NEUTRAL", "fake-neutral"


class _WindowJudge:
    """ENTAILED iff the judged span CONTAINS the support phrase; NEUTRAL otherwise (a copy of
    ``test_provenance_reanchor._WindowJudge``). Models the local-window leak: a narrow distractor
    span that shares the number + content words but does NOT contain the support phrase is NEUTRAL on
    its OWN content, while the real support sentence LATER in the same row entails — so the gap-#18
    local-window fallback would (pre-fix) find the support window and PASS, keeping the token bound to
    the non-entailing distractor span."""

    def __init__(self, support_phrase: str) -> None:
        self.support_phrase = support_phrase.lower()
        self.calls: list[tuple[str, str]] = []

    def judge(self, sentence: str, span: str) -> tuple[str, str]:
        self.calls.append((sentence, span))
        if self.support_phrase in (span or "").lower():
            return "ENTAILED", "fake-entailed"
        return "NEUTRAL", "fake-neutral"


def _install_judge(monkeypatch, fake) -> None:
    monkeypatch.setattr(_gen2, "_JUDGE_SINGLETON", fake, raising=False)
    monkeypatch.setattr(_gen2, "_get_judge", lambda: fake)


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    _gen2.reset_judge_telemetry()
    # Clean slate: each test sets the flags it needs.
    monkeypatch.delenv("PG_STRICT_VERIFY_ENTAILMENT", raising=False)
    monkeypatch.delenv("PG_VERIFICATION_MODE", raising=False)
    monkeypatch.delenv("PG_NO_TOKEN_SPAN_GROUNDING", raising=False)
    monkeypatch.delenv("PG_NO_TOKEN_SENTENCE_REPAIR", raising=False)
    yield


# ─────────────────────────────────────────────────────────────────────────────
# Real drb_72 fixture: the Acemoglu-Restrepo robot finding + its real source span.
# ─────────────────────────────────────────────────────────────────────────────
# The exact untokened sentence strict_verify dropped no_provenance_token in the run.
_ROBOT_FINDING = (
    "One more robot per thousand workers reduces the employment-to-population ratio "
    "by 0.2 percentage points and wages by 0.42%."
)
# A compact evidence row carrying that finding verbatim after a leading admin clause (so the
# grounding must SEARCH for the right span, not blindly cite the whole row). Modeled on the real
# acemoglu_restrepo_robots_jobs.direct_quote.
_ROBOT_QUOTE = (
    "We use variation in the exposure to robots across US local labor markets. "
    "One more robot per thousand workers reduces the employment-to-population ratio "
    "by 0.2 percentage points and wages by 0.42%."
)
_ROBOT_ANCHOR = "reduces the employment-to-population ratio by 0.2 percentage points"


def _robot_pool() -> dict:
    return {"acemoglu_restrepo_robots_jobs": {"direct_quote": _ROBOT_QUOTE, "source_tier": "T1"}}


def _empty_writer(_basket, _pool) -> str:
    return ""


# ─────────────────────────────────────────────────────────────────────────────
# 1. GREEN — a real untokened quantitative finding is grounded to its real span,
#    carries a real [#ev] token, and SURVIVES the UNCHANGED strict_verify.
# ─────────────────────────────────────────────────────────────────────────────
def test_quantitative_finding_grounded_to_real_span_and_survives(monkeypatch):
    monkeypatch.setenv("PG_NO_TOKEN_SPAN_GROUNDING", "1")
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    _install_judge(monkeypatch, _FakeJudge(_ROBOT_ANCHOR))
    pool = _robot_pool()

    assert not _EV_TOKEN_RE.search(_ROBOT_FINDING)  # the leak precondition

    grounded = vc.ground_untokened_sentence_to_span(
        _ROBOT_FINDING, pool, verify_fn=verify_sentence_provenance,
    )
    assert grounded is not None, "groundable quantitative finding must be RECOVERED, not dropped"
    assert _EV_TOKEN_RE.search(grounded), "recovered finding must carry a real [#ev] provenance token"
    assert "acemoglu_restrepo_robots_jobs" in grounded
    # The ORIGINAL finding prose is PRESERVED (attach-a-token, not replace-with-a-clause): stripping
    # the [#ev] token restores the exact finding sentence.
    assert _EV_TOKEN_RE.sub("", grounded).replace(" ", "") == _ROBOT_FINDING.replace(" ", "")
    assert "0.42%" in grounded and "0.2 percentage points" in grounded

    # It must SURVIVE the UNCHANGED strict_verify (the same gate the run uses at the drop site).
    report = strict_verify(grounded, pool)
    assert report.kept_sentences, "grounded finding must survive the UNCHANGED strict_verify"
    kept = " ".join(str(getattr(s, "sentence", s)) for s in report.kept_sentences)
    assert _EV_TOKEN_RE.search(kept) and "0.42%" in kept


# ─────────────────────────────────────────────────────────────────────────────
# 2. RED->GREEN via the kill-switch — pre-fix (flag OFF) the SAME finding is dropped.
# ─────────────────────────────────────────────────────────────────────────────
def test_killswitch_off_is_byte_identical_drop(monkeypatch):
    monkeypatch.setenv("PG_NO_TOKEN_SPAN_GROUNDING", "0")  # pre-fix behavior
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    _install_judge(monkeypatch, _FakeJudge(_ROBOT_ANCHOR))
    out = vc.ground_untokened_sentence_to_span(
        _ROBOT_FINDING, _robot_pool(), verify_fn=verify_sentence_provenance,
    )
    assert out is None, "flag OFF => no span grounding => the legacy no_provenance_token drop (byte-identical)"


# ─────────────────────────────────────────────────────────────────────────────
# 3. SAFETY — enforce-only laundering guard: a coincidental decimal + content-word
#    match on a NON-entailing span STAYS dropped (never laundered into a pass).
# ─────────────────────────────────────────────────────────────────────────────
def test_coincidental_nonentailing_match_stays_dropped(monkeypatch):
    monkeypatch.setenv("PG_NO_TOKEN_SPAN_GROUNDING", "1")
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    # Judge entails ONLY the true claim's anchor — absent from the coincidental span => NEUTRAL.
    _install_judge(monkeypatch, _FakeJudge("consumer sentiment improved"))

    sentence = "Consumer sentiment improved by 0.2 and 0.42 index points across markets."
    # A row that mechanically matches (both decimals + >=2 shared content words) but does NOT entail.
    pool = {
        "ev_unrelated": {
            "direct_quote": (
                "The robot index moved 0.2 percentage points and 0.42 across the observed markets sample."
            ),
        }
    }
    out = vc.ground_untokened_sentence_to_span(sentence, pool, verify_fn=verify_sentence_provenance)
    assert out is None, "a coincidental non-entailing span must STAY dropped (enforce judge is the gate)"


def test_enforce_gate_off_mode_does_not_ground(monkeypatch):
    """Search-for-a-match is accepted ONLY under entailment enforce. In off/warn mode the fallback
    no-ops (returns None) — the laundering guard mirrors provenance_generator._try_reanchor."""
    monkeypatch.setenv("PG_NO_TOKEN_SPAN_GROUNDING", "1")
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "off")
    _install_judge(monkeypatch, _FakeJudge(_ROBOT_ANCHOR))
    out = vc.ground_untokened_sentence_to_span(
        _ROBOT_FINDING, _robot_pool(), verify_fn=verify_sentence_provenance,
    )
    assert out is None, "off-mode => no grounding (enforce-only accept gate)"


# ─────────────────────────────────────────────────────────────────────────────
# 4. SCOPE — a non-numeric untokened sentence is NOT this fallback's concern (None).
# ─────────────────────────────────────────────────────────────────────────────
def test_non_numeric_sentence_left_to_basket_path(monkeypatch):
    monkeypatch.setenv("PG_NO_TOKEN_SPAN_GROUNDING", "1")
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    _install_judge(monkeypatch, _FakeJudge("mechanism"))
    sentence = "Production requires tasks, which are allocated to capital or labor."
    pool = {"ev_x": {"direct_quote": "Production requires tasks, which are allocated to capital or labor."}}
    out = vc.ground_untokened_sentence_to_span(sentence, pool, verify_fn=verify_sentence_provenance)
    assert out is None, "no numeric anchor => the span-grounding fallback abstains (basket path owns it)"


def test_already_tokened_sentence_not_grounded(monkeypatch):
    monkeypatch.setenv("PG_NO_TOKEN_SPAN_GROUNDING", "1")
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    _install_judge(monkeypatch, _FakeJudge(_ROBOT_ANCHOR))
    already = f"{_ROBOT_FINDING} [#ev:acemoglu_restrepo_robots_jobs:0-40]"
    out = vc.ground_untokened_sentence_to_span(already, _robot_pool(), verify_fn=verify_sentence_provenance)
    assert out is None, "a sentence that already cites a span is not a grounding candidate"


# ─────────────────────────────────────────────────────────────────────────────
# 5. WIRING — repair_untokened_sentence FALLS BACK to span-grounding when NO basket binds.
# ─────────────────────────────────────────────────────────────────────────────
def test_repair_untokened_sentence_falls_back_to_span_grounding(monkeypatch):
    """The end-to-end repair entry point: with NO consolidated basket to bind the finding, the basket
    path yields nothing and the NEW span-grounding fallback recovers it (attach real token, preserve
    finding). RED pre-fix: repair_untokened_sentence returned None here -> no_provenance_token drop."""
    monkeypatch.setenv("PG_NO_TOKEN_SENTENCE_REPAIR", "1")
    monkeypatch.setenv("PG_NO_TOKEN_SPAN_GROUNDING", "1")
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    _install_judge(monkeypatch, _FakeJudge(_ROBOT_ANCHOR))

    out = vc.repair_untokened_sentence(
        _ROBOT_FINDING,
        [],  # NO baskets -> the basket path binds nothing -> the fallback must fire
        _robot_pool(),
        writer_fn=_empty_writer,
        verify_fn=verify_sentence_provenance,
    )
    assert out is not None, "with no basket, repair must fall back to span-grounding (not drop)"
    assert _EV_TOKEN_RE.search(out)
    assert _EV_TOKEN_RE.sub("", out).replace(" ", "") == _ROBOT_FINDING.replace(" ", "")


def test_repair_untokened_sentence_fallback_off_still_drops(monkeypatch):
    """The basket-only path is byte-identical when the fallback flag is OFF: no basket + no fallback
    => None (the legacy drop)."""
    monkeypatch.setenv("PG_NO_TOKEN_SENTENCE_REPAIR", "1")
    monkeypatch.setenv("PG_NO_TOKEN_SPAN_GROUNDING", "0")
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    _install_judge(monkeypatch, _FakeJudge(_ROBOT_ANCHOR))
    out = vc.repair_untokened_sentence(
        _ROBOT_FINDING, [], _robot_pool(), writer_fn=_empty_writer, verify_fn=verify_sentence_provenance,
    )
    assert out is None, "fallback OFF + no basket => byte-identical legacy drop (None)"


# ─────────────────────────────────────────────────────────────────────────────
# 6. iter-2 Codex P1 — LOCAL-WINDOW LAUNDERING LEAK CLOSED.
#    A candidate whose BOUND span does NOT entail (only a DIFFERENT in-row window
#    does) must STAY DROPPED — ground_untokened_sentence_to_span forces
#    allow_local_window_fallback=False, so no different-window rescue can launder
#    the binding. Mirrors provenance_generator._try_reanchor (:1573/:1625/:1663).
# ─────────────────────────────────────────────────────────────────────────────
class _LocalWindowLeakVerify:
    """A faithful behavioral MODEL of the strict_verify local-window leak Codex flagged: the BOUND
    span does NOT entail on its own, but a DIFFERENT in-row window DOES. ``verify_sentence_provenance``
    defaults ``allow_local_window_fallback=True`` (provenance_generator.py:2049), so under the default
    a NEUTRAL bound span is RESCUED by a different window (``is_verified=True`` — the LEAK); with
    ``allow_local_window_fallback=False`` the bound span itself must entail, so it fails closed
    (``is_verified=False``). Records every call's flag so the test can assert the fix forces False on
    EVERY candidate.
    """

    def __init__(self) -> None:
        self.calls: list[bool] = []

    def __call__(self, sentence, evidence_pool, *, allow_local_window_fallback: bool = True, **kwargs):
        self.calls.append(allow_local_window_fallback)
        # The leak: passes on the default (a different in-row window rescues); drops when the bound
        # span must itself entail.
        return SimpleNamespace(is_verified=bool(allow_local_window_fallback))


def test_bound_span_only_entailment_stays_dropped_and_forces_flag(monkeypatch):
    """RED->GREEN at the ground_untokened_sentence_to_span boundary. The modeled verifier LEAKS on the
    default flag (a different in-row window rescues a NEUTRAL bound span) and CLOSES on
    allow_local_window_fallback=False. The fix forces False on every candidate, so a finding whose
    bound span does not itself entail STAYS DROPPED (returns None) and never carries a token pointing at
    a non-entailing span."""
    monkeypatch.setenv("PG_NO_TOKEN_SPAN_GROUNDING", "1")
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")

    sentence = "Treatment reduced the score by 15.5 percent in adults."
    # Row carries the sentence's decimal (15.5) + >=2 shared content words in BOTH a non-entailing
    # distractor sentence and a genuinely-entailing sentence — so >=1 decimal-carrying candidate span
    # is verified (the fix's call site is exercised).
    pool = {
        "ev_leak": {
            "direct_quote": (
                "Adults scored 15.5 percent in a baseline treatment survey. "
                "Treatment reduced the score by 15.5 percent in adults overall."
            ),
        }
    }
    leaky = _LocalWindowLeakVerify()

    # RED baseline / non-vacuity: the modeled verifier is LOAD-BEARING — it passes under the default
    # (leak) and fails closed only when the bound span must itself entail.
    assert leaky("x", pool).is_verified is True, (
        "red baseline: default allow_local_window_fallback=True launders a NEUTRAL bound span via a "
        "different in-row window"
    )
    assert leaky("x", pool, allow_local_window_fallback=False).is_verified is False, (
        "the fix gate: bound-span-only entailment drops the non-entailing span"
    )
    leaky.calls.clear()

    # GREEN: the fix forces False on EVERY candidate -> the modeled leak can never rescue -> DROPPED.
    out = vc.ground_untokened_sentence_to_span(sentence, pool, verify_fn=leaky)
    assert out is None, (
        "a candidate whose BOUND span does not entail (only a different in-row window does) must STAY "
        "DROPPED — the fix forbids the different-window rescue"
    )
    assert leaky.calls, "the verify_fn must be exercised (a decimal-carrying candidate span was tried)"
    assert all(flag is False for flag in leaky.calls), (
        "every verify_fn call must force allow_local_window_fallback=False (Codex P1 laundering fix)"
    )


def test_real_engine_distractor_span_leak_closed_by_flag(monkeypatch):
    """RED->GREEN at the REAL verify_sentence_provenance engine (mirrors
    test_provenance_reanchor.test_reanchor_red_baseline_leak_requires_fallback). The EXACT distractor
    candidate ground_untokened_sentence_to_span builds for the non-entailing span leaks with the
    fallback ON and fails closed with it OFF; end-to-end the function never returns a token bound to
    that non-entailing distractor span."""
    monkeypatch.setenv("PG_NO_TOKEN_SPAN_GROUNDING", "1")
    monkeypatch.setenv("PG_VERIFICATION_MODE", "enforce")
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    _install_judge(monkeypatch, _WindowJudge("reduced the score by 15.5 percent"))

    # DISTRACTOR first (shares 15.5 + content words, clears the mechanical floor) but does NOT support
    # the claim; the REAL support lives LATER in the SAME row.
    distractor = "Adults scored 15.5 percent in a baseline treatment survey."
    support = " Treatment reduced the score by 15.5 percent in adults overall."
    direct_quote = distractor + support
    pool = {"ev_win": {"direct_quote": direct_quote}}
    claim = "Treatment reduced the score by 15.5 percent in adults"
    distractor_end = len(distractor)
    # The EXACT candidate ground_untokened_sentence_to_span verifies for the distractor segment
    # (_reanchor_candidate_spans branch (a) emits (0, len(distractor)) as the first segment).
    candidate_distractor = f"{claim} [#ev:ev_win:0-{distractor_end}]."

    # RED (real engine): with the fallback ON the non-entailing distractor span leaks through via the
    # different in-row support window.
    v_leak = verify_sentence_provenance(
        candidate_distractor, pool, allow_local_window_fallback=True,
    )
    assert v_leak.is_verified is True, (
        "red baseline: the real engine launders the non-entailing distractor span with the fallback ON"
    )
    # GREEN (real engine): the SAME distractor span fails closed once the bound span must itself entail.
    v_fixed = verify_sentence_provenance(
        candidate_distractor, pool, allow_local_window_fallback=False,
    )
    assert v_fixed.is_verified is False, (
        "the fix: bound-span-only entailment drops the non-entailing distractor span"
    )

    # End-to-end: the function forces False, so it NEVER returns a token bound to the non-entailing
    # distractor span 0-<distractor_end> (pre-fix it would — the distractor is enumerated first and
    # passed via the rescue). It may legitimately bind the genuinely-entailing later span instead.
    out = vc.ground_untokened_sentence_to_span(
        f"{claim}.", pool, verify_fn=verify_sentence_provenance,
    )
    assert out is None or f":0-{distractor_end}]" not in out, (
        "LEAK: token bound to the non-entailing distractor span — the fix must bind ONLY a span that "
        "itself entails (or drop)"
    )
