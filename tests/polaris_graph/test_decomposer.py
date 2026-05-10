"""Tests for I-decompose-001 — multi-question decomposition (Path G)."""

from __future__ import annotations

import pytest

from src.polaris_graph.decomposer import (
    DecomposedQuestion,
    decompose,
)


def test_simple_question_passes_through_as_single_subquestion():
    """No aspect markers → return original question as 1-of-1 element."""
    parts = decompose("Does tirzepatide work for type 2 diabetes?")
    assert len(parts) == 1
    assert parts[0].total == 1
    assert parts[0].index == 0
    assert parts[0].aspect == "full"
    assert "tirzepatide" in parts[0].sub_question


def test_multi_aspect_considering_decomposes():
    """`...considering A, B, C, and D` → 4 sub-questions."""
    parts = decompose(
        "How do tirzepatide and semaglutide compare in T2DM, "
        "considering efficacy, safety, cost, and availability?"
    )
    assert len(parts) == 4
    aspects = [p.aspect for p in parts]
    assert aspects == ["efficacy", "safety", "cost", "availability"]
    for i, p in enumerate(parts):
        assert p.index == i
        assert p.total == 4
        assert p.parent_question == (
            "How do tirzepatide and semaglutide compare in T2DM, "
            "considering efficacy, safety, cost, and availability?"
        )


def test_acceptance_canonical_example():
    """Issue body explicit example: tirzepatide vs semaglutide T2DM
    decomposes to efficacy / safety / cost / availability.
    """
    parts = decompose(
        "Compare tirzepatide vs semaglutide in T2DM, "
        "considering efficacy, safety, cost, and availability"
    )
    assert len(parts) == 4
    for aspect, p in zip(["efficacy", "safety", "cost", "availability"], parts):
        assert p.aspect == aspect
        assert "tirzepatide" in p.sub_question.lower()
        assert "semaglutide" in p.sub_question.lower()
        assert aspect in p.sub_question.lower()


def test_aspect_cap_truncates_with_others_bucket():
    """If aspects exceed max_sub, the last bucket is 'other considerations'."""
    q = (
        "How do GLP-1 agonists compare with respect to "
        "efficacy, safety, cost, availability, prescription rate, "
        "side effect profile, dosing, and patient adherence?"
    )
    parts = decompose(q, max_sub=4)
    assert len(parts) == 4
    assert parts[-1].aspect == "other considerations"
    # The first 3 aspects should be the literal first 3 from the list
    assert [p.aspect for p in parts[:3]] == ["efficacy", "safety", "cost"]


def test_question_with_in_terms_of_marker():
    parts = decompose(
        "Compare drug A and drug B in terms of efficacy, safety, and cost"
    )
    assert len(parts) == 3
    assert [p.aspect for p in parts] == ["efficacy", "safety", "cost"]


def test_question_with_across_marker():
    parts = decompose(
        "Survey of tirzepatide outcomes across efficacy, safety, and "
        "regulatory approvals"
    )
    assert len(parts) == 3
    assert "regulatory approvals" in [p.aspect for p in parts]


def test_empty_question_returns_empty():
    assert decompose("") == []
    assert decompose("   ") == []


def test_decomposed_question_is_immutable():
    """DecomposedQuestion is frozen; downstream pipeline can rely on
    hash-stable identity for caching."""
    parts = decompose("Q considering a, b")
    with pytest.raises(Exception):
        parts[0].sub_question = "tampered"


def test_no_double_question_mark_in_sub_question():
    """Stripping trailing ? + adding ? back must not produce '??'."""
    parts = decompose("How do A and B compare considering speed and cost?")
    for p in parts:
        assert not p.sub_question.endswith("??")
        assert p.sub_question.endswith("?")


def test_filters_short_aspect_artifacts():
    """Single-char or 2-char artifacts (e.g., dangling punctuation)
    must not become aspects.
    """
    parts = decompose("Q considering a, x, and efficacy")
    # 'a' and 'x' are 1-char; should be filtered
    aspects = [p.aspect for p in parts]
    assert "a" not in aspects
    assert "x" not in aspects
    assert "efficacy" in aspects
