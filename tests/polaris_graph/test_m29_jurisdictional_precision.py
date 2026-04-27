"""M-29 tests: jurisdictional-precision prompt rule + (future) verifier.

Codex DR audit pass 9 (2026-04-20) found that V18 introduced a
regulatory jurisdictional overclaim: the report said "A key safety
warning from both agencies is a boxed warning for risk of thyroid
C-cell tumors..." while citing only FDA labels. The EMA SmPC for
the same product does not use the FDA boxed-warning legal instrument.

M-29 adds rule #11 to SECTION_SYSTEM_PROMPT_TEMPLATE instructing the
generator to attribute each regulatory assertion to its specific
jurisdiction and to forbid generic plurals ("both agencies",
"regulators") when only one jurisdiction's source is cited.

These tests verify the prompt rule exists in the template and cover
the jurisdictional-precision contract at the template level. Runtime
verification of the rule's effectiveness comes via the full-scale
sweep + Codex DR audit cycle — prompt-only rules can't be unit-tested
for LLM compliance, but the presence of the rule is verifiable here.

Generalization constraint: the rule's wording must be domain-agnostic
(no "FDA"/"EMA"/"clinical" etc.), so it works for policy, finance,
environmental, or any cross-jurisdiction query.
"""
from __future__ import annotations

from src.polaris_graph.generator.multi_section_generator import (
    SECTION_SYSTEM_PROMPT_TEMPLATE,
)


class TestPromptRule11Present:
    """Verify rule #11 exists and is domain-agnostic."""

    def test_rule_11_present_in_template(self) -> None:
        # The rule is numbered 11 in the CRITICAL RULES section.
        assert "11." in SECTION_SYSTEM_PROMPT_TEMPLATE
        # Rule is keyed by the phrase "Jurisdictional precision".
        assert "Jurisdictional precision" in SECTION_SYSTEM_PROMPT_TEMPLATE

    def test_rule_forbids_generic_plurals(self) -> None:
        """Rule must explicitly enumerate generic-plural phrases that
        conflate jurisdictions when only one is cited."""
        banned_phrases_in_rule = [
            "both agencies",
            "all regulators",
            "authorities generally",
            "regulators require",
            "jurisdictions mandate",
        ]
        for phrase in banned_phrases_in_rule:
            assert phrase in SECTION_SYSTEM_PROMPT_TEMPLATE, (
                f"rule #11 must forbid the phrase {phrase!r} "
                f"so the generator avoids it"
            )

    def test_rule_provides_correct_pattern(self) -> None:
        """Rule must show the generator what the correct attribution
        pattern looks like (jurisdiction-specific claim + jurisdiction-
        specific citation)."""
        # The rule gives a template example using A/B placeholders so
        # it's domain-agnostic.
        assert "Jurisdiction A" in SECTION_SYSTEM_PROMPT_TEMPLATE
        assert "Jurisdiction B" in SECTION_SYSTEM_PROMPT_TEMPLATE

    def test_rule_references_the_actual_defect_class(self) -> None:
        """Rule must name the specific failure modes observed in V18
        so the generator can pattern-match the rule to a claim it's
        about to write."""
        # "boxed warning" vs "precaution" is the exact V18 defect pattern.
        assert "boxed warning" in SECTION_SYSTEM_PROMPT_TEMPLATE.lower()
        assert "precaution" in SECTION_SYSTEM_PROMPT_TEMPLATE.lower()
        assert "contraindication" in SECTION_SYSTEM_PROMPT_TEMPLATE.lower()


class TestRuleIsGeneralizable:
    """Verify the rule is NOT hard-coded for clinical/tirzepatide."""

    def test_rule_uses_placeholder_jurisdictions_not_real_agencies(self) -> None:
        """The rule illustrates with "Jurisdiction A / Jurisdiction B"
        rather than FDA / EMA / Health Canada / NICE etc., so it
        applies uniformly to policy, finance, environmental queries.

        M-26-era triage Codex review: the original scan range went
        from rule #11 to "EVIDENCE TIER DISCIPLINE" but that included
        rule #11b (M-37 jurisdictional coverage) which legitimately
        names jurisdictions in its detection examples. The test's
        stated intent is rule #11 (M-29) only, so narrow the scan to
        stop at "11b.".
        """
        # Find rule #11 block (between "11." and "11b." — the next
        # rule starts at "11b.").
        idx = SECTION_SYSTEM_PROMPT_TEMPLATE.find("11.")
        assert idx >= 0
        end_idx = SECTION_SYSTEM_PROMPT_TEMPLATE.find("11b.", idx)
        if end_idx == -1:
            # Fallback if rule #11b is removed or renamed: scan until
            # "EVIDENCE TIER DISCIPLINE" but cap to a reasonable range
            # so we don't sweep into M-47.
            end_idx = SECTION_SYSTEM_PROMPT_TEMPLATE.find(
                "EVIDENCE TIER DISCIPLINE", idx,
            )
            if end_idx == -1:
                end_idx = idx + 2000
        rule_block = SECTION_SYSTEM_PROMPT_TEMPLATE[idx:end_idx]
        # These agency names are domain-specific and must NOT appear
        # in the rule block itself. They may appear elsewhere in the
        # template as legitimate examples (like the tier-discipline
        # list), but the M-29 rule must be generic.
        forbidden_in_rule = [
            "FDA",
            "EMA",
            "Health Canada",
            "NICE",
            "Mounjaro",
            "tirzepatide",
            "SURPASS",
            "Federal Register",
            "SEC filing",
        ]
        leaks = [term for term in forbidden_in_rule if term in rule_block]
        assert not leaks, (
            f"M-29 rule #11 contains domain-specific terms that would "
            f"prevent generalization to non-clinical queries: {leaks}. "
            f"Rule should use placeholder jurisdictions (A, B, etc.) "
            f"or generic words like 'agency', 'framework'."
        )

    def test_rule_mentions_different_kinds_of_authority(self) -> None:
        """The rule should note it applies beyond just drug regulators —
        it should extend to standards-setting bodies, courts, or
        rulemaking bodies."""
        idx = SECTION_SYSTEM_PROMPT_TEMPLATE.find("Jurisdictional precision")
        assert idx >= 0
        rule_block = SECTION_SYSTEM_PROMPT_TEMPLATE[idx:idx + 2000]
        # At least one of these domain-neutral authority words must
        # appear to make the rule feel like it applies to more than
        # drug agencies.
        authority_words = [
            "standards", "governance", "courts", "rulemaking",
            "countries", "agencies",
        ]
        found = [w for w in authority_words if w in rule_block.lower()]
        assert len(found) >= 2, (
            f"M-29 rule should mention multiple authority types to be "
            f"clearly generalizable; found only: {found}"
        )


class TestRuleCoexistsWithPriorRules:
    """Regression check: adding rule #11 didn't break rules #1-10
    (M-24 through M-27 all still require specific behaviors)."""

    def test_rule_10_m27_multi_source_still_present(self) -> None:
        assert "Multi-source citation" in SECTION_SYSTEM_PROMPT_TEMPLATE
        assert "M-27" in SECTION_SYSTEM_PROMPT_TEMPLATE

    def test_rules_are_sequentially_numbered(self) -> None:
        """Rules should be 1. 2. 3. ... 11. in order, no gaps."""
        for n in range(1, 12):
            assert f"\n{n}." in SECTION_SYSTEM_PROMPT_TEMPLATE, (
                f"rule #{n} must be sequentially numbered in template"
            )
