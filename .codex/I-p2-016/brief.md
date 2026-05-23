# Codex DESIGN+DIFF review — I-p2-016 (#755): run-progress page (depth visible)

HARD ITERATION CAP: 5. iter 1. Canonical-diff-sha256 `e31490021d7745a82569779ce5842acefcc881e5c8cfe0bb0df47969db265bfe`. web/ only. MERGE AUTHORIZED if mergeable. APPROVE iff zero P0/P1.

## Context
#755 = "Run progress: depth visible." The /runs/[runId] page ALREADY shows depth via the #747 RunProgress component (staged checklist Scope→Retrieval→Generation→Verification + ELAPSED/SOURCES-READ/SENTENCES-VERIFIED metrics + a Hide-details Thinking-Toggle) — verified by screenshot. So the depth requirement is met; this PR is a small honesty/consistency polish on the page shell.

## Diff (web/app/runs/[runId]/page.tsx)
- Error: replaced the hand-rolled banner (border-destructive/60 ...) with the #750 ErrorState (design tokens + role=alert + specific message) — consistent with every other page.
- Title: `{status?.question ?? "Loading…"}` → when an error has fired, show "Couldn't load this run" instead of "Loading…" (no more Loading+error shown together).

## Claude visual audit (standalone @1366, sent to operator earlier): full depth — staged pipeline checklist + metrics + thinking toggle + affordances (Open Inspector / Export / Cancel / Pin) + FollowupPanel (completed). "Canadian-hosted" mark (post #762).

## Review focus
1. ErrorState swap correct (no unused imports; role=alert)? Title no longer shows "Loading…" alongside an error?
2. Depth genuinely visible (the #747 staged checklist + metrics)? Any honesty issue (status shown raw is the lifecycle status — acceptable on the progress page)? Any P0/P1.

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
merge_decision: MERGE AUTHORIZED | DO NOT MERGE
```
