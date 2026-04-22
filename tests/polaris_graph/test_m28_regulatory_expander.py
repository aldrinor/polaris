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


# ─────────────────────────────────────────────────────────────────────
# Guard tests (Codex audit follow-up, 2026-04-20)
# ─────────────────────────────────────────────────────────────────────


class TestNoHardCodedHostsInModule:
    """Guardrail: regulatory_expander.py must not contain any
    hard-coded agency / host / jurisdiction terms. All such content
    lives only in YAML templates and in test fixtures. If a future
    edit slips a host name into a docstring or comment, this test
    fails and prevents a generalization regression.

    Covers M-28 Codex audit blocker item #1.
    """

    def test_module_contains_no_agency_or_host_strings(self) -> None:
        import pathlib
        p = pathlib.Path(__file__).parent.parent.parent / (
            "src/polaris_graph/retrieval/regulatory_expander.py"
        )
        assert p.exists(), f"expander module missing at {p}"
        text = p.read_text(encoding="utf-8").lower()

        # Banned substrings: regulatory agencies, governmental hosts,
        # jurisdictional acronyms, clinical-domain terms. Any one of
        # these in the expander module signals a generalization leak.
        banned = [
            # US agencies / hosts
            "fda", "sec.gov", "ftc", "gao", "cbo", "epa",
            "whitehouse", "federalregister", "accessdata",
            "congress", "justice.gov",
            # EU / UK / CA agencies
            "ema", "europa.eu", "mhra", "tga", "pmda", "nmpa",
            "hres", "canada", "nice",
            "who.int",
            # Clinical-domain leaks (would indicate hard-coded clinical
            # assumption inside a generic module)
            "mounjaro", "zepbound", "tirzepatide", "surpass", "surmount",
            "semaglutide", "glargine", "degludec", "diabetes",
            "clinical",  # domain name itself
        ]
        leaks = [term for term in banned if term in text]
        assert not leaks, (
            f"regulatory_expander.py contains hard-coded agency/clinical "
            f"terms that belong only in YAML templates or tests: {leaks}"
        )


class TestAnchorCountCap:
    """Codex audit medium #2: enforce the configurable query-count cap.

    PG_SWEEP_MAX_REGULATORY_ANCHORS bounds the number of queries the
    expander emits per call so a template with 50 anchors cannot
    blow up the retrieval budget unexpectedly.
    """

    def test_default_cap_truncates_to_twelve(self, monkeypatch) -> None:
        """M-43 (2026-04-22): default cap raised 10 -> 12 so an
        11-anchor template is not silently truncated."""
        monkeypatch.delenv("PG_SWEEP_MAX_REGULATORY_ANCHORS", raising=False)
        tmpl = {"regulatory_anchors": [f"host{i}.example" for i in range(20)]}
        result = expand_regulatory_queries("q", tmpl)
        assert len(result) == 12
        assert result[0] == "q site:host0.example"
        assert result[-1] == "q site:host11.example"

    def test_env_override_tightens_cap(self, monkeypatch) -> None:
        monkeypatch.setenv("PG_SWEEP_MAX_REGULATORY_ANCHORS", "3")
        tmpl = {"regulatory_anchors": [f"h{i}.gov" for i in range(8)]}
        result = expand_regulatory_queries("q", tmpl)
        assert len(result) == 3

    def test_zero_env_disables_cap(self, monkeypatch) -> None:
        monkeypatch.setenv("PG_SWEEP_MAX_REGULATORY_ANCHORS", "0")
        tmpl = {"regulatory_anchors": [f"h{i}.gov" for i in range(25)]}
        result = expand_regulatory_queries("q", tmpl)
        assert len(result) == 25

    def test_invalid_env_falls_back_to_default(self, monkeypatch) -> None:
        monkeypatch.setenv("PG_SWEEP_MAX_REGULATORY_ANCHORS", "not a number")
        tmpl = {"regulatory_anchors": [f"h{i}.gov" for i in range(15)]}
        result = expand_regulatory_queries("q", tmpl)
        # M-43: default raised 10 -> 12.
        assert len(result) == 12

    def test_negative_env_clamps_to_zero_disables_cap(self, monkeypatch) -> None:
        monkeypatch.setenv("PG_SWEEP_MAX_REGULATORY_ANCHORS", "-5")
        tmpl = {"regulatory_anchors": [f"h{i}.gov" for i in range(15)]}
        result = expand_regulatory_queries("q", tmpl)
        # -5 is clamped to 0 (no cap), so all 15 emitted
        assert len(result) == 15


