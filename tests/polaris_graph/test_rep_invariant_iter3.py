"""Offline unit tests for the Fable Fix 1(d) representative-invariant post-pass and the
numeric split-confirm byte-identical short-circuit (S2/S3 re-pass iter-3).

Deterministic: the NLI is a test seam (``entail_fn``) — no GPU / cross-encoder loaded. These
reproduce the drb_72 false-split root cause (a byte-identical / same-visible-claim finding
landing in two baskets because the split-confirm fails open on an NLI ``None``) and prove the
fix repairs it WITHOUT ever merging two genuinely-distinct claims.
"""
import os

os.environ["PG_FINDING_REP_INVARIANT"] = "1"
os.environ["PG_FINDING_NUMERIC_NLI_CONFIRM"] = "1"
os.environ["PG_FINDING_NUMERIC_NLI_CONFIRM_STRICT"] = "1"
os.environ["PG_CONSOLIDATION_NLI"] = "0"          # keep the invariant's entail leg off (byte-identical only)
os.environ["PG_FINDING_DEDUP_NLI"] = "0"

from src.polaris_graph.synthesis import finding_dedup as fd  # noqa: E402


def _row(body, auth=0.5, rel=0.5):
    return {"direct_quote": body, "authority_score": auth, "selection_relevance": rel}


def _rank(rows):
    return lambda ri: (
        float(rows[ri].get("authority_score", 0.0) or 0.0),
        float(rows[ri].get("selection_relevance", 0.0) or 0.0),
        -ri,
    )


SENT_46 = "When accounting for likely future software developments that complement LLM capabilities, this share jumps to just over 46% of jobs."


def test_invariant_merges_byte_identical_visible_reps():
    # Two copies of the SAME 46% finding: one clean abstract, one wrapped in nav chrome.
    rows = [
        _row(SENT_46),
        _row("Login Subscribe Menu About Research. " + SENT_46),
    ]
    # split-confirm has already split them into two separate keys (the drb_72 shape).
    groups = {
        ("capabilities", "share", 46.0, "percent", "", "", ""): [0],
        ("capabilities", "share", 46.0, "percent", "", "", "", "__split__", 1): [1],
    }
    out, merged = fd._apply_representative_invariant(groups, rows, _rank(rows))
    assert merged == 1, (merged, list(out.keys()))
    assert len(out) == 1
    members = sorted(next(iter(out.values())))
    assert members == [0, 1], members


def test_invariant_keeps_distinct_claims_separate():
    rows = [
        _row("About 46% of all worker tasks could be completed faster with an LLM."),
        _row("One more robot per thousand workers reduces employment by 0.2 percentage points."),
    ]
    groups = {
        ("tasks", "share", 46.0, "percent", "", "", ""): [0],
        ("employment", "reduces", 0.2, "points", "", "", ""): [1],
    }
    out, merged = fd._apply_representative_invariant(groups, rows, _rank(rows))
    assert merged == 0, merged
    assert len(out) == 2


def test_split_confirm_shortcircuits_identical_on_nli_none():
    # Three byte-identical copies (same PDF fetched thrice) sharing ONE numeric key. A
    # cross-encoder that returns None on every pair (the observed drb_72 infra answer) would,
    # under strict split, shatter them into 3 singletons — the short-circuit keeps them merged.
    body = "18 The lesson from these prior experiences is that the parties who deploy these tools matter."
    rows = [_row(body), _row(body), _row(body)]
    groups = {("what", "percentage", 18.0, "", "", "", ""): [0, 1, 2]}
    out = fd._confirm_numeric_clusters_via_nli(
        groups, rows, _rank(rows), entail_fn=lambda a, b: None,
    )
    # exactly one surviving cluster carrying all three members (no __split__ singletons).
    assert len(out) == 1, list(out.keys())
    assert sorted(next(iter(out.values()))) == [0, 1, 2]


def test_split_confirm_still_splits_genuinely_different_on_confident_no():
    # A confident non-entailment (False) still splits — the short-circuit only spares
    # byte-identical claim sentences, never a real different claim on a key collision.
    rows = [
        _row("About 15% of all worker tasks could be completed faster with an LLM."),
        _row("Roughly 15 percent of firms reported reduced headcount after adoption, a different measure."),
    ]
    groups = {("share", "is", 15.0, "percent", "", "", ""): [0, 1]}
    out = fd._confirm_numeric_clusters_via_nli(
        groups, rows, _rank(rows), entail_fn=lambda a, b: False,
    )
    assert len(out) == 2, list(out.keys())


if __name__ == "__main__":
    test_invariant_merges_byte_identical_visible_reps()
    test_invariant_keeps_distinct_claims_separate()
    test_split_confirm_shortcircuits_identical_on_nli_none()
    test_split_confirm_still_splits_genuinely_different_on_confident_no()
    print("ALL REP-INVARIANT TESTS PASSED")
