"""S2/S3 re-pass iter-4 (Fable full-list) — the NEW deltas, offline (no GPU/LLM).

Covers, general + question-agnostic:
  P0-1  boilerplate/heading MERGE guard: a byte-identical HEADING / license / metadata line is
        NOT a claim and must never byte-identical/NLI-merge two DIFFERENT works, while a genuine
        byte-identical CLAIM sentence still unions (Weizenbaum / Eloundou 46%).
  Fix 6 claim-bearing / non-boilerplate representative choice.
  Fix 3 SSRN dual URL form (papers.cfm?abstract_id= AND Delivery.cfm?abstractid=) => one work id.
  P0-2/fix 9  consolidation_nli scoring telemetry (scored_pairs / total_pairs), scored==0 loud.
"""
import os

from src.polaris_graph.synthesis import finding_dedup as fd
from src.polaris_graph.synthesis import consolidation_nli as cnli


# ── P0-1 predicates ────────────────────────────────────────────────────────
def test_boilerplate_metadata_detector_general():
    assert fd._is_boilerplate_or_metadata_line(
        "This article is distributed under the terms of the Creative Commons Attribution License."
    )
    assert fd._is_boilerplate_or_metadata_line("Keywords: generative AI, labor, automation")
    assert fd._is_boilerplate_or_metadata_line("JEL classification: J23, O33")
    assert fd._is_boilerplate_or_metadata_line("This work is licensed under CC BY 4.0.")
    assert fd._is_boilerplate_or_metadata_line("Corresponding author: e-mail: a@b.edu")
    # a real claim is NOT boilerplate (fail toward False so a claim is never force-split)
    assert not fd._is_boilerplate_or_metadata_line(
        "Generative AI could expose 46% of tasks to automation by 2030."
    )


def test_claim_bearing_sentence_ignores_trailing_citation():
    # a real claim with a trailing provenance token stays claim-bearing (rung-0 case)
    assert fd._is_claim_bearing_sentence("AI will displace 300 million jobs. [#ev:e1:0-30]")
    # a bare heading / label is not a claim
    assert not fd._is_claim_bearing_sentence("Cost-benefit analysis")
    assert not fd._is_claim_bearing_sentence("Table 3")


def test_sentence_mergeable_blocks_boilerplate_keeps_claim():
    assert fd._sentence_mergeable("Generative AI could expose 46% of tasks to automation.")
    assert not fd._sentence_mergeable("This work is licensed under CC BY 4.0.")
    assert not fd._sentence_mergeable("Cost-benefit analysis")


# ── P0-1 rung-0: boilerplate byte-identical must NOT collapse; claim still does ──
def test_rung0_does_not_collapse_byte_identical_boilerplate():
    boiler = "This work is licensed under the Creative Commons Attribution License."
    rows = [
        {"evidence_id": "a", "direct_quote": boiler, "authority_score": 0.9},
        {"evidence_id": "b", "direct_quote": boiler, "authority_score": 0.8},
    ]
    groups = {("__unknown__", "a", 0): [0], ("__unknown__", "b", 0): [1]}
    _merged, collapsed = fd._apply_rung0_exact_collapse(groups, rows, lambda ri: (0.0, -ri))
    assert collapsed == 0, "byte-identical BOILERPLATE must not merge two different works"


def test_rung0_still_collapses_byte_identical_claim():
    claim = "AI will displace 300 million jobs by 2030."
    rows = [
        {"evidence_id": "a", "direct_quote": claim, "authority_score": 0.9},
        {"evidence_id": "b", "direct_quote": claim, "authority_score": 0.8},
    ]
    groups = {("__unknown__", "a", 0): [0], ("__unknown__", "b", 0): [1]}
    _merged, collapsed = fd._apply_rung0_exact_collapse(groups, rows, lambda ri: (0.0, -ri))
    assert collapsed == 1, "byte-identical CLAIM sentences must still union"


