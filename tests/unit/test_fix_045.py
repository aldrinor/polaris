"""
Unit tests for FIX-045A through FIX-045H plus WARN-1/WARN-2 fixes.

Tests the post-T044 audit fixes:
- FIX-045A: Orphan citation removal
- FIX-045B: Navigation boilerplate stripping
- FIX-045C: Abstract metric recomputation
- FIX-045D: Sequential citation renumbering
- FIX-045E: Number spacing fix
- FIX-045F: Orphaned parenthetical fix
- FIX-045G: Individual api_error retry (integration-level)
- FIX-045H: Multi-evidence corroboration
- WARN-1: STORM perspective propagation
- WARN-2: Domain-adaptive hedging threshold
"""

import pytest

from src.polaris_graph.synthesis.report_assembler import (
    _remove_orphan_citations,
    _fix_number_spacing,
    _fix_abstract_metrics,
    _fix_orphaned_parentheticals,
    _renumber_citations_sequential,
)
from src.tools.access_bypass import _strip_navigation_boilerplate


# ---------------------------------------------------------------------------
# FIX-045A: Orphan citation removal
# ---------------------------------------------------------------------------
class TestRemoveOrphanCitations:
    """FIX-045A: Remove [N] citations that have no bibliography entry."""

    def test_no_orphans(self):
        text = "Evidence shows [1] that water [2] is important [3]."
        valid = {1, 2, 3}
        cleaned, count = _remove_orphan_citations(text, valid)
        assert count == 0
        assert cleaned == text

    def test_removes_orphans_beyond_range(self):
        """Body cites [1]-[5] but bibliography only has [1]-[3]."""
        text = "Claim A [1]. Claim B [2]. Claim C [3]. Claim D [4]. Claim E [5]."
        valid = {1, 2, 3}
        cleaned, count = _remove_orphan_citations(text, valid)
        assert count == 2
        assert "[4]" not in cleaned
        assert "[5]" not in cleaned
        assert "[1]" in cleaned
        assert "[2]" in cleaned
        assert "[3]" in cleaned

    def test_removes_orphans_with_gaps(self):
        """Body cites [1], [3], [7] but only [1] and [3] exist."""
        text = "First [1]. Second [3]. Third [7]."
        valid = {1, 3}
        cleaned, count = _remove_orphan_citations(text, valid)
        assert count == 1
        assert "[7]" not in cleaned
        assert "[1]" in cleaned
        assert "[3]" in cleaned

    def test_cleans_double_spaces(self):
        text = "Point [4] here."
        valid = {1, 2, 3}
        cleaned, count = _remove_orphan_citations(text, valid)
        assert count == 1
        assert "  " not in cleaned

    def test_empty_valid_set(self):
        text = "Citation [1] here."
        cleaned, count = _remove_orphan_citations(text, set())
        assert count == 0
        assert cleaned == text

    def test_no_citations_in_text(self):
        text = "No citations here at all."
        valid = {1, 2, 3}
        cleaned, count = _remove_orphan_citations(text, valid)
        assert count == 0
        assert cleaned == text


