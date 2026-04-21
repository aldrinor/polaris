"""Tests for M-28 Fix #1: regulatory-anchor query expansion.

Generalizable contract (no hard-coded agency names in Python):
  - Empty / missing template → no queries (backwards compat).
  - Template without `regulatory_anchors` key → no queries.
  - Template with `regulatory_anchors: []` → no queries.
  - Template with a list of hosts → one query per host, of the form
    `{question} site:{host}`.
  - Invalid entries (non-strings, URLs with paths, whitespace tokens)
    are dropped silently; valid ones still expand.
  - Duplicate hosts in the template → deduplicated while preserving
    declared order.
  - Empty / whitespace question → no queries (defensive).
"""
from __future__ import annotations

from polaris_graph.retrieval.regulatory_expander import (
    expand_regulatory_queries,
)


class TestEmptyOrMissingTemplate:
    def test_none_template_yields_no_queries(self) -> None:
        assert expand_regulatory_queries("any question", None) == []

    def test_template_without_anchors_key(self) -> None:
        tmpl = {"domain": "clinical", "description": "no anchors here"}
        assert expand_regulatory_queries("q", tmpl) == []

    def test_anchors_empty_list(self) -> None:
        tmpl = {"regulatory_anchors": []}
        assert expand_regulatory_queries("q", tmpl) == []

    def test_anchors_wrong_type_dict(self) -> None:
        """Defensive against YAML corruption — dict instead of list."""
        tmpl = {"regulatory_anchors": {"fda": "gov"}}
        assert expand_regulatory_queries("q", tmpl) == []


class TestValidExpansion:
    def test_single_anchor(self) -> None:
        tmpl = {"regulatory_anchors": ["example.gov"]}
        result = expand_regulatory_queries("tirzepatide safety", tmpl)
        assert result == ["tirzepatide safety site:example.gov"]

    def test_multiple_anchors_in_declared_order(self) -> None:
        tmpl = {"regulatory_anchors": ["a.gov", "b.gov", "c.gov"]}
        result = expand_regulatory_queries("q", tmpl)
        assert result == [
            "q site:a.gov",
            "q site:b.gov",
            "q site:c.gov",
        ]

    def test_anchors_are_lowercased(self) -> None:
        tmpl = {"regulatory_anchors": ["FDA.GOV"]}
        result = expand_regulatory_queries("q", tmpl)
        assert result == ["q site:fda.gov"]

    def test_anchor_whitespace_stripped(self) -> None:
        tmpl = {"regulatory_anchors": ["  fda.gov  "]}
        result = expand_regulatory_queries("q", tmpl)
        assert result == ["q site:fda.gov"]


class TestRejectInvalidEntries:
    def test_non_string_entry_dropped(self) -> None:
        tmpl = {"regulatory_anchors": ["ok.gov", 123, None, "valid.com"]}
        result = expand_regulatory_queries("q", tmpl)
        assert result == ["q site:ok.gov", "q site:valid.com"]

    def test_url_with_path_rejected(self) -> None:
        """`site:` expects a host, not a full URL path."""
        tmpl = {"regulatory_anchors": [
            "https://fda.gov/drugs",  # rejected (contains /)
            "fda.gov/path",            # rejected (contains /)
            "fda.gov",                 # kept
        ]}
        result = expand_regulatory_queries("q", tmpl)
        assert result == ["q site:fda.gov"]

    def test_host_with_space_rejected(self) -> None:
        tmpl = {"regulatory_anchors": ["invalid host.com", "ok.gov"]}
        result = expand_regulatory_queries("q", tmpl)
        assert result == ["q site:ok.gov"]

    def test_empty_string_entry_dropped(self) -> None:
        tmpl = {"regulatory_anchors": ["", "  ", "real.gov"]}
        result = expand_regulatory_queries("q", tmpl)
        assert result == ["q site:real.gov"]


class TestDeduplication:
    def test_duplicate_anchors_deduped_preserving_order(self) -> None:
        tmpl = {"regulatory_anchors": ["a.gov", "b.gov", "a.gov", "c.gov", "b.gov"]}
        result = expand_regulatory_queries("q", tmpl)
        assert result == ["q site:a.gov", "q site:b.gov", "q site:c.gov"]

    def test_case_duplicates_deduped_via_lowercase_normalization(self) -> None:
        tmpl = {"regulatory_anchors": ["FDA.gov", "fda.gov", "FDA.GOV"]}
        result = expand_regulatory_queries("q", tmpl)
        assert result == ["q site:fda.gov"]


class TestEmptyQuestion:
    def test_empty_question_returns_nothing(self) -> None:
        tmpl = {"regulatory_anchors": ["fda.gov"]}
        assert expand_regulatory_queries("", tmpl) == []

    def test_whitespace_only_question_returns_nothing(self) -> None:
        tmpl = {"regulatory_anchors": ["fda.gov"]}
        assert expand_regulatory_queries("   \t\n  ", tmpl) == []

    def test_question_is_trimmed(self) -> None:
        """Leading/trailing whitespace on question should be trimmed
        before concatenation so the emitted query is well-formed."""
        tmpl = {"regulatory_anchors": ["fda.gov"]}
        result = expand_regulatory_queries("  tirzepatide safety  ", tmpl)
        assert result == ["tirzepatide safety site:fda.gov"]


class TestGeneralizationSmokeTests:
    """These tests verify the abstraction works across non-clinical
    domains — satisfies the user's 2026-04-20 mandate that fixes
    must generalize, not hard-code clinical assumptions.
    """

    def test_policy_domain_federal_register(self) -> None:
        tmpl = {"regulatory_anchors": ["federalregister.gov", "gao.gov"]}
        result = expand_regulatory_queries(
            "impact of CMMI bundled payment models", tmpl
        )
        assert result == [
            "impact of CMMI bundled payment models site:federalregister.gov",
            "impact of CMMI bundled payment models site:gao.gov",
        ]

    def test_due_diligence_sec_filings(self) -> None:
        tmpl = {"regulatory_anchors": ["sec.gov", "ftc.gov"]}
        result = expand_regulatory_queries(
            "Novo Nordisk Q3 revenue disclosures", tmpl
        )
        assert result == [
            "Novo Nordisk Q3 revenue disclosures site:sec.gov",
            "Novo Nordisk Q3 revenue disclosures site:ftc.gov",
        ]

    def test_environmental_hypothetical_epa_domain(self) -> None:
        """Hypothetical — no environmental template exists yet, but
        the function must work if one is added with epa.gov."""
        tmpl = {"regulatory_anchors": ["epa.gov", "eea.europa.eu"]}
        result = expand_regulatory_queries(
            "PFAS drinking-water standards", tmpl
        )
        assert result == [
            "PFAS drinking-water standards site:epa.gov",
            "PFAS drinking-water standards site:eea.europa.eu",
        ]
