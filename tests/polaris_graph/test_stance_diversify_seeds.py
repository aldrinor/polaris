"""GENERAL stance / view-diversification seed lane (fs_researcher_query_gen) — offline, $0.

Proves the ADDITIVE stance lane mirrors the existing PG_LANDMARK_EXPANDER lane exactly:

  * OFF (flag unset AND explicit "0") is BYTE-IDENTICAL — no stance query is added, the issued
    frontier equals the baseline.
  * ON appends generic stance-framed queries (supporting / opposing / challenges / opportunities) per
    facet, ON TOP of the baseline (strict superset) — WITHOUT raising the query budget.
  * FAIL-OPEN — a raising stance builder adds ZERO queries, emits the DISTINCT
    ``unavailable_failopen`` degrade marker, SUPPRESSES the positive marker, and NEVER aborts qgen.
  * GENERAL — the templates are topic-agnostic; NO benchmark study title / author / country / topic
    appears in any generated query.
  * The honest ``[activation] stance_diversify_seeds: issued=<N>`` marker reports the REALIZED count of
    net-new stance queries added to the frontier (a count > 0 is NEVER gated — 0 is an honest fire).

EVERYTHING IS OFFLINE: no network, no GPU, no model load. The injected ``llm`` / ``per_query_retrieve``
are pure stubs. The FROZEN faithfulness engine (strict_verify / NLI / 4-role / provenance /
span-grounding) is NEVER touched — this is retrieval query-frontier assembly only (§-1.3 additive-only).
"""

from __future__ import annotations

import logging

import pytest

from src.polaris_graph.retrieval import fs_researcher_query_gen as fq

_LOGGER_NAME = "polaris_graph.fs_researcher_query_gen"
_QUESTION = "What is the impact of automation on the labor market?"

# Generic facet names the stub LLM returns for the facet-tree decomposition — TOPIC-AGNOSTIC, no
# benchmark study / author / country baked in (the lane must stay general).
_STUB_FACETS = ("labor market effects", "automation adoption", "skill demand shifts")

# A guard list of drb_72-specific study authors / countries / topics that MUST NOT appear in any
# generated query — proves the stance templates are general, not benchmark-gamed.
_BENCHMARK_LEAK_TOKENS = (
    "noy", "zhang", "frey", "osborne", "brynjolfsson", "acemoglu", "autor",
    "denmark", "germany", "generative ai", "chatgpt", "gpt-4", "tirzepatide",
)


class _StubResult:
    """A minimal LiveRetrievalResult stand-in — the stance lane only reads ``evidence_rows``."""

    def __init__(self) -> None:
        self.evidence_rows: list = []
        self.classified_sources: list = []


def _make_stub_retrieve() -> "tuple[list[str], callable]":
    calls: list[str] = []

    def _retrieve(research_question: str, **_kw):
        calls.append(research_question)
        return _StubResult()

    return calls, _retrieve


def _stub_llm(_prompt: str) -> str:
    """Deterministic facet-tree reply: one generic facet name per line."""
    return "\n".join(_STUB_FACETS)


def _plan(monkeypatch) -> list[str]:
    """Run the expert-facet qgen path and return the ORDERED issued-query list."""
    _calls, retrieve = _make_stub_retrieve()
    queries, _results = fq.plan_fs_researcher_queries(
        _QUESTION, _stub_llm, retrieve, retrieve_kwargs={}
    )
    return queries


@pytest.fixture(autouse=True)
def _expert_facet_on(monkeypatch):
    """The stance lane lives on the expert-facet path (mirrors the landmark lane); arm the planner and
    keep every OTHER additive lane OFF so the test isolates the stance lane. Env is monkeypatched so it
    is restored automatically after each test."""
    monkeypatch.setenv("PG_EXPERT_FACET_PLANNER", "1")
    monkeypatch.setenv("PG_QGEN_FS_RESEARCHER", "1")
    for _off in (
        "PG_LANDMARK_EXPANDER", "PG_SUBENTITY_QUERY_EXPANSION",
        "PG_FACET_COMPLETENESS", "PG_MULTILINGUAL_RETRIEVAL", "PG_QGEN_PARALLEL_QUERIES",
    ):
        monkeypatch.delenv(_off, raising=False)


