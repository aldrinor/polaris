"""I-deepfix-001 BANK-BEFORE-WALL — the credibility pass BANKS partial verdicts at its soft
deadline; the all-or-nothing wall discard that emptied the corroboration layer is structurally gone.

drb_72 box1 (commit 9db58130, ``run_gate_b.py --only drb_72_ai_labor``, rc=1): a rich corpus
(1061 sources / ~999 basket members) overran the force-pinned ``PG_CREDIBILITY_PASS_WALL_S=3000``;
``asyncio.wait_for`` discarded the WHOLE ``CredibilityAnalysis`` -> ``credibility_analysis=None`` ->
``weighted_enrichment.diagnose_unbound_supports_selection`` returned
``reason=credibility_analysis_none`` -> NO "Corroborated Weighted Findings" section in report.md ->
the breadth-enrichment canary FAILED CLOSED (the §-1.3 funnel silently reasserting).

This suite proves OFFLINE (no network, no model spend), against the REAL production functions:
  (1) legacy behavior preserved — no deadline => genuine verdicts only, byte-identical paths;
  (2) the serial AND bounded-parallel member-verify paths BANK the verified prefix at the deadline
      and sentinel-fill the rest (KEEP-ALL: length preserved, disclosed, nothing raises/discards);
  (3) the banked SUPPORTS members flow through the REAL enrichment selection + plan builder — the
      "Corroborated Weighted Findings" SectionPlan IS built (the render precondition);
  (4) the REAL post-run canary returns "present" on a report carrying the section + a citation and
      still FAILS CLOSED on the box1 shape (no enrichment heading at all) — fail-closed preserved;
  (5) the phase-A budget cap: ``score_source_credibility(pool_wall_s=...)`` bounds the join under
      the caller's budget and priors-fills at the cap (drain-not-discard), so phase B (the leg that
      feeds the SUPPORTS baskets) is always left a share of the deadline budget.

FAITHFULNESS-NEUTRAL throughout: the verifier is INJECTED (the frozen strict_verify / NLI / 4-role
engine is never edited, never re-run as a gate); a deadline-skipped member is
``("UNSUPPORTED", UNVERIFIED, judge_unavailable=True)`` — an UNDERCOUNT-only, disclosed degrade
that can never surface an unverified claim or inflate corroboration.
"""

from __future__ import annotations

import json
import time as real_time
from types import SimpleNamespace

import pytest

import src.polaris_graph.synthesis.credibility_pass as cp
from src.polaris_graph.authority.credibility_skill import _judge_rows_pooled
from src.polaris_graph.generator.weighted_enrichment import (
    _ENRICHMENT_TITLE,
    build_weighted_enrichment_plan,
    diagnose_unbound_supports_selection,
)
from src.polaris_graph.generator.multi_section_generator import SectionPlan
from src.polaris_graph.synthesis.credibility_pass import (
    _DEADLINE_SKIP_VERDICT,
    _run_member_verifies,
    BasketMember,
    ClaimBasket,
    CredibilityAnalysis,
)
from scripts.dr_benchmark.run_gate_b import (
    BreadthEnrichmentCanaryError,
    assert_breadth_enrichment_rendered,
)

_GENUINE = ("SUPPORTS", "ENTAILMENT_VERIFIED", False)


def _tasks(n: int) -> list[tuple[str, dict]]:
    return [
        (f"claim text {i}", {"evidence_id": f"ev{i}", "direct_quote": f"span text {i}"})
        for i in range(n)
    ]


# ── (1) legacy no-deadline paths are unchanged ────────────────────────────────────────────────────


def test_no_deadline_serial_all_genuine(monkeypatch):
    calls = []
    monkeypatch.setattr(
        cp, "_verify_member_in_isolation",
        lambda text, row, *, verify_fn: (calls.append(text) or _GENUINE),
    )
    out = _run_member_verifies(_tasks(4), verify_fn=object(), max_inflight=1)
    assert out == [_GENUINE] * 4
    assert len(calls) == 4


def test_no_deadline_parallel_all_genuine(monkeypatch):
    monkeypatch.setattr(
        cp, "_verify_member_in_isolation", lambda text, row, *, verify_fn: _GENUINE,
    )
    out = _run_member_verifies(_tasks(5), verify_fn=object(), max_inflight=3)
    assert out == [_GENUINE] * 5
    assert _DEADLINE_SKIP_VERDICT not in out


# ── (2) deadline paths BANK the verified prefix and sentinel-fill the rest (KEEP-ALL) ─────────────


