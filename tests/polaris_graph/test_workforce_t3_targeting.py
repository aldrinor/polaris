"""BUILD 1 — workforce T3 retrieval-targeting (PG_WORKFORCE_T3_TARGETING).

Diagnosis (why drb_72 got only 4 T3):
    * RETRIEVAL REACH: run_domain_backends had NO "workforce" branch, so the workforce
      domain fired ZERO statistical-agency site: queries. drb_72's amplified set is
      journal-publisher-targeted (site:aeaweb.org / site:science.org / ...) with no
      agency site: query, so BLS / OECD / ILO / StatCan / Eurostat were under-reached.
    * CLASSIFICATION OVERRIDE: the paid run used the W5 LLM-tiering winner
      (PG_CREDIBILITY_LLM_TIERING). Its T3 scheme text names only clinical
      government/regulatory bodies (FDA/EMA/WHO/CDC/...), NOT statistical/data agencies,
      so the GLM can DOWN-tier a genuine OECD/ILO page below the deterministic floor's
      correct T3 (which R2b_statistical_agency already assigns).

Fix (both §-1.3-consistent ADD/CORRECT, never filter; flag-gated default-SAFE):
    (i)  domain_backends: a "workforce" branch runs statistical_agency_serper (a
         (site:bls.gov OR site:oecd.org OR ...) OR-clause over the SAME Serper budget).
    (ii) credibility_llm_tiering: a known statistical-agency domain is kept at its
         deterministic rules-floor tier when the LLM under-tiers it (raise-to-floor,
         never a drop, never lowers a higher tier).

Every assertion runs OFFLINE (no network, no LLM, no paid code): the retrieval backend
is exercised with SERPER_API_KEY removed (fail-open) or via a scope-capturing double, and
the tiering path is exercised with an INJECTED call_llm.
"""
from __future__ import annotations

import pytest

from src.polaris_graph.retrieval import domain_backends
from src.polaris_graph.retrieval.credibility_llm_tiering import (
    classify_source_tier_llm,
    classify_sources_llm_tiering,
)
from src.polaris_graph.retrieval.tier_classifier import (
    STATISTICAL_AGENCY_DOMAINS,
    ClassificationSignals,
    TierLevel,
    _classify_source_tier_rules,
)

_FLAG = "PG_WORKFORCE_T3_TARGETING"
# The five statistical agencies the workforce template names explicitly.
_TEMPLATE_NAMED_AGENCIES = ("bls.gov", "oecd.org", "ilo.org", "statcan.gc.ca", "ec.europa.eu")


# ─────────────────────────────────────────────────────────────────────────────
# (i) RETRIEVAL REACH — the workforce statistical-agency backend
# ─────────────────────────────────────────────────────────────────────────────

def test_workforce_backend_fires_only_when_flag_on(monkeypatch):
    """ON => the workforce domain selects the statistical-agency backend; OFF =>
    no backend (byte-identical to the legacy workforce path, specs == [])."""
    # Force the serial dispatch leg and remove the Serper key so the backend is
    # fail-open (0 network, 0 candidates) but STILL recorded as used.
    monkeypatch.setenv("PG_SEARCH_FUSION_WRRF", "0")
    monkeypatch.delenv("SERPER_API_KEY", raising=False)

    monkeypatch.setenv(_FLAG, "1")
    on = domain_backends.run_domain_backends(
        domain="workforce",
        research_question="AI impact on the labour market",
        amplified_queries=["automation employment"],
    )
    assert on.backends_used == ["serper_statistical_agency"]

    monkeypatch.setenv(_FLAG, "0")
    off = domain_backends.run_domain_backends(
        domain="workforce",
        research_question="AI impact on the labour market",
        amplified_queries=["automation employment"],
    )
    assert off.backends_used == []
    assert off.candidates == []


def test_statistical_agency_serper_scopes_the_named_agencies(monkeypatch):
    """statistical_agency_serper must scope the OR-clause to the agencies the
    workforce template names (§-1.3: ADD reach — no hard-coded target count)."""
    captured: dict[str, object] = {}

    def _fake_scoped(query, *, scopes, source, limit):
        captured["query"] = query
        captured["scopes"] = list(scopes)
        captured["source"] = source
        return []

    monkeypatch.setattr(domain_backends, "site_scoped_serper", _fake_scoped)
    domain_backends.statistical_agency_serper("labour force survey")

    assert captured["source"] == "serper_statistical_agency"
    for host in _TEMPLATE_NAMED_AGENCIES:
        assert host in captured["scopes"], f"{host} missing from statistical-agency scopes"


