"""I-arch-007 ITEM 1 + ITEM 1b (#1264) — advisory credibility-pass wall-deadline + bounded parallelism.

The advisory credibility pass (``credibility_pass.run_credibility_analysis``) is NOT a binding gate
(CLAUDE.md §-1.3: ``strict_verify`` + NLI entailment + 4-role D8 + span-grounding are the ONLY hard
gates; ``basket_verdict`` is a pure LABEL). A SERIAL O(N) per-member entailment-verify loop in
``_assemble_baskets`` wedged the run (Q72/Q76/Q90) in ``generation_in_progress`` — the death this batch
fixes. These tests prove the two faithfulness-NEUTRAL fixes:

  ITEM 1  — a WALL-CLOCK bound (``PG_CREDIBILITY_PASS_WALL_S``) on the ``asyncio.to_thread`` offload so
            the run can NEVER hang: on expiry the always-release degrade ships ``credibility_analysis =
            None`` + a LOUD disclosed gap NAMING the timeout cause; with always-release OFF it re-raises
            (byte-identical legacy). No gate verdict moves — the four ``apply_disclosure_to_svs`` consumers
            are ``is not None``-guarded, so ``None`` ships sources UNSCORED at neutral weight.
  ITEM 1b — the per-member isolated verifies run under a BOUNDED pool (``PG_CREDIBILITY_PASS_MAX_INFLIGHT``,
            default 1 = byte-identical serial) with deterministic post-step reassembly: the baskets
            (member order, each ``span_verdict``, ``verified_support_origin_count``, ``basket_verdict``) are
            IDENTICAL serial vs parallel — only wall-clock differs. Each worker runs under a copied
            ``contextvars.copy_context()`` and reconciles run-scoped COST back to the parent (the run-scoped
            judge-telemetry dict is the SAME mutable object through the copy, so its in-place ticks
            auto-propagate — no explicit reconcile needed; mirrors ``provenance_generator``).

Offline / spend-free: ITEM 1 drives ``generate_multi_section_report`` with an EMPTY pool + ``partial_mode``
(no LLM, mirrors ``test_saturation_phase4.py::test_p4_7c_*``) and a STUB ``run_credibility_analysis``.
ITEM 1b reuses the REAL ``_assemble_baskets`` + REAL ``verify_sentence_provenance`` (entailment OFF, fully
deterministic) and a deterministic fake ``verify_fn`` to give the cost-parity assertion teeth. NO
``unittest.mock`` (CLAUDE.md §9.4).
"""
from __future__ import annotations

import asyncio
import time

import pytest

from src.polaris_graph.generator.multi_section_generator import (
    generate_multi_section_report,
)
from src.polaris_graph.planning.research_planner import (
    ResearchFrame,
    ResearchPlan,
    SectionOutlineItem,
)
from src.polaris_graph.retrieval.contradiction_detector import ExtractedNumericClaim
from src.polaris_graph.generator.provenance_generator import verify_sentence_provenance
from src.polaris_graph.synthesis.claim_graph import build_claim_graph
from src.polaris_graph.synthesis import credibility_pass as cp
from src.polaris_graph.synthesis.credibility_pass import (
    EvidenceCredibility,
    _assemble_baskets,
    _pass_max_inflight,
)
from src.polaris_graph.synthesis.weight_mass import aggregate_weight_mass
import src.polaris_graph.llm.openrouter_client as orc


# ─────────────────────────────────────────────────────────────────────────────
# PART A — ITEM 1: the wall-clock bound on the advisory credibility pass
# ─────────────────────────────────────────────────────────────────────────────


def _minimal_plan() -> ResearchPlan:
    return ResearchPlan(
        research_question="q",
        frame=ResearchFrame(),
        sub_queries=["sq0", "sq1"],
        outline=[
            SectionOutlineItem(
                archetype="Background",
                title="Kept Section",
                evidence_target=1,
                sub_query_indices=[0, 1],
            )
        ],
    )


