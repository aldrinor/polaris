"""I-perm-011 (#1205): max-over-subqueries relevance floor.

`_row_relevance` normalizes lexical overlap by the WHOLE question+protocol token
set, so a long multi-part research question makes the 0.30 floor demand many exact
matches — over-dropping an on-topic paper whose domain vocabulary matches ONE
facet but not the whole paragraph (drb_76: 597->53 pre-select; 74 on-topic T1
shed). The fix scores each row against the BEST-MATCHING decomposed sub-query
(small per-facet denominator), gated on PG_SELECT_SUBQUERY_FLOOR (default OFF).

These tests prove the two contract guarantees:
  1. THROTTLE OPENS: a row matching ONE facet strongly but scoring < floor against
     the whole question is DROPPED when off, KEPT when on (more rows reach gen).
  2. BEHAVIOR-SAFE WHEN OFF: flag off (or no sub-queries) => selection is
     byte-identical to the prior whole-question floor, and the on-mode result is a
     SUPERSET of the off-mode result (monotonic-up; never tightens).
"""
from __future__ import annotations

import pytest

from src.polaris_graph.retrieval.evidence_selector import (
    select_evidence_for_generation,
    _row_relevance,
    _row_relevance_facet,
    _subquery_token_sets,
    _content_tokens,
)


# A long multi-part research question (the drb_76 denominator pathology, in
# miniature): many distinct content tokens, so a row matching only a niche facet
# scores far below the 0.30 floor against the whole paragraph.
_LONG_QUESTION = (
    "Considering the predominant dietary choices that shape and influence the "
    "delicate equilibrium of the intestinal environment, what mechanisms might "
    "mitigate, retard, or otherwise modulate the downstream physiological "
    "consequences across multiple distinct organ systems and metabolic pathways?"
)

# A focused facet sub-query (q1d/STORM decomposition) with a SMALL token set.
_FACET = "gut microbiota dysbiosis colorectal cancer tumorigenesis"

# A target row whose vocabulary matches the FACET strongly but barely overlaps the
# long question's exact words. Off-mode score is < 0.30; facet score is >> 0.30.
_TARGET_ROW = {
    "evidence_id": "ev_facet",
    "url": "https://www.nature.com/articles/microbiota-crc",
    "tier": "T1",
    "title": "Microbiota dysbiosis and colorectal tumorigenesis",
    "statement": (
        "Gut microbiota dysbiosis promotes colorectal cancer tumorigenesis "
        "through pathogenic bacteria and toxic metabolites."
    ),
    "direct_quote": "dysbiosis drives colorectal tumorigenesis",
}

_FLOOR = 0.30


def _classified(url: str, tier: str):
    return {"url": url, "tier": tier}


def test_target_row_scores_below_floor_against_whole_question() -> None:
    """Precondition: with the whole-question score (off mode) the target row is
    UNDER the 0.30 floor — i.e. today's behaviour drops this genuinely on-topic
    row. (If this ever stops holding the fixture is stale, not the fix.)"""
    q_toks = _content_tokens(_LONG_QUESTION)
    base = _row_relevance(_TARGET_ROW, q_toks, set())
    assert base < _FLOOR, f"fixture stale: base score {base} not below floor"


def test_target_row_scores_above_floor_against_best_facet() -> None:
    """The max-over-subqueries score clears the floor because the row matches the
    small-denominator facet strongly."""
    q_toks = _content_tokens(_LONG_QUESTION)
    sets = [_content_tokens(_FACET)]
    facet = _row_relevance_facet(_TARGET_ROW, q_toks, set(), sets)
    assert facet >= _FLOOR, f"facet score {facet} did not clear floor"
    # And it is never LOWER than the whole-question base (monotonic-up).
    assert facet >= _row_relevance(_TARGET_ROW, q_toks, set())


