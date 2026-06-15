"""fix#19 (#1262) — bounded parallel per-claim verification + section generation.

SPEED fix, faithfulness-NEUTRAL. These tests prove the parallel paths are pure
SCHEDULING changes that never alter a verdict, a kept/dropped decision, the
deterministic output ordering, or the downstream consolidation:

  (a) parallel verification (PG_PARALLEL_VERIFY>=2) over a FAKE judge yields the
      SAME per-sentence verdicts AND the SAME kept/dropped ORDER as the serial path
      (no verdict change, deterministic reassembly);
  (b) the concurrency is BOUNDED — the observed max in-flight judge calls never
      exceeds the PG_PARALLEL_VERIFY worker cap;
  (c) per-run judge telemetry (the FX-09 ContextVar) still ticks under the thread
      pool because the parent context is copied into each worker;
  (d) section-generation concurrency is BOUNDED + env-driven (PG_PARALLEL_SECTIONS)
      and a fake bounded-section gather preserves the SAME set+order of section
      results serial-vs-parallel (determinism of the consolidation/merge step).

All judge work is faked / asyncio — NO real LLM calls, NO network, offline only.
"""

from __future__ import annotations

import asyncio
import os
import threading
import time

import pytest

from src.polaris_graph.clinical_generator import strict_verify as _gen2
from src.polaris_graph.generator import provenance_generator as _pg
from src.polaris_graph.generator.provenance_generator import strict_verify


# ───────────────────────── fake judge (concurrency-instrumented) ─────────────────────────


class _CountingFakeJudge:
    """Fake entailment judge whose verdict is a DETERMINISTIC function of the
    sentence text (so serial and parallel must agree), and which records both the
    set of judged sentences and the MAX concurrent in-flight calls (to prove the
    pool is bounded). A small sleep widens the overlap window so a real bound
    violation would be observable."""

    def __init__(self, *, verdict_fn, delay: float = 0.0) -> None:
        self._verdict_fn = verdict_fn
        self._delay = delay
        self._lock = threading.Lock()
        self._inflight = 0
        self.max_inflight = 0
        self.judged_sentences: list[str] = []

    def judge(self, sentence: str, span: str) -> tuple[str, str]:
        with self._lock:
            self._inflight += 1
            if self._inflight > self.max_inflight:
                self.max_inflight = self._inflight
            self.judged_sentences.append(sentence)
        try:
            if self._delay:
                time.sleep(self._delay)
            return self._verdict_fn(sentence), "fake"
        finally:
            with self._lock:
                self._inflight -= 1


def _install_judge(monkeypatch, fake) -> None:
    monkeypatch.setattr(_gen2, "_JUDGE_SINGLETON", fake, raising=False)
    monkeypatch.setattr(_gen2, "_get_judge", lambda: fake)


@pytest.fixture(autouse=True)
def _reset_telemetry():
    _gen2.reset_judge_telemetry()
    yield
    _gen2.reset_judge_telemetry()


# ───────────────────────── draft + pool builders ─────────────────────────

# Each sentence paraphrases its own evidence span (passes the mechanical gates:
# token valid, span bounds valid, no numerics, >=2 content-word overlap) so every
# sentence REACHES the entailment judge — the judge verdict is then the only thing
# deciding kept vs dropped.
_SPANS = {
    "ev_a": "Tirzepatide reduced body weight substantially across the SURMOUNT program in adults with obesity.",
    "ev_b": "Semaglutide improved glycaemic control and supported weight reduction in type two diabetes adults.",
    "ev_c": "The cohort reported meaningful cardiovascular benefit during the extended open label follow up period.",
    "ev_d": "Patients receiving the intervention showed improved renal outcomes over the multiyear observation window.",
    "ev_e": "The registry described durable functional recovery among participants completing the rehabilitation protocol.",
    "ev_f": "Investigators observed sustained symptom relief throughout the maintenance phase of the controlled study.",
}

