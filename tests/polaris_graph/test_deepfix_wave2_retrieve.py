"""Behavioral fail-loud tests for I-deepfix-001 WAVE-2 WIRER-RETRIEVE seams.

Each test flips the seam's flag ON and asserts the EFFECT APPEARS in real output
(§-1.4 behavioral acceptance), and asserts OFF => byte-identical / keys-absent.
Owned seams covered:
  B7  — corpus_adequacy_gate on-topic predicate (off-topic rows demoted from the
        sufficiency denominator; fail-OPEN on a missing relevance_weight key).
  B3  — query_decomposer directive-screen leg (do-not-view / injected directive
        sub-clauses dropped before they can become live search queries).
  B10(a) — scope_gate intake constraint extraction (NL "before June 2023" parsed
        into protocol.date_range + user_constraints, override still wins).
  B10(b)/B14 — the leaf-module contracts the live_retriever row build merges onto
        each evidence row (publication-year carry + title<->body identity flags).
  B10(d) — evidence_selector date-window demotion (out-of-window source sorts LAST
        but is KEPT) + recency tiebreak inverted when a max-date is present.

No network, no model, no paid run (§8.4): leaf modules + pure functions only.
"""
from __future__ import annotations

import pytest

from src.polaris_graph.nodes import corpus_adequacy_gate as cag
from src.polaris_graph.retrieval import query_decomposer as qd
from src.polaris_graph.retrieval import title_body_consistency as tbc
from src.polaris_graph.retrieval import intake_constraint_extractor as ice
from src.polaris_graph.retrieval import evidence_selector as es


# ───────────────────────────── B7 adequacy on-topic ─────────────────────────


def _rows_with_weights(weights):
    """Grounded (non-stub) rows carrying explicit relevance_weight values + a tier."""
    return [
        {"evidence_id": f"ev_{i:03d}", "source_url": f"https://x/{i}",
         "tier": "T1", "relevance_weight": w, "direct_quote": "q"}
        for i, w in enumerate(weights)
    ]


def test_b7_off_topic_rows_demoted_from_denominator(monkeypatch):
    """ON: rows with an explicit relevance_weight BELOW the floor are excluded from
    the grounded on-topic denominator AND a disclosure note appears (the effect)."""
    monkeypatch.setenv("PG_ADEQUACY_RELEVANCE_FLOOR", "0.30")
    # 5 on-topic (>=0.30) + 4 off-topic (<0.30) grounded rows.
    rows = _rows_with_weights([0.9, 0.8, 0.7, 0.6, 0.5, 0.1, 0.05, 0.2, 0.0])
    tier_counts = {"T1": 9}
    rpt = cag.assess_corpus_adequacy(
        tier_counts=tier_counts, evidence_row_count=9,
        domain="clinical", evidence_rows=rows,
    )
    assert rpt.raw_grounded_evidence_rows == 9, "all 9 are grounded (non-stub)"
    assert rpt.on_topic_evidence_rows == 5, "only the 5 >=floor rows are on-topic"
    assert rpt.evidence_rows == 5, "gate evidence_rows reflects on-topic count"
    # The disclosure note must surface the demotion (the §-1.1 contaminated-pool fix).
    assert any("ON-TOPIC grounded rows" in n for n in rpt.notes), rpt.notes
    # on-topic tier_counts re-tally drives the gate (5 on-topic T1, not 9).
    assert rpt.on_topic_tier_counts.get("T1") == 5


def test_b7_fail_open_missing_relevance_key(monkeypatch):
    """FAIL-OPEN (the wave-1 P0 class): rows WITHOUT a relevance_weight key — every
    legacy/OFF-path/seed row — count as ON-TOPIC. A missing key must NEVER demote a
    row (else legacy runs collapse to a false ABORT)."""
    monkeypatch.setenv("PG_ADEQUACY_RELEVANCE_FLOOR", "0.30")
    rows = [
        {"evidence_id": f"ev_{i:03d}", "source_url": f"https://x/{i}",
         "tier": "T1", "direct_quote": "q"}  # NO relevance_weight key
        for i in range(8)
    ]
    rpt = cag.assess_corpus_adequacy(
        tier_counts={"T1": 8}, evidence_row_count=8,
        domain="clinical", evidence_rows=rows,
    )
    assert rpt.on_topic_evidence_rows == 8, "missing key => on-topic (fail-open)"
    assert rpt.raw_grounded_evidence_rows == 8
    # No demotion => no off-topic disclosure note.
    assert not any("demoted from the denominator" in n for n in rpt.notes)


def test_b7_off_path_byte_identical_when_no_rows():
    """When evidence_rows is NOT supplied the gate is byte-identical to the legacy
    callers (uses evidence_row_count; on-topic fields stay at their inert defaults)."""
    rpt = cag.assess_corpus_adequacy(
        tier_counts={"T1": 3, "T2": 4}, evidence_row_count=6, domain="clinical",
    )
    assert rpt.evidence_rows == 6
    assert rpt.on_topic_relevance_floor == 0.0, "gate inert when no rows passed"
    assert rpt.on_topic_tier_counts == {}


