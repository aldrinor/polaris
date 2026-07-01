"""Beat-both Wave B / WS-13 (#1344) — bounded-PARALLEL retrieval-wall tier-classification.

WS-13 problem: the LLM tier-classification used to run SERIAL, so on a slow judge socket the
per-source calls could not all finish before the retrieval wall — the fetched-but-unclassified
sources (~13 on the observed run) were dropped at ``retrieval_wall_hit=true``. §-1.3 is
WEIGHT-and-CONSOLIDATE, never FILTER-and-DROP: a source that could not be tiered in time must
enter the corpus at the deterministic rules-floor tier (a WEIGHT), NOT be dropped.

The fix (in ``credibility_llm_tiering.classify_sources_llm_tiering``) runs the per-source
tiering BOUNDED-PARALLEL — in-flight requests capped at ``PG_TIER_LLM_WORKERS`` (the
concurrency cap), bounded by a batch wall (``PG_TIER_LLM_BATCH_WALL_SECONDS`` and/or the
caller's ``deadline_monotonic``, tighter wins) — so far more sources get tiered inside the same
wall. A straggler that STILL exceeds the wall keeps its rules-floor tier (present, not dropped).
The default-ON kill-switch ``PG_TIER_LLM_PARALLEL``; OFF reverts to the legacy SERIAL leg,
byte-identical.

These tests are OFFLINE + spend-free: the per-source LLM tiering call is dependency-injected
(a fast deterministic fake), so NO real model / network / judge is used — allowed for a UNIT
test of the concurrency/wall logic. The live-evidence DB is NOT mocked. NO ``unittest.mock``
(CLAUDE.md §9.4) — the injected callers are plain callables. Faithfulness-NEUTRAL: nothing here
touches strict_verify / NLI / D8 / provenance.
"""
from __future__ import annotations

import contextlib
import os
import re
import threading
import time

from src.polaris_graph.retrieval.credibility_llm_tiering import (
    classify_sources_llm_tiering,
)
from src.polaris_graph.retrieval.tier_classifier import (
    ClassificationSignals,
    TierLevel,
)

_N_SOURCES = 13
# Non-top tiers only (T3..T7) so the B2 uncorroborated-top-tier venue cap can never rewrite an
# expected LLM tier (it is additionally disabled via env below). Cycled by index so a REORDER
# under concurrency would surface as a tier/index mismatch (order-independence check).
_TIER_CYCLE = ["T3", "T4", "T5", "T6", "T7"]


@contextlib.contextmanager
def _env(**overrides: str):
    """Set env vars for the block, restoring prior values on exit (hermetic under pytest AND
    a direct ``python file.py`` run — no monkeypatch dependency)."""
    saved: dict[str, str | None] = {k: os.environ.get(k) for k in overrides}
    try:
        for k, v in overrides.items():
            os.environ[k] = v
        yield
    finally:
        for k, prior in saved.items():
            if prior is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = prior


def _sources(n: int = _N_SOURCES, *, slow_index: int | None = None) -> list[ClassificationSignals]:
    """N non-retracted sources. Each URL encodes the tier the fake will return (``tier-T4``)
    so the expected per-source classification is deterministic and index-bound. ``slow_index``
    marks one source ``slow`` so the straggler fake can make it exceed the wall."""
    out: list[ClassificationSignals] = []
    for i in range(n):
        tier = _TIER_CYCLE[i % len(_TIER_CYCLE)]
        marker = "slow" if i == slow_index else "fast"
        out.append(
            ClassificationSignals(
                url=f"https://example.com/{marker}/tier-{tier}/src-{i}",
                title=f"Source {i}",
                fetched_content_length=5000,
            )
        )
    return out


