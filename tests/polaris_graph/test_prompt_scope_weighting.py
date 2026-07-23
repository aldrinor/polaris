"""STEP 5: prompt-derived continuous weights with a complete stream."""

from src.polaris_graph.retrieval.prompt_scope_weighting import (
    bias_queries_by_prompt_scope,
    weight_evidence_stream,
)


def _row(evidence_id, text, **metadata):
    return {
        "evidence_id": evidence_id,
        "source_url": f"https://example.invalid/{evidence_id}",
        "statement": text,
        **metadata,
    }


def test_no_constraints_is_order_noop():
    rows = [_row("a", "first"), _row("b", "second")]
    ordered, ledger = weight_evidence_stream(rows, constraints={})
    assert ordered == rows
    assert ledger["active"] is False
    assert ledger["input_count"] == ledger["output_count"] == 2


def test_soft_coverage_preference_is_continuous_and_keeps_every_row():
    rows = [
        _row("miss", "A different subject", authority_score=0.8),
        _row("match", "Orbital calibration mechanics", authority_score=0.8),
    ]
    ordered, ledger = weight_evidence_stream(
        rows, constraints={"required_coverage": ["orbital calibration"]},
    )
    assert [row["evidence_id"] for row in ordered] == ["match", "miss"]
    assert len(ordered) == len(rows)
    weights = {row["evidence_id"]: row["prompt_scope_weight"] for row in ordered}
    assert 0 < weights["miss"] < weights["match"] <= 1
    assert ledger["input_count"] == ledger["output_count"] == 2


def test_hard_wording_becomes_weight_not_filter():
    rows = [
        _row("requested", "Relevant finding", language="fr"),
        _row("outside", "Other relevant finding", language="en"),
    ]
    ordered, ledger = weight_evidence_stream(rows, constraints={"languages": ["fr"]})
    assert {row["evidence_id"] for row in ordered} == {"requested", "outside"}
    by_id = {row["evidence_id"]: row for row in ordered}
    assert by_id["requested"]["prompt_scope_weight"] == 1.0
    assert 0 < by_id["outside"]["prompt_scope_weight"] < 1.0
    assert any(
        "language" in reason for reason in by_id["outside"]["prompt_scope_reasons"]
    )
    assert ledger["output_count"] == 2


def test_mixed_language_date_and_facet_constraints_are_all_traced():
    rows = [
        _row("aligned", "Thermal transfer coefficient", language="de", year=2024),
        _row("mixed", "Thermal transfer coefficient", language="en", year=2018),
        _row("unknown", "Thermal transfer coefficient"),
    ]
    ordered, ledger = weight_evidence_stream(
        rows,
        constraints={
            "languages": ["de"],
            "recency": "since 2022",
            "required_coverage": ["thermal transfer"],
        },
    )
    assert [row["evidence_id"] for row in ordered][0] == "aligned"
    assert len(ledger["rows"]) == 3
    assert {record["evidence_id"] for record in ledger["rows"]} == {
        "aligned", "mixed", "unknown",
    }
    # Unknown metadata fails open at full eligibility weight; it is never deleted.
    assert any(record["evidence_id"] == "unknown" for record in ledger["rows"])


def test_live_query_bias_uses_prompt_phrases_without_adding_or_dropping_queries():
    queries = ["orbital calibration", "sensor stability"]
    biased = bias_queries_by_prompt_scope(
        queries,
        {"source_types": ["technical report"], "languages": ["de"], "recency": "since 2021"},
    )
    assert len(biased) == len(queries)
    assert all("technical report" in query and "since 2021" in query for query in biased)
    assert biased[0].startswith(queries[0]) and biased[1].startswith(queries[1])


def test_live_fetch_budget_order_uses_scope_weight_without_new_filter():
    from src.polaris_graph.retrieval.live_retriever import _rerank_and_reserve
    from src.polaris_graph.retrieval.prefetch_offtopic_filter import SearchCandidate

    outside = SearchCandidate(
        url="https://example.invalid/outside", title="Topic result", snippet="topic", query_origin="q",
    )
    requested = SearchCandidate(
        url="https://example.invalid/requested", title="Topic result", snippet="topic", query_origin="q",
    )
    outside.language = "en"
    requested.language = "fr"
    chosen = _rerank_and_reserve(
        [outside, requested],
        research_question="topic",
        fetch_cap=1,
        n_seed_injected=0,
        prompt_scope_constraints={"languages": ["fr"]},
    )
    assert [candidate.url for candidate in chosen] == [requested.url]


def test_live_constraint_extractor_uses_central_completion_budget(monkeypatch):
    import src.polaris_graph.instruction.constraint_extractor as extractor
    from src.polaris_graph.retrieval.rq_eligibility import ensure_rq_constraints
    from src.polaris_graph.settings import resolve

    seen = {}

    def fake_extract(prompt, *, max_tokens, **_kwargs):
        seen["prompt"] = prompt
        seen["max_tokens"] = max_tokens
        return {"languages": ["fr"]}

    monkeypatch.setenv("PG_PROMPT_SCOPE_WEIGHTING", "1")
    monkeypatch.setattr(extractor, "extract_constraints", fake_extract)
    protocol = {}
    result = ensure_rq_constraints(protocol, "Use French-language sources")
    assert result == {"languages": ["fr"]}
    assert seen["max_tokens"] == int(resolve("PG_EXTRACTION_MAX_TOKENS"))
