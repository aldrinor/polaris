"""I-complete-003 (#1189) — PROVENANCE RE-ANCHOR at the strict_verify drop site.

When a findings sentence FAILS `verify_sentence_provenance` on its currently-
cited span, the re-anchor (env-gated PG_PROVENANCE_REANCHOR, accept ONLY under
entailment `enforce`) enumerates a BOUNDED set of candidate spans WITHIN the
SAME cited evidence row (or, for an uncited verbatim-grounded sentence, the
pool row containing it) and re-runs the EXACT same acceptance gate against each
candidate. The first candidate that passes the FULL gate re-binds the token and
the sentence is kept as RECOVERED. If none passes, the original drop stands.

These tests are network-free + deterministic: a fake entailment judge is
installed (the same convention as test_provenance_generator_entailment.py).
No relaxation of any verify check — the re-anchor reuses verify_sentence_provenance
unchanged, so it can only ever bind to a span that already passes the full bar.

Cases:
  (a) cited span WRONG, a DIFFERENT span in the SAME row supports it -> re-anchored + verified
  (b) no supporting span ANYWHERE -> still dropped (no fabrication)
  (c) uncited verbatim lift of a pool row -> bound
  (d) PG_PROVENANCE_REANCHOR unset -> byte-identical old behaviour (no re-anchor)
  (e) flag ON but entailment OFF + coincidental mechanical match -> STILL dropped (laundering guard)
"""

from __future__ import annotations

import pytest

from src.polaris_graph.clinical_generator import strict_verify as _gen2
from src.polaris_graph.generator import provenance_generator as _pg
from src.polaris_graph.generator.provenance_generator import (
    get_reanchor_telemetry,
    reset_reanchor_telemetry,
    strict_verify,
)


# ---------------------------------------------------------------------------
# Fake judge (mirrors test_provenance_generator_entailment.py)
# ---------------------------------------------------------------------------
class _FakeJudge:
    """Returns ENTAILED only when the judged span actually contains the
    sentence's anchor phrase; NEUTRAL otherwise. This lets the re-anchor
    search behave realistically — a candidate window that does NOT cover the
    support is rejected by the (faked) NLI just as a real judge would, while
    the correct window passes."""

    def __init__(self, anchor: str) -> None:
        self.anchor = anchor.lower()
        self.calls: list[tuple[str, str]] = []

    def judge(self, sentence: str, span: str) -> tuple[str, str]:
        self.calls.append((sentence, span))
        if self.anchor in (span or "").lower():
            return "ENTAILED", "fake-entailed"
        return "NEUTRAL", "fake-neutral"


def _install_judge(monkeypatch, fake: _FakeJudge) -> None:
    monkeypatch.setattr(_gen2, "_JUDGE_SINGLETON", fake, raising=False)
    monkeypatch.setattr(_gen2, "_get_judge", lambda: fake)


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    _gen2.reset_judge_telemetry()
    reset_reanchor_telemetry()
    # Default each test to a clean slate; individual tests set the flags.
    monkeypatch.delenv("PG_PROVENANCE_REANCHOR", raising=False)
    monkeypatch.delenv("PG_STRICT_VERIFY_ENTAILMENT", raising=False)
    yield


# ---------------------------------------------------------------------------
# (a) cited span WRONG, a different span in the SAME row supports it
# ---------------------------------------------------------------------------
def test_reanchor_recovers_wrong_span_same_row(monkeypatch):
    """The token cites bytes 0-30 (a sentence about enrolment) but the actual
    support — "HbA1c reduction of 1.5 percent" — lives later in the SAME row.
    Re-anchor must find the supporting window, re-bind, and KEEP the sentence."""
    monkeypatch.setenv("PG_PROVENANCE_REANCHOR", "1")
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    _install_judge(monkeypatch, _FakeJudge("hba1c reduction of 1.5 percent"))

    # Row: a leading admin sentence, then the supporting clause.
    leading = "The trial enrolled adults at sites."          # bytes 0..len(leading)
    support = " Treatment produced an HbA1c reduction of 1.5 percent in adults."
    direct_quote = leading + support
    pool = {"ev_a": {"direct_quote": direct_quote}}

    # Cite the WRONG span (the admin leading clause) — number + content absent there.
    wrong_end = len(leading)
    draft = (
        f"Treatment produced an HbA1c reduction of 1.5 percent in adults "
        f"[#ev:ev_a:0-{wrong_end}]."
    )

    report = strict_verify(draft, pool)
    assert report.total_kept == 1, (
        f"expected re-anchor to recover the sentence, dropped="
        f"{[d.failure_reasons for d in report.dropped_sentences]}"
    )
    assert report.total_dropped == 0
    kept = report.kept_sentences[0]
    assert kept.is_verified is True
    assert any(w.startswith("reanchored:ev_a:") for w in kept.soft_warnings)
    tel = get_reanchor_telemetry()
    assert tel["reanchor_attempts"] == 1
    assert tel["reanchor_recovered"] == 1


