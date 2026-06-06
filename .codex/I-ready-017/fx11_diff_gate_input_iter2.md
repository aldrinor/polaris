# FX-11 (#1116) diff-gate — ITER 2 of 5

```
HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Output schema (REQUIRED — reply with EXACTLY this YAML, nothing else)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## Scope reminder
Cost-accounting ONLY. NOT a faithfulness invariant (no grounding / strict_verify / 4-role-decision
change). `check_run_budget` (the spend gate, on the per-task `current_run_cost()` ContextVar) is
untouched. Diff: `.codex/I-ready-017/fx11_codex_diff.patch` (vs FX-10 tip `e63c102b`).

## Your iter-1 verdict (what this iter addresses)
- **P1 (the blocker):** "role cost-ledger cumulative under default parallel four-role workers must
  use the parent/shared inclusive run total and be non-decreasing." Root cause: cumulative was read
  from `current_run_cost()`, the per-asyncio-task ContextVar that each parallel claim worker
  RESETS — so role-row cumulatives were per-worker / non-monotonic.
- **P2a:** blank-verdict retry (`openrouter_role_transport`) added run-budget cost but wrote no
  ledger row.
- **P2b:** `loopback_client` `usage.record(api_cost=0.0)` ledgered a phantom paid-rate token
  estimate for a free call.
- **P2c:** the best-effort write-failure test did not actually force a failure (mkdir created the
  parents).

## What iter-2 changed (the fix = the issue's literal title: a SINGLE canonical accumulator)
1. **One process-global, per-session accumulator + ONE canonical writer.** `_LEDGER_CUM_LOCK` is now
   a `threading.RLock`; new `append_cost_ledger_row(...)` (openrouter_client) **bumps the
   per-session accumulator AND appends the JSONL row under the SAME lock**. So the persisted file is
   non-decreasing in **write order** (not merely assignment order) even when several
   ThreadPoolExecutor workers write concurrently. Returns the inclusive cumulative.
2. **Grounding for the P1 (please verify):** the real fan-out is `sweep_integration.py:329-332` —
   `concurrent.futures.ThreadPoolExecutor(max_workers=PG_FOUR_ROLE_CLAIM_WORKERS)` + each task
   submitted via `contextvars.copy_context().run(...)`. `copy_context()` **inherits**
   `_CURRENT_RUN_ID_CTX` (the run id) into every worker; each worker resets only its OWN
   `_RUN_COST_CTX`. Therefore all workers resolve the SAME accumulator key (the shared run id), and
   the shared accumulator gives one rising total. (If you think threads do NOT inherit the run id
   here, that is the key thing to check — the fix's correctness rests on this copy_context inherit.)
3. **All four writers route the accumulator with ONE precedence.** `UsageTracker.record` keys
   `self.session_id or _CURRENT_RUN_ID_CTX.get() or ""`; judge / role / blank-retry key
   `_CURRENT_RUN_ID_CTX.get() or "no_run_id"`; `append_cost_ledger_row`/`ledger_bump_cumulative`
   normalize `"" -> "no_run_id"`. So generate + judge + role rows of one run share ONE accumulator
   in every case (N-301: pick up the ambient run id when none was passed). `record` does its bump +
   `_append_ledger` inside the same RLock (RLock => the inner `ledger_bump_cumulative` re-acquire is
   safe). `_append_ledger` is kept only because a test monkeypatches it.
4. **role / judge / blank-retry** now call `append_cost_ledger_row` (this removed ~50 lines of
   duplicated manual mkdir+open blocks — net DRYer).
5. **P2a:** blank-verdict retry writes a `role:<role>:blank_attempt` row (distinct call_type marks
   the discarded attempt) so ledger total stays == run-budget total. Skipped only when the blank
   carried no usage (cost 0 — accumulator unchanged anyway).
6. **P2b:** `usage.record(..., free=True)` forces `call_cost = 0.0`; `loopback_client` passes
   `free=True`. The token-based imputation backstop (invariant #6) for PAID calls with no reported
   cost is untouched (default `free=False`).
7. **P2c:** the test now points the ledger path THROUGH a regular file so `.parent.mkdir` raises a
   real error; asserts the role call still returns and no partial file is created.

## Evidence
- **§-1.1 on REAL held ledger** (`outputs/audits/I-ready-017/fx11_s11_audit.md`): the held drb_72
  ledger has 26 decreasing steps + 0 role rows (of 472). The fix is proven by offline smoke + the
  new parallel repro (a fresh ledger needs a live run).
- **Offline smoke — `test_fx11_cost_ledger_iready017.py` → 6 passed**, incl. the P1 repro
  `test_bug10b_role_cumulative_monotonic_under_parallel_workers`: 6 ThreadPoolExecutor workers ×
  `copy_context()` × per-worker `reset_run_cost()`, 30 role rows → cumulative NON-DECREASING **in
  file write order**, all tagged the ONE shared run id, final == the GLOBAL total of every role cost
  (which per-worker `current_run_cost()` could not show). Plus P2a / P2b (with a paid-call control
  proving #6 still imputes) / P2c (forced write failure).
- **Regression:** `tests/roles/` (437) + `test_entailment_judge_cost` (8) +
  `test_m206_n301_cost_ledger` (10) + sota session_id/`_append_ledger` (3) + `llm/` (11) + loopback
  regression (12) all pass.

## Questions for you
1. Is the parallel-worker monotonicity now correct given the `copy_context()` inherit of the run id
   (P1 closed)? Any path where a worker would resolve a DIFFERENT accumulator key than the
   generator for the same run?
2. Holding the RLock across the file `open()/write()` serializes ledger appends. Acceptable for
   correctness (it is what guarantees file-order monotonicity), or do you see a real contention /
   deadlock risk? (`check_run_budget` is NOT under this lock.)
3. Anything blocking APPROVE?

## THE DIFF UNDER REVIEW (vs FX-10 tip e63c102b)
```diff
diff --git a/src/polaris_graph/llm/entailment_judge.py b/src/polaris_graph/llm/entailment_judge.py
index 6d72aa00..28b5fe50 100644
--- a/src/polaris_graph/llm/entailment_judge.py
+++ b/src/polaris_graph/llm/entailment_judge.py
@@ -52,7 +52,6 @@ import json
 import logging
 import os
 import time
