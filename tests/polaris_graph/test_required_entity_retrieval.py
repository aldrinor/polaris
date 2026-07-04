"""I-complete-004 (#1190): offline tests for the targeted required-entity lane.

ALL deterministic, NO network — ``search_fn`` / ``retrieval_fn`` are stubs
injected into ``run_required_entity_lane``. Covers the faithfulness-critical
cases:

(a) targeted query built with authoritative-domain bias (default set UNION the
    entity's own url_pattern host) for a missing entity;
(b) lane finds NO candidate URLs -> NO evidence rows injected (no fabrication,
    no forced coverage); the frame rows are NEVER mutated;
(c) PG_REQUIRED_ENTITY_RETRIEVAL OFF -> ``lane_enabled()`` False (caller gate);
    already-satisfied frame rows are never searched/fetched;
(d) §-1.1 provenance honesty: the FETCHED corpus rows carry their REAL fetched
    URLs and are NOT keyed to any entity_id and NOT relabeled with the entity's
    canonical url_pattern -> the operator-locked exact-equality coverage gate
    cannot be tricked by an alternate-URL source.
"""
from __future__ import annotations

import pytest

from src.polaris_graph.retrieval.frame_fetcher import FrameRow, ProvenanceClass
from src.polaris_graph.retrieval.required_entity_retrieval import (
    _DEFAULT_REQUIRED_ENTITY_DOMAINS,
    COVERAGE_L5_SEED_QUERY_ORIGIN,
    COVERAGE_L5_SEED_SOURCE_LABEL,
    CoverageL5Result,
    SEED_QUERY_ORIGIN,
    SEED_SOURCE_LABEL,
    build_targeted_queries,
    coverage_l5_enabled,
    entity_url_host,
    extract_required_entities,
    frame_row_is_unsatisfied,
    lane_enabled,
    required_entity_domains,
    run_l5_required_entity_coverage,
    run_required_entity_lane,
)
from src.polaris_graph.roles.native_gate_b_inputs import _entity_canonical_match


# ─────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────
_ENTITY_URL = "https://ods.od.nih.gov/factsheets/Iron-HealthProfessional/"
_ENTITY_ID = "fda_iron_supplement_contraindication"
# The URL the targeted search actually surfaced (a DIFFERENT authoritative page).
_FOUND_URL = "https://ods.od.nih.gov/factsheets/Iron-Consumer/"


def _entity_cfg() -> dict:
    return {
        "id": _ENTITY_ID,
        "type": "regulatory",
        "severity": "S0",
        "s0_category": "contraindications",
        "url_pattern": _ENTITY_URL,
        "label_name": "NIH ODS Iron fact sheet",
        "coverage_content_requirements": ["contraindicated", "iron overload"],
    }


def _gap_row() -> FrameRow:
    return FrameRow(
        entity_id=_ENTITY_ID,
        entity_type="regulatory",
        rendering_slot="regulatory_supplement_safety",
        provenance_class=ProvenanceClass.FRAME_GAP_UNRECOVERABLE,
        direct_quote="",
        quote_source="none",
        doi=None,
        pmid=None,
        oa_pdf_url=None,
        url=_ENTITY_URL,
        title=None,
        authors=(),
        journal=None,
        year=None,
        failure_reason="all sources failed",
    )


def _open_row(quote: str, url: str = _ENTITY_URL) -> FrameRow:
    return FrameRow(
        entity_id=_ENTITY_ID,
        entity_type="regulatory",
        rendering_slot="regulatory_supplement_safety",
        provenance_class=ProvenanceClass.OPEN_ACCESS,
        direct_quote=quote,
        quote_source="url_pattern_fetch",
        doi=None,
        pmid=None,
        oa_pdf_url=None,
        url=url,
        title=None,
        authors=(),
        journal=None,
        year=None,
        failure_reason=None,
    )


class _SearchRecorder:
    """Records every search_fn(query, domains=, max_results=) call.

    ``return_urls`` is the candidate URL list each call yields (as Serper-shaped
    result dicts).
    """

    def __init__(self, return_urls=None):
        self.calls: list[dict] = []
        self._return_urls = return_urls or []

    def __call__(self, query, *, domains, max_results):
        self.calls.append(
            {"query": query, "domains": list(domains), "max_results": max_results}
        )
        return [{"url": u, "title": "", "snippet": ""} for u in self._return_urls]


