"""S2/S3 re-pass iter-8 (Fable full-list) regression tests.

Deterministic + offline: every judge / embedder is injected as a stub, so no model download and
no network. Covers the mandate edge cases (Fix 10) + the P0/P1 fixes:

  Fix 1  — semantic recall consolidation: paraphrase baskets merge; a different-number pair NEVER
           merges (numbers-strict nomination guard); empty / <3-basket inputs are inert.
  Fix 2b — byte-identical cross-work split-outs collapse into ONE basket (no duplicate cg).
  Fix 2c — a non-confirming SAME-WORK member is kept in the basket, not split to a phantom sibling.
  Fix 4  — masthead / license / address / cover-page metadata lines are non-mergeable.
  Fix 8  — a supplementary-material file basename folds into its parent work.
"""
from __future__ import annotations

import pytest

from src.polaris_graph.synthesis import finding_dedup as fd


# ── shared stubs ─────────────────────────────────────────────────────────────
def _rank(ri: int) -> tuple:
    return (0.0, 0.0, -ri)


def _row(eid: str, text: str, url: str = "") -> dict:
    return {"evidence_id": eid, "statement": text, "direct_quote": text, "source_url": url}


# ── Fix 1: semantic recall consolidation ─────────────────────────────────────
def test_semantic_recall_merges_paraphrase_but_not_different_number():
    # Three single-member qualitative baskets; A and B paraphrase the SAME 5.5% claim, C asserts a
    # DIFFERENT number (0.4%). The stub embedder nominates A-B and A-C; the stub judge would entail
    # BOTH, but the numbers-strict nomination guard must SKIP A-C (different number) and only A-B
    # may merge.
    rows = [
        _row("ev_a", "Generative AI could expose about 5.5 percent of employment in high income countries."),
        _row("ev_b", "Roughly 5.5% of jobs in wealthy countries are potentially exposed to generative AI."),
        _row("ev_c", "Only 0.4 percent of employment in low income countries is exposed to automation."),
    ]
    groups = {("__qual__", "a"): [0], ("__qual__", "b"): [1], ("__qual__", "c"): [2]}

    def stub_pairs(texts, max_pairs, *, topk=None, embed_fn=None):
        return [(0, 1), (0, 2)]

    def stub_entail(a, b):
        return True  # the judge would merge everything; the numeric guard must gate it

    out, merged = fd._apply_semantic_recall_consolidation(
        groups, rows, _rank, entail_fn=stub_entail, embed_pairs_fn=stub_pairs,
    )
    assert merged == 1, "A-B (same 5.5%) must merge; A-C (0.4% vs 5.5%) must not"
    # A and B collapse into one key; C stays separate => 2 surviving baskets.
    assert len(out) == 2
    sizes = sorted(len(v) for v in out.values())
    assert sizes == [1, 2]


def test_semantic_recall_no_merge_when_judge_refuses():
    rows = [
        _row("ev_a", "Generative AI raises measured worker productivity by 14 percent in support roles."),
        _row("ev_b", "Automation lowered manufacturing employment by 14 percent over the decade."),
        _row("ev_c", "A third unrelated claim about 14 percent of something else entirely here today."),
    ]
    groups = {("__qual__", "a"): [0], ("__qual__", "b"): [1], ("__qual__", "c"): [2]}

    def stub_pairs(texts, max_pairs, *, topk=None, embed_fn=None):
        return [(0, 1)]

    def stub_entail(a, b):
        return False  # antonym / different claim — judge refuses

    out, merged = fd._apply_semantic_recall_consolidation(
        groups, rows, _rank, entail_fn=stub_entail, embed_pairs_fn=stub_pairs,
    )
    assert merged == 0
    assert len(out) == 3


def test_semantic_recall_inert_on_empty_and_single():
    assert fd._apply_semantic_recall_consolidation({}, [], _rank)[1] == 0
    rows = [_row("ev_a", "A single lonely claim about generative AI and the labor market today.")]
    assert fd._apply_semantic_recall_consolidation({("__qual__", "a"): [0]}, rows, _rank)[1] == 0


def test_semantic_recall_embedder_failure_fails_open_keep():
    rows = [
        _row("ev_a", "Generative AI could expose about 5.5 percent of employment across the economy."),
        _row("ev_b", "Roughly 5.5% of jobs are potentially exposed to generative AI in the economy."),
        _row("ev_c", "Roughly 5.5% of positions face generative AI exposure across the whole economy."),
    ]
    groups = {("__qual__", "a"): [0], ("__qual__", "b"): [1], ("__qual__", "c"): [2]}

    def boom(texts, max_pairs, *, topk=None, embed_fn=None):
        raise RuntimeError("embedder down")

    out, merged = fd._apply_semantic_recall_consolidation(
        groups, rows, _rank, entail_fn=lambda a, b: True, embed_pairs_fn=boom,
    )
    assert merged == 0 and len(out) == 3  # fail-open: no basket merged, none dropped


