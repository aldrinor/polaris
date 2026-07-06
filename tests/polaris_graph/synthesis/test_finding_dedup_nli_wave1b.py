"""I-deepfix-001 Wave 1b (#1344): PG_FINDING_DEDUP_NLI bidirectional-entailment
qualitative grouping (REAL_PLAN_2026 coverage_fix item 1).

WHAT THIS PROVES
----------------
The coverage-fix keystone flag ``PG_FINDING_DEDUP_NLI`` (default-OFF) adds a directional,
3-state NLI grouping to ``finding_dedup`` so INDEPENDENT sources that assert the SAME
qualitative (non-numeric) claim in DIFFERENT words reach ONE corroboration basket. The merge
rule is STRICT BIDIRECTIONAL ENTAILMENT via ``consolidation_nli.entails_directional``:

  * bidirectional entails (BOTH directions True)   => MERGE (keep-all, one basket);
  * one-direction-only (exactly one True)          => an EXTENSION relation => do NOT merge;
  * contradiction (neither direction entails)      => a durable relation => do NOT merge;
  * infra ``None`` on EITHER direction             => NO merge, FAIL-CLOSED singleton, run continues;
  * POLARITY hard-block (defense-in-depth)         => mismatched polarity never merges.

FAITHFULNESS (§-1.3): MERGE-ONLY / KEEP-ALL / WEIGHT-ONLY — the union only GROWS member lists;
no row is dropped and NO verify gate (strict_verify / the NLI entailment verifier / 4-role D8 /
provenance / span-grounding) is touched. Per-member isolated verify is UNTOUCHED.

OFFLINE / NO GPU / NO SPEND: the unit tests inject a deterministic ``entail_fn`` stub directly;
the end-to-end tests inject a deterministic cross-encoder stub through the SAME production seam
``consolidation_nli._load_model`` that ``entails_directional`` reads. No torch, no
sentence-transformers, no model download, no network.
"""
from __future__ import annotations

import pytest

import src.polaris_graph.synthesis.consolidation_nli as cnli
from src.polaris_graph.authority.data_loader import load_authority_data
from src.polaris_graph.synthesis.finding_dedup import (
    _apply_finding_dedup_nli_grouping,
    dedup_by_finding,
)


# ─────────────────────────────────────────────────────────────────────────
# Part 1 — UNIT tests of the merge predicate (injected entail_fn stub; no model at all)
# ─────────────────────────────────────────────────────────────────────────
def _rows(bodies):
    """One evidence row per body (distinct host so a real corroboration count could form)."""
    return [
        {
            "evidence_id": f"ev{i}",
            "source_url": f"https://host{i}.example.org/x",
            "direct_quote": body,
            "authority_score": 0.7,
            "selection_relevance": 0.7,
        }
        for i, body in enumerate(bodies)
    ]


def _singletons(rows, polarities=None):
    """One lexical singleton cluster per row (the shape ``_build_qualitative_groups`` passes):
    ``[rep_shingles, rep_polarity, [member_ris]]``. Default polarity ``()`` for every cluster
    (equal => all pairs eligible); pass ``polarities`` to force a polarity mismatch."""
    return [
        [
            frozenset({rows[i]["direct_quote"]}),
            (polarities[i] if polarities is not None else ()),
            [i],
        ]
        for i in range(len(rows))
    ]


def _stub(table):
    """A deterministic directional ``entail_fn``: returns the verdict mapped for an ORDERED
    (premise, hypothesis) pair, defaulting to ``False`` (a confident non-entailment)."""
    def _entail(premise: str, hypothesis: str):
        return table.get((premise, hypothesis), False)
    return _entail


def _merged_members(out):
    """The set of frozenset member-groups (each cluster's member indices) in the output."""
    return {frozenset(c[2]) for c in out}


def _together(out, a: int, b: int) -> bool:
    return any({a, b}.issubset(set(c[2])) for c in out)


def test_bidirectional_entails_merges_keeping_all_members():
    """ON + bidirectional entails => the paraphrase pair MERGES into ONE multi-member cluster
    that KEEPS ALL members (§-1.3 keep-all)."""
    a, b = "AI adoption is concentrated among the largest firms.", \
           "Uptake of these tools skews heavily toward big incumbents."
    rows = _rows([a, b])
    out = _apply_finding_dedup_nli_grouping(
        rows, _singletons(rows), entail_fn=_stub({(a, b): True, (b, a): True}),
    )
    assert _together(out, 0, 1), "bidirectional-entailing paraphrases must merge into one basket"
    merged = [c for c in out if len(c[2]) >= 2]
    assert len(merged) == 1 and merged[0][2] == [0, 1]
    # KEEP-ALL: every input row index still appears exactly once across the output.
    all_members = sorted(i for c in out for i in c[2])
    assert all_members == [0, 1]


