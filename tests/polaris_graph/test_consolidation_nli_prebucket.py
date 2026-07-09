"""I-deepfix-001 W04-prebucket (#1369): over-MAX_PAIRS PRE-BUCKETING fire-test.

EVIDENCE (drb_72 live run): two large buckets (311 and 351 texts -> 48,205 / 61,425
candidate pairs) exceeded PG_CONSOLIDATION_NLI_MAX_PAIRS=20,000, so `score_pairs`
SKIPPED the NLI consolidation for the WHOLE bucket -> near-duplicate findings stayed
UNMERGED -> the report rendered the same claim REPEATEDLY instead of once with grouped
citations. A blind cap raise would re-open the O(n^2) compute/memory blowup the cap
guards; the fix PRE-BUCKETS an over-cap bucket into lexical-overlap sub-buckets whose
per-sub-bucket pair count stays <= the cap, then runs the NLI within each sub-bucket.

This test freezes a synthetic 320-text bucket (51,040 pairs > the 20,000 cap) with:
  * 8 planted near-duplicate paraphrase groups x 5 members (the repetition to merge);
  * 250 same-family DISTINCT claims sharing a broad token core (forces the size-cap
    split of one lexical sub-bucket into 200 + 50);
  * 30 unrelated singleton claims.
The cross-encoder is a deterministic stub injected via the `predict_fn` seam (no GPU,
no model download). GREEN iff, with the flag ON: (a) consolidation is NOT skipped and
runs; (b) every sub-bucket's pair count <= the cap; (c) every planted near-dup group
MERGES into one basket carrying ALL members (citations preserved on the survivor);
(d) the distinct-claim count is exactly preserved (nothing dropped, no false merge);
(e) with the flag OFF the over-cap skip reproduces byte-identically (no scoring at
all, empty edge set, the SKIPPING telemetry fires).

§-1.3 CONSOLIDATE-keep-all: near-dups MERGE with all member citations kept; a
cross-sub-bucket near-dup pair simply stays unmerged (KEEP — never worse than the
skip); no basket is dropped; the faithfulness engine (strict_verify / NLI entailment
verifier / 4-role D8 / provenance / span-grounding) is untouched — this is the
CONSOLIDATION (grouping) NLI only.

Standalone runnable (seconds, offline):
    PYTHONIOENCODING=utf-8 PYTHONPATH=C:/POLARIS python tests/polaris_graph/test_consolidation_nli_prebucket.py
"""
from __future__ import annotations

import logging
import os
from contextlib import contextmanager

import src.polaris_graph.synthesis.consolidation_nli as cnli

CAP = 20000
N_GROUPS = 8
GROUP_SIZE = 5
N_FAMILY = 250
N_SINGLETONS = 30
N_TEXTS = N_GROUPS * GROUP_SIZE + N_FAMILY + N_SINGLETONS  # 320
EXPECTED_DISTINCT = N_TEXTS - N_GROUPS * (GROUP_SIZE - 1)  # 320 - 32 = 288


# ─────────────────────────────────────────────────────────────────────────
# Frozen synthetic bucket + deterministic cross-encoder stub
# ─────────────────────────────────────────────────────────────────────────
def _build_bucket() -> tuple[list[str], dict[int, int | None]]:
    """320 texts; `group_of[i]` = planted near-dup group id, or None for distinct."""
    texts: list[str] = []
    group_of: dict[int, int | None] = {}
    # 8 planted near-duplicate paraphrase groups (5 members each) — high lexical
    # overlap, exactly the same-claim repetition the consolidation must merge.
    for g in range(N_GROUPS):
        drug = f"alphadrug{g}"
        variants = [
            f"treatment {drug} reduces mortality risk substantially in the trial cohort patients",
            f"the trial cohort shows treatment {drug} substantially reduces mortality risk for patients",
            f"mortality risk falls substantially with treatment {drug} across the trial cohort patients",
            f"patients in the trial cohort on treatment {drug} show substantially reduced mortality risk",
            f"substantially reduced mortality risk observed for trial cohort patients receiving treatment {drug}",
        ]
        for v in variants:
            group_of[len(texts)] = g
            texts.append(v)
    # 250 same-family DISTINCT claims sharing a broad token core: they route into one
    # lexical sub-bucket that OVERFLOWS the size cap (200) and must split (200 + 50).
    for i in range(N_FAMILY):
        group_of[len(texts)] = None
        texts.append(
            f"global energy market report volume{i} discusses infrastructure "
            f"investment segment{i} outlook findings"
        )
    # 30 unrelated singleton claims (mutually low overlap => singleton sub-buckets).
    for i in range(N_SINGLETONS):
        group_of[len(texts)] = None
        texts.append(f"unrelated{i} zebra{i} orbit{i} quartz{i} meadow{i} statement")
    assert len(texts) == N_TEXTS
    return texts, group_of


