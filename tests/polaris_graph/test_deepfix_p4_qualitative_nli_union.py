"""I-deepfix-001 P4 recall rung-1 (#1344): QUALITATIVE-basket bidirectional-NLI union.

WHAT THIS PROVES
----------------
Breadth is lost at CONSOLIDATION, not (yet) retrieval: the qualitative corroboration
matcher (`finding_dedup._build_qualitative_groups`) is lexical-only near-verbatim
(content-word shingle Jaccard 0.82), so two INDEPENDENT sources that assert the SAME
qualitative claim in DIFFERENT words never cluster — each stays a singleton and earns NO
corroboration weight. Most DRB-II rubric facts are non-numeric, so this is the dominant
breadth leak. P4 rung-1 gives the qualitative baskets the SAME strict bidirectional-entailment
consolidation the NUMERIC baskets already get (`consolidation_nli.score_pairs`), behind
`PG_CONSOLIDATION_NLI_QUALITATIVE` (× the master `PG_CONSOLIDATION_NLI`).

RED before the P4 edit (the qualitative pass is lexical-only, so the paraphrase pair stays two
singletons and NO multi-source qualitative basket forms); GREEN after (the NLI union recalls the
paraphrase into ONE basket carrying >=2 distinct independent hosts).

THE FOUR REQUIRED OVER-MERGE CANARIES (fail-loud, NOT recommendations)
---------------------------------------------------------------------
An NLI union of related-but-DISTINCT claims raises corroboration_count which the render layer
would then label 'corroborated' — a FALSE corroboration statement, the misstated-corroboration
class §-1.1 calls clinical-lethal. So the union is guarded by a STRICT bidirectional requirement
(A entails B AND B entails A) plus a polarity hard-block. Each of these four adversarial pairs
MUST remain unmerged — a merge on ANY is a hard test FAILURE:
  n1 SCOPE            manufacturing-vs-services productivity (neither direction entails)
  n2 CAUSAL-DIRECTION A->B vs B->A                          (neither direction entails)
  n3 TEMPORALITY      early-wave vs recent-era same metric  (neither direction entails)
  n4 HEDGED-vs-FLAT   'may displace' vs 'displace'          (ONE-directional only => no union)
Plus a fifth defense-in-depth ANTONYM/polarity check (increased vs decreased): the stub WRONGLY
scores it bidirectional-entailing, and the polarity guard must still block the union.

OFFLINE / NO GPU / NO SPEND
---------------------------
The cross-encoder is replaced by a deterministic stub injected through
`consolidation_nli._load_model` (the SAME production seam `score_pairs` reads), so the whole
test runs with no torch, no sentence-transformers, no model download, no network.

FAITHFULNESS (§-1.3): the union is WEIGHT-ONLY / KEEP-ALL — it only GROWS member lists
(corroboration_count / independent_hosts rise); every input row still appears in deduped_rows and
NO verify gate (strict_verify / NLI entailment verifier / 4-role / provenance / span) is touched.
"""
from __future__ import annotations

import pytest

import src.polaris_graph.synthesis.consolidation_nli as cnli
from src.polaris_graph.authority.data_loader import load_authority_data
from src.polaris_graph.synthesis.finding_dedup import dedup_by_finding


# ── The 12 qualitative claim bodies (number-free => no numeric finding; all pairs below the
#    0.82 lexical Jaccard so each row is its OWN candidate cluster the NLI must recall/keep-apart).
POS_A = "Adoption of artificial intelligence remains concentrated among the largest firms."
POS_B = "Uptake of these tools is heavily skewed toward big incumbent corporations."

SCOPE_A = "Automation lifts output per worker throughout manufacturing plants nationwide."
SCOPE_B = "Automation lifts output per worker across service industry branches nationwide."

CAUSAL_A = "Rising automation drives higher unemployment in the affected coastal regions."
CAUSAL_B = "Higher unemployment drives greater investment in automation elsewhere entirely."

TEMPORAL_A = "During the early industrial automation wave clerical staffing expanded steadily."
TEMPORAL_B = "Within the recent generative model era clerical staffing expanded steadily."

