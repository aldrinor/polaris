"""M-34 tests: PT11 lookahead-window size for long sentences.

V23 full-scale (2026-04-21) aborted with PT11 flagging 3 uncited
decimals of 36 in the tirzepatide report. All three were early
decimals in LONG sentences (~300-450 chars) whose `[N]` citation
appeared at the sentence end, outside PT11's 200-char lookahead
window. Not an M-30 boundary-detection issue — M-30 correctly keeps
"8.1 weeks" from being a sentence boundary. The failure mode is:
a legitimate long regulatory/clinical sentence with the citation at
the end, where the window truncates before the citation.

M-34 widens the lookahead (scan the full remainder with a 1000-char
safety cap) and changes the None-fallback to `len(after_text)`
instead of `min(150, ...)`. Same change mirrored on the
back-lookup path.

Generalizable design: no domain-specific tokens. The widening is
a pure cap increase + fallback correction. Nothing about the
tirzepatide/T2D content is encoded.
"""
from __future__ import annotations

import pathlib

from src.polaris_graph.evaluator.external_evaluator import run_rule_checks

V23_REPORT = pathlib.Path(
    "outputs/full_scale_v23/clinical/clinical_tirzepatide_t2dm/report.md"
)


def _run_pt11(report_text: str) -> tuple[bool, str]:
    """Run the evaluator rule checks on a full report text and return
    (pt11_passed, details)."""
    results, _, _ = run_rule_checks(
        report_text=report_text,
        protocol={"research_question": "test"},
        tier_distribution_report=None,
        contradictions=[],
        evidence_pool={
            f"ev_{i:03d}": {"content": "stub", "url": "https://example.com"}
            for i in range(1, 40)
        },
        generator_model="deepseek/deepseek-v3.2-exp",
        evaluator_model="qwen/qwen3-8b",
    )
    for r in results:
        if r.item_id == "PT11":
            return r.passed, r.details
    raise AssertionError("PT11 not found in rule checks")


class TestM34V23ReportPT11:
    """The primary regression check — PT11 must pass on the actual V23
    report.md under M-34. Before M-34, this run recorded
    `rule_pt11_uncited_numeric_claims` and aborted release. After
    M-34, the same report must pass."""

    def test_v23_report_passes_pt11(self) -> None:
        if not V23_REPORT.exists():
            import pytest
            pytest.skip(f"V23 report not present at {V23_REPORT}")
        text = V23_REPORT.read_text(encoding="utf-8")
        passed, details = _run_pt11(text)
        assert passed, (
            f"M-34 must pass V23 report.md (3 uncited decimals in long "
            f"sentences were the release blocker). Got details={details!r}"
        )


class TestM34LongSentenceSyntheticBundle:
    """Portable bundle test (runs even if V23 report absent). Embeds
    the 3 V23 long sentences AND 1 short uncited sentence in one body.
    Under the current 200-char lookahead the 3 V23 sentences contribute
    ~3-5 uncited decimals → PT11 threshold exceeded. Under M-34 the
    V23 sentences contribute 0 uncited, only the 1 short sentence
    remains → under threshold."""

    def test_mixed_bundle_passes_under_m34(self) -> None:
        sentences = [
            # Three real V23 fixtures, each with citation at end.
            "A systematic review and network meta-analysis of subcutaneous "
            "GLP-1 receptor agonists and tirzepatide concluded that all "
            "tirzepatide doses were comparable to semaglutide 2.0 mg and "
            "superior to semaglutide 1.0 mg and 0.5 mg in reducing HbA1c, "
            "and that tirzepatide 15 mg, 10 mg, and 5 mg demonstrated "
            "greater weight loss efficacy than semaglutide 2.0 mg, "
            "1.0 mg, and 0.5 mg, respectively.[5]",

            "The FDA-approved dosing regimen for this indication starts at "
            "2.5 mg injected subcutaneously once weekly, with the dose "
            "increased to 5 mg after 4 weeks, and further increased in "
            "2.5 mg increments after a minimum of 4 weeks on the current "
            "dose as needed for glycemic control, up to a maximum of 15 mg "
            "once weekly.[17][18]",

            "The NICE guidance for weight management advises a starting "
            "dose of 2.5 mg once weekly, with titration by 2.5 mg every "
            "4 weeks to recommended maintenance doses of 5 mg, 10 mg, or "
            "15 mg once weekly, and recommends assessing treatment response "
            "after 6 months on the highest tolerated dose.[27]",

            # Already-cited filler to push total decimal count past the
            # max(3, n//10) threshold so additional uncited decimals from
            # the long sentences are visible against the bound.
            "Mean HbA1c reductions were 1.9%, 2.2%, and 2.4% at the three "
            "doses.[1] Weight loss was 7.8 kg, 10.3 kg, and 12.4 kg.[2] "
            "Discontinuations were 6.0%, 8.5%, and 8.5%.[3] "
            "HbA1c <7.0% was achieved by 82% to 86%.[4]",
        ]
        body = "\n\n".join(sentences)
        full = (
            "# Test\n\n### Results\n\n"
            + body
            + "\n\n## Methods\n"
            + "Pre-registered protocol.json (SHA-256 deadbeef).\n"
            + "Generator model: deepseek/deepseek-v3.2-exp. "
            + "Evaluator model: qwen/qwen3-8b. Retrieved 2026-04-21.\n"
            + "Inclusion / exclusion: z. Sources classified using T1-T7.\n"
            + "Expected tier distribution: T1 30-60%. Actual: T1 50%.\n"
            + "Sponsor / conflict-of-interest review per source.\n"
            + "Prompt-injection sanitization enabled.\n"
            + "Corpus adequacy: decision=proceed, 7/7 thresholds met.\n\n"
            + "## Contradiction disclosures\nNone.\n\n"
            + "## Bibliography\n"
            + "".join(
                f"[{i}] Dummy — https://example.com (tier T1)\n"
                for i in range(1, 31)
            )
        )
        passed, details = _run_pt11(full)
        assert passed, (
            f"M-34 must pass the bundled body where all uncited decimals "
            f"are in long sentences whose citation is at the end. Got "
            f"details={details!r}"
        )


