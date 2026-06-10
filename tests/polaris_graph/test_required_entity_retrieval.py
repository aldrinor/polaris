"""I-complete-004 (#1190): offline tests for the targeted required-entity lane.

ALL deterministic, NO network — ``search_fn`` / ``fetch_fn`` are stubs injected
into ``run_required_entity_lane``. Covers the four faithfulness-critical cases:

(a) targeted query built with authoritative-domain bias (default set UNION the
    entity's own url_pattern host) for a missing entity;
(b) lane finds NO verifiable evidence (fetch stub returns a gap) -> the gap
    FrameRow STAYS a gap (no fabrication, no forced coverage);
(c) PG_REQUIRED_ENTITY_RETRIEVAL OFF -> the caller gate ``lane_enabled()`` is
    False AND, when the lane is nonetheless invoked, no row is mutated; the
    byte-identical contract is the caller checking ``lane_enabled()`` first;
(d) §-1.1 provenance honesty: a re-fetch that yields content whose REAL resolved
    URL != the entity's url_pattern is NOT relabeled to the canonical URL — the
    satisfied row carries its actual url, and coverage binds only on EXACT
    equality (so foreign content can never silently cover the entity).
"""
from __future__ import annotations

import pytest

from src.polaris_graph.nodes.frame_compiler import EvidenceBinding
from src.polaris_graph.retrieval.frame_fetcher import FrameRow, ProvenanceClass
from src.polaris_graph.retrieval.required_entity_retrieval import (
    _DEFAULT_REQUIRED_ENTITY_DOMAINS,
    build_targeted_queries,
    entity_url_host,
    frame_row_is_unsatisfied,
    lane_enabled,
    required_entity_domains,
    run_required_entity_lane,
)
from src.polaris_graph.roles.native_gate_b_inputs import _entity_canonical_match


# ─────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────
_ENTITY_URL = "https://ods.od.nih.gov/factsheets/Iron-HealthProfessional/"
_ENTITY_ID = "fda_iron_supplement_contraindication"


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


def _binding() -> EvidenceBinding:
    return EvidenceBinding(
        entity_id=_ENTITY_ID,
        entity_type="regulatory",
        primary_identifier=f"url:{_ENTITY_URL}",
        secondary_identifiers=(),
        rendering_slot="regulatory_supplement_safety",
        required_fields=("contraindication",),
        min_fields_for_completion=1,
    )


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