HEDGE_FLAT = "Generative models displace routine clerical writing tasks."
HEDGE_HEDGED = "Generative models might sometimes displace certain routine clerical writing tasks."

ANTONYM_UP = "Automation increased the number of warehouse jobs across the sector."
ANTONYM_DOWN = "Automation decreased the number of warehouse jobs across the sector."

# TRANSITIVITY CHAIN (I-deepfix-001 P4 Codex fix, #1344): three DISTINCT same-polarity claims
# where A<->B and B<->C bidirectionally entail but A and C do NOT directly entail. The prior
# TRANSITIVE union-find would fold A/B/C into ONE basket (A and C together) even though A and C
# were never scored as the same claim — a false-'corroborated' render chain (§-1.1 clinical-lethal).
# The direct-to-primary grouping must merge only the DIRECT edge (A+B) and leave C a singleton.
# All three are UP-direction / no-negation => identical polarity signature, so the ONLY thing that
# can keep A and C apart is the transitivity guard itself (a polarity mismatch is deliberately
# excluded so this canary isolates the transitive-merge defect).
TRANS_A = "Digital skills training expanded the pool of qualified rural applicants substantially."
TRANS_B = "Vocational upskilling programmes grew the number of employable countryside candidates."
TRANS_C = "Apprenticeship funding raised the availability of skilled provincial workers considerably."


# Ordered (premise, hypothesis) pairs the stub scores as ENTAILMENT. A merge needs BOTH
# orderings present (strict bidirectional).
_ENTAIL_ORDERED = frozenset({
    # POSITIVE: same claim, different words => bidirectional entail => SHOULD merge.
    (POS_A, POS_B),
    (POS_B, POS_A),
    # HEDGED-vs-FLAT: 'displace' entails 'might sometimes displace' but NOT the reverse =>
    # ONE-directional => the strict bidirectional requirement must REFUSE the union.
    (HEDGE_FLAT, HEDGE_HEDGED),
    # ANTONYM: the stub WRONGLY claims bidirectional entailment; the polarity guard must still
    # block the union (defense-in-depth — a model-independent hard block).
    (ANTONYM_UP, ANTONYM_DOWN),
    (ANTONYM_DOWN, ANTONYM_UP),
    # TRANSITIVITY CHAIN: A<->B and B<->C entail, but A<->C is DELIBERATELY ABSENT. A transitive
    # union-find would still merge A/B/C; the direct-to-primary grouping must NOT pull C into A's
    # basket (C never directly entails A).
    (TRANS_A, TRANS_B),
    (TRANS_B, TRANS_A),
    (TRANS_B, TRANS_C),
    (TRANS_C, TRANS_B),
    # SCOPE / CAUSAL / TEMPORALITY: NO ordered pair => neither direction entails => no union.
})


class _FakeCrossEncoder:
    """Deterministic stand-in for the nli-deberta cross-encoder. Returns
    [contradiction, entailment, neutral] logits: entailment-argmax for an ordered pair in
    `_ENTAIL_ORDERED`, else neutral-argmax. No torch, no GPU, no download."""

    def predict(self, batch):
        out = []
        for premise, hypothesis in batch:
            if (premise, hypothesis) in _ENTAIL_ORDERED:
                out.append([0.0, 5.0, 0.0])   # entailment is the strict argmax
            else:
                out.append([0.0, 0.0, 5.0])   # neutral (not entailing)
        return out