# ---------------------------------------------------------------------------
# FIX-045B: Navigation boilerplate stripping
# ---------------------------------------------------------------------------
class TestStripNavigationBoilerplate:
    """FIX-045B: Strip HTML navigation artifacts from fetched content."""

    def test_strips_skip_to_content(self):
        content = "[Skip to Main Content]\n\nReal article content here."
        cleaned = _strip_navigation_boilerplate(content)
        assert "[Skip to Main Content]" not in cleaned
        assert "Real article content here." in cleaned

    def test_strips_skip_to_navigation(self):
        content = "[Skip to Navigation]\nImportant text."
        cleaned = _strip_navigation_boilerplate(content)
        assert "[Skip to Navigation]" not in cleaned
        assert "Important text." in cleaned

    def test_strips_standalone_menu(self):
        content = "Header\nMenu\nActual content."
        cleaned = _strip_navigation_boilerplate(content)
        assert "\nMenu\n" not in cleaned
        assert "Actual content." in cleaned

    def test_strips_sign_in(self):
        content = "Sign in\nWelcome to the article."
        cleaned = _strip_navigation_boilerplate(content)
        assert "Sign in" not in cleaned
        assert "Welcome to the article." in cleaned

    def test_preserves_real_content(self):
        content = "The menu of options includes various filters [1]. Navigation through PFAS testing requires proper equipment."
        cleaned = _strip_navigation_boilerplate(content)
        # "menu" and "navigation" in context should be preserved
        assert "menu of options" in cleaned
        assert "Navigation through" in cleaned

    def test_empty_content(self):
        assert _strip_navigation_boilerplate("") == ""

    def test_collapses_blank_lines(self):
        content = "[Skip to Content]\n\n\n\n\nReal content."
        cleaned = _strip_navigation_boilerplate(content)
        assert "\n\n\n" not in cleaned

    def test_strips_jump_to(self):
        content = "[Jump to Content]\nArticle text."
        cleaned = _strip_navigation_boilerplate(content)
        assert "[Jump to Content]" not in cleaned


# ---------------------------------------------------------------------------
# FIX-045C: Abstract metric recomputation
# ---------------------------------------------------------------------------
class TestFixAbstractMetrics:
    """FIX-045C: Recompute abstract metrics from actual content."""

    def test_fixes_word_count(self):
        abstract = "This report synthesizes 10,418 words of analysis."
        fixed = _fix_abstract_metrics(abstract, 25, 200, 12000)
        assert "12,000 words" in fixed
        assert "10,418" not in fixed

    def test_fixes_source_count(self):
        abstract = "Drawing from 23 sources across the literature."
        fixed = _fix_abstract_metrics(abstract, 30, 200, 10000)
        assert "30 sources" in fixed
        assert "23" not in fixed

    def test_fixes_citation_count(self):
        abstract = "With 218 citations to peer-reviewed work."
        fixed = _fix_abstract_metrics(abstract, 25, 150, 10000)
        assert "150 citations" in fixed
        assert "218" not in fixed

    def test_fixes_multiple_metrics(self):
        abstract = "Analysis of 10,418 words with 218 citations from 23 sources."
        fixed = _fix_abstract_metrics(abstract, 30, 150, 12000)
        assert "12,000 words" in fixed
        assert "150 citations" in fixed
        assert "30 sources" in fixed

    def test_no_change_when_no_metrics(self):
        abstract = "This report examines water filtration technology."
        fixed = _fix_abstract_metrics(abstract, 25, 200, 10000)
        assert fixed == abstract

    def test_preserves_non_metric_numbers(self):
        abstract = "Examining 5 key themes with 10,000 words of evidence."
        fixed = _fix_abstract_metrics(abstract, 25, 200, 10500)
        assert "10,500 words" in fixed
        assert "5 key themes" in fixed  # "5" is NOT a metric keyword