def _satisfied_row(url: str, quote: str) -> FrameRow:
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
    """Records every search_fn(query, domains=, max_results=) call."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def __call__(self, query, *, domains, max_results):
        self.calls.append(
            {"query": query, "domains": list(domains), "max_results": max_results}
        )
        return []


def _lane(
    *,
    frame_rows,
    search_fn,
    fetch_fn,
):
    return run_required_entity_lane(
        frame_rows=frame_rows,
        bindings_by_entity_id={_ENTITY_ID: _binding()},
        entity_meta_by_id={},
        entity_cfg_by_id={_ENTITY_ID: _entity_cfg()},
        research_question="iron supplementation cardiovascular safety",
        scope_overrides={"intervention": "iron supplementation"},
        search_fn=search_fn,
        fetch_fn=fetch_fn,
    )


# ─────────────────────────────────────────────────────────────────────
# (a) targeted query built with authoritative-domain bias
# ─────────────────────────────────────────────────────────────────────
def test_a_targeted_query_authoritative_domain_bias(monkeypatch):
    monkeypatch.delenv("PG_REQUIRED_ENTITY_DOMAINS", raising=False)
    rec = _SearchRecorder()

    # fetch_fn returns the SAME gap (so we isolate the search/query behavior).
    _lane(frame_rows=[_gap_row()], search_fn=rec, fetch_fn=lambda b: _gap_row())

    assert rec.calls, "lane must fire at least one targeted query for a gap entity"
    # Every targeted query is anchored to the intervention anchor (here the
    # scope_override intervention, since entity_meta carries no label_name) and a
    # contraindications-category safety term.
    queries = [c["query"] for c in rec.calls]
    assert any("contraindications" in q.lower() for q in queries)
    assert all("iron supplementation" in q for q in queries)
    # Domain bias = the operator-approved default set UNION the entity's OWN host
    # (ods.od.nih.gov is NOT in the default set, so the union is what makes the
    # url-only-canonical entity reachable).
    domains = rec.calls[0]["domains"]
    for default_domain in _DEFAULT_REQUIRED_ENTITY_DOMAINS:
        assert default_domain in domains
    assert "ods.od.nih.gov" in domains


class _EntityMeta:
    """Minimal stand-in for a contract RequiredEntity carrying a label_name."""

    def __init__(self, label_name):
        self.label_name = label_name


def test_label_name_anchor_wins_over_scope_override():
    """When the contract entity_meta carries a label_name, it anchors the query.

    Priority order: entity_meta.label_name > scope_overrides.intervention >
    research_question prefix.
    """
    rec = _SearchRecorder()
    run_required_entity_lane(
        frame_rows=[_gap_row()],
        bindings_by_entity_id={_ENTITY_ID: _binding()},
        entity_meta_by_id={_ENTITY_ID: _EntityMeta("Mounjaro")},
        entity_cfg_by_id={_ENTITY_ID: _entity_cfg()},
        research_question="iron supplementation cardiovascular safety",
        scope_overrides={"intervention": "iron supplementation"},
        search_fn=rec,
        fetch_fn=lambda b: _gap_row(),
    )
    queries = [c["query"] for c in rec.calls]
    assert queries and all(q.startswith("Mounjaro ") for q in queries)


def test_build_targeted_queries_capped_and_category_aware():
    queries = build_targeted_queries(
        entity=_entity_cfg(), intervention_anchor="iron supplementation"
    )
    assert queries  # non-empty
    assert len(queries) <= 3  # default per-entity cap
    # contraindications category terms drive the phrasing
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
# (b) no verifiable evidence -> gap stays a gap (no fabrication)
# ─────────────────────────────────────────────────────────────────────
def test_b_no_evidence_keeps_gap_no_fabrication():
    rec = _SearchRecorder()
    # fetch stub keeps returning a gap (url_pattern fetch found nothing usable).
    result = _lane(
        frame_rows=[_gap_row()], search_fn=rec, fetch_fn=lambda b: _gap_row()
    )
    assert result.attempted_entity_ids == (_ENTITY_ID,)
    assert result.satisfied_entity_ids == ()
    only = result.frame_rows[0]
    assert only.provenance_class == ProvenanceClass.FRAME_GAP_UNRECOVERABLE
    assert only.direct_quote == ""  # nothing fabricated into the span


def test_b_satisfied_refetch_replaces_gap():
    rec = _SearchRecorder()
    good = _satisfied_row(
        url=_ENTITY_URL,
        quote=(
            "Iron supplements are contraindicated in patients with iron overload "
            "disorders such as hereditary hemochromatosis."
        ),
    )
    result = _lane(frame_rows=[_gap_row()], search_fn=rec, fetch_fn=lambda b: good)
    assert result.satisfied_entity_ids == (_ENTITY_ID,)
    assert result.frame_rows[0].provenance_class == ProvenanceClass.OPEN_ACCESS
    # The satisfied row carries the entity's REAL canonical url -> coverage binds.
    assert _entity_canonical_match(_entity_cfg(), {"url": result.frame_rows[0].url})


# ─────────────────────────────────────────────────────────────────────
# (c) flag OFF -> lane_enabled() False; no-op when not invoked
# ─────────────────────────────────────────────────────────────────────
def test_c_flag_off_lane_disabled(monkeypatch):
    monkeypatch.delenv("PG_REQUIRED_ENTITY_RETRIEVAL", raising=False)
    assert lane_enabled() is False
    monkeypatch.setenv("PG_REQUIRED_ENTITY_RETRIEVAL", "0")
    assert lane_enabled() is False
    monkeypatch.setenv("PG_REQUIRED_ENTITY_RETRIEVAL", "1")
    assert lane_enabled() is True


def test_c_already_satisfied_rows_untouched_no_calls():
    """A non-gap input row is never searched or re-fetched (lane is additive)."""
    rec = _SearchRecorder()

    def _fetch_must_not_be_called(binding):  # pragma: no cover - asserts non-call
        raise AssertionError("fetch_fn must not be called for a satisfied row")

    satisfied_input = _satisfied_row(url=_ENTITY_URL, quote="x" * 80)
    result = run_required_entity_lane(
        frame_rows=[satisfied_input],
        bindings_by_entity_id={_ENTITY_ID: _binding()},
        entity_meta_by_id={},
        entity_cfg_by_id={_ENTITY_ID: _entity_cfg()},
        research_question="q",
        scope_overrides=None,
        search_fn=rec,
        fetch_fn=_fetch_must_not_be_called,
    )
    assert result.attempted_entity_ids == ()
    assert result.frame_rows == (satisfied_input,)
    assert rec.calls == []


# ─────────────────────────────────────────────────────────────────────
# (d) §-1.1 provenance honesty: foreign-URL content never relabeled / never covers
# ─────────────────────────────────────────────────────────────────────
def test_d_foreign_url_not_relabeled_and_does_not_cover():
    """A re-fetch landing on a DIFFERENT real URL keeps that real URL.

    The lane re-binds via the entity's OWN url_pattern fetch, so a faithful
    fetch_fn returns whatever URL it actually resolved. If that URL is NOT the
    entity's canonical url_pattern, EXACT-equality coverage must FAIL closed —
    the content is never silently credited as covering the S0 entity, and the
    row's url is the foreign one (no relabel to the canonical pattern).
    """
    rec = _SearchRecorder()
    foreign_url = "https://some-aggregator.example.com/iron"
    foreign = _satisfied_row(
        url=foreign_url,
        quote="Iron overload contraindication discussed on a third-party page.",
    )
    result = _lane(frame_rows=[_gap_row()], search_fn=rec, fetch_fn=lambda b: foreign)

    # The row, if replaced, carries the REAL foreign url (no relabel to canonical).
    replaced = result.frame_rows[0]
    assert replaced.url == foreign_url
    assert replaced.url != _ENTITY_URL
    # EXACT-equality coverage: foreign url != entity url_pattern -> NO coverage.
    assert not _entity_canonical_match(_entity_cfg(), {"url": replaced.url})


# ─────────────────────────────────────────────────────────────────────
# unsatisfied classifier
# ─────────────────────────────────────────────────────────────────────
def test_frame_row_is_unsatisfied_classifier(monkeypatch):
    monkeypatch.delenv("PG_MIN_VERIFIABLE_SPAN_CHARS", raising=False)
    assert frame_row_is_unsatisfied(_gap_row()) is True
    # METADATA_ONLY with a near-empty span is unsatisfied
    meta_empty = _satisfied_row(url=_ENTITY_URL, quote="short")
    meta_empty = FrameRow(
        **{**meta_empty.__dict__, "provenance_class": ProvenanceClass.METADATA_ONLY}
    )
    assert frame_row_is_unsatisfied(meta_empty) is True
    # OPEN_ACCESS with a real span is satisfied
    assert frame_row_is_unsatisfied(_satisfied_row(url=_ENTITY_URL, quote="x" * 80)) is False
