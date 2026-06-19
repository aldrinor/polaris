"""I-arch-007 ITEM 2 (#1264) CHOKE-FIX — the weighted-enrichment section MUST actually FIRE.

The forensic confirmed the breadth fix silently no-op'd in EVERY report: the enrichment plan was
NEVER appended (zero "appended weighted-enrichment section" log lines) because the call site logged
only the success branch and the decisive live gate (``credibility_analysis`` degraded to ``None`` on
a trickle-judge timeout) emptied the selection without a single line saying so. This suite proves the
COMPLETE fix, faithfulness-NEUTRAL:

  (a) given a corpus with unbound-SUPPORTS baskets, the enrichment plan IS built and contains the
      unbound ev_ids (the SELECTION surfaces the basket) — and the diagnostic surfaces a stable
      reason for EVERY LEGITIMATE empty-exit so a no-op is never silent again. I-arch-011 (B18):
      the "all below the relevance floor" empty-exit is RETIRED — the floor is now an ORDERING
      weight (keep-all-sort-below-floor-last), never a drop, so a below-floor pool keeps-all;
  (b) the enrichment SectionPlan is a plain ``SectionPlan`` (NOT a ``ContractSectionPlanExt``), so it
      dispatches through the UNCHANGED ``_run_section`` -> ``strict_verify`` faithfulness path — i.e.
      every newly-surfaced source re-passes the same gate before it earns a citation (faithfulness
      intact: strict_verify is still the binding gate);
  (c) the POST-RUN canary FAILS CLOSED when a released report drops the enrichment surface, and
      stands down correctly on a non-released / smoke / credibility-degraded run.

Pure offline unit test over the REAL basket dataclasses + the REAL canary; no network, no model
spend. The downstream strict_verify DROP of a fabricated / numeric-mismatch draft is the UNCHANGED
``_run_section`` gate (covered by the existing strict_verify suite); this suite proves the SELECTION
+ APPEND + CANARY wiring around it.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.polaris_graph.generator.contract_section_runner import is_contract_section
from src.polaris_graph.generator.multi_section_generator import SectionPlan
from src.polaris_graph.generator.weighted_enrichment import (
    _ENRICHMENT_TITLE,
    UnboundSupportsSelection,
    build_weighted_enrichment_plan,
    diagnose_unbound_supports_selection,
    select_unbound_supports_by_weight,
)
from src.polaris_graph.synthesis.credibility_pass import (
    BasketMember,
    ClaimBasket,
    CredibilityAnalysis,
)
from scripts.dr_benchmark.run_gate_b import (
    BreadthEnrichmentCanaryError,
    assert_breadth_enrichment_rendered,
)

_POOL = {f"ev{i}": {"evidence_id": f"ev{i}"} for i in range(1, 9)}


def _member(evidence_id: str, span_verdict: str) -> BasketMember:
    return BasketMember(
        evidence_id=evidence_id,
        source_url=f"https://example.org/{evidence_id}",
        source_tier="T2",
        origin_cluster_id=f"oc_{evidence_id}",
        credibility_weight=0.8,
        authority_score=0.8,
        span=(0, 20),
        direct_quote="a verified span of source text",
        span_verdict=span_verdict,
    )


def _basket(cluster_id: str, weight_mass: float, members: list[BasketMember]) -> ClaimBasket:
    n_supports = sum(1 for m in members if m.span_verdict == "SUPPORTS")
    return ClaimBasket(
        claim_cluster_id=cluster_id,
        claim_text="claim text",
        subject="subject",
        predicate="predicate",
        supporting_members=members,
        refuter_cluster_ids=(),
        weight_mass=weight_mass,
        total_clustered_origin_count=len(members),
        verified_support_origin_count=n_supports,
        basket_verdict="full",
    )


def _analysis(baskets: list[ClaimBasket]) -> CredibilityAnalysis:
    return CredibilityAnalysis(
        credibility_by_evidence={},
        origin_by_evidence={},
        claims=[],
        edges=[],
        weight_mass=[],
        baskets=baskets,
        cluster_id_by_evidence={},
    )


def _contract_plan(ev_ids, slot_entity_id_groups):
    return SimpleNamespace(
        title="Efficacy",
        ev_ids=list(ev_ids),
        slots=tuple(SimpleNamespace(entity_ids=list(g)) for g in slot_entity_id_groups),
    )


# ── (a) the selection surfaces the unbound SUPPORTS basket + diagnoses every empty exit ──────────


def test_enrichment_plan_built_with_unbound_supports_ev_ids():
    """A corpus with unbound-SUPPORTS baskets => the enrichment plan IS built and carries the
    unbound ev_ids (the §-1.3 breadth surface). The contract-bound members are NOT re-surfaced."""
    baskets = [
        # ev1 is bound to the contract; ev2/ev3/ev4 are UNBOUND span-verified SUPPORTS.
        _basket("c1", 0.9, [_member("ev1", "SUPPORTS"), _member("ev2", "SUPPORTS")]),
        _basket("c2", 0.6, [_member("ev3", "SUPPORTS")]),
        _basket("c3", 0.4, [_member("ev4", "SUPPORTS"), _member("ev5", "UNSUPPORTED")]),
    ]
    contract = [_contract_plan(ev_ids=["ev1"], slot_entity_id_groups=[])]
    sel = diagnose_unbound_supports_selection(
        evidence_pool=_POOL, credibility_analysis=_analysis(baskets), contract_plans=contract,
    )
    assert isinstance(sel, UnboundSupportsSelection)
    assert sel.reason == "ok"
    # ev1 bound (excluded); ev5 UNSUPPORTED (never surfaces); ev2/ev3/ev4 surface, weight desc.
    assert sel.ev_ids == ["ev2", "ev3", "ev4"]
    assert sel.excluded_bound == 1  # ev1
    assert sel.supports_members_seen == 4  # ev1, ev2, ev3, ev4 (ev5 is UNSUPPORTED, not counted)

    plan = build_weighted_enrichment_plan(sel.ev_ids, section_plan_cls=SectionPlan)
    assert plan is not None
    assert plan.ev_ids == ["ev2", "ev3", "ev4"]
    assert plan.title == _ENRICHMENT_TITLE


def test_select_wrapper_matches_diagnostic_list():
    """The list-returning wrapper is byte-identical to the diagnostic form's ev_ids (back-compat)."""
    baskets = [_basket("c1", 0.9, [_member("ev2", "SUPPORTS"), _member("ev3", "SUPPORTS")])]
    contract = [_contract_plan([], [])]
    a = select_unbound_supports_by_weight(
        evidence_pool=_POOL, credibility_analysis=_analysis(baskets), contract_plans=contract,
    )
    b = diagnose_unbound_supports_selection(
        evidence_pool=_POOL, credibility_analysis=_analysis(baskets), contract_plans=contract,
    )
    assert a == b.ev_ids == ["ev2", "ev3"]


