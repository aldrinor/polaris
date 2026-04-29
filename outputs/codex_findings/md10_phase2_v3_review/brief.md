# Codex round 3 — M-D10 phase 2 v3

## Tool hints
- `python -m pytest -q tests\polaris_graph\test_md10_phase2_freshness_aggregates.py`
- DO NOT run rg/find — read these files directly:
  - `src/polaris_graph/audit_ir/freshness_aggregates.py`
  - `tests/polaris_graph/test_md10_phase2_freshness_aggregates.py`
  - `docs/md10_phase2_threat_model.md`
- DO NOT run Python verification scripts that print Unicode

## Round-2 finding to verify closed

You returned PARTIAL on v2 with:
**[MEDIUM]** over-cap gate ignores since/until — narrow recent
windows that would be safe in isolation also raise.
**[LOW]** no test for over-cap + narrow window.

Your final word: "PARTIAL until the over-cap gate is made
window-aware OR the contract/docs are tightened to explicitly
reject all queries once workspace cardinality exceeds
_MAX_LIMIT."

v3 chose option B (contract clarification). Rationale: option
A requires phase 1 store API expansion (SQL-side windowed
COUNT or WHERE-on-checked_at, neither exists). Per LAW II,
silent miscounting on narrow OLD windows is the unacceptable
failure mode — substrate raises uniformly across since/until.

## What v3 changed

**Code (`freshness_aggregates.py:127-179`)**: docstring
expanded to document that the gate is workspace-wide, NOT
window-aware, and explains the operator paths once a
workspace exceeds the cap. The error message now explicitly
notes "this raise is uniform across since/until — narrow
recent windows that would be safe in isolation also raise,
by design".

**Test (`test_md10_phase2_freshness_aggregates.py`)**: added
`test_over_cap_raises_even_for_narrow_window` with 3
sub-cases that exactly mirror Codex round-2 LOW gap:
1. Narrow RECENT window (since=2500, until=3500) — raises
2. Narrow OLD window (since=500, until=1500) — raises
3. only_latest_per_source mode — raises

**Threat model**: bumped v2→v3 with explicit contract
clarification under boundary 1.

## Verdict checklist

- [Y/N] v3 contract clarification + uniform raise closes
  Codex round-2 MEDIUM (or does the substrate need window-
  aware gate)?
- [Y/N] test_over_cap_raises_even_for_narrow_window covers
  the gap from round-2 LOW?
- [Y/N] Any other findings on the same predicate?
- [Y/N] Any findings on a different probe surface?

## Verdict format

```
## Verdict
GREEN | PARTIAL | BLOCKED

## Round-2 fix integration
- [x/ ] MEDIUM contract clarified, uniform raise documented
- [x/ ] LOW over-cap + narrow-window test added

## New findings (if any)
[SEVERITY] file:line — description

## Final word
GREEN | PARTIAL until X
```
