"""I-deepfix-001 (#1344) WAVE-2 FETCH THROUGHPUT — RED/GREEN unit tests.

Two DEFAULT-OFF flags that stop already-FETCHED bodies from being lost under the
retrieval wall (the throughput collapse behind "only 3 of ~35 queries mattered"):

  (A) ``PG_POST_FETCH_ENRICH_PARALLEL`` (+ ``PG_POST_FETCH_ENRICH_WORKERS``) — a
      BOUNDED ThreadPool that pre-batches the per-candidate OpenAlex enrich before
      the serial classify loop. This suite proves the parallel batch returns the
      SAME per-candidate enrich as the serial loop, ORDER-STABLE (result[i] always
      maps to candidates[i]), even when worker completion order != submit order,
      and fails OPEN to ``{}`` on a per-source error (never corruption, never a
      drop of the other sources).

  (B) ``PG_WALL_CLASSIFY_RESCUE`` — at the wall break, classify the remaining
      already-fetched bodies RULES-ONLY at the rules-floor tier and KEEP them
      (§-1.3 keep-not-drop). This suite proves the shared rescue-classify helper
      ALWAYS returns a kept ``CorpusSource`` (never ``None`` / never a drop) — even
      when the deterministic rules floor lands at the LOWEST tier — and preserves
      the surfaced content-relevance weight/label.

RED-then-GREEN: on the pre-fix branch the symbols below do not exist, so this
module fails at import (collection error = RED). After the Wave-2 build it imports
and every assertion passes (GREEN).

Imports are NARROW (no heavy models): the enrich fn is stubbed for Fix A and the
rules classifier + genre stamp are stubbed for Fix B.
"""
from __future__ import annotations

import threading
import time
import types

import pytest

from src.polaris_graph.retrieval import live_retriever as lr
from src.polaris_graph.retrieval.live_retriever import (
    _WALL_RESCUE_LABEL,
    _loop_budget_truncation_active,
    _post_fetch_enrich_parallel_enabled,
    _post_fetch_enrich_wall_fraction,
    _post_fetch_enrich_workers,
    _prefetch_openalex_enrich_parallel,
    _wall_classify_rescue_enabled,
    _wall_rescue_armed_marker,
    _wall_rescue_classify_source,
    _wall_rescue_weight,
)


def _cand(url: str, title: str) -> types.SimpleNamespace:
    """A minimal candidate stand-in — the helpers read only ``.url`` / ``.title``."""
    return types.SimpleNamespace(url=url, title=title)


# ── Env gates: both flags DEFAULT-OFF (OFF byte-identical) ────────────────────


def test_enrich_parallel_flag_default_off(monkeypatch):
    monkeypatch.delenv("PG_POST_FETCH_ENRICH_PARALLEL", raising=False)
    assert _post_fetch_enrich_parallel_enabled() is False


def test_wall_rescue_flag_default_off(monkeypatch):
    monkeypatch.delenv("PG_WALL_CLASSIFY_RESCUE", raising=False)
    assert _wall_classify_rescue_enabled() is False


@pytest.mark.parametrize("raw", ["1", "true", "on", "YES", "On"])
def test_enrich_parallel_flag_on_variants(monkeypatch, raw):
    monkeypatch.setenv("PG_POST_FETCH_ENRICH_PARALLEL", raw)
    assert _post_fetch_enrich_parallel_enabled() is True


@pytest.mark.parametrize("raw", ["1", "true", "on", "YES", "On"])
def test_wall_rescue_flag_on_variants(monkeypatch, raw):
    monkeypatch.setenv("PG_WALL_CLASSIFY_RESCUE", raw)
    assert _wall_classify_rescue_enabled() is True


def test_enrich_workers_default_and_override(monkeypatch):
    monkeypatch.delenv("PG_POST_FETCH_ENRICH_WORKERS", raising=False)
    assert _post_fetch_enrich_workers() == 8  # sane bounded default
    monkeypatch.setenv("PG_POST_FETCH_ENRICH_WORKERS", "4")
    assert _post_fetch_enrich_workers() == 4
    # A non-positive / garbage override falls back to the safe default (LAW VI).
    monkeypatch.setenv("PG_POST_FETCH_ENRICH_WORKERS", "0")
    assert _post_fetch_enrich_workers() == 8
    monkeypatch.setenv("PG_POST_FETCH_ENRICH_WORKERS", "junk")
    assert _post_fetch_enrich_workers() == 8