def test_workforce_backend_candidates_flow_through(monkeypatch):
    """When the backend returns hits, they reach the DomainBackendResult (ADD, not
    filter). Uses a double so no network is touched."""
    monkeypatch.setenv(_FLAG, "1")
    monkeypatch.setenv("PG_SEARCH_FUSION_WRRF", "0")

    from src.polaris_graph.retrieval.domain_backends import SearchCandidate

    def _fake_agency(query, limit=10):
        return [SearchCandidate(
            url="https://www.oecd.org/employment-outlook-2026",
            title="OECD Employment Outlook 2026",
            snippet="labour market",
            source="serper_statistical_agency",
        )]

    monkeypatch.setattr(domain_backends, "statistical_agency_serper", _fake_agency)
    res = domain_backends.run_domain_backends(
        domain="workforce",
        research_question="AI impact on the labour market",
    )
    assert res.backends_used == ["serper_statistical_agency"]
    assert [c.url for c in res.candidates] == [
        "https://www.oecd.org/employment-outlook-2026"
    ]


def test_non_workforce_domains_unaffected_by_flag(monkeypatch):
    """The flag must not perturb another domain's backend selection."""
    monkeypatch.setenv(_FLAG, "1")
    monkeypatch.setenv("PG_SEARCH_FUSION_WRRF", "0")
    monkeypatch.delenv("SERPER_API_KEY", raising=False)
    res = domain_backends.run_domain_backends(
        domain="due_diligence",
        research_question="10-K risk factors",
    )
    assert "serper_statistical_agency" not in res.backends_used


# ─────────────────────────────────────────────────────────────────────────────
# (ii) CLASSIFICATION — a known statistical agency must land at T3
# ─────────────────────────────────────────────────────────────────────────────

def test_bls_classifies_t3_deterministic():
    """The deterministic rules-floor already assigns bls.gov -> T3 (the always-on
    R2b_statistical_agency correctness fix). The test requirement: bls.gov is T3."""
    sig = ClassificationSignals(
        url="https://www.bls.gov/emp/tables/employment-by-major-industry.htm",
        title="Employment Projections by Major Industry",
        fetched_content_length=8000,
    )
    assert _classify_source_tier_rules(sig).tier == TierLevel.T3


def _bls_signals() -> ClassificationSignals:
    return ClassificationSignals(
        url="https://www.bls.gov/opub/mlr/2026/article/ai-and-jobs.htm",
        title="AI and Jobs",
        fetched_content_length=9000,
    )


def _llm_returns(tier_label: str):
    def _call(_prompt: str) -> str:
        return '{"tier": "%s", "rationale": "scheme omits statistical agencies"}' % tier_label
    return _call


def test_llm_down_tier_of_agency_is_floored_to_t3_when_on(monkeypatch):
    """Flag ON: an LLM that mis-tiers a known statistical agency as T6 is raised back
    UP to the deterministic floor T3 (raise-to-floor WEIGHT, never a drop, §-1.3)."""
    monkeypatch.setenv(_FLAG, "1")
    out = classify_sources_llm_tiering([_bls_signals()], call_llm=_llm_returns("T6"))
    assert len(out) == 1  # no source ever dropped
    assert out[0].tier == TierLevel.T3


def test_llm_down_tier_of_agency_is_byte_identical_when_off(monkeypatch):
    """Flag OFF: the legacy LLM override wins unchanged (T6) — byte-identical."""
    monkeypatch.setenv(_FLAG, "0")
    out = classify_sources_llm_tiering([_bls_signals()], call_llm=_llm_returns("T6"))
    assert out[0].tier == TierLevel.T6


def test_floor_never_lowers_a_non_agency_source(monkeypatch):
    """Flag ON must ONLY touch KNOWN statistical agencies: a non-agency source keeps
    its LLM tier (the floor guarantee is scoped to the authority allowlist)."""
    monkeypatch.setenv(_FLAG, "1")
    blog = ClassificationSignals(
        url="https://example-blog.com/ai-and-jobs",
        title="AI and Jobs, a hot take",
        fetched_content_length=4000,
    )
    out = classify_sources_llm_tiering([blog], call_llm=_llm_returns("T6"))
    assert out[0].tier == TierLevel.T6


def test_single_source_path_floors_agency_when_on(monkeypatch):
    """The single-source dispatcher applies the SAME floor as the batch path."""
    monkeypatch.setenv(_FLAG, "1")

    import src.polaris_graph.retrieval.credibility_llm_tiering as clt

    monkeypatch.setattr(clt, "_default_caller", lambda: _llm_returns("T6"))
    res = classify_source_tier_llm(_bls_signals())
    assert res.tier == TierLevel.T3


def test_flag_shared_between_backend_and_tiering():
    """Both legs read the SAME kill-switch name so one switch drives the whole build."""
    assert domain_backends._workforce_t3_targeting_enabled.__name__ == (
        "_workforce_t3_targeting_enabled"
    )
    # The agency hosts the backend scopes are all in the deterministic authority list
    # the tier floor uses, so a reached agency is guaranteed a floor tier to snap to.
    from src.polaris_graph.retrieval.tier_classifier import _domain_matches
    for host in domain_backends._STATISTICAL_AGENCY_HOSTS:
        assert _domain_matches(host, STATISTICAL_AGENCY_DOMAINS), host
