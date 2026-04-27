"""Billing + quotas (M-NEW — Phase C).

Per FINAL_PLAN Phase C deliverable #6 (under
"Org-level RBAC + workspace isolation + billing + quotas + ..."),
the billing + quotas substrate that gates org-level audit-run
enqueue + audit-bundle export + workspace creation.

Scope of v1:
  - Per-org plan + quota limits (audit_runs_per_month,
    workspace_count, audit_bundle_exports_per_month).
  - Atomic counter increments for billed events.
  - reset_monthly_counters() for the start-of-billing-cycle job.
  - check_quota(org_id, kind) returns the remaining budget; the
    runner / endpoint pre-check refuses to enqueue when budget
    is exhausted.
  - Append-only billing_events table for invoicing reconciliation
    + customer-facing usage reports.

Out of scope for v1:
  - Stripe / payment-rails integration. The plan assignment is
    operator-managed via direct SQL until a v2 milestone wires
    in self-serve billing.
  - Per-event metered pricing. v1 is fixed-tier (Pilot, Startup,
    Production) with hard quotas. v2 adds usage-based overage.

LAW VII compliance: stdlib + the existing audit_ir surface
only. The endpoint that wires this in is added separately.
"""

from __future__ import annotations

import sqlite3
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Plan tiers + quota event kinds
# ---------------------------------------------------------------------------


class PlanTier(Enum):
    """Stable string-valued plan tier identifiers."""

    PILOT = "pilot"
    STARTUP = "startup"
    PRODUCTION = "production"
    ENTERPRISE = "enterprise"


class QuotaEventKind(Enum):
    """Each quota-tracked operation type.

    Stable string values so external billing reconciliation can
    join on these without pickling enums.
    """

    AUDIT_RUN_ENQUEUED = "audit_run_enqueued"
    AUDIT_BUNDLE_EXPORTED = "audit_bundle_exported"
    WORKSPACE_CREATED = "workspace_created"


# Per-tier hard limits. operator can override via update_plan().
# Keys: (tier, kind) → monthly cap. -1 means unlimited.
_PLAN_DEFAULTS: dict[PlanTier, dict[QuotaEventKind, int]] = {
    PlanTier.PILOT: {
        QuotaEventKind.AUDIT_RUN_ENQUEUED: 50,
        QuotaEventKind.AUDIT_BUNDLE_EXPORTED: 50,
        QuotaEventKind.WORKSPACE_CREATED: 5,
    },
    PlanTier.STARTUP: {
        QuotaEventKind.AUDIT_RUN_ENQUEUED: 500,
        QuotaEventKind.AUDIT_BUNDLE_EXPORTED: 500,
        QuotaEventKind.WORKSPACE_CREATED: 25,
    },
    PlanTier.PRODUCTION: {
        QuotaEventKind.AUDIT_RUN_ENQUEUED: 5000,
        QuotaEventKind.AUDIT_BUNDLE_EXPORTED: 5000,
        QuotaEventKind.WORKSPACE_CREATED: 100,
    },
    PlanTier.ENTERPRISE: {
        QuotaEventKind.AUDIT_RUN_ENQUEUED: -1,
        QuotaEventKind.AUDIT_BUNDLE_EXPORTED: -1,
        QuotaEventKind.WORKSPACE_CREATED: -1,
    },
}


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class BillingQuotaError(Exception):
    """Base error for billing/quota operations."""


class QuotaExceededError(BillingQuotaError):
    """Raised when an org has hit its monthly cap for a given kind."""


class QuotaStateError(BillingQuotaError):
    """Invalid input or state."""


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PlanAssignment:
    """One org's plan + per-kind quota overrides.

    `quotas` is the resolved quota for THIS org; either the
    PlanTier defaults or an operator-supplied override.
    """

    org_id: str
    tier: PlanTier
    quotas: dict[QuotaEventKind, int]
    cycle_start: float  # Unix timestamp; counters reset on/after this.


