"""Central config contracts for the Step 1/3-7 implementation."""

from src.polaris_graph.settings import resolve


def test_new_behavior_gates_default_off(monkeypatch):
    flags = (
        "PG_SYNTHESIS_TABLE_CONSTRUCT",
        "PG_SUMMARY_TABLE_COMPOSE",
        "PG_PROMPT_SCOPE_WEIGHTING",
        "PG_NARRATIVE_ATTRIBUTION",
        "PG_FACET_EVIDENCE_PACKS",
        "PG_BASKET_SYNTHESIS",
        "PG_COVERAGE_OBLIGATIONS",
    )
    for flag in flags:
        monkeypatch.delenv(flag, raising=False)
        assert resolve(flag) == ""


def test_route_all_has_one_central_champion_default(monkeypatch):
    monkeypatch.delenv("PG_ROUTE_ALL_BASKETS", raising=False)
    assert resolve("PG_ROUTE_ALL_BASKETS") == "1"
