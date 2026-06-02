HARD ITERATION CAP: 5 per document. This is iter 2 of 5.

## iter-1 → iter-2 changelog (Codex P1 + P2 + rulings ADOPTED)
- P1 (success manifest is INLINE): confirmed — the success path builds `manifest = {...}` inline at
  run_honest_sweep_r3.py:3331 with its OWN `"retrieval"` block at :3348 (bypasses `_base_manifest_envelope`).
  FIX: a single shared helper `_retrieval_manifest_section(retrieval) -> dict` (pre_filter, fetched, failed,
  api_calls, corpus_truncated, candidates_total, candidates_processed) is used by BOTH `_base_manifest_envelope`
  (abort paths) AND the inline success block (:3348). One writer → no path can omit the fields.
- P2: `candidates_processed` = the zero-based break index `i` (post-filter candidates whose loop iteration
  began), NOT `len(classified_sources)`. Normal exit sets processed = total = len(candidates).
- Gate seam (your ruling): per-run layer, NOT pathB_run_gate preflight (no corpus artifact there).
  (a) `pathB_runner.gate_around_question`: after the body `yield`, read manifest.json; if corpus_truncated,
      raise `GateError` → the EXISTING except-handler writes `pathB_gate_result.json {verdict: FAIL}` + the
      `pathB_gate_INVALID` sentinel (reuses the machinery; no new artifact path).
  (b) `score_run._check_polaris_gate`: backstop — read manifest.json; if corpus_truncated → raise
      InvalidRunError (independent of whether the gate ran).
- Recording is UNCONDITIONAL (no kill-switch) — it's the truth.
- `manifest["status"]` UNCHANGED; the flag blocks BOTH Path-B PASS and scoring (the minimum safe seam).
- Shared predicate `corpus_truncated_from_manifest(manifest) -> bool` in pathB_capture.py (fail-safe False on
  absence), imported by both consumers.


- Front-load ALL findings. Reserve P0/P1 for real execution risks.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## Output schema (emit FIRST, then ≤6 sentences)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

# BRIEF gate — #958 (S2): corpus truncation must be a fail-loud gate signal (no-spend)

Reviewing ACCEPTANCE CRITERIA + DESIGN (not a diff). CLINICAL-SAFETY SENSITIVE: a run that fetched only part
of its corpus before a wall-clock budget cutoff but emits 'success' is a silent under-coverage — a clinical
answer built on a truncated evidence base. The fix must make truncation VISIBLE (recorded) and make a
truncated corpus a non-clean signal the gate can act on. NO SPEND.

## The finding (issue #958, Codex-area CONFIRMED #950) — grounded in real code
`live_retriever.run_live_retrieval` has a post-fetch loop with a wall-clock budget
(`PG_POST_FETCH_LOOP_BUDGET`, default 900s). When exceeded it `break`s mid-loop
(live_retriever.py ~1695-1701), classifying only the candidates reached so far — and emits ONLY a
`logger.warning(...)`. The break is invisible downstream: `LiveRetrievalResult` has no truncation field, the
manifest's `env["retrieval"]` (run_honest_sweep_r3.py `_base_manifest_envelope` ~261) records only
pre_filter/fetched/failed/api_calls, and the run still reaches a 'success' status. Combined with no
arrival-order rerank on the slow first batch (now fixed by #959), the most relevant later candidates may never
be fetched, yet the report ships as success.

## Proposed design (contained, additive, no-spend)
1. `LiveRetrievalResult` (dataclass) gains `corpus_truncated: bool = False`, `candidates_total: int = 0`,
   `candidates_processed: int = 0` (defaults preserve every existing constructor call). In the budget-break
   branch, set a local `corpus_truncated = True`, capture `i` (processed) and `len(candidates)` (total); the
   warning stays. Pass the three values into the returned `LiveRetrievalResult`. (`candidates_processed`/
   `candidates_total` are also populated on the normal non-truncated exit = len(candidates)/len(candidates)
   so consumers always see counts.)
2. `_base_manifest_envelope`: `env["retrieval"]` gains `"corpus_truncated"`, `"candidates_total"`,
   `"candidates_processed"` from the retrieval result (getattr with defaults — backward compatible). This is
   the "record corpus_truncated=true + counts in manifest.json" requirement.
3. Gate-side: add a small reusable predicate `corpus_truncated_from_manifest(manifest) -> bool` (reads
   `manifest["retrieval"]["corpus_truncated"]`, fail-safe False on absence) and wire it as a signal so a
   truncated corpus is treated as PARTIAL/INVALID rather than a clean pass.

## Open questions for you to rule on
1. WHERE should the gate-side enforcement live? Candidates: (a) `scripts/dr_benchmark/pathB_run_gate.py`
   (the pre-rental gate — but it gates control-surface/preflight/architecture, not per-run corpus); (b)
   `pathB_runner.py` / the gate_b run scorer (per-run manifest consumer); (c) the manifest status taxonomy
   in run_honest_sweep_r3.py (add a `partial_corpus_truncated` status or a top-level
   `manifest["corpus_truncated"]` flag that downstream scoring treats as partial). I lean (c) record-flag +
   (b) consumer-check, leaving the success taxonomy intact but carrying the flag. Rule on the right seam.
2. Should `manifest["status"]` itself change (e.g. success → partial) when truncated, or stay 'success' with a
   separate `corpus_truncated` flag the scorer/gate reads? (Changing BUG-B-101 status taxonomy is heavier; a
   flag is more conservative. Your call.)
3. Kill-switch needed, or is recording-a-true-fact unconditional (no flag)? (I lean: recording is
   unconditional — it's the truth; only the gate's TREATMENT of it could be configurable. Rule.)

## Files I have ALSO checked
- live_retriever.py: budget loop (~1688 `_loop_deadline`), break (~1696-1701), result construction (~1831);
  `LiveRetrievalResult` dataclass (~67). The per-URL 90s deadline (~1094) is a separate layer (unchanged).
- run_honest_sweep_r3.py: `_base_manifest_envelope` (~237-265); unified manifest.status taxonomy (BUG-B-101,
  ~158-220); abort statuses (~2038 corpus_inadequate etc.).
- scripts/dr_benchmark/pathB_run_gate.py (649 lines: control surface + preflight + architecture coverage).

## Acceptance criteria (iter 2)
A. `LiveRetrievalResult` carries corpus_truncated + candidates_total + candidates_processed (defaults keep all
   existing constructors valid); the budget-break sets corpus_truncated=True, candidates_processed=i,
   candidates_total=len(candidates); normal exit sets processed=total=len(candidates), truncated=False.
B. `_retrieval_manifest_section(retrieval)` is the SINGLE retrieval-section writer; used by BOTH
   `_base_manifest_envelope` AND the inline success manifest (:3348) — both record corpus_truncated + counts.
C. `corpus_truncated_from_manifest(manifest)` predicate (fail-safe False). `gate_around_question` raises
   GateError on truncation (→ existing FAIL + INVALID sentinel before PASS); `_check_polaris_gate` raises
   InvalidRunError on truncation (scoring backstop). Recording unconditional; status unchanged.
D. Tests: budget-break sets corpus_truncated=True + processed=i; non-truncated = False + full counts;
   `_retrieval_manifest_section` carries the fields; predicate fail-safe; gate raises GateError + writes
   INVALID on a truncated manifest; `_check_polaris_gate` raises InvalidRunError on a truncated manifest.
   Existing live_retriever + pathB_runner + score_run tests stay green.

Is this iter-2 design correct + safe (single retrieval-section writer so no manifest path omits the flag;
both per-run consumers reject truncation; recording unconditional; no silent success)?
