"""§8 mechanical-proof tests for the Wave-3 per-claim ClaimBasket (I-arch-002 [8] + [7]).

Pure CPU: no network, no LLM, no spend. Exercises the basket-assembly path in
``credibility_pass.py`` (design §5/§6) + the activated main-path domain threading
(P3.1, design §7 FIX-5). The faithfulness engine (``verify_sentence_provenance`` /
strict_verify) is the REAL production callable, used ADVISORY only — never re-run as
a gate, never mocked (CLAUDE.md §9.4: no unittest.mock, no mocked evidence DB).

Test ids map to design §8:
  #14 union-laundering END-TO-END: a basket whose span-union would pass but one member
      fails ALONE -> verified_support_origin_count == 1, not 2 (the isolation property).
  #11 basket_verdict=full cannot resurrect a strict_verify-dropped sentence (LABEL only).
  #22 activated main-path consolidation: with the REAL query domain threaded, two
      all-known equal clinical atoms MERGE (basket of 2) while an unknown-domain atom
      stays a SINGLETON — proves consolidation is live on the production path AND
      fail-closed on unknown domain at once.

The merge key is the SOLE defence against over-merge (strict_verify is basket-blind,
design §0); the basket's verified count is the SOLE strengthening signal and it is
computed by ISOLATED per-member verification so a union can never launder a member
that fails alone.
"""
from __future__ import annotations

import pytest

from src.polaris_graph.retrieval.contradiction_detector import ExtractedNumericClaim
from src.polaris_graph.generator.provenance_generator import (
    SentenceVerification,
    verify_sentence_provenance,
)
from src.polaris_graph.synthesis.claim_graph import build_claim_graph, extract_atomic_claims
from src.polaris_graph.synthesis.credibility_pass import (
    BASKET_VERDICT_FULL,
    BASKET_VERDICT_PARTIAL,
    BasketMember,
    ClaimBasket,
    EvidenceCredibility,
    _assemble_baskets,
)
from src.polaris_graph.synthesis.weight_mass import aggregate_weight_mass


@pytest.fixture(autouse=True)
def _offline_and_redesign_on(monkeypatch):
    """Force the entailment/verification judges OFF (so verify_sentence_provenance is
    fully deterministic + offline) and turn the redesign master flag ON (so the claim
    graph builds the spec-driven merge keys the consolidation needs)."""
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "off")
    monkeypatch.setenv("PG_VERIFICATION_MODE", "off")
    monkeypatch.setenv("PG_SWEEP_CREDIBILITY_REDESIGN", "1")


# ── shared builders ───────────────────────────────────────────────────────────


def _all_known_numeric(evidence_id, *, value=14.9, **overrides):
    """A fully-positively-known clinical ExtractedNumericClaim — every discriminator
    set so two such claims merge (a singleton would defeat the basket tests). The
    ``context_snippet`` carries the claim TEXT the basket verifies in isolation."""
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
    """A per-row numeric extractor (matches extract_numeric_claims' (rows, domain)
    shape) that returns the pre-built all-known claim for each row's evidence_id."""

    def extractor(rows, domain=None):
        out = []
        for r in rows:
            eid = str(r.get("evidence_id", ""))
            if eid in claims_by_eid:
                out.append(claims_by_eid[eid])
        return out

    return extractor


def _no_qual_extractor(rows, domain=None):
    """A qualitative extractor that yields nothing — keeps the graph numeric-only so
    the basket under test is exactly the numeric cluster."""
    return []


def _annotated_rows(specs):
    """Evidence rows already carrying Phase-4 origin annotation (distinct origin per
    row + each its own canonical) so weight_mass + the basket see distinct origins."""
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
    """A credibility_by_evidence map (eid -> EvidenceCredibility) carrying each row's
    distinct origin_cluster_id so the basket counts DISTINCT verified origins."""
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


