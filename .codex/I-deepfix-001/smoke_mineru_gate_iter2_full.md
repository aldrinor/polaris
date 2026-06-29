HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

STATIC review (read-only), FOCUSED + FAST. Do NOT run pytest.

CONTEXT: `scripts/dr_benchmark/run_gate_b.py`. iter-1 found 1 P1: the unconditional winner-exact-value assertion loop (~2525) required PG_CLINICAL_PDF_EXTRACTOR='mineru25' even on a smoke, so the smoke's PG_CLINICAL_PDF_EXTRACTOR='docling' override (added to _SMOKE_SCALE_OVERRIDES to dodge the mineru25 GPU-VLM native SIGABRT that killed the whole run) would FAIL preflight.

THE iter-2 FIX (this diff): in the assertion loop (~2525-2540), when `smoke_scale and _winner_flag == "PG_CLINICAL_PDF_EXTRACTOR"`, set `_winner_expected = "docling"` before the equality check — so the smoke expects 'docling' and the PAID run (smoke_scale=False) still requires the slate's 'mineru25'. Plus the smoke override `PG_CLINICAL_PDF_EXTRACTOR=docling` in _SMOKE_SCALE_OVERRIDES, and two comment updates (~1365 and ~2518).

YOUR TASK — verify ONLY:
1. The iter-1 P1 is RESOLVED: on a smoke, the assertion loop now accepts PG_CLINICAL_PDF_EXTRACTOR='docling' (no RuntimeError); `smoke_scale` is in scope (it is a parameter of preflight_full_capability). Confirm the special-case is scoped to ONLY that one key and ONLY when smoke_scale is True.
2. PAID path UNCHANGED: when smoke_scale=False, the loop still requires every winner including PG_CLINICAL_PDF_EXTRACTOR='mineru25' (the override and the special-case both only apply on smoke). A paid run is byte-identical.
3. No OTHER preflight/postflight gate fails the smoke for W4 not firing with docling (you confirmed the conditional W4 GPU gate + firing marker are tolerant in iter-1; re-confirm nothing new).
4. The two comment updates are accurate (no remaining stale 'smoke does not touch winners' / 'mineru25 never crashes' claims) and no NEW bug.

If resolved with no NEW/continuing P0/P1, APPROVE.

OUTPUT EXACTLY THIS SCHEMA (LAST line starts with `verdict:`):
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]

