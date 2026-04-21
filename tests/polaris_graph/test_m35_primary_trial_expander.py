"""Tests for M-35: primary-trial-name query expansion.

Generalizable contract (no hard-coded trial/drug names in Python):
  - Empty / missing template → no queries (backwards compat).
  - Template without `per_query_primary_trial_anchors` key → no queries.
  - Slug not present in the per-query dict → no queries.
  - Empty list for a slug → no queries.
  - Non-empty list for a slug → one query per anchor of the form
    `"{anchor}" {question}`.
  - Invalid entries (non-strings, whitespace-containing tokens, empty
    strings, double-quote chars) are dropped silently.
  - Duplicate anchors → deduped preserving declared order.
  - Empty / whitespace question → no queries.
  - PG_SWEEP_MAX_PRIMARY_TRIAL_ANCHORS env var bounds emission.
"""
from __future__ import annotations

from src.polaris_graph.retrieval.primary_trial_expander import (
    expand_primary_trial_queries,
)


class TestEmptyOrMissingTemplate:
    def test_none_template_yields_no_queries(self) -> None:
        assert expand_primary_trial_queries("q", None, "some_slug") == []

    def test_template_without_per_query_key(self) -> None:
        tmpl = {"domain": "clinical", "description": "no per_query here"}
        assert expand_primary_trial_queries("q", tmpl, "some_slug") == []

    def test_per_query_wrong_type_list(self) -> None:
        """Defensive against YAML corruption — list instead of dict."""
        tmpl = {"per_query_primary_trial_anchors": ["TRIAL-1"]}
        assert expand_primary_trial_queries("q", tmpl, "some_slug") == []

    def test_slug_missing_from_dict(self) -> None:
        tmpl = {"per_query_primary_trial_anchors": {"other_slug": ["TRIAL-1"]}}
        assert expand_primary_trial_queries("q", tmpl, "target_slug") == []

    def test_slug_value_not_a_list(self) -> None:
        """Slug value must be a list. Dict/str/int → no queries."""
        tmpl = {"per_query_primary_trial_anchors": {"s": "TRIAL-1"}}
        assert expand_primary_trial_queries("q", tmpl, "s") == []

    def test_slug_empty_list(self) -> None:
        tmpl = {"per_query_primary_trial_anchors": {"s": []}}
        assert expand_primary_trial_queries("q", tmpl, "s") == []


class TestValidExpansion:
    def test_single_anchor(self) -> None:
        tmpl = {"per_query_primary_trial_anchors": {"s": ["TRIAL-A"]}}
        result = expand_primary_trial_queries("efficacy safety", tmpl, "s")
        assert result == ['"TRIAL-A" efficacy safety']

    def test_multiple_anchors_in_declared_order(self) -> None:
        tmpl = {"per_query_primary_trial_anchors": {
            "s": ["TRIAL-A", "TRIAL-B", "TRIAL-C"]
        }}
        result = expand_primary_trial_queries("q", tmpl, "s")
        assert result == ['"TRIAL-A" q', '"TRIAL-B" q', '"TRIAL-C" q']

    def test_anchor_case_preserved(self) -> None:
        """Unlike M-28 host names, trial names are case-preserved
        (SURPASS-1 vs Surpass-1 may matter for exact quoted match)."""
        tmpl = {"per_query_primary_trial_anchors": {"s": ["Trial-ABC"]}}
        result = expand_primary_trial_queries("q", tmpl, "s")
        assert result == ['"Trial-ABC" q']

    def test_anchor_whitespace_stripped(self) -> None:
        tmpl = {"per_query_primary_trial_anchors": {"s": ["  TRIAL-1  "]}}
        result = expand_primary_trial_queries("q", tmpl, "s")
        assert result == ['"TRIAL-1" q']

    def test_multiple_slugs_isolated(self) -> None:
        """Only the requested slug's anchors are returned."""
        tmpl = {"per_query_primary_trial_anchors": {
            "slug_a": ["A-1", "A-2"],
            "slug_b": ["B-1"],
        }}
        assert expand_primary_trial_queries("q", tmpl, "slug_a") == [
            '"A-1" q', '"A-2" q'
        ]
        assert expand_primary_trial_queries("q", tmpl, "slug_b") == [
            '"B-1" q'
        ]


