"""Blocker tests for the evidence-selector relevance-floor telemetry + anchor
preservation — I-pipe-003 (#1228). I-pipe-005 (#1230) is DEFERRED (see below).

Forensic finding (dual Claude+Codex 2026-06-12, drb_72 run-29): PG_RELEVANCE_FLOOR
=0.30 cut 236 of 589 evidence rows (589 -> 353) yet the operator-facing
`[select] ... dropped=0` hid the cut. Root cause: `_relevance_floor_selection`
ALREADY reports the real drop in `dropped_count`, but the downstream
capped-finding-dedup pass in run_honest_sweep_r3.py reassigns the EvidenceSelection
to a SECOND `relevance_floor=None` call whose short-pool path legitimately returns
`dropped_count=0`, laundering the floor cut out of the surfaced telemetry. The
operator-facing line is a CROSS-FILE fix (run_honest_sweep_r3.py:4723); the in-file
fix here EMITS the real floor-cut count at the moment the cut happens (survives the
reassignment) and adds an opt-in marquee/required-entity floor exemption.

These tests assert:
  #1228 honest-drop
    (a) flag-OFF (HONEST_DROP=0 + PRESERVE_ANCHORS unset) == current behavior:
        identical kept rows, identical `dropped_count`, identical `notes` string.
    (b) `dropped_count` reflects the REAL number of rows cut by the floor.
    (c) HONEST_DROP default-ON emits a log line carrying the real cut count;
        HONEST_DROP=0 suppresses the log but NEVER changes the selection.
  #1228 preserve-anchors
    (d) a below-floor marquee / required-entity row is DROPPED when the flag is
        OFF and KEPT when PG_RELEVANCE_PRESERVE_ANCHORS=1 (each marquee marker).
    (e) the preserve flag never resurrects a below-floor NON-marquee row.
    (f) a primary_trial_anchors row is floor-exempt regardless of the new flag
        (pre-existing exemption is untouched).
  #1230 deferred
    (g) NO constraint-strip env flag (PG_QUERY_STRIP_CONSTRAINTS) is introduced in
        this module — sub-query construction is in query_decomposer.py / planner.py,
        not the selector, so #1230 is recorded in cross_file_deferred (honest defer,
        no accidental no-op flag).
  faithfulness
    (h) the module touches no strict_verify / NLI / 4-role / provenance gate — the
        preserve flag can only ADD an already-fetched row to the candidate pool; it
        never fabricates or emits an unverified claim.
"""
from __future__ import annotations

import logging
import os
from typing import Any

import pytest

from src.polaris_graph.retrieval import evidence_selector as es
from src.polaris_graph.retrieval.evidence_selector import (
    EvidenceSelection,
    select_evidence_for_generation,
)


# ── deterministic fixture ───────────────────────────────────────────────────
# Question has exactly 5 content tokens, so a row matching k of them scores
# k / 5. Floor 0.30 => need >= 2 matches (2/5 = 0.40) to clear; 1 match
# (1/5 = 0.20) is below floor.
_QUESTION = "alpha beta gamma delta epsilon"
_FLOOR = 0.30

_RELEVANCE_ENV = (
    "PG_RELEVANCE_HONEST_DROP",
    "PG_RELEVANCE_PRESERVE_ANCHORS",
)


@pytest.fixture(autouse=True)
def _clear_relevance_env(monkeypatch):
    """Every test starts from a clean env so default (OFF/ON) semantics hold.
    Also clears unrelated selector flags that could perturb ordering."""
    for name in _RELEVANCE_ENV + (
        "PG_SELECT_SUBQUERY_FLOOR",
        "PG_SELECT_RECENCY_TIEBREAK",
    ):
        monkeypatch.delenv(name, raising=False)
    # Recency tiebreak defaults ON but only reorders same-band ties; pin OFF so
    # the fixture's ordering assertions are unambiguous.
    monkeypatch.setenv("PG_SELECT_RECENCY_TIEBREAK", "0")
    yield


def _row(statement: str, *, url: str, **extra: Any) -> dict[str, Any]:
    row: dict[str, Any] = {"statement": statement, "source_url": url, "tier": "T1"}
    row.update(extra)
    return row


def _base_rows() -> list[dict[str, Any]]:
    # Two above-floor rows (3 matches => 0.60) and one below-floor NON-marquee
    # row (1 match => 0.20) that the floor must cut.
    return [
        _row("alpha beta gamma findings one", url="https://a/1"),
        _row("alpha beta gamma findings two", url="https://a/2"),
        _row("alpha unrelated padding text", url="https://a/3"),
    ]


def _select(rows: list[dict[str, Any]], **kw: Any) -> EvidenceSelection:
    return select_evidence_for_generation(
        research_question=_QUESTION,
        protocol=None,
        classified_sources=[],
        evidence_rows=rows,
        max_rows=999,
        relevance_floor=_FLOOR,
        **kw,
    )


