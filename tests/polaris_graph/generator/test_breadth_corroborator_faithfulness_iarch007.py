"""I-arch-007 BREADTH FIX — contract-path corroborator FAITHFULNESS guard (net-new control).

Owner: ``src/polaris_graph/generator/contract_section_runner.py`` (the V30 contract path
Gate-B forces via ``PG_V30_PHASE2_ENABLED=1``).

## Why this file exists (scope, per BREADTH_FIX_DESIGN.md §1.2 + §4)

The inline whole-basket multi-citation render on the contract path is ALREADY wired and
faithful (``contract_section_runner.py:1276-1280`` threads the baskets into
``resolve_provenance_to_citations``; ``:1364-1372`` appends every same-cluster SUPPORTS
corroborator via the shared ``verified_corroborators_for_tokens`` core). That wiring landed
in commit ``a8b6ea3f`` (#1257) + the FIX-1 PART-B chain and is proven by
``test_lane_section_arch005_contract_path.py`` (multi-citation, uncited-corroborator,
anti-cross-claim, OFF byte-identical, UNSUPPORTED-member-excluded). NO production edit is
needed for item 1, and item 3 (attaching DIFFERENT-cluster / non-contract sources as
corroborators) is deliberately NOT implemented — it is blocked by the hard contract-entity
wall at ``contract_section_runner.py:963-966`` and would relax the anti-cross-claim rule
(§-1.1 lethal; the Codex scope-lock at ``contract_section_runner.py:386-397`` records this
as out-of-bounds). The 437 unbound sources are surfaced by the SEPARATE enrichment path
(``weighted_enrichment.py`` + ``multi_section_generator.py``), whose ``_run_section``
strict_verify negative controls (numeric-mismatch / content-overlap) belong to THAT owner's
``test_breadth_enrichment_iarch007.py`` — NOT here (the contract deterministic stream is
verbatim-by-construction, so those drafts cannot even be constructed on this path).

## The net-new faithfulness control this file adds

The one corroborator-surfacing guard NOT yet covered on the live contract path is the
``_support_eid in evidence_pool`` exclusion at ``provenance_generator.py:3003``: a basket
member with ``span_verdict == "SUPPORTS"`` in the SAME cluster as a cited token, but with NO
resolvable row in ``evidence_pool``, must NEVER surface as an inline ``[N]`` corroborator and
must NEVER enter the bibliography. A member with no pool row has no real source to attribute
to — surfacing it would be a fabricated citation. ``build_basket_supports_by_cluster``
(``provenance_generator.py:2948-2958``) DOES include such a member in the per-cluster SUPPORTS
index (it keys only on ``span_verdict``), so the pool-resolution filter is the load-bearing
guard — and it is exercised here on the REAL ``run_contract_section`` slot-regroup, not in
isolation.

A POSITIVE companion (a real in-pool same-cluster SUPPORTS member DOES surface) is asserted in
the SAME run so the negative result is non-vacuous: the fixture provably CAN render a
corroborator, and the phantom is excluded specifically because it is absent from the pool.

The LLM is injected (fake); ``strict_verify`` + the citation rewriter are REAL (the live-sweep
components). No network, no model spend. The harness is imported from
``test_lane_section_arch005_contract_path`` so there is a single source of truth for the
contract-path driver.
"""
from __future__ import annotations

import pytest

from src.polaris_graph.synthesis.credibility_pass import (
    BASKET_VERDICT_FULL,
    BasketMember,
    ClaimBasket,
    CredibilityAnalysis,
)

# Single source of truth for the REAL contract-path harness (driver + fixtures).
from tests.polaris_graph.generator.test_lane_section_arch005_contract_path import (  # noqa: E501
    _ENDPOINT_SPAN,
    _build_contract_inputs,
    _covering_cred,
    _member,
    _num_for_evidence,
    _run,
    _slot_body_for,
    clinical_template,  # noqa: F401 — re-exported pytest fixture
)


# ─────────────────────────────────────────────────────────────────────────────
# NET-NEW FAITHFULNESS CONTROL: a same-cluster SUPPORTS member ABSENT from
# evidence_pool must NOT surface as an inline corroborator (provenance:3003 guard),
# while a same-cluster SUPPORTS member PRESENT in the pool DOES — proving the
# exclusion is the pool-resolution filter, not an artifact of the fixture.
# ─────────────────────────────────────────────────────────────────────────────


