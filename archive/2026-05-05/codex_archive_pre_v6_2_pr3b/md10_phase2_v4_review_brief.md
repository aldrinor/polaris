# Codex round 4 — M-D10 phase 2 v4

## Tool hints
- DO NOT run rg/find — read these files directly:
  - `src/polaris_graph/audit_ir/freshness_aggregates.py`
- DO NOT run Python verification scripts that print Unicode

## Round-3 finding to verify closed

You returned PARTIAL on v3 with one LOW:
the `_MAX_LIMIT` comment at line 124 still mentioned "split
into narrower windows" as an operator path — contradicting the
v3 uniform-raise contract.

Your final word: "PARTIAL until the stale `_MAX_LIMIT` comment
is aligned with the uniform-raise contract. The substrate does
not need a window-aware gate for v3; the remaining issue is
contract consistency, not behavior."

## What v4 changed

`freshness_aggregates.py:124-134` — rewrote the `_MAX_LIMIT`
comment block:
  - removed "split into narrower windows"
  - added explicit note: "narrowing the since/until window
    does NOT bypass the cap — the gate is workspace-wide
    because phase 1 store API has no SQL-side windowed COUNT"
  - kept the 3 valid operator paths (shard, use phase 1 store
    API directly, wait for v2)

No code/test changes — this is a pure comment-contract
alignment.

## Verdict checklist

- [Y/N] v4 comment now consistent with the uniform-raise
  contract documented in the docstring + threat model?
- [Y/N] Any other round-3-style contract-consistency issues?

## Verdict format

```
## Verdict
GREEN | PARTIAL | BLOCKED

## Round-3 fix integration
- [x/ ] LOW _MAX_LIMIT comment aligned with uniform-raise contract

## New findings (if any)
[SEVERITY] file:line — description

## Final word
GREEN | PARTIAL until X
```
