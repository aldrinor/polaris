HARD ITERATION CAP: 5 per document. This is iter 1 of 5. Front-load ALL findings. Reserve P0/P1 for real blockers. Verdict APPROVE iff zero P0 and zero P1.

FRONTIER-TECH: review against sound 2025-2026 practice; no grandfather assumptions.

Review this POLARIS tiering-starvation fix (I-deepfix-001 #1344 followup). CONTEXT: Run A aborted at abort_corpus_approval_denied because the credibility LLM-tiering batch was handed an ALREADY-EXPIRED retrieval deadline (slow fetch consumed the 1800s wall), so min(expired, now+batch_wall)==expired and the batch tiered ZERO of 20 sources -> all rules-floored -> false T4-dominant corpus -> abort. The fix gives tiering its OWN budget from now (PG_TIER_LLM_BATCH_WALL_SECONDS, default 600s) and only tightens to the retrieval wall when that wall is still in the FUTURE.

QUESTIONS: (1) Is this faithfulness-NEUTRAL? It must NOT touch strict_verify/NLI/D8/provenance — it only changes how many sources get a real GLM tier vs the deterministic rules-floor (a WEIGHT, never a drop; all sources kept, §-1.3). (2) Does it correctly stop the zero-tier without letting the batch run unbounded (the 600s batch wall + the still-future retrieval-wall tightening must both hold)? (3) Any P0/P1 correctness/safety issue (e.g. could it now run tiering long past a legitimately-short run wall)? (4) The batch-wall-disabled branch sets None when the retrieval wall is expired — is unbounded acceptable there (only when PG_TIER_LLM_BATCH_WALL_SECONDS<=0, an explicit opt-out)?

THE DIFF:
commit 936b26569f2c333fb945464ee41b3911b869bc10
Author: msn <msn@polaris.dev>
Date:   Thu Jul 2 06:58:45 2026 -0700

    I-deepfix-001 (#1344 followup): tiering-starvation fix — expired retrieval wall no longer zero-tiers
    
    Run A aborted at abort_corpus_approval_denied: the credibility LLM-tiering batch was handed the
    ALREADY-EXPIRED retrieval deadline (slow fetch consumed the 1800s wall), so min(expired, now+batch_wall)
    == the expired instant and the batch tiered ZERO of 20 sources -> all rules-floored -> false
    T4-dominant corpus -> abort. Fix: tiering gets its OWN budget from now (PG_TIER_LLM_BATCH_WALL_SECONDS,
    600s), tightening to the retrieval wall only when that wall is still in the FUTURE. Faithfulness-NEUTRAL
    (weight-tiering completeness, never a drop, all sources kept, §-1.3; strict_verify/NLI/D8/provenance
    untouched). Forced-positive proven on box: expired deadline -> 6/6 tiered (was 0).
    
    Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
    Claude-Session: https://claude.ai/code/session_01KJhHYhrBZNLiiEngsqhRV8

diff --git a/src/polaris_graph/retrieval/credibility_llm_tiering.py b/src/polaris_graph/retrieval/credibility_llm_tiering.py
index 919acb8f..29c26979 100644
--- a/src/polaris_graph/retrieval/credibility_llm_tiering.py
+++ b/src/polaris_graph/retrieval/credibility_llm_tiering.py
@@ -536,11 +536,31 @@ def _run_llm_tiering_parallel(
     # consecutive-fallback circuit-breaker. The TIGHTER (earlier) of the threaded
     # `deadline_monotonic` (the caller's retrieval wall) and the env fallback wins.
     _batch_wall = _tier_llm_batch_wall_seconds()
-    _eff_deadline = deadline_monotonic
+    _now_monotonic = time.monotonic()
+    # I-deepfix-001 (#1344 followup — tiering-starvation fix, Run A 2026-07-02): credibility
+    # tiering is a CHEAP WEIGHT (T1-T7) whose INCOMPLETENESS silently fabricates a false
+    # material-deviation corpus — every un-tiered source defaults to the deterministic
+    # rules-floor, which the downstream corpus_approval gate reads as a T4-dominant skew and
+    # ABORTS. Run A proved the failure: the retrieval wall had ALREADY been consumed by a slow
+    # fetch, so ``deadline_monotonic`` arrived here already in the PAST; the old
+    # ``min(expired, now + batch_wall)`` == the expired instant, so the loop broke on the first
+    # iteration and tiered ZERO of 20 sources -> false T4-dominant -> abort_corpus_approval_denied.
+    # Tiering therefore gets its OWN budget from NOW (``_batch_wall``, default 600s), and only
+    # tightens to the caller's retrieval wall when that wall is STILL IN THE FUTURE. This is
+    # faithfulness-NEUTRAL: it only changes how many sources receive a real GLM tier vs the
+    # deterministic rules-floor (a WEIGHT, never a drop — every source is kept either way, §-1.3);
+    # it never touches strict_verify / NLI / D8 / provenance.
     if _batch_wall > 0:
-        _wall_instant = time.monotonic() + _batch_wall
+        _eff_deadline = _now_monotonic + _batch_wall
+        if deadline_monotonic is not None and deadline_monotonic > _now_monotonic:
+            _eff_deadline = min(_eff_deadline, deadline_monotonic)
+    else:
+        # Batch wall disabled (``PG_TIER_LLM_BATCH_WALL_SECONDS <= 0``): only a STILL-FUTURE
+        # retrieval wall bounds the batch; an already-expired one is ignored (never zero-tier).
         _eff_deadline = (
-            _wall_instant if _eff_deadline is None else min(_eff_deadline, _wall_instant)
+            deadline_monotonic
+            if (deadline_monotonic is not None and deadline_monotonic > _now_monotonic)
+            else None
         )
     _degrade_after = _tier_llm_degrade_after()
     _consecutive_fallbacks = 0


Output schema: verdict: APPROVE|REQUEST_CHANGES then p0/p1/p2 lists.