def test_one_direction_only_does_not_merge():
    """ON + one-direction-only (an EXTENSION relation) => do NOT merge."""
    flat, hedged = "Generative models displace routine clerical tasks.", \
                   "Generative models might sometimes displace certain routine clerical tasks."
    rows = _rows([flat, hedged])
    out = _apply_finding_dedup_nli_grouping(
        rows, _singletons(rows), entail_fn=_stub({(flat, hedged): True}),  # reverse absent => False
    )
    assert not _together(out, 0, 1), "a one-directional (extension) verdict must NOT merge"
    assert _merged_members(out) == {frozenset({0}), frozenset({1})}


def test_contradiction_does_not_merge():
    """ON + contradiction (neither direction entails) => do NOT merge."""
    up, down = "Automation increased warehouse jobs across the sector.", \
               "Automation decreased warehouse jobs across the sector."
    rows = _rows([up, down])
    out = _apply_finding_dedup_nli_grouping(
        rows, _singletons(rows), entail_fn=_stub({}),  # both directions default False
    )
    assert not _together(out, 0, 1), "a contradiction must NOT merge"


def test_infra_none_is_fail_closed_singleton():
    """ON + infra ``None`` on either direction => NO merge (fail-closed singleton); the caller
    keeps the singleton and the run continues (the stub never raises)."""
    a, b = "Remote work raised measured output in knowledge roles.", \
           "Distributed teams recorded higher productivity in knowledge work."
    rows = _rows([a, b])
    # Forward entails, but the reverse verdict is UNAVAILABLE (None) => must not merge.
    out = _apply_finding_dedup_nli_grouping(
        rows, _singletons(rows), entail_fn=_stub({(a, b): True, (b, a): None}),
    )
    assert not _together(out, 0, 1), "an infra None verdict must fail-closed to a singleton"
    # Also a fully-None pair (both directions unavailable) never merges.
    out2 = _apply_finding_dedup_nli_grouping(
        rows, _singletons(rows), entail_fn=_stub({(a, b): None, (b, a): None}),
    )
    assert not _together(out2, 0, 1)


def test_polarity_hard_block_defeats_bidirectional_entail():
    """Defense-in-depth: even when the scorer returns bidirectional-entailing, a POLARITY
    mismatch hard-blocks the union (a model-independent guard)."""
    a, b = "Automation raised regional employment.", "Automation lowered regional employment."
    rows = _rows([a, b])
    out = _apply_finding_dedup_nli_grouping(
        rows,
        _singletons(rows, polarities=[("pos",), ("neg",)]),   # mismatched polarity signatures
        entail_fn=_stub({(a, b): True, (b, a): True}),         # scorer WRONGLY says merge
    )
    assert not _together(out, 0, 1), "mismatched polarity must never merge, even on entailment"


def test_direct_edge_grouping_blocks_transitive_over_merge():
    """DIRECT-EDGE keep-first (NOT transitive union-find): A<->B and B<->C entail but A<->C does
    NOT — A+B must merge and C must stay a singleton (a transitive fold A/B/C would inflate a
    basket head's corroboration with a claim that only entails a sibling — §-1.1 clinical-lethal)."""
    ca, cb, cc = "Digital skills training expanded the qualified rural applicant pool.", \
                 "Vocational upskilling grew the number of employable countryside candidates.", \
                 "Apprenticeship funding raised the availability of skilled provincial workers."
    rows = _rows([ca, cb, cc])
    out = _apply_finding_dedup_nli_grouping(
        rows, _singletons(rows),
        entail_fn=_stub({(ca, cb): True, (cb, ca): True, (cb, cc): True, (cc, cb): True}),
    )
    assert _together(out, 0, 1), "the DIRECT A<->B edge must consolidate"
    assert not _together(out, 0, 2), "A and C never directly entail — no transitive fold"
    assert not _together(out, 1, 2), "once B is consumed into A's basket, C stays a singleton"


def test_below_two_clusters_is_noop():
    """A single (or empty) cluster list is returned unchanged (nothing to pair)."""
    rows = _rows(["only one qualitative claim here."])
    clusters = _singletons(rows)
    assert _apply_finding_dedup_nli_grouping(rows, clusters, entail_fn=_stub({})) is clusters


# ─────────────────────────────────────────────────────────────────────────
# Part 2 — END-TO-END through dedup_by_finding (stub cross-encoder via _load_model)
# ─────────────────────────────────────────────────────────────────────────
POS_A = "Adoption of artificial intelligence remains concentrated among the largest firms."
POS_B = "Uptake of these tools is heavily skewed toward big incumbent corporations."
UNRELATED = "Coastal shipping volumes followed the usual seasonal winter pattern this quarter."

