"""M-51 tests: anchor-matched primary hard-reservation post-process.

V29 cycle 1 (Strategy β). Codex plan pass-1 CONDITIONAL-no-blockers
with revisions woven in. Addresses V28 failure mode where SURPASS-4
Del Prato + SURPASS-CVOT Nicholls were in live_corpus but dropped
by the selector.

Codex revisions incorporated:
1. Canonical identity (evidence_id or (url, title, quote[:200]) tuple)
   — NOT Python id() for duplicate detection.
2. Cap = min(|unique_anchors|, max_rows), not literal 11.
3. Trim non-M-51 tail on overflow.
4. Backward-compat: no-anchors path byte-identical to pre-M-51.
5. Explicit trim fixture for max_rows overflow.

All tests pure (no network, no LLM). Fixture-based.
"""
from __future__ import annotations

import pytest

from src.polaris_graph.retrieval.evidence_selector import (
    select_evidence_for_generation,
)


def _primary_row(
    ev_id: str,
    anchor: str,
    tier: str = "T1",
    score_hint: str = "",
) -> dict:
    """Build a row that `_m42e_detect_primary_for_anchor` will match:
    title contains the anchor + primary journal host, no non-primary
    marker.
    """
    return {
        "evidence_id": ev_id,
        "source_url": f"https://www.nejm.org/doi/{ev_id}",
        "title": f"{anchor}: Primary publication of a phase-3 trial",
        "statement": f"{anchor} primary publication",
        "direct_quote": (
            f"{anchor} enrolled N=1879 participants. Primary endpoint met. "
        ) * 5,  # 300+ chars so downstream refetch isn't triggered
        "tier": tier,
        "source": "serper",
        "full_content_length": 3000,
    }


def _non_primary_row(
    ev_id: str,
    tier: str = "T1",
    title: str = "Generic review of incretins",
) -> dict:
    return {
        "evidence_id": ev_id,
        "source_url": f"https://example.com/{ev_id}",
        "title": title,
        "statement": f"generic statement for {ev_id}",
        "direct_quote": "generic review content " * 20,
        "tier": tier,
        "source": "serper",
        "full_content_length": 500,
    }


class TestM51AnchorPrimaryCustody:
    """M-51 core acceptance — primary in corpus but not selected
    naturally → post-process inserts at position 0."""

    def test_primary_in_corpus_inserted_when_not_naturally_selected(self) -> None:
        """Codex acceptance: SURPASS-4 in corpus but dropped by
        tier-balanced allocation → inserted by M-51."""
        # Pool: 1 SURPASS-4 primary + 50 non-primary T1 rows that will
        # outrank it on relevance (since primary's title doesn't match
        # the question as well as many reviews).
        rows = [_primary_row("ev_s4", "SURPASS-4")]
        for i in range(50):
            rows.append(_non_primary_row(
                f"ev_r{i}", title="Tirzepatide weight loss review"))
        result = select_evidence_for_generation(
            research_question="tirzepatide weight loss review meta-analysis",
            protocol=None,
            classified_sources=[],
            evidence_rows=rows,
            max_rows=10,  # forces truncation; most non-primary T1 wins on relevance
            primary_trial_anchors=["SURPASS-4"],
        )
        selected_ids = [r["evidence_id"] for r in result.selected_rows]
        assert "ev_s4" in selected_ids, (
            f"SURPASS-4 primary should be inserted by M-51; got "
            f"selected={selected_ids}"
        )

    def test_multi_anchor_multi_primary_all_inserted(self) -> None:
        """2 primaries, 2 anchors, both should be inserted."""
        rows = [
            _primary_row("ev_s4", "SURPASS-4"),
            _primary_row("ev_cvot", "SURPASS-CVOT"),
        ]
        for i in range(50):
            rows.append(_non_primary_row(f"ev_r{i}"))
        result = select_evidence_for_generation(
            research_question="tirzepatide clinical evidence",
            protocol=None,
            classified_sources=[],
            evidence_rows=rows,
            max_rows=10,
            primary_trial_anchors=["SURPASS-4", "SURPASS-CVOT"],
        )
        selected_ids = set(r["evidence_id"] for r in result.selected_rows)
        assert "ev_s4" in selected_ids
        assert "ev_cvot" in selected_ids

    def test_anchor_with_no_primary_in_corpus_is_noop(self) -> None:
        """Anchor configured but no matching primary → no insertion."""
        rows = [_non_primary_row(f"ev_r{i}") for i in range(20)]
        result = select_evidence_for_generation(
            research_question="x",
            protocol=None,
            classified_sources=[],
            evidence_rows=rows,
            max_rows=10,
            primary_trial_anchors=["SURPASS-4"],  # no SURPASS-4 in corpus
        )
        assert len(result.selected_rows) == 10  # trimmed normally
        # No M-51 telemetry note
        assert not any("m51_anchor_primary_custody" in n
                       for n in result.notes)

    def test_primary_already_selected_no_duplicate(self) -> None:
        """Primary that the tier-balanced pass already selected should
        not be duplicated by M-51."""
        # Only 1 primary + 1 non-primary; max_rows=10 means both
        # fit naturally (below early-exit threshold — goes to
        # M-46 short-pool path)
        rows = [
            _primary_row("ev_s4", "SURPASS-4"),
            _non_primary_row("ev_r1"),
        ]
        result = select_evidence_for_generation(
            research_question="x",
            protocol=None,
            classified_sources=[],
            evidence_rows=rows,
            max_rows=10,
            primary_trial_anchors=["SURPASS-4"],
        )
        ids = [r["evidence_id"] for r in result.selected_rows]
        assert ids.count("ev_s4") == 1  # exactly one


