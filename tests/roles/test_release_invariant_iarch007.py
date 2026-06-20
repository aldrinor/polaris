"""iarch007 FIX-RELEASE regression suite for the A18 hard release-invariant + A2-seam floor.

Covers the three FIX-RELEASE hardenings (Codex iarch007 RELEASE verdict P0/P1):
  * P0 seam-screen floor: ``fabrication_screen_ran=None``/unknown WITHHOLDS the body (never
    treated as a passed screen).
  * P1 ``assert_release_invariant`` strengthening:
    - prefix-aware seam-gap detection (the bare constant AND the descriptive runtime form);
    - adjudicated-by-default CONTRADICTION (seam gap present + adjudicated=True -> RAISE);
    - leg-3 (compensating screen) COUPLED to the specific seam gap (a bare screen flag without
      the disclosure is NOT proof);
  * A coherent runtime seam outcome (the exact shape ``build_seam_release_outcome`` emits) must
    PASS the invariant — the false-reject guard against blocking all real releases.

No network, no spend — pure functions over dataclasses.
"""

from __future__ import annotations

import pytest

from src.polaris_graph.roles.release_policy import (
    STATUS_RELEASED_INSUFFICIENT_SAFETY,
    STATUS_RELEASED_WITH_DISCLOSED_GAPS,
    STATUS_SUCCESS,
    ReleaseDecision,
    ReleaseInvariantError,
    ReleaseOutcome,
    _GAP_FOUR_ROLE_SEAM_UNADJUDICATED,
    _has_seam_unadjudicated_gap,
    assert_release_invariant,
    compute_release_outcome,
)

# The descriptive runtime form that scripts/run_honest_sweep_r3.build_seam_release_outcome appends.
_RUNTIME_SEAM_GAP = (
    f"{_GAP_FOUR_ROLE_SEAM_UNADJUDICATED}: the four-role D8 judge could not be reached "
    "(judge HTTP 400); the report below was NOT final-adjudicated by the judge."
)


def _seam_outcome(
    *,
    adjudicated: bool,
    body_withheld: bool,
    compensating_screen_passed: bool,
    disclosed_gaps: list[str],
    status: str = STATUS_RELEASED_WITH_DISCLOSED_GAPS,
    released: bool = True,
) -> ReleaseOutcome:
    return ReleaseOutcome(
        released=released,
        hard_block=False,
        normal_release_blocked=body_withheld,
        status=status,
        disclosed_gaps=disclosed_gaps,
        hard_block_reasons=[],
        release_quality_score=0.5,
        safety_floor="ok",
        adjudicated=adjudicated,
        body_withheld=body_withheld,
        compensating_screen_passed=compensating_screen_passed,
    )


# ── prefix-aware seam-gap detection ─────────────────────────────────────────────────────────


def test_has_seam_gap_bare_constant():
    assert _has_seam_unadjudicated_gap([_GAP_FOUR_ROLE_SEAM_UNADJUDICATED]) is True


def test_has_seam_gap_runtime_descriptive_form():
    # The exact shape build_seam_release_outcome emits — prefix-aware match must catch it.
    assert _has_seam_unadjudicated_gap([_RUNTIME_SEAM_GAP]) is True


def test_has_seam_gap_rejects_arbitrary_gap():
    assert _has_seam_unadjudicated_gap(["some_other_disclosed_gap", "coverage_shortfall"]) is False


def test_has_seam_gap_rejects_substring_without_label_prefix():
    # A gap that merely CONTAINS the label as a substring (not a prefix) is NOT the seam gap.
    assert _has_seam_unadjudicated_gap(["note: four_role_seam_unadjudicated happened"]) is False


# ── adjudicated-by-default CONTRADICTION ────────────────────────────────────────────────────


def test_seam_gap_with_adjudicated_true_raises_bare():
    """The default-True-on-seam leak: seam gap present but adjudicated=True -> fail closed."""
    outcome = _seam_outcome(
        adjudicated=True,  # the leak
        body_withheld=False,
        compensating_screen_passed=True,
        disclosed_gaps=[_GAP_FOUR_ROLE_SEAM_UNADJUDICATED],
    )
    with pytest.raises(ReleaseInvariantError):
        assert_release_invariant(outcome)


def test_seam_gap_with_adjudicated_true_raises_runtime_form():
    """Same contradiction, but with the DESCRIPTIVE runtime gap form (prefix-aware)."""
    outcome = _seam_outcome(
        adjudicated=True,
        body_withheld=False,
        compensating_screen_passed=True,
        disclosed_gaps=[_RUNTIME_SEAM_GAP],
    )
    with pytest.raises(ReleaseInvariantError):
        assert_release_invariant(outcome)