_ENTAIL_ORDERED = frozenset({(POS_A, POS_B), (POS_B, POS_A)})


class _FakeCrossEncoder:
    """Deterministic nli-deberta stand-in. Returns [contradiction, entailment, neutral] logits:
    entailment-argmax for an ordered pair in ``_ENTAIL_ORDERED``, else neutral-argmax. Counts
    ``predict`` calls so the OFF path can be proven to never touch the model."""

    def __init__(self):
        self.calls = 0

    def predict(self, batch):
        self.calls += 1
        out = []
        for premise, hypothesis in batch:
            out.append([0.0, 5.0, 0.0] if (premise, hypothesis) in _ENTAIL_ORDERED else [0.0, 0.0, 5.0])
        return out


class _RaisingCrossEncoder:
    """A cross-encoder whose predict RAISES a non-OOM error => ``entails_directional`` returns
    None (fail-closed). Proves an infra fault degrades to a singleton without aborting the run."""

    def predict(self, batch):
        raise RuntimeError("simulated cross-encoder failure (non-OOM)")


def _rows_e2e():
    specs = [
        ("ev_pos_a", POS_A, "https://digitaleconomy.stanford.edu/ai-diffusion"),
        ("ev_pos_b", POS_B, "https://www.oecd.org/employment/ai-adoption"),
        ("ev_unrelated", UNRELATED, "https://example-shipping.net/winter"),
    ]
    return [
        {
            "evidence_id": eid, "source_url": url, "direct_quote": body,
            "authority_score": 0.7, "selection_relevance": 0.7,
        }
        for eid, body, url in specs
    ]


def _gov():
    return tuple(load_authority_data()["psl_gov_suffixes"])


def _base_env(monkeypatch):
    """The keep-all consolidate regime + the qualitative pass ON, but the MASTER
    PG_CONSOLIDATION_NLI OFF so the existing score_pairs union never runs — this isolates the
    NEW PG_FINDING_DEDUP_NLI keystone path."""
    monkeypatch.setenv("PG_SWEEP_CREDIBILITY_REDESIGN", "on")
    monkeypatch.setenv("PG_FINDING_DEDUP_QUALITATIVE", "1")
    monkeypatch.setenv("PG_CONSOLIDATION_NLI", "0")          # master OFF => other union inert
    monkeypatch.setenv("PG_FINDING_DEDUP_NLI_WORKERS", "1")  # deterministic


def _qual_together(result, eid_a: str, eid_b: str) -> bool:
    idx = {str(r["evidence_id"]): i for i, r in enumerate(_rows_e2e())}
    ia, ib = idx[eid_a], idx[eid_b]
    return any({ia, ib}.issubset(set(c.member_indices)) for c in result.clusters)


def test_e2e_flag_off_is_byte_identical(monkeypatch):
    """OFF (PG_FINDING_DEDUP_NLI unset) => byte-identical: the paraphrase pair (lexical Jaccard
    ~0) never merges, NO qualitative basket forms, and the cross-encoder is NEVER loaded/called."""
    _base_env(monkeypatch)
    # PG_FINDING_DEDUP_NLI deliberately unset => default OFF.
    fake = _FakeCrossEncoder()
    monkeypatch.setattr(cnli, "_load_model", lambda *a, **k: fake)

    result = dedup_by_finding(_rows_e2e(), gov_suffixes=_gov(), domain=None)
    assert result.qualitative_basket_count == 0, "OFF must not form an NLI qualitative basket"
    assert not _qual_together(result, "ev_pos_a", "ev_pos_b")
    assert fake.calls == 0, "OFF must never touch the cross-encoder (byte-identical)"


