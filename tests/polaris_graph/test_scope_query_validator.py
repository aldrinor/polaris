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
    # Force a very high floor — a query with only PARTIAL token overlap drops.
    monkeypatch.setenv("PG_AMPLIFIER_SCOPE_FLOOR", "0.80")
    # I-retr-001 (#1340): default measure is now `containment`, under which a fully
    # on-topic short query scores 1.0 regardless of floor. Use a PARTIAL-overlap query
    # (1 of 4 tokens in the anchor -> containment 0.25 < 0.80) so the floor still bites.
    amplified = ["semaglutide marathon training schedule"]
    result = validate_amplified_queries(amplified, proto)
    # Only research_question should survive (anchor kept)
    assert len(result.dropped) == 1


def test_default_similarity_measure_is_containment(monkeypatch) -> None:
    """I-retr-001 (#1340): the CODE default measure must be containment (not jaccard),
    so every run path — not only the Gate-B slate — clears short on-topic queries."""
    from src.polaris_graph.retrieval.scope_query_validator import _select_sim_measure

    # clear any leaked env so we assert the CODE default, not an ambient override
    monkeypatch.delenv("PG_SCOPE_SIM_MEASURE", raising=False)
    name, _ = _select_sim_measure()
    assert name == "containment"


def test_long_anchor_short_query_kept_under_default(monkeypatch) -> None:
    """I-retr-001 (#1340) regression — the drb_72 breadth collapse.

    A short, clearly on-topic query against a LONG research-question anchor must be
    KEPT. Under the old SYMMETRIC-jaccard default it scored ~|q|/|anchor| (drb_72:
    ~8/136 ≈ 0.06) and was wrongly dropped, collapsing breadth (kept=2 of 35). Under
    the containment default it scores ~1.0 and survives. Uses bare defaults (no
    explicit floor/measure) so it guards the actual run-path behaviour.
    """
    # ensure no leaked env from another test overrides the code defaults
    monkeypatch.delenv("PG_SCOPE_SIM_MEASURE", raising=False)
    monkeypatch.delenv("PG_AMPLIFIER_SCOPE_FLOOR", raising=False)
    long_question = (
        "I am researching the impact of generative AI on the future labor market. "
        "The report must summarize the existing academic literature's positive views, "
        "negative views, specific challenges, and future opportunities regarding "
        "generative artificial intelligence's impact on employment, displacement, wage "
        "polarization, task reinstatement, firm-level adoption, productivity, reskilling, "
        "and the broader Fourth Industrial Revolution restructuring of occupations."
    )
    proto = {"research_question": long_question}
    amplified = [
        "generative AI wage polarization",
        "labor market displacement employment",
        "task reinstatement productivity reskilling",
    ]
    result = validate_amplified_queries(amplified, proto)  # bare defaults
    assert len(result.anchor_tokens_used) > 20, (
        f"expected a long anchor, got {len(result.anchor_tokens_used)}"
    )
    # all three short on-topic queries survive under the containment default
    assert result.dropped == [], f"on-topic short queries wrongly dropped: {result.dropped}"
    assert len(result.kept) >= 4  # 3 amplified + the anchor