def test_floor_drops_target_when_flag_off(monkeypatch) -> None:
    """OFF: the over-aggressive whole-question floor drops the on-topic row."""
    monkeypatch.delenv("PG_SELECT_SUBQUERY_FLOOR", raising=False)
    # I-beatboth-004 (#1281): the #1205 sub-query floor governs the LEGACY drop path.
    # The PG_SWEEP_CREDIBILITY_REDESIGN="on" default is keep-all (§-1.3 WEIGHT-not-
    # FILTER, breadth-maximal) where no row is ever dropped, so the floor is moot
    # there. Pin the legacy path to exercise the floor feature under test.
    monkeypatch.setenv("PG_SWEEP_CREDIBILITY_REDESIGN", "0")
    sel = select_evidence_for_generation(
        research_question=_LONG_QUESTION,
        protocol=None,
        classified_sources=[_classified(_TARGET_ROW["url"], "T1")],
        evidence_rows=[dict(_TARGET_ROW)],
        max_rows=0,                       # floor mode replaces the cap
        relevance_floor=_FLOOR,
        sub_queries=[_FACET],             # provided, but flag OFF => ignored
    )
    kept_urls = {r["url"] for r in sel.selected_rows}
    assert _TARGET_ROW["url"] not in kept_urls
    assert sel.dropped_count == 1


def test_floor_keeps_target_when_flag_on(monkeypatch) -> None:
    """ON: the throttle OPENS — the row matching one facet strongly is kept."""
    monkeypatch.setenv("PG_SELECT_SUBQUERY_FLOOR", "1")
    sel = select_evidence_for_generation(
        research_question=_LONG_QUESTION,
        protocol=None,
        classified_sources=[_classified(_TARGET_ROW["url"], "T1")],
        evidence_rows=[dict(_TARGET_ROW)],
        max_rows=0,
        relevance_floor=_FLOOR,
        sub_queries=[_FACET],
    )
    kept_urls = {r["url"] for r in sel.selected_rows}
    assert _TARGET_ROW["url"] in kept_urls
    assert sel.dropped_count == 0


def test_on_mode_is_superset_of_off_mode(monkeypatch) -> None:
    """Monotonic-up: every row kept OFF is also kept ON (never tightens), and ON
    keeps at least as many rows. Mixed pool: one facet-matching niche row + one
    row that clears the whole-question floor outright."""
    on_topic_general = {
        "evidence_id": "ev_general",
        "url": "https://example.org/general",
        "tier": "T2",
        "title": "dietary choices and intestinal equilibrium",
        # Overlaps the whole question heavily -> clears the floor in BOTH modes.
        "statement": (
            "predominant dietary choices shape the intestinal equilibrium and "
            "mitigate downstream physiological consequences across organ systems "
            "and metabolic pathways"
        ),
        "direct_quote": "dietary choices modulate intestinal equilibrium",
    }
    rows = [dict(_TARGET_ROW), dict(on_topic_general)]
    classified = [
        _classified(_TARGET_ROW["url"], "T1"),
        _classified(on_topic_general["url"], "T2"),
    ]

    # I-beatboth-004 (#1281): pin the legacy drop path (redesign default is keep-all,
    # where OFF and ON both keep every row so the throttle has nothing to open).
    monkeypatch.setenv("PG_SWEEP_CREDIBILITY_REDESIGN", "0")
    monkeypatch.delenv("PG_SELECT_SUBQUERY_FLOOR", raising=False)
    off = select_evidence_for_generation(
        research_question=_LONG_QUESTION, protocol=None,
        classified_sources=classified, evidence_rows=[dict(r) for r in rows],
        max_rows=0, relevance_floor=_FLOOR, sub_queries=[_FACET],
    )
    off_urls = {r["url"] for r in off.selected_rows}

    monkeypatch.setenv("PG_SELECT_SUBQUERY_FLOOR", "1")
    on = select_evidence_for_generation(
        research_question=_LONG_QUESTION, protocol=None,
        classified_sources=classified, evidence_rows=[dict(r) for r in rows],
        max_rows=0, relevance_floor=_FLOOR, sub_queries=[_FACET],
    )
    on_urls = {r["url"] for r in on.selected_rows}

    assert off_urls.issubset(on_urls), "on mode dropped a row that off kept"
    assert len(on_urls) > len(off_urls), "on mode did not open the throttle"
    assert on_topic_general["url"] in off_urls  # general row clears floor in both


