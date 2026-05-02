M-D9 phase 1 v3 review (commit 8abf160).

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Round count: R1=2 → R2=1 (converging).

Round 2 (commit 44c8f7b) PARTIAL with 1 HIGH finding: status
validation used prefix-match, leaking typos/future taxonomy
values into within-tier YELLOW.

This v3 commit closes that.

## What changed in v3

`src/polaris_graph/audit_ir/regression_lab.py`:
  - Replaced prefix-match with `_STATUS_TIERS` dict mirroring
    exactly the 13 unified status values from
    `scripts/run_honest_sweep_r3.py:95-113`
    (UNIFIED_STATUS_VALUES).
  - Public `KNOWN_STATUS_VALUES = frozenset(_STATUS_TIERS)`.
  - `_status_tier()` returns -1 for unknown — fails closed in
    `_status_is_regression`.

`tests/polaris_graph/test_md9_regression_lab.py`:
  - 35 tests (was 32). New:
    * test_manifest_unknown_partial_typo_fails_closed
    * test_manifest_unknown_abort_typo_fails_closed
    * test_known_status_values_match_live_runner — taxonomy-
      drift guard that imports
      `scripts.run_honest_sweep_r3.UNIFIED_STATUS_VALUES` at
      test time and asserts equality

## Your job

GREEN-LOCK or PARTIAL.

1. **Round 2 fix integration**:
   - [ ] status now uses exact-match (no prefix bucketing)
   - [ ] unknown values fail closed
   - [ ] taxonomy-drift guard catches future divergence

2. **Stop criterion this round**: GREEN-lock if remaining
   findings are minor (doc accuracy, additional manifest
   field hints, env enumeration). PARTIAL only if you find:
     (a) Foundational logic gap in the verdict pipeline
     (b) A new categorical class of drift not covered by
         pin/induction/manifest
     (c) The taxonomy-drift guard test is broken or wrong
     (d) A regression introduced by v3

3. **Phase 2 readiness**: with v3 schema-aligned + taxonomy-
   safe, can BEAT-BOTH dimension scoring layer cleanly?

## Output

`outputs/codex_findings/md9_phase1_v3_review/findings.md`:

```markdown
# Codex round 3 — M-D9 phase 1 v3 (commit 8abf160)

## Verdict
GREEN / PARTIAL / DISAGREE

## Round 2 fix integration
- [x/no] exact-match status taxonomy
- [x/no] unknown values fail closed
- [x/no] taxonomy-drift guard works

## New findings (if any)
- [...]

## Final word
GREEN to lock M-D9 phase 1 / PARTIAL with edits.
```

Be terse. Under 50 lines.
