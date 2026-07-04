"""R2 x R5 interaction (I-deepfix-001, #1344) — sub-entity + multilingual widen-only.

Codex iter-2 found a NOVEL P1 on the MULTILINGUAL path: the R2 sub-entity expansion
(``PG_SUBENTITY_QUERY_EXPANSION``) lengthened ``seed_queries`` BEFORE the R5 multilingual
block, and ``language_profile.expand_queries_for_profile`` caps its native-language additions
at ``max(PG_MULTILINGUAL_MAX_QUERIES, len(base))``. Once the R2 slice pushed ``base`` OVER
that cap, the native-language queries a flag-OFF run WOULD issue were DROPPED — breaking the
§-1.3 strict-superset (widen-only) contract on non-English (e.g. Chinese) tasks.

The fix orders R5 BEFORE R2 so R5 expands the PRE-R2 baseline (identical input to the flag-OFF
path), then R2's proven ``widen_with_sub_entities`` layers the bounded sub-entity slice ON TOP
and RAISES the effective budget. The result: on a non-English task the flag-ON issued query set
is a strict SUPERSET of the flag-OFF set — every native-language query is STILL issued (zero
dropped) AND the sub-entity queries are added. English/facet-path behaviour is unchanged.

Offline / $0 / no network / no GPU; the LLM + retrieval are deterministic stubs.
"""
from __future__ import annotations

from src.polaris_graph.retrieval import fs_researcher_query_gen as fsr


# A MIXED-language question: a Chinese (zh) body (source of native-script queries via R5) plus
# English content words (source of the pure-ASCII scope anchor R2's sub-entity queries carry).
# So native queries carry CJK and sub-entity queries do NOT — the two widenings are cleanly
# distinguishable in the issued set.
QUESTION = (
    "人工智能对劳动力市场的重构影响 "
    "restructuring impact of artificial intelligence on the labor market"
)

# Long-tail NICHE sub-entities the abstract facet frontier never names (the R2 recall lever).
_SUB_ENTITIES = "\n".join(["Radiologists", "Paralegals", "Truck drivers", "Warehouse workers"])
_NICHES = ("radiologists", "paralegals", "truck drivers", "warehouse workers")

# A small English facet frontier: 6 seeds. With PG_MULTILINGUAL_MAX_QUERIES=10 the flag-OFF
# native additions get 10-6=4 slots (native queries ARE issued). The R2 sub-entity slice (4
# niches + 6 perspectives = 10) would push the base to 16 > 10 — the exact condition that made
# the pre-fix (R2-before-R5) code drop EVERY native query (the Codex/Fable iter-2 P1).
_ENGLISH_FACETS = [f"english facet query number {i}" for i in range(6)]


def _has_cjk(text: str) -> bool:
    return any("一" <= ch <= "鿿" for ch in text or "")


class _Facet:
    def __init__(self, queries):
        self.name = "facet"
        self.queries = queries


def _sub_entity_llm(prompt: str) -> str:
    """Stub policy: return the named sub-entities for R2's enumeration prompt; nothing else.

    (``plan_expert_facets`` is stubbed directly, so its facet prompt never reaches this llm;
    the R5 translator prompt is unused because the zh body carries native script already.)
    """
    if "NAMED sub-entities" in prompt:
        return _SUB_ENTITIES + "\n"
    return ""


def _wire_stubs(monkeypatch):
    """Deterministic offline frontier: stub the expert-facet planner + per-query retrieve, and
    keep the facet-completeness expansion loop OFF so the comparison isolates the R2 x R5 seed
    frontier. Returns the list capturing ISSUED (fetched) queries."""
    from src.polaris_graph.retrieval import expert_facet_planner as efp
    from src.polaris_graph.retrieval import facet_completeness as fc

    monkeypatch.setattr(
        efp, "plan_expert_facets",
        lambda question, llm: [_Facet(list(_ENGLISH_FACETS))],
    )
    monkeypatch.setattr(fc, "facet_completeness_enabled", lambda: False)

    issued: list[str] = []

    class _Result:
        evidence_rows: list = []

    def _retrieve(*, research_question, **kwargs):
        issued.append(research_question)
        return _Result()

    return issued, _retrieve


def _base_env(monkeypatch):
    """Shared env for BOTH runs: multilingual ON with a small cap that the R2 slice would push
    the base over; a comfortably large FS-Researcher budget so the seed loop issues everything;
    all sub-entity knobs at their defaults. Both flags are set EXPLICITLY in each run so shell
    env pollution cannot flip a result."""
    monkeypatch.setenv("PG_MULTILINGUAL_RETRIEVAL", "1")
    monkeypatch.setenv("PG_MULTILINGUAL_MAX_QUERIES", "10")
    monkeypatch.setenv("PG_QGEN_FS_RESEARCHER_MAX_QUERIES", "35")
    monkeypatch.delenv("PG_SUBENTITY_MAX_ENTITIES", raising=False)
    monkeypatch.delenv("PG_SUBENTITY_MAX_PERSPECTIVES", raising=False)
    monkeypatch.delenv("PG_SUBENTITY_QUERY_RESERVE", raising=False)


