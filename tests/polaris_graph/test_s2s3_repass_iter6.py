"""S2/S3 re-pass iter-6 (Fable) — offline unit tests for the consolidation fixes.

Covers, all general / question-agnostic:
  * Fix 1  — post-merge member re-verify SPLITS a fabricated corroborator + numbers-strict.
  * Fix 2a — rep-invariant unions byte-identical SINGLETON __unknown__ sentinels.
  * Fix 4a — new boilerplate/metadata rep classes (RIS tag, SSRN cover, preprint, fed chrome).
  * Fix 4b — all-chrome basket predicate + DEFAULT-OFF kill switch (fail-open on scanned prose).
  * Fix 6  — filename version-tail multi-group + parenthetical fold (mirror double-count).

Deterministic ``entail_fn`` seams — no GPU / no model. Pure-function where possible.
"""
import os

import pytest

os.environ.setdefault("PG_CONSOLIDATION_NLI", "1")  # activate an NLI path for the gated passes

from src.polaris_graph.synthesis import finding_dedup as fd


def _rank(ri: int) -> int:
    return -ri  # deterministic (lowest index = highest rank)


# ── Fix 6 — filename version-tail multi-group + parenthetical fold ──────────────
def test_fix6_multi_group_version_tail_folds_mirror():
    k1 = fd._url_basename_key({"source_url": "https://economics.mit.edu/files/Noy_Zhang_1.pdf"})
    k2 = fd._url_basename_key({"source_url": "https://economics.mit.edu/files/Noy_Zhang_1_0.pdf"})
    assert k1 and k1 == k2  # '_1' and '_1_0' fold to ONE work


@pytest.mark.parametrize("a,b", [
    ("https://x.org/labor_report(1).pdf", "https://x.org/labor_report.pdf"),
    ("https://x.org/eloundou_gpts-v2.pdf", "https://x.org/eloundou_gpts.pdf"),
])
def test_fix6_paren_and_v_suffix_fold(a, b):
    ka, kb = fd._url_basename_key({"source_url": a}), fd._url_basename_key({"source_url": b})
    assert ka and ka == kb


def test_fix6_does_not_over_strip_discriminative_id():
    # digits glued to letters ('wp10601') are NOT a version tail — the id is preserved.
    assert fd._url_basename_key({"source_url": "https://econstor.eu/cesifo1_wp10601.pdf"}) == "file:cesifo1_wp10601"


# ── Fix 4a — new boilerplate rep classes ───────────────────────────────────────
@pytest.mark.parametrize("text", [
    "KW  - artificial intelligence",
    "TY  - JOUR",
    "Electronic copy available at: https://ssrn.com/abstract=4637198",
    "Preprint Concept Paper This version is not peer-reviewed.",
    "Before sharing sensitive information, make sure you are on a federal government site.",
])
def test_fix4a_new_boilerplate_classes_detected(text):
    assert fd._is_boilerplate_or_metadata_line(text) is True


@pytest.mark.parametrize("text", [
    "Generative AI could expose 46% of jobs to task automation by 2035.",
    "The randomized trial reduced HbA1c by 2.1 percentage points versus placebo.",
])
def test_fix4a_genuine_claim_not_boilerplate(text):
    assert fd._is_boilerplate_or_metadata_line(text) is False


# ── Fix 2a — rep-invariant unions byte-identical singleton sentinels ────────────
def test_fix2a_byte_identical_singleton_unknown_sentinels_union():
    claim = "Generative AI could expose 46% of jobs to significant task automation."
    rows = [
        {"statement": claim, "evidence_id": "ev_A", "source_url": "https://openai.com/g.pdf"},
        {"statement": claim, "evidence_id": "ev_B", "source_url": "https://governance.ai/g.pdf"},
    ]
    groups = {("__unknown__", "ev_A", "s0"): [0], ("__unknown__", "ev_B", "s1"): [1]}
    merged, n = fd._apply_representative_invariant(
        dict(groups), rows, _rank, entail_fn=lambda x, y: True
    )
    assert len(merged) == 1 and sorted(next(iter(merged.values()))) == [0, 1]


def test_fix2a_multi_member_sentinel_pool_stays_excluded():
    claim = "Generative AI could expose 46% of jobs to significant task automation."
    rows = [{"statement": claim, "evidence_id": "ev_A"}, {"statement": claim, "evidence_id": "ev_B"}]
    groups = {("__unknown__", "ev_A", "s0"): [0, 1]}
    merged, _ = fd._apply_representative_invariant(
        dict(groups), rows, _rank, entail_fn=lambda x, y: True
    )
    assert len(merged) == 1  # untouched (guard preserved, no crash)


# ── Fix 1 — post-merge member re-verify (anti-fabrication) ─────────────────────
def test_fix1_splits_fabricated_corroborator_keeps_genuine():
    pwbm = "AI raises total factor productivity and GDP by 1.5% by 2035."
    springer = "Impact and cost-benefit analysis: a unifying approach to project appraisal."
    rows = [
        {"statement": pwbm, "evidence_id": "ev_pwbm", "source_url": "https://pwbm.org/a.pdf"},
        {"statement": springer, "evidence_id": "ev_689", "source_url": "https://springer.com/b.pdf"},
        {"statement": pwbm, "evidence_id": "ev_pwbm2", "source_url": "https://mirror.org/c.pdf"},
    ]
    grp = {("ai", "raises", 1.5, "%"): [0, 1, 2]}

    def entail_pwbm_only(x, y):
        return bool(("1.5" in x) and ("1.5" in y)
                    and "productivity" in x.lower() and "productivity" in y.lower())

    out, split = fd._apply_post_merge_reverify(dict(grp), rows, _rank, entail_fn=entail_pwbm_only)
    assert split >= 1
    kept = [set(v) for v in out.values() if len(v) >= 2]
    assert kept == [{0, 2}]  # only the two byte-identical PWBM copies stay merged


def test_fix1_numbers_strict_splits_member_without_value():
    rows = [
        {"statement": "Unemployment rose by 3.1 percent in 2024.", "evidence_id": "e1"},
        {"statement": "The labor force participation rate changed notably.", "evidence_id": "e2"},
    ]
    grp = {("unemp", "rose", 3.1, "%"): [0, 1]}
    out, split = fd._apply_post_merge_reverify(dict(grp), rows, _rank, entail_fn=lambda x, y: True)
    assert split == 1  # e2 lacks '3.1' => split even though entail_fn says True


def test_fix1_default_on():
    assert fd._post_merge_reverify_enabled() is True


# ── Fix 4b — all-chrome basket predicate + DEFAULT-OFF flag ─────────────────────
def test_fix4b_flag_default_off():
    assert fd._chrome_basket_delete_enabled() is False


def test_fix4b_chrome_predicate_and_failopen():
    assert fd._row_has_mergeable_claim(
        {"statement": "AI displaced 300 million full-time jobs worldwide."}
    ) is True
    assert fd._row_has_mergeable_claim(
        {"statement": "KW  - artificial intelligence KW  - generative AI"}
    ) is False
    # fail-open: a spaced/scanned-PDF abstract collapses to a claim => NOT chrome.
    spaced = "W e   i n v e s t i g a t e   t h e   e f f e c t s   o f   A I   o n   l a b o r   m a r k e t s ."
    assert fd._row_has_mergeable_claim({"statement": spaced}) is True
