# Codex round 2 — M-LIVE-1 v2 (5 R1 findings closed)

## Pre-flight
- Branch: `polaris`
- Commit: `<FILL_AFTER_COMMIT>`
- Brief format: `.codex/REVIEW_BRIEF_FORMAT_v2.md` (autoloop V3)
- Smoke output: `outputs/m_live_1_smoke/run_<timestamp>/smoke_manifest.json`

## R1 findings (all 5 closed in v2)

**P0 #1 — Harness can report GREEN on wrong run.**
- Fix: `scripts/run_m_live_1_smoke.py` now creates a
  timestamped run-scoped subdir per invocation
  (`outputs/m_live_1_smoke/run_YYYYMMDD_HHMMSS/`); verifiers
  scan only that dir.
- Fix: `all_phase_e_fired` now requires `sweep_rc == 0` AND
  `not_fired_substrates == []`. Process exit code respects the
  same gate. A failed sweep can no longer inherit stale
  artifacts and pass.

**P0 #2 — M-INT-0b false positive (no success marker).**
- Codex R1 correctly noted production code emits no success
  `[M-INT-0b]` stdout marker; only WARN markers on failure
  (`run_honest_sweep_r3.py:1000`).
- Fix: `_verify_m_int_0b()` requires `sweep_rc == 0` AND
  `model_pin.json` present. Acceptance bar updated to
  "file written + sweep succeeded" (the marker requirement
  was a brief-drafting error in v1).

**P0 #3 — M-INT-6 false positive (queue conditional on abstain).**
- Codex R1 correctly noted `operator_review_queue.jsonl` is
  only written on `abstain` decision; current run logged
  `decision=accept`, queue file absent, and v1 verifier passed
  via OR fallback.
- Fix: `_verify_m_int_6()` requires the
  `[M-INT-6] inductor:` run_log marker (load-bearing) and
  treats the queue file as informational. Acceptance bar
  updated to reflect substrate semantics: queue write is
  conditional, marker emission is not.

**P1 #1 — 12 vs 13 substrate count.**
- v1 brief said "12 substrates"; v1 manifest emitted 13.
- Fix: Phase E has 13 distinct substrates (M-INT-0a + 0b +
  1..11). v2 brief uses 13 throughout. Manifest emits
  `expected_substrates: 13`, `fired_count: 13`.

**P1 #2 — Endpoint checkers accept 200 OR 201.**
- Fix: M-INT-9/10/11 checkers now require exact `201`. M-INT-0a
  requires `200` (route_query is GET semantics). M-INT-8
  requires `200` (slide-deck GET).

## Scope
First Phase F milestone. Verifies all 13 Phase E integration
substrates fire end-to-end on a single real audit query.

## Tool hints
- `python scripts/run_m_live_1_smoke.py` → fresh run
- Read in full:
  - `scripts/run_m_live_1_smoke.py`
  - `outputs/m_live_1_smoke/run_<latest>/smoke_manifest.json`
  - `outputs/m_live_1_smoke/run_<latest>/clinical/clinical_tirzepatide_t2dm/manifest.json`
- Do NOT re-litigate R1 findings already addressed in v2

## Acceptance bar (v2)
1. **Sweep runs cleanly.** `rc=0`, manifest.json valid JSON.
2. **All 13 Phase E substrates fire** with verifiable sink:
   - M-INT-0a: `decision_rows_after > decision_rows_before`
     after `POST /api/inspector/templates/route` returns 200
   - M-INT-0b: `model_pin.json` present in run-scoped dir AND
     `sweep_rc == 0` (production code emits no success marker;
     file presence + clean exit is the contract)
   - M-INT-1: manifest.json
     `retrieval.api_calls.parallel_fetch_success_count` present
   - M-INT-2: stdout `[M-INT-2] cache_warming` marker
   - M-INT-3: stdout `[M-INT-3] sweep_freshness_summary` marker
   - M-INT-4: run_log.txt `[M-INT-4] scope_llm:` marker
   - M-INT-5: run_log.txt `[M-INT-5] domain_router:` marker
   - M-INT-6: run_log.txt `[M-INT-6] inductor:` marker
     (queue file is conditional on abstain decision; not
     load-bearing for the substrate-fired check)
   - M-INT-7: stdout `[M-INT-7] billing_quota:` marker
   - M-INT-8: GET `/api/inspector/runs/{slug}/slide-deck`
     returns 200
   - M-INT-9: POST `/api/inspector/contract-drafts` returns 201
   - M-INT-10: POST `/api/inspector/private-corpus-sources`
     returns 201
   - M-INT-11: POST `/api/inspector/support-tickets` returns 201
3. **smoke_manifest.json**: `all_phase_e_fired=true`,
   `fired_count=13`, `sweep_rc=0`, `expected_substrates=13`.

## Severity rubric
- **P0** — production-breaker: smoke falsely reports GREEN;
  sweep crashes; sink claim wrong; rollback flag broken; stale
  artifacts inherited
- **P1** — phase-rework: acceptance criterion not met
- **P2** — governance precision: bounded blast radius
- **P3** — polish: naming, comments, style

**APPROVE iff zero P0 + zero P1.** P2/P3 → `deferred_polish`,
non-blocking.

## Reviewer instructions
- Find ALL P0/P1 defects. If zero, write **"no P0/P1 found"**
  explicitly — do not manufacture findings.
- Do NOT re-raise R1 findings already addressed (would be a
  defect per the autoloop V3 protocol). In-scope: regressions
  in v2 patch + P0/P1 missed in R1.

## Skepticism gate
Before declaring a verdict, list:
- which files you read + line ranges
- which acceptance bar items you confirmed evidence for
- which R1 findings you verified are closed in v2

## Anti-nits (do NOT flag)
- Prose grammar / formatting / docstring style
- R1 findings already addressed
- Speculative concerns about code that does not exist

## Verdict format
```
## Files scanned
- path:line-range
- ...

## R1 findings closure verification
- R1 P0 #1 [stale-tree gate]: <closed/regressed/incomplete>
- R1 P0 #2 [M-INT-0b]: <closed/regressed/incomplete>
- R1 P0 #3 [M-INT-6]: <closed/regressed/incomplete>
- R1 P1 #1 [12 vs 13]: <closed/regressed/incomplete>
- R1 P1 #2 [200/201]: <closed/regressed/incomplete>

## Acceptance bar verification (v2)
- Criterion 1 [sweep clean]: <evidence or NONE>
- Criterion 2 [13 substrates fire]: <evidence per substrate>
- Criterion 3 [smoke_manifest]: <evidence or NONE>

## Findings (NEW — exclude R1 already addressed)

### P0 (blocking)
- [file:line] description

### P1 (blocking)
- [file:line] description

### deferred_polish (P2/P3, non-blocking)
- [file:line] description

## Verdict
APPROVE | REQUEST_CHANGES

Convergence: APPROVE iff zero P0 + zero P1 (excluding R1
already-closed).
```

## Round metadata
This is round 2. Round 1 was the comprehensive pass. v2+
findings must be either (a) regressions in the v2 patch or
(b) P0/P1 missed in R1.

Hard iter cap: 5 rounds. Currently at 2 of 5.
