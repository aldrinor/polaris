HARD ITERATION CAP: 5 per document. This is iter 3 of 5.
Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

STATIC review (read-only), FOCUSED + FAST — do NOT re-audit the whole pipeline (iter-1 and iter-2 already confirmed the end-to-end wall-class completeness AND that P1#1 generator-run-wall-on-Gate-B + P1#2 strict_verify kept_disclosure_label are fully resolved; do NOT re-open those). Do NOT run pytest.

YOUR ONLY TASK this iter: verify the TWO small iter-2 P1 fixes are correct + introduce no regression. Read ONLY these two regions of `scripts/run_honest_sweep_r3.py`:

A) ~lines 12568-12595 — W12 excessive-gap disclose-and-ship. The import was changed from the NONEXISTENT `src.polaris_graph.generator.release_policy` to the real `src.polaris_graph.roles.release_policy` (which defines `always_release_enabled`). VERIFY: the import now resolves, and the W12 ship-the-verified-remainder path no longer raises ImportError. Confirm nothing else in this block depends on the old (wrong) path.

B) ~lines 7155-7185 — W13 intent-frame worker timeout. It NO LONGER uses `with _intent_frame_futures.ThreadPoolExecutor(...) as _ex:` (whose __exit__ shutdown(wait=True) blocked the event-loop thread on a wedged worker at the `.result(timeout=...)` expiry). It now creates `_ex = _intent_frame_futures.ThreadPoolExecutor(max_workers=1)` explicitly, returns `_ex.submit(_worker).result(timeout=...)`, and in `finally` calls `_ex.shutdown(wait=False, cancel_futures=True)` (TypeError-guarded for py<3.9) BEFORE the existing cost-delta restore. VERIFY: (a) on the `.result()` TimeoutError the loop is freed immediately (shutdown does NOT wait) and the error propagates to the W13/IntentFrameError degrade; (b) the cost-delta `finally` still runs; (c) the success path (normal return) is unchanged; (d) no NEW bug (double-shutdown, leaked reference, swallowed exception).

If both are correct with no NEW P0/P1, APPROVE — this gate is the green-light for the paid re-smoke. If you spot a real NEW P0/P1 in THESE TWO regions, REQUEST_CHANGES with the exact file:line.

OUTPUT EXACTLY THIS SCHEMA (LAST line starts with `verdict:`):
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