# ── (a) flag-OFF identity ────────────────────────────────────────────────────
def test_a_flag_off_identity_kept_dropped_notes(monkeypatch):
    """HONEST_DROP=0 + PRESERVE_ANCHORS unset reproduces the prior behavior
    exactly: same kept rows, same dropped_count, same notes string."""
    monkeypatch.setenv("PG_RELEVANCE_HONEST_DROP", "0")
    monkeypatch.delenv("PG_RELEVANCE_PRESERVE_ANCHORS", raising=False)

    sel = _select(_base_rows())

    # Below-floor non-marquee row is cut; 2 above-floor rows kept.
    urls = [r["source_url"] for r in sel.selected_rows]
    assert urls == ["https://a/1", "https://a/2"]
    assert sel.dropped_count == 1
    assert sel.selection_strategy == "relevance_floor_v1"
    # Note string is byte-identical to the pre-fix wording (no marquee suffix
    # because the preserve flag is OFF).
    assert sel.notes == [
        f"relevance_floor={_FLOOR}: kept 2/3 rows (>= floor OR primary anchor); "
        f"no max_rows cap; ranked relevance x authority_score; anchor_floor_exempt=0"
    ]


# ── (b) honest drop count reflects real cuts ─────────────────────────────────
def test_b_dropped_count_reflects_real_floor_cuts(monkeypatch):
    """The reported drop equals the number of rows actually cut by the floor —
    never 0 when cuts occurred (the '360 ceiling' / dropped=0 forensic bug)."""
    # Default env: HONEST_DROP on, PRESERVE_ANCHORS off.
    rows = _base_rows() + [
        _row("alpha lone token only here", url="https://a/4"),  # 1 match -> cut
        _row("alpha single match again", url="https://a/5"),    # 1 match -> cut
    ]
    sel = _select(rows)
    # 5 rows in, 2 above floor kept, 3 below-floor non-marquee cut.
    assert len(sel.selected_rows) == 2
    assert sel.dropped_count == 3
    assert sel.dropped_count == len(rows) - len(sel.selected_rows)
    assert sel.dropped_count != 0


# ── (c) honest-drop log fires only when enabled, never alters selection ──────
def test_c_honest_drop_log_emitted_with_real_count(monkeypatch, caplog):
    monkeypatch.setenv("PG_RELEVANCE_HONEST_DROP", "1")
    with caplog.at_level(logging.INFO, logger=es.__name__):
        sel = _select(_base_rows())
    msgs = [r.getMessage() for r in caplog.records]
    assert any("honest_drop" in m and "cut 1 of 3 rows" in m for m in msgs), msgs
    # selection unchanged regardless of the log
    assert sel.dropped_count == 1


def test_c_honest_drop_off_suppresses_log_identical_selection(monkeypatch, caplog):
    monkeypatch.setenv("PG_RELEVANCE_HONEST_DROP", "0")
    with caplog.at_level(logging.INFO, logger=es.__name__):
        sel_off = _select(_base_rows())
    assert not any("honest_drop" in r.getMessage() for r in caplog.records)

    # Selection is identical to the HONEST_DROP-on case (telemetry-only flag).
    monkeypatch.setenv("PG_RELEVANCE_HONEST_DROP", "1")
    sel_on = _select(_base_rows())
    assert [r["source_url"] for r in sel_off.selected_rows] == \
        [r["source_url"] for r in sel_on.selected_rows]
    assert sel_off.dropped_count == sel_on.dropped_count == 1
    assert sel_off.notes == sel_on.notes


# ── (d) preserve-anchors keeps below-floor marquee rows when ON ──────────────
@pytest.mark.parametrize(
    "marker",
    [
        {"is_marquee": True},
        {"required_entity": True},
        {"anchor_seed": True},
        {"is_anchor": True},
        {"entity_anchor": True},
        {"marquee": True},
        {"seed_source": "required_entity_lane"},
        {"query_origin": "required_entity_targeted_search"},
        {"seed_query_origin": "anchor_injection"},
    ],
)
def test_d_preserve_anchors_keeps_below_floor_marquee(monkeypatch, marker):
    """A below-floor row carrying ANY marquee/required-entity marker is dropped
    when the flag is OFF and kept when PG_RELEVANCE_PRESERVE_ANCHORS=1."""
    marquee_row = _row("alpha lonely below floor", url="https://m/1", **marker)
    rows = _base_rows() + [marquee_row]

    # Flag OFF: TWO rows are below floor and cut — the plain non-marquee row
    # a/3 from _base_rows() (1 match -> 0.20) AND this marquee row m/1 (also
    # 0.20); the preserve flag is OFF so the marquee marker grants no exemption.
    monkeypatch.delenv("PG_RELEVANCE_PRESERVE_ANCHORS", raising=False)
    sel_off = _select(rows)
    assert "https://m/1" not in [r["source_url"] for r in sel_off.selected_rows]
    assert sel_off.dropped_count == 2

    # Flag ON: the below-floor marquee row is preserved.
    monkeypatch.setenv("PG_RELEVANCE_PRESERVE_ANCHORS", "1")
    sel_on = _select(rows)
    on_urls = [r["source_url"] for r in sel_on.selected_rows]
    assert "https://m/1" in on_urls
    # The plain below-floor non-marquee row (a/3) is STILL cut.
    assert "https://a/3" not in on_urls
    assert sel_on.dropped_count == 1
    # The widened note discloses the marquee exemption count (ON-mode only).
    assert "marquee_floor_exempt=1" in sel_on.notes[0]