class _TrackingCaller:
    """Deterministic offline LLM-tiering fake that ALSO tracks concurrency.

    Returns the tier encoded in the prompt's URL (``tier-T4`` -> T4). Records the maximum
    number of simultaneously in-flight calls under a lock so a test can assert the bounded
    concurrency cap held (parallel: 1 < max <= cap; serial: max == 1). A small sleep forces
    genuine overlap in the parallel leg. A source whose URL carries ``/slow/`` sleeps long
    enough to exceed a tight wall (straggler)."""

    def __init__(self, *, fast_sleep: float = 0.05, slow_sleep: float = 1.0) -> None:
        self.fast_sleep = fast_sleep
        self.slow_sleep = slow_sleep
        self._lock = threading.Lock()
        self._in_flight = 0
        self.max_in_flight = 0
        self.calls = 0

    def __call__(self, prompt: str) -> str:
        with self._lock:
            self._in_flight += 1
            self.calls += 1
            if self._in_flight > self.max_in_flight:
                self.max_in_flight = self._in_flight
        try:
            time.sleep(self.slow_sleep if "/slow/" in prompt else self.fast_sleep)
            m = re.search(r"tier-(T[1-7])", prompt)
            tier = m.group(1) if m else "T4"
            return f'{{"tier": "{tier}", "rationale": "encoded {tier}"}}'
        finally:
            with self._lock:
                self._in_flight -= 1


# ─────────────────────────────────────────────────────────────────────────────
# 1) Bounded-parallel classifies ALL sources inside the wall, cap never exceeded.
# ─────────────────────────────────────────────────────────────────────────────

def test_parallel_classifies_all_within_wall_and_respects_concurrency_cap() -> None:
    cap = 3
    caller = _TrackingCaller(fast_sleep=0.05)
    sources = _sources()
    # Generous wall (600s env default + no caller deadline): nothing is cut off, so every
    # source is expected to be tiered via the (fake) LLM.
    with _env(
        PG_TIER_LLM_PARALLEL="1",
        PG_TIER_REQUIRE_VENUE_CORROBORATION="0",
        PG_TIER_LLM_DEGRADE_AFTER="0",  # no circuit-breaker; prove pure wall/cap behavior
        PG_TIER_LLM_BATCH_WALL_SECONDS="600",
    ):
        result = classify_sources_llm_tiering(
            sources, call_llm=caller, max_workers=cap,
        )

    # No source dropped — tier is a WEIGHT (§-1.3).
    assert len(result) == _N_SOURCES
    # Every source was tiered via the LLM leg (none fell to the rules-floor) and carries the
    # tier encoded in ITS OWN url — proving order-independent aggregation.
    for i, res in enumerate(result):
        assert res.matched_rules == ["llm_tiering"], (i, res.matched_rules)
        assert res.tier == TierLevel(_TIER_CYCLE[i % len(_TIER_CYCLE)]), (i, res.tier)
    # Bounded concurrency: in-flight NEVER exceeded the cap, and genuine parallelism happened.
    assert caller.max_in_flight <= cap, caller.max_in_flight
    assert caller.max_in_flight >= 2, caller.max_in_flight
    assert caller.calls == _N_SOURCES
    # Honest machine-readable status.
    status = result.tiering_status
    assert status["total"] == _N_SOURCES
    assert status["llm_success_count"] == _N_SOURCES
    assert status["rules_floor_count"] == 0
    assert status["tiering_mode"] == "tiered_via_glm"
    return caller.max_in_flight  # surfaced by the __main__ runner


# ─────────────────────────────────────────────────────────────────────────────
# 2) A straggler past the wall enters at the rules-floor (present, NOT dropped).
# ─────────────────────────────────────────────────────────────────────────────

