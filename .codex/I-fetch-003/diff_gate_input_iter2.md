HARD ITERATION CAP 5, this is iter 2 of 5. Front-load findings; APPROVE iff zero NOVEL/continuing P0 and zero P1; final line 'verdict: APPROVE|REQUEST_CHANGES' + §8.3.9 schema. ITER-2 CHANGELOG: addressed your iter-1 P1 (added a global batch-budget termination guarantee — when monotonic now exceeds batch_start + budget, remaining NEVER-STARTED futures are cancelled + recorded FetchOutcome.NOT_DISPATCHED (distinct, not mislabeled TIMEOUT) and the loop breaks, so parallel_fetch terminates in bounded time even if all workers are wedged by abandoned in-flight tasks) + iter-1 P2 (the slow-sibling test now advances the virtual clock: fast siblings return while the slow task is genuinely in-flight; the slow task is TIMEOUT'd only at its own start-anchored deadline).

VERIFY checklist:
(1) batch-budget guarantees termination under all-workers-wedged + queued; never-started tasks recorded NOT_DISPATCHED not TIMEOUT;
(2) start-anchored monotonic per-task deadline + bounded poll intact;
(3) round-robin submit indexing correct;
(4) host-keyed semaphore + env knobs + named constants;
(5) NOT_DISPATCHED handled by downstream consumers without crash;
(6) fail-closed + faithfulness gates untouched;
(7) the new batch-termination test + the fixed slow-sibling test genuinely exercise their boundaries (not tautological).

----- DIFF -----
diff --git a/scripts/run_honest_sweep_r3.py b/scripts/run_honest_sweep_r3.py
index ff2d4ac7..c7bb228b 100644
--- a/scripts/run_honest_sweep_r3.py
+++ b/scripts/run_honest_sweep_r3.py
@@ -670,6 +670,17 @@ def _retrieval_manifest_section(retrieval) -> dict:
         "corpus_truncated": bool(getattr(retrieval, "corpus_truncated", False)),
         "candidates_total": getattr(retrieval, "candidates_total", 0),
         "candidates_processed": getattr(retrieval, "candidates_processed", 0),
+        # I-fetch-003 (#1175 / AC3): NEW retrieval-throughput diagnostics,
+        # SIBLING fields (NOT folded into api_calls — that dict[str,int]
+        # contract stays unwidened). None when the parallel-fetch path did not
+        # run (serial fallback / no candidates); getattr defaults keep this
+        # backward compatible with pre-#1175 retrieval objects.
+        "fetch_success_rate": getattr(retrieval, "fetch_success_rate", None),
+        "parallel_completion_rate": getattr(
+            retrieval, "parallel_completion_rate", None,
+        ),
+        "fetch_workers": getattr(retrieval, "fetch_workers", None),
+        "distinct_hosts": getattr(retrieval, "distinct_hosts", None),
     }
 
 
diff --git a/src/polaris_graph/audit_ir/parallel_fetch.py b/src/polaris_graph/audit_ir/parallel_fetch.py
index 4a779fc7..d9f84995 100644
--- a/src/polaris_graph/audit_ir/parallel_fetch.py
+++ b/src/polaris_graph/audit_ir/parallel_fetch.py
@@ -53,6 +53,8 @@ See `docs/md8_phase1_threat_model.md` for boundaries.
 from __future__ import annotations
 
 import concurrent.futures
+import math
+import os
 import threading
 import time
 from dataclasses import dataclass, field