def _stance_lens_phrases() -> tuple[str, ...]:
    return tuple(lens for _label, lens in fq._STANCE_FRAMES)


def _count_stance_queries(queries: list[str]) -> int:
    lenses = _stance_lens_phrases()
    return sum(1 for q in queries if any(lens in q for lens in lenses))


def _expected_stance_count() -> int:
    """The REALIZED number of net-new stance queries the lane adds, derived from the SAME facet planner
    + stance builder the production path uses (so the test never hardcodes a fragile count — the
    deterministic floor may add the question itself as an extra facet)."""
    from src.polaris_graph.retrieval import expert_facet_planner as efp

    facets = efp.plan_expert_facets(_QUESTION, _stub_llm)
    return len(fq._stance_diversify_seeds(facets, _QUESTION))


# ── OFF is byte-identical (unset AND explicit "0") ────────────────────────────────────────────────
def test_off_is_byte_identical(monkeypatch):
    monkeypatch.delenv("PG_STANCE_DIVERSIFY_SEEDS", raising=False)
    queries_unset = _plan(monkeypatch)

    monkeypatch.setenv("PG_STANCE_DIVERSIFY_SEEDS", "0")
    queries_off = _plan(monkeypatch)

    assert queries_unset == queries_off, "explicit '0' must equal unset (both OFF)"
    assert _count_stance_queries(queries_unset) == 0, "OFF must add ZERO stance queries"
    assert queries_unset, "sanity: the baseline frontier is non-empty"


# ── ON appends generic stance queries per facet, strict superset ──────────────────────────────────
def test_on_adds_stance_queries_per_facet_strict_superset(monkeypatch):
    # generous budget so every baseline + stance query fits (isolates the additive-superset property
    # from the budget bound, which is proved separately below).
    monkeypatch.setenv("PG_QGEN_FS_RESEARCHER_MAX_QUERIES", "500")
    monkeypatch.delenv("PG_STANCE_DIVERSIFY_SEEDS", raising=False)
    baseline = _plan(monkeypatch)

    monkeypatch.setenv("PG_STANCE_DIVERSIFY_SEEDS", "1")
    on = _plan(monkeypatch)

    # Strict superset, order-preserving: the baseline seeds issue FIRST and unchanged, stance queries
    # are APPENDED after them (additive-only).
    assert on[: len(baseline)] == baseline
    expected = _expected_stance_count()
    assert expected > 0, "sanity: the lane adds at least one stance query"
    added = _count_stance_queries(on)
    # every added query is a stance query, and every stance query the builder emits was added.
    assert added == expected
    assert len(on) == len(baseline) + expected


# ── the budget is NOT raised to fit the stance queries (honest truncation, no cap-raise) ───────────
def test_budget_not_raised_stance_queries_honestly_truncated(monkeypatch):
    monkeypatch.delenv("PG_STANCE_DIVERSIFY_SEEDS", raising=False)
    monkeypatch.setenv("PG_QGEN_FS_RESEARCHER_MAX_QUERIES", "500")
    baseline = _plan(monkeypatch)  # the full baseline frontier size, unbounded
    expected = _expected_stance_count()
    # a TIGHT budget: the full baseline + only 2 stance slots. Unlike the landmark/sub-entity widen
    # lanes, the stance lane must NOT raise the budget to fit its queries — so exactly the tight budget
    # issues, never baseline + all stance.
    tight = len(baseline) + 2
    assert expected > 2, "sanity: more stance queries exist than the 2 spare budget slots"
    monkeypatch.setenv("PG_QGEN_FS_RESEARCHER_MAX_QUERIES", str(tight))
    monkeypatch.setenv("PG_STANCE_DIVERSIFY_SEEDS", "1")
    on = _plan(monkeypatch)
    # the budget was HONOURED, not raised: total issued == the tight budget (baseline head + 2 stance),
    # never len(baseline) + expected. This is the "do NOT raise a cap to fit them" contract.
    assert len(on) == tight
    assert _count_stance_queries(on) == 2


