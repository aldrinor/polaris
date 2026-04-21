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


class TestContextDependentDisambiguation:
    """M-30 pass-2 (addressing Codex blocker): abbreviations can be
    sentence-final when the next word starts with a capital letter.
    `Jan.` in "in Jan. A separate claim" is a real boundary; `Jan.` in
    "Jan. 15, 2020" is not."""

    def test_month_before_capital_is_boundary(self) -> None:
        # "...in Jan. A separate claim..." — Jan. ends the sentence.
        text = "Declines were 4.2%, 5.3%, and 6.4% in Jan. A separate claim"
        period_pos = text.index("Jan.") + 3
        assert not _is_abbreviation_period(text, period_pos), (
            "Jan. followed by capital letter should be a real sentence "
            "boundary (Codex blocker)."
        )

    def test_month_before_digit_is_nonboundary(self) -> None:
        # "Jan. 15, 2020" — date continuation.
        text = "The study started Jan. 15, 2020 and ran for"
        period_pos = text.index("Jan.") + 3
        assert _is_abbreviation_period(text, period_pos), (
            "Jan. followed by a date number is mid-sentence."
        )

    def test_inc_before_capital_is_boundary(self) -> None:
        # "...Eli Lilly Inc. Separately, another trial..."
        text = "Study was sponsored by Eli Lilly Inc. Separately, another trial"
        period_pos = text.index("Inc.") + 3
        assert not _is_abbreviation_period(text, period_pos)

    def test_inc_before_lowercase_is_nonboundary(self) -> None:
        # "Eli Lilly Inc. reported..."
        text = "Eli Lilly Inc. reported tirzepatide outcomes"
        period_pos = text.index("Inc.") + 3
        assert _is_abbreviation_period(text, period_pos)

    def test_no_before_digit_is_nonboundary(self) -> None:
        text = "See Study No. 42 which reported"
        period_pos = text.index("No.") + 2
        assert _is_abbreviation_period(text, period_pos)

    def test_fig_before_digit_is_nonboundary(self) -> None:
        text = "As shown in Fig. 3A, the trend"
        period_pos = text.index("Fig.") + 3
        assert _is_abbreviation_period(text, period_pos)

    def test_vs_followed_by_capital_still_nonboundary(self) -> None:
        # vs. is ALWAYS_NONBOUNDARY so even "...vs. Placebo..." stays
        # mid-sentence (common in pharma prose).
        text = "tirzepatide 10 mg vs. Placebo comparator arm"
        period_pos = text.index("vs.") + 2
        assert _is_abbreviation_period(text, period_pos)

    def test_dr_before_proper_noun_is_nonboundary(self) -> None:
        text = "reported by Dr. Jastreboff in 2023"
        period_pos = text.index("Dr.") + 2
        assert _is_abbreviation_period(text, period_pos)


class TestCitationAdjacentBoundary:
    """M-30 pass-2 (addressing Codex medium): `.[N]` commonly appears
    in POLARIS reports and must be recognised as a sentence terminator
    so lookback/lookahead windows don't over-extend."""

    def test_period_followed_by_bracket_citation_is_boundary(self) -> None:
        text = "The trial reported 2.4% reduction.[7] Another trial showed"
        # The `.` after "reduction" is followed immediately by `[` — the
        # new regex must still match it as a sentence terminator.
        end = _next_real_sentence_end(text)
        assert end is not None
        # End index must land AT or PAST the `.` — i.e. the `.` position + 1
        expected_min = text.index("reduction.") + len("reduction.")
        assert end >= expected_min

    def test_prev_sentence_end_finds_period_before_bracket(self) -> None:
        """The last char of the prior sentence is the closing `]` of
        its trailing citation — so back_text[end+1:] starts cleanly
        at the next sentence and does NOT see the prior-sentence
        citation (which would be a false-positive for PT11)."""
        text = "First sentence.[1] Second sentence with 3.4% reduction"
        end = _prev_real_sentence_end(text)
        # End at the `]` of [1]
        assert end == text.index("[1]") + 2


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

    def test_pt11_does_not_accept_next_sentence_citation(self) -> None:
        """Codex M-30 pass-1 blocker: sentence-final abbreviation must
        NOT be treated as non-boundary when followed by a capital, or
        else a citation in the next sentence falsely covers uncited
        decimals in the prior sentence."""
        report = (
            "# Test report\n"
            "\n"
            "## Results\n"
            "The measured declines were 4.2%, 5.3%, 6.4%, and 7.5% "
            "during the study enrollment period in Jan. "
            "A separate analysis by Eli Lilly Inc. Separately reports "
            "that tirzepatide is efficacious.[1]\n"
            "Additional numbers 8.6%, 9.7%, 10.8%, 11.9% here. "
            "More data 12.1%, 13.2%, 14.3%, 15.4%, 16.5%, 17.6%.\n"
            "\n"
            "## Methods\n"
            "Retrieved 2026-04-20. PubMed. T1-T7. RCTs. Sponsor. "
            "Sanitization. Generator. Evaluator.\n"
        )
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
        assert not pt11.passed, (
            "Codex blocker: the decimals before `in Jan.` should NOT be "
            "covered by [1] in the next sentence — Jan. is sentence-final "
            "because 'A separate' starts with a capital letter. PT11 must "
            "still flag these as uncited."
        )