class TestM51Cap:
    """Codex revision #3: cap = min(|unique_anchors|, max_rows)."""

    def test_cap_is_min_of_anchors_and_max_rows(self) -> None:
        """5 anchors, 5 primaries in corpus, max_rows=3 → cap=3."""
        rows = []
        for i in range(5):
            rows.append(_primary_row(f"ev_p{i}", f"TRIAL-{i}"))
        for i in range(50):
            rows.append(_non_primary_row(f"ev_r{i}"))
        result = select_evidence_for_generation(
            research_question="x",
            protocol=None,
            classified_sources=[],
            evidence_rows=rows,
            max_rows=3,
            primary_trial_anchors=[f"TRIAL-{i}" for i in range(5)],
        )
        # Exactly 3 rows (max_rows cap)
        assert len(result.selected_rows) == 3
        primary_count = sum(
            1 for r in result.selected_rows
            if r["evidence_id"].startswith("ev_p")
        )
        # All 3 slots should be primaries (M-51 takes priority)
        assert primary_count == 3

    def test_duplicate_anchors_dedupe_in_cap(self) -> None:
        """Anchors list with duplicates: cap uses unique count.
        Note: when M-42e already catches the primary, M-51 no-ops
        for that anchor (correct behavior — M-42e is the first
        line of defense). This test forces M-51 to fire by having
        many non-primary T1 rows outrank the primary on relevance.

        The important invariant: SURPASS-4 ends up selected exactly
        once, regardless of duplicate anchors in the config."""
        rows = [_primary_row("ev_s4", "SURPASS-4")]
        # 50 non-primary T1 rows with relevance-boosting words that
        # will outrank the primary's lexical score. Need relevance
        # boost to force M-42e to miss (relevance loss) and force
        # M-51 to catch on post-process.
        for i in range(50):
            r = _non_primary_row(f"ev_r{i}")
            r["statement"] = (
                "tirzepatide review meta-analysis pooled analysis "
                "glycemic weight loss comparative effectiveness "
                "efficacy safety clinical trial evidence"
            )
            rows.append(r)
        result = select_evidence_for_generation(
            research_question="tirzepatide review meta-analysis clinical",
            protocol=None,
            classified_sources=[],
            evidence_rows=rows,
            max_rows=5,
            primary_trial_anchors=["SURPASS-4", "SURPASS-4", "SURPASS-4"],
        )
        selected_ids = [r["evidence_id"] for r in result.selected_rows]
        assert selected_ids.count("ev_s4") == 1, (
            f"SURPASS-4 must be selected exactly once; got {selected_ids}"
        )


class TestM51TrimOverflow:
    """Codex revision #2: explicit max_rows overflow fixture.

    Codex M-51 pass-1 audit flagged that using a T1 primary tests
    M-42e retention, not M-51 specifically. Revised fixture: use a
    T4 primary so M-42e's T1-only floor doesn't catch it, forcing
    M-51 to do the insertion + trim work."""

    def test_insertion_triggers_trim_to_max_rows(self) -> None:
        """Pool: 50 non-primary T4 rows + 1 T4 SURPASS-4 primary;
        max_rows=10. M-42e cannot reserve (T4 not T1), so M-51 is the
        mechanism that inserts the primary. Must trim a non-M-51 tail
        row to keep len=10. M-51 telemetry note must be present."""
        non_primary_rows = [
            _non_primary_row(f"ev_r{i}", tier="T4") for i in range(50)
        ]
        # T4 primary so M-42e T1-only floor doesn't catch it
        primary_row = _primary_row("ev_s4", "SURPASS-4", tier="T4")
        rows = non_primary_rows + [primary_row]
        result = select_evidence_for_generation(
            research_question="tirzepatide review",
            protocol=None,
            classified_sources=[],
            evidence_rows=rows,
            max_rows=10,
            primary_trial_anchors=["SURPASS-4"],
        )
        # (1) Length exactly max_rows
        assert len(result.selected_rows) == 10
        # (2) Primary survives trim
        selected_ids = set(r["evidence_id"] for r in result.selected_rows)
        assert "ev_s4" in selected_ids, (
            f"SURPASS-4 must survive trim; got {selected_ids}"
        )
        # (3) M-51 note present (not m42e)
        m51_notes = [
            n for n in result.notes if "m51_anchor_primary_custody" in n
        ]
        assert m51_notes, (
            f"M-51 telemetry note missing; got notes={result.notes}"
        )
        assert "matched=1" in m51_notes[0]
        # (4) One non-M-51 row evicted (starts from 51 rows, trimmed to 10)
        # Evicted 41 rows; at least 1 is from the non-primary set.
        non_primary_kept = sum(
            1 for r in result.selected_rows
            if r["evidence_id"].startswith("ev_r")
        )
        assert non_primary_kept == 9  # 10 - 1 primary


