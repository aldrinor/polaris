HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL findings. Reserve P0/P1 for real execution risks.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
- Read ONLY `.codex/I-meta-002-q1d-truncation/codex_diff.patch`. Emit the YAML verdict block FIRST, then ≤6 sentences.

## Output schema (emit FIRST)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

# DIFF gate — #958 (S2): corpus truncation = fail-loud gate signal. Patch: 5 src/script + 1 test, +186/-12 (non-test +94).

You APPROVED the iter-2 design. Verify the patch implements it EXACTLY, honoring the two P2 guardrails:
(P2a) the truncation check is inside gate_around_question's existing post-run GateError-handled block before
any PASS write; (P2b) the retrieval counters are initialized BEFORE the loop so the empty/no-break path does
not depend on a loop-local `i`.

## What the patch does (5 files)
1. `live_retriever.py`: `LiveRetrievalResult` gains `corpus_truncated: bool=False`, `candidates_total:int=0`,
   `candidates_processed:int=0` (defaults preserve existing constructors). Counters initialized BEFORE the
   post-fetch loop (P2b): `_corpus_truncated=False`, `_candidates_total=len(candidates)`,
   `_candidates_processed=len(candidates)`. On the budget-break: `_corpus_truncated=True`,
   `_candidates_processed=i` (the zero-based break index, P2). The three are passed to the returned result.
2. `run_honest_sweep_r3.py`: new `_retrieval_manifest_section(retrieval)` is the SINGLE retrieval-section
   writer (adds corpus_truncated + candidates_total/processed, all getattr-with-default). Used by BOTH
   `_base_manifest_envelope` (abort paths) AND the inline success manifest's `"retrieval"` (the P1 fix — the
   success path previously had its own inline block that bypassed the envelope).
3. `pathB_capture.py`: `corpus_truncated_from_manifest(manifest) -> bool` (fail-safe False on absence/malformed;
   zero `scripts` dependency, so both consumers can import it).
4. `pathB_runner.gate_around_question`: at the TOP of the existing post-run `try` (before assert_post_run /
   PASS write), read manifest.json and if corpus_truncated raise `GateError` → caught by the EXISTING
   `except GateError` handler → writes `pathB_gate_result.json {verdict: FAIL}` + the `pathB_gate_INVALID`
   sentinel (reuses the proven machinery; P2a).
5. `score_run._check_polaris_gate`: backstop — reads manifest.json; if corpus_truncated raise InvalidRunError
   (independent of the gate). `manifest["status"]` is UNCHANGED; the flag blocks BOTH PASS and scoring.

## Evidence (verified by Claude main-thread, NO SPEND)
- 6 new tests pass: predicate true/false/absent/None fail-safe; LiveRetrievalResult defaults not-truncated;
  `_retrieval_manifest_section` carries truncation + counts (truncated and clean); scorer backstop raises
  InvalidRunError("corpus truncated") on a truncated manifest; a CLEAN manifest does NOT trip the truncation
  backstop (it fails later for the missing gate result — a different error).
- 125 existing dr_benchmark pathB/gate tests pass (pathB_runner, pathB_run_gate, pathB_capture, pr3_pipeline,
  gate_b_seam, offline_e2e) + 39 live_retriever/retrieval_trace tests pass. `py_compile` OK on all 5 files.

## The real risks to rule on
1. Does the SINGLE `_retrieval_manifest_section` writer guarantee corpus_truncated lands on EVERY manifest
   path (abort + the inline success block)? (The success-path inline `"retrieval"` now calls it.)
2. Is `candidates_processed` the break index `i` (P2), and are the counters init'd before the loop so a
   no-break / empty-candidates run reports processed=total, truncated=False (P2b)?
3. Does the gate check sit inside the existing GateError-handled block before any PASS write, reusing the
   FAIL + INVALID-sentinel machinery (P2a)?
4. Does the scorer backstop reject a truncated manifest independently, while a clean manifest is unaffected?
5. Recording unconditional (no kill-switch); status unchanged; fail-safe predicate; backward-compatible
   getattr so pre-#958 retrieval objects don't crash the writer?
6. Anything beyond the 5 files / beyond the approved design?

APPROVE iff the diff makes truncation a recorded, gate-and-scorer-blocking signal via the single shared
manifest writer + the two named per-run consumers, honors P2a/P2b, keeps recording unconditional and status
unchanged, and breaks no existing pathB/retriever test.