def test_serial_deadline_banks_prefix_and_fills_rest(monkeypatch):
    """Fake clock: each verify advances 1.0s; deadline at t=2.5 => exactly 3 banked, 2 sentinel."""
    now = [0.0]

    def _fake_verify(text, row, *, verify_fn):
        now[0] += 1.0
        return _GENUINE

    monkeypatch.setattr(cp, "_verify_member_in_isolation", _fake_verify)
    monkeypatch.setattr(cp, "time", SimpleNamespace(monotonic=lambda: now[0]))
    out = _run_member_verifies(
        _tasks(5), verify_fn=object(), max_inflight=1, deadline_monotonic=2.5,
    )
    assert len(out) == 5  # KEEP-ALL: every member gets a verdict slot, nothing dropped
    assert out[:3] == [_GENUINE] * 3  # the verified prefix is BANKED verbatim
    assert out[3:] == [_DEADLINE_SKIP_VERDICT] * 2  # the rest disclosed, undercount-only
    assert now[0] == 3.0  # no further verifier work after expiry (no hang, no spend)


def test_serial_already_expired_deadline_zero_calls(monkeypatch):
    calls = []
    monkeypatch.setattr(
        cp, "_verify_member_in_isolation",
        lambda text, row, *, verify_fn: (calls.append(1) or _GENUINE),
    )
    monkeypatch.setattr(cp, "time", SimpleNamespace(monotonic=lambda: 100.0))
    out = _run_member_verifies(
        _tasks(3), verify_fn=object(), max_inflight=1, deadline_monotonic=1.0,
    )
    assert out == [_DEADLINE_SKIP_VERDICT] * 3
    assert calls == []  # structurally bounded: zero verifier calls after expiry


def test_parallel_deadline_banks_completed_and_fills_rest(monkeypatch):
    """Real clock, generous margins: 2 fast members bank; 4 slow members sentinel-fill at the
    deadline. Proves the bounded-parallel join banks-then-returns instead of discarding."""

    def _fake_verify(text, row, *, verify_fn):
        if "slow" in text:
            real_time.sleep(2.0)
        return _GENUINE

    monkeypatch.setattr(cp, "_verify_member_in_isolation", _fake_verify)
    tasks = [
        ("fast 0", {"evidence_id": "ev0", "direct_quote": "s"}),
        ("fast 1", {"evidence_id": "ev1", "direct_quote": "s"}),
        ("slow 2", {"evidence_id": "ev2", "direct_quote": "s"}),
        ("slow 3", {"evidence_id": "ev3", "direct_quote": "s"}),
        ("slow 4", {"evidence_id": "ev4", "direct_quote": "s"}),
        ("slow 5", {"evidence_id": "ev5", "direct_quote": "s"}),
    ]
    t0 = real_time.monotonic()
    out = _run_member_verifies(
        tasks, verify_fn=object(), max_inflight=2,
        deadline_monotonic=real_time.monotonic() + 0.6,
    )
    elapsed = real_time.monotonic() - t0
    assert len(out) == 6                      # KEEP-ALL
    assert out[0] == _GENUINE and out[1] == _GENUINE  # completed verdicts BANKED
    assert out[2] == _DEADLINE_SKIP_VERDICT   # in-flight/queued at the deadline => sentinel
    assert out[5] == _DEADLINE_SKIP_VERDICT
    assert elapsed < 1.9                      # returned at the deadline, not after 2.0s+ of joins


# ── (3) banked SUPPORTS members SURFACE the enrichment plan (the render precondition) ─────────────