class TestRejectInvalidEntries:
    def test_non_string_entry_dropped(self) -> None:
        tmpl = {"per_query_primary_trial_anchors": {"s": [
            "OK-1", 123, None, "OK-2",
        ]}}
        result = expand_primary_trial_queries("q", tmpl, "s")
        assert result == ['"OK-1" q', '"OK-2" q']

    def test_trial_with_space_rejected(self) -> None:
        """Quoted query `"TRIAL A" q` would be parsed OK by Serper
        but trial names are conventionally hyphenated tokens. A
        space-containing entry is more likely an authoring mistake
        (e.g. pasting sentence fragments) than an intentional name."""
        tmpl = {"per_query_primary_trial_anchors": {"s": [
            "BAD ENTRY", "OK-1",
        ]}}
        result = expand_primary_trial_queries("q", tmpl, "s")
        assert result == ['"OK-1" q']

    def test_double_quote_in_entry_rejected(self) -> None:
        """A `"` inside the anchor would break the outer `"{anchor}"`
        quoting and produce a malformed query."""
        tmpl = {"per_query_primary_trial_anchors": {"s": [
            'BAD"-1', "OK-1",
        ]}}
        result = expand_primary_trial_queries("q", tmpl, "s")
        assert result == ['"OK-1" q']

    def test_empty_string_entry_dropped(self) -> None:
        tmpl = {"per_query_primary_trial_anchors": {"s": [
            "", "  ", "REAL-1",
        ]}}
        result = expand_primary_trial_queries("q", tmpl, "s")
        assert result == ['"REAL-1" q']

    def test_tab_in_entry_rejected(self) -> None:
        """M-35 pass-2 Codex blocker fix: `str.strip()` removes only
        leading/trailing whitespace. Interior tab must be caught by
        the `any(ch.isspace() for ch in stripped)` guard, not by the
        original narrower `" " in stripped` check."""
        tmpl = {"per_query_primary_trial_anchors": {"s": [
            "BAD\tENTRY", "OK-1",
        ]}}
        result = expand_primary_trial_queries("q", tmpl, "s")
        assert result == ['"OK-1" q']

    def test_newline_in_entry_rejected(self) -> None:
        """YAML block scalars can embed newlines. Same whitespace
        class as the tab case — must be dropped."""
        tmpl = {"per_query_primary_trial_anchors": {"s": [
            "BAD\nENTRY", "OK-1",
        ]}}
        result = expand_primary_trial_queries("q", tmpl, "s")
        assert result == ['"OK-1" q']

    def test_carriage_return_in_entry_rejected(self) -> None:
        """Windows line-endings in a copy-pasted YAML fragment could
        sneak in a `\\r`. Must be dropped."""
        tmpl = {"per_query_primary_trial_anchors": {"s": [
            "BAD\rENTRY", "OK-1",
        ]}}
        result = expand_primary_trial_queries("q", tmpl, "s")
        assert result == ['"OK-1" q']

    def test_vertical_tab_in_entry_rejected(self) -> None:
        """Non-regression: vertical tab (U+000B) and form-feed
        (U+000C) are also whitespace per Python's isspace()."""
        tmpl = {"per_query_primary_trial_anchors": {"s": [
            "BAD\x0bENTRY", "BAD\x0cENTRY", "OK-1",
        ]}}
        result = expand_primary_trial_queries("q", tmpl, "s")
        assert result == ['"OK-1" q']

    def test_backslash_in_entry_rejected(self) -> None:
        """M-35 pass-2 Codex medium: a trailing `\\` could survive
        as `"BAD\\" q` and escape-eat the closing quote in some
        downstream search-query parsers. Drop defensively."""
        tmpl = {"per_query_primary_trial_anchors": {"s": [
            "BAD\\", "BAD\\MIDDLE", "OK-1",
        ]}}
        result = expand_primary_trial_queries("q", tmpl, "s")
        assert result == ['"OK-1" q']


class TestDeduplication:
    def test_duplicate_anchors_deduped_preserving_order(self) -> None:
        tmpl = {"per_query_primary_trial_anchors": {"s": [
            "A-1", "B-1", "A-1", "C-1", "B-1",
        ]}}
        result = expand_primary_trial_queries("q", tmpl, "s")
        assert result == ['"A-1" q', '"B-1" q', '"C-1" q']


class TestEmptyQuestion:
    def test_empty_question_returns_nothing(self) -> None:
        tmpl = {"per_query_primary_trial_anchors": {"s": ["A-1"]}}
        assert expand_primary_trial_queries("", tmpl, "s") == []

    def test_whitespace_only_question_returns_nothing(self) -> None:
        tmpl = {"per_query_primary_trial_anchors": {"s": ["A-1"]}}
        assert expand_primary_trial_queries("  \t\n ", tmpl, "s") == []

    def test_question_is_trimmed(self) -> None:
        tmpl = {"per_query_primary_trial_anchors": {"s": ["A-1"]}}
        result = expand_primary_trial_queries(
            "  tirzepatide safety  ", tmpl, "s"
        )
        assert result == ['"A-1" tirzepatide safety']