class _RetrievalRecorder:
    """Records retrieval_fn(...) kwargs and returns a stub with evidence_rows."""

    def __init__(self, evidence_rows=None):
        self.calls: list[dict] = []
        self._rows = evidence_rows or []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)

        class _Result:
            evidence_rows = list(self._rows)

        return _Result()


def _lane(*, frame_rows, search_fn, retrieval_fn, scope_overrides=None):
    return run_required_entity_lane(
        frame_rows=frame_rows,
        entity_meta_by_id={},
        entity_cfg_by_id={_ENTITY_ID: _entity_cfg()},
        research_question="iron supplementation cardiovascular safety",
        scope_overrides=scope_overrides
        if scope_overrides is not None
        else {"intervention": "iron supplementation"},
        search_fn=search_fn,
        retrieval_fn=retrieval_fn,
    )


# ─────────────────────────────────────────────────────────────────────
# (a) targeted query built with authoritative-domain bias
# ─────────────────────────────────────────────────────────────────────
def test_a_targeted_query_authoritative_domain_bias(monkeypatch):
    monkeypatch.delenv("PG_REQUIRED_ENTITY_DOMAINS", raising=False)
    search = _SearchRecorder(return_urls=[_FOUND_URL])
    retr = _RetrievalRecorder(evidence_rows=[])

    _lane(frame_rows=[_gap_row()], search_fn=search, retrieval_fn=retr)

    assert search.calls, "lane must fire at least one targeted query for a gap entity"
    queries = [c["query"] for c in search.calls]
    # anchored to the intervention anchor + a contraindications safety term
    assert any("contraindications" in q.lower() for q in queries)
    assert all("iron supplementation" in q for q in queries)
    # Domain bias = default set UNION the entity's OWN host (ods.od.nih.gov is
    # NOT in the default set, so the union is what makes it reachable).
    domains = search.calls[0]["domains"]
    for default_domain in _DEFAULT_REQUIRED_ENTITY_DOMAINS:
        assert default_domain in domains
    assert "ods.od.nih.gov" in domains


def test_a_label_name_anchor_wins_over_scope_override():
    class _Meta:
        label_name = "Mounjaro"

    search = _SearchRecorder(return_urls=[])
    run_required_entity_lane(
        frame_rows=[_gap_row()],
        entity_meta_by_id={_ENTITY_ID: _Meta()},
        entity_cfg_by_id={_ENTITY_ID: _entity_cfg()},
        research_question="q",
        scope_overrides={"intervention": "iron supplementation"},
        search_fn=search,
        retrieval_fn=_RetrievalRecorder(),
    )
    queries = [c["query"] for c in search.calls]
    assert queries and all(q.startswith("Mounjaro ") for q in queries)


def test_build_targeted_queries_capped_and_category_aware():
    queries = build_targeted_queries(
        entity=_entity_cfg(), intervention_anchor="iron supplementation"
    )
    assert queries
    assert len(queries) <= 3  # default per-entity cap
    assert any("contraindications" in q.lower() for q in queries)


def test_entity_url_host_extracts_bare_host():
    assert entity_url_host(_ENTITY_URL) == "ods.od.nih.gov"
    assert entity_url_host("https://www.accessdata.fda.gov/x/y.pdf") == "www.accessdata.fda.gov"
    assert entity_url_host("") is None
    assert entity_url_host(None) is None


def test_required_entity_domains_default_and_override(monkeypatch):
    monkeypatch.delenv("PG_REQUIRED_ENTITY_DOMAINS", raising=False)
    assert required_entity_domains() == _DEFAULT_REQUIRED_ENTITY_DOMAINS
    monkeypatch.setenv("PG_REQUIRED_ENTITY_DOMAINS", "a.gov, b.org ,")
    assert required_entity_domains() == ("a.gov", "b.org")


# ─────────────────────────────────────────────────────────────────────
# (b) no candidate URLs -> no injection, frame rows never mutated
# ─────────────────────────────────────────────────────────────────────
def test_b_no_candidates_no_injection_no_mutation():
    search = _SearchRecorder(return_urls=[])  # search finds nothing
    retr = _RetrievalRecorder(evidence_rows=[{"source_url": "x"}])
    gap = _gap_row()
    result = _lane(frame_rows=[gap], search_fn=search, retrieval_fn=retr)

    assert result.attempted_entity_ids == (_ENTITY_ID,)
    assert result.seed_urls == ()
    assert result.evidence_rows == []  # nothing injected
    # retrieval is NEVER called when there are no seed urls (no wasted fetch)
    assert retr.calls == []
    # the frame row is untouched (the lane never mutates frame rows)
    assert gap.provenance_class == ProvenanceClass.FRAME_GAP_UNRECOVERABLE
    assert gap.direct_quote == ""