def _rows():
    """12 qualitative evidence rows: the positive paraphrase pair (2 distinct hosts) + the
    four over-merge canary pairs + the antonym/polarity pair."""
    specs = [
        ("ev_pos_a", POS_A, "https://digitaleconomy.stanford.edu/ai-diffusion"),
        ("ev_pos_b", POS_B, "https://www.oecd.org/employment/ai-adoption"),
        ("ev_scope_a", SCOPE_A, "https://example-scope-a.org/manufacturing"),
        ("ev_scope_b", SCOPE_B, "https://example-scope-b.net/services"),
        ("ev_causal_a", CAUSAL_A, "https://example-causal-a.org/regions"),
        ("ev_causal_b", CAUSAL_B, "https://example-causal-b.net/investment"),
        ("ev_temporal_a", TEMPORAL_A, "https://example-temporal-a.org/early"),
        ("ev_temporal_b", TEMPORAL_B, "https://example-temporal-b.net/recent"),
        ("ev_hedge_flat", HEDGE_FLAT, "https://example-hedge-a.org/flat"),
        ("ev_hedge_hedged", HEDGE_HEDGED, "https://example-hedge-b.net/hedged"),
        ("ev_antonym_up", ANTONYM_UP, "https://example-antonym-a.org/up"),
        ("ev_antonym_down", ANTONYM_DOWN, "https://example-antonym-b.net/down"),
        ("ev_trans_a", TRANS_A, "https://example-trans-a.org/skills"),
        ("ev_trans_b", TRANS_B, "https://example-trans-b.net/vocational"),
        ("ev_trans_c", TRANS_C, "https://example-trans-c.org/apprentice"),
    ]
    return [
        {
            "evidence_id": eid,
            "source_url": url,
            "direct_quote": body,
            "authority_score": 0.7,
            "selection_relevance": 0.7,
        }
        for eid, body, url in specs
    ]


# Row-index constants (positional, mirrors `_rows()` order) for canary assertions.
_IDX = {eid: i for i, (eid, *_rest) in enumerate([
    ("ev_pos_a",), ("ev_pos_b",), ("ev_scope_a",), ("ev_scope_b",),
    ("ev_causal_a",), ("ev_causal_b",), ("ev_temporal_a",), ("ev_temporal_b",),
    ("ev_hedge_flat",), ("ev_hedge_hedged",), ("ev_antonym_up",), ("ev_antonym_down",),
    ("ev_trans_a",), ("ev_trans_b",), ("ev_trans_c",),
])}


def _gov():
    return tuple(load_authority_data()["psl_gov_suffixes"])


def _set_common_env(monkeypatch, *, qual_nli: str):
    """The WEIGHT-AND-CONSOLIDATE keep-all regime + the qualitative pass + the master NLI gate,
    with the qualitative-NLI sub-flag set to `qual_nli` ('1' union ON, '0' lexical-only)."""
    monkeypatch.setenv("PG_SWEEP_CREDIBILITY_REDESIGN", "on")   # keep-all consolidate regime
    monkeypatch.setenv("PG_FINDING_DEDUP_QUALITATIVE", "1")     # qualitative pass on
    monkeypatch.setenv("PG_CONSOLIDATION_NLI", "1")             # master NLI gate on
    monkeypatch.setenv("PG_CONSOLIDATION_NLI_QUALITATIVE", qual_nli)
    monkeypatch.setenv("PG_CONSOLIDATION_NLI_WORKERS", "1")     # single-worker => deterministic
    # Inject the deterministic stub through the SAME production seam score_pairs reads.
    monkeypatch.setattr(cnli, "_load_model", lambda *a, **k: _FakeCrossEncoder())


def _qual_clusters(result):
    """The qualitative baskets (finding_key[0] == '__qual__') among the result clusters."""
    return [
        c for c in result.clusters
        if isinstance(c.finding_key, tuple) and c.finding_key and c.finding_key[0] == "__qual__"
    ]


def _members_together(result, eid_a: str, eid_b: str) -> bool:
    """True iff any single cluster contains BOTH row indices (i.e. the two rows merged)."""
    ia, ib = _IDX[eid_a], _IDX[eid_b]
    for c in result.clusters:
        mi = set(c.member_indices)
        if ia in mi and ib in mi:
            return True
    return False