def _build_basket(claims_by_eid, rows):
    """Run the REAL basket-assembly path: build a real claim graph (numeric-only,
    injected all-known extractor so the two rows cluster), a real weight_mass, then
    _assemble_baskets with the REAL production verifier."""
    graph = build_claim_graph(
        rows,
        domain="clinical",
        numeric_extractor=_fake_numeric_extractor(claims_by_eid),
        qualitative_extractor=_no_qual_extractor,
    )
    # post-P3 judgments stand in via the credibility map's weights; weight_mass only
    # needs evidence_id + credibility_weight, so a tiny shim is enough.
    judgments = [
        type("J", (), {"evidence_id": r["evidence_id"], "credibility_weight": 0.8})()
        for r in rows
    ]
    weight_mass = aggregate_weight_mass(graph.claims, rows, judgments)
    baskets = _assemble_baskets(
        graph, weight_mass, rows, _credibility_map(rows),
        verify_fn=verify_sentence_provenance,
    )
    return graph, baskets


# ── §8 test #14: union-laundering END-TO-END ─────────────────────────────────


def test_14_union_laundering_member_failing_alone_counts_once():
    """#14: two sources cluster into ONE basket carrying the SAME claim ("14.9%
    weight loss"). Member A's own span CONTAINS '14.9'; member B's own span does NOT
    (it carries a different value, 22.5). A multi-citation UNION would find '14.9' in
    A's span and pass both; ISOLATED per-member verification verifies each member
    against ITS OWN single span, so B fails ALONE.

    The basket therefore reports verified_support_origin_count == 1 (only A's origin),
    NOT 2 — the union-laundering trap is defeated end-to-end through the real
    credibility_pass basket-assembly path (design §0/§5 FIX-3)."""
    claims_by_eid = {
        "evA": _all_known_numeric("evA", value=14.9),
        "evB": _all_known_numeric("evB", value=14.9),  # SAME merge key -> same basket
    }
    rows = _annotated_rows([
        # A's span supports the 14.9% claim text.
        ("evA", "Semaglutide achieved 14.9% weight loss at week 68 in the trial.", 0.9),
        # B's span is about a DIFFERENT value (22.5) — it does NOT contain 14.9, so
        # B fails strict_verify ALONE even though A's span would launder it in a union.
        ("evB", "Tirzepatide achieved 22.5% weight loss at week 72 in the trial.", 0.8),
    ])

    # POSITIVE HALF (the trap is REAL): a multi-citation UNION sentence citing BOTH
    # spans DOES pass strict_verify — A's span carries '14.9', so the verifier's
    # per-token union loop finds the decimal + content overlap across the two tokens.
    # This is exactly the laundering the isolated count must defeat.
    span_a = rows[0]["direct_quote"]
    span_b = rows[1]["direct_quote"]
    union_sentence = (
        "Semaglutide achieved 14.9% weight loss "
        f"[#ev:evA:0-{len(span_a)}][#ev:evB:0-{len(span_b)}]"
    )
    union_pool = {"evA": rows[0], "evB": rows[1]}
    union_result = verify_sentence_provenance(union_sentence, union_pool)
    assert union_result.is_verified is True, (
        "precondition: the two-token UNION passes (the laundering trap is real) — "
        "only isolation defeats it"
    )

    graph, baskets = _build_basket(claims_by_eid, rows)

    # The two all-known-equal claims clustered into ONE basket of two members.
    assert len(baskets) == 1, f"expected one merged basket, got {len(baskets)}"
    basket = baskets[0]
    assert len(basket.supporting_members) == 2, "CONSOLIDATE: both sources kept"

    # ISOLATED verification: A SUPPORTS on its own span, B is UNSUPPORTED alone.
    verdicts = {m.evidence_id: m.span_verdict for m in basket.supporting_members}
    assert verdicts["evA"] == "SUPPORTS", "A's own span contains 14.9 -> SUPPORTS"
    assert verdicts["evB"] == "UNSUPPORTED", "B's own span lacks 14.9 -> fails ALONE"

    # The anti-laundering invariant: distinct VERIFIED origins == 1, never 2.
    assert basket.verified_support_origin_count == 1, (
        "a member failing alone must NOT be counted via the union (union-laundering)"
    )
    # The clustered advisory count is a SEPARATE field and must NOT be reused as the
    # strengthening count (it is the not-verified count from weight_mass).
    assert basket.total_clustered_origin_count == 2, (
        "advisory clustered count is the full multi-attribution (NOT the verified count)"
    )
    # not-all-verified -> partial (and no refuter here).
    assert basket.basket_verdict == BASKET_VERDICT_PARTIAL