def _make_stub(texts: list[str], group_of: dict[int, int | None]):
    """Deterministic 3-way-logit stub in nli-deberta label order [contradiction,
    entailment, neutral]: bidirectional ENTAILMENT iff both texts belong to the SAME
    planted near-dup group; NEUTRAL otherwise. Counts calls for the flag-OFF assert."""
    text_group = {t: group_of[i] for i, t in enumerate(texts)}
    calls = {"batches": 0, "rows": 0}

    def predict(batch):
        calls["batches"] += 1
        calls["rows"] += len(batch)
        out = []
        for premise, hypothesis in batch:
            ga, gb = text_group[premise], text_group[hypothesis]
            if ga is not None and ga == gb and premise != hypothesis:
                out.append([0.0, 5.0, 0.0])  # entailment argmax (both directions)
            else:
                out.append([0.0, 0.0, 5.0])  # neutral argmax => no edge
        return out

    return predict, calls


@contextmanager
def _subbucket_flag(value: str | None):
    old = os.environ.get(cnli.ENV_SUBBUCKET)
    try:
        if value is None:
            os.environ.pop(cnli.ENV_SUBBUCKET, None)
        else:
            os.environ[cnli.ENV_SUBBUCKET] = value
        yield
    finally:
        if old is None:
            os.environ.pop(cnli.ENV_SUBBUCKET, None)
        else:
            os.environ[cnli.ENV_SUBBUCKET] = old


@contextmanager
def _capture_logs():
    class _Capture(logging.Handler):
        def __init__(self):
            super().__init__()
            self.messages: list[str] = []

        def emit(self, record):
            self.messages.append(record.getMessage())

    handler = _Capture()
    cnli.logger.addHandler(handler)
    old_level = cnli.logger.level
    cnli.logger.setLevel(logging.DEBUG)
    try:
        yield handler.messages
    finally:
        cnli.logger.removeHandler(handler)
        cnli.logger.setLevel(old_level)


# ─────────────────────────────────────────────────────────────────────────
# (a) + (c) + (d): flag ON => NOT skipped; planted groups MERGE keep-all;
#                  distinct-claim count exactly preserved (nothing dropped)
# ─────────────────────────────────────────────────────────────────────────
def test_flag_on_runs_and_merges_planted_near_dups():
    texts, group_of = _build_bucket()
    predict, calls = _make_stub(texts, group_of)
    with _subbucket_flag("1"), _capture_logs() as messages:
        mapping = cnli.group_clusters(texts, workers=2, max_pairs=CAP, predict_fn=predict)
    # (a) NOT skipped: the scoring actually ran on the over-cap bucket ...
    assert calls["batches"] > 0 and calls["rows"] > 0, "cross-encoder stub never invoked"
    assert not any("SKIPPING NLI consolidation" in m for m in messages), (
        "over-cap bucket was still SKIPPED with the pre-bucket flag ON"
    )
    # ... and the pre-bucket telemetry fired loud (never silent).
    assert any("PRE-BUCKETING" in m for m in messages), "pre-bucket telemetry missing"
    # keep-all: EVERY input index appears in the mapping (no basket dropped).
    assert set(mapping.keys()) == set(range(N_TEXTS))
    # (c) every planted near-dup group merges into ONE basket rooted at its lowest
    # member index — repetition reduced from 5 renders to 1 consolidated basket.
    for g in range(N_GROUPS):
        members = list(range(g * GROUP_SIZE, (g + 1) * GROUP_SIZE))
        roots = {mapping[m] for m in members}
        assert roots == {members[0]}, f"planted group {g} did not fully merge: {roots}"
    # citations preserved on the survivor: the root basket carries ALL member indices.
    baskets: dict[int, list[int]] = {}
    for idx, root in mapping.items():
        baskets.setdefault(root, []).append(idx)
    for g in range(N_GROUPS):
        members = set(range(g * GROUP_SIZE, (g + 1) * GROUP_SIZE))
        assert set(baskets[g * GROUP_SIZE]) == members, (
            f"group {g} survivor basket lost a member (citation dropped)"
        )
    assert sum(len(v) for v in baskets.values()) == N_TEXTS, "membership not keep-all"
    # (d) distinct-claim count EXACTLY preserved: 8 merged baskets + 280 untouched
    # singletons = 288 roots; every non-planted text maps to itself (no false merge).
    assert len(baskets) == EXPECTED_DISTINCT, (
        f"expected {EXPECTED_DISTINCT} distinct baskets, got {len(baskets)}"
    )
    for i in range(N_GROUPS * GROUP_SIZE, N_TEXTS):
        assert mapping[i] == i, f"distinct claim {i} was falsely merged into {mapping[i]}"


