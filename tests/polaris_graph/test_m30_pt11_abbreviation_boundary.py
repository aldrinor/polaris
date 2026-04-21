"""M-30 tests: PT11 sentence-boundary must skip English abbreviations.

V19 (2026-04-20) aborted with `release_allowed=False` because PT11 flagged
4 decimals as uncited in a sentence like:

    "...including diarrhea (10.7% vs. 4.8%), nausea (8.1% vs. 2.7%),
    and vomiting (5.7% vs. 1.2%).[7]"

The prior PT11 regex treated every `. ` as a sentence boundary, so the
lookahead from `4.8`, `8.1`, `2.7`, `5.7` stopped at the nearest `vs. `
instead of reaching `[7]` at the real sentence end.

These tests are generalizable — they exercise abbreviation patterns that
appear across clinical, policy, materials, energy, and due-diligence
domains. Nothing in the fix is POLARIS-specific or
tirzepatide-specific.
"""
from __future__ import annotations

from src.polaris_graph.evaluator.external_evaluator import (
    _is_abbreviation_period,
    _next_real_sentence_end,
    _prev_real_sentence_end,
    run_rule_checks,
)


class TestIsAbbreviationPeriod:
    """Unit tests for the abbreviation-detection helper."""

    def test_vs_period_is_abbreviation(self) -> None:
        text = "diarrhea (10.7% vs. 4.8%)"
        period_pos = text.index("vs.") + 2
        assert _is_abbreviation_period(text, period_pos)

    def test_etc_period_is_abbreviation(self) -> None:
        text = "tirzepatide, semaglutide, etc. showed similar"
        period_pos = text.index("etc.") + 3
        assert _is_abbreviation_period(text, period_pos)

    def test_fig_period_is_abbreviation(self) -> None:
        text = "As shown in Fig. 3, tirzepatide"
        period_pos = text.index("Fig.") + 3
        assert _is_abbreviation_period(text, period_pos)

    def test_no_period_is_abbreviation(self) -> None:
        text = "Study No. 42 reported"
        period_pos = text.index("No.") + 2
        assert _is_abbreviation_period(text, period_pos)

    def test_dr_period_is_abbreviation(self) -> None:
        text = "Dr. Smith wrote"
        period_pos = text.index("Dr.") + 2
        assert _is_abbreviation_period(text, period_pos)

    def test_inc_period_is_abbreviation(self) -> None:
        text = "Eli Lilly Inc. reported"
        period_pos = text.index("Inc.") + 3
        assert _is_abbreviation_period(text, period_pos)

    def test_eg_period_is_abbreviation(self) -> None:
        text = "e.g. tirzepatide showed"
        period_pos = text.index("e.g.") + 3
        assert _is_abbreviation_period(text, period_pos)

    def test_ie_period_is_abbreviation(self) -> None:
        text = "GLP-1/GIP co-agonist, i.e. tirzepatide"
        period_pos = text.index("i.e.") + 3
        assert _is_abbreviation_period(text, period_pos)

    def test_et_al_period_is_abbreviation(self) -> None:
        text = "Jastreboff et al. reported"
        period_pos = text.index("al.") + 2
        assert _is_abbreviation_period(text, period_pos)

    def test_real_sentence_end_not_abbreviation(self) -> None:
        text = "Tirzepatide is effective. Semaglutide also works."
        period_pos = text.index("effective.") + len("effective")
        assert not _is_abbreviation_period(text, period_pos)

    def test_number_before_period_not_abbreviation(self) -> None:
        text = "HbA1c reduction was 2.4. That is significant."
        # The "2.4." — this should NOT be treated as abbreviation.
        period_pos = text.index("2.4.") + 3
        assert not _is_abbreviation_period(text, period_pos)