def test_b_candidates_found_rows_fetched_and_returned():
    search = _SearchRecorder(return_urls=[_FOUND_URL])
    fetched = {
        "source_url": _FOUND_URL,
        "direct_quote": (
            "Iron supplements are contraindicated in iron overload disorders "
            "such as hereditary hemochromatosis."
        ),
        "tier": "T1",
    }
    retr = _RetrievalRecorder(evidence_rows=[fetched])
    result = _lane(frame_rows=[_gap_row()], search_fn=search, retrieval_fn=retr)

    assert result.seed_urls == (_FOUND_URL,)
    # retrieval was called seed-only with the discovered urls + honest labels
    assert len(retr.calls) == 1
    call = retr.calls[0]
    assert call["seed_urls"] == [_FOUND_URL]
    assert call["seed_only"] is True
    assert call["amplified_queries"] == []
    assert call["anchor_seed"] is False
    assert call["seed_source"] == SEED_SOURCE_LABEL
    assert call["seed_query_origin"] == SEED_QUERY_ORIGIN
    # the fetched corpus row is returned verbatim for the caller to merge
    assert result.evidence_rows == [fetched]


# ─────────────────────────────────────────────────────────────────────
# (c) flag OFF -> lane_enabled() False; satisfied rows never touched
# ─────────────────────────────────────────────────────────────────────
def test_c_flag_off_lane_disabled(monkeypatch):
    monkeypatch.delenv("PG_REQUIRED_ENTITY_RETRIEVAL", raising=False)
    assert lane_enabled() is False
    monkeypatch.setenv("PG_REQUIRED_ENTITY_RETRIEVAL", "0")
    assert lane_enabled() is False
    monkeypatch.setenv("PG_REQUIRED_ENTITY_RETRIEVAL", "1")
    assert lane_enabled() is True


def test_c_already_satisfied_rows_untouched_no_calls():
    """A non-gap input row is never searched or fetched (lane is additive)."""
    search = _SearchRecorder(return_urls=[_FOUND_URL])
    retr = _RetrievalRecorder(evidence_rows=[{"source_url": "x"}])
    satisfied = _open_row(quote="x" * 80)
    result = _lane(frame_rows=[satisfied], search_fn=search, retrieval_fn=retr)

    assert result.attempted_entity_ids == ()
    assert result.evidence_rows == []
    assert search.calls == []
    assert retr.calls == []


# ─────────────────────────────────────────────────────────────────────
# (d) §-1.1 provenance honesty: fetched rows keep their REAL url, never relabel
# ─────────────────────────────────────────────────────────────────────
def test_d_fetched_row_keeps_real_url_not_keyed_to_entity():
    """A discovered alternate-URL source keeps its real url and does NOT cover.

    The lane injects fetched rows as ORDINARY corpus evidence. The row carries
    the REAL fetched url (NOT the entity's url_pattern), is NOT keyed to the
    entity_id, and therefore the operator-locked EXACT-equality coverage gate
    (`_entity_canonical_match`) cannot be satisfied by it — no relabel, no
    silent credit.
    """
    search = _SearchRecorder(return_urls=[_FOUND_URL])
    fetched = {
        "source_url": _FOUND_URL,
        "direct_quote": "Iron overload contraindication discussed.",
        "tier": "T1",
    }
    retr = _RetrievalRecorder(evidence_rows=[fetched])
    result = _lane(frame_rows=[_gap_row()], search_fn=search, retrieval_fn=retr)

    row = result.evidence_rows[0]
    # real fetched url, NOT the entity's canonical url_pattern
    assert row["source_url"] == _FOUND_URL
    assert row["source_url"] != _ENTITY_URL
    # no entity_id keying / no canonical relabel
    assert row.get("entity_id") is None
    assert "url_pattern" not in row
    # exact-equality coverage on the real url FAILS (alternate url != url_pattern)
    assert not _entity_canonical_match(_entity_cfg(), {"url": row["source_url"]})
    # and DOES bind only if the real url IS the canonical one (sanity)
    assert _entity_canonical_match(_entity_cfg(), {"url": _ENTITY_URL})