# ---------------------------------------------------------------------------
# (b) no supporting span ANYWHERE -> still dropped (no fabrication)
# ---------------------------------------------------------------------------
def test_reanchor_no_support_anywhere_still_dropped(monkeypatch):
    """The claimed number (9.9 percent) appears in NO span of ANY row. Even
    with the flag ON + enforce, every candidate fails the numeric gate, so the
    sentence is DROPPED — the re-anchor introduces no fabrication path."""
    monkeypatch.setenv("PG_PROVENANCE_REANCHOR", "1")
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    _install_judge(monkeypatch, _FakeJudge("never-matches-this-anchor"))

    direct_quote = "Treatment produced an HbA1c reduction of 1.5 percent in adults."
    pool = {"ev_b": {"direct_quote": direct_quote}}
    draft = (
        f"Treatment produced an HbA1c reduction of 9.9 percent in adults "
        f"[#ev:ev_b:0-{len(direct_quote)}]."
    )

    report = strict_verify(draft, pool)
    assert report.total_kept == 0
    assert report.total_dropped == 1
    assert any(
        "number_not_in_any_cited_span" in r
        for r in report.dropped_sentences[0].failure_reasons
    )
    tel = get_reanchor_telemetry()
    assert tel["reanchor_attempts"] == 1
    assert tel["reanchor_recovered"] == 0


# ---------------------------------------------------------------------------
# (c) uncited verbatim lift of a pool row -> bound
# ---------------------------------------------------------------------------
def test_reanchor_binds_uncited_verbatim_lift(monkeypatch):
    """A sentence with NO [#ev] token that is a verbatim lift of a pool row
    must be located in the pool and BOUND (uncited-bound telemetry ticks)."""
    monkeypatch.setenv("PG_PROVENANCE_REANCHOR", "1")
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    _install_judge(
        monkeypatch, _FakeJudge("cardiovascular events in adults by 23.5 percent"),
    )

    direct_quote = (
        "Aspirin reduced cardiovascular events in adults by 23.5 percent."
    )
    pool = {"ev_c": {"direct_quote": direct_quote}}
    # Uncited sentence (no token) that verbatim-matches the row.
    draft = "Aspirin reduced cardiovascular events in adults by 23.5 percent."

    report = strict_verify(draft, pool)
    assert report.total_kept == 1, (
        f"expected uncited verbatim lift to be bound, dropped="
        f"{[d.failure_reasons for d in report.dropped_sentences]}"
    )
    kept = report.kept_sentences[0]
    assert kept.is_verified is True
    assert any(w.startswith("reanchored_uncited:ev_c:") for w in kept.soft_warnings)
    tel = get_reanchor_telemetry()
    assert tel["reanchor_uncited_bound"] == 1
    assert tel["reanchor_recovered"] == 1