def test_straggler_past_wall_enters_at_rules_floor_not_dropped() -> None:
    cap = 4
    slow_index = _N_SOURCES - 1
    caller = _TrackingCaller(fast_sleep=0.0, slow_sleep=1.0)
    sources = _sources(slow_index=slow_index)
    # TIGHT wall via the caller deadline: the 12 fast sources finish well inside 0.3s; the one
    # slow source (1.0s) is un-returned at the wall and must keep its deterministic rules-floor.
    with _env(
        PG_TIER_LLM_PARALLEL="1",
        PG_TIER_REQUIRE_VENUE_CORROBORATION="0",
        PG_TIER_LLM_DEGRADE_AFTER="0",  # isolate the WALL path from the circuit-breaker
        PG_TIER_LLM_BATCH_WALL_SECONDS="600",  # keep the env wall loose so the deadline binds
    ):
        result = classify_sources_llm_tiering(
            sources,
            call_llm=caller,
            max_workers=cap,
            deadline_monotonic=time.monotonic() + 0.3,
        )

    # No drop: the straggler is STILL present (§-1.3).
    assert len(result) == _N_SOURCES
    straggler = result[slow_index]
    # It entered at the rules-floor WEIGHT — a real tier, NOT the LLM leg, NOT dropped/None.
    assert straggler.matched_rules != ["llm_tiering"], straggler.matched_rules
    assert isinstance(straggler.tier, TierLevel)
    # The 12 fast sources were tiered via the LLM leg.
    for i in range(_N_SOURCES):
        if i == slow_index:
            continue
        assert result[i].matched_rules == ["llm_tiering"], (i, result[i].matched_rules)
    # Status: 12 via GLM, 1 at the rules-floor -> partial (never a false 'tiered_via_glm').
    status = result.tiering_status
    assert status["total"] == _N_SOURCES
    assert status["llm_success_count"] == _N_SOURCES - 1
    assert status["rules_floor_count"] == 1
    assert status["tiering_mode"] == "partial"
    return caller.max_in_flight


# ─────────────────────────────────────────────────────────────────────────────
# 3) Kill-switch OFF -> serial leg, byte-identical classifications & status.
# ─────────────────────────────────────────────────────────────────────────────

def _run(parallel: str, cap: int) -> tuple[list, dict, int]:
    caller = _TrackingCaller(fast_sleep=0.05)
    sources = _sources()
    with _env(
        PG_TIER_LLM_PARALLEL=parallel,
        PG_TIER_REQUIRE_VENUE_CORROBORATION="0",
        PG_TIER_LLM_DEGRADE_AFTER="0",
        PG_TIER_LLM_BATCH_WALL_SECONDS="600",
    ):
        result = classify_sources_llm_tiering(sources, call_llm=caller, max_workers=cap)
    return list(result), dict(result.tiering_status), caller.max_in_flight


def test_killswitch_off_serial_is_byte_identical_to_parallel() -> None:
    par_out, par_status, par_max = _run("1", cap=3)   # default-ON bounded-parallel
    ser_out, ser_status, ser_max = _run("0", cap=3)   # OFF -> legacy serial

    # Same per-source classification, field-by-field — byte-identical outputs.
    assert len(par_out) == len(ser_out) == _N_SOURCES
    for i, (p, s) in enumerate(zip(par_out, ser_out)):
        assert p.tier.value == s.tier.value, (i, p.tier, s.tier)
        assert p.confidence == s.confidence, (i, p.confidence, s.confidence)
        assert p.matched_rules == s.matched_rules, (i, p.matched_rules, s.matched_rules)
        assert p.reasons == s.reasons, (i, p.reasons, s.reasons)
        assert p.signals_used == s.signals_used, (i, p.signals_used, s.signals_used)
    # Same honest machine-readable status.
    assert par_status == ser_status
    # The serial leg used NO concurrency (proves the OFF path is genuinely serial); the
    # parallel leg genuinely overlapped (proves the ON path is genuinely parallel).
    assert ser_max == 1, ser_max
    assert par_max >= 2, par_max
    return par_max, ser_max


if __name__ == "__main__":
    m1 = test_parallel_classifies_all_within_wall_and_respects_concurrency_cap()
    print(f"[1] parallel-classifies-all: PASS  (observed max in-flight = {m1}, cap = 3)")
    m2 = test_straggler_past_wall_enters_at_rules_floor_not_dropped()
    print(f"[2] straggler-degrades-not-drops: PASS  (observed max in-flight = {m2}, cap = 4)")
    par_max, ser_max = test_killswitch_off_serial_is_byte_identical_to_parallel()
    print(
        f"[3] killswitch-off-byte-identical: PASS  "
        f"(parallel max in-flight = {par_max}, serial max in-flight = {ser_max})"
    )
    print("ALL WS-13 TESTS PASSED")
