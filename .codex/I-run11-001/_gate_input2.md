HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings. Reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, force-APPROVE on remaining non-P0/P1.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

Return EXACTLY this schema, nothing else:
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

# Diff review iter 2 — I-run11-001 / #1042: parallelize 4-role eval claim COMPUTE

Your iter-1 P1/P2 are addressed; verify each fix and raise only NEW/CONTINUING real blockers.

**Your iter-1 P1.2 (copy_context() taken inside the worker -> parent _PATHB_SINK absent -> capture no-ops -> completeness fails workers>1).** FIXED: the per-claim snapshot is now taken on the PARENT at submit: `pool.submit(_compute_one, idx, claim, contextvars.copy_context())` (line ~323); the worker runs `worker_ctx.run(_run)` and `_run` does reset_run_cost()+pipeline+return current_run_cost(). New test_pathb_sink_visible_in_workers registers the sink as pathB_runner does, runs workers=4, asserts the PARENT sink got ALL n*roles captures (proven regression-catching: 0 with the old bug, 16/16 with the fix). Confirm copy_context() on the parent AFTER register_pathB_capture() captures the _SINK list by reference and worker writes are visible at the parent.

**Your iter-1 P1.1 (cap enforced after draining all claims).** FIXED: the as_completed loop now does `_add_run_cost(delta); check_run_budget(0)` per completion (line ~334); manual pool + `shutdown(wait=False, cancel_futures=True)` on breach/any exception (line ~349) -> overspend bounded to in-flight (~workers-1). The duplicate cost re-add was REMOVED from run_four_role_evaluation's reduction loop (reduction stays parent-only, input-order). New test_cap_trip_is_bounded_in_flight proves bounded (old drain-all behavior fails "ran 12/12"; fix passes a bounded prefix). Confirm no double-count and the reduction loop no longer touches cost.

**Your iter-1 P2s.** P2.2 cancel-on-fail (except BaseException -> shutdown(cancel_futures)+raise); P2.3 four_role_compute_progress.json written per completion (mid-compute monitorability); P2.1 documented as parity with the existing seam-timeout cost tradeoff. Verify.

Tests: tests/roles/test_seam_parallel.py 8/8; 4-role regression 330 passed / 0 new failures; sequential fast path byte-equivalent.

