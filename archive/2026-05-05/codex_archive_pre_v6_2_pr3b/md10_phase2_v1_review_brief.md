# Codex round 1 — M-D10 phase 2 v1 (commit dbe24ea)

## Tool hints
- `python -m pytest -q tests\polaris_graph\test_md10_phase2_freshness_aggregates.py`
- DO NOT run rg/find — read these files directly:
  - `src/polaris_graph/audit_ir/freshness_aggregates.py` (~250 lines)
  - `tests/polaris_graph/test_md10_phase2_freshness_aggregates.py` (~340 lines)
  - `docs/md10_phase2_threat_model.md` (~210 lines)
- DO NOT run Python verification scripts that print Unicode

## Scope
M-D10 phase 1 (commit a85812f, LOCKED) shipped per-workspace
SQLite FreshnessAlertStore + 5-status taxonomy + M-D7 cache
eviction integration + 3 record-level query APIs.

This v2 layers aggregation queries: per-workspace counts by
FreshnessStatus over time window + latest-status-per-source
rollup for V19+ live audit "report freshness" signal.

## Public API

```python
@dataclass(frozen=True)
class FreshnessAggregates:
    workspace_id: str
    window_start: float | None
    window_end: float | None
    only_latest_per_source: bool
    total_alerts: int
    unchanged_count: int
    superseded_count: int
    retracted_count: int
    expression_of_concern_count: int
    unreachable_count: int
    evicting_count: int  # superseded + retracted + EoC
    unique_source_count: int

def compute_freshness_aggregates(
    store: FreshnessAlertStore,
    workspace_id: str,
    *,
    since: float | None = None,
    until: float | None = None,
    only_latest_per_source: bool = False,
) -> FreshnessAggregates: ...
```

## Boundaries (7 documented)

1. Pure substrate — stdlib + freshness_monitor only
2. only_latest_per_source is mode, not default
3. Latest-mode rollup AFTER window filter
4. Time window inclusive on both bounds
5. evicting_count = SUPERSEDED + RETRACTED + EoC
6. unique_source_count over windowed set
7. Schema-drift defense (unknown status raises)

## Tests (22/22 passing)

- Empty store + contract validation
- 5-status taxonomy counted exactly
- evicting_count arithmetic
- only_latest_per_source dedup (same URL, canonical
  collision, distinct sources)
- Window inclusivity + latest-after-window interaction
- Workspace isolation
- unique_source_count over windowed set + with repeats
- Status counts sum to total invariant

## What might Codex probe

- Latest-per-source ordering correctness (relies on phase 1
  store returning DESC by checked_at — pinned by phase 1 tests)
- The 1M alert hard cap behavior at boundary
- FreshnessStatus.value vs FreshnessStatus enum confusion
  (alert.status is the .value string per phase 1 schema)
- since=None && until=None short-circuit (skips filter loop)
- Empty windowed list → all counts 0 (no division/None handling
  needed since freshness aggregates use raw counts, not rates)

## Verdict format

```
## Verdict
GREEN | PARTIAL | BLOCKED

## Boundary integration
- [x/ ] Pure substrate
- [x/ ] only_latest_per_source rollup correct
- [x/ ] Latest-after-window semantic correct
- [x/ ] Workspace isolation preserved

## New findings (if any)
[SEVERITY] file:line — description

## Final word
GREEN | PARTIAL until X
```