# ── (e) preserve flag never resurrects a below-floor NON-marquee row ─────────
def test_e_preserve_flag_does_not_keep_plain_below_floor_row(monkeypatch):
    monkeypatch.setenv("PG_RELEVANCE_PRESERVE_ANCHORS", "1")
    sel = _select(_base_rows())
    urls = [r["source_url"] for r in sel.selected_rows]
    # The plain below-floor row a/3 (no marquee marker) is still dropped.
    assert "https://a/3" not in urls
    assert sel.dropped_count == 1


# ── (f) primary_trial_anchors exemption is independent of the new flag ───────
def test_f_primary_anchor_exempt_regardless_of_preserve_flag(monkeypatch):
    """A below-floor row matching a primary_trial_anchor stays floor-exempt even
    with PRESERVE_ANCHORS OFF (pre-existing #989 exemption untouched)."""
    # Primary detection requires: (1) anchor in title, (2) primary host/DOI in
    # URL, (3) no non-primary marker in title. `title` is preferred over
    # `statement` by `_row_title_text`, so the lexical score still derives from
    # `statement` ("alpha ..." => 1/5 = 0.20, below floor).
    anchor_url = "https://www.nejm.org/doi/full/10.1056/nejmoa2206038"
    anchor_row = _row(
        "alpha trial below floor",
        url=anchor_url,
        title="SURMOUNT-1 randomized controlled trial",
    )
    rows = _base_rows() + [anchor_row]
    monkeypatch.delenv("PG_RELEVANCE_PRESERVE_ANCHORS", raising=False)
    sel = _select(rows, primary_trial_anchors=["SURMOUNT-1"])
    urls = [r["source_url"] for r in sel.selected_rows]
    assert anchor_url in urls, "primary anchor must be floor-exempt"
    assert "anchor_floor_exempt=1" in sel.notes[0]


# ── (g) #1230 deferred: no constraint-strip flag added to this module ────────
def test_g_no_constraint_strip_flag_introduced(monkeypatch):
    """#1230 (constraint-as-query) is DEFERRED — sub-query construction lives in
    query_decomposer.py / planner.py, not the selector. This module must NOT
    introduce a PG_QUERY_STRIP_CONSTRAINTS no-op flag; sub_queries pass through
    the selector untouched (they only feed the OFF-by-default subquery floor)."""
    import inspect

    src = inspect.getsource(es)
    assert "PG_QUERY_STRIP_CONSTRAINTS" not in src

    # And passing constraint-like sub_queries does not change the selection
    # (sub_queries only matter when PG_SELECT_SUBQUERY_FLOOR is ON, default OFF).
    rows = _base_rows()
    base = _select(rows)
    with_constraints = _select(
        rows,
        sub_queries=["only cite high-quality English-language journal articles"],
    )
    assert [r["source_url"] for r in base.selected_rows] == \
        [r["source_url"] for r in with_constraints.selected_rows]
    assert base.dropped_count == with_constraints.dropped_count


# ── (h) faithfulness gates untouched ─────────────────────────────────────────
def test_h_no_faithfulness_gate_touched():
    """The selector module exposes no CODE path that weakens strict_verify / NLI /
    4-role / provenance. The preserve flag only ADDS an already-fetched row to
    the candidate pool; nothing here emits or fabricates an unverified claim.

    We strip comments AND string/docstring literals (via ``tokenize``) before
    grepping, because the module legitimately *documents* its faithfulness-safety
    rationale in comments (the downstream per-sentence + multi-role gates re-check
    every emitted sentence). Those comments are explanations, not gate calls — the
    test must catch a real CODE reference (an import or call), not a word in a
    comment. Verified 2026-06-12: every banned token in this module appears only
    in a comment, never in code.
    """
    import inspect
    import io
    import tokenize

    src = inspect.getsource(es)
    strip_types = {tokenize.COMMENT, tokenize.STRING}
    for _fstr in ("FSTRING_START", "FSTRING_MIDDLE", "FSTRING_END"):
        _t = getattr(tokenize, _fstr, None)
        if _t is not None:
            strip_types.add(_t)
    code_tokens = [
        tok.string
        for tok in tokenize.generate_tokens(io.StringIO(src).readline)
        if tok.type not in strip_types
    ]
    code_only = " ".join(code_tokens).lower()
    for banned in (
        "strict_verify",
        "strict_verify_entailment",
        "nli",
        "four_role",
        "provenance_min_content_overlap",
    ):
        assert banned not in code_only, (
            f"selector CODE unexpectedly references {banned!r}"
        )
