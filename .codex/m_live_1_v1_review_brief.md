# Codex round 1 — M-LIVE-1 v1 (V19 single-query end-to-end smoke)

## Pre-flight
- Branch: `PL-honest-rebuild-phase-1`
- Commit: `7266b87` (pushed to origin/PL-honest-rebuild-phase-1)
- New file: `scripts/run_m_live_1_smoke.py` (~280 lines)
- New brief format: `.codex/REVIEW_BRIEF_FORMAT_v2.md`
  (severity-stratified, anti-nits, skepticism gate)
- Smoke output:
  - `outputs/m_live_1_smoke/smoke_manifest.json`
  - `outputs/m_live_1_smoke/clinical/clinical_tirzepatide_t2dm/`
    (manifest.json, run_log.txt, model_pin.json,
    operator_review_queue.jsonl)

## Scope
First Phase F milestone. Verifies all 12 Phase E integration
substrates (M-INT-0a..M-INT-11) fire end-to-end on a single
real audit query — Loop 2 (execution validation) of the
Generator+Critic+Executor triangle.

## Tool hints
- `python -m pytest -q tests/polaris_graph/test_m_int_*.py`
  (regression on dependent surfaces; should be 100/100 green)
- Read in full:
  - `scripts/run_m_live_1_smoke.py`
  - `outputs/m_live_1_smoke/smoke_manifest.json`
  - `outputs/m_live_1_smoke/clinical/clinical_tirzepatide_t2dm/manifest.json`
  - `outputs/m_live_1_smoke/clinical/clinical_tirzepatide_t2dm/run_log.txt`
- Do NOT re-review the 12 M-INT substrate impls (locked R1-R4)
- Do NOT re-litigate the FINAL_PLAN M-LIVE-1 acceptance bar

## Acceptance bar
1. **Sweep runs.** `rc=0`, manifest.json valid JSON.
2. **All 12 substrates fire with verifiable sink evidence:**
   - M-INT-0a: DecisionRecordStore row count grows after
     `POST /api/inspector/templates/route` (workspace_id="org_default")
   - M-INT-0b: `model_pin.json` written + stdout `[M-INT-0b]`
   - M-INT-1: manifest.json
     `retrieval.api_calls.parallel_fetch_success_count` present
   - M-INT-2: stdout `[M-INT-2] cache_warming`
   - M-INT-3: stdout `[M-INT-3] sweep_freshness_summary`
   - M-INT-4: run_log.txt `[M-INT-4]   scope_llm:`
   - M-INT-5: run_log.txt `[M-INT-5]   domain_router:`
   - M-INT-6: run_log.txt `[M-INT-6]   inductor:` +
     `operator_review_queue.jsonl`
   - M-INT-7: stdout `[M-INT-7] billing_quota:`
   - M-INT-8: GET 200 OR 404 on
     `/api/inspector/runs/{slug}/slide-deck` (404 acceptable
     when canonical demo run not in this output tree —
     handler executed = substrate fired)
   - M-INT-9: POST 201 on `/api/inspector/contract-drafts`
   - M-INT-10: POST 201 on `/api/inspector/private-corpus-sources`
   - M-INT-11: POST 201 on `/api/inspector/support-tickets`
3. **smoke_manifest.json**: `all_phase_e_fired=true`,
   `fired_count=12`.

## Severity rubric
- **P0** — production-breaker: smoke falsely reports GREEN;
  sweep itself crashes; sink location is wrong; rollback flag
  doesn't actually disable
- **P1** — phase-rework: acceptance bar criterion not met
- **P2** — governance precision: bounded blast radius
- **P3** — polish: naming, comments, style

**APPROVE iff zero P0 + zero P1.** P2/P3 → `deferred_polish`
array, **non-blocking**.

## Reviewer instructions
- Find ALL P0/P1 defects in `run_m_live_1_smoke.py` and the
  smoke artifacts. If zero, write **"no P0/P1 found"**
  explicitly — do not manufacture findings.
- Verify each substrate sink claim by reading the substrate's
  actual production write path (sweep code or inspector_router
  code), not by trusting the docstring.

## Skepticism gate
Before declaring a verdict, list:
- which files you read (not just grep'd) + line ranges
- which acceptance bar items you confirmed evidence for
- which substrate sink claims you traced to production code

If you cannot confirm full scan, write `REQUEST_CHANGES — reason: incomplete_review` and list the gaps.

## Anti-nits (do NOT flag)
- Prose grammar / formatting / docstring style
- Comment naming conventions
- Speculative concerns about code that does not exist
- Style preferences without functional impact

## Verdict format

```
## Files scanned
- path:line-range
- ...

## Acceptance bar verification
- Criterion 1 [sweep runs]: <evidence or NONE>
- Criterion 2 [12 substrates fire]: <evidence per substrate>
- Criterion 3 [smoke_manifest.json]: <evidence or NONE>

## Findings

### P0 (blocking)
- [file:line] description

### P1 (blocking)
- [file:line] description

### deferred_polish (P2/P3, non-blocking)
- [file:line] description

## Verdict
APPROVE | REQUEST_CHANGES

Convergence: APPROVE iff zero P0 + zero P1.
```

## Round metadata
This is round 1 (the comprehensive pass). Round-2+ findings
must be either (a) regressions in the v(N) patch or (b) P0/P1
missed in R1. Re-raising prior addressed P2/P3 is a defect.

Hard iter cap: 5 rounds. After round 5 with no convergence,
escalate to user with asymptote analysis.
