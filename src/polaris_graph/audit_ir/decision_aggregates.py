"""M-D3 phase 2 v1 (Phase D): Decision telemetry aggregation.

M-D3 phase 1 (`decision_telemetry.py`, commit 212102d) shipped
the per-workspace SQLite DecisionRecordStore. Records-level
APIs (record_decision, update_curator_action, get,
list_for_workspace, count_for_workspace) are all in place.

Phase 2 v1 layers **aggregation queries** on top: per-workspace
acceptance/modification/override/rejection rates, optionally
filtered by DecisionKind and time-windowed. Pure substrate
on top of the M-D3 phase 1 store.

## Why this milestone matters

M-D4 (auto-trust gate) is calendar-blocked on accumulating ≥6
months of telemetry. When M-D4 ships, it will need aggregate
metrics like "what fraction of induction decisions in this
workspace over the last 90 days were accepted_as_proposed?"
to decide whether the system is trustworthy enough to bypass
the operator-review queue for that workspace.

Phase 2 v1 ships the substrate query API M-D4 will consume.
No M-D4 calibration logic here — just the deterministic
aggregation primitive.

## What v1 ships

  - `DecisionAggregates` dataclass — counts + rates per
    terminal action, plus pending count, plus
    total_decisions and total_terminal aggregates
  - `compute_aggregates(store, workspace_id, *,
    decision_kind, since, until)` — pure derivation backed
    by the M-D3 phase 1 store query API

## Substrate boundary

Imports `decision_telemetry` (CuratorAction, DecisionKind,
DecisionRecordStore, DecisionTelemetryError) only. No new DB
schema; reuses the phase 1 store's queries. No LLM, no HTTP.

See `docs/md3_phase2_threat_model.md` for boundaries.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from src.polaris_graph.audit_ir.decision_telemetry import (
    CuratorAction,
    DecisionKind,
    DecisionRecord,
    DecisionRecordStore,
    DecisionTelemetryError,
)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class DecisionAggregatesError(ValueError):
    """Raised on contract violations — invalid window, etc."""


# ---------------------------------------------------------------------------
# Aggregates dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DecisionAggregates:
    """Per-window decision aggregates.

    `total_decisions` is total records in the window (including
    PENDING — i.e. records the curator hasn't yet acted on).
    `total_terminal` is the subset that has reached a terminal
    `CuratorAction`. The 4 terminal counts sum to `total_terminal`.
    `pending_count` is `total_decisions - total_terminal`.

    `acceptance_rate`, `modification_rate`, `override_rate`,
    `rejection_rate` are each `count / total_terminal`. They
    are None when `total_terminal == 0` (rates are undefined
    on an empty terminal set — surfacing 0.0 would be
    misleading: "0% accepted because we haven't decided
    anything" is different from "0% accepted because curator
    rejects everything").

    `window_start` / `window_end` are the time bounds applied
    to the query (UNIX epoch floats, same convention as
    DecisionRecord.created_at). `None` means open on that
    end.

    `decision_kind` is None for "all kinds aggregated" or a
    specific kind for filtered aggregates.
    """

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
    acceptance_rate: float | None
    modification_rate: float | None
    override_rate: float | None
    rejection_rate: float | None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compute_aggregates(
    store: DecisionRecordStore,
    workspace_id: str,
    *,
    decision_kind: DecisionKind | None = None,
    since: float | None = None,
    until: float | None = None,
) -> DecisionAggregates:
    """Compute decision aggregates for `workspace_id`.

    `decision_kind` filters to one kind (induction vs
    scope_gate); None aggregates across both.

    `since` and `until` are UNIX epoch floats (matching
    `DecisionRecord.created_at`). Records with
    `created_at < since` or `created_at > until` are excluded.
    Both bounds are inclusive on the boundary. Either can be
    None for an open window. `since == until` selects records
    captured exactly at that instant (rare but valid).

    Pure derivation backed by the M-D3 phase 1 store's
    `list_for_workspace` API. No new SQL paths added — the
    aggregation is computed in Python over the returned
    record list. This trades query efficiency for code
    simplicity at the v1 stage; v2 may add a SQL-side
    aggregation query if record counts grow.
    """
    if not isinstance(store, DecisionRecordStore):
        raise DecisionAggregatesError(
            f"store must be DecisionRecordStore, got "
            f"{type(store).__name__}"
        )
    if not workspace_id or not workspace_id.strip():
        raise DecisionAggregatesError("workspace_id must be non-empty")
    if since is not None and until is not None and since > until:
        raise DecisionAggregatesError(
            f"since ({since}) must be <= until ({until})"
        )

    ws = workspace_id.strip()

    # Use the v1 store's query API. Pull all records (no limit)
    # for the workspace+kind filter, then filter+aggregate in
    # Python.
    records = store.list_for_workspace(
        ws, decision_kind=decision_kind,
    )

    counts = {
        CuratorAction.PENDING: 0,
        CuratorAction.ACCEPTED_AS_PROPOSED: 0,
        CuratorAction.MODIFIED: 0,
        CuratorAction.OVERRIDDEN: 0,
        CuratorAction.REJECTED: 0,
    }
    total_decisions = 0

    for rec in records:
        if since is not None and rec.created_at < since:
            continue
        if until is not None and rec.created_at > until:
            continue
        total_decisions += 1
        counts[rec.curator_action] = counts[rec.curator_action] + 1

    pending = counts[CuratorAction.PENDING]
    accepted = counts[CuratorAction.ACCEPTED_AS_PROPOSED]
    modified = counts[CuratorAction.MODIFIED]
    overridden = counts[CuratorAction.OVERRIDDEN]
    rejected = counts[CuratorAction.REJECTED]
    total_terminal = accepted + modified + overridden + rejected

    if total_terminal == 0:
        acceptance_rate = None
        modification_rate = None
        override_rate = None
        rejection_rate = None
    else:
        acceptance_rate = accepted / total_terminal
        modification_rate = modified / total_terminal
        override_rate = overridden / total_terminal
        rejection_rate = rejected / total_terminal

    return DecisionAggregates(
        workspace_id=ws,
        decision_kind=decision_kind,
        window_start=since,
        window_end=until,
        total_decisions=total_decisions,
        total_terminal=total_terminal,
        pending_count=pending,
        accepted_count=accepted,
        modified_count=modified,
        overridden_count=overridden,
        rejected_count=rejected,
        acceptance_rate=acceptance_rate,
        modification_rate=modification_rate,
        override_rate=override_rate,
        rejection_rate=rejection_rate,
    )