@@ -110,12 +112,23 @@ class FetchOutcome(str, Enum):
     SUCCESS: fetcher returned a payload (regardless of HTTP
        status code — caller's Fetcher decides what to raise on).
     ERRORED: fetcher raised an exception.
-    TIMEOUT: per-task timeout fired before the fetcher returned.
+    TIMEOUT: per-task timeout fired AFTER the task STARTED (it
+       reached `fetcher.fetch` and over-ran its own start-anchored
+       budget — or the global batch budget fired while it was
+       in-flight past its deadline).
+    NOT_DISPATCHED: the global batch budget (I-fetch-003) fired
+       while this task was still QUEUED and had never started — the
+       worker pool was starved by abandoned in-flight fetches, so
+       this task never reached `fetcher.fetch`. Distinct from
+       TIMEOUT (which means the task DID run): NOT_DISPATCHED is a
+       never-ran non-result. Downstream consumers treat it as a
+       non-result, the same class as TIMEOUT/ERRORED (no payload).
     """
 
     SUCCESS = "success"
     ERRORED = "errored"
     TIMEOUT = "timeout"
+    NOT_DISPATCHED = "not_dispatched"
 
 
 @dataclass(frozen=True)
@@ -172,7 +185,14 @@ class ParallelFetchReport:
     (the substrate doesn't fetch the same URL twice in one
     call by design).
 
-    Counts sum to `len(results)`.
+    `not_dispatched_count` (I-fetch-003) counts tasks the global
+    batch budget cancelled while still QUEUED (never started) —
+    see `FetchOutcome.NOT_DISPATCHED`. It is its own bucket so the
+    invariant below stays honest.
+
+    Counts sum to `len(results)`:
+    `success_count + errored_count + timeout_count
+    + not_dispatched_count == len(results)`.
     """
 
     started_at: float
@@ -181,6 +201,7 @@ class ParallelFetchReport:
     success_count: int = 0
     errored_count: int = 0
     timeout_count: int = 0
+    not_dispatched_count: int = 0
 
 
 # ---------------------------------------------------------------------------
@@ -226,6 +247,132 @@ class ParallelFetcher(Protocol):
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
+# Global batch-budget termination guarantee (I-fetch-003 / BB5-C01 P1)
+# ---------------------------------------------------------------------------
+
+
+# The per-task START-anchored timeout guarantees a STARTED task terminates,
+# but a never-started task carries a +inf deadline: if every worker thread is
+# wedged on an abandoned (timed-out but un-cancellable) in-flight fetch, the
+# queued siblings keep their +inf deadline and the harvest loop could spin
+# forever. The GLOBAL batch budget is the backstop that guarantees
+# `parallel_fetch` ALWAYS returns in bounded time even under all-workers-wedged
+# + queued-siblings. When the budget fires, every still-remaining future is
+# recorded — started-but-unfinished as TIMEOUT (it ran, over-ran its budget),
+# never-started as NOT_DISPATCHED (it never reached the fetcher) — and the
+# harvest loop breaks.
+#
+# Operators override the budget directly with this env var (seconds). When
+# UNSET, the budget is DERIVED from `per_task_timeout` and the number of
+# submission waves: `per_task_timeout * (ceil(len(deduped)/max_workers)
+# + _BATCH_BUDGET_WAVE_SLACK)`. `ceil(len/max_workers)` is the number of waves
+# needed to run every task once if each task takes a full per_task_timeout; the
+# slack adds head-room so a healthy batch (tasks finishing well inside budget,
+# semaphore queuing) is never tripped spuriously.
+PG_PARALLEL_FETCH_BATCH_BUDGET_SECONDS_ENV = (
+    "PG_PARALLEL_FETCH_BATCH_BUDGET_SECONDS"
+)
+_BATCH_BUDGET_WAVE_SLACK = 2
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
+# ---------------------------------------------------------------------------
+# Global batch-budget derivation (I-fetch-003 / BB5-C01 P1)
+# ---------------------------------------------------------------------------
+
+
+def _derive_batch_budget_seconds(
+    *,
+    num_tasks: int,
+    max_workers: int,
+    per_task_timeout: float | None,
+) -> float | None:
+    """Derive the GLOBAL batch budget (seconds) or None to disable it.
+
+    Precedence:
+      1. Env `PG_PARALLEL_FETCH_BATCH_BUDGET_SECONDS` (positive float) wins.
+      2. Else, if `per_task_timeout` is set: derive from the wave count —
+         `per_task_timeout * (ceil(num_tasks / max_workers)
+         + _BATCH_BUDGET_WAVE_SLACK)`. The ceil term is how many sequential
+         waves it takes to run every task once if each consumes a full
+         per_task_timeout; the slack is head-room so a healthy batch is never
+         tripped spuriously.
+      3. Else (no env AND no per-task timeout): None — preserve the existing
+         "None disables timeout" contract. With no per-task budget there is no
+         natural time-scale to derive from; the caller opted out of bounding.
+
+    An env value that is empty, non-numeric, or <= 0 is ignored (falls through
+    to the derived/None path) — a malformed knob must never silently disable
+    the termination guarantee when a per_task_timeout is in force.
+    """
+    env_raw = os.environ.get(PG_PARALLEL_FETCH_BATCH_BUDGET_SECONDS_ENV)
+    if env_raw is not None and env_raw.strip():
+        try:
+            env_val = float(env_raw)
+        except ValueError:
+            env_val = None
+        if env_val is not None and env_val > 0:
+            return env_val
+
+    if per_task_timeout is None:
+        return None
+
+    waves = math.ceil(num_tasks / max_workers) + _BATCH_BUDGET_WAVE_SLACK
+    return per_task_timeout * waves
+
+
 # ---------------------------------------------------------------------------
 # Public API
 # ---------------------------------------------------------------------------
@@ -342,7 +489,14 @@ def parallel_fetch(
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
@@ -351,8 +505,10 @@ def parallel_fetch(
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
@@ -411,29 +567,85 @@ def parallel_fetch(
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
+        # I-fetch-003 (BB5-C01 P1): anchor the GLOBAL batch budget at submit.
+        batch_start = time.monotonic()
+        for idx in submit_order:
+            task = deduped[idx]
             fut = executor.submit(_run_task, idx, task)
             future_to_index[fut] = idx
-            if per_task_timeout is not None:
-                deadline_per_future[fut] = submit_now + per_task_timeout
+
+        # I-fetch-003 (BB5-C01 P1): derive the GLOBAL batch budget — the
+        # termination backstop that guarantees this call returns in bounded
+        # time even when every worker is wedged on an abandoned in-flight fetch
+        # and the queued siblings keep their +inf per-task deadline. Env wins;
+        # else derive from per_task_timeout and the wave count; else (no
+        # per-task timeout AND no env) the batch budget is disabled (None),
+        # preserving the existing "None disables timeout" contract.
+        batch_budget = _derive_batch_budget_seconds(
+            num_tasks=len(deduped),
+            max_workers=max_workers,
+            per_task_timeout=per_task_timeout,
+        )
 
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
+        batch_deadline = (
+            batch_start + batch_budget if batch_budget is not None else None
+        )
+
         while remaining and protocol_error_to_raise is None:
-            if per_task_timeout is None:
-                # No timeout — just wait for the next completion.
+            if per_task_timeout is None and batch_deadline is None:
+                # No per-task timeout AND no batch budget — just wait for the
+                # next completion (the original "None disables timeout" path).
                 done, _ = concurrent.futures.wait(
                     remaining,
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
+                # (or one that hangs), AND the GLOBAL batch deadline, are
+                # re-checked within the poll interval — the harvest never
+                # relies on a sibling completing to make progress. When there
+                # is no per-task timeout (batch budget only), the per-task
+                # deadlines are all +inf so the poll interval alone bounds the
+                # wait until the batch deadline fires.
+                now_mono = time.monotonic()
+                if per_task_timeout is None:
+                    next_deadline = float("inf")
+                else:
+                    with task_started_lock:
+                        next_deadline = min(
+                            _effective_deadline_monotonic(future_to_index[f])
+                            for f in remaining
+                        )
+                if batch_deadline is not None:
+                    next_deadline = min(next_deadline, batch_deadline)
+                wait_timeout = min(
+                    max(0.0, next_deadline - now_mono),
+                    _HARVEST_POLL_INTERVAL_SECONDS,
+                )
                 done, _ = concurrent.futures.wait(
                     remaining,
                     timeout=wait_timeout,
@@ -451,42 +663,109 @@ def parallel_fetch(
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
+                        )
+                        remaining.discard(fut)
+
+            # I-fetch-003 (BB5-C01 P1): GLOBAL batch-budget termination
+            # guarantee. If the batch deadline has passed, the batch did NOT
+            # converge in bounded time — almost always because every worker is
+            # wedged on an abandoned (timed-out but un-cancellable) in-flight
+            # fetch while distinct-host siblings sit queued behind it forever.
+            # Record EVERY still-remaining future (not just never-started ones,
+            # or the final `results_by_index[i]` reduction KeyErrors on a
+            # started-but-unfinished index) and break so the call ALWAYS
+            # returns:
+            #   - started-but-unfinished (idx in the start map) → TIMEOUT (it
+            #     ran and over-ran; same class as a normal per-task timeout).
+            #   - never-started (idx absent from the start map) → NOT_DISPATCHED
+            #     (it never reached the fetcher; distinct outcome, NOT a
+            #     mislabelled TIMEOUT).
+            if (
+                batch_deadline is not None
+                and remaining
+                and time.monotonic() > batch_deadline
+            ):
+                now_wall = time.time()
+                for fut in list(remaining):
                     idx = future_to_index[fut]
                     task = deduped[idx]
                     fut.cancel()  # best-effort
                     with task_started_lock:
-                        timeout_started_at = task_started_by_index.get(
-                            idx, submit_now,
+                        was_started = (
+                            idx in task_started_monotonic_by_index
+                        )
+                        started_wall = task_started_wall_by_index.get(
+                            idx, now_wall,
+                        )
+                    if was_started:
+                        results_by_index[idx] = FetchResultRecord(
+                            source_url=task.source_url,
+                            backend_id=task.backend_id,
+                            outcome=FetchOutcome.TIMEOUT,
+                            payload=None,
+                            content_type=None,
+                            fetch_status_code=None,
+                            error="per-task timeout exceeded",
+                            started_at=started_wall,
+                            finished_at=now_wall,
+                            task_metadata=task.task_metadata,
+                        )
+                    else:
+                        results_by_index[idx] = FetchResultRecord(
+                            source_url=task.source_url,
+                            backend_id=task.backend_id,
+                            outcome=FetchOutcome.NOT_DISPATCHED,
+                            payload=None,
+                            content_type=None,
+                            fetch_status_code=None,
+                            error=(
+                                "never dispatched: parallel-fetch batch "
+                                "budget exceeded (worker pool starved by "
+                                "abandoned in-flight tasks)"
+                            ),
+                            started_at=now_wall,
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
                     remaining.discard(fut)
-                    deadline_per_future.pop(fut, None)
+                break
 
         if protocol_error_to_raise is not None:
             for other_fut in remaining:
@@ -511,6 +790,9 @@ def parallel_fetch(
     success = sum(1 for r in results if r.outcome == FetchOutcome.SUCCESS)
     errored = sum(1 for r in results if r.outcome == FetchOutcome.ERRORED)
     timed_out = sum(1 for r in results if r.outcome == FetchOutcome.TIMEOUT)
+    not_dispatched = sum(
+        1 for r in results if r.outcome == FetchOutcome.NOT_DISPATCHED
+    )
 
     return ParallelFetchReport(
         started_at=started_at,
@@ -519,15 +801,22 @@ def parallel_fetch(
         success_count=success,
         errored_count=errored,
         timeout_count=timed_out,
+        not_dispatched_count=not_dispatched,
     )
 
 
 def report_to_exit_code(report: ParallelFetchReport) -> int:
     """Map outcome to CI exit code.
 
-    Convention: any errored OR timeout → 1; all-success or
-    empty → 0.
+    Convention: any errored OR timeout OR not-dispatched → 1;
+    all-success or empty → 0. NOT_DISPATCHED (I-fetch-003) is a
+    starvation failure — a batch that never ran its queued tasks
+    must NOT report success, so it is treated the same as TIMEOUT.
     """
-    if report.errored_count > 0 or report.timeout_count > 0:
+    if (
+        report.errored_count > 0
+        or report.timeout_count > 0
+        or report.not_dispatched_count > 0
+    ):
         return 1
     return 0
diff --git a/src/polaris_graph/retrieval/live_retriever.py b/src/polaris_graph/retrieval/live_retriever.py
index 874d5675..9e9867e7 100644
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
@@ -2842,6 +2907,53 @@ def run_live_retrieval(
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
+        # I-fetch-003 (#1175): a NOT_DISPATCHED task (batch-budget starvation)
+        # never ran — it is NOT a completion. Subtract it alongside timeouts so
+        # a starved batch reports a LOW completion rate (else the AC3 diagnostic
+        # this issue added would paint a starved run as near-fully-complete).
+        _parallel_completion_rate = (
+            (
+                _submitted
+                - parallel_report.timeout_count
+                - parallel_report.not_dispatched_count
+            ) / _submitted
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
@@ -3109,4 +3221,8 @@ def run_live_retrieval(
         candidates_total=_candidates_total,
         candidates_processed=_candidates_processed,
         journal_metadata_sidecar=(_journal_sidecar if _journal_only_on else None),
+        fetch_success_rate=_fetch_success_rate,
+        parallel_completion_rate=_parallel_completion_rate,
+        fetch_workers=_fetch_workers,
+        distinct_hosts=_distinct_hosts,
     )
