#!/usr/bin/env python3
"""I-arch-010 PR1a behavioral replay-harness — the NO-LEAK proof (§-1.4, FAIL LOUD).

Acceptance for PR1a is BEHAVIORAL: the no-leak effect must ACTUALLY APPEAR in the real
classification + assembly output, not "Codex approved the diff" and not "tests are green"
(CLAUDE.md §-1.4). This harness drives the PRODUCTION classifier + the REAL basket
assembly (``credibility_pass._assemble_baskets``) through a deterministic fake
``verify_fn`` (the same ``verify_fn`` seam ``_verify_member_in_isolation`` injects), and
FAILS LOUD (non-zero exit) if any case's effect did not fire.

Injection mechanism (per the design plan): the fake ``verify_fn`` returns a
``SentenceVerification``-shaped result with a CHOSEN ``is_verified`` / ``judge_error`` /
``failure_reasons`` for each evidence_id. That result flows the REAL path
``verify_fn -> _verify_member_in_isolation -> _classify_member_tier`` AND the REAL
``_assemble_baskets`` reassembly, so the harness exercises the production classification +
no-leak count logic, NOT a mock of it.

Codex-REQUIRED cases:
  * CASE A (P1-1 deterministic-NEUTRAL): a member that PASSES the deterministic (a)-(e)
    engine but whose entailment verdict is NEUTRAL -> NOT counted in
    ``verified_support_origin_count``, NOT render-eligible (``span_verdict == "UNSUPPORTED"``),
    ``member_tier == "DETERMINISTIC_ONLY"`` (grounded-but-weak, I-arch-011-surfaceable).
  * CASE B (P1-1 judge_error / Leak-1): a member whose entailment judge ERRORS (transport
    sentinel) while ``is_verified == True`` (FIX-1 keeps it on the deterministic checks) ->
    NOT counted, NOT render-eligible (``span_verdict == "UNSUPPORTED"``),
    ``member_tier == "DETERMINISTIC_ONLY"``. The Leak-1 closure proof: the ``judge_error``
    BOOL, not ``is_verified``, gates the count.
  * CASE 4b (tier-distinction): a member whose OWN span FAILS the deterministic (a)-(e)
    engine -> ``member_tier == "UNVERIFIED"`` (DISTINCT from DETERMINISTIC_ONLY) so
    I-arch-011 never surfaces deterministic garbage as a weak candidate.
  * CASE positive (non-vacuous control): a genuinely ENTAILED member (is_verified, no
    judge_error) -> COUNTED, render-eligible (``span_verdict == "SUPPORTS"``),
    ``member_tier == "ENTAILMENT_VERIFIED"``. Proves the fixture CAN count a member, so the
    A/B/4b exclusions are real.

Run: ``python scripts/iarch010_replay_breadth_faithfulness_harness.py`` -> exit 0 if every
case fires, non-zero + the failing case/member on any miss.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

# Make the repo root importable so the harness runs standalone (§-1.4: run directly, not
# only under pytest). scripts/ is one level under the repo root.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.polaris_graph.generator.provenance_generator import _basket_for_biblio
from src.polaris_graph.synthesis.credibility_pass import (
    MEMBER_TIER_DETERMINISTIC_ONLY,
    MEMBER_TIER_ENTAILMENT_VERIFIED,
    MEMBER_TIER_UNVERIFIED,
    _assemble_baskets,
)

# A span that deterministically PASSES (a)-(e) for the positive/A/B members and a claim
# text whose number + content words appear in it. The DETERMINISTIC pass/fail is driven by
# the fake verify_fn below, so these strings only need to be non-empty + stable.
_GOOD_SPAN = "Tirzepatide lowered HbA1c by 2.3 percentage points in the SURPASS trial."
_GOOD_CLAIM = "Tirzepatide lowered HbA1c by 2.3 points."


@dataclass
class _FakeSentenceVerification:
    """The minimal shape ``_classify_member_tier`` reads off the verify result."""

    is_verified: bool
    judge_error: bool = False
    failure_reasons: list = field(default_factory=list)


# evidence_id -> the verify result the fake verify_fn returns for that member. This is the
# ONLY place each case's verdict is chosen; everything downstream is production code.
_VERDICT_BY_EID: dict[str, _FakeSentenceVerification] = {
    # CASE positive — genuine ENTAILED: passes (a)-(e), judge ran clean.
    "ev_positive": _FakeSentenceVerification(is_verified=True, judge_error=False),
    # CASE A — deterministic-PASS but entailment NEUTRAL: is_verified=False with ONLY an
    # entailment_failed failure reason (the (a)-(e) engine passed; only the judge dropped).
    "ev_case_a": _FakeSentenceVerification(
        is_verified=False,
        judge_error=False,
        failure_reasons=["entailment_failed:ev_case_a:verdict=NEUTRAL:reason=injected"],
    ),
    # CASE B — judge_error / Leak-1: is_verified=True (FIX-1 keeps it on (a)-(e)) AND
    # judge_error=True (the transport sentinel). Must NOT count/render.
    "ev_case_b": _FakeSentenceVerification(is_verified=True, judge_error=True),
    # CASE 4b — deterministic GARBAGE: is_verified=False with a NON-entailment failure
    # reason (the member's own span fails (a)-(e): missing number / content-overlap).
    "ev_case_4b": _FakeSentenceVerification(
        is_verified=False,
        judge_error=False,
        failure_reasons=["content_overlap_below_min:ev_case_4b"],
    ),
}


def _fake_verify_fn(sentence: str, pool: dict):
    """The injected verifier: returns the chosen result for the single pooled member.

    ``_verify_member_in_isolation`` builds a one-token sentence + a single-member pool, so
    ``pool`` has exactly one evidence_id — we key the chosen verdict off it.
    """
    eids = list(pool.keys())
    if len(eids) != 1:
        raise AssertionError(
            f"harness invariant broken: isolation pool must have exactly 1 member, got {eids!r}"
        )
    eid = eids[0]
    if eid not in _VERDICT_BY_EID:
        raise AssertionError(f"harness has no chosen verdict for evidence_id {eid!r}")
    return _VERDICT_BY_EID[eid]


def _build_inputs():
    """One claim cluster ``c_case`` with FOUR members (positive / A / B / 4b), each its own
    origin so a counted member increments ``verified_support_origin_count`` distinctly.

    Returns ``(graph, weight_mass, annotated, credibility_by_evidence)`` in the shape
    ``_assemble_baskets`` consumes (duck-typed SimpleNamespace claims/graph)."""
    eids = ["ev_positive", "ev_case_a", "ev_case_b", "ev_case_4b"]
    # Each claim is a duck-typed object with .text / .evidence_id / .source_url / .source_tier.
    claims = [
        SimpleNamespace(
            text=_GOOD_CLAIM,
            evidence_id=eid,
            source_url=f"https://{eid}/",
            source_tier="T1",
        )
        for eid in eids
    ]
    # graph: .clusters maps cluster_id -> [claim indices]; .claims is the flat list;
    # .edges is empty (no refuters).
    graph = SimpleNamespace(
        clusters={"c_case": list(range(len(eids)))},
        claims=claims,
        edges=[],
    )
    # weight_mass: one ClaimWeightMass-shaped object per cluster (advisory count only).
    weight_mass = [
        SimpleNamespace(claim_cluster_id="c_case", independent_origin_count=len(eids))
    ]
    # annotated rows: each carries the member's own span (direct_quote) the verifier reads.
    annotated = [
        {"evidence_id": eid, "direct_quote": _GOOD_SPAN, "authority_score": 0.9}
        for eid in eids
    ]
    # credibility_by_evidence: each member maps to its OWN distinct origin cluster so a
    # counted member is a distinct verified origin.
    credibility_by_evidence = {
        eid: SimpleNamespace(origin_cluster_id=f"o::{eid}", credibility_weight=0.9)
        for eid in eids
    }
    return graph, weight_mass, annotated, credibility_by_evidence


def _fail(case: str, detail: str) -> None:
    print(f"FAIL [{case}]: {detail}", file=sys.stderr)
    sys.exit(1)


def main() -> int:
    graph, weight_mass, annotated, cred = _build_inputs()
    baskets = _assemble_baskets(
        graph, weight_mass, annotated, cred, verify_fn=_fake_verify_fn, max_inflight=1,
    )
    if len(baskets) != 1:
        _fail("setup", f"expected exactly 1 basket, got {len(baskets)}")
    basket = baskets[0]
    members = {m.evidence_id: m for m in basket.supporting_members}
    expected_eids = {"ev_positive", "ev_case_a", "ev_case_b", "ev_case_4b"}
    if set(members) != expected_eids:
        _fail("setup", f"member eids {set(members)!r} != expected {expected_eids!r}")

    # ── per-member tier + span_verdict assertions (the production classifier output) ──
    expected = {
        "ev_positive": ("SUPPORTS", MEMBER_TIER_ENTAILMENT_VERIFIED),
        "ev_case_a": ("UNSUPPORTED", MEMBER_TIER_DETERMINISTIC_ONLY),
        "ev_case_b": ("UNSUPPORTED", MEMBER_TIER_DETERMINISTIC_ONLY),
        "ev_case_4b": ("UNSUPPORTED", MEMBER_TIER_UNVERIFIED),
    }
    for eid, (want_sv, want_tier) in expected.items():
        m = members[eid]
        if m.span_verdict != want_sv:
            _fail(eid, f"span_verdict {m.span_verdict!r} != expected {want_sv!r}")
        if m.member_tier != want_tier:
            _fail(eid, f"member_tier {m.member_tier!r} != expected {want_tier!r}")

    # ── binding invariant: span_verdict=="SUPPORTS" IFF member_tier==ENTAILMENT_VERIFIED ──
    for eid, m in members.items():
        sv_supports = m.span_verdict == "SUPPORTS"
        tier_entailed = m.member_tier == MEMBER_TIER_ENTAILMENT_VERIFIED
        if sv_supports != tier_entailed:
            _fail(
                eid,
                "binding invariant broken: span_verdict=='SUPPORTS' "
                f"({sv_supports}) != member_tier=='ENTAILMENT_VERIFIED' ({tier_entailed})",
            )

    # ── NO-LEAK assembly proof: only the genuine ENTAILED member is counted ──
    # verified_support_origin_count counts DISTINCT verified origins; exactly one member
    # (ev_positive) is genuine ENTAILED, so it must be 1 — A/B/4b leaked NOTHING.
    if basket.verified_support_origin_count != 1:
        _fail(
            "no_leak_count",
            "verified_support_origin_count must be 1 (only ev_positive genuine ENTAILED); "
            f"got {basket.verified_support_origin_count} — a non-entailed member LEAKED into the count",
        )

    # ── render-eligibility proof via the biblio projection (the render/count consumers) ──
    # build_basket_supports_by_cluster keys on span_verdict=="SUPPORTS"; the projection
    # carries both span_verdict and member_tier. Assert ONLY ev_positive is render-eligible
    # and member_tier is faithfully projected for the I-arch-011 seam.
    proj = _basket_for_biblio(basket)
    proj_members = {mm["evidence_id"]: mm for mm in proj["supporting_members"]}
    render_eligible = {
        eid for eid, mm in proj_members.items()
        if str(mm.get("span_verdict") or "").upper() == "SUPPORTS"
    }
    if render_eligible != {"ev_positive"}:
        _fail(
            "no_leak_render",
            f"render-eligible (span_verdict==SUPPORTS) members {render_eligible!r} "
            "!= {'ev_positive'} — a non-entailed member is render-eligible (LEAK)",
        )
    for eid, (_, want_tier) in expected.items():
        got_tier = str(proj_members[eid].get("member_tier") or "")
        if got_tier != want_tier:
            _fail(
                "biblio_projection",
                f"{eid}: projected member_tier {got_tier!r} != expected {want_tier!r} "
                "(I-arch-011 seam not carried through the projection)",
            )

    print(
        "PASS iarch010 PR1a no-leak harness: "
        "CASE A (deterministic-NEUTRAL) NOT counted/rendered, member_tier=DETERMINISTIC_ONLY; "
        "CASE B (judge_error) NOT counted/rendered, member_tier=DETERMINISTIC_ONLY; "
        "CASE 4b (deterministic-garbage) member_tier=UNVERIFIED (distinct); "
        "positive ENTAILED counted=1, render-eligible={ev_positive}; "
        "binding invariant held; biblio projection carries member_tier."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
