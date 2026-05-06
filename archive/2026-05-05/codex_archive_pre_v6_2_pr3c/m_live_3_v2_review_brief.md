# Codex round 2 — M-LIVE-3 v2 (1 R1 P0 closed)

## Pre-flight
- Branch: `polaris`
- Commit: `e4ff4c6`
- Brief format: lean autoloop V3

## R1 closure
- **R1 P0 [PinDriftEvent attribute mismatch]**: closed.
  v2 uses `e.before` / `e.after` (correct attributes) instead
  of `e.from_value` / `e.to_value` (which don't exist).
  Endpoint returns 200 with valid drift_events list; previously
  500'd on any drift.

## Acceptance bar (unchanged from R1)
1. 3 endpoints exist
2. Substrate wiring correct
3. Org-scoped via caller.org_id
4. Time-windowed
5. Rollback flag works
6. Auth required
7. Path traversal guard

R1 confirmed all 7 criteria. Round 2 verifies the P0 closure and
flags any v2 regressions.

## Severity rubric
- **P0** — production-breaker
- **P1** — phase-rework
- **P2** — governance precision (non-blocking)
- **P3** — polish (non-blocking)

**APPROVE iff zero P0 + zero P1.**

## Reviewer instructions
- Find ALL P0/P1 defects. If zero, write "no P0/P1 found"
  explicitly.
- Do NOT re-raise R1 finding (already closed).
- Verify v2 patch by invoking pin-trends endpoint with a
  drifting pin pair — it should return 200 with drift_events
  containing valid `before` / `after` fields (not 500
  AttributeError).

## Skepticism gate
List which files you read + line ranges + whether you actually
invoked the endpoint with a multi-pin drift case.

## Anti-nits (do NOT flag)
- Prose grammar / docstring style
- R1 finding already addressed
- Pin trends org-scoping (deferred to M-INT-0b v2 per brief)

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