@pytest.mark.parametrize(
    "credibility_analysis_factory, baskets, contract, pool, expected_reason",
    [
        # credibility degraded to None — the decisive LIVE gate (trickle-judge timeout).
        (lambda b: None, None, [_contract_plan([], [])], _POOL, "credibility_analysis_none"),
        # baskets empty.
        (_analysis, [], [_contract_plan([], [])], _POOL, "no_baskets"),
        # baskets exist but no SUPPORTS member at all.
        (
            _analysis,
            [_basket("c1", 0.9, [_member("ev1", "UNSUPPORTED")])],
            [_contract_plan([], [])],
            _POOL,
            "no_supports_members",
        ),
        # every SUPPORTS member already bound.
        (
            _analysis,
            [_basket("c1", 0.9, [_member("ev1", "SUPPORTS")])],
            [_contract_plan(["ev1"], [])],
            _POOL,
            "all_supports_bound_or_pool_absent",
        ),
        # I-arch-011 (B18): the "every remaining member below the relevance floor" empty-exit is
        # RETIRED — the floor no longer EXCLUDES (keep-all-sort-below-floor-last). A below-floor-only
        # pool now yields a NON-empty kept-all selection (see
        # test_below_floor_pool_is_not_an_empty_exit_keep_all), so it is no longer an empty-exit case.
    ],
)
def test_every_empty_exit_has_a_distinct_reason(
    monkeypatch, credibility_analysis_factory, baskets, contract, pool, expected_reason,
):
    """No empty-exit is silent: each way the selection can LEGITIMATELY be empty (degraded
    credibility / no baskets / no SUPPORTS member / all bound-or-pool-absent) yields a DISTINCT,
    machine-readable reason the call site logs LOUDLY (the observability meta-bug). I-arch-011 (B18):
    "all below floor" is NO LONGER an empty-exit — the floor demotes ORDER, never drops."""
    monkeypatch.setenv("PG_RELEVANCE_FLOOR", "0.30")
    ca = credibility_analysis_factory(baskets)
    sel = diagnose_unbound_supports_selection(
        evidence_pool=pool, credibility_analysis=ca, contract_plans=contract,
    )
    assert sel.ev_ids == []
    assert sel.reason == expected_reason
    # An empty selection builds NO plan => byte-identical OFF/degrade append path.
    assert build_weighted_enrichment_plan(sel.ev_ids, section_plan_cls=SectionPlan) is None