# ── coherent runtime seam outcome must PASS (false-reject guard) ─────────────────────────────


def test_runtime_seam_body_ships_passes():
    """The exact shape build_seam_release_outcome emits when the body ships (screen clean):
    adjudicated=False, body_withheld=False, compensating_screen_passed=True, prefixed seam gap.
    This MUST pass — false-rejecting it would block every real runtime seam release."""
    outcome = _seam_outcome(
        adjudicated=False,
        body_withheld=False,
        compensating_screen_passed=True,
        disclosed_gaps=[_RUNTIME_SEAM_GAP],
    )
    assert assert_release_invariant(outcome) is outcome


def test_runtime_seam_body_withheld_passes():
    """Seam with the body WITHHELD (screen could not run / found fabrication) passes via leg-2."""
    outcome = _seam_outcome(
        adjudicated=False,
        body_withheld=True,
        compensating_screen_passed=False,
        disclosed_gaps=[_RUNTIME_SEAM_GAP, "four_role_seam_fabrication_screen_unavailable"],
        status=STATUS_RELEASED_WITH_DISCLOSED_GAPS,
    )
    assert assert_release_invariant(outcome) is outcome


def test_runtime_seam_insufficient_safety_passes():
    """Clinical seam insufficient-safety variant (body ships, screen clean) passes."""
    outcome = _seam_outcome(
        adjudicated=False,
        body_withheld=False,
        compensating_screen_passed=True,
        disclosed_gaps=[_RUNTIME_SEAM_GAP],
        status=STATUS_RELEASED_INSUFFICIENT_SAFETY,
    )
    outcome.safety_floor = "insufficient"
    outcome.normal_release_blocked = True
    assert assert_release_invariant(outcome) is outcome


# ── leg-3 COUPLED to the specific seam gap ──────────────────────────────────────────────────


def test_compensating_flag_without_seam_gap_raises():
    """A bare compensating_screen_passed=True WITHOUT the seam disclosure is NOT proof (item 2):
    un-judged prose with no withheld body and no DISCLOSED seam -> fail closed."""
    outcome = _seam_outcome(
        adjudicated=False,
        body_withheld=False,
        compensating_screen_passed=True,
        disclosed_gaps=["coverage_shortfall"],  # arbitrary gap, NOT the seam label
    )
    with pytest.raises(ReleaseInvariantError):
        assert_release_invariant(outcome)


def test_unjudged_no_proof_raises():
    """adjudicated=False, body not withheld, no compensating screen, no seam gap -> fail closed."""
    outcome = _seam_outcome(
        adjudicated=False,
        body_withheld=False,
        compensating_screen_passed=False,
        disclosed_gaps=[],
    )
    with pytest.raises(ReleaseInvariantError):
        assert_release_invariant(outcome)


# ── SUCCESS terminal unchanged + non-release statuses untouched ──────────────────────────────


def test_success_adjudicated_clean_passes():
    outcome = ReleaseOutcome(
        released=True, hard_block=False, normal_release_blocked=False,
        status=STATUS_SUCCESS, disclosed_gaps=[], hard_block_reasons=[],
        release_quality_score=1.0, safety_floor="ok",
        adjudicated=True, body_withheld=False, compensating_screen_passed=False,
    )
    assert assert_release_invariant(outcome) is outcome


def test_success_with_seam_gap_raises():
    """SUCCESS may not carry the seam gap (contradiction check fires before the SUCCESS leg)."""
    outcome = ReleaseOutcome(
        released=True, hard_block=False, normal_release_blocked=False,
        status=STATUS_SUCCESS, disclosed_gaps=[_GAP_FOUR_ROLE_SEAM_UNADJUDICATED],
        hard_block_reasons=[], release_quality_score=1.0, safety_floor="ok",
        adjudicated=True, body_withheld=False, compensating_screen_passed=False,
    )
    with pytest.raises(ReleaseInvariantError):
        assert_release_invariant(outcome)


def test_non_release_status_untouched():
    outcome = ReleaseOutcome(
        released=False, hard_block=True, normal_release_blocked=True,
        status="abort_no_verified_sections", disclosed_gaps=[], hard_block_reasons=["zero_grounding"],
        release_quality_score=0.0, safety_floor="ok",
        adjudicated=False, body_withheld=False, compensating_screen_passed=False,
    )
    assert assert_release_invariant(outcome) is outcome