# ───────────────────────────── B3 decomposer leg ────────────────────────────


def test_b3_decomposer_drops_directive_subqueries(monkeypatch):
    """ON (default): an injected do-not-view / output-shape directive clause in the
    question is DROPPED before it can become a live search sub-query."""
    monkeypatch.setenv("PG_QUERY_DIRECTIVE_SCREEN", "1")
    q = (
        "What is the impact of generative AI on the labor market? "
        "You are not allowed to view https://doi.org/10.1016/j.chbr.2025.100652. "
        "What are the effects on wages and on employment levels overall?"
    )
    subs = qd.decompose_question(q)
    joined = " ".join(subs).lower()
    assert "not allowed to view" not in joined, subs
    assert "doi.org/10.1016/j.chbr.2025.100652" not in joined, subs
    # The legitimate research clauses survive.
    assert any("labor market" in s.lower() for s in subs), subs


def test_b3_decomposer_off_keeps_directive(monkeypatch):
    """OFF: byte-identical legacy behavior — the directive clause is NOT screened."""
    monkeypatch.setenv("PG_QUERY_DIRECTIVE_SCREEN", "0")
    q = (
        "What is the impact of generative AI on the labor market? "
        "You are not allowed to view the prohibited Salari paper entirely. "
        "What are the effects on wages and on employment levels overall?"
    )
    subs = qd.decompose_question(q)
    joined = " ".join(subs).lower()
    assert "not allowed to view" in joined, subs


# ─────────────────────── B14 title<->body leaf contract ──────────────────────


def test_b14_mismatch_rederives_title_and_flags(monkeypatch):
    """ON: a metadata title belonging to a DIFFERENT paper than the fetched body
    (fresh2 ev_037 class) is flagged identity_consistent=False and the title is
    re-derived from the body — NEVER dropped. similarity_fn=None: the cheap
    overlap prescreen + fallback catches the gross 'two different papers' case."""
    monkeypatch.setenv("PG_TITLE_BODY_CONSISTENCY", "1")
    verdict = tbc.check_title_body_consistency(
        metadata_title="Enhancing U.S. K-12 Competitiveness Through STEM Policy",
        body_title="Can Online GenAI Discussion Serve as Bellwether for Labor Market Shifts",
        body_text="We study GenAI discussion as a labor-market bellwether ...",
        similarity_fn=None,
    )
    assert verdict.identity_consistent is False
    assert verdict.title_source == "rederived_from_body"
    assert "Bellwether" in verdict.resolved_title
    keys = tbc.consistency_keys(verdict)
    assert keys == {"identity_consistent": False, "title_source": "rederived_from_body"}


def test_b14_consistent_keeps_metadata():
    """A consistent metadata/body title pair keeps the metadata title, flagged True."""
    verdict = tbc.check_title_body_consistency(
        metadata_title="GenAI Impact on the Labor Market: A Systematic Review",
        body_title="GenAI Impact on the Labor Market Systematic Review",
        body_text="...",
        similarity_fn=None,
    )
    assert verdict.identity_consistent is True
    assert verdict.title_source == "metadata"


def test_b14_off_no_keys():
    """OFF: the gate is disabled; consistency_keys is never merged (the wiring
    guards on title_body_consistency_enabled())."""
    monkeypatch_off = {"PG_TITLE_BODY_CONSISTENCY": "0"}
    import os
    old = os.environ.get("PG_TITLE_BODY_CONSISTENCY")
    os.environ.update(monkeypatch_off)
    try:
        assert tbc.title_body_consistency_enabled() is False
    finally:
        if old is None:
            os.environ.pop("PG_TITLE_BODY_CONSISTENCY", None)
        else:
            os.environ["PG_TITLE_BODY_CONSISTENCY"] = old


# ─────────────────────── B10(a) intake constraint extract ────────────────────


def test_b10a_extracts_before_june_2023():
    """The NL 'published before June 2023' is parsed at MONTH precision (Codex
    wave-2 P1: a year-only ceiling let post-June-2023 rows survive). The end bound
    carries the month so the selector can enforce a sub-year ceiling."""
    uc = ice.extract_user_constraints(
        "Please base the report on academic research published before June 2023."
    )
    assert uc.date_end_year == 2023, uc
    assert uc.date_end_month == 6, uc
    assert uc.date_end_iso() == "2023-06", uc
    assert not uc.is_empty()


def test_b10a_extracts_year_only_still_works():
    """A bare-year ceiling ('before 2023') is unchanged — whole-year ceiling."""
    uc = ice.extract_user_constraints(
        "Please base the report on academic research published before 2023."
    )
    assert uc.date_end_year == 2023 and uc.date_end_month is None, uc
    assert uc.date_end_iso() == "2023-12-31", uc