class TestEmptySlug:
    def test_empty_slug_returns_nothing(self) -> None:
        tmpl = {"per_query_primary_trial_anchors": {"": ["A-1"]}}
        assert expand_primary_trial_queries("q", tmpl, "") == []

    def test_whitespace_slug_returns_nothing(self) -> None:
        tmpl = {"per_query_primary_trial_anchors": {"   ": ["A-1"]}}
        assert expand_primary_trial_queries("q", tmpl, "   ") == []

    def test_non_string_slug_returns_nothing(self) -> None:
        tmpl = {"per_query_primary_trial_anchors": {"s": ["A-1"]}}
        # type: ignore[arg-type] — intentional wrong type for safety
        assert expand_primary_trial_queries("q", tmpl, 123) == []  # type: ignore[arg-type]


class TestAnchorCountCap:
    """PG_SWEEP_MAX_PRIMARY_TRIAL_ANCHORS bounds the number of queries
    the expander emits so a template with 50 anchors cannot blow up
    the retrieval budget unexpectedly."""

    def test_default_cap_truncates_to_fifteen(self, monkeypatch) -> None:
        monkeypatch.delenv("PG_SWEEP_MAX_PRIMARY_TRIAL_ANCHORS", raising=False)
        tmpl = {"per_query_primary_trial_anchors": {
            "s": [f"T-{i}" for i in range(25)]
        }}
        result = expand_primary_trial_queries("q", tmpl, "s")
        assert len(result) == 15
        assert result[0] == '"T-0" q'
        assert result[-1] == '"T-14" q'

    def test_env_override_tightens_cap(self, monkeypatch) -> None:
        monkeypatch.setenv("PG_SWEEP_MAX_PRIMARY_TRIAL_ANCHORS", "3")
        tmpl = {"per_query_primary_trial_anchors": {
            "s": [f"T-{i}" for i in range(10)]
        }}
        result = expand_primary_trial_queries("q", tmpl, "s")
        assert len(result) == 3

    def test_zero_env_disables_cap(self, monkeypatch) -> None:
        monkeypatch.setenv("PG_SWEEP_MAX_PRIMARY_TRIAL_ANCHORS", "0")
        tmpl = {"per_query_primary_trial_anchors": {
            "s": [f"T-{i}" for i in range(30)]
        }}
        result = expand_primary_trial_queries("q", tmpl, "s")
        assert len(result) == 30

    def test_invalid_env_falls_back_to_default(self, monkeypatch) -> None:
        monkeypatch.setenv(
            "PG_SWEEP_MAX_PRIMARY_TRIAL_ANCHORS", "not a number"
        )
        tmpl = {"per_query_primary_trial_anchors": {
            "s": [f"T-{i}" for i in range(25)]
        }}
        result = expand_primary_trial_queries("q", tmpl, "s")
        assert len(result) == 15  # default

    def test_negative_env_clamps_to_zero_disables_cap(
        self, monkeypatch
    ) -> None:
        monkeypatch.setenv("PG_SWEEP_MAX_PRIMARY_TRIAL_ANCHORS", "-5")
        tmpl = {"per_query_primary_trial_anchors": {
            "s": [f"T-{i}" for i in range(25)]
        }}
        result = expand_primary_trial_queries("q", tmpl, "s")
        # -5 clamps to 0 (no cap) → all 25 emitted.
        assert len(result) == 25


