"""M-46 tests: selector no-bypass when pool_size <= max_rows.

V27 forensic finding: selector short-circuited when pool=422 <
max_rows=600, bypassing M-42e/c/d floor reservations and telemetry.
Codex V28 plan pass-2 APPROVED the selector-level fix (not just a
launcher knob).

Expected post-M-46 behavior in short-pool mode:
  1. All rows returned (no truncation, same as pre-M-46)
  2. Rows ordered by priority class: M-42e primary → M-42c mechanism
     → M-42d HC → rest by (tier priority, -score, index)
  3. Notes include m42e_primary_floor / m42c_mechanism_floor /
     m42d_hc_quota_expand entries when applicable
  4. Backwards-compatible: pools without floors configured still work
     with just the pool_size<=max_rows note
"""
from __future__ import annotations

import pytest

from src.polaris_graph.retrieval.evidence_selector import (
    select_evidence_for_generation,
)


def _row(
    ev_id: str,
    url: str,
    tier: str,
    title: str = "",
    statement: str = "",
    direct_quote: str = "",
) -> dict:
    return {
        "evidence_id": ev_id,
        "url": url,
        "tier": tier,
        "title": title or f"row {ev_id}",
        "statement": statement or f"evidence for {ev_id}",
        "direct_quote": direct_quote,
    }