_PHANTOM_EID = "phantom_supports_not_in_pool"


@pytest.mark.asyncio
async def test_contract_path_supports_member_absent_from_pool_never_surfaces(clinical_template):
    """One claim cluster ``c_pool`` has THREE SUPPORTS members:

      * ``surpass_1_primary`` — in the pool, has its OWN cited sentence (the anchor);
      * ``surpass_2_primary`` — in the pool, SUPPORTS (the POSITIVE companion: it MUST
        surface inline on surpass_1's sentence, so the negative result below is non-vacuous);
      * ``phantom_supports_not_in_pool`` — SUPPORTS for the SAME cluster, but NEVER registered
        into ``evidence_pool`` (no real source row).

    The phantom is in ``build_basket_supports_by_cluster``'s index (it keys only on
    ``span_verdict``), so the ONLY thing keeping it out of the rendered report is the
    ``_support_eid in evidence_pool`` filter at ``provenance_generator.py:3003``. This test
    drives the REAL ``run_contract_section`` and asserts the phantom appears NOWHERE — not in
    the biblio, not inline — while the in-pool corroborator surfaces normally. Zero fabricated
    additions: a SUPPORTS verdict alone never licenses a citation to a non-existent source.
    """
    plan, pool = _build_contract_inputs(clinical_template)
    assert {"surpass_1_primary", "surpass_2_primary"} <= set(pool)
    # The phantom is DELIBERATELY absent from the evidence_pool (it is in the basket only).
    assert _PHANTOM_EID not in pool

    phantom_member = BasketMember(
        evidence_id=_PHANTOM_EID,
        source_url=f"https://{_PHANTOM_EID}/",
        source_tier="T1",
        origin_cluster_id=f"o::{_PHANTOM_EID}",
        credibility_weight=0.9,          # high WEIGHT — weight never overrides the pool gate
        authority_score=0.9,
        span=(0, len(_ENDPOINT_SPAN)),
        direct_quote=_ENDPOINT_SPAN,
        span_verdict="SUPPORTS",         # SUPPORTS — yet still must NOT surface (no pool row)
    )
    members = [
        _member("surpass_1_primary", "SUPPORTS"),
        _member("surpass_2_primary", "SUPPORTS"),   # in-pool corroborator — POSITIVE companion
        phantom_member,                              # SUPPORTS but absent from the pool
    ]
    basket = ClaimBasket(
        claim_cluster_id="c_pool",
        claim_text="endpoint claim",
        subject="trial",
        predicate="endpoint",
        supporting_members=members,
        refuter_cluster_ids=(),
        weight_mass=2.4,
        total_clustered_origin_count=3,   # ADVISORY — must NEVER render
        verified_support_origin_count=3,
        basket_verdict=BASKET_VERDICT_FULL,
    )
    binding = {
        "surpass_1_primary": ["c_pool"],
        "surpass_2_primary": ["c_pool"],
        _PHANTOM_EID: ["c_pool"],
    }
    analysis = CredibilityAnalysis(
        credibility_by_evidence=_covering_cred(pool),
        origin_by_evidence={e: f"o::{e}" for e in pool},
        claims=[], edges=[], weight_mass=[],
        baskets=[basket], cluster_id_by_evidence=binding,
    )

    result = await _run(plan, pool, analysis)
    text = result.verified_text
    biblio = result.biblio_slice

    n1 = _num_for_evidence(biblio, "surpass_1_primary")
    n2 = _num_for_evidence(biblio, "surpass_2_primary")
    assert n1 is not None, "surpass_1 must be numbered (it has its own cited sentence)"

    body1 = _slot_body_for(text, f"[{n1}]")
    assert body1, "could not locate the surpass_1 slot body"

    # POSITIVE companion: the in-pool same-cluster SUPPORTS member DOES surface inline —
    # so the fixture provably CAN render a corroborator, making the negative below meaningful.
    assert n2 is not None, "the in-pool corroborator must be numbered into the biblio"
    assert f"[{n2}]" in body1, (
        "the in-pool same-cluster SUPPORTS corroborator must render inline (non-vacuous "
        f"control); body:\n{body1!r}"
    )

    # NET-NEW NEGATIVE CONTROL: the phantom — SUPPORTS, same cluster, ABSENT from the pool —
    # must NEVER be numbered into the bibliography (no real source to cite).
    assert _num_for_evidence(biblio, _PHANTOM_EID) is None, (
        "FAITHFULNESS FAIL: a SUPPORTS basket member with NO evidence_pool row was numbered "
        "into the contract biblio — the provenance:3003 pool-resolution guard was bypassed."
    )
    # ... and must NEVER appear inline anywhere in the verified text (id or any marker).
    assert _PHANTOM_EID not in text, (
        "the phantom corroborator's evidence_id leaked into the rendered verified_text"
    )