# ── P0-1 split-confirm: boilerplate members split even when the judge says merge ──
def test_split_confirm_splits_boilerplate_even_if_entail_true():
    boiler = "This paper is made available under the Creative Commons license 4.0 terms."
    rows = [
        {"evidence_id": "a", "direct_quote": boiler, "authority_score": 0.9},
        {"evidence_id": "b", "direct_quote": boiler, "authority_score": 0.8},
        {"evidence_id": "c", "direct_quote": boiler, "authority_score": 0.7},
    ]
    key = ("licensed work", "is", 4.0, "", "", "", "")
    groups = {key: [0, 1, 2]}
    out = fd._confirm_numeric_clusters_via_nli(
        groups, rows, lambda ri: (rows[ri]["authority_score"], -ri),
        entail_fn=lambda a, b: True,  # judge would MERGE — the guard must still split
    )
    # rep stays; the two boilerplate members split to their own singletons.
    assert len(out) == 3
    assert all(len(v) == 1 for v in out.values())


def test_split_confirm_keeps_byte_identical_claim_merged():
    claim = "Generative AI could expose 46 percent of tasks to automation."
    rows = [
        {"evidence_id": "a", "direct_quote": claim, "authority_score": 0.9},
        {"evidence_id": "b", "direct_quote": claim, "authority_score": 0.8},
    ]
    key = ("tasks", "expose", 46.0, "", "", "", "")
    groups = {key: [0, 1]}
    out = fd._confirm_numeric_clusters_via_nli(
        groups, rows, lambda ri: (rows[ri]["authority_score"], -ri),
        entail_fn=lambda a, b: None,  # judge unavailable — byte-identical CLAIM still merges
    )
    assert len(out) == 1
    assert sorted(next(iter(out.values()))) == [0, 1]


# ── Fix 6: claim-bearing / non-boilerplate representative ───────────────────
def test_representative_prefers_claim_over_boilerplate():
    rows = [
        {"evidence_id": "meta", "direct_quote": "Keywords: labor, automation, AI",
         "authority_score": 0.95},
        {"evidence_id": "claim",
         "direct_quote": "Generative AI could expose 46 percent of tasks to automation.",
         "authority_score": 0.5},
    ]
    rep = fd._choose_clean_representative([0, 1], lambda ri: (rows[ri]["authority_score"], -ri), rows)
    assert rep == 1, "a claim-bearing member must be preferred over a higher-ranked keyword line"


# ── Fix 3: SSRN dual URL form => one work id ────────────────────────────────
def test_ssrn_dual_form_same_work_id():
    a = fd._url_work_identifier(
        {"source_url": "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5136877"}
    )
    b = fd._url_work_identifier(
        {"source_url": "https://download.ssrn.com/Delivery.cfm?abstractid=5136877"}
    )
    assert a == b == "ssrn:5136877"
    # distinct ids stay distinct works
    c = fd._url_work_identifier(
        {"source_url": "https://download.ssrn.com/Delivery.cfm?abstractid=4375283"}
    )
    assert c == "ssrn:4375283" and c != a


# ── P0-2 / fix 9: scoring telemetry ─────────────────────────────────────────
def _neutral_stub(batch):
    # [contradiction, entailment, neutral] — neutral wins => no entailment edges
    return [[0.0, 0.0, 1.0] for _ in batch]


def test_score_stats_populated_on_normal_run():
    cnli.score_pairs(["alpha", "beta", "gamma"], workers=1, predict_fn=_neutral_stub)
    st = cnli.get_last_score_stats()
    assert st["n_texts"] == 3
    assert st["total_pairs"] == 3
    assert st["candidate_pairs"] == 3
    assert st["scored_pairs"] == 3
    assert st["truncated"] is False
    assert st["over_cap_skipped"] is False


def test_score_stats_flags_over_cap_skip_as_blind():
    os.environ["PG_CONSOLIDATION_NLI_EMBED_BLOCK"] = "0"
    os.environ["PG_CONSOLIDATION_NLI_SUBBUCKET"] = "0"
    try:
        edges = cnli.score_pairs(
            ["a", "b", "c", "d"], workers=1, max_pairs=1, predict_fn=_neutral_stub,
        )
    finally:
        os.environ.pop("PG_CONSOLIDATION_NLI_EMBED_BLOCK", None)
        os.environ.pop("PG_CONSOLIDATION_NLI_SUBBUCKET", None)
    assert edges == []
    st = cnli.get_last_score_stats()
    # the loud run-validity signal: total > 0 but scored == 0 (the judge saw nothing)
    assert st["total_pairs"] > 0 and st["scored_pairs"] == 0
    assert st["over_cap_skipped"] is True