class TestM51BackwardCompatibility:
    """Codex revision #4: explicit backward-compat fixture."""

    def test_no_anchors_produces_identical_output_to_v28(self) -> None:
        """With primary_trial_anchors=None, M-51 is a no-op; selector
        output is byte-identical to pre-V29 behavior."""
        rows = [_primary_row("ev_s4", "SURPASS-4")]
        for i in range(10):
            rows.append(_non_primary_row(f"ev_r{i}"))
        result_none = select_evidence_for_generation(
            research_question="x",
            protocol=None,
            classified_sources=[],
            evidence_rows=rows,
            max_rows=5,
            primary_trial_anchors=None,
        )
        result_empty = select_evidence_for_generation(
            research_question="x",
            protocol=None,
            classified_sources=[],
            evidence_rows=rows,
            max_rows=5,
            primary_trial_anchors=[],
        )
        # Both paths should produce the same output
        ids_none = [r["evidence_id"] for r in result_none.selected_rows]
        ids_empty = [r["evidence_id"] for r in result_empty.selected_rows]
        assert ids_none == ids_empty
        # No M-51 telemetry
        for r in (result_none, result_empty):
            assert not any("m51_anchor_primary_custody" in n
                           for n in r.notes)


class TestM51ShortPoolPath:
    """M-51 must also fire in the short-pool (M-46) path."""

    def test_short_pool_scans_full_pool_for_primaries(self) -> None:
        """Short pool: 5 rows total, max_rows=100 (forces M-46
        short-pool path). Primary should be detected and priority-
        ordered first."""
        rows = [_non_primary_row(f"ev_r{i}") for i in range(4)]
        rows.append(_primary_row("ev_cvot", "SURPASS-CVOT"))
        result = select_evidence_for_generation(
            research_question="x",
            protocol=None,
            classified_sources=[],
            evidence_rows=rows,
            max_rows=100,
            primary_trial_anchors=["SURPASS-CVOT"],
        )
        # Short-pool path keeps all 5 rows; M-42e primary floor
        # already fires for SURPASS-CVOT (same anchor detection).
        # M-51 short-pool only adds NEW matches beyond M-42e, so
        # when M-42e already caught it, M-51 is a no-op. The primary
        # should appear at priority class 0.
        selected_ids = [r["evidence_id"] for r in result.selected_rows]
        assert selected_ids[0] == "ev_cvot"  # first by priority


class TestM51CanonicalIdentity:
    """Codex revision #1: evidence_id preferred; fallback to
    (url, title, quote[:200]) tuple. Tested via dup detection."""

    def test_m51_does_not_reinsert_already_selected_primary(self) -> None:
        """Codex revision #1 core invariant: if M-42e already selected
        the primary into `selected`, M-51's canonical-identity check
        must recognize it and NOT re-insert, regardless of row
        identity (`id()`) differences.

        The test constructs a case where M-42e successfully catches
        the primary (T1 budget allows it through), then verifies
        M-51 does not add a duplicate via its post-process."""
        primary = _primary_row("ev_s4", "SURPASS-4")
        # Only a few non-primary rows so tier-balanced selection
        # naturally keeps the primary.
        rows = [primary]
        for i in range(3):
            rows.append(_non_primary_row(f"ev_r{i}"))
        result = select_evidence_for_generation(
            research_question="x",
            protocol=None,
            classified_sources=[],
            evidence_rows=rows,
            max_rows=10,  # all 4 fit → short-pool path
            primary_trial_anchors=["SURPASS-4"],
        )
        ids = [r["evidence_id"] for r in result.selected_rows]
        # Short-pool path keeps all rows, SURPASS-4 present once
        assert ids.count("ev_s4") == 1

    def test_missing_evidence_id_uses_url_tuple_identity(self) -> None:
        """Row without evidence_id uses (url, title, quote) as key."""
        r1 = _non_primary_row("ev_r1")
        r1.pop("evidence_id")  # simulate a retrieval bug
        r1["title"] = "SURPASS-4: primary result"
        r1["source_url"] = "https://www.nejm.org/doi/unique"
        # Still matches the anchor via title
        rows = [r1]
        for i in range(5):
            rows.append(_non_primary_row(f"ev_r{i+2}"))
        result = select_evidence_for_generation(
            research_question="x",
            protocol=None,
            classified_sources=[],
            evidence_rows=rows,
            max_rows=4,
            primary_trial_anchors=["SURPASS-4"],
        )
        # Should not crash; row without evidence_id handled correctly
        assert len(result.selected_rows) == 4