# ---------------------------------------------------------------------------
# (d) flag unset -> byte-identical old behaviour (no re-anchor)
# ---------------------------------------------------------------------------
def test_reanchor_disabled_is_byte_identical(monkeypatch):
    """With PG_PROVENANCE_REANCHOR unset, the SAME wrong-span draft from case
    (a) is DROPPED exactly as before — no re-anchor, no judge call, no counter
    mutation."""
    # Flag intentionally NOT set (fixture deleted it). Entailment off so no
    # judge fires either — proves the early-out happens before any new logic.
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "off")
    fake = _FakeJudge("anything")
    _install_judge(monkeypatch, fake)

    leading = "The trial enrolled adults at sites."
    support = " Treatment produced an HbA1c reduction of 1.5 percent in adults."
    direct_quote = leading + support
    pool = {"ev_d": {"direct_quote": direct_quote}}
    wrong_end = len(leading)
    draft = (
        f"Treatment produced an HbA1c reduction of 1.5 percent in adults "
        f"[#ev:ev_d:0-{wrong_end}]."
    )

    report = strict_verify(draft, pool)
    assert report.total_kept == 0, "flag-off must NOT recover the sentence"
    assert report.total_dropped == 1
    # No re-anchor counters touched.
    tel = get_reanchor_telemetry()
    assert tel == {
        "reanchor_attempts": 0,
        "reanchor_recovered": 0,
        "reanchor_uncited_bound": 0,
        # I-perm-004 (#1198) slice 2: argmax-recovery counter, untouched in OFF mode.
        "reanchor_argmax_recovered": 0,
    }
    # Helper must agree it is disabled.
    assert _pg._provenance_reanchor_enabled() is False


# ---------------------------------------------------------------------------
# (e) laundering guard — flag ON, entailment OFF, coincidental mechanical match
# ---------------------------------------------------------------------------
def test_reanchor_off_entailment_does_not_launder(monkeypatch):
    """ADVISOR-required laundering guard: with PG_PROVENANCE_REANCHOR=1 but
    PG_STRICT_VERIFY_ENTAILMENT=off, a row that contains a coincidental
    mechanically-matching window (number + 2 content words) must NOT rescue the
    sentence — the enforce-only accept gate keeps the drop. Otherwise the
    active span-search would launder a coincidental match into a pass (§-1.1
    lethal mode)."""
    monkeypatch.setenv("PG_PROVENANCE_REANCHOR", "1")
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "off")
    fake = _FakeJudge("anything")
    _install_judge(monkeypatch, fake)

    # A row where "reduction" + "adults" + "1.5" co-occur in a window — a
    # mechanically-passing coincidence that, under off-mode, would slip
    # through if accept were not gated on enforce.
    leading = "Enrolment of adults began early."
    support = " A separate reduction of 1.5 percent in adults was noted."
    direct_quote = leading + support
    pool = {"ev_e": {"direct_quote": direct_quote}}
    wrong_end = len(leading)
    draft = (
        f"Treatment produced a reduction of 1.5 percent in adults "
        f"[#ev:ev_e:0-{wrong_end}]."
    )

    report = strict_verify(draft, pool)
    assert report.total_kept == 0, (
        "off-mode re-anchor must NOT accept — that would launder a coincidental "
        "mechanical match into a pass"
    )
    assert report.total_dropped == 1
    # Enforce-only gate returns before any attempt, so no counters tick + no
    # judge call.
    tel = get_reanchor_telemetry()
    assert tel["reanchor_attempts"] == 0
    assert tel["reanchor_recovered"] == 0
    assert fake.calls == [], "off-mode must not invoke the entailment judge"


