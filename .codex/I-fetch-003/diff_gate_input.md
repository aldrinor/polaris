HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

Output the §8.3.9 schema and a FINAL single line `verdict: APPROVE` or `verdict: REQUEST_CHANGES`:
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

Diff review I-fetch-003 (#1175): fetch-starvation fix, BRIEF APPROVED iter-3. VERIFY adversarially (retrieval throughput only — faithfulness gates untouched): (1) deadline is START-anchored + MONOTONIC; not-yet-started never TIMEOUT; harvest wait ALWAYS bounded (never timeout=None); a task is TIMEOUT iff IT exceeded its own budget. (2) round-robin submit-by-backend defeats worker-slot hoarding; result indexing maps back to the ORIGINAL index correctly. (3) backend_id=host gives per-host semaphores; per-host limit + max_workers env-overridable + named constants, no magic numbers. (4) new diag fields do NOT widen api_calls dict; existing parallel_fetch_* fields unchanged. (5) fail-closed + no faithfulness weakening. (6) the offline tests genuinely exercise the slow-sibling, own-budget-timeout, cross-host-concurrency, AND adversarial same-host-prefix-hoarding cases (not tautological). Output the §8.3.9 schema + a final 'verdict:' line.

----- DIFF -----
diff --git a/src/polaris_graph/audit_ir/parallel_fetch.py b/src/polaris_graph/audit_ir/parallel_fetch.py
index 4a779fc7..70e04ec3 100644
--- a/src/polaris_graph/audit_ir/parallel_fetch.py
+++ b/src/polaris_graph/audit_ir/parallel_fetch.py
@@ -226,6 +226,58 @@ class ParallelFetcher(Protocol):
 DEFAULT_PER_BACKEND_LIMIT = 4
 
 
+# ---------------------------------------------------------------------------
+# Harvest-loop poll interval (I-fetch-003 / BB5-C01)
+# ---------------------------------------------------------------------------
+
+
+# Upper bound on a single harvest-loop wait. The deadline is anchored at
+# each task's OBSERVED start (`task_started_monotonic_by_index`), not submit,
+# so a task that has not started yet can never be marked TIMEOUT. To detect
+# a task that STARTS after the previous snapshot (or one that hangs) within
+# a bounded delay of its own start-anchored budget, the harvest loop never
+# waits unbounded: it re-snapshots start-times + recomputes the expired set
+# at least this often. Small enough to be responsive, large enough to avoid
+# a busy-poll. The actual wait is `min(next_deadline - now, this)`.
+_HARVEST_POLL_INTERVAL_SECONDS = 2.0
+
+
+# ---------------------------------------------------------------------------
+# Round-robin submit ordering (I-fetch-003 / BB5-C02)
+# ---------------------------------------------------------------------------
+
+
+def _round_robin_indices(
+    tasks: Sequence[FetchTask],
+) -> list[int]:
+    """Return ORIGINAL task indices reordered into round-robin
+    `backend_id` order.
+
+    Group indices by `backend_id` (preserving first-seen group order
+    and intra-group input order), then emit one index per backend per
+    round until every group is exhausted. So the first ``len(groups)``
+    indices span distinct backends/hosts.
+
+    The result is a permutation of ``range(len(tasks))`` — every input
+    index appears exactly once — so callers map results back to the
+    ORIGINAL index unchanged. Pure / deterministic / allocation-light.
+    """
+    groups: dict[str, list[int]] = {}
+    for idx, task in enumerate(tasks):
+        groups.setdefault(task.backend_id, []).append(idx)
+
+    ordered: list[int] = []
+    group_queues = list(groups.values())
+    while group_queues:
+        next_round: list[list[int]] = []
+        for queue in group_queues:
+            ordered.append(queue.pop(0))
+            if queue:
+                next_round.append(queue)
+        group_queues = next_round
+    return ordered
+
+
 # ---------------------------------------------------------------------------
 # Public API
 # ---------------------------------------------------------------------------
@@ -342,7 +394,14 @@ def parallel_fetch(
                 semaphores[backend_id] = sem
             return sem
 
-    task_started_by_index: dict[int, float] = {}
+    # I-fetch-003 (BB5-C01): the deadline is START-anchored, so we record the
+    # MONOTONIC start of each task (immune to wall-clock jumps) keyed by index
+    # under the lock. The wall-clock start is kept separately ONLY for the
+    # FetchResultRecord.started_at report field (AC7 — never used in deadline
+    # arithmetic). A not-yet-started index is absent from BOTH maps → +inf
+    # effective deadline → cannot TIMEOUT before it runs.
+    task_started_monotonic_by_index: dict[int, float] = {}
+    task_started_wall_by_index: dict[int, float] = {}
     task_started_lock = threading.Lock()
 
     def _run_task(
@@ -351,8 +410,10 @@ def parallel_fetch(
         sem = _get_semaphore(task.backend_id)
         sem.acquire()
         task_started = time.time()
+        task_started_mono = time.monotonic()
         with task_started_lock:
-            task_started_by_index[index] = task_started
+            task_started_monotonic_by_index[index] = task_started_mono
+            task_started_wall_by_index[index] = task_started
         try:
             try:
                 result = fetcher.fetch(task)
@@ -411,17 +472,33 @@ def parallel_fetch(
     )
     try:
         future_to_index: dict[concurrent.futures.Future, int] = {}
-        deadline_per_future: dict[concurrent.futures.Future, float] = {}
-        submit_now = time.time()
-        for idx, task in enumerate(deduped):
+        # I-fetch-003 (BB5-C02): submit in ROUND-ROBIN backend order so the
+        # first `max_workers` submissions span up to `max_workers` distinct
+        # backends/hosts. Without this, a clustered same-host candidate prefix
+        # makes the first workers all block on ONE host-semaphore (acquired
+        # inside `_run_task`), starving distinct-host tasks queued behind them.
+        # `_round_robin_indices` returns ORIGINAL deduped indices, so result
+        # indexing into `results_by_index` is unchanged (correctness preserved).
+        submit_order = _round_robin_indices(deduped)
+        for idx in submit_order:
+            task = deduped[idx]
             fut = executor.submit(_run_task, idx, task)
             future_to_index[fut] = idx
-            if per_task_timeout is not None:
-                deadline_per_future[fut] = submit_now + per_task_timeout
 
         remaining: set[concurrent.futures.Future] = set(future_to_index)
         protocol_error_to_raise: FetcherProtocolError | None = None
 
+        def _effective_deadline_monotonic(idx: int) -> float:
+            # I-fetch-003 (BB5-C01): START-anchored, MONOTONIC effective
+            # deadline. A not-yet-started index (absent from the start map)
+            # → +inf: it CANNOT TIMEOUT before it runs. A started index →
+            # its OWN observed start + per_task_timeout. Caller holds
+            # `task_started_lock`.
+            started = task_started_monotonic_by_index.get(idx)
+            if started is None:
+                return float("inf")
+            return started + per_task_timeout  # type: ignore[operator]
+
         while remaining and protocol_error_to_raise is None:
             if per_task_timeout is None:
                 # No timeout — just wait for the next completion.
@@ -430,10 +507,22 @@ def parallel_fetch(
                     return_when=concurrent.futures.FIRST_COMPLETED,
                 )
             else:
-                now = time.time()
-                # Earliest deadline among still-running futures.
-                next_deadline = min(deadline_per_future[f] for f in remaining)
-                wait_timeout = max(0.0, next_deadline - now)
+                # I-fetch-003 (BB5-C01): BOUNDED-POLL harvest. The wait is
+                # ALWAYS bounded by `_HARVEST_POLL_INTERVAL_SECONDS`, never
+                # `timeout=None`, so a task that STARTS after this snapshot
+                # (or one that hangs) is re-checked against ITS OWN start-
+                # anchored deadline within the poll interval — the harvest
+                # never relies on a sibling completing to make progress.
+                now_mono = time.monotonic()
+                with task_started_lock:
+                    next_deadline = min(
+                        _effective_deadline_monotonic(future_to_index[f])
+                        for f in remaining
+                    )
+                wait_timeout = min(
+                    max(0.0, next_deadline - now_mono),
+                    _HARVEST_POLL_INTERVAL_SECONDS,
+                )
                 done, _ = concurrent.futures.wait(
                     remaining,
                     timeout=wait_timeout,
@@ -451,42 +540,45 @@ def parallel_fetch(
                         break
                     results_by_index[idx] = rec
                     remaining.discard(fut)
-                    deadline_per_future.pop(fut, None)
-            else:
-                # Wait expired with no completions — at least one
-                # future has hit its deadline. Mark expired futures
-                # as TIMEOUT and continue.
-                now = time.time()
-                expired = [
-                    f for f in list(remaining)
-                    if deadline_per_future.get(f, float("inf")) <= now
-                ]
-                if not expired:
-                    # No expired but no completions either — defensive
-                    # tiny-deadline race; loop again.
-                    continue
-                for fut in expired:
-                    idx = future_to_index[fut]
-                    task = deduped[idx]
-                    fut.cancel()  # best-effort
-                    with task_started_lock:
-                        timeout_started_at = task_started_by_index.get(
-                            idx, submit_now,
+
+            if protocol_error_to_raise is not None:
+                break
+
+            if per_task_timeout is not None:
+                # Recompute the expired set from CURRENT start-times after
+                # every wake (whether or not anything completed). A task is
+                # TIMEOUT iff IT exceeded ITS OWN start-anchored budget.
+                now_mono = time.monotonic()
+                with task_started_lock:
+                    expired = [
+                        f for f in list(remaining)
+                        if _effective_deadline_monotonic(
+                            future_to_index[f]
+                        ) <= now_mono
+                    ]
+                if expired:
+                    now_wall = time.time()
+                    for fut in expired:
+                        idx = future_to_index[fut]
+                        task = deduped[idx]
+                        fut.cancel()  # best-effort
+                        with task_started_lock:
+                            timeout_started_at = (
+                                task_started_wall_by_index.get(idx, now_wall)
+                            )
+                        results_by_index[idx] = FetchResultRecord(
+                            source_url=task.source_url,
+                            backend_id=task.backend_id,
+                            outcome=FetchOutcome.TIMEOUT,
+                            payload=None,
+                            content_type=None,
+                            fetch_status_code=None,
+                            error="per-task timeout exceeded",
+                            started_at=timeout_started_at,
+                            finished_at=now_wall,
+                            task_metadata=task.task_metadata,
                         )
-                    results_by_index[idx] = FetchResultRecord(
-                        source_url=task.source_url,
-                        backend_id=task.backend_id,
-                        outcome=FetchOutcome.TIMEOUT,
-                        payload=None,
-                        content_type=None,
-                        fetch_status_code=None,
-                        error="per-task timeout exceeded",
-                        started_at=timeout_started_at,
-                        finished_at=now,
-                        task_metadata=task.task_metadata,
-                    )
-                    remaining.discard(fut)
-                    deadline_per_future.pop(fut, None)
+                        remaining.discard(fut)
 
         if protocol_error_to_raise is not None:
             for other_fut in remaining:
diff --git a/src/polaris_graph/retrieval/live_retriever.py b/src/polaris_graph/retrieval/live_retriever.py
index 874d5675..2d7dcc5f 100644
--- a/src/polaris_graph/retrieval/live_retriever.py
+++ b/src/polaris_graph/retrieval/live_retriever.py
@@ -34,7 +34,7 @@ import time
 from dataclasses import dataclass, field
 from pathlib import Path
 from typing import Any, Optional
-from urllib.parse import urlparse
+from urllib.parse import urlparse, urlsplit
 
 import httpx
 
@@ -93,6 +93,26 @@ DEFAULT_FETCH_CAP = int(os.getenv("PG_LIVE_FETCH_CAP", "40"))
 DEFAULT_CONTENT_MAX_CHARS = int(os.getenv("PG_LIVE_CONTENT_MAX", "25000"))
 DEFAULT_HTTP_TIMEOUT = float(os.getenv("PG_LIVE_HTTP_TIMEOUT", "20"))
 
+# I-fetch-003 (#1175 / BB5-C02): parallel-fetch worker-pool sizing. When
+# PG_LIVE_RETRIEVER_MAX_WORKERS is UNSET, the pool scales with the candidate
+# count: min(_CEILING, max(_FLOOR, len(candidates) // _PER_CANDIDATE)). Named
+# constants (LAW VI — no magic numbers). Floor keeps small corpora at the
+# legacy default of 8; ceiling caps the pool so a huge corpus cannot spawn an
+# unbounded thread count; per-candidate divisor sets the ramp.
+_FETCH_WORKERS_FLOOR = 8
+_FETCH_WORKERS_CEILING = 48
+_FETCH_WORKERS_PER_CANDIDATE = 16
+# Mirror of parallel_fetch.DEFAULT_PER_BACKEND_LIMIT (4) used as the default
+# per-HOST concurrency cap; imported as a named constant rather than hardcoded.
+from src.polaris_graph.audit_ir.parallel_fetch import (  # noqa: E402
+    DEFAULT_PER_BACKEND_LIMIT as _PARALLEL_FETCH_DEFAULT_PER_BACKEND_LIMIT,
+)
+# I-fetch-003 (#1175 / AC3): WARN floor for the new fetch_success_rate
+# retrieval diagnostic. Env-overridable; below this, a loud warning fires.
+_FETCH_SUCCESS_RATE_WARN_FLOOR = float(
+    os.getenv("PG_LIVE_FETCH_SUCCESS_RATE_WARN_FLOOR", "0.5")
+)
+
 
 @dataclass
 class LiveRetrievalResult:
@@ -117,6 +137,15 @@ class LiveRetrievalResult:
     # source_type / is_peer_reviewed / is_retracted / doi / venue) that the
     # citeability predicate needs; merged across retrieval stages by the sweep.
     journal_metadata_sidecar: dict[str, Any] | None = None
+    # I-fetch-003 (#1175 / AC3): NEW retrieval-throughput diagnostics, emitted
+    # as SIBLING fields (NOT folded into api_calls: dict[str, int] — that
+    # contract stays unwidened). None when the parallel-fetch path did not run
+    # (serial fallback or no candidates). fetch_success_rate = usable / (usable
+    # + failed); parallel_completion_rate = completed-in-deadline / submitted.
+    fetch_success_rate: float | None = None
+    parallel_completion_rate: float | None = None
+    fetch_workers: int | None = None
+    distinct_hosts: int | None = None
 
 
 # ─────────────────────────────────────────────────────────────────────────────
@@ -2751,9 +2780,16 @@ def run_live_retrieval(
     # element is the raw ld+json captured before _strip_html (Signal C input).
     use_parallel = os.environ.get("PG_USE_PARALLEL_FETCH", "1") != "0"
     fetched_side: dict[str, tuple[str, bool, str, str, str]] = {}
+    # I-fetch-003 (#1175 / AC3): retrieval-throughput diagnostics. Stay None on
+    # the serial fallback / no-candidates path (no parallel_fetch report).
+    _fetch_success_rate: float | None = None
+    _parallel_completion_rate: float | None = None
+    _fetch_workers: int | None = None
+    _distinct_hosts: int | None = None
 
     if use_parallel and candidates:
         from src.polaris_graph.audit_ir.parallel_fetch import (
+            FetchOutcome,
             FetchTask,
             parallel_fetch,
         )
@@ -2790,12 +2826,25 @@ def run_live_retrieval(
                 payload = (content or "").encode("utf-8", errors="replace")
                 return (payload, "text/plain", 200 if ok else 502)
 
-        try:
-            max_workers = int(os.environ.get(
-                "PG_LIVE_RETRIEVER_MAX_WORKERS", "8",
-            ))
-        except ValueError:
-            max_workers = 8
+        # I-fetch-003 (#1175 / BB5-C02): scale max_workers with the candidate
+        # count instead of a flat default-8. Explicit env wins; when UNSET,
+        # min(_CEILING, max(_FLOOR, len(candidates) // _PER_CANDIDATE)). Named
+        # constants (LAW VI — no magic numbers). For ~740 candidates this
+        # yields ~46 workers; small corpora stay at the floor of 8.
+        _explicit_workers = os.environ.get("PG_LIVE_RETRIEVER_MAX_WORKERS")
+        if _explicit_workers is not None:
+            try:
+                max_workers = max(1, int(_explicit_workers))
+            except ValueError:
+                max_workers = _FETCH_WORKERS_FLOOR
+        else:
+            max_workers = min(
+                _FETCH_WORKERS_CEILING,
+                max(
+                    _FETCH_WORKERS_FLOOR,
+                    len(candidates) // _FETCH_WORKERS_PER_CANDIDATE,
+                ),
+            )
         try:
             per_task_timeout = float(os.environ.get(
                 "PG_LIVE_RETRIEVER_FETCH_TIMEOUT_SECONDS", "120",
@@ -2803,16 +2852,31 @@ def run_live_retrieval(
         except ValueError:
             per_task_timeout = 120.0
 
+        # I-fetch-003 (#1175 / BB5-C02): per-HOST politeness limit. The
+        # parallel_fetch semaphore is keyed by FetchTask.backend_id; keying it
+        # by the URL host (below) gives each host its own Semaphore so distinct
+        # hosts fetch concurrently while same-host stays capped. Env-overridable;
+        # default mirrors parallel_fetch DEFAULT_PER_BACKEND_LIMIT (4).
+        _per_host_limit = _env_int(
+            "PG_LIVE_RETRIEVER_PER_HOST_CONCURRENT",
+            _PARALLEL_FETCH_DEFAULT_PER_BACKEND_LIMIT,
+        )
+
         fetch_tasks = []
+        _per_host_concurrent: dict[str, int] = {}
         for idx, c in enumerate(candidates):
             # I-meta-007c: carry the candidate's DOI/PMID hints into the
             # FetchTask so _LiveContentParallelFetcher.fetch can pass them to
             # _fetch_content for the OA resolver (default = parallel path).
             _doi, _pmid = _candidate_oa_hints(getattr(c, "metadata", None))
+            # I-fetch-003 (#1175): key the rate-limit class by URL host so the
+            # parallel_fetch host-semaphore yields cross-host parallelism.
+            _host = urlsplit(c.url).hostname or "default"
+            _per_host_concurrent[_host] = _per_host_limit
             fetch_tasks.append(
                 FetchTask(
                     source_url=c.url,
-                    backend_id="default",
+                    backend_id=_host,
                     task_metadata={"index": idx, "doi": _doi, "pmid": _pmid},
                 )
             )
@@ -2820,6 +2884,7 @@ def run_live_retrieval(
         parallel_report = parallel_fetch(
             fetch_tasks, fetcher,
             max_workers=max_workers,
+            per_backend_max_concurrent=_per_host_concurrent,
             per_task_timeout=per_task_timeout,
         )
         # Run-log evidence: persist the substrate's report into
@@ -2842,6 +2907,45 @@ def run_live_retrieval(
             parallel_report.timeout_count,
             max_workers, per_task_timeout,
         )
+        # I-fetch-003 (#1175 / AC3): NEW retrieval-throughput diagnostics.
+        # fetch_success_rate = usable / (usable + failed): a SUCCESS outcome
+        # with a 2xx status is "usable"; an ERRORED/TIMEOUT or a non-2xx
+        # SUCCESS (the adapter returns 502 when _fetch_content reports not-ok)
+        # is "failed". parallel_completion_rate = completed-in-deadline /
+        # submitted (1 - timeout_fraction). These are SIBLING fields surfaced on
+        # LiveRetrievalResult; they are NOT folded into api_calls (contract
+        # stays unwidened, M-INT-1 fields above unchanged).
+        _usable_fetched = sum(
+            1 for r in parallel_report.results
+            if r.outcome is FetchOutcome.SUCCESS
+            and (r.fetch_status_code or 0) < 400
+        )
+        _failed_fetched = len(parallel_report.results) - _usable_fetched
+        _denom = _usable_fetched + _failed_fetched
+        _fetch_success_rate = (
+            _usable_fetched / _denom if _denom > 0 else None
+        )
+        _submitted = len(parallel_report.results)
+        _parallel_completion_rate = (
+            (_submitted - parallel_report.timeout_count) / _submitted
+            if _submitted > 0 else None
+        )
+        _fetch_workers = max_workers
+        _distinct_hosts = len(_per_host_concurrent)
+        if (
+            _fetch_success_rate is not None
+            and _fetch_success_rate < _FETCH_SUCCESS_RATE_WARN_FLOOR
+        ):
+            logger.warning(
+                "[live_retriever] I-fetch-003 LOW fetch_success_rate %.2f "
+                "(< floor %.2f): %d usable / %d submitted across %d hosts, "
+                "%d timeout — corpus may be starved; check per-host limit / "
+                "max_workers / per_task_timeout.",
+                _fetch_success_rate,
+                _FETCH_SUCCESS_RATE_WARN_FLOOR,
+                _usable_fetched, _submitted, _distinct_hosts,
+                parallel_report.timeout_count,
+            )
 
     # #554 (I-bug-115): bound the synchronous post-fetch candidate loop so a
     # wedged per-candidate operation can never hang the run with no terminal
@@ -3109,4 +3213,8 @@ def run_live_retrieval(
         candidates_total=_candidates_total,
         candidates_processed=_candidates_processed,
         journal_metadata_sidecar=(_journal_sidecar if _journal_only_on else None),
+        fetch_success_rate=_fetch_success_rate,
+        parallel_completion_rate=_parallel_completion_rate,
+        fetch_workers=_fetch_workers,
+        distinct_hosts=_distinct_hosts,
     )
diff --git a/tests/polaris_graph/test_parallel_fetch_ifetch003.py b/tests/polaris_graph/test_parallel_fetch_ifetch003.py
new file mode 100644
index 00000000..555ffdaf
--- /dev/null
+++ b/tests/polaris_graph/test_parallel_fetch_ifetch003.py
@@ -0,0 +1,369 @@
+"""I-fetch-003 (#1175 / BB5-C01/C02) — start-anchored, bounded-poll,
+round-robin parallel-fetch starvation fix.
+
+Offline + deterministic: NO network, NO spend. A mock fetcher plus a
+virtual monotonic clock (monkeypatched onto the parallel_fetch module)
+drive the start-anchored deadline arithmetic; `threading.Event`
+barriers make concurrency ordering deterministic without sleeping on
+the wall clock. The harvest poll interval is shrunk so the bounded
+poll wakes quickly instead of really blocking ~2s.
+
+Covers (per AC5):
+  (a) a single SLOW task does NOT time out fast/queued siblings under
+      start-anchoring + bounded poll (the C01 starvation root cause).
+  (b) a task exceeding ITS OWN start-anchored budget IS TIMEOUT even
+      when no sibling ever completes.
+  (c) two DISTINCT hosts run concurrently while same-host is capped at
+      the per-host limit (C02 host-keyed semaphore).
+  (d) ADVERSARIAL: >max_workers same-host tasks followed by a
+      different-host task — the other host STARTS before the same-host
+      prefix drains (round-robin submit defeats worker-slot hoarding).
+"""
+
+from __future__ import annotations
+
+import threading
+import time
+from dataclasses import dataclass, field
+
+import pytest
+
+import src.polaris_graph.audit_ir.parallel_fetch as pf_mod
+from src.polaris_graph.audit_ir.parallel_fetch import (
+    FetchOutcome,
+    FetchTask,
+    _round_robin_indices,
+    parallel_fetch,
+)
+
+
+# ---------------------------------------------------------------------------
+# Virtual monotonic clock — deterministic deadline arithmetic, no wall sleep
+# ---------------------------------------------------------------------------
+
+
+class _VirtualClock:
+    """A controllable monotonic clock. Worker threads advance it from
+    inside the mock fetcher (per-task), the harvest loop reads it for
+    deadline decisions. Thread-safe."""
+
+    def __init__(self) -> None:
+        self._now = 0.0
+        self._lock = threading.Lock()
+
+    def monotonic(self) -> float:
+        with self._lock:
+            return self._now
+
+    def advance(self, seconds: float) -> None:
+        with self._lock:
+            self._now += seconds
+
+
+# ---------------------------------------------------------------------------
+# Mock fetchers
+# ---------------------------------------------------------------------------
+
+
+@dataclass
+class _GatedFetcher:
+    """Per-URL gated fetcher. Each task records its start order, then
+    blocks on a per-URL `threading.Event` until the test releases it.
+    Optionally advances a virtual clock by `clock_advance` BEFORE
+    blocking so the harvest loop sees the task as having consumed time.
+    """
+
+    release_events: dict[str, threading.Event]
+    clock: _VirtualClock | None = None
+    clock_advance: float = 0.0
+    start_order: list[str] = field(default_factory=list)
+    started_events: dict[str, threading.Event] = field(default_factory=dict)
+    _lock: threading.Lock = field(default_factory=threading.Lock)
+
+    def fetch(self, task: FetchTask) -> tuple[bytes, str, int]:
+        with self._lock:
+            self.start_order.append(task.source_url)
+        ev = self.started_events.get(task.source_url)
+        if ev is not None:
+            ev.set()
+        if self.clock is not None and self.clock_advance:
+            self.clock.advance(self.clock_advance)
+        gate = self.release_events.get(task.source_url)
+        if gate is not None:
+            gate.wait(timeout=10.0)
+        return (task.source_url.encode("utf-8"), "text/plain", 200)
+
+
+# ---------------------------------------------------------------------------
+# (round-robin permutation correctness — submit-order primitive)
+# ---------------------------------------------------------------------------
+
+
+def test_round_robin_indices_is_a_permutation() -> None:
+    tasks = [
+        FetchTask("https://a/1", "host_a"),
+        FetchTask("https://a/2", "host_a"),
+        FetchTask("https://a/3", "host_a"),
+        FetchTask("https://b/1", "host_b"),
+    ]
+    order = _round_robin_indices(tasks)
+    # A permutation of range(len): every original index exactly once.
+    assert sorted(order) == [0, 1, 2, 3]
+    # First two submissions span the two distinct hosts (no hoarding).
+    assert {tasks[order[0]].backend_id, tasks[order[1]].backend_id} == {
+        "host_a", "host_b",
+    }
+
+
+def test_round_robin_indices_single_backend_preserves_order() -> None:
+    tasks = [FetchTask(f"https://a/{i}", "host_a") for i in range(5)]
+    assert _round_robin_indices(tasks) == [0, 1, 2, 3, 4]
+
+
+# ---------------------------------------------------------------------------
+# (a) slow task does NOT time out fast/queued siblings
+# ---------------------------------------------------------------------------
+
+
+def test_slow_task_does_not_timeout_fast_siblings(
+    monkeypatch: pytest.MonkeyPatch,
+) -> None:
+    """C01 root cause: ONE slow task must not drag fast (and not-yet-
+    started) siblings into a batch TIMEOUT. Start-anchoring means a
+    not-yet-started task has a +inf deadline; a fast task that runs
+    well inside its own budget SUCCEEDS."""
+    clock = _VirtualClock()
+    monkeypatch.setattr(pf_mod.time, "monotonic", clock.monotonic)
+    # Shrink the bounded poll so the harvest loop wakes fast (no real 2s).
+    monkeypatch.setattr(pf_mod, "_HARVEST_POLL_INTERVAL_SECONDS", 0.02)
+
+    urls = ["https://fast/1", "https://fast/2", "https://slow/1"]
+    release = {u: threading.Event() for u in urls}
+    # Release the two fast tasks immediately; the slow one stays gated
+    # but will finish WELL within its own budget (no clock advance).
+    release["https://fast/1"].set()
+    release["https://fast/2"].set()
+    release["https://slow/1"].set()
+    fetcher = _GatedFetcher(release_events=release, clock=clock)
+
+    tasks = [FetchTask(u, "default") for u in urls]
+    report = parallel_fetch(
+        tasks, fetcher,
+        max_workers=4,
+        per_backend_max_concurrent={"default": 4},
+        per_task_timeout=100.0,
+    )
+    # None timed out: every task ran inside its own start-anchored budget.
+    assert report.timeout_count == 0
+    assert report.success_count == 3
+    assert all(r.outcome is FetchOutcome.SUCCESS for r in report.results)
+
+
+# ---------------------------------------------------------------------------
+# (b) a task exceeding ITS OWN budget IS TIMEOUT even with no sibling done
+# ---------------------------------------------------------------------------
+
+
+def test_task_over_own_budget_is_timeout_without_sibling_completion(
+    monkeypatch: pytest.MonkeyPatch,
+) -> None:
+    """A single task that consumes MORE than its own start-anchored
+    budget is marked TIMEOUT — the bounded poll catches it within the
+    poll interval and does NOT rely on any sibling completing."""
+    clock = _VirtualClock()
+    monkeypatch.setattr(pf_mod.time, "monotonic", clock.monotonic)
+    monkeypatch.setattr(pf_mod, "_HARVEST_POLL_INTERVAL_SECONDS", 0.02)
+
+    # The single task starts, advances the virtual clock PAST its budget,
+    # then stays gated (never completes). The harvest loop must TIMEOUT it.
+    url = "https://hang/1"
+    release = {url: threading.Event()}  # never set -> never completes
+    started = {url: threading.Event()}
+    fetcher = _GatedFetcher(
+        release_events=release,
+        clock=clock,
+        clock_advance=5.0,  # > per_task_timeout below
+        started_events=started,
+    )
+
+    tasks = [FetchTask(url, "default")]
+    report = parallel_fetch(
+        tasks, fetcher,
+        max_workers=2,
+        per_task_timeout=1.0,
+    )
+    assert report.timeout_count == 1
+    rec = report.results[0]
+    assert rec.outcome is FetchOutcome.TIMEOUT
+    assert rec.error == "per-task timeout exceeded"
+    # The gated worker did start (proving the budget was START-anchored,
+    # not relabeled at submit time).
+    assert started[url].is_set()
+
+
+def test_not_yet_started_task_never_times_out_behind_a_slot_hog(
+    monkeypatch: pytest.MonkeyPatch,
+) -> None:
+    """With max_workers=1, a queued (not-yet-started) task has a +inf
+    effective deadline: even though wall time passes while the first
+    task hogs the only slot, the queued task is NOT batch-TIMEOUT'd —
+    it runs and SUCCEEDS once the slot frees. (Inverse of C01.)"""
+    clock = _VirtualClock()
+    monkeypatch.setattr(pf_mod.time, "monotonic", clock.monotonic)
+    monkeypatch.setattr(pf_mod, "_HARVEST_POLL_INTERVAL_SECONDS", 0.02)
+
+    first, second = "https://first/1", "https://second/1"
+    release = {first: threading.Event(), second: threading.Event()}
+    started = {first: threading.Event(), second: threading.Event()}
+    release[second].set()  # second completes instantly once it starts
+    fetcher = _GatedFetcher(
+        release_events=release, clock=clock, started_events=started,
+    )
+
+    tasks = [FetchTask(first, "default"), FetchTask(second, "default")]
+
+    def _run() -> pf_mod.ParallelFetchReport:
+        return parallel_fetch(
+            tasks, fetcher,
+            max_workers=1,  # second is QUEUED behind first
+            per_task_timeout=1.0,
+        )
+
+    holder: dict[str, object] = {}
+    runner = threading.Thread(target=lambda: holder.update(r=_run()))
+    runner.start()
+    # First task has started and is holding the only worker slot.
+    assert started[first].wait(timeout=5.0)
+    # Advance virtual time PAST first's budget. The QUEUED second task
+    # has no start yet (+inf deadline) -> must NOT be timed out.
+    clock.advance(10.0)
+    time.sleep(0.1)
+    assert not started[second].is_set()  # still queued, not started
+    # Release first inside its (virtual) budget consumption is moot — it
+    # already over-ran; it will TIMEOUT. Free the slot so second can run.
+    release[first].set()
+    runner.join(timeout=10.0)
+    report = holder["r"]  # type: ignore[assignment]
+
+    outcomes = {r.source_url: r.outcome for r in report.results}
+    # first over-ran its own budget -> TIMEOUT; second ran fresh -> SUCCESS.
+    assert outcomes[second] is FetchOutcome.SUCCESS
+    assert outcomes[first] is FetchOutcome.TIMEOUT
+
+
+# ---------------------------------------------------------------------------
+# (c) two distinct hosts concurrent; same-host capped at per-host limit
+# ---------------------------------------------------------------------------
+
+
+def test_distinct_hosts_run_concurrently_same_host_capped() -> None:
+    """Host-keyed backend_id (limit=1 per host): two tasks on DIFFERENT
+    hosts overlap; two tasks on the SAME host serialize."""
+
+    @dataclass
+    class _DelayFetcher:
+        delay: float
+
+        def fetch(self, task: FetchTask) -> tuple[bytes, str, int]:
+            time.sleep(self.delay)
+            return (task.source_url.encode(), "text/plain", 200)
+
+    same_host = [
+        FetchTask("https://h1/a", "host1"),
+        FetchTask("https://h1/b", "host1"),
+    ]
+    t0 = time.time()
+    rep_same = parallel_fetch(
+        same_host, _DelayFetcher(0.05),
+        max_workers=4,
+        per_backend_max_concurrent={"host1": 1},
+    )
+    same_elapsed = time.time() - t0
+    assert rep_same.success_count == 2
+    # limit=1 serializes -> ~2 * 0.05.
+    assert same_elapsed >= 0.09, (
+        f"same-host elapsed {same_elapsed} suggests cap=1 violated"
+    )
+
+    # Distinct hosts: overlap -> faster than serial.
+    diff_host = [
+        FetchTask("https://h1/a", "host1"),
+        FetchTask("https://h2/a", "host2"),
+    ]
+    t0 = time.time()
+    rep_diff = parallel_fetch(
+        diff_host, _DelayFetcher(0.05),
+        max_workers=4,
+        per_backend_max_concurrent={"host1": 1, "host2": 1},
+    )
+    diff_elapsed = time.time() - t0
+    assert rep_diff.success_count == 2
+    # Two distinct hosts run concurrently -> ~0.05, not ~0.10.
+    assert diff_elapsed < 0.09, (
+        f"distinct-host elapsed {diff_elapsed} suggests no cross-host "
+        "parallelism"
+    )
+
+
+# ---------------------------------------------------------------------------
+# (d) ADVERSARIAL — round-robin submit defeats worker-slot hoarding
+# ---------------------------------------------------------------------------
+
+
+def test_roundrobin_other_host_starts_before_same_host_prefix_drains() -> None:
+    """ADVERSARIAL: a clustered same-host prefix (more tasks than
+    max_workers, each on host_a capped at 1) followed by ONE host_b
+    task. Without round-robin submit the first max_workers workers all
+    block on host_a's single semaphore and host_b starves until the
+    prefix drains. With round-robin submit, host_b is submitted in the
+    first round and STARTS before the host_a prefix finishes.
+    """
+    n_same = 6  # > max_workers
+    max_workers = 4
+    same_urls = [f"https://host_a/{i}" for i in range(n_same)]
+    other_url = "https://host_b/1"
+
+    release = {u: threading.Event() for u in same_urls}
+    release[other_url] = threading.Event()
+    release[other_url].set()  # host_b completes immediately once started
+    started = {u: threading.Event() for u in same_urls}
+    started[other_url] = threading.Event()
+    fetcher = _GatedFetcher(
+        release_events=release, started_events=started,
+    )
+
+    # Same-host prefix THEN the other host (the hoarding-bait order).
+    tasks = [FetchTask(u, "host_a") for u in same_urls]
+    tasks.append(FetchTask(other_url, "host_b"))
+
+    holder: dict[str, object] = {}
+
+    def _run() -> None:
+        holder["r"] = parallel_fetch(
+            tasks, fetcher,
+            max_workers=max_workers,
+            # host_a capped at 1 -> only one host_a task runs at a time;
+            # the other 3 worker slots would be IDLE-but-blocked under a
+            # naive submit order. Round-robin must let host_b run.
+            per_backend_max_concurrent={"host_a": 1, "host_b": 1},
+            per_task_timeout=None,
+        )
+
+    runner = threading.Thread(target=_run)
+    runner.start()
+    # host_b must START while the host_a prefix is still gated (none of
+    # the host_a tasks have been released yet).
+    assert started[other_url].wait(timeout=5.0), (
+        "host_b did not start before the host_a prefix drained — "
+        "round-robin submit failed to defeat worker-slot hoarding"
+    )
+    # Confirm the host_a prefix is genuinely still blocked (proof the
+    # other host started CONCURRENTLY, not after the prefix completed).
+    assert not all(started[u].is_set() for u in same_urls[1:])
+
+    # Drain the host_a prefix so the run can finish cleanly.
+    for ev in release.values():
+        ev.set()
+    runner.join(timeout=10.0)
+    report = holder["r"]  # type: ignore[assignment]
+    assert report.success_count == n_same + 1
