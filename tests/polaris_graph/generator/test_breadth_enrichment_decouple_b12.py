"""B12 (#1356) behavioral fire-test — weighted-enrichment breadth surfaces on the
GENERIC (non-contract) DRB render path.

THE BUG (forensic basket B12): the I-arch-007 breadth-enrichment block in
``multi_section_generator`` was gated behind ``v30_contract_plans`` being present
(``if not (v30_contract_plans and not partial_mode): skip``). On a generic
DeepResearch-Bench-II run there are NO v30 contract plans, so the breadth enrichment
NEVER fired — the very path the breadth deficit (~27 rows) was measured on.

THE FIX: the skip now gates ONLY on ``partial_mode`` + the already-force-ON master flag
``PG_BREADTH_ENRICHMENT_ENABLED``; ``contract_plans=list(v30_contract_plans or [])`` is
passed through (empty on the generic path => ``contract_bound_evidence_ids`` returns an
empty set => nothing wrongly excluded; the bound set on the contract path is byte-identical).

This test FAILS LOUD if the decouple regresses:
  (1) it imports the REAL ``diagnose_unbound_supports_selection`` /
      ``build_weighted_enrichment_plan`` and proves that with ``contract_plans=[]``
      (the generic path) a real basket with an in-pool SUPPORTS member yields a NON-EMPTY
      selection and a BUILT enrichment SectionPlan — i.e. the breadth surfaces; and
  (2) it asserts (source-level guard) that the call-site skip no longer references
      ``v30_contract_plans`` as a precondition for SKIPPING (so a future edit that
      re-couples it is caught).

Faithfulness-neutral: the surfaced section still routes through the UNCHANGED strict_verify;
this test only proves the SELECTION+PLAN-BUILD seam fires on the non-contract path.
"""
from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

from src.polaris_graph.generator.weighted_enrichment import (
    build_weighted_enrichment_plan,
    diagnose_unbound_supports_selection,
)


class _SectionPlanStub:
    """Minimal SectionPlan duck (build_weighted_enrichment_plan only sets title/focus/ev_ids)."""

    def __init__(self, *, title: str, focus: str, ev_ids: list[str]) -> None:
        self.title = title
        self.focus = focus
        self.ev_ids = ev_ids


def _make_credibility_analysis_with_supports() -> SimpleNamespace:
    """A real-shaped credibility_analysis carrying ONE basket with a span-verified SUPPORTS
    member (the diagnose fn reads attrs via getattr — duck typing is faithful to production)."""
    member = SimpleNamespace(span_verdict="SUPPORTS", evidence_id="ev_007")
    basket = SimpleNamespace(weight_mass=0.91, supporting_members=[member])
    return SimpleNamespace(baskets=[basket])


def test_b12_enrichment_fires_on_generic_non_contract_path(monkeypatch):
    """With contract_plans=[] (generic DRB path) the breadth selection is NON-EMPTY and a
    SectionPlan is built — the decouple's whole point. Pre-fix the call site never reached
    this on the non-contract path."""
    # PG_RELEVANCE_FLOOR default (0.30) — a pool row with no relevance score is keep-neutral.
    monkeypatch.delenv("PG_RELEVANCE_FLOOR", raising=False)
    credibility_analysis = _make_credibility_analysis_with_supports()
    # The evidence pool must resolve the eid so the section can cite a real span.
    evidence_pool = {"ev_007": {"text": "Tirzepatide reduced HbA1c by 2.1% vs placebo."}}

    selection = diagnose_unbound_supports_selection(
        evidence_pool=evidence_pool,
        credibility_analysis=credibility_analysis,
        contract_plans=[],  # <-- THE GENERIC PATH: no v30 contract plans present
    )

    # FIRE assertion 1: a SUPPORTS member surfaced on the non-contract path.
    assert selection.ev_ids == ["ev_007"], (
        "B12 REGRESSION: weighted-enrichment selected NOTHING on the generic (contract_plans=[]) "
        f"path — breadth will not surface on a DRB run. selection={selection!r}"
    )
    assert selection.reason == "ok"
    assert selection.excluded_bound == 0, (
        "B12: an empty contract_plans must bind NOTHING (contract_bound_evidence_ids([])==set())"
    )

    # FIRE assertion 2: the plan actually builds (a non-None SectionPlan the caller appends).
    plan = build_weighted_enrichment_plan(selection.ev_ids, section_plan_cls=_SectionPlanStub)
    assert plan is not None, "B12 REGRESSION: no enrichment SectionPlan built from a non-empty selection"
    assert plan.ev_ids == ["ev_007"]


def test_b12_call_site_skip_does_not_recouple_to_v30_contract_plans():
    """Source-level guard: the breadth call-site SKIP must gate on partial_mode + the master flag,
    NOT on ``v30_contract_plans`` presence. Catches a future edit that re-introduces the coupling."""
    src = Path(__file__).resolve().parents[3] / "src" / "polaris_graph" / "generator" / "multi_section_generator.py"
    text = src.read_text(encoding="utf-8")
    # The decoupled guard.
    assert "if partial_mode:" in text, (
        "B12 REGRESSION: the decoupled `if partial_mode:` skip guard is gone from the breadth block"
    )
    # The OLD coupled skip condition must NOT be present any more.
    assert "if not (v30_contract_plans and not partial_mode):" not in text, (
        "B12 REGRESSION: the breadth block RE-COUPLED its skip to v30_contract_plans presence — "
        "the enrichment will not fire on the generic DRB (non-contract) path again."
    )
    # The diagnose call must pass the None-safe `or []` form (generic path => empty bound set).
    assert re.search(r"contract_plans=list\(v30_contract_plans or \[\]\)", text), (
        "B12 REGRESSION: the diagnose call no longer passes the None-safe "
        "`list(v30_contract_plans or [])` — the non-contract path may crash or over-exclude."
    )