def test_below_floor_pool_is_not_an_empty_exit_keep_all(monkeypatch):
    """I-arch-011 (B18) — WEIGHT-not-FILTER: a pool where the ONLY SUPPORTS member is below the
    relevance floor is NO LONGER an empty exit. The member is KEPT and sorted last (the floor is an
    ORDERING weight, never a drop); the reason is 'ok'. The pre-I-arch-011 code DROPPED it and
    reported 'all_candidates_below_relevance_floor' — this test encodes the removed neck and FAILS on
    the pre-fix code."""
    monkeypatch.setenv("PG_RELEVANCE_FLOOR", "0.30")
    sel = diagnose_unbound_supports_selection(
        evidence_pool={"ev1": {"evidence_id": "ev1", "selection_relevance": 0.01}},
        credibility_analysis=_analysis([_basket("c1", 0.9, [_member("ev1", "SUPPORTS")])]),
        contract_plans=[_contract_plan([], [])],
    )
    assert sel.ev_ids == ["ev1"]  # KEPT, not dropped
    assert sel.reason == "ok"
    assert sel.excluded_below_floor == 1  # telemetry: kept-but-below-floor (NOT an exclusion)
    # And a real plan IS built (the breadth section fires, not a silent no-op).
    assert build_weighted_enrichment_plan(sel.ev_ids, section_plan_cls=SectionPlan) is not None


# ── (b) the enrichment plan routes through the UNCHANGED strict_verify path (faithfulness intact) ─


def test_enrichment_plan_dispatches_through_legacy_strict_verify_path():
    """The enrichment SectionPlan is a PLAIN SectionPlan (NOT a ContractSectionPlanExt), so the
    dispatcher routes it through _run_section -> strict_verify — the UNCHANGED faithfulness gate.
    Every surfaced source therefore re-passes strict_verify before it earns a citation."""
    plan = build_weighted_enrichment_plan(["ev2", "ev3"], section_plan_cls=SectionPlan)
    assert plan is not None
    # is_contract_section gates the dispatch: False => legacy _run_section => strict_verify path.
    assert is_contract_section(plan) is False


# ── (c) the POST-RUN canary fails closed on a silent breadth drop, stands down legitimately ──────


def _write_report(body: str) -> str:
    d = Path(tempfile.mkdtemp())
    (d / "report.md").write_text(body, encoding="utf-8")
    return str(d)


def test_canary_present_when_section_rendered_with_citation():
    run_dir = _write_report(
        f"# Report\n## {_ENRICHMENT_TITLE}\nAn unbound corroborated finding [42].\n"
    )
    assert assert_breadth_enrichment_rendered(
        {"status": "success", "run_dir": run_dir}
    ) == "present"


def test_canary_fails_closed_when_section_absent():
    run_dir = _write_report("# Report\nContract entities only; no enrichment section.\n")
    with pytest.raises(BreadthEnrichmentCanaryError, match="does NOT contain"):
        assert_breadth_enrichment_rendered({"status": "success", "run_dir": run_dir})


def test_canary_fails_closed_when_section_has_no_citation():
    """Section heading present but ZERO citation markers => the breadth surface silently emptied
    (heading + gap-disclosure only). Fail closed — no unbound source survived into a cited slot."""
    run_dir = _write_report(
        f"# Report\n## {_ENRICHMENT_TITLE}\nNo additional corroborated findings were verified.\n"
    )
    with pytest.raises(BreadthEnrichmentCanaryError, match="NO citation marker"):
        assert_breadth_enrichment_rendered({"status": "success", "run_dir": run_dir})