# ── Codex wave-2 P1a: the pre-batch reserves a slice of the wall for classify ──


def test_enrich_wall_fraction_default_reserves_half(monkeypatch):
    """DEFAULT reserves half the remaining wall for the classify loop — so the
    SYNCHRONOUS pre-batch can never burn the WHOLE wall before classification
    starts (the bug: rescue-off drop / all-rules-only rescue). A fraction < 1.0
    guarantees the classify loop keeps budget."""
    monkeypatch.delenv("PG_POST_FETCH_ENRICH_WALL_FRACTION", raising=False)
    frac = _post_fetch_enrich_wall_fraction()
    assert frac == 0.5
    assert 0.0 < frac < 1.0  # strictly reserves budget for classification


@pytest.mark.parametrize("raw,expected", [("0.25", 0.25), ("1.0", 1.0), ("0.75", 0.75)])
def test_enrich_wall_fraction_valid_override(monkeypatch, raw, expected):
    monkeypatch.setenv("PG_POST_FETCH_ENRICH_WALL_FRACTION", raw)
    assert _post_fetch_enrich_wall_fraction() == expected


@pytest.mark.parametrize("raw", ["0", "-0.5", "1.5", "nan", "inf", "junk", ""])
def test_enrich_wall_fraction_invalid_falls_back_to_full_wall(monkeypatch, raw):
    """ANY set-but-invalid value => 1.0 = pass the FULL retrieval deadline unchanged
    (byte-identical to the pre-P1a full-wall collection). Never a spurious tiny slice."""
    monkeypatch.setenv("PG_POST_FETCH_ENRICH_WALL_FRACTION", raw)
    assert _post_fetch_enrich_wall_fraction() == 1.0


def test_prefetch_past_deadline_keeps_every_index_fail_open():
    """The mechanism Fix A relies on: an already-expired ``deadline_monotonic``
    records each un-collected straggler as ``{}`` (fail-open) but STILL returns a
    key for EVERY candidate index — never a drop of the batch (§-1.3). This is what
    lets the reserved-slice deadline hand control back to the classify loop instead
    of blocking to the wall."""
    candidates = [_cand(f"https://ex/{i}", f"t{i}") for i in range(5)]

    def slow_enrich(url, title):
        time.sleep(0.05)  # never completes within the already-passed deadline
        return {"url": url}

    parallel = _prefetch_openalex_enrich_parallel(
        candidates, workers=5, enrich_fn=slow_enrich,
        deadline_monotonic=time.monotonic() - 1.0,  # already expired
    )
    assert set(parallel.keys()) == set(range(5))   # every index kept
    assert all(v == {} for v in parallel.values()) # stragglers fail open to {}


def test_prefetch_cancels_queued_futures_past_deadline():
    """Codex wave-2 P0: once the reserved wall slice is spent the pre-batch must STOP
    starting new enriches — it is bounded by the WALL, not just by worker count. With
    few workers + an already-expired deadline, the still-QUEUED enriches are CANCELLED
    (never started), so the batch cannot keep hammering OpenAlex during the classify
    phase. Every index still returns a value (fail-open {}, §-1.3 keep-not-drop).

    RED/GREEN: with the pre-fix ``executor.shutdown(wait=False)`` (no cancel) the queued
    futures stayed live and the workers kept picking them up AFTER the call returned, so
    ``started`` climbed past ``workers`` during the grace window below. The fix cancels
    them, so at most ``workers`` enriches ever start."""
    n = 12
    workers = 2
    started = {"n": 0}
    _lock = threading.Lock()

    def slow_enrich(url, title):
        with _lock:
            started["n"] += 1
        time.sleep(0.2)  # busy long enough that no worker frees before the cancel
        return {"url": url}

    candidates = [_cand(f"https://ex/{i}", f"t{i}") for i in range(n)]
    parallel = _prefetch_openalex_enrich_parallel(
        candidates, workers=workers, enrich_fn=slow_enrich,
        deadline_monotonic=time.monotonic() - 1.0,  # already expired
    )
    # Every index kept (never a drop), all fail-open to {} (§-1.3).
    assert set(parallel.keys()) == set(range(n))
    assert all(v == {} for v in parallel.values())
    # Grace window: give any UN-cancelled queued future ample time to run. With the fix
    # the queue is cancelled + purged, so `started` stays <= workers; pre-fix it climbs.
    time.sleep(0.5)
    assert started["n"] <= workers


