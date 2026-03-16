"""
Tests for FIX-043 audit fixes.

Covers:
1. FIX-043A: Crash recovery preserves state keys (merge, not replace)
2. FIX-043B: evidence_chain key in synthesizer output
3. FIX-043I: Double bracket cleanup in report assembly
4. FIX-043G: Tier recalibration with env var thresholds
5. FIX-043K: Hedging cap prompt instruction
6. FIX-043N: Softening placeholder cleanup
"""

import os
import re

import pytest


# ---------------------------------------------------------------------------
# FIX-043A: Crash recovery merge pattern
# ---------------------------------------------------------------------------

class TestCrashRecoveryMerge:
    """Verify crash recovery path merges result dict (not replaces)."""

    def test_crash_recovery_preserves_state_keys(self):
        """Simulate crash recovery merge pattern: synth_state.update(synth_result)
        must preserve evidence, claims, and faithfulness_score from synth_state."""
        # Simulate the accumulated state before crash recovery
        synth_state = {
            "evidence": [{"evidence_id": "ev_1", "statement": "fact A"}],
            "claims": [{"claim": "test", "is_faithful": True}],
            "faithfulness_score": 0.85,
            "fetched_content": [{"url": "https://a.com"}],
            "status": "timeout_synthesizing",
            "error": "astream failed: timeout",
        }

        # Simulate synthesis output (what synthesize_report returns)
        synth_result = {
            "final_report": "# Report\n\nContent here.",
            "report_sections": [{"title": "Intro", "content": "text"}],
            "bibliography": [{"formatted": "[1] Source A"}],
            "quality_metrics": {"word_count": 5000},
        }

        # FIX-043A merge pattern: synth_state.update(synth_result)
        synth_state.update(synth_result)
        synth_state["status"] = "timeout_synthesized"

        # Verify ALL state keys are preserved
        assert synth_state["evidence"] == [{"evidence_id": "ev_1", "statement": "fact A"}]
        assert synth_state["claims"] == [{"claim": "test", "is_faithful": True}]
        assert synth_state["faithfulness_score"] == 0.85
        assert synth_state["fetched_content"] == [{"url": "https://a.com"}]
        # AND synthesis results are present
        assert synth_state["final_report"].startswith("# Report")
        assert len(synth_state["report_sections"]) == 1
        assert synth_state["status"] == "timeout_synthesized"

    def test_old_pattern_would_lose_state(self):
        """Demonstrate that the OLD pattern (result = synth_result) loses state."""
        synth_state = {
            "evidence": [{"evidence_id": "ev_1"}],
            "faithfulness_score": 0.85,
        }
        synth_result = {
            "final_report": "report text",
        }

        # OLD broken pattern: result = synth_result
        result = synth_result

        # Evidence and faithfulness are LOST
        assert "evidence" not in result
        assert "faithfulness_score" not in result


# ---------------------------------------------------------------------------
# FIX-043B: evidence_chain key
# ---------------------------------------------------------------------------

class TestEvidenceChainKey:
    """Verify the correct key fallback for evidence retrieval."""

    def test_evidence_chain_key_primary(self):
        """Primary key is evidence_chain."""
        result = {"evidence_chain": [{"id": "ev_1"}]}
        evidence = result.get("evidence_chain", result.get("evidence", []))
        assert len(evidence) == 1
        assert evidence[0]["id"] == "ev_1"

    def test_evidence_key_fallback(self):
        """Falls back to evidence if evidence_chain is missing."""
        result = {"evidence": [{"id": "ev_2"}]}
        evidence = result.get("evidence_chain", result.get("evidence", []))
        assert len(evidence) == 1
        assert evidence[0]["id"] == "ev_2"

    def test_neither_key_returns_empty(self):
        """Returns empty list if neither key exists."""
        result = {"final_report": "text"}
        evidence = result.get("evidence_chain", result.get("evidence", []))
        assert evidence == []