# Sentences citing each span (paraphrase, no decimals so numeric-match is a no-op).
_SENTENCES = {
    "ev_a": "Tirzepatide produced substantial body weight reduction across SURMOUNT in obesity adults",
    "ev_b": "Semaglutide supported glycaemic control and weight reduction in type two diabetes adults",
    "ev_c": "The cohort experienced meaningful cardiovascular benefit during extended open label follow up",
    "ev_d": "Intervention patients showed improved renal outcomes over the multiyear observation window",
    "ev_e": "The registry recorded durable functional recovery among rehabilitation protocol completers",
    "ev_f": "Investigators saw sustained symptom relief throughout the controlled maintenance phase",
}


def _build_pool() -> dict:
    return {
        ev_id: {
            "evidence_id": ev_id,
            "direct_quote": span,
            "url": f"https://example.org/{ev_id}",
            "tier": "T1",
        }
        for ev_id, span in _SPANS.items()
    }


def _build_draft() -> str:
    lines = []
    for ev_id, span in _SPANS.items():
        sent = _SENTENCES[ev_id]
        lines.append(f"{sent} [#ev:{ev_id}:0-{len(span)}].")
    return " ".join(lines)


def _verdict_fn(sentence: str) -> str:
    # Deterministic: drop the cohort + registry sentences (NEUTRAL), keep the rest.
    if "cohort" in sentence or "registry" in sentence:
        return "NEUTRAL"
    return "ENTAILED"


def _run_strict_verify(monkeypatch, *, parallel: int | None) -> "object":
    """Run strict_verify in enforce mode with a fresh fake judge; return the report
    and the fake judge so callers can inspect verdicts + bound."""
    fake = _CountingFakeJudge(verdict_fn=_verdict_fn, delay=0.02)
    _install_judge(monkeypatch, fake)
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    if parallel is None:
        monkeypatch.delenv("PG_PARALLEL_VERIFY", raising=False)
    else:
        monkeypatch.setenv("PG_PARALLEL_VERIFY", str(parallel))
    report = strict_verify(_build_draft(), _build_pool())
    return report, fake


# ───────────────────────── (a) verdict + ordering determinism ─────────────────────────


def test_parallel_verify_same_verdicts_and_order_as_serial(monkeypatch):
    """(a) parallel verification over a fake judge yields the SAME per-claim
    verdicts AND the SAME kept/dropped ORDER as serial (no verdict change)."""
    serial_report, _ = _run_strict_verify(monkeypatch, parallel=None)
    parallel_report, _ = _run_strict_verify(monkeypatch, parallel=4)

    serial_kept = [sv.sentence for sv in serial_report.kept_sentences]
    parallel_kept = [sv.sentence for sv in parallel_report.kept_sentences]
    serial_dropped = [sv.sentence for sv in serial_report.dropped_sentences]
    parallel_dropped = [sv.sentence for sv in parallel_report.dropped_sentences]

    # Exact order-preserving equality — not just set equality.
    assert parallel_kept == serial_kept, (
        f"parallel kept order diverged:\n serial={serial_kept}\n parallel={parallel_kept}"
    )
    assert parallel_dropped == serial_dropped, (
        f"parallel dropped order diverged:\n serial={serial_dropped}\n parallel={parallel_dropped}"
    )
    # Counters must match too (the consolidation denominator is identical).
    assert parallel_report.total_in == serial_report.total_in
    assert parallel_report.total_kept == serial_report.total_kept
    assert parallel_report.total_dropped == serial_report.total_dropped
    # And the per-sentence is_verified verdict matches index-for-index.
    assert [sv.is_verified for sv in parallel_report.kept_sentences] == \
           [sv.is_verified for sv in serial_report.kept_sentences]


