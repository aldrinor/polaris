"""I-arch-007 BREADTH — RESOLVER-side generic multi-citation (item 1, prove-only).

Owner: ``src/polaris_graph/generator/provenance_generator.py`` (the legacy
resolver path). The design
(``outputs/audits/iarch007_death_forensic/breadth_fix/BREADTH_FIX_DESIGN.md``
§1.1 + §1.2) records that the whole-basket inline multi-citation render is
ALREADY WIRED and faithful in the live tree:

  * ``build_basket_supports_by_cluster`` (provenance_generator.py:2932) — the
    SUPPORTS-only cluster index.
  * ``verified_corroborators_for_tokens`` (provenance_generator.py:2961) — the
    shared anti-cross-claim core (single-cluster expands; multi-cluster skips;
    member must resolve in ``evidence_pool``).
  * the resolver append loop (provenance_generator.py:3246-3251) — adds each
    OTHER independently span-verified (SUPPORTS) member as an EXTRA citation.

Per design §1.2 ("No code change in item 1 beyond the test"), this fix is
TEST-ONLY: the resolver-side multi-citation is not re-implemented (doing so
would be fake-working, LAW II, and would collide with the committed death-fix).
This module is ADDITIVE to ``test_lane_section_arch005.py`` (which proves the
B6/B8 keystone through the full ``resolve_provenance_to_citations_with_count``
path). Here we:

  1. DIRECT-unit the two module helpers the existing suite only hits indirectly.
  2. STRENGTHEN the ">1 verified member" case to TWO corroborators (3 inline
     markers) so we prove "the WHOLE basket", not just "one extra".
  3. Re-pin the negatives at the helper level: a non-SUPPORTS member is never
     surfaced; a cross-cluster (multi-cluster, ambiguous) token never expands;
     a member absent from ``evidence_pool`` is excluded; the OFF / baskets-absent
     path returns ``[]`` so the resolver render is byte-identical.

FAITHFULNESS (constraint 1, §-1.1 "citation appropriate for the claim"): every
surfaced corroborator is a member whose OWN isolated ``span_verdict == "SUPPORTS"``
in the sentence's SINGLE unambiguous cluster, resolvable in ``evidence_pool``.
No strict_verify / NLI / 4-role / span-grounding / section floor / sentinel is
touched; no citation is invented; no new textual claim is generated. The
baskets-absent path is byte-identical.
"""
from __future__ import annotations

import pytest