def test_canary_fails_closed_on_credibility_degrade_with_no_enrichment():
    """Codex P0 (choke-fix iter2): a credibility TOTAL-degrade that rendered NO enrichment is the
    EXACT choke this canary guards — it FAILS CLOSED (it was WRONGLY a stand-down, which green-lit the
    silent no-op the operator flagged). The manifest degrade signal annotates the failure with the
    cause + remediation; it never skips. The report still ships via always-release — this canary is a
    benchmark-quality gate (re-run the choked datapoint), not a report hold."""
    run_dir = _write_report("# Report\nNo enrichment (credibility degraded).\n")
    with pytest.raises(BreadthEnrichmentCanaryError) as _exc:
        assert_breadth_enrichment_rendered({
            "status": "success",
            "run_dir": run_dir,
            "manifest": {"credibility_disclosed_gap": "the credibility pass timed out"},
        })
    # the degrade cause + remediation are surfaced in the failure message (hint), not silently skipped
    assert "credibility" in str(_exc.value).lower()
    assert "PG_CREDIBILITY_PASS_WALL_S" in str(_exc.value)


def test_canary_fails_closed_on_disclosed_gap_in_manifest_list():
    """A breadth/credibility total-degrade disclosed in the manifest disclosed_gaps list, with no
    rendered enrichment, FAILS CLOSED (Codex P0 iter2) — re-run the choked datapoint."""
    run_dir = _write_report("# Report\nNo enrichment.\n")
    with pytest.raises(BreadthEnrichmentCanaryError) as _exc:
        assert_breadth_enrichment_rendered({
            "status": "success",
            "run_dir": run_dir,
            "manifest": {"disclosed_gaps": ["breadth_enrichment_unavailable: pass did not complete"]},
        })
    assert "RE-RUN" in str(_exc.value)


def test_canary_present_when_degraded_but_enrichment_rendered():
    """Codex P0 iter2 — the fix must NOT over-fail: a run that disclosed a MINOR per-source gap but
    STILL rendered the enrichment section with an in-section citation is HEALTHY (the credibility pass
    completed; the gap is incidental). Report-content decides => 'present', no false-fail."""
    run_dir = _write_report(
        f"# Report\n## {_ENRICHMENT_TITLE}\nAn unbound corroborated finding [7].\n"
    )
    out = assert_breadth_enrichment_rendered({
        "status": "success",
        "run_dir": run_dir,
        "manifest": {"credibility_disclosed_gap": "1/730 sources unscored"},
    })
    assert out == "present"


def test_canary_fails_closed_on_hollow_section_with_trailing_bibliography():
    """Codex P1 (choke-fix iter2): a HOLLOW enrichment heading followed by a downstream
    References/Bibliography section that carries [N] markers must STILL fail — the citation check is
    scoped to the enrichment SECTION body (heading -> next heading), not heading-to-EOF, so a trailing
    bibliography cannot satisfy it."""
    run_dir = _write_report(
        f"# Report\n## {_ENRICHMENT_TITLE}\nNo additional corroborated findings were verified.\n"
        f"## References\n[1] Some Source — https://example.org\n[2] Another — https://example.org\n"
    )
    with pytest.raises(BreadthEnrichmentCanaryError, match="NO citation marker"):
        assert_breadth_enrichment_rendered({"status": "success", "run_dir": run_dir})


def test_canary_stands_down_on_non_released_status():
    run_dir = _write_report(f"# Report\n## {_ENRICHMENT_TITLE}\nfinding [1].\n")
    assert assert_breadth_enrichment_rendered(
        {"status": "abort_scope_rejected", "run_dir": run_dir}
    ).startswith("skip:status=")


def test_canary_stands_down_on_smoke_scale():
    run_dir = _write_report("# Report\nthin smoke pool, no enrichment.\n")
    assert assert_breadth_enrichment_rendered(
        {"status": "success", "run_dir": run_dir}, smoke_scale=True,
    ) == "skip:smoke_scale"


def test_canary_reads_manifest_json_from_disk_when_summary_lacks_it():
    """When the in-process summary has no manifest, the canary reads manifest.json from run_dir to
    build the degrade HINT — then FAILS CLOSED on the absent enrichment (Codex P0 iter2: a degraded
    run with no breadth surface is the choke, not a stand-down)."""
    import json
    d = Path(tempfile.mkdtemp())
    (d / "report.md").write_text("# Report\nNo enrichment (degraded).\n", encoding="utf-8")
    (d / "manifest.json").write_text(
        json.dumps({"credibility_disclosed_gap": "pass timed out"}), encoding="utf-8",
    )
    with pytest.raises(BreadthEnrichmentCanaryError) as _exc:
        assert_breadth_enrichment_rendered({"status": "success", "run_dir": str(d)})
    assert "credibility" in str(_exc.value).lower()