class TestM34Nonregressions:
    """Fixes must not make PT11 a rubber stamp."""

    def test_short_uncited_sentence_still_fails(self) -> None:
        """Many short sentences with decimals and NO citations anywhere
        must still fail PT11. The fix is a window-size change, not a
        rule disablement."""
        body = (
            "Tirzepatide reduced HbA1c by 2.4%. The drug achieved 22.0% "
            "weight loss. Placebo showed 3.1% loss. SURPASS-2 enrolled "
            "1879 participants. Mean age was 56.6 years. BMI was 34.2. "
            "Baseline HbA1c was 8.28%. Weight was 93.7 kg. Dose was 5.0 "
            "mg or 10.0 mg or 15.0 mg. Semaglutide dose was 1.0 mg."
        )
        full = (
            "# Test\n\n### Results\n\n"
            + body
            + "\n\n## Methods\n"
            + "Pre-registered protocol.json (SHA-256 deadbeef).\n"
            + "Generator model: x. Evaluator model: y. Retrieved 2026-04-21.\n"
            + "Inclusion / exclusion: z. Sources classified using T1-T7.\n"
            + "Expected tier distribution: T1 30-60%. Actual: T1 50%.\n"
            + "Sponsor / conflict-of-interest review per source.\n"
            + "Prompt-injection sanitization enabled.\n"
            + "Corpus adequacy: decision=proceed, 7/7 thresholds met.\n\n"
            + "## Contradiction disclosures\nNone.\n\n"
            + "## Bibliography\n[1] Dummy — https://example.com (tier T1)\n"
        )
        passed, details = _run_pt11(full)
        assert not passed, (
            f"M-34 must not silently pass bodies with many uncited "
            f"decimals. Got details={details!r}"
        )

    def test_vs_decimal_chain_still_works(self) -> None:
        """M-30 non-regression: 'vs.'-chained decimals with a single
        trailing citation must still pass."""
        body = (
            "Diarrhea was reported in 10.7% vs 4.8% placebo, nausea in "
            "8.1% vs 2.7%, and vomiting in 5.7% vs 1.2% during the "
            "double-blind period.[1]"
        )
        full = (
            "# Test\n\n### Results\n\n"
            + body
            + "\n\n## Methods\n"
            + "Pre-registered protocol.json (SHA-256 deadbeef).\n"
            + "Generator model: x. Evaluator model: y. Retrieved 2026-04-21.\n"
            + "Inclusion / exclusion: z. Sources classified using T1-T7.\n"
            + "Expected tier distribution: T1 30-60%. Actual: T1 50%.\n"
            + "Sponsor / conflict-of-interest review per source.\n"
            + "Prompt-injection sanitization enabled.\n"
            + "Corpus adequacy: decision=proceed, 7/7 thresholds met.\n\n"
            + "## Contradiction disclosures\nNone.\n\n"
            + "## Bibliography\n[1] Dummy — https://example.com (tier T1)\n"
        )
        passed, details = _run_pt11(full)
        assert passed, (
            f"M-30 non-regression: vs-chained decimals must still pass. "
            f"Got details={details!r}"
        )
