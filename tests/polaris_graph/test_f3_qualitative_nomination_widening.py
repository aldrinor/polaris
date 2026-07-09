"""F3-3a (I-deepfix-001 #1369) — WIDENED qualitative candidate NOMINATION + NLI confirm.

WHAT THIS PROVES
----------------
The qualitative candidate NOMINATION was lexical NEAR-VERBATIM only: the greedy pass in
``finding_dedup._build_qualitative_groups`` clusters rows by content-word shingle Jaccard
>= 0.82, so a cross-document PARAPHRASE whose surface wording differs enough that its
shingle-Jaccard falls below 0.82 stays its OWN singleton and never corroborates. F3-3a
WIDENS the nomination with ASYMMETRIC token-CONTAINMENT (catches paraphrase/expansion pairs
Jaccard misses) and CONFIRMS each nominated pair through the SAME strict bidirectional NLI —
the NLI stays the SOLE merge decision, token-containment is only a candidate blocker.

  (i)  PARAPHRASE (verbatim A + paraphrased B, Jaccard < 0.82 AND containment >= 0.60):
       nominated by containment AND NLI-approved => ONE basket, 2 independent origins
       (corroboration_count == 2). This is the finding_dedup layer's realization of
       "verified_support_origin_count == 2" (2 distinct verified corroboration origins).
  (ii) ANTI-FABRICATION: two docs with HIGH shared vocabulary but a DIFFERENT subject/metric
       (productivity metric vs unemployment metric) are NOMINATED by containment but the NLI
       REJECTS them => they stay 2 SEPARATE baskets (origin_count 1 each). The nominator can
       never launder a false corroboration past the NLI gate.
  polarity defense-in-depth: an antonym pair (increased vs decreased) is polarity-blocked at
       nomination even if a stub scored it entailing.

OFFLINE / NO GPU / NO SPEND: the cross-encoder is replaced by a deterministic stub injected
through ``consolidation_nli._load_model`` (the SAME production seam ``entails_directional``
reads), so the whole test runs with no torch, no model download, no network.

FAITHFULNESS (§-1.3): the widening is WEIGHT-ONLY / KEEP-ALL — it only GROWS member lists;
every input row still appears in ``deduped_rows`` and NO verify gate is touched.
"""
from __future__ import annotations

import src.polaris_graph.synthesis.consolidation_nli as cnli
from src.polaris_graph.authority.data_loader import load_authority_data
from src.polaris_graph.synthesis.finding_dedup import (
    _apply_qualitative_containment_nli_grouping,
    _content_tokens,
    _token_containment,
    dedup_by_finding,
)

# ── Paraphrase pair: B's content tokens are fully contained in A (containment 1.0) but the
#    surface wording/length differs enough that shingle-Jaccard is far below 0.82. SAME UP polarity.
PARA_A = "Remote work substantially increased employee productivity across large technology firms."
PARA_B = "Remote work increased employee productivity."

# ── Anti-fabrication pair: HIGH shared vocabulary (containment >= 0.60) but a DIFFERENT
#    subject/metric (productivity vs unemployment). SAME polarity (no direction word), so the
#    polarity guard does NOT block them — only the NLI can keep them apart.
ANTIFAB_C = "The productivity metric from automation reached record levels this cycle."
ANTIFAB_D = "The unemployment metric from automation reached record levels this cycle."

# ── Antonym pair: same tokens except increased/decreased => opposite polarity (UP vs DOWN).
ANTONYM_UP = "Automation increased the number of warehouse jobs sharply this cycle."
ANTONYM_DOWN = "Automation decreased the number of warehouse jobs sharply this cycle."


# Ordered (premise, hypothesis) pairs the stub scores as ENTAILMENT (a merge needs BOTH orderings).
_ENTAIL_ORDERED = frozenset({
    (PARA_A, PARA_B),
    (PARA_B, PARA_A),
    # The antonym pair is WRONGLY scored entailing to prove the polarity guard blocks it anyway.
    (ANTONYM_UP, ANTONYM_DOWN),
    (ANTONYM_DOWN, ANTONYM_UP),
    # The anti-fab pair is deliberately NOT here => the NLI (correctly) rejects it => no merge.
})


class _FakeCrossEncoder:
    """Deterministic nli-deberta stand-in. Returns [contradiction, entailment, neutral] logits:
    entailment-argmax for an ordered pair in ``_ENTAIL_ORDERED``, else neutral-argmax."""

    def predict(self, batch):
        out = []
        for premise, hypothesis in batch:
            if (premise, hypothesis) in _ENTAIL_ORDERED:
                out.append([0.0, 5.0, 0.0])
            else:
                out.append([0.0, 0.0, 5.0])
        return out