# ─────────────────────────────────────────────────────────────────────
# unsatisfied classifier
# ─────────────────────────────────────────────────────────────────────
def test_frame_row_is_unsatisfied_classifier(monkeypatch):
    monkeypatch.delenv("PG_MIN_VERIFIABLE_SPAN_CHARS", raising=False)
    assert frame_row_is_unsatisfied(_gap_row()) is True
    # METADATA_ONLY with a near-empty span is unsatisfied
    meta = _open_row(quote="short")
    meta = FrameRow(**{**meta.__dict__, "provenance_class": ProvenanceClass.METADATA_ONLY})
    assert frame_row_is_unsatisfied(meta) is True
    # OPEN_ACCESS with a real span is satisfied
    assert frame_row_is_unsatisfied(_open_row(quote="x" * 80)) is False


# ═════════════════════════════════════════════════════════════════════
# COVERAGE LEVER L5 — question/facet-derived required-entity lane
# ═════════════════════════════════════════════════════════════════════
class _FacetObj:
    """Minimal stand-in for expert_facet_planner.Facet (has a ``name``)."""

    def __init__(self, name):
        self.name = name


# --- L5 (a) entity derivation from the question -----------------------
def test_l5_extracts_named_entities_from_question_not_stopwords():
    entities = extract_required_entities(
        "How does AI automation affect the Federal Reserve and Ozempic pricing?"
    )
    joined = " | ".join(entities)
    # named entities are pulled...
    assert "AI" in entities
    assert "Federal Reserve" in entities
    assert "Ozempic" in entities
    # ...but sentence-initial / function words are NOT entities
    assert "How" not in entities
    assert "The" not in entities
    # "Federal Reserve and Ozempic" must SPLIT on the list-conjunction, not weld
    assert "Federal Reserve and Ozempic" not in joined


def test_l5_bridges_name_internal_connective_but_splits_conjunction():
    entities = extract_required_entities("Bank of England versus Ozempic and Mounjaro")
    assert "Bank of England" in entities  # "of" bridges a single name
    assert "Ozempic" in entities and "Mounjaro" in entities  # "and" splits
    assert "Ozempic and Mounjaro" not in " | ".join(entities)


# --- L5 (b) derivation from facets (names + explicit lists) -----------
def test_l5_extracts_from_facet_names_and_explicit_entity_lists():
    facets = [
        _FacetObj("European Central Bank policy stance"),
        {"name": "Labor market", "entities": ["Acemoglu", "Autor"]},
        {"title": "Adoption in the EU", "required_entities": [{"name": "GDPR"}]},
        "plain string facet mentioning Nvidia",
    ]
    entities = extract_required_entities("automation and jobs", facets)
    # explicit curated names are trusted verbatim and come FIRST
    assert entities[0] == "Acemoglu" and entities[1] == "Autor"
    assert "GDPR" in entities
    # proper nouns are pulled from facet display text
    assert "European Central Bank" in entities
    assert "EU" in entities
    assert "Nvidia" in entities


def test_l5_extract_dedups_and_is_bounded(monkeypatch):
    monkeypatch.setenv("PG_COVERAGE_L5_MAX_ENTITIES", "2")
    facets = [{"name": "f", "entities": [f"Entity{i}" for i in range(6)]}]
    entities = extract_required_entities("Entity0 Entity0", facets)
    # dedup (Entity0 once) + compute-safety ceiling of 2
    assert len(entities) == 2
    assert entities[0] == "Entity0"


# --- L5 (c) default-ON kill-switch ------------------------------------
def test_l5_default_on_kill_switch(monkeypatch):
    monkeypatch.delenv("PG_COVERAGE_L5_REQUIRED_ENTITY", raising=False)
    assert coverage_l5_enabled() is True  # DEFAULT-ON
    for off in ("0", "false", "no", "off", "OFF", "False"):
        monkeypatch.setenv("PG_COVERAGE_L5_REQUIRED_ENTITY", off)
        assert coverage_l5_enabled() is False
    monkeypatch.setenv("PG_COVERAGE_L5_REQUIRED_ENTITY", "1")
    assert coverage_l5_enabled() is True


