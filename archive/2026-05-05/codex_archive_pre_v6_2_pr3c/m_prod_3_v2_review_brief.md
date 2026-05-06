# Codex round 2 — M-PROD-3 v2 (R1 P1 closed)

## Pre-flight
- Branch: `polaris`
- Commit: `9ee32a4`
- Brief format: lean autoloop V3

## R1 closure
**R1 P1 [percentile off-by-one]:**
- v1: `idx = int(q * len(s))` selected next-higher element
- v2: `idx = ceil(q * n) - 1` (nearest-rank, 1-indexed →
  0-indexed)

All 8 verification cases (Codex's 3 + 5 edge cases) now
correct:

| Input | q | Expected | Actual |
|---|---|---|---|
| [10, 20] | 0.50 | 10 | 10 ✓ |
| 1..100 | 0.95 | 95 | 95 ✓ |
| 1..100 | 0.99 | 99 | 99 ✓ |
| 1..10 | 0.50 | 5 | 5 ✓ |
| 1..10 | 1.00 | 10 | 10 ✓ |
| 1..10 | 0.0 | 1 | 1 ✓ |
| [42] | 0.50 | 42 | 42 ✓ |
| [] | 0.50 | 0 | 0 ✓ |

## Acceptance bar (unchanged)
1. Endpoint exists (verified R1)
2. Counters thread-safe (verified R1)
3. Percentile correct (now correct in v2)
4. Rollback flag (verified R1)
5. Auth required (verified R1)
6. Public instrumentation API (verified R1)

## Severity rubric
- **P0** — production-breaker
- **P1** — phase-rework
- **P2** — governance precision (non-blocking)
- **P3** — polish (non-blocking)

**APPROVE iff zero P0 + zero P1.**

## Reviewer instructions
- Find ALL P0/P1 defects. If zero, write "no P0/P1 found"
  explicitly.
- Do NOT re-raise R1 finding.
- Verify the v2 percentile formula against Codex's 3 R1 cases.

## Skepticism gate
List which files you read + line ranges + whether you actually
ran the percentile against the R1 cases.

## Anti-nits (do NOT flag)
- Prose grammar / docstring style
- R1 finding already addressed
- Test coverage (deferred per R1 P3 polish)

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