def _rows():
    specs = [
        ("ev_para_a", PARA_A, "https://digitaleconomy.stanford.edu/remote"),
        ("ev_para_b", PARA_B, "https://www.oecd.org/employment/remote"),
        ("ev_antifab_c", ANTIFAB_C, "https://example-c.org/productivity"),
        ("ev_antifab_d", ANTIFAB_D, "https://example-d.net/unemployment"),
        ("ev_antonym_up", ANTONYM_UP, "https://example-up.org/jobs"),
        ("ev_antonym_down", ANTONYM_DOWN, "https://example-down.net/jobs"),
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


_IDX = {eid: i for i, (eid, *_r) in enumerate([
    ("ev_para_a",), ("ev_para_b",), ("ev_antifab_c",), ("ev_antifab_d",),
    ("ev_antonym_up",), ("ev_antonym_down",),
])}


def _gov():
    return tuple(load_authority_data()["psl_gov_suffixes"])


def _isolate_env(monkeypatch):
    """Enable ONLY the F3-3a widened-nomination pass: keep-all regime + qualitative pass ON, the
    master NLI gate ON (so the pass's cross-encoder path activates) but BOTH existing qualitative
    NLI unions OFF, so any merge is attributable to the F3-3a containment nominator alone."""
    monkeypatch.setenv("PG_SWEEP_CREDIBILITY_REDESIGN", "on")
    monkeypatch.setenv("PG_FINDING_DEDUP_QUALITATIVE", "1")
    monkeypatch.setenv("PG_CONSOLIDATION_NLI", "1")            # activates the FOURTH-pass gate
    monkeypatch.setenv("PG_CONSOLIDATION_NLI_QUALITATIVE", "0")  # existing SECOND pass OFF
    monkeypatch.setenv("PG_FINDING_DEDUP_NLI", "0")           # existing THIRD pass OFF
    monkeypatch.setenv("PG_FINDING_DEDUP_QUALITATIVE_NOMINATE", "1")  # F3-3a widening ON (default)
    monkeypatch.setattr(cnli, "_load_model", lambda *a, **k: _FakeCrossEncoder())


def _members_together(result, eid_a, eid_b) -> bool:
    ia, ib = _IDX[eid_a], _IDX[eid_b]
    for c in result.clusters:
        mi = set(c.member_indices)
        if ia in mi and ib in mi:
            return True
    return False


# ── Sanity: the fixtures actually have the Jaccard/containment shape the test relies on ──

def test_paraphrase_fixture_has_low_jaccard_high_containment():
    ta = _content_tokens(PARA_A)
    tb = _content_tokens(PARA_B)
    # asymmetric containment is high (B fully contained in A)
    assert _token_containment(ta, tb) >= 0.60
    # symmetric Jaccard is BELOW the 0.82 near-verbatim gate (the greedy pass keeps them apart)
    jac = len(ta & tb) / len(ta | tb)
    assert jac < 0.82, f"fixture must be below the near-verbatim gate, got Jaccard {jac}"


# ── (i) PARAPHRASE recalled into ONE basket with 2 origins ──

def test_paraphrase_nominated_and_nli_approved_into_one_basket(monkeypatch):
    _isolate_env(monkeypatch)
    result = dedup_by_finding(_rows(), gov_suffixes=_gov(), domain=None)

    assert _members_together(result, "ev_para_a", "ev_para_b"), (
        "F3-3a: the paraphrase pair (Jaccard < 0.82, containment >= 0.60) must be NOMINATED by "
        "token-containment AND NLI-approved into ONE basket."
    )
    para_basket = next(
        c for c in result.clusters
        if {_IDX["ev_para_a"], _IDX["ev_para_b"]}.issubset(set(c.member_indices))
    )
    # corroboration_count == 2 distinct independent origins == the finding_dedup realization of
    # "verified_support_origin_count == 2".
    assert para_basket.corroboration_count == 2, (
        f"the recalled basket must carry 2 independent corroboration origins, got "
        f"{para_basket.corroboration_count} (hosts={para_basket.member_hosts})"
    )
    assert len(para_basket.member_hosts) == 2
    assert result.qualitative_basket_count >= 1


# ── (ii) ANTI-FABRICATION: token-overlapping but distinct => NLI rejects => stays 2 baskets ──

def test_antifabrication_distinct_subject_nominated_but_nli_rejects(monkeypatch):
    _isolate_env(monkeypatch)
    result = dedup_by_finding(_rows(), gov_suffixes=_gov(), domain=None)

    # sanity: the anti-fab pair IS nominated (high containment) so we are truly testing the NLI gate
    assert _token_containment(_content_tokens(ANTIFAB_C), _content_tokens(ANTIFAB_D)) >= 0.60

    assert not _members_together(result, "ev_antifab_c", "ev_antifab_d"), (
        "ANTI-FABRICATION: a productivity-metric claim and an unemployment-metric claim share "
        "vocabulary (nominated) but assert DIFFERENT subjects — the NLI must REJECT the union so "
        "they stay 2 SEPARATE baskets (origin_count 1 each). The nominator can never launder a "
        "false corroboration past the NLI gate."
    )


def test_antonym_polarity_hard_block(monkeypatch):
    _isolate_env(monkeypatch)
    result = dedup_by_finding(_rows(), gov_suffixes=_gov(), domain=None)
    assert not _members_together(result, "ev_antonym_up", "ev_antonym_down"), (
        "POLARITY: an 'increased' vs 'decreased' antonym must NEVER corroborate even when the "
        "stub scores it entailing — the polarity hard-block excludes it at nomination."
    )


# ── keep-all / faithfulness-neutral ──

def test_keep_all_no_row_dropped(monkeypatch):
    rows = _rows()
    _isolate_env(monkeypatch)
    result = dedup_by_finding(rows, gov_suffixes=_gov(), domain=None)
    kept = {str(r.get("evidence_id")) for r in result.deduped_rows}
    for r in rows:
        assert str(r["evidence_id"]) in kept, f"keep-all violated: {r['evidence_id']} dropped"
    assert result.collapsed_row_count == 0


# ── The widening is a NO-OP when its kill switch is OFF (byte-identical lexical-only) ──

def test_nominate_flag_off_does_not_merge_paraphrase(monkeypatch):
    _isolate_env(monkeypatch)
    monkeypatch.setenv("PG_FINDING_DEDUP_QUALITATIVE_NOMINATE", "0")  # widening OFF
    result = dedup_by_finding(_rows(), gov_suffixes=_gov(), domain=None)
    assert not _members_together(result, "ev_para_a", "ev_para_b"), (
        "with the F3-3a widening OFF and the existing qualitative NLI unions OFF, the paraphrase "
        "pair (Jaccard < 0.82) must stay separate — proving the merge above is the widening's doing."
    )


# ── Direct unit test of the nominator + NLI confirm with an injected entail_fn (no stub-of-stub) ──

def _clusters_from(rows):
    """Build the greedy-cluster shape ([rep_shingles, rep_polarity, [member_ris]]) directly — one
    singleton cluster per row (the state the widened pass receives after a near-verbatim greedy pass
    leaves paraphrases un-grouped)."""
    from src.polaris_graph.generator.fact_dedup import _polarity_signature, _prose_shingles
    return [
        [_prose_shingles(r["direct_quote"]), _polarity_signature(r["direct_quote"]), [i]]
        for i, r in enumerate(rows)
    ]


def test_apply_containment_nli_grouping_unit(monkeypatch):
    monkeypatch.setenv("PG_FINDING_DEDUP_QUALITATIVE_NOMINATE", "1")
    rows = _rows()
    clusters = _clusters_from(rows)

    def _entail(premise: str, hypothesis: str):
        return True if (premise, hypothesis) in _ENTAIL_ORDERED else False

    telem: dict = {}
    merged = _apply_qualitative_containment_nli_grouping(
        rows, clusters, entail_fn=_entail, telemetry=telem,
    )

    def _together(a_eid, b_eid) -> bool:
        ia, ib = _IDX[a_eid], _IDX[b_eid]
        return any(ia in set(c[2]) and ib in set(c[2]) for c in merged)

    # paraphrase pair merges (nominated + bidirectional-entail confirmed)
    assert _together("ev_para_a", "ev_para_b")
    # anti-fab pair nominated but NLI rejects (neutral) => stays apart
    assert not _together("ev_antifab_c", "ev_antifab_d")
    # antonym pair polarity-blocked at nomination => stays apart
    assert not _together("ev_antonym_up", "ev_antonym_down")
    assert telem["containment_merges"] == 1
    assert telem["nominated_pairs"] >= 1