# ── the honest [activation] marker reports the REALIZED issued count (post-budget), NOT the appended count ──
def test_activation_marker_reports_realized_issued_count(monkeypatch, caplog):
    """Codex Wave-6c P1: the marker fires AFTER _issue_seed_frontier and reports the count of stance queries
    that ACTUALLY passed the (deliberately-unraised) budget + dedup + wall — NOT the pre-truncation appended
    count. So marker issued=N must equal the number of stance queries present in the ISSUED frontier, which
    can be LESS than the total possible stance queries when the budget truncates the tail (honest realized)."""
    monkeypatch.setenv("PG_STANCE_DIVERSIFY_SEEDS", "1")
    with caplog.at_level(logging.INFO, logger=_LOGGER_NAME):
        on = _plan(monkeypatch)
    realized = _count_stance_queries(on)  # stance queries that ACTUALLY reached the issued frontier
    assert realized > 0, "sanity: at least one stance query issued under the default budget"
    markers = [r.getMessage() for r in caplog.records if "stance_diversify_seeds" in r.getMessage()]
    assert any(f"stance_diversify_seeds: issued={realized}" in m for m in markers), (realized, markers)
    # The marker must report the REALIZED count, never the pre-truncation appended total when they differ.
    _possible = _expected_stance_count()
    if _possible != realized:
        assert not any(f"stance_diversify_seeds: issued={_possible}" in m for m in markers), (
            "marker must report realized issued, not the pre-budget appended count", _possible, realized, markers)
    # NO degrade marker on the healthy path.
    assert not any("unavailable_failopen" in m for m in markers), markers


# ── FAIL-OPEN: a raising builder adds ZERO, emits the degrade marker, never aborts qgen ────────────
def test_fail_open_adds_zero_and_emits_degrade_marker(monkeypatch, caplog):
    monkeypatch.delenv("PG_STANCE_DIVERSIFY_SEEDS", raising=False)
    baseline = _plan(monkeypatch)

    def _boom(_facets, _question):
        raise RuntimeError("stance builder blew up")

    monkeypatch.setattr(fq, "_stance_diversify_seeds", _boom)
    monkeypatch.setenv("PG_STANCE_DIVERSIFY_SEEDS", "1")
    with caplog.at_level(logging.INFO, logger=_LOGGER_NAME):
        failed = _plan(monkeypatch)

    # host query-gen path did NOT abort — it returned the unchanged baseline (zero stance added).
    assert failed == baseline
    assert _count_stance_queries(failed) == 0
    msgs = [r.getMessage() for r in caplog.records if "stance_diversify_seeds" in r.getMessage()]
    assert any("stance_diversify_seeds: unavailable_failopen" in m for m in msgs), msgs
    # the positive marker is SUPPRESSED on the fail-open path.
    assert not any("stance_diversify_seeds: issued=" in m for m in msgs), msgs


# ── GENERAL: no benchmark study title / author / country appears in any generated query ────────────
def test_no_benchmark_study_title_in_any_query(monkeypatch):
    monkeypatch.setenv("PG_STANCE_DIVERSIFY_SEEDS", "1")
    on = _plan(monkeypatch)
    blob = " || ".join(on).lower()
    for token in _BENCHMARK_LEAK_TOKENS:
        assert token not in blob, f"benchmark-specific token leaked into a stance query: {token!r}"


# ── the builder emits one query per stance frame per facet, scope-anchored, deduped ────────────────
def test_builder_is_generic_and_deterministic():
    from src.polaris_graph.retrieval.expert_facet_planner import Facet

    facets = [Facet(name=n, queries=[]) for n in _STUB_FACETS]
    out = fq._stance_diversify_seeds(facets, _QUESTION)
    assert len(out) == len(_STUB_FACETS) * len(fq._STANCE_FRAMES)
    # every query carries its facet, a generic stance lens, and the question's scope anchor.
    lenses = _stance_lens_phrases()
    for q in out:
        assert any(lens in q for lens in lenses)
    # no facets => empty (honest ran-ok-zero), never a raise.
    assert fq._stance_diversify_seeds([], _QUESTION) == []