# ---------------------------------------------------------------------------
# (f) NLI fail-open guard — judge_error sentinel must NOT recover across the
#     40-window search (the re-anchor must not amplify the fail-open path)
# ---------------------------------------------------------------------------
class _JudgeErrorJudge:
    """Simulates a DEGRADED NLI judge: every call fails OPEN, returning the
    `("ENTAILED", "judge_error: ...")` sentinel exactly as entailment_judge.py
    does on an API/parse error. The verifier's L1865-1872 fail-closed gate must
    turn this into is_verified=False under enforce, so NO candidate window can
    be 'recovered' by a degraded judge — the re-anchor's 40-window search must
    not multiply the fail-open into a pass."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def judge(self, sentence: str, span: str) -> tuple[str, str]:
        self.calls.append((sentence, span))
        return "ENTAILED", "judge_error: simulated transient API failure"


def test_reanchor_judge_error_does_not_amplify_fail_open(monkeypatch):
    """ADVISOR-required (point 6): in enforce mode, a candidate window where the
    NLI judge returns the judge_error fail-open sentinel must NOT yield
    is_verified=True inside the re-anchor loop. A genuinely supported sentence
    (number + content present in the cited span) is used so the ONLY thing that
    can flip is_verified is the judge — proving the L1865-1872 fail-closed fires
    on each re-bound candidate. The sentence stays DROPPED; the re-anchor cannot
    recover a sentence on the back of a degraded judge across the 40 windows."""
    monkeypatch.setenv("PG_PROVENANCE_REANCHOR", "1")
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    # I-arch-010 FIX-1: this test's whole structure assumes the judge_error sentence DROPS (it
    # asserts total_kept==0, reanchor_attempts==1). Under the new default-advisory the sentence is
    # KEPT directly and re-anchor never fires on it. Pin the kill-switch so this stays a
    # legacy-hard-drop / no-fail-open-amplification regression test. The not-laundered-as-verified
    # intent under the NEW default is covered by the credibility-pass tier classifier (harness case B:
    # a judge_error member is member_tier=DETERMINISTIC_ONLY, span_verdict=UNSUPPORTED, never counted).
    monkeypatch.setenv("PG_ENTAILMENT_JUDGE_ERROR_ADVISORY", "0")
    fake = _JudgeErrorJudge()
    _install_judge(monkeypatch, fake)

    # The support genuinely lives later in the SAME row, so numeric + content
    # gates would pass on the right window — ONLY the judge_error fail-closed
    # keeps it dropped. This isolates the fail-open-amplification risk.
    leading = "The trial enrolled adults at sites."
    support = " Treatment produced an HbA1c reduction of 1.5 percent in adults."
    direct_quote = leading + support
    pool = {"ev_f": {"direct_quote": direct_quote}}
    wrong_end = len(leading)
    draft = (
        f"Treatment produced an HbA1c reduction of 1.5 percent in adults "
        f"[#ev:ev_f:0-{wrong_end}]."
    )

    report = strict_verify(draft, pool)
    assert report.total_kept == 0, (
        "a judge_error fail-open must NOT let the re-anchor recover the sentence "
        "across the 40-window search — that would amplify the NLI fail-open"
    )
    assert report.total_dropped == 1
    # The re-anchor DID attempt (flag on, enforce on, row present) but recovered
    # nothing — the candidate window where numeric+content pass reaches the
    # entailment block, and the judge_error fail-closed (L1865-1872, enforce)
    # turns is_verified back to False, so NO candidate is accepted.
    tel = get_reanchor_telemetry()
    assert tel["reanchor_attempts"] == 1
    assert tel["reanchor_recovered"] == 0
    # The judge WAS consulted on at least one candidate window (proving the
    # candidate reached the entailment gate, where the fail-open was caught).
    assert fake.calls, "judge should have been consulted on a candidate window"
    # Direct proof that the fail-closed fires on a candidate whose numeric +
    # content gates pass: the correct-span candidate verifies to is_verified
    # False with the judge_error fail-closed failure, NOT a pass.
    correct_span = (
        f"Treatment produced an HbA1c reduction of 1.5 percent in adults "
        f"[#ev:ev_f:{wrong_end}-{len(direct_quote)}]."
    )
    v_correct = _pg.verify_sentence_provenance(
        correct_span, pool, require_number_match=True,
    )
    assert v_correct.is_verified is False, (
        "under judge_error the candidate must fail-closed, not pass"
    )
    assert any(
        "entailment_judge_error_fail_closed" in r
        for r in v_correct.failure_reasons
    ), v_correct.failure_reasons
    assert v_correct.judge_error is True


# ---------------------------------------------------------------------------
# (g) I-complete-003 iter-2 (#1189) P1 — BOUND-SPAN-ITSELF-SUPPORTS invariant.
#     A re-anchor candidate span that does NOT itself entail must NOT be kept
#     on the back of a DIFFERENT in-row window that entails (the Codex iter-1
#     leak). The final bound token must directly support the claim WITHOUT a
#     different-window rescue.
# ---------------------------------------------------------------------------
class _WindowJudge:
    """ENTAILED iff the judged span CONTAINS the real support phrase. So a
    NON-supporting distractor span is NEUTRAL on its OWN content, while the real
    support sentence (later in the same row) entails. Mirrors the production NLI:
    the narrow distractor span fails, but the gap-#18 local-window fallback would
    (pre-fix) find the support window and PASS — keeping the token bound to the
    non-supporting distractor span."""

    def __init__(self, support_phrase: str) -> None:
        self.support_phrase = support_phrase.lower()
        self.calls: list[tuple[str, str]] = []

    def judge(self, sentence: str, span: str) -> tuple[str, str]:
        self.calls.append((sentence, span))
        if self.support_phrase in (span or "").lower():
            return "ENTAILED", "fake-entailed"
        return "NEUTRAL", "fake-neutral"


def test_reanchor_rejects_nonentailing_candidate_bound_to_other_window(monkeypatch):
    """P1 (FAITHFULNESS-LETHAL): a DISTRACTOR span that shares the number +
    >=2 content words with the claim (so it clears the span-scoped numeric +
    content floor) but does NOT itself entail must NOT be kept bound to that
    span just because a DIFFERENT in-row window entails. The re-anchor accept
    gate passes allow_local_window_fallback=False, so the candidate passes ONLY
    if its OWN bound span directly entails.

    PG_VERIFICATION_MODE=enforce AND PG_STRICT_VERIFY_ENTAILMENT=enforce are BOTH
    required for the leak to be REACHABLE (the gap-#18 rescue sites are gated on
    PG_VERIFICATION_MODE; an integer-only "15 percent" claim hits the non-numeric
    content-window rescue). Without the fix, the distractor span is kept at its
    OWN offsets via the different-window rescue (red baseline, proven below)."""
    monkeypatch.setenv("PG_PROVENANCE_REANCHOR", "1")
    monkeypatch.setenv("PG_VERIFICATION_MODE", "enforce")
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    fake = _WindowJudge("reduced blood pressure by 15 percent")
    _install_judge(monkeypatch, fake)

    # DISTRACTOR up front (shares "15"/"reduced"/"percent"/"adults" with the
    # claim — clears the mechanical floor) but does NOT support the blood-
    # pressure claim. REAL support lives later in the SAME row.
    distractor = "Adults reduced 15 percent in adults treatment."
    support = " Treatment reduced blood pressure by 15 percent in adults overall."
    direct_quote = distractor + support
    pool = {"ev_g": {"direct_quote": direct_quote}}

    # Cite a tiny WRONG span (forces drop + re-anchor search).
    draft = (
        "Treatment reduced blood pressure by 15 percent in adults "
        "[#ev:ev_g:0-5]."
    )

    report = strict_verify(draft, pool)

    # The sentence is recovered ONLY if a candidate's OWN span directly entails.
    # The distractor span (0-len(distractor)) must NEVER be the bound span.
    distractor_end = len(distractor)
    for kept in report.kept_sentences:
        for tok in kept.tokens:
            assert not (tok.start == 0 and tok.end == distractor_end), (
                "LEAK: token bound to the non-entailing distractor span "
                f"0-{distractor_end} — a different in-row window must NOT rescue "
                "a non-supporting candidate"
            )

    # Encode Codex's invariant DIRECTLY: every kept token, re-verified standalone
    # with the local-window fallback DISABLED, must pass on its OWN bound span.
    for kept in report.kept_sentences:
        v_standalone = _pg.verify_sentence_provenance(
            kept.sentence, pool,
            require_number_match=True,
            allow_local_window_fallback=False,
        )
        assert v_standalone.is_verified is True, (
            "kept span must itself directly support without a different-window "
            f"rescue; reasons={v_standalone.failure_reasons}"
        )


def test_reanchor_red_baseline_leak_requires_fallback(monkeypatch):
    """RED-PROOF (anti-vacuous-green): the SAME distractor span that
    test_reanchor_rejects_nonentailing_candidate_bound_to_other_window forbids is
    is_verified=True when the local-window fallback is ENABLED (default). This
    proves the fix is load-bearing — the only thing keeping the non-entailing
    span out is allow_local_window_fallback=False, not some incidental floor."""
    monkeypatch.setenv("PG_VERIFICATION_MODE", "enforce")
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    fake = _WindowJudge("reduced blood pressure by 15 percent")
    _install_judge(monkeypatch, fake)

    distractor = "Adults reduced 15 percent in adults treatment."
    support = " Treatment reduced blood pressure by 15 percent in adults overall."
    direct_quote = distractor + support
    pool = {"ev_g2": {"direct_quote": direct_quote}}
    distractor_end = len(distractor)
    draft_distractor = (
        "Treatment reduced blood pressure by 15 percent in adults "
        f"[#ev:ev_g2:0-{distractor_end}]."
    )

    # WITH the fallback (default): the different-window rescue passes the
    # non-entailing distractor span — the leak path.
    v_leak = _pg.verify_sentence_provenance(
        draft_distractor, pool,
        require_number_match=True,
        allow_local_window_fallback=True,
    )
    assert v_leak.is_verified is True, (
        "red baseline: with the fallback ON the non-entailing distractor span "
        "leaks through — confirms the test is not vacuously green"
    )

    # WITHOUT the fallback (the re-anchor accept gate): the SAME span fails closed
    # on its OWN narrow-span NEUTRAL verdict.
    v_fixed = _pg.verify_sentence_provenance(
        draft_distractor, pool,
        require_number_match=True,
        allow_local_window_fallback=False,
    )
    assert v_fixed.is_verified is False
    assert any("entailment_failed" in r for r in v_fixed.failure_reasons), (
        v_fixed.failure_reasons
    )


def test_reanchor_recovers_to_the_directly_entailing_span(monkeypatch):
    """GENUINE-RECOVERY companion to (g): the re-anchor still RECOVERS the
    sentence — but it binds the token to the span that DIRECTLY entails (the
    real support sentence), never the distractor. Proves the P1 fix tightens
    faithfulness WITHOUT killing legitimate recovery."""
    monkeypatch.setenv("PG_PROVENANCE_REANCHOR", "1")
    monkeypatch.setenv("PG_VERIFICATION_MODE", "enforce")
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    fake = _WindowJudge("reduced blood pressure by 15 percent")
    _install_judge(monkeypatch, fake)

    distractor = "Adults reduced 15 percent in adults treatment."
    support = " Treatment reduced blood pressure by 15 percent in adults overall."
    direct_quote = distractor + support
    pool = {"ev_h": {"direct_quote": direct_quote}}
    draft = (
        "Treatment reduced blood pressure by 15 percent in adults "
        "[#ev:ev_h:0-5]."
    )

    report = strict_verify(draft, pool)
    assert report.total_kept == 1, (
        "genuine recovery expected; dropped="
        f"{[d.failure_reasons for d in report.dropped_sentences]}"
    )
    kept = report.kept_sentences[0]
    assert kept.is_verified is True
    # Bound to the support sentence span, which starts AFTER the distractor.
    assert len(kept.tokens) == 1
    tok = kept.tokens[0]
    bound_span = direct_quote[tok.start:tok.end]
    assert "reduced blood pressure by 15 percent" in bound_span.lower(), (
        f"token must bind to the directly-entailing span, got {bound_span!r}"
    )
    assert tok.start >= len(distractor), (
        f"token must NOT start inside the distractor; start={tok.start}"
    )


# ---------------------------------------------------------------------------
# (h) P2-1 — decimal-aware segmentation: a decimal number is NOT split at its
#     period, and a short row is NOT rebound to the WHOLE row by the sliding
#     window (citation-precision guard).
# ---------------------------------------------------------------------------
def test_reanchor_candidate_spans_keeps_decimals_intact():
    """The decimal-aware segmenter must NOT split "1.5"/"23.5" at the period.
    A row "...reduction of 1.5 percent in adults." must yield ONE candidate
    segment that contains the whole "1.5", not two fragments split at the dot."""
    row = "Treatment produced a reduction of 1.5 percent in adults."
    spans = _pg._reanchor_candidate_spans(row)
    # Every sentence-segment candidate that contains the "1." must also contain
    # the full "1.5" (i.e. the decimal was not severed at the period).
    dot_idx = row.index("1.5")
    covering = [
        (s, e) for (s, e) in spans if s <= dot_idx and e >= dot_idx + len("1.5")
    ]
    assert covering, (
        f"no candidate span keeps '1.5' intact; spans={spans!r}"
    )
    # And the SEGMENT candidate (branch a) covers the whole one-sentence row, so
    # a single-sentence verbatim row is still recoverable.
    assert (0, len(row)) in spans, (
        f"single-sentence row must still emit a full-row SEGMENT candidate; "
        f"spans={spans!r}"
    )


def test_reanchor_candidate_spans_suppresses_whole_row_sliding_window(monkeypatch):
    """P2-1 citation-precision guard: for a MULTI-sentence row shorter than the
    window, the sliding-window branch must NOT add the degenerate (0, n) whole-
    row candidate — that weakens citation precision. The per-sentence segments
    are still emitted by branch (a)."""
    # Window comfortably larger than the row so the sliding loop would otherwise
    # add exactly (0, n).
    monkeypatch.setattr(_pg, "PG_PROVENANCE_REANCHOR_WINDOW", 4000)
    row = "First admin sentence here. Second supporting sentence here."
    spans = _pg._reanchor_candidate_spans(row)
    n = len(row)
    # Two sentence segments present (branch a), but the whole-row sliding-window
    # candidate (0, n) is suppressed UNLESS a sentence segment legitimately spans
    # the whole row (it does not here — there are two sentences).
    seg_full_row = any(s == 0 and e == n for (s, e) in spans)
    assert not seg_full_row, (
        f"multi-sentence row must NOT yield a whole-row (0,{n}) candidate; "
        f"spans={spans!r}"
    )
    # Sanity: the two sentence segments ARE present.
    assert len(spans) >= 2, f"expected >=2 sentence segments; spans={spans!r}"


# ---------------------------------------------------------------------------
# (i) P2-2 — single-token guard: a sentence with TWO [#ev] tokens (even same
#     id, different spans) is OUT OF SCOPE for v1 re-anchor and must be left
#     dropped (NOT collapsed onto one rescued span).
# ---------------------------------------------------------------------------
def test_reanchor_skips_multi_token_same_id_sentence(monkeypatch):
    """P2-2: _rebind_single_token rewrites EVERY [#ev] occurrence to one span, so
    a sentence with two same-id tokens citing DIFFERENT spans would have both
    collapsed onto a single rescued span — silently discarding the 2nd citation.
    The explicit len(tokens)==1 guard leaves such a sentence DROPPED."""
    monkeypatch.setenv("PG_PROVENANCE_REANCHOR", "1")
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    fake = _FakeJudge("reduction of 1.5 percent")
    _install_judge(monkeypatch, fake)

    leading = "The trial enrolled adults at sites."
    support = " Treatment produced an HbA1c reduction of 1.5 percent in adults."
    direct_quote = leading + support
    pool = {"ev_i": {"direct_quote": direct_quote}}
    wrong_end = len(leading)
    # TWO same-id tokens citing DIFFERENT (wrong) spans — multi-token same-id.
    draft = (
        "Treatment produced an HbA1c reduction of 1.5 percent in adults "
        f"[#ev:ev_i:0-{wrong_end}] [#ev:ev_i:0-3]."
    )

    report = strict_verify(draft, pool)
    assert report.total_kept == 0, (
        "multi-token sentence must be OUT OF SCOPE for v1 re-anchor (dropped)"
    )
    assert report.total_dropped == 1
    # The single-token guard returns BEFORE any candidate attempt, so the
    # attempt counter does NOT tick for this sentence.
    tel = get_reanchor_telemetry()
    assert tel["reanchor_attempts"] == 0, (
        f"multi-token sentence must not enter the candidate loop; tel={tel}"
    )


# ---------------------------------------------------------------------------
# (j) P1 fail-closed angle — when the entailing support STRADDLES two sentences
#     so NO single candidate segment entails on its own, the sentence must
#     DROP (not be rescued by a whole-row window that the old fallback bridged).
# ---------------------------------------------------------------------------
def test_reanchor_straddling_support_no_single_span_entails_drops(monkeypatch):
    """The genuine support is SPLIT across a sentence boundary: only the
    CONCATENATION of two segments entails, no single candidate segment does.
    With the local-window fallback disabled (the re-anchor accept gate), no
    candidate's OWN span entails, so the sentence DROPS — proving the fix
    fails closed when there is no clean alternative span, not just when a
    better segment happens to exist."""
    monkeypatch.setenv("PG_PROVENANCE_REANCHOR", "1")
    monkeypatch.setenv("PG_VERIFICATION_MODE", "enforce")
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    # The judge only ENTAILS when BOTH halves are present in the judged span —
    # i.e. when the WHOLE row is judged (the old whole-row fallback), never on a
    # single sentence segment.
    full_support = "reduced blood pressure by 15 percent in adults overall"

    class _StraddleJudge:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        def judge(self, sentence: str, span: str) -> tuple[str, str]:
            self.calls.append((sentence, span))
            sl = (span or "").lower()
            # Entails ONLY if both halves co-occur (whole-row), never a segment.
            if "reduced blood pressure by 15 percent" in sl and "in adults overall" in sl:
                return "ENTAILED", "fake-entailed"
            return "NEUTRAL", "fake-neutral"

    fake = _StraddleJudge()
    _install_judge(monkeypatch, fake)

    # Support is split at a sentence boundary: half-A ends one sentence, half-B
    # begins the next. No single decimal-aware segment carries the full support.
    half_a = "Treatment reduced blood pressure by 15 percent. "
    half_b = "This held in adults overall across the cohort."
    direct_quote = half_a + half_b
    pool = {"ev_j": {"direct_quote": direct_quote}}
    _ = full_support  # documents the entailment target
    draft = (
        "Treatment reduced blood pressure by 15 percent in adults "
        "[#ev:ev_j:0-5]."
    )

    report = strict_verify(draft, pool)
    assert report.total_kept == 0, (
        "no single candidate segment entails on its own; the re-anchor must "
        "FAIL CLOSED, not bridge two segments via a whole-row window"
    )
    assert report.total_dropped == 1


# ---------------------------------------------------------------------------
# (k) I-perm-004 (#1198) slice 2 — boilerplate-aware ARGMAX picks the entailing
#     PROSE span where first-passing bound the earlier Title-cased span.
# ---------------------------------------------------------------------------
def _argmax_offsets(soft_warnings):
    """Pull (start, end) from a `reanchored*:ev:S-E[:...]` soft-warning."""
    for w in soft_warnings:
        if w.startswith("reanchored"):
            span = w.split(":")[2]  # ev id is field 1, S-E is field 2
            s, e = span.split("-")
            return int(s), int(e)
    return None


def test_argmax_prefers_prose_span_over_earlier_title(monkeypatch):
    """The supporting clause appears in BOTH a Title-Case segment (enumerated
    first) and a later prose segment. First-passing binds the title; the
    PG_SPAN_RESOLVER argmax binds the prose span and labels it q=prose."""
    monkeypatch.setenv("PG_PROVENANCE_REANCHOR", "1")
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    _install_judge(monkeypatch, _FakeJudge("hba1c reduction of 1.5 percent"))

    admin = "Adults were enrolled at five sites."
    title = " HbA1c Reduction Of 1.5 Percent In Adults: Trial Result."
    prose = " The treatment produced an hba1c reduction of 1.5 percent in enrolled adults overall."
    direct_quote = admin + title + prose
    pool = {"ev_k": {"direct_quote": direct_quote}}
    wrong_end = len(admin)  # cite the admin clause (no support there) -> recovery fires
    draft = (
        f"Treatment produced an HbA1c reduction of 1.5 percent in adults "
        f"[#ev:ev_k:0-{wrong_end}]."
    )

    title_start = len(admin)
    prose_start = len(admin) + len(title)

    # --- flag OFF (first-passing): binds the earlier TITLE segment ---
    monkeypatch.delenv("PG_SPAN_RESOLVER", raising=False)
    reset_reanchor_telemetry()
    rep_off = strict_verify(draft, pool)
    assert rep_off.total_kept == 1
    off_warn = rep_off.kept_sentences[0].soft_warnings
    assert any(w.startswith("reanchored:ev_k:") for w in off_warn)
    off_s, off_e = _argmax_offsets(off_warn)
    assert "Trial Result" in direct_quote[off_s:off_e], "first-passing should bind the title segment"
    assert get_reanchor_telemetry()["reanchor_argmax_recovered"] == 0

    # --- flag ON (argmax): binds the PROSE segment, labeled q=prose ---
    monkeypatch.setenv("PG_SPAN_RESOLVER", "1")
    reset_reanchor_telemetry()
    rep_on = strict_verify(draft, pool)
    assert rep_on.total_kept == 1
    on_warn = rep_on.kept_sentences[0].soft_warnings
    assert any(w.startswith("reanchored_argmax:ev_k:") and ":q=prose:" in w for w in on_warn), on_warn
    on_s, on_e = _argmax_offsets(on_warn)
    assert "the treatment produced" in direct_quote[on_s:on_e].lower(), "argmax should bind the prose span"
    assert on_s != off_s, "argmax must pick a DIFFERENT (better) span than first-passing"
    assert get_reanchor_telemetry()["reanchor_argmax_recovered"] == 1
