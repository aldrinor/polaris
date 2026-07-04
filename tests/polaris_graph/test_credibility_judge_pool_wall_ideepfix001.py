"""I-deepfix-001 — credibility-pass HANG backstop (the pool-JOIN wall).

Root: ``credibility_skill.score_source_credibility`` fans the per-source judge out over a ThreadPool and
JOINS with ``concurrent.futures.as_completed(futures)``. Each worker carries a ~300s per-call deadline, but
the JOIN had NO outer bound — under a 429 / empty-provider-window storm every worker re-enters retry+backoff
and the whole pass grinds past the sweep wall (tonight's live faulthandler: credibility_skill as_completed
blocked, main asyncio loop parked). The fix adds a HARD wall on the join
(``PG_CREDIBILITY_JUDGE_POOL_WALL_S``): on the wall it STOPS joining, fills every un-scored source with its
deterministic priors (``judge_error=True`` -> credibility_pass LABELS it ``credibility_unscored``), and
RETURNS — self-terminating, independent of the event loop, so no stalled judge can ever freeze the run.

Codex diff-gate iter1 P0 (daemon-thread masking): the ORIGINAL regression ran the whole pass from a DAEMON
outer thread, so ``t.is_alive()`` flipped False simply because the daemon target returned — a signal that
would NOT hold for the main (non-daemon) thread in production, and it never proved the orphaned POOL workers
terminate. This rewrite runs the pass from a NON-DAEMON thread (exactly like production) and blocks the judge
on a ``threading.Event`` instead of a fixed sleep, so it can assert the two real properties:

  1. ANTI-HANG: ``score_source_credibility`` RETURNS within the wall WHILE its worker threads are STILL
     BLOCKED (alive) — the pass does not depend on a stalled worker finishing (the exact production hang).
  2. BOUNDED TERMINATION: once the workers are released they ALL exit promptly — a stalled worker can never
     keep the real (non-daemon) process alive indefinitely. (In production every real worker call is also
     bounded by ``_post_with_total_deadline`` — a 300s hard socket-close wall in the OpenRouter caller — so
     the orphan is reaped even without a release; that per-call bound is covered by that module's own tests.)

OFFLINE / $0 / no GPU / no network. NO ``unittest.mock`` (CLAUDE.md §9.4). The advisory pass is
faithfulness-neutral (strict_verify / NLI / 4-role D8 / span-grounding untouched); a priors-filled source is
a disclosed gap, never a silent drop.
"""
from __future__ import annotations

import threading
import time

from src.polaris_graph.authority.credibility_skill import score_source_credibility


def _rows(specs):
    """Minimal credibility rows: an evidence_id + a real deterministic authority prior + a signal so the
    source is not flagged LOW/thin (keeps the priors weight == authority_score for a clean assertion)."""
    return [
        {
            "evidence_id": eid,
            "authority_score": auth,
            "authority_confidence": "HIGH",
            "source_class": "gov",
            "signal_scores": {"peer_review": 1.0},
        }
        for eid, auth in specs
    ]


def _run_in_thread(fn, join_timeout, *, daemon=False):
    """Run ``fn`` in a thread and report whether it was still running after ``join_timeout``.

    ``daemon=False`` by default so the pass runs under the SAME thread-daemon status as production (the
    main thread). A non-daemon outer thread means ``alive`` genuinely reflects whether the CALL returned,
    not a daemon shortcut."""
    box = {}

    def _target():
        box["result"] = fn()

    t = threading.Thread(target=_target, daemon=daemon)
    started = time.monotonic()
    t.start()
    t.join(timeout=join_timeout)
    box["elapsed"] = time.monotonic() - started
    box["alive"] = t.is_alive()
    box["thread"] = t
    return box


def _pool_worker_threads(exclude_idents):
    """The credibility ThreadPool's worker threads currently alive (named ``ThreadPoolExecutor*``) that did
    NOT exist before the pass started. Scopes the assertion to THIS pass's workers."""
    return [
        t for t in threading.enumerate()
        if t.ident not in exclude_idents and (t.name or "").startswith("ThreadPoolExecutor")
    ]


