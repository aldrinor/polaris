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
