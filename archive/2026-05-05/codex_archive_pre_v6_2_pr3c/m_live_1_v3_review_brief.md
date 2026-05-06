# Codex round 3 — M-LIVE-1 v3 (2 R2 P0 findings closed)

## Pre-flight
- Branch: `polaris`
- Commit: `52485fd` (pushed to origin/polaris)
- Brief format: `.codex/REVIEW_BRIEF_FORMAT_v2.md` (autoloop V3)
- Smoke output: `outputs/m_live_1_smoke/run_<latest>/smoke_manifest.json`

## Round-by-round closure

**R1 findings (5 total — all closed in v2):**
- R1 P0 #1 [stale-tree gate]: closed in v2 (`52485fd^`)
- R1 P0 #2 [M-INT-0b]: closed in v2
- R1 P0 #3 [M-INT-6]: closed in v2
- R1 P1 #1 [12 vs 13]: closed in v2
- R1 P1 #2 [200/201]: marked incomplete in R2 (M-INT-8 missed in v2);
  closed in v3

**R2 findings (2 total — both closed in v3):**
- R2 P0 #1 [M-INT-8 accepts 404]: v3 requires status_code == 200
  strictly; 404 fallback removed
- R2 P0 #2 [M-INT-8 doesn't verify fresh run]: documented as
  architectural decoupling. The slide-deck endpoint reads from
  `find_run_by_slug()` allowlist, NOT from fresh smoke out_root.
  Substrate verification is endpoint+auth+flag wiring against
  the canonical demo run; fresh-run coupling would require
  registry-bypass plumbing outside M-LIVE-1 scope. v3 adds a
  body-content sanity check confirming the response actually
  references `CANONICAL_DEMO_SLUG` (rules out stale
  boilerplate).

## Acceptance bar (v3 — unchanged from v2)
1. **Sweep runs cleanly.** `rc=0`, manifest.json valid JSON.
2. **All 13 Phase E substrates fire** with verifiable sink:
   - M-INT-0a: `decision_rows_after > decision_rows_before` after
     `POST /api/inspector/templates/route` returns 200
   - M-INT-0b: `model_pin.json` present + `sweep_rc == 0`
   - M-INT-1: manifest.json `parallel_fetch_success_count` present
   - M-INT-2/3/7: stdout markers present
   - M-INT-4/5/6: run_log.txt markers present
   - M-INT-8: GET `/api/inspector/runs/{slug}/slide-deck`
     returns 200 AND body references CANONICAL_DEMO_SLUG
   - M-INT-9/10/11: POST returns 201
3. **smoke_manifest.json**: `all_phase_e_fired=true`,
   `fired_count=13`, `sweep_rc=0`.

## Tool hints
- `python scripts/run_m_live_1_smoke.py` → fresh v3 run
- Read in full:
  - `scripts/run_m_live_1_smoke.py:339-396` (M-INT-8 v3 fix)
  - `outputs/m_live_1_smoke/run_<latest>/smoke_manifest.json`
- Do NOT re-litigate R1/R2 findings already addressed

## Severity rubric
- **P0** — production-breaker
- **P1** — phase-rework
- **P2** — governance precision (non-blocking)
- **P3** — polish (non-blocking)

**APPROVE iff zero P0 + zero P1.**

## Reviewer instructions
- Find ALL P0/P1 defects. If zero, write **"no P0/P1 found"**
  explicitly — do not manufacture findings.
- Do NOT re-raise R1/R2 findings already closed.
- In-scope: regressions in v3 patch + P0/P1 missed in R1/R2.

## Skepticism gate
Before declaring a verdict, list:
- which files you read + line ranges
- which acceptance bar items you confirmed evidence for
- which R1/R2 closures you verified

## Anti-nits (do NOT flag)
- Prose grammar / formatting / docstring style
- R1/R2 findings already addressed
- Architectural decisions explicitly documented as out-of-scope
  (e.g., M-INT-8 fresh-run coupling deferred to a future milestone)

## Verdict format
```
## Files scanned
## R1+R2 findings closure verification
## Acceptance bar verification (v3)
## Findings (NEW only — exclude R1/R2 already addressed)
### P0 (blocking)
### P1 (blocking)
### deferred_polish (P2/P3, non-blocking)
## Verdict
APPROVE | REQUEST_CHANGES
```

## Round metadata
This is round 3 of 5 (hard cap). v3 patch only touches M-INT-8
endpoint smoke logic. R1+R2 findings should not be re-raised.
