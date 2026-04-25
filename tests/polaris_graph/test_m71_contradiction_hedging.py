"""V32 — M-71 contradiction-aware hedging tests.

Codex strategic review (2026-04-25): run-9..run-11 Qwen flagged
hedging_appropriateness because contradictions live only in the
appendix. M-71 routes high-severity, section-relevant contradictions
into the body prose via prompt-injected hedging hints.
"""
from __future__ import annotations

import pytest

from src.polaris_graph.generator.contradiction_hedging import (
    SectionContradictionHint,
    _is_high_severity,
    _section_keywords_for,
    filter_section_contradictions,
    render_section_hedging_block,
)


# ─────────────────────────────────────────────────────────────────────
# (1) Section keyword routing
# ─────────────────────────────────────────────────────────────────────
class TestSectionKeywords:
    def test_safety_section_keywords(self) -> None:
        kw = _section_keywords_for("Safety")
        assert "hypoglycemia" in kw
        assert "adverse" in kw

    def test_comparative_section_keywords(self) -> None:
        kw = _section_keywords_for("Comparative")
        assert "weight" in kw
        assert "hba1c" in kw

    def test_population_subgroups_section_keywords(self) -> None:
        kw = _section_keywords_for("Population Subgroups")
        assert "bmi" in kw
        assert "subgroup" in kw

    def test_efficacy_section_keywords(self) -> None:
        kw = _section_keywords_for("Efficacy")
        assert "primary endpoint" in kw

    def test_unknown_section_returns_empty(self) -> None:
        assert _section_keywords_for("Random Section") == frozenset()


# ─────────────────────────────────────────────────────────────────────
# (2) Severity gate
# ─────────────────────────────────────────────────────────────────────
class TestSeverityGate:
    def test_high_severity_three_values_30pct_spread_t1_passes(self) -> None:
        c = {
            "subject": "tirzepatide",
            "predicate": "weight loss",
            "values": [5.0, 10.0, 20.0],
            "tiers": ["T1", "T2", "T4"],
        }
        assert _is_high_severity(c) is True

    def test_low_value_count_fails(self) -> None:
        c = {
            "values": [5.0, 10.0],
            "tiers": ["T1", "T2"],
        }
        assert _is_high_severity(c) is False

    def test_narrow_spread_fails(self) -> None:
        c = {
            "values": [10.0, 11.0, 12.0],  # 20% spread
            "tiers": ["T1", "T2", "T4"],
        }
        assert _is_high_severity(c) is False

    def test_no_t1_source_fails(self) -> None:
        """Pure noise without a T1 source — gated out."""
        c = {
            "values": [5.0, 10.0, 20.0],
            "tiers": ["T4", "T7", "T7"],
        }
        assert _is_high_severity(c) is False


# ─────────────────────────────────────────────────────────────────────
# (3) Section filtering
# ─────────────────────────────────────────────────────────────────────
class TestFilterSectionContradictions:
    def test_safety_relevant_contradiction_routes_to_safety(self) -> None:
        contradictions = [
            {
                "subject": "tirzepatide",
                "predicate": "hypoglycemia",
                "values": [0.5, 5.0, 12.0],
                "tiers": ["T1", "T2", "T4"],
            },
            {
                "subject": "tirzepatide",
                "predicate": "weight loss",
                "values": [5.0, 10.0, 20.0],
                "tiers": ["T1", "T2"],
            },
        ]
        hints = filter_section_contradictions("Safety", contradictions)
        assert len(hints) == 1
        assert hints[0].predicate == "hypoglycemia"

    def test_comparative_routes_weight_contradictions(self) -> None:
        contradictions = [
            {
                "subject": "tirzepatide",
                "predicate": "body weight (15 mg)",
                "values": [10.0, 15.0, 25.0],
                "tiers": ["T1", "T2", "T4"],
            },
        ]
        hints = filter_section_contradictions(
            "Comparative", contradictions,
        )
        assert len(hints) == 1
        assert "body weight" in hints[0].predicate

    def test_irrelevant_section_excludes_all(self) -> None:
        contradictions = [
            {
                "subject": "tirzepatide",
                "predicate": "weight loss",
                "values": [5.0, 10.0, 20.0],
                "tiers": ["T1", "T2", "T4"],
            },
        ]
        # "Methods" isn't in the routing table
        hints = filter_section_contradictions(
            "Methods", contradictions,
        )
        assert hints == []

    def test_max_per_section_cap(self) -> None:
        # 4 high-severity weight contradictions; default cap is 2
        contradictions = []
        for spread in [10, 50, 100, 30]:
            contradictions.append({
                "subject": "tirzepatide",
                "predicate": "weight loss",
                "values": [1.0, spread / 2, spread],
                "tiers": ["T1", "T2", "T4"],
            })
        hints = filter_section_contradictions(
            "Comparative", contradictions, max_per_section=2,
        )
        assert len(hints) == 2

    def test_low_severity_filtered_out(self) -> None:
        contradictions = [{
            "subject": "tirzepatide",
            "predicate": "weight loss",
            "values": [10.0, 11.0, 12.0],  # narrow spread
            "tiers": ["T1", "T2", "T4"],
        }]
        hints = filter_section_contradictions(
            "Comparative", contradictions,
        )
        assert hints == []

    def test_empty_contradictions_returns_empty(self) -> None:
        assert filter_section_contradictions("Safety", None) == []
        assert filter_section_contradictions("Safety", []) == []


# ─────────────────────────────────────────────────────────────────────
# (4) Render hedging block
# ─────────────────────────────────────────────────────────────────────
class TestRenderHedgingBlock:
    def test_empty_hints_returns_empty_string(self) -> None:
        assert render_section_hedging_block([]) == ""

    def test_block_includes_required_directives(self) -> None:
        hints = [
            SectionContradictionHint(
                section_title="Safety",
                subject="tirzepatide",
                predicate="hypoglycemia",
                value_range="0.5 to 12",
                tiers=("T1", "T2", "T4"),
            ),
        ]
        block = render_section_hedging_block(hints)
        # Critical instruction phrasing
        assert "M-71" in block
        assert "INCLUDE ONE HEDGED SENTENCE" in block
        assert "tirzepatide" in block
        assert "hypoglycemia" in block
        assert "0.5 to 12" in block
        assert "T1/T2/T4" in block