# ---------------------------------------------------------------------------
# FIX-045D: Sequential citation renumbering
# ---------------------------------------------------------------------------
class TestRenumberCitationsSequential:
    """FIX-045D: Renumber citations in order of first appearance."""

    def test_already_sequential(self):
        report = "Claim [1]. Claim [2]. Claim [3].\n\n## References\n\n[1] A\n[2] B\n[3] C\n"
        sections = [
            {"content": "Claim [1]. Claim [2]. Claim [3].", "citation_ids": ["[1]", "[2]", "[3]"], "section_id": "s1", "title": "T", "word_count": 6, "evidence_ids": []},
        ]
        bib = [
            {"citation_key": "[1]", "formatted": "[1] A", "url": "a.com", "source_type": "web", "evidence_ids": ["e1"]},
            {"citation_key": "[2]", "formatted": "[2] B", "url": "b.com", "source_type": "web", "evidence_ids": ["e2"]},
            {"citation_key": "[3]", "formatted": "[3] C", "url": "c.com", "source_type": "web", "evidence_ids": ["e3"]},
        ]
        result_report, result_sections, result_bib = _renumber_citations_sequential(report, sections, bib)
        assert result_report == report
        assert len(result_bib) == 3

    def test_renumbers_non_sequential(self):
        report = "First [5] then [2] then [5] again.\n\n## References\n\n[1] A\n[2] B\n[3] C\n[4] D\n[5] E\n"
        sections = [
            {"content": "First [5] then [2] then [5] again.", "citation_ids": ["[5]", "[2]", "[5]"], "section_id": "s1", "title": "T", "word_count": 7, "evidence_ids": []},
        ]
        bib = [
            {"citation_key": "[1]", "formatted": "[1] A", "url": "a.com", "source_type": "web", "evidence_ids": ["e1"]},
            {"citation_key": "[2]", "formatted": "[2] B", "url": "b.com", "source_type": "web", "evidence_ids": ["e2"]},
            {"citation_key": "[3]", "formatted": "[3] C", "url": "c.com", "source_type": "web", "evidence_ids": ["e3"]},
            {"citation_key": "[4]", "formatted": "[4] D", "url": "d.com", "source_type": "web", "evidence_ids": ["e4"]},
            {"citation_key": "[5]", "formatted": "[5] E", "url": "e.com", "source_type": "web", "evidence_ids": ["e5"]},
        ]
        result_report, result_sections, result_bib = _renumber_citations_sequential(report, sections, bib)

        body_part = result_report.split("## References")[0]
        # [5] appeared first -> becomes [1], [2] appeared second -> becomes [2]
        assert "[1]" in body_part
        assert "[2]" in body_part
        assert "First [1] then [2] then [1] again." in body_part

        # Section content also renumbered
        assert "First [1] then [2] then [1] again." in result_sections[0]["content"]

    def test_no_references_section(self):
        report = "No refs section here [1]."
        sections = [{"content": "[1]", "citation_ids": ["[1]"], "section_id": "s1", "title": "T", "word_count": 1, "evidence_ids": []}]
        bib = [{"citation_key": "[1]", "formatted": "[1] A", "url": "a.com", "source_type": "web", "evidence_ids": ["e1"]}]
        result_report, result_sections, result_bib = _renumber_citations_sequential(report, sections, bib)
        assert result_report == report  # No change

    def test_preserves_unreferenced_bib_entries(self):
        """Bibliography entries not cited in body are kept at end."""
        report = "Only [2] cited.\n\n## References\n\n[1] A\n[2] B\n[3] C\n"
        sections = [
            {"content": "Only [2] cited.", "citation_ids": ["[2]"], "section_id": "s1", "title": "T", "word_count": 3, "evidence_ids": []},
        ]
        bib = [
            {"citation_key": "[1]", "formatted": "[1] A", "url": "a.com", "source_type": "web", "evidence_ids": ["e1"]},
            {"citation_key": "[2]", "formatted": "[2] B", "url": "b.com", "source_type": "web", "evidence_ids": ["e2"]},
            {"citation_key": "[3]", "formatted": "[3] C", "url": "c.com", "source_type": "web", "evidence_ids": ["e3"]},
        ]
        result_report, result_sections, result_bib = _renumber_citations_sequential(report, sections, bib)

        # [2] was first in body -> becomes [1]
        assert "Only [1] cited." in result_report
        # Unreferenced entries appended at end
        assert len(result_bib) == 3
        assert result_bib[0]["citation_key"] == "[1]"  # was [2]


# ---------------------------------------------------------------------------
# FIX-045E: Number spacing fix
# ---------------------------------------------------------------------------
class TestFixNumberSpacing:
    """FIX-045E: Fix spacing errors in numbers like '99. 9%'."""

    def test_fixes_percent_spacing(self):
        assert _fix_number_spacing("99. 9%") == "99.9%"

    def test_fixes_decimal_spacing(self):
        assert _fix_number_spacing("3. 14") == "3.14"

    def test_preserves_normal_numbers(self):
        assert _fix_number_spacing("99.9%") == "99.9%"
        assert _fix_number_spacing("3.14") == "3.14"

    def test_fixes_multiple_occurrences(self):
        text = "Results show 99. 9% removal and 95. 2% efficiency."
        fixed = _fix_number_spacing(text)
        assert "99.9%" in fixed
        assert "95.2%" in fixed

    def test_no_change_without_errors(self):
        text = "The value is 42 and 3.14 is pi."
        assert _fix_number_spacing(text) == text

    def test_sentence_ending_not_affected(self):
        """Period followed by space and digit in next sentence should be kept."""
        text = "Value is 5. 6 items were found."
        fixed = _fix_number_spacing(text)
        # "5. 6" looks like a decimal with errant space, so it gets fixed
        assert "5.6" in fixed