def test_14_both_members_verify_alone_count_is_two():
    """Control for #14: when BOTH members' own spans support the claim, isolated
    verification counts TWO distinct origins (consolidation strengthens honestly when
    the corroboration is real) and the verdict is full."""
    claims_by_eid = {
        "evA": _all_known_numeric("evA", value=14.9),
        "evB": _all_known_numeric("evB", value=14.9),
    }
    rows = _annotated_rows([
        ("evA", "Semaglutide achieved 14.9% weight loss at week 68 in the trial.", 0.9),
        ("evB", "A second cohort also showed 14.9% weight loss with semaglutide.", 0.8),
    ])
    _graph, baskets = _build_basket(claims_by_eid, rows)
    assert len(baskets) == 1
    basket = baskets[0]
    assert all(m.span_verdict == "SUPPORTS" for m in basket.supporting_members)
    assert basket.verified_support_origin_count == 2, "two real corroborating origins"
    assert basket.basket_verdict == BASKET_VERDICT_FULL


# ── §8 test #11: basket_verdict=full cannot resurrect a dropped sentence ───────


def test_11_basket_verdict_full_does_not_resurrect_a_dropped_sentence():
    """#11: basket_verdict is a LABEL, never a verification authority (design §6). A
    strict_verify-dropped SentenceVerification must stay dropped even when the SAME
    claim's basket is labelled `full`.

    The load-bearing proof is a CONSTRUCTION GUARANTEE: the basket-assembly path READS
    verification output (each member's isolated span verdict) but the ClaimBasket /
    BasketMember types carry NO is_verified field and NO SentenceVerification handle —
    so the assembly has, by construction, no path to flip a sentence's faithfulness
    verdict. A label cannot resurrect what it cannot write."""
    # Precondition: a real dropped sentence exists (no provenance token -> dropped).
    dropped_sv = verify_sentence_provenance(
        "Semaglutide achieved 14.9% weight loss.", {}, require_number_match=True,
    )
    assert dropped_sv.is_verified is False, "precondition: the sentence is dropped"

    # Build a real `full` basket for the same claim (both members support alone).
    claims_by_eid = {
        "evA": _all_known_numeric("evA", value=14.9),
        "evB": _all_known_numeric("evB", value=14.9),
    }
    rows = _annotated_rows([
        ("evA", "Semaglutide achieved 14.9% weight loss at week 68 in the trial.", 0.9),
        ("evB", "A second cohort also showed 14.9% weight loss with semaglutide.", 0.8),
    ])
    _graph, baskets = _build_basket(claims_by_eid, rows)
    assert baskets[0].basket_verdict == BASKET_VERDICT_FULL

    # CONSTRUCTION GUARANTEE: neither the ClaimBasket nor any BasketMember exposes an
    # is_verified attribute or a SentenceVerification handle. The `full` label is a
    # pure string describing the members' isolated verdicts; there is no field the
    # assembly could write to upgrade a strict_verify-dropped sentence. The dropped
    # SV is an independent object the basket never references, so it is structurally
    # impossible for `full` to resurrect it.
    assert not hasattr(baskets[0], "is_verified")
    assert not hasattr(baskets[0], "verifications")
    assert all(
        not hasattr(m, "is_verified") for m in baskets[0].supporting_members
    ), "BasketMember carries only an advisory span_verdict, never is_verified"