class TestSentenceEndLocators:
    """Test next/prev sentence-end helpers skip abbreviation periods."""

    def test_next_real_sentence_end_skips_vs_period(self) -> None:
        # Text: start at the beginning, first real boundary is at "...1.2%). "
        text = "(10.7% vs. 4.8%), nausea (8.1% vs. 2.7%), and (5.7% vs. 1.2%).[7] Next sentence here."
        end = _next_real_sentence_end(text)
        # Should land PAST the "). " or "[7] " — definitely AFTER "1.2%).[7]"
        assert end is not None
        assert end > text.index("1.2%")
        # "vs. 4.8" would have been treated as boundary in the buggy version
        # — assert it wasn't
        assert end > text.index("vs. 4.8")

    def test_next_real_sentence_end_handles_no_boundary(self) -> None:
        text = "no period at all here vs. something else"
        assert _next_real_sentence_end(text) is None

    def test_prev_real_sentence_end_skips_vs_period(self) -> None:
        text = "(10.7% vs. 4.8%), nausea (8.1% vs."
        # No real sentence end in this snippet — but many "vs." patterns
        end = _prev_real_sentence_end(text)
        # Buggy version would return the last "vs." period; fixed should -1
        assert end == -1

    def test_prev_real_sentence_end_finds_real_boundary(self) -> None:
        text = "First sentence here. Then something vs. another thing"
        end = _prev_real_sentence_end(text)
        # Should find the "." after "First sentence here"
        assert end == text.index("here.") + 4


class TestPT11WithAbbreviations:
    """End-to-end: PT11 rule must PASS when decimals sit around 'vs.'
    abbreviations that the buggy regex misread as sentence boundaries."""

    def _report_with_vs_decimals(self) -> str:
        """V19-style sentence: several decimal pairs around 'vs.', all
        covered by a single [7] citation at the true sentence end."""
        return (
            "# Test report\n"
            "\n"
            "## Results\n"
            "The safety profile shows, including diarrhea (10.7% vs. 4.8%), "
            "nausea (8.1% vs. 2.7%), and vomiting (5.7% vs. 1.2%).[7]\n"
            "Serious adverse events were reported in 3.0% of participants.[8]\n"
            "\n"
            "## Methods\n"
            "Retrieved 2026-04-20. PubMed and OpenAlex. T1-T7 tiers. "
            "RCTs included, blogs excluded. Sponsor COI flagged. "
            "Prompt-injection sanitization. Generator model disclosed. "
            "Evaluator model disclosed.\n"
        )

    def test_pt11_passes_on_vs_abbreviation_pattern(self) -> None:
        report = self._report_with_vs_decimals()
        results, _, _ = run_rule_checks(
            report_text=report,
            protocol={"expected_tier_distribution": []},
            tier_distribution_report={},
            contradictions=[],
            evidence_pool={},
            generator_model="deepseek/deepseek-v3.2-exp",
            evaluator_model="qwen/qwen3-8b",
        )
        pt11 = next(r for r in results if r.item_id == "PT11")
        assert pt11.passed, (
            f"PT11 regressed on vs.-abbreviation pattern: {pt11.details!r}. "
            f"This is the exact V19 failure mode (2026-04-20)."
        )

    def test_pt11_still_detects_genuinely_uncited_decimals(self) -> None:
        """Fix must not mask real uncited-claim failures."""
        bad_report = (
            "# Test report\n"
            "\n"
            "## Results\n"
            "HbA1c was reduced by 2.4%. Weight dropped 15.2%. "
            "Another trial showed 18.4% reduction. "
            "Yet another showed 20.9%. "
            "And one more reported 22.5%. "
            "Plus a sixth with 24.6% reduction.\n"
            "\n"
            "## Methods\n"
            "Retrieved 2026-04-20. PubMed. T1-T7. RCTs. Sponsor. "
            "Sanitization. Generator. Evaluator.\n"
        )
        results, _, _ = run_rule_checks(
            report_text=bad_report,
            protocol={"expected_tier_distribution": []},
            tier_distribution_report={},
            contradictions=[],
            evidence_pool={},
            generator_model="deepseek/deepseek-v3.2-exp",
            evaluator_model="qwen/qwen3-8b",
        )
        pt11 = next(r for r in results if r.item_id == "PT11")
        assert not pt11.passed, (
            "PT11 must still flag reports where decimals are genuinely "
            "uncited — the fix should not over-relax the rule."
        )
