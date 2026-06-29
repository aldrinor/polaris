HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings now. Reserve P0/P1 for real execution risks.
Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

STATIC review (read-only), FOCUSED + FAST. Do NOT run pytest. Do NOT re-audit the whole pipeline.

CONTEXT: POLARIS benchmark harness `scripts/dr_benchmark/run_gate_b.py`. `--smoke-scale` applies `_SMOKE_SCALE_OVERRIDES` (force-set into os.environ AFTER the full-capability slate's FLOOR/force-exact loop, at ~line 2291-2293) for a fast plumbing smoke. The full slate force-sets `PG_CLINICAL_PDF_EXTRACTOR=mineru25` (W4 winner, run_gate_b.py:1338/1868, in the force-exact allowlist ~1791/2072).

THE BUG THIS FIXES (confirmed from a real run, rc=134): on the smoke, mineru25 (the W4 GPU-VLM clinical-PDF parser) crashed the WHOLE process with a native `Fatal Python error: Aborted` (SIGABRT) inside transformers `.generate()` (access_bypass.py:5022 `_mineru25_extract` -> mineru vlm_analyze.py:151). A native abort() is uncatchable by the mineru circuit-breaker / per-call timeout / try-except, so it killed the run mid-retrieval before the back half (generation->4role->strict_verify->render) ever executed.

THE FIX (this diff, in `_SMOKE_SCALE_OVERRIDES` only): add `PG_CLINICAL_PDF_EXTRACTOR=docling` so the smoke uses the safe default PDF path (docling->PyMuPDF) instead of the crashing GPU-VLM. Smoke-only; the paid slate keeps mineru25.

YOUR TASK — verify ONLY these properties:
1. CORRECTNESS: on a smoke run, after `_SMOKE_SCALE_OVERRIDES` is force-applied (the 2291-2293 direct os.environ assignment, AFTER the slate force-exact loop), `PG_CLINICAL_PDF_EXTRACTOR` resolves to `docling` (not `mineru25`). Confirm the smoke override genuinely wins over the slate's force-exact assignment for this key (i.e. nothing re-forces mineru25 after the smoke loop).
2. NO WINNER-FIRES ASSERTION BREAK (the critical check): with `PG_CLINICAL_PDF_EXTRACTOR=docling` on a smoke, does ANY preflight OR postflight gate FAIL the run for W4 not firing? Inspect: the W4 pre-spend GPU-present gate (~run_gate_b.py:2830-2846, which only triggers when ==mineru25), and the post-run firing-marker check (W4_clinical_pdf_mineru25 is `conditional=True`, ~1958). Confirm a smoke with extractor=docling does NOT raise a 'W4 winner did not fire' / 'required winner missing' error (conditional + extractor-off must be tolerated, AND/OR smoke_scale must be exempt). If it WOULD fail the smoke, that is a P1 — report the exact file:line.
3. PAID PATH UNTOUCHED: the full slate keeps PG_CLINICAL_PDF_EXTRACTOR=mineru25; a non-smoke run is byte-identical.
4. FAITHFULNESS-NEUTRAL / §-1.3: docling->PyMuPDF still extracts the PDF body (no source dropped, no faithfulness gate touched); only PDF-parse fidelity (VLM layout) is reduced for the smoke.
5. NO NEW BUG introduced by the one-line addition.

If correct with no NEW P0/P1, APPROVE. If a real NEW P0/P1, REQUEST_CHANGES with exact file:line.

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
index e9b3b929..c3bda590 100644
--- a/scripts/dr_benchmark/run_gate_b.py
+++ b/scripts/dr_benchmark/run_gate_b.py
@@ -2232,6 +2232,16 @@ _SMOKE_SCALE_OVERRIDES: dict[str, str] = {
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
```
