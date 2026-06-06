"""FX-15a (I-ready-017 #1118): agentic seed source-label correctness.

Agentic-discovered seed URLs were injected as `source='primary_trial_doi'`,
`query_origin='primary_trial_doi_seed'` — mislabeling ordinary web discoveries as primary-trial
DOI seeds. The fix threads caller-supplied `seed_source` / `seed_query_origin` through
`run_live_retrieval`, splits the reserved seed lane on the SET {primary_trial_doi, agentic_seed}
(so the relabel changes NO selection — both classes stay reserved/undroppable), and adds
`agentic_seed` to `plan_sufficiency_gate.SENTINEL_ORIGINS` (so fallback-eligibility is preserved).

Telemetry-correctness ONLY — no retrieval-selection, grounding, strict_verify or 4-role change.
Offline, no network (seed_only + stubbed `_fetch_content`).
"""
from __future__ import annotations

import src.polaris_graph.retrieval.live_retriever as lr
from src.polaris_graph.adequacy.plan_sufficiency_gate import SENTINEL_ORIGINS
from src.polaris_graph.retrieval.live_retriever import (
    SearchCandidate,
    _rerank_and_reserve,
    _SEED_SOURCE_LABELS,
)


def test_seed_split_reserves_both_seed_classes_unranked():
    """The relabel must NOT change selection: BOTH primary_trial_doi AND agentic_seed candidates
    stay in the reserved lane (prepended, never ranked, never dropped) — only the label differs."""
    doi_seed = SearchCandidate(
        url="https://doi.org/10.1056/x", title="", snippet="", source="primary_trial_doi",
        query_origin="primary_trial_doi_seed",
    )
    agentic_seed = SearchCandidate(
        url="https://aeaweb.org/articles?id=10.1257/y", title="", snippet="",
        source="agentic_seed", query_origin="agentic_seed",
    )
    web = SearchCandidate(
        url="https://example.org/web", title="W", snippet="w", source="serper",
        query_origin="sub query text",
    )
    out = _rerank_and_reserve(
        [web, doi_seed, agentic_seed],
        research_question="anticoagulation in atrial fibrillation",
        fetch_cap=1,
        n_seed_injected=2,
    )
    out_sources = [c.source for c in out]
    # both seed classes survive (reserved); none dropped despite fetch_cap=1
    assert "primary_trial_doi" in out_sources
    assert "agentic_seed" in out_sources
    # seeds are PREPENDED before the (single) reserved web candidate
    assert out_sources[:2] == ["primary_trial_doi", "agentic_seed"]
    assert "serper" in out_sources  # the one non-seed slot


def test_seed_source_labels_constant():
    assert _SEED_SOURCE_LABELS == frozenset({"primary_trial_doi", "agentic_seed"})


def test_agentic_seed_is_a_sentinel_origin():
    """Preserves fallback-eligibility the old mislabel `primary_trial_doi_seed` (a sentinel) had."""
    assert "agentic_seed" in SENTINEL_ORIGINS
    assert "primary_trial_doi_seed" in SENTINEL_ORIGINS  # unchanged


def _stub_fetch(url, max_chars, **kwargs):
    # (content, ok, title, body_type, jsonld) — non-starved content so the row is kept.
    return (
        "Apixaban reduced stroke versus warfarin in atrial fibrillation patients. " * 8,
        True, "Stub Title", "html", "",
    )


def test_injection_uses_caller_label_agentic(monkeypatch):
    monkeypatch.setattr(lr, "_fetch_content", _stub_fetch)
    res = lr.run_live_retrieval(
        research_question="anticoagulation in atrial fibrillation",
        seed_urls=["https://aeaweb.org/articles?id=10.1257/y"],
        seed_only=True,
        seed_source="agentic_seed",
        seed_query_origin="agentic_seed",
        enable_openalex_enrich=False,
        fetch_cap=5,
    )
    rows = [r for r in res.evidence_rows if r["source_url"] == "https://aeaweb.org/articles?id=10.1257/y"]
    assert rows, "the stubbed agentic seed should produce one kept evidence row"
    assert rows[0]["source"] == "agentic_seed"
    assert rows[0]["query_origin"] == "agentic_seed"


def test_injection_default_label_is_doi_seed(monkeypatch):
    """DOI-lane caller (defaults) is unchanged — no regression from the new params."""
    monkeypatch.setattr(lr, "_fetch_content", _stub_fetch)
    res = lr.run_live_retrieval(
        research_question="anticoagulation in atrial fibrillation",
        seed_urls=["https://doi.org/10.1056/NEJMoa1107039"],
        seed_only=True,
        enable_openalex_enrich=False,
        fetch_cap=5,
    )
    rows = [r for r in res.evidence_rows if r["source_url"] == "https://doi.org/10.1056/NEJMoa1107039"]
    assert rows, "the stubbed DOI seed should produce one kept evidence row"
    assert rows[0]["source"] == "primary_trial_doi"
    assert rows[0]["query_origin"] == "primary_trial_doi_seed"