class TestYamlTemplateSchemaCoexistence:
    """M-35 pass-2 Codex medium #2: prove the templates load and
    expose the correct per-query anchors, that M-28 and M-35 fields
    coexist without breaking, and that templates without M-35 fields
    still load with no-op expansion.
    """

    def test_clinical_template_loads_with_both_m28_and_m35_keys(self) -> None:
        from src.polaris_graph.nodes.scope_gate import load_scope_template
        tmpl = load_scope_template("clinical")
        assert isinstance(tmpl, dict)
        # M-28 field
        reg = tmpl.get("regulatory_anchors")
        assert isinstance(reg, list) and len(reg) > 0
        # M-35 field
        by_slug = tmpl.get("per_query_primary_trial_anchors")
        assert isinstance(by_slug, dict) and len(by_slug) > 0

    def test_clinical_template_exposes_tirzepatide_trial_anchors(self) -> None:
        """Generic check: at least one slug in the clinical template
        has a non-empty anchor list, and the expander emits queries
        for it. Does NOT assert trial names — those live in YAML,
        not in test assertions (generalization discipline)."""
        from src.polaris_graph.nodes.scope_gate import load_scope_template
        tmpl = load_scope_template("clinical")
        by_slug = tmpl.get("per_query_primary_trial_anchors", {})
        assert isinstance(by_slug, dict)
        # Find first slug with a non-empty list and verify expansion.
        for slug, anchors in by_slug.items():
            if isinstance(anchors, list) and anchors:
                result = expand_primary_trial_queries(
                    "test question", tmpl, slug
                )
                assert 0 < len(result) <= 15  # default cap
                for q in result:
                    assert q.startswith('"') and '" test question' in q
                return
        raise AssertionError(
            "clinical template has no populated "
            "per_query_primary_trial_anchors slug"
        )

    def test_policy_template_has_no_m35_field_and_expander_noop(self) -> None:
        """Policy template has regulatory_anchors but no M-35 field.
        Expander must still return []."""
        from src.polaris_graph.nodes.scope_gate import load_scope_template
        tmpl = load_scope_template("policy")
        # M-28 field present
        assert isinstance(tmpl.get("regulatory_anchors"), list)
        # M-35 field absent (or empty)
        assert tmpl.get("per_query_primary_trial_anchors", {}) in ({}, None)
        # Expander is a no-op.
        assert expand_primary_trial_queries(
            "q", tmpl, "any_slug"
        ) == []

    def test_tech_template_has_neither_field_and_expander_noop(self) -> None:
        """Tech template has no M-28 or M-35 fields — both expanders
        are pure no-ops."""
        from src.polaris_graph.nodes.scope_gate import load_scope_template
        tmpl = load_scope_template("tech")
        assert expand_primary_trial_queries(
            "q", tmpl, "any_slug"
        ) == []


class TestNoHardCodedTrialsInModule:
    """Guardrail: primary_trial_expander.py must not contain any
    hard-coded trial / drug / domain terms. Same discipline as M-28's
    regulatory_expander. If a future edit slips a trial name into a
    docstring or comment, this test fails — preventing a
    generalization regression.

    NOTE: the module docstring legitimately references the Codex pass
    11 gap that motivated the fix, so it mentions SURPASS/SURMOUNT/
    tirzepatide once in prose. Acceptable: the *data* (anchor list)
    is elsewhere. To avoid fighting the docstring, this test checks
    only executable code (functions and module constants), not
    docstrings."""

    def test_executable_code_contains_no_trial_names(self) -> None:
        import ast
        import pathlib

        p = pathlib.Path(__file__).parent.parent.parent / (
            "src/polaris_graph/retrieval/primary_trial_expander.py"
        )
        assert p.exists(), f"expander module missing at {p}"
        source = p.read_text(encoding="utf-8")
        tree = ast.parse(source)

        # Banned substrings in executable code only (no docstrings).
        banned = [
            "surpass", "surmount", "step", "select", "leader", "sustain",
            "pioneer", "rewind", "award", "grade",
            "tirzepatide", "semaglutide", "liraglutide", "dulaglutide",
            "mounjaro", "zepbound", "ozempic", "wegovy",
            "diabetes", "obesity",
            "fda", "ema", "nice",
        ]

        # Walk AST, collect constants and names EXCLUDING docstrings.
        executable_strings: list[str] = []

        def _is_docstring(node, parent) -> bool:
            return (
                isinstance(node, ast.Expr)
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)
                and isinstance(
                    parent,
                    (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                     ast.ClassDef),
                )
                and parent.body
                and parent.body[0] is node
            )

        class StringCollector(ast.NodeVisitor):
            def __init__(self):
                self._skip = set()

            def visit_Module(self, node):
                if (
                    node.body
                    and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)
                    and isinstance(node.body[0].value.value, str)
                ):
                    self._skip.add(id(node.body[0]))
                self.generic_visit(node)

            def _skip_docstring(self, node):
                if (
                    node.body
                    and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)
                    and isinstance(node.body[0].value.value, str)
                ):
                    self._skip.add(id(node.body[0]))

            def visit_FunctionDef(self, node):
                self._skip_docstring(node)
                self.generic_visit(node)

            def visit_AsyncFunctionDef(self, node):
                self._skip_docstring(node)
                self.generic_visit(node)

            def visit_ClassDef(self, node):
                self._skip_docstring(node)
                self.generic_visit(node)

            def visit_Expr(self, node):
                if id(node) in self._skip:
                    return
                self.generic_visit(node)

            def visit_Constant(self, node):
                if isinstance(node.value, str):
                    executable_strings.append(node.value)

            def visit_Name(self, node):
                executable_strings.append(node.id)

        StringCollector().visit(tree)

        haystack = "\n".join(executable_strings).lower()
        leaks = [term for term in banned if term in haystack]
        assert not leaks, (
            f"primary_trial_expander.py executable code contains "
            f"hard-coded trial/drug/domain terms: {leaks}"
        )