## THE DIFF (iter-1 commit + iter-2 fix; both on the branch)
```diff
diff --git a/src/polaris_graph/roles/sweep_integration.py b/src/polaris_graph/roles/sweep_integration.py
index 587ca90e..407b925f 100644
--- a/src/polaris_graph/roles/sweep_integration.py
+++ b/src/polaris_graph/roles/sweep_integration.py
@@ -35,11 +35,21 @@ Fail-closed contract (Codex P2 directives, binding):
 
 from __future__ import annotations
 
+import concurrent.futures
+import contextvars
 import json
+import os
 from dataclasses import dataclass, field
 from pathlib import Path
 from typing import Callable
 
+from src.polaris_graph.llm.openrouter_client import (
+    BudgetExceededError,
+    _add_run_cost,
+    check_run_budget,
+    current_run_cost,
+    reset_run_cost,
+)
 from src.polaris_graph.roles.release_policy import (
     CoverageLedger,
     D8ClaimRow,
@@ -48,7 +58,10 @@ from src.polaris_graph.roles.release_policy import (
     apply_d8_release_policy,
     load_d8_policy_config,
 )
-from src.polaris_graph.roles.role_pipeline import run_claim_pipeline
+from src.polaris_graph.roles.role_pipeline import (
+    ClaimPipelineResult,
+    run_claim_pipeline,
+)
 from src.polaris_graph.roles.role_transport import (
     EvidenceDocument,
     RoleCallRecord,
@@ -62,6 +75,22 @@ _VERDICT_VERIFIED = "VERIFIED"
 # The three role slots the per-claim pipeline expects in its `model_slugs` map.
 _REQUIRED_ROLE_SLUG_KEYS = ("mirror", "sentinel", "judge")
 
+# I-run11-001 (#1042): bounded per-claim COMPUTE parallelism for the 4-role seam. The per-claim
+# Mirror->Sentinel->Judge pipeline is independent across claims (each `run_claim_pipeline` builds
+# its OWN `RecordingTransport`), so the COMPUTE half can run in a small thread pool while ALL
+# reduction + persistence (D8 policy, coverage credit, KG write, run-budget cap) stays on the
+# PARENT thread in ORIGINAL claim order (Codex Path-B SAFE design, .codex/I-run11-seam). At the
+# benchmark stage (xhigh reasoning, minutes/claim) this is what makes the seam finish in time;
+# run 10 died on the sequential operational failure mode. LAW VI: worker count from env only.
+# `1` (or a single claim) preserves the EXACT sequential behaviour, including the live per-call
+# budget enforcement inside `RecordingTransport.complete()`.
+_CLAIM_WORKERS = max(1, int(os.getenv("PG_FOUR_ROLE_CLAIM_WORKERS", "6")))
+
+# I-run11-001 (#1042) Codex iter-2 P2.3: tiny on-disk progress marker the PARALLEL compute writes
+# after EACH claim completes ({"done": k, "total": n}), so a hung mid-compute is visible on disk
+# DURING compute — the role_call_log only grows during the later, parent-only reduction.
+FOUR_ROLE_COMPUTE_PROGRESS_FILENAME = "four_role_compute_progress.json"
+
 
 @dataclass
 class FourRoleClaim:
@@ -169,6 +198,170 @@ def build_evaluator_agrees_map(
     return agrees_map
 
 
+def _write_role_call_log(path: Path, role_call_log: list[dict]) -> None:
+    """Write the per-role-call reasoning log as one sorted-key JSON object per line.
+
+    I-run11-001 (#1042): factored out of `run_four_role_evaluation` so the SAME serialization is
+    used by both the INCREMENTAL per-claim write (mid-run monitorability) and the final idempotent
+    write. Byte-identical to the prior inline `write_text` (`ensure_ascii=False, sort_keys=True`),
+    so a partial file rewritten on the next claim is just a longer prefix of the same content.
+    """
+    path.write_text(
+        "".join(
+            json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n"
+            for entry in role_call_log
+        ),
+        encoding="utf-8",
+    )
+
+
+def _compute_claim_results(
+    transport: RoleTransport,
+    *,
+    claims: list[FourRoleClaim],
+    model_slugs: dict[str, str],
+    timestamp: str,
+    run_dir: Path,
+) -> list[tuple[ClaimPipelineResult, float | None]]:
+    """COMPUTE the per-claim 4-role pipeline for every claim, returning results BY INPUT INDEX.
+
+    I-run11-001 (#1042), Codex Path-B SAFE design (.codex/I-run11-seam). This is the ONLY half
+    that runs the (already-paid) verifier calls; it makes NO reduction decision — the parent
+    reduces in input order. Each element is `(ClaimPipelineResult, cost_delta)` for `claims[idx]`,
+    where:
+
+      * SEQUENTIAL (`_CLAIM_WORKERS == 1` or a single claim): `run_claim_pipeline` is called
+        DIRECTLY on the parent thread (no copied context, no `reset_run_cost`), so
+        `RecordingTransport.complete()` enforces the LIVE per-call run budget on the parent
+        `_RUN_COST_CTX` EXACTLY as today. `cost_delta is None` signals the parent "already
+        accounted — do not re-add" (byte-equivalence with the pre-#1042 behaviour).
+
+      * PARALLEL: each claim runs inside its OWN `contextvars.copy_context()` snapshot that is taken
+        ON THE PARENT THREAD BEFORE submit (Codex iter-2 P1.2 — copying inside the worker would
+        snapshot the worker's EMPTY default context, so the parent Path-B capture sink
+        `pathB_capture._SINK` / `_ROLE` registered by `pathB_runner` on the PARENT would be ABSENT
+        and verifier capture would no-op, failing post-run completeness when workers>1). Each claim
+        gets its OWN copy (never one shared copy across concurrent workers — a copy carries the
+        worker's isolated `_RUN_COST_CTX` AND the parent's `_SINK` reference). The worker
+        `reset_run_cost()`s its copy, runs the pipeline, and returns `current_run_cost()` as
+        `cost_delta`; the PARENT re-adds it to the single run counter and enforces the cap DURING
+        compute (Codex iter-2 P1.1) so overspend is bounded to the workers in-flight at breach
+        (~workers-1), not all claims. The pathB capture `_SINK` is shared BY REFERENCE through the
+        copied context (atomic `list.append`), so verifier captures land at the PARENT sink for the
+        M4 gate — it is NOT isolated. A worker exception PROPAGATES (fail closed; no `except: pass`).
+    """
+    n = len(claims)
+
+    def _compute_one(
+        idx: int, claim: FourRoleClaim, worker_ctx: contextvars.Context
+    ) -> tuple[int, ClaimPipelineResult, float]:
+        def _run() -> tuple[ClaimPipelineResult, float]:
+            # Isolate THIS claim's verifier spend in the copied context so the parent can re-add a
+            # clean per-claim delta and enforce the cap deterministically at the claim boundary.
+            # `reset_run_cost()` zeroes ONLY this copy's `_RUN_COST_CTX`; the parent's `_SINK` /
+            # `_ROLE` references carried by the same copy are untouched, so verifier capture lands
+            # at the parent sink.
+            reset_run_cost()
+            res = run_claim_pipeline(
+                transport,
+                claim_id=claim.claim_id,
+                claim=claim.claim_text,
+                evidence_documents=claim.evidence_documents,
+                severity=claim.severity,
+                s0_categories=claim.s0_categories,
+                model_slugs=model_slugs,
+                timestamp=timestamp,
+            )
+            return res, current_run_cost()
+
+        # Run inside the PARENT-captured context snapshot (P1.2): the worker executes `_run` under
+        # the parent's Path-B capture state, not the worker thread's empty default context.
+        result, delta = worker_ctx.run(_run)
+        return idx, result, delta
+
+    # SEQUENTIAL fast path: byte-equivalent to the pre-#1042 loop (live per-call budget preserved,
+    # cost_delta None so the parent does not re-account). A single claim also takes this path (a
+    # thread pool for one item is pure overhead).
+    if _CLAIM_WORKERS == 1 or n <= 1:
+        out: list[tuple[ClaimPipelineResult, float | None]] = []
+        for claim in claims:
+            result = run_claim_pipeline(
+                transport,
+                claim_id=claim.claim_id,
+                claim=claim.claim_text,
+                evidence_documents=claim.evidence_documents,
+                severity=claim.severity,
+                s0_categories=claim.s0_categories,
+                model_slugs=model_slugs,
+                timestamp=timestamp,
+            )
+            out.append((result, None))
+        return out
+
+    # PARALLEL path (Codex iter-2 P1.1 + P1.2): enforce the run budget DURING compute, not after the
+    # whole pool drains. Each claim is submitted with its OWN parent-captured context snapshot so the
+    # worker inherits the Path-B capture sink/role registered on the parent. We iterate
+    # `as_completed` and, for each completed future, re-add the worker's per-claim verifier delta to
+    # the SINGLE parent run counter and re-check the cap — so a cumulative cap breach raises after
+    # only ~(workers-in-flight) claims have spent, NOT all n. The pool is managed MANUALLY (not via
+    # `with`, whose `__exit__` waits for ALL pending futures) so on a breach / worker exception we
+    # `shutdown(wait=False, cancel_futures=True)` to cancel still-queued claims, then re-raise
+    # (P2.2 cancel-on-fail).
+    #
+    # P2.1 (aborted-run cost under-accounting — documented, not over-engineered): on a worker
+    # exception the worker's partial paid spend lives in the worker's isolated copied context and is
+    # NOT reconciled into the parent counter. This is the SAME accepted tradeoff the seam-timeout
+    # wrapper documents (run_honest_sweep_r3.py ~L4587-4596: in-flight verifier cost on the
+    # held/aborted path is not reconciled) — prompt fail-closed termination outranks exact accounting
+    # on an already-aborted run, and the operator authorized the spend.
+    computed: list[tuple[ClaimPipelineResult, float | None] | None] = [None] * n
+    progress_path = run_dir / FOUR_ROLE_COMPUTE_PROGRESS_FILENAME
+    done = 0
+    pool = concurrent.futures.ThreadPoolExecutor(max_workers=_CLAIM_WORKERS)
+    try:
+        futures = [
+            pool.submit(_compute_one, idx, claim, contextvars.copy_context())
+            for idx, claim in enumerate(claims)
+        ]
+        for future in concurrent.futures.as_completed(futures):
+            # `future.result()` re-raises any worker exception (fail closed) — handled below.
+            idx, result, delta = future.result()
+            computed[idx] = (result, delta)
+            # Enforce the run budget DURING compute (P1.1): thread this claim's verifier spend into
+            # the SINGLE parent run counter and re-check the cap immediately. A `BudgetExceededError`
+            # here bounds overspend to the workers in-flight at the breach (~workers-1), not all n.
+            if delta is not None:
+                _add_run_cost(delta)
+                check_run_budget(0)  # raises BudgetExceededError if the cap is now exceeded.
+            # P2.3: write a tiny on-disk progress marker after each completion so a hung compute is
+            # visible on disk DURING compute (the role_call_log only grows during the later, parent-
+            # only reduction). Parent-only write — never inside a worker.
+            done += 1
+            progress_path.write_text(
+                json.dumps({"done": done, "total": n}, sort_keys=True) + "\n",
+                encoding="utf-8",
+            )
+    except BaseException:
+        # On ANY failure (BudgetExceededError from the cap OR a propagated worker exception) cancel
+        # still-pending claims and tear the pool down NON-BLOCKING (P2.2), then re-raise so the
+        # existing budget-abort / fail-closed path in run_four_role_evaluation handles it. No
+        # `except: pass` — the error always propagates.
+        pool.shutdown(wait=False, cancel_futures=True)
+        raise
+    else:
+        pool.shutdown(wait=True)
+
+    # Defensive: every index must be filled (a None here would mean a future silently dropped — a
+    # real bug, never a vacuous pass). Fail loud rather than reduce a partial result set.
+    for idx, item in enumerate(computed):
+        if item is None:
+            raise RuntimeError(
+                f"run_four_role_evaluation: claim index {idx} produced no result from the "
+                f"compute pool (fail-closed — a dropped future must never reduce silently)."
+            )
+    return [item for item in computed if item is not None]
+
+
 def run_four_role_evaluation(
     transport: RoleTransport,
     *,
@@ -261,6 +454,26 @@ def run_four_role_evaluation(
     # for line-by-line review. `reasoning` is its OWN field — NEVER concatenated into the verdict.
     role_call_log: list[dict] = []
 
+    # I-run11-001 (#1042): COMPUTE the per-claim pipeline (possibly in parallel), then REDUCE on
+    # the parent thread in ORIGINAL claim order. `computed[idx]` holds `(ClaimPipelineResult,
+    # cost_delta)` for `claims[idx]`; `cost_delta` is the per-claim verifier spend captured INSIDE
+    # the worker's isolated `_RUN_COST_CTX` (parallel path) or None (sequential path, where
+    # RecordingTransport already enforced the LIVE per-call budget on the parent counter).
+    # Codex iter-2 P1.1: the PARALLEL path now ENFORCES the run-budget cap DURING compute (each
+    # claim's delta is re-added to the parent counter and the cap re-checked as its future
+    # completes), so a cap breach raises after only ~(workers-in-flight) claims have spent — the
+    # reduction below NO LONGER re-adds `cost_delta` (it would double-count). `cost_delta` is kept
+    # in the returned tuples for audit only.
+    computed: list[tuple[ClaimPipelineResult, float | None]] = _compute_claim_results(
+        transport,
+        claims=claims,
+        model_slugs=model_slugs,
+        timestamp=timestamp,
+        run_dir=run_dir,
+    )
+
+    role_calls_path = run_dir / FOUR_ROLE_ROLE_CALLS_FILENAME
+
     # I-meta-002-q1d (#948): campaign-scoped KG when given, else per-question run_dir (default).
     kg_store = (
         VerifiedClaimGraphStore(db_path=campaign_kg_db)
@@ -268,17 +481,16 @@ def run_four_role_evaluation(
         else VerifiedClaimGraphStore(run_dir=run_dir)
     )
     try:
-        for claim in claims:
-            result = run_claim_pipeline(
-                transport,
-                claim_id=claim.claim_id,
-                claim=claim.claim_text,
-                evidence_documents=claim.evidence_documents,
-                severity=claim.severity,
-                s0_categories=claim.s0_categories,
-                model_slugs=model_slugs,
-                timestamp=timestamp,
-            )
+        # Reduce in INPUT order (zip over claims + the index-ordered `computed` list). Completion
+        # order NEVER drives any reduction — the parallel path collected results BY INDEX, so this
+        # is byte-identical to the sequential reduction regardless of which claim finished first.
+        # Codex iter-2 P1.1: the run-budget cap is now enforced DURING compute inside
+        # `_compute_claim_results` (parallel path) — the per-claim `cost_delta` was ALREADY re-added
+        # to the parent counter and the cap re-checked there. This reduction is therefore PARENT-only
+        # and budget-NEUTRAL: it touches ONLY d8_rows / all_records / final_verdicts / role_call_log /
+        # coverage / kg_store.write_claim / the incremental log. `cost_delta` is retained in the tuple
+        # for audit but is NOT re-added here (re-adding would double-count the verifier spend).
+        for claim, (result, _cost_delta) in zip(claims, computed):
             d8_rows.append(result.d8_row)
             all_records.extend(result.records)
             final_verdicts[claim.claim_id] = result.final_verdict
@@ -297,6 +509,12 @@ def run_four_role_evaluation(
                     }
                 )
 
+            # I-run11-001 (#1042): INCREMENTALLY persist the role-call log after EACH claim is
+            # reduced (rewrite the whole file in claim order — small, fine) so a mid-run hang is
+            # monitorable on disk instead of the log only landing after the full loop. The final
+            # write below is kept (idempotent: it rewrites the same complete content).
+            _write_role_call_log(role_calls_path, role_call_log)
+
             # Coverage credit ONLY on a VERIFIED final verdict, against the CANONICAL required
             # ids this claim covers — a dropped/UNSUPPORTED claim adds nothing (denominator is
             # the fixed required set, so this can only ever lower the achieved fraction).
@@ -305,7 +523,8 @@ def run_four_role_evaluation(
 
             # Snowball KG: persist EVERY outcome (audit); only VERIFIED rows are reusable
             # (anti-poisoning is enforced inside the store). role_verdicts records the raw
-            # Mirror/Sentinel/Judge signals for provenance.
+            # Mirror/Sentinel/Judge signals for provenance. KG writes stay PARENT-only (single
+            # SQLite connection) — never inside a worker (Codex Path-B risk #2).
             kg_store.write_claim(
                 claim_text=claim.claim_text,
                 claim_id=claim.claim_id,
@@ -332,14 +551,9 @@ def run_four_role_evaluation(
 
     # I-meta-002-q1b (#939): persist the per-role-call reasoning log next to the run — one JSON
     # object per line, `reasoning` in its own field, NEVER mixed into the verdict. Reviewable
-    # line-by-line alongside the generator's reasoning_trace.jsonl.
-    (run_dir / FOUR_ROLE_ROLE_CALLS_FILENAME).write_text(
-        "".join(
-            json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n"
-            for entry in role_call_log
-        ),
-        encoding="utf-8",
-    )
+    # line-by-line alongside the generator's reasoning_trace.jsonl. (Kept as the final write even
+    # though I-run11-001 also writes incrementally above — idempotent same-content rewrite.)
+    _write_role_call_log(role_calls_path, role_call_log)
 
     # The D8 threshold is loaded from config (LAW VI, pure file read — no network).
     config = load_d8_policy_config(d8_config_path)
diff --git a/tests/roles/test_seam_parallel.py b/tests/roles/test_seam_parallel.py
new file mode 100644
index 00000000..27a546de
--- /dev/null
+++ b/tests/roles/test_seam_parallel.py
@@ -0,0 +1,603 @@
+"""I-run11-001 (#1042) — the 4-role seam parallelizes the per-claim COMPUTE while keeping ALL
+reduction + persistence deterministic on the parent thread in INPUT order. Offline, fake
+transport, NO network, NO real LLM, NO spend.
+
+Codex Path-B SAFE design (`.codex/I-run11-seam/codex_decision.txt`): the per-claim
+Mirror->Sentinel->Judge pipeline is independent across claims (each `run_claim_pipeline` builds
+its OWN `RecordingTransport`), so the COMPUTE half can run in a small thread pool while the D8
+policy, coverage credit, KG write, run-budget cap, and `four_role_role_calls.jsonl` write all
+stay on the PARENT thread in ORIGINAL claim order.
+
+These tests prove the five acceptance criteria:
+  (a) output order (final_verdicts / d8_rows / role_call_log) == INPUT order regardless of
+      COMPLETION order — the fake sleeps INVERSELY to index (claim 0 longest) with workers >=
+      len(claims) so completion order reverses input order, yet the reduction stays input-ordered.
+  (b) parallel total cost == sequential total cost AND the SAME PG_MAX_COST_PER_RUN cap trips
+      (BudgetExceededError) at the same accumulated spend — the tipping cost is on the LAST
+      pipeline call (Judge) of the tripping claim, so sequential mid-claim trip and parallel
+      claim-boundary trip both fire at total = sum(1..K).
+  (c) coverage credited ONLY on VERIFIED.
+  (d) role_call_log complete (one block of records per claim, in INPUT order).
+  (e) PG_FOUR_ROLE_CLAIM_WORKERS=1 path matches the multi-worker result.
+
+Worker-count control: `_CLAIM_WORKERS` is read from env AT IMPORT, so tests
+`monkeypatch.setattr(sweep_integration, "_CLAIM_WORKERS", n)` — the same module-attribute pattern
+`test_four_role_budget_cap.py` uses for `PG_MAX_COST_PER_RUN` (an in-test env var would NOT take).
+The cap is likewise patched via `monkeypatch.setattr(openrouter_client, "PG_MAX_COST_PER_RUN", x)`
+(import-time constant, NOT re-read from env), and `reset_run_cost()` is called at the top of every
+cost test because `_RUN_COST_CTX` persists across synchronous tests in one process.
+
+Thread-safety of the fake: the shared `complete()` counter is guarded by a `threading.Lock` (the
+parallel path calls it from several worker threads at once); a plain `+= 1` would race.
+"""
+
+from __future__ import annotations
+
+import json
+import re
+import sqlite3
+import threading
+import time
+
+import pytest
+
+import src.polaris_graph.benchmark.pathB_capture as pathB_capture
+import src.polaris_graph.llm.openrouter_client as openrouter_client
+from src.polaris_graph.llm.openrouter_client import BudgetExceededError
+from src.polaris_graph.roles import sweep_integration
+from src.polaris_graph.roles.mirror_contract import CitationSpan
+from src.polaris_graph.roles.release_policy import CoverageLedger
+from src.polaris_graph.roles.role_transport import (
+    EvidenceDocument,
+    RoleRequest,
+    RoleResponse,
+)
+from src.polaris_graph.roles.sweep_integration import (
+    FOUR_ROLE_ROLE_CALLS_FILENAME,
+    FourRoleClaim,
+    run_four_role_evaluation,
+)
+
+_MODEL_SLUGS = {
+    "mirror": "cohere/command-a-plus",
+    "sentinel": "ibm-granite/granite-guardian-4.1-8b",
+    "judge": "qwen/qwen3.6-35b-a3b",
+}
+_TIMESTAMP = "2026-05-29T00:00:00Z"
+_REQUIRED_S0 = ["contraindications"]
+
+
+# A per-claim marker embedded in BOTH the claim text and the evidence text so the fake can recover
+# a claim's index from ANY role call: the Mirror pass-1 + Sentinel calls carry it via the
+# `documents` payload, and the Judge call carries it via its prompt (claim + evidence rendered in).
+_CLAIM_IDX_RE = re.compile(r"\[\[CLAIMIDX=(\d+)\]\]")
+
+
+class _DelayedFakeTransport:
+    """Deterministic, thread-safe fake `RoleTransport` keyed on a per-claim index marker.
+
+    Each claim's claim_text AND evidence text carry `[[CLAIMIDX=<idx>]]`; the fake recovers `<idx>`
+    from the request's `documents` payload (Mirror pass-1, Sentinel) OR its `prompt` (Judge — the
+    claim + evidence are rendered into the prompt by `build_judge_request`). The Mirror PASS-2 call
+    carries NEITHER (its prompt is a fixed string, no documents), so its index is None and it gets
+    `usage=None` — harmless for these tests, which never place usage on the Mirror pass-2 call.
+
+    On the Mirror PASS-1 call (the FIRST call of each claim) it sleeps `delay_per_index[idx]` so a
+    larger early-index delay makes COMPLETION order reverse INPUT order. Verdicts are per-index
+    deterministic:
+
+      * `judge_verdict_by_index[idx]` -> the Judge token for claim idx (default "VERIFIED").
+      * `sentinel_grounded_by_index[idx]` -> Sentinel GROUNDED (`no`) vs UNGROUNDED (`yes`).
+      * `usage_by_index_role[(idx, role)]` -> the per-call `usage` dict driving cost (cap tests).
+
+    `completions` (lock-guarded) counts in-process completions; NEVER a socket.
+    """
+
+    def __init__(
+        self,
+        *,
+        delay_per_index: dict[int, float] | None = None,
+        judge_verdict_by_index: dict[int, str] | None = None,
+        sentinel_grounded_by_index: dict[int, bool] | None = None,
+        usage_by_index_role: dict[tuple[int, str], dict] | None = None,
+    ) -> None:
+        self._delay = delay_per_index or {}
+        self._judge = judge_verdict_by_index or {}
+        self._sentinel_grounded = sentinel_grounded_by_index or {}
+        self._usage = usage_by_index_role or {}
+        self._lock = threading.Lock()
+        self.completions = 0
+
+    @staticmethod
+    def _index_from_request(request: RoleRequest) -> int | None:
+        """Recover the claim index from the `[[CLAIMIDX=<idx>]]` marker in the documents or prompt.
+
+        Searches the `documents` payload first (Mirror pass-1, Sentinel) then the prompt (Judge).
+        Returns None when neither carries the marker (the Mirror pass-2 call), which the tests
+        treat as a no-usage call.
+        """
+        documents = (request.params or {}).get("documents") or []
+        for doc in documents:
+            m = _CLAIM_IDX_RE.search(doc.get("text", "") or "")
+            if m:
+                return int(m.group(1))
+        if request.prompt:
+            m = _CLAIM_IDX_RE.search(request.prompt)
+            if m:
+                return int(m.group(1))
+        return None
+
+    def complete(self, request: RoleRequest) -> RoleResponse:
+        with self._lock:
+            self.completions += 1
+
+        if request.role == "mirror":
+            if "pass2_input" in (request.params or {}):
+                content_hash = request.params["pass2_input"]["content_hash"]
+                payload = {"content_hash": content_hash, "classification": "supported"}
+                return RoleResponse(
+                    raw_text=json.dumps(payload),
+                    served_model=request.model_slug,
+                    usage=None,  # Mirror pass-2 carries no index marker; tests place no usage here.
+                )
+            # Pass-1: this is the FIRST call of the claim — sleep here so completion order can
+            # reverse input order. The citation binds the claim's `doc-<idx>` doc_id.
+            idx = self._index_from_request(request)
+            assert idx is not None, "pass-1 mirror request must carry the claim-index marker"
+            delay = self._delay.get(idx, 0.0)
+            if delay:
+                time.sleep(delay)
+            return RoleResponse(
+                raw_text="grounded answer",
+                served_model=request.model_slug,
+                citations=[CitationSpan(span_start=0, span_end=8, doc_ids=(f"doc-{idx}",))],
+                usage=self._usage.get((idx, "mirror")),
+            )
+
+        idx = self._index_from_request(request)
+        if request.role == "sentinel":
+            grounded = self._sentinel_grounded.get(idx, True)
+            score = "no" if grounded else "yes"
+            return RoleResponse(
+                raw_text=f"<score>{score}</score>",
+                served_model=request.model_slug,
+                usage=self._usage.get((idx, "sentinel")),
+            )
+        if request.role == "judge":
+            verdict = self._judge.get(idx, "VERIFIED")
+            return RoleResponse(
+                raw_text=verdict,
+                served_model=request.model_slug,
+                usage=self._usage.get((idx, "judge")),
+            )
+        raise AssertionError(f"unexpected role {request.role!r}")
+
+
+def _claim(idx: int, *, covers=None, s0=None) -> FourRoleClaim:
+    """Build claim `idx`. The `[[CLAIMIDX=<idx>]]` marker rides in BOTH the claim text and the
+    evidence text so the fake can recover the index from any role call (documents OR judge prompt);
+    the citation binds `doc-<idx>`."""
+    return FourRoleClaim(
+        claim_id=f"claim-{idx}",
+        claim_text=f"The dose is {idx}.0 mg. [[CLAIMIDX={idx}]]",
+        evidence_documents=[
+            EvidenceDocument(
+                doc_id=f"doc-{idx}",
+                text=f"The trial reported a {idx}.0 mg dose. [[CLAIMIDX={idx}]]",
+            )
+        ],
+        severity="S0",
+        s0_categories=s0 if s0 is not None else ["contraindications"],
+        covered_element_ids=covers if covers is not None else [f"elem-{idx}"],
+    )
+
+
+def _run(transport, claims, *, run_dir, ledger):
+    return run_four_role_evaluation(
+        transport,
+        claims=claims,
+        run_dir=run_dir,
+        timestamp=_TIMESTAMP,
+        coverage_ledger=ledger,
+        required_s0_categories=_REQUIRED_S0,
+        model_slugs=_MODEL_SLUGS,
+        rewrite_already_attempted=True,
+    )
+
+
+def _read_role_call_log(run_dir) -> list[dict]:
+    path = run_dir / FOUR_ROLE_ROLE_CALLS_FILENAME
+    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
+    return [json.loads(ln) for ln in lines]
+
+
+# === (a) + (d) output/role_call_log order == INPUT order regardless of COMPLETION order ========
+def test_output_order_is_input_order_under_reversed_completion(monkeypatch, tmp_path):
+    # 4 workers, 4 claims; claim 0 sleeps LONGEST so it COMPLETES LAST (completion order is the
+    # REVERSE of input order). The reduction must still be input-ordered.
+    monkeypatch.setattr(sweep_integration, "_CLAIM_WORKERS", 4)
+    n = 4
+    claims = [_claim(i, covers=[f"elem-{i}"]) for i in range(n)]
+    ledger = CoverageLedger(required_element_ids=[f"elem-{i}" for i in range(n)])
+    # Decreasing delay with index -> claim 0 finishes LAST, claim n-1 finishes FIRST.
+    delays = {i: 0.05 * (n - i) for i in range(n)}
+    transport = _DelayedFakeTransport(delay_per_index=delays)
+
+    result = _run(transport, claims, run_dir=tmp_path, ledger=ledger)
+
+    # (a) final_verdicts iteration order == input order (dict preserves insertion order).
+    assert list(result.final_verdicts.keys()) == [f"claim-{i}" for i in range(n)]
+    # all_records are appended in input claim order: the per-claim record blocks (asserted from the
+    # role-call log below) partition the served-identity trail in input order.
+    # (d) role_call_log: one contiguous block per claim, claims in INPUT order.
+    log = _read_role_call_log(tmp_path)
+    claim_order_in_log = []
+    for entry in log:
+        if not claim_order_in_log or claim_order_in_log[-1] != entry["claim_id"]:
+            claim_order_in_log.append(entry["claim_id"])
+    assert claim_order_in_log == [f"claim-{i}" for i in range(n)]
+    # Each claim contributes a CONTIGUOUS block (mirror x2, sentinel, judge == 4 records) and the
+    # blocks do not interleave.
+    from itertools import groupby
+
+    block_ids = [cid for cid, _ in groupby(e["claim_id"] for e in log)]
+    assert block_ids == [f"claim-{i}" for i in range(n)], "claim blocks must not interleave"
+    per_claim_counts = {cid: sum(1 for e in log if e["claim_id"] == cid) for cid in block_ids}
+    assert all(c == 4 for c in per_claim_counts.values()), per_claim_counts
+
+
+# === (e) PG_FOUR_ROLE_CLAIM_WORKERS=1 result == multi-worker result =============================
+def test_sequential_path_matches_multi_worker(monkeypatch, tmp_path):
+    n = 3
+    ledger_req = [f"elem-{i}" for i in range(n)]
+    # Mixed verdicts so the comparison is non-trivial: claim 1 is Sentinel-UNGROUNDED -> UNSUPPORTED.
+    judge = {0: "VERIFIED", 1: "VERIFIED", 2: "VERIFIED"}
+    sentinel = {0: True, 1: False, 2: True}
+
+    def run_with_workers(workers, sub_dir):
+        monkeypatch.setattr(sweep_integration, "_CLAIM_WORKERS", workers)
+        run_dir = tmp_path / sub_dir
+        run_dir.mkdir()
+        claims = [_claim(i, covers=[f"elem-{i}"]) for i in range(n)]
+        ledger = CoverageLedger(required_element_ids=list(ledger_req))
+        transport = _DelayedFakeTransport(
+            judge_verdict_by_index=judge, sentinel_grounded_by_index=sentinel
+        )
+        return _run(transport, claims, run_dir=run_dir, ledger=ledger), run_dir
+
+    seq, seq_dir = run_with_workers(1, "seq")
+    par, par_dir = run_with_workers(4, "par")
+
+    assert seq.final_verdicts == par.final_verdicts
+    assert seq.final_verdicts == {
+        "claim-0": "VERIFIED",
+        "claim-1": "UNSUPPORTED",
+        "claim-2": "VERIFIED",
+    }
+    # Gap is a plain dataclass -> structural equality; the gaps list must match in content + order.
+    assert seq.gaps == par.gaps
+    assert seq.release_allowed == par.release_allowed
+    assert seq.coverage_fraction == pytest.approx(par.coverage_fraction)
+    # The role-call logs are byte-identical between the two paths (input-ordered, same content).
+    assert _read_role_call_log(seq_dir) == _read_role_call_log(par_dir)
+
+
+# === (c) coverage credited ONLY on VERIFIED (parallel path) =====================================
+def test_coverage_credit_only_on_verified_parallel(monkeypatch, tmp_path):
+    monkeypatch.setattr(sweep_integration, "_CLAIM_WORKERS", 4)
+    n = 2
+    claims = [_claim(i, covers=[f"elem-{i}"]) for i in range(n)]
+    ledger = CoverageLedger(required_element_ids=[f"elem-{i}" for i in range(n)])
+    # claim-0 VERIFIED, claim-1 Sentinel-UNGROUNDED -> UNSUPPORTED -> elem-1 uncovered.
+    transport = _DelayedFakeTransport(
+        judge_verdict_by_index={0: "VERIFIED", 1: "VERIFIED"},
+        sentinel_grounded_by_index={0: True, 1: False},
+    )
+    result = _run(transport, claims, run_dir=tmp_path, ledger=ledger)
+    assert result.final_verdicts == {"claim-0": "VERIFIED", "claim-1": "UNSUPPORTED"}
+    # Only elem-0 credited -> 0.5 < 0.70 -> held.
+    assert result.coverage_fraction == pytest.approx(0.5)
+    assert result.release_allowed is False
+    # KG persisted both, only the VERIFIED row is reusable (anti-poisoning), order is input-order.
+    conn = sqlite3.connect(str(result.kg_path))
+    try:
+        rows = conn.execute(
+            "SELECT claim_id, verdict, reusable FROM verified_claims ORDER BY rowid"
+        ).fetchall()
+    finally:
+        conn.close()
+    assert rows == [("claim-0", "VERIFIED", 1), ("claim-1", "UNSUPPORTED", 0)]
+
+
+# === (b) parallel total cost == sequential total cost AND same cap trip point ===================
+# The tipping cost is placed on the LAST pipeline call (the JUDGE) of the tripping claim, so the
+# sequential live-mid-claim trip and the parallel claim-boundary trip fire at the SAME total.
+
+# A LARGE reasoning block on the qwen Judge slug (~$0.12/call at $0.60/M output) — an order of
+# magnitude above the ~$0.003 per-call floor, so it alone tips the cap and makes the trip point
+# unambiguous (it is the LAST call of its claim, so the sequential live-trip and the parallel
+# boundary-trip fire at the SAME accumulated total).
+_BIG_JUDGE_USAGE = {
+    "prompt_tokens": 1000,
+    "completion_tokens": 1000,
+    "completion_tokens_details": {"reasoning_tokens": 200_000},
+}
+
+
+def _cost_claims(n):
+    claims = [_claim(i, covers=[f"elem-{i}"]) for i in range(n)]
+    ledger = CoverageLedger(required_element_ids=[f"elem-{i}" for i in range(n)])
+    return claims, ledger
+
+
+def test_parallel_and_sequential_trip_cap_at_same_total(monkeypatch, tmp_path):
+    # (b) CUMULATIVE cap, same trip total on both paths. n=2; the LAST claim (claim-1) is the
+    # tripping claim and its JUDGE (the LAST call of its pipeline) carries the tipping usage
+    # (~$0.1207). Conditions (advisor): every claim is individually UNDER the cap (so NO worker
+    # pre-trips in its reset context), and a parent pre-seed makes the CUMULATIVE — not a single
+    # claim — cross the cap. With n=2 and the tip on the last claim, BOTH workers fully spend and
+    # BOTH deltas are reduced, so the parent total equals the true spend (clean equality).
+    #
+    #   cap = 0.20; parent pre-seed 0.10.
+    #   claim-0 total ~= 0.00911 ; claim-1 total ~= 0.00911 - 0.00011 + 0.1207 ~= 0.12970 (< cap,
+    #     so claim-1's worker does NOT in-worker-trip).
+    #   SEQUENTIAL live: 0.10 + 0.00911 (claim-0) + 0.009 (claim-1 mirror+sentinel) = 0.11811 < cap,
+    #     then + Judge 0.1207 -> 0.23881 > cap -> trips AT claim-1's Judge call.
+    #   PARALLEL boundary: parent re-adds claim-0 -> 0.10911 ok; claim-1 -> 0.23881 > cap -> trips.
+    #   Both report 0.23881. The tip on claim-1's LAST call is what makes the totals identical.
+    n = 2
+    usage = {(1, "judge"): dict(_BIG_JUDGE_USAGE)}
+
+    def run_path(workers, sub_dir):
+        monkeypatch.setattr(sweep_integration, "_CLAIM_WORKERS", workers)
+        monkeypatch.setattr(openrouter_client, "PG_MAX_COST_PER_RUN", 0.20)
+        openrouter_client.reset_run_cost()
+        openrouter_client._add_run_cost(0.10)  # near-cap generator pre-seed (shared accumulator).
+        run_dir = tmp_path / sub_dir
+        run_dir.mkdir()
+        claims, ledger = _cost_claims(n)
+        transport = _DelayedFakeTransport(usage_by_index_role=usage)
+        with pytest.raises(BudgetExceededError):
+            _run(transport, claims, run_dir=run_dir, ledger=ledger)
+        return openrouter_client.current_run_cost()
+
+    seq_total = run_path(1, "seq")
+    par_total = run_path(2, "par")
+    # Same accumulated spend at the trip on BOTH paths (deterministic — no floor noise).
+    assert seq_total > 0.20 and par_total > 0.20
+    assert seq_total == pytest.approx(par_total, rel=1e-9)
+
+
+def test_single_claim_over_cap_trips_in_worker_fail_closed(monkeypatch, tmp_path):
+    # The SECOND parallel enforcement point (honest documentation): when a SINGLE claim's own cost
+    # exceeds the FULL cap, its worker trips LIVE inside RecordingTransport (the per-worker reset
+    # context baselines at 0, so the claim's own spend alone crosses the cap) and raises
+    # BudgetExceededError BEFORE returning a delta — the parent never re-adds it. This is
+    # fail-closed and correct; we assert it RAISES but do NOT assert an equal parent total (the
+    # parent counter stays at the pre-seed because the worker aborted before reduction).
+    monkeypatch.setattr(sweep_integration, "_CLAIM_WORKERS", 4)
+    monkeypatch.setattr(openrouter_client, "PG_MAX_COST_PER_RUN", 0.05)
+    openrouter_client.reset_run_cost()
+    n = 2
+    # claim-0's Judge alone (~$0.1207) exceeds the 0.05 cap -> its worker trips in-worker.
+    usage = {(0, "judge"): dict(_BIG_JUDGE_USAGE)}
+    claims, ledger = _cost_claims(n)
+    transport = _DelayedFakeTransport(usage_by_index_role=usage)
+    with pytest.raises(BudgetExceededError):
+        _run(transport, claims, run_dir=tmp_path, ledger=ledger)
+
+
+def test_parallel_cost_equals_sequential_cost_under_cap(monkeypatch, tmp_path):
+    # No cap pressure: prove the TOTAL accounted spend is identical between the sequential and the
+    # parallel paths (the parent re-adds exactly each worker's per-claim delta — no double count,
+    # no drop). 3 claims, each Judge carries a modest usage.
+    n = 3
+    modest = {
+        "prompt_tokens": 100,
+        "completion_tokens": 100,
+        "completion_tokens_details": {"reasoning_tokens": 1000},
+    }
+    usage = {(i, "judge"): dict(modest) for i in range(n)}
+
+    def total_for(workers, sub_dir):
+        monkeypatch.setattr(sweep_integration, "_CLAIM_WORKERS", workers)
+        monkeypatch.setattr(openrouter_client, "PG_MAX_COST_PER_RUN", 1000.0)
+        openrouter_client.reset_run_cost()
+        run_dir = tmp_path / sub_dir
+        run_dir.mkdir()
+        claims, ledger = _cost_claims(n)
+        transport = _DelayedFakeTransport(usage_by_index_role=usage)
+        _run(transport, claims, run_dir=run_dir, ledger=ledger)
+        return openrouter_client.current_run_cost()
+
+    seq_total = total_for(1, "seq")
+    par_total = total_for(4, "par")
+    assert seq_total > 0.0
+    assert seq_total == pytest.approx(par_total, rel=1e-9)
+
+
+# === Codex iter-2 P1.2 — the PARENT Path-B capture sink is visible inside workers ===============
+class _CapturingFakeTransport:
+    """Fake `RoleTransport` that emits a CAPTUREABLE verifier call exactly as the real transports
+    do: it scopes the role via `pathB_capture.llm_role(request.role)` and calls
+    `pathB_capture.capture_llm_call(...)` for EVERY role call. The capture only lands in the parent
+    `_PATHB_SINK` if the worker runs under a context snapshot that was taken on the PARENT (P1.2);
+    with `copy_context()` taken INSIDE the worker the sink is the worker's empty default (None) and
+    capture no-ops, so the parent sink stays empty. Verdicts are fixed VERIFIED so the seam reduces
+    cleanly; this test is about CAPTURE VISIBILITY, not verdict math.
+    """
+
+    def __init__(self) -> None:
+        self._lock = threading.Lock()
+        self.completions = 0
+
+    def complete(self, request: RoleRequest) -> RoleResponse:
+        with self._lock:
+            self.completions += 1
+        # Emit a captureable call THE SAME WAY the real OpenRouter/OpenAI-compatible transports do:
+        # scope the role, then capture. A minimal served-identity raw response so the capture record
+        # carries response_metadata (the M4 gate's served==pinned surface).
+        with pathB_capture.llm_role(request.role):
+            pathB_capture.capture_llm_call(
+                role=request.role,
+                messages=[{"role": "user", "content": request.prompt or ""}],
+                raw_response={"provider": "FakeProvider", "model": request.model_slug},
+            )
+
+        if request.role == "mirror":
+            if "pass2_input" in (request.params or {}):
+                content_hash = request.params["pass2_input"]["content_hash"]
+                return RoleResponse(
+                    raw_text=json.dumps(
+                        {"content_hash": content_hash, "classification": "supported"}
+                    ),
+                    served_model=request.model_slug,
+                    usage=None,
+                )
+            idx = _DelayedFakeTransport._index_from_request(request)
+            return RoleResponse(
+                raw_text="grounded answer",
+                served_model=request.model_slug,
+                citations=[CitationSpan(span_start=0, span_end=8, doc_ids=(f"doc-{idx}",))],
+                usage=None,
+            )
+        if request.role == "sentinel":
+            return RoleResponse(
+                raw_text="<score>no</score>", served_model=request.model_slug, usage=None
+            )
+        if request.role == "judge":
+            return RoleResponse(
+                raw_text="VERIFIED", served_model=request.model_slug, usage=None
+            )
+        raise AssertionError(f"unexpected role {request.role!r}")
+
+
+def test_pathb_sink_visible_in_workers(monkeypatch, tmp_path):
+    # P1.2: register a Path-B capture sink on the PARENT (as pathB_runner does), run the seam with
+    # 4 workers + a fake transport that emits captureable verifier calls, and assert the PARENT sink
+    # received ALL workers' captures. This FAILS with copy_context() taken INSIDE the worker (the
+    # worker's empty default context has _SINK=None, so capture no-ops and the parent sink stays
+    # empty), and PASSES once the snapshot is taken on the parent before submit.
+    monkeypatch.setattr(sweep_integration, "_CLAIM_WORKERS", 4)
+    n = 4
+    claims = [_claim(i, covers=[f"elem-{i}"]) for i in range(n)]
+    ledger = CoverageLedger(required_element_ids=[f"elem-{i}" for i in range(n)])
+    transport = _CapturingFakeTransport()
+
+    # Register the parent capture sink THE SAME WAY pathB_runner.gate_around_question does, and
+    # always clear it so the contextvar never leaks into another test.
+    pathB_capture.register_pathB_capture()
+    try:
+        result = _run(transport, claims, run_dir=tmp_path, ledger=ledger)
+        captured = pathB_capture.collected_calls()
+    finally:
+        pathB_capture.clear_pathB_capture()
+
+    assert result.final_verdicts == {f"claim-{i}": "VERIFIED" for i in range(n)}
+    # Every claim runs Mirror(x2) + Sentinel + Judge == 4 captureable calls -> 4 claims * 4 = 16.
+    # The exact count proves NO worker's captures were lost to an isolated empty context.
+    assert len(captured) == n * 4, (
+        f"parent sink saw {len(captured)} captures, expected {n * 4}; a missing batch means a "
+        f"worker ran under an empty context and capture no-oped (P1.2 regression)."
+    )
+    # All three verifier roles are present at the parent (capture visibility is per-role).
+    roles_seen = {c["role"] for c in captured}
+    assert roles_seen == {"mirror", "sentinel", "judge"}, roles_seen
+    # Every captured call carries the served-identity metadata the M4 gate reads (proves the
+    # capture pipeline ran end-to-end inside the worker, not just an empty append).
+    assert all(c["response_metadata"].get("provider_name") == "FakeProvider" for c in captured)
+
+
+# === Codex iter-2 P1.1 — a cumulative cap trip is BOUNDED to ~(workers) in-flight ===============
+class _CountingCostTransport:
+    """Fake `RoleTransport` that bills a FIXED cost on each claim's JUDGE call (the LAST call of the
+    pipeline) and records WHICH claim indices actually started, so a test can prove that a cumulative
+    cap trip stops further claims rather than running all N. Thread-safe; NEVER a socket.
+
+    Each claim's Mirror PASS-1 (its FIRST call) sleeps `per_claim_delay` so workers process claims in
+    bounded WAVES instead of racing the whole batch to completion before the parent re-adds any
+    delta — without the delay a near-instant fake would let all N claims finish before the parent's
+    cumulative cap check fires, defeating the in-flight-bound assertion.
+    """
+
+    def __init__(self, *, judge_usage: dict, per_claim_delay: float = 0.0) -> None:
+        self._judge_usage = judge_usage
+        self._delay = per_claim_delay
+        self._lock = threading.Lock()
+        self.started_indices: set[int] = set()
+        self.completions = 0
+
+    def complete(self, request: RoleRequest) -> RoleResponse:
+        idx = _DelayedFakeTransport._index_from_request(request)
+        with self._lock:
+            self.completions += 1
+            if idx is not None:
+                self.started_indices.add(idx)
+
+        if request.role == "mirror":
+            if "pass2_input" in (request.params or {}):
+                content_hash = request.params["pass2_input"]["content_hash"]
+                return RoleResponse(
+                    raw_text=json.dumps(
+                        {"content_hash": content_hash, "classification": "supported"}
+                    ),
+                    served_model=request.model_slug,
+                    usage=None,
+                )
+            # Pass-1 is the FIRST call of the claim -> sleep here so workers advance in bounded waves.
+            if self._delay:
+                time.sleep(self._delay)
+            return RoleResponse(
+                raw_text="grounded answer",
+                served_model=request.model_slug,
+                citations=[CitationSpan(span_start=0, span_end=8, doc_ids=(f"doc-{idx}",))],
+                usage=None,
+            )
+        if request.role == "sentinel":
+            return RoleResponse(
+                raw_text="<score>no</score>", served_model=request.model_slug, usage=None
+            )
+        if request.role == "judge":
+            return RoleResponse(
+                raw_text="VERIFIED",
+                served_model=request.model_slug,
+                usage=dict(self._judge_usage),
+            )
+        raise AssertionError(f"unexpected role {request.role!r}")
+
+
+def test_cap_trip_is_bounded_in_flight(monkeypatch, tmp_path):
+    # P1.1: N claims, each individually UNDER the cap, but the CUMULATIVE spend crosses the cap after
+    # a few claims. With the cap enforced DURING compute (parent re-adds each completed claim's delta
+    # and re-checks immediately), a BudgetExceededError fires and the pool is shut down with
+    # cancel_futures=True — so the number of claims that ACTUALLY RAN is bounded near the worker count
+    # in-flight at the breach, NOT all N. With the OLD code (submit+drain ALL, then re-add in the
+    # reduction) every one of the N claims would have run and spent before the cap tripped.
+    workers = 2
+    n = 12
+    monkeypatch.setattr(sweep_integration, "_CLAIM_WORKERS", workers)
+    # Each claim's Judge bills ~$0.1207 (the _BIG_JUDGE_USAGE block). Cap 0.30 -> the cumulative
+    # total crosses after claim #3's delta is re-added (3 * 0.1207 = 0.3621 > 0.30), so only a
+    # SMALL prefix of the 12 claims should ever start.
+    monkeypatch.setattr(openrouter_client, "PG_MAX_COST_PER_RUN", 0.30)
+    openrouter_client.reset_run_cost()
+    judge_usage = dict(_BIG_JUDGE_USAGE)
+    claims, ledger = _cost_claims(n)
+    # A small per-claim delay makes workers advance in bounded waves of `workers`, so the parent's
+    # cumulative cap check fires BEFORE the whole batch of 12 finishes (a near-instant fake would let
+    # all N complete first and defeat the in-flight bound).
+    transport = _CountingCostTransport(judge_usage=judge_usage, per_claim_delay=0.05)
+
+    with pytest.raises(BudgetExceededError):
+        _run(transport, claims, run_dir=tmp_path, ledger=ledger)
+
+    ran = len(transport.started_indices)
+    # BOUNDED: each Judge bills ~$0.1207; the cumulative cap (0.30) crosses once the parent has
+    # re-added ~3 claims' deltas (3 * 0.1207 = 0.3621 > 0.30). At the breach at most `workers` more
+    # claims can be in flight, so `ran` is bounded near (3 + workers), NEVER all 12. The headline
+    # assertion is `ran < n`: the OLD submit-and-drain-all code would have run every one of the 12.
+    assert ran < n, f"cap trip ran {ran}/{n} claims — should be bounded near the worker count, not all N"
+    assert ran <= 3 + 2 * workers, (
+        f"cap trip ran {ran} claims; the cumulative cap crosses after ~3 claims and only a bounded "
+        f"number more can be in-flight at the breach (bounded overspend, P1.1, workers={workers})."
+    )

```