=== THE DIFF UNDER REVIEW ===
```diff
diff --git a/scripts/dr_benchmark/run_gate_b.py b/scripts/dr_benchmark/run_gate_b.py
index e9b3b929..efb09ee2 100644
--- a/scripts/dr_benchmark/run_gate_b.py
+++ b/scripts/dr_benchmark/run_gate_b.py
@@ -1362,12 +1362,15 @@ _FULL_CAPABILITY_BENCHMARK_SLATE: dict[str, str] = {
     #   / the FROZEN faithfulness contract). NOT slate-forced / NOT preflight-required; named in the
     #   build-deferred WARNING. Do NOT add a "W9 flag" until a real consolidate-keep-all content-dedup
     #   stage is wired onto the sweep evidence path.
-    # SMOKE NOTE: _SMOKE_SCALE_OVERRIDES does NOT override any winner above, so a --smoke-scale run
-    # DELIBERATELY inherits the real winner models (Qwen3 embed/rerank + mineru25) as genuine
-    # model-loading plumbing coverage — a smoke on the default MiniLM would never exercise the
-    # winner-model load path, so a load bug would surface only on the expensive full run. Gate-B
-    # model-loading runs land on the GPU VM per the VM-only run policy; mineru25 degrades gracefully
-    # (logged, fetch-degraded) on a no-GPU host, never a crash.
+    # SMOKE NOTE: _SMOKE_SCALE_OVERRIDES inherits the real EMBED/RERANK winners (Qwen3 embed/rerank) as
+    # genuine model-loading plumbing coverage — a smoke on the default MiniLM would never exercise the
+    # winner-model load path, so a load bug would surface only on the expensive full run. EXCEPTION
+    # (I-deepfix-001 #1344): the smoke pins PG_CLINICAL_PDF_EXTRACTOR=docling (NOT the slate's mineru25)
+    # because the mineru25 GPU-VLM crashed the whole run with a NATIVE SIGABRT (uncatchable abort() inside
+    # transformers .generate(), rc=134) before the back half ran — so the smoke validates the back-half
+    # plumbing on the safe docling->PyMuPDF PDF path. mineru25 firing + its crash-isolation (subprocess/
+    # hard-kill) is the queued fix before the paid run. Gate-B model-loading runs land on the GPU VM per
+    # the VM-only run policy.
 }
 
 # Minimum effective values the run MUST meet — the preflight FAILS CLOSED if any is below these (i.e.
@@ -2232,6 +2235,16 @@ _SMOKE_SCALE_OVERRIDES: dict[str, str] = {
     # the SUPER-HEAVY pre-spend preflight requires discovery to return >= this many candidate URLs
     # (default 100); the smoke discovers ~20-40, so lower the floor or it aborts before the sweep.
     "PG_PREFLIGHT_MIN_BREADTH": "10",        # was 100
+    # I-deepfix-001 (#1344) SMOKE-CRASH FIX: the W4 mineru25 GPU-VLM PDF parser (the full slate forces
+    # PG_CLINICAL_PDF_EXTRACTOR=mineru25) crashed the WHOLE run with a native `Fatal Python error:
+    # Aborted` (SIGABRT, rc=134) inside transformers `.generate()` during VLM layout-detect on a PDF —
+    # a native abort() is uncatchable by the mineru circuit-breaker / per-call timeout / try-except, so
+    # it killed the process mid-retrieval before the back half ever ran. The PLUMBING smoke only needs
+    # PDF BODIES (which docling->PyMuPDF extracts faithfully — §-1.3: every source kept, faithfulness
+    # untouched), NOT the VLM layout fidelity. Pin the smoke to the safe default extractor so the smoke
+    # can validate the back half (generation->4role->strict_verify->render). PAID slate keeps mineru25
+    # (W4 winner); its crash-isolation (subprocess/hard-kill) is the queued fix before the paid run.
+    "PG_CLINICAL_PDF_EXTRACTOR": "docling",  # smoke: no GPU-VLM (avoids the mineru25 SIGABRT); paid keeps mineru25
     # I-cred-008b basket-coverage gate scales with breadth; keep the super-heavy preflight's own
     # gates ON (faithfulness/behavioral) — only the BREADTH-count floor is lowered for the smoke.
     # timeout hierarchy — coherent retrieval-wall < run-wall (with back-half headroom) AND
@@ -2509,10 +2522,17 @@ def preflight_full_capability(smoke_scale: bool = False, offline: bool = False)
     # they cannot ride the truthy required-flags loop above ("qwen3"/"mineru25"/"Qwen/Qwen3-Reranker-0.6B"
     # are not "1"), the SAME reason PG_RELEVANCE_SCORER is asserted separately. Fail CLOSED so a dropped
     # force-exact pin or a stray/empty value can never silently leave a model winner OFF (the default
-    # model would run). Unconditional (smoke + full): the slate force-exacts these on BOTH paths
-    # (_SMOKE_SCALE_OVERRIDES does not touch them), so the assertion passes on a smoke too and a smoke
+    # model would run). The slate force-exacts these; the assertion passes on the paid run and a paid run
     # genuinely exercises the winner-model load path. FAITHFULNESS-NEUTRAL (model choice; engine frozen).
+    # I-deepfix-001 (#1344) SMOKE EXCEPTION (one key): the smoke pins PG_CLINICAL_PDF_EXTRACTOR=docling
+    # (the safe non-VLM docling->PyMuPDF PDF path) to dodge the mineru25 GPU-VLM native SIGABRT that was
+    # killing the whole run before the back half — so on a smoke this ONE key is expected to be 'docling'
+    # while the PAID run still requires the slate's 'mineru25'. All OTHER winners stay asserted on BOTH
+    # paths (the smoke genuinely loads Qwen3 embed/rerank etc.). §-1.3: docling extracts the PDF body, no
+    # source dropped; mineru25-on-paid + its crash-isolation is the queued fix before the paid run.
     for _winner_flag, _winner_expected in _BENCHMARK_WINNER_EXACT_VALUE_ASSERTIONS.items():
+        if smoke_scale and _winner_flag == "PG_CLINICAL_PDF_EXTRACTOR":
+            _winner_expected = "docling"   # smoke: safe non-VLM PDF path; paid keeps mineru25
         _winner_value = os.getenv(_winner_flag, "").strip()
         if _winner_value != _winner_expected:
             raise RuntimeError(
```