class TestYamlTemplateIntegration:
    """Codex audit medium #3: prove the templates load and expose the
    new field to scope_gate without breaking the scope protocol flow."""

    def test_clinical_template_loads_with_anchors(self) -> None:
        from polaris_graph.nodes.scope_gate import load_scope_template
        tmpl = load_scope_template("clinical")
        assert isinstance(tmpl, dict)
        anchors = tmpl.get("regulatory_anchors")
        assert isinstance(anchors, list) and len(anchors) > 0, (
            "clinical template must expose non-empty regulatory_anchors"
        )
        # Each anchor must be a host-shaped string (sanity check).
        for a in anchors:
            assert isinstance(a, str) and "/" not in a and " " not in a

    def test_policy_template_loads_with_anchors(self) -> None:
        from polaris_graph.nodes.scope_gate import load_scope_template
        tmpl = load_scope_template("policy")
        assert isinstance(tmpl.get("regulatory_anchors"), list)
        assert len(tmpl["regulatory_anchors"]) > 0

    def test_due_diligence_template_loads_with_anchors(self) -> None:
        from polaris_graph.nodes.scope_gate import load_scope_template
        tmpl = load_scope_template("due_diligence")
        assert isinstance(tmpl.get("regulatory_anchors"), list)
        assert len(tmpl["regulatory_anchors"]) > 0

    def test_template_without_anchors_field_still_loads(self) -> None:
        """Tech template has no regulatory_anchors field (zero-anchor
        domain). scope_gate must still load it, and the expander must
        emit zero queries."""
        from polaris_graph.nodes.scope_gate import load_scope_template
        tmpl = load_scope_template("tech")
        # Either missing or an empty list — either is acceptable.
        assert tmpl.get("regulatory_anchors", []) in ([], None) or (
            isinstance(tmpl.get("regulatory_anchors"), list)
            and len(tmpl["regulatory_anchors"]) == 0
        ) or tmpl.get("regulatory_anchors") is None
        result = expand_regulatory_queries("q", tmpl)
        assert result == []

    def test_clinical_template_expansion_end_to_end(self) -> None:
        """Load the real clinical YAML and run the expander — prove
        the end-to-end config → expansion path emits sensible queries.
        Does not check specific host names (those live in the YAML,
        not in test assertions).

        M-43 (2026-04-22): default cap raised to 12; end-to-end test
        verifies the template fits under the current cap and does not
        silently truncate.
        """
        from polaris_graph.nodes.scope_gate import load_scope_template
        tmpl = load_scope_template("clinical")
        result = expand_regulatory_queries("test question", tmpl)
        # Capped at 12 by default (M-43).
        assert 0 < len(result) <= 12
        # M-43 regression guard: the clinical template must NOT be
        # silently truncated. Count of emitted queries must equal the
        # count of declared anchors in the template.
        declared = [
            a for a in (tmpl.get("regulatory_anchors") or [])
            if isinstance(a, str) and a.strip() and "/" not in a.strip()
        ]
        assert len(result) == len(declared), (
            f"anchor truncation: emitted={len(result)} declared="
            f"{len(declared)}. Cap may be below template size."
        )
        # Each query starts with the base question and has site:{host}.
        for q in result:
            assert q.startswith("test question site:")
            host = q.split("site:", 1)[1]
            assert "/" not in host and " " not in host