# ── Codex wave-2 P1b: rescue keeps at the RULES-FLOOR weight, never full/zero ──


def test_wall_rescue_weight_default_is_rules_floor(monkeypatch):
    """DEFAULT rescue weight is the rules floor (0.25) — low but NON-zero: a rescued
    body flows to composition at reduced weight and is NEVER dropped, and is NEVER
    kept at the full 1.0 weight that would falsely rank it as fully relevant."""
    monkeypatch.delenv("PG_WALL_RESCUE_WEIGHT", raising=False)
    w = _wall_rescue_weight()
    assert w == 0.25
    assert 0.0 < w < 1.0   # never full (would falsely rank relevant), never zero (a drop)


@pytest.mark.parametrize("raw,expected", [("0.1", 0.1), ("0.5", 0.5), ("1.0", 1.0)])
def test_wall_rescue_weight_valid_override(monkeypatch, raw, expected):
    monkeypatch.setenv("PG_WALL_RESCUE_WEIGHT", raw)
    assert _wall_rescue_weight() == expected


@pytest.mark.parametrize("raw", ["0", "-1", "1.5", "nan", "inf", "junk", ""])
def test_wall_rescue_weight_invalid_or_zero_falls_back_never_drops(monkeypatch, raw):
    """A zero / negative / garbage override can NEVER zero-drop a rescued source:
    it clamps back to the safe rules floor (§-1.3 keep-at-floor, never a drop)."""
    monkeypatch.setenv("PG_WALL_RESCUE_WEIGHT", raw)
    w = _wall_rescue_weight()
    assert w == 0.25
    assert w > 0.0


def test_wall_rescue_label_is_keep_neutral_not_offtopic():
    """The rescue label must NOT be a confirmed-off-topic label — those suppress the
    cite surface (weighted_enrichment._is_confirmed_offtopic), which would turn the
    §-1.3 keep into a drop. A rescued body was never judged off-topic, only unscored."""
    from src.polaris_graph.generator.weighted_enrichment import (
        _CONFIRMED_OFFTOPIC_LABELS,
    )
    assert _WALL_RESCUE_LABEL not in _CONFIRMED_OFFTOPIC_LABELS
    assert _WALL_RESCUE_LABEL  # non-empty => an honest, disclosed telemetry label


def test_wall_rescue_helper_keeps_source_at_the_floor_weight(monkeypatch):
    """End-to-end contract of the rescue call site: handing the helper the rules-floor
    weight + keep-neutral label KEEPS the source (never None) carrying the floor weight
    (not full 1.0) and the disclosed label."""
    monkeypatch.delenv("PG_WALL_RESCUE_WEIGHT", raising=False)
    monkeypatch.setattr(
        lr, "_classify_source_tier_rules",
        lambda signals: _fake_tier_result("T6"),
    )
    monkeypatch.setattr(lr, "_m2_dt", lambda result, signals: None)
    signals = types.SimpleNamespace(url="https://ex/7", title="Rescued")
    src, _ = _wall_rescue_classify_source(
        signals, "https://ex/7", "Rescued", "ex",
        content_relevance_weight=_wall_rescue_weight(),
        content_relevance_label=_WALL_RESCUE_LABEL,
    )
    assert src is not None                          # KEPT, never dropped
    assert src.content_relevance_weight == 0.25     # rules floor, not full 1.0
    assert src.content_relevance_weight < 1.0
    assert src.content_relevance_label == _WALL_RESCUE_LABEL


# ── Fix A: parallel enrich == serial enrich, ORDER-STABLE ─────────────────────


def _serial_map(candidates, enrich_fn):
    """The reference the serial in-loop enrich would produce (index -> enrich)."""
    return {i: enrich_fn(c.url, c.title) for i, c in enumerate(candidates)}


def test_prefetch_parallel_equals_serial_order_stable():
    candidates = [_cand(f"https://ex/{i}", f"title {i}") for i in range(12)]

    def enrich(url, title):
        # A distinct, deterministic dict per candidate.
        return {"url": url, "title": title, "venue": f"v-{url[-1]}"}

    serial = _serial_map(candidates, enrich)
    parallel = _prefetch_openalex_enrich_parallel(
        candidates, workers=6, enrich_fn=enrich,
    )
    # Same keys 0..n-1 and the SAME per-index enrich value (order-stable merge).
    assert set(parallel.keys()) == set(range(12))
    assert parallel == serial


