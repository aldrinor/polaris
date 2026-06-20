#!/usr/bin/env python3
"""I-arch-011 #1268 PR-c — behavioral replay harness for per-basket VERIFIED-COMPOSE.

Fail-loud (non-zero exit) acceptance for the CONTRACT (composition_design_plan.md PR-c):
per basket the writer drafts prose -> deterministic strict_verify each sentence against the
BASKET-SCOPED pool -> a passing sentence is kept; a FAILING sentence (incl. one citing ANOTHER
basket's evidence_id, the P1-2 anti-cross-claim case) FALLS BACK to THAT BASKET'S OWN verified
K-span; never empty.

THREE DISCRIMINATING FIXTURES (verbatim from the design):
  c1  the writer returns marker-less garbage (FORCED compose FAIL)  -> basket-1's OWN verbatim K-span.
  c2  the writer returns a faithful marker-bearing sentence (= c2's own span + ``[#ev:c2]``) -> PASSES,
      composed prose renders.
  c3  the writer returns c2's faithful sentence — content-faithful to the FOREIGN basket, citing
      ``[#ev:c2]`` (a FOREIGN id for basket-3). Under basket-3's BASKET-SCOPED pool (only c3's id)
      ``[#ev:c2]`` is ABSENT -> strict_verify REJECTS it -> basket-3 falls back to its OWN K-span.
      (If the compose pool were the FULL pool, the foreign sentence would PASS and basket-3 would
      render c2's foreign content — the exact P1-2 regression this fixture discriminates.)

The LLM writer is FAKE (injected); strict_verify is the REAL production single-sentence verifier
(``verify_sentence_provenance``). No network, no model spend, no relaxation.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

# strict_verify is the REAL gate; verified-compose is the production under test.
from src.polaris_graph.generator.provenance_generator import verify_sentence_provenance  # noqa: E402
from src.polaris_graph.generator.multi_section_generator import (  # noqa: E402
    _compose_section_per_basket,
    build_verified_span_draft,
)
from src.polaris_graph.synthesis.credibility_pass import (  # noqa: E402
    BasketMember,
    ClaimBasket,
    MEMBER_TIER_ENTAILMENT_VERIFIED,
    MEMBER_TIER_UNVERIFIED,
    _assemble_baskets,
)

# Deterministic verification only — keep the entailment judge OFF so this harness needs no model.
os.environ.pop("PG_STRICT_VERIFY_ENTAILMENT", None)

_C1_QUOTE = "Hydroelectric power supply reduces regional industrial emissions substantially."
_C2_QUOTE = "Renewable energy subsidies accelerated national solar deployment programs."
_C3_QUOTE = "Grid storage capacity expanded across the coastal provinces this decade."


def _member(eid: str, quote: str) -> BasketMember:
    return BasketMember(
        evidence_id=eid, source_url=f"https://example.org/{eid}", source_tier="T1",
        origin_cluster_id=f"o::{eid}", credibility_weight=0.9, authority_score=0.9,
        span=(0, len(quote)), direct_quote=quote, span_verdict="SUPPORTS",
        member_tier=MEMBER_TIER_ENTAILMENT_VERIFIED,
    )


def _basket(ccid: str, subject: str, quote: str, eid: str) -> ClaimBasket:
    return ClaimBasket(
        claim_cluster_id=ccid, claim_text=quote, subject=subject, predicate="finding",
        supporting_members=[_member(eid, quote)], refuter_cluster_ids=(), weight_mass=1.0,
        total_clustered_origin_count=1, verified_support_origin_count=1, basket_verdict="full",
    )


def _fail(case: str, detail: str) -> None:
    print(f"FAIL [{case}]: {detail}")
    sys.exit(1)


# ── ISSUE #1279 P1#1 — region/pool must EXCLUDE non-SUPPORTS members ─────────────────────────────────
#
# A basket intentionally KEEPS unsupported members (Principle 2: consolidate, never drop). The compose
# scoped pool + acceptance regions MUST be built from SUPPORTS-only members; if they admit an UNSUPPORTED
# member's evidence_id+span, a writer that cites that member renders unverified text AS verified. The
# fixture: a basket with one SUPPORTS member and one UNSUPPORTED member; the writer cites the UNSUPPORTED
# member's own (real-row-resolvable) span. EXPECTED (post-fix): the sentence is REJECTED (the unsupported
# member defines NO scoped-pool entry / acceptance region) and the basket falls back to its SUPPORTS
# K-span. RED (current code): the unsupported member is in the pool+region, so the sentence PASSES.
_P1_SUPPORTS_QUOTE = "Coastal wetland restoration increased measured carbon sequestration rates."
_P1_UNSUPPORTED_QUOTE = "An unrelated assertion about deep-sea mining royalty frameworks entirely."


def _p1_member(eid: str, quote: str, verdict: str, tier: str) -> BasketMember:
    return BasketMember(
        evidence_id=eid, source_url=f"https://example.org/{eid}", source_tier="T1",
        origin_cluster_id=f"o::{eid}", credibility_weight=0.9, authority_score=0.9,
        span=(0, len(quote)), direct_quote=quote, span_verdict=verdict, member_tier=tier,
    )


def _assert_p1_unsupported_member_excluded() -> None:
    """ISSUE #1279 P1#1: a writer that cites an UNSUPPORTED in-basket member must be REJECTED; the basket
    falls back to its SUPPORTS K-span. RED on the holed code (the unsupported member is pooled+regioned)."""
    eid_ok = "ev_p1_supports"
    eid_bad = "ev_p1_unsupported"
    basket = ClaimBasket(
        claim_cluster_id="p1c", claim_text=_P1_SUPPORTS_QUOTE, subject="wetland carbon", predicate="finding",
        # ORDER MATTERS: the UNSUPPORTED member is FIRST so a naive "use supporting_members[..]" path
        # would surface it; the SUPPORTS member is the only legitimate region/fallback source.
        supporting_members=[
            _p1_member(eid_bad, _P1_UNSUPPORTED_QUOTE, "UNSUPPORTED", MEMBER_TIER_UNVERIFIED),
            _p1_member(eid_ok, _P1_SUPPORTS_QUOTE, "SUPPORTS", MEMBER_TIER_ENTAILMENT_VERIFIED),
        ],
        refuter_cluster_ids=(), weight_mass=1.0, total_clustered_origin_count=2,
        verified_support_origin_count=1, basket_verdict="partial",
    )
    pool = {
        eid_ok: {"evidence_id": eid_ok, "direct_quote": _P1_SUPPORTS_QUOTE},
        eid_bad: {"evidence_id": eid_bad, "direct_quote": _P1_UNSUPPORTED_QUOTE},
    }

    def _writer_cite_unsupported(_basket, _scoped_pool) -> str:
        # The writer DRAFTS the unsupported member's own span, citing the unsupported member's own
        # (real-row-resolvable) offsets — it span-grounds against the global row but the member is
        # NOT a supporting source for the claim.
        return f"{_P1_UNSUPPORTED_QUOTE} [#ev:{eid_bad}:0-{len(_P1_UNSUPPORTED_QUOTE)}]"

    out = _compose_section_per_basket(
        [basket], pool, writer_fn=_writer_cite_unsupported, verify_fn=verify_sentence_provenance,
    )
    rendered = out[0]
    if eid_bad in rendered or _P1_UNSUPPORTED_QUOTE.rstrip(".") in rendered:
        _fail("p1_unsupported_member_rendered",
              f"P1#1 VIOLATION: the UNSUPPORTED member's span/id rendered as verified prose — the compose "
              f"scoped pool / acceptance region admitted a non-SUPPORTS member; got {rendered!r}")
    # It must fall back to the basket's OWN SUPPORTS K-span (the SUPPORTS member's span + id).
    if f"[#ev:{eid_ok}:" not in rendered or _P1_SUPPORTS_QUOTE.rstrip(".") not in rendered:
        _fail("p1_no_supports_fallback",
              f"P1#1: after rejecting the unsupported cite the basket must fall back to its SUPPORTS "
              f"K-span ({eid_ok}); got {rendered!r}")
    # Re-verify against the global pool (no token mis-anchoring downstream).
    import re as _re  # noqa: PLC0415
    for unit in [u for u in _re.split(r"(?<=\])\s+(?=[A-Z0-9])", rendered) if u.strip()]:
        gv = verify_sentence_provenance(unit, pool)
        if not bool(getattr(gv, "is_verified", False)):
            _fail("p1_global_resolve", f"P1#1 fallback unit does NOT re-verify globally: {unit!r}")


# ── ISSUE #1279 P1#2 — full-row direct_quote must NOT become a whole-row acceptance region ──────────
#
# The bug is in ``_assemble_baskets``: it sets ``BasketMember.direct_quote`` from ``_row_span_text(row)``
# (the FULL row), so ``_member_global_span`` recovers ``(0, len(row))`` and the acceptance region is the
# WHOLE row — a writer citing a DIFFERENT in-row claim's offsets passes the cross-claim region gate.
# This fixture DRIVES ``_assemble_baskets`` (NOT a hand-built member) so the production assembly is what
# is under test: a single row containing TWO claims; the AtomicClaim's ``text`` is the claim-LOCAL span.
# EXPECTED (post-fix): the assembled member's ``direct_quote`` is the claim-local span, the acceptance
# region is the claim-local offsets, and a writer citing the OTHER claim's offsets is REJECTED. RED
# (current code): ``direct_quote`` is the full row, so the cross-claim cite passes.
_P1B_OWN_CLAIM = "Reported aggregate employment impact remained small in the near term."
_P1B_OTHER_CLAIM = "Task automation potential is concentrated in routine cognitive occupations."
_P1B_FULL_ROW = f"{_P1B_OWN_CLAIM} {_P1B_OTHER_CLAIM}"


class _FakeGraph:
    """Minimal ClaimGraph stand-in for ``_assemble_baskets`` (reads .clusters/.claims/.edges only)."""

    def __init__(self, claims: list, clusters: dict, edges: list) -> None:
        self.claims = claims
        self.clusters = clusters
        self.edges = edges


def _assert_p1b_claim_local_region() -> None:
    """ISSUE #1279 P1#2: ``_assemble_baskets`` must set ``direct_quote`` to the claim-LOCAL span so the
    acceptance region is the claim-specific offsets — a cross-claim cite to the OTHER in-row claim is
    REJECTED. RED on the holed code (``direct_quote`` is the full row -> whole-row region)."""
    from src.polaris_graph.synthesis.claim_graph import AtomicClaim  # noqa: PLC0415

    eid = "ev_p1b_full"
    # The AtomicClaim carries the claim-LOCAL span (its ``text``) — a verbatim substring of the full row,
    # exactly as the production numeric/qualitative extractors populate ``context_snippet``.
    claim = AtomicClaim(
        evidence_id=eid, kind="qualitative", subject="employment impact", predicate="finding",
        normalized_key=("__test__", eid, "own"), text=_P1B_OWN_CLAIM,
        source_url=f"https://example.org/{eid}", source_tier="T1",
        claim_cluster_id="p1bc",
    )
    graph = _FakeGraph(claims=[claim], clusters={"p1bc": [0]}, edges=[])
    # The annotated (assembly-time) row text == the FULL row (both claims).
    annotated = [{"evidence_id": eid, "direct_quote": _P1B_FULL_ROW, "authority_score": 0.9,
                  "source_url": f"https://example.org/{eid}", "tier": "T1"}]
    baskets = _assemble_baskets(
        graph, [], annotated, {}, verify_fn=verify_sentence_provenance, max_inflight=1,
    )
    if not baskets:
        _fail("p1b_no_basket", "P1#2: _assemble_baskets produced no basket for the single-claim cluster")
    basket = baskets[0]
    members = list(getattr(basket, "supporting_members", None) or [])
    if not members:
        _fail("p1b_no_member", "P1#2: assembled basket has no members")
    member = members[0]
    # CORE P1#2 ASSERTION: the member's direct_quote is the CLAIM-LOCAL span, NOT the full row.
    if str(getattr(member, "direct_quote", "")) == _P1B_FULL_ROW:
        _fail("p1b_full_row_direct_quote",
              "P1#2 VIOLATION: BasketMember.direct_quote is the FULL row (both claims) — the acceptance "
              "region becomes the whole row, defeating the cross-claim gate. It must be the claim-local "
              f"span ({_P1B_OWN_CLAIM!r}); got {getattr(member, 'direct_quote', '')!r}")
    if str(getattr(member, "direct_quote", "")) != _P1B_OWN_CLAIM:
        _fail("p1b_not_claim_local",
              f"P1#2: BasketMember.direct_quote must be the claim-local span {_P1B_OWN_CLAIM!r}; "
              f"got {getattr(member, 'direct_quote', '')!r}")
    # BEHAVIORAL gate: the compose path's global pool is the FULL row; a writer citing the OTHER claim's
    # offsets (a real region of the shared row, but NOT this claim's region) must be REJECTED.
    pool = {eid: {"evidence_id": eid, "direct_quote": _P1B_FULL_ROW}}
    _other_start = _P1B_FULL_ROW.find(_P1B_OTHER_CLAIM)
    _other_off = (_other_start, _other_start + len(_P1B_OTHER_CLAIM))

    def _writer_cross_claim(_basket, _scoped_pool) -> str:
        # DRIFT to the OTHER in-row claim, citing its REAL offsets within the shared row.
        return f"{_P1B_OTHER_CLAIM} [#ev:{eid}:{_other_off[0]}-{_other_off[1]}]"

    out = _compose_section_per_basket(
        [basket], pool, writer_fn=_writer_cross_claim, verify_fn=verify_sentence_provenance,
    )
    rendered = out[0]
    if _P1B_OTHER_CLAIM.rstrip(".") in rendered:
        _fail("p1b_cross_claim_rendered",
              f"P1#2 VIOLATION: the OTHER in-row claim rendered as this basket's verified prose (the "
              f"whole-row acceptance region let a cross-claim cite pass); got {rendered!r}")
    # It must fall back to its OWN claim-local K-span.
    if _P1B_OWN_CLAIM.rstrip(".") not in rendered:
        _fail("p1b_no_own_fallback",
              f"P1#2: after rejecting the cross-claim cite the basket must fall back to its OWN claim-local "
              f"K-span ({_P1B_OWN_CLAIM!r}); got {rendered!r}")


def main() -> int:
    c1 = _basket("c1", "hydroelectric emissions", _C1_QUOTE, "ev_c1")
    c2 = _basket("c2", "renewable subsidies", _C2_QUOTE, "ev_c2")
    c3 = _basket("c3", "grid storage", _C3_QUOTE, "ev_c3")

    evidence_pool = {
        "ev_c1": {"evidence_id": "ev_c1", "direct_quote": _C1_QUOTE},
        "ev_c2": {"evidence_id": "ev_c2", "direct_quote": _C2_QUOTE},
        "ev_c3": {"evidence_id": "ev_c3", "direct_quote": _C3_QUOTE},
    }

    # The FAKE writer (the only injected part). c1 -> garbage (no token, must fail). c2 -> faithful.
    # c3 -> c2's faithful sentence (FOREIGN [#ev:c2]) — content-faithful to the foreign basket.
    def _writer(basket, scoped_pool) -> str:
        ccid = str(getattr(basket, "claim_cluster_id", ""))
        if ccid == "c1":
            return "An entirely unsupported assertion with no provenance token whatsoever."
        if ccid == "c2":
            return f"{_C2_QUOTE} [#ev:ev_c2:0-{len(_C2_QUOTE)}]"
        if ccid == "c3":
            # FOREIGN: c2's own verified sentence + c2's id (absent from c3's basket-scoped pool).
            return f"{_C2_QUOTE} [#ev:ev_c2:0-{len(_C2_QUOTE)}]"
        return ""

    results = _compose_section_per_basket(
        [c1, c2, c3], evidence_pool, writer_fn=_writer, verify_fn=verify_sentence_provenance,
    )
    if len(results) != 3:
        _fail("count", f"expected 3 composed baskets, got {len(results)}")
    r1, r2, r3 = results

    # Sanity: the verbatim fallbacks the contract refers to.
    k1 = build_verified_span_draft(c1, evidence_pool)
    k3 = build_verified_span_draft(c3, evidence_pool)
    if k1 is None or "ev_c1" not in k1 or k3 is None or "ev_c3" not in k3:
        _fail("kspan", f"verbatim K-span draft did not bind to the basket's own id: k1={k1!r} k3={k3!r}")

    # ── c1: FORCED compose-fail -> basket-1's OWN verbatim K-span (its quote + its own id). ──
    if "[#ev:ev_c1:" not in r1 or _C1_QUOTE.rstrip(".") not in r1:
        _fail("c1_own_kspan", f"c1 must fall back to its OWN verbatim K-span; got {r1!r}")
    if "ev_c2" in r1 or "ev_c3" in r1:
        _fail("c1_no_foreign", f"c1 fallback leaked a foreign basket id; got {r1!r}")

    # ── c2: faithful compose PASSES -> the composed sentence renders (c2's span + c2's id). ──
    if "[#ev:ev_c2:" not in r2 or _C2_QUOTE.rstrip(".") not in r2:
        _fail("c2_pass", f"c2's faithful composed sentence must render; got {r2!r}")

    # ── c3: P1-2 — foreign-cited compose REJECTED under the basket-scoped pool -> c3's OWN K-span. ──
    if "[#ev:ev_c2:" in r3:
        _fail("c3_p1_2", f"P1-2 VIOLATION: c3 rendered the FOREIGN [#ev:ev_c2] compose; got {r3!r}")
    if "[#ev:ev_c3:" not in r3 or _C3_QUOTE.rstrip(".") not in r3:
        _fail("c3_own_kspan", f"c3 must fall back to its OWN verbatim K-span after rejecting the foreign cite; got {r3!r}")

    # ── P1-1 HARDENING (Codex core-gate): the HARDER cross-claim case — a SHARED source backs two
    # baskets with DIFFERENT claim-specific spans. cluster_id_by_evidence is 1-to-many, so a naive
    # evidence_id-only scope would let basket C render basket B's claim citing the shared id (the id
    # IS in C's pool). The fix pins each scoped row to the MEMBER'S OWN span, so the cross-claim
    # sentence fails to ground -> C falls back to its OWN claim-specific span.
    _shared = "ev_shared"
    _b_span = "Tariff reductions lowered consumer electronics prices."
    _c_span = "Vaccine coverage rose among rural adolescent populations."
    _full = f"{_b_span} {_c_span}"                          # the GLOBAL source text (both claims)
    _b_off = (0, len(_b_span))
    _c_off = (len(_b_span) + 1, len(_full))

    def _shared_member(span_off, quote) -> BasketMember:
        return BasketMember(
            evidence_id=_shared, source_url="https://example.org/shared", source_tier="T1",
            origin_cluster_id="o::shared", credibility_weight=0.9, authority_score=0.9,
            span=span_off, direct_quote=quote, span_verdict="SUPPORTS",
            member_tier=MEMBER_TIER_ENTAILMENT_VERIFIED,
        )

    c_shared = ClaimBasket(
        claim_cluster_id="c_shared", claim_text=_c_span, subject="vaccines", predicate="finding",
        supporting_members=[_shared_member(_c_off, _c_span)], refuter_cluster_ids=(), weight_mass=1.0,
        total_clustered_origin_count=1, verified_support_origin_count=1, basket_verdict="full",
    )
    # The GLOBAL pool row is the FULL source text — its [_b_off] is B's claim, [_c_off] is C's.
    pool_shared = {_shared: {"evidence_id": _shared, "direct_quote": _full}}

    def _writer_cross(basket, scoped_pool) -> str:
        # c_shared's writer DRIFTS to B's claim, citing B's REGION of the shared source (it span-
        # grounds against the global row, but B's region is NOT c_shared's claim region).
        return f"{_b_span} [#ev:{_shared}:{_b_off[0]}-{_b_off[1]}]"

    out_shared = _compose_section_per_basket(
        [c_shared], pool_shared, writer_fn=_writer_cross, verify_fn=verify_sentence_provenance,
    )
    rc = out_shared[0]
    if _b_span.rstrip(".") in rc:
        _fail("p1_1_shared_source",
              f"P1-1 VIOLATION: basket c_shared rendered basket B's claim region of the SHARED id; got {rc!r}")
    if _c_span.rstrip(".") not in rc or f"[#ev:{_shared}:{_c_off[0]}-{_c_off[1]}]" not in rc:
        _fail("p1_1_shared_kspan",
              f"c_shared must fall back to its OWN claim region ({_c_off}) of the shared source; got {rc!r}")

    # ── GLOBAL RE-VERIFY (Codex core-gate P1-3): every emitted sentence must re-pass strict_verify
    # against the DOWNSTREAM (global) pool — proving the emitted tokens (composed re-anchor + verbatim
    # fallback offsets) resolve to the verified span globally, not just under the scoped pool. ──
    for tag, sent, pool in (("c1", r1, evidence_pool), ("c2", r2, evidence_pool),
                            ("c3", r3, evidence_pool), ("shared", rc, pool_shared)):
        for unit in [u for u in __import__("re").split(r"(?<=\])\s+(?=[A-Z0-9])", sent) if u.strip()]:
            gv = verify_sentence_provenance(unit, pool)
            if not bool(getattr(gv, "is_verified", False)):
                _fail("global_resolve",
                      f"{tag}: emitted sentence does NOT re-verify against the global pool "
                      f"(token mis-anchored downstream): {unit!r}")

    # ── ISSUE #1279 — the two P1 faithfulness-hole fixtures (RED on the holed code, GREEN post-fix). ──
    _assert_p1_unsupported_member_excluded()
    _assert_p1b_claim_local_region()

    print("PASS iarch011 PR-c verified-compose harness: "
          "c1 forced-fail -> OWN verbatim K-span (no foreign leak); "
          "c2 faithful compose PASSES strict_verify -> composed prose renders; "
          "c3 FOREIGN [#ev:c2] compose REJECTED under the basket-scoped pool (P1-2) -> c3's OWN K-span; "
          "SHARED-source cross-claim (basket cites a shared id for ANOTHER basket's claim) REJECTED via "
          "member-own-span scoping -> own claim-specific K-span (P1-1). "
          "ISSUE #1279 P1#1: an UNSUPPORTED in-basket member is EXCLUDED from the compose scoped pool + "
          "acceptance region (a writer citing it is REJECTED -> SUPPORTS K-span); "
          "ISSUE #1279 P1#2: _assemble_baskets binds direct_quote to the claim-LOCAL span (NOT the full "
          "row), so a cross-claim cite to another in-row claim is REJECTED -> own claim-local K-span. "
          "NEVER empty; strict_verify untouched (re-anchored sentence used); verbatim fallback basket-id-bound.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
