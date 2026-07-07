"""I-deepfix-001 Wave-3 COVERAGE (#1344) — RED/GREEN unit tests for the three additive,
faithfulness-neutral coverage levers:

  (A) PG_QGEN_PARALLEL_QUERIES — bounded-parallel seed-frontier fan-out
      (fs_researcher_query_gen._issue_seed_frontier): default 1 = serial byte-identical;
      >1 = order-stable parallel returning the SAME query set as serial (first-seen-wins).
  (B) PG_OPENALEX_DATE_FILTER — additive date-scoped OpenAlex lane
      (domain_backends.openalex_search + _openalex_date_filter): a date window adds a `filter`
      param and returns candidates; no window => NO `filter` param (byte-identical); the union
      of the base + date-scoped hits is a strict SUPERSET (drops no base source).
  (C) PG_LANDMARK_EXPANDER — in-window landmark-study query expander
      (landmark_study_expander): default OFF byte-identical; the enumeration prompt is
      constrained to the question's publication window (in-window only, never a later
      re-publication); the widen is additive (strict superset, budget raised) and an empty
      enumeration is a byte-identical no-op.

Imports are narrow (no heavy models / no live network): the fan-out uses a fake
`per_query_retrieve`, the OpenAlex HTTP GET is monkeypatched, and the landmark LLM is a fake.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from src.polaris_graph.retrieval import fs_researcher_query_gen as fsq
from src.polaris_graph.retrieval import landmark_study_expander as lse
from src.polaris_graph.retrieval import domain_backends as db

# Wave-3b (#1344): the landmark liveness tests below drive the REAL run_gate_b activation canary
# (assert_activation_markers_fired). Importing it is offline (the module opens no client / socket at
# import — see its module docstring). Bootstrap the repo root onto sys.path exactly like the sibling
# test_activation_canary_wave3a.py so ``scripts.dr_benchmark.run_gate_b`` resolves.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
os.environ.setdefault("PG_VERIFICATION_MODE", "off")  # deterministic import, no judge calls

import scripts.dr_benchmark.run_gate_b as rg  # noqa: E402


# ─────────────────────────────────────────────────────────────────────────────
# Test doubles
# ─────────────────────────────────────────────────────────────────────────────
class _FakeResult:
    """Minimal stand-in for a LiveRetrievalResult carrying `evidence_rows`."""

    def __init__(self, query: str) -> None:
        self.query = query
        self.evidence_rows = [{"q": query}]


def _make_retrieve(calls: list[str]):
    def _retrieve(*, research_question: str, **_kw):
        calls.append(research_question)
        return _FakeResult(research_question)

    return _retrieve


def _never_wall() -> bool:
    return False


# ─────────────────────────────────────────────────────────────────────────────
# (A) PG_QGEN_PARALLEL_QUERIES — order-stable parallel == serial
# ─────────────────────────────────────────────────────────────────────────────
def test_a_serial_default_is_byte_identical(monkeypatch):
    """Default (flag unset) issues the frontier serially in seed order, first-seen-wins,
    budget-capped — the byte-identical legacy behaviour."""
    monkeypatch.delenv("PG_QGEN_PARALLEL_QUERIES", raising=False)
    assert fsq._qgen_parallel_workers() == 1

    seeds = ["Alpha", "Beta", "alpha", "Gamma", "Delta"]  # 'alpha' dup of 'Alpha'
    seen: set[str] = set()
    calls: list[str] = []
    issued, results, rows = fsq._issue_seed_frontier(
        seeds, seen, budget=10,
        per_query_retrieve=_make_retrieve(calls),
        retrieve_kwargs={}, wall_passed=_never_wall,
    )
    # dedup (case-insensitive, first-seen-wins), order preserved.
    assert issued == ["Alpha", "Beta", "Gamma", "Delta"]
    assert calls == issued                       # one retrieve per issued query, in order
    assert [r.query for r in results] == issued  # results in seed order
    assert len(rows) == len(issued)              # corpus rows accumulated
    assert seen == {"alpha", "beta", "gamma", "delta"}  # seen_q mutated in place


def test_a_budget_caps_issued_set(monkeypatch):
    monkeypatch.delenv("PG_QGEN_PARALLEL_QUERIES", raising=False)
    seeds = ["a", "b", "c", "d", "e"]
    issued, _r, _rows = fsq._issue_seed_frontier(
        seeds, set(), budget=2,
        per_query_retrieve=_make_retrieve([]),
        retrieve_kwargs={}, wall_passed=_never_wall,
    )
    assert issued == ["a", "b"]  # only the first `budget` unique queries


def test_a_parallel_matches_serial_order_stable(monkeypatch):
    """PG_QGEN_PARALLEL_QUERIES>1: the parallel fan-out issues the SAME query set as serial,
    merged back in seed order (order-stable), with seen_q updated identically."""
    seeds = ["q1", "q2", "q1", "q3", "q4", "q5"]  # 'q1' repeated

    # Serial reference.
    monkeypatch.setenv("PG_QGEN_PARALLEL_QUERIES", "1")
    seen_s: set[str] = set()
    issued_s, results_s, rows_s = fsq._issue_seed_frontier(
        seeds, seen_s, budget=10,
        per_query_retrieve=_make_retrieve([]),
        retrieve_kwargs={}, wall_passed=_never_wall,
    )

    # Parallel.
    monkeypatch.setenv("PG_QGEN_PARALLEL_QUERIES", "4")
    assert fsq._qgen_parallel_workers() == 4
    seen_p: set[str] = set()
    issued_p, results_p, rows_p = fsq._issue_seed_frontier(
        seeds, seen_p, budget=10,
        per_query_retrieve=_make_retrieve([]),
        retrieve_kwargs={}, wall_passed=_never_wall,
    )

    assert issued_p == issued_s == ["q1", "q2", "q3", "q4", "q5"]
    assert [r.query for r in results_p] == [r.query for r in results_s] == issued_s
    assert seen_p == seen_s
    assert len(rows_p) == len(rows_s) == len(issued_s)


def test_a_bad_value_falls_back_to_serial(monkeypatch):
    monkeypatch.setenv("PG_QGEN_PARALLEL_QUERIES", "not-an-int")
    assert fsq._qgen_parallel_workers() == 1


def test_a_parallel_emits_activation_marker(monkeypatch, caplog):
    """Anti-dark liveness (Fable P1, Wave-3b Codex P1.2): the >1 (parallel) path emits the
    `[activation] qgen_parallel_fanout: workers=N selected=M issued=K` marker — carrying the REALIZED
    ``issued`` count — so the official run's log can DISTINGUISH serial from parallel-N; the serial
    default emits NO such line (byte-identical). Here the wall never trips so issued == selected == 3."""
    import logging as _logging

    seeds = ["p1", "p2", "p3"]
    monkeypatch.setenv("PG_QGEN_PARALLEL_QUERIES", "4")
    with caplog.at_level(_logging.INFO, logger="polaris_graph.fs_researcher_query_gen"):
        fsq._issue_seed_frontier(
            seeds, set(), budget=10,
            per_query_retrieve=_make_retrieve([]),
            retrieve_kwargs={}, wall_passed=_never_wall,
        )
    _msgs = [r.getMessage() for r in caplog.records]
    # the marker now REQUIRES the realized issued= field (canary positive_re keys on it)
    assert any(
        m == "[activation] qgen_parallel_fanout: workers=4 selected=3 issued=3" for m in _msgs
    ), _msgs

    caplog.clear()
    monkeypatch.setenv("PG_QGEN_PARALLEL_QUERIES", "1")
    with caplog.at_level(_logging.INFO, logger="polaris_graph.fs_researcher_query_gen"):
        fsq._issue_seed_frontier(
            seeds, set(), budget=10,
            per_query_retrieve=_make_retrieve([]),
            retrieve_kwargs={}, wall_passed=_never_wall,
        )
    assert not any("qgen_parallel_fanout" in r.getMessage() for r in caplog.records)


def test_a_parallel_marker_reports_realized_issued_not_selected(monkeypatch, caplog):
    """Wave-3b (Codex P1.2 FALSE-GREEN fix): when ``selected[0]`` trips the retrieval wall the fan-out
    of ``_rest`` is skipped, so only 1 of the 4 selected queries actually ISSUES. The marker must report
    the REALIZED ``issued=1`` — NOT the pre-issue ``selected=4`` INTENT — so the official log / PROVEN
    table tells the truth about the fan-out collapse. issued=1 (not >=2) still PASSES the canary (a wall
    truncation is compute-safety, never gated on a count per §-1.3); the point is the number is TRUE."""
    import logging as _logging

    monkeypatch.setenv("PG_QGEN_PARALLEL_QUERIES", "4")
    state = {"wall_tripped": False}

    def _retrieve(*, research_question: str, **_kw):
        state["wall_tripped"] = True  # the FIRST (serial) retrieval consumes the wall
        return _FakeResult(research_question)

    def _wall() -> bool:
        return state["wall_tripped"]

    seeds = ["s0", "s1", "s2", "s3"]
    with caplog.at_level(_logging.INFO, logger="polaris_graph.fs_researcher_query_gen"):
        issued, _r, _rows = fsq._issue_seed_frontier(
            seeds, set(), budget=10,
            per_query_retrieve=_retrieve,
            retrieve_kwargs={}, wall_passed=_wall,
        )
    assert issued == ["s0"]  # only the first serial query fired
    _msgs = [r.getMessage() for r in caplog.records]
    # REALIZED count: selected=4 (dedup) but issued=1 (wall-tripped tail) — the honesty fix.
    assert "[activation] qgen_parallel_fanout: workers=4 selected=4 issued=1" in _msgs, _msgs
    # the misleading "fired 4" reading must NOT appear anywhere.
    assert not any("issued=4" in m for m in _msgs), _msgs


def test_a_parallel_seed_bound_to_first_selected_query_no_race(monkeypatch):
    """Race-safety at the production call site (Fable P1): the layer-4 seed — attached by the
    injected closure's SERIAL-written check-then-set on shared state — binds to EXACTLY the first
    selected query even under the parallel fan-out, so the same seed PDFs are not re-fetched by
    several concurrent instances. Emulates run_honest_sweep_r3._iter_per_query_retrieve's side-effect.
    Order-stable + additive-safe (never drops a source)."""
    monkeypatch.setenv("PG_QGEN_PARALLEL_QUERIES", "8")
    seed_used = {"done": False}
    seed_carriers: list[str] = []

    def _retrieve(*, research_question: str, **_kw):
        # the exact non-atomic check-then-set the production closure uses (written for serial calls)
        if not seed_used["done"]:
            seed_used["done"] = True
            seed_carriers.append(research_question)
        return _FakeResult(research_question)

    seeds = [f"q{i}" for i in range(8)]
    issued, results, rows = fsq._issue_seed_frontier(
        seeds, set(), budget=8,
        per_query_retrieve=_retrieve,
        retrieve_kwargs={}, wall_passed=_never_wall,
    )
    assert issued == seeds                       # order-stable: same set, same order as serial
    assert [r.query for r in results] == seeds   # results merged in seed order
    assert len(rows) == len(seeds)               # every query's rows accumulated (no drop)
    # the seed attaches exactly once, deterministically, to the FIRST selected query (no double-attach)
    assert seed_carriers == ["q0"]


def test_a_parallel_rechecks_wall_after_first_serial_query(monkeypatch):
    """Codex P1 (retrieval-wall bound): on the parallel path ``selected[0]`` is issued SERIALLY,
    and its retrieval can itself consume the shared retrieval wall. When it does, the remaining
    frontier (``_rest``) must NOT be dispatched — mirroring the serial loop's per-iteration
    ``wall_passed()`` guard (whose next iteration would ``break``). Without the re-check the whole
    ``_rest`` batch launches past the wall (off-path execution/spend). Coverage stays additive:
    this issues no MORE than serial would."""
    monkeypatch.setenv("PG_QGEN_PARALLEL_QUERIES", "4")
    assert fsq._qgen_parallel_workers() == 4

    state = {"wall_tripped": False}
    calls: list[str] = []

    def _retrieve(*, research_question: str, **_kw):
        calls.append(research_question)
        state["wall_tripped"] = True  # the FIRST (serial) retrieval consumes the wall
        return _FakeResult(research_question)

    def _wall() -> bool:
        return state["wall_tripped"]

    seeds = ["s0", "s1", "s2", "s3"]
    issued, results, rows = fsq._issue_seed_frontier(
        seeds, set(), budget=10,
        per_query_retrieve=_retrieve,
        retrieve_kwargs={}, wall_passed=_wall,
    )
    # ONLY the first serial query fired; the wall it tripped stopped the fan-out of `_rest`.
    assert issued == ["s0"]
    assert calls == ["s0"]                    # `_rest` NEVER dispatched (no off-path retrievals)
    assert [r.query for r in results] == ["s0"]
    assert len(rows) == 1                     # exactly the first query's rows accumulated
    # This matches the SERIAL path exactly: serial would issue s0 then `break` on the wall.


def test_a_parallel_unissued_rest_not_marked_seen(monkeypatch):
    """Codex P0 (no-drop / order-stable): when the wall trips on ``selected[0]`` the un-issued
    ``_rest`` queries must NOT be left in ``seen_q``. The downstream facet-completeness expansion loop
    reads ``seen_q`` as ``already_issued``; a query marked seen but never issued can never be re-issued
    — a real dropped-source breadth loss. The serial path only marks a query seen when it retrieves it,
    so the parallel path must do the same: exactly the ISSUED query is in ``seen_q``, the skipped tail
    stays eligible."""
    monkeypatch.setenv("PG_QGEN_PARALLEL_QUERIES", "4")
    state = {"wall_tripped": False}

    def _retrieve(*, research_question: str, **_kw):
        state["wall_tripped"] = True  # the FIRST (serial) retrieval consumes the wall
        return _FakeResult(research_question)

    def _wall() -> bool:
        return state["wall_tripped"]

    seeds = ["s0", "s1", "s2", "s3"]
    seen: set[str] = set()
    issued, _r, _rows = fsq._issue_seed_frontier(
        seeds, seen, budget=10,
        per_query_retrieve=_retrieve,
        retrieve_kwargs={}, wall_passed=_wall,
    )
    assert issued == ["s0"]
    # ONLY the issued query is marked seen; the un-issued tail stays eligible for the R2 expansion loop.
    assert seen == {"s0"}
    assert "s1" not in seen and "s2" not in seen and "s3" not in seen


# ─────────────────────────────────────────────────────────────────────────────
# (B) PG_OPENALEX_DATE_FILTER — additive date-scoped lane
# ─────────────────────────────────────────────────────────────────────────────
def test_b_date_filter_string():
    assert db._openalex_date_filter(None, None) is None
    assert db._openalex_date_filter("2010-01-01", None) == "from_publication_date:2010-01-01"
    assert db._openalex_date_filter(None, "2023-06-30") == "to_publication_date:2023-06-30"
    assert (
        db._openalex_date_filter("2010-01-01", "2023-06-30")
        == "from_publication_date:2010-01-01,to_publication_date:2023-06-30"
    )


def _fake_http(payload: dict, captured: list[dict]):
    def _get(url, params=None, *, strict=False):
        captured.append(dict(params or {}))
        return payload

    return _get


def test_b_openalex_no_dates_is_byte_identical(monkeypatch):
    """Unscoped call (no dates) attaches NO `filter` param — byte-identical to legacy."""
    captured: list[dict] = []
    payload = {"results": [{"id": "https://openalex.org/W1", "doi": "", "display_name": "Base"}],
               "meta": {}}
    monkeypatch.setattr(db, "_http_get_json", _fake_http(payload, captured))
    hits = db.openalex_search("genai labor market", limit=5)
    assert len(hits) == 1
    assert "filter" not in captured[0]


def test_b_openalex_date_scoped_adds_filter_and_returns(monkeypatch):
    """Date-scoped call attaches the publication-window `filter` and still returns candidates."""
    captured: list[dict] = []
    payload = {"results": [{"id": "https://openalex.org/W2", "doi": "", "display_name": "Dated"}],
               "meta": {}}
    monkeypatch.setattr(db, "_http_get_json", _fake_http(payload, captured))
    hits = db.openalex_search(
        "genai labor market", limit=5,
        from_date="2010-01-01", to_date="2023-06-30",
    )
    assert len(hits) == 1
    assert captured[0].get("filter") == (
        "from_publication_date:2010-01-01,to_publication_date:2023-06-30"
    )


def test_b_union_is_additive_superset():
    """The caller UNIONs date-scoped hits on top of the base hits by url (shared seen_urls
    dedup) — the union is a strict SUPERSET of the base and drops no base source."""
    base = ["u_base_1", "u_base_2"]
    dated = ["u_base_1", "u_dated_new"]  # overlaps base_1, adds dated_new
    seen = set()
    union: list[str] = []
    for u in base + dated:
        if u in seen:
            continue
        seen.add(u)
        union.append(u)
    assert set(base).issubset(set(union))       # never drops a base source
    assert "u_dated_new" in union               # adds the in-window primary
    assert len(union) >= len(base)


# ─────────────────────────────────────────────────────────────────────────────
# (B) date-window normalization (live_retriever helpers)
# ─────────────────────────────────────────────────────────────────────────────
def test_b_full_iso_ceiling_month_snap():
    from src.polaris_graph.retrieval.live_retriever import _openalex_full_iso
    # month-precision ceiling snaps to the last day of that month (inclusive)
    assert _openalex_full_iso("2023-06", ceiling=True) == "2023-06-30"
    assert _openalex_full_iso("2024-02", ceiling=True) == "2024-02-29"  # leap year
    # month-precision floor snaps to the first day
    assert _openalex_full_iso("2020-03", ceiling=False) == "2020-03-01"
    # already-full and year-only bounds
    assert _openalex_full_iso("2020-03-01", ceiling=False) == "2020-03-01"
    assert _openalex_full_iso("2023-12-31", ceiling=True) == "2023-12-31"
    assert _openalex_full_iso(None, ceiling=True) is None
    assert _openalex_full_iso("", ceiling=False) is None


# ─────────────────────────────────────────────────────────────────────────────
# (C) PG_LANDMARK_EXPANDER — in-window landmark study expander
# ─────────────────────────────────────────────────────────────────────────────
def test_c_flag_default_off(monkeypatch):
    monkeypatch.delenv("PG_LANDMARK_EXPANDER", raising=False)
    assert lse.landmark_study_expansion_enabled() is False
    monkeypatch.setenv("PG_LANDMARK_EXPANDER", "1")
    assert lse.landmark_study_expansion_enabled() is True
    monkeypatch.setenv("PG_LANDMARK_EXPANDER", "0")
    assert lse.landmark_study_expansion_enabled() is False


def test_c_prompt_is_window_constrained():
    """When a publication window is supplied, the enumeration prompt DEMANDS the in-window
    version and FORBIDS a later re-publication — the in-window-only guard."""
    prompts: list[str] = []

    def _fake_llm(prompt: str) -> str:
        prompts.append(prompt)
        return "Noy & Zhang, 2023, ChatGPT productivity experiment\nBrynjolfsson et al., 2023, GenAI call center"

    qs = lse.plan_landmark_study_queries(
        "impact of Generative AI on the labor market for studies published before June 2023",
        _fake_llm, window_end="2023-06",
    )
    assert prompts, "the enumerator must issue exactly one bounded LLM call"
    p = prompts[0]
    assert "2023-06" in p                        # the window ceiling is spliced in
    assert "ON OR BEFORE" in p                    # in-window demand
    assert "re-publication" in p                  # forbids the later re-publication
    # every emitted query carries a study name (scope-anchored, non-empty)
    assert qs and all(q.strip() for q in qs)
    assert any("Noy" in q for q in qs)


def test_c_no_window_still_honours_stated_window():
    """With no explicit window_end the prompt still instructs in-window discipline (never
    hardcodes a date)."""
    prompts: list[str] = []

    def _fake_llm(prompt: str) -> str:
        prompts.append(prompt)
        return "Peng et al., 2023, Copilot developer RCT"

    qs = lse.plan_landmark_study_queries("impact of GenAI on jobs", _fake_llm, window_end=None)
    assert prompts
    assert "date window" in prompts[0].lower()
    assert qs


def test_c_widen_is_additive_superset():
    """widen_with_landmark_studies ADDS the landmark queries on top of the FULL baseline window
    (strict superset) and RAISES the budget by the added slice — never swaps out a baseline query."""
    monkeypatch_env = {}
    base = [f"base_{i}" for i in range(5)]
    landmark = ["lm_a base", "lm_b base"]
    widened, new_budget = lse.widen_with_landmark_studies(base, landmark, max_queries=5)
    issued_before = base[:5]
    issued_after = widened[:new_budget]
    # every baseline query the flag-OFF path would issue is STILL issued
    for b in issued_before:
        assert b in issued_after
    # the landmark queries are ADDED
    for lm in landmark:
        assert lm in issued_after
    assert new_budget == 5 + 2


def test_c_empty_enumeration_is_no_op():
    """An empty landmark enumeration is a byte-identical no-op (no queries, budget unchanged)."""
    def _empty_llm(_prompt: str) -> str:
        return "none"

    qs = lse.plan_landmark_study_queries("q", _empty_llm, window_end="2023-06")
    assert qs == []
    base = ["b0", "b1"]
    widened, budget = lse.widen_with_landmark_studies(base, [], max_queries=2)
    assert widened == base
    assert budget == 2


def test_c_landmark_lane_fail_open_never_aborts_qgen(monkeypatch):
    """Codex/Fable P1 (additive-on-failure): with PG_LANDMARK_EXPANDER=1, if the landmark expander's
    planning call raises (module broken / LLM failure), the additive lane must add ZERO queries and the
    qgen path must PROCEED on the unchanged baseline facet frontier — it must NEVER abort the whole
    query generation. The baseline queries are still issued (no drop) and the exception does not
    propagate. Drives ``_plan_expert_facet_queries`` with the sibling lanes OFF so only the landmark
    lane fires, and makes its plan call explode."""
    from src.polaris_graph.retrieval import (
        expert_facet_planner as efp,
        facet_completeness as fc,
        language_profile as lp,
        sub_entity_query_expander as sqe,
        landmark_study_expander as lse_mod,
    )

    class _Facet:
        def __init__(self, queries):
            self.queries = queries

    monkeypatch.delenv("PG_QGEN_PARALLEL_QUERIES", raising=False)   # serial issue
    monkeypatch.setenv("PG_LANDMARK_EXPANDER", "1")                 # additive lane ON
    monkeypatch.setattr(efp, "expert_facet_enabled", lambda: True)
    monkeypatch.setattr(
        efp, "plan_expert_facets",
        lambda _q, _llm: [_Facet(["fq_a", "fq_b"]), _Facet(["fq_c"])],
    )
    monkeypatch.setattr(fc, "facet_completeness_enabled", lambda: False)
    monkeypatch.setattr(lp, "multilingual_enabled", lambda: False)
    monkeypatch.setattr(sqe, "sub_entity_expansion_enabled", lambda: False)

    def _boom(*_a, **_k):
        raise RuntimeError("landmark planner exploded")

    monkeypatch.setattr(lse_mod, "plan_landmark_study_queries", _boom)

    calls: list[str] = []
    queries, results = fsq._plan_expert_facet_queries(
        "impact of GenAI on the labor market",
        lambda _p: "",
        _make_retrieve(calls),
        max_queries=10,
        retrieve_kwargs={},
    )
    # The landmark failure is swallowed (fail-open): the baseline breadth-first facet frontier is still
    # issued in full, nothing is dropped, and no exception escapes.
    assert queries == ["fq_a", "fq_c", "fq_b"]   # breadth-first baseline, unchanged by the failure
    assert calls == ["fq_a", "fq_c", "fq_b"]     # each baseline query retrieved (additive, no drop)
    assert len(results) == 3


# ─────────────────────────────────────────────────────────────────────────────
# (C) PG_LANDMARK_EXPANDER — Wave-3b liveness HONESTY: the run_gate_b activation canary must
#     REJECT a fail-open (dark) landmark lane and ACCEPT a ran-ok lane (even at count=0).
# ─────────────────────────────────────────────────────────────────────────────
_LOG_PREFIX = "2026-07-06 12:00:00,000 INFO src.polaris_graph - "


def _run_landmark_canary(monkeypatch, *marker_lines):
    """Drive rg.assert_activation_markers_fired over a run-log carrying ``marker_lines`` with the canary
    opt-in + PG_LANDMARK_EXPANDER ON and the sibling coverage flags OFF, so ONLY the landmark spec is
    asserted (every other module flag defaults OFF => self-scoped out)."""
    monkeypatch.setenv("PG_ACTIVATION_CANARY", "1")
    monkeypatch.setenv("PG_LANDMARK_EXPANDER", "1")
    monkeypatch.delenv("PG_QGEN_PARALLEL_QUERIES", raising=False)  # numeric spec: OFF (<2) => self-skip
    monkeypatch.delenv("PG_OPENALEX_DATE_FILTER", raising=False)   # whitelist spec: OFF => self-skip
    # summary_table is DEFAULT-ON (flag_default_on) — set explicit "0" so an unset default-on flag does not
    # over-demand its marker on this landmark-only log (delenv would leave the default-on path ON).
    monkeypatch.setenv("PG_RENDER_SUMMARY_TABLE", "0")
    log_text = "".join(_LOG_PREFIX + m + "\n" for m in marker_lines)
    rg.assert_activation_markers_fired(log_text)


def test_c_canary_rejects_failopen_landmark(monkeypatch):
    """Wave-3b (Codex P1.1) anti-dark: a FAIL-OPEN landmark lane (positive marker SUPPRESSED, distinct
    ``unavailable_failopen`` degrade marker present) must NOT satisfy the canary — it RAISES. A
    missing/broken/not-recovered expander that adds zero can no longer read as a healthy fire."""
    with pytest.raises(RuntimeError):
        _run_landmark_canary(
            monkeypatch,
            "[activation] landmark_study_expansion: unavailable_failopen (added 0)",
        )


def test_c_canary_rejects_failopen_even_if_stale_positive_present(monkeypatch):
    """Belt-and-suspenders: even if a positive marker co-occurs, the registered ``unavailable_failopen``
    absent_marker fails the canary on the OLD/DEGRADE-MARKER-PRESENT leg (independent of MARKER-ABSENT)."""
    with pytest.raises(RuntimeError):
        _run_landmark_canary(
            monkeypatch,
            "[activation] landmark_study_expansion: expanded_queries=3",
            "[activation] landmark_study_expansion: unavailable_failopen (added 0)",
        )


def test_c_canary_accepts_ran_ok_zero_landmark(monkeypatch):
    """§-1.3 no-threshold: a landmark lane that RAN and legitimately added zero (``expanded_queries=0``,
    no degrade marker) SATISFIES the canary — eligible-yet-zero is ACCEPTED, never gated on a count.
    ``assert_activation_markers_fired`` must NOT raise (no threshold regression)."""
    _run_landmark_canary(  # must not raise
        monkeypatch,
        "[activation] landmark_study_expansion: expanded_queries=0",
    )


def test_c_canary_accepts_ran_ok_nonzero_landmark(monkeypatch):
    """Control: a healthy non-zero landmark fire (``expanded_queries=5``) also passes."""
    _run_landmark_canary(  # must not raise
        monkeypatch,
        "[activation] landmark_study_expansion: expanded_queries=5",
    )


def test_c_producer_failopen_emits_degrade_marker_and_canary_rejects_it(monkeypatch, caplog):
    """END-TO-END RED/GREEN (the P1.1 false-green fix): drive the REAL producer
    ``_plan_expert_facet_queries`` with the landmark planner exploding, CAPTURE what it actually logs,
    and prove (1) it emits the DISTINCT ``unavailable_failopen`` degrade marker, (2) it SUPPRESSES the
    positive ``expanded_queries=`` marker, and (3) feeding that real captured log to the run_gate_b
    canary RAISES. Without the producer fix the fail-open path would log ``expanded_queries=0`` and the
    canary would ACCEPT it — the exact dark false-green this test forbids."""
    import logging as _logging

    from src.polaris_graph.retrieval import (
        expert_facet_planner as efp,
        facet_completeness as fc,
        language_profile as lp,
        sub_entity_query_expander as sqe,
        landmark_study_expander as lse_mod,
    )

    class _Facet:
        def __init__(self, queries):
            self.queries = queries

    monkeypatch.delenv("PG_QGEN_PARALLEL_QUERIES", raising=False)  # serial issue
    monkeypatch.setenv("PG_LANDMARK_EXPANDER", "1")                # additive lane ON
    monkeypatch.setattr(efp, "expert_facet_enabled", lambda: True)
    monkeypatch.setattr(
        efp, "plan_expert_facets",
        lambda _q, _llm: [_Facet(["fq_a", "fq_b"]), _Facet(["fq_c"])],
    )
    monkeypatch.setattr(fc, "facet_completeness_enabled", lambda: False)
    monkeypatch.setattr(lp, "multilingual_enabled", lambda: False)
    monkeypatch.setattr(sqe, "sub_entity_expansion_enabled", lambda: False)

    def _boom(*_a, **_k):
        raise RuntimeError("landmark planner exploded")

    monkeypatch.setattr(lse_mod, "plan_landmark_study_queries", _boom)

    with caplog.at_level(_logging.INFO, logger="polaris_graph.fs_researcher_query_gen"):
        queries, _results = fsq._plan_expert_facet_queries(
            "impact of GenAI on the labor market",
            lambda _p: "",
            _make_retrieve([]),
            max_queries=10,
            retrieve_kwargs={},
        )
    assert queries == ["fq_a", "fq_c", "fq_b"]  # fail-open: baseline frontier still issued (no drop)

    _msgs = [r.getMessage() for r in caplog.records]
    # (1) the distinct degrade marker fired, (2) the positive marker is SUPPRESSED on this path.
    assert any("landmark_study_expansion: unavailable_failopen" in m for m in _msgs), _msgs
    assert not any("landmark_study_expansion: expanded_queries=" in m for m in _msgs), _msgs

    # (3) the REAL captured producer log is REJECTED by the run_gate_b canary (dark lane fails loud).
    monkeypatch.setenv("PG_ACTIVATION_CANARY", "1")
    monkeypatch.delenv("PG_OPENALEX_DATE_FILTER", raising=False)
    landmark_lines = [
        _LOG_PREFIX + m + "\n" for m in _msgs if "landmark_study_expansion" in m
    ]
    with pytest.raises(RuntimeError):
        rg.assert_activation_markers_fired("".join(landmark_lines))


def test_c_enumerate_propagates_llm_exception():
    """Codex P0 (Wave-3b anti-dark false-green — the INNER swallow): a GENUINE ``llm(...)`` failure
    inside the landmark enumerator must PROPAGATE out of the REAL ``plan_landmark_study_queries`` — NOT
    be swallowed to ``[]``. The prior ``_enumerate_landmark_studies`` caught every exception and
    returned ``[]``, so a real planner failure looked identical to a healthy RAN-ok-added-zero: the
    caller read ``[]`` and emitted a positive ``expanded_queries=0`` marker, the fail-open
    ``unavailable_failopen`` degrade marker never fired, and the canary ACCEPTED a dark lane. This drives
    the real (un-monkeypatched) function so the exception must travel through
    ``_enumerate_landmark_studies`` -> ``plan_landmark_study_queries`` to the caller's fail-open handler.
    A legitimately EMPTY reply must still yield ``[]`` (ran-ok-zero preserved — no count-threshold)."""
    def _boom_llm(_prompt: str) -> str:
        raise RuntimeError("landmark planner LLM unavailable")

    with pytest.raises(RuntimeError):
        lse.plan_landmark_study_queries(
            "impact of Generative AI on the labor market", _boom_llm, window_end="2023-06",
        )

    # Control (§-1.3 ran-ok-zero): a legitimately empty model reply is NOT an exception — it returns
    # ``[]`` so the caller reports a healthy ``expanded_queries=0`` (the accepted eligible-yet-zero).
    def _empty_llm(_prompt: str) -> str:
        return "none"

    assert lse.plan_landmark_study_queries("q", _empty_llm, window_end="2023-06") == []


def test_c_real_landmark_llm_failure_producer_emits_degrade_marker(monkeypatch, caplog):
    """END-TO-END RED/GREEN for the INNER-swallow fix: drive the REAL producer
    ``_plan_expert_facet_queries`` with the REAL ``landmark_study_expander`` (NOT monkeypatched) and an
    injected ``llm`` that RAISES on the landmark enumeration call. Prove the ``llm`` exception travels
    through the real ``_enumerate_landmark_studies`` -> ``plan_landmark_study_queries`` -> the caller's
    fail-open handler so (1) the DISTINCT ``unavailable_failopen`` degrade marker fires, (2) the positive
    ``expanded_queries=`` marker is SUPPRESSED, (3) the baseline frontier is STILL issued (fail-open, no
    abort, no drop), and (4) feeding that real captured log to the run_gate_b canary RAISES. With the
    prior inner swallow the lane would have logged ``expanded_queries=0`` and the canary would ACCEPT the
    dark lane — the exact false-green the sibling monkeypatched test could not catch (it stubbed out the
    very function whose inner swallow was the bug)."""
    import logging as _logging

    from src.polaris_graph.retrieval import (
        expert_facet_planner as efp,
        facet_completeness as fc,
        language_profile as lp,
        sub_entity_query_expander as sqe,
    )

    class _Facet:
        def __init__(self, queries):
            self.queries = queries

    monkeypatch.delenv("PG_QGEN_PARALLEL_QUERIES", raising=False)  # serial issue
    monkeypatch.setenv("PG_LANDMARK_EXPANDER", "1")                # additive lane ON
    monkeypatch.setattr(efp, "expert_facet_enabled", lambda: True)
    monkeypatch.setattr(
        efp, "plan_expert_facets",
        lambda _q, _llm: [_Facet(["fq_a", "fq_b"]), _Facet(["fq_c"])],
    )
    monkeypatch.setattr(fc, "facet_completeness_enabled", lambda: False)
    monkeypatch.setattr(lp, "multilingual_enabled", lambda: False)
    monkeypatch.setattr(sqe, "sub_entity_expansion_enabled", lambda: False)
    # NOTE: the REAL landmark_study_expander is used — the ``llm`` (not the module) is what fails, so the
    # exception must propagate through the real inner enumerator to prove the swallow is gone.

    def _boom_llm(_prompt: str) -> str:
        raise RuntimeError("landmark planner LLM unavailable")

    with caplog.at_level(_logging.INFO, logger="polaris_graph.fs_researcher_query_gen"):
        queries, _results = fsq._plan_expert_facet_queries(
            "impact of GenAI on the labor market",
            _boom_llm,
            _make_retrieve([]),
            max_queries=10,
            retrieve_kwargs={},
        )
    assert queries == ["fq_a", "fq_c", "fq_b"]  # fail-open: baseline frontier still issued (no drop)

    _msgs = [r.getMessage() for r in caplog.records]
    # (1) the distinct degrade marker fired, (2) the positive marker is SUPPRESSED on this path.
    assert any("landmark_study_expansion: unavailable_failopen" in m for m in _msgs), _msgs
    assert not any("landmark_study_expansion: expanded_queries=" in m for m in _msgs), _msgs

    # (3) the REAL captured producer log is REJECTED by the run_gate_b canary (dark lane fails loud).
    monkeypatch.setenv("PG_ACTIVATION_CANARY", "1")
    monkeypatch.delenv("PG_OPENALEX_DATE_FILTER", raising=False)
    landmark_lines = [
        _LOG_PREFIX + m + "\n" for m in _msgs if "landmark_study_expansion" in m
    ]
    with pytest.raises(RuntimeError):
        rg.assert_activation_markers_fired("".join(landmark_lines))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q", "-p", "no:cacheprovider"]))
