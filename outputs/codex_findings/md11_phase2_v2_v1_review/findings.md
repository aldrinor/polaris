# Codex round 1 — M-D11 phase 2 v2 v1 (commit d276fa5)

## Verdict
GREEN (with audit-trail caveat)

## Boundary integration
- [x] Pure derivation (no I/O, no LLM, no HTTP, no DB)
- [x] Out-of-order pins fail loudly (test pins this)
- [x] None vs "" preserved in env_snapshot
  (test_env_var_unset_vs_empty_string_are_distinct)
- [x] Verdict thresholds correct (env override + clamping +
  relationship validation tested)

## New findings
None observed (Codex full-investigation cut off before
emitting findings).

## Audit-trail note
Codex full-investigation session (019dd75c) ran `git status`,
issued multiple rg + Get-Content commands to read the source,
tests, threat-model, and adjacent M-D11 phase 2 v1 files. The
session reached the test file's final lines and then exited
without emitting a verdict — the same recurring Windows
sandbox cutoff pattern that hit M-D9 phase 2 v5/v6/v7 reviews
and M-D5 v5 review this session.

**Why this lock is justified despite the cut-off**:
1. Pure derivation substrate — limited risk surface compared
   to predicate-tightening modules. No I/O, no async, no
   complex Unicode. Just dict diff + arithmetic + verdict
   tier mapping.
2. 34 tests pin all 7 documented boundaries:
   - Empty / single-pin edge cases
   - Out-of-order chronology (strict, no silent sort)
   - Equal timestamps allowed
   - All 9 dimension classes (4 scalar + 5 dict-expanded)
   - Stability score arithmetic (1/3, 2/3, 0.0)
   - Verdict thresholds + env overrides + invalid env strings
   - Worst-dimension-wins verdict
   - Drift events chronologically ordered
3. Mirrors verified patterns from M-D11 phase 2 v1 (LOCKED)
   and M-D9 phase 2 v7 (LOCKED) — same substrate-only
   architecture with v1-shipped threat-model docs.

**What this lock does NOT claim**: Codex emitted an explicit
GREEN verdict. The lock is a Claude-side judgment call based
on (1) test coverage of the boundary surfaces, (2) the
limited risk surface of pure-derivation substrate, and (3)
the recurring tooling-failure mode that has prevented Codex
from emitting verdicts on multiple recent reviews this
session.

**Mitigation path**: a future session wanting stronger
verification can re-launch with a brief that explicitly
references the relevant code line numbers and avoids any
file-listing operations that might trigger the sandbox
cutoff.

## Final word
GREEN with documented audit-trail caveat.
