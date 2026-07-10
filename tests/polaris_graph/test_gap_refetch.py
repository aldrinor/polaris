"""S-X thin-section re-fetch contract tests (I-arch-plan ruling R10 / Design 5 ORCH-4).

Offline + hermetic (LAW II — no network, no live corpus, no spend): the production per-query
retrieval lane is replaced by a FIXTURE stub that returns canned ``LiveRetrievalResult``-shaped
rows, and the merge factory is a ``SimpleNamespace`` stand-in for ``LiveRetrievalResult``. These
prove the S-X ENGINE contract that the ORCH-3 recompose seam (WP-3a) will drive:

  * budget resolution precedence (RunConfig > env PG_OUTLINE_GAP_QUERIES > default 0) + abs ceiling;
  * OFF (budget<=0 OR no gap queries) => NO fetch, NO gap_refetch.json (byte-identical);
  * the budget bounds the number of gap QUERIES issued (spend cap, never a source cap);
  * query dedup (first-seen, case-insensitive);
  * the delta merges through the REAL merge contract (global ev_id renumber, delta-local ids);
  * the shared per-question retrieval wall stops issuing further gap queries;
  * the DATA-ONLY gap_refetch.json checkpoint (no verdict key, invariant stamp);
  * fold_gap_delta renumbers the delta against the existing pool + de-dups on source_url.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.polaris_graph.retrieval.gap_refetch import (
    GapRefetchOutcome,
    fold_gap_delta,
    resolve_gap_refetch_budget,
    run_gap_refetch,
)


# --------------------------------------------------------------------------------------------
# Fixtures — a stub retrieval lane + a stub result factory (the ONE allowed mock location).
# --------------------------------------------------------------------------------------------

def _make_row(ev_id: str, url: str, text: str = "some claim text") -> dict:
    return {"evidence_id": ev_id, "source_url": url, "direct_quote": text}


def _result_factory(**kwargs):
    """Stand-in for LiveRetrievalResult — merge_retrieval_results builds one via kwargs."""
    return SimpleNamespace(**kwargs)


def _make_stub_retrieve(rows_by_query):
    """Return a per_query_retrieve stub + a call-log list. Each query yields its canned rows,
    each restarting at ev_000 (exactly like a real per-query run_live_retrieval)."""
    calls: list[str] = []

    def _stub(*, research_question: str, **_kw):
        calls.append(research_question)
        rows = rows_by_query.get(research_question, [])
        return SimpleNamespace(evidence_rows=[dict(r) for r in rows])

    return _stub, calls


# --------------------------------------------------------------------------------------------
# Budget resolution
# --------------------------------------------------------------------------------------------

def test_budget_default_off(monkeypatch):
    monkeypatch.delenv("PG_OUTLINE_GAP_QUERIES", raising=False)
    monkeypatch.delenv("PG_GAP_REFETCH_ABS_MAX", raising=False)
    res = resolve_gap_refetch_budget(run_config=None)
    assert res.value == 0
    assert res.source == "default"
    assert res.clamped is False


def test_budget_from_env(monkeypatch):
    monkeypatch.setenv("PG_OUTLINE_GAP_QUERIES", "4")
    res = resolve_gap_refetch_budget(run_config=None)
    assert res.value == 4
    assert res.source == "env"


def test_budget_runconfig_beats_env(monkeypatch):
    monkeypatch.setenv("PG_OUTLINE_GAP_QUERIES", "3")
    rc = SimpleNamespace(stages=SimpleNamespace(gap_refetch_budget=6))
    res = resolve_gap_refetch_budget(run_config=rc)
    assert res.value == 6
    assert res.source == "run_config"


def test_budget_clamped_to_ceiling(monkeypatch):
    monkeypatch.setenv("PG_OUTLINE_GAP_QUERIES", "999")
    monkeypatch.setenv("PG_GAP_REFETCH_ABS_MAX", "12")
    res = resolve_gap_refetch_budget(run_config=None)
    assert res.value == 12
    assert res.requested == 999
    assert res.clamped is True


def test_budget_malformed_env_fails_open_off(monkeypatch):
    monkeypatch.setenv("PG_OUTLINE_GAP_QUERIES", "not-a-number")
    res = resolve_gap_refetch_budget(run_config=None)
    assert res.value == 0  # fail-open to OFF (no spend)


# --------------------------------------------------------------------------------------------
# OFF path — byte-identical, no fetch, no artifact
# --------------------------------------------------------------------------------------------

def test_off_budget_zero_no_fetch_no_file(tmp_path):
    stub, calls = _make_stub_retrieve({"q1": [_make_row("ev_000", "http://a")]})
    out = run_gap_refetch(
        gap_queries=["q1"], per_query_retrieve=stub, result_factory=_result_factory,
        budget=0, run_dir=tmp_path,
    )
    assert isinstance(out, GapRefetchOutcome)
    assert out.active is False
    assert calls == []                      # NO retrieval fired
    assert out.delta_result is None
    assert not (tmp_path / "gap_refetch.json").exists()   # NO checkpoint written


def test_off_no_gap_queries_no_fetch_no_file(tmp_path):
    stub, calls = _make_stub_retrieve({})
    out = run_gap_refetch(
        gap_queries=[], per_query_retrieve=stub, result_factory=_result_factory,
        budget=4, run_dir=tmp_path,
    )
    assert out.active is False
    assert calls == []
    assert not (tmp_path / "gap_refetch.json").exists()


# --------------------------------------------------------------------------------------------
# Active path — budget bound, dedup, real merge, checkpoint
# --------------------------------------------------------------------------------------------

def test_budget_bounds_queries_issued(tmp_path):
    rows = {
        "q1": [_make_row("ev_000", "http://a")],
        "q2": [_make_row("ev_000", "http://b")],
        "q3": [_make_row("ev_000", "http://c")],
    }
    stub, calls = _make_stub_retrieve(rows)
    out = run_gap_refetch(
        gap_queries=["q1", "q2", "q3"], per_query_retrieve=stub,
        result_factory=_result_factory, budget=2, run_dir=tmp_path,
    )
    assert out.active is True
    assert calls == ["q1", "q2"]            # budget=2 => only 2 gap QUERIES issued
    assert out.queries_issued == ["q1", "q2"]
    assert out.rows_added == 2


def test_query_dedup_case_insensitive(tmp_path):
    rows = {"q1": [_make_row("ev_000", "http://a")]}
    stub, calls = _make_stub_retrieve(rows)
    out = run_gap_refetch(
        gap_queries=["q1", "Q1", "  q1  ", ""], per_query_retrieve=stub,
        result_factory=_result_factory, budget=5, run_dir=tmp_path,
    )
    assert calls == ["q1"]                  # duplicates + blanks collapsed
    assert out.queries_requested == ["q1"]


def test_delta_merged_with_global_local_ev_ids(tmp_path):
    # Two queries, each returning a row that RESTARTS at ev_000 — the real merge must renumber
    # them to globally-unique DELTA-LOCAL ids (ev_000, ev_001).
    rows = {
        "q1": [_make_row("ev_000", "http://a", "alpha")],
        "q2": [_make_row("ev_000", "http://b", "beta")],
    }
    stub, _ = _make_stub_retrieve(rows)
    out = run_gap_refetch(
        gap_queries=["q1", "q2"], per_query_retrieve=stub,
        result_factory=_result_factory, budget=4, run_dir=tmp_path,
    )
    ids = [r["evidence_id"] for r in out.delta_result.evidence_rows]
    assert ids == ["ev_000", "ev_001"]      # delta-local, renumbered, unique
    urls = {r["source_url"] for r in out.delta_result.evidence_rows}
    assert urls == {"http://a", "http://b"}


def test_wall_stops_issuing(tmp_path):
    rows = {"q1": [_make_row("ev_000", "http://a")], "q2": [_make_row("ev_000", "http://b")]}
    stub, calls = _make_stub_retrieve(rows)
    fired = {"n": 0}

    def _wall_passed():
        # trips AFTER the first query has been issued
        return fired["n"] >= 1

    def _counting_stub(*, research_question: str, **_kw):
        fired["n"] += 1
        return SimpleNamespace(evidence_rows=[dict(r) for r in rows.get(research_question, [])])

    out = run_gap_refetch(
        gap_queries=["q1", "q2", "q3"], per_query_retrieve=_counting_stub,
        result_factory=_result_factory, budget=4, run_dir=tmp_path, wall_passed=_wall_passed,
    )
    assert out.wall_hit is True
    assert out.queries_issued == ["q1"]     # stopped before q2


def test_checkpoint_is_data_only(tmp_path):
    import json

    rows = {"q1": [_make_row("ev_000", "http://a")]}
    stub, _ = _make_stub_retrieve(rows)
    run_gap_refetch(
        gap_queries=["q1"], per_query_retrieve=stub, result_factory=_result_factory,
        budget=2, run_dir=tmp_path, section_titles=["Efficacy in older adults"],
    )
    path = tmp_path / "gap_refetch.json"
    assert path.exists()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["stage"] == "sx_thin_section_refetch"
    assert payload["queries_issued"] == ["q1"]
    assert payload["per_query_row_counts"] == {"q1": 1}
    assert payload["section_titles"] == ["Efficacy in older adults"]
    assert "faithfulness_invariant" in payload
    # DATA-ONLY: no verdict / faithfulness-decision key may leak into a checkpoint.
    forbidden = {"verdict", "is_verified", "verified", "strict_verify", "entailment", "nli"}
    assert forbidden.isdisjoint(set(payload.keys()))


# --------------------------------------------------------------------------------------------
# fold_gap_delta — the S3-delta fold (renumber against pool + source-URL dedup)
# --------------------------------------------------------------------------------------------

def test_fold_renumbers_and_dedups():
    existing = [
        _make_row("ev_000", "http://a"),
        _make_row("ev_001", "http://b"),
        _make_row("ev_002", "http://c"),
    ]
    delta = [
        _make_row("ev_000", "http://b"),   # DUPLICATE url -> consolidated, not re-added
        _make_row("ev_001", "http://d"),   # new
        _make_row("ev_002", "http://e"),   # new
    ]
    fold = fold_gap_delta(existing, delta)
    assert fold.added == 2                          # only the two new urls
    ids = [r["evidence_id"] for r in fold.folded_rows]
    assert ids == ["ev_000", "ev_001", "ev_002", "ev_003", "ev_004"]  # global renumber
    # id_remap points the delta-local ids of the ADDED rows to their final pool ids.
    assert fold.id_remap == {"ev_001": "ev_003", "ev_002": "ev_004"}
    # existing rows are never mutated or dropped (§-1.3 consolidate-not-drop)
    assert fold.folded_rows[:3] == existing


def test_fold_empty_delta_is_noop():
    existing = [_make_row("ev_000", "http://a")]
    fold = fold_gap_delta(existing, [])
    assert fold.added == 0
    assert fold.id_remap == {}
    assert fold.folded_rows == existing