class TestM46ShortPoolFloorsFire:
    """Codex pass-2 verbatim acceptance test."""

    def test_pool_smaller_than_max_rows_still_emits_m42e_note(self) -> None:
        """Fixture: 3 T1 primaries (SURPASS-1/2/3) + 2 T1 reviews +
        1 T2 = 6 rows. max_rows=100. Anchors configured.

        Pre-M-46: early-exit → notes=['pool_size<=max_rows ...']
        (no m42e note, no prioritized ordering).

        Post-M-46: notes include m42e_primary_floor entry with
        matched=3 reserved=3."""
        rows = [
            _row("ev_s1", "https://www.nejm.org/doi/10.1056/NEJMoa2107019",
                 "T1", title="SURPASS-1: Tirzepatide monotherapy"),
            _row("ev_s2", "https://www.nejm.org/doi/10.1056/NEJMoa2107519",
                 "T1", title="SURPASS-2: Tirzepatide vs semaglutide"),
            _row("ev_s3", "https://www.thelancet.com/article/S0140-6736(21)01324-6",
                 "T1", title="SURPASS-3: Tirzepatide vs insulin degludec"),
            _row("ev_r1", "https://example.com/review1",
                 "T1", title="Narrative review of incretins"),
            _row("ev_r2", "https://example.com/review2",
                 "T1", title="GLP-1 mechanism review"),
            _row("ev_m1", "https://example.com/meta1",
                 "T2", title="Meta-analysis of tirzepatide"),
        ]
        result = select_evidence_for_generation(
            research_question="tirzepatide efficacy in type 2 diabetes",
            protocol=None,
            classified_sources=[],
            evidence_rows=rows,
            max_rows=100,  # pool(6) << max_rows(100) → short-pool path
            primary_trial_anchors=["SURPASS-1", "SURPASS-2", "SURPASS-3"],
        )

        # Acceptance: m42e note present
        m42e_notes = [n for n in result.notes if "m42e_primary_floor" in n]
        assert m42e_notes, (
            f"M-46 did not emit m42e_primary_floor note in short-pool mode. "
            f"notes={result.notes}"
        )
        assert "matched=3" in m42e_notes[0]
        assert "reserved=3" in m42e_notes[0]

    def test_all_rows_kept_in_short_pool(self) -> None:
        """All rows must remain in output — M-46 only reorders."""
        rows = [
            _row("ev_s1", "https://www.nejm.org/x1",
                 "T1", title="SURPASS-1 primary"),
            _row("ev_r1", "https://example.com/r1", "T1"),
            _row("ev_r2", "https://example.com/r2", "T2"),
        ]
        result = select_evidence_for_generation(
            research_question="tirzepatide",
            protocol=None,
            classified_sources=[],
            evidence_rows=rows,
            max_rows=50,
            primary_trial_anchors=["SURPASS-1"],
        )
        assert len(result.selected_rows) == 3
        assert result.dropped_count == 0

    def test_primary_ordered_before_derivatives(self) -> None:
        """Codex acceptance: reserved primary rows must appear BEFORE
        derivative rows in the selected_rows ordering."""
        rows = [
            _row("ev_r1", "https://example.com/r1",
                 "T1", title="Generic review"),
            _row("ev_r2", "https://example.com/r2",
                 "T1", title="Another review"),
            _row("ev_s1", "https://www.nejm.org/x1",
                 "T1", title="SURPASS-1 primary publication"),
            _row("ev_r3", "https://example.com/r3",
                 "T1", title="Third review"),
        ]
        result = select_evidence_for_generation(
            research_question="tirzepatide",
            protocol=None,
            classified_sources=[],
            evidence_rows=rows,
            max_rows=50,
            primary_trial_anchors=["SURPASS-1"],
        )
        # Primary ev_s1 must be first — reserved class 0.
        assert result.selected_rows[0]["evidence_id"] == "ev_s1", (
            f"primary row not ordered first: "
            f"{[r['evidence_id'] for r in result.selected_rows]}"
        )

    def test_mechanism_rows_ordered_after_primaries(self) -> None:
        """Priority: primary (0) → mechanism (1) → HC (2) → rest (3)."""
        rows = [
            _row("ev_r1", "https://example.com/r1",
                 "T1", title="Plain review"),
            _row("ev_m1", "https://example.com/m1",
                 "T1", title="Receptor pharmacokinetic clamp study",
                 statement="receptor binding affinity and half-life"),
            _row("ev_m2", "https://example.com/m2",
                 "T1", title="Signaling pathway mechanism",
                 statement="pathway kinetic analysis"),
            _row("ev_m3", "https://example.com/m3",
                 "T1", title="Insulin secretion and glucagon signaling",
                 statement="signaling pathway"),
            _row("ev_m4", "https://example.com/m4",
                 "T2", title="Bioavailability metabolism pathway",
                 statement="pharmacokinetic metabolism pathway"),
            _row("ev_s1", "https://www.nejm.org/x1",
                 "T1", title="SURPASS-2 primary"),
        ]
        result = select_evidence_for_generation(
            research_question="tirzepatide",
            protocol=None,
            classified_sources=[],
            evidence_rows=rows,
            max_rows=50,
            primary_trial_anchors=["SURPASS-2"],
        )
        # Expected order prefix: primary (ev_s1), then mechanism rows
        # (any of ev_m1..ev_m4), then rest.
        order = [r["evidence_id"] for r in result.selected_rows]
        assert order[0] == "ev_s1", f"primary not first: {order}"
        # Next two slots occupied by mechanism rows (M-42c reserves 3
        # slots; 4 mech rows present; reserves top 3 by tier+score).
        assert order[1].startswith("ev_m"), f"mech #1 missing: {order}"
        assert order[2].startswith("ev_m"), f"mech #2 missing: {order}"
        # And m42c note present
        m42c_notes = [n for n in result.notes if "m42c_mechanism_floor" in n]
        assert m42c_notes, f"m42c note missing: {result.notes}"

    def test_hc_expansion_telemetry_in_short_pool(self) -> None:
        """M-42d HC quota expansion emits telemetry in short-pool mode."""
        rows = [
            _row("ev_fda1", "https://www.accessdata.fda.gov/drugsatfda/x1",
                 "T3", title="FDA label"),
            _row("ev_hc1", "https://pdf.hres.ca/1.pdf",
                 "T3", title="HC monograph"),
            _row("ev_hc2", "https://canada.ca/recall/2",
                 "T3", title="HC recall"),
            _row("ev_ema1", "https://www.ema.europa.eu/1",
                 "T3", title="EMA EPAR"),
        ]
        result = select_evidence_for_generation(
            research_question="tirzepatide regulatory",
            protocol=None,
            classified_sources=[],
            evidence_rows=rows,
            max_rows=50,
        )
        m42d_notes = [n for n in result.notes if "m42d_hc_quota_expand" in n]
        assert m42d_notes, f"m42d note missing in short pool: {result.notes}"

    def test_backwards_compat_no_anchors_no_notes(self) -> None:
        """Backwards compat: pool without anchors configured still
        returns all rows with just the pool_size note (no m42e/c/d
        notes since floors don't fire)."""
        rows = [
            _row("ev_r1", "https://example.com/r1", "T1"),
            _row("ev_r2", "https://example.com/r2", "T2"),
            _row("ev_r3", "https://example.com/r3", "T4"),
        ]
        result = select_evidence_for_generation(
            research_question="generic",
            protocol=None,
            classified_sources=[],
            evidence_rows=rows,
            max_rows=50,
            primary_trial_anchors=None,
        )
        # All rows kept
        assert len(result.selected_rows) == 3
        # pool_size note present
        assert any("pool_size<=max_rows" in n for n in result.notes)
        # No m42e note (no anchors)
        assert not any("m42e_primary_floor" in n for n in result.notes)
        # No m42c note (no mechanism rows)
        assert not any("m42c_mechanism_floor" in n for n in result.notes)

    def test_m46_ordered_strategy_label(self) -> None:
        """The selection_strategy label changes to reflect the M-46
        ordering so downstream audits can tell the short-pool path
        now does work (instead of silent early-exit)."""
        rows = [
            _row("ev_s1", "https://www.nejm.org/x1",
                 "T1", title="SURPASS-1 primary"),
            _row("ev_r1", "https://example.com/r1", "T1"),
        ]
        result = select_evidence_for_generation(
            research_question="tirzepatide",
            protocol=None,
            classified_sources=[],
            evidence_rows=rows,
            max_rows=50,
            primary_trial_anchors=["SURPASS-1"],
        )
        assert result.selection_strategy == "tier_balanced_v1_all_m46_ordered"