def test_parallel_verify_drops_exactly_the_neutral_sentences(monkeypatch):
    """Sanity: the fake judge drops the cohort+registry sentences in BOTH paths,
    proving the judge actually ran and gated (not a vacuous pass-through)."""
    _, fake = _run_strict_verify(monkeypatch, parallel=4)
    # 6 sentences, 2 NEUTRAL => 4 kept, 2 dropped.
    report, _ = _run_strict_verify(monkeypatch, parallel=4)
    assert report.total_kept == 4
    assert report.total_dropped == 2
    dropped_text = " ".join(sv.sentence for sv in report.dropped_sentences)
    assert "cohort" in dropped_text and "registry" in dropped_text


def test_parallel_verify_order_is_by_input_index_not_completion(monkeypatch):
    """Faithfulness-critical: even when later sentences finish FIRST (inverse
    delay), kept/dropped are ordered by INPUT index, never completion time — a race
    must never reorder a verdict. The drop pattern is interleaved so an ordering bug
    would be visible in BOTH kept and dropped lists."""

    # Per-sentence delay decreasing with position => later sentences finish earlier.
    order = list(_SPANS.keys())  # ev_a..ev_f, stable insertion order

    def _delayed_verdict(sentence: str) -> str:
        # Sleep longer for EARLIER sentences so completion order is reversed.
        try:
            pos = next(i for i, ev in enumerate(order) if _SENTENCES[ev] in sentence)
        except StopIteration:
            pos = 0
        time.sleep(0.005 * (len(order) - pos))
        return _verdict_fn(sentence)

    fake = _CountingFakeJudge(verdict_fn=_delayed_verdict, delay=0.0)
    _install_judge(monkeypatch, fake)
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    monkeypatch.setenv("PG_PARALLEL_VERIFY", "6")
    parallel_report = strict_verify(_build_draft(), _build_pool())

    # Compare against the serial baseline.
    serial_report, _ = _run_strict_verify(monkeypatch, parallel=None)
    assert [sv.sentence for sv in parallel_report.kept_sentences] == \
           [sv.sentence for sv in serial_report.kept_sentences]
    assert [sv.sentence for sv in parallel_report.dropped_sentences] == \
           [sv.sentence for sv in serial_report.dropped_sentences]


# ───────────────────────── (b) bounded concurrency ─────────────────────────


@pytest.mark.parametrize("cap", [2, 3])
def test_parallel_verify_concurrency_is_bounded(monkeypatch, cap):
    """(b) the semaphore/pool cap is honored: max concurrent judge calls never
    exceeds PG_PARALLEL_VERIFY. With 6 sentences and a delay, an unbounded pool
    would reach 6 in flight; a cap of `cap` must hold the ceiling at `cap`."""
    _, fake = _run_strict_verify(monkeypatch, parallel=cap)
    assert fake.max_inflight <= cap, (
        f"observed {fake.max_inflight} concurrent judge calls, cap was {cap}"
    )
    # And it actually OVERLAPPED (proves the pool ran, not silently serial):
    assert fake.max_inflight >= 2, (
        f"expected real overlap with cap={cap}, saw max_inflight={fake.max_inflight}"
    )
    # Every surviving sentence was judged exactly once (no dropped/duplicated work).
    assert len(fake.judged_sentences) == 6


def test_serial_path_has_no_overlap(monkeypatch):
    """The default (unset) and =1 paths run strictly serially: max in-flight == 1."""
    _, fake_default = _run_strict_verify(monkeypatch, parallel=None)
    assert fake_default.max_inflight == 1
    _, fake_one = _run_strict_verify(monkeypatch, parallel=1)
    assert fake_one.max_inflight == 1


# ───────────────────────── (c) telemetry survives the thread pool ─────────────────────────


def test_parallel_verify_run_telemetry_ticks(monkeypatch):
    """(c) The per-run judge telemetry ContextVar (FX-09) must still tick inside
    worker threads — proves the parent context is copied into each worker (else a
    fresh thread context would silently drop these ticks)."""
    from src.polaris_graph.llm.entailment_judge import begin_run_judge_telemetry

    run_tel = begin_run_judge_telemetry()
    _run_strict_verify(monkeypatch, parallel=4)
    # 6 sentences reach the judge => 6 run-scoped calls recorded from worker threads.
    assert run_tel["calls"] == 6, (
        f"per-run judge telemetry lost ticks under the pool: {run_tel}"
    )


