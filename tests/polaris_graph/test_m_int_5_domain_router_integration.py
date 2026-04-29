"""M-INT-5 — Domain router integrated into sweep flow.

Acceptance bar:
  1. Imported (DomainTemplate, DomainTemplateRegistry, DomainAdapter,
     RoutingResult, RoutingOutcome, route_to_domain)
  2. Invoked (`_route_query_to_domain` called from sweep when
     scope LLM produced a verdict)
  3. Run-log evidence (`[M-INT-5] domain_router: outcome=...`)
  4. PG_USE_DOMAIN_ROUTER=0 disables (returns None)
  5. UNCERTAIN-verdict fallback path: routing returns
     REJECTED_UNCERTAIN, NOT in_scope, NOT raise
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


def test_sweep_imports_domain_router_substrates() -> None:
    sweep = importlib.import_module("scripts.run_honest_sweep_r3")
    assert hasattr(sweep, "DomainTemplate")
    assert hasattr(sweep, "DomainTemplateRegistry")
    assert hasattr(sweep, "DomainAdapter")
    assert hasattr(sweep, "RoutingResult")
    assert hasattr(sweep, "RoutingOutcome")
    assert hasattr(sweep, "route_to_domain")
    assert hasattr(sweep, "_route_query_to_domain")
    assert hasattr(sweep, "_build_domain_router_registry")
    assert hasattr(sweep, "_build_domain_router_adapters")


def test_route_in_scope_clinical_returns_routed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PG_USE_DOMAIN_ROUTER", "1")
    sweep = importlib.import_module("scripts.run_honest_sweep_r3")
    from src.polaris_graph.audit_ir.scope_classifier import (
        ScopeClassification, ScopeVerdict,
    )
    classification = ScopeClassification(
        verdict=ScopeVerdict.IN_SCOPE,
        confidence=0.85,
        domain="clinical",
        rationale="clinical-specific keywords detected",
    )
    summary = sweep._route_query_to_domain(classification)
    assert summary is not None
    assert summary["outcome"] == "routed"
    assert summary["domain"] == "clinical"
    # Adapter IDs should be present
    assert isinstance(summary["adapter_ids"], list)
    assert len(summary["adapter_ids"]) >= 1


def test_route_out_of_scope_rejects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PG_USE_DOMAIN_ROUTER", "1")
    sweep = importlib.import_module("scripts.run_honest_sweep_r3")
    from src.polaris_graph.audit_ir.scope_classifier import (
        ScopeClassification, ScopeVerdict,
    )
    classification = ScopeClassification(
        verdict=ScopeVerdict.OUT_OF_SCOPE,
        confidence=0.9,
        domain=None,
        rationale="non-supported domain",
    )
    summary = sweep._route_query_to_domain(classification)
    assert summary is not None
    assert summary["outcome"] == "rejected_out_of_scope"
    assert summary["domain"] is None


def test_route_uncertain_does_not_raise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Per FINAL_PLAN M-INT-5 acceptance bar: UNCERTAIN-verdict
    fallback path must NOT raise."""
    monkeypatch.setenv("PG_USE_DOMAIN_ROUTER", "1")
    sweep = importlib.import_module("scripts.run_honest_sweep_r3")
    from src.polaris_graph.audit_ir.scope_classifier import (
        ScopeClassification, ScopeVerdict,
    )
    classification = ScopeClassification(
        verdict=ScopeVerdict.UNCERTAIN,
        confidence=0.4,
        domain=None,
        rationale="borderline",
    )
    summary = sweep._route_query_to_domain(classification)
    assert summary is not None
    assert summary["outcome"] == "rejected_uncertain"


def test_disabled_flag_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PG_USE_DOMAIN_ROUTER", "0")
    sweep = importlib.import_module("scripts.run_honest_sweep_r3")
    from src.polaris_graph.audit_ir.scope_classifier import (
        ScopeClassification, ScopeVerdict,
    )
    classification = ScopeClassification(
        verdict=ScopeVerdict.IN_SCOPE,
        confidence=0.85, domain="clinical", rationale="x",
    )
    summary = sweep._route_query_to_domain(classification)
    assert summary is None


def test_route_failure_does_not_raise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Per LAW II — routing failure must not gate sweep."""
    monkeypatch.setenv("PG_USE_DOMAIN_ROUTER", "1")
    sweep = importlib.import_module("scripts.run_honest_sweep_r3")

    def _broken_route(*args, **kwargs):
        raise RuntimeError("simulated router failure")

    monkeypatch.setattr(sweep, "route_to_domain", _broken_route)

    from src.polaris_graph.audit_ir.scope_classifier import (
        ScopeClassification, ScopeVerdict,
    )
    classification = ScopeClassification(
        verdict=ScopeVerdict.IN_SCOPE,
        confidence=0.85, domain="clinical", rationale="x",
    )
    summary = sweep._route_query_to_domain(classification)
    # Returns None on internal failure, never raises.
    assert summary is None


def test_route_unknown_domain_outcome(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """In-scope verdict with a domain not in the registry should
    route as UNKNOWN_DOMAIN, not raise."""
    monkeypatch.setenv("PG_USE_DOMAIN_ROUTER", "1")
    sweep = importlib.import_module("scripts.run_honest_sweep_r3")
    from src.polaris_graph.audit_ir.scope_classifier import (
        ScopeClassification, ScopeVerdict,
    )
    classification = ScopeClassification(
        verdict=ScopeVerdict.IN_SCOPE,
        confidence=0.85,
        domain="aerospace",  # not in default registry
        rationale="x",
    )
    summary = sweep._route_query_to_domain(classification)
    assert summary is not None
    assert summary["outcome"] == "unknown_domain"
