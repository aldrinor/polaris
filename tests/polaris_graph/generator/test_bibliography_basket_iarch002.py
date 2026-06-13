"""I-arch-002 [11] P5.2 — basket-carrying bibliography (design §6).

Proves the render contract for the bibliography/resolver row:

  * OFF (no basket args) emits the LEGACY ``{num,evidence_id,url,tier,statement}``
    dict BYTE-IDENTICAL — even when ``PG_SWEEP_CREDIBILITY_REDESIGN=1`` is set
    (the gate is PARAMETER PRESENCE, not an env read, so the render layer is not
    coupled to global flag state). §8 #13 (OFF byte-identical).
  * ON (baskets + the evidence_id->cluster binding supplied) carries the whole
    basket per row: supporting sources + weights + N VERIFIED independent origins,
    with a contested basket REFERENCING the both_sides neutral block via
    ``refuter_cluster_ids``. §8 #18 (operator-visible emit carries verified count
    + basket).
  * A member with no verified span is surfaced as UNSUPPORTED (context), never
    silently counted as support; the basket label is the upstream-computed one and
    no render path can resurrect a strict_verify-dropped sentence. §8 #11.

The basket types are imported from ``credibility_pass`` (not redefined) so this
test also pins that the render layer and the assembly layer share the SAME field
names — the checklist's cross-file shared-type consistency requirement.

The faithfulness engine (strict_verify / provenance / NLI / 4-role) is NOT
exercised or altered here: this is a pure render-layer projection of an
already-assembled basket.
"""
from __future__ import annotations

from src.polaris_graph.generator.provenance_generator import (
    resolve_provenance_to_citations,
    verify_sentence_provenance,
)
from src.polaris_graph.synthesis.credibility_pass import (
    BASKET_VERDICT_CONTESTED,
    BASKET_VERDICT_FULL,
    BASKET_VERDICT_PARTIAL,
    BasketMember,
    ClaimBasket,
)


# ── shared fixtures ───────────────────────────────────────────────────────────


def _evidence_pool() -> dict:
    return {
        "ev_a": {
            "direct_quote": "Reported value was 14.9% here.",
            "statement": "A statement.",
            "source_url": "https://a/",
            "tier": "T1",
        },
        "ev_b": {
            "direct_quote": "Observed value was 17.4% here.",
            "statement": "B statement.",
            "source_url": "https://b/",
            "tier": "T2",
        },
    }


def _kept_two_sentences(pool: dict) -> list:
    # Spans cover number AND >=2 content words (mirrors the existing
    # test_resolve_to_citations_produces_numbered_markers fixture).
    kept = [
        verify_sentence_provenance(
            "Reported value was 14.9% here [#ev:ev_a:0-29].", pool,
        ),
        verify_sentence_provenance(
            "Observed value was 17.4% here [#ev:ev_b:0-29].", pool,
        ),
    ]
    assert all(sv.is_verified for sv in kept)
    return kept


_LEGACY_KEYS = {"num", "evidence_id", "url", "tier", "statement"}


def _legacy_row(num: int, ev_id: str, url: str, tier: str, statement: str) -> dict:
    return {
        "num": num,
        "evidence_id": ev_id,
        "url": url,
        "tier": tier,
        "statement": statement,
    }


# ── OFF byte-identity (§8 #13) ────────────────────────────────────────────────


def test_off_bibliography_is_byte_identical_to_legacy() -> None:
    """No basket args -> the EXACT legacy 5-key dicts, value-for-value."""
    pool = _evidence_pool()
    kept = _kept_two_sentences(pool)

    text, biblio = resolve_provenance_to_citations(kept, pool)

    assert len(biblio) == 2
    # exact-equality, not just key-presence: the dict must equal the legacy literal.
    assert biblio[0] == _legacy_row(1, "ev_a", "https://a/", "T1", "A statement.")
    assert biblio[1] == _legacy_row(2, "ev_b", "https://b/", "T2", "B statement.")
    # and no basket key leaked onto the OFF path.
    assert set(biblio[0].keys()) == _LEGACY_KEYS
    assert set(biblio[1].keys()) == _LEGACY_KEYS
    # rendered prose still has the numbered markers, tokens stripped.
    assert "[1]" in text and "[2]" in text
    assert "[#ev:" not in text


def test_off_byte_identical_even_with_master_flag_set(monkeypatch) -> None:
    """Gate is PARAMETER presence, not the env flag: setting
    PG_SWEEP_CREDIBILITY_REDESIGN=1 but passing no baskets MUST still emit the
    legacy dict byte-identical. This proves the render layer is uncoupled from
    global flag state (the advisor's param-gating proof)."""
    monkeypatch.setenv("PG_SWEEP_CREDIBILITY_REDESIGN", "1")
    pool = _evidence_pool()
    kept = _kept_two_sentences(pool)

    _text, biblio = resolve_provenance_to_citations(kept, pool)

    assert biblio[0] == _legacy_row(1, "ev_a", "https://a/", "T1", "A statement.")
    assert biblio[1] == _legacy_row(2, "ev_b", "https://b/", "T2", "B statement.")
    assert set(biblio[0].keys()) == _LEGACY_KEYS