# ─────────────────────────────────────────────────────────────────────────
# (b): partition is complete + disjoint; every sub-bucket's pairs <= cap;
#      the size cap genuinely bites (the 250-text family splits)
# ─────────────────────────────────────────────────────────────────────────
def test_every_subbucket_pair_count_under_cap():
    texts, group_of = _build_bucket()
    sub_buckets = cnli._pre_bucket_indices(texts, CAP)
    # complete + disjoint: every index exactly once (nothing dropped, nothing doubled).
    flat = [i for bucket in sub_buckets for i in bucket]
    assert sorted(flat) == list(range(N_TEXTS))
    assert len(flat) == len(set(flat)) == N_TEXTS
    # per-sub-bucket pair count <= cap (the whole point of the pre-bucketing).
    size_cap = cnli._max_subbucket_size(CAP)
    for bucket in sub_buckets:
        k = len(bucket)
        assert k * (k - 1) // 2 <= CAP, f"sub-bucket of {k} exceeds the pair cap"
        assert k <= size_cap
    # non-vacuous: real multi-member sub-buckets exist.
    assert max(len(b) for b in sub_buckets) >= 2
    # each planted near-dup group is CO-BUCKETED (so the merge in test (c) is real,
    # not an accident of scoring order).
    bucket_of = {i: bi for bi, bucket in enumerate(sub_buckets) for i in bucket}
    for g in range(N_GROUPS):
        members = range(g * GROUP_SIZE, (g + 1) * GROUP_SIZE)
        assert len({bucket_of[m] for m in members}) == 1, f"group {g} split across sub-buckets"
    # the size cap genuinely bites: the 250-text lexical family cannot fit one
    # sub-bucket (cap 200), so its members span >= 2 sub-buckets.
    family = range(N_GROUPS * GROUP_SIZE, N_GROUPS * GROUP_SIZE + N_FAMILY)
    assert len({bucket_of[i] for i in family}) >= 2, "size cap never exercised"


def test_max_subbucket_size_math():
    assert cnli._max_subbucket_size(20000) == 200   # 200*199/2 = 19,900 <= 20,000
    assert cnli._max_subbucket_size(19900) == 200   # exact boundary
    assert cnli._max_subbucket_size(19899) == 199
    assert cnli._max_subbucket_size(1) == 2         # floor: one pair still scorable
    for m in (1, 3, 10, 4950, 19899, 19900, 20000, 61425):
        k = cnli._max_subbucket_size(m)
        assert k * (k - 1) // 2 <= max(m, 1) or k == 2


# ─────────────────────────────────────────────────────────────────────────
# (e): flag OFF => byte-identical over-cap SKIP (zero scoring, empty edges,
#      SKIPPING telemetry; group_clusters leaves everything unmerged)
# ─────────────────────────────────────────────────────────────────────────
def test_flag_off_reproduces_skip():
    texts, group_of = _build_bucket()
    predict, calls = _make_stub(texts, group_of)
    with _subbucket_flag(None), _capture_logs() as messages:
        edges = cnli.score_pairs(texts, workers=2, max_pairs=CAP, predict_fn=predict)
    assert edges == [], "flag OFF must return the empty edge set (skip)"
    assert calls["batches"] == 0, "flag OFF must never invoke the cross-encoder"
    assert any("SKIPPING NLI consolidation" in m for m in messages), "skip telemetry missing"
    assert not any("PRE-BUCKETING" in m for m in messages)
    # explicit "0" behaves like unset; group_clusters leaves every cluster unmerged.
    predict2, calls2 = _make_stub(texts, group_of)
    with _subbucket_flag("0"):
        mapping = cnli.group_clusters(texts, workers=2, max_pairs=CAP, predict_fn=predict2)
    assert calls2["batches"] == 0
    assert mapping == {i: i for i in range(N_TEXTS)}


# ─────────────────────────────────────────────────────────────────────────
# under-cap path unchanged with the flag ON (no pre-bucketing triggered)
# ─────────────────────────────────────────────────────────────────────────
def test_flag_on_under_cap_path_unchanged():
    texts, group_of = _build_bucket()
    small = texts[: 2 * GROUP_SIZE]  # groups 0 + 1 => 45 pairs, far under the cap
    predict, calls = _make_stub(texts, group_of)
    with _subbucket_flag("1"), _capture_logs() as messages:
        edges = cnli.score_pairs(small, workers=2, max_pairs=CAP, predict_fn=predict)
    assert not any("PRE-BUCKETING" in m for m in messages), "pre-bucket fired under cap"
    assert not any("SKIPPING NLI consolidation" in m for m in messages)
    expected = sorted(
        [(i, j) for i in range(5) for j in range(i + 1, 5)]
        + [(i, j) for i in range(5, 10) for j in range(i + 1, 10)]
    )
    assert edges == expected, "under-cap edge set changed"


if __name__ == "__main__":
    tests = [
        test_flag_on_runs_and_merges_planted_near_dups,
        test_every_subbucket_pair_count_under_cap,
        test_max_subbucket_size_math,
        test_flag_off_reproduces_skip,
        test_flag_on_under_cap_path_unchanged,
    ]
    for test in tests:
        test()
        print(f"OK   {test.__name__}")
    print(f"GREEN: {len(tests)}/{len(tests)} tests passed "
          f"(over-cap bucket = {N_TEXTS} texts / {N_TEXTS * (N_TEXTS - 1) // 2} pairs > cap {CAP})")
