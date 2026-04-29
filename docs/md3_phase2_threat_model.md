# M-D3 phase 2 v1 — decision telemetry aggregation boundary

**Status:** v1 / 2026-04-28
**Module:** `src/polaris_graph/audit_ir/decision_aggregates.py`
**Tests:** `tests/polaris_graph/test_md3_phase2_decision_aggregates.py` (21 passing)
**Pairs with:** M-D3 phase 1 (`decision_telemetry.py`, commit 212102d).
**Substrate:** stdlib + `decision_telemetry` only.

---

## Scope

M-D3 phase 1 ships per-workspace SQLite DecisionRecordStore
with record-level APIs (record_decision, update_curator_action,
get, list_for_workspace, count_for_workspace). Phase 2 v1
layers **aggregation queries** on top: per-workspace
acceptance/modification/override/rejection rates, optionally
filtered by DecisionKind and time-windowed.

Why this milestone matters: M-D4 (auto-trust gate) is
calendar-blocked on accumulating ≥6 months of telemetry. When
M-D4 ships, it will need aggregate metrics like "what fraction
of induction decisions in this workspace over the last 90 days
were accepted_as_proposed?" to decide whether the system is
trustworthy enough to bypass the operator-review queue.

Phase 2 v1 ships the substrate query API M-D4 will consume.

---

## v1 boundaries

### 1. Pure substrate — no I/O beyond M-D3 phase 1 store

`decision_aggregates.py` imports stdlib + `decision_telemetry`
only. No new SQL paths or schema changes. The aggregation is
computed in Python over the record list returned by
`store.list_for_workspace`.

This trades query efficiency for code simplicity at v1; v2
may add a SQL-side aggregation query if record counts grow
large enough that per-workspace list materialization becomes
a memory/latency concern. For the M-D4 ≥6-month calibration
window with realistic workspace volumes (single-digit
thousands of decisions), Python-side aggregation is fast.

### 2. Rates are None when total_terminal == 0

`acceptance_rate`, `modification_rate`, `override_rate`,
`rejection_rate` are each `count / total_terminal`. They
return None when total_terminal == 0 (no terminal records in
the window).

Surfacing 0.0 would be misleading: "0% accepted because we
haven't decided anything yet" (pending-only) is different
from "0% accepted because the curator rejected everything".
None forces callers (M-D4 calibration) to handle the
empty-window case explicitly rather than silently treating
"no data" as "0% acceptance".

**Mitigation**: `test_only_pending_yields_none_rates` and
`test_window_with_no_matches_yields_empty_aggregates` pin
this contract.

### 3. Time window inclusive on both bounds

`since` and `until` are UNIX epoch floats (matching
`DecisionRecord.created_at`). A record exactly at the
boundary is included. This matches the standard SQL
BETWEEN convention and lets callers query a single instant
via `since == until`.

`since == until` selects records captured exactly at that
instant — rare but valid (e.g. a batch import). Otherwise
`since > until` raises (incoherent window).

**Mitigation**: `test_window_inclusive_at_boundaries` +
`test_invalid_window_raises`.

### 4. DecisionKind filter is closed-taxonomy-aware

Filter accepts `DecisionKind.INDUCTION`, `DecisionKind.SCOPE_GATE`,
or None (aggregate across both). The aggregator passes
through to `store.list_for_workspace(decision_kind=...)` —
same enum used by M-D3 phase 1. If M-D3 phase 1 grows new
kinds (per the locked memory note about generic discriminator),
the aggregator picks them up automatically when
`decision_kind=None`.

**Mitigation**: `test_filter_by_induction_excludes_scope_gate`
+ `test_filter_by_scope_gate_excludes_induction` +
`test_no_kind_filter_aggregates_both` pin both modes.

### 5. Workspace isolation via M-D3 phase 1 store query

The aggregator calls `store.list_for_workspace(workspace_id, ...)`
which is workspace-scoped at the SQL level. Cross-workspace
aggregation is impossible by API. Workspace_id is stripped
before passing through (matches M-D3 phase 1 store behavior).

**Mitigation**: `test_workspace_isolation` + `test_workspace_id_stripped`.

### 6. total_decisions == pending_count + total_terminal (invariant)

The pending/terminal accounting holds at all times:
`agg.pending_count + agg.total_terminal == agg.total_decisions`.
This is enforced by `CuratorAction` having exactly 5 values
(PENDING + 4 terminal) and the aggregator counting each
record into exactly one bucket.

**Mitigation**: `test_pending_plus_terminal_equals_total`
pins this. Callers can rely on this invariant for sanity-
checking aggregator output.

### 7. Frozen dataclass — DecisionAggregates is immutable

`DecisionAggregates` is `@dataclass(frozen=True)`. Computed
aggregates are values, not state — immutability prevents
accidental mutation by callers (e.g. M-D4 calibration code
that wants to "merge" two aggregates would have to construct
a new dataclass rather than mutating in place).

---

## v1 NON-goals (defer to v2)

  - **No SQL-side aggregation**: substrate uses Python loop
    over `list_for_workspace`. v2 may add a SQL `GROUP BY
    curator_action` query if performance demands.
  - **No multi-workspace aggregation**: caller iterates
    workspaces themselves. The substrate is workspace-scoped.
  - **No rolling-window / time-bucketed aggregates**: only
    point-in-time `since/until` windows. v2 may add a
    bucketed variant for trending.
  - **No M-D4 calibration logic**: v1 ships the substrate
    primitive only. M-D4 is calendar-blocked separately.
  - **No alert / notification glue**: aggregates are
    returned as data; emitting alerts on rate thresholds is
    M-D4 territory.
  - **No confidence-stratified aggregates** (e.g. "rate
    among high-confidence proposals only"): caller filters
    the input list themselves if needed.

---

## Codex review trail

Round-1 brief incoming. Tool hints:
- Use `python -m pytest -q tests\polaris_graph\test_md3_phase2_decision_aggregates.py`
- Skip `outputs/codex_*` and `.codex_tmp/` in `rg`
- DO NOT run Python verification scripts that print Unicode —
  Windows sandbox uses cp1252 (this has caused 6+ Codex
  review cutoffs this session)
- 21 tests pin all 7 boundaries

Targeted at 1-2 round convergence per the M-D3 phase 1 / M-D7
phase 2 / M-D11 phase 2 v2 patterns (substrate work with
v1-shipped threat-model docs converges fast).

---

## Lock note

v1 GREEN-lock target after Codex round 1-2. v2 (SQL-side
aggregation, time-bucketed variants, multi-workspace) tracked
separately.
