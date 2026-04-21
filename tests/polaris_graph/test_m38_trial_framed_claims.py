"""M-38 tests: trial-framed claim hard constraint.

Codex DR pass-11 gap #3 on V23:
> "Convert efficacy and safety claims into trial-framed statements:
> trial name, N, baseline HbA1c/weight/BMI or population, comparator,
> dose, endpoint, timepoint, effect size, and uncertainty where
> available."

V23 Claim-frames scored LOSE_BOTH. The per-section prompt already
had rule #12 (M-32) asking for the full frame, but the generator
followed it only sporadically — producing sentences like:

  "SURPASS-2 showed that tirzepatide reduced HbA1c more than
   semaglutide [ev_042]."

which names a trial with only 1 frame element. V23's Efficacy
section has multiple such under-framed trial mentions.

M-38 extends rule #12 with rule #12b — a STRICT hard floor:
  - Naming a trial by its short name requires >=3 frame elements
    (N, baseline, comparator, dose, endpoint, timepoint, effect
    size with uncertainty).
  - If <3 frame elements are present in the cited evidence, the
    sentence must phrase generically ("one phase-3 RCT ...",
    "a randomized trial in [population] ...").

Test design:
  - Check rule #12b is present with the M-38 marker.
  - Check the 3-of-7 frame floor is spelled out.
  - Check the "do not name the trial if frame missing" clause is
    present and offers the generic phrasing alternative.
  - Non-regression: rule #12 (M-32) still present; rule #11b (M-37)
    still present; rule #12b is inserted between rule #12 and the
    closing rules block.
"""
from __future__ import annotations


class TestM38RulePresent:
    def test_m38_marker_present(self) -> None:
        from src.polaris_graph.generator.multi_section_generator import (
            SECTION_SYSTEM_PROMPT_TEMPLATE,
        )
        assert "M-38" in SECTION_SYSTEM_PROMPT_TEMPLATE

    def test_rule_title_present(self) -> None:
        from src.polaris_graph.generator.multi_section_generator import (
            SECTION_SYSTEM_PROMPT_TEMPLATE,
        )
        assert "Claim-frame hard constraint" in SECTION_SYSTEM_PROMPT_TEMPLATE


class TestM38FrameFloor:
    """The rule must spell out the 3-of-7 frame-element floor."""

    def test_three_of_seven_floor_stated(self) -> None:
        from src.polaris_graph.generator.multi_section_generator import (
            SECTION_SYSTEM_PROMPT_TEMPLATE,
        )
        # The rule must require at least three frame elements.
        assert "THREE" in SECTION_SYSTEM_PROMPT_TEMPLATE or (
            "three" in SECTION_SYSTEM_PROMPT_TEMPLATE
            and "frame elements" in SECTION_SYSTEM_PROMPT_TEMPLATE
        )

    def test_frame_element_candidates_named(self) -> None:
        """All 7 candidate frame elements should be named in the rule:
        N/size, baseline, comparator, dose, endpoint, timepoint,
        effect size with uncertainty."""
        from src.polaris_graph.generator.multi_section_generator import (
            SECTION_SYSTEM_PROMPT_TEMPLATE,
        )
        start = SECTION_SYSTEM_PROMPT_TEMPLATE.find("Claim-frame hard constraint")
        assert start >= 0
        rule_body = SECTION_SYSTEM_PROMPT_TEMPLATE[start:start + 3000].lower()
        for element in [
            "sample size",
            "baseline",
            "comparator",
            "dose",
            "endpoint",
            "timepoint",
            "uncertainty",
        ]:
            assert element in rule_body, (
                f"M-38 rule missing frame element: {element}"
            )


class TestM38FallbackPhrasing:
    """When frame elements are missing from the evidence, the rule
    must offer generic phrasing instead of letting the LLM name the
    trial under-framed."""

    def test_generic_fallback_phrasing_mentioned(self) -> None:
        from src.polaris_graph.generator.multi_section_generator import (
            SECTION_SYSTEM_PROMPT_TEMPLATE,
        )
        start = SECTION_SYSTEM_PROMPT_TEMPLATE.find("Claim-frame hard constraint")
        assert start >= 0
        rule_body = SECTION_SYSTEM_PROMPT_TEMPLATE[start:start + 3000]
        # The rule must offer a generic fallback phrasing.
        fallback_markers = [
            "phase-3 RCT",
            "randomized trial",
            "pooled analysis",
        ]
        present = [m for m in fallback_markers if m in rule_body]
        assert len(present) >= 2, (
            f"M-38 rule must name at least 2 generic fallback phrases; "
            f"found {present}"
        )

    def test_do_not_name_trial_clause(self) -> None:
        """The rule must explicitly tell the LLM NOT to name the trial
        when frame elements are missing — otherwise the LLM could
        still compromise by naming the trial with only 1-2 frame
        elements."""
        from src.polaris_graph.generator.multi_section_generator import (
            SECTION_SYSTEM_PROMPT_TEMPLATE,
        )
        start = SECTION_SYSTEM_PROMPT_TEMPLATE.find("Claim-frame hard constraint")
        assert start >= 0
        rule_body = SECTION_SYSTEM_PROMPT_TEMPLATE[start:start + 3000]
        # Look for the "do not name" / "DO NOT name" injunction
        assert "DO NOT name" in rule_body or "do not name" in rule_body


