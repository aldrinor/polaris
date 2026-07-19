"""U26 (I-deepfix-001) — the release-quality scorecard must reflect real deficiencies.

A green scorecard (release_quality_score == 1.0 / display "1.000") previously masked a run whose
evaluator rule-gate returned gate_class=abort (a PT11 uncited-numeric failure) or which left a
required-entity slot empty. These offline tests assert that an abort eval-gate OR an empty required
slot pulls the displayed score strictly below the green floor, and that a genuinely-clean,
adjudicated run stays green. No GPU / network / paid-LLM — pure functions over dict inputs.
"""

from __future__ import annotations

from src.polaris_graph.roles.release_policy import (
    apply_release_quality_scorecard_to_manifest,
    green_quality_floor,
    honest_release_quality_score,
)


# ── the pure score derivation ────────────────────────────────────────────────────────────────

def test_clean_run_stays_green():
    """No deficiency -> the score is returned unchanged and remains green."""
    floor = green_quality_floor()
    score = honest_release_quality_score(1.0)
    assert score == 1.0
    assert score >= floor


def test_abort_eval_gate_pulls_below_green():
    """An abort-class evaluator gate must drop the score strictly below the green floor."""
    floor = green_quality_floor()
    score = honest_release_quality_score(1.0, eval_gate_aborted=True)
    assert score < floor


def test_empty_required_slot_pulls_below_green():
    """A single empty required-entity slot must drop the score strictly below the green floor."""
    floor = green_quality_floor()
    score = honest_release_quality_score(1.0, empty_required_slots=1)
    assert score < floor


def test_more_empty_slots_read_strictly_worse():
    """More empty required slots must never score better than fewer."""
    one = honest_release_quality_score(1.0, empty_required_slots=1)
    three = honest_release_quality_score(1.0, empty_required_slots=3)
    assert three <= one


def test_score_never_raised_above_coverage():
    """The recompute can only lower the score, never raise it above the coverage base."""
    assert honest_release_quality_score(0.4, eval_gate_aborted=True) <= 0.4
    assert honest_release_quality_score(0.4, empty_required_slots=2) <= 0.4


# ── the manifest wiring (mirrors the autopsy'd drb_76 manifest shape) ──────────────────────────

def _green_manifest_with_abort_gate() -> dict:
    """The exact U26 shape: adjudicated green scorecard while the eval gate class is abort."""
    return {
        "evaluator_gate_advisory": {
            "gate_class": "abort",
            "release_allowed": False,
            "rule_blockers": ["PT11"],
        },
        "required_entity_coverage": {
            "total_required": 5,
            "verified": 5,
            "coverage_fraction": 1.0,
        },
        "release_disclosure": {
            "adjudicated": True,
            "release_quality_score": 1.0,
            "release_quality_score_display": "1.000",
            "safety_floor": "ok",
        },
    }


def test_manifest_abort_gate_pulls_scorecard_below_green():
    """The green (1.000) scorecard on an abort-gate run must be lowered below green in the manifest."""
    manifest = _green_manifest_with_abort_gate()
    floor = green_quality_floor()

    apply_release_quality_scorecard_to_manifest(manifest)

    rd = manifest["release_disclosure"]
    assert rd["release_quality_score"] < floor
    assert float(rd["release_quality_score_display"]) < floor
    assert rd["release_quality_deficiency"]["eval_gate_aborted"] is True
    assert rd["release_quality_deficiency"]["base_coverage_fraction"] == 1.0


def test_manifest_empty_required_slot_pulls_scorecard_below_green():
    """An empty contraindication/required slot (verified < total) must drop the scorecard below green."""
    manifest = _green_manifest_with_abort_gate()
    # Clear the eval-gate deficiency so ONLY the empty-slot signal is under test.
    manifest["evaluator_gate_advisory"]["gate_class"] = "pass"
    manifest["required_entity_coverage"]["verified"] = 4  # one empty required slot
    floor = green_quality_floor()

    apply_release_quality_scorecard_to_manifest(manifest)

    rd = manifest["release_disclosure"]
    assert rd["release_quality_score"] < floor
    assert rd["release_quality_deficiency"]["empty_required_slots"] == 1


def test_manifest_clean_adjudicated_run_stays_green():
    """A clean, adjudicated run (pass gate, all slots verified) keeps its green 1.000 score."""
    manifest = _green_manifest_with_abort_gate()
    manifest["evaluator_gate_advisory"]["gate_class"] = "pass"  # no abort
    # 5/5 already verified -> no empty slot
    before = dict(manifest["release_disclosure"])

    apply_release_quality_scorecard_to_manifest(manifest)

    rd = manifest["release_disclosure"]
    assert rd["release_quality_score"] == 1.0
    assert rd["release_quality_score_display"] == before["release_quality_score_display"]
    assert "release_quality_deficiency" not in rd


def test_manifest_unadjudicated_display_preserved():
    """An unadjudicated outcome keeps its honest N/A display and is not re-scored to a bare number."""
    manifest = _green_manifest_with_abort_gate()
    manifest["release_disclosure"]["adjudicated"] = False
    manifest["release_disclosure"]["release_quality_score_display"] = "N/A (D8 unadjudicated)"

    apply_release_quality_scorecard_to_manifest(manifest)

    rd = manifest["release_disclosure"]
    assert rd["release_quality_score_display"] == "N/A (D8 unadjudicated)"
    assert "release_quality_deficiency" not in rd


def test_manifest_without_release_disclosure_is_noop():
    """The legacy always-release-OFF path (no release_disclosure) is left byte-identical."""
    manifest = {"evaluator_gate_advisory": {"gate_class": "abort"}}
    apply_release_quality_scorecard_to_manifest(manifest)
    assert manifest == {"evaluator_gate_advisory": {"gate_class": "abort"}}