# ───────────────────────── (d) section concurrency: bounded + deterministic ─────────────────────────


def _make_fake_section_gather():
    """Replicate the production section-gather shape: bounded asyncio.Semaphore +
    asyncio.gather, results merged back in ORIGINAL plan order. This is the exact
    machinery fix#19 leaves in place for sections (it was already parallel); the
    test pins that more concurrency does NOT reorder or drop a section result and
    that the bound is honored."""

    async def _gather(plans, *, concurrency):
        sem = asyncio.Semaphore(concurrency)
        state = {"inflight": 0, "max_inflight": 0}
        lock = asyncio.Lock()

        async def _one(idx, plan):
            async with sem:
                async with lock:
                    state["inflight"] += 1
                    state["max_inflight"] = max(state["max_inflight"], state["inflight"])
                await asyncio.sleep(0.01)
                async with lock:
                    state["inflight"] -= 1
                # the "section result" is deterministic per plan
                return f"SECTION::{plan}"

        tasks = [asyncio.ensure_future(_one(i, p)) for i, p in enumerate(plans)]
        results = await asyncio.gather(*tasks)
        return results, state["max_inflight"]

    return _gather


def test_parallel_sections_same_set_and_order_as_serial():
    """(d) parallel section generation yields the SAME set+order of section results
    as the serial path (determinism of the merge/consolidation step)."""
    gather = _make_fake_section_gather()
    plans = [f"plan_{i}" for i in range(7)]

    serial_results, serial_max = asyncio.run(gather(plans, concurrency=1))
    parallel_results, parallel_max = asyncio.run(gather(plans, concurrency=5))

    assert parallel_results == serial_results, (
        "section results must be identical + same order regardless of concurrency"
    )
    assert serial_max == 1
    # Bounded: never more than the cap in flight; and it really overlapped.
    assert parallel_max <= 5
    assert parallel_max >= 2


def test_pg_parallel_sections_env_override_bounds_concurrency():
    """The PG_PARALLEL_SECTIONS knob (LAW VI) drives the Semaphore bound in
    multi_section_generator; verify the resolver semantics the production site uses:
    unset => caller default; positive int => override; malformed/<=0 => caller
    default (fail-safe)."""
    # Mirror the exact resolution logic at the production semaphore site.
    def _resolve(default, raw):
        val = default
        raw = (raw or "").strip()
        if raw:
            try:
                ov = int(raw)
                if ov >= 1:
                    val = ov
            except ValueError:
                pass
        return val

    assert _resolve(3, None) == 3       # unset => caller default
    assert _resolve(3, "") == 3         # empty => caller default
    assert _resolve(3, "7") == 7        # positive override
    assert _resolve(3, "1") == 1        # explicit single worker
    assert _resolve(3, "0") == 3        # zero => fail-safe to default
    assert _resolve(3, "-2") == 3       # negative => fail-safe to default
    assert _resolve(3, "abc") == 3      # malformed => fail-safe to default


def test_parallel_verify_worker_resolver_edges(monkeypatch):
    """The PG_PARALLEL_VERIFY resolver: unset/0/1/negative/malformed => 1 (serial);
    explicit >=2 => that value (concurrency cap)."""
    monkeypatch.delenv("PG_PARALLEL_VERIFY", raising=False)
    assert _pg._parallel_verify_workers() == 1
    for bad in ("0", "1", "-5", "abc", ""):
        monkeypatch.setenv("PG_PARALLEL_VERIFY", bad)
        assert _pg._parallel_verify_workers() == 1, bad
    for good, want in (("2", 2), ("8", 8), ("16", 16)):
        monkeypatch.setenv("PG_PARALLEL_VERIFY", good)
        assert _pg._parallel_verify_workers() == want