from src.polaris_graph.generator.provenance_generator import (
    build_basket_supports_by_cluster,
    resolve_provenance_to_citations,
    resolve_provenance_to_citations_with_count,
    verified_corroborators_for_tokens,
    verify_sentence_provenance,
)
from src.polaris_graph.synthesis.credibility_pass import (
    BASKET_VERDICT_FULL,
    BasketMember,
    ClaimBasket,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures — a four-source pool with a 3-SUPPORTS cluster so the strengthened
# "whole basket" (two corroborators -> three inline markers) case is exercisable.
# ─────────────────────────────────────────────────────────────────────────────


def _pool_four() -> dict:
    """ev_a/ev_b/ev_d all carry the SAME verifiable value (one claim, three
    independent origins); ev_c is an UNSUPPORTED context line."""
    return {
        "ev_a": {
            "direct_quote": "Reported value was 14.9% here.",
            "statement": "A statement about the value.",
            "source_url": "https://a/",
            "tier": "T1",
        },
        "ev_b": {
            "direct_quote": "Confirmed value was 14.9% too.",
            "statement": "B statement about the value.",
            "source_url": "https://b/",
            "tier": "T2",
        },
        "ev_d": {
            "direct_quote": "Independently the value was 14.9% as well.",
            "statement": "D statement about the value.",
            "source_url": "https://d/",
            "tier": "T1",
        },
        "ev_c": {
            "direct_quote": "A different unverified context line.",
            "statement": "C statement.",
            "source_url": "https://c/",
            "tier": "T5",
        },
    }


def _one_cited_sentence(pool: dict) -> list:
    """A single verified sentence that cites ONLY ev_a (real provenance token,
    built via verify_sentence_provenance — not a hand-faked SentenceVerification)."""
    kept = [
        verify_sentence_provenance(
            "Reported value was 14.9% here [#ev:ev_a:0-29].", pool,
        ),
    ]
    assert all(sv.is_verified for sv in kept), "fixture sentence must verify"
    return kept


def _member(eid: str, url: str, tier: str, quote: str, verdict: str) -> BasketMember:
    return BasketMember(
        evidence_id=eid, source_url=url, source_tier=tier,
        origin_cluster_id=f"o::{eid}", credibility_weight=0.7, authority_score=0.6,
        span=(0, len(quote)), direct_quote=quote, span_verdict=verdict,
    )


def _basket_c1_three_supports() -> ClaimBasket:
    """Cluster c1 with THREE SUPPORTS members (ev_a, ev_b, ev_d) + one UNSUPPORTED
    member (ev_c). verified_support_origin_count = 3 (NOT the clustered total 4)."""
    members = [
        _member("ev_a", "https://a/", "T1", "Reported value was 14.9% here.", "SUPPORTS"),
        _member("ev_b", "https://b/", "T2", "Confirmed value was 14.9% too.", "SUPPORTS"),
        _member("ev_d", "https://d/", "T1", "Independently the value was 14.9% as well.", "SUPPORTS"),
        _member("ev_c", "https://c/", "T5", "A different unverified context line.", "UNSUPPORTED"),
    ]
    return ClaimBasket(
        claim_cluster_id="c1",
        claim_text="Reported value was 14.9%.",
        subject="intervention", predicate="outcome",
        supporting_members=members,
        refuter_cluster_ids=(),
        weight_mass=2.6,
        total_clustered_origin_count=4,           # ADVISORY — must NEVER render
        verified_support_origin_count=3,
        basket_verdict=BASKET_VERDICT_FULL,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 1. DIRECT unit — build_basket_supports_by_cluster: SUPPORTS-only filter.
# ─────────────────────────────────────────────────────────────────────────────


def test_supports_index_keeps_only_supports_members() -> None:
    """The cluster index keeps ONLY members whose OWN span_verdict == 'SUPPORTS'
    (the verified_support_origin_count members), never the advisory clustered
    total. The UNSUPPORTED member ev_c is dropped from the index entirely."""
    from src.polaris_graph.generator.provenance_generator import _basket_for_biblio

    projected = {"c1": _basket_for_biblio(_basket_c1_three_supports())}
    index = build_basket_supports_by_cluster(projected)

    assert index == {"c1": ["ev_a", "ev_b", "ev_d"]}, (
        "SUPPORTS-only: the 3 verified origins index, the UNSUPPORTED ev_c does not"
    )
    assert "ev_c" not in index.get("c1", []), "an UNSUPPORTED member must never index"


def test_supports_index_skips_cluster_with_no_supports() -> None:
    """A cluster whose every member is UNSUPPORTED contributes NO index entry (so it
    can never surface an inline corroborator)."""
    from src.polaris_graph.generator.provenance_generator import _basket_for_biblio

    b = _basket_c1_three_supports()
    for m in b.supporting_members:
        m.span_verdict = "UNSUPPORTED"
    b.verified_support_origin_count = 0
    projected = {"c1": _basket_for_biblio(b)}

    assert build_basket_supports_by_cluster(projected) == {}, (
        "a cluster with zero SUPPORTS members must not appear in the index"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 2. DIRECT unit — verified_corroborators_for_tokens: the anti-cross-claim core.
# ─────────────────────────────────────────────────────────────────────────────


def test_core_single_cluster_token_surfaces_all_other_supports() -> None:
    """A sentence token that maps to EXACTLY ONE cluster surfaces every OTHER
    SUPPORTS member of that cluster (the whole basket), each resolvable in the pool."""
    pool = _pool_four()
    index = {"c1": ["ev_a", "ev_b", "ev_d"]}
    binding = {"ev_a": ["c1"], "ev_b": ["c1"], "ev_d": ["c1"]}

    corro = verified_corroborators_for_tokens(
        ["ev_a"],
        basket_supports_by_cluster=index,
        cluster_id_by_evidence=binding,
        evidence_pool=pool,
    )
    # The two OTHER SUPPORTS members surface (ev_a is the sentence's own token; the
    # resolver dedups it against used_nums, so the core may legitimately include it —
    # what matters is ev_b AND ev_d are present and ev_c is absent).
    assert "ev_b" in corro and "ev_d" in corro, "whole basket: BOTH corroborators surface"
    assert "ev_c" not in corro, "an UNSUPPORTED member is not in the SUPPORTS index"


def test_core_multi_cluster_token_never_expands_cross_claim() -> None:
    """FAITHFULNESS (§-1.1): a token whose evidence_id maps to MULTIPLE clusters is
    AMBIGUOUS (which claim does the sentence assert?), so it expands NOTHING — a
    different cluster's verified member is never attached to this sentence's claim.
    This is the guard at provenance_generator.py:3000-3001, asserted directly."""
    pool = _pool_four()
    # ev_a backs c1 (value) AND c2 (a DIFFERENT claim whose verified member is ev_c).
    index = {"c1": ["ev_a", "ev_b"], "c2": ["ev_c"]}
    binding = {"ev_a": ["c1", "c2"], "ev_b": ["c1"], "ev_c": ["c2"]}

    corro = verified_corroborators_for_tokens(
        ["ev_a"],
        basket_supports_by_cluster=index,
        cluster_id_by_evidence=binding,
        evidence_pool=pool,
    )
    assert corro == [], (
        "a multi-cluster (ambiguous) token must expand NO corroborator — "
        "c2's verified member ev_c must never attach to a c1 sentence"
    )


def test_core_excludes_member_absent_from_pool() -> None:
    """A SUPPORTS member that does NOT resolve in evidence_pool is excluded (it cannot
    be rendered as a real numbered citation, so it is never surfaced)."""
    pool = _pool_four()
    del pool["ev_d"]  # ev_d is a SUPPORTS member but no longer in the pool
    index = {"c1": ["ev_a", "ev_b", "ev_d"]}
    binding = {"ev_a": ["c1"]}

    corro = verified_corroborators_for_tokens(
        ["ev_a"],
        basket_supports_by_cluster=index,
        cluster_id_by_evidence=binding,
        evidence_pool=pool,
    )
    assert "ev_d" not in corro, "a member absent from evidence_pool must be excluded"
    assert "ev_b" in corro, "an in-pool SUPPORTS member still surfaces"


def test_core_empty_index_returns_empty_off_path() -> None:
    """The OFF / no-basket path: an empty SUPPORTS index returns [] (so the resolver
    render is byte-identical legacy single-citation)."""
    assert verified_corroborators_for_tokens(
        ["ev_a"],
        basket_supports_by_cluster={},
        cluster_id_by_evidence={"ev_a": ["c1"]},
        evidence_pool=_pool_four(),
    ) == [], "empty index -> [] -> byte-identical OFF path"


# ─────────────────────────────────────────────────────────────────────────────
# 3. STRENGTHENED end-to-end — the WHOLE basket (TWO corroborators -> 3 markers).
#    This is the case the existing suite does NOT cover (it tests 1 corroborator).
# ─────────────────────────────────────────────────────────────────────────────


def test_resolver_renders_whole_basket_three_markers() -> None:
    """The headline of item 1: a sentence the generator cited via ONE source (ev_a)
    renders ALL THREE independently span-verified members of its cluster inline —
    ev_a + the TWO corroborators ev_b and ev_d — i.e. the WHOLE basket, not just one
    extra. The UNSUPPORTED ev_c is NOT rendered. The advisory clustered total (4) is
    never materialized (no [4] marker)."""
    pool = _pool_four()
    kept = _one_cited_sentence(pool)
    basket = _basket_c1_three_supports()
    binding = {"ev_a": ["c1"], "ev_b": ["c1"], "ev_d": ["c1"], "ev_c": ["c1"]}

    text, biblio, emitted = resolve_provenance_to_citations_with_count(
        kept, pool, baskets=[basket], cluster_id_by_evidence=binding,
    )

    assert emitted == 1
    biblio_ids = {r["evidence_id"] for r in biblio}
    assert biblio_ids == {"ev_a", "ev_b", "ev_d"}, (
        "the WHOLE basket of SUPPORTS members renders; ev_c (UNSUPPORTED) does not"
    )
    # Exactly THREE inline markers ([1][2][3]); never the 4th (advisory clustered) member.
    assert "[1]" in text and "[2]" in text and "[3]" in text, (
        f"the whole 3-member basket must render three inline markers; got: {text!r}"
    )
    assert "[4]" not in text, "the advisory clustered count must never become a 4th marker"


# ─────────────────────────────────────────────────────────────────────────────
# 4. NEGATIVES / OFF — re-pinned at the resolver boundary (additive controls).
# ─────────────────────────────────────────────────────────────────────────────


def test_resolver_off_path_byte_identical() -> None:
    """No basket args -> byte-identical legacy single-citation render. The OFF path is
    the safety net: until Gate-B passes baskets, the resolver is unchanged."""
    pool = _pool_four()
    kept = _one_cited_sentence(pool)

    text_off, biblio_off = resolve_provenance_to_citations(kept, pool)

    assert {r["evidence_id"] for r in biblio_off} == {"ev_a"}, "OFF: only the cited source"
    assert "[1]" in text_off and "[2]" not in text_off, "OFF: exactly one inline citation"
    assert set(biblio_off[0].keys()) == {"num", "evidence_id", "url", "tier", "statement"}, (
        "OFF: the legacy 5-key bibliography row, byte-identical"
    )


def test_resolver_one_param_absent_stays_legacy() -> None:
    """Param-presence gate: baskets without binding (or binding without baskets) must
    NOT half-render corroborators — a single missing param keeps the legacy render."""
    pool = _pool_four()
    kept = _one_cited_sentence(pool)
    basket = _basket_c1_three_supports()

    _t1, b1, _ = resolve_provenance_to_citations_with_count(kept, pool, baskets=[basket])
    assert {r["evidence_id"] for r in b1} == {"ev_a"}, "no binding -> legacy single citation"

    _t2, b2, _ = resolve_provenance_to_citations_with_count(
        kept, pool, cluster_id_by_evidence={"ev_a": ["c1"]},
    )
    assert {r["evidence_id"] for r in b2} == {"ev_a"}, "no baskets -> legacy single citation"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