def test_11_unverified_basket_label_is_advisory_not_a_drop_gate():
    """A basket whose members all FAIL alone is labelled `unverified` (not `full`) —
    but that label likewise only DESCRIBES, it never forces a drop on any sentence
    (there is no sentence handle on the basket to drop)."""
    claims_by_eid = {
        "evA": _all_known_numeric("evA", value=14.9),
        "evB": _all_known_numeric("evB", value=14.9),
    }
    # Neither span contains 14.9 -> both members fail alone.
    rows = _annotated_rows([
        ("evA", "Tirzepatide achieved 22.5% weight loss at week 72.", 0.9),
        ("evB", "Liraglutide achieved 8.0% weight loss at week 56.", 0.8),
    ])
    _graph, baskets = _build_basket(claims_by_eid, rows)
    assert baskets[0].verified_support_origin_count == 0
    assert baskets[0].basket_verdict == "unverified"


# ── §8 test #22: activated main-path consolidation (real domain threaded) ──────


def test_22_real_domain_threaded_consolidates_equal_clinical_atoms():
    """#22: with the REAL query domain threaded (domain='clinical', as P3.1 wires),
    two all-known EQUAL clinical numeric atoms MERGE into ONE cluster (consolidation
    is LIVE on the production path). The same two atoms with NO domain ('' -> UNKNOWN)
    SINGLETON via the fail-closed dispatch (consolidation is correctly INERT-and-safe
    when the domain is unknown). This proves P3.1's threading is what activates
    consolidation, and that it is fail-closed at once."""
    rows = [
        {"evidence_id": "e1", "direct_quote": "Semaglutide achieved 14.9% weight loss.",
         "source_url": "https://e1.org", "tier": "T1"},
        {"evidence_id": "e2", "direct_quote": "Semaglutide achieved 14.9% weight loss.",
         "source_url": "https://e2.org", "tier": "T1"},
    ]
    claims_by_eid = {
        "e1": _all_known_numeric("e1", value=14.9),
        "e2": _all_known_numeric("e2", value=14.9),
    }
    num = _fake_numeric_extractor(claims_by_eid)

    # domain THREADED -> the two equal clinical atoms share one cluster id.
    clinical = extract_atomic_claims(
        rows, domain="clinical", numeric_extractor=num,
        qualitative_extractor=_no_qual_extractor,
    )
    clinical_numeric = [c for c in clinical if c.kind == "numeric"]
    assert len(clinical_numeric) == 2, "both rows must yield a numeric atom"
    assert all(c.domain == "clinical" for c in clinical_numeric), "domain stamped"
    assert clinical_numeric[0].normalized_key == clinical_numeric[1].normalized_key, (
        "all-known equal clinical atoms must share one merge key (consolidation LIVE)"
    )

    # domain UNSET -> UNKNOWN -> fail-closed dispatch -> each atom singletons.
    unknown = extract_atomic_claims(
        rows, domain="", numeric_extractor=num,
        qualitative_extractor=_no_qual_extractor,
    )
    unknown_numeric = [c for c in unknown if c.kind == "numeric"]
    assert len(unknown_numeric) == 2
    assert unknown_numeric[0].normalized_key != unknown_numeric[1].normalized_key, (
        "unknown-domain atoms must SINGLETON (fail-closed) — consolidation inert+safe"
    )
    # the unknown singleton key is the redesign __unresolved__ shape (not legacy).
    assert unknown_numeric[0].normalized_key[0] == "__unresolved__"


def test_22_main_path_basket_merges_distinct_origins_into_one_cluster():
    """#22 through the basket-assembly path: the two consolidated clinical atoms
    (distinct origins, both verifying alone) produce ONE basket whose
    verified_support_origin_count == 2 — corroboration emerges from honest
    multi-attribution on the activated main path, exactly the breadth Principle."""
    claims_by_eid = {
        "e1": _all_known_numeric("e1", value=14.9),
        "e2": _all_known_numeric("e2", value=14.9),
    }
    rows = _annotated_rows([
        ("e1", "Semaglutide achieved 14.9% weight loss at week 68.", 0.9),
        ("e2", "Semaglutide achieved 14.9% weight loss at week 68.", 0.8),
    ])
    _graph, baskets = _build_basket(claims_by_eid, rows)
    assert len(baskets) == 1, "the two equal clinical atoms consolidate into one basket"
    assert baskets[0].verified_support_origin_count == 2
    assert baskets[0].basket_verdict == BASKET_VERDICT_FULL
