"""I-deepfix-001 tail-B1 (#1344) finding #8 — span-snap must not merge two members' spans.

RED/GREEN: when a forward sentence-boundary span-snap of member A's verified span would extend PAST
a sibling member B's span co-located in A's row, the snap is CAPPED at B's boundary so B's text is
never emitted under A's single [#ev] token / [N]. Before the fix, A's snapped token swallowed B's
span and the report cited one source's content under another source's number (ev_036's text under
ev_051's [13] instead of its own [14]). Offline, $0.
"""
from __future__ import annotations

import importlib
import types

vc = importlib.import_module("src.polaris_graph.generator.verified_compose")


def _member(evidence_id, direct_quote, weight):
    return types.SimpleNamespace(
        evidence_id=evidence_id,
        direct_quote=direct_quote,
        span_verdict="SUPPORTS",
        credibility_weight=weight,
        origin_cluster_id=evidence_id,
    )


# A's fetched row physically CONTAINS B's quote right after A's own span, with NO period between them
# (the drb_72-shape concatenation) — so A's mid-sentence span would snap forward across into B's text.
_QUOTE_A = "Robots reduce employment sharply"                      # a PREFIX of A's row (no terminator)
_QUOTE_B = "The Philippine study examines media industry outcomes in Manila."  # B's own complete span
_ROW_A = _QUOTE_A + " " + _QUOTE_B                                  # the concatenated fetched row
_POOL = {
    "ev_A": {"direct_quote": _ROW_A},
    "ev_B": {"direct_quote": _QUOTE_B},
}
_BASKET = types.SimpleNamespace(
    claim_cluster_id="c1",
    supporting_members=[_member("ev_A", _QUOTE_A, 0.9), _member("ev_B", _QUOTE_B, 0.5)],
    subject="robots and employment",
    claim_text="robots reduce employment",
)
_MERGE_SIGNATURE = "sharply The Philippine"  # only appears when A's snap swallowed B's span


def test_snap_cap_helper_stops_at_sibling_span():
    """GREEN core: the cap is the offset where B's quote begins in A's row (never past it)."""
    member_a = _BASKET.supporting_members[0]
    boundary = vc._snap_cap_to_sibling_member(
        _BASKET, member_a, _ROW_A, start=0, end=len(_QUOTE_A), evidence_pool=_POOL
    )
    assert boundary == _ROW_A.find(_QUOTE_B), "cap must land at the sibling member's span start"
    assert boundary < len(_ROW_A), "cap must be strictly inside the row (an actual shrink)"


def test_single_draft_does_not_merge_sibling_span_default_on():
    """GREEN e2e: with the cap ON (default) A's token never swallows B's Philippine span; B's text is
    cited to ITS OWN number (ev_B), never under ev_A."""
    out = vc.build_verified_span_draft(_BASKET, _POOL)
    assert out is not None
    assert _MERGE_SIGNATURE not in out, "B's span must NOT be merged under A's [#ev] token"
    assert "[#ev:ev_A" not in out, "A must not emit an over-extended token covering B's span"
    assert "Manila [#ev:ev_B:0-" in out, "B's span is cited to its OWN evidence_id"


def test_single_draft_merges_when_cap_disabled(monkeypatch):
    """RED anchor: with the cap OFF the pre-fix snap swallows B's span into A's single token."""
    monkeypatch.setenv("PG_SNAP_MEMBER_BOUNDARY", "0")
    out = vc.build_verified_span_draft(_BASKET, _POOL)
    assert out is not None
    assert _MERGE_SIGNATURE in out and "[#ev:ev_A" in out, "pre-fix: A's token merges B's span"


def test_multi_draft_binds_each_member_to_its_own_token():
    """GREEN e2e (multi): B's Philippine span is cited to ev_B only — never merged under ev_A."""
    out = vc.build_verified_span_draft_multi(_BASKET, _POOL)
    assert out is not None
    assert _MERGE_SIGNATURE not in out, "A's token must not swallow B's span"
    assert "[#ev:ev_B:" in out, "B cites its own span"
    # the Philippine span never resolves under ev_A anywhere in the output
    assert "outcomes in Manila [#ev:ev_A" not in out


def test_multi_draft_merges_when_cap_disabled(monkeypatch):
    """RED anchor (multi): cap OFF reproduces the merge under A's single token."""
    monkeypatch.setenv("PG_SNAP_MEMBER_BOUNDARY", "0")
    out = vc.build_verified_span_draft_multi(_BASKET, _POOL)
    assert out is not None
    assert _MERGE_SIGNATURE in out, "pre-fix: A's snapped span swallows B's text"