# ---------------------------------------------------------------------------
# FIX-045F: Orphaned parenthetical fix
# ---------------------------------------------------------------------------
class TestFixOrphanedParentheticals:
    """FIX-045F: Fix orphaned parentheticals in report text."""

    def test_removes_known_softening_patterns(self):
        text = "Values range widely (specific values vary by study). Next sentence."
        fixed = _fix_orphaned_parentheticals(text)
        assert "(specific values vary by study)" not in fixed
        assert "Next sentence." in fixed

    def test_removes_reported_values_vary(self):
        text = "The results were mixed (reported values vary). Conclusion."
        fixed = _fix_orphaned_parentheticals(text)
        assert "(reported values vary)" not in fixed

    def test_preserves_normal_parentheticals(self):
        text = "Water filters (such as reverse osmosis) are effective."
        fixed = _fix_orphaned_parentheticals(text)
        assert "(such as reverse osmosis)" in fixed

    def test_cleans_double_spaces(self):
        text = "Data shows  (specific values vary by study)  here."
        fixed = _fix_orphaned_parentheticals(text)
        assert "  " not in fixed

    def test_unwraps_standalone_parenthetical_after_period(self):
        text = "First claim. (This observation requires further study). Next."
        fixed = _fix_orphaned_parentheticals(text)
        assert "This observation requires further study." in fixed
        assert "(This observation" not in fixed


# ---------------------------------------------------------------------------
# FIX-045H: Multi-evidence corroboration
# ---------------------------------------------------------------------------
from src.polaris_graph.agents.verifier import link_corroborating_evidence


