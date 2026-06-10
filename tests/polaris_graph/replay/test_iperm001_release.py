"""I-perm-001 (#1195) keystone slice 1 — WITHHOLD -> ALWAYS-RELEASE + LABEL.

Proves the release-policy BLOCK->LABEL transform on the real saved drb_76 run (offline) + the
no-fabrication hard line and the clinical safety floor on synthetic decisions. DEFAULT OFF is
byte-identical to the legacy withhold decision.
"""

from __future__ import annotations

from src.polaris_graph.roles.release_policy import (
    ReleaseDecision,
    compute_release_outcome,
)

from tests.polaris_graph.replay.d8_replay_harness import replay_release_outcome
from tests.polaris_graph.replay.saved_run_loader import load_saved_run


def _decision(*, release_allowed, held_reasons, fabricated=False, needs_rewrite=None):
    return ReleaseDecision(
        release_allowed=release_allowed,
        held_reasons=list(held_reasons),
        gaps=[],
        needs_rewrite=list(needs_rewrite or []),
        fabricated_occurrence_latched=fabricated,
    )


# --- real drb_76 via the harness ------------------------------------------------------------


def test_off_is_legacy_byte_identical():
    """PG_ALWAYS_RELEASE OFF reproduces the legacy withhold decision: drb_76 stays held."""
    run = load_saved_run()
    out = replay_release_outcome(run, always_release=False)
    assert out.released is False
    assert out.normal_release_blocked is True
    assert out.status == "abort_four_role_release_held"


def test_on_releases_drb76_as_insufficient_safety():
    """PG_ALWAYS_RELEASE ON: drb_76 RELEASES (no longer a hard withhold). The only required S0
    safety category (contraindications) is uncredited under the current literal gate, so the
    clinical safety floor ships the honest insufficient-safety report (blocked NORMAL render),
    NOT a hard block. I-perm-002 (semantic contraindication credit) later flips this to a normal
    caveated release."""
    run = load_saved_run()
    out = replay_release_outcome(run, always_release=True)
    assert out.released is True  # a report ships
    assert out.hard_block is False  # NOT the no-fabrication hard line (23 verified, evidence present)
    assert out.safety_floor == "insufficient"
    assert out.normal_release_blocked is True
    assert out.status == "released_insufficient_safety_evidence"
    # The legacy held_reasons are now DISPLAYED disclosed gaps, not blockers.
    assert "d8_s0_must_cover_missing:contraindications" in out.disclosed_gaps
    assert out.release_quality_score == 0.40  # displayed coverage, same value


# --- the no-fabrication hard line (synthetic) -----------------------------------------------


def test_fabricated_is_always_hard_block():
    out = compute_release_outcome(
        _decision(release_allowed=False, held_reasons=["d8_fabricated_occurrence"], fabricated=True),
        zero_verified=False,
        zero_usable_evidence=False,
        safety_floor_insufficient=False,
        coverage_fraction=0.9,
        always_release=True,
    )
    assert out.hard_block is True
    assert out.released is False
    assert "d8_fabricated_occurrence" in out.hard_block_reasons
    assert out.status != "released_with_disclosed_gaps"


def test_zero_grounding_is_hard_block():
    out = compute_release_outcome(
        _decision(release_allowed=False, held_reasons=["d8_unsupported_residual_below_coverage"]),
        zero_verified=True,
        zero_usable_evidence=True,
        safety_floor_insufficient=False,
        coverage_fraction=0.0,
        always_release=True,
    )
    assert out.hard_block is True
    assert out.released is False
    assert out.status == "abort_no_verified_sections"
    assert "zero_grounding" in out.hard_block_reasons


def test_non_hard_holds_become_disclosed_gaps_and_release():
    out = compute_release_outcome(
        _decision(
            release_allowed=False,
            held_reasons=["d8_unsupported_residual_below_coverage", "d8_pending_rewrite"],
        ),
        zero_verified=False,
        zero_usable_evidence=False,
        safety_floor_insufficient=False,
        coverage_fraction=0.43,
        always_release=True,
    )
    assert out.released is True
    assert out.hard_block is False
    assert out.normal_release_blocked is False
    assert out.status == "released_with_disclosed_gaps"
    assert set(out.disclosed_gaps) == {
        "d8_unsupported_residual_below_coverage",
        "d8_pending_rewrite",
    }


def test_clean_decision_is_success():
    out = compute_release_outcome(
        _decision(release_allowed=True, held_reasons=[]),
        zero_verified=False,
        zero_usable_evidence=False,
        safety_floor_insufficient=False,
        coverage_fraction=0.95,
        always_release=True,
    )
    assert out.released is True
    assert out.status == "success"
    assert out.disclosed_gaps == []


def test_zero_verified_but_evidence_present_is_not_hard_block():
    """zero_verified ALONE is not a hard block — only zero_verified AND zero_usable_evidence."""
    out = compute_release_outcome(
        _decision(release_allowed=False, held_reasons=["d8_unsupported_residual_below_coverage"]),
        zero_verified=True,
        zero_usable_evidence=False,  # evidence WAS fetched, just nothing verified yet
        safety_floor_insufficient=False,
        coverage_fraction=0.0,
        always_release=True,
    )
    assert out.hard_block is False
    assert out.released is True