# ── P0 seam-screen floor via compute_release_outcome (None/unknown WITHHOLDS) ────────────────


def _seam_decision() -> ReleaseDecision:
    # A clean decision (no fabricated latch, no held reasons) so only the seam disposition governs.
    return ReleaseDecision(
        release_allowed=True,
        held_reasons=[],
        gaps=[],
        needs_rewrite=[],
        fabricated_occurrence_latched=False,
    )


def test_seam_screen_ran_none_withholds_body():
    """P0: fabrication_screen_ran=None (default/unknown) -> body WITHHELD (never passed)."""
    outcome = compute_release_outcome(
        _seam_decision(),
        zero_verified=False, zero_usable_evidence=False,
        safety_floor_insufficient=False, coverage_fraction=0.8,
        always_release=True, redaction_active=True,
        seam_unadjudicated=True, fabrication_screen_ran=None,
    )
    assert outcome.body_withheld is True
    assert outcome.compensating_screen_passed is False
    assert _has_seam_unadjudicated_gap(outcome.disclosed_gaps)
    # The withhold must never be silent -> the unavailable-screen gap is disclosed.
    assert "four_role_seam_fabrication_screen_unavailable" in outcome.disclosed_gaps
    # And it must still pass the invariant (leg-2: body withheld).
    assert assert_release_invariant(outcome) is outcome


def test_seam_screen_ran_false_withholds_body():
    """fabrication_screen_ran=False (could not run) -> body WITHHELD."""
    outcome = compute_release_outcome(
        _seam_decision(),
        zero_verified=False, zero_usable_evidence=False,
        safety_floor_insufficient=False, coverage_fraction=0.8,
        always_release=True, redaction_active=True,
        seam_unadjudicated=True, fabrication_screen_ran=False,
    )
    assert outcome.body_withheld is True
    assert outcome.compensating_screen_passed is False


def test_seam_screen_ran_true_clean_ships_body():
    """Only an EXPLICIT True (screen ran clean) ships the body (compensating_screen_passed)."""
    outcome = compute_release_outcome(
        _seam_decision(),
        zero_verified=False, zero_usable_evidence=False,
        safety_floor_insufficient=False, coverage_fraction=0.8,
        always_release=True, redaction_active=True,
        seam_unadjudicated=True, fabrication_screen_ran=True,
        fabrication_screen_found_fabrication=False,
    )
    assert outcome.body_withheld is False
    assert outcome.compensating_screen_passed is True
    assert outcome.adjudicated is False
    assert assert_release_invariant(outcome) is outcome


def test_seam_clinical_safety_floor_clean_screen_ships_with_disclosure():
    """ALWAYS-RELEASE (operator-locked: the verifier is a LABEL, never a HOLD): a CLINICAL safety-floor
    seam with a CLEAN fabrication screen SHIPS the body — the unadjudicated state is DISCLOSED so the
    user judges, NOT withheld. safety_floor_insufficient is a label on the run, not a gate. (Corrects
    an earlier wrong withhold; reverted per operator 2026-06-20.)"""
    outcome = compute_release_outcome(
        _seam_decision(),
        zero_verified=False, zero_usable_evidence=False,
        safety_floor_insufficient=True, coverage_fraction=0.8,
        always_release=True, redaction_active=True,
        seam_unadjudicated=True, fabrication_screen_ran=True,
        fabrication_screen_found_fabrication=False,
    )
    # The body SHIPS (always-release) — the clean screen is a compensating pass; the safety floor is a
    # LABEL, not a withhold.
    assert outcome.released is True
    assert outcome.body_withheld is False
    assert outcome.compensating_screen_passed is True
    assert outcome.adjudicated is False
    assert outcome.safety_floor == "insufficient"
    # The unadjudicated state is honestly DISCLOSED so the user judges.
    assert _has_seam_unadjudicated_gap(outcome.disclosed_gaps)
    assert assert_release_invariant(outcome) is outcome


def test_seam_screen_ran_true_found_fabrication_withholds_body():
    """Screen ran but FOUND a fabricated identity -> body WITHHELD (conservative)."""
    outcome = compute_release_outcome(
        _seam_decision(),
        zero_verified=False, zero_usable_evidence=False,
        safety_floor_insufficient=False, coverage_fraction=0.8,
        always_release=True, redaction_active=True,
        seam_unadjudicated=True, fabrication_screen_ran=True,
        fabrication_screen_found_fabrication=True,
    )
    assert outcome.body_withheld is True
    assert outcome.compensating_screen_passed is False
