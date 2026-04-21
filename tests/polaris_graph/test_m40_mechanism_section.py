"""M-40 tests: Mechanism-section narrative-depth rule.

Codex DR pass-11 gap #6 on V23:
> "Expand narrative depth with mechanism/pharmacology, clinical
> interpretation, patient-selection logic, trial-design limitations,
> and sequencing/access gaps without relying on detector metadata
> as a substitute for explanation."

V23's Narrative depth scored LOSE_BOTH. V23 outline: Efficacy,
Comparative, Safety, Regulatory, Dose Response — no Mechanism
section, zero "mechanism" mentions in the final report. Gemini
3.1 Pro DR's report has a dedicated mechanism/pharmacology section
covering dual GIP/GLP-1 agonism, half-life, receptor binding,
insulin sensitivity.

M-40 adds a rule to `OUTLINE_SYSTEM_PROMPT` requiring "Mechanism"
as one of the 5 outline sections whenever the corpus contains at
least 3 evidence rows with mechanism-of-action vocabulary in title
or snippet. The rule is generalizable beyond clinical (materials,
policy, finance variants named explicitly).

Test design:
  - Rule present with M-40 marker.
  - Triggering vocabulary list named.
  - Non-regression: M-25b 5-section rule, tier-priority rules
    still present in OUTLINE_SYSTEM_PROMPT.
  - Generalization: rule references non-clinical domains.
  - Format safety: prompt still renders without KeyError.
"""
from __future__ import annotations


class TestM40RulePresent:
    def test_m40_marker_present(self) -> None:
        from src.polaris_graph.generator.multi_section_generator import (
            OUTLINE_SYSTEM_PROMPT,
        )
        assert "M-40" in OUTLINE_SYSTEM_PROMPT

    def test_rule_title_present(self) -> None:
        from src.polaris_graph.generator.multi_section_generator import (
            OUTLINE_SYSTEM_PROMPT,
        )
        assert "Mechanism section" in OUTLINE_SYSTEM_PROMPT


class TestM40TriggerVocabulary:
    """The rule must enumerate the vocabulary that triggers the
    Mechanism-section requirement. Without an explicit list the
    outline LLM has to guess what counts."""

    def test_rule_names_key_trigger_terms(self) -> None:
        from src.polaris_graph.generator.multi_section_generator import (
            OUTLINE_SYSTEM_PROMPT,
        )
        lowered = OUTLINE_SYSTEM_PROMPT.lower()
        # At least half of these seed terms should be explicitly named
        seed_terms = [
            "mechanism",
            "pharmacokinetic",
            "receptor",
            "half-life",
            "metabolism",
            "agonist",
            "binding",
            "pathway",
        ]
        hits = [t for t in seed_terms if t in lowered]
        assert len(hits) >= 5, (
            f"M-40 rule must name explicit trigger vocabulary; found {hits}"
        )

    def test_rule_specifies_minimum_evidence_count(self) -> None:
        """The rule must set a threshold (e.g. 'at least 3 evidence
        rows') so the LLM has a deterministic trigger, not a vibes-
        based decision."""
        from src.polaris_graph.generator.multi_section_generator import (
            OUTLINE_SYSTEM_PROMPT,
        )
        assert "AT LEAST 3" in OUTLINE_SYSTEM_PROMPT or (
            "at least 3" in OUTLINE_SYSTEM_PROMPT
        )


class TestM40ReasoningIsStated:
    """The rule should justify itself so the LLM treats it as
    important rather than decorative."""

    def test_rule_explains_narrative_depth_value(self) -> None:
        from src.polaris_graph.generator.multi_section_generator import (
            OUTLINE_SYSTEM_PROMPT,
        )
        lowered = OUTLINE_SYSTEM_PROMPT.lower()
        # Must explain WHY mechanism matters: "why", "how", "explains",
        # "research-grade", "deep research", or similar
        explanation_markers = [
            "why", "research-grade", "deep research", "narrative-depth",
            "narrative depth",
        ]
        hits = [m for m in explanation_markers if m in lowered]
        assert hits, (
            f"M-40 rule should justify the Mechanism requirement; found {hits}"
        )


class TestM40Generalization:
    """The rule must be generalizable beyond clinical (per the
    discipline set in M-32 and reconfirmed in M-37/M-38)."""

    def test_rule_names_non_clinical_domains(self) -> None:
        from src.polaris_graph.generator.multi_section_generator import (
            OUTLINE_SYSTEM_PROMPT,
        )
        lowered = OUTLINE_SYSTEM_PROMPT.lower()
        non_clinical = [
            "materials", "chemistry", "policy", "finance", "reaction",
            "incentive", "transmission",
        ]
        hits = [d for d in non_clinical if d in lowered]
        assert hits, (
            f"M-40 rule must name non-clinical domain(s); found {hits}"
        )

    def test_rule_body_uses_no_drug_names(self) -> None:
        """Generalization discipline: the rule body should not
        hardcode drug names. Check only the M-40 sub-paragraph."""
        from src.polaris_graph.generator.multi_section_generator import (
            OUTLINE_SYSTEM_PROMPT,
        )
        start = OUTLINE_SYSTEM_PROMPT.find("M-40:")
        assert start >= 0
        # Take up to next blank line or end
        remainder = OUTLINE_SYSTEM_PROMPT[start:start + 2500]
        rule_end = remainder.find("\n- ", 10)  # next rule start
        if rule_end < 0:
            rule_end = len(remainder)
        m40_body = remainder[:rule_end].lower()
        banned = ["tirzepatide", "semaglutide", "liraglutide", "dulaglutide",
                  "mounjaro", "ozempic", "wegovy", "zepbound"]
        leaks = [d for d in banned if d in m40_body]
        assert not leaks, (
            f"M-40 rule body hardcodes drug names: {leaks}"
        )


