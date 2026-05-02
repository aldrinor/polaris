# Codex round 5 — M-D10 phase 2 v5

## Tool hints
- DO NOT run rg/find — read these files directly:
  - `src/polaris_graph/audit_ir/freshness_aggregates.py`
  - `docs/md10_phase2_threat_model.md`
- DO NOT run Python verification scripts that print Unicode

## Round-4 finding to verify closed

You returned PARTIAL on v4 with one LOW: the `_list_window`
docstring's operator-path bullets blended path 1 (phase-1
store API) with path 3 (wait for v2 SQL-side aggregation),
making the wording inconsistent with the `_MAX_LIMIT` comment
+ threat model.

## What v5 changed

`freshness_aggregates.py:159-167` (within `_list_window`
docstring) — rewrote the operator-paths bullets to match the
canonical 3-path wording verbatim:

```
Operator paths once a workspace exceeds the cap (same
three paths documented in the `_MAX_LIMIT` block and
`docs/md10_phase2_threat_model.md`):
  1. Shard the workspace.
  2. Use the phase 1 store query API directly
     (`store.list_alerts`, `store.count`,
     `store.latest_for_url`) with caller-side aggregation.
  3. Wait for phase 2 v2 SQL-side aggregation.
```

This now matches `_MAX_LIMIT` comment AND threat model
section under boundary 1.

## Convergence note

Rounds 3 and 4 both surfaced contract-text consistency
findings (no behavior issues). v5 closes the round-4
finding. If round 5 finds another wording inconsistency,
that's the asymptote signal — substrate behavior is correct,
all three places (comment, docstring, threat model) say the
same thing. Further rounds on doc-text polish would be
spinning.

## Verdict checklist

- [Y/N] Operator-paths wording in `_list_window` docstring
  now matches the canonical 3-path wording in
  `_MAX_LIMIT` comment + threat model?
- [Y/N] Any other contract-text inconsistencies?

## Verdict format

```
## Verdict
GREEN | PARTIAL | BLOCKED

## Round-4 fix integration
- [x/ ] LOW operator-paths wording aligned

## New findings (if any)
[SEVERITY] file:line — description

## Final word
GREEN | PARTIAL until X
```
