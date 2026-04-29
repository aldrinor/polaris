"""M-INT-7 — Billing quota gating in production.

Acceptance bar:
  1. Imported (BillingQuotaStore, PlanTier, QuotaEventKind,
     QuotaExceededError)
  2. Invoked (`_check_audit_run_quota` from sweep)
  3. Run-log evidence (`[M-INT-7] billing_quota:` line)
  4. PG_USE_BILLING_QUOTA=0 disables (default 0)
  5. QuotaExceededError → abort with quota_exceeded status
     (does NOT raise into outer fatal)
  6. Failure does NOT raise (LAW II)
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


def test_sweep_imports_billing_quota_substrates() -> None:
    sweep = importlib.import_module("scripts.run_honest_sweep_r3")
    assert hasattr(sweep, "BillingQuotaStore")
    assert hasattr(sweep, "PlanTier")
    assert hasattr(sweep, "QuotaEventKind")
    assert hasattr(sweep, "QuotaExceededError")
    assert hasattr(sweep, "_check_audit_run_quota")


def test_check_audit_run_quota_consumes_when_under_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PG_USE_BILLING_QUOTA", "1")
    monkeypatch.setenv(
        "PG_BILLING_QUOTA_DB_PATH", str(tmp_path / "billing.sqlite"),
    )
    monkeypatch.setenv("PG_BILLING_ORG_ID", "test_org")

    sweep = importlib.import_module("scripts.run_honest_sweep_r3")

    # Pre-assign a plan so the consume call has a quota to draw from.
    from src.polaris_graph.audit_ir.billing_quota_store import (
        BillingQuotaStore, PlanTier,
    )
    store = BillingQuotaStore(tmp_path / "billing.sqlite")
    store.assign_plan(org_id="test_org", tier=PlanTier.STARTUP)

    summary = sweep._check_audit_run_quota()
    assert summary is not None
    assert summary["consumed"] is True
    assert summary["org_id"] == "test_org"
    assert summary["used"] >= 1
    assert summary["cap"] >= 1


def test_check_audit_run_quota_rejects_when_over_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Per FINAL_PLAN M-INT-7: quota exceeded must produce a
    rejection signal, NOT a successful consume."""
    monkeypatch.setenv("PG_USE_BILLING_QUOTA", "1")
    monkeypatch.setenv(
        "PG_BILLING_QUOTA_DB_PATH", str(tmp_path / "billing.sqlite"),
    )
    monkeypatch.setenv("PG_BILLING_ORG_ID", "rejected_org")

    sweep = importlib.import_module("scripts.run_honest_sweep_r3")

    # Pre-assign a tiny quota and exhaust it.
    from src.polaris_graph.audit_ir.billing_quota_store import (
        BillingQuotaStore, PlanTier, QuotaEventKind,
    )
    store = BillingQuotaStore(tmp_path / "billing.sqlite")
    store.assign_plan(
        org_id="rejected_org",
        tier=PlanTier.PILOT,
        quotas_override={QuotaEventKind.AUDIT_RUN_ENQUEUED: 1},
    )
    store.consume(
        org_id="rejected_org",
        kind=QuotaEventKind.AUDIT_RUN_ENQUEUED,
    )  # exhaust

    summary = sweep._check_audit_run_quota()
    assert summary is not None
    assert summary["consumed"] is False
    assert summary["exceeded"] is True


def test_disabled_flag_returns_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PG_USE_BILLING_QUOTA", "0")
    sweep = importlib.import_module("scripts.run_honest_sweep_r3")
    summary = sweep._check_audit_run_quota()
    assert summary is None


def test_no_org_id_returns_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without PG_BILLING_ORG_ID set, the helper should return
    None (best-effort: don't gate the sweep without an explicit
    org assignment)."""
    monkeypatch.setenv("PG_USE_BILLING_QUOTA", "1")
    monkeypatch.delenv("PG_BILLING_ORG_ID", raising=False)
    sweep = importlib.import_module("scripts.run_honest_sweep_r3")
    summary = sweep._check_audit_run_quota()
    assert summary is None


def test_no_plan_assigned_returns_exceeded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An org with no assigned plan gets zero quota — consume
    raises QuotaExceededError. Helper must turn that into a
    structured summary, not propagate."""
    monkeypatch.setenv("PG_USE_BILLING_QUOTA", "1")
    monkeypatch.setenv(
        "PG_BILLING_QUOTA_DB_PATH", str(tmp_path / "billing.sqlite"),
    )
    monkeypatch.setenv("PG_BILLING_ORG_ID", "no_plan_org")

    sweep = importlib.import_module("scripts.run_honest_sweep_r3")
    summary = sweep._check_audit_run_quota()
    assert summary is not None
    assert summary["consumed"] is False
    assert summary["exceeded"] is True


def test_billing_failure_does_not_raise(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Per LAW II — billing path failure must not gate sweep."""
    monkeypatch.setenv("PG_USE_BILLING_QUOTA", "1")
    monkeypatch.setenv(
        "PG_BILLING_QUOTA_DB_PATH", str(tmp_path / "billing.sqlite"),
    )
    monkeypatch.setenv("PG_BILLING_ORG_ID", "test_org")

    sweep = importlib.import_module("scripts.run_honest_sweep_r3")

    # Force the store constructor to raise.
    def _broken_store(*args, **kwargs):
        raise RuntimeError("simulated billing store failure")

    monkeypatch.setattr(sweep, "BillingQuotaStore", _broken_store)

    summary = sweep._check_audit_run_quota()
    # Returns None on internal failure — does not raise.
    assert summary is None