def test_off_when_only_one_basket_arg_supplied_stays_legacy() -> None:
    """Both basket params are required to activate; one without the other (an
    incomplete wiring) MUST NOT half-emit — stays legacy byte-identical."""
    pool = _evidence_pool()
    kept = _kept_two_sentences(pool)

    # baskets present but no binding
    _t1, b1 = resolve_provenance_to_citations(kept, pool, baskets=[])
    assert set(b1[0].keys()) == _LEGACY_KEYS
    # binding present but no baskets
    _t2, b2 = resolve_provenance_to_citations(
        kept, pool, cluster_id_by_evidence={"ev_a": ["c1"]},
    )
    assert set(b2[0].keys()) == _LEGACY_KEYS


# ── ON: carries basket weights + verified count (§8 #18) ──────────────────────


def _full_basket() -> ClaimBasket:
    """A 2-member basket, both members verified alone -> verified count 2, full."""
    return ClaimBasket(
        claim_cluster_id="c_full",
        claim_text="Reported value was 14.9%.",
        subject="intervention",
        predicate="weight loss",
        supporting_members=[
            BasketMember(
                evidence_id="ev_a",
                source_url="https://a/",
                source_tier="T1",
                origin_cluster_id="origin::ev_a",
                credibility_weight=0.91,
                authority_score=0.8,
                span=(0, 29),
                direct_quote="Reported value was 14.9% here.",
                span_verdict="SUPPORTS",
            ),
            BasketMember(
                evidence_id="ev_b",
                source_url="https://b/",
                source_tier="T2",
                origin_cluster_id="origin::ev_b",
                credibility_weight=0.74,
                authority_score=0.6,
                span=(0, 29),
                direct_quote="Observed value was 17.4% here.",
                span_verdict="SUPPORTS",
            ),
        ],
        refuter_cluster_ids=(),
        weight_mass=1.4,
        total_clustered_origin_count=2,
        verified_support_origin_count=2,
        basket_verdict=BASKET_VERDICT_FULL,
    )


def test_on_bibliography_carries_basket_weights_and_verified_count() -> None:
    pool = _evidence_pool()
    kept = _kept_two_sentences(pool)
    basket = _full_basket()
    # both cited evidence_ids map to the same (full) basket cluster.
    binding = {"ev_a": ["c_full"], "ev_b": ["c_full"]}

    _text, biblio = resolve_provenance_to_citations(
        kept, pool, baskets=[basket], cluster_id_by_evidence=binding,
    )

    # legacy fields still present + unchanged.
    assert biblio[0]["num"] == 1 and biblio[0]["evidence_id"] == "ev_a"
    assert biblio[0]["statement"] == "A statement."
    # NEW: baskets key carried.
    assert "baskets" in biblio[0]
    rows_baskets = biblio[0]["baskets"]
    assert len(rows_baskets) == 1
    b = rows_baskets[0]
    # the ONLY strengthening count is the VERIFIED count, not the clustered total.
    assert b["verified_support_origin_count"] == 2
    assert b["total_clustered_origin_count"] == 2
    assert b["basket_verdict"] == BASKET_VERDICT_FULL
    assert b["weight_mass"] == 1.4
    assert b["claim_cluster_id"] == "c_full"
    # per-member weights surfaced, each with its OWN isolated span verdict.
    members = b["supporting_members"]
    assert len(members) == 2
    assert {m["evidence_id"] for m in members} == {"ev_a", "ev_b"}
    m_a = next(m for m in members if m["evidence_id"] == "ev_a")
    assert m_a["credibility_weight"] == 0.91
    assert m_a["authority_score"] == 0.8
    assert m_a["source_tier"] == "T1"
    assert m_a["span_verdict"] == "SUPPORTS"
    # contested-reference is empty for a full basket.
    assert b["refuter_cluster_ids"] == ()


def test_on_member_without_verified_span_shown_unsupported_not_counted() -> None:
    """A member with no verified span is surfaced as UNSUPPORTED (context), and
    the basket carries a partial verdict + an honest verified count of 1 — never
    silently full. §8 #11 (no render upgrade of an unverified member)."""
    pool = _evidence_pool()
    kept = _kept_two_sentences(pool)
    basket = _full_basket()
    # downgrade member ev_b to UNSUPPORTED; upstream assembly would then have
    # counted only 1 verified origin and labelled the basket partial.
    basket.supporting_members[1].span_verdict = "UNSUPPORTED"
    basket.verified_support_origin_count = 1
    basket.basket_verdict = BASKET_VERDICT_PARTIAL
    binding = {"ev_a": ["c_full"], "ev_b": ["c_full"]}

    _text, biblio = resolve_provenance_to_citations(
        kept, pool, baskets=[basket], cluster_id_by_evidence=binding,
    )

    b = biblio[0]["baskets"][0]
    assert b["verified_support_origin_count"] == 1  # the UNSUPPORTED member NOT counted
    assert b["basket_verdict"] == BASKET_VERDICT_PARTIAL  # never silently full
    m_b = next(m for m in b["supporting_members"] if m["evidence_id"] == "ev_b")
    assert m_b["span_verdict"] == "UNSUPPORTED"