-from datetime import datetime, timezone
 
 # I-bug-100: import openrouter_client as a MODULE reference (not by-value)
 # so monkeypatch.setattr on its globals (`PG_MAX_COST_PER_RUN`,
@@ -279,20 +278,17 @@ def _append_judge_ledger_entry(
     test monkeypatch.setattr on `openrouter_client._COST_LEDGER_PATH`
     propagates correctly.
     """
-    entry = {
-        "timestamp": datetime.now(timezone.utc).isoformat(),
-        "session_id": _orc._CURRENT_RUN_ID_CTX.get() or "no_run_id",
-        "call_type": "entailment_judge",
-        "input_tokens": input_tokens,
-        "output_tokens": output_tokens,
-        "reasoning_tokens": 0,
-        "duration_ms": round(duration_ms, 1),
-        "cost_usd": round(actual_cost, 6),
-        "cumulative_cost_usd": round(_orc.current_run_cost(), 4),
-    }
-    _orc._COST_LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
-    with open(_orc._COST_LEDGER_PATH, "a", encoding="utf-8") as f:
-        f.write(json.dumps(entry) + "\n")
+    # FX-11 (BUG-10): route through the SINGLE canonical cost-ledger writer, which bumps the shared,
+    # monotonic per-session accumulator and appends the row atomically (NOT current_run_cost(),
+    # which is reset per parallel four-role worker). Best-effort I/O is handled inside the writer.
+    _orc.append_cost_ledger_row(
+        session_id=_orc._CURRENT_RUN_ID_CTX.get() or "no_run_id",
+        call_type="entailment_judge",
+        cost_usd=actual_cost,
+        input_tokens=input_tokens,
+        output_tokens=output_tokens,
+        duration_ms=duration_ms,
+    )
 
 
 _JUDGE_SINGLETON: _EntailmentJudge | None = None
diff --git a/src/polaris_graph/llm/loopback_client.py b/src/polaris_graph/llm/loopback_client.py
index 64e9626a..1db2a8f9 100644
--- a/src/polaris_graph/llm/loopback_client.py
+++ b/src/polaris_graph/llm/loopback_client.py
@@ -300,6 +300,9 @@ class LoopbackLLMClient:
                     output_tokens=output_tokens,
                     duration_ms=duration_ms,
                     api_cost=0.0,  # operator is free
+                    # FX-11 (I-ready-017 P2b): free=True ledgers cost 0 instead of a phantom
+                    # paid-rate token estimate, and (with no _add_run_cost) keeps ledger==run-total.
+                    free=True,
                 )
 
                 logger.info(
diff --git a/src/polaris_graph/llm/openrouter_client.py b/src/polaris_graph/llm/openrouter_client.py
index 8bcc4d5b..0880f976 100644
--- a/src/polaris_graph/llm/openrouter_client.py
+++ b/src/polaris_graph/llm/openrouter_client.py
@@ -16,6 +16,7 @@ import json
 import logging
 import os
 import re
+import threading
 import time
 from dataclasses import dataclass, field
 from datetime import datetime, timezone
@@ -253,6 +254,92 @@ def _add_run_cost(delta: float) -> None:
     _RUN_COST_CTX.set(_RUN_COST_CTX.get() + float(delta))
 
 
+# FX-11 (I-ready-017 BUG-10/10b): a PROCESS-GLOBAL, lock-protected, per-SESSION monotonic
+# accumulator for the cost LEDGER's `cumulative_cost_usd`. The budget guard uses the per-task
+# ContextVar `current_run_cost()`, which is RESET inside each parallel four-role claim worker
+# (sweep_integration) and merged to the parent only at the end — so a per-row cumulative read
+# from it is per-worker and NON-monotonic/interleaved. The ledger's cumulative must instead be a
+# single rising run total regardless of which thread/worker writes the row (Uptrace SOTA: LLM
+# cost is a MONOTONIC counter). Keyed by session_id (run_id, unique per run) so concurrent
+# workers of ONE run share the counter and distinct runs in one process never bleed. The budget
+# GATE (current_run_cost / check_run_budget) is intentionally NOT changed.
+# RLock (reentrant): append_cost_ledger_row holds it across bump+write and calls
+# ledger_bump_cumulative, which re-acquires it. A plain Lock would self-deadlock.
+_LEDGER_CUM_LOCK = threading.RLock()
+_LEDGER_CUM_BY_SESSION: dict[str, float] = {}
+
+
+def ledger_bump_cumulative(session_id: str, cost: float) -> float:
+    """Atomically add `cost` to the per-session ledger total; return the new total (rounded 4).
+
+    Monotonic within a `session_id` across threads/workers — this is the value every cost-ledger
+    row must record as `cumulative_cost_usd`.
+    """
+    sid = session_id or "no_run_id"
+    with _LEDGER_CUM_LOCK:
+        total = _LEDGER_CUM_BY_SESSION.get(sid, 0.0) + float(cost)
+        _LEDGER_CUM_BY_SESSION[sid] = total
+        return round(total, 4)
+
+
+def reset_ledger_cumulative(session_id: str) -> None:
+    """Clear the per-session ledger accumulator so a re-used `session_id` in one process starts
+    fresh. Production run_ids are unique per run (no reset needed); tests reuse ids and call this.
+    NOTE: do NOT hook this into reset_run_cost — that is called per parallel worker and would zero
+    the shared run total mid-run.
+    """
+    sid = session_id or "no_run_id"
+    with _LEDGER_CUM_LOCK:
+        _LEDGER_CUM_BY_SESSION.pop(sid, None)
+
+
+def append_cost_ledger_row(
+    *,
+    session_id: str,
+    call_type: str,
+    cost_usd: float,
+    input_tokens: int = 0,
+    output_tokens: int = 0,
+    reasoning_tokens: int = 0,
+    duration_ms: float = 0.0,
+) -> float:
+    """THE single canonical cost-ledger writer (FX-11, I-ready-017 #1116 — issue title).
+
+    Under ONE re-entrant process-global lock: (1) add ``cost_usd`` to the per-session monotonic
+    accumulator, (2) append the row — carrying that inclusive ``cumulative_cost_usd`` — to the
+    JSONL ledger. Bumping and appending share the lock so the PERSISTED FILE is non-decreasing in
+    WRITE order (not merely in assignment order) even under the parallel four-role
+    ThreadPoolExecutor workers (sweep_integration), which each copy_context() (inheriting the run
+    id) and reset their own ``_RUN_COST_CTX``. Returns the new cumulative (rounded 4).
+
+    Best-effort I/O: a write failure is logged, NEVER raised, and the in-memory accumulator still
+    advances so it stays == the run-budget total. Used by the four-role role / judge / blank-retry
+    writers; the generator (UsageTracker.record) bumps the SAME accumulator under the SAME lock via
+    its ``_append_ledger`` hook (kept distinct only because a test monkeypatches that hook).
+    """
+    sid = session_id or "no_run_id"
+    with _LEDGER_CUM_LOCK:
+        total = ledger_bump_cumulative(sid, cost_usd)  # reentrant acquire (RLock)
+        row = {
+            "timestamp": datetime.now(timezone.utc).isoformat(),
+            "session_id": sid,
+            "call_type": call_type,
+            "input_tokens": int(input_tokens),
+            "output_tokens": int(output_tokens),
+            "reasoning_tokens": int(reasoning_tokens),
+            "duration_ms": round(float(duration_ms), 1),
+            "cost_usd": round(float(cost_usd), 6),
+            "cumulative_cost_usd": total,
+        }
+        try:
+            _COST_LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
+            with open(_COST_LEDGER_PATH, "a", encoding="utf-8") as f:
+                f.write(json.dumps(row) + "\n")
+        except Exception as exc:  # best-effort: never break the caller's call/budget path
+            logger.warning("FIX-O1/FX-11: Cost ledger write failed: %s", exc)
+        return total
+
+
 # Codex round 1 B-4: conservative per-model prices used when OpenRouter
 # omits usage.cost. Prices are $/M tokens and represent the UPPER END of
 # published rates for each provider family (if a cheaper provider is used
@@ -729,6 +816,7 @@ class UsageTracker:
         duration_ms: float = 0,
         api_cost: float = 0.0,
         prompt_component_tokens: dict | None = None,
+        free: bool = False,
     ):
         self.total_input_tokens += input_tokens
         self.total_output_tokens += output_tokens
@@ -737,11 +825,49 @@ class UsageTracker:
         # FIX-C2: Accumulate API-reported cost for accurate billing
         if api_cost > 0:
             self.total_api_reported_cost += api_cost
-        call_cost = api_cost if api_cost > 0 else round(
-            (input_tokens / 1_000_000) * INPUT_COST_PER_M
-            + (output_tokens / 1_000_000) * OUTPUT_COST_PER_M,
-            6,
-        )
+        # FX-11 (I-ready-017 Codex iter-1 P2b): a GENUINELY-FREE call (e.g. the operator
+        # loopback transport — "operator is free") must ledger cost 0, NOT a phantom paid-rate
+        # token estimate. `free=True` forces 0 and is the ONLY way to suppress the token-based
+        # fallback; it does NOT touch the imputation backstop (invariant #6) that paid calls rely
+        # on when OpenRouter omits usage.cost (those pass free=False / the default and still get
+        # the token estimate). A free call also does not feed `_add_run_cost`, so cost 0 keeps the
+        # persisted ledger total == the run-budget total.
+        if free:
+            call_cost = 0.0
+        else:
+            call_cost = api_cost if api_cost > 0 else round(
+                (input_tokens / 1_000_000) * INPUT_COST_PER_M
+                + (output_tokens / 1_000_000) * OUTPUT_COST_PER_M,
+                6,
+            )
+        # FX-11 (BUG-10): cumulative_cost_usd is the shared, monotonic per-session RUN total
+        # (process-global accumulator) — NOT the per-instance self.total_cost_usd (non-monotonic
+        # across clients sharing a run) and NOT current_run_cost() (the per-task ContextVar that
+        # is reset per parallel four-role worker). Bump ONCE here and reuse for BOTH the in-memory
+        # _call_log entry and the persisted ledger row, so they agree and never double-count.
+        # The accumulator KEY (and the row's session_id field) is resolved with the SAME precedence
+        # the judge + role writers use — `self.session_id or ambient run_id` — so all three writers
+        # of one run share ONE accumulator (N-301: pick up the ambient run_id when none was passed).
+        _sid = self.session_id or _CURRENT_RUN_ID_CTX.get() or ""
+        # Bump the shared per-session accumulator AND persist the ledger row ATOMICALLY under the
+        # canonical RLock, so the persisted file stays monotonic in WRITE order even if a four-role
+        # worker (which uses append_cost_ledger_row — the SAME lock + accumulator) writes
+        # concurrently. _append_ledger is kept as a method only because a test monkeypatches it; it
+        # is now invoked inside the lock. RLock => the inner ledger_bump_cumulative re-acquire is OK.
+        with _LEDGER_CUM_LOCK:
+            _cum = ledger_bump_cumulative(_sid, call_cost)
+            # FIX-305: Persist to JSONL cost ledger
+            self._append_ledger({
+                "timestamp": datetime.now(timezone.utc).isoformat(),
+                "session_id": _sid,  # FIX-F2/FX-11: ambient-resolved run ID (matches accumulator key)
+                "call_type": call_type,
+                "input_tokens": input_tokens,
+                "output_tokens": output_tokens,
+                "reasoning_tokens": reasoning_tokens,
+                "duration_ms": round(duration_ms, 1),
+                "cost_usd": round(call_cost, 6),
+                "cumulative_cost_usd": _cum,
+            })
         entry = {
             "type": call_type,
             "input_tokens": input_tokens,
@@ -749,26 +875,13 @@ class UsageTracker:
             "reasoning_tokens": reasoning_tokens,
             "duration_ms": duration_ms,
             "cost_usd": round(call_cost, 6),
-            "cumulative_cost_usd": round(self.total_cost_usd, 4),
+            "cumulative_cost_usd": _cum,
         }
         # TIER-3 Stage 6: Optional prompt component breakdown
         if prompt_component_tokens:
             entry["prompt_components"] = prompt_component_tokens
         self._call_log.append(entry)
 
-        # FIX-305: Persist to JSONL cost ledger
-        self._append_ledger({
-            "timestamp": datetime.now(timezone.utc).isoformat(),
-            "session_id": self.session_id,  # FIX-F2: Tag entries with run ID
-            "call_type": call_type,
-            "input_tokens": input_tokens,
-            "output_tokens": output_tokens,
-            "reasoning_tokens": reasoning_tokens,
-            "duration_ms": round(duration_ms, 1),
-            "cost_usd": round(call_cost, 6),
-            "cumulative_cost_usd": round(self.total_cost_usd, 4),
-        })
-
     def _append_ledger(self, entry: dict):
         """Append a cost entry to the persistent JSONL ledger."""
         try:
@@ -1878,7 +1991,14 @@ class OpenRouterClient:
                 )
             api_cost = max(api_cost or 0.0, imputed)
 
-        # Track usage
+        # FX-11 (I-ready-017 BUG-10): contribute to the shared run-cost counter BEFORE
+        # usage.record so the cumulative_cost_usd it writes (now current_run_cost()) is
+        # INCLUSIVE of this call — matching the judge add-then-write order, and making the
+        # ledger's cumulative a monotonic run-total instead of a per-instance value. The
+        # budget cap is checked BEFORE the call by callers via check_run_budget(); this
+        # post-call add only accumulates (does not gate).
+        _add_run_cost(api_cost)
+        # Track usage (writes the line item + ledger row with the inclusive cumulative).
         self.usage.record(
             call_type=call_type,
             input_tokens=input_tokens,
@@ -1887,9 +2007,6 @@ class OpenRouterClient:
             duration_ms=duration_ms,
             api_cost=api_cost,
         )
-        # R-2: contribute to the shared run-cost counter AFTER the call.
-        # Checking the cap BEFORE is done by callers via check_run_budget().
-        _add_run_cost(api_cost)
 
         # COT-1: Strict separation — NEVER mix reasoning into content.
         # The API separates content and reasoning_content correctly.
@@ -1996,7 +2113,10 @@ class OpenRouterClient:
                     + (output_tokens / 1_000_000) * OUTPUT_COST_PER_M,
                     6,
                 ),
-                cumulative_cost_usd=round(self.usage.total_cost_usd, 4),
+                # FX-11 (BUG-10): the live-UI trace event uses the shared monotonic run
+                # total (current_run_cost(), inclusive — _add_run_cost ran before record),
+                # not the per-instance self.usage.total_cost_usd that under-reported NOW.
+                cumulative_cost_usd=round(current_run_cost(), 4),
                 model=self.model[:50],
             )
 
diff --git a/src/polaris_graph/roles/openrouter_role_transport.py b/src/polaris_graph/roles/openrouter_role_transport.py
index d171f744..a3b6ac1e 100644
--- a/src/polaris_graph/roles/openrouter_role_transport.py
+++ b/src/polaris_graph/roles/openrouter_role_transport.py
@@ -778,9 +778,32 @@ class OpenRouterRoleTransport:
                     import src.polaris_graph.llm.openrouter_client as _orc
                     from src.polaris_graph.roles.role_pipeline import compute_role_call_cost
 
-                    _orc._add_run_cost(
-                        compute_role_call_cost(request.model_slug, raw.get("usage"))
-                    )
+                    _blank_cost = compute_role_call_cost(request.model_slug, raw.get("usage"))
+                    _orc._add_run_cost(_blank_cost)
+                    # FX-11 (I-ready-017 BUG-10b / Codex iter-1 P2a): this BLANKED attempt is
+                    # DISCARDED, so RecordingTransport (which ledgers only the FINAL returned
+                    # response) never records it — yet it cost real money and DID feed the run
+                    # budget above. Append a row through the SINGLE canonical writer (shared
+                    # per-session accumulator) so the persisted ledger total stays == the run-budget
+                    # total; the distinct call_type marks it a discarded attempt (not the served
+                    # verdict). Best-effort I/O is handled inside the writer. Skip the row when the
+                    # blank carried no usage (cost 0 leaves the accumulator unchanged anyway).
+                    if _blank_cost > 0:
+                        _ub = raw.get("usage") or {}
+                        _rt = int(_ub.get("reasoning_tokens", 0) or 0) or int(
+                            (_ub.get("completion_tokens_details") or {}).get(
+                                "reasoning_tokens", 0
+                            )
+                            or 0
+                        )
+                        _orc.append_cost_ledger_row(
+                            session_id=_orc._CURRENT_RUN_ID_CTX.get() or "no_run_id",
+                            call_type=f"role:{request.role}:blank_attempt",
+                            cost_usd=_blank_cost,
+                            input_tokens=int(_ub.get("prompt_tokens", 0) or 0),
+                            output_tokens=int(_ub.get("completion_tokens", 0) or 0),
+                            reasoning_tokens=_rt,
+                        )
                     _orc.check_run_budget(0)  # raises BudgetExceededError if the cap is now crossed.
                     # I-run11-007 (#1051): exclude the provider that just returned blank so the NEXT
                     # attempt advances to the next HEALTHY provider in the ranked order (OpenRouter
diff --git a/src/polaris_graph/roles/role_pipeline.py b/src/polaris_graph/roles/role_pipeline.py
index 32db5c14..58294e42 100644
--- a/src/polaris_graph/roles/role_pipeline.py
+++ b/src/polaris_graph/roles/role_pipeline.py
@@ -171,7 +171,26 @@ class RecordingTransport:
         # generator feeds, then enforce the cap. `_RUN_COST_CTX` is per-asyncio-Task; the seam
         # runs synchronously inside the same `run_one_query` task that holds the generator spend,
         # so the delta lands on the counter holding `generator_spend + verifier_spend`.
-        _orc._add_run_cost(compute_role_call_cost(request.model_slug, response.usage))
+        _role_cost = compute_role_call_cost(request.model_slug, response.usage)
+        _orc._add_run_cost(_role_cost)
+        # FX-11 (I-ready-017 BUG-10b + Codex iter-1 P1): the four-role verifier calls
+        # (mirror/sentinel/judge) wrote ZERO cost-ledger rows before this. Ledger THIS call through
+        # the SINGLE canonical writer, which bumps the shared per-session accumulator and appends
+        # the row atomically — so role-row cumulative is non-monotonic NEITHER across the parallel
+        # claim workers (each reset their own _RUN_COST_CTX) NOR in file write order. Best-effort
+        # inside the writer: a ledger failure never breaks the verifier call or the budget check.
+        _ub = response.usage or {}
+        _rt = int(_ub.get("reasoning_tokens", 0) or 0) or int(
+            (_ub.get("completion_tokens_details") or {}).get("reasoning_tokens", 0) or 0
+        )
+        _orc.append_cost_ledger_row(
+            session_id=_orc._CURRENT_RUN_ID_CTX.get() or "no_run_id",
+            call_type=f"role:{request.role}",
+            cost_usd=_role_cost,
+            input_tokens=int(_ub.get("prompt_tokens", 0) or 0),
+            output_tokens=int(_ub.get("completion_tokens", 0) or 0),
+            reasoning_tokens=_rt,
+        )
         _orc.check_run_budget(0)  # raises BudgetExceededError if the cap is now exceeded.
         return response
 
diff --git a/tests/polaris_graph/test_fx11_cost_ledger_iready017.py b/tests/polaris_graph/test_fx11_cost_ledger_iready017.py
new file mode 100644
index 00000000..08a2f1cc
--- /dev/null
+++ b/tests/polaris_graph/test_fx11_cost_ledger_iready017.py
@@ -0,0 +1,198 @@
+"""FX-11 (I-ready-017 #1116): cost_ledger SINGLE canonical accumulator + role-call rows.
+
+BUG-10: cumulative_cost_usd was the per-instance total (non-monotonic across clients sharing a
+run; the UI under-reported). Now every writer (generator / judge / role / blank-retry) routes the
+SAME process-global, lock-protected, per-session accumulator (`_LEDGER_CUM_BY_SESSION`), keyed by
+the run id, so cumulative is a single rising run total.
+BUG-10b: the four-role verifier calls (mirror/sentinel/judge) wrote ZERO ledger rows;
+RecordingTransport now appends one inclusive row per role call.
+Codex iter-1 P1: under the parallel four-role ThreadPoolExecutor workers (each copy_context() —
+inheriting the run id — and reset their OWN `_RUN_COST_CTX`), reading cumulative from
+`current_run_cost()` made role-row cumulatives per-worker / non-monotonic. The shared accumulator
+(bump + file append under ONE RLock) makes the PERSISTED FILE non-decreasing in write order.
+Codex iter-1 P2a: the blank-verdict retry path billed the run budget but wrote no ledger row.
+Codex iter-1 P2b: a genuinely-free call (operator loopback) ledgered a phantom paid-rate estimate.
+Codex iter-1 P2c: the best-effort write-failure test never actually forced a failure.
+
+Cost-accounting only — no faithfulness/strict_verify/4-role-decision change. Offline, no network.
+"""
+from __future__ import annotations
+
+import concurrent.futures
+import contextvars
+import json
+
+import pytest
+
+from src.polaris_graph.llm import openrouter_client as orc
+from src.polaris_graph.llm.openrouter_client import (
+    UsageTracker,
+    _add_run_cost,
+    current_run_cost,
+    reset_ledger_cumulative,
+    reset_run_cost,
+    set_current_run_id,
+)
+from src.polaris_graph.roles.role_pipeline import RecordingTransport
+from src.polaris_graph.roles.role_transport import RoleRequest, RoleResponse
+
+_SID = "FX11_TEST"
+
+
+@pytest.fixture
+def tmp_ledger(tmp_path, monkeypatch):
+    p = tmp_path / "cost_ledger.jsonl"
+    monkeypatch.setattr(orc, "_COST_LEDGER_PATH", p)
+    reset_run_cost()
+    # The accumulator is PROCESS-GLOBAL and persists across tests; reset it so a re-used run id
+    # starts fresh (production run ids are unique per run and never need this).
+    reset_ledger_cumulative(_SID)
+    set_current_run_id(_SID)
+    try:
+        yield p
+    finally:
+        reset_run_cost()
+        reset_ledger_cumulative(_SID)
+        set_current_run_id(None)
+
+
+def _rows(p):
+    if not p.exists():
+        return []
+    return [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
+
+
+class _FakeTransport:
+    def complete(self, request: RoleRequest) -> RoleResponse:
+        return RoleResponse(
+            raw_text="ok",
+            served_model=request.model_slug,
+            usage={"prompt_tokens": 100, "completion_tokens": 50},
+        )
+
+
+def test_bug10_cumulative_is_monotonic_run_total(tmp_ledger):
+    usage = UsageTracker(session_id=_SID)
+    # Simulate the reordered real path: _add_run_cost BEFORE record, once per call.
+    for cost in (0.5, 0.3, 0.2):
+        _add_run_cost(cost)
+        usage.record(call_type="generate", input_tokens=10, output_tokens=5, api_cost=cost)
+    rows = [r for r in _rows(tmp_ledger) if r.get("session_id") == _SID]
+    cums = [r["cumulative_cost_usd"] for r in rows]
+    assert cums == sorted(cums), f"cumulative must be NON-DECREASING, got {cums}"
+    assert cums == [0.5, 0.8, 1.0]
+    assert abs(cums[-1] - round(current_run_cost(), 4)) < 1e-9, "final == run total"
+    # generate rows no longer equal their OWN cost after >1 call (the old per-instance bug)
+    assert rows[-1]["cumulative_cost_usd"] != rows[-1]["cost_usd"]
+
+
+def test_bug10b_role_call_writes_inclusive_ledger_row(tmp_ledger):
+    rt = RecordingTransport(_FakeTransport())
+    rt.complete(RoleRequest(role="mirror", model_slug="z-ai/glm-5.1"))
+    rt.complete(RoleRequest(role="sentinel", model_slug="minimax/minimax-m2"))
+    role_rows = [r for r in _rows(tmp_ledger) if str(r.get("call_type", "")).startswith("role:")]
+    assert len(role_rows) == 2, "each four-role verifier call must write ONE ledger row"
+    assert {r["call_type"] for r in role_rows} == {"role:mirror", "role:sentinel"}
+    cums = [r["cumulative_cost_usd"] for r in role_rows]
+    assert cums == sorted(cums), "role-row cumulative must be NON-DECREASING"
+    assert abs(cums[-1] - round(current_run_cost(), 4)) < 1e-9, "inclusive of both calls"
+    assert role_rows[0]["cost_usd"] > 0, "non-zero role cost (floor guarantees > 0)"
+    assert {r["session_id"] for r in role_rows} == {_SID}
+
+
+def test_bug10b_role_cumulative_monotonic_under_parallel_workers(tmp_ledger):
+    """Codex iter-1 P1 repro: replicate sweep_integration's EXACT fan-out —
+    ThreadPoolExecutor + a per-worker contextvars.copy_context() snapshot (which INHERITS
+    `_CURRENT_RUN_ID_CTX` = the run id), each worker reset_run_cost()-ing ONLY its own copy.
+    With the OLD cumulative = current_run_cost(), each worker's run-cost restarts at 0, so the
+    interleaved role rows are per-worker / NON-monotonic. The shared per-session accumulator (bump
+    + append under one RLock) keeps every persisted role row's cumulative non-decreasing in WRITE
+    order and tagged with the ONE shared run id.
+    """
+    n_workers, calls_per_worker = 6, 5
+
+    def _worker(_widx):
+        reset_run_cost()  # zero ONLY this context copy's _RUN_COST_CTX (mirrors sweep_integration)
+        rt = RecordingTransport(_FakeTransport())
+        for _ in range(calls_per_worker):
+            rt.complete(RoleRequest(role="mirror", model_slug="z-ai/glm-5.1"))
+
+    with concurrent.futures.ThreadPoolExecutor(max_workers=n_workers) as pool:
+        futs = [
+            pool.submit(contextvars.copy_context().run, _worker, w) for w in range(n_workers)
+        ]
+        for f in futs:
+            f.result()
+
+    role_rows = [r for r in _rows(tmp_ledger) if str(r.get("call_type", "")).startswith("role:")]
+    assert len(role_rows) == n_workers * calls_per_worker
+    # ALL rows belong to the ONE shared (inherited) run id — NOT per-worker / "no_run_id".
+    assert {r["session_id"] for r in role_rows} == {_SID}
+    cums = [r["cumulative_cost_usd"] for r in role_rows]
+    assert cums == sorted(cums), (
+        f"GLOBAL role-row cumulative must be NON-DECREASING in file order under parallel "
+        f"workers, got {cums}"
+    )
+    # Final cumulative == the GLOBAL total of every role cost (per-worker current_run_cost() —
+    # the old approach — could only ever have shown one worker's share).
+    total = sum(r["cost_usd"] for r in role_rows)
+    assert abs(cums[-1] - round(total, 4)) < 1e-3
+    assert cums[-1] > role_rows[0]["cost_usd"], "the global total exceeds any single call's cost"
+
+
+def test_p2a_blank_attempt_costs_are_ledgered(tmp_ledger):
+    """P2a: the blank-verdict retry path adds run-budget cost; it must also write a ledger row so
+    the persisted total stays == the run-budget total. We exercise the canonical writer directly
+    with the same call_type the retry path uses (the live retry path needs a real HTTP 200 blank).
+    """
+    before = round(current_run_cost(), 4)
+    cum = orc.append_cost_ledger_row(
+        session_id=orc._CURRENT_RUN_ID_CTX.get() or "no_run_id",
+        call_type="role:mirror:blank_attempt",
+        cost_usd=0.0123,
+        input_tokens=80,
+        output_tokens=0,
+    )
+    rows = [r for r in _rows(tmp_ledger) if r.get("call_type") == "role:mirror:blank_attempt"]
+    assert len(rows) == 1
+    assert rows[0]["cost_usd"] == 0.0123
+    assert abs(rows[0]["cumulative_cost_usd"] - cum) < 1e-9
+    # The writer bumps the LEDGER accumulator (not _RUN_COST_CTX — the retry path calls
+    # _add_run_cost separately), so current_run_cost is unchanged by the writer alone.
+    assert round(current_run_cost(), 4) == before
+
+
+def test_p2b_free_call_ledgers_zero_not_phantom_estimate(tmp_ledger):
+    """P2b: a free call (operator loopback passes free=True) must ledger cost 0, NOT a phantom
+    paid-rate token estimate; and it must not advance the cumulative."""
+    usage = UsageTracker(session_id=_SID)
+    usage.record(call_type="loopback", input_tokens=5000, output_tokens=5000, api_cost=0.0, free=True)
+    rows = [r for r in _rows(tmp_ledger) if r.get("call_type") == "loopback"]
+    assert len(rows) == 1
+    assert rows[0]["cost_usd"] == 0.0, "free call must ledger 0, not a token-based estimate"
+    assert rows[0]["cumulative_cost_usd"] == 0.0
+    # Control: the SAME tokens WITHOUT free=True DO get the imputation backstop (invariant #6).
+    usage.record(call_type="paid_no_cost", input_tokens=5000, output_tokens=5000, api_cost=0.0)
+    paid = [r for r in _rows(tmp_ledger) if r.get("call_type") == "paid_no_cost"]
+    assert paid and paid[0]["cost_usd"] > 0.0, "paid call w/o reported cost still imputes (#6)"
+
+
+def test_p2c_ledger_write_failure_never_breaks_role_call(tmp_path, monkeypatch):
+    """P2c: FORCE a real write failure (point the ledger UNDER an existing file so .parent.mkdir
+    raises), then prove the role call still returns and no partial row is persisted."""
+    reset_run_cost()
+    reset_ledger_cumulative(_SID)
+    set_current_run_id(_SID)
+    blocker = tmp_path / "blocker_is_a_file"
+    blocker.write_text("x", encoding="utf-8")
+    bad = blocker / "sub" / "cost_ledger.jsonl"  # parent path traverses through a FILE
+    monkeypatch.setattr(orc, "_COST_LEDGER_PATH", bad)
+    try:
+        rt = RecordingTransport(_FakeTransport())
+        resp = rt.complete(RoleRequest(role="judge", model_slug="qwen/qwen3.6-35b-a3b"))
+        assert resp.raw_text == "ok", "best-effort ledger failure must NOT break the role call"
+        assert not bad.exists(), "no ledger file should have been created on the bad path"
+    finally:
+        reset_run_cost()
+        reset_ledger_cumulative(_SID)
+        set_current_run_id(None)
```
