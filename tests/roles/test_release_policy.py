"""Contract tests for the D8 production release policy (I-meta-002 sub-PR-3).

Properties under test (clinical occurrence/residual split):
- FABRICATED occurrence-gates and the latch holds even with rewrite_already_attempted=True;
- the latch PERSISTS across passes — prior_fabricated_latched=True holds release even when
  THIS pass is all clean (no laundering), and the decision threads the latch forward;
- a row arriving already stamped verdict=="FABRICATED" (fabricated identity stamped upstream)
  occurrence-gates;
- UNSUPPORTED routes to needs_rewrite first, then residual-gates only when the CoverageLedger
  fraction < threshold;
- dropping a covered claim LOWERS the ledger fraction (fixed denominator) and so does NOT
  dodge the residual gate;
- a material verdict=="UNREACHABLE" fetch-miss routes to needs_rewrite then a visible gap
  (never silently passed);
- S0 must-cover missing holds regardless of coverage, driven by D8ClaimRow.s0_categories, and
  a PARTIAL/citation-only claim in a required category does NOT satisfy it (only VERIFIED);
- PARTIAL S0 -> advisory gap after the attempt;
- to_gaps_json shape;
- the config loader reads the yaml.
Pure logic, no model, no network.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.polaris_graph.roles.release_policy import (
    CoverageLedger,
    D8ClaimRow,
    Gap,
    ReleaseDecision,
    apply_d8_release_policy,
    load_d8_policy_config,
    to_gaps_json,
)

_THRESHOLD = 0.70


def _full_ledger() -> CoverageLedger:
    """A ledger at fraction 1.0 (all required elements covered)."""
    return CoverageLedger(
        required_element_ids=["e1", "e2"],
        covered_element_ids={"e1", "e2"},
    )


def _empty_ledger() -> CoverageLedger:
    """A ledger with no required elements -> fraction 1.0 by definition."""
    return CoverageLedger(required_element_ids=[], covered_element_ids=set())


# --- (a) FABRICATED occurrence latch -----------------------------------------------------
def test_fabricated_occurrence_gates_when_stamped_upstream() -> None:
    rows = [
        D8ClaimRow(claim_id="c1", severity="S0", verdict="FABRICATED", citation_id="fake-1"),
    ]
    decision = apply_d8_release_policy(
        rows,
        required_s0_categories=[],
        coverage_ledger=_empty_ledger(),
        coverage_threshold=_THRESHOLD,
        rewrite_already_attempted=False,
    )
    assert decision.release_allowed is False
    assert "d8_fabricated_occurrence" in decision.held_reasons
    assert decision.fabricated_occurrence_latched is True


def test_fabricated_holds_even_after_rewrite_attempt() -> None:
    rows = [D8ClaimRow(claim_id="c1", severity="S1", verdict="FABRICATED")]
    decision = apply_d8_release_policy(
        rows,
        required_s0_categories=[],
        coverage_ledger=_empty_ledger(),
        coverage_threshold=_THRESHOLD,
        rewrite_already_attempted=True,  # does NOT clear the occurrence gate
    )
    assert decision.release_allowed is False
    assert "d8_fabricated_occurrence" in decision.held_reasons
    assert decision.fabricated_occurrence_latched is True


def test_latch_persists_across_clean_pass_no_laundering() -> None:
    # A later, all-clean pass cannot launder an earlier fabrication.
    clean_rows = [
        D8ClaimRow(claim_id="c1", severity="S0", verdict="VERIFIED"),
        D8ClaimRow(claim_id="c2", severity="S1", verdict="VERIFIED"),
    ]
    decision = apply_d8_release_policy(
        clean_rows,
        required_s0_categories=[],
        coverage_ledger=_full_ledger(),
        coverage_threshold=_THRESHOLD,
        rewrite_already_attempted=True,
        prior_fabricated_latched=True,  # carried in from an earlier pass
    )
    assert decision.release_allowed is False
    assert "d8_fabricated_occurrence" in decision.held_reasons
    # The latch is threaded forward so the caller persists it.
    assert decision.fabricated_occurrence_latched is True


def test_s3_fabricated_does_not_latch() -> None:
    # S3 is observe-only; an S3 FABRICATED is not material and must not occurrence-gate.
    rows = [D8ClaimRow(claim_id="c1", severity="S3", verdict="FABRICATED")]
    decision = apply_d8_release_policy(
        rows,
        required_s0_categories=[],
        coverage_ledger=_empty_ledger(),
        coverage_threshold=_THRESHOLD,
        rewrite_already_attempted=False,
    )
    assert decision.fabricated_occurrence_latched is False
    assert "d8_fabricated_occurrence" not in decision.held_reasons


# --- (b) UNSUPPORTED residual ------------------------------------------------------------
def test_unsupported_routes_to_needs_rewrite_first() -> None:
    rows = [D8ClaimRow(claim_id="c1", severity="S1", verdict="UNSUPPORTED")]
    decision = apply_d8_release_policy(
        rows,
        required_s0_categories=[],
        coverage_ledger=_full_ledger(),
        coverage_threshold=_THRESHOLD,
        rewrite_already_attempted=False,
    )
    assert "c1" in decision.needs_rewrite
    # No residual gate before the rewrite attempt.
    assert "d8_unsupported_residual_below_coverage" not in decision.held_reasons


def test_unsupported_residual_gates_only_when_below_coverage() -> None:
    rows = [D8ClaimRow(claim_id="c1", severity="S1", verdict="UNSUPPORTED")]
    # Above threshold (1.0) -> ships with a visible residual gap, no hold.
    above = apply_d8_release_policy(
        rows,
        required_s0_categories=[],
        coverage_ledger=_full_ledger(),
        coverage_threshold=_THRESHOLD,
        rewrite_already_attempted=True,
    )
    assert above.release_allowed is True
    assert "d8_unsupported_residual_below_coverage" not in above.held_reasons
    assert any(g.kind == "residual_unsupported" for g in above.gaps)

    # Below threshold (0.5) -> hold.
    low_ledger = CoverageLedger(
        required_element_ids=["e1", "e2"], covered_element_ids={"e1"}
    )
    below = apply_d8_release_policy(
        rows,
        required_s0_categories=[],
        coverage_ledger=low_ledger,
        coverage_threshold=_THRESHOLD,
        rewrite_already_attempted=True,
    )
    assert below.release_allowed is False
    assert "d8_unsupported_residual_below_coverage" in below.held_reasons


def test_dropping_covered_claim_lowers_fraction_and_does_not_dodge_gate() -> None:
    # Fixed denominator of 4 required elements. Covering all 4 = 1.0 (passes).
    rows = [D8ClaimRow(claim_id="c1", severity="S1", verdict="UNSUPPORTED")]
    full = CoverageLedger(
        required_element_ids=["e1", "e2", "e3", "e4"],
        covered_element_ids={"e1", "e2", "e3", "e4"},
    )
    passes = apply_d8_release_policy(
        rows,
        required_s0_categories=[],
        coverage_ledger=full,
        coverage_threshold=_THRESHOLD,
        rewrite_already_attempted=True,
    )
    assert passes.release_allowed is True

    # Drop 2 covered elements: numerator shrinks, denominator FIXED at 4 -> 0.5 < 0.70.
    dropped = CoverageLedger(
        required_element_ids=["e1", "e2", "e3", "e4"],
        covered_element_ids={"e1", "e2"},
    )
    assert dropped.fraction() == pytest.approx(0.5)
    gated = apply_d8_release_policy(
        rows,
        required_s0_categories=[],
        coverage_ledger=dropped,
        coverage_threshold=_THRESHOLD,
        rewrite_already_attempted=True,
    )
    assert gated.release_allowed is False
    assert "d8_unsupported_residual_below_coverage" in gated.held_reasons


# --- (b2) genuine UNREACHABLE residual ---------------------------------------------------
def test_unreachable_routes_to_needs_rewrite_then_visible_gap() -> None:
    rows = [D8ClaimRow(claim_id="c1", severity="S1", verdict="UNREACHABLE")]
    pre = apply_d8_release_policy(
        rows,
        required_s0_categories=[],
        coverage_ledger=_full_ledger(),
        coverage_threshold=_THRESHOLD,
        rewrite_already_attempted=False,
    )
    assert "c1" in pre.needs_rewrite

    post = apply_d8_release_policy(
        rows,
        required_s0_categories=[],
        coverage_ledger=_full_ledger(),
        coverage_threshold=_THRESHOLD,
        rewrite_already_attempted=True,
    )
    # Never silently passed: it surfaces as a visible residual gap with an unreachable note.
    unreachable_gaps = [g for g in post.gaps if g.kind == "residual_unsupported"]
    assert len(unreachable_gaps) == 1
    assert "UNREACHABLE" in unreachable_gaps[0].note


# --- (c) S0 must-cover gate --------------------------------------------------------------
def test_s0_must_cover_missing_holds_regardless_of_coverage() -> None:
    # Coverage fraction is 1.0, but a required S0 category has no VERIFIED claim.
    rows = [
        D8ClaimRow(
            claim_id="c1",
            severity="S0",
            verdict="VERIFIED",
            s0_categories=["dosing_limits"],
        ),
    ]
    decision = apply_d8_release_policy(
        rows,
        required_s0_categories=["dosing_limits", "contraindications"],
        coverage_ledger=_full_ledger(),
        coverage_threshold=_THRESHOLD,
        rewrite_already_attempted=True,
    )
    assert decision.release_allowed is False
    assert "d8_s0_must_cover_missing:contraindications" in decision.held_reasons
    assert "d8_s0_must_cover_missing:dosing_limits" not in decision.held_reasons
    assert any(g.kind == "uncovered_s0" and g.ref == "contraindications" for g in decision.gaps)


def test_s0_partial_or_citation_only_does_not_satisfy_must_cover() -> None:
    # A PARTIAL claim carrying the category does NOT count; only VERIFIED does.
    rows = [
        D8ClaimRow(
            claim_id="c1",
            severity="S0",
            verdict="PARTIAL",
            citation_id="src-1",
            s0_categories=["contraindications"],
        ),
    ]
    decision = apply_d8_release_policy(
        rows,
        required_s0_categories=["contraindications"],
        coverage_ledger=_full_ledger(),
        coverage_threshold=_THRESHOLD,
        rewrite_already_attempted=True,
    )
    assert decision.release_allowed is False
    assert "d8_s0_must_cover_missing:contraindications" in decision.held_reasons


def test_s0_must_cover_satisfied_by_verified_allows_release() -> None:
    rows = [
        D8ClaimRow(
            claim_id="c1",
            severity="S0",
            verdict="VERIFIED",
            s0_categories=["contraindications"],
        ),
    ]
    decision = apply_d8_release_policy(
        rows,
        required_s0_categories=["contraindications"],
        coverage_ledger=_full_ledger(),
        coverage_threshold=_THRESHOLD,
        rewrite_already_attempted=True,
    )
    assert decision.release_allowed is True
    assert decision.held_reasons == []


# --- (d) PARTIAL S0/S1 one-rewrite-then-advisory -----------------------------------------
def test_partial_s0_needs_rewrite_then_advisory_gap() -> None:
    rows = [
        D8ClaimRow(
            claim_id="c1",
            severity="S0",
            verdict="PARTIAL",
            citation_id="src-1",
            s0_categories=["contraindications"],
        ),
    ]
    pre = apply_d8_release_policy(
        rows,
        required_s0_categories=[],
        coverage_ledger=_full_ledger(),
        coverage_threshold=_THRESHOLD,
        rewrite_already_attempted=False,
    )
    assert "c1" in pre.needs_rewrite

    post = apply_d8_release_policy(
        rows,
        required_s0_categories=[],
        coverage_ledger=_full_ledger(),
        coverage_threshold=_THRESHOLD,
        rewrite_already_attempted=True,
    )
    advisory = [g for g in post.gaps if g.kind == "partial_advisory"]
    assert len(advisory) == 1
    assert advisory[0].ref == "c1"


# --- (6) gaps serializer -----------------------------------------------------------------
def test_to_gaps_json_shape() -> None:
    decision = ReleaseDecision(
        release_allowed=False,
        held_reasons=["d8_s0_must_cover_missing:contraindications"],
        gaps=[
            Gap(
                ref="contraindications",
                kind="uncovered_s0",
                severity="S0",
                note="required S0 must-cover category has no VERIFIED claim",
            )
        ],
        needs_rewrite=[],
        fabricated_occurrence_latched=False,
    )
    serialized = to_gaps_json(decision)
    assert serialized == [
        {
            "ref": "contraindications",
            "kind": "uncovered_s0",
            "severity": "S0",
            "note": "required S0 must-cover category has no VERIFIED claim",
        }
    ]


# --- (7) config loader -------------------------------------------------------------------
def test_loader_reads_default_yaml() -> None:
    config = load_d8_policy_config()
    assert config.coverage_threshold == pytest.approx(0.70)
    assert config.material_severities == ["S0", "S1", "S2"]
    assert config.s0_must_cover_categories == [
        "contraindications",
        "dosing_limits",
        "black_box_warnings",
        "pregnancy_renal_hepatic_cautions",
        "regulatory_status",
    ]


def test_loader_raises_on_missing_file() -> None:
    with pytest.raises(FileNotFoundError):
        load_d8_policy_config(Path("does_not_exist_d8_policy.yaml"))


# --- Codex diff iter-1 P1 regressions ----------------------------------------------------
def test_first_pass_pending_rewrite_blocks_release_codex_p1a() -> None:
    """Codex diff P1-a: release_allowed previously ignored needs_rewrite, so a first-pass
    material UNSUPPORTED could release BEFORE the required rewrite attempt. A pass with
    pending rewrites must NOT be releasable."""
    rows = [D8ClaimRow(claim_id="c1", severity="S1", verdict="UNSUPPORTED")]
    decision = apply_d8_release_policy(
        rows,
        required_s0_categories=[],
        coverage_ledger=_full_ledger(),  # coverage fine; the block is the pending rewrite
        coverage_threshold=_THRESHOLD,
        rewrite_already_attempted=False,
    )
    assert "c1" in decision.needs_rewrite
    assert decision.release_allowed is False
    assert "d8_pending_rewrite" in decision.held_reasons


def test_dropped_residual_below_coverage_still_holds_codex_p1b() -> None:
    """Codex diff P1-b: after rewrite_already_attempted=True, DROPPING the residual row left
    no current UNSUPPORTED/UNREACHABLE row, so the old gate (which required a present row) let
    the run release with empty held_reasons despite fixed-ledger coverage 0.25 < 0.70. The
    coverage floor must hold on the ledger alone."""
    # No residual row present this pass (it was dropped/refused upstream), all-clean rows.
    rows = [D8ClaimRow(claim_id="kept", severity="S1", verdict="VERIFIED")]
    dropped_ledger = CoverageLedger(
        required_element_ids=["e1", "e2", "e3", "e4"],
        covered_element_ids={"e1"},  # 1/4 = 0.25 < 0.70
    )
    assert dropped_ledger.fraction() == pytest.approx(0.25)
    decision = apply_d8_release_policy(
        rows,
        required_s0_categories=[],
        coverage_ledger=dropped_ledger,
        coverage_threshold=_THRESHOLD,
        rewrite_already_attempted=True,
    )
    assert decision.release_allowed is False
    assert "d8_unsupported_residual_below_coverage" in decision.held_reasons
    assert any(g.kind == "coverage_shortfall" for g in decision.gaps)
