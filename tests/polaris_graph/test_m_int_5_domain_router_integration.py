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


# ---------------------------------------------------------------------------
# Codex round-1 fixes (v2)
# ---------------------------------------------------------------------------


def test_route_unknown_domain_preserves_original_domain_tag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Codex round-1 MEDIUM: v1 lost the LLM-asserted domain on
    unknown_domain outcomes (result.template is None →
    summary['domain']=None). v2 surfaces requested_domain so
    telemetry preserves "user asked for aerospace, registry
    doesn't know it" signal."""
    monkeypatch.setenv("PG_USE_DOMAIN_ROUTER", "1")
    sweep = importlib.import_module("scripts.run_honest_sweep_r3")
    from src.polaris_graph.audit_ir.scope_classifier import (
        ScopeClassification, ScopeVerdict,
    )
    classification = ScopeClassification(
        verdict=ScopeVerdict.IN_SCOPE,
        confidence=0.85,
        domain="aerospace",
        rationale="x",
    )
    summary = sweep._route_query_to_domain(
        classification, requested_domain="aerospace",
    )
    assert summary is not None
    assert summary["outcome"] == "unknown_domain"
    assert summary["domain"] is None  # registry didn't match
    assert summary["requested_domain"] == "aerospace"  # preserved


def test_route_routed_domain_matches_requested(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the route succeeds, requested_domain should match
    template.domain_id."""
    monkeypatch.setenv("PG_USE_DOMAIN_ROUTER", "1")
    sweep = importlib.import_module("scripts.run_honest_sweep_r3")
    from src.polaris_graph.audit_ir.scope_classifier import (
        ScopeClassification, ScopeVerdict,
    )
    classification = ScopeClassification(
        verdict=ScopeVerdict.IN_SCOPE,
        confidence=0.85,
        domain="clinical",
        rationale="x",
    )
    summary = sweep._route_query_to_domain(
        classification, requested_domain="clinical",
    )
    assert summary["domain"] == "clinical"
    assert summary["requested_domain"] == "clinical"


def test_route_default_requested_domain_from_classification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When caller doesn't pass requested_domain explicitly, the
    helper should default to classification.domain. This keeps
    the simple call shape `_route_query_to_domain(classification)`
    working with the v2 schema."""
    monkeypatch.setenv("PG_USE_DOMAIN_ROUTER", "1")
    sweep = importlib.import_module("scripts.run_honest_sweep_r3")
    from src.polaris_graph.audit_ir.scope_classifier import (
        ScopeClassification, ScopeVerdict,
    )
    classification = ScopeClassification(
        verdict=ScopeVerdict.IN_SCOPE,
        confidence=0.85,
        domain="aerospace",
        rationale="x",
    )
    summary = sweep._route_query_to_domain(classification)  # no kwarg
    assert summary["requested_domain"] == "aerospace"


# ---------------------------------------------------------------------------
# Codex round-1 HIGH fix: malformed M-INT-4 dict shape MUST NOT
# abort run_one_query (LAW II — best-effort telemetry).
# ---------------------------------------------------------------------------


def test_run_one_query_survives_malformed_scope_llm_dict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Codex round-1 HIGH: v1 dereferenced scope_llm_summary
    dict keys with [] before the M-INT-5 try block, so a malformed
    M-INT-4 dict (e.g. {'verdict': 'in_scope'}) raised KeyError
    that aborted run_one_query at the outer fatal handler. v2
    uses .get() throughout the M-INT-4 log line + M-INT-5 synthesis
    so a malformed dict degrades to a partial log line + None
    routing summary, never an abort.
    """
    import asyncio

    monkeypatch.setenv("PG_USE_LLM_SCOPE", "1")
    monkeypatch.setenv("PG_USE_DOMAIN_ROUTER", "1")
    monkeypatch.setenv("PG_CAPTURE_PIN", "0")

    sweep = importlib.import_module("scripts.run_honest_sweep_r3")

    # Stub _classify_scope_with_llm to return a malformed dict —
    # missing "confidence", "domain", "template_domain_hint".
    monkeypatch.setattr(
        sweep, "_classify_scope_with_llm",
        lambda *a, **kw: {"verdict": "in_scope"},  # malformed
    )

    # Stub run_scope_gate to short-circuit successfully —
    # we only care about the M-INT-4/5 wiring path.
    from types import SimpleNamespace

    def _fake_run_scope_gate(*args, **kwargs):
        protocol = SimpleNamespace(
            scope_decision="accepted",
            scope_rejected=False,
            scope_rejection_code=None,
            scope_reasons=[],
            needs_user_review=False,
            to_json_dict=lambda: {"decision": "accepted"},
        )
        return SimpleNamespace(
            protocol=protocol,
            protocol_sha256="0" * 64,
        )

    monkeypatch.setattr(sweep, "run_scope_gate", _fake_run_scope_gate)

    # Stub run_live_retrieval to short-circuit (we just need the
    # query path to NOT abort due to malformed M-INT-4 dict).
    async def _fake_retrieval(**kwargs):
        return SimpleNamespace(
            evidence=[],
            run_dir=kwargs.get("run_dir") or tmp_path,
            stats={"sources": 0},
        )

    monkeypatch.setattr(sweep, "run_live_retrieval", _fake_retrieval)

    q = {
        "domain": "tech",
        "slug": "malformed_dict_smoke",
        "question": "Test query",
    }

    out_root = tmp_path / "out"
    out_root.mkdir(parents=True, exist_ok=True)

    # Should NOT raise — the malformed M-INT-4 dict must not
    # propagate a KeyError out of the M-INT-4 log line or M-INT-5
    # synthesis. The query may abort for OTHER reasons (corpus
    # adequacy, etc.), but NOT due to malformed scope_llm_summary.
    summary = asyncio.run(sweep.run_one_query(q, out_root))

    # The status must NOT be "error" with a KeyError — it can
    # be any other valid pipeline status (success / abort_*).
    error_msg = str(summary.get("error", ""))
    assert "KeyError" not in error_msg, (
        f"M-INT-4 malformed dict caused KeyError abort: {error_msg!r}"
    )
    assert "'confidence'" not in error_msg
    assert "'template_domain_hint'" not in error_msg