@dataclass(frozen=True)
class QuotaCheckResult:
    """Returned by check_quota() — used by callers to decide
    whether to proceed with a billed action."""

    org_id: str
    kind: QuotaEventKind
    used: int
    cap: int
    remaining: int  # cap - used; -1 if cap is unlimited
    is_exceeded: bool


@dataclass(frozen=True)
class BillingEvent:
    """One row in the billing_events append-only log."""

    event_id: str
    org_id: str
    kind: QuotaEventKind
    user_id: str | None
    cost_units: int  # always 1 in v1; v2 surfaces actual cost
    created_at: float


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


_SCHEMA = """
CREATE TABLE IF NOT EXISTS plans (
    org_id TEXT PRIMARY KEY,
    tier TEXT NOT NULL,
    quotas_json TEXT NOT NULL,
    cycle_start REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS billing_events (
    event_id TEXT PRIMARY KEY,
    org_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    user_id TEXT,
    cost_units INTEGER NOT NULL DEFAULT 1,
    created_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_billing_events_org_kind_created
    ON billing_events(org_id, kind, created_at);

CREATE INDEX IF NOT EXISTS idx_billing_events_org_created
    ON billing_events(org_id, created_at);
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _quotas_to_json(quotas: dict[QuotaEventKind, int]) -> str:
    """Serialize a quota dict to a JSON-safe string keyed by enum
    string value (not the enum object)."""
    import json
    return json.dumps(
        {k.value: v for k, v in quotas.items()},
        sort_keys=True,
    )


def _quotas_from_json(raw: str | None) -> dict[QuotaEventKind, int]:
    import json
    if not raw:
        return {}
    decoded = json.loads(raw)
    out: dict[QuotaEventKind, int] = {}
    for k, v in decoded.items():
        try:
            kind = QuotaEventKind(k)
        except ValueError:
            continue
        out[kind] = int(v)
    return out


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


class BillingQuotaStore:
    """SQLite-backed billing + quota store.

    Per-call connections (matches the workspace/job/review/memory
    pattern). WAL journal mode. BEGIN IMMEDIATE on
    increment/check-and-increment paths so racing calls serialize.

    Authorization posture (Codex M-NEW v1 review):
    This store is PRIVILEGED-ONLY. It does NOT validate that the
    caller has authority over the passed `org_id` — any caller
    who can invoke `consume()` / `check_quota()` / `assign_plan()`
    can target any org. The endpoint layer that wires this up
    MUST gate on caller.org_id == passed org_id (and on
    admin/owner role for assign_plan / reset_monthly_counters).
    Without that gate, the store is a cross-org auth boundary
    bypass.
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            self._db_path, isolation_level=None, timeout=30.0,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    # ------------------------------------------------------------------
    # Plan management
    # ------------------------------------------------------------------

    def assign_plan(
        self,
        *,
        org_id: str,
        tier: PlanTier,
        quotas_override: dict[QuotaEventKind, int] | None = None,
    ) -> PlanAssignment:
        """Assign a plan to an org. Idempotent — re-assigning
        updates the row in place. The assignment resets the
        cycle_start so the new tier takes effect immediately."""
        if not org_id.strip():
            raise QuotaStateError("org_id must be non-empty")
        if not isinstance(tier, PlanTier):
            raise QuotaStateError(
                f"tier must be PlanTier, got {tier!r}"
            )
        quotas = dict(_PLAN_DEFAULTS[tier])
        if quotas_override:
            for k, v in quotas_override.items():
                if not isinstance(k, QuotaEventKind):
                    raise QuotaStateError(
                        f"quota override key must be QuotaEventKind; "
                        f"got {k!r}"
                    )
                if not isinstance(v, int):
                    raise QuotaStateError(
                        f"quota override value must be int; got {v!r}"
                    )
                # Codex M-NEW v1 review fix: only -1 means unlimited;
                # other negative values would silently grant unlimited
                # too because the enforcement path treats cap<0 as
                # unbounded. v2 rejects all negatives except -1.
                if v < -1:
                    raise QuotaStateError(
                        f"quota override value must be >= 0 for a "
                        f"finite cap, or exactly -1 for unlimited; "
                        f"got {v}"
                    )
                quotas[k] = v
        # Codex M-NEW v1 review fix: capture `now` AFTER acquiring
        # BEGIN IMMEDIATE so a racing consume() can't slip an event
        # into the new cycle window between the timestamp capture
        # and the row write.
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                # Codex M-NEW v1 review fix: redundant re-assign of
                # the SAME tier with the SAME overrides should NOT
                # refresh cycle_start (a customer calling assign_plan
                # to "confirm tier" should not get free budget).
                # Refresh cycle only when the plan composition
                # actually changes.
                existing = conn.execute(
                    "SELECT tier, quotas_json, cycle_start "
                    "FROM plans WHERE org_id = ?",
                    (org_id,),
                ).fetchone()
                composition_changed = True
                cycle_start = time.time()
                if existing is not None:
                    if (
                        existing["tier"] == tier.value
                        and existing["quotas_json"] == _quotas_to_json(quotas)
                    ):
                        composition_changed = False
                        cycle_start = float(existing["cycle_start"])
                conn.execute(
                    "INSERT INTO plans (org_id, tier, quotas_json, "
                    "cycle_start, updated_at) VALUES (?, ?, ?, ?, ?) "
                    "ON CONFLICT(org_id) DO UPDATE SET "
                    "tier = excluded.tier, "
                    "quotas_json = excluded.quotas_json, "
                    "cycle_start = excluded.cycle_start, "
                    "updated_at = excluded.updated_at",
                    (
                        org_id.strip(), tier.value,
                        _quotas_to_json(quotas),
                        cycle_start, time.time(),
                    ),
                )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        return PlanAssignment(
            org_id=org_id.strip(), tier=tier, quotas=quotas,
            cycle_start=cycle_start,
        )

    def get_plan(self, *, org_id: str) -> PlanAssignment | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM plans WHERE org_id = ?",
                (org_id,),
            ).fetchone()
        if row is None:
            return None
        return PlanAssignment(
            org_id=row["org_id"],
            tier=PlanTier(row["tier"]),
            quotas=_quotas_from_json(row["quotas_json"]),
            cycle_start=float(row["cycle_start"]),
        )

    def reset_monthly_counters(self, *, org_id: str) -> None:
        """Mark the start of a new billing cycle for an org.

        v1 doesn't physically delete prior billing events — they
        stay in the append-only log for invoicing. The "counter
        reset" is implemented by updating cycle_start; subsequent
        check_quota / increment calls only count events newer than
        cycle_start when computing usage.

        Codex M-NEW v1 review fix: `now` is captured AFTER
        BEGIN IMMEDIATE acquires the write lock, so an event
        committed milliseconds before the lock cannot accidentally
        land in the new cycle window.
        """
        if not org_id.strip():
            raise QuotaStateError("org_id must be non-empty")
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                now = time.time()
                cur = conn.execute(
                    "UPDATE plans SET cycle_start = ?, updated_at = ? "
                    "WHERE org_id = ?",
                    (now, now, org_id.strip()),
                )
                if cur.rowcount == 0:
                    raise QuotaStateError(
                        f"org {org_id!r} has no assigned plan; "
                        f"cannot reset"
                    )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise

    # ------------------------------------------------------------------
    # Quota check + atomic increment
    # ------------------------------------------------------------------

    def check_quota(
        self, *, org_id: str, kind: QuotaEventKind,
    ) -> QuotaCheckResult:
        """Return current usage + remaining budget for one kind.

        The org MUST have an assigned plan; orgs with no plan get
        zero quota (the caller's pre-check refuses the action).
        """
        plan = self.get_plan(org_id=org_id)
        if plan is None:
            return QuotaCheckResult(
                org_id=org_id, kind=kind, used=0, cap=0,
                remaining=0, is_exceeded=True,
            )
        used = self._used_in_cycle(
            org_id=org_id, kind=kind, cycle_start=plan.cycle_start,
        )
        cap = int(plan.quotas.get(kind, 0))
        if cap < 0:
            # -1 means unlimited.
            return QuotaCheckResult(
                org_id=org_id, kind=kind, used=used, cap=-1,
                remaining=-1, is_exceeded=False,
            )
        remaining = max(0, cap - used)
        return QuotaCheckResult(
            org_id=org_id, kind=kind, used=used, cap=cap,
            remaining=remaining, is_exceeded=remaining == 0,
        )

    def consume(
        self,
        *,
        org_id: str,
        kind: QuotaEventKind,
        user_id: str | None = None,
        cost_units: int = 1,
    ) -> BillingEvent:
        """Atomic check-and-increment: raises QuotaExceededError
        if the action would exceed the cap. On success appends a
        billing_events row.
        """
        if cost_units < 1:
            raise QuotaStateError(
                f"cost_units must be >= 1; got {cost_units}"
            )
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                # Look up plan inside the transaction so a racing
                # update_plan() can't slip a quota change between
                # check and increment.
                plan_row = conn.execute(
                    "SELECT tier, quotas_json, cycle_start "
                    "FROM plans WHERE org_id = ?",
                    (org_id,),
                ).fetchone()
                if plan_row is None:
                    raise QuotaExceededError(
                        f"org {org_id!r} has no assigned plan; "
                        f"cannot consume quota"
                    )
                quotas = _quotas_from_json(plan_row["quotas_json"])
                cap = int(quotas.get(kind, 0))
                cycle_start = float(plan_row["cycle_start"])

                used_row = conn.execute(
                    "SELECT COALESCE(SUM(cost_units), 0) AS s "
                    "FROM billing_events "
                    "WHERE org_id = ? AND kind = ? AND created_at >= ?",
                    (org_id, kind.value, cycle_start),
                ).fetchone()
                used = int(used_row["s"])

                if cap >= 0 and (used + cost_units) > cap:
                    raise QuotaExceededError(
                        f"org {org_id!r} exceeded {kind.value!r} "
                        f"quota: cap {cap}, used {used}, "
                        f"requested {cost_units}"
                    )

                event_id = f"bil_{uuid.uuid4().hex[:16]}"
                now = time.time()
                conn.execute(
                    "INSERT INTO billing_events (event_id, org_id, "
                    "kind, user_id, cost_units, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        event_id, org_id, kind.value,
                        user_id, cost_units, now,
                    ),
                )
                conn.execute("COMMIT")
                return BillingEvent(
                    event_id=event_id, org_id=org_id, kind=kind,
                    user_id=user_id, cost_units=cost_units,
                    created_at=now,
                )
            except Exception:
                conn.execute("ROLLBACK")
                raise

    # ------------------------------------------------------------------
    # Read paths
    # ------------------------------------------------------------------

    def list_events(
        self,
        *,
        org_id: str,
        kind: QuotaEventKind | None = None,
        since: float | None = None,
        until: float | None = None,
        limit: int = 1000,
    ) -> list[BillingEvent]:
        if limit < 1 or limit > 10000:
            raise QuotaStateError(
                f"limit must be in [1, 10000]; got {limit}"
            )
        clauses = ["org_id = ?"]
        params: list[Any] = [org_id]
        if kind is not None:
            clauses.append("kind = ?")
            params.append(kind.value)
        if since is not None:
            clauses.append("created_at >= ?")
            params.append(since)
        if until is not None:
            clauses.append("created_at <= ?")
            params.append(until)
        sql = (
            f"SELECT * FROM billing_events WHERE "
            f"{' AND '.join(clauses)} "
            f"ORDER BY created_at DESC LIMIT ?"
        )
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [
            BillingEvent(
                event_id=r["event_id"], org_id=r["org_id"],
                kind=QuotaEventKind(r["kind"]),
                user_id=r["user_id"],
                cost_units=int(r["cost_units"]),
                created_at=float(r["created_at"]),
            )
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _used_in_cycle(
        self, *, org_id: str, kind: QuotaEventKind, cycle_start: float,
    ) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(cost_units), 0) AS s "
                "FROM billing_events "
                "WHERE org_id = ? AND kind = ? AND created_at >= ?",
                (org_id, kind.value, cycle_start),
            ).fetchone()
        return int(row["s"]) if row is not None else 0