def _drive_report(**overrides):
    """Drive the REAL generate_multi_section_report on the spend-free seam: an EMPTY evidence pool +
    partial_mode (sections drop with NO LLM call) + a credibility judge/gov_suffixes threaded so the
    pass guard decides 'run' and the ITEM-1 offload block is reached."""

    async def _run():
        kwargs = dict(
            research_question="q",
            evidence=[],
            research_plan=_minimal_plan(),
            partial_mode=True,
            live_corpus=[],
            # threaded so _credibility_guard_decision -> "run" (reaches the offload block)
            credibility_pass_judge=(lambda *a, **k: None),
            credibility_pass_gov_suffixes=(".gov",),
        )
        kwargs.update(overrides)
        return await generate_multi_section_report(**kwargs)

    return asyncio.run(_run())


def test_item1_wall_deadline_fires_degrades_and_does_not_hang(monkeypatch):
    """The bound FIRES + DEGRADES: a run_credibility_analysis that sleeps past the wall causes the
    report to RETURN (not hang), credibility_analysis is None, and the disclosed gap NAMES the
    timeout cause. always-release is ON (production default) so the degrade path is taken."""
    monkeypatch.setenv("PG_SWEEP_CREDIBILITY_REDESIGN", "1")
    monkeypatch.delenv("PG_ALWAYS_RELEASE", raising=False)  # default ON
    monkeypatch.setenv("PG_CREDIBILITY_PASS_WALL_S", "0.05")

    def _slow_pass(*args, **kwargs):
        # Sleep far past the 0.05s wall. If the wait_for did NOT fire (the report blocked on the
        # whole pass), THIS sentinel would surface as the result instead of the degrade path's None.
        time.sleep(0.6)
        return cp.CredibilityAnalysis({"BLOCKED": object()}, {}, [], [], [])

    monkeypatch.setattr(cp, "run_credibility_analysis", _slow_pass)

    result = _drive_report()

    # Did NOT block on the pass: the wall-deadline fired and the always-release degrade ran, so the
    # report ships credibility_analysis=None — NOT the stub's "BLOCKED" analysis. (The to_thread worker
    # is non-cancellable and is reaped at asyncio.run teardown — ITEM 1 honest caveat — but the run
    # itself never hung on it; the degrade outcome below is the load-bearing non-hang proof.)
    assert result.credibility_analysis is None
    # The disclosed gap is emitted AND names the timeout cause (LAW II: loud, never silent).
    gap = result.credibility_disclosed_gap
    assert gap is not None
    assert "wall-clock deadline" in gap
    assert "PG_CREDIBILITY_PASS_WALL_S" in gap


def test_item1_wall_deadline_off_path_reraises(monkeypatch):
    """always-release OFF (the legacy escape hatch): the SAME timeout re-raises a TimeoutError instead
    of degrading — byte-identical to the pre-fix fail-loud posture (the widened except still routes the
    TimeoutError, but the body re-raises when always-release is OFF)."""
    monkeypatch.setenv("PG_SWEEP_CREDIBILITY_REDESIGN", "1")
    monkeypatch.setenv("PG_ALWAYS_RELEASE", "0")  # OFF -> re-raise
    monkeypatch.setenv("PG_CREDIBILITY_PASS_WALL_S", "0.05")

    def _slow_pass(*args, **kwargs):
        time.sleep(0.6)
        return None

    monkeypatch.setattr(cp, "run_credibility_analysis", _slow_pass)

    with pytest.raises(asyncio.TimeoutError):
        _drive_report()


def test_item1_healthy_pass_completes_unaffected(monkeypatch):
    """A FAST pass completes within the wall -> credibility_analysis is populated, identical to today
    (the wall-deadline is a backstop, not a behavior change on the healthy path)."""
    monkeypatch.setenv("PG_SWEEP_CREDIBILITY_REDESIGN", "1")
    monkeypatch.delenv("PG_ALWAYS_RELEASE", raising=False)
    monkeypatch.setenv("PG_CREDIBILITY_PASS_WALL_S", "30")  # generous wall

    sentinel = cp.CredibilityAnalysis({}, {}, [], [], [])

    def _fast_pass(*args, **kwargs):
        return sentinel

    monkeypatch.setattr(cp, "run_credibility_analysis", _fast_pass)

    result = _drive_report()
    assert result.credibility_analysis is sentinel
    # no disclosed gap on the healthy path
    assert result.credibility_disclosed_gap is None