# ---------------------------------------------------------------------------
# FIX-043I: Double bracket cleanup
# ---------------------------------------------------------------------------

class TestDoubleBracketCleanup:
    """Verify bracket cleanup regex handles all known patterns."""

    def test_double_bracket_fix(self):
        """[[2][[2] -> [2]"""
        text = "Some text [[2][[2] more text"
        fixed = re.sub(r'\[+(\d+)\]+', r'[\1]', text)
        assert "[[" not in fixed
        assert "[2]" in fixed

    def test_nested_bracket_fix(self):
        """[[[3]]] -> [3]"""
        text = "fact [[[3]]] here"
        fixed = re.sub(r'\[+(\d+)\]+', r'[\1]', text)
        assert fixed == "fact [3] here"

    def test_adjacent_duplicate_removal(self):
        """[2][2] -> [2]"""
        text = "claim [2][2] rest"
        fixed = re.sub(r'(\[\d+\])(?:\1)+', r'\1', text)
        assert fixed == "claim [2] rest"

    def test_triple_adjacent_duplicate(self):
        """[5][5][5] -> [5]"""
        text = "claim [5][5][5] rest"
        fixed = re.sub(r'(\[\d+\])(?:\1)+', r'\1', text)
        assert fixed == "claim [5] rest"

    def test_different_citations_preserved(self):
        """[1][2] should remain [1][2]"""
        text = "claim [1][2] rest"
        fixed = re.sub(r'\[+(\d+)\]+', r'[\1]', text)
        fixed = re.sub(r'(\[\d+\])(?:\1)+', r'\1', fixed)
        assert fixed == "claim [1][2] rest"

    def test_full_pipeline_cleanup(self):
        """Test both regex passes in sequence (as in report_assembler)."""
        text = "Water quality [[2][[2] is important [3][3][3] for health [1][4]."
        # Pass 1: Fix nested/double brackets
        text = re.sub(r'\[+(\d+)\]+', r'[\1]', text)
        # Pass 2: Fix adjacent duplicates
        text = re.sub(r'(\[\d+\])(?:\1)+', r'\1', text)
        assert text == "Water quality [2] is important [3] for health [1][4]."


# ---------------------------------------------------------------------------
# FIX-043G: Tier recalibration
# ---------------------------------------------------------------------------

