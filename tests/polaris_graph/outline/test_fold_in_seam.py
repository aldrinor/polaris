"""The shared fold-in seam (outline/_fold_in.py) — the ONE unit both search_more_evidence and
fetch_url re-enter external content through. Locks the id-collision fail-loud guard and the
end-to-end url-dedup -> renumber -> stamp -> insert orchestrator.

Faithfulness-critical: a second content path (fetch_url) that diverged from this seam could
re-use an existing ev_id and silently overwrite a real evidence row (LAW II breach). The
id-collision assert here is the guard that makes that structurally impossible.
"""
from __future__ import annotations

import asyncio

import pytest

from src.polaris_graph.outline._fold_in import (
    FoldInResult,
    _offset_renumber,
    fold_in_fetched_rows,
)
from src.polaris_graph.outline.outline_agent import OutlineWorkspace


# --------------------------------------------------------------------------- _offset_renumber


def test_offset_renumber_assigns_sequential_ids_from_offset():
    rows = [{"source_url": "http://a", "direct_quote": "x"},
            {"source_url": "http://b", "direct_quote": "y"}]
    out = _offset_renumber(rows, offset=5, existing_ids={"ev_000", "ev_004"})
    assert [r["evidence_id"] for r in out] == ["ev_005", "ev_006"]
    # originals untouched (copied)
    assert "evidence_id" not in rows[0]


def test_offset_renumber_fail_loud_on_collision_with_existing():
    """A new id landing on an existing id is a programming bug in the offset math — it must
    RAISE, never silently overwrite a real evidence row."""
    with pytest.raises(AssertionError, match="id-collision seam FAILED"):
        _offset_renumber([{"x": 1}], offset=3, existing_ids={"ev_003"})


def test_offset_renumber_empty_is_noop():
    assert _offset_renumber([], offset=0, existing_ids=set()) == []


# --------------------------------------------------------------------------- fold_in orchestrator


def _ws(existing: dict | None = None) -> OutlineWorkspace:
    return OutlineWorkspace(research_question="does X work?", ev_store=dict(existing or {}))


def _run(coro):
    return asyncio.run(coro)


def test_fold_in_dedups_by_url_renumbers_and_inserts(monkeypatch):
    # Neutralize the S2 stamp pass so this test isolates dedup/renumber/insert (the stamp pass
    # has its own fail-open contract; here we assert the seam plumbing).
    import src.polaris_graph.outline._fold_in as fi

    async def _passthrough(rows, rq, model):
        return list(rows), [], []

    monkeypatch.setattr(fi, "_stamp_and_delete", _passthrough)

    ws = _ws({"ev_000": {"evidence_id": "ev_000", "source_url": "http://known"}})
    fetched = [
        {"source_url": "http://known", "direct_quote": "dup — already held"},   # url-dup, dropped
        {"source_url": "http://new1", "direct_quote": "fresh one"},
        {"source_url": "http://new2", "direct_quote": "fresh two"},
    ]
    res: FoldInResult = _run(fold_in_fetched_rows(
        ws, fetched, research_question=ws.research_question, agent_model="stub/agent",
    ))

    assert res.n_url_dup == 1
    assert res.n_kept == 2
    # renumbered from next_ev_offset()==1, disjoint from the existing ev_000
    assert [r["evidence_id"] for r in res.kept_rows] == ["ev_001", "ev_002"]
    # inserted into the store, existing row untouched
    assert set(ws.ev_store) == {"ev_000", "ev_001", "ev_002"}
    assert ws.ev_store["ev_000"]["source_url"] == "http://known"


def test_fold_in_never_collides_across_two_sequential_folds(monkeypatch):
    """search_more_evidence then fetch_url (two folds) must produce a disjoint id space — the
    second fold's offset is computed from the store the first mutated."""
    import src.polaris_graph.outline._fold_in as fi

    async def _passthrough(rows, rq, model):
        return list(rows), [], []

    monkeypatch.setattr(fi, "_stamp_and_delete", _passthrough)

    ws = _ws()
    first = _run(fold_in_fetched_rows(
        ws, [{"source_url": "http://a", "direct_quote": "a"}],
        research_question=ws.research_question, agent_model="stub",
    ))
    second = _run(fold_in_fetched_rows(
        ws, [{"source_url": "http://b", "direct_quote": "b"}],
        research_question=ws.research_question, agent_model="stub",
    ))
    ids = [r["evidence_id"] for r in first.kept_rows + second.kept_rows]
    assert ids == ["ev_000", "ev_001"], ids
    assert len(set(ws.ev_store)) == 2, "no id-collision across folds"


def test_fold_in_insert_false_leaves_store_untouched(monkeypatch):
    import src.polaris_graph.outline._fold_in as fi

    async def _passthrough(rows, rq, model):
        return list(rows), [], []

    monkeypatch.setattr(fi, "_stamp_and_delete", _passthrough)

    ws = _ws()
    res = _run(fold_in_fetched_rows(
        ws, [{"source_url": "http://a", "direct_quote": "a"}],
        research_question=ws.research_question, agent_model="stub", insert=False,
    ))
    assert res.n_kept == 1
    assert ws.ev_store == {}, "insert=False must not mutate the store"