def test_b10a_scope_gate_populates_date_range(tmp_path, monkeypatch):
    """ON: run_scope_gate threads the extracted date window into protocol.date_range
    AND records user_constraints (the audit surface), where today it is dropped."""
    monkeypatch.setenv("PG_EXTRACT_USER_CONSTRAINTS", "1")
    from src.polaris_graph.nodes import scope_gate as sg
    res = sg.run_scope_gate(
        research_question=(
            "What is the impact of generative AI on the labor market based on "
            "academic research published before 2023?"
        ),
        run_id="b10a_test",
        run_dir=str(tmp_path),
    )
    start, end = res.protocol.date_range
    assert end == "2023-12-31", res.protocol.date_range
    assert res.protocol.user_constraints.get("date_end_year") == 2023
    # to_json_dict serializes the window in the {start,end} dict shape.
    data = res.protocol.to_json_dict()
    assert data["date_range"]["end"] == "2023-12-31"
    assert data["user_constraints"]["date_end_year"] == 2023


def test_b10a_off_byte_identical(tmp_path, monkeypatch):
    """OFF: the extractor never runs; date_range stays the template default and
    user_constraints is empty (byte-identical legacy protocol)."""
    monkeypatch.setenv("PG_EXTRACT_USER_CONSTRAINTS", "0")
    from src.polaris_graph.nodes import scope_gate as sg
    res = sg.run_scope_gate(
        research_question=(
            "What is the impact of generative AI on the labor market based on "
            "academic research published before 2023?"
        ),
        run_id="b10a_off_test",
        run_dir=str(tmp_path),
    )
    assert res.protocol.user_constraints == {}
    # The "before 2023" was NOT parsed (legacy bug preserved when OFF).
    assert res.protocol.date_range[1] is None


# ─────────────────────── B10(d) selector date-window demote ──────────────────


def test_b10d_out_of_window_demoted_kept_and_recency_inverted():
    """ON: with protocol.date_range.end=2023, an out-of-window 2025 source is KEPT
    but sorts LAST (demoted), the in-window 2022 source ranks first, AND the
    selection disclosure note records the date-window demotion."""
    protocol = {"date_range": {"start": None, "end": "2023-12-31"},
                "research_question": "generative ai labor market wages employment"}
    rows = [
        {"evidence_id": "ev_000", "source_url": "https://in/2022", "tier": "T1",
         "year": 2022, "statement": "generative ai labor market wages employment",
         "direct_quote": "generative ai labor market wages employment effects"},
        {"evidence_id": "ev_001", "source_url": "https://out/2025", "tier": "T1",
         "year": 2025, "statement": "generative ai labor market wages employment",
         "direct_quote": "generative ai labor market wages employment effects"},
    ]
    classified = [
        type("S", (), {"url": "https://in/2022", "tier": "T1"})(),
        type("S", (), {"url": "https://out/2025", "tier": "T1"})(),
    ]
    sel = es.select_evidence_for_generation(
        research_question="generative ai labor market wages employment",
        protocol=protocol,
        classified_sources=classified,
        evidence_rows=rows,
        max_rows=10,
        relevance_floor=0.0,  # floor path (the production path)
    )
    urls = [r.get("source_url") for r in sel.selected_rows]
    assert set(urls) == {"https://in/2022", "https://out/2025"}, "NEVER dropped"
    assert urls[0] == "https://in/2022", "in-window source ranks first; out-of-window LAST"
    assert any("date-window" in n.lower() for n in sel.notes), sel.notes


def test_b10d_no_window_byte_identical():
    """OFF (no date window): the date-window map is empty, the sort is byte-identical
    and no date-window note is emitted."""
    protocol = {"date_range": {"start": None, "end": None},
                "research_question": "generative ai labor market"}
    rows = [
        {"evidence_id": "ev_000", "source_url": "https://a/2022", "tier": "T1",
         "year": 2022, "statement": "generative ai labor market",
         "direct_quote": "generative ai labor market effects"},
        {"evidence_id": "ev_001", "source_url": "https://b/2025", "tier": "T1",
         "year": 2025, "statement": "generative ai labor market",
         "direct_quote": "generative ai labor market effects"},
    ]
    classified = [
        type("S", (), {"url": "https://a/2022", "tier": "T1"})(),
        type("S", (), {"url": "https://b/2025", "tier": "T1"})(),
    ]
    sel = es.select_evidence_for_generation(
        research_question="generative ai labor market",
        protocol=protocol,
        classified_sources=classified,
        evidence_rows=rows,
        max_rows=10,
        relevance_floor=0.0,
    )
    assert not any("date-window" in n.lower() for n in sel.notes), sel.notes


def test_b10d_undated_row_never_demoted():
    """FAIL-OPEN: an UNDATED row (no resolvable year) is never out-of-window even
    when a date window is set — it keeps full weight."""
    assert es._row_out_of_window({"source_url": "x"}, None, 2023) is False
    assert es._row_out_of_window({"year": 2025}, None, 2023) is True
    assert es._row_out_of_window({"year": 2022}, None, 2023) is False
    assert es._row_out_of_window({"year": 2010}, 2015, None) is True
