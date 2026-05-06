# Codex round 1 — M-LIVE-4 v1 (M-D9 regression-lab CI gate)

## Pre-flight
- Branch: `polaris`
- Commit: `f9ee291`
- Brief format: `.codex/REVIEW_BRIEF_FORMAT_v2.md` (autoloop V3)

## Scope
Phase F final milestone per FINAL_PLAN. M-D9 phase 1
diff_regression() runs as CI gate on every release/PR;
verdict RED blocks merge, GREEN/YELLOW pass.

## Tool hints
- Read: `scripts/run_m_live_4_regression_gate.py` (full file,
  ~210 lines)
- Read: `src/polaris_graph/audit_ir/regression_lab.py:668-720`
  (diff_regression + report_to_exit_code)
- Run: `python scripts/run_m_live_4_regression_gate.py`
  → expect verdict=GREEN, exit_code=0
- Run: `python scripts/run_m_live_4_regression_gate.py
  --current outputs/m_live_1_smoke/run_<older_ts>` → also
  expect GREEN (functionally equivalent runs)
- Note: GitHub Actions workflow YAML is at
  `.github/workflows/m_live_4_regression_gate.yml.pending_workflow_scope`
  (renamed pending OAuth token with `workflow` scope; not yet
  pushed). Out of scope for code review.

## Acceptance bar
1. **CI gate exits correctly.**
   - GREEN/YELLOW verdict → exit 0 (merge OK)
   - RED verdict → exit 1 (block merge)
   - Per `report_to_exit_code(report)` semantics.
2. **Baseline + current dirs load cleanly.** Each must contain
   manifest.json + model_pin.json (M-LIVE-1 layout).
3. **Bootstrap path.** When baseline doesn't exist, gate
   passes through (rc=0) with a warning, not a hard failure.
4. **Default lookups.** When --current omitted, finds the
   latest `run_*` subdir under `outputs/m_live_1_smoke/`.
5. **Canonical fixture.** `tests/fixtures/m_live_4_baseline/`
   is committed as the baseline reference (per LAW VI:
   fixtures live in `tests/fixtures/`).
6. **Self-test passes.** Running the gate baseline-vs-baseline
   produces verdict=GREEN, exit_code=0.

## Severity rubric
- **P0** — production-breaker: gate falsely passes RED;
  exit_code wrong; baseline/current loaded incorrectly
- **P1** — phase-rework: acceptance criterion not met
- **P2** — governance precision (non-blocking)
- **P3** — polish (non-blocking)

**APPROVE iff zero P0 + zero P1.**

## Reviewer instructions
- Find ALL P0/P1 defects. If zero, write "no P0/P1 found"
  explicitly — do not manufacture findings.
- Run the gate yourself against the committed fixture and
  verify verdict + exit_code match expected.
- Check that a real RED verdict (synthetic regression in a
  scratch dir) actually returns exit 1 — verify the gate
  isn't always-pass.

## Skepticism gate
Before declaring a verdict, list:
- which files you read + line ranges
- which acceptance criteria you confirmed evidence for
- whether you ran the gate (and verified its output)

## Anti-nits (do NOT flag)
- Prose grammar / formatting / docstring style
- Speculative concerns about code that does not exist
- GitHub Actions workflow YAML (out of scope; deferred to
  workflow-scoped push)
- Hard-coded `_DEFAULT_BASELINE_METRICS` (documented as v1
  limitation; v2 will load YAML)

## Verdict format
```
## Files scanned
## Acceptance bar verification
## Findings
### P0 (blocking)
### P1 (blocking)
### deferred_polish (P2/P3, non-blocking)
## Verdict
APPROVE | REQUEST_CHANGES
```

## Round metadata
This is round 1 — comprehensive pass. Hard iter cap: 5.
