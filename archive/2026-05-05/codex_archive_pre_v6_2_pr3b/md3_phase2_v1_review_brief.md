# Codex round 1 — M-D3 phase 2 v1

## Tool hints
- `python -m pytest -q tests\polaris_graph\test_md3_phase2_decision_aggregates.py`
- DO NOT run rg/find — read these files directly:
  - `src/polaris_graph/audit_ir/decision_aggregates.py` (~210 lines)
  - `tests/polaris_graph/test_md3_phase2_decision_aggregates.py` (~360 lines)
  - `docs/md3_phase2_threat_model.md` (~160 lines)
- DO NOT run Python verification scripts that print Unicode

## Scope
M-D3 phase 1 (commit 212102d, LOCKED) shipped per-workspace
SQLite DecisionRecordStore + record-level APIs.

This v2 layers aggregation queries: per-workspace
acceptance/modification/override/rejection rates by
DecisionKind, time-windowed.

## Public API

```python
@dataclass(frozen=True)
class DecisionAggregates:
    workspace_id: str
    decision_kind: DecisionKind | None
    window_start: float | None
    window_end: float | None
    total_decisions: int
    total_terminal: int
    pending_count: int
    accepted_count: int
    modified_count: int
    overridden_count: int
    rejected_count: int
    acceptance_rate: float | None  # None when total_terminal == 0
    modification_rate: float | None
    override_rate: float | None
    rejection_rate: float | None

def compute_aggregates(
    store: DecisionRecordStore,
    workspace_id: str,
    *,
    decision_kind: DecisionKind | None = None,
    since: float | None = None,
    until: float | None = None,
) -> DecisionAggregates: ...
```

## Boundaries (7 documented)

1. Pure substrate — stdlib + decision_telemetry only
2. Rates None when total_terminal == 0
3. Time window inclusive on both bounds
4. DecisionKind filter (closed taxonomy)
5. Workspace isolation via M-D3 phase 1 store
6. Invariant: pending + terminal == total_decisions
7. Frozen dataclass (immutable values)

## Tests (21/21 passing locally)

- Empty store → zero counts + None rates
- Pending-only window → rates None
- All-accepted / all-rejected single-action windows
- Mixed terminal arithmetic (rates sum to 1.0)
- DecisionKind filter (induction / scope_gate / both)
- Time window (since/until inclusive boundaries)
- Combined kind+window filter
- Workspace isolation
- pending + terminal == total invariant
- Contract validation (empty workspace_id, non-store, invalid window)

## What might Codex probe

- Does compute_aggregates handle a record where the curator
  transitioned to terminal AFTER `until`? The aggregator filters
  on `created_at`, NOT `decided_at`. If a record was created at
  T1 and decided at T2 > until, it IS counted as terminal.
  Whether this is correct depends on M-D4's intended semantics.
  Tests pin the current behavior (filter on created_at only).
- SQL injection / parameterized query safety on workspace_id
  (per-call connection, parameterized queries used by phase 1
  store)
- Float precision on rates (4 rates summing to exactly 1.0)
- Performance: list_for_workspace() materializes all matching
  records into Python — for large workspaces this could be
  memory-heavy. v1 boundary 1 explicitly defers SQL-side
  aggregation to v2.
- decision_kind filter passing through correctly

## Verdict format

```
## Verdict
GREEN | PARTIAL | BLOCKED

## Boundary integration
- [x/ ] Pure substrate
- [x/ ] Rate semantics correct (None vs 0.0)
- [x/ ] Window inclusivity correct
- [x/ ] Workspace isolation preserved

## New findings (if any)
[SEVERITY] file:line — description

## Final word
GREEN | PARTIAL until X
```
