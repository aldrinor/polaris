# Codex round 2 — M-LIVE-4 v2 (2 R1 P0 closed)

## Pre-flight
- Branch: `polaris`
- Commit: `e4ff4c6`
- Brief format: lean autoloop V3

## R1 closures (both verified manually)

**R1 P0 #1 [PinDriftField.dimension wrong]:**
- v1 used `pd.dimension`, but PinDriftField defines `field_name`
- v2: `pd.field_name`. Synthetic pin drift now prints correctly.

**R1 P0 #2 [ManifestDriftField.field_path wrong]:**
- v1 used `md.field_path`, but ManifestDriftField defines `field`
  (ManifestDrift enum)
- v2: `md.field` + `.value` extraction for enum. Synthetic
  manifest drift now prints + writes summary correctly.

## Empirical verification

Synthetic RED drift on `status: partial_qwen_advisory →
abort_no_verified_sections`:
  verdict: RED
  manifest_drift fields: 1
  manifest drift detail printed correctly
  summary written
  exit_code: 1 (correctly blocks merge)

## Acceptance bar (unchanged)
1. CI gate exits correctly per `report_to_exit_code(report)`
2. Baseline + current dirs load cleanly
3. Bootstrap path (missing baseline → rc=0)
4. Default lookups (latest run_*)
5. Canonical fixture at tests/fixtures/m_live_4_baseline/
6. Self-test passes (baseline-vs-baseline → GREEN/0)

## Severity rubric
- **P0** — production-breaker
- **P1** — phase-rework
- **P2** — governance precision (non-blocking)
- **P3** — polish (non-blocking)

**APPROVE iff zero P0 + zero P1.**

## Reviewer instructions
- Find ALL P0/P1 defects. If zero, write "no P0/P1 found"
  explicitly.
- Do NOT re-raise R1 findings already addressed.
- Verify both fixes by invoking the gate with synthetic pin
  drift AND synthetic manifest drift — both should print drift
  detail without AttributeError and exit per the proper verdict
  path (RED→1, GREEN/YELLOW→0).

## Skepticism gate
List which files you read + line ranges + whether you actually
invoked the gate against synthetic regressions.

## Anti-nits (do NOT flag)
- Prose grammar / docstring style
- R1 findings already addressed
- Hard-coded `_DEFAULT_BASELINE_METRICS` (deferred to v2 with
  YAML loading; called out in v1 brief as known limitation)

## Verdict format
```
## Files scanned
## R1 closure verification
## Acceptance bar verification
## Findings (NEW only)
## Verdict APPROVE | REQUEST_CHANGES
```

## Round metadata
Round 2 of 5 hard cap.
