"""
Tests for Phase 2e scope-protocol query validator.
"""
from __future__ import annotations

from src.polaris_graph.retrieval.scope_query_validator import (
    validate_amplified_queries,
)


def _mk_protocol() -> dict:
    return {
        "research_question": (
            "What is the efficacy and safety of semaglutide 2.4mg for "
            "weight loss in adults with obesity?"
        ),
        "population": "adults",
        "intervention": "semaglutide",
        "outcome": "weight loss",
    }


def test_on_scope_queries_kept() -> None:
    amplified = [
        "semaglutide weight loss efficacy adults",
        "semaglutide safety obesity trial",
        "2.4 mg semaglutide in overweight adults efficacy trial",
    ]
    result = validate_amplified_queries(amplified, _mk_protocol(), floor=0.15)
    # All three should be kept (good overlap with anchor).
    # research_question is also prepended because always_keep_anchor=True.
    assert len(result.kept) >= 3
    assert result.dropped == []


def test_off_scope_queries_dropped() -> None:
    amplified = [
        "Japan national health insurance elderly care coverage",
        "Blockchain for agricultural supply chain traceability",
        "semaglutide weight loss trial",  # this one is on-scope
    ]
    result = validate_amplified_queries(amplified, _mk_protocol(), floor=0.15)
    dropped_queries = [d[0] for d in result.dropped]
    assert any("Japan" in q for q in dropped_queries)
    assert any("Blockchain" in q for q in dropped_queries)
    # On-scope query must be kept
    assert any("semaglutide" in q.lower() for q in result.kept)


def test_always_keep_anchor_even_if_similarity_low() -> None:
    proto = {
        "research_question": "Efficacy of X.",
        "intervention": "x",
    }
    amplified = ["unrelated query one", "unrelated query two"]
    result = validate_amplified_queries(amplified, proto, floor=0.15)
    # Both amplified should drop
    assert len(result.dropped) == 2
    # But the research question is always kept
    assert "Efficacy of X." in result.kept


def test_dedupes_amplified_queries() -> None:
    amplified = [
        "semaglutide weight loss",
        "semaglutide weight loss",
        "SEMAGLUTIDE WEIGHT LOSS",  # case-insensitive dupe
    ]
    proto = {
        # Use a research_question that does NOT contain "semaglutide weight
        # loss" verbatim so we can count amplified survivors cleanly.
        "research_question": "Drug X therapeutic question.",
        "intervention": "semaglutide",
        "outcome": "weight loss",
    }
    result = validate_amplified_queries(amplified, proto, floor=0.10)
    # The three amplified variants collapse to one unique "semaglutide
    # weight loss" entry. research_question is also added as the anchor
    # but it's a different string.
    amplified_kept = [
        q for q in result.kept if q != proto["research_question"]
    ]
    assert len(amplified_kept) == 1
    assert amplified_kept[0].lower() == "semaglutide weight loss"


def test_empty_amplified_list_still_keeps_anchor() -> None:
    result = validate_amplified_queries([], _mk_protocol(), floor=0.15)
    assert len(result.kept) == 1
    assert result.kept[0].startswith("What is the efficacy")


def test_anchor_tokens_computed_from_pico_fields() -> None:
    proto = {
        "research_question": "Short q.",
        "intervention": "tirzepatide",
        "population": "type 2 diabetes",
        "outcome": "hba1c",
    }
    result = validate_amplified_queries(
        ["tirzepatide diabetes hba1c trial", "unrelated query"],
        proto,
        floor=0.15,
    )
    # Tokens from PICO should contribute to anchor
    assert "tirzepatide" in result.anchor_tokens_used
    assert "hba1c" in result.anchor_tokens_used
    # tirzepatide query should be kept, unrelated should drop
    assert any("tirzepatide" in q.lower() for q in result.kept)
    assert any("unrelated" in d[0].lower() for d in result.dropped)


def test_floor_environment_variable_is_respected(monkeypatch) -> None:
    proto = _mk_protocol()
    # Force a very high floor — most queries will drop
    monkeypatch.setenv("PG_AMPLIFIER_SCOPE_FLOOR", "0.80")
    amplified = ["semaglutide weight loss"]  # only partial overlap
    result = validate_amplified_queries(amplified, proto)
    # Only research_question should survive (anchor kept)
    assert len(result.dropped) == 1