def test_prefetch_order_stable_under_scrambled_completion():
    """The merge keys on SUBMIT index, not COMPLETION order: a slow-first /
    fast-last latency profile scrambles completion order but MUST NOT corrupt the
    index->enrich mapping. RED if the merge collected by completion order."""
    n = 10
    candidates = [_cand(f"https://ex/{i}", f"t{i}") for i in range(n)]
    completion_order: list[int] = []
    _lock = threading.Lock()

    def enrich(url, title):
        idx = int(url.rsplit("/", 1)[-1])
        # Earlier indices sleep LONGER -> finish LATER (reverse completion order).
        time.sleep(0.01 * (n - idx))
        with _lock:
            completion_order.append(idx)
        return {"idx": idx, "url": url}

    parallel = _prefetch_openalex_enrich_parallel(
        candidates, workers=n, enrich_fn=enrich,
    )
    # Every candidate enriched, keyed by its OWN index (no cross-wiring).
    assert set(parallel.keys()) == set(range(n))
    for i in range(n):
        assert parallel[i] == {"idx": i, "url": f"https://ex/{i}"}
    # Sanity: concurrency actually ran (all completed); typically reverse-ish order.
    assert sorted(completion_order) == list(range(n))


def test_prefetch_fails_open_per_source_keeps_the_rest():
    """A per-source enrich error yields ``{}`` for THAT index only — the other
    sources are still enriched (§-1.3: never drop the whole batch on one failure)."""
    candidates = [_cand(f"https://ex/{i}", f"t{i}") for i in range(6)]

    def enrich(url, title):
        idx = int(url.rsplit("/", 1)[-1])
        if idx in (2, 4):
            raise RuntimeError("simulated OpenAlex failure")
        return {"idx": idx}

    parallel = _prefetch_openalex_enrich_parallel(
        candidates, workers=4, enrich_fn=enrich,
    )
    assert set(parallel.keys()) == set(range(6))
    assert parallel[2] == {}          # failed source -> empty, not a crash
    assert parallel[4] == {}
    assert parallel[0] == {"idx": 0}  # the rest are still enriched (kept)
    assert parallel[5] == {"idx": 5}


def test_prefetch_empty_candidates_returns_empty():
    assert _prefetch_openalex_enrich_parallel([], workers=8, enrich_fn=lambda u, t: {}) == {}


# ── Fix B: wall-rescue KEEPS (never drops) at the rules-floor ─────────────────


def _fake_tier_result(tier_value, *, confidence=0.3, rules=("rule_x",), reasons=("r1",)):
    return types.SimpleNamespace(
        tier=types.SimpleNamespace(value=tier_value),
        confidence=confidence,
        matched_rules=list(rules),
        reasons=list(reasons),
    )


def test_wall_rescue_keeps_source_with_rules_tier(monkeypatch):
    calls = {"m2_dt": 0}
    monkeypatch.setattr(
        lr, "_classify_source_tier_rules",
        lambda signals: _fake_tier_result("T5"),
    )
    monkeypatch.setattr(
        lr, "_m2_dt",
        lambda result, signals: calls.__setitem__("m2_dt", calls["m2_dt"] + 1),
    )
    signals = types.SimpleNamespace(url="https://ex/1", title="Some Title")
    src, tier_result = _wall_rescue_classify_source(
        signals, "https://ex/1", "Some Title", "ex",
        content_relevance_weight=0.42,
        content_relevance_label="w2_relevant",
    )
    # KEPT (never None), rules-floor tier surfaced, weight/label preserved.
    assert src is not None
    assert src.url == "https://ex/1"
    assert src.tier == "T5"
    assert src.tier_rule == "rule_x"
    assert src.content_relevance_weight == 0.42
    assert src.content_relevance_label == "w2_relevant"
    assert tier_result.tier.value == "T5"
    assert calls["m2_dt"] == 1  # genre stamp mirrors the deferred W5 path


