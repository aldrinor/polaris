"""M-32 tests: primary-study claim-frame prompt rule.

Codex DR pass 10 verdict on V21: LOSE_BOTH on "claim frames". V21
produced compact efficacy numbers ("reduced HbA1c 2.4%") where
ChatGPT DR and Gemini DR gave full trial frames (N + baseline +
comparator + endpoint + timepoint).

M-32 adds rule #12 to `SECTION_SYSTEM_PROMPT_TEMPLATE` instructing
the generator to emit the FULL FRAME in the first sentence that
introduces any named primary study / trial / cohort / experiment.

Generalizable test assertions: the rule must NOT be clinical-specific
— it must cover materials, policy, financial, and other empirical
domains. These tests verify rule presence and domain-agnostic
framing.
"""
from __future__ import annotations

from src.polaris_graph.generator.multi_section_generator import (
    SECTION_SYSTEM_PROMPT_TEMPLATE,
)


class TestM32RulePresence:
    """The prompt template must contain rule #12 with the required
    frame components."""

    def test_rule_12_exists_and_numbered(self) -> None:
        assert "12." in SECTION_SYSTEM_PROMPT_TEMPLATE
        assert "Primary-study framing" in SECTION_SYSTEM_PROMPT_TEMPLATE
        assert "(M-32" in SECTION_SYSTEM_PROMPT_TEMPLATE

    def test_rule_12_requires_sample_size(self) -> None:
        """The frame must include N (sample/cohort size)."""
        text = SECTION_SYSTEM_PROMPT_TEMPLATE
        assert "sample size" in text or "cohort size" in text
        assert "N=" in text  # example format

    def test_rule_12_requires_baseline_value(self) -> None:
        text = SECTION_SYSTEM_PROMPT_TEMPLATE.lower()
        assert "baseline" in text

    def test_rule_12_requires_comparator(self) -> None:
        text = SECTION_SYSTEM_PROMPT_TEMPLATE.lower()
        assert "comparator" in text or "control" in text

    def test_rule_12_requires_endpoint(self) -> None:
        text = SECTION_SYSTEM_PROMPT_TEMPLATE.lower()
        assert "endpoint" in text or "outcome" in text
        assert "timepoint" in text

    def test_rule_12_provides_example_template(self) -> None:
        """The rule must include a template example the generator can
        follow, using placeholder tokens."""
        text = SECTION_SYSTEM_PROMPT_TEMPLATE
        assert "[TRIAL NAME]" in text or "[SAMPLE_SIZE]" in text
        # Template uses [ev_X] to show citation placement
        assert "[ev_X]" in text or "[ev_" in text


class TestM32Generalization:
    """Rule #12 must not hard-code clinical-domain vocabulary only.
    Codex DR pass 10 specifically flagged this as a generalization
    requirement: "a materials paper gets composition + baseline
    performance + test condition + measured outcome; a policy study
    gets population + baseline metric + intervention + policy
    outcome"."""

    def test_no_clinical_only_framing(self) -> None:
        """The rule must mention non-clinical domains explicitly so
        the prompt reads as domain-agnostic."""
        text = SECTION_SYSTEM_PROMPT_TEMPLATE.lower()
        # Must reference at least one non-clinical domain to prove
        # the rule is domain-agnostic.
        nonclinical_signals = ["materials", "policy", "financial", "cohort study"]
        hits = [s for s in nonclinical_signals if s in text]
        assert hits, (
            f"M-32 rule must mention non-clinical domain(s) so the rule "
            f"reads as generalizable; found none of {nonclinical_signals}"
        )

    def test_no_drug_name_hardcoded(self) -> None:
        """No drug brand names in the prompt rule (generalization check)."""
        text = SECTION_SYSTEM_PROMPT_TEMPLATE.lower()
        banned = ["mounjaro", "zepbound", "tirzepatide", "ozempic",
                  "wegovy", "semaglutide"]
        # These are allowed to appear in evidence/input examples, but
        # not in the instruction text for the generalizable rule.
        # The rule text is the section between "12. **Primary-study"
        # and the next numbered/ALL-CAPS heading.
        rule_start = text.find("12. **primary-study")
        rule_end = text.find("\n\nevidence tier discipline", rule_start)
        if rule_end < 0:
            rule_end = len(text)
        rule_segment = text[rule_start:rule_end]
        leaks = [term for term in banned if term in rule_segment]
        assert not leaks, (
            f"M-32 rule leaks clinical-drug hard-codes: {leaks}. Generalization "
            f"requires the instruction text to stay domain-agnostic."
        )


class TestM32DoesNotBreakExistingRules:
    """Non-regression: the prior rules (1-11) must still be intact."""

    def test_rule_10_still_present(self) -> None:
        assert "10. **Multi-source citation (M-27" in SECTION_SYSTEM_PROMPT_TEMPLATE

    def test_rule_11_still_present(self) -> None:
        assert "11. **Jurisdictional precision (M-29" in SECTION_SYSTEM_PROMPT_TEMPLATE

    def test_all_rules_1_through_12_numbered(self) -> None:
        """Every rule number 1-12 must appear as a numbered item in
        the prompt."""
        for n in range(1, 13):
            assert f"{n}." in SECTION_SYSTEM_PROMPT_TEMPLATE, (
                f"rule {n}. missing from SECTION_SYSTEM_PROMPT_TEMPLATE"
            )