def test_no_subqueries_is_byte_identical(monkeypatch) -> None:
    """Flag ON but NO sub-queries supplied => `_subquery_token_sets` is empty =>
    scoring falls back to the whole-question floor exactly (byte-identical)."""
    monkeypatch.setenv("PG_SELECT_SUBQUERY_FLOOR", "1")
    # I-beatboth-004 (#1281): pin the legacy drop path (redesign default is keep-all).
    monkeypatch.setenv("PG_SWEEP_CREDIBILITY_REDESIGN", "0")
    assert _subquery_token_sets(None) == []
    assert _subquery_token_sets([]) == []
    sel = select_evidence_for_generation(
        research_question=_LONG_QUESTION,
        protocol=None,
        classified_sources=[_classified(_TARGET_ROW["url"], "T1")],
        evidence_rows=[dict(_TARGET_ROW)],
        max_rows=0,
        relevance_floor=_FLOOR,
        sub_queries=None,                 # no facets => fall back
    )
    assert _TARGET_ROW["url"] not in {r["url"] for r in sel.selected_rows}


def test_tier_balanced_truncating_path_unchanged_when_flag_on(monkeypatch) -> None:
    """The lift is CONFINED to the relevance-floor path. On the tier-balanced
    TRUNCATING path (relevance_floor=None, max_rows < pool), lifting scores would
    reorder the top-N and could DISPLACE a previously-kept row — a tighten. So the
    facet lift must NOT apply there: the selection is byte-identical regardless of
    the flag, even with sub_queries supplied."""
    rows = [dict(_TARGET_ROW)]
    for i in range(6):
        rows.append({
            "evidence_id": f"ev_{i}",
            "url": f"https://example.org/row{i}",
            "tier": "T2",
            "title": f"intestinal equilibrium dietary choices {i}",
            "statement": (
                "predominant dietary choices shape intestinal equilibrium and "
                f"modulate downstream physiological consequences {i}"
            ),
            "direct_quote": "",
        })
    classified = [{"url": r["url"], "tier": r["tier"]} for r in rows]

    def _run() -> list[str]:
        sel = select_evidence_for_generation(
            research_question=_LONG_QUESTION,
            protocol=None,
            classified_sources=classified,
            evidence_rows=[dict(r) for r in rows],
            max_rows=3,                    # truncating tier-balanced path
            relevance_floor=None,          # NOT the floor path
            sub_queries=[_FACET],
        )
        return [r["url"] for r in sel.selected_rows]

    monkeypatch.delenv("PG_SELECT_SUBQUERY_FLOOR", raising=False)
    off = _run()
    monkeypatch.setenv("PG_SELECT_SUBQUERY_FLOOR", "1")
    on = _run()
    assert on == off, "facet lift leaked into the tier-balanced truncating path"


def test_facet_helper_clamps_to_unit_interval() -> None:
    """A row that contains every facet token still scores <= 1.0."""
    q_toks = _content_tokens(_LONG_QUESTION)
    sets = [_content_tokens("alpha beta")]
    row = {"statement": "alpha beta alpha beta", "direct_quote": "alpha beta"}
    assert _row_relevance_facet(row, q_toks, set(), sets) == pytest.approx(1.0)


def test_subquery_token_sets_drops_empty_and_respects_flag(monkeypatch) -> None:
    """Empty/whitespace sub-queries are dropped; flag OFF returns []."""
    monkeypatch.setenv("PG_SELECT_SUBQUERY_FLOOR", "1")
    sets = _subquery_token_sets([_FACET, "", "   ", "the a an"])
    assert len(sets) == 1                 # only the real facet survives
    assert sets[0] == _content_tokens(_FACET)
    monkeypatch.setenv("PG_SELECT_SUBQUERY_FLOOR", "0")
    assert _subquery_token_sets([_FACET]) == []
