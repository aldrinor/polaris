# Codex round 2 — M-D11 phase 2 v2 v2 (commit 460234a)

## Tool hints
- `python -m pytest -q tests\polaris_graph\test_md11_phase2_v2_pin_trends.py`
- DO NOT run rg/find — read directly:
  - `src/polaris_graph/audit_ir/pin_trends.py`
  - `tests/polaris_graph/test_md11_phase2_v2_pin_trends.py`

## Round-1 findings to verify closed

You returned PARTIAL on v1 with 2 MEDs:

[MEDIUM] drift_events emitted by iterating `seen_dims` (a
set) — non-deterministic order across processes, violating
pure-derivation contract.

v2 fix: iterate `sorted(seen_dims)` so events within each
transition are dimension-name-lexicographic. Pin order
preserved by pin_index across transitions.

[MEDIUM] Explicit threshold kwargs (`stable_threshold`,
`unstable_threshold`) not clamped to [0.0, 1.0] — raised on
out-of-range, contradicting docstring contract that says
clamped.

v2 fix: clamp explicit kwargs the same way env overrides
are. Validation now: `if not (unstable_t <= stable_t)`
(equality on stable_t==1.0 / unstable_t==0.0 after clamp).

## What v2 changed

`pin_trends.py` lines ~297-313 (threshold logic) +
lines ~329-360 (drift event collection now uses
`sorted(seen_dims)`).

New tests:
- `test_explicit_threshold_kwargs_clamped_to_unit_interval`
- `test_drift_events_ordering_deterministic`

36/36 passing locally.

## Verdict format

```
## Verdict
GREEN | PARTIAL | BLOCKED

## Round-1 fix integration
- [x/ ] MEDIUM sorted-iteration deterministic order
- [x/ ] MEDIUM explicit-kwarg clamping

## New findings (if any)
[SEVERITY] file:line — description

## Final word
GREEN | PARTIAL until X
```