def test_qualitative_nli_union_recalls_paraphrase_basket(monkeypatch):
    """GREEN after P4: the positive paraphrase pair (lexical Jaccard 0.0) is RECALLED by the
    bidirectional-NLI union into ONE qualitative basket carrying >=2 distinct independent hosts.

    RED before P4 (lexical-only): the pair never clusters => zero qualitative baskets =>
    `real_multi_source` below is empty and this assertion FAILS.
    """
    _set_common_env(monkeypatch, qual_nli="1")
    result = dedup_by_finding(_rows(), gov_suffixes=_gov(), domain=None)

    quals = _qual_clusters(result)
    real_multi_source = [
        c for c in quals
        if len(c.member_indices) >= 2 and c.corroboration_count >= 2
    ]
    assert real_multi_source, (
        "P4 RED/GREEN: expected >=1 qualitative basket with >=2 members AND "
        "corroboration_count>=2 (the paraphrase pair recalled by the NLI union). Got "
        f"qualitative baskets={[(c.finding_key[:2], c.member_indices, c.corroboration_count) for c in quals]}"
    )

    # The recalled basket is EXACTLY the positive paraphrase pair, with 2 distinct hosts.
    assert _members_together(result, "ev_pos_a", "ev_pos_b"), (
        "the positive paraphrase pair must be consolidated into ONE basket"
    )
    pos_basket = next(
        c for c in real_multi_source
        if {_IDX["ev_pos_a"], _IDX["ev_pos_b"]}.issubset(set(c.member_indices))
    )
    assert len(pos_basket.member_hosts) >= 2, (
        f"the recalled basket must carry >=2 DISTINCT independent hosts, got {pos_basket.member_hosts}"
    )
    assert result.qualitative_basket_count >= 1


def test_qualitative_nli_union_strictly_increases_baskets_vs_lexical_only(monkeypatch):
    """Behavioral RED->GREEN counter: lexical-only (sub-flag OFF) forms ZERO qualitative baskets
    for the paraphrase pair; the NLI union (sub-flag ON) forms >=1. Same rows, same corpus."""
    rows = _rows()

    _set_common_env(monkeypatch, qual_nli="0")   # lexical-only baseline
    baseline = dedup_by_finding(rows, gov_suffixes=_gov(), domain=None)

    _set_common_env(monkeypatch, qual_nli="1")   # NLI union ON
    unioned = dedup_by_finding(rows, gov_suffixes=_gov(), domain=None)

    assert baseline.qualitative_basket_count == 0, (
        "lexical-only baseline must NOT cluster the paraphrase pair (Jaccard 0.0) — the leak P4 fixes"
    )
    assert unioned.qualitative_basket_count > baseline.qualitative_basket_count, (
        f"the NLI union must strictly increase qualitative baskets "
        f"({unioned.qualitative_basket_count} !> {baseline.qualitative_basket_count})"
    )


def test_four_over_merge_canaries_never_merge(monkeypatch):
    """REQUIRED fail-loud: the four over-merge canaries (SCOPE / CAUSAL-DIRECTION / TEMPORALITY /
    HEDGED-vs-FLAT) MUST each remain UNMERGED under the bidirectional-NLI union. A merge on any is
    a false-'corroborated' render chain (§-1.1 clinical-lethal)."""
    _set_common_env(monkeypatch, qual_nli="1")
    result = dedup_by_finding(_rows(), gov_suffixes=_gov(), domain=None)

    assert not _members_together(result, "ev_scope_a", "ev_scope_b"), (
        "CANARY n1 SCOPE over-merge: manufacturing-productivity and services-productivity are "
        "DIFFERENT-scope claims (neither entails the other) — they must NEVER consolidate into one "
        "'corroborated' basket."
    )
    assert not _members_together(result, "ev_causal_a", "ev_causal_b"), (
        "CANARY n2 CAUSAL-DIRECTION over-merge: A->B and B->A are different claims — the strict "
        "bidirectional entailment must keep them apart."
    )
    assert not _members_together(result, "ev_temporal_a", "ev_temporal_b"), (
        "CANARY n3 TEMPORALITY over-merge: an early-wave claim and a recent-era claim about the "
        "same metric are different claims — they must NEVER merge."
    )
    assert not _members_together(result, "ev_hedge_flat", "ev_hedge_hedged"), (
        "CANARY n4 HEDGED-vs-FLAT over-merge: 'displace' entails 'might sometimes displace' but NOT "
        "the reverse (one-directional) — merging them is a certainty distortion. The strict "
        "bidirectional requirement must REFUSE this union."
    )


