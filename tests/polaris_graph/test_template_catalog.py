"""Tests for src/polaris_graph/audit_ir/template_catalog.py (M-10)."""

from __future__ import annotations

import pytest

from src.polaris_graph.audit_ir.template_catalog import (
    CuratedTemplate,
    TEMPLATE_CATALOG,
    get_template,
    list_catalog,
)


def test_catalog_is_nonempty() -> None:
    assert len(TEMPLATE_CATALOG) >= 1


def test_v30_clinical_in_catalog() -> None:
    """Phase B requires v30_clinical to be in the catalog so the
    UI can surface it on the scope page."""
    tmpl = get_template("v30_clinical")
    assert tmpl is not None
    assert tmpl.template_id == "v30_clinical"
    assert tmpl.display_name
    assert tmpl.description
    assert tmpl.scope_summary
    assert tmpl.scope_keywords
    assert tmpl.scope_examples


def test_get_template_unknown_returns_none() -> None:
    assert get_template("does_not_exist") is None


def test_list_catalog_returns_tuple() -> None:
    cat = list_catalog()
    assert isinstance(cat, tuple)
    assert all(isinstance(t, CuratedTemplate) for t in cat)


def test_template_id_unique() -> None:
    ids = [t.template_id for t in TEMPLATE_CATALOG]
    assert len(ids) == len(set(ids)), "duplicate template_id in catalog"


def test_template_dataclass_is_frozen() -> None:
    """Catalog entries must be immutable so callers can't mutate
    shared state."""
    tmpl = get_template("v30_clinical")
    assert tmpl is not None
    with pytest.raises((AttributeError, Exception)):
        tmpl.template_id = "mutated"  # type: ignore[misc]


def test_scope_examples_are_concrete_questions() -> None:
    """Examples should be real-shape questions, not slogans.
    Heuristic: at least 5 words and a question word or '?'."""
    for tmpl in TEMPLATE_CATALOG:
        for ex in tmpl.scope_examples:
            words = ex.split()
            assert len(words) >= 5, (
                f"scope_example too short for {tmpl.template_id}: {ex!r}"
            )


def test_scope_keywords_are_lowercase() -> None:
    """Keywords must be lowercased so the classifier's case-fold
    tokenization gives stable matches."""
    for tmpl in TEMPLATE_CATALOG:
        for kw in tmpl.scope_keywords:
            assert kw == kw.lower(), (
                f"scope_keyword {kw!r} for {tmpl.template_id} is not lowercase"
            )


def test_scope_summary_documents_in_and_out() -> None:
    """Per FINAL_PLAN scope-page reinforcement: scope_summary must
    document both IN-scope and OUT-of-scope to set honest expectations."""
    for tmpl in TEMPLATE_CATALOG:
        summary = tmpl.scope_summary.lower()
        assert "in scope" in summary, (
            f"scope_summary for {tmpl.template_id} missing IN-scope section"
        )
        assert "out of scope" in summary, (
            f"scope_summary for {tmpl.template_id} missing OUT-of-scope section"
        )