def test_banked_supports_surface_the_enrichment_plan(monkeypatch):
    """One basket, one member verified BEFORE the deadline (SUPPORTS, banked) and one skipped at
    the deadline (the sentinel verdict). The REAL selection surfaces the banked member; the REAL
    plan builder emits the "Corroborated Weighted Findings" SectionPlan — under the old
    all-or-nothing discard this whole surface was ``credibility_analysis_none``-empty."""
    monkeypatch.delenv("PG_RELEVANCE_FLOOR", raising=False)
    banked = BasketMember(
        evidence_id="ev_banked", source_url="https://journals.example.org/a", source_tier="T2",
        origin_cluster_id="oc_a", credibility_weight=0.8, authority_score=0.8,
        span=(0, 30), direct_quote="a verified span of source text",
        span_verdict="SUPPORTS",
    )
    skipped = BasketMember(
        evidence_id="ev_skipped", source_url="https://journals.example.org/b", source_tier="T2",
        origin_cluster_id="oc_b", credibility_weight=0.8, authority_score=0.8,
        span=(0, 30), direct_quote="another span of source text",
        # the BANK-BEFORE-WALL sentinel shape: UNSUPPORTED + disclosed verification-unavailable
        span_verdict=_DEADLINE_SKIP_VERDICT[0],
    )
    basket = ClaimBasket(
        claim_cluster_id="clm_1", claim_text="claim text", subject="s", predicate="p",
        supporting_members=[banked, skipped], refuter_cluster_ids=(),
        weight_mass=1.0, total_clustered_origin_count=2, verified_support_origin_count=1,
        basket_verdict="partial",
    )
    analysis = CredibilityAnalysis(
        credibility_by_evidence={}, origin_by_evidence={}, claims=[], edges=[],
        weight_mass=[], baskets=[basket], cluster_id_by_evidence={},
    )
    pool = {
        "ev_banked": {"evidence_id": "ev_banked", "direct_quote": "a verified span of source text"},
        "ev_skipped": {"evidence_id": "ev_skipped", "direct_quote": "another span of source text"},
    }
    sel = diagnose_unbound_supports_selection(
        evidence_pool=pool, credibility_analysis=analysis, contract_plans=[],
    )
    assert sel.reason == "ok"
    assert sel.ev_ids == ["ev_banked"]      # the banked member surfaces
    # the skipped member can only UNDERCOUNT: it is absent from the cite surface, never deleted
    assert "ev_skipped" in pool
    plan = build_weighted_enrichment_plan(sel.ev_ids, section_plan_cls=SectionPlan)
    assert plan is not None
    assert plan.title == _ENRICHMENT_TITLE  # "Corroborated Weighted Findings" renders
    assert plan.ev_ids == ["ev_banked"]


def test_old_discard_shape_still_diagnosed_empty():
    """RED shape (box1): credibility_analysis=None (the wall discard) => the selection is EMPTY with
    the stable reason token — the report then carries NO enrichment heading and the canary fails.
    This is the exact failure the bank now prevents upstream."""
    sel = diagnose_unbound_supports_selection(
        evidence_pool={"ev1": {"evidence_id": "ev1"}}, credibility_analysis=None, contract_plans=[],
    )
    assert sel.ev_ids == []
    assert sel.reason == "credibility_analysis_none"
    assert build_weighted_enrichment_plan(sel.ev_ids, section_plan_cls=SectionPlan) is None


# ── (4) the REAL canary: present on the fixed shape, fail-closed on the box1 shape ────────────────


def _summary(run_dir) -> dict:
    return {"status": "success", "run_dir": str(run_dir), "manifest": {}}


def test_canary_present_when_enrichment_section_renders(tmp_path):
    (tmp_path / "report.md").write_text(
        "# Research report: q\n\n## Key Findings\n\nbody [1]\n\n"
        f"## {_ENRICHMENT_TITLE}\n\nA banked verified finding sentence. [2]\n\n"
        "## Bibliography\n\n[1] https://a\n[2] https://b\n",
        encoding="utf-8",
    )
    (tmp_path / "manifest.json").write_text(json.dumps({}), encoding="utf-8")
    assert assert_breadth_enrichment_rendered(_summary(tmp_path)) == "present"


def test_canary_fails_closed_on_box1_shape(tmp_path):
    # the box1 report: rich body, NO enrichment heading of ANY of the three forms
    (tmp_path / "report.md").write_text(
        "# Research report: q\n\n## Key Findings\n\nbody [1]\n\n## Methods\n\nm\n\n"
        "## Bibliography\n\n[1] https://a\n",
        encoding="utf-8",
    )
    (tmp_path / "manifest.json").write_text(
        json.dumps({"credibility_disclosed_gap": "credibility_pass_unavailable: wall"}),
        encoding="utf-8",
    )
    with pytest.raises(BreadthEnrichmentCanaryError):
        assert_breadth_enrichment_rendered(_summary(tmp_path))


# ── (5) phase-A budget cap: pool_wall_s bounds the join, priors-fill (drain-not-discard) ──────────


def test_phase_a_pool_wall_override_caps_and_priors_fills(monkeypatch):
    monkeypatch.setenv("PG_CREDIBILITY_JUDGE_CONCURRENCY", "2")

    def _slow_judge(question, payload):
        real_time.sleep(2.0)
        return {"reliability": 0.5, "relevance": 0.5, "rationale": "slow"}

    rows = [
        {"evidence_id": f"e{i}", "url": f"https://x/{i}", "tier": "T4", "authority_score": 0.4}
        for i in range(4)
    ]
    t0 = real_time.monotonic()
    out = _judge_rows_pooled("q", rows, None, _slow_judge, pool_wall_s=0.4)
    elapsed = real_time.monotonic() - t0
    assert len(out) == 4                       # KEEP-ALL: every row gets a judgment
    assert any(getattr(j, "judge_error", False) for j in out)  # capped rows priors-filled + labeled
    assert elapsed < 1.9                       # the caller's budget bound held (no 2s+ join)