class TestM46NoRegressionOnTruncatingRuns:
    """When pool > max_rows the main branch runs unchanged. Verify no
    regression on the established M-42 tests."""

    def test_truncating_path_still_works(self) -> None:
        """Pool 6 rows, max_rows 3 → truncating path (not M-46 early
        exit). Verify M-42e primary floor still fires."""
        rows = [
            _row("ev_s1", "https://www.nejm.org/x1",
                 "T1", title="SURPASS-1 primary"),
            _row("ev_s2", "https://www.nejm.org/x2",
                 "T1", title="SURPASS-2 primary"),
            _row("ev_r1", "https://example.com/r1", "T1"),
            _row("ev_r2", "https://example.com/r2", "T1"),
            _row("ev_r3", "https://example.com/r3", "T2"),
            _row("ev_r4", "https://example.com/r4", "T4"),
        ]
        result = select_evidence_for_generation(
            research_question="tirzepatide",
            protocol=None,
            classified_sources=[],
            evidence_rows=rows,
            max_rows=3,  # forces truncation
            primary_trial_anchors=["SURPASS-1", "SURPASS-2"],
        )
        # Truncating path: selection_strategy != M-46 label
        assert result.selection_strategy != "tier_balanced_v1_all_m46_ordered"
        # M-42e note still emitted (main-branch telemetry)
        m42e_notes = [n for n in result.notes if "m42e_primary_floor" in n]
        assert m42e_notes, f"m42e lost on truncating path: {result.notes}"


class TestM46TelemetryStability:
    """Ensure M-46 telemetry is stable across runs with identical input."""

    def test_deterministic_ordering(self) -> None:
        """Two runs on same input must produce identical selected_rows
        order."""
        rows = [
            _row("ev_s1", "https://www.nejm.org/x1",
                 "T1", title="SURPASS-1 primary"),
            _row("ev_r1", "https://example.com/r1", "T2"),
            _row("ev_m1", "https://example.com/m1",
                 "T1", title="Receptor pharmacokinetic analysis",
                 statement="receptor binding half-life pharmacokinetic"),
        ]
        # Add 2 more mech rows so floor fires (requires ≥4 mech pool)
        rows.append(_row("ev_m2", "https://example.com/m2",
                         "T1", title="Clamp study mechanism",
                         statement="clamp insulin secretion signaling"))
        rows.append(_row("ev_m3", "https://example.com/m3",
                         "T2", title="Metabolism pathway receptor",
                         statement="metabolism receptor kinetic"))

        r1 = select_evidence_for_generation(
            research_question="tirzepatide",
            protocol=None,
            classified_sources=[],
            evidence_rows=rows,
            max_rows=50,
            primary_trial_anchors=["SURPASS-1"],
        )
        r2 = select_evidence_for_generation(
            research_question="tirzepatide",
            protocol=None,
            classified_sources=[],
            evidence_rows=rows,
            max_rows=50,
            primary_trial_anchors=["SURPASS-1"],
        )
        order1 = [r["evidence_id"] for r in r1.selected_rows]
        order2 = [r["evidence_id"] for r in r2.selected_rows]
        assert order1 == order2