# ── ON: contested basket references the both_sides block ──────────────────────


def test_on_contested_basket_carries_refuter_reference() -> None:
    pool = _evidence_pool()
    kept = _kept_two_sentences(pool)
    contested = ClaimBasket(
        claim_cluster_id="c_contested",
        claim_text="Reported value was 14.9%.",
        subject="intervention",
        predicate="weight loss",
        supporting_members=[
            BasketMember(
                evidence_id="ev_a",
                source_url="https://a/",
                source_tier="T1",
                origin_cluster_id="origin::ev_a",
                credibility_weight=0.9,
                authority_score=0.8,
                span=(0, 29),
                direct_quote="Reported value was 14.9% here.",
                span_verdict="SUPPORTS",
            ),
        ],
        # REFERENCE to the contradicting cluster(s) — the both_sides neutral block.
        refuter_cluster_ids=("c_refuter_1", "c_refuter_2"),
        weight_mass=0.9,
        total_clustered_origin_count=1,
        verified_support_origin_count=1,
        basket_verdict=BASKET_VERDICT_CONTESTED,
    )
    binding = {"ev_a": ["c_contested"]}

    _text, biblio = resolve_provenance_to_citations(
        kept, pool, baskets=[contested], cluster_id_by_evidence=binding,
    )

    b = biblio[0]["baskets"][0]
    assert b["basket_verdict"] == BASKET_VERDICT_CONTESTED
    # refuters REFERENCED (cluster ids), not duplicated into the basket.
    assert b["refuter_cluster_ids"] == ("c_refuter_1", "c_refuter_2")


# ── ON: 1-to-many binding ─────────────────────────────────────────────────────


def test_on_one_evidence_id_maps_to_multiple_baskets() -> None:
    """The evidence_id -> claim_cluster_id binding is 1-to-MANY: one source can
    back several baskets. The row must surface ALL of them (design §5 per-cluster
    rule), not just one."""
    pool = _evidence_pool()
    kept = _kept_two_sentences(pool)
    b_full = _full_basket()
    b_full.claim_cluster_id = "c1"
    for m in b_full.supporting_members:
        pass  # members unchanged
    b_two = ClaimBasket(
        claim_cluster_id="c2",
        claim_text="A second distinct claim from the same source.",
        subject="intervention",
        predicate="other outcome",
        supporting_members=[
            BasketMember(
                evidence_id="ev_a",
                source_url="https://a/",
                source_tier="T1",
                origin_cluster_id="origin::ev_a",
                credibility_weight=0.5,
                authority_score=0.8,
                span=(0, 10),
                direct_quote="Reported v",
                span_verdict="SUPPORTS",
            ),
        ],
        refuter_cluster_ids=(),
        weight_mass=0.8,
        total_clustered_origin_count=1,
        verified_support_origin_count=1,
        basket_verdict=BASKET_VERDICT_FULL,
    )
    # ev_a backs BOTH baskets c1 and c2.
    binding = {"ev_a": ["c1", "c2"], "ev_b": ["c1"]}

    _text, biblio = resolve_provenance_to_citations(
        kept, pool, baskets=[b_full, b_two], cluster_id_by_evidence=binding,
    )

    row_a = next(r for r in biblio if r["evidence_id"] == "ev_a")
    cluster_ids = {b["claim_cluster_id"] for b in row_a["baskets"]}
    assert cluster_ids == {"c1", "c2"}


def test_on_evidence_id_with_no_basket_gets_empty_basket_list() -> None:
    """A cited source not present in the binding (or whose clusters aren't in the
    basket list) still gets the legacy fields + an empty baskets list — never a
    KeyError, never a missing key under the ON path."""
    pool = _evidence_pool()
    kept = _kept_two_sentences(pool)
    basket = _full_basket()
    basket.claim_cluster_id = "c_only_a"
    basket.supporting_members = [basket.supporting_members[0]]  # ev_a only
    binding = {"ev_a": ["c_only_a"]}  # ev_b absent from the binding

    _text, biblio = resolve_provenance_to_citations(
        kept, pool, baskets=[basket], cluster_id_by_evidence=binding,
    )

    row_b = next(r for r in biblio if r["evidence_id"] == "ev_b")
    assert row_b["baskets"] == []  # present, empty, no crash
    assert row_b["statement"] == "B statement."  # legacy fields intact