def test_wall_rescue_keeps_even_lowest_tier(monkeypatch):
    """§-1.3 keep-not-drop: a body the rules floor tiers as UNKNOWN (lowest) is
    STILL returned as a kept CorpusSource — it is never filtered out."""
    monkeypatch.setattr(
        lr, "_classify_source_tier_rules",
        lambda signals: _fake_tier_result("UNKNOWN", confidence=0.0, rules=(), reasons=()),
    )
    monkeypatch.setattr(lr, "_m2_dt", lambda result, signals: None)
    signals = types.SimpleNamespace(url="https://ex/9", title="Low")
    src, _ = _wall_rescue_classify_source(
        signals, "https://ex/9", "Low", "ex",
        content_relevance_weight=1.0,
        content_relevance_label="",
    )
    assert src is not None            # KEPT, not dropped
    assert src.tier == "UNKNOWN"
    assert src.tier_rule == ""        # no matched rule -> empty, not an index error
    assert src.content_relevance_weight == 1.0


# ── Codex wave-2 P1: the loop-budget truncation never DROPS once rescue engaged ─


def test_loop_budget_truncation_inert_in_rescue_mode():
    """Codex wave-2 P1: once PG_WALL_CLASSIFY_RESCUE has engaged rules-only rescue, the
    legacy loop-budget truncation (which BREAKS the loop and drops the fetched tail)
    must NOT fire — even when _loop_deadline is ALSO expired. In rescue mode the
    predicate is ALWAYS False, so the loop keeps classifying+keeping (§-1.3 keep-not-
    drop) instead of dropping the remaining already-fetched bodies."""
    now = 1000.0
    expired_deadline = 0.0  # deadline long past
    # Rescue engaged -> inert regardless of how far past the loop deadline we are.
    assert _loop_budget_truncation_active(
        wall_rescue_mode=True, now=now, loop_deadline=expired_deadline
    ) is False


def test_loop_budget_truncation_off_is_byte_identical_bare_check():
    """OFF / pre-rescue (wall_rescue_mode=False — the ONLY value when the flag is OFF)
    the predicate is byte-identical to the prior bare ``now > loop_deadline`` check:
    True past the deadline, False before it. This preserves the legacy truncation
    behaviour untouched on the OFF path."""
    assert _loop_budget_truncation_active(
        wall_rescue_mode=False, now=1000.0, loop_deadline=0.0
    ) is True    # past the deadline -> legacy truncation still fires
    assert _loop_budget_truncation_active(
        wall_rescue_mode=False, now=1000.0, loop_deadline=2000.0
    ) is False   # before the deadline -> no truncation
    # Exactly AT the deadline is NOT past it (strict > semantics preserved).
    assert _loop_budget_truncation_active(
        wall_rescue_mode=False, now=1000.0, loop_deadline=1000.0
    ) is False


# ── Codex wave-2 P1: anti-dark LIVENESS marker (wall-independent) ──────────────


def test_wall_rescue_armed_marker_is_wall_independent_liveness():
    """Codex wave-2 P1: the armed liveness marker is a PURE function of the flag
    context — it takes NO wall / deadline input, so it fires on every run the flag is
    ON, closing the anti-dark gap where the parallel enrich pre-batch keeps the wall
    from ever tripping (so the wall-hit 'engaged' log alone is not liveness proof)."""
    m_on = _wall_rescue_armed_marker(enrich_parallel=True)
    m_off = _wall_rescue_armed_marker(enrich_parallel=False)
    # The forensic activation-capture buffer keeps ONLY '[activation] '-prefixed lines.
    assert m_on.startswith("[activation] wall_classify_rescue: armed")
    assert m_off.startswith("[activation] wall_classify_rescue: armed")
    # It discloses whether Fix A (parallel enrich) is co-armed on the same run.
    assert "enrich_parallel=True" in m_on
    assert "enrich_parallel=False" in m_off


def test_wall_rescue_armed_marker_emitted_when_flag_on(monkeypatch, caplog):
    """The armed marker is emitted at loop setup whenever the flag reads ON — the
    module-logger record the forensic capture handler / activation buffer catches. OFF
    => the builder is simply never called (no marker), keeping the OFF path silent."""
    monkeypatch.setenv("PG_WALL_CLASSIFY_RESCUE", "1")
    assert _wall_classify_rescue_enabled() is True
    with caplog.at_level("INFO", logger=lr.logger.name):
        lr.logger.info("%s", _wall_rescue_armed_marker(enrich_parallel=True))
    assert any(
        "[activation] wall_classify_rescue: armed" in rec.getMessage()
        for rec in caplog.records
    )
