"""M-26a tests: evidence selector tier exclusion.

Per DR audit pass 6: V13 cited Facebook [T6] for the FDA tirzepatide
boxed warning. Facebook was correctly classified T6 (RP1 social
platform), but it still reached the generator because the selector
passed all rows through. M-26a adds an explicit exclude_tiers filter
defaulting to {"T6"} so social-platform / press-release evidence
never competes with authoritative sources in clinical reports.
"""
from __future__ import annotations

from polaris_graph.retrieval.evidence_selector import (
    select_evidence_for_generation,
)


def _row(ev_id: str, url: str, tier: str, statement: str = "Example statement") -> dict:
    return {
        "evidence_id": ev_id,
        "source_url": url,
        "url": url,
        "tier": tier,
        "statement": statement,
        "direct_quote": statement,
    }


def _src(url: str, tier: str) -> dict:
    return {"url": url, "tier": tier}


class TestTierExclusion:
    def test_facebook_t6_excluded_by_default(self) -> None:
        """The DR pass 6 defect: Facebook post for boxed warning must
        not reach the generator for a clinical query."""
        rows = [
            _row("ev_001", "https://nejm.org/t2d-trial", "T1", "tirzepatide primary RCT"),
            _row("ev_002", "https://facebook.com/post/123", "T6", "box warning post"),
            _row("ev_003", "https://jamanetwork.com/study", "T1", "another RCT"),
        ]
        sources = [
            _src("https://nejm.org/t2d-trial", "T1"),
            _src("https://facebook.com/post/123", "T6"),
            _src("https://jamanetwork.com/study", "T1"),
        ]
        result = select_evidence_for_generation(
            research_question="tirzepatide T2D safety",
            protocol={"population": "adults with T2D"},
            classified_sources=sources,
            evidence_rows=rows,
            max_rows=20,
        )
        # Facebook T6 row dropped; the other two kept.
        kept_ids = [r["evidence_id"] for r in result.selected_rows]
        assert "ev_002" not in kept_ids, (
            f"expected Facebook T6 ev_002 dropped; got {kept_ids}"
        )
        assert "ev_001" in kept_ids
        assert "ev_003" in kept_ids

    def test_custom_exclude_tiers_parameter(self) -> None:
        """Caller can override the default to exclude additional tiers."""
        rows = [
            _row("ev_001", "https://nejm.org/rct", "T1"),
            _row("ev_002", "https://fb.com/post", "T6"),
            _row("ev_003", "https://conf.com/abstract", "T7"),
        ]
        sources = [
            _src("https://nejm.org/rct", "T1"),
            _src("https://fb.com/post", "T6"),
            _src("https://conf.com/abstract", "T7"),
        ]
        # Exclude both T6 AND T7
        result = select_evidence_for_generation(
            research_question="test",
            protocol=None,
            classified_sources=sources,
            evidence_rows=rows,
            max_rows=20,
            exclude_tiers={"T6", "T7"},
        )
        kept_ids = [r["evidence_id"] for r in result.selected_rows]
        assert kept_ids == ["ev_001"]

    def test_empty_exclude_tiers_disables_filter(self) -> None:
        """Passing an empty set disables M-26a filtering (for
        ephemeral-news queries where T6 might be the only source)."""
        rows = [
            _row("ev_001", "https://fb.com/a", "T6"),
            _row("ev_002", "https://fb.com/b", "T6"),
        ]
        sources = [_src("https://fb.com/a", "T6"), _src("https://fb.com/b", "T6")]
        result = select_evidence_for_generation(
            research_question="test",
            protocol=None,
            classified_sources=sources,
            evidence_rows=rows,
            max_rows=20,
            exclude_tiers=set(),
        )
        assert len(result.selected_rows) == 2

    def test_all_excluded_returns_empty_with_reason(self) -> None:
        """Degenerate case: every row is in an excluded tier. Fail
        loudly via notes rather than silently passing through."""
        rows = [_row("ev_001", "https://fb.com/a", "T6")]
        sources = [_src("https://fb.com/a", "T6")]
        result = select_evidence_for_generation(
            research_question="test",
            protocol=None,
            classified_sources=sources,
            evidence_rows=rows,
            max_rows=20,
        )
        assert result.selected_rows == []
        assert result.selection_strategy == "tier_balanced_v1_all_excluded"
        assert any("M-26a" in n for n in result.notes)

    def test_tier_from_row_fallback_when_not_in_classified(self) -> None:
        """If a row's URL isn't in classified_sources, use its own
        'tier' field for exclusion decisions."""
        rows = [
            _row("ev_001", "https://nejm.org/rct", "T1"),
            _row("ev_002", "https://facebook.com/xyz", "T6"),
        ]
        # Empty classified_sources — forces fallback to row.tier
        result = select_evidence_for_generation(
            research_question="test",
            protocol=None,
            classified_sources=[],
            evidence_rows=rows,
            max_rows=20,
        )
        kept_ids = [r["evidence_id"] for r in result.selected_rows]
        assert "ev_002" not in kept_ids
        assert "ev_001" in kept_ids