def test_item1_widened_except_routes_both_causes_in_source():
    """Structural guard (the byte-identical-degrade invariant): the offload site widens the degrade
    except to BOTH asyncio.TimeoutError AND CredibilityPassError so the wall-deadline degrades through
    the SAME B5/B7 always-release body as a pass-internal failure (no second handler, no body fork)."""
    import inspect

    src = inspect.getsource(generate_multi_section_report)
    assert "asyncio.wait_for(" in src
    assert 'os.getenv("PG_CREDIBILITY_PASS_WALL_S"' in src
    assert "except (asyncio.TimeoutError, _credibility_pass.CredibilityPassError)" in src


# ─────────────────────────────────────────────────────────────────────────────
# PART B — ITEM 1b: bounded-parallel _assemble_baskets, deterministic + reconciled
# ─────────────────────────────────────────────────────────────────────────────


def _all_known_numeric(evidence_id, *, value=14.9, **overrides):
    base = dict(
        evidence_id=evidence_id,
        subject="semaglutide",
        predicate="weight_loss",
        value=value,
        unit="%",
        context_snippet=f"Semaglutide achieved {value}% weight loss.",
        source_url=f"https://{evidence_id}.example.org",
        source_tier="T1",
        dose="2.4 mg",
        dose_frequency="weekly",
        comparator="placebo",
        route_formulation="sc",
        effect_measure="relative",
        direction="decrease",
        population="patients with t2dm",
        arm="comparator_adjacent",
        endpoint_phrase="at week 68",
    )
    base.update(overrides)
    return ExtractedNumericClaim(**base)


def _fake_numeric_extractor(claims_by_eid):
    def extractor(rows, domain=None):
        return [claims_by_eid[str(r.get("evidence_id", ""))]
                for r in rows if str(r.get("evidence_id", "")) in claims_by_eid]
    return extractor


def _no_qual_extractor(rows, domain=None):
    return []


def _annotated_rows(specs):
    rows = []
    for eid, dq, auth in specs:
        rows.append({
            "evidence_id": eid,
            "direct_quote": dq,
            "source_url": f"https://{eid}.example.org",
            "tier": "T1",
            "authority_score": auth,
            "origin_cluster_id": f"origin_{eid}",
            "is_canonical_origin": True,
        })
    return rows


def _credibility_map(rows):
    out = {}
    for r in rows:
        eid = r["evidence_id"]
        out[eid] = EvidenceCredibility(
            evidence_id=eid,
            credibility_weight=0.8,
            reliability_score=0.8,
            relevance_score=0.9,
            origin_cluster_id=r["origin_cluster_id"],
            is_canonical_origin=True,
            certainty_downgrade=False,
            soft_warning=None,
        )
    return out


def _build_graph_and_inputs():
    """A REAL multi-cluster, multi-member corpus: two clusters (14.9% and 22.5%), each with a member
    that supports alone and one that does not — so the baskets carry a MIX of SUPPORTS/UNSUPPORTED
    verdicts and full/partial labels (a parity test on a trivial all-SUPPORTS corpus would be weak)."""
    claims_by_eid = {
        "evA": _all_known_numeric("evA", value=14.9),
        "evB": _all_known_numeric("evB", value=14.9),   # same merge key as evA
        "evC": _all_known_numeric("evC", value=22.5),
        "evD": _all_known_numeric("evD", value=22.5),   # same merge key as evC
    }
    rows = _annotated_rows([
        ("evA", "Semaglutide achieved 14.9% weight loss at week 68 in the trial.", 0.9),
        ("evB", "A second cohort also showed 14.9% weight loss with semaglutide.", 0.8),
        ("evC", "Tirzepatide achieved 22.5% weight loss at week 72 in the trial.", 0.9),
        ("evD", "Liraglutide achieved 8.0% weight loss at week 56 in the trial.", 0.8),  # lacks 22.5 -> UNSUPPORTED alone
    ])
    graph = build_claim_graph(
        rows, domain="clinical",
        numeric_extractor=_fake_numeric_extractor(claims_by_eid),
        qualitative_extractor=_no_qual_extractor,
    )
    judgments = [
        type("J", (), {"evidence_id": r["evidence_id"], "credibility_weight": 0.8})()
        for r in rows
    ]
    weight_mass = aggregate_weight_mass(graph.claims, rows, judgments)
    return graph, weight_mass, rows, _credibility_map(rows)