def test_e2e_flag_on_merges_paraphrase_into_one_basket(monkeypatch):
    """ON => the paraphrase pair is RECALLED into ONE __qual__ basket with >=2 members and
    >=2 distinct independent hosts; KEEP-ALL holds (every row survives, collapsed_row_count 0)."""
    _base_env(monkeypatch)
    monkeypatch.setenv("PG_FINDING_DEDUP_NLI", "1")
    monkeypatch.setattr(cnli, "_load_model", lambda *a, **k: _FakeCrossEncoder())

    rows = _rows_e2e()
    result = dedup_by_finding(rows, gov_suffixes=_gov(), domain=None)

    assert result.qualitative_basket_count >= 1
    assert _qual_together(result, "ev_pos_a", "ev_pos_b"), "the paraphrase pair must consolidate"
    quals = [
        c for c in result.clusters
        if isinstance(c.finding_key, tuple) and c.finding_key and c.finding_key[0] == "__qual__"
    ]
    real_multi = [c for c in quals if len(c.member_indices) >= 2 and c.corroboration_count >= 2]
    assert real_multi, f"expected a real multi-source qualitative basket, got {[c.member_indices for c in quals]}"
    assert len(real_multi[0].member_hosts) >= 2
    # KEEP-ALL / WEIGHT-ONLY.
    kept = {str(r.get("evidence_id")) for r in result.deduped_rows}
    for r in rows:
        assert str(r["evidence_id"]) in kept, "keep-all violated: a row went missing"
    assert len(result.deduped_rows) == len(rows)
    assert result.collapsed_row_count == 0
    # The UNRELATED row stays its own singleton (never dragged into the basket).
    assert not _qual_together(result, "ev_pos_a", "ev_unrelated")


def test_e2e_infra_none_fail_closed_run_completes(monkeypatch):
    """ON + a cross-encoder that fails (non-OOM) => entails_directional returns None => the
    paraphrase pair fails-closed to singletons; NO basket forms and dedup_by_finding COMPLETES
    (never raises)."""
    _base_env(monkeypatch)
    monkeypatch.setenv("PG_FINDING_DEDUP_NLI", "1")
    monkeypatch.setattr(cnli, "_load_model", lambda *a, **k: _RaisingCrossEncoder())

    result = dedup_by_finding(_rows_e2e(), gov_suffixes=_gov(), domain=None)
    assert result.qualitative_basket_count == 0, "an infra fault must fail-closed (no merge)"
    assert not _qual_together(result, "ev_pos_a", "ev_pos_b")


def _both_flags_env(monkeypatch):
    """The Wave-3 slate config: BOTH the legacy score_pairs union (master + sub) AND the new
    keystone are ON — the exact config the P1 both-flags-ON crash guard protects."""
    monkeypatch.setenv("PG_SWEEP_CREDIBILITY_REDESIGN", "on")
    monkeypatch.setenv("PG_FINDING_DEDUP_QUALITATIVE", "1")
    monkeypatch.setenv("PG_CONSOLIDATION_NLI", "1")             # master ON => legacy union active
    monkeypatch.setenv("PG_CONSOLIDATION_NLI_QUALITATIVE", "1")  # legacy qualitative union ON
    monkeypatch.setenv("PG_FINDING_DEDUP_NLI", "1")            # keystone ON
    monkeypatch.setenv("PG_CONSOLIDATION_NLI_WORKERS", "1")     # deterministic
    monkeypatch.setenv("PG_FINDING_DEDUP_NLI_WORKERS", "1")     # deterministic


def test_e2e_both_flags_on_raising_model_completes_no_abort(monkeypatch):
    """P1 REGRESSION: with BOTH flags ON (the Wave-3 slate), the legacy score_pairs union runs
    FIRST and RAISES on a non-OOM model fault. The guard must degrade that raise to a §-1.3-safe
    under-merge so dedup_by_finding COMPLETES (never aborts the paid run at the dedup step); the
    keystone's own None path then yields singletons => 0 merged baskets."""
    _both_flags_env(monkeypatch)
    monkeypatch.setattr(cnli, "_load_model", lambda *a, **k: _RaisingCrossEncoder())

    # Must NOT raise (pre-fix this aborted the run inside _apply_qualitative_nli_union).
    result = dedup_by_finding(_rows_e2e(), gov_suffixes=_gov(), domain=None)
    assert result.qualitative_basket_count == 0, "a dead model must fail-closed to 0 baskets"
    assert not _qual_together(result, "ev_pos_a", "ev_pos_b")


def test_e2e_both_flags_on_fake_model_forms_basket_keep_all(monkeypatch):
    """With BOTH flags ON + a working (fake) cross-encoder, the paraphrase pair consolidates into
    ONE basket and KEEP-ALL holds (every row survives, collapsed_row_count 0)."""
    _both_flags_env(monkeypatch)
    monkeypatch.setattr(cnli, "_load_model", lambda *a, **k: _FakeCrossEncoder())

    rows = _rows_e2e()
    result = dedup_by_finding(rows, gov_suffixes=_gov(), domain=None)
    assert result.qualitative_basket_count >= 1
    assert _qual_together(result, "ev_pos_a", "ev_pos_b"), "the paraphrase pair must consolidate"
    kept = {str(r.get("evidence_id")) for r in result.deduped_rows}
    for r in rows:
        assert str(r["evidence_id"]) in kept, "keep-all violated: a row went missing"
    assert len(result.deduped_rows) == len(rows)
    assert result.collapsed_row_count == 0