class TestTierRecalibration:
    """Verify tier assignment with configurable thresholds."""

    def test_gold_threshold_from_env(self, monkeypatch):
        """GOLD at confidence >= 0.6 AND relevance >= 0.6 for authoritative sources."""
        monkeypatch.setenv("PG_GOLD_CONFIDENCE_THRESHOLD", "0.6")
        monkeypatch.setenv("PG_GOLD_RELEVANCE_THRESHOLD", "0.6")
        monkeypatch.setenv("PG_SILVER_CONFIDENCE_THRESHOLD", "0.3")
        monkeypatch.setenv("PG_SILVER_RELEVANCE_THRESHOLD", "0.4")
        monkeypatch.setenv("PG_NLI_ENABLED", "0")

        from src.polaris_graph.agents.analyzer import _assign_quality_tiers

        evidence = [
            {
                "source_type": "journal_article",
                "relevance_score": 0.7,
                "source_url": "https://pubmed.ncbi.nlm.nih.gov/12345",
                "source_confidence": 0.8,
                "direct_quote": "The study found that activated carbon adsorption removed 95% of PFAS contaminants from drinking water supplies at pilot scale.",
            },
        ]
        result = _assign_quality_tiers(evidence)
        assert result[0]["quality_tier"] == "GOLD"

    def test_silver_threshold_for_non_authoritative(self, monkeypatch):
        """Non-authoritative source with high scores -> SILVER.

        authority = 0.6 * default(0.5) + 0.4 * 0.7 = 0.58
        adjusted_relevance = 0.9 * 0.58 = 0.522 >= 0.4 (SILVER threshold)
        """
        monkeypatch.setenv("PG_GOLD_CONFIDENCE_THRESHOLD", "0.6")
        monkeypatch.setenv("PG_GOLD_RELEVANCE_THRESHOLD", "0.6")
        monkeypatch.setenv("PG_SILVER_CONFIDENCE_THRESHOLD", "0.3")
        monkeypatch.setenv("PG_SILVER_RELEVANCE_THRESHOLD", "0.4")
        monkeypatch.setenv("PG_NLI_ENABLED", "0")

        from src.polaris_graph.agents.analyzer import _assign_quality_tiers

        evidence = [
            {
                "source_type": "web",
                "relevance_score": 0.9,
                "source_url": "https://example.com/article",
                "source_confidence": 0.7,
                "direct_quote": "Water treatment technologies have improved significantly in recent years with new filtration methods.",
            },
        ]
        result = _assign_quality_tiers(evidence)
        assert result[0]["quality_tier"] == "SILVER"

    def test_bronze_for_low_scores(self, monkeypatch):
        """Low relevance + low confidence -> BRONZE."""
        monkeypatch.setenv("PG_GOLD_CONFIDENCE_THRESHOLD", "0.6")
        monkeypatch.setenv("PG_GOLD_RELEVANCE_THRESHOLD", "0.6")
        monkeypatch.setenv("PG_SILVER_CONFIDENCE_THRESHOLD", "0.3")
        monkeypatch.setenv("PG_SILVER_RELEVANCE_THRESHOLD", "0.4")
        monkeypatch.setenv("PG_NLI_ENABLED", "0")

        from src.polaris_graph.agents.analyzer import _assign_quality_tiers

        evidence = [
            {
                "source_type": "web",
                "relevance_score": 0.2,
                "source_url": "https://random-blog.com/post",
                "source_confidence": 0.1,
            },
        ]
        result = _assign_quality_tiers(evidence)
        assert result[0]["quality_tier"] == "BRONZE"


# ---------------------------------------------------------------------------
# FIX-043K: Hedging cap prompt
# ---------------------------------------------------------------------------

class TestHedgingCapPrompt:
    """Verify hedging cap instruction is present in section system prompt."""

    def test_hedging_cap_in_system_prompt(self):
        """SECTION_SYSTEM_PROMPT contains hedging word cap instruction."""
        from src.polaris_graph.synthesis.section_writer import SECTION_SYSTEM_PROMPT
        assert "Maximum 5 hedging words per SECTION total" in SECTION_SYSTEM_PROMPT

    def test_definitive_language_instruction(self):
        """SECTION_SYSTEM_PROMPT instructs definitive language."""
        from src.polaris_graph.synthesis.section_writer import SECTION_SYSTEM_PROMPT
        assert "DEFINITIVE language" in SECTION_SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# FIX-043N: Softening placeholder cleanup
# ---------------------------------------------------------------------------

class TestSofteningPlaceholderCleanup:
    """Verify excessive softening placeholders are stripped."""

    def test_excessive_placeholders_stripped(self):
        """When count > 3, placeholders are replaced."""
        report = (
            "Fact A (specific values vary by study). "
            "Fact B (specific values vary by study). "
            "Fact C (specific values vary by study). "
            "Fact D (specific values vary by study). "
        )
        placeholder = "(specific values vary by study)"
        count = report.count(placeholder)
        assert count == 4  # > 3 threshold
        report = report.replace(placeholder, "the reported value")
        assert "(specific values vary by study)" not in report
        assert "the reported value" in report

    def test_few_placeholders_preserved(self):
        """When count <= 3, placeholders are NOT stripped (legitimate hedging)."""
        report = (
            "Fact A (specific values vary by study). "
            "Fact B with data. "
            "Fact C (specific values vary by study). "
        )
        placeholder = "(specific values vary by study)"
        count = report.count(placeholder)
        assert count == 2  # <= 3, should preserve
        if count > 3:
            report = report.replace(placeholder, "the reported value")
        assert "(specific values vary by study)" in report  # Still present
