# Claude architect audit — #958 (S2): corpus truncation = fail-loud gate signal

**Branch:** `bot/I-meta-002-q1d-truncation` (stacked on the #956 branch — shares live_retriever.py). **Brief
gate:** APPROVE iter 2 (P1 inline-success-manifest + P2×2 adopted). **Diff gate:** pending. **NO SPEND.**

## Why
The post-fetch loop budget (PG_POST_FETCH_LOOP_BUDGET, 900s) broke mid-corpus and emitted ONLY a
`logger.warning` — invisible downstream; the run still reached 'success'. A clinical answer built on a
partial corpus shipped as clean. The fix makes truncation a recorded, gate-and-scorer-blocking signal.

## Fix (5 files, Codex iter-2 design)
1. live_retriever: `LiveRetrievalResult` carries corpus_truncated + candidates_total/processed; counters
   init'd BEFORE the loop (P2b); budget-break sets corpus_truncated=True, candidates_processed=i (P2).
2. run_honest_sweep_r3: `_retrieval_manifest_section()` = the SINGLE retrieval-section writer; used by both
   `_base_manifest_envelope` AND the inline success manifest (the P1 fix — success path previously bypassed
   the envelope).
3. pathB_capture: `corpus_truncated_from_manifest()` fail-safe predicate (no scripts dep).
4. pathB_runner.gate_around_question: truncation check at the top of the existing post-run GateError block
   before any PASS write (P2a) → reuses the FAIL + INVALID-sentinel machinery.
5. score_run._check_polaris_gate: backstop — raises InvalidRunError on a truncated manifest, independent of
   the gate. status unchanged; recording unconditional (no kill-switch).

## Safety
- No path can omit the flag (single shared writer covers abort + inline success).
- Both per-run consumers reject truncation (gate blocks PASS; scorer blocks scoring) — the minimum safe seam.
- Fail-safe predicate + backward-compatible getattr → pre-#958 manifests/objects never crash or false-reject.
- Recording is the truth (unconditional); manifest.status taxonomy untouched.

## Tests
6 new (predicate true/false/absent/None; dataclass defaults; shared writer carries truncation+counts; scorer
backstop rejects truncated + clean passes the truncation check) + 125 existing dr_benchmark pathB/gate tests
+ 39 live_retriever/retrieval_trace tests pass. `py_compile` OK on all 5 files.

## Verdict
Truncation is now recorded on the result → manifest (single writer) → blocked by both the Path-B gate and the
scorer; P2a/P2b honored; recording unconditional; status unchanged; offline-tested NO SPEND. Brief APPROVE
iter 2; diff gate next. This is the LAST of the four S2 depth refinements.