def _issue(monkeypatch, subentity_on: bool):
    _base_env(monkeypatch)
    if subentity_on:
        monkeypatch.setenv("PG_SUBENTITY_QUERY_EXPANSION", "1")
    else:
        monkeypatch.delenv("PG_SUBENTITY_QUERY_EXPANSION", raising=False)
    issued, retrieve = _wire_stubs(monkeypatch)
    queries, results = fsr._plan_expert_facet_queries(
        QUESTION, llm=_sub_entity_llm, per_query_retrieve=retrieve,
    )
    # Every issued query routed through per_query_retrieve exactly once (drops ZERO sources).
    assert issued == queries, "every issued query must route through per_query_retrieve"
    assert len(results) == len(queries)
    return queries


def test_subentity_on_multilingual_is_strict_superset_of_off(monkeypatch):
    """§-1.3 widen-only, the Codex/Fable iter-2 P1: with BOTH flags ON on a non-English task,
    the flag-ON issued set is a strict SUPERSET of the flag-OFF set — every native-language
    query still issued (zero dropped) AND the sub-entity queries added.

    RED on the pre-fix (R2-before-R5) order: the R2 slice pushed the base over
    PG_MULTILINGUAL_MAX_QUERIES, so ``expand_queries_for_profile`` dropped every native query
    and the flag-ON set was NOT a superset (no CJK query issued)."""
    off_queries = _issue(monkeypatch, subentity_on=False)
    on_queries = _issue(monkeypatch, subentity_on=True)

    off_set, on_set = set(off_queries), set(on_queries)

    # Precondition: the flag-OFF run actually issues native-language (CJK) queries — otherwise
    # the multilingual dimension of this test would be vacuous.
    off_native = [q for q in off_queries if _has_cjk(q)]
    assert off_native, "flag-OFF must issue native-language queries (test precondition)"

    # STRICT SUPERSET (§-1.3 widen-only): every flag-OFF query is still issued flag-ON; more added.
    assert off_set <= on_set, (
        "flag-ON dropped a query the flag-OFF path issued — a swap/drop, not a widen "
        "(the Codex/Fable iter-2 multilingual P1)"
    )
    assert on_set > off_set, "flag-ON must ADD queries on top of the baseline (strict widen)"

    # ZERO native dropped: every native-language query flag-OFF issued is STILL issued flag-ON.
    for q in off_native:
        assert q in on_set, f"native-language query {q!r} was DROPPED with sub-entity ON"

    # The full flag-OFF issued window (English + reserved native) stays at the FRONT, in order —
    # R5 saw the identical pre-R2 baseline, so nothing is reordered or displaced.
    assert on_queries[: len(off_queries)] == off_queries, (
        "the flag-OFF issued window (incl. native queries) must remain unchanged at the front"
    )

    # The ADDED queries are the sub-entity / perspective ones (ASCII, scope-anchored) — NOT native.
    added = [q for q in on_queries if q not in off_set]
    assert added, "expected added sub-entity / perspective queries"
    for niche in _NICHES:
        assert any(q.lower().startswith(niche + " ") for q in added), (
            f"missing sub-entity query for {niche!r} (the canonical-only gap must close)"
        )
    # The sub-entity additions are on-topic (never native, never off-baseline) — they widen, not swap.
    assert not any(_has_cjk(q) for q in added), (
        "sub-entity queries are English scope-anchored (option-b: R5 runs on the pre-R2 base, "
        "so the sub-entity slice is added un-translated and routes through the unchanged fetch)"
    )


def test_multilingual_off_subentity_on_is_iter2_english_path(monkeypatch):
    """Preserve iter-2 behaviour on the English/facet path: with multilingual OFF and sub-entity
    ON, R5 is a no-op and the issued set is the baseline + the sub-entity slice on top (a strict
    superset of the multilingual-OFF baseline). Ordering R5 before R2 must not perturb this."""
    monkeypatch.setenv("PG_MULTILINGUAL_RETRIEVAL", "0")
    monkeypatch.setenv("PG_QGEN_FS_RESEARCHER_MAX_QUERIES", "35")
    monkeypatch.delenv("PG_SUBENTITY_QUERY_RESERVE", raising=False)

    monkeypatch.delenv("PG_SUBENTITY_QUERY_EXPANSION", raising=False)
    off_issued, off_retrieve = _wire_stubs(monkeypatch)
    off_queries, _ = fsr._plan_expert_facet_queries(
        QUESTION, llm=_sub_entity_llm, per_query_retrieve=off_retrieve,
    )
    # Multilingual OFF -> the baseline is the English facet frontier, byte-for-byte (no native).
    assert off_queries == _ENGLISH_FACETS
    assert not any(_has_cjk(q) for q in off_queries)

    monkeypatch.setenv("PG_SUBENTITY_QUERY_EXPANSION", "1")
    on_issued, on_retrieve = _wire_stubs(monkeypatch)
    on_queries, _ = fsr._plan_expert_facet_queries(
        QUESTION, llm=_sub_entity_llm, per_query_retrieve=on_retrieve,
    )
    assert set(off_queries) <= set(on_queries), "English-path baseline must not be dropped"
    assert on_queries[: len(off_queries)] == off_queries, "baseline stays at the front, unchanged"
    added = [q for q in on_queries if q not in set(off_queries)]
    for niche in _NICHES:
        assert any(q.lower().startswith(niche + " ") for q in added), f"missing sub-entity {niche!r}"


if __name__ == "__main__":
    import pytest as _pytest

    raise SystemExit(_pytest.main([__file__, "-q"]))