# ── Fix 2c: same-work member kept; Fix 2b: byte-identical split-outs collapse ─
def test_same_work_member_kept_not_split():
    # rep + a non-confirming member from the SAME evidence row (same paper chunk). The judge refuses;
    # Fix 2(c) must KEEP the member in the basket, not split it into a phantom sibling.
    rows = [
        _row("ev_1", "Generative AI could expose about 5.5 percent of employment in high income countries."),
        _row("ev_1", "The same paper also discusses adoption barriers among small and medium firms broadly."),
    ]
    groups = {("__qual__", "x"): [0, 1]}
    out, split = fd._apply_post_merge_reverify(
        groups, rows, _rank, entail_fn=lambda a, b: False,
    )
    assert split == 0, "same-work non-confirm must not split"
    # exactly one basket carrying both members, no __reverify_split__ key
    assert len(out) == 1
    assert all("__reverify_split__" not in k for k in out)
    assert sorted(next(iter(out.values()))) == [0, 1]


def test_cross_work_member_splits():
    rows = [
        _row("ev_1", "Generative AI could expose about 5.5 percent of employment in high income countries."),
        _row("ev_2", "A completely different claim about robotics and manufacturing wages in the 1990s era."),
    ]
    groups = {("__qual__", "x"): [0, 1]}
    out, split = fd._apply_post_merge_reverify(
        groups, rows, _rank, entail_fn=lambda a, b: False,
    )
    assert split == 1
    assert any("__reverify_split__" in k for k in out)


def test_byte_identical_cross_work_split_outs_collapse():
    # Two cross-work members with a BYTE-IDENTICAL visible claim must collapse into ONE emitted key
    # (so downstream they cannot hash to a duplicate claim_group_id).
    out: dict = {}
    key = ("__qual__", "x")
    ident = "Automation could displace three hundred million jobs worldwide over the coming decade."
    rows = [
        _row("ev_0", "rep sentence carrying the basket claim about generative AI exposure levels."),
        _row("ev_1", ident, "http://a.example/x"),
        _row("ev_2", ident, "http://b.example/y"),  # DIFFERENT host/work, identical claim
        _row("ev_3", "A distinct third claim about wage compression in clerical occupations lately."),
    ]
    n_keys = fd._emit_reverify_split_members(out, key, [1, 2, 3], rows)
    # ev_1 + ev_2 (byte-identical) => ONE key with both; ev_3 => its own key. Total 2 keys.
    assert n_keys == 2
    sizes = sorted(len(v) for v in out.values())
    assert sizes == [1, 2]


# ── Fix 2c helper: same-work detection ───────────────────────────────────────
def test_member_same_work_by_evidence_and_key():
    a = _row("ev_1", "x", "http://arxiv.org/abs/2303.10130")
    b = _row("ev_1", "y", "http://other.example/z")  # same evidence_id
    c = _row("ev_9", "z", "http://ideas.repec.org/p/arx/papers/2303.10130.html")  # same arxiv work
    d = _row("ev_8", "w", "http://unrelated.example/paper")
    assert fd._member_same_work_as_rep(b, a) is True   # same evidence_id
    assert fd._member_same_work_as_rep(c, a) is True   # same arXiv work id, different host
    assert fd._member_same_work_as_rep(d, a) is False


# ── Fix 4: masthead / license / address / cover-page metadata ────────────────
@pytest.mark.parametrize("line", [
    "CC0 1.0 Universal Public Domain Dedication applies to this dataset.",
    "Impressum",
    "This paper was Prepared by the staff of the International Monetary Fund; Authorized for distribution.",
    "Authored By: A. Researcher 1 of 3",
    "Mann This version: January 2024",
    "CEPR Press, Paris & London.",
    "Whiteknights House 21 Earley Gate Reading Road",
])
def test_boilerplate_metadata_new_classes(line):
    assert fd._is_boilerplate_or_metadata_line(line) is True
    assert fd._sentence_mergeable(line) is False


@pytest.mark.parametrize("claim", [
    "Generative AI could raise the productivity of support agents by 14 percent overall.",
    "The study found that 5.5 percent of employment is exposed to automation in high income countries.",
    "Only 0.4 percent of low income country employment faces near term automation pressure.",
])
def test_real_claims_are_not_boilerplate(claim):
    assert fd._is_boilerplate_or_metadata_line(claim) is False


# ── Fix 8: supplementary-material folding ────────────────────────────────────
def test_supplement_file_folds_into_parent():
    parent = _row("ev_1", "x", "https://econ.example/papers/doshi_hauser.pdf")
    supp = _row("ev_2", "y", "https://econ.example/papers/doshi_hauser_sm.pdf")
    kp = fd._url_basename_key(parent)
    ks = fd._url_basename_key(supp)
    assert kp and ks and kp == ks, f"parent={kp!r} supplement={ks!r} must fold to one work"


def test_supplement_bare_marker_not_over_folded():
    # A bare 'appendix' / 'sm' basename with no parent stem must not fold to a generic key.
    bare = _row("ev_1", "x", "https://site.example/files/appendix.pdf")
    assert fd._url_basename_key(bare) == ""  # generic / too short after strip => no key


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