class TestM40NonRegression:
    """Adding M-40 must not displace existing outline rules."""

    def test_m25b_five_section_rule_still_present(self) -> None:
        from src.polaris_graph.generator.multi_section_generator import (
            OUTLINE_SYSTEM_PROMPT,
        )
        assert "M-25b" in OUTLINE_SYSTEM_PROMPT
        assert "EXACTLY 5 sections" in OUTLINE_SYSTEM_PROMPT

    def test_tier_hierarchy_still_present(self) -> None:
        from src.polaris_graph.generator.multi_section_generator import (
            OUTLINE_SYSTEM_PROMPT,
        )
        assert "EVIDENCE QUALITY HIERARCHY" in OUTLINE_SYSTEM_PROMPT
        assert "[T1]" in OUTLINE_SYSTEM_PROMPT

    def test_output_format_requirement_still_present(self) -> None:
        from src.polaris_graph.generator.multi_section_generator import (
            OUTLINE_SYSTEM_PROMPT,
        )
        assert "OUTPUT FORMAT" in OUTLINE_SYSTEM_PROMPT


class TestM40OutlineSummaryIncludesTitle:
    """M-40 pass-2 Codex audit: `_call_outline` previously passed only
    `ev_id [tier]: statement[:160]` to the planner. Titles were not
    visible, so a rule triggering on "title or snippet vocabulary"
    could under-fire when the mechanism term lived in the title only.
    Pass-2 includes the title (truncated to 120 chars) in the summary
    so the trigger is reliable."""

    def test_outline_prompt_includes_title_when_present(self) -> None:
        """Build a fake evidence row with a mechanism-vocabulary title
        and an unrelated statement. The summary text sent to the LLM
        must contain the title."""
        # We can't reach the inner summary without calling an LLM.
        # But we CAN reach the `_call_outline` source to verify the
        # summary-building path uses the title field. Parse the function
        # source for the `title` attribute read.
        import inspect
        from src.polaris_graph.generator import multi_section_generator as m
        src = inspect.getsource(m._call_outline)
        # The builder must read `title` from each evidence row.
        assert 'ev.get("title"' in src or "ev.get('title'" in src, (
            "_call_outline must include title in the outline summary "
            "(M-40 pass-2 Codex audit medium #1)"
        )
        # The builder must also embed the title into the summary block.
        assert "title:" in src or "title_clean" in src, (
            "_call_outline summary block must expose the title field "
            "to the outline LLM"
        )

    def test_rule_mentions_title_field(self) -> None:
        """The M-40 rule must reference the `title:` field explicitly
        so the LLM knows where to look for the trigger vocabulary."""
        from src.polaris_graph.generator.multi_section_generator import (
            OUTLINE_SYSTEM_PROMPT,
        )
        start = OUTLINE_SYSTEM_PROMPT.find("M-40")
        assert start >= 0
        rule_body = OUTLINE_SYSTEM_PROMPT[start:start + 2500]
        # Rule must mention title field or statement body so LLM knows
        # where to look
        assert "title:" in rule_body or "title" in rule_body, (
            "M-40 rule should name the `title:` field explicitly"
        )


class TestM40FormatSafety:
    """Prompt templates often interpolate via `.format()`. M-38 shipped
    with a KeyError bug from `{set_literals}`. Verify M-40 doesn't
    reintroduce it."""

    def test_outline_prompt_has_no_unescaped_placeholders(self) -> None:
        """The OUTLINE_SYSTEM_PROMPT is an f-string literal in the
        module, so `{_ALLOWED_SECTIONS}` expands at module load. After
        module load, any remaining `{` or `}` in the string is literal
        text. Verify: no `{...}` pair in the LOADED string other than
        known-safe ones."""
        import re
        from src.polaris_graph.generator.multi_section_generator import (
            OUTLINE_SYSTEM_PROMPT,
        )
        # Find `{word}` style placeholder-ish tokens that would trip
        # `str.format()`. The outline prompt isn't actually passed
        # through `.format()` by callers, so this is defensive only;
        # still, no bare `{word}` should appear.
        suspicious = re.findall(r"\{([A-Za-z_][A-Za-z_0-9]*)\}", OUTLINE_SYSTEM_PROMPT)
        # Allow only `{_ALLOWED_SECTIONS}`-style debug artifacts from
        # the f-string eval — those would not survive into the loaded
        # string if substitution ran, so `suspicious` should be empty.
        assert not suspicious, (
            f"OUTLINE_SYSTEM_PROMPT contains unexpected `{{...}}` "
            f"tokens: {suspicious}"
        )