class TestM38ConcreteExamples:
    """Rule #12b includes concrete good/bad examples that demonstrate
    the 3-of-7 floor and the generic-phrasing fallback."""

    def test_good_and_bad_examples_present(self) -> None:
        from src.polaris_graph.generator.multi_section_generator import (
            SECTION_SYSTEM_PROMPT_TEMPLATE,
        )
        start = SECTION_SYSTEM_PROMPT_TEMPLATE.find("Claim-frame hard constraint")
        rule_body = SECTION_SYSTEM_PROMPT_TEMPLATE[start:start + 3000]
        assert "GOOD" in rule_body
        assert "BAD" in rule_body

    def test_rewrite_alternative_shown(self) -> None:
        """A BAD example must be paired with a REWRITE showing the
        correct generic phrasing — so the LLM sees the transformation,
        not just the prohibition."""
        from src.polaris_graph.generator.multi_section_generator import (
            SECTION_SYSTEM_PROMPT_TEMPLATE,
        )
        start = SECTION_SYSTEM_PROMPT_TEMPLATE.find("Claim-frame hard constraint")
        rule_body = SECTION_SYSTEM_PROMPT_TEMPLATE[start:start + 3000]
        assert "rewrite" in rule_body.lower()


class TestM38RuleOrdering:
    """M-38 must be inserted between M-32 (#12) and the closing
    EVIDENCE TIER DISCIPLINE block. The ordering matters: a model
    reading the prompt should see M-32's framing requirement, then
    M-38's hard-floor enforcement, then the tier-priority block."""

    def test_m32_precedes_m38(self) -> None:
        from src.polaris_graph.generator.multi_section_generator import (
            SECTION_SYSTEM_PROMPT_TEMPLATE,
        )
        m32_idx = SECTION_SYSTEM_PROMPT_TEMPLATE.find(
            "Primary-study framing (M-32"
        )
        m38_idx = SECTION_SYSTEM_PROMPT_TEMPLATE.find(
            "Claim-frame hard constraint (M-38"
        )
        assert 0 < m32_idx < m38_idx

    def test_m38_precedes_tier_discipline_block(self) -> None:
        """The tier-priority block (EVIDENCE TIER DISCIPLINE) should
        come after the claim-frame rules."""
        from src.polaris_graph.generator.multi_section_generator import (
            SECTION_SYSTEM_PROMPT_TEMPLATE,
        )
        m38_idx = SECTION_SYSTEM_PROMPT_TEMPLATE.find(
            "Claim-frame hard constraint (M-38"
        )
        tier_idx = SECTION_SYSTEM_PROMPT_TEMPLATE.find(
            "EVIDENCE TIER DISCIPLINE"
        )
        assert 0 < m38_idx < tier_idx

    def test_m37_coverage_rule_still_present(self) -> None:
        """Non-regression: adding M-38 must not displace M-37."""
        from src.polaris_graph.generator.multi_section_generator import (
            SECTION_SYSTEM_PROMPT_TEMPLATE,
        )
        assert "Jurisdictional coverage (M-37" in SECTION_SYSTEM_PROMPT_TEMPLATE

    def test_m32_framing_rule_still_present(self) -> None:
        """Non-regression: M-38 EXTENDS M-32, it doesn't replace it."""
        from src.polaris_graph.generator.multi_section_generator import (
            SECTION_SYSTEM_PROMPT_TEMPLATE,
        )
        assert "Primary-study framing (M-32" in SECTION_SYSTEM_PROMPT_TEMPLATE


class TestM38PromptFormattability:
    """Regression test: the section prompt must be `.format()`-able
    with `title=...` and `focus=...` substitution. A previous M-38
    draft used literal curly braces `{element1, element2, ...}` for a
    set enumeration, which `str.format()` misparsed as a placeholder
    and raised KeyError. The smoke test caught this; this unit test
    locks in the fix so a future edit reintroducing a `{...}` literal
    fails fast."""

    def test_template_format_succeeds(self) -> None:
        from src.polaris_graph.generator.multi_section_generator import (
            SECTION_SYSTEM_PROMPT_TEMPLATE,
        )
        # Must not raise KeyError / IndexError / ValueError.
        prompt = SECTION_SYSTEM_PROMPT_TEMPLATE.format(
            title="Efficacy",
            focus="Compare trial arms",
        )
        # Title and focus must both substitute successfully.
        assert "Efficacy" in prompt
        assert "Compare trial arms" in prompt
        # The M-38 rule must still be present post-format.
        assert "M-38" in prompt
        assert "Claim-frame hard constraint" in prompt


class TestM38Generalization:
    """The rule should generalize beyond clinical — M-32 already names
    'materials-science equivalent' and 'cohort-study equivalent' for
    the same reason, and M-38 should preserve that generality."""

    def test_rule_names_multiple_domains(self) -> None:
        """The rule #12b must at least mention that the constraint
        applies beyond clinical (e.g. materials / cohort equivalents)
        so the abstraction generalizes."""
        from src.polaris_graph.generator.multi_section_generator import (
            SECTION_SYSTEM_PROMPT_TEMPLATE,
        )
        start = SECTION_SYSTEM_PROMPT_TEMPLATE.find("Claim-frame hard constraint")
        rule_body = SECTION_SYSTEM_PROMPT_TEMPLATE[start:start + 3000].lower()
        # Should mention either "materials" or "cohort" or similar
        # generalization — not hardcoded to clinical only.
        generalization_markers = ["materials", "cohort", "equivalent"]
        hits = [m for m in generalization_markers if m in rule_body]
        assert hits, (
            f"M-38 rule should generalize beyond clinical; found {hits}"
        )