def test_l5_disabled_is_noop_no_calls(monkeypatch):
    monkeypatch.setenv("PG_COVERAGE_L5_REQUIRED_ENTITY", "0")
    search = _SearchRecorder(return_urls=[_FOUND_URL])
    retr = _RetrievalRecorder(evidence_rows=[{"source_url": _FOUND_URL}])
    result = run_l5_required_entity_coverage(
        research_question="AI automation and Ozempic",
        facets=[{"name": "x", "entities": ["Ozempic"]}],
        corpus_texts=[],
        search_fn=search,
        retrieval_fn=retr,
    )
    assert isinstance(result, CoverageL5Result)
    assert result.derived_entities == ()
    assert result.evidence_rows == []
    assert search.calls == [] and retr.calls == []


# --- L5 (d) targets ONLY still-missing derived entities ---------------
def _l5_facets():
    # lowercase facet name (no proper noun) so the derived set is exactly the
    # explicit entity list — keeps the gap-set assertions deterministic.
    return [{"name": "workforce automation", "entities": ["Acemoglu", "Autor", "Brynjolfsson"]}]


def test_l5_targets_only_uncovered_entities(monkeypatch):
    monkeypatch.setenv("PG_COVERAGE_L5_REQUIRED_ENTITY", "1")
    search = _SearchRecorder(return_urls=[_FOUND_URL])
    retr = _RetrievalRecorder(
        evidence_rows=[{"source_url": _FOUND_URL, "direct_quote": "x" * 80, "tier": "T1"}]
    )
    result = run_l5_required_entity_coverage(
        research_question="How does automation affect workers?",
        facets=_l5_facets(),
        # Acemoglu already in the corpus -> covered; Autor + Brynjolfsson missing
        corpus_texts=["Daron Acemoglu models task automation.", "Automation is widespread."],
        search_fn=search,
        retrieval_fn=retr,
    )
    assert "Acemoglu" in result.derived_entities
    assert set(result.missing_entities) == {"Autor", "Brynjolfsson"}
    # exactly one targeted query per MISSING entity (covered ones never queried)
    assert set(result.queries_by_entity.keys()) == {"Autor", "Brynjolfsson"}
    assert len(search.calls) == 2
    # each query is anchored to the research question (keeps it on-subject)
    for q in (c["query"] for c in search.calls):
        assert "automation affect workers" in q.lower()
    # field-agnostic: L5 applies NO clinical-domain bias by default
    assert search.calls[0]["domains"] == []
    # discovered urls were fetched seed-only with honest L5 labels
    assert len(retr.calls) == 1
    call = retr.calls[0]
    assert call["seed_only"] is True
    assert call["seed_source"] == COVERAGE_L5_SEED_SOURCE_LABEL
    assert call["seed_query_origin"] == COVERAGE_L5_SEED_QUERY_ORIGIN


# --- L5 (e) no evidence -> entity STAYS a gap disclosure (no fabricate)
def test_l5_no_evidence_entity_stays_gap_no_fetch():
    search = _SearchRecorder(return_urls=[])  # search surfaces NOTHING
    retr = _RetrievalRecorder(evidence_rows=[{"source_url": "should-not-be-used"}])
    result = run_l5_required_entity_coverage(
        research_question="labor market automation",
        facets=_l5_facets(),
        corpus_texts=[],  # nothing covered -> all three missing
        search_fn=search,
        retrieval_fn=retr,
    )
    # every missing entity has no candidate -> stays a gap; nothing injected
    assert set(result.gap_entities) == {"Acemoglu", "Autor", "Brynjolfsson"}
    assert result.seed_urls == ()
    assert result.evidence_rows == []
    # no seed urls -> the fetch chokepoint is NEVER called (no wasted spend)
    assert retr.calls == []


# --- L5 (f) §-1.1 provenance honesty: fetched rows keep their REAL url -
def test_l5_fetched_rows_keep_real_url_not_keyed_or_relabeled():
    search = _SearchRecorder(return_urls=[_FOUND_URL])
    fetched = {
        "source_url": _FOUND_URL,
        "direct_quote": "Autor discusses labor market polarization.",
        "tier": "T1",
    }
    retr = _RetrievalRecorder(evidence_rows=[fetched])
    result = run_l5_required_entity_coverage(
        research_question="automation and the workforce",
        facets=[{"name": "x", "entities": ["Autor"]}],
        corpus_texts=[],
        search_fn=search,
        retrieval_fn=retr,
    )
    assert result.seed_urls == (_FOUND_URL,)
    row = result.evidence_rows[0]
    # returned verbatim: real fetched url, NOT keyed to an entity, NOT relabeled
    assert row["source_url"] == _FOUND_URL
    assert row.get("entity_id") is None
    assert "url_pattern" not in row
    assert "entity_term" not in row
