"""U11 (I-deepfix-001) offline tests: clinical evidence-type query expansion
(a WEIGHT/recall fix) + WRRF per-engine weights are read from env (not all-1.0).

No GPU / network / paid-LLM: both units are pure, deterministic string/rank
transforms. RED before the U11 module + wiring exist; GREEN after.
"""
from __future__ import annotations

from dataclasses import dataclass

import pytest

from src.polaris_graph.retrieval.evidence_type_query_expansion import (
    _DEFAULT_CLINICAL_EVIDENCE_TYPE_TERMS,
    evidence_type_query_expansion_enabled,
    expand_evidence_type_queries,
)
from src.polaris_graph.retrieval.search_fusion_wrrf import (
    _engine_weights,
    wrrf_fuse,
)


# ── evidence-type query expansion (fix 1: recall WEIGHT) ────────────────────


def test_expansion_emits_rct_and_guideline_subquery_for_clinical_question():
    """Acceptance: for a clinical question, expansion emits an RCT-targeted AND a
    guideline-targeted sub-query, keeping the original queries first and intact."""
    base = ["metformin cardiovascular outcomes in type 2 diabetes"]
    out = expand_evidence_type_queries(base, clinical=True, enabled=True)

    # Originals preserved, in order, at the front (WEIGHT-not-filter: never drop).
    assert out[: len(base)] == base
    assert len(out) > len(base)

    joined = " || ".join(out).lower()
    # An RCT-targeted sub-query must be emitted.
    assert "randomized controlled trial" in joined
    # A guideline-targeted sub-query must be emitted.
    assert "clinical practice guideline" in joined
    # A systematic-review / meta-analysis sub-query too (T1 high-tier).
    assert "systematic review meta-analysis" in joined

    # Every added variant is anchored on the original clinical question (on-topic
    # by construction — not an off-drift generic query).
    added = out[len(base):]
    assert added, "expansion must add at least one evidence-type sub-query"
    for variant in added:
        assert variant.lower().startswith(base[0].lower())
    # One variant per default evidence-type term.
    assert len(added) == len(_DEFAULT_CLINICAL_EVIDENCE_TYPE_TERMS)


def test_expansion_noop_for_non_clinical_run():
    """Non-clinical runs are returned unchanged even when the flag is ON."""
    base = ["quarterly revenue guidance for the semiconductor sector"]
    out = expand_evidence_type_queries(base, clinical=False, enabled=True)
    assert out == base


def test_expansion_noop_when_disabled_byte_identical():
    """Kill switch OFF => byte-identical passthrough (the safe default)."""
    base = ["stroke thrombolysis outcomes", "tPA time window"]
    out = expand_evidence_type_queries(base, clinical=True, enabled=False)
    assert out == base


def test_expansion_default_flag_is_off(monkeypatch):
    """Unset env flag => disabled => passthrough (default OFF invariant)."""
    monkeypatch.delenv("PG_EVIDENCE_TYPE_QUERY_EXPANSION", raising=False)
    assert evidence_type_query_expansion_enabled() is False
    base = ["sepsis fluid resuscitation"]
    # enabled defaults to the (unset) env knob -> no expansion.
    assert expand_evidence_type_queries(base, clinical=True) == base


def test_expansion_reads_env_flag(monkeypatch):
    """Flag ON via env => clinical expansion fires without an explicit enabled."""
    monkeypatch.setenv("PG_EVIDENCE_TYPE_QUERY_EXPANSION", "1")
    assert evidence_type_query_expansion_enabled() is True
    base = ["heart failure SGLT2 inhibitors"]
    out = expand_evidence_type_queries(base, clinical=True)
    assert len(out) == len(base) + len(_DEFAULT_CLINICAL_EVIDENCE_TYPE_TERMS)


def test_expansion_dedups_and_handles_empty_anchor():
    """Case-insensitive dedup; an empty/blank query list yields no variants."""
    # A variant that already exists must not be duplicated.
    base = [
        "asthma biologics",
        "asthma biologics randomized controlled trial",  # collides with a variant
    ]
    out = expand_evidence_type_queries(base, clinical=True, enabled=True)
    lowered = [q.lower() for q in out]
    assert lowered.count("asthma biologics randomized controlled trial") == 1
    # Empty anchor -> nothing added.
    assert expand_evidence_type_queries(["", "   "], clinical=True, enabled=True) == ["", "   "]


def test_expansion_custom_terms_override():
    """Explicit terms override the clinical defaults."""
    base = ["copd exacerbation"]
    out = expand_evidence_type_queries(
        base, clinical=True, enabled=True, terms=["cochrane review"]
    )
    assert out == ["copd exacerbation", "copd exacerbation cochrane review"]


# ── WRRF per-engine weights are read from env, not all-1.0 (fix 3) ──────────


@dataclass
class _Cand:
    url: str


def test_wrrf_weights_read_from_env(monkeypatch):
    """PG_SEARCH_FUSION_WRRF_WEIGHTS is parsed into a per-engine weight map."""
    monkeypatch.setenv(
        "PG_SEARCH_FUSION_WRRF_WEIGHTS",
        "europe_pmc:1.5,openalex:1.3,serper:0.5",
    )
    weights = _engine_weights()
    assert weights == {"europe_pmc": 1.5, "openalex": 1.3, "serper": 0.5}
    # Not the degenerate all-1.0 map that an unset env would imply.
    assert not all(w == 1.0 for w in weights.values())


def test_wrrf_weights_lift_academic_engine_over_web(monkeypatch):
    """A high-tier academic hit that Europe PMC ranks #1 outranks a generic-web
    hit that Serper ranks #1 ONCE the env weights are applied — proving the
    weights are ACTIVE in fusion, not flattened to 1.0."""
    monkeypatch.setenv("PG_SEARCH_FUSION_WRRF_WEIGHTS", "europe_pmc:3.0,serper:0.5")
    per_engine = {
        "serper": [_Cand("https://blog.example.com/marketing")],
        "europe_pmc": [_Cand("https://www.ncbi.nlm.nih.gov/pmc/articles/PMC1/")],
    }
    res = wrrf_fuse(per_engine)
    # weights_used reflects the env knob (not the default 1.0).
    assert res.weights_used["europe_pmc"] == 3.0
    assert res.weights_used["serper"] == 0.5
    # The Europe PMC primary-literature URL fuses ABOVE the generic-web URL.
    assert res.fused[0].url == "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC1/"


def test_wrrf_weights_unset_is_empty_map(monkeypatch):
    """Unset env => empty map (fusion then applies the default engine weight)."""
    monkeypatch.delenv("PG_SEARCH_FUSION_WRRF_WEIGHTS", raising=False)
    assert _engine_weights() == {}


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