def _basket_signature(baskets):
    """The faithfulness-load-bearing projection of the basket list: order + every verdict/label/count
    a downstream consumer reads. Parallelism must leave ALL of these identical to the serial path."""
    return [
        (
            b.claim_cluster_id,
            tuple((m.evidence_id, m.span_verdict) for m in b.supporting_members),
            b.verified_support_origin_count,
            b.total_clustered_origin_count,
            b.basket_verdict,
        )
        for b in baskets
    ]


@pytest.fixture(autouse=True)
def _offline_judges(monkeypatch):
    """Entailment / verification judges OFF -> verify_sentence_provenance is deterministic + offline;
    redesign master flag ON so the claim graph builds the merge keys consolidation needs."""
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "off")
    monkeypatch.setenv("PG_VERIFICATION_MODE", "off")
    monkeypatch.setenv("PG_SWEEP_CREDIBILITY_REDESIGN", "1")


def test_item1b_default_inflight_is_serial():
    """LAW VI + the 2a-before-1b ordering constraint: PG_CREDIBILITY_PASS_MAX_INFLIGHT defaults to 1
    (the byte-identical SERIAL path) so 1b's parallelism stays INERT until ITEM 2a makes the shared
    judge client thread-safe."""
    assert _pass_max_inflight() == 1


def test_item1b_parallel_baskets_identical_to_serial():
    """The core faithfulness-neutrality proof: the SAME corpus assembled SERIAL (max_inflight=1) vs
    BOUNDED-PARALLEL (max_inflight=8) yields byte-identical baskets — member order, each span_verdict,
    verified_support_origin_count, total_clustered_origin_count, and basket_verdict all match. The
    REAL production verify_sentence_provenance is used (advisory; never re-run as a gate)."""
    graph, weight_mass, rows, cred = _build_graph_and_inputs()

    serial = _assemble_baskets(
        graph, weight_mass, rows, cred,
        verify_fn=verify_sentence_provenance, max_inflight=1,
    )
    parallel = _assemble_baskets(
        graph, weight_mass, rows, cred,
        verify_fn=verify_sentence_provenance, max_inflight=8,
    )

    assert _basket_signature(serial) == _basket_signature(parallel)
    # Sanity: the corpus is non-trivial — MULTIPLE baskets AND a MIX of per-member SUPPORTS/UNSUPPORTED
    # verdicts (evD's span lacks 22.5 -> UNSUPPORTED alone; evA/evB/evC support alone) — so the parity
    # above genuinely exercises divergent per-member verdicts, not a degenerate all-same corpus.
    assert len(serial) >= 2, "expected multiple clusters/baskets"
    member_verdicts = {m.span_verdict for b in serial for m in b.supporting_members}
    assert member_verdicts == {"SUPPORTS", "UNSUPPORTED"}, (
        "the corpus must carry BOTH verdicts for the parity proof to be meaningful"
    )


def test_item1b_cost_reconcile_no_lost_ticks():
    """The cost-accounting teeth (Codex P2): with a deterministic fake verify_fn that charges a fixed
    cost per call onto the run-scoped cost ContextVar, the run-cost total after the parallel pass MUST
    equal the serial total AND equal N_members × per-call cost. If the per-worker reset/_add_run_cost
    reconcile were dropped, the copied-context spend would never propagate and the parallel total would
    read 0 — so this assertion fails loudly on a lost tick."""
    graph, weight_mass, rows, cred = _build_graph_and_inputs()
    per_call = 0.0007
    # one verify task per basket member (the flat per-member task list)
    n_members = sum(len(clusters_members) for clusters_members in graph.clusters.values())

    def _charging_verify(sentence, pool, **kwargs):
        orc._add_run_cost(per_call)  # charge the run-scoped cost ContextVar on every isolated verify
        return type("V", (), {"is_verified": True})()

    # SERIAL baseline
    orc.reset_run_cost()
    _assemble_baskets(graph, weight_mass, rows, cred, verify_fn=_charging_verify, max_inflight=1)
    serial_cost = orc.current_run_cost()

    # BOUNDED-PARALLEL: each worker resets + re-adds its delta; the parent must see the SAME total
    orc.reset_run_cost()
    _assemble_baskets(graph, weight_mass, rows, cred, verify_fn=_charging_verify, max_inflight=8)
    parallel_cost = orc.current_run_cost()

    assert serial_cost == pytest.approx(n_members * per_call)
    assert parallel_cost == pytest.approx(serial_cost), (
        "the parallel per-worker cost reconcile lost ticks — run-cost accounting is not faithful"
    )