def test_polarity_hard_block_defeats_antonym_even_when_nli_says_entail(monkeypatch):
    """Defense-in-depth: the stub WRONGLY scores the antonym pair (increased vs decreased) as
    bidirectional-entailing; the `_polarity_signature` hard-block must STILL prevent the union — a
    model-independent guard, not left to the NLI verdict alone."""
    _set_common_env(monkeypatch, qual_nli="1")
    result = dedup_by_finding(_rows(), gov_suffixes=_gov(), domain=None)
    assert not _members_together(result, "ev_antonym_up", "ev_antonym_down"), (
        "POLARITY over-merge: an 'increased' vs 'decreased' antonym must NEVER corroborate, even "
        "when the cross-encoder scores it entailing — the polarity hard-block is required."
    )


def test_transitive_chain_never_over_merges(monkeypatch):
    """REQUIRED fail-loud (I-deepfix-001 P4 Codex fix, #1344): the A<->B / B<->C chain (with NO
    direct A<->C edge) MUST NOT fold A/B/C into one basket. The prior TRANSITIVE union-find merged
    all three; the direct-to-primary grouping must merge only the DIRECT edge (A+B) and leave C a
    singleton. Merging A and C here is a false-'corroborated' render chain — a basket head would
    carry a corroboration_count inflated by a claim (C) that verifies only against a SIBLING span
    (B), never against the head (§-1.1 clinical-lethal)."""
    _set_common_env(monkeypatch, qual_nli="1")
    result = dedup_by_finding(_rows(), gov_suffixes=_gov(), domain=None)

    # The DIRECT edge still consolidates: A and B (which directly bidirectionally entail) merge.
    assert _members_together(result, "ev_trans_a", "ev_trans_b"), (
        "the DIRECT A<->B edge must still consolidate (proves the fix did not disable direct "
        "recall — only the transitive hop is blocked)."
    )
    # The transitive hop is BLOCKED: C (which entails only the sibling B, never the head A) must
    # NOT land in A's basket.
    assert not _members_together(result, "ev_trans_a", "ev_trans_c"), (
        "TRANSITIVE over-merge: A and C do NOT directly entail — a transitive union-find would "
        "wrongly fold them into one 'corroborated' basket via B. The direct-to-primary grouping "
        "must keep them apart."
    )
    # C is not pulled into B's consolidated group either (B was consumed into A's basket; C only
    # ever entailed B directly, so with B consumed C stays a singleton).
    assert not _members_together(result, "ev_trans_b", "ev_trans_c"), (
        "TRANSITIVE over-merge: once B is consumed into A's basket, C (entailing only B) must not "
        "be dragged in transitively — it remains its own singleton."
    )


def test_keep_all_and_weight_only(monkeypatch):
    """FAITHFULNESS: the union is KEEP-ALL / WEIGHT-ONLY — every input row still appears in
    deduped_rows (no row dropped), and collapsed_row_count stays 0 (keep-all regime)."""
    rows = _rows()
    _set_common_env(monkeypatch, qual_nli="1")
    result = dedup_by_finding(rows, gov_suffixes=_gov(), domain=None)

    kept_ids = {str(r.get("evidence_id")) for r in result.deduped_rows}
    for r in rows:
        assert str(r["evidence_id"]) in kept_ids, (
            f"keep-all violated: input row {r['evidence_id']} missing from deduped_rows"
        )
    assert len(result.deduped_rows) == len(rows), "no qualitative row may be dropped by the union"
    assert result.collapsed_row_count == 0, "keep-all regime => collapsed_row_count must be 0"


def test_sub_flag_off_is_lexical_only_byte_identical(monkeypatch):
    """The sub-flag OFF (or the master gate OFF) => the qualitative pass is byte-identical
    lexical-only: the paraphrase pair does NOT cluster, so no qualitative basket forms."""
    _set_common_env(monkeypatch, qual_nli="0")
    result = dedup_by_finding(_rows(), gov_suffixes=_gov(), domain=None)
    assert result.qualitative_basket_count == 0
    assert not _members_together(result, "ev_pos_a", "ev_pos_b")