def test_pool_wall_returns_before_blocked_workers_then_workers_terminate(monkeypatch):
    """The wall fires WHILE every judge worker is still blocked: the pass returns priors for all sources
    within the wall (anti-hang, production-realistic non-daemon thread), and once the workers are released
    they all terminate (bounded — a stall can never keep the real process alive)."""
    monkeypatch.setenv("PG_CREDIBILITY_JUDGE_CONCURRENCY", "4")
    monkeypatch.setenv("PG_CREDIBILITY_JUDGE_POOL_WALL_S", "0.3")
    rows = _rows([("ev0", 0.7), ("ev1", 0.7), ("ev2", 0.7), ("ev3", 0.7), ("ev4", 0.7), ("ev5", 0.7)])

    release = threading.Event()
    entered = threading.Event()

    def _blocked_judge(research_question, payload):
        # A 429-storm worker wedged in retry+backoff: blocks PAST the wall. Released by the test only
        # AFTER it verifies the pass returned. Bounded so a forgotten release can never wedge the suite.
        entered.set()
        release.wait(timeout=30.0)
        return {"reliability_score": 0.95, "relevance_score": 1.0, "rationale": "late", "signals_cited": []}

    before = {t.ident for t in threading.enumerate()}
    box = _run_in_thread(
        lambda: score_source_credibility("q", rows, judge=_blocked_judge),
        join_timeout=3.0, daemon=False,
    )
    try:
        assert entered.wait(timeout=3.0), "judge workers never started"
        assert not box["alive"], "score_source_credibility HUNG past the pool wall (the bug this fix closes)"
        res = box["result"]
        assert len(res) == 6, "every source must still be present (fail-closed: never a silent drop)"
        assert all(j.judge_error for j in res), "stalled sources must be LABELED judge_error (credibility_unscored)"
        # priors-only weight == clamp01(authority_score) == 0.7 (the honest deterministic fallback).
        assert all(abs(j.credibility_weight - 0.7) < 1e-9 for j in res)
        # The pass RETURNED while its workers were STILL BLOCKED and alive — proving it does not wait on
        # a stalled worker. (This is the property the old daemon-thread test could not show.)
        orphans = _pool_worker_threads(before)
        assert orphans, "expected the credibility pool workers to still be ALIVE (blocked) after the wall returned"
    finally:
        release.set()  # unblock the orphaned workers so they terminate (and the suite exits cleanly)
    # BOUNDED TERMINATION: once released, every orphaned worker must exit promptly — a stalled worker can
    # never keep the real (non-daemon) process alive indefinitely.
    for t in _pool_worker_threads(before):
        t.join(timeout=5.0)
    assert not _pool_worker_threads(before), (
        "orphaned credibility pool workers failed to terminate after release — would block process exit"
    )


def test_pool_wall_keeps_completed_verdicts_and_fills_only_blocked(monkeypatch):
    """A MIX: fast sources keep their REAL judgment (judge_error=False); only the blocked ones fall back
    to priors — the wall degrades the minimum, never the whole pass."""
    monkeypatch.setenv("PG_CREDIBILITY_JUDGE_CONCURRENCY", "4")
    monkeypatch.setenv("PG_CREDIBILITY_JUDGE_POOL_WALL_S", "0.5")
    rows = _rows([("fast0", 0.6), ("slow0", 0.7), ("fast1", 0.6), ("slow1", 0.7)])

    release = threading.Event()

    def _mixed_judge(research_question, payload):
        if str(payload.get("evidence_id", "")).startswith("slow"):
            release.wait(timeout=30.0)  # blocks PAST the 0.5s wall until the test releases it
        return {"reliability_score": 0.9, "relevance_score": 1.0, "rationale": "x", "signals_cited": []}

    before = {t.ident for t in threading.enumerate()}
    box = _run_in_thread(
        lambda: score_source_credibility("q", rows, judge=_mixed_judge),
        join_timeout=3.0, daemon=False,
    )
    try:
        assert not box["alive"], "the mixed pass HUNG past the pool wall"
        by_id = {j.evidence_id: j for j in box["result"]}
        assert len(by_id) == 4
        assert not by_id["fast0"].judge_error and not by_id["fast1"].judge_error, "fast verdicts must survive"
        assert by_id["slow0"].judge_error and by_id["slow1"].judge_error, "blocked sources must fall back to priors"
        # the fast sources carry the REAL judged weight (0.9 * 1.0), not the priors fallback (0.6).
        assert abs(by_id["fast0"].credibility_weight - 0.9) < 1e-9
    finally:
        release.set()
    for t in _pool_worker_threads(before):
        t.join(timeout=5.0)


def test_healthy_pass_is_unaffected_by_the_wall(monkeypatch):
    """A fast judge completes well inside the generous wall -> every source carries its REAL verdict and
    NONE is judge_error — the wall is a backstop, byte-identical on the healthy path."""
    monkeypatch.setenv("PG_CREDIBILITY_JUDGE_CONCURRENCY", "4")
    monkeypatch.delenv("PG_CREDIBILITY_JUDGE_POOL_WALL_S", raising=False)  # default 3600s

    def _fast_judge(research_question, payload):
        return {"reliability_score": 0.85, "relevance_score": 1.0, "rationale": "ok", "signals_cited": []}

    rows = _rows([("a", 0.6), ("b", 0.6), ("c", 0.6)])
    res = score_source_credibility("q", rows, judge=_fast_judge)
    assert len(res) == 3
    assert not any(j.judge_error for j in res)
    assert all(abs(j.credibility_weight - 0.85) < 1e-9 for j in res)