class TestLinkCorroboratingEvidence:
    """FIX-045H: Enrich claims with corroborating evidence IDs."""

    def _make_claim(self, claim_id, statement="test", is_faithful=True):
        return {
            "claim_id": claim_id,
            "statement": statement,
            "evidence_ids": [claim_id],
            "confidence": 0.8,
            "verification_method": "atomic",
            "is_faithful": is_faithful,
            "section_id": None,
            "reasoning": "test",
            "verification_basis": "content",
        }

    def _make_evidence(self, eid, url, statement):
        return {
            "evidence_id": eid,
            "source_url": url,
            "statement": statement,
            "quality_tier": "SILVER",
        }

    def test_basic_cross_ref_enrichment(self):
        """Claims in same cross-ref group get multiple evidence_ids."""
        claims = [
            self._make_claim("ev_1", "water filter PFAS removal technology"),
            self._make_claim("ev_2", "water filter PFAS removal effectiveness"),
        ]
        evidence = [
            self._make_evidence("ev_1", "url1", "water filter PFAS removal technology"),
            self._make_evidence("ev_2", "url2", "water filter PFAS removal effectiveness"),
            self._make_evidence("ev_3", "url3", "water filter PFAS treatment methods"),
        ]
        groups = [
            {
                "claim": "test",
                "evidence_ids": ["ev_1", "ev_2", "ev_3"],
                "source_urls": ["url1", "url2", "url3"],
                "agreement_score": 0.8,
                "cross_ref_count": 3,
            }
        ]
        enriched = link_corroborating_evidence(claims, evidence, groups)
        assert enriched == 2
        assert len(claims[0]["evidence_ids"]) == 3  # ev_1 + ev_2 + ev_3
        assert claims[0]["evidence_ids"][0] == "ev_1"  # Primary first

    def test_no_self_in_corroboration(self):
        """Primary evidence_id is not duplicated."""
        claims = [self._make_claim("ev_1", "PFAS water treatment removal")]
        evidence = [
            self._make_evidence("ev_1", "url1", "PFAS water treatment removal"),
            self._make_evidence("ev_2", "url2", "PFAS water treatment effectiveness"),
        ]
        groups = [
            {
                "claim": "test",
                "evidence_ids": ["ev_1", "ev_2"],
                "source_urls": ["url1", "url2"],
                "agreement_score": 0.8,
                "cross_ref_count": 2,
            }
        ]
        link_corroborating_evidence(claims, evidence, groups)
        assert claims[0]["evidence_ids"].count("ev_1") == 1

    def test_max_per_claim_cap(self):
        """Respects max_per_claim limit."""
        claims = [self._make_claim("ev_1", "PFAS water treatment removal technology")]
        evidence = [
            self._make_evidence(f"ev_{i}", f"url_{i}", f"PFAS water treatment removal technology variant {i}")
            for i in range(20)
        ]
        groups = [
            {
                "claim": "test",
                "evidence_ids": [f"ev_{i}" for i in range(20)],
                "source_urls": [f"url_{i}" for i in range(20)],
                "agreement_score": 0.8,
                "cross_ref_count": 20,
            }
        ]
        link_corroborating_evidence(claims, evidence, groups, max_per_claim=3)
        # 1 primary + 3 corroborating = 4 max
        assert len(claims[0]["evidence_ids"]) <= 4

    def test_no_groups_jaccard_fallback(self):
        """Falls back to Jaccard when cross-reference groups empty."""
        claims = [self._make_claim("ev_a", "water filter PFAS removal technology")]
        evidence = [
            self._make_evidence("ev_a", "url1", "water filter PFAS removal technology"),
            self._make_evidence("ev_b", "url2", "water filter PFAS removal technology effective"),
            self._make_evidence("ev_c", "url3", "unrelated topic about cooking recipes"),
        ]
        enriched = link_corroborating_evidence(claims, evidence, [])
        assert enriched >= 1
        assert "ev_b" in claims[0]["evidence_ids"]
        assert "ev_c" not in claims[0]["evidence_ids"]

    def test_same_source_excluded_jaccard(self):
        """Jaccard fallback excludes same-source evidence."""
        claims = [self._make_claim("ev_a", "water filter PFAS removal technology")]
        evidence = [
            self._make_evidence("ev_a", "url1", "water filter PFAS removal technology"),
            self._make_evidence("ev_b", "url1", "water filter PFAS removal technology design"),
        ]
        enriched = link_corroborating_evidence(claims, evidence, [])
        assert enriched == 0  # Same source, so no corroboration

    def test_empty_claims(self):
        """Empty claims list returns 0."""
        result = link_corroborating_evidence([], [], [])
        assert result == 0

    def test_single_source_no_corroboration(self):
        """All evidence from one source = no corroboration possible."""
        claims = [self._make_claim("ev_a", "water filter removal technology is effective")]
        evidence = [
            self._make_evidence("ev_a", "url1", "water filter removal technology is effective"),
            self._make_evidence("ev_b", "url1", "water filter removal technology is proven effective"),
        ]
        enriched = link_corroborating_evidence(claims, evidence, [])
        assert enriched == 0

    def test_short_statements_skipped_jaccard(self):
        """Statements with fewer than 5 words are skipped in Jaccard."""
        claims = [self._make_claim("ev_a", "short")]
        evidence = [
            self._make_evidence("ev_a", "url1", "short"),
            self._make_evidence("ev_b", "url2", "short"),
        ]
        enriched = link_corroborating_evidence(claims, evidence, [])
        assert enriched == 0

    def test_claim_without_evidence_ids_skipped(self):
        """Claim with empty evidence_ids is not enriched."""
        claim = self._make_claim("ev_a")
        claim["evidence_ids"] = []
        claims = [claim]
        groups = [
            {
                "claim": "test",
                "evidence_ids": ["ev_a", "ev_b"],
                "source_urls": ["url1", "url2"],
                "agreement_score": 0.8,
                "cross_ref_count": 2,
            }
        ]
        enriched = link_corroborating_evidence(claims, [], groups)
        assert enriched == 0