@pytest.mark.asyncio
async def test_contract_path_pool_absent_member_does_not_change_render(clinical_template):
    """Adjacency/determinism guard: adding the pool-absent phantom SUPPORTS member to the
    basket must leave the rendered ``verified_text`` BYTE-IDENTICAL to a run WITHOUT it. The
    phantom is silently filtered at ``provenance:3003``, so it can neither add nor perturb a
    single citation — proving the guard is a clean exclusion (no renumbering side effect, no
    'fabricated addition' however subtle)."""
    # Run A — basket has ONLY the two real in-pool SUPPORTS members.
    plan_a, pool_a = _build_contract_inputs(clinical_template)
    basket_a = ClaimBasket(
        claim_cluster_id="c_pool", claim_text="endpoint claim",
        subject="trial", predicate="endpoint",
        supporting_members=[
            _member("surpass_1_primary", "SUPPORTS"),
            _member("surpass_2_primary", "SUPPORTS"),
        ],
        refuter_cluster_ids=(), weight_mass=1.6,
        total_clustered_origin_count=2, verified_support_origin_count=2,
        basket_verdict=BASKET_VERDICT_FULL,
    )
    binding_a = {"surpass_1_primary": ["c_pool"], "surpass_2_primary": ["c_pool"]}
    analysis_a = CredibilityAnalysis(
        credibility_by_evidence=_covering_cred(pool_a),
        origin_by_evidence={e: f"o::{e}" for e in pool_a},
        claims=[], edges=[], weight_mass=[],
        baskets=[basket_a], cluster_id_by_evidence=binding_a,
    )
    result_a = await _run(plan_a, pool_a, analysis_a)

    # Run B — SAME basket plus the pool-absent phantom SUPPORTS member + its binding.
    plan_b, pool_b = _build_contract_inputs(clinical_template)
    phantom_member = BasketMember(
        evidence_id=_PHANTOM_EID, source_url=f"https://{_PHANTOM_EID}/", source_tier="T1",
        origin_cluster_id=f"o::{_PHANTOM_EID}", credibility_weight=0.9, authority_score=0.9,
        span=(0, len(_ENDPOINT_SPAN)), direct_quote=_ENDPOINT_SPAN, span_verdict="SUPPORTS",
    )
    basket_b = ClaimBasket(
        claim_cluster_id="c_pool", claim_text="endpoint claim",
        subject="trial", predicate="endpoint",
        supporting_members=[
            _member("surpass_1_primary", "SUPPORTS"),
            _member("surpass_2_primary", "SUPPORTS"),
            phantom_member,
        ],
        refuter_cluster_ids=(), weight_mass=2.4,
        total_clustered_origin_count=3, verified_support_origin_count=3,
        basket_verdict=BASKET_VERDICT_FULL,
    )
    binding_b = {
        "surpass_1_primary": ["c_pool"],
        "surpass_2_primary": ["c_pool"],
        _PHANTOM_EID: ["c_pool"],
    }
    analysis_b = CredibilityAnalysis(
        credibility_by_evidence=_covering_cred(pool_b),
        origin_by_evidence={e: f"o::{e}" for e in pool_b},
        claims=[], edges=[], weight_mass=[],
        baskets=[basket_b], cluster_id_by_evidence=binding_b,
    )
    result_b = await _run(plan_b, pool_b, analysis_b)

    assert result_a.verified_text == result_b.verified_text, (
        "a pool-absent SUPPORTS member must be a no-op: the rendered verified_text changed "
        "when an unresolvable corroborator was added to the basket (provenance:3003 must be a "
        "clean exclusion with no renumbering / fabricated-addition side effect)."
    )